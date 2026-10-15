#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

try:
    from scripts import followups_capture as capture
except ModuleNotFoundError:
    import followups_capture as capture


PLAN_REF = "docs/plans/260716_1046_fixture.md"
LEGACY_DERIVED_BANNER_LINE = (
    "_DO NOT EDIT - regenerate via `PYTHONDONTWRITEBYTECODE=1 "
    "python3 -B scripts/process_improvements_collect.py --project-root . "
    "--rebuild-derived`._"
)

class FollowupsContinuationCheckpointTests(unittest.TestCase):
    def _fixture(self, root: Path, *, materialized: bool = False):
        try:
            from scripts.test_docs_closeout import DocsCloseoutContinuationAdmissionTests, MODULE
        except ModuleNotFoundError:
            from test_docs_closeout import DocsCloseoutContinuationAdmissionTests, MODULE
        fixture = DocsCloseoutContinuationAdmissionTests()
        cycle = fixture._fixture(root, materialized=materialized)
        return fixture, MODULE, cycle

    def _payload(self, fixture, module, root, cycle):
        return module.classify_docs_closeout(root=root, plan_ref=fixture.plan_ref,
            bundle_payload=fixture._bundle(), followups_capture_cycle_id=cycle)

    def test_explicit_continuation_checkpoint_and_replay_preserve_general_objects(self) -> None:
        for materialized in (False, True):
            with self.subTest(materialized=materialized), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve(); fixture, module, cycle = self._fixture(root, materialized=materialized)
                receipt_path = fixture._receipt_path(root, cycle)
                before = fixture._objects(root); payload = self._payload(fixture, module, root, cycle)
                self.assertEqual(payload["followups_continuation_admission"]["state"], "ready")
                with mock.patch.object(capture, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()) as fresh:
                    result = capture.checkpoint_general_pi(root, fixture.plan_ref, cycle, docs_closeout_payload=payload)
                fresh.assert_called_once_with(root, fixture.plan_ref)
                self.assertEqual(result["reason_code"], "followup_capture_pi_general_checkpointed")
                after = fixture._objects(root)
                self.assertEqual([p for p in before if before[p] != after[p]], [receipt_path.relative_to(root).as_posix()])
                raw = receipt_path.read_bytes(); receipt = json.loads(raw)
                self.assertEqual(receipt["receipt_revision"], 2)
                replay = self._payload(fixture, module, root, cycle)
                with mock.patch.object(capture, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
                    result = capture.checkpoint_general_pi(root, fixture.plan_ref, cycle, docs_closeout_payload=replay)
                self.assertEqual(result["reason_code"], "followup_capture_pi_general_checkpoint_already_published")
                self.assertEqual(raw, receipt_path.read_bytes())
                self.assertEqual(after, fixture._objects(root))
                capture.prepare_role(root, fixture.plan_ref, cycle, "Architect")
                before_refusal = fixture._objects(root)
                with self.assertRaises(capture.CaptureError):
                    capture.checkpoint_general_pi(root, fixture.plan_ref, cycle, docs_closeout_payload=replay)
                self.assertEqual(before_refusal, fixture._objects(root))

    def test_checkpoint_refuses_missing_tampered_or_stale_admission_without_writes(self) -> None:
        for variant in ("missing", "malformed", "digest", "source", "inputs", "stale_checkpoint", "head", "semantic", "foreign", "protected", "collector"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve(); fixture, module, cycle = self._fixture(root)
                payload = self._payload(fixture, module, root, cycle); bundle = fixture._bundle()
                admission = payload["followups_continuation_admission"]
                if variant == "missing": payload.pop("followups_continuation_admission")
                elif variant == "malformed": admission["proof"] = []
                elif variant == "digest": admission["proof"]["receipt_sha256"] = "0" * 64
                elif variant == "source": admission["proof"]["source_identity"]["source_terminal_commit_oid"] = "1" * 40
                elif variant == "inputs": admission["proof"]["collector_inputs"]["Architect"] = "2" * 64
                elif variant == "stale_checkpoint": capture.checkpoint_general_pi(root, fixture.plan_ref, cycle)
                elif variant == "head":
                    (root / "unrelated.txt").write_text("new committed source HEAD\n")
                    subprocess.run(["git", "-C", str(root), "add", "unrelated.txt"], check=True, capture_output=True)
                    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                    "commit", "-qm", "source HEAD drift"], check=True, capture_output=True)
                elif variant == "semantic": bundle["closeout_kind"] = "staged_empty"
                elif variant in {"foreign", "protected"}:
                    path = root / ("docs/roles/manager.md" if variant == "protected" else "docs/foreign.md")
                    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("dirty docs\n")
                else:
                    path = root / capture.process_improvements_collect.capture_receipt_rel_path(fixture.plan_ref, "Architect", cycle)
                    receipt = json.loads(path.read_bytes()); receipt["input_sha256"] = "3" * 64; path.write_text(json.dumps(receipt))
                before = fixture._objects(root)
                with mock.patch.object(capture, "_fresh_continuation_bundle_payload", return_value=bundle):
                    with self.assertRaises(capture.CaptureError) as rejected:
                        capture.checkpoint_general_pi(root, fixture.plan_ref, cycle, docs_closeout_payload=payload)
                self.assertEqual(rejected.exception.reason_code, "followup_capture_continuation_admission_invalid")
                self.assertEqual(before, fixture._objects(root))

    def test_fresh_bundle_uses_existing_public_facade_and_exact_subject(self) -> None:
        with mock.patch.object(capture.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b'{"bundle_ok":true}')) as child:
            self.assertEqual(capture._fresh_continuation_bundle_payload(Path("/fixture"), PLAN_REF), {"bundle_ok": True})
        argv = child.call_args.args[0]
        self.assertEqual(argv[1:], ["--project", "/fixture", "planveyor_plan_bundle", "--closeout-json", PLAN_REF])
        self.assertEqual(Path(argv[0]).name, "planveyor")
        self.assertNotIn("TUI", " ".join(argv))


class GeneralPIFormatCorrectionTests(unittest.TestCase):
    clean = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
    malformed = "## Process improvements\nunsupported prose\n"

    def fixture(self, root: Path, role: str = "Coder", *, materialized: bool = False):
        try:
            from scripts.test_docs_closeout import DocsCloseoutContinuationAdmissionTests, MODULE
        except ModuleNotFoundError:
            from test_docs_closeout import DocsCloseoutContinuationAdmissionTests, MODULE
        fixture = DocsCloseoutContinuationAdmissionTests()
        cap = MODULE.followups_capture

        def collect(target, cycle, **_kwargs):
            for position, current in enumerate(cap.REQUIRED_ROLES):
                body = self.malformed if current == role else self.clean
                if materialized and position == 0 and current != role:
                    body = ("## Process improvements\n### Suggestion 1\n- symptom: correction prefix\n"
                            "- process_gap: exact prefix proof\n- suggested_fix: preserve prefix\n"
                            "- owner: Architect\n- promotion_class: helper_change\n- trigger_ref: unknown\n"
                            f"- source_ref: {fixture.plan_ref}\n")
                try:
                    cap.process_improvements_collect.collect_process_improvements(project_root=target,
                        role=current, source_ref=fixture.plan_ref, text=body, followups_capture_cycle_id=cycle)
                except cap.process_improvements_collect.PIFormatError:
                    break
        with mock.patch.object(fixture, "_collect", side_effect=collect):
            cycle = fixture._fixture(root)
        leaf = root / cap.process_improvements_collect.capture_receipt_rel_path(fixture.plan_ref, role, cycle)
        # Exact preservation includes arbitrary valid JSON whitespace/newlines.
        leaf.write_text(json.dumps(json.loads(leaf.read_bytes()), ensure_ascii=False, indent=3) + "\n\n")
        return fixture, MODULE, cap, cycle, leaf

    def payload(self, root, fixture, module, cycle):
        return module.classify_docs_closeout(root=root, plan_ref=fixture.plan_ref,
            bundle_payload=fixture._bundle(), followups_capture_cycle_id=cycle)

    def reserve(self, root, fixture, module, cap, cycle, role):
        payload = self.payload(root, fixture, module, cycle)
        self.assertEqual(payload["schema_state"], "ok", payload.get("schema_errors"))
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["general_pi_format_correction_admission"]["state"], "retryable", payload["general_pi_format_correction_admission"])
        with mock.patch.object(cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
            result = cap.reserve_general_pi_correction(root, fixture.plan_ref, cycle, role, payload)
        self.assertEqual(result["state"], "reserved")
        return result, payload

    def corrected(self, root, fixture, cap, cycle, role, reservation_id, body):
        collector = cap.process_improvements_collect
        with mock.patch.object(collector, "_load_capture_admission_module", return_value=cap), mock.patch.object(
                cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
            context, bounded, admission = collector._general_collection_writer_context(root, role=role,
                source_ref=fixture.plan_ref, followups_capture_cycle_id=cycle, context=None,
                format_correction_reservation_id=reservation_id)
            self.assertTrue(bounded)  # Explicit correction is safe even in a legacy/self fixture.
            return collector._collect_process_improvements(project_root=root, role=role,
                source_ref=fixture.plan_ref, text=body, followups_capture_cycle_id=cycle,
                context=context, engaged_public=bounded, active_admission=admission)

    def restarted_admission(self, root, fixture, cycle):
        program = ("import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                   "import followups_capture as c; print(json.dumps(c.general_pi_format_correction_admission("
                   "Path(sys.argv[2]),sys.argv[3],sys.argv[4],bundle_payload=json.loads(sys.argv[5]))))")
        process = subprocess.run([sys.executable, "-B", "-c", program, str(Path(__file__).parent), str(root),
            fixture.plan_ref, cycle, json.dumps(fixture._bundle())], capture_output=True, text=True, check=True)
        return json.loads(process.stdout)

    def test_all_role_positions_original_bytes_and_bounded_second_refusal(self):
        for role in capture.REQUIRED_ROLES:
            for second_malformed in (False, True):
                with self.subTest(role=role, second_malformed=second_malformed), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    fixture, module, cap, cycle, leaf = self.fixture(root, role, materialized=True)
                    original = leaf.read_bytes()
                    aggregate_path = fixture._receipt_path(root, cycle)
                    self.assertEqual(json.loads(aggregate_path.read_bytes())[cap.PI_FORMAT_CORRECTIONS_KEY], {})
                    result, retained = self.reserve(root, fixture, module, cap, cycle, role)
                    reserved_bytes = aggregate_path.read_bytes()
                    record = json.loads(reserved_bytes)[cap.PI_FORMAT_CORRECTIONS_KEY][role]
                    self.assertEqual(record["original_receipt_utf8"].encode(), original)
                    self.assertEqual(record["original_receipt_sha256"], hashlib.sha256(original).hexdigest())
                    self.assertEqual(json.loads(reserved_bytes)["state"], "started")
                    spent = self.payload(root, fixture, module, cycle)["general_pi_format_correction_admission"]
                    self.assertEqual((spent["state"], spent["attempts_reserved"]), ("blocked", 1))
                    with mock.patch.object(cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
                        with self.assertRaises(cap.CaptureError):
                            cap.reserve_general_pi_correction(root, fixture.plan_ref, cycle, role, retained)
                        admitted = cap.validate_reserved_general_pi_ingest(root, fixture.plan_ref, cycle, role, result["reservation_id"])
                    self.assertEqual(admitted["attempts_reserved"], 1)
                    self.assertEqual(aggregate_path.read_bytes(), reserved_bytes)
                    body = self.malformed + "again\n" if second_malformed else self.clean
                    if second_malformed:
                        with self.assertRaises(cap.process_improvements_collect.PIFormatError):
                            self.corrected(root, fixture, cap, cycle, role, result["reservation_id"], body)
                        with mock.patch.object(cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
                            with self.assertRaises(cap.CaptureError):
                                cap.validate_reserved_general_pi_ingest(root, fixture.plan_ref, cycle, role, result["reservation_id"])
                        restarted = self.restarted_admission(root, fixture, cycle)
                        self.assertEqual((restarted["state"], restarted["attempts_reserved"]), ("blocked", 1))
                        self.assertIsNone(restarted["next_dispatch"])
                        before = fixture._objects(root)
                        with self.assertRaises(cap.CaptureError):
                            self.corrected(root, fixture, cap, cycle, role, result["reservation_id"], self.clean)
                        self.assertEqual(before, fixture._objects(root))
                    else:
                        self.corrected(root, fixture, cap, cycle, role, result["reservation_id"], body)
                        before = fixture._objects(root)
                        with self.assertRaises(cap.CaptureError):
                            self.corrected(root, fixture, cap, cycle, role, result["reservation_id"], body)
                        self.assertEqual(before, fixture._objects(root))
                        # The existing exact replay remains no-write and spends no slot.
                        cap.process_improvements_collect.collect_process_improvements(project_root=root,
                            role=role, source_ref=fixture.plan_ref, text=body, followups_capture_cycle_id=cycle)
                        self.assertEqual(before, fixture._objects(root))
                        for successor in cap.REQUIRED_ROLES[cap.REQUIRED_ROLES.index(role) + 1:]:
                            cap.process_improvements_collect.collect_process_improvements(project_root=root,
                                role=successor, source_ref=fixture.plan_ref, text=self.clean, followups_capture_cycle_id=cycle)
                        cap.checkpoint_general_pi(root, fixture.plan_ref, cycle)
                    after = json.loads(aggregate_path.read_bytes())[cap.PI_FORMAT_CORRECTIONS_KEY][role]
                    self.assertEqual(after, record)
                    original_json = json.loads(after["original_receipt_utf8"])
                    self.assertEqual(original_json["input_sha256"], hashlib.sha256(self.malformed.encode()).hexdigest())
                    self.assertEqual(original_json["capture_state"], "blocked")

    def test_negative_predicates_and_retained_proof_are_zero_mutation(self):
        variants = ("untyped", "suffix", "extra_leaf", "missing_prefix", "red_prefix", "effect", "role", "cycle", "source",
                    "missing_carrier", "unknown_carrier", "checkpoint", "followups", "live", "derived", "foreign", "protected", "plan", "stale_proof",
                    "project", "host", "source_commit")
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                fixture, module, cap, cycle, leaf = self.fixture(root, "Coder", materialized=variant == "derived")
                retained = self.payload(root, fixture, module, cycle)
                value = json.loads(leaf.read_bytes())
                if variant in {"untyped", "effect", "role", "cycle", "source"}:
                    if variant == "untyped": value.pop("error_type")
                    elif variant == "effect": value["after_process_improvement_files"] = {}; value["before_process_improvement_files"] = {"bad": {}}
                    elif variant == "role": value["role"] = "Reviewer"
                    elif variant == "cycle": value["followups_capture_cycle_id"] = "00000000-0000-4000-8000-000000000000"
                    else: value["source_ref"] = "docs/plans/foreign.md"
                    leaf.write_text(json.dumps(value))
                elif variant == "missing_prefix":
                    (root / cap.process_improvements_collect.capture_receipt_rel_path(fixture.plan_ref, "Architect", cycle)).unlink()
                elif variant == "red_prefix":
                    target = root / cap.process_improvements_collect.capture_receipt_rel_path(fixture.plan_ref, "Architect", cycle)
                    bad = json.loads(target.read_bytes()); bad.update(capture_state="blocked", reason_code="collector_error", error="unknown")
                    target.write_text(json.dumps(bad))
                elif variant == "suffix":
                    cap.process_improvements_collect.collect_process_improvements(project_root=root, role="Reviewer",
                        source_ref=fixture.plan_ref, text=self.clean, followups_capture_cycle_id=cycle)
                elif variant == "extra_leaf":
                    (leaf.parent / "unknown.json").write_text("{}\n")
                elif variant in {"missing_carrier", "unknown_carrier", "checkpoint", "followups"}:
                    def edit(receipt):
                        if variant == "missing_carrier": receipt.pop(cap.PI_FORMAT_CORRECTIONS_KEY)
                        elif variant == "unknown_carrier": receipt[cap.PI_FORMAT_CORRECTIONS_KEY]["Unknown"] = {}
                        elif variant == "checkpoint": receipt["general_pi_checkpoint"] = {}
                        else: receipt["completed_roles"] = ["Architect"]
                    fixture._edit_receipt(root, cycle, edit)
                elif variant == "stale_proof":
                    retained["general_pi_format_correction_admission"]["proof"]["receipt_sha256"] = "0" * 64
                elif variant in {"project", "host"}:
                    def edit_host(receipt):
                        if variant == "project": receipt["transaction_host_identity"]["project_root"] = "/fixture/foreign"
                        else: receipt["cycle_directory_identity"]["path"] = ".tmp/foreign"
                    fixture._edit_receipt(root, cycle, edit_host)
                elif variant == "source_commit":
                    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "source changed"], check=True, capture_output=True)
                else:
                    target = root / {"live": cap.process_improvements_collect.backlog_rel_path_for_source_ref(fixture.plan_ref),
                        "derived": "docs/process_improvements/index.md", "foreign": "docs/foreign.md",
                        "protected": "docs/roles/manager.md", "plan": fixture.plan_ref}[variant]
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_text("changed\n")
                before = fixture._objects(root)
                head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"])
                index = subprocess.check_output(["git", "-C", str(root), "diff", "--cached", "--binary"])
                with mock.patch.object(cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()), mock.patch.object(cap, "_publish_mutation") as publish:
                    with self.assertRaises(cap.CaptureError):
                        cap.reserve_general_pi_correction(root, fixture.plan_ref, cycle, "Coder", retained)
                    publish.assert_not_called()
                self.assertEqual(before, fixture._objects(root))
                self.assertEqual(head, subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]))
                self.assertEqual(index, subprocess.check_output(["git", "-C", str(root), "diff", "--cached", "--binary"]))

    def test_reserved_crash_lost_result_and_reentry_never_replenish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture, module, cap, cycle, leaf = self.fixture(root)
            result, retained = self.reserve(root, fixture, module, cap, cycle, "Coder")
            original = leaf.read_bytes(); aggregate = fixture._receipt_path(root, cycle).read_bytes()
            # Independent processes model restart after reservation before send,
            # lost terminal result, and another subsequent invocation.
            for _ in range(3):
                readback = self.restarted_admission(root, fixture, cycle)
                self.assertEqual((readback["state"], readback["attempts_reserved"]), ("blocked", 1))
                self.assertEqual(readback["reason"], "pi_format_correction_reservation_consumed")
                self.assertIsNone(readback["next_dispatch"])
            self.assertEqual(leaf.read_bytes(), original)
            self.assertEqual(fixture._receipt_path(root, cycle).read_bytes(), aggregate)

    def test_each_role_retains_its_independent_spent_slot_in_one_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture, module, cap, cycle, _ = self.fixture(root, "Architect")
            for position, role in enumerate(cap.REQUIRED_ROLES):
                if position:
                    with self.assertRaises(cap.process_improvements_collect.PIFormatError):
                        cap.process_improvements_collect.collect_process_improvements(project_root=root, role=role,
                            source_ref=fixture.plan_ref, text=self.malformed, followups_capture_cycle_id=cycle)
                result, _ = self.reserve(root, fixture, module, cap, cycle, role)
                self.corrected(root, fixture, cap, cycle, role, result["reservation_id"], self.clean)
                records = json.loads(fixture._receipt_path(root, cycle).read_bytes())[cap.PI_FORMAT_CORRECTIONS_KEY]
                self.assertEqual(list(records), sorted(cap.REQUIRED_ROLES[:position + 1]))
                self.assertEqual({entry["attempts_reserved"] for entry in records.values()}, {1})
            self.assertEqual(len(records), 4)
            self.assertEqual(sorted(record["reserved_revision"] for record in records.values()), [2, 3, 4, 5])
            original = fixture._receipt_path(root, cycle).read_bytes()
            for variant in ("duplicate_id", "duplicate_revision"):
                def corrupt(receipt):
                    field = "reservation_id" if variant == "duplicate_id" else "reserved_revision"
                    receipt[cap.PI_FORMAT_CORRECTIONS_KEY]["Coder"][field] = receipt[cap.PI_FORMAT_CORRECTIONS_KEY]["Architect"][field]
                fixture._edit_receipt(root, cycle, corrupt)
                before = fixture._objects(root)
                refused = cap.general_pi_format_correction_admission(root, fixture.plan_ref, cycle, bundle_payload=fixture._bundle())
                self.assertEqual(refused["state"], "blocked")
                self.assertEqual(before, fixture._objects(root))
                fixture._receipt_path(root, cycle).write_bytes(original)
            cap.checkpoint_general_pi(root, fixture.plan_ref, cycle)

    def test_corrected_ingest_revalidates_after_stdin_and_before_effect(self):
        for phase in ("stdin", "effect"):
            for variant in ("bytes", "inode", "aggregate", "source"):
                with self.subTest(phase=phase, variant=variant), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve(); fixture, module, cap, cycle, leaf = self.fixture(root)
                    reserved, _ = self.reserve(root, fixture, module, cap, cycle, "Coder")
                    collector = cap.process_improvements_collect
                    changed = {}
                    def mutate():
                        if variant == "bytes": leaf.write_bytes(leaf.read_bytes() + b"\n")
                        elif variant == "inode":
                            other = leaf.with_suffix(".replacement"); other.write_bytes(leaf.read_bytes()); other.replace(leaf)
                        elif variant == "aggregate":
                            fixture._edit_receipt(root, cycle, lambda receipt: receipt.update(started_at="2026-01-01T00:00:00Z"))
                        else:
                            subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                                "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "source drift"], check=True, capture_output=True)
                        changed["objects"] = fixture._objects(root)
                    with mock.patch.object(collector, "_load_capture_admission_module", return_value=cap), mock.patch.object(
                            cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()):
                        context, bounded, admission = collector._general_collection_writer_context(root, role="Coder",
                            source_ref=fixture.plan_ref, followups_capture_cycle_id=cycle, context=None,
                            format_correction_reservation_id=reserved["reservation_id"])
                        original_parser = collector.parse_process_improvements_section
                        def parse(*args, **kwargs):
                            mutate()
                            return original_parser(*args, **kwargs)
                        if phase == "stdin": mutate()
                        with mock.patch.object(collector, "parse_process_improvements_section",
                                side_effect=parse if phase == "effect" else original_parser):
                            with self.assertRaises(cap.CaptureError):
                                collector._collect_process_improvements(project_root=root, role="Coder", source_ref=fixture.plan_ref,
                                    text=self.clean, followups_capture_cycle_id=cycle, context=context,
                                    engaged_public=bounded, active_admission=admission)
                    self.assertEqual(changed["objects"], fixture._objects(root))

    def test_stale_reservation_writer_cannot_overwrite_another_durable_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture, module, cap, cycle, _ = self.fixture(root)
            retained = self.payload(root, fixture, module, cycle)
            publish = cap._publish_mutation
            competitor_bytes = []
            competitor_id = "6ab5b5ce-513b-4ef0-8e0d-3f5c72f8575b"
            def competing(host, fd, exact_cycle, raw, next_receipt):
                competitor = json.loads(json.dumps(next_receipt))
                competitor[cap.PI_FORMAT_CORRECTIONS_KEY]["Coder"]["reservation_id"] = competitor_id
                publish(host, fd, exact_cycle, raw, competitor)
                competitor_bytes.append(fixture._receipt_path(root, cycle).read_bytes())
                return publish(host, fd, exact_cycle, raw, next_receipt)
            with mock.patch.object(cap, "_fresh_continuation_bundle_payload", return_value=fixture._bundle()), mock.patch.object(
                    cap, "_publish_mutation", side_effect=competing):
                with self.assertRaises(cap.CaptureError):
                    cap.reserve_general_pi_correction(root, fixture.plan_ref, cycle, "Coder", retained)
            self.assertEqual(fixture._receipt_path(root, cycle).read_bytes(), competitor_bytes[0])
            records = json.loads(competitor_bytes[0])[cap.PI_FORMAT_CORRECTIONS_KEY]
            self.assertEqual(set(records), {"Coder"})
            self.assertEqual(records["Coder"]["reservation_id"], competitor_id)
            restarted = self.restarted_admission(root, fixture, cycle)
            self.assertEqual((restarted["state"], restarted["attempts_reserved"]), ("blocked", 1))


class FollowupsCaptureTests(unittest.TestCase):
    def _root(self, tmpdir: str) -> Path:
        root = Path(tmpdir).resolve()
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / PLAN_REF).write_text(
            "# Plan: fixture\n\n**Status:** Done\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "add", PLAN_REF], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Authority Fixture",
                "-c",
                'user.email=' + 'authority-fixture' + '@' + 'example' + '.' + 'invalid',
                "commit",
                "-qm",
                "fixture baseline",
            ],
            check=True,
            capture_output=True,
        )
        return root

    def _begin_payload(self) -> dict[str, object]:
        return {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": PLAN_REF,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
        }

    def _receipt_path(self, root: Path, cycle_id: str) -> Path:
        return root / ".tmp/followups_capture" / Path(PLAN_REF).stem / cycle_id / capture.RECEIPT_NAME

    def _checkpoint_general(self, root: Path, cycle_id: str) -> dict[str, object]:
        receipt = json.loads(self._receipt_path(root, cycle_id).read_text(encoding="utf-8"))
        if receipt.get("general_pi_checkpoint") is not None:
            return capture._response(
                receipt,
                state="started",
                reason_code="followup_capture_pi_general_checkpoint_already_published",
            )
        for role in capture.REQUIRED_ROLES:
            capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=PLAN_REF,
                text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                followups_capture_cycle_id=cycle_id,
            )
        return capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)

    def _begin(self, root: Path, *, checkpoint_general: bool = True) -> dict[str, object]:
        payload = capture.begin_cycle(root, PLAN_REF, self._begin_payload())
        if checkpoint_general:
            self._checkpoint_general(root, str(payload["capture_cycle_id"]))
        return payload

    def _commit_worktree(self, root: Path, message: str) -> None:
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Fixture",
                "-c",
                'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit",
                "-q",
                "-m",
                message,
            ],
            check=True,
            capture_output=True,
        )

    def _finish_noop(self, root: Path, cycle_id: str, *, start_at: int = 0) -> None:
        self._checkpoint_general(root, cycle_id)
        for role in capture.REQUIRED_ROLES[start_at:]:
            capture.prepare_role(root, PLAN_REF, cycle_id, role)
            capture.finalize_role(root, PLAN_REF, cycle_id, role, b"NO FOLLOWUPS\nsummary\n")

    def _write_followup(self, root: Path, rel_path: str) -> None:
        (root / rel_path).write_text(
            "# Follow-ups backlog — fixture\n\n"
            "**Date:** 21.07.2026 02:00\n"
            "**Source:** terminal docs finalize\n"
            "**Status:** Draft\n"
            "**Schema version:** followups.v1\n\n"
            "## Follow-ups (backlog)\n"
            "- P1 [ ] Exact ownership fixture — cluster=process — tags=fixture — to=Architect "
            f"— status=open — plan=null — source_ref={PLAN_REF} — why: post-terminal finding\n",
            encoding="utf-8",
        )

    def _write_pi_objects(self, root: Path, *, marker: str) -> dict[str, dict[str, object]]:
        for index, rel_path in enumerate(capture._process_improvement_data_paths(PLAN_REF), start=1):
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{marker}:{index}\n", encoding="utf-8")
        return capture.snapshot_process_improvement_data_files(root, PLAN_REF)

    def _write_valid_pi_objects(self, root: Path) -> dict[str, dict[str, object]]:
        capture.process_improvements_collect.ensure_derived_surface_docs(root)
        capture.process_improvements_collect.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref=PLAN_REF,
            text=(
                "## Process improvements\n"
                "### Suggestion 1\n"
                "- symptom: fixture checkpoint needs a valid PI carrier\n"
                "- process_gap: fixture lacked a derived-surface proof\n"
                "- suggested_fix: emit one source-bound backlog row\n"
                "- owner: Architect\n"
                "- promotion_class: helper_change\n"
                "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                f"- source_ref: {PLAN_REF}\n"
            ),
        )
        return capture.snapshot_process_improvement_data_files(root, PLAN_REF)

    def _materialize_valid_pi_objects_without_receipt(
        self,
        root: Path,
        *,
        blocker_id: str,
    ) -> dict[str, dict[str, object]]:
        capture.process_improvements_collect.ensure_derived_surface_docs(root)
        capture.process_improvements_collect.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref=PLAN_REF,
            text=(
                "## Process improvements\n"
                "### Suggestion 1\n"
                f"- symptom: fixture state-effect proof {blocker_id}\n"
                f"- process_gap: fixture must retain a distinct object map for {blocker_id}\n"
                f"- suggested_fix: emit the exact source-bound backlog row for {blocker_id}\n"
                "- owner: Architect\n"
                "- promotion_class: helper_change\n"
                f"- trigger_ref: docs/code_reviews/fixture.md#{blocker_id}\n"
                f"- source_ref: {PLAN_REF}\n"
            ),
            write_receipt=False,
        )
        return capture.snapshot_process_improvement_data_files(root, PLAN_REF)

    def _collect_general_chain(self, root: Path, cycle_id: str, *, materialize_coder: bool) -> dict[str, dict[str, object]]:
        noop = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        suggestion = (
            "## Process improvements\n"
            "### Suggestion 1\n"
            "- symptom: general PI outputs need a checkpoint bridge\n"
            "- process_gap: aggregate capture did not accept a collector object chain\n"
            "- suggested_fix: publish one exact general-to-followups checkpoint\n"
            "- owner: Architect\n"
            "- promotion_class: helper_change\n"
            "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
            f"- source_ref: {PLAN_REF}\n"
        )
        texts = {
            "Architect": noop,
            "Coder": suggestion if materialize_coder else noop,
            "Planner": noop,
            "Reviewer": "## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n" if materialize_coder else noop,
        }
        payloads: dict[str, dict[str, object]] = {}
        for role in capture.REQUIRED_ROLES:
            payloads[role] = capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=PLAN_REF,
                text=texts[role],
                followups_capture_cycle_id=cycle_id,
            )
        return payloads

    def test_canonical_digest_formula_and_persisted_newline_are_byte_exact(self) -> None:
        receipt = {
            "z": "кириллица",
            "receipt_revision": 1,
            "receipt_content_sha256": "ignored",
            "a": [1, True],
        }
        expected_content = '{"a":[1,true],"receipt_revision":1,"z":"кириллица"}'.encode("utf-8")
        self.assertEqual(capture.canonical_receipt_content_bytes(receipt), expected_content)
        self.assertEqual(capture.receipt_content_sha256(receipt), hashlib.sha256(expected_content).hexdigest())
        receipt["receipt_content_sha256"] = capture.receipt_content_sha256(receipt)
        persisted = capture.persisted_receipt_bytes(receipt)
        self.assertTrue(persisted.endswith(b"\n"))
        self.assertFalse(persisted.endswith(b"\n\n"))

    def test_explicit_cycle_baseline_and_checkpoint_ignore_legacy_v1_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role="Architect",
                source_ref=PLAN_REF,
                text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
            )
            legacy_path = capture.process_improvements_collect.capture_receipt_rel_path(PLAN_REF, "Architect")
            self.assertTrue((root / legacy_path).exists())

            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            aggregate = json.loads(self._receipt_path(root, cycle_id).read_text(encoding="utf-8"))
            self.assertNotIn(legacy_path.as_posix(), aggregate["baseline_process_improvement_files"])
            with self.assertRaises(capture.CaptureError) as missing:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(missing.exception.reason_code, "followup_capture_pi_general_receipt_missing")

            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            marker = json.loads(self._receipt_path(root, cycle_id).read_text(encoding="utf-8"))["general_pi_checkpoint"]

        self.assertEqual(
            [item["path"] for item in marker["input_receipts"]],
            [
                capture.process_improvements_collect.capture_receipt_rel_path(PLAN_REF, role, cycle_id).as_posix()
                for role in capture.REQUIRED_ROLES
            ],
        )
        self.assertNotIn(legacy_path.as_posix(), [item["path"] for item in marker["input_receipts"]])

    def test_pi_dirty_baseline_fails_closed_when_git_marker_exists_but_probe_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            failed = SimpleNamespace(returncode=128, stdout=b"", stderr=b"probe failed")
            with mock.patch.object(capture, "_git", return_value=failed):
                with self.assertRaises(capture.CaptureError) as caught:
                    capture.snapshot_dirty_process_improvement_paths(root, PLAN_REF)

        self.assertEqual(caught.exception.reason_code, "followup_capture_pi_dirty_baseline_failed")

    def test_cycle_revisions_created_row_and_idempotent_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            begin = self._begin(root)
            cycle_id = str(begin["capture_cycle_id"])
            path = self._receipt_path(root, cycle_id)

            prepared = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            prepared_bytes = path.read_bytes()
            prepared_retry = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            self.assertEqual(prepared_retry["reason_code"], "already_prepared")
            self.assertEqual(path.read_bytes(), prepared_bytes)

            created = "docs/followups/260721_0200_fixture.md"
            self._write_followup(root, created)
            finalized = capture.finalize_role(
                root,
                PLAN_REF,
                cycle_id,
                "Architect",
                f"Created: {created}\nSummary: one row\n".encode(),
            )
            finalized_bytes = path.read_bytes()
            finalized_retry = capture.finalize_role(
                root,
                PLAN_REF,
                cycle_id,
                "Architect",
                f"Created: {created}\nSummary: one row\n".encode(),
            )
            self.assertEqual(finalized_retry["reason_code"], "already_finalized")
            self.assertEqual(path.read_bytes(), finalized_bytes)
            self.assertGreater(finalized["receipt_revision"], prepared["receipt_revision"])

            self._finish_noop(root, cycle_id, start_at=1)
            readback = capture.read_capture(
                root,
                PLAN_REF,
                cycle_id,
                semantic_fields=("Done", "done", "already_materialized"),
            )
            self.assertEqual(readback["state"], "materialized")
            self.assertEqual(readback["created_paths"], [created])
            self.assertEqual(readback["staging_expectations"][0]["expected_staged_mode"], "100644")

            receipt = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["receipt_revision"], 10)
            self.assertNotIn("previous_receipt_sha256", receipt)
            self.assertEqual(receipt["receipt_content_sha256"], capture.receipt_content_sha256(receipt))
            self.assertEqual(path.read_bytes(), capture.persisted_receipt_bytes(receipt))
            self.assertEqual(receipt["pi_lineage_root_cycle_id"], cycle_id)
            self.assertEqual(receipt["pi_adopted_from_cycle_ids"], [])
            self.assertEqual(receipt["pi_ownership_state"], "finalized")
            self.assertEqual(receipt["pi_final_objects"], {})
            self.assertIsNone(receipt["pi_failure_checkpoint"])

    def test_active_general_pi_collection_admission_is_read_only_and_checkpoint_closes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            receipt_path = self._receipt_path(root, cycle_id)
            before = receipt_path.read_bytes()

            proof = capture.admit_active_general_pi_collection(root, PLAN_REF, cycle_id, "Architect")
            self.assertEqual(proof["plan_ref"], PLAN_REF)
            self.assertEqual(proof["capture_cycle_id"], cycle_id)
            self.assertEqual(proof["role"], "Architect")
            self.assertEqual(receipt_path.read_bytes(), before)

            with self.assertRaises(capture.CaptureError) as invalid_role:
                capture.admit_active_general_pi_collection(root, PLAN_REF, cycle_id, "Manager")
            self.assertEqual(invalid_role.exception.reason_code, "followup_capture_pi_general_collection_role_invalid")
            self.assertEqual(receipt_path.read_bytes(), before)

            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            closed_bytes = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as checkpoint_closed:
                capture.admit_active_general_pi_collection(root, PLAN_REF, cycle_id, "Architect")
            self.assertEqual(receipt_path.read_bytes(), closed_bytes)

        self.assertEqual(
            checkpoint_closed.exception.reason_code,
            "followup_capture_pi_general_collection_checkpoint_closed",
        )

    def test_general_pi_checkpoint_allows_full_followups_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=True)
            checkpoint = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(checkpoint["state"], "started")
            self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")

            for role in capture.REQUIRED_ROLES:
                prepared = capture.prepare_role(root, PLAN_REF, cycle_id, role)
                self.assertEqual(prepared["reason_code"], "role_prepared")
                finalized = capture.finalize_role(root, PLAN_REF, cycle_id, role, b"NO FOLLOWUPS\n")
                self.assertIn(finalized["state"], {"started", "finalized"})
            readback = capture.read_capture(root, PLAN_REF, cycle_id)

        self.assertEqual(readback["state"], "clean_noop")
        self.assertEqual(readback["completed_roles"], list(capture.REQUIRED_ROLES))
        self.assertIsNotNone(readback["general_pi_checkpoint"])

    def test_finalized_prepare_role_is_read_only(self) -> None:
        for variant in ("clean", "materialized", "post_terminal_foreign"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                if variant == "post_terminal_foreign":
                    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
                cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
                self._collect_general_chain(root, cycle_id, materialize_coder=variant == "materialized")
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
                self._finish_noop(root, cycle_id)
                if variant == "post_terminal_foreign":
                    foreign_plan_ref = "docs/plans/260716_1049_terminal_foreign.md"
                    foreign_backlog = root / capture.process_improvements_collect.backlog_rel_path_for_source_ref(
                        foreign_plan_ref
                    )
                    foreign_backlog.parent.mkdir(parents=True, exist_ok=True)
                    foreign_backlog.write_text("# Foreign process improvements backlog\n", encoding="utf-8")

                receipt_path = self._receipt_path(root, cycle_id)
                before_bytes = receipt_path.read_bytes()
                before = json.loads(before_bytes)
                before_readback = capture.read_capture(root, PLAN_REF, cycle_id)
                late_prepare = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                after_bytes = receipt_path.read_bytes()
                after = json.loads(after_bytes)
                after_readback = capture.read_capture(root, PLAN_REF, cycle_id)

                self.assertEqual(late_prepare["state"], "finalized")
                self.assertEqual(late_prepare["reason_code"], "already_finalized")
                self.assertEqual(after_bytes, before_bytes)
                self.assertEqual(after, before)
                self.assertEqual(after["state"], "finalized")
                self.assertEqual(after["pi_ownership_state"], "finalized")
                self.assertEqual(after["blocked_roles"], [])
                self.assertEqual(after_readback, before_readback)
                self.assertEqual(
                    len(after["pi_final_objects"]),
                    len(capture._process_improvement_data_paths(PLAN_REF)) if variant == "materialized" else 0,
                )

    def test_general_pi_checkpoint_records_exact_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            receipt_path = self._receipt_path(root, cycle_id)
            before = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertIsNone(before["general_pi_checkpoint"])
            self._collect_general_chain(root, cycle_id, materialize_coder=True)
            capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            after = json.loads(receipt_path.read_text(encoding="utf-8"))

        marker = after["general_pi_checkpoint"]
        self.assertEqual(after["receipt_revision"], before["receipt_revision"] + 1)
        self.assertEqual(marker["prior_receipt_revision"], before["receipt_revision"])
        self.assertEqual(marker["prior_receipt_content_sha256"], before["receipt_content_sha256"])
        self.assertEqual([item["role"] for item in marker["input_receipts"]], list(capture.REQUIRED_ROLES))
        self.assertEqual(
            [item["path"] for item in marker["input_receipts"]],
            [
                capture.process_improvements_collect.capture_receipt_rel_path(PLAN_REF, role, cycle_id).as_posix()
                for role in capture.REQUIRED_ROLES
            ],
        )
        self.assertEqual(marker["after_process_improvement_files"], after["current_process_improvement_files"])
        self.assertEqual(
            [item["path"] for item in marker["process_improvement_path_results"]],
            sorted(item["path"] for item in marker["process_improvement_path_results"]),
        )
        self.assertEqual(after["pi_ownership_state"], "active")
        self.assertEqual(after["pi_final_objects"], {})
        self.assertIsNone(after["pi_failure_checkpoint"])

    def test_same_cycle_checkpoint_accepts_legacy_surfaces_and_preserves_collectors(self) -> None:
        collector = capture.process_improvements_collect
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            self._write_valid_pi_objects(root)
            surfaces = (collector.INDEX_PATH, collector.DEFERRED_PATH, collector.PROMOTION_PATH)
            for rel in surfaces:
                path = root / rel
                path.write_text(path.read_text(encoding="utf-8").replace(collector.PROCESS_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE), encoding="utf-8")
            self._commit_worktree(root, "seed legacy derived surfaces")
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            role_paths = [collector.capture_receipt_rel_path(PLAN_REF, role, cycle_id) for role in capture.REQUIRED_ROLES]
            before = {rel: ((root / rel).read_bytes(), stat.S_IMODE((root / rel).stat().st_mode)) for rel in (*surfaces, *role_paths)}
            receipt_path = self._receipt_path(root, cycle_id)
            aggregate_before = json.loads(receipt_path.read_bytes())
            self.assertIsNone(aggregate_before["general_pi_checkpoint"])

            self.assertTrue(collector.check_derived_surfaces(root)["ok"])
            checkpoint = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            aggregate_after = json.loads(receipt_path.read_bytes())

            self.assertEqual(checkpoint["state"], "started")
            self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")
            self.assertEqual(aggregate_after["capture_cycle_id"], cycle_id)
            self.assertEqual(aggregate_after["receipt_revision"], aggregate_before["receipt_revision"] + 1)
            self.assertIsNotNone(aggregate_after["general_pi_checkpoint"])
            self.assertEqual(aggregate_after["general_pi_checkpoint"]["prior_receipt_content_sha256"], aggregate_before["receipt_content_sha256"])
            self.assertTrue(collector.check_derived_surfaces(root)["ok"])
            for rel, expected in before.items():
                self.assertEqual(((root / rel).read_bytes(), stat.S_IMODE((root / rel).stat().st_mode)), expected)
            for rel in role_paths:
                self.assertEqual(json.loads((root / rel).read_bytes())["capture_state"], "clean_noop")

    def test_general_pi_checkpoint_replay_and_invalid_inputs_do_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            receipt_path = self._receipt_path(root, cycle_id)
            initial_bytes = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as missing:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(missing.exception.reason_code, "followup_capture_pi_general_receipt_missing")
            self.assertEqual(receipt_path.read_bytes(), initial_bytes)

            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            published = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            published_bytes = receipt_path.read_bytes()
            replay = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(replay["reason_code"], "followup_capture_pi_general_checkpoint_already_published")
            self.assertEqual(replay["receipt_revision"], published["receipt_revision"])
            self.assertEqual(receipt_path.read_bytes(), published_bytes)

            stale_receipt = json.loads(published_bytes)
            stale_receipt["general_pi_checkpoint"]["prior_receipt_revision"] += 1
            stale_receipt["receipt_content_sha256"] = capture.receipt_content_sha256(stale_receipt)
            receipt_path.write_bytes(capture.persisted_receipt_bytes(stale_receipt))
            stale_bytes = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as stale:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(stale.exception.reason_code, "followup_capture_pi_general_checkpoint_stale_revision")
            self.assertEqual(receipt_path.read_bytes(), stale_bytes)
            receipt_path.write_bytes(published_bytes)

            role_path = root / capture.process_improvements_collect.capture_receipt_rel_path(
                PLAN_REF,
                "Planner",
                cycle_id,
            )
            forged = json.loads(role_path.read_text(encoding="utf-8"))
            forged["followups_capture_cycle_id"] = str(capture.uuid.uuid4())
            role_path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as wrong_cycle:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(wrong_cycle.exception.reason_code, "followup_capture_pi_general_receipt_identity_mismatch")
            self.assertEqual(receipt_path.read_bytes(), published_bytes)

    def test_checkpoint_general_pi_cli_uses_canonical_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            command = [
                sys.executable,
                "-B",
                str(Path(capture.__file__).resolve()),
                "checkpoint-general-pi",
                "--project-root",
                str(root),
                "--plan-ref",
                PLAN_REF,
                "--capture-cycle-id",
                cycle_id,
            ]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["reason_code"], "followup_capture_pi_general_checkpointed")

            rejected = subprocess.run(
                [*command, "--receipt-path", "forbidden.json"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unrecognized arguments", rejected.stderr)

    def test_general_pi_checkpoint_phase_closes_after_followups_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            receipt_path = self._receipt_path(root, cycle_id)
            after_prepare = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as closed:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            unchanged = receipt_path.read_bytes() == after_prepare

        self.assertEqual(closed.exception.reason_code, "followup_capture_pi_general_checkpoint_phase_closed")
        self.assertTrue(unchanged)

    def test_general_pi_checkpoint_rejects_object_and_derived_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=True)
            receipt_path = self._receipt_path(root, cycle_id)
            before = receipt_path.read_bytes()
            (root / "docs/process_improvements/index.md").write_text("stale derived surface\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as stale:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(receipt_path.read_bytes(), before)

            role_path = root / capture.process_improvements_collect.capture_receipt_rel_path(
                PLAN_REF,
                "Reviewer",
                cycle_id,
            )
            forged = json.loads(role_path.read_text(encoding="utf-8"))
            forged["after_process_improvement_files"]["docs/process_improvements/unexpected.md"] = {
                "sha256": "0" * 64,
                "file_type": "regular",
                "st_size": 0,
            }
            forged["process_improvement_path_results"].append(
                {
                    "path": "docs/process_improvements/unexpected.md",
                    "before_object": None,
                    "after_object": forged["after_process_improvement_files"]["docs/process_improvements/unexpected.md"],
                }
            )
            role_path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as malformed:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)

        self.assertIn(stale.exception.reason_code, {
            "followup_capture_pi_general_checkpoint_live_drift",
            "followup_capture_pi_general_checkpoint_derived_mismatch",
        })
        self.assertEqual(malformed.exception.reason_code, "followup_capture_pi_general_receipt_invalid")

    def test_general_pi_checkpoint_rejects_foreign_dirty_backlog_before_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            foreign_plan_ref = "docs/plans/260716_1047_foreign.md"
            foreign_backlog = root / capture.process_improvements_collect.backlog_rel_path_for_source_ref(foreign_plan_ref)
            foreign_backlog.parent.mkdir(parents=True, exist_ok=True)
            foreign_backlog.write_text("# Foreign process improvements backlog\n", encoding="utf-8")
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            receipt_path = self._receipt_path(root, cycle_id)
            before = receipt_path.read_bytes()

            with self.assertRaises(capture.CaptureError) as foreign:
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            self.assertEqual(receipt_path.read_bytes(), before)

            with self.assertRaises(capture.CaptureError) as missing_marker:
                capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            self.assertEqual(receipt_path.read_bytes(), before)

        self.assertEqual(foreign.exception.reason_code, "followup_capture_pi_general_checkpoint_foreign_backlog")
        self.assertEqual(missing_marker.exception.reason_code, "followup_capture_pi_general_checkpoint_missing")

    def test_post_checkpoint_foreign_backlog_and_scan_failure_stay_nonadoptable(self) -> None:
        for phase in ("before_prepare", "after_prepare", "scan_failure"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
                cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
                self._collect_general_chain(root, cycle_id, materialize_coder=False)
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
                receipt_path = self._receipt_path(root, cycle_id)
                marker = json.loads(receipt_path.read_text(encoding="utf-8"))["general_pi_checkpoint"]
                if phase == "after_prepare":
                    prepared = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                    self.assertEqual(prepared["reason_code"], "role_prepared")
                expected_reason = "followup_capture_pi_post_checkpoint_foreign_backlog"
                git_dir = root / ".git"
                preserved_git_dir: Path | None = None
                if phase == "scan_failure":
                    preserved_git_dir = root / ".git.valid"
                    git_dir.rename(preserved_git_dir)
                    git_dir.write_text("gitdir: /missing\n", encoding="utf-8")
                    expected_reason = "followup_capture_pi_post_checkpoint_foreign_backlog_scan_failed"
                else:
                    foreign_plan_ref = "docs/plans/260716_1048_foreign_after_checkpoint.md"
                    foreign_backlog = root / capture.process_improvements_collect.backlog_rel_path_for_source_ref(foreign_plan_ref)
                    foreign_backlog.parent.mkdir(parents=True, exist_ok=True)
                    foreign_backlog.write_text("# Foreign process improvements backlog\n", encoding="utf-8")
                if phase == "after_prepare":
                    blocked = capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\n")
                else:
                    blocked = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if preserved_git_dir is not None:
                    git_dir.unlink()
                    preserved_git_dir.rename(git_dir)
                with self.assertRaises(capture.CaptureError) as retry:
                    capture.begin_cycle(
                        root,
                        PLAN_REF,
                        self._begin_payload(),
                        retry_of_capture_cycle_id=cycle_id,
                    )

                self.assertEqual(blocked["state"], "blocked")
                self.assertEqual(blocked["reason_code"], expected_reason)
                self.assertEqual(receipt["state"], "blocked")
                self.assertEqual(receipt["reason_code"], expected_reason)
                self.assertEqual(receipt["completed_roles"], [])
                self.assertEqual(receipt["pi_ownership_state"], "blocked")
                self.assertEqual(receipt["pi_final_objects"], {})
                self.assertEqual(receipt["current_process_improvement_files"], marker["after_process_improvement_files"])
                self.assertEqual(receipt["general_pi_checkpoint"], marker)
                self.assertNotEqual(receipt["reason_code"], "capture_finalized")
                self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")

    def test_missing_git_identity_fails_closed_before_and_after_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            nested_root = root / "nested"
            nested_root.mkdir()
            with self.assertRaises(capture.CaptureError) as nested_git:
                capture.snapshot_dirty_process_improvement_paths(nested_root, PLAN_REF)
            self.assertEqual(nested_git.exception.reason_code, "followup_capture_pi_dirty_baseline_failed")

            hidden_git_dir = root / ".git.absent"
            (root / ".git").rename(hidden_git_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(hidden_git_dir),
                    "GIT_WORK_TREE": str(root),
                    "GIT_COMMON_DIR": str(hidden_git_dir),
                },
            ):
                with self.assertRaises(capture.CaptureError) as missing_git:
                    capture.begin_cycle(root, PLAN_REF, self._begin_payload())

            self.assertEqual(missing_git.exception.reason_code, "followup_capture_pi_dirty_baseline_failed")
            self.assertEqual(list((root / ".tmp/followups_capture").rglob(capture.RECEIPT_NAME)), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=False)
            receipt_path = self._receipt_path(root, cycle_id)
            before = receipt_path.read_bytes()
            hidden_git_dir = root / ".git.absent"
            (root / ".git").rename(hidden_git_dir)

            with mock.patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(hidden_git_dir),
                    "GIT_WORK_TREE": str(root),
                    "GIT_COMMON_DIR": str(hidden_git_dir),
                },
            ):
                with self.assertRaises(capture.CaptureError) as missing_git:
                    capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)

            self.assertEqual(
                missing_git.exception.reason_code,
                "followup_capture_pi_general_checkpoint_foreign_backlog_scan_failed",
            )
            self.assertEqual(receipt_path.read_bytes(), before)

        for phase in ("before_prepare", "after_prepare"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
                self._collect_general_chain(root, cycle_id, materialize_coder=False)
                capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
                receipt_path = self._receipt_path(root, cycle_id)
                marker = json.loads(receipt_path.read_text(encoding="utf-8"))["general_pi_checkpoint"]
                if phase == "after_prepare":
                    prepared = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                    self.assertEqual(prepared["reason_code"], "role_prepared")
                hidden_git_dir = root / ".git.absent"
                (root / ".git").rename(hidden_git_dir)

                with mock.patch.dict(
                    os.environ,
                    {
                        "GIT_DIR": str(hidden_git_dir),
                        "GIT_WORK_TREE": str(root),
                        "GIT_COMMON_DIR": str(hidden_git_dir),
                    },
                ):
                    if phase == "after_prepare":
                        blocked = capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\n")
                    else:
                        blocked = capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                with self.assertRaises(capture.CaptureError) as readback:
                    capture.read_capture(root, PLAN_REF, cycle_id)

                self.assertEqual(blocked["state"], "blocked")
                self.assertEqual(
                    blocked["reason_code"],
                    "followup_capture_pi_post_checkpoint_foreign_backlog_scan_failed",
                )
                self.assertEqual(receipt["state"], "blocked")
                self.assertEqual(receipt["completed_roles"], [])
                self.assertEqual(receipt["pi_ownership_state"], "blocked")
                self.assertEqual(receipt["pi_final_objects"], {})
                self.assertEqual(receipt["current_process_improvement_files"], marker["after_process_improvement_files"])
                self.assertEqual(receipt["general_pi_checkpoint"], marker)
                self.assertNotEqual(receipt["reason_code"], "capture_finalized")
                self.assertEqual(readback.exception.reason_code, "followup_capture_incomplete")

    def test_general_pi_checkpoint_rejects_state_effect_mismatch(self) -> None:
        for capture_state in ("clean_noop", "already_tracked", "materialized"):
            with self.subTest(capture_state=capture_state), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                baseline = self._materialize_valid_pi_objects_without_receipt(root, blocker_id="B1")
                cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
                self._collect_general_chain(root, cycle_id, materialize_coder=False)
                after = baseline
                if capture_state != "materialized":
                    after = self._materialize_valid_pi_objects_without_receipt(root, blocker_id="B2")
                    self.assertNotEqual(after, baseline)

                def rewrite_receipt(
                    role: str,
                    *,
                    before_objects: dict[str, dict[str, object]],
                    after_objects: dict[str, dict[str, object]],
                    state: str,
                ) -> None:
                    path = root / capture.process_improvements_collect.capture_receipt_rel_path(
                        PLAN_REF,
                        role,
                        cycle_id,
                    )
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                    receipt["capture_state"] = state
                    receipt["before_process_improvement_files"] = before_objects
                    receipt["after_process_improvement_files"] = after_objects
                    receipt["process_improvement_path_results"] = capture._pi_path_results(before_objects, after_objects)
                    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

                rewrite_receipt(
                    "Coder",
                    before_objects=baseline,
                    after_objects=after,
                    state=capture_state,
                )
                if after != baseline:
                    for role in ("Planner", "Reviewer"):
                        rewrite_receipt(
                            role,
                            before_objects=after,
                            after_objects=after,
                            state="clean_noop",
                        )

                receipt_path = self._receipt_path(root, cycle_id)
                before = receipt_path.read_bytes()
                with self.assertRaises(capture.CaptureError) as mismatch:
                    capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
                self.assertEqual(receipt_path.read_bytes(), before)
                with self.assertRaises(capture.CaptureError) as missing_marker:
                    capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
                self.assertEqual(receipt_path.read_bytes(), before)

                self.assertEqual(
                    mismatch.exception.reason_code,
                    "followup_capture_pi_general_receipt_state_effect_mismatch",
                )
                self.assertEqual(missing_marker.exception.reason_code, "followup_capture_pi_general_checkpoint_missing")

    _GENERAL_NOOP = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
    _GENERAL_SUGGESTION = (
        "## Process improvements\n"
        "### Suggestion 1\n"
        "- symptom: general PI outputs need a checkpoint bridge\n"
        "- process_gap: aggregate capture did not accept a collector object chain\n"
        "- suggested_fix: publish one exact general-to-followups checkpoint\n"
        "- owner: Architect\n"
        "- promotion_class: helper_change\n"
        "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
        f"- source_ref: {PLAN_REF}\n"
    )

    def _collect_engaged_general(self, root: Path, cycle_id: str, role: str, text: str) -> dict[str, object]:
        """Run the engaged collector route behind the real active-cycle admission.

        Callers patch ``_validate_writer_effect``: an engaged ContractContext needs
        the pinned runtime and authority marker that only the subprocess
        AuthorityFixture harness builds.  Admission, receipts and the checkpoint
        stay real.
        """

        admission = capture.admit_active_general_pi_collection(root, PLAN_REF, cycle_id, role)
        return capture.process_improvements_collect._collect_process_improvements(
            project_root=root,
            role=role,
            source_ref=PLAN_REF,
            text=text,
            followups_capture_cycle_id=cycle_id,
            context=object(),
            engaged_public=True,
            active_admission=admission,
        )

    def _general_role_receipt(self, root: Path, cycle_id: str, role: str) -> dict[str, object]:
        path = root / capture.process_improvements_collect.capture_receipt_rel_path(PLAN_REF, role, cycle_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_engaged_partial_blocked_recovery_receipt_matches_effect_and_checkpoints(self) -> None:
        """A same-input recovery of a partial blocked receipt reports its whole effect."""

        collector = capture.process_improvements_collect
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(collector, "_validate_writer_effect"):
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            with mock.patch.object(
                collector,
                "_safe_pi_rebuild_derived_surfaces",
                side_effect=RuntimeError("injected derived failure after backlog write"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected derived failure"):
                    self._collect_engaged_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            blocked = self._general_role_receipt(root, cycle_id, "Architect")
            recovered = self._collect_engaged_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            recovered_receipt = self._general_role_receipt(root, cycle_id, "Architect")
            successors = {
                role: self._collect_engaged_general(root, cycle_id, role, self._GENERAL_NOOP)[
                    "process_improvement_capture_state"
                ]
                for role in ("Coder", "Planner", "Reviewer")
            }
            checkpoint = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            derived_ok = collector.check_derived_surfaces(root)["ok"]

        self.assertEqual(blocked["capture_state"], "blocked")
        self.assertNotEqual(
            blocked["before_process_improvement_files"],
            blocked["after_process_improvement_files"],
        )
        self.assertEqual(recovered["created"], [])
        self.assertEqual(len(recovered["duplicates"]), 1)
        self.assertEqual(recovered["process_improvement_capture_state"], "materialized")
        self.assertEqual(recovered_receipt["capture_state"], "materialized")
        self.assertEqual(
            recovered_receipt["before_process_improvement_files"],
            blocked["before_process_improvement_files"],
        )
        self.assertTrue(recovered_receipt["process_improvement_path_results"])
        self.assertEqual(successors, {"Coder": "clean_noop", "Planner": "clean_noop", "Reviewer": "clean_noop"})
        self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")
        self.assertTrue(derived_ok)

    def test_engaged_effectless_blocked_retry_keeps_duplicate_receipt_without_effect(self) -> None:
        """A corrected retry after an effect-free blocked receipt does not rewrite derived surfaces."""

        collector = capture.process_improvements_collect
        malformed = "## Process improvements\n### Suggestion 1\n- symptom only, no colon field\n"
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(collector, "_validate_writer_effect"):
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            predecessors = {
                role: self._collect_engaged_general(root, cycle_id, role, text)["process_improvement_capture_state"]
                for role, text in (
                    ("Architect", self._GENERAL_NOOP),
                    ("Coder", self._GENERAL_SUGGESTION),
                    ("Planner", self._GENERAL_NOOP),
                )
            }
            with self.assertRaises(ValueError):
                self._collect_engaged_general(root, cycle_id, "Reviewer", malformed)
            blocked = self._general_role_receipt(root, cycle_id, "Reviewer")
            live_before_retry = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            # The corrected turn arrives in a later minute, so any derived rewrite
            # would change the summary stamp bytes.
            with mock.patch.object(collector, "_summary_stamp", return_value="2000-01-01 00:00 MSK"):
                corrected = self._collect_engaged_general(root, cycle_id, "Reviewer", self._GENERAL_SUGGESTION)
            corrected_receipt = self._general_role_receipt(root, cycle_id, "Reviewer")
            live_after_retry = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            checkpoint = capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)

        self.assertEqual(predecessors, {"Architect": "clean_noop", "Coder": "materialized", "Planner": "clean_noop"})
        self.assertEqual(blocked["capture_state"], "blocked")
        self.assertEqual(
            blocked["before_process_improvement_files"],
            blocked["after_process_improvement_files"],
        )
        self.assertEqual(corrected["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(corrected_receipt["capture_state"], "already_tracked")
        self.assertEqual(corrected_receipt["process_improvement_path_results"], [])
        self.assertEqual(live_after_retry, live_before_retry)
        self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")

    def _collect_legacy_general(self, root: Path, cycle_id: str, role: str, text: str) -> dict[str, object]:
        """Run the public collector in a root without the authority marker (legacy route)."""

        return capture.process_improvements_collect.collect_process_improvements(
            project_root=root,
            role=role,
            source_ref=PLAN_REF,
            text=text,
            followups_capture_cycle_id=cycle_id,
        )

    def _general_checkpoint_reason(self, root: Path, cycle_id: str) -> str:
        try:
            return str(capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)["reason_code"])
        except capture.CaptureError as exc:
            return exc.reason_code

    def _begin_legacy(self, root: Path) -> str:
        collector = capture.process_improvements_collect
        self.assertFalse((root / "docs/_meta/planveyor_contract_authority.v1.json").exists())
        self.assertEqual(collector.authority_context.context_for_reader(root).state, "legacy")
        return str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])

    def _legacy_partial_blocked_architect(self, root: Path, cycle_id: str) -> dict[str, object]:
        """Leave the legacy Architect receipt blocked after its backlog write."""

        collector = capture.process_improvements_collect
        with mock.patch.object(
            collector,
            "_rebuild_derived_surfaces",
            side_effect=RuntimeError("injected derived failure after backlog write"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected derived failure"):
                self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
        blocked = self._general_role_receipt(root, cycle_id, "Architect")
        self.assertEqual(blocked["capture_state"], "blocked")
        self.assertNotEqual(
            blocked["before_process_improvement_files"],
            blocked["after_process_improvement_files"],
        )
        self.assertEqual(
            blocked["after_process_improvement_files"],
            capture.snapshot_process_improvement_data_files(root, PLAN_REF),
        )
        return blocked

    def _finish_legacy_general_chain(self, root: Path, cycle_id: str) -> dict[str, object]:
        successors = {
            role: self._collect_legacy_general(root, cycle_id, role, self._GENERAL_NOOP)[
                "process_improvement_capture_state"
            ]
            for role in ("Coder", "Planner", "Reviewer")
        }
        return {
            "successors": successors,
            "checkpoint": self._general_checkpoint_reason(root, cycle_id),
            "derived_ok": capture.process_improvements_collect.check_derived_surfaces(root)["ok"],
        }

    _LEGACY_CHAIN_CHECKPOINTED = {
        "successors": {"Coder": "clean_noop", "Planner": "clean_noop", "Reviewer": "clean_noop"},
        "checkpoint": "followup_capture_pi_general_checkpointed",
        "derived_ok": True,
    }

    def test_legacy_partial_blocked_recovery_receipt_matches_effect_and_checkpoints(self) -> None:
        """Without the authority marker a same-input recovery also owns the partial blocked effect."""

        self.maxDiff = None
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin_legacy(root)
            blocked = self._legacy_partial_blocked_architect(root, cycle_id)
            recovered = self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            recovered_receipt = self._general_role_receipt(root, cycle_id, "Architect")
            outcome = self._finish_legacy_general_chain(root, cycle_id)

        self.assertEqual(
            {
                "recovered_state": recovered["process_improvement_capture_state"],
                "receipt_state": recovered_receipt["capture_state"],
                "receipt_keeps_blocked_before": (
                    recovered_receipt["before_process_improvement_files"]
                    == blocked["before_process_improvement_files"]
                ),
                **outcome,
            },
            {
                "recovered_state": "materialized",
                "receipt_state": "materialized",
                "receipt_keeps_blocked_before": True,
                **self._LEGACY_CHAIN_CHECKPOINTED,
            },
        )
        self.assertEqual(recovered["created"], [])
        self.assertEqual(len(recovered["duplicates"]), 1)
        self.assertTrue(recovered_receipt["process_improvement_path_results"])

    def test_legacy_effectless_blocked_retry_keeps_duplicate_receipt_without_effect(self) -> None:
        """A corrected legacy retry after an effect-free blocked receipt does not rewrite derived surfaces."""

        collector = capture.process_improvements_collect
        malformed = "## Process improvements\n### Suggestion 1\n- symptom only, no colon field\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            # The legacy dedup key includes the role, so the corrected Reviewer
            # suggestion duplicates only a Reviewer row committed before the cycle.
            collector.collect_process_improvements(
                project_root=root,
                role="Reviewer",
                source_ref=PLAN_REF,
                text=self._GENERAL_SUGGESTION,
            )
            self._commit_worktree(root, "reviewer PI baseline")
            cycle_id = self._begin_legacy(root)
            predecessors = {
                role: self._collect_legacy_general(root, cycle_id, role, self._GENERAL_NOOP)[
                    "process_improvement_capture_state"
                ]
                for role in ("Architect", "Coder", "Planner")
            }
            with self.assertRaises(ValueError):
                self._collect_legacy_general(root, cycle_id, "Reviewer", malformed)
            blocked = self._general_role_receipt(root, cycle_id, "Reviewer")
            live_before_retry = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            # The corrected turn arrives in a later minute, so any derived rewrite
            # would change the summary stamp bytes.
            with mock.patch.object(collector, "_summary_stamp", return_value="2000-01-01 00:00 MSK"):
                corrected = self._collect_legacy_general(root, cycle_id, "Reviewer", self._GENERAL_SUGGESTION)
            corrected_receipt = self._general_role_receipt(root, cycle_id, "Reviewer")
            live_after_retry = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            checkpoint = self._general_checkpoint_reason(root, cycle_id)

        self.assertEqual(predecessors, {"Architect": "clean_noop", "Coder": "clean_noop", "Planner": "clean_noop"})
        self.assertEqual(blocked["capture_state"], "blocked")
        self.assertEqual(
            blocked["before_process_improvement_files"],
            blocked["after_process_improvement_files"],
        )
        self.assertEqual(corrected["duplicates"][0]["entry_id"], "PI-001")
        self.assertEqual(corrected["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(corrected_receipt["capture_state"], "already_tracked")
        self.assertEqual(corrected_receipt["process_improvement_path_results"], [])
        self.assertEqual(live_after_retry, live_before_retry)
        self.assertEqual(checkpoint, "followup_capture_pi_general_checkpointed")

    def test_legacy_blocked_recovery_admission_conflicts_keep_blocked_receipt(self) -> None:
        """Legacy recovery refuses a changed partial input or a drifted live map before collection."""

        collector = capture.process_improvements_collect
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin_legacy(root)
            blocked = self._legacy_partial_blocked_architect(root, cycle_id)
            receipt_path = root / collector.capture_receipt_rel_path(PLAN_REF, "Architect", cycle_id)
            blocked_bytes = receipt_path.read_bytes()
            live_blocked = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            refused: dict[str, str] = {}
            with mock.patch.object(
                collector,
                "_collect_process_improvements_impl",
                side_effect=AssertionError("must not collect"),
            ):
                with self.assertRaises(ValueError) as changed_input:
                    self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION + "\n")
                refused["changed_input"] = str(changed_input.exception)
                changed_input_bytes = receipt_path.read_bytes()
                backlog = root / collector.backlog_rel_path_for_source_ref(PLAN_REF)
                backlog_bytes = backlog.read_bytes()
                backlog.write_bytes(backlog_bytes + b"\n")
                with self.assertRaises(ValueError) as drifted:
                    self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
                refused["drifted_live"] = str(drifted.exception)
                drifted_bytes = receipt_path.read_bytes()
                backlog.write_bytes(backlog_bytes)
            live_restored = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            recovered = self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            outcome = self._finish_legacy_general_chain(root, cycle_id)

        self.assertEqual(
            refused,
            {
                "changed_input": "process-improvement v2 blocked partial receipt input digest conflicts before recovery",
                "drifted_live": "process-improvement v2 blocked receipt live map conflicts before recovery",
            },
        )
        self.assertEqual(changed_input_bytes, blocked_bytes)
        self.assertEqual(drifted_bytes, blocked_bytes)
        self.assertEqual(live_restored, live_blocked)
        self.assertEqual(recovered["process_improvement_capture_state"], "materialized")
        self.assertEqual(recovered["before_process_improvement_files"], blocked["before_process_improvement_files"])
        self.assertEqual(outcome, self._LEGACY_CHAIN_CHECKPOINTED)

    def test_legacy_failed_recovery_replaces_blocked_receipt_truthfully(self) -> None:
        """A legacy recovery that fails after further output keeps one truthful blocked receipt."""

        collector = capture.process_improvements_collect

        def fail_after_first_derived_write(project_root: Path, **_kwargs: object) -> dict[str, str]:
            (project_root / collector.INDEX_PATH).write_text(collector.default_index_text(), encoding="utf-8")
            raise RuntimeError("injected recovery derived failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin_legacy(root)
            first = self._legacy_partial_blocked_architect(root, cycle_id)
            receipt_path = root / collector.capture_receipt_rel_path(PLAN_REF, "Architect", cycle_id)
            with mock.patch.object(
                collector,
                "_rebuild_derived_surfaces",
                side_effect=fail_after_first_derived_write,
            ):
                with self.assertRaisesRegex(RuntimeError, "injected recovery derived failure"):
                    self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            second = self._general_role_receipt(root, cycle_id, "Architect")
            live_after_second = capture.snapshot_process_improvement_data_files(root, PLAN_REF)
            derived_after_second = collector.check_derived_surfaces(root)["ok"]
            recovered = self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_SUGGESTION)
            recovered_receipt = self._general_role_receipt(root, cycle_id, "Architect")
            temporaries = sorted(path.name for path in receipt_path.parent.glob(".*.tmp"))
            outcome = self._finish_legacy_general_chain(root, cycle_id)

        self.assertEqual(second["capture_state"], "blocked")
        self.assertEqual(second["before_process_improvement_files"], first["before_process_improvement_files"])
        self.assertEqual(second["after_process_improvement_files"], live_after_second)
        self.assertNotEqual(second["after_process_improvement_files"], first["after_process_improvement_files"])
        self.assertFalse(derived_after_second)
        self.assertEqual(recovered["process_improvement_capture_state"], "materialized")
        self.assertEqual(
            recovered_receipt["before_process_improvement_files"],
            first["before_process_improvement_files"],
        )
        self.assertEqual(temporaries, [])
        self.assertEqual(outcome, self._LEGACY_CHAIN_CHECKPOINTED)

    def test_legacy_unobservable_postmap_skips_fabricated_blocked_receipt(self) -> None:
        """A legacy v2 failure cannot publish a false empty after-map that would block recovery."""

        collector = capture.process_improvements_collect
        malformed = "## Process improvements\n### Suggestion 1\n- symptom only, no colon field\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            baseline = self._write_valid_pi_objects(root)
            self._commit_worktree(root, "PI baseline")
            cycle_id = self._begin_legacy(root)
            receipt_path = root / collector.capture_receipt_rel_path(PLAN_REF, "Architect", cycle_id)
            real_object_map = collector._capture_pi_object_map
            reads: list[int] = []

            def unobservable_after_first_read(project_root: Path, source_ref: str) -> dict[str, dict[str, object]]:
                reads.append(1)
                if len(reads) > 1:
                    raise ValueError("injected post-map read failure")
                return real_object_map(project_root, source_ref)

            with mock.patch.object(collector, "_capture_pi_object_map", side_effect=unobservable_after_first_read):
                with self.assertRaisesRegex(ValueError, "Unsupported line inside `Process improvements`"):
                    self._collect_legacy_general(root, cycle_id, "Architect", malformed)
            receipt_after_failure = receipt_path.exists()
            corrected = self._collect_legacy_general(root, cycle_id, "Architect", self._GENERAL_NOOP)
            outcome = self._finish_legacy_general_chain(root, cycle_id)

        self.assertEqual(len(reads), 2)
        self.assertFalse(receipt_after_failure)
        self.assertEqual(corrected["process_improvement_capture_state"], "clean_noop")
        self.assertEqual(corrected["before_process_improvement_files"], baseline)
        self.assertEqual(outcome, self._LEGACY_CHAIN_CHECKPOINTED)

    def test_post_checkpoint_pi_mutation_stays_nonadoptable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            self._collect_general_chain(root, cycle_id, materialize_coder=True)
            capture.checkpoint_general_pi(root, PLAN_REF, cycle_id)
            marker_before = json.loads(self._receipt_path(root, cycle_id).read_text(encoding="utf-8"))["general_pi_checkpoint"]
            capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            backlog = root / capture.process_improvements_collect.backlog_rel_path_for_source_ref(PLAN_REF)
            backlog.write_text("mutated after checkpoint\n", encoding="utf-8")
            blocked = capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\n")
            receipt = json.loads(self._receipt_path(root, cycle_id).read_text(encoding="utf-8"))
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    self._begin_payload(),
                    retry_of_capture_cycle_id=cycle_id,
                )

        self.assertEqual(blocked["reason_code"], "followup_capture_pi_post_checkpoint_drift")
        self.assertEqual(receipt["pi_ownership_state"], "blocked")
        self.assertEqual(receipt["pi_final_objects"], {})
        self.assertEqual(receipt["general_pi_checkpoint"], marker_before)
        self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")

    def test_legacy_finalized_receipt_remains_readable_but_nonterminal_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            fresh_cycle_id = str(self._begin(root, checkpoint_general=False)["capture_cycle_id"])
            fresh_path = self._receipt_path(root, fresh_cycle_id)
            fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
            fresh.pop("general_pi_checkpoint")
            fresh["receipt_content_sha256"] = capture.receipt_content_sha256(fresh)
            fresh_path.write_bytes(capture.persisted_receipt_bytes(fresh))
            before_prepare = fresh_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as nonterminal:
                capture.prepare_role(root, PLAN_REF, fresh_cycle_id, "Architect")
            self.assertEqual(fresh_path.read_bytes(), before_prepare)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            legacy_cycle_id = str(self._begin(root)["capture_cycle_id"])
            self._finish_noop(root, legacy_cycle_id)
            legacy_path = self._receipt_path(root, legacy_cycle_id)
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            legacy.pop("general_pi_checkpoint")
            legacy["receipt_content_sha256"] = capture.receipt_content_sha256(legacy)
            legacy_path.write_bytes(capture.persisted_receipt_bytes(legacy))
            readback = capture.read_capture(root, PLAN_REF, legacy_cycle_id)

        self.assertEqual(nonterminal.exception.reason_code, "followup_capture_pi_general_checkpoint_legacy")
        self.assertEqual(readback["state"], "clean_noop")
        self.assertIsNone(readback["general_pi_checkpoint"])

    def test_changed_duplicate_blocks_once_without_lost_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root)["capture_cycle_id"])
            path = self._receipt_path(root, cycle_id)
            capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\n")
            before = json.loads(path.read_text(encoding="utf-8"))

            blocked = capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\nchanged summary\n")
            after_bytes = path.read_bytes()
            after = json.loads(after_bytes)
            blocked_retry = capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", b"NO FOLLOWUPS\nchanged summary\n")

            self.assertEqual(blocked["state"], "blocked")
            self.assertEqual(after["receipt_revision"], before["receipt_revision"] + 1)
            self.assertNotIn("previous_receipt_sha256", after)
            self.assertEqual(blocked_retry["state"], "blocked")
            self.assertEqual(path.read_bytes(), after_bytes)


    def test_terminal_plan_bytes_remain_identical_across_the_full_role_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            plan = root / PLAN_REF
            before = plan.read_bytes()
            cycle_id = str(self._begin(root)["capture_cycle_id"])
            self._finish_noop(root, cycle_id)
            self.assertEqual(plan.read_bytes(), before)
            readback = capture.read_capture(root, PLAN_REF, cycle_id)
            self.assertEqual(readback["state"], "clean_noop")

            plan.write_bytes(before + b"\n")
            with self.assertRaises(capture.CaptureError) as changed:
                capture.read_capture(root, PLAN_REF, cycle_id)
            self.assertEqual(changed.exception.reason_code, "followup_capture_plan_identity_mismatch")

    def test_symlink_fifo_rejected_and_same_bytes_replacement_is_content_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            external = root / "external.md"
            external.write_text("secret\n", encoding="utf-8")
            link = root / "docs/followups/link.md"
            link.symlink_to(external)
            with self.assertRaises(capture.CaptureError) as symlink_error:
                capture.snapshot_followups(root)
            self.assertEqual(symlink_error.exception.reason_code, "followup_capture_path_unsafe")
            self.assertEqual(external.read_text(encoding="utf-8"), "secret\n")
            link.unlink()

            fifo = root / "docs/followups/fifo.md"
            os.mkfifo(fifo)
            with self.assertRaises(capture.CaptureError) as fifo_error:
                capture.snapshot_followups(root)
            self.assertEqual(fifo_error.exception.reason_code, "followup_capture_path_unsafe")
            fifo.unlink()

            cycle_id = str(self._begin(root)["capture_cycle_id"])
            capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            created = "docs/followups/created.md"
            self._write_followup(root, created)
            capture.finalize_role(root, PLAN_REF, cycle_id, "Architect", f"Created: {created}\n".encode())
            self._finish_noop(root, cycle_id, start_at=1)
            old = (root / created).read_bytes()
            replacement = root / "docs/followups/replacement.tmp"
            replacement.write_bytes(old)
            replacement.replace(root / created)
            readback = capture.read_capture(root, PLAN_REF, cycle_id)
            self.assertEqual(readback["state"], "materialized")

    def test_host_and_receipt_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            unsafe_path = root / ".tmp"
            external = root / "outside"
            external.mkdir()
            unsafe_path.symlink_to(external, target_is_directory=True)
            with self.assertRaises(capture.CaptureError) as ancestor:
                self._begin(root)
            self.assertIn(ancestor.exception.reason_code, {"followup_capture_host_unsafe", "followup_capture_host_object_drift"})
            self.assertEqual(list(external.iterdir()), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = str(self._begin(root)["capture_cycle_id"])
            path = self._receipt_path(root, cycle_id)
            path.write_bytes(path.read_bytes().replace(b'"receipt_revision":2', b'"receipt_revision":0'))
            with self.assertRaises(capture.CaptureError) as corrupt:
                capture.prepare_role(root, PLAN_REF, cycle_id, "Architect")
            self.assertEqual(corrupt.exception.reason_code, "followup_capture_receipt_corrupt")

    def test_explicit_retry_rejects_active_or_corrupt_predecessor_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first = self._begin(root)
            first_id = str(first["capture_cycle_id"])

            with self.assertRaises(capture.CaptureError) as duplicate:
                self._begin(root)
            self.assertEqual(duplicate.exception.reason_code, "followup_capture_ambiguous_cycle")

            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = self._receipt_path(root, first_id).read_bytes()
            with self.assertRaises(capture.CaptureError) as active:
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    self._begin_payload(),
                    retry_of_capture_cycle_id=first_id,
                )
            self.assertEqual(active.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(self._receipt_path(root, first_id).read_bytes(), before_receipt)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            self._receipt_path(root, first_id).write_text("{broken\n", encoding="utf-8")
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            with self.assertRaises(capture.CaptureError) as corrupt:
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    self._begin_payload(),
                    retry_of_capture_cycle_id=first_id,
                )
            self.assertEqual(corrupt.exception.reason_code, "followup_capture_retry_predecessor_invalid")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)

    def test_expected_role_preprepare_pi_drift_blocks_without_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            observed_objects = self._write_pi_objects(root, marker="expected-pre-prepare")
            blocked = capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            self.assertEqual(blocked["state"], "blocked")
            self.assertEqual(blocked["reason_code"], "followup_capture_pi_post_checkpoint_drift")

            receipt_path = self._receipt_path(root, first_id)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(receipt["reason_code"], "followup_capture_pi_post_checkpoint_drift")
            self.assertEqual(receipt["role_results"]["Architect"]["state"], "blocked")
            self.assertEqual(receipt["current_process_improvement_files"], {})
            self.assertEqual(receipt["pi_ownership_state"], "blocked")
            self.assertEqual(receipt["pi_final_objects"], {})
            self.assertIsNone(receipt["pi_failure_checkpoint"])

            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(receipt_path.read_bytes(), before_receipt)

    def test_preprepare_stop_and_unreadable_lineage_prefix_remain_nonadoptable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            observed_objects = self._write_pi_objects(root, marker="pre-prepare")
            blocked = capture.prepare_role(root, PLAN_REF, first_id, "Coder")
            self.assertEqual(blocked["reason_code"], "followup_capture_pi_post_checkpoint_drift")
            receipt_path = self._receipt_path(root, first_id)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["pi_ownership_state"], "blocked")
            self.assertEqual(receipt["current_process_improvement_files"], {})
            self.assertEqual(receipt["pi_final_objects"], {})
            self.assertIsNone(receipt["pi_failure_checkpoint"])
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(receipt_path.read_bytes(), before_receipt)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            root_cycle_id = str(self._begin(root)["capture_cycle_id"])
            self._finish_noop(root, root_cycle_id)
            retry_id = str(
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    self._begin_payload(),
                    retry_of_capture_cycle_id=root_cycle_id,
                )["capture_cycle_id"]
            )
            self._finish_noop(root, retry_id)
            retry_path = self._receipt_path(root, retry_id)
            forged = json.loads(retry_path.read_text(encoding="utf-8"))
            missing_cycle_id = str(capture.uuid.uuid4())
            forged["pi_lineage_root_cycle_id"] = missing_cycle_id
            forged["pi_adopted_from_cycle_ids"] = [missing_cycle_id]
            forged["retry_of_capture_cycle_id"] = missing_cycle_id
            forged["receipt_content_sha256"] = capture.receipt_content_sha256(forged)
            retry_path.write_bytes(capture.persisted_receipt_bytes(forged))
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = retry_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as malformed_prefix:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=retry_id)
            self.assertEqual(malformed_prefix.exception.reason_code, "followup_capture_retry_predecessor_invalid")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(retry_path.read_bytes(), before_receipt)

    def test_retry_predecessor_semantic_and_host_fences_are_side_effect_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            self._write_pi_objects(root, marker="semantic")
            capture.finalize_role(root, PLAN_REF, first_id, "Architect", b"invalid role output\n")
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            receipt_path = self._receipt_path(root, first_id)
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = receipt_path.read_bytes()
            different_semantic_payload = self._begin_payload()
            different_semantic_payload["semantic_closeout_kind"] = "different_terminal_kind"
            with self.assertRaises(capture.CaptureError) as semantic:
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    different_semantic_payload,
                    retry_of_capture_cycle_id=first_id,
                )
            self.assertEqual(semantic.exception.reason_code, "followup_capture_retry_predecessor_semantic_mismatch")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(receipt_path.read_bytes(), before_receipt)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            self._write_pi_objects(root, marker="host")
            capture.finalize_role(root, PLAN_REF, first_id, "Architect", b"invalid role output\n")
            receipt_path = self._receipt_path(root, first_id)
            forged = json.loads(receipt_path.read_text(encoding="utf-8"))
            forged["transaction_host_identity"] = {
                "project_root": "/wrong/root",
                "plan_family": ".tmp/followups_capture/wrong",
                "execution_model": "trusted_serial_manager",
            }
            forged["receipt_content_sha256"] = capture.receipt_content_sha256(forged)
            receipt_path.write_bytes(capture.persisted_receipt_bytes(forged))
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            before_receipt = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as host:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(host.exception.reason_code, "followup_capture_retry_predecessor_host_mismatch")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)
            self.assertEqual(receipt_path.read_bytes(), before_receipt)

    def test_retry_rejects_blocked_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            receipt_path = self._receipt_path(root, first_id)
            capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            observed_objects = self._write_pi_objects(root, marker="first")
            blocked = capture.finalize_role(root, PLAN_REF, first_id, "Architect", b"invalid role output\n")
            self.assertEqual(blocked["state"], "blocked")
            predecessor_bytes = receipt_path.read_bytes()
            predecessor = json.loads(predecessor_bytes)
            self.assertEqual(predecessor["reason_code"], "followup_capture_pi_post_checkpoint_drift")
            self.assertEqual(predecessor["pi_ownership_state"], "blocked")
            self.assertEqual(predecessor["pi_final_objects"], {})
            self.assertIsNone(predecessor["pi_failure_checkpoint"])
            self.assertEqual(predecessor["current_process_improvement_files"], {})
            role_result = predecessor["role_results"]["Architect"]
            self.assertEqual(
                [item["path"] for item in role_result["process_improvement_path_results"]],
                sorted(observed_objects),
            )
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(
                    root,
                    PLAN_REF,
                    self._begin_payload(),
                    retry_of_capture_cycle_id=first_id,
                )
            self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")
            self.assertEqual(receipt_path.read_bytes(), predecessor_bytes)

    def test_retry_object_drift_and_legacy_predecessor_fail_before_new_cycle_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            self._write_pi_objects(root, marker="first")
            capture.finalize_role(root, PLAN_REF, first_id, "Architect", b"invalid role output\n")
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            drifted_path = root / capture._process_improvement_data_paths(PLAN_REF)[0]
            drifted_path.write_text("drifted\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as drift:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(drift.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            first_id = str(self._begin(root)["capture_cycle_id"])
            receipt_path = self._receipt_path(root, first_id)
            legacy = json.loads(receipt_path.read_text(encoding="utf-8"))
            for key in (
                "pi_lineage_root_cycle_id",
                "pi_adopted_from_cycle_ids",
                "pi_ownership_state",
                "pi_final_objects",
                "pi_failure_checkpoint",
                "current_process_improvement_files",
            ):
                legacy.pop(key)
            legacy["receipt_content_sha256"] = capture.receipt_content_sha256(legacy)
            receipt_path.write_bytes(capture.persisted_receipt_bytes(legacy))
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            with self.assertRaises(capture.CaptureError) as legacy_error:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(legacy_error.exception.reason_code, "followup_capture_retry_predecessor_legacy")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)

    def test_pre_root_pi_dirt_remains_nonadoptable_after_full_role_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            pre_root_objects = self._write_valid_pi_objects(root)
            dirty_path = capture._process_improvement_data_paths(PLAN_REF)[0]
            with mock.patch.object(capture, "snapshot_dirty_process_improvement_paths", return_value=[dirty_path]):
                first_id = str(self._begin(root)["capture_cycle_id"])
            self._finish_noop(root, first_id)
            receipt_path = self._receipt_path(root, first_id)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(receipt["pi_ownership_state"], "blocked")
            self.assertEqual(receipt["current_process_improvement_files"], pre_root_objects)
            family = root / ".tmp/followups_capture" / Path(PLAN_REF).stem
            before_entries = sorted(path.name for path in family.iterdir())
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(retry.exception.reason_code, "followup_capture_retry_pre_root_dirt")
            self.assertEqual(sorted(path.name for path in family.iterdir()), before_entries)

    def test_pi_path_deletion_blocks_without_checkpoint_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            self._write_valid_pi_objects(root)
            self._commit_worktree(root, "fixture baseline")
            first_id = str(self._begin(root)["capture_cycle_id"])
            capture.prepare_role(root, PLAN_REF, first_id, "Architect")
            deleted = root / capture._process_improvement_data_paths(PLAN_REF)[0]
            deleted.unlink()
            blocked = capture.finalize_role(root, PLAN_REF, first_id, "Architect", b"NO FOLLOWUPS\n")
            self.assertEqual(blocked["state"], "blocked")
            receipt = json.loads(self._receipt_path(root, first_id).read_text(encoding="utf-8"))
            self.assertEqual(receipt["reason_code"], "followup_capture_pi_post_checkpoint_drift")
            self.assertEqual(receipt["pi_ownership_state"], "blocked")
            self.assertIsNone(receipt["pi_failure_checkpoint"])
            with self.assertRaises(capture.CaptureError) as retry:
                capture.begin_cycle(root, PLAN_REF, self._begin_payload(), retry_of_capture_cycle_id=first_id)
            self.assertEqual(retry.exception.reason_code, "followup_capture_retry_predecessor_nonadoptable")

    def test_direct_execution_exposes_real_command_family(self) -> None:
        self.assertNotIn("TRACKING_STUB_MARKER", vars(capture))
        parser = capture._parser()
        help_text = parser.format_help()
        self.assertIn("Capture and verify", help_text)
        self.assertIn("begin", help_text)
        self.assertIn("commit-exact", help_text)


class FollowupsCaptureV2Tests(unittest.TestCase):
    plan_ref = "docs/plans/260811_0010_terminal_source.md"

    def _commit(self, root: Path, message: str) -> None:
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            [
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit", "-qm", message,
            ],
            check=True,
            capture_output=True,
        )

    def _row(self) -> dict[str, object]:
        return {
            "priority": "P1",
            "summary": "Capture V2 tuple",
            "cluster": "process",
            "to": "coder",
            "status": "open",
            "plan": None,
            "why": "prove external readback",
            "tags": [],
            "item_id": "capture-001",
            "source_ref": self.plan_ref,
            "disposition_kind": None,
            "disposition_ref": None,
            "disposition_commit_oid": None,
            "reason": None,
        }

    def _unreachable_source_commits(self, root: Path) -> tuple[str, str]:
        tree_oid = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True).strip()
        dangling = subprocess.check_output(
            [
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit-tree", tree_oid, "-m", "dangling terminal source",
            ],
            text=True,
        ).strip()
        unrelated = subprocess.check_output(
            [
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit-tree", tree_oid, "-m", "unrelated terminal source",
            ],
            text=True,
        ).strip()
        subprocess.run(["git", "-C", str(root), "update-ref", "refs/heads/unrelated", unrelated], check=True)
        return dangling, unrelated

    def test_four_ordered_declarations_freeze_and_exact_open_proof_is_clean(self) -> None:
        try:
            from scripts import followups_apply, followups_lint
        except ModuleNotFoundError:
            import followups_apply
            import followups_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            self._commit(root, "terminal source")
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            blob = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"HEAD:{self.plan_ref}"], text=True
            ).strip()
            snapshot, _ = capture.snapshot_followups(root, include_bytes=True)
            row = self._row()
            declaration_rows = [
                {
                    "followup_path": "docs/followups/process_followups_master.md",
                    "payload": row,
                    "row_digest": followups_lint.v2_row_digest(row),
                }
            ]
            declarations = []
            for role in capture.REQUIRED_ROLES:
                declarations.append(
                    {
                        "schema_version": "followups_declaration.v2",
                        "role": role,
                        "plan_ref": self.plan_ref,
                        "source_terminal_commit_oid": commit,
                        "source_plan_blob_oid": blob,
                        "baseline_followups_snapshot": snapshot,
                        "proposed_rows": declaration_rows if role == "Coder" else [],
                        "role_no_items_reason": None if role == "Coder" else f"{role} found no owned rows",
                    }
                )

            frozen = capture.freeze_v2_declarations(root, self.plan_ref, declarations)
            self.assertEqual(frozen["declaration_roles"], list(capture.REQUIRED_ROLES))
            self.assertEqual(frozen["tuple_owners"], {f"{self.plan_ref}\u0000capture-001": "Coder"})
            persisted = capture.persist_v2_frozen_manifest(root, self.plan_ref, frozen)
            self.assertEqual(
                persisted,
                ".tmp/followups_capture/260811_0010_terminal_source/v2_frozen_manifest.json",
            )
            self.assertTrue((root / persisted).is_file())
            followups_apply.apply_frozen_rows(root, frozen, mutate=True)
            proof = capture.v2_external_proof(root, frozen)
            self.assertEqual(proof["state"], "external_clean")
            self.assertEqual(proof["proof_rows"][0]["proof_host"], "docs/followups/process_followups_master.md#capture-001")

            malformed_lineage = dict(frozen)
            malformed_lineage.pop("declaration_roles")
            with self.assertRaises(capture.CaptureError) as malformed:
                capture.v2_external_proof(root, malformed_lineage)
            self.assertEqual(malformed.exception.reason_code, "followup_v2_cycle_invalid")

    def test_v2_external_proof_fails_closed_for_foreign_explicit_v2_but_not_malformed_legacy(self) -> None:
        try:
            from scripts import followups_apply, followups_lint
        except ModuleNotFoundError:
            import followups_apply
            import followups_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            self._commit(root, "terminal source")
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            blob = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"HEAD:{self.plan_ref}"], text=True
            ).strip()
            snapshot, _ = capture.snapshot_followups(root, include_bytes=True)
            row = self._row()
            declaration_row = {
                "followup_path": "docs/followups/process_followups_master.md",
                "payload": row,
                "row_digest": followups_lint.v2_row_digest(row),
            }
            declarations = [
                {
                    "schema_version": "followups_declaration.v2",
                    "role": role,
                    "plan_ref": self.plan_ref,
                    "source_terminal_commit_oid": commit,
                    "source_plan_blob_oid": blob,
                    "baseline_followups_snapshot": snapshot,
                    "proposed_rows": [declaration_row] if role == "Coder" else [],
                    "role_no_items_reason": None if role == "Coder" else f"{role} found no owned rows",
                }
                for role in capture.REQUIRED_ROLES
            ]
            frozen = capture.freeze_v2_declarations(root, self.plan_ref, declarations)
            self.assertEqual(followups_apply.apply_frozen_rows(root, frozen, mutate=True)["state"], "applied")
            foreign = root / "docs/followups/foreign.md"
            foreign.write_text(
                "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n",
                encoding="utf-8",
            )

            blocked = capture.v2_external_proof(root, frozen)
            self.assertEqual(blocked["state"], "external_invalid")
            self.assertEqual(blocked["reason"], "v2_integrity_blocker")

            foreign.write_text(
                "# legacy\n\n**Schema version:** followups.v1\n\n## Follow-ups\n- P1 [ ] malformed legacy row\n",
                encoding="utf-8",
            )
            compatibility = capture.v2_external_proof(root, frozen)
            self.assertEqual(compatibility["state"], "external_clean")

    def test_v2_declaration_rejects_wrong_source_and_role_order(self) -> None:
        try:
            from scripts import followups_lint
        except ModuleNotFoundError:
            import followups_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text("# terminal\n\n**Status:** Done\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            self._commit(root, "terminal source")
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            blob = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"HEAD:{self.plan_ref}"], text=True
            ).strip()
            snapshot, _ = capture.snapshot_followups(root, include_bytes=True)
            bad_payload = {**self._row(), "source_ref": "docs/plans/foreign.md"}
            bad = {
                "schema_version": "followups_declaration.v2", "role": "Architect", "plan_ref": self.plan_ref,
                "source_terminal_commit_oid": commit, "source_plan_blob_oid": blob,
                "baseline_followups_snapshot": snapshot,
                "proposed_rows": [{
                    "followup_path": "docs/followups/process_followups_master.md",
                    "payload": bad_payload,
                    "row_digest": followups_lint.v2_row_digest(bad_payload),
                }],
                "role_no_items_reason": None,
            }
            with self.assertRaises(capture.CaptureError) as wrong_source:
                capture.validate_v2_declaration(root, self.plan_ref, bad)
            self.assertEqual(wrong_source.exception.reason_code, "followup_v2_declaration_source_ref_mismatch")

    def test_v2_terminal_identity_rejects_dangling_and_unrelated_commits_in_declaration_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            self._commit(root, "terminal source")
            blob = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"HEAD:{self.plan_ref}"], text=True
            ).strip()
            snapshot, _ = capture.snapshot_followups(root, include_bytes=True)
            for source_commit in self._unreachable_source_commits(root):
                declaration = {
                    "schema_version": "followups_declaration.v2",
                    "role": "Architect",
                    "plan_ref": self.plan_ref,
                    "source_terminal_commit_oid": source_commit,
                    "source_plan_blob_oid": blob,
                    "baseline_followups_snapshot": snapshot,
                    "proposed_rows": [],
                    "role_no_items_reason": "no owned rows",
                }
                with self.assertRaises(capture.CaptureError) as declaration_error:
                    capture.validate_v2_declaration(root, self.plan_ref, declaration)
                self.assertEqual(declaration_error.exception.reason_code, "followup_v2_source_commit_unreachable")

                manifest = {
                    "schema_version": "followups_capture_cycle.v2",
                    "plan_ref": self.plan_ref,
                    "source_terminal_commit_oid": source_commit,
                    "source_plan_blob_oid": blob,
                    "baseline_followups_snapshot": snapshot,
                    "declaration_roles": list(capture.REQUIRED_ROLES),
                    "expected_owned_tuples": [],
                    "tuple_owners": {},
                    "expected_zero_reason": "no declared rows",
                    "proposed_rows": [],
                }
                with self.assertRaises(capture.CaptureError) as readback_error:
                    capture.v2_external_proof(root, manifest)
                self.assertEqual(readback_error.exception.reason_code, "followup_v2_source_commit_unreachable")

    def test_v1_terminal_source_freezes_exact_architect_union_and_zero_declarations(self) -> None:
        try:
            from scripts import followups_lint
        except ModuleNotFoundError:
            import followups_lint

        plan_ref = "docs/plans/270101_0102_v1_terminal_fixture.md"
        owner_ref = "docs/plans/270101_0103_v1_owner_fixture.md"
        delivery_ref = "docs/plans/270101_0104_v1_delivery_fixture.md"
        zero_reasons = {
            "Coder": "No Coder-owned row in the frozen V1 fixture cycle.",
            "Planner": "No Planner-owned row in the frozen V1 fixture cycle.",
            "Reviewer": "No Reviewer-owned row in the frozen V1 fixture cycle.",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            rows = [
                {"summary": "cancel only the duplicate owner", "plan": None, "status": "open"},
                {"summary": "bind the existing terminal delivery", "plan": None, "status": "open"},
            ]
            (root / plan_ref).write_text(
                "# terminal source\n\n**Status:** Done\n**Schema version:** plan.v1\n\n```json\n"
                + json.dumps({"plan_meta": {"followups_out": rows}}, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            (root / owner_ref).write_text("# owner\n\n**Status:** In progress\n", encoding="utf-8")
            (root / delivery_ref).write_text("# delivery\n\n**Status:** Done\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            self._commit(root, "v1 terminal source")
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            blob = subprocess.check_output(["git", "-C", str(root), "rev-parse", f"HEAD:{plan_ref}"], text=True).strip()
            source_sha = hashlib.sha256((root / plan_ref).read_bytes()).hexdigest()
            snapshot, _ = capture.snapshot_followups(root, include_bytes=True)

            def row_payload(index: int, *, status: str) -> dict[str, object]:
                row_sha = hashlib.sha256(
                    json.dumps(rows[index - 1], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                payload: dict[str, object] = {
                    "priority": "P1",
                    "summary": str(rows[index - 1]["summary"]),
                    "cluster": "process",
                    "to": "architect",
                    "status": status,
                    "plan": None,
                    "why": "freeze one exact V1 fixture tuple",
                    "tags": ["v1-fixture"],
                    "item_id": ("v1-fixture-owner" if index == 1 else "v1-fixture-delivery"),
                    "source_ref": plan_ref,
                    "disposition_kind": ("cancelled_decision" if status == "cancelled" else "terminal_delivery"),
                    "disposition_ref": (f"{owner_ref}#plan_meta.followups_out[4]" if status == "cancelled" else delivery_ref),
                    "disposition_commit_oid": commit,
                    "reason": ("only the duplicate terminal ownership is cancelled" if status == "cancelled" else "the terminal delivery is already durable"),
                    "legacy_row_ref": f"plan_meta.followups_out[{index}]",
                    "legacy_plan_sha256": source_sha,
                    "legacy_row_sha256": row_sha,
                }
                return payload

            payloads = [row_payload(1, status="cancelled"), row_payload(2, status="handled")]
            declarations = [
                {
                    "schema_version": "followups_declaration.v2",
                    "role": role,
                    "plan_ref": plan_ref,
                    "source_terminal_commit_oid": commit,
                    "source_plan_blob_oid": blob,
                    "baseline_followups_snapshot": snapshot,
                    "proposed_rows": [
                        {
                            "followup_path": "docs/followups/270101_0102_v1_terminal_fixture.md",
                            "payload": payload,
                            "row_digest": followups_lint.v2_row_digest(payload),
                        }
                        for payload in payloads
                    ] if role == "Architect" else [],
                    "role_no_items_reason": None if role == "Architect" else zero_reasons[role],
                }
                for role in capture.REQUIRED_ROLES
            ]
            frozen = capture.freeze_v2_declarations(root, plan_ref, declarations)

            self.assertEqual(frozen["declaration_roles"], ["Architect", "Coder", "Planner", "Reviewer"])
            self.assertEqual(frozen["source_plan_sha256"], source_sha)
            self.assertEqual(
                frozen["tuple_owners"],
                {
                    f"{plan_ref}\u0000v1-fixture-owner": "Architect",
                    f"{plan_ref}\u0000v1-fixture-delivery": "Architect",
                },
            )
            self.assertEqual(
                sorted(row["row_digest"] for row in frozen["proposed_rows"]),
                sorted(followups_lint.v2_row_digest(payload) for payload in payloads),
            )
            self.assertEqual(len(frozen["proposed_rows"]), 2)
            self.assertTrue(all(row["payload"]["source_ref"] == plan_ref for row in frozen["proposed_rows"]))

            wrong_order = [*declarations]
            wrong_order[1], wrong_order[2] = wrong_order[2], wrong_order[1]
            with self.assertRaises(capture.CaptureError) as order_error:
                capture.freeze_v2_declarations(root, plan_ref, wrong_order)
            self.assertEqual(order_error.exception.reason_code, "followup_v2_declaration_order_invalid")

            source_drift = [dict(declaration) for declaration in declarations]
            source_drift[1]["source_plan_blob_oid"] = "0" * 40
            with self.assertRaises(capture.CaptureError) as source_error:
                capture.freeze_v2_declarations(root, plan_ref, source_drift)
            self.assertEqual(source_error.exception.reason_code, "followup_v2_source_blob_mismatch")

            tuple_drift = [dict(declaration) for declaration in declarations]
            tuple_drift[1]["proposed_rows"] = [dict(declarations[0]["proposed_rows"][0])]
            tuple_drift[1]["role_no_items_reason"] = None
            with self.assertRaises(capture.CaptureError) as tuple_error:
                capture.freeze_v2_declarations(root, plan_ref, tuple_drift)
            self.assertEqual(tuple_error.exception.reason_code, "followup_v2_declaration_overlap")

            baseline_drift = [dict(declaration) for declaration in declarations]
            baseline_drift[3]["baseline_followups_snapshot"] = {"docs/followups/drift.md": {}}
            with self.assertRaises(capture.CaptureError) as baseline_error:
                capture.freeze_v2_declarations(root, plan_ref, baseline_drift)
            self.assertEqual(baseline_error.exception.reason_code, "followup_v2_declaration_baseline_drift")


class BootstrapAdmissionBeginTests(unittest.TestCase):
    plan_ref = "docs/plans/260821_0131_bootstrap_capture_fixture.md"

    def _root(self, tmpdir: str) -> Path:
        root = Path(tmpdir).resolve()
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / self.plan_ref).write_text(
            "# terminal bootstrap fixture\n\n**Status:** Done\n**Schema version:** plan.v2\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'test'], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "add", self.plan_ref], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "terminal bootstrap source"], check=True, capture_output=True)
        return root

    def _payload(self, root: Path) -> dict[str, object]:
        try:
            from scripts import docs_closeout
        except ModuleNotFoundError:
            import docs_closeout

        return {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": self.plan_ref,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
            "followups_bootstrap_admission": docs_closeout.classify_followups_bootstrap_admission(root, self.plan_ref),
        }

    def _cycle_names(self, root: Path) -> list[str]:
        family = root / ".tmp/followups_capture" / Path(self.plan_ref).stem
        if not family.exists():
            return []
        return sorted(name for name in os.listdir(family) if capture.UUID4_RE.fullmatch(name))

    def test_ready_admission_is_rederived_before_one_cycle_is_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            payload = self._payload(root)
            started = capture.begin_cycle(root, self.plan_ref, payload)
            cycle_names = self._cycle_names(root)

        self.assertEqual(started["state"], "started")
        self.assertEqual(len(cycle_names), 1)

    def test_missing_or_nonready_admission_cannot_consume_a_ready_bootstrap(self) -> None:
        for mutation in ("missing", "nonready"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                payload = self._payload(root)
                if mutation == "missing":
                    payload.pop("followups_bootstrap_admission")
                else:
                    admission = payload["followups_bootstrap_admission"]
                    assert isinstance(admission, dict)
                    admission["state"] = "blocked"

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.begin_cycle(root, self.plan_ref, payload)

                self.assertEqual(rejected.exception.reason_code, "followup_capture_bootstrap_admission_invalid")
                self.assertEqual(self._cycle_names(root), [])

    def test_stale_or_present_manifest_admission_fails_before_capture_host_mutation(self) -> None:
        for mutation in ("worktree_drift", "manifest_present", "admission_field_drift", "head_blob_drift"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                payload = self._payload(root)
                if mutation == "worktree_drift":
                    (root / self.plan_ref).write_text(
                        "# drift\n\n**Status:** Done\n**Schema version:** plan.v2\n",
                        encoding="utf-8",
                    )
                else:
                    if mutation == "manifest_present":
                        manifest = capture.v2_frozen_manifest_path(root, self.plan_ref)
                        manifest.parent.mkdir(parents=True)
                        manifest.write_bytes(b"{}\n")
                    elif mutation == "admission_field_drift":
                        admission = payload["followups_bootstrap_admission"]
                        assert isinstance(admission, dict)
                        admission["source_plan_sha256"] = "0" * 64
                    else:
                        (root / self.plan_ref).write_text(
                            "# replacement terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n",
                            encoding="utf-8",
                        )
                        subprocess.run(
                            ["git", "-C", str(root), "add", self.plan_ref],
                            check=True,
                            capture_output=True,
                        )
                        subprocess.run(
                            ["git", "-C", str(root), "commit", "-qm", "replacement terminal source"],
                            check=True,
                            capture_output=True,
                        )

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.begin_cycle(root, self.plan_ref, payload)

                self.assertEqual(rejected.exception.reason_code, "followup_capture_bootstrap_admission_invalid")
                self.assertEqual(self._cycle_names(root), [])

    def test_active_cycle_invalidates_an_earlier_ready_admission_without_second_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            ready = self._payload(root)
            first = capture.begin_cycle(root, self.plan_ref, ready)

            with self.assertRaises(capture.CaptureError) as rejected:
                capture.begin_cycle(root, self.plan_ref, ready)

            cycle_names = self._cycle_names(root)

        self.assertEqual(rejected.exception.reason_code, "followup_capture_bootstrap_admission_invalid")
        self.assertEqual(cycle_names, [str(first["capture_cycle_id"])])


class OrdinaryCompactFollowupsV2Tests(unittest.TestCase):
    plan_ref = "docs/plans/260818_0024_ordinary_compact_fixture.md"
    code_draft_ref = "docs/code_drafts/260818_0024_ordinary_compact_fixture__code_draft.md"
    review_ref = "docs/code_reviews/260818_0024_ordinary_compact_fixture.md"
    bundle_target_ref = "scripts/ordinary_compact_post_cas_fixture.py"

    def _commit(self, root: Path, message: str) -> None:
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            [
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit", "-qm", message,
            ],
            check=True,
            capture_output=True,
        )

    def _commit_paths(self, root: Path, message: str, *paths: str) -> None:
        subprocess.run(["git", "-C", str(root), "add", "--", *paths], check=True, capture_output=True)
        subprocess.run(
            [
                "git", "-C", str(root), "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                "commit", "-qm", message,
            ],
            check=True,
            capture_output=True,
        )

    def _root(
        self,
        tmpdir: str,
        *,
        baseline_count: int = 0,
        schema_version: str = "plan.v2",
        with_index: bool = False,
    ) -> Path:
        root = Path(tmpdir).resolve()
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/code_drafts").mkdir(parents=True)
        (root / "docs/code_reviews").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / "scripts").mkdir(parents=True)
        (root / self.bundle_target_ref).write_text("# canonical post-CAS target\n", encoding="utf-8")
        (root / self.code_draft_ref).write_text(
            "\n".join(
                [
                    "# Code draft: ordinary compact fixture",
                    "",
                    "```json",
                    json.dumps(
                        {
                            "code_draft_meta": {
                                "plan": self.plan_ref,
                                "cluster": "process",
                                "targets": [{"path": self.bundle_target_ref, "kind": "py"}],
                                "deleted_paths": [],
                            }
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (root / self.review_ref).write_text("# Code review — fixture\n\n**Status:** ✅ OK\n", encoding="utf-8")
        (root / self.plan_ref).write_text(
            "\n".join(
                [
                    "# terminal compact fixture",
                    "",
                    "**Status:** Done",
                    f"**Schema version:** {schema_version}",
                    "",
                    "**Context links (source of truth):**",
                    f"- Code draft(s): `{self.code_draft_ref}`",
                    "",
                    "## Review artifacts",
                    f"- Code review (primary): `{self.review_ref}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if with_index:
            (root / "docs/followups/index.md").write_text(
                "# Follow-ups — index\n\nfixture manual header\n",
                encoding="utf-8",
            )
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        self._commit(root, "terminal compact source")
        for index in range(baseline_count):
            (root / "docs/followups" / f"baseline-{index:03d}.md").write_text(
                "# baseline compatibility file\n",
                encoding="utf-8",
            )
        return root

    def _payload(
        self,
        root: Path,
        *,
        semantic_closeout_kind: str = "already_materialized",
    ) -> dict[str, object]:
        try:
            from scripts import docs_closeout
        except ModuleNotFoundError:
            import docs_closeout

        return {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": self.plan_ref,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": semantic_closeout_kind,
            "followups_bootstrap_admission": docs_closeout.classify_followups_bootstrap_admission(
                root,
                self.plan_ref,
            ),
        }

    def _begin(
        self,
        root: Path,
        *,
        materialize_coder_pi: bool = False,
        semantic_closeout_kind: str = "already_materialized",
    ) -> str:
        cycle_id = str(
            capture.begin_cycle(
                root,
                self.plan_ref,
                self._payload(root, semantic_closeout_kind=semantic_closeout_kind),
            )["capture_cycle_id"]
        )
        noop = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        suggestion = (
            "## Process improvements\n"
            "### Suggestion 1\n"
            "- symptom: replay fixture needs a current-cycle PI tail\n"
            "- process_gap: post-CAS replay coverage omitted PI-only descendants\n"
            "- suggested_fix: retain exact marker-bound replay after the PI commit\n"
            "- owner: Architect\n"
            "- promotion_class: helper_change\n"
            "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
            f"- source_ref: {self.plan_ref}\n"
        )
        texts = {
            "Architect": noop,
            "Coder": suggestion if materialize_coder_pi else noop,
            "Planner": noop,
            "Reviewer": "## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n" if materialize_coder_pi else noop,
        }
        for role in capture.REQUIRED_ROLES:
            capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=self.plan_ref,
                text=texts[role],
                followups_capture_cycle_id=cycle_id,
            )
        capture.checkpoint_general_pi(root, self.plan_ref, cycle_id)
        return cycle_id

    def _row(self) -> dict[str, object]:
        return {
            "priority": "P1",
            "summary": "Ordinary compact declaration fixture",
            "cluster": "process",
            "to": "coder",
            "status": "open",
            "plan": None,
            "why": "prove helper-owned ordinary compact binding",
            "tags": ["compact-fixture"],
            "item_id": "ordinary-compact-001",
            "source_ref": self.plan_ref,
            "disposition_kind": None,
            "disposition_ref": None,
            "disposition_commit_oid": None,
            "reason": None,
        }

    def _compact(self, role: str, *, rows: list[dict[str, object]] | None = None) -> bytes:
        value: dict[str, object] = {
            "role": role,
            "proposed_rows": rows or [],
            "role_no_items_reason": None if rows else f"{role} found no ordinary compact rows.",
        }
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _bind_all(
        self,
        root: Path,
        cycle_id: str,
        *,
        row_role: str | None = None,
        row_payload: dict[str, object] | None = None,
    ) -> None:
        try:
            from scripts import followups_lint
        except ModuleNotFoundError:
            import followups_lint

        for role in capture.REQUIRED_ROLES:
            capture.prepare_role(root, self.plan_ref, cycle_id, role)
            rows: list[dict[str, object]] = []
            if role == row_role:
                payload = dict(row_payload) if row_payload is not None else self._row()
                rows = [{
                    "followup_path": "docs/followups/ordinary_compact_fixture.md",
                    "payload": payload,
                    "row_digest": followups_lint.v2_row_digest(payload),
                }]
            submitted = capture.submit_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role=role,
                raw_input=self._compact(role, rows=rows),
                write=True,
            )
            self.assertIn(submitted["state"], {"submitted", "already_submitted"})
            bound = capture.bind_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role=role,
                submission_current=True,
                write=True,
            )
            self.assertEqual(bound["state"], "bound")
            self.assertNotIn("baseline_followups_snapshot", bound)
            self.assertNotIn("source_terminal_commit_oid", bound)

    def _ordinary_receipt_path(self, root: Path, cycle_id: str) -> Path:
        return root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME

    def _rewrite_ordinary_receipt(self, path: Path, receipt: dict[str, object]) -> None:
        receipt["receipt_content_sha256"] = capture.receipt_content_sha256(receipt)
        path.write_bytes(capture.persisted_receipt_bytes(receipt))

    def _binding_predecessor_and_frozen_index_successor(
        self,
        root: Path,
    ) -> tuple[str, str, dict[str, object]]:
        predecessor_cycle_id = self._begin(root)
        self._bind_all(root, predecessor_cycle_id)
        predecessor = json.loads(self._ordinary_receipt_path(root, predecessor_cycle_id).read_text(encoding="utf-8"))
        self.assertEqual(predecessor[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")

        successor_cycle_id = self._begin(root)
        self._bind_all(root, successor_cycle_id, row_role="Coder")
        frozen = capture.freeze_ordinary_v2(
            root,
            plan_ref=self.plan_ref,
            capture_cycle_id=successor_cycle_id,
            write=True,
        )
        successor = json.loads(self._ordinary_receipt_path(root, successor_cycle_id).read_text(encoding="utf-8"))
        self.assertEqual(successor[capture.ORDINARY_V2_BINDING_KEY]["state"], "frozen")
        manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
        return predecessor_cycle_id, successor_cycle_id, manifest

    def _assert_index_apply_refusal_preserves_followups(
        self,
        root: Path,
        manifest: dict[str, object],
        *,
        owner_cycle_id: str,
        reason_code: str,
    ) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        before = capture.snapshot_followups(root, include_bytes=True)
        with self.assertRaises(followups_apply.ApplyError) as rejected:
            followups_apply.apply_frozen_rows(root, manifest, mutate=True)
        self.assertEqual(rejected.exception.reason_code, reason_code)
        self.assertEqual(capture.snapshot_followups(root, include_bytes=True), before)
        self.assertFalse(
            (
                root
                / capture.followups_index_refresh_receipt_relpath(
                    self.plan_ref,
                    owner_cycle_id,
                )
            ).exists()
        )

    @unittest.skipUnless(Path("/dev/fd").is_dir(), "/dev/fd is unavailable")
    def test_ordinary_compact_four_binds_keep_descriptor_count_stable(self) -> None:
        """Four in-process binds must not retain one submission directory each."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            before = len(os.listdir("/dev/fd"))
            self._bind_all(root, cycle_id)
            after = len(os.listdir("/dev/fd"))

        self.assertEqual(after, before)

    def test_ordinary_compact_role_local_subprocess_submission_is_immutable_before_bind(self) -> None:
        """A finite producer owns the slot; Manager only binds the current slot."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            receipt_before = receipt_path.read_bytes()
            command = [
                sys.executable,
                str(Path(capture.__file__).resolve()),
                "submit-ordinary-v2",
                "--project-root", str(root),
                "--plan-ref", self.plan_ref,
                "--capture-cycle-id", cycle_id,
                "--role", "Architect",
                "--input", "-",
                "--write",
            ]

            first = subprocess.run(command, cwd=root, input=self._compact("Architect"), capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr.decode("utf-8", errors="replace"))
            acknowledgement = json.loads(first.stdout)
            self.assertEqual(acknowledgement["schema_version"], capture.ORDINARY_V2_SUBMISSION_ACK_SCHEMA)
            self.assertEqual(acknowledgement["state"], "submitted")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            submission_path = root / acknowledgement["submission_path"]
            submission_before = submission_path.read_bytes()
            self.assertTrue(stat.S_ISREG(submission_path.stat().st_mode))
            self.assertEqual(stat.S_IMODE(submission_path.stat().st_mode), 0o600)

            replay = subprocess.run(command, cwd=root, input=self._compact("Architect"), capture_output=True)
            self.assertEqual(replay.returncode, 0, replay.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(json.loads(replay.stdout)["state"], "already_submitted")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertEqual(submission_path.read_bytes(), submission_before)

            conflicting = json.dumps(
                {
                    "role": "Architect",
                    "proposed_rows": [],
                    "role_no_items_reason": "A different producer result must not replace the slot.",
                },
                separators=(",", ":"),
            ).encode("utf-8")
            conflict = subprocess.run(command, cwd=root, input=conflicting, capture_output=True)
            self.assertEqual(conflict.returncode, 2)
            self.assertEqual(
                json.loads(conflict.stdout)["reason_code"],
                "followup_ordinary_v2_submission_conflict",
            )
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertEqual(submission_path.read_bytes(), submission_before)

            bound = capture.bind_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Architect",
                submission_current=True,
                write=True,
            )

        self.assertEqual(bound["state"], "bound")

    def test_ordinary_compact_prepare_provisions_current_input_directory_without_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            prepared = capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            input_dir = root / capture._ordinary_v2_input_dir_relpath(self.plan_ref, cycle_id)
            leaf = input_dir / "Architect.json"

            self.assertEqual(prepared["reason_code"], "role_prepared")
            self.assertTrue(input_dir.is_dir())
            self.assertEqual(stat.S_IMODE(input_dir.stat().st_mode), 0o700)
            self.assertFalse(os.path.lexists(leaf))

            replay = capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")

        self.assertEqual(replay["reason_code"], "already_prepared")
        self.assertFalse(os.path.lexists(leaf))

    def test_ordinary_compact_input_current_cli_recovers_prepared_reviewer_without_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            for role in ("Architect", "Coder", "Planner"):
                capture.prepare_role(root, self.plan_ref, cycle_id, role)
                capture.submit_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role=role,
                    raw_input=self._compact(role),
                    write=True,
                )
                capture.bind_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role=role,
                    submission_current=True,
                    write=True,
                )
            capture.prepare_role(root, self.plan_ref, cycle_id, "Reviewer")
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            receipt_before = receipt_path.read_bytes()
            leaf = root / capture._ordinary_v2_input_role_relpath(self.plan_ref, cycle_id, "Reviewer")
            submission_path = root / capture._ordinary_v2_submission_role_relpath(self.plan_ref, cycle_id, "Reviewer")
            base_command = [
                sys.executable,
                str(Path(capture.__file__).resolve()),
                "submit-ordinary-v2",
                "--project-root", str(root),
                "--plan-ref", self.plan_ref,
                "--capture-cycle-id", cycle_id,
                "--role", "Reviewer",
            ]

            stdin_failure = subprocess.run(
                [*base_command, "--input", "-", "--write"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
            )
            self.assertEqual(stdin_failure.returncode, 2)
            self.assertEqual(json.loads(stdin_failure.stdout)["reason_code"], "followup_ordinary_v2_input_invalid")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertFalse(submission_path.exists())

            missing_failure = subprocess.run(
                [*base_command, "--input-current", "--write"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
            )
            self.assertEqual(missing_failure.returncode, 2)
            self.assertEqual(json.loads(missing_failure.stdout)["reason_code"], "followup_ordinary_v2_input_missing")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertFalse(submission_path.exists())

            leaf.write_bytes(b"")
            empty_failure = subprocess.run(
                [*base_command, "--input-current", "--write"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
            )
            self.assertEqual(empty_failure.returncode, 2)
            self.assertEqual(json.loads(empty_failure.stdout)["reason_code"], "followup_ordinary_v2_input_invalid")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertFalse(submission_path.exists())

            leaf.write_bytes(self._compact("Reviewer"))
            recovered = subprocess.run(
                [*base_command, "--input-current", "--write"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr.decode("utf-8", errors="replace"))
            acknowledgement = json.loads(recovered.stdout)
            self.assertEqual(acknowledgement["state"], "submitted")
            self.assertEqual(leaf.read_bytes(), self._compact("Reviewer"))
            bound = capture.bind_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Reviewer",
                submission_current=True,
                write=True,
            )

        self.assertEqual(bound["state"], "bound")

    def test_ordinary_compact_current_input_rejects_unsafe_and_read_drift_without_publication(self) -> None:
        cases = ("missing", "empty", "oversize", "oversize_larger", "malformed", "symlink", "drift")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                cycle_id = self._begin(root)
                capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                receipt_before = receipt_path.read_bytes()
                leaf = root / capture._ordinary_v2_input_role_relpath(self.plan_ref, cycle_id, "Architect")
                submission_path = root / capture._ordinary_v2_submission_role_relpath(self.plan_ref, cycle_id, "Architect")
                expected = {
                    "missing": "followup_ordinary_v2_input_missing",
                    "empty": "followup_ordinary_v2_input_invalid",
                    "oversize": "followup_ordinary_v2_input_too_large",
                    "oversize_larger": "followup_ordinary_v2_input_too_large",
                    "malformed": "followup_ordinary_v2_input_invalid",
                    "symlink": "followup_ordinary_v2_input_path_unsafe",
                    "drift": "followup_ordinary_v2_input_path_drift",
                }[case]
                if case == "empty":
                    leaf.write_bytes(b"")
                elif case == "oversize":
                    leaf.write_bytes(b" " * (capture.ORDINARY_V2_COMPACT_MAX_BYTES + 1))
                elif case == "oversize_larger":
                    leaf.write_bytes(b" " * (capture.ORDINARY_V2_COMPACT_MAX_BYTES + 2))
                elif case == "malformed":
                    leaf.write_bytes(b"not valid JSON")
                elif case == "symlink":
                    target = leaf.with_name("unsafe-target.json")
                    target.write_bytes(self._compact("Architect"))
                    os.symlink(target.name, leaf)
                elif case == "drift":
                    leaf.write_bytes(self._compact("Architect"))

                if case == "drift":
                    original_read = capture._ordinary_v2_read_fd_limited

                    def mutate_during_read(fd: int, *, limit: int) -> bytes:
                        raw = original_read(fd, limit=limit)
                        leaf.write_bytes(raw + b" ")
                        return raw

                    with mock.patch.object(capture, "_ordinary_v2_read_fd_limited", side_effect=mutate_during_read):
                        with self.assertRaises(capture.CaptureError) as rejected:
                            capture.submit_ordinary_v2(
                                root,
                                plan_ref=self.plan_ref,
                                capture_cycle_id=cycle_id,
                                role="Architect",
                                input_current=True,
                                write=True,
                            )
                else:
                    with self.assertRaises(capture.CaptureError) as rejected:
                        capture.submit_ordinary_v2(
                            root,
                            plan_ref=self.plan_ref,
                            capture_cycle_id=cycle_id,
                            role="Architect",
                            input_current=True,
                            write=True,
                        )

                self.assertEqual(rejected.exception.reason_code, expected)
                self.assertEqual(receipt_path.read_bytes(), receipt_before)
                self.assertFalse(submission_path.exists())

    def test_ordinary_compact_current_input_replay_precedes_leaf_read_and_cleanup_is_identity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            leaf = root / capture._ordinary_v2_input_role_relpath(self.plan_ref, cycle_id, "Architect")
            leaf.write_bytes(self._compact("Architect"))
            first = capture.submit_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Architect",
                input_current=True,
                write=True,
            )
            self.assertEqual(first["state"], "submitted")
            self.assertEqual(leaf.read_bytes(), self._compact("Architect"))
            leaf.unlink()
            os.symlink("missing-replacement.json", leaf)

            replay = capture.submit_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Architect",
                input_current=True,
                write=True,
            )
            bound = capture.bind_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Architect",
                submission_current=True,
                write=True,
            )

            self.assertEqual(replay["state"], "already_submitted")
            self.assertTrue(os.path.lexists(leaf))
            self.assertEqual(bound["state"], "bound")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            leaf = root / capture._ordinary_v2_input_role_relpath(self.plan_ref, cycle_id, "Architect")
            leaf.write_bytes(self._compact("Architect"))
            replacement = leaf.with_name("replacement.json")
            original_write = capture._ordinary_v2_write_submission
            original_unlink = capture.os.unlink
            leaf_unlink_attempts: list[str] = []

            # This is the former post-publish cleanup window.  Retention must
            # leave the replacement intact and make no role-leaf unlink call.
            def replace_after_publish(*args: object, **kwargs: object) -> tuple[str, str, dict[str, object], bool]:
                result = original_write(*args, **kwargs)
                replacement.write_bytes(b"replacement must survive post-publish retention")
                os.replace(replacement, leaf)
                return result

            def record_leaf_unlink(path: str, *args: object, **kwargs: object) -> None:
                if path == "Architect.json":
                    leaf_unlink_attempts.append(path)
                original_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(capture, "_ordinary_v2_write_submission", side_effect=replace_after_publish),
                mock.patch.object(capture.os, "unlink", side_effect=record_leaf_unlink),
            ):
                acknowledged = capture.submit_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role="Architect",
                    input_current=True,
                    write=True,
                )

            self.assertEqual(acknowledged["state"], "submitted")
            self.assertEqual(leaf.read_bytes(), b"replacement must survive post-publish retention")
            self.assertEqual(leaf_unlink_attempts, [])
            self.assertTrue((root / acknowledged["submission_path"]).is_file())

    def test_ordinary_compact_submission_fails_closed_on_prepared_receipt_drift_or_unsafe_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            capture.submit_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role="Architect",
                raw_input=self._compact("Architect"),
                write=True,
            )
            with capture.CaptureHost(root, self.plan_ref) as host:
                cycle_fd, _identity = capture._open_cycle(host, cycle_id)
                try:
                    receipt, raw, _receipt_identity = capture._read_receipt(cycle_fd, self.plan_ref, cycle_id)
                    capture._publish_mutation(host, cycle_fd, cycle_id, raw, capture._next_receipt(receipt))
                finally:
                    os.close(cycle_fd)
            with self.assertRaises(capture.CaptureError) as drifted:
                capture.bind_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role="Architect",
                    submission_current=True,
                    write=True,
                )

            self.assertEqual(drifted.exception.reason_code, "followup_ordinary_v2_submission_prepared_receipt_drift")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            receipt_before = receipt_path.read_bytes()
            submission_dir = root / capture._ordinary_v2_submission_dir_relpath(self.plan_ref, cycle_id)
            submission_dir.mkdir(parents=True)
            os.chmod(submission_dir, 0o700)
            os.symlink("not-a-submission", submission_dir / "Architect.json")
            with self.assertRaises(capture.CaptureError) as unsafe:
                capture.submit_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role="Architect",
                    raw_input=self._compact("Architect"),
                    write=True,
                )

            self.assertEqual(unsafe.exception.reason_code, "followup_ordinary_v2_submission_path_unsafe")
            self.assertEqual(receipt_path.read_bytes(), receipt_before)

    def _write_existing_carrier(self, root: Path, payload: dict[str, object] | None = None) -> tuple[str, bytes]:
        try:
            from scripts import followups_apply, followups_lint
        except ModuleNotFoundError:
            import followups_apply
            import followups_lint

        carrier_path = "docs/followups/ordinary_compact_fixture.md"
        carrier = root / carrier_path
        carrier.write_text(
            followups_apply._new_v2_file_text(carrier_path) + followups_lint.render_v2_row(payload or self._row()),
            encoding="utf-8",
        )
        return carrier_path, carrier.read_bytes()

    def _apply_row_bearing_cycle(
        self,
        root: Path,
        *,
        semantic_closeout_kind: str = "already_materialized",
    ) -> tuple[str, str]:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        cycle_id = self._begin(root, semantic_closeout_kind=semantic_closeout_kind)
        self._bind_all(root, cycle_id, row_role="Coder")
        frozen = capture.freeze_ordinary_v2(
            root,
            plan_ref=self.plan_ref,
            capture_cycle_id=cycle_id,
            write=True,
        )
        manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
        self.assertEqual(followups_apply.apply_frozen_rows(root, manifest, mutate=True)["state"], "applied")
        return cycle_id, "docs/followups/ordinary_compact_fixture.md"

    def test_ordinary_compact_zero_122_baseline_freezes_and_reads_clean_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir, baseline_count=122)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id)
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            self.assertEqual(frozen["state"], "frozen")
            self.assertEqual(frozen["expected_owned_tuples"], [])
            self.assertFalse((root / "docs/followups/ordinary_compact_fixture.md").exists())
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(receipt["state"], "clean_noop")
        self.assertEqual(receipt["completed_roles"], list(capture.REQUIRED_ROLES))

    def test_ordinary_compact_nonempty_post_apply_allowance_is_exact(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            self.assertEqual(followups_apply.apply_frozen_rows(root, manifest, mutate=True)["state"], "applied")
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)
            (root / "docs/followups/foreign.md").write_text("# foreign\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as drift:
                capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(receipt["state"], "clean_noop")
        self.assertEqual(drift.exception.reason_code, "followup_capture_path_object_drift")

    def test_ordinary_compact_index_transaction_requires_one_exact_receipt_and_tree_pair(self) -> None:
        try:
            from scripts import followups_apply, followups_index_rebuild
        except ModuleNotFoundError:
            import followups_apply
            import followups_index_rebuild

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir, with_index=True)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            carrier_path = "docs/followups/ordinary_compact_fixture.md"
            index_path = "docs/followups/index.md"
            index_before = (root / index_path).read_bytes()

            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            receipt, receipt_object = capture.read_followups_index_refresh_receipt(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
            )
            readback = capture.read_capture(root, self.plan_ref, cycle_id)

            self.assertEqual(applied["state"], "applied")
            self.assertEqual(applied["changed_paths"], [index_path, carrier_path])
            self.assertEqual(set(receipt), {
                "authoritative_followups_manifest_sha256",
                "capture_cycle_id",
                "changed_paths",
                "index_after_sha256",
                "index_before_sha256",
                "owner_id",
                "rendered_summary_sha256",
                "state",
            })
            self.assertEqual(receipt["capture_cycle_id"], cycle_id)
            self.assertEqual(receipt["changed_paths"], [index_path, carrier_path])
            self.assertEqual(receipt["owner_id"], capture.FOLLOWUPS_INDEX_REFRESH_OWNER_ID)
            self.assertEqual(receipt["state"], "updated")
            self.assertIn(".tmp/followups_capture/", str(receipt_object["path"]))
            self.assertNotEqual((root / index_path).read_bytes(), index_before)
            self.assertTrue(followups_index_rebuild.check_index(root).ok)
            self.assertEqual(readback["state"], "clean_noop")

            self._commit_paths(root, "land raw and generated terminal followups pair", carrier_path, index_path)
            committed = capture.read_capture(root, self.plan_ref, cycle_id)
            changed = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", "HEAD^", "HEAD", "--", "docs/followups"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()

        self.assertEqual(changed, [index_path, carrier_path])
        self.assertEqual(committed["state"], "clean_noop")

    def test_ordinary_compact_index_binding_predecessor_skips_to_exact_frozen_successor(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir, with_index=True)
            predecessor_cycle_id, successor_cycle_id, manifest = self._binding_predecessor_and_frozen_index_successor(root)
            predecessor_path = self._ordinary_receipt_path(root, predecessor_cycle_id)
            predecessor_before = predecessor_path.read_bytes()
            before = capture.snapshot_followups(root, include_bytes=True)

            preflight = followups_apply.apply_frozen_rows(root, manifest, mutate=False)
            self.assertEqual(preflight["state"], "preflight")
            self.assertEqual(capture.snapshot_followups(root, include_bytes=True), before)

            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            refresh_receipt = applied["followups_index_refresh_receipt"]

            self.assertNotEqual(predecessor_cycle_id, successor_cycle_id)
            self.assertEqual(applied["state"], "applied")
            self.assertEqual(
                applied["changed_paths"],
                ["docs/followups/index.md", "docs/followups/ordinary_compact_fixture.md"],
            )
            self.assertEqual(refresh_receipt["capture_cycle_id"], successor_cycle_id)
            self.assertEqual(capture.read_capture(root, self.plan_ref, successor_cycle_id)["state"], "clean_noop")
            self.assertEqual(predecessor_path.read_bytes(), predecessor_before)

    def test_ordinary_compact_index_finder_rejects_invalid_binding_or_frozen_proof_without_mutation(self) -> None:
        for case, expected_reason in (
            ("malformed_binding", "followup_ordinary_v2_marker_invalid"),
            ("frozen_source", "followup_v2_source_commit_missing"),
            ("frozen_bound", "followup_ordinary_v2_path_object_drift"),
            ("frozen_manifest", "followups_index_refresh_binding_invalid"),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir, with_index=True)
                predecessor_cycle_id, successor_cycle_id, manifest = self._binding_predecessor_and_frozen_index_successor(root)
                predecessor_path = self._ordinary_receipt_path(root, predecessor_cycle_id)
                successor_path = self._ordinary_receipt_path(root, successor_cycle_id)

                if case == "malformed_binding":
                    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
                    predecessor[capture.ORDINARY_V2_BINDING_KEY]["unexpected"] = True
                    self._rewrite_ordinary_receipt(predecessor_path, predecessor)
                elif case == "frozen_source":
                    successor = json.loads(successor_path.read_text(encoding="utf-8"))
                    successor[capture.ORDINARY_V2_BINDING_KEY]["source_identity"]["source_terminal_commit_oid"] = "0" * 40
                    self._rewrite_ordinary_receipt(successor_path, successor)
                elif case == "frozen_bound":
                    bound_path = root / capture._ordinary_v2_bound_role_relpath(
                        self.plan_ref,
                        successor_cycle_id,
                        "Coder",
                    )
                    bound = json.loads(bound_path.read_text(encoding="utf-8"))
                    bound["role_no_items_reason"] = "corrupted bound declaration"
                    bound_path.write_bytes(capture._canonical_json_bytes(bound) + b"\n")
                else:
                    successor = json.loads(successor_path.read_text(encoding="utf-8"))
                    successor[capture.ORDINARY_V2_BINDING_KEY]["frozen_manifest_sha256"] = "0" * 64
                    self._rewrite_ordinary_receipt(successor_path, successor)

                self._assert_index_apply_refusal_preserves_followups(
                    root,
                    manifest,
                    owner_cycle_id=successor_cycle_id,
                    reason_code=expected_reason,
                )

    def test_ordinary_compact_index_finder_rejects_ambiguous_or_missing_owner_without_mutation(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        for case, expected_reason in (
            ("ambiguous", "followups_index_refresh_binding_ambiguous"),
            ("missing", "followups_index_refresh_binding_missing"),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir, with_index=True)
                if case == "ambiguous":
                    first_cycle_id = self._begin(root)
                    self._bind_all(root, first_cycle_id, row_role="Coder")
                    first_frozen = capture.freeze_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=first_cycle_id,
                        write=True,
                    )
                    manifest_path = root / str(first_frozen["frozen_manifest_path"])
                    first_manifest = manifest_path.read_bytes()
                    manifest_path.unlink()
                    second_cycle_id = self._begin(root)
                    self._bind_all(root, second_cycle_id, row_role="Coder")
                    second_frozen = capture.freeze_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=second_cycle_id,
                        write=True,
                    )
                    manifest = json.loads((root / str(second_frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
                    self.assertEqual((root / str(second_frozen["frozen_manifest_path"])).read_bytes(), first_manifest)
                    owner_cycle_id = second_cycle_id
                else:
                    _predecessor_cycle_id, successor_cycle_id, manifest = self._binding_predecessor_and_frozen_index_successor(root)
                    successor_dir = self._ordinary_receipt_path(root, successor_cycle_id).parent
                    os.rename(successor_dir, successor_dir.with_name("not-an-owner"))
                    owner_cycle_id = successor_cycle_id

                before = capture.snapshot_followups(root, include_bytes=True)
                with self.assertRaises(followups_apply.ApplyError) as rejected:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)
                self.assertEqual(rejected.exception.reason_code, expected_reason)
                self.assertEqual(capture.snapshot_followups(root, include_bytes=True), before)
                self.assertFalse(
                    (
                        root
                        / capture.followups_index_refresh_receipt_relpath(
                            self.plan_ref,
                            owner_cycle_id,
                        )
                    ).exists()
                )

    def test_ordinary_compact_index_readback_rejects_promoted_lifecycle_drift(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir, with_index=True)
            target_ref = "docs/plans/260831_0002_promoted_target.md"
            target = root / target_ref
            target.write_text("# promoted target\n\n**Status:** In progress\n", encoding="utf-8")
            self._commit(root, "add promoted target")
            target_commit = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            promoted = self._row()
            promoted.update(
                {
                    "status": "promoted",
                    "plan": target_ref,
                    "disposition_kind": "promoted_plan",
                    "disposition_ref": target_ref,
                    "disposition_commit_oid": target_commit,
                    "reason": "Fixture commit materialized the promoted target.",
                }
            )
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id, row_role="Coder", row_payload=promoted)
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            self.assertEqual(followups_apply.apply_frozen_rows(root, manifest, mutate=True)["state"], "applied")
            self.assertEqual(capture.read_capture(root, self.plan_ref, cycle_id)["state"], "clean_noop")

            target.write_text("# promoted target\n\n**Status:** Done\n", encoding="utf-8")
            with self.assertRaises(capture.CaptureError) as drift:
                capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(drift.exception.reason_code, "missing_or_mismatched_v2_tuple_proof")

    def test_ordinary_compact_index_receipt_publish_failure_restores_the_full_pair(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir, with_index=True)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            carrier_path = "docs/followups/ordinary_compact_fixture.md"
            index_path = "docs/followups/index.md"
            index_before = (root / index_path).read_bytes()
            publish = followups_apply.followups_capture.publish_followups_index_refresh_receipt

            def publish_then_fail(*args: object, **kwargs: object) -> tuple[dict[str, object], dict[str, object], bool]:
                publish(*args, **kwargs)
                raise capture.CaptureError(
                    "followups_index_refresh_receipt_publish_failed",
                    "injected failure after the receipt became visible",
                )

            with mock.patch.object(
                followups_apply.followups_capture,
                "publish_followups_index_refresh_receipt",
                side_effect=publish_then_fail,
            ):
                with self.assertRaises(followups_apply.ApplyError) as failed:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            self.assertEqual(failed.exception.reason_code, "followups_index_refresh_receipt_publish_failed")
            self.assertFalse((root / carrier_path).exists())
            self.assertEqual((root / index_path).read_bytes(), index_before)
            with self.assertRaises(capture.CaptureError) as receipt_missing:
                capture.read_followups_index_refresh_receipt(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                )

        self.assertEqual(receipt_missing.exception.reason_code, "followups_index_refresh_receipt_missing")

    def test_ordinary_compact_existing_carrier_exact_replay_is_idempotent_and_reads_clean_noop(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            carrier_path, carrier_before = self._write_existing_carrier(root)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)
            self.assertEqual(applied["state"], "idempotent")
            self.assertEqual(applied["changed_paths"], [])
            self.assertEqual((root / carrier_path).read_bytes(), carrier_before)
            self.assertEqual(receipt["state"], "clean_noop")

    def test_ordinary_compact_source_carried_exact_replay_survives_pi_only_descendant(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            carrier_path, carrier_before = self._write_existing_carrier(root)
            self._commit_paths(root, "commit exact ordinary compact baseline carrier", carrier_path)
            source_oid = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            canonical_oid = subprocess.run(
                ["git", "-C", str(root), "hash-object", "--stdin"],
                input=carrier_before,
                check=True,
                capture_output=True,
            ).stdout.decode("ascii").strip()
            source_entry = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-z", source_oid, "--", carrier_path],
                check=True,
                capture_output=True,
            ).stdout
            cycle_id = self._begin(root, materialize_coder_pi=True)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(applied["state"], "idempotent")
            self.assertEqual(applied["changed_paths"], [])
            self.assertEqual((root / carrier_path).read_bytes(), carrier_before)
            self.assertEqual(capture.read_capture(root, self.plan_ref, cycle_id)["state"], "clean_noop")

            pi_paths = sorted(capture.snapshot_process_improvement_data_files(root, self.plan_ref))
            self.assertTrue(pi_paths)
            self._commit_paths(root, "land current-cycle process-improvement tail", *pi_paths)
            followup_delta = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", source_oid, "HEAD", "--", "docs/followups"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            head_entry = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-z", "HEAD", "--", carrier_path],
                check=True,
                capture_output=True,
            ).stdout
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(source_entry, f"100644 blob {canonical_oid}\t{carrier_path}\0".encode("utf-8"))
        self.assertEqual(head_entry, f"100644 blob {canonical_oid}\t{carrier_path}\0".encode("utf-8"))
        self.assertEqual(followup_delta, [])
        self.assertEqual(receipt["state"], "clean_noop")

    def test_ordinary_compact_baseline_carrier_absent_from_source_survives_carrier_and_pi_descendant(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            carrier_path, carrier_before = self._write_existing_carrier(root)
            source_oid = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            canonical_oid = subprocess.run(
                ["git", "-C", str(root), "hash-object", "--stdin"],
                input=carrier_before,
                check=True,
                capture_output=True,
            ).stdout.decode("ascii").strip()
            source_entry = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-z", source_oid, "--", carrier_path],
                check=True,
                capture_output=True,
            ).stdout
            cycle_id = self._begin(root, materialize_coder_pi=True)
            self._bind_all(root, cycle_id, row_role="Coder")
            frozen = capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                write=True,
            )
            manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(applied["state"], "idempotent")
            self.assertEqual(applied["changed_paths"], [])
            self.assertEqual((root / carrier_path).read_bytes(), carrier_before)
            self.assertEqual(capture.read_capture(root, self.plan_ref, cycle_id)["state"], "clean_noop")

            pi_paths = sorted(capture.snapshot_process_improvement_data_files(root, self.plan_ref))
            self.assertTrue(pi_paths)
            self._commit_paths(
                root,
                "land baseline carrier and current-cycle process-improvement tail",
                carrier_path,
                *pi_paths,
            )
            followup_delta = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-only", source_oid, "HEAD", "--", "docs/followups"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            head_entry = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-z", "HEAD", "--", carrier_path],
                check=True,
                capture_output=True,
            ).stdout
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(source_entry, b"")
        self.assertEqual(head_entry, f"100644 blob {canonical_oid}\t{carrier_path}\0".encode("utf-8"))
        self.assertEqual(followup_delta, [carrier_path])
        self.assertEqual(receipt["state"], "clean_noop")

    def test_ordinary_compact_noncanonical_source_entry_is_rejected_before_manifest(self) -> None:
        for case in ("source_executable", "source_gitlink", "source_symlink", "source_wrong_oid"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                carrier_path, carrier_before = self._write_existing_carrier(root)
                carrier = root / carrier_path
                if case == "source_executable":
                    carrier.chmod(0o755)
                    self._commit_paths(root, "commit executable ordinary compact source carrier", carrier_path)
                    carrier.chmod(0o644)
                elif case == "source_gitlink":
                    source_target = subprocess.run(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    carrier.unlink()
                    subprocess.run(
                        [
                            "git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                            "160000", source_target, carrier_path,
                        ],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test', "commit", "-qm", "commit gitlink source carrier",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    carrier.write_bytes(carrier_before)
                elif case == "source_symlink":
                    carrier.unlink()
                    carrier.symlink_to("ordinary_compact_target.md")
                    self._commit_paths(root, "commit symlink ordinary compact source carrier", carrier_path)
                    carrier.unlink()
                    carrier.write_bytes(carrier_before)
                else:
                    carrier.write_text("# wrong ordinary compact source carrier\n", encoding="utf-8")
                    self._commit_paths(root, "commit wrong ordinary compact source carrier", carrier_path)
                    carrier.write_bytes(carrier_before)

                source_oid = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                source_entry = subprocess.run(
                    ["git", "-C", str(root), "ls-tree", "-z", source_oid, "--", carrier_path],
                    check=True,
                    capture_output=True,
                ).stdout
                canonical_oid = subprocess.run(
                    ["git", "-C", str(root), "hash-object", "--stdin"],
                    input=carrier_before,
                    check=True,
                    capture_output=True,
                ).stdout.decode("ascii").strip()
                cycle_id = self._begin(root)
                self._bind_all(root, cycle_id, row_role="Coder")
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                receipt_before = receipt_path.read_bytes()
                baseline_before, _contents = capture.snapshot_followups(root)
                manifest_path = capture.v2_frozen_manifest_path(root, self.plan_ref)

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.freeze_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        write=True,
                    )

                receipt_after = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_bound_family_invalid")
                self.assertNotEqual(source_entry, f"100644 blob {canonical_oid}\t{carrier_path}\0".encode("utf-8"))
                self.assertFalse(os.path.lexists(manifest_path))
                self.assertEqual(receipt_path.read_bytes(), receipt_before)
                self.assertEqual(receipt_after[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")
                self.assertEqual(capture.snapshot_followups(root)[0], baseline_before)
                self.assertEqual(carrier.read_bytes(), carrier_before)

    def test_ordinary_compact_noncanonical_source_entry_is_rejected_before_manifest_when_current_absent(self) -> None:
        for case in ("source_executable", "source_gitlink", "source_symlink", "source_wrong_oid"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                carrier_path, carrier_before = self._write_existing_carrier(root)
                carrier = root / carrier_path
                if case == "source_executable":
                    carrier.chmod(0o755)
                    self._commit_paths(root, "commit executable ordinary compact source carrier", carrier_path)
                    carrier.unlink()
                elif case == "source_gitlink":
                    source_target = subprocess.run(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    carrier.unlink()
                    subprocess.run(
                        [
                            "git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                            "160000", source_target, carrier_path,
                        ],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test', "commit", "-qm", "commit gitlink source carrier",
                        ],
                        check=True,
                        capture_output=True,
                    )
                elif case == "source_symlink":
                    carrier.unlink()
                    carrier.symlink_to("ordinary_compact_target.md")
                    self._commit_paths(root, "commit symlink ordinary compact source carrier", carrier_path)
                    carrier.unlink()
                else:
                    carrier.write_text("# wrong ordinary compact source carrier\n", encoding="utf-8")
                    self._commit_paths(root, "commit wrong ordinary compact source carrier", carrier_path)
                    carrier.unlink()

                source_oid = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                source_entry = subprocess.run(
                    ["git", "-C", str(root), "ls-tree", "-z", source_oid, "--", carrier_path],
                    check=True,
                    capture_output=True,
                ).stdout
                canonical_oid = subprocess.run(
                    ["git", "-C", str(root), "hash-object", "--stdin"],
                    input=carrier_before,
                    check=True,
                    capture_output=True,
                ).stdout.decode("ascii").strip()
                self.assertFalse(os.path.lexists(carrier))
                cycle_id = self._begin(root)
                self._bind_all(root, cycle_id, row_role="Coder")
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                receipt_before = receipt_path.read_bytes()
                baseline_before, _contents = capture.snapshot_followups(root)
                manifest_path = capture.v2_frozen_manifest_path(root, self.plan_ref)

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.freeze_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        write=True,
                    )

                receipt_after = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_bound_family_invalid")
                self.assertNotEqual(source_entry, f"100644 blob {canonical_oid}\t{carrier_path}\0".encode("utf-8"))
                self.assertNotIn(carrier_path, baseline_before)
                self.assertFalse(os.path.lexists(manifest_path))
                self.assertEqual(receipt_path.read_bytes(), receipt_before)
                self.assertEqual(receipt_after[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")
                self.assertEqual(capture.snapshot_followups(root)[0], baseline_before)
                self.assertFalse(os.path.lexists(carrier))

    def test_ordinary_compact_post_apply_tree_entry_contract_rejects_noncanonical_entries(self) -> None:
        for case in (
            "head_executable",
            "head_gitlink",
            "head_wrong_oid",
            "extra_followup",
            "source_executable",
            "source_gitlink",
            "source_wrong_oid",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                carrier_path, carrier_bytes = self._write_existing_carrier(root)
                source_oid = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if case == "source_executable":
                    carrier = root / carrier_path
                    carrier.chmod(0o755)
                    self._commit_paths(root, "commit executable source carrier", carrier_path)
                    source_oid = subprocess.run(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    carrier.chmod(0o644)
                    self._commit_paths(root, "normalize executable carrier head", carrier_path)
                elif case == "source_gitlink":
                    (root / carrier_path).unlink()
                    subprocess.run(
                        [
                            "git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                            "160000", source_oid, carrier_path,
                        ],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test', "commit", "-qm", "commit gitlink source carrier",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    source_oid = subprocess.run(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    (root / carrier_path).write_bytes(carrier_bytes)
                    self._commit_paths(root, "normalize gitlink carrier head", carrier_path)
                elif case == "source_wrong_oid":
                    (root / carrier_path).write_text("# wrong ordinary compact source carrier\n", encoding="utf-8")
                    self._commit_paths(root, "commit wrong source carrier bytes", carrier_path)
                    source_oid = subprocess.run(
                        ["git", "-C", str(root), "rev-parse", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    (root / carrier_path).write_bytes(carrier_bytes)
                    self._commit_paths(root, "restore canonical carrier head", carrier_path)
                elif case == "head_executable":
                    carrier = root / carrier_path
                    carrier.chmod(carrier.stat().st_mode | stat.S_IXUSR)
                    self._commit_paths(root, "commit executable carrier head", carrier_path)
                elif case == "head_gitlink":
                    (root / carrier_path).unlink()
                    subprocess.run(
                        [
                            "git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                            "160000", source_oid, carrier_path,
                        ],
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git", "-C", str(root), "-c", "user.name=Fixture",
                            "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test', "commit", "-qm", "commit gitlink carrier head",
                        ],
                        check=True,
                        capture_output=True,
                    )
                elif case == "head_wrong_oid":
                    (root / carrier_path).write_text("# wrong ordinary compact carrier\n", encoding="utf-8")
                    self._commit_paths(root, "commit wrong carrier bytes", carrier_path)
                else:
                    (root / "docs/followups/extra_after_commit.md").write_text("# extra followup\n", encoding="utf-8")
                    self._commit_paths(root, "commit carrier and extra followup", carrier_path, "docs/followups/extra_after_commit.md")

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture._ordinary_v2_validate_post_apply_head(
                        root,
                        source={"source_terminal_commit_oid": source_oid},
                        carrier_path=carrier_path,
                        carrier_bytes=carrier_bytes,
                    )

                self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_post_apply_invalid")

    def test_ordinary_compact_existing_carrier_mutations_are_rejected_before_manifest_or_apply(self) -> None:
        for case in ("new_tuple", "changed_tuple"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                carrier_path, carrier_before = self._write_existing_carrier(root)
                cycle_id = self._begin(root)
                replacement = self._row()
                if case == "new_tuple":
                    replacement["item_id"] = "ordinary-compact-002"
                    replacement["summary"] = "Ordinary compact existing-carrier new-tuple fixture"
                else:
                    replacement["summary"] = "Ordinary compact existing-carrier changed-tuple fixture"
                self._bind_all(root, cycle_id, row_role="Coder", row_payload=replacement)
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                receipt_before = receipt_path.read_bytes()
                baseline_before, _contents = capture.snapshot_followups(root)
                manifest_path = capture.v2_frozen_manifest_path(root, self.plan_ref)
                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.freeze_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        write=True,
                    )

                receipt_after = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_bound_family_invalid")
                self.assertFalse(os.path.lexists(manifest_path))
                self.assertEqual(receipt_path.read_bytes(), receipt_before)
                self.assertEqual(receipt_after[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")
                self.assertEqual(capture.snapshot_followups(root)[0], baseline_before)
                self.assertEqual((root / carrier_path).read_bytes(), carrier_before)

    def test_ordinary_compact_rejects_multi_carrier_union_before_manifest_or_apply(self) -> None:
        try:
            from scripts import followups_lint
        except ModuleNotFoundError:
            import followups_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            carrier_paths = {
                "Architect": "docs/followups/ordinary_compact_architect.md",
                "Coder": "docs/followups/ordinary_compact_coder.md",
            }
            for role in capture.REQUIRED_ROLES:
                capture.prepare_role(root, self.plan_ref, cycle_id, role)
                rows: list[dict[str, object]] = []
                if role in carrier_paths:
                    payload = self._row()
                    payload["item_id"] = f"ordinary-compact-{role.lower()}-001"
                    payload["summary"] = f"Ordinary compact {role} carrier fixture"
                    rows = [{
                        "followup_path": carrier_paths[role],
                        "payload": payload,
                        "row_digest": followups_lint.v2_row_digest(payload),
                    }]
                capture.submit_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role=role,
                    raw_input=self._compact(role, rows=rows),
                    write=True,
                )
                capture.bind_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role=role,
                    submission_current=True,
                    write=True,
                )

            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            receipt_before = receipt_path.read_bytes()
            baseline_before, _contents = capture.snapshot_followups(root)
            manifest_path = capture.v2_frozen_manifest_path(root, self.plan_ref)
            with self.assertRaises(capture.CaptureError) as rejected:
                capture.freeze_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    write=True,
                )

            receipt_after = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_bound_family_invalid")
            self.assertFalse(os.path.lexists(manifest_path))
            self.assertEqual(receipt_path.read_bytes(), receipt_before)
            self.assertEqual(receipt_after[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")
            self.assertEqual(capture.snapshot_followups(root)[0], baseline_before)
            for carrier_path in carrier_paths.values():
                self.assertFalse((root / carrier_path).exists())

    def test_ordinary_compact_post_commit_readback_keeps_only_marker_bound_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id, carrier_path = self._apply_row_bearing_cycle(root)
            self.assertEqual(capture.read_capture(root, self.plan_ref, cycle_id)["state"], "clean_noop")
            self._commit_paths(root, "land canonical ordinary compact carrier", carrier_path)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(root), "diff", "--name-only", "HEAD^", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.splitlines(),
                [carrier_path],
            )
            receipt = capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(receipt["state"], "clean_noop")

    def _post_cas_semantic_proof(self, root: Path, cycle_id: str, carrier_path: str) -> dict[str, object]:
        try:
            from scripts import docs_closeout
        except ModuleNotFoundError:
            import docs_closeout

        bundle_paths = list(
            capture._post_cas_semantic_identity_canonical_bundle_paths(
                root,
                plan_ref=self.plan_ref,
            )
        )
        self.assertNotIn(carrier_path, bundle_paths)
        proof = docs_closeout._post_cas_semantic_identity_proof(
            root=root,
            plan_ref=self.plan_ref,
            capture_cycle_id=cycle_id,
            semantic_fields=("Done", "done", "already_materialized"),
            bundle_payload={
                "plan": self.plan_ref,
                "bundle_ok": True,
                "closeout_kind": "already_materialized",
                "repo_roots": [{"repo_root": str(root), "bundle_paths": bundle_paths}],
            },
        )
        self.assertIsNotNone(proof)
        assert proof is not None
        return proof

    def test_ordinary_compact_post_cas_semantic_identity_transition_is_exact_and_read_only(self) -> None:
        cases = {
            "eligible": lambda proof: (("Done", "done", "already_materialized"), proof),
            "inverse": lambda proof: (("Done", "done", "staged_empty"), proof),
            "status": lambda proof: (("Superseded", "superseded", "already_materialized"), proof),
            "norm": lambda proof: (("Done", "superseded", "already_materialized"), proof),
            "other_kind": lambda proof: (("Done", "done", "commit_ready"), proof),
            "missing_proof": lambda proof: (("Done", "done", "already_materialized"), None),
            "stale_receipt": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "receipt_content_sha256": "0" * 64},
            ),
            "stale_plan": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "plan_sha256": "0" * 64},
            ),
            "stale_terminal_status": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "terminal_status_line": "**Status:** Superseded"},
            ),
            "stale_head": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "current_head": "0" * 40},
            ),
            "stale_source": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "source_plan_blob_oid": "0" * 40},
            ),
            "stale_manifest": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "frozen_manifest_sha256": "0" * 64},
            ),
            "stale_pi": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "pi_final_objects": {"docs/process_improvements/stale.md": {}}},
            ),
            "malformed_bundle": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "bundle_tree_entries": []},
            ),
            "ambiguous_bundle": lambda proof: (
                ("Done", "done", "already_materialized"),
                {**proof, "bundle_tree_entries": [*proof["bundle_tree_entries"], proof["bundle_tree_entries"][0]]},
            ),
            "omitted_canonical_member": lambda proof: (
                ("Done", "done", "already_materialized"),
                {
                    **proof,
                    "bundle_tree_entries": [
                        entry
                        for entry in proof["bundle_tree_entries"]
                        if entry["path"] != self.bundle_target_ref
                    ],
                },
            ),
            "missing_proof_field": lambda proof: (
                ("Done", "done", "already_materialized"),
                {key: value for key, value in proof.items() if key != "current_head"},
            ),
        }
        for case, configure in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                cycle_id, carrier_path = self._apply_row_bearing_cycle(
                    root,
                    semantic_closeout_kind="staged_empty",
                )
                self._commit_paths(root, "land exact post-CAS carrier", carrier_path)
                proof = self._post_cas_semantic_proof(root, cycle_id, carrier_path)
                fields, candidate = configure(json.loads(json.dumps(proof)))
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                before = receipt_path.read_bytes()

                if case == "eligible":
                    readback = capture.read_capture(
                        root,
                        self.plan_ref,
                        cycle_id,
                        semantic_fields=fields,
                        _post_cas_semantic_identity_proof=candidate,
                    )
                    self.assertEqual(readback["state"], "clean_noop")
                else:
                    with self.assertRaises(capture.CaptureError) as rejected:
                        capture.read_capture(
                            root,
                            self.plan_ref,
                            cycle_id,
                            semantic_fields=fields,
                            _post_cas_semantic_identity_proof=candidate,
                        )
                    self.assertEqual(rejected.exception.reason_code, "followup_capture_semantic_identity_mismatch")

                self.assertEqual(receipt_path.read_bytes(), before)

    def test_ordinary_compact_post_commit_readback_rejects_noncanonical_descendants(self) -> None:
        for case in ("changed_plan", "foreign_head", "carrier_bytes", "extra_followup"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                cycle_id, carrier_path = self._apply_row_bearing_cycle(root)
                self._commit_paths(root, "land canonical ordinary compact carrier", carrier_path)
                if case == "changed_plan":
                    (root / self.plan_ref).write_text(
                        "# changed terminal compact fixture\n\n**Status:** Done\n**Schema version:** plan.v2\n",
                        encoding="utf-8",
                    )
                    self._commit_paths(root, "mutate terminal plan", self.plan_ref)
                elif case == "foreign_head":
                    # The forged head carries the exact canonical tree, so only
                    # source ancestry—not a shallow path/blob comparison—can
                    # distinguish it from the valid post-CAS descendant.
                    canonical_tree = subprocess.run(
                        ["git", "-C", str(root), "write-tree"],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    strict_identity_env = {
                        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
                    }
                    strict_identity_env.update(
                        {
                            "HOME": str(root / "strict-identity-home"),
                            "XDG_CONFIG_HOME": str(root / "strict-identity-xdg"),
                            "GIT_CONFIG_NOSYSTEM": "1",
                            "GIT_CONFIG_COUNT": "1",
                            "GIT_CONFIG_KEY_0": "user.useConfigOnly",
                            "GIT_CONFIG_VALUE_0": "true",
                        }
                    )
                    foreign = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(root),
                            "-c",
                            "user.name=Fixture",
                            "-c",
                            'user.email=' + 'fixture' + '@' + 'example' + '.' + 'test',
                            "commit-tree",
                            canonical_tree,
                            "-m",
                            "foreign terminal head",
                        ],
                        env=strict_identity_env,
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    subprocess.run(
                        ["git", "-C", str(root), "checkout", "-q", "--detach", foreign],
                        check=True,
                        capture_output=True,
                    )
                elif case == "carrier_bytes":
                    (root / carrier_path).write_text("# unexpected carrier bytes\n", encoding="utf-8")
                else:
                    (root / "docs/followups/extra_after_commit.md").write_text("# unexpected followup\n", encoding="utf-8")

                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.read_capture(root, self.plan_ref, cycle_id)

                self.assertIn(
                    rejected.exception.reason_code,
                    {
                        "followup_capture_plan_identity_mismatch",
                        "followup_v2_source_commit_unreachable",
                        "followup_ordinary_v2_post_apply_invalid",
                        "followup_capture_path_object_drift",
                    },
                )

    def test_ordinary_compact_rejects_wrong_order_and_malformed_input_without_advancement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            before = receipt_path.read_bytes()
            with self.assertRaises(capture.CaptureError) as later:
                capture.bind_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    role="Coder",
                    submission_current=True,
                    write=True,
                )
            self.assertEqual(later.exception.reason_code, "followup_ordinary_v2_role_not_prepared")
            self.assertEqual(receipt_path.read_bytes(), before)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            prepared = receipt_path.read_bytes()
            for raw in (
                b"\xef\xbb\xbf{}",
                b'{"role":"Architect","role":"Architect","proposed_rows":[],"role_no_items_reason":"none"}',
                b'{"role":"Architect","proposed_rows":[],"role_no_items_reason":NaN}',
                b"prefix {}",
                b" " * (capture.ORDINARY_V2_COMPACT_MAX_BYTES + 1),
            ):
                with self.subTest(raw=raw[:8]), self.assertRaises(capture.CaptureError):
                    capture.submit_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        role="Architect",
                        raw_input=raw,
                        write=True,
                    )
                self.assertEqual(receipt_path.read_bytes(), prepared)
            self.assertFalse((receipt_path.parent / capture.ORDINARY_V2_BOUND_DIRECTORY).exists())

    def test_ordinary_compact_rejects_semantic_envelope_variants_before_bind_write(self) -> None:
        try:
            from scripts import followups_lint
        except ModuleNotFoundError:
            import followups_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            before = receipt_path.read_bytes()
            valid_payload = self._row()
            valid_row = {
                "followup_path": "docs/followups/ordinary_compact_fixture.md",
                "payload": valid_payload,
                "row_digest": followups_lint.v2_row_digest(valid_payload),
            }
            malformed_path_row = dict(valid_row)
            malformed_path_row["followup_path"] = "docs/ffollowups/not-a-followup.md"
            invalid_values = (
                {"role": "Architect", "proposed_rows": [], "role_no_items_reason": ""},
                {"role": "Architect", "proposed_rows": [], "role_no_items_reason": "none", "extra": True},
                {"role": "Coder", "proposed_rows": [], "role_no_items_reason": "none"},
                {"role": "Architect", "proposed_rows": [valid_row], "role_no_items_reason": "not allowed"},
                {"role": "Architect", "proposed_rows": [malformed_path_row], "role_no_items_reason": None},
                {
                    "role": "Architect",
                    "proposed_rows": [{"followup_path": "docs/followups/x.md", "payload": {}, "row_digest": "0" * 64}],
                    "role_no_items_reason": None,
                },
            )
            for value in invalid_values:
                with self.subTest(value=value), self.assertRaises(capture.CaptureError):
                    capture.submit_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        role="Architect",
                        raw_input=json.dumps(value, separators=(",", ":")).encode("utf-8"),
                        write=True,
                    )
                self.assertEqual(receipt_path.read_bytes(), before)
                self.assertFalse((receipt_path.parent / capture.ORDINARY_V2_BOUND_DIRECTORY).exists())

    def test_ordinary_compact_rejects_versionless_and_v1_terminal_sources(self) -> None:
        for schema_version in ("plan.v1", "legacy"):
            with self.subTest(schema_version=schema_version), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir, schema_version=schema_version)
                cycle_id = self._begin(root)
                capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
                before = receipt_path.read_bytes()
                with self.assertRaises(capture.CaptureError) as rejected:
                    capture.submit_ordinary_v2(
                        root,
                        plan_ref=self.plan_ref,
                        capture_cycle_id=cycle_id,
                        role="Architect",
                        raw_input=self._compact("Architect"),
                        write=True,
                    )
                self.assertEqual(rejected.exception.reason_code, "followup_ordinary_v2_plan_schema_invalid")
                self.assertEqual(receipt_path.read_bytes(), before)
                self.assertFalse((receipt_path.parent / capture.ORDINARY_V2_BOUND_DIRECTORY).exists())

    def test_public_full_envelope_freeze_cannot_satisfy_ordinary_marker_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            self._bind_all(root, cycle_id)
            bound_dir = root / capture._ordinary_v2_bound_dir_relpath(self.plan_ref, cycle_id)
            declarations = [
                json.loads((bound_dir / f"{role}.json").read_text(encoding="utf-8"))
                for role in capture.REQUIRED_ROLES
            ]
            generic_manifest = capture.freeze_v2_declarations(root, self.plan_ref, declarations)
            capture.persist_v2_frozen_manifest(root, self.plan_ref, generic_manifest)
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

            self.assertEqual(receipt[capture.ORDINARY_V2_BINDING_KEY]["state"], "binding")
            with self.assertRaises(capture.CaptureError) as freeze:
                capture.freeze_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    write=True,
                )
            with self.assertRaises(capture.CaptureError) as readback:
                capture.read_capture(root, self.plan_ref, cycle_id)

        self.assertEqual(freeze.exception.reason_code, "followup_ordinary_v2_manifest_exists")
        self.assertEqual(readback.exception.reason_code, "followup_ordinary_v2_marker_invalid")

    def test_ordinary_cli_input_selector_admission_and_explicit_stdin_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            cycle_id = self._begin(root)
            capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
            rejected_input = root / "compact.json"
            rejected_input.write_bytes(self._compact("Architect"))
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = capture.main(
                    [
                        "submit-ordinary-v2",
                        "--project-root", str(root),
                        "--plan-ref", self.plan_ref,
                        "--capture-cycle-id", cycle_id,
                        "--role", "Architect",
                        "--input", str(rejected_input),
                        "--write",
                    ]
                )
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(stdout.getvalue())["reason_code"], "followup_ordinary_v2_input_path_invalid")

            parser = capture._parser()
            base = [
                "submit-ordinary-v2",
                "--project-root", str(root),
                "--plan-ref", self.plan_ref,
                "--capture-cycle-id", cycle_id,
                "--role", "Architect",
                "--write",
            ]
            with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(base)
            with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args([*base, "--input", "-", "--input-current"])
            explicit_stdin = parser.parse_args([*base, "--input", "-"])
            self.assertEqual(explicit_stdin.input, "-")
            self.assertFalse(explicit_stdin.input_current)
            current = parser.parse_args([*base, "--input-current"])
            self.assertIsNone(current.input)
            self.assertTrue(current.input_current)

            with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "bind-ordinary-v2",
                        "--project-root", str(root),
                        "--plan-ref", self.plan_ref,
                        "--capture-cycle-id", cycle_id,
                        "--role", "Architect",
                        "--submission-current",
                        "--profile", "unexpected-profile",
                        "--write",
                    ]
                )


if __name__ == "__main__":
    unittest.main()

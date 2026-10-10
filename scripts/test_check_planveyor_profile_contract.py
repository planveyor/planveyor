#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("check_planveyor_profile_contract.py")
SPEC = importlib.util.spec_from_file_location("check_planveyor_profile_contract_proposal", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOURCE_ROOT = Path(
    os.environ.get("PLANVEYOR_PROFILE_CONTRACT_SOURCE_ROOT", str(MODULE_PATH.parent.parent))
).resolve()


class PlanveyorPublicContractCheckerTests(unittest.TestCase):
    def _copy_bundle(self, root: Path) -> None:
        for rel_path in MODULE.EXACT_BUNDLE:
            source = SOURCE_ROOT / rel_path
            self.assertTrue(source.is_file(), rel_path)
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _replace_once(self, root: Path, rel_path: str, old: str, new: str) -> None:
        target = root / rel_path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text, rel_path)
        target.write_text(text.replace(old, new, 1), encoding="utf-8")

    def _replace_all(self, root: Path, rel_path: str, old: str, new: str) -> None:
        target = root / rel_path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text, rel_path)
        target.write_text(text.replace(old, new), encoding="utf-8")

    def _assert_invariant(self, root: Path, invariant_id: str, rel_path: str) -> None:
        findings = MODULE.check_planveyor_profile_contract(root)
        self.assertTrue(
            any(item.invariant_id == invariant_id and item.rel_path == rel_path for item in findings),
            "\n".join(item.render() for item in findings),
        )

    def test_live_public_bundle_passes(self) -> None:
        self.assertEqual(MODULE.check_planveyor_profile_contract(SOURCE_ROOT), [])

    def test_main_prints_green_summary(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = MODULE.main(["--root", str(SOURCE_ROOT)])

        self.assertEqual(result, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            f"planveyor-profile-contract: OK files={len(MODULE.EXACT_BUNDLE)} invariants={len(MODULE.INVARIANT_IDS)}",
        )

    def test_copied_current_public_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self.assertEqual(MODULE.check_planveyor_profile_contract(root), [])

    def test_bundle_uses_only_public_root_owners(self) -> None:
        self.assertFalse(any("owner_runbook" in rel_path for rel_path in MODULE.EXACT_BUNDLE))
        self.assertFalse(any("profiles" in Path(rel_path).parts for rel_path in MODULE.EXACT_BUNDLE))
        self.assertIn(MODULE.MANAGER_PROMPT, MODULE.EXACT_BUNDLE)
        self.assertIn(MODULE.PLANVEYOR_ZSH, MODULE.EXACT_BUNDLE)

    def test_no_default_baseline_requires_declared_target_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.MANAGER_PROMPT,
                "Target-defined gate запускается только когда tracker-linked canon/plan literal-но объявляет его contract, preconditions и success criterion;",
                "Every target gate runs as a default baseline.",
            )
            self._assert_invariant(root, "no_default_django_baseline", MODULE.MANAGER_PROMPT)

    def test_merge_step_set_rejects_missing_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_all(root, MODULE.MANAGER_PROMPT, "step:canon_sweep", "step:retired_canon_sweep")
            self._assert_invariant(root, "tooling_merge_step_set", MODULE.MANAGER_PROMPT)

    def test_doc_lint_rejects_comment_only_dispatch(self) -> None:
        lint_args_ref = MODULE.DOLLAR + "{lint_args[@]}"
        command = 'env PYTHONDONTWRITEBYTECODE=1 "$pybin" -B "$lint_script" "' + lint_args_ref + '"'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, command, "# " + command)
            self._assert_invariant(root, "doc_lint_gate", MODULE.PLANVEYOR_ZSH)

    def test_doc_lint_rejects_unrelated_function_dispatch(self) -> None:
        lint_args_ref = MODULE.DOLLAR + "{lint_args[@]}"
        command = 'env PYTHONDONTWRITEBYTECODE=1 "$pybin" -B "$lint_script" "' + lint_args_ref + '"'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, command, "true")
            target = root / MODULE.PLANVEYOR_ZSH
            target.write_text(
                target.read_text(encoding="utf-8")
                + "\nunrelated_doc_lint_text() {\n  "
                + command
                + "\n}\n",
                encoding="utf-8",
            )
            self._assert_invariant(root, "doc_lint_gate", MODULE.PLANVEYOR_ZSH)

    def test_docs_hygiene_rejects_comment_only_runner(self) -> None:
        command = 'planveyor_docs_hygiene_suggest --range "$range" >"$stdout_path" 2>"$stderr_path"'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, command, "# " + command)
            self._assert_invariant(root, "docs_hygiene_suggest_autorun", MODULE.PLANVEYOR_ZSH)

    def test_ready_to_push_rejects_missing_terminal_proof_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.READY_TO_PUSH_CLOSEOUT,
                'TERMINAL_PROOF_STATE = "terminal_ready_to_push_proof"',
                'TERMINAL_PROOF_STATE = "retired_terminal_state"',
            )
            self._assert_invariant(root, "ready_to_push_auto_closeout", MODULE.READY_TO_PUSH_CLOSEOUT)

    def test_no_progress_text_is_not_docs_finalize_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.ARCHITECT_DOCS_FINALIZE,
                "chat-only prose, skeleton-only текст и placeholder values здесь не являются proof и запрещены.",
                "chat-only prose is acceptable proof.",
            )
            self._assert_invariant(root, "no_progress_updates", MODULE.ARCHITECT_DOCS_FINALIZE)

    def test_docs_finalize_rejects_comment_only_preflight(self) -> None:
        command = 'planveyor_post_merge_receipt_preflight docs_finalize --role "$role" --range "$range" --path "$receipt_path" || return $?'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, command, "# " + command)
            self._assert_invariant(root, "docs_finalize_merge_receipt", MODULE.PLANVEYOR_ZSH)

    def test_docs_finalize_rejects_nonexact_role_readback(self) -> None:
        receipt_ref = MODULE.DOLLAR + "{receipt_path}"
        expected = 'local expected_readback="docs_finalize_receipt_path=' + receipt_ref + '"'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.DOCS_FINALIZE_ZSH,
                expected,
                'local expected_readback="ignored=' + receipt_ref + '"',
            )
            self._assert_invariant(root, "docs_finalize_merge_receipt", MODULE.DOCS_FINALIZE_ZSH)

    def test_docs_finalize_rejects_followups_lane_in_current_step(self) -> None:
        only_general = (
            '        - Запусти только Architect general: `planveyor_arch_docs_general --receipt-path "$DOCS_FINALIZE_RECEIPT_PATH"`. '
            'Не запускай `planveyor_arch_followups` или другой role lane как proof этого tracker step.'
        )
        injected = (
            '        - `planveyor_arch_docs_general --receipt-path "$DOCS_FINALIZE_RECEIPT_PATH"`\n'
            '        - `planveyor_arch_followups --receipt-path "$DOCS_FINALIZE_RECEIPT_PATH"`\n'
            '        - Не запускай `planveyor_arch_followups` или другой role lane как proof этого tracker step.'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.MANAGER_PROMPT, only_general, injected)
            self._assert_invariant(root, "docs_finalize_merge_receipt", MODULE.MANAGER_PROMPT)

    def test_docs_finalize_rejects_followups_lane_on_prohibition_line(self) -> None:
        only_general = (
            '        - Запусти только Architect general: `planveyor_arch_docs_general --receipt-path "$DOCS_FINALIZE_RECEIPT_PATH"`. '
            'Не запускай `planveyor_arch_followups` или другой role lane как proof этого tracker step.'
        )
        injected = only_general + ' `planveyor_arch_followups --receipt-path "$DOCS_FINALIZE_RECEIPT_PATH"`'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.MANAGER_PROMPT, only_general, injected)
            self._assert_invariant(root, "docs_finalize_merge_receipt", MODULE.MANAGER_PROMPT)

    def test_packetization_rejects_mandatory_source_plan(self) -> None:
        optional = "Run-level " + MODULE.code("--source-plan") + " is optional provenance;"
        mandatory = "Run-level " + MODULE.code("--source-plan") + " is mandatory provenance."
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.MANAGER_PROMPT, optional, mandatory)
            self._assert_invariant(root, "packetization_range_identity", MODULE.MANAGER_PROMPT)

    def test_packetization_recovery_facade_rejects_mandatory_source_plan_comment_and_usage(self) -> None:
        optional_comment = "# Bounded source-local recovery: --range is mandatory; --source-plan is optional provenance."
        mandatory_comment = "# Bounded source-local recovery: --range and --source-plan are mandatory provenance."
        optional_usage = (
            "#   planveyor_post_merge_packetization_gate_recover --range BASE..HEAD "
            "[--source-plan docs/plans/<provenance-plan>.md] "
            "[--packet docs/rollout_packets/<packet>.md ...] [--stage-packets] [--format plain|json]"
        )
        mandatory_usage = (
            "#   planveyor_post_merge_packetization_gate_recover --range BASE..HEAD "
            "--source-plan docs/plans/<provenance-plan>.md "
            "[--packet docs/rollout_packets/<packet>.md ...] [--stage-packets] [--format plain|json]"
        )
        dispatch = '_planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" --recover "$@"'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, optional_comment, mandatory_comment)
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, optional_usage, mandatory_usage)
            target = root / MODULE.PLANVEYOR_ZSH
            target.write_text(
                target.read_text(encoding="utf-8")
                + "\nunrelated_optional_packetization_text() {\n"
                + "  "
                + optional_comment
                + "\n  "
                + optional_usage
                + "\n  "
                + dispatch
                + "\n}\n",
                encoding="utf-8",
            )
            self._assert_invariant(root, "packetization_range_identity", MODULE.PLANVEYOR_ZSH)

    def test_packetization_recovery_facade_rejects_source_plan_runtime_guard(self) -> None:
        range_assignment = '[[ "$arg" == "--range" ]] && have_range=1'
        dispatch = '_planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" --recover "$@"'
        guarded_dispatch = (
            '(( have_source_plan )) || {\n'
            '    echo "ERROR: source plan required" >&2\n'
            '    return 2\n'
            '  }\n'
            '  ' + dispatch
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.PLANVEYOR_ZSH,
                "local have_range=0",
                "local have_range=0\n  local have_source_plan=0",
            )
            self._replace_once(
                root,
                MODULE.PLANVEYOR_ZSH,
                range_assignment,
                range_assignment + '\n        [[ "$arg" == "--source-plan" ]] && have_source_plan=1',
            )
            self._replace_once(root, MODULE.PLANVEYOR_ZSH, dispatch, guarded_dispatch)
            self._assert_invariant(root, "packetization_range_identity", MODULE.PLANVEYOR_ZSH)

    def test_packetization_rejects_done_plan_as_range_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.MANAGER_PROMPT,
                "neither can choose artifacts, close coverage or yield terminal green.",
                "a Done source plan can choose artifacts and close coverage.",
            )
            self._assert_invariant(root, "packetization_range_identity", MODULE.MANAGER_PROMPT)

    def test_packetization_rejects_target_carrier_as_source_coverage(self) -> None:
        old = (
            MODULE.code("source_artifacts")
            + " — единственный source coverage carrier; "
            + MODULE.code("target_writable_carriers")
            + " — отдельная structural meta/Markdown parity"
        )
        new = (
            MODULE.code("target_writable_carriers")
            + " — source coverage carrier; "
            + MODULE.code("source_artifacts")
            + " — only structural metadata"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.MANAGER_PROMPT, old, new)
            self._assert_invariant(root, "packetization_range_identity", MODULE.MANAGER_PROMPT)

    def test_packetization_rejects_source_artifacts_range_identity_conflict(self) -> None:
        correct = "Packetization authority is exact full-OID range identity (`source_range`, `source_revision`), not a plan header."
        conflict = "exact full-OID range identity (`source_range`, `source_revision`, sorted `source_artifacts`)"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(root, MODULE.MANAGER_PROMPT, correct, correct + " " + conflict)
            self._assert_invariant(root, "packetization_range_identity", MODULE.MANAGER_PROMPT)

    def test_packetization_rejects_fixed_target_fanout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.MANAGER_PROMPT,
                "Нельзя применять global sibling union или fixed two-target fanout.",
                "Use a global sibling union and fixed target fanout.",
            )
            self._assert_invariant(root, "packetization_target_applicability", MODULE.MANAGER_PROMPT)

    def test_packetization_rejects_inferred_consumer_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.PACKETIZATION_GATE,
                "code never falls back to an inferred sibling obligation.",
                "code may infer a sibling obligation.",
            )
            self._assert_invariant(root, "packetization_target_applicability", MODULE.PACKETIZATION_GATE)

    def test_main_prints_red_finding_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._copy_bundle(root)
            self._replace_once(
                root,
                MODULE.DOC_LINT_PLAYBOOK,
                "Canonical closeout gate: `planveyor_doc_lint`",
                "Canonical closeout gate: `retired_doc_lint`",
            )
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--root", str(root)])

        self.assertEqual(result, 1)
        line = stdout.getvalue().strip().splitlines()[0]
        self.assertTrue(line.startswith(f"ERROR doc_lint_gate {MODULE.DOC_LINT_PLAYBOOK}:"))


if __name__ == "__main__":
    unittest.main()

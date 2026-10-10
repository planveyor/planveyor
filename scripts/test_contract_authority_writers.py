#!/usr/bin/env python3
"""Focused authority-boundary coverage for Package B Python writers."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import followups_promote as promote
import post_merge_receipt_skeleton as receipts
import process_improvements_collect as improvements


def _engaged_context(root: Path) -> SimpleNamespace:
    """A minimal pre-captured context for boundary-only tests.

    The tests deliberately do not modify the reviewed admission constant.  The
    public writer receives an already captured engaged context exactly as a
    later shell/bridge caller will, while the shared boundary calls are mocked
    only to isolate writer-family disposition from target fixture construction.
    """

    return SimpleNamespace(state="engaged", project_root=root.resolve())


class ContractAuthorityWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="contract-authority-writers-")
        self.root = Path(self.temporary.name).resolve() / "target"
        self.root.mkdir()
        self.context = _engaged_context(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _context_patches(self, module: object):
        authority = module.authority_context
        return (
            mock.patch.object(authority, "context_for_reader", return_value=self.context),
            mock.patch.object(authority, "validate_before_effect"),
        )

    def _run_writer_loader_probe(self, writer_name: str, mode: str) -> subprocess.CompletedProcess[str]:
        """Exercise a fresh direct import without trusting inherited aliases."""

        writer_path = SCRIPT_DIR / f"{writer_name}.py"
        probe = """
import importlib.util
from pathlib import Path
import sys
import types

writer_path = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
foreign_dir = Path(sys.argv[3]).resolve()
foreign_dir.mkdir(exist_ok=True)
foreign_context = foreign_dir / "contract_authority_context.py"
foreign_context.write_text("# foreign\\n", encoding="utf-8")

if mode == "foreign_parent":
    foreign_scripts = types.ModuleType("scripts")
    foreign_scripts.__path__ = [str(foreign_dir)]
    sys.modules["scripts"] = foreign_scripts
elif mode == "foreign_alias":
    poisoned = types.ModuleType("scripts.contract_authority_context")
    poisoned.__file__ = str(foreign_context)
    sys.modules["scripts.contract_authority_context"] = poisoned
else:
    raise AssertionError(mode)

if writer_path.stem == "followups_promote":
    for name in ("followups_lint", "followups_apply", "followups_capture"):
        sys.modules[name] = types.ModuleType(name)
elif writer_path.stem == "post_merge_receipt_skeleton":
    operational = types.ModuleType("post_merge_operational_receipt")
    operational.SCHEMA_VERSION = "receipt.v1"
    sys.modules[operational.__name__] = operational
    review = types.ModuleType("review_schema_contract")
    review.CURRENT_REVIEW_SCHEMA_VERSION = "review.v1"
    sys.modules[review.__name__] = review

spec = importlib.util.spec_from_file_location("writer_under_test", writer_path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
try:
    spec.loader.exec_module(module)
except ImportError as error:
    if mode != "foreign_alias":
        raise
    assert str(error) == "authority module has an unsafe origin"
else:
    if mode == "foreign_alias":
        raise AssertionError("poisoned authority alias was accepted")
    expected = writer_path.parent / "contract_authority_context.py"
    assert Path(module.authority_context.__file__).resolve() == expected.resolve()
    assert "scripts.contract_authority_context" not in sys.modules
"""
        return subprocess.run(
            [sys.executable, "-c", probe, str(writer_path), mode, str(self.root / "foreign")],
            cwd=SCRIPT_DIR.parent,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_writer_loaders_ignore_a_generic_foreign_scripts_parent(self) -> None:
        for writer_name in (
            "followups_promote",
            "process_improvements_collect",
            "post_merge_receipt_skeleton",
        ):
            with self.subTest(writer=writer_name):
                completed = self._run_writer_loader_probe(writer_name, "foreign_parent")
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_writer_loaders_reject_a_poisoned_authority_alias(self) -> None:
        for writer_name in (
            "followups_promote",
            "process_improvements_collect",
            "post_merge_receipt_skeleton",
        ):
            with self.subTest(writer=writer_name):
                completed = self._run_writer_loader_probe(writer_name, "foreign_alias")
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_legacy_followups_promotion_rejects_engaged_before_source_read(self) -> None:
        capture, validate = self._context_patches(promote)
        with capture as capture_context, validate as validate_effect:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = promote.main(
                    [
                        "--project-root",
                        str(self.root),
                        "--file",
                        "docs/followups/missing.md",
                        "--line",
                        "1",
                        "--plan-path",
                        "docs/plans/260907_0001_blocked.md",
                        "--apply",
                        "--format",
                        "json",
                    ],
                    context=self.context,
                )

        self.assertEqual(result, 2)
        self.assertIn('"reason_code": "engaged_legacy_promotion_unsupported"', stdout.getvalue())
        self.assertFalse((self.root / "docs").exists())
        capture_context.assert_called_once_with(self.root, self.context)
        validate_effect.assert_not_called()

    def test_v2_prepare_allows_engaged_and_rechecks_each_artifact_effect(self) -> None:
        followup = SimpleNamespace(rel_path="docs/followups/source.md")
        item = object()
        args = argparse.Namespace(author_role="Architect", apply=True)
        plan_rel = "docs/plans/260907_0001_candidate.md"
        draft_rel = "docs/code_drafts/260907_0001_candidate__code_draft.md"
        capture, validate = self._context_patches(promote)
        with (
            capture,
            validate as checked,
            mock.patch.object(promote, "_v2_payload", return_value=(followup, item, plan_rel, draft_rel)),
            mock.patch.object(promote, "_require_v2_open", return_value={"source_ref": "docs/plans/source.md", "item_id": "I-1"}),
            mock.patch.object(promote, "_render_v2_plan", return_value="plan\n"),
            mock.patch.object(promote, "_render_v2_code_draft", return_value="draft\n"),
        ):
            payload = promote._run_v2_prepare(self.root, args, context=self.context)

        self.assertEqual(payload["state"], "prepared")
        self.assertEqual((self.root / plan_rel).read_text(encoding="utf-8"), "plan\n")
        self.assertEqual((self.root / draft_rel).read_text(encoding="utf-8"), "draft\n")
        self.assertEqual(checked.call_count, 4)

    def test_v2_finalize_allows_engaged_and_rechecks_before_row_writer(self) -> None:
        source_ref = "docs/plans/source.md"
        item_id = "I-1"
        plan_rel = "docs/plans/260907_0002_candidate.md"
        followup = SimpleNamespace(rel_path="docs/followups/source.md")
        item = object()
        commit = "a" * 40
        desired = {
            "status": "promoted",
            "plan": plan_rel,
            "disposition_kind": "promoted_plan",
            "disposition_ref": plan_rel,
            "disposition_commit_oid": commit,
        }
        row = SimpleNamespace(tuple=(source_ref, item_id), payload=desired, digest="frozen-row")
        frozen = {
            "declaration_roles": list(promote.followups_capture.REQUIRED_ROLES),
            "expected_current_row_digests": {f"{source_ref}\x00{item_id}": "current-row"},
        }
        args = argparse.Namespace(
            frozen_manifest="frozen.json",
            commit_oid=commit,
            item_id=item_id,
            apply=True,
        )
        current_payload = {"status": "open", "source_ref": source_ref, "item_id": item_id}
        capture, validate = self._context_patches(promote)
        with (
            capture,
            validate as checked,
            mock.patch.object(promote, "_v2_payload", return_value=(followup, item, plan_rel, "docs/code_drafts/x.md")),
            mock.patch.object(promote.common, "lint_v2_item", return_value=[]),
            mock.patch.object(promote.common, "v2_row_payload", return_value=current_payload),
            mock.patch.object(promote.common, "v2_row_digest", return_value="current-row"),
            mock.patch.object(promote, "_read_json", return_value={"manifest": "fixture"}),
            mock.patch.object(promote.followups_apply, "load_frozen_manifest", return_value=(frozen, [row])),
            mock.patch.object(promote, "_require_v2_open"),
            mock.patch.object(promote, "_reachable_commit", return_value=commit),
            mock.patch.object(promote, "_commit_blob", return_value="b" * 40),
            mock.patch.object(promote.followups_apply, "apply_frozen_rows", return_value={"state": "applied"}) as apply_rows,
        ):
            payload = promote._run_v2_finalize(self.root, args, context=self.context)

        self.assertEqual(payload["state"], "applied")
        checked.assert_called_once_with(self.context)
        apply_rows.assert_called_once_with(self.root, {"manifest": "fixture"}, mutate=True)

    def test_docs_finalize_receipt_is_allowed_inside_engaged_root(self) -> None:
        output = self.root / "docs" / "reviews" / "docs_finalize.md"
        capture, validate = self._context_patches(receipts)
        stdout = io.StringIO()
        with capture, validate as checked, redirect_stdout(stdout):
            result = receipts.main(["docs_finalize_receipt", "--out", str(output)], context=self.context)

        self.assertEqual(result, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), receipts.render_skeleton("docs_finalize_receipt"))
        self.assertEqual(stdout.getvalue(), output.read_text(encoding="utf-8"))
        self.assertEqual(checked.call_count, 1)

    def test_private_receipt_family_rejects_before_render_or_output(self) -> None:
        output = self.root / "docs" / "reviews" / "private.md"
        capture, validate = self._context_patches(receipts)
        with (
            capture,
            validate,
            mock.patch.object(receipts, "render_skeleton") as render,
            self.assertRaises(receipts.authority_context.ContractAuthorityError) as raised,
        ):
            receipts.main(["canon_sweep_receipt", "--out", str(output)], context=self.context)

        self.assertEqual(raised.exception.reason_code, "engaged_private_delivery_unsupported")
        render.assert_not_called()
        self.assertFalse(output.parent.exists())

    def test_engaged_receipt_output_cannot_escape_context_root(self) -> None:
        output = Path(self.temporary.name).resolve() / "outside" / "receipt.md"
        capture, validate = self._context_patches(receipts)
        with capture, validate, self.assertRaises(receipts.authority_context.ContractAuthorityError) as raised:
            receipts.main(["docs_finalize_receipt", "--out", str(output)], context=self.context)

        self.assertEqual(raised.exception.reason_code, "context_output_root_mismatch")
        self.assertFalse(output.parent.exists())

    def test_process_improvement_public_writers_reject_engaged_before_effects(self) -> None:
        backlog = self.root / "docs" / "process_improvements" / "source__process_improvements_backlog.md"
        calls = (
            lambda: improvements.ensure_derived_surface_docs(self.root, context=self.context),
            lambda: improvements.rebuild_derived_surfaces(self.root, context=self.context),
            lambda: improvements.collect_process_improvements(
                project_root=self.root,
                role="Coder",
                source_ref="docs/plans/source.md",
                text="## Process improvements\n\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                write_receipt=False,
                context=self.context,
            ),
            lambda: improvements.import_process_improvements(
                project_root=self.root,
                import_files=(),
                apply=False,
                context=self.context,
            ),
            lambda: improvements.update_backlog_entry(
                project_root=self.root,
                backlog_path=backlog,
                entry_id="PI-001",
                context=self.context,
            ),
        )
        capture, validate = self._context_patches(improvements)
        with capture, validate as checked:
            for call in calls:
                with self.subTest(call=call):
                    with self.assertRaises(improvements.authority_context.ContractAuthorityError) as raised:
                        call()
                    self.assertEqual(raised.exception.reason_code, "engaged_private_delivery_unsupported")

        self.assertFalse((self.root / "docs").exists())
        self.assertEqual(checked.call_count, 0)

    def test_process_improvement_direct_cli_rejects_engaged_before_rebuild(self) -> None:
        capture, validate = self._context_patches(improvements)
        with capture, validate as checked:
            with self.assertRaises(improvements.authority_context.ContractAuthorityError) as raised:
                improvements.main(
                    ["--project-root", str(self.root), "--rebuild-derived"],
                    context=self.context,
                )

        self.assertEqual(raised.exception.reason_code, "engaged_private_delivery_unsupported")
        self.assertFalse((self.root / "docs").exists())
        checked.assert_not_called()
    def test_engaged_cli_requires_cycle_before_stdin_or_pi_map(self) -> None:
        capture, validate = self._context_patches(improvements)
        with (
            capture,
            validate as checked,
            mock.patch.object(improvements, "_read_input", side_effect=AssertionError("stdin must stay unread")) as read_input,
            mock.patch.object(improvements, "_safe_pi_object_map", side_effect=AssertionError("PI map must stay unread")) as object_map,
            self.assertRaises(improvements.authority_context.ContractAuthorityError) as raised,
        ):
            improvements.main(
                [
                    "--project-root",
                    str(self.root),
                    "--role",
                    "Coder",
                    "--source-ref",
                    "docs/plans/source.md",
                    "--input",
                    "-",
                    "--json",
                ],
                context=self.context,
            )

        self.assertEqual(raised.exception.reason_code, "engaged_private_delivery_unsupported")
        read_input.assert_not_called()
        object_map.assert_not_called()
        self.assertFalse((self.root / "docs").exists())
        checked.assert_not_called()


if __name__ == "__main__":
    unittest.main()

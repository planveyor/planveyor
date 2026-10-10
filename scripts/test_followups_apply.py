#!/usr/bin/env python3
"""Focused V2 frozen-union writer tests.

Coverage: V2 follow-ups ingress.
"""

from __future__ import annotations

import sys
import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_apply
import followups_capture
import followups_lint


SOURCE_PLAN = "docs/plans/260811_0000_terminal_source.md"


def _prepare_root(
    root: Path,
    *,
    source_schema: str = "plan.v2",
    source_meta: dict[str, object] | None = None,
) -> None:
    (root / "docs" / "followups").mkdir(parents=True)
    plan = root / SOURCE_PLAN
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan_text = f"# terminal\n\n**Status:** Done\n**Schema version:** {source_schema}\n"
    if source_meta is not None:
        plan_text += "\n```json\n" + json.dumps({"plan_meta": source_meta}, ensure_ascii=False) + "\n```\n"
    plan.write_text(plan_text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid'], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", SOURCE_PLAN], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "terminal source"], cwd=root, check=True)


def _source_identity(root: Path) -> tuple[str, str]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    blob = subprocess.check_output(["git", "rev-parse", f"HEAD:{SOURCE_PLAN}"], cwd=root, text=True).strip()
    return commit, blob


def _payload(
    *,
    item_id: str = "item-001",
    status: str = "open",
    disposition_commit_oid: str | None = None,
) -> dict[str, object]:
    promoted = status == "promoted"
    return {
        "priority": "P1",
        "summary": "Frozen writer regression",
        "cluster": "process",
        "to": "coder",
        "status": status,
        "plan": "docs/plans/260811_0001_promoted.md" if promoted else None,
        "why": "prove one serial writer",
        "tags": ["v2"],
        "item_id": item_id,
        "source_ref": SOURCE_PLAN,
        "disposition_kind": "promoted_plan" if promoted else None,
        "disposition_ref": "docs/plans/260811_0001_promoted.md" if promoted else None,
        "disposition_commit_oid": (disposition_commit_oid or "c" * 40) if promoted else None,
        "reason": "Commit A materialized the target plan" if promoted else None,
    }


def _manifest(
    root: Path,
    rows: list[tuple[str, dict[str, object]]],
    *,
    expected_current: dict[str, str] | None = None,
) -> dict[str, object]:
    snapshot, _ = followups_capture.snapshot_followups(root, include_bytes=True)
    expected = []
    owners: dict[str, str] = {}
    proposed = []
    for path, payload in rows:
        source_ref = str(payload["source_ref"])
        item_id = str(payload["item_id"])
        expected.append({"source_ref": source_ref, "item_id": item_id})
        owners[f"{source_ref}\u0000{item_id}"] = "Coder"
        proposed.append(
            {
                "followup_path": path,
                "payload": payload,
                "row_digest": followups_lint.v2_row_digest(payload),
            }
        )
    expected.sort(key=lambda value: (value["source_ref"], value["item_id"]))
    commit, blob = _source_identity(root)
    return {
        "schema_version": "followups_capture_cycle.v2",
        "plan_ref": SOURCE_PLAN,
        "source_terminal_commit_oid": commit,
        "source_plan_blob_oid": blob,
        "baseline_followups_snapshot": snapshot,
        "declaration_roles": list(followups_capture.REQUIRED_ROLES),
        "expected_owned_tuples": expected,
        "tuple_owners": owners,
        "expected_zero_reason": None if expected else "no declared rows",
        "proposed_rows": proposed,
        **({"expected_current_row_digests": expected_current} if expected_current is not None else {}),
    }


def _generic_payload(*, item_id: str, source_ref: str, summary: str = "Generic writer regression") -> dict[str, object]:
    return {
        "priority": "P1",
        "summary": summary,
        "cluster": "process",
        "to": "coder",
        "status": "open",
        "plan": None,
        "why": "prove producer ingress reaches only the serial writer",
        "tags": ["generic"],
        "item_id": item_id,
        "source_ref": source_ref,
        "disposition_kind": None,
        "disposition_ref": None,
        "disposition_commit_oid": None,
        "reason": None,
    }


def _generic_batch(
    root: Path,
    rows: list[dict[str, object]],
    *,
    target_path: str = "docs/followups/generic.md",
    producer_id: str = "code_reviews_harvest",
) -> dict[str, object]:
    snapshot, _ = followups_capture.snapshot_followups(root, include_bytes=True)
    source_anchors: dict[str, set[str]] = {}
    proposed: list[dict[str, object]] = []
    for payload in sorted(rows, key=lambda value: (str(value["source_ref"]), str(value["item_id"]))):
        source_path, anchor = str(payload["source_ref"]).split("#", 1)
        source_anchors.setdefault(source_path, set()).add(anchor)
        proposed.append(
            {
                "followup_path": target_path,
                "payload": payload,
                "row_digest": followups_lint.v2_row_digest(payload),
                "expected_current_row_digest": None,
            }
        )
    source_objects = []
    for source_path, anchors in sorted(source_anchors.items()):
        data = (root / source_path).read_bytes()
        source_objects.append(
            {
                "source_path": source_path,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "anchors": sorted(anchors),
            }
        )
    return {
        "schema_version": "followups_generic_batch.v2",
        "source_kind": "generic_harvest",
        "producer_id": producer_id,
        "target_followup_path": target_path,
        "target_header": followups_apply._new_v2_file_text(target_path),
        "baseline_followups_snapshot": snapshot,
        "source_objects": source_objects,
        "expected_owned_tuples": [
            {"source_ref": str(row["payload"]["source_ref"]), "item_id": str(row["payload"]["item_id"])}
            for row in proposed
        ],
        "expected_zero_reason": None if proposed else "no generic source items",
        "proposed_rows": proposed,
    }


def _unreachable_source_commits(root: Path) -> tuple[str, str]:
    tree_oid = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    dangling = subprocess.check_output(["git", "commit-tree", tree_oid, "-m", "dangling source"], cwd=root, text=True).strip()
    unrelated = subprocess.check_output(["git", "commit-tree", tree_oid, "-m", "unrelated source"], cwd=root, text=True).strip()
    subprocess.run(["git", "update-ref", "refs/heads/unrelated", unrelated], cwd=root, check=True)
    return dangling, unrelated


def _commit_promoted_target(root: Path) -> str:
    target = root / "docs" / "plans" / "260811_0001_promoted.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# promoted target\n\n**Status:** Architect initial draft\n", encoding="utf-8")
    subprocess.run(["git", "add", target.relative_to(root).as_posix()], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "Commit A target"], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _global_v2_findings(root: Path) -> list[followups_lint.Finding]:
    _objects, contents = followups_capture.snapshot_followups(root, include_bytes=True)
    carriers = []
    for rel_path, data in sorted(contents.items()):
        if Path(rel_path).name in followups_lint.FOLLOWUPS_IGNORE:
            continue
        parsed = followups_lint.parse_followup_text(data.decode("utf-8"), rel_path, root / rel_path)
        if followups_lint.classify_followups_schema_version(parsed)[0] == "v2":
            carriers.append(parsed)
    return followups_lint.lint_followup_files(carriers, root)


def _followup_bytes(root: Path) -> dict[str, bytes]:
    followups_dir = root / "docs" / "followups"
    if not followups_dir.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(followups_dir.rglob("*"))
        if path.is_file()
    }


def _write_index_before_image(root: Path) -> bytes:
    index = root / "docs" / "followups" / "index.md"
    index.write_text("# Follow-ups — index\n\nmanual header\n", encoding="utf-8")
    return index.read_bytes()


class FollowupsApplyTests(unittest.TestCase):
    def test_new_row_apply_is_lint_green_and_exact_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            payload = _payload()
            manifest = _manifest(root, [("docs/followups/process_followups_master.md", payload)])

            applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(applied["state"], "applied")
            source = root / "docs" / "followups" / "process_followups_master.md"
            parsed = followups_lint.parse_followup_file(source, root)
            self.assertEqual(followups_lint.lint_followup_files([parsed], root), [])
            self.assertEqual(parsed.items[0].item_id, "item-001")
            self.assertIsNone(followups_lint.v2_row_payload(parsed.items[0])["plan"])

            retry = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(retry["state"], "idempotent")
            self.assertEqual(retry["changed_paths"], [])

    def test_terminal_index_transaction_updates_and_exact_receipt_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            index_before = _write_index_before_image(root)
            carrier_path = "docs/followups/process_followups_master.md"
            manifest = _manifest(root, [(carrier_path, _payload())])
            binding = {"capture_cycle_id": "123e4567-e89b-42d3-a456-426614174000"}
            published: dict[str, object] = {}

            def missing_receipt(*_args: object, **_kwargs: object) -> tuple[dict[str, object], dict[str, object]]:
                raise followups_apply.followups_capture.CaptureError(
                    "followups_index_refresh_receipt_missing",
                    "fixture has no receipt before the terminal write",
                )

            def publish_receipt(*_args: object, receipt: dict[str, object], **_kwargs: object) -> tuple[dict[str, object], dict[str, object], bool]:
                published.update(receipt)
                return receipt, {"path": "fixture-receipt"}, True

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(followups_apply.followups_capture, "read_followups_index_refresh_receipt", side_effect=missing_receipt),
                mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt", side_effect=publish_receipt),
            ):
                applied = followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            index_after = (root / "docs/followups/index.md").read_bytes()
            self.assertEqual(applied["state"], "applied")
            self.assertEqual(applied["changed_paths"], ["docs/followups/index.md", carrier_path])
            self.assertNotEqual(index_after, index_before)
            self.assertEqual(
                published["changed_paths"],
                ["docs/followups/index.md", carrier_path],
            )
            self.assertEqual(published["owner_id"], followups_capture.FOLLOWUPS_INDEX_REFRESH_OWNER_ID)
            self.assertEqual(published["state"], "updated")
            self.assertEqual(applied["followups_index_refresh_receipt"], published)

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(
                    followups_apply.followups_capture,
                    "read_followups_index_refresh_receipt",
                    return_value=(dict(published), {"path": "fixture-receipt"}),
                ),
                mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt") as publish_again,
            ):
                replay = followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(replay["state"], "idempotent")
            self.assertEqual(replay["changed_paths"], [])
            self.assertEqual((root / "docs/followups/index.md").read_bytes(), index_after)
            publish_again.assert_not_called()

    def test_terminal_index_clean_noop_receipt_and_owner_or_cycle_drift_do_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            _write_index_before_image(root)
            followups_apply.followups_index_rebuild.rebuild_index(root, stamp="31.08.2026 20:00")
            manifest = _manifest(root, [])
            binding = {"capture_cycle_id": "123e4567-e89b-42d3-a456-426614174000"}
            published: dict[str, object] = {}

            def missing_receipt(*_args: object, **_kwargs: object) -> tuple[dict[str, object], dict[str, object]]:
                raise followups_apply.followups_capture.CaptureError(
                    "followups_index_refresh_receipt_missing",
                    "fixture has no receipt before the terminal write",
                )

            def publish_receipt(*_args: object, receipt: dict[str, object], **_kwargs: object) -> tuple[dict[str, object], dict[str, object], bool]:
                published.update(receipt)
                return receipt, {"path": "fixture-receipt"}, True

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(followups_apply.followups_capture, "read_followups_index_refresh_receipt", side_effect=missing_receipt),
                mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt", side_effect=publish_receipt),
            ):
                clean = followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            self.assertEqual(clean["state"], "idempotent")
            self.assertEqual(clean["changed_paths"], [])
            self.assertEqual(published["state"], "clean_noop")
            self.assertEqual(published["changed_paths"], [])
            before_drift = _followup_bytes(root)
            for field, foreign_value in (
                ("owner_id", "foreign_terminal_owner"),
                ("capture_cycle_id", "123e4567-e89b-42d3-a456-426614174111"),
            ):
                with self.subTest(field=field):
                    with (
                        mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                        mock.patch.object(
                            followups_apply.followups_capture,
                            "read_followups_index_refresh_receipt",
                            return_value=({**published, field: foreign_value}, {"path": "fixture-receipt"}),
                        ),
                        mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt") as publish_again,
                    ):
                        with self.assertRaises(followups_apply.ApplyError) as drift:
                            followups_apply.apply_frozen_rows(root, manifest, mutate=True)
                        self.assertEqual(drift.exception.reason_code, "followups_index_refresh_receipt_drift")
                        self.assertEqual(_followup_bytes(root), before_drift)
                        publish_again.assert_not_called()

    def test_terminal_index_refresh_missing_binding_and_write_failure_leave_no_partial_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            _write_index_before_image(root)
            carrier_path = "docs/followups/process_followups_master.md"
            manifest = _manifest(root, [(carrier_path, _payload())])
            before = _followup_bytes(root)

            with self.assertRaises(followups_apply.ApplyError) as missing:
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(missing.exception.reason_code, "followups_index_refresh_binding_invalid")
            self.assertEqual(_followup_bytes(root), before)

            binding = {"capture_cycle_id": "123e4567-e89b-42d3-a456-426614174000"}
            index_path = root / "docs/followups/index.md"
            index_before = index_path.read_bytes()
            index_path.write_text("# foreign prewrite index\n", encoding="utf-8")
            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(
                    followups_apply.followups_capture,
                    "read_followups_index_refresh_receipt",
                    side_effect=followups_apply.followups_capture.CaptureError(
                        "followups_index_refresh_receipt_missing",
                        "fixture absent",
                    ),
                ),
            ):
                with self.assertRaises(followups_apply.ApplyError) as index_drift:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(index_drift.exception.reason_code, "followups_index_prewrite_drift")
            self.assertFalse((root / carrier_path).exists())
            self.assertEqual(index_path.read_text(encoding="utf-8"), "# foreign prewrite index\n")
            index_path.write_bytes(index_before)

            original_atomic_write = followups_apply._atomic_write
            calls = 0

            def fail_second_write(path: Path, data: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected terminal replacement failure")
                original_atomic_write(path, data)

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(
                    followups_apply.followups_capture,
                    "read_followups_index_refresh_receipt",
                    side_effect=followups_apply.followups_capture.CaptureError(
                        "followups_index_refresh_receipt_missing",
                        "fixture absent",
                    ),
                ),
                mock.patch.object(followups_apply, "_atomic_write", side_effect=fail_second_write),
            ):
                with self.assertRaises(OSError):
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(_followup_bytes(root), before)

    def test_terminal_index_lifecycle_drift_fails_before_any_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            _write_index_before_image(root)
            target_commit = _commit_promoted_target(root)
            carrier_path = "docs/followups/process_followups_master.md"
            manifest = _manifest(
                root,
                [(carrier_path, _payload(status="promoted", disposition_commit_oid=target_commit))],
            )
            target = root / "docs/plans/260811_0001_promoted.md"
            before = _followup_bytes(root)
            binding = {"capture_cycle_id": "123e4567-e89b-42d3-a456-426614174000"}
            original_render = followups_apply._render_terminal_index_candidate
            render_calls = 0

            def mutate_after_locked_candidate(*args: object, **kwargs: object) -> object:
                nonlocal render_calls
                rendered = original_render(*args, **kwargs)
                render_calls += 1
                if render_calls == 2:
                    target.write_text("# promoted target\n\n**Status:** Done\n", encoding="utf-8")
                return rendered

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(
                    followups_apply.followups_capture,
                    "read_followups_index_refresh_receipt",
                    side_effect=followups_apply.followups_capture.CaptureError(
                        "followups_index_refresh_receipt_missing",
                        "fixture has no receipt before the terminal write",
                    ),
                ),
                mock.patch.object(
                    followups_apply,
                    "_render_terminal_index_candidate",
                    side_effect=mutate_after_locked_candidate,
                ),
                mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt") as publish_receipt,
            ):
                with self.assertRaises(followups_apply.ApplyError) as drift:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            self.assertEqual(drift.exception.reason_code, "followups_index_lifecycle_drift")
            self.assertEqual(_followup_bytes(root), before)
            self.assertGreaterEqual(render_calls, 3)
            publish_receipt.assert_not_called()

    def test_terminal_index_lifecycle_drift_at_first_replace_rolls_back_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            index_before = _write_index_before_image(root)
            target_commit = _commit_promoted_target(root)
            carrier_path = "docs/followups/process_followups_master.md"
            manifest = _manifest(
                root,
                [(carrier_path, _payload(status="promoted", disposition_commit_oid=target_commit))],
            )
            target = root / "docs/plans/260811_0001_promoted.md"
            before = _followup_bytes(root)
            binding = {"capture_cycle_id": "123e4567-e89b-42d3-a456-426614174000"}
            original_atomic_write = followups_apply._atomic_write
            replaced_once = False

            def mutate_at_first_replace(path: Path, data: bytes) -> None:
                nonlocal replaced_once
                original_atomic_write(path, data)
                if not replaced_once:
                    replaced_once = True
                    target.write_text("# promoted target\n\n**Status:** Done\n", encoding="utf-8")

            with (
                mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding", return_value=binding),
                mock.patch.object(
                    followups_apply.followups_capture,
                    "read_followups_index_refresh_receipt",
                    side_effect=followups_apply.followups_capture.CaptureError(
                        "followups_index_refresh_receipt_missing",
                        "fixture has no receipt before the terminal write",
                    ),
                ),
                mock.patch.object(followups_apply, "_atomic_write", side_effect=mutate_at_first_replace),
                mock.patch.object(followups_apply.followups_capture, "publish_followups_index_refresh_receipt") as publish_receipt,
            ):
                with self.assertRaises(followups_apply.ApplyError) as drift:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            self.assertEqual(drift.exception.reason_code, "followups_index_lifecycle_drift")
            self.assertTrue(replaced_once)
            self.assertEqual(_followup_bytes(root), before)
            self.assertEqual((root / "docs/followups/index.md").read_bytes(), index_before)
            self.assertFalse((root / carrier_path).exists())
            publish_receipt.assert_not_called()

    def test_generic_batch_never_refreshes_an_index_bearing_terminal_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            index_before = _write_index_before_image(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
            batch = _generic_batch(
                root,
                [_generic_payload(item_id="generic-index-001", source_ref="docs/code_reviews/generic.md#L3")],
            )

            with mock.patch.object(followups_apply.followups_capture, "find_followups_index_refresh_binding") as unexpected_binding:
                applied = followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(applied["state"], "applied")
            self.assertEqual((root / "docs/followups/index.md").read_bytes(), index_before)
            unexpected_binding.assert_not_called()

    def test_terminal_manifest_requires_exact_roles_and_declared_owners_before_write(self) -> None:
        role_cases: list[tuple[str, object]] = [
            ("wrong-type", "Architect,Coder,Planner,Reviewer"),
            ("reordered", ["Coder", "Architect", "Planner", "Reviewer"]),
            ("duplicate", ["Architect", "Coder", "Planner", "Planner"]),
            ("extra", ["Architect", "Coder", "Planner", "Reviewer", "Intruder"]),
        ]
        for name, roles in role_cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _prepare_root(root)
                manifest = _manifest(root, [("docs/followups/process_followups_master.md", _payload())])
                manifest["declaration_roles"] = roles
                before = _followup_bytes(root)
                with self.assertRaises(followups_apply.ApplyError) as blocked:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)
                self.assertEqual(blocked.exception.reason_code, "frozen_manifest_declaration_roles_invalid")
                self.assertEqual(_followup_bytes(root), before)
                self.assertFalse((root / followups_apply.LOCK_REL_PATH).exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            manifest = _manifest(root, [("docs/followups/process_followups_master.md", _payload())])
            manifest.pop("declaration_roles")
            before = _followup_bytes(root)
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "frozen_manifest_declaration_roles_invalid")
            self.assertEqual(_followup_bytes(root), before)
            self.assertFalse((root / followups_apply.LOCK_REL_PATH).exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            manifest = _manifest(root, [])
            manifest.pop("declaration_roles")
            before = _followup_bytes(root)
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "frozen_manifest_declaration_roles_invalid")
            self.assertEqual(_followup_bytes(root), before)
            self.assertFalse((root / followups_apply.LOCK_REL_PATH).exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            payload = _payload()
            manifest = _manifest(root, [("docs/followups/process_followups_master.md", payload)])
            manifest["tuple_owners"][f"{payload['source_ref']}\u0000{payload['item_id']}"] = "Intruder"
            before = _followup_bytes(root)
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "frozen_manifest_owner_invalid")
            self.assertEqual(_followup_bytes(root), before)
            self.assertFalse((root / followups_apply.LOCK_REL_PATH).exists())

    def test_transition_needs_exact_current_row_digest_and_updates_one_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            path = "docs/followups/process_followups_master.md"
            open_payload = _payload()
            followups_apply.apply_frozen_rows(root, _manifest(root, [(path, open_payload)]), mutate=True)

            tuple_key = f"{open_payload['source_ref']}\u0000{open_payload['item_id']}"
            bad_transition = _manifest(
                root,
                [(path, _payload(status="promoted"))],
                expected_current={tuple_key: followups_lint.v2_row_digest(open_payload)},
            )
            with self.assertRaisesRegex(followups_apply.ApplyError, "lint-green contract"):
                followups_apply.apply_frozen_rows(root, bad_transition, mutate=True)

            commit_a = _commit_promoted_target(root)
            tree_oid = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
            dangling_commit = subprocess.check_output(
                ["git", "commit-tree", tree_oid, "-m", "unreachable target"],
                cwd=root,
                text=True,
            ).strip()
            unreachable_payload = _payload(status="promoted", disposition_commit_oid=dangling_commit)
            unreachable_transition = _manifest(
                root,
                [(path, unreachable_payload)],
                expected_current={tuple_key: followups_lint.v2_row_digest(open_payload)},
            )
            with self.assertRaisesRegex(followups_apply.ApplyError, "lint-green contract"):
                followups_apply.apply_frozen_rows(root, unreachable_transition, mutate=True)

            promoted_payload = _payload(status="promoted", disposition_commit_oid=commit_a)
            transition = _manifest(
                root,
                [(path, promoted_payload)],
                expected_current={tuple_key: followups_lint.v2_row_digest(open_payload)},
            )
            applied = followups_apply.apply_frozen_rows(root, transition, mutate=True)
            self.assertEqual(applied["state"], "applied")
            parsed = followups_lint.parse_followup_file(root / path, root)
            self.assertEqual(len(parsed.items), 1)
            self.assertEqual(parsed.items[0].status, "promoted")
            self.assertEqual(parsed.items[0].plan, "docs/plans/260811_0001_promoted.md")

            retry = followups_apply.apply_frozen_rows(root, transition, mutate=True)
            self.assertEqual(retry["state"], "idempotent")

    def test_drift_or_second_bad_row_does_not_partially_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            first_path = "docs/followups/process_followups_master.md"
            second_path = "docs/followups/ops_followups_master.md"
            first = _payload(item_id="item-001")
            second = _payload(item_id="item-002")
            manifest = _manifest(root, [(first_path, first), (second_path, second)])
            # A foreign write changes the frozen object map before apply.
            (root / "docs" / "followups" / "foreign.md").write_text("# foreign\n", encoding="utf-8")
            with self.assertRaisesRegex(followups_apply.ApplyError, "object map changed"):
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            self.assertFalse((root / first_path).exists())
            self.assertFalse((root / second_path).exists())

            # Even with a fresh snapshot, a stale CAS payload prevents the
            # complete multi-file write, rather than committing the first row.
            baseline = _manifest(root, [(first_path, first), (second_path, second)])
            current_file = root / "docs" / "followups" / "foreign.md"
            current_file.write_text(
                "# Follow-ups\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                + followups_lint.render_v2_row(_payload(item_id="item-002"))
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(followups_apply.ApplyError):
                followups_apply.apply_frozen_rows(root, baseline, mutate=True)
            self.assertFalse((root / first_path).exists())

    def test_writer_refuses_an_invalid_existing_v2_target_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            path = "docs/followups/process_followups_master.md"
            target = root / path
            before = (
                "# Follow-ups backlog — process\n\n"
                "**Schema version:** followups.v2\n\n"
                "## Follow-ups (backlog)\n"
                "- P1 [ ] malformed V2 row — status=open\n"
            )
            target.write_text(before, encoding="utf-8")
            manifest = _manifest(root, [(path, _payload())])

            with self.assertRaisesRegex(followups_apply.ApplyError, "lint-green"):
                followups_apply.apply_frozen_rows(root, manifest, mutate=True)

            self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_terminal_and_generic_apply_reject_a_foreign_explicit_v2_blocker_without_write(self) -> None:
        malformed = (
            "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n"
        )
        for source_kind in ("terminal", "generic"):
            with self.subTest(source_kind=source_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _prepare_root(root)
                if source_kind == "terminal":
                    target = root / "docs/followups/terminal.md"
                    request = _manifest(root, [(target.relative_to(root).as_posix(), _payload())])
                else:
                    source = root / "docs/code_reviews/generic.md"
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
                    target = root / "docs/followups/generic.md"
                    request = _generic_batch(
                        root,
                        [_generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")],
                    )
                foreign = root / "docs/followups/foreign.md"
                foreign.write_text(malformed, encoding="utf-8")
                before_foreign = foreign.read_bytes()

                with self.assertRaises(followups_apply.ApplyError) as blocked:
                    followups_apply.apply_frozen_rows(root, request, mutate=True)

                self.assertEqual(blocked.exception.reason_code, "v2_integrity_blocker")
                self.assertFalse(target.exists())
                self.assertEqual(foreign.read_bytes(), before_foreign)

    def test_exact_owner_retry_rechecks_foreign_v2_integrity_under_lock(self) -> None:
        malformed = (
            "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n"
        )
        for source_kind in ("terminal", "generic"):
            with self.subTest(source_kind=source_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _prepare_root(root)
                if source_kind == "terminal":
                    owner = root / "docs/followups/owner.md"
                    request = _manifest(root, [(owner.relative_to(root).as_posix(), _payload())])
                else:
                    source = root / "docs/code_reviews/generic.md"
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
                    owner = root / "docs/followups/generic.md"
                    request = _generic_batch(
                        root,
                        [_generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")],
                    )
                self.assertEqual(followups_apply.apply_frozen_rows(root, request, mutate=True)["state"], "applied")
                before_owner = owner.read_bytes()
                foreign = root / "docs/followups/foreign.md"
                original_acquire = followups_apply._acquire_lock

                def inject_before_locked_reread(lock_root: Path) -> int:
                    fd = original_acquire(lock_root)
                    foreign.write_text(malformed, encoding="utf-8")
                    return fd

                with mock.patch.object(
                    followups_apply,
                    "_acquire_lock",
                    side_effect=inject_before_locked_reread,
                ):
                    with self.assertRaises(followups_apply.ApplyError) as blocked:
                        followups_apply.apply_frozen_rows(root, request, mutate=True)

                self.assertEqual(blocked.exception.reason_code, "v2_integrity_blocker")
                self.assertEqual(owner.read_bytes(), before_owner)
                self.assertEqual(foreign.read_text(encoding="utf-8"), malformed)

    def test_writer_preserves_only_a_full_hash_bound_legacy_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_row = {"cluster": "process", "summary": "frozen V1 row", "plan": None}
            _prepare_root(
                root,
                source_schema="plan.v1",
                source_meta={"followups_out": [legacy_row]},
            )
            plan_bytes = (root / SOURCE_PLAN).read_bytes()
            payload = _payload()
            payload.update(
                {
                    "legacy_row_ref": "plan_meta.followups_out[1]",
                    "legacy_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                    "legacy_row_sha256": hashlib.sha256(
                        json.dumps(legacy_row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest(),
                }
            )
            path = "docs/followups/process_followups_master.md"

            applied = followups_apply.apply_frozen_rows(root, _manifest(root, [(path, payload)]), mutate=True)

            self.assertEqual(applied["state"], "applied")
            parsed = followups_lint.parse_followup_file(root / path, root)
            self.assertEqual(followups_lint.lint_followup_files([parsed], root), [])
            self.assertEqual(parsed.items[0].legacy_row_ref, "plan_meta.followups_out[1]")

    def test_canceled_todo_stage_producer_cannot_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Review\n\n## finding\n", encoding="utf-8")
            row = _generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")
            batch = _generic_batch(root, [row], producer_id="todo_stage_harvest")
            with self.assertRaises(followups_apply.ApplyError) as rejected:
                followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(rejected.exception.reason_code, "generic_batch_producer_invalid")
            self.assertFalse((root / "docs/followups/generic.md").exists())

    def test_generic_batch_uses_the_same_writer_with_source_cas_and_exact_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n## item two\n", encoding="utf-8")
            first = _generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")
            second = _generic_payload(item_id="generic-002", source_ref="docs/code_reviews/generic.md#L4")
            batch = _generic_batch(root, [first, second])

            applied = followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(applied["state"], "applied")
            self.assertEqual(applied["producer_id"], "code_reviews_harvest")
            target = root / "docs/followups/generic.md"
            parsed = followups_lint.parse_followup_file(target, root)
            self.assertEqual(followups_lint.lint_followup_files([parsed], root), [])
            self.assertEqual({item.item_id for item in parsed.items}, {"generic-001", "generic-002"})

            retry = followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(retry["state"], "idempotent")
            self.assertEqual(retry["changed_paths"], [])

            # A fresh batch may omit an existing tuple without deleting it.
            retained = _generic_batch(root, [first])
            retained_result = followups_apply.apply_frozen_rows(root, retained, mutate=True)
            self.assertEqual(retained_result["state"], "idempotent")
            self.assertEqual({item.item_id for item in followups_lint.parse_followup_file(target, root).items}, {"generic-001", "generic-002"})

    def test_generic_batch_rejects_profile_source_and_carrier_drift_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n## item two\n", encoding="utf-8")
            first = _generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")
            second = _generic_payload(item_id="generic-002", source_ref="docs/code_reviews/generic.md#L4")
            batch = _generic_batch(root, [first, second])
            target = root / "docs/followups/generic.md"

            batch["producer_id"] = "untrusted"
            with self.assertRaises(followups_apply.ApplyError) as bad_producer:
                followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(bad_producer.exception.reason_code, "generic_batch_producer_invalid")
            self.assertFalse(target.exists())

            batch = _generic_batch(root, [first, second])
            batch["source_terminal_commit_oid"] = "a" * 40
            with self.assertRaises(followups_apply.ApplyError) as impersonation:
                followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(impersonation.exception.reason_code, "generic_batch_terminal_profile_impersonation")
            self.assertFalse(target.exists())

            batch = _generic_batch(root, [first, second])

            source.write_text("# TODO\n\n## item one changed\n## item two\n", encoding="utf-8")
            with self.assertRaises(followups_apply.ApplyError) as source_drift:
                followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(source_drift.exception.reason_code, "generic_source_hash_drift")
            self.assertFalse(target.exists())

            source.write_text("# TODO\n\n## item one\n## item two\n", encoding="utf-8")
            batch = _generic_batch(root, [first, second])
            (root / "docs/followups/foreign.md").write_text("# foreign\n", encoding="utf-8")
            with self.assertRaises(followups_apply.ApplyError) as baseline_drift:
                followups_apply.apply_frozen_rows(root, batch, mutate=True)
            self.assertEqual(baseline_drift.exception.reason_code, "generic_baseline_snapshot_drift")
            self.assertFalse(target.exists())

    def test_generic_batch_rejects_unsafe_uncovered_and_stale_cas_inputs_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n## item two\n", encoding="utf-8")
            first = _generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")
            second = _generic_payload(item_id="generic-002", source_ref="docs/code_reviews/generic.md#L4")
            target = root / "docs/followups/generic.md"

            unsafe = _generic_batch(root, [first])
            unsafe["source_objects"][0]["source_path"] = "../outside.md"
            with self.assertRaises(followups_apply.ApplyError) as unsafe_error:
                followups_apply.apply_frozen_rows(root, unsafe, mutate=True)
            self.assertEqual(unsafe_error.exception.reason_code, "generic_source_path_invalid")
            self.assertFalse(target.exists())

            uncovered = _generic_batch(root, [first])
            uncovered["source_objects"][0]["anchors"] = []
            with self.assertRaises(followups_apply.ApplyError) as uncovered_error:
                followups_apply.apply_frozen_rows(root, uncovered, mutate=True)
            self.assertEqual(uncovered_error.exception.reason_code, "generic_source_ref_uncovered")
            self.assertFalse(target.exists())

            anchor_drift = _generic_batch(root, [first])

            source.write_text("# TODO\n", encoding="utf-8")
            anchor_drift["source_objects"][0]["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            with self.assertRaises(followups_apply.ApplyError) as anchor_error:
                followups_apply.apply_frozen_rows(root, anchor_drift, mutate=True)
            self.assertEqual(anchor_error.exception.reason_code, "generic_source_anchor_drift")
            self.assertFalse(target.exists())

            source.write_text("# TODO\n\n## item one\n## item two\n", encoding="utf-8")

            duplicate = _generic_batch(root, [first])
            duplicate["expected_owned_tuples"].append(dict(duplicate["expected_owned_tuples"][0]))
            with self.assertRaises(followups_apply.ApplyError) as duplicate_error:
                followups_apply.apply_frozen_rows(root, duplicate, mutate=True)
            self.assertEqual(duplicate_error.exception.reason_code, "generic_batch_tuple_invalid")
            self.assertFalse(target.exists())

            followups_apply.apply_frozen_rows(root, _generic_batch(root, [first, second]), mutate=True)
            before = target.read_bytes()
            updated_first = {**first, "summary": "Generic writer regression updated"}
            stale = _generic_batch(root, [updated_first, second])
            stale["proposed_rows"][0]["expected_current_row_digest"] = "0" * 64
            with self.assertRaises(followups_apply.ApplyError) as stale_error:
                followups_apply.apply_frozen_rows(root, stale, mutate=True)
            self.assertEqual(stale_error.exception.reason_code, "generic_current_tuple_drift")
            self.assertEqual(target.read_bytes(), before)

            unexpected = _generic_batch(root, [updated_first])
            unexpected["proposed_rows"][0]["expected_current_row_digest"] = None
            with self.assertRaises(followups_apply.ApplyError) as unexpected_error:
                followups_apply.apply_frozen_rows(root, unexpected, mutate=True)
            self.assertEqual(unexpected_error.exception.reason_code, "generic_unexpected_existing_tuple")
            self.assertEqual(target.read_bytes(), before)

            parsed_before = followups_lint.parse_followup_file(target, root)
            old_digest = next(
                followups_lint.v2_row_digest(item) for item in parsed_before.items if item.item_id == "generic-001"
            )
            transition = _generic_batch(root, [updated_first])
            transition["proposed_rows"][0]["expected_current_row_digest"] = old_digest
            self.assertEqual(followups_apply.apply_frozen_rows(root, transition, mutate=True)["state"], "applied")
            self.assertEqual(
                next(item.summary for item in followups_lint.parse_followup_file(target, root).items if item.item_id == "generic-001"),
                "Generic writer regression updated",
            )
            self.assertEqual(followups_apply.apply_frozen_rows(root, transition, mutate=True)["state"], "idempotent")

    def test_terminal_global_tuple_ownership_blocks_a_foreign_carrier_and_allows_owner_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            payload = _payload()
            a_manifest = _manifest(root, [("docs/followups/a.md", payload)])
            self.assertEqual(followups_apply.apply_frozen_rows(root, a_manifest, mutate=True)["state"], "applied")
            a_path = root / "docs/followups/a.md"
            b_path = root / "docs/followups/b.md"
            before_a = a_path.read_bytes()

            b_manifest = _manifest(root, [("docs/followups/b.md", payload)])
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, b_manifest, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "global_tuple_owner_conflict")
            self.assertEqual(a_path.read_bytes(), before_a)
            self.assertFalse(b_path.exists())

            retry = followups_apply.apply_frozen_rows(root, a_manifest, mutate=True)
            self.assertEqual(retry["state"], "idempotent")
            self.assertEqual(retry["changed_paths"], [])
            self.assertEqual(_global_v2_findings(root), [])

    def test_generic_global_tuple_ownership_blocks_a_foreign_carrier_and_allows_owner_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
            payload = _generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")
            a_batch = _generic_batch(root, [payload], target_path="docs/followups/a.md")
            self.assertEqual(followups_apply.apply_frozen_rows(root, a_batch, mutate=True)["state"], "applied")
            a_path = root / "docs/followups/a.md"
            b_path = root / "docs/followups/b.md"
            before_a = a_path.read_bytes()

            b_batch = _generic_batch(root, [payload], target_path="docs/followups/b.md")
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, b_batch, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "global_tuple_owner_conflict")
            self.assertEqual(a_path.read_bytes(), before_a)
            self.assertFalse(b_path.exists())

            retry = followups_apply.apply_frozen_rows(root, a_batch, mutate=True)
            self.assertEqual(retry["state"], "idempotent")
            self.assertEqual(retry["changed_paths"], [])
            self.assertEqual(_global_v2_findings(root), [])

    def test_preexisting_foreign_duplicate_blocks_even_an_exact_owner_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            payload = _payload()
            owner_manifest = _manifest(root, [("docs/followups/a.md", payload)])
            self.assertEqual(followups_apply.apply_frozen_rows(root, owner_manifest, mutate=True)["state"], "applied")
            a_path = root / "docs/followups/a.md"
            b_path = root / "docs/followups/b.md"
            b_path.write_bytes(a_path.read_bytes())
            before_a = a_path.read_bytes()
            before_b = b_path.read_bytes()

            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, owner_manifest, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "v2_integrity_blocker")
            self.assertEqual(a_path.read_bytes(), before_a)
            self.assertEqual(b_path.read_bytes(), before_b)

    def test_global_tuple_conflict_has_no_partial_write_and_leaves_v2_set_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            first = _payload(item_id="item-001")
            second = _payload(item_id="item-002")
            self.assertEqual(
                followups_apply.apply_frozen_rows(root, _manifest(root, [("docs/followups/a.md", first)]), mutate=True)["state"],
                "applied",
            )
            proposal = _manifest(
                root,
                [
                    ("docs/followups/b.md", second),
                    ("docs/followups/c.md", first),
                ],
            )
            with self.assertRaises(followups_apply.ApplyError) as blocked:
                followups_apply.apply_frozen_rows(root, proposal, mutate=True)
            self.assertEqual(blocked.exception.reason_code, "global_tuple_owner_conflict")
            self.assertFalse((root / "docs/followups/b.md").exists())
            self.assertFalse((root / "docs/followups/c.md").exists())
            self.assertEqual(_global_v2_findings(root), [])

    def test_serial_writer_busy_has_no_terminal_or_generic_carrier_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            lock_path = root / followups_apply.LOCK_REL_PATH
            lock_path.parent.mkdir(parents=True)
            lock_path.write_text("busy\n", encoding="utf-8")

            terminal = _manifest(root, [("docs/followups/a.md", _payload())])
            with self.assertRaises(followups_apply.ApplyError) as terminal_busy:
                followups_apply.apply_frozen_rows(root, terminal, mutate=True)
            self.assertEqual(terminal_busy.exception.reason_code, "serial_writer_busy")
            self.assertFalse((root / "docs/followups/a.md").exists())

            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
            generic = _generic_batch(
                root,
                [_generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")],
                target_path="docs/followups/b.md",
            )
            with self.assertRaises(followups_apply.ApplyError) as generic_busy:
                followups_apply.apply_frozen_rows(root, generic, mutate=True)
            self.assertEqual(generic_busy.exception.reason_code, "serial_writer_busy")
            self.assertFalse((root / "docs/followups/b.md").exists())

    def test_writer_rejects_ignored_carriers_and_does_not_require_legacy_v1_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            for index, name in enumerate(sorted(followups_lint.FOLLOWUPS_IGNORE), start=1):
                path = f"docs/followups/{name}"
                with self.assertRaises(followups_apply.ApplyError) as ignored:
                    followups_apply.apply_frozen_rows(
                        root,
                        _manifest(root, [(path, _payload(item_id=f"item-{index:03d}"))]),
                        mutate=True,
                    )
                self.assertEqual(ignored.exception.reason_code, "frozen_row_path_ignored")
                self.assertFalse((root / path).exists())

            source = root / "docs/code_reviews/generic.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# TODO\n\n## item one\n", encoding="utf-8")
            ignored_generic = _generic_batch(
                root,
                [_generic_payload(item_id="generic-001", source_ref="docs/code_reviews/generic.md#L3")],
                target_path="docs/followups/README.md",
            )
            with self.assertRaises(followups_apply.ApplyError) as ignored:
                followups_apply.apply_frozen_rows(root, ignored_generic, mutate=True)
            self.assertEqual(ignored.exception.reason_code, "frozen_row_path_ignored")

            legacy = root / "docs/followups/legacy.md"
            legacy.write_text(
                "# Legacy\n\n**Schema version:** followups.v1\n\n## Follow-ups\n- P1 [ ] malformed legacy row\n",
                encoding="utf-8",
            )
            legacy_parsed = followups_lint.parse_followup_file(legacy, root)
            self.assertTrue(followups_lint.lint_followup_files([legacy_parsed], root))
            applied = followups_apply.apply_frozen_rows(
                root,
                _manifest(root, [("docs/followups/a.md", _payload())]),
                mutate=True,
            )
            self.assertEqual(applied["state"], "applied")
            self.assertEqual(_global_v2_findings(root), [])

    def test_terminal_apply_rejects_dangling_and_unrelated_source_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            blob = _source_identity(root)[1]
            payload = _payload()
            for source_commit in _unreachable_source_commits(root):
                manifest = _manifest(root, [("docs/followups/process_followups_master.md", payload)])
                manifest["source_terminal_commit_oid"] = source_commit
                manifest["source_plan_blob_oid"] = blob
                with self.assertRaises(followups_apply.ApplyError) as caught:
                    followups_apply.apply_frozen_rows(root, manifest, mutate=True)
                self.assertEqual(caught.exception.reason_code, "followup_v2_source_commit_unreachable")
                self.assertFalse((root / "docs/followups/process_followups_master.md").exists())

    def test_terminal_and_generic_profiles_cannot_impersonate_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_root(root)
            terminal = _manifest(root, [("docs/followups/process_followups_master.md", _payload())])
            terminal["producer_id"] = "code_reviews_harvest"
            with self.assertRaises(followups_apply.ApplyError) as terminal_error:
                followups_apply.apply_frozen_rows(root, terminal, mutate=True)
            self.assertEqual(terminal_error.exception.reason_code, "frozen_manifest_generic_profile_impersonation")


if __name__ == "__main__":
    unittest.main()

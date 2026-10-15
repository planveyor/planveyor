#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from textwrap import dedent
from typing import Callable
from unittest import mock

try:
    from scripts.test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root


MODULE_PATH = Path(__file__).with_name("docs_closeout.py")
SPEC = importlib.util.spec_from_file_location("docs_closeout", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

PLAN_QUEUE_PATH = Path(__file__).with_name("plan_queue.py")
PLAN_QUEUE_SPEC = importlib.util.spec_from_file_location("plan_queue", PLAN_QUEUE_PATH)
assert PLAN_QUEUE_SPEC is not None and PLAN_QUEUE_SPEC.loader is not None
PLAN_QUEUE = importlib.util.module_from_spec(PLAN_QUEUE_SPEC)
sys.modules[PLAN_QUEUE_SPEC.name] = PLAN_QUEUE
PLAN_QUEUE_SPEC.loader.exec_module(PLAN_QUEUE)

COLLECT_PATH = Path(__file__).with_name("process_improvements_collect.py")
COLLECT_SPEC = importlib.util.spec_from_file_location("process_improvements_collect", COLLECT_PATH)
assert COLLECT_SPEC is not None and COLLECT_SPEC.loader is not None
COLLECT = importlib.util.module_from_spec(COLLECT_SPEC)
sys.modules[COLLECT_SPEC.name] = COLLECT
COLLECT_SPEC.loader.exec_module(COLLECT)


class DocsCloseoutTests(unittest.TestCase):
    def _write_plan(
        self,
        root: Path,
        rel_path: str,
        *,
        status: str = "Done",
        review_artifact: str | None = None,
        evidence_tail: str | None = None,
        handoff_statuses: str | None = None,
        context_links: str | None = None,
        meta_json: str | None = None,
        machine_authority: bool = True,
    ) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        review_line = f"- Code review (primary): `{review_artifact}`" if review_artifact else "- `N/A (why=fixture)`"
        evidence_block = evidence_tail or "- [2026-04-18 10:00 MSK] (Reviewer) Fixture."
        handoff_block = handoff_statuses or dedent(
            """\
            - `Ready for Planner` — Architect
            - `Ready for Coder` — Planner
            - `Ready for Review` — Coder
            - `Ready for Arch review` — Reviewer
            - `Done` — Architect
            """
        ).rstrip()
        context_block = context_links or f"- Code draft(s): `docs/code_drafts/{Path(rel_path).stem}__code_draft.md`"
        default_decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "docs_or_tests_only",
        }
        decision: dict[str, str] | None = None
        if meta_json is None:
            plan_meta: dict[str, object] = {
                "cluster": "process",
                "tags": [],
                "phase_overlay": None,
                "phase_state": None,
                "parent": None,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": [],
            }
            if machine_authority:
                plan_meta["machine_authority_decision"] = default_decision
                decision = default_decision
            meta_block = json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)
        else:
            meta_block = meta_json
            if machine_authority:
                try:
                    meta_payload = json.loads(meta_json)
                except json.JSONDecodeError:
                    meta_payload = None
                if isinstance(meta_payload, dict) and isinstance(meta_payload.get("plan_meta"), dict):
                    plan_meta = meta_payload["plan_meta"]
                    candidate = plan_meta.get("machine_authority_decision")
                    if (
                        isinstance(candidate, dict)
                        and set(candidate) == {"schema_version", "applicability", "reason_code"}
                        and candidate.get("schema_version") == "machine_authority_decision.v1"
                        and candidate.get("applicability") == "not_applicable"
                        and candidate.get("reason_code")
                        in MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_NA_REASONS
                    ):
                        decision = {
                            "schema_version": str(candidate["schema_version"]),
                            "applicability": str(candidate["applicability"]),
                            "reason_code": str(candidate["reason_code"]),
                        }
        # Canonical column-0 markdown: the strict routing reader used by the
        # queue admission lanes accepts `## Meta` headings with at most three
        # leading spaces, like real repo plans.
        target.write_text(
            "\n".join(
                [
                    "# Plan: fixture",
                    "",
                    "**Date:** 2026-04-18 10:00 MSK",
                    "**Stage:** Stage 1",
                    "**Priority:** P1",
                    "**Plan type:** dev",
                    f"**Status:** {status}",
                    "",
                    "**Handoff statuses (кто ставит):**",
                    handoff_block,
                    "",
                    "**Context links (source of truth):**",
                    context_block,
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    meta_block,
                    "```",
                    "",
                    "## Review artifacts",
                    review_line,
                    "",
                    "## Evidence (chronological, append-only)",
                    evidence_block,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        status_norm = " ".join(status.lower().split())
        if (
            decision is not None
            and context_links is None
            and status_norm in MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_REF_REQUIRED_STATUSES
        ):
            draft_path = root / f"docs/code_drafts/{Path(rel_path).stem}__code_draft.md"
            if not draft_path.exists() and not draft_path.is_symlink():
                draft_path.parent.mkdir(parents=True, exist_ok=True)
                draft_path.write_text(
                    "# Code draft: fixture\n\n"
                    "```json\n"
                    + json.dumps(
                        {
                                "code_draft_meta": {
                                    "plan": rel_path,
                                    "cluster": "process",
                                    "targets": [{"path": "docs/fixture.md", "kind": "doc"}],
                                    "deleted_paths": [],
                                    "machine_authority_decision_ref": {
                                    "applicability": "not_applicable",
                                    "reason_code": "docs_or_tests_only",
                                    "carrier_sha256": (
                                        MODULE.plan_status_oracle.machine_authority_decision_sha256(
                                            decision
                                        )
                                    ),
                                },
                            }
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )
        return target

    def _write_review(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )

    def _init_git(self, root: Path) -> None:
        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')

    def _commit_all(self, root: Path, message: str = "baseline") -> None:
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", message)

    def _init_committed_fixture_repo(self, root: Path) -> None:
        """Create the marker-free Git baseline required by authority readers."""

        self._init_git(root)
        self._commit_all(root, message="fixture baseline")

    def _accepted_red_receipt_fixture(
        self,
        root: Path,
        *,
        target_rel: str,
        target_present: bool = True,
        target_recovery_owned: bool = True,
        frozen_recovery_contract: bool = True,
        recovery_status: str = "In progress",
        write_recovery_review: bool = False,
        source_review_directory: str = "docs/code_reviews",
        source_review_label: str = "Code review (primary)",
        recovery_review_directory: str = "docs/code_reviews",
        recovery_review_label: str = "Code review (primary)",
        manifest_historical_review: str | None = None,
        omit_manifest_historical_review: bool = False,
    ) -> tuple[str, dict[str, object]]:
        source_rel = "docs/plans/260724_0300_process_source.md"
        source_draft_rel = "docs/code_drafts/260724_0300_process_source__code_draft.md"
        source_review_rel = (
            f"{source_review_directory}/260724_0300_process_source.md"
        )
        recovery_rel = "docs/plans/260724_0301_process_recovery.md"
        recovery_draft_rel = "docs/code_drafts/260724_0301_process_recovery__code_draft.md"
        recovery_review_rel = (
            f"{recovery_review_directory}/260724_0301_process_recovery.md"
        )
        successor_rel = "docs/plans/260724_0302_process_successor.md"
        recovery_owned_rel = (
            target_rel
            if target_recovery_owned
            else "docs/recovery-owned/control.md"
        )
        source_targets = sorted({target_rel, recovery_owned_rel})
        recovery_targets = [recovery_owned_rel]
        target_bytes = b"baseline\n"
        if target_present:
            file_records = [
                {
                    "git_mode": "100644",
                    "path": rel,
                    "sha256": hashlib.sha256(target_bytes).hexdigest(),
                    "size_bytes": len(target_bytes),
                }
                for rel in source_targets
            ]
            hash_basis_payload = {
                "algorithm": "sha256",
                "files": file_records,
                "schema_version": "review_target_snapshot.hash_basis.v2",
            }
            review_sha = hashlib.sha256(
                json.dumps(
                    hash_basis_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        else:
            review_sha = "a" * 64
        ref = f"refs/planveyor/rejected-baselines/fixture/{review_sha}"
        manifest_rel = ".planveyor/rejected-baselines/fixture/manifest.json"
        cleanup_rel = ".planveyor/rejected-baselines/fixture/cleanup.json"
        for rel in (
            source_rel,
            source_draft_rel,
            source_review_rel,
            successor_rel,
            recovery_rel,
            recovery_draft_rel,
            recovery_review_rel,
            *source_targets,
        ):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
        source_decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        source_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": [successor_rel],
                "scope_expansion": {
                    "state": "architect_accepted",
                    "target_contour": "decomposition_wave",
                    "source_ref": f"{source_review_rel}#B1",
                    "reason": "fixture",
                },
                "machine_authority_decision": source_decision,
            }
        }
        (root / source_rel).write_text(
            "# Source\n\n"
            "**Plan type:** dev\n"
            "**Status:** Superseded\n\n"
            "**Context links (source of truth):**\n"
            f"- Code draft(s): `{source_draft_rel}`\n\n"
            "## Meta\n"
            f"```json\n{json.dumps(source_meta, indent=2)}\n```\n\n"
            "## Review artifacts\n"
            f"- {source_review_label}: `{source_review_rel}`\n",
            encoding="utf-8",
        )
        source_draft_meta = {
            "code_draft_meta": {
                "plan": source_rel,
                "cluster": "process",
                "targets": [
                    {"path": rel, "kind": "doc"} for rel in source_targets
                ],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(
                        source_decision
                    ),
                },
            }
        }
        (root / source_draft_rel).write_text(
            f"# Draft\n\n```json\n{json.dumps(source_draft_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        (root / source_review_rel).write_text(
            "# Review\n\n"
            f"**Target:** BUNDLE=current bundle_sha256={review_sha}\n"
            "**Status:** ❌ S1 blocker\n\n"
            "## S1 Blocker\n\n"
            "### B1) fixture blocker\n\n"
            "- Blocker ID: `B1`\n"
            "- Current state: `open`\n",
            encoding="utf-8",
        )
        successor_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": source_rel,
                "next_plans": [],
                "scope_expansion": {"state": "n/a"},
            }
        }
        (root / successor_rel).write_text(
            "# Successor\n\n"
            f"`{source_review_rel}#B1`\n\n"
            f"```json\n{json.dumps(successor_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        recovery_decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        recovery_plan_meta = {
            "plan_meta": {
                "cluster": "process",
                "machine_authority_decision": recovery_decision,
            }
        }
        (root / recovery_rel).write_text(
            "# Recovery\n\n"
            f"**Status:** {recovery_status}\n\n"
            f"- Superseded incident plan: `{source_rel}`.\n"
            f"- Code draft(s): `{recovery_draft_rel}`\n\n"
            "## Meta\n"
            f"```json\n{json.dumps(recovery_plan_meta, indent=2)}\n```\n\n"
            "## Review artifacts\n"
            f"- {recovery_review_label}: `{recovery_review_rel}`\n",
            encoding="utf-8",
        )
        recovery_meta = {
            "code_draft_meta": {
                "plan": recovery_rel,
                "cluster": "process",
                "targets": [
                    {"path": rel, "kind": "doc"} for rel in recovery_targets
                ],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(
                        recovery_decision
                    ),
                },
            }
        }
        (root / recovery_draft_rel).write_text(
            f"# Draft\n\n```json\n{json.dumps(recovery_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        for rel in source_targets:
            if rel != target_rel or target_present:
                (root / rel).write_bytes(target_bytes)
        if write_recovery_review:
            recovery_files = []
            for rel in recovery_targets:
                path = root / rel
                if path.is_file():
                    data = path.read_bytes()
                    recovery_files.append(
                        {
                            "git_mode": "100644",
                            "path": rel,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "size_bytes": len(data),
                        }
                    )
            recovery_hash_basis = {
                "algorithm": "sha256",
                "files": recovery_files,
                "schema_version": "review_target_snapshot.hash_basis.v2",
            }
            recovery_review_sha = hashlib.sha256(
                json.dumps(
                    recovery_hash_basis,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            (root / recovery_review_rel).write_text(
                "# Recovery review\n\n"
                f"**Target:** BUNDLE=current bundle_sha256={recovery_review_sha}\n"
                "**Status:** ✅ OK\n",
                encoding="utf-8",
            )
        vocab_path = root / "docs/_meta/plan_vocab.json"
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        vocab_path.write_text(
            json.dumps(
                {
                    "planning_contour": {
                        "scope_expansion_states": [
                            "n/a",
                            "suspected",
                            "reroute_required",
                            "architect_accepted",
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self._init_git(root)
        self._commit_all(root)
        captured_parent = self._git(root, "rev-parse", "HEAD").stdout.strip()

        manifest = {
            "schema": "planveyor_rejected_baseline.v1",
            "source_plan": source_rel,
            "recovery_plan": recovery_rel,
            "successor_plan": successor_rel,
            "review_bundle_sha256": review_sha,
            "recovery_ref": ref,
            "recovery_manifest_path": manifest_rel,
            "recovery_cleanup_path": cleanup_rel,
            "captured_parent": captured_parent,
            "targets": [{"path": rel} for rel in source_targets],
            "routing_carriers": [
                {"path": rel}
                for rel in sorted((source_rel, source_review_rel))
            ],
        }
        if not omit_manifest_historical_review:
            manifest["historical_review"] = (
                source_review_rel
                if manifest_historical_review is None
                else manifest_historical_review
            )
        if frozen_recovery_contract:
            manifest.update(
                recovery_code_draft=recovery_draft_rel,
                recovery_targets=recovery_targets,
            )
        manifest_path = root / manifest_rel
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self._commit_all(root, "capture")
        capture_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()

        cleanup = {
            "schema": "planveyor_rejected_baseline_cleanup.v1",
            "source_plan": source_rel,
            "recovery_plan": recovery_rel,
            "recovery_ref": ref,
            "review_bundle_sha256": review_sha,
            "capture_commit": capture_commit,
            "captured_parent": captured_parent,
            "cleanup_head": captured_parent,
        }
        if frozen_recovery_contract:
            cleanup.update(
                recovery_code_draft=recovery_draft_rel,
                recovery_targets=recovery_targets,
            )
        cleanup_path = root / cleanup_rel
        cleanup_path.write_text(json.dumps(cleanup), encoding="utf-8")
        self._commit_all(root, "cleanup")
        cleanup_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
        self._git(root, "update-ref", ref, cleanup_commit)
        self._git(root, "reset", "--hard", captured_parent)
        return source_rel, {
            "recovery_ref": ref,
            "recovery_manifest_path": manifest_rel,
            "recovery_cleanup_path": cleanup_rel,
            "recovery_plan": recovery_rel,
            "recovery_code_draft": recovery_draft_rel,
            "recovery_targets": recovery_targets,
            "successor_plan": successor_rel,
            "review_bundle_sha256": review_sha,
            "capture_commit": capture_commit,
            "cleanup_commit": cleanup_commit,
            "captured_parent": captured_parent,
            "active_checkout_state": "recovery_owned_overlap",
            "recovery_contract_state": (
                "manifest_frozen"
                if frozen_recovery_contract
                else "legacy_completed_terminal"
            ),
        }

    def _accepted_red_completed_bundle(
        self,
        source_rel: str,
        receipt: dict[str, object],
    ) -> dict[str, object]:
        return {
            **receipt,
            "plan": source_rel,
            "bundle_ok": True,
            "errors": [],
            "closeout_kind": "accepted_red_recovered",
            "terminal_disposition": "accepted_red_supersession",
            "delivery_green": False,
            "staging_policy": "forbidden",
            "durable_capture_required": True,
            "durable_capture_state": "cleanup_recorded",
            "recovery_state": "completed",
            "repo_roots": [{"repo_root": None, "bundle_paths": [source_rel]}],
        }

    def _accepted_red_oracle(
        self,
        plan: Path,
        receipt: dict[str, object],
    ) -> object:
        ordinary = MODULE.plan_status_oracle.oracle_result(plan)
        return replace(
            ordinary,
            terminal_disposition="accepted_red_supersession",
            delivery_green=False,
            staging_policy="forbidden",
            durable_capture_required=True,
            accepted_red_successor_plan=str(receipt["successor_plan"]),
            accepted_red_historical_review=(
                "docs/code_reviews/260724_0300_process_source.md"
            ),
            accepted_red_review_bundle_sha256=str(receipt["review_bundle_sha256"]),
            terminal_disposition_reason="fixture",
        )

    def _run_public_docs_closeout(
        self,
        root: Path,
        source_rel: str,
        bundle: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        fixture_env = {"BUNDLE_JSON": json.dumps(bundle, ensure_ascii=False, sort_keys=True)}
        shell = dedent(
            """\
            source "$1"
            planveyor_plan_bundle() {
              printf '%s\\n' "$BUNDLE_JSON"
            }
            planveyor_docs_closeout "$2" --json
            """
        )
        return run_zsh_fixture(
            shell,
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=sys.executable,
            fixture_env=fixture_env,
            argv0="docs-closeout-test",
            argv_tail=(str(MODULE_PATH.with_name("planveyor.zsh")), source_rel),
            capture_output=True,
            check=False,
        )

    def _bundle_payload(
        self,
        closeout_kind: str,
        *,
        bundle_ok: bool = True,
        final_docs_commit: str | None = None,
        bundle_paths: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "plan": "docs/plans/fixture.md",
            "bundle_ok": bundle_ok,
            "errors": errors or [],
            "closeout_kind": closeout_kind,
            "repo_roots": [{"repo_root": None, "bundle_paths": bundle_paths or []}],
        }
        if final_docs_commit is not None:
            payload["final_docs_commit"] = final_docs_commit
        return payload

    def _clone_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return json.loads(json.dumps(payload))

    def _assert_fast_path_blocked(self, payload: dict[str, object], precondition: str) -> None:
        fast_path = payload["terminal_closeout_fast_path"]
        assert isinstance(fast_path, dict)
        self.assertFalse(fast_path["eligible"])
        self.assertIn(precondition, fast_path["missing_or_dirty_preconditions"])
        self.assertIn("Architect:general", fast_path["fallback_lanes"])

    def _write_capture_receipts(
        self,
        root: Path,
        plan_rel: str,
        *,
        state_by_role: dict[str, str] | None = None,
        reason_by_role: dict[str, str] | None = None,
        backlog_paths: list[str] | None = None,
        followups_capture_cycle_id: str = "none",
        roles: tuple[str, ...] = ("Architect", "Coder", "Planner", "Reviewer"),
        pi_chain_by_role: dict[str, tuple[dict[str, object], dict[str, object]]] | None = None,
    ) -> None:
        state_by_role = state_by_role or {}
        reason_by_role = reason_by_role or {}
        pi_objects = MODULE.followups_capture.snapshot_process_improvement_data_files(root, plan_rel)
        for role in roles:
            state = state_by_role.get(role, "clean_noop")
            before_pi, after_pi = (pi_chain_by_role or {}).get(role, (pi_objects, pi_objects))
            path_results = [
                {
                    "path": path,
                    "before_object": before_pi.get(path),
                    "after_object": after_pi.get(path),
                }
                for path in MODULE.followups_capture._changed_paths(before_pi, after_pi)
            ]
            explicit_cycle = followups_capture_cycle_id if followups_capture_cycle_id != "none" else None
            rel_path = COLLECT.capture_receipt_rel_path(plan_rel, role, explicit_cycle)
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "receipt_schema": (
                            COLLECT.CAPTURE_RECEIPT_V2_SCHEMA
                            if explicit_cycle is not None
                            else COLLECT.CAPTURE_RECEIPT_V1_SCHEMA
                        ),
                        "source_ref": plan_rel,
                        "role": role,
                        "capture_state": state,
                        "reason_code": reason_by_role.get(role, "clean_run"),
                        "followups_capture_cycle_id": followups_capture_cycle_id,
                        **({"input_sha256": "0" * 64} if explicit_cycle is not None else {}),
                        "backlog_paths": backlog_paths or [],
                        "before_process_improvement_files": before_pi,
                        "after_process_improvement_files": after_pi,
                        "process_improvement_path_results": path_results,
                        "created": [],
                        "duplicates": [],
                        "written_at": "2026-04-18 10:10 MSK",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    def _write_owned_followup(self, root: Path, rel_path: str, plan_ref: str) -> None:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Follow-ups backlog — docs-closeout fixture\n\n"
            "**Date:** 21.07.2026 02:10\n"
            "**Source:** terminal docs finalize\n"
            "**Status:** Draft\n"
            "**Schema version:** followups.v1\n\n"
            "## Follow-ups (backlog)\n"
            "- P1 [ ] Scoped ordinary finding — cluster=process — tags=fixture — to=Architect "
            f"— status=open — plan=null — source_ref={plan_ref} — why: captured after terminal\n",
            encoding="utf-8",
        )

    def _finalize_followups_cycle(
        self,
        root: Path,
        plan_ref: str,
        bundle_payload: dict[str, object],
        *,
        created_rel: str | None = None,
        before_finalize: Callable[[str, str], None] | None = None,
        prepare_general: Callable[[str], None] | None = None,
    ) -> str:
        pre_family = MODULE.classify_docs_closeout(
            plan_ref=plan_ref,
            bundle_payload=bundle_payload,
            root=root,
        )
        begin = MODULE.followups_capture.begin_cycle(root, plan_ref, pre_family)
        cycle_id = str(begin["capture_cycle_id"])
        if prepare_general is None:
            self._write_capture_receipts(
                root,
                plan_ref,
                followups_capture_cycle_id=cycle_id,
            )
        else:
            prepare_general(cycle_id)
        MODULE.followups_capture.checkpoint_general_pi(root, plan_ref, cycle_id)
        for index, role in enumerate(MODULE.followups_capture.REQUIRED_ROLES):
            MODULE.followups_capture.prepare_role(root, plan_ref, cycle_id, role)
            if before_finalize is not None:
                before_finalize(role, cycle_id)
            if index == 0 and created_rel:
                self._write_owned_followup(root, created_rel, plan_ref)
                output = f"Created: {created_rel}\nSummary: fixture\n".encode()
            else:
                output = b"NO FOLLOWUPS\nSummary: none\n"
            MODULE.followups_capture.finalize_role(root, plan_ref, cycle_id, role, output)
        return cycle_id

    def _write_pi_backlog(
        self,
        root: Path,
        rel_path: str,
        *,
        source_ref: str = "docs/plans/260418_1032_fixture.md",
        entries: list[dict[str, str]] | None = None,
    ) -> None:
        entries = entries or []
        lines = [
            "# Process improvements backlog - fixture",
            "",
            "**Date:** 2026-04-18 10:10 MSK",
            f"**Source ref:** `{source_ref}`",
            "**Status:** Draft",
            "",
            "## Suggestions (truth)",
        ]
        for index, raw_entry in enumerate(entries, start=1):
            entry = {
                "status": "open",
                "priority": "P1",
                "role": "Coder",
                "owner": "Architect",
                "promotion_class": "helper_change",
                "target_canon_path": "null",
                "target_repo_scope": "null",
                "delivery_mode": "null",
                "execution_kind": "null",
                "execution_ref": "null",
                "delivery_refs": "null",
                "handled_ref": "null",
                "promoted_at": "null",
                "handled_at": "null",
                "trigger_ref": "docs/code_reviews/fixture.md#B1",
                "source_ref": source_ref,
                "symptom": "fixture symptom",
                "process_gap": "fixture gap",
                "suggested_fix": "fixture fix",
                "created_at": "2026-04-18 10:10 MSK",
                "triage_note": "none",
            }
            entry.update(raw_entry)
            lines.append(f"### PI-{index:03d}")
            for key in COLLECT.ENTRY_FIELD_ORDER:
                lines.append(f"- {key}: `{entry[key]}`")
            lines.append("")
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _queue_paths(self, root: Path) -> PLAN_QUEUE.QueuePaths:
        return PLAN_QUEUE.QueuePaths(root=root, state_path=root / ".planveyor.planqueue.json", log_path=root / ".planveyor.planqueue.log")

    def _activate_runtime_fixture(self, paths: PLAN_QUEUE.QueuePaths, *, now: str) -> None:
        """Activate a queue fixture without coupling runtime-context tests to lint setup."""

        with mock.patch.object(PLAN_QUEUE, "_plan_lint_activation_blocker", return_value=None):
            PLAN_QUEUE.activate_next(paths, now=now)

    def _advance_runtime_fixture(
        self,
        paths: PLAN_QUEUE.QueuePaths,
        status: str,
        *,
        now: str,
    ) -> None:
        """Advance a runtime-context fixture without coupling it to lint setup."""

        with mock.patch.object(PLAN_QUEUE, "_plan_lint_activation_blocker", return_value=None):
            PLAN_QUEUE.advance_queue(paths, status, now=now)

    def test_review_status_blocking_parser_distinguishes_ok_no_blockers(self) -> None:
        self.assertTrue(MODULE._review_status_is_blocking("❌ S1 blocker(ы)"))
        self.assertTrue(MODULE._review_status_is_blocking("S1 blocker"))
        self.assertFalse(MODULE._review_status_is_blocking("✅ OK"))
        self.assertFalse(MODULE._review_status_is_blocking("✅ OK, no blockers"))

    def test_completed_state_requires_terminal_status_and_already_materialized_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1000_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["reason_code"], "semantic_closeout_materialized")
        self.assertEqual(payload["plan_ref"], plan_rel)
        self.assertEqual(payload["schema"], "docs_closeout_payload.v1")
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["schema_errors"], [])
        self.assertIn("- docs_closeout_payload_schema=docs_closeout_payload.v1", payload["dispatch_context_block"])
        self.assertIn("- docs_closeout_payload_schema_state=ok", payload["dispatch_context_block"])
        self.assertEqual(len(payload["dispatch_family"]), 8)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "no_net_docs_diff")
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["role"], "Architect")
        self.assertEqual(payload["architect_final_handoff"]["plan_ref"], plan_rel)
        self.assertIn("final_docs_commit=no_op|landed", payload["architect_final_handoff"]["proof_expectation"])

    def test_accepted_red_closeout_requires_helper_completed_receipt_and_owns_routing_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260724_0200_process_accepted_red.md"
            plan = self._write_plan(root, plan_rel, status="Superseded")
            self._init_git(root)
            self._commit_all(root)
            ordinary = MODULE.plan_status_oracle.oracle_result(plan)
            review_rel = "docs/code_reviews/260724_0200_process_accepted_red.md"
            successor_rel = "docs/plans/260724_0201_process_successor.md"
            accepted = replace(
                ordinary,
                terminal_disposition="accepted_red_supersession",
                delivery_green=False,
                staging_policy="forbidden",
                durable_capture_required=True,
                accepted_red_successor_plan=successor_rel,
                accepted_red_historical_review=review_rel,
                accepted_red_review_bundle_sha256="a" * 64,
                terminal_disposition_reason="fixture",
            )
            bundle = {
                **self._bundle_payload("accepted_red_recovered"),
                "terminal_disposition": "accepted_red_supersession",
                "delivery_green": False,
                "staging_policy": "forbidden",
                "durable_capture_required": True,
                "durable_capture_state": "cleanup_recorded",
                "active_checkout_state": "clean",
                "recovery_state": "completed",
                "recovery_ref": "refs/planveyor/rejected-baselines/fixture/" + ("a" * 64),
                "recovery_manifest_path": ".planveyor/rejected-baselines/fixture/manifest.json",
                "recovery_cleanup_path": ".planveyor/rejected-baselines/fixture/cleanup.json",
                "recovery_plan": "docs/plans/260724_0202_process_recovery.md",
                "recovery_code_draft": (
                    "docs/code_drafts/260724_0202_process_recovery__code_draft.md"
                ),
                "recovery_targets": ["docs/rejected-overlap.md"],
                "successor_plan": successor_rel,
                "review_bundle_sha256": "a" * 64,
                "capture_commit": "b" * 40,
                "cleanup_commit": "c" * 40,
                "captured_parent": "d" * 40,
            }

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ) as oracle_result,
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=bundle,
                    root=root,
                )

        oracle_result.assert_called_once_with(plan, context=mock.ANY)
        self.assertEqual(oracle_result.call_args.kwargs["context"].project_root, root)
        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["reason_code"], "accepted_red_recovery_completed")
        self.assertEqual(payload["semantic_closeout_kind"], "accepted_red_recovered")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "accepted_red_evidence_ref_materialized")
        self.assertEqual(
            payload["accepted_red_routing_docs"],
            [
                plan_rel,
                "docs/code_drafts/260724_0200_process_accepted_red__code_draft.md",
                review_rel,
                successor_rel,
            ],
        )
        self.assertEqual(payload["schema_state"], "ok")

    def test_accepted_red_closeout_live_route_guard_blocks_completion_and_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260724_0201_process_accepted_red_guarded.md"
            plan = self._write_plan(
                root,
                plan_rel,
                status="Superseded",
                machine_authority=False,
            )
            self._init_git(root)
            self._commit_all(root)
            ordinary = MODULE.plan_status_oracle.oracle_result(plan)
            review_rel = "docs/code_reviews/260724_0201_process_accepted_red_guarded.md"
            successor_rel = "docs/plans/260724_0202_process_successor.md"
            guarded = replace(
                ordinary,
                terminal_disposition="accepted_red_supersession",
                delivery_green=False,
                staging_policy="forbidden",
                durable_capture_required=True,
                accepted_red_successor_plan=successor_rel,
                accepted_red_historical_review=review_rel,
                accepted_red_review_bundle_sha256="a" * 64,
                terminal_disposition_reason="fixture",
                route_guard_triggered=True,
                route_guard_kind="machine_authority_decision_missing_required_carrier",
                queue_closeout_ready=False,
                queue_closeout_kind="route_guard_blocked",
            )
            bundle = {
                **self._bundle_payload("accepted_red_recovered"),
                "terminal_disposition": "accepted_red_supersession",
                "delivery_green": False,
                "staging_policy": "forbidden",
                "durable_capture_required": True,
                "durable_capture_state": "cleanup_recorded",
                "active_checkout_state": "clean",
                "recovery_state": "completed",
                "recovery_ref": "refs/planveyor/rejected-baselines/fixture/" + ("a" * 64),
                "recovery_manifest_path": ".planveyor/rejected-baselines/fixture/manifest.json",
                "recovery_cleanup_path": ".planveyor/rejected-baselines/fixture/cleanup.json",
                "recovery_plan": "docs/plans/260724_0203_process_recovery.md",
                "recovery_code_draft": "docs/code_drafts/260724_0203_process_recovery__code_draft.md",
                "recovery_targets": ["docs/rejected-overlap.md"],
                "successor_plan": successor_rel,
                "review_bundle_sha256": "a" * 64,
                "capture_commit": "b" * 40,
                "cleanup_commit": "c" * 40,
                "captured_parent": "d" * 40,
            }

            with (
                mock.patch.object(MODULE.plan_status_oracle, "oracle_result", return_value=guarded),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=bundle,
                    root=root,
                )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(
            payload["reason_code"],
            "oracle_terminal_admission_blocked:machine_authority_decision_missing_required_carrier",
        )
        self.assertNotEqual(payload["reason_code"], "accepted_red_recovery_completed")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")

    def test_accepted_red_topology_rebind_stays_in_shared_oracle_authority(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("plan_status_oracle.oracle_result", source)
        self.assertNotIn("ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST", source)
        self.assertNotIn("successor backlink does not match source", source)
        self.assertNotIn("depends_on[]", source)

    def test_accepted_red_closeout_pending_or_identity_mismatch_stays_blocked(self) -> None:
        for mutation in (
            {"closeout_kind": "accepted_red_pending", "bundle_ok": False, "recovery_state": "cleanup_required"},
            {"successor_plan": "docs/plans/wrong.md"},
            {"delivery_green": True},
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = "docs/plans/260724_0210_process_accepted_red.md"
                review_rel = (
                    "docs/code_reviews/260724_0210_process_accepted_red.md"
                )
                plan = self._write_plan(
                    root,
                    plan_rel,
                    status="Superseded",
                    review_artifact=review_rel,
                )
                plan.write_text(
                    plan.read_text(encoding="utf-8")
                    .replace(
                        "                ## Review artifacts",
                        "## Review artifacts",
                    )
                    .replace(
                        "                - Code review (primary):",
                        "- Code review (primary):",
                    ),
                    encoding="utf-8",
                )
                (root / review_rel).parent.mkdir(parents=True, exist_ok=True)
                (root / review_rel).write_text("# Review\n", encoding="utf-8")
                # The authority reader treats any `.git` directory as an
                # advertised repository and fails closed if it has no valid
                # HEAD.  This fixture needs the ordinary legacy oracle only
                # as a baseline for its accepted-red mutation matrix.
                self._init_git(root)
                self._commit_all(root)
                ordinary = MODULE.plan_status_oracle.oracle_result(plan)
                accepted = replace(
                    ordinary,
                    terminal_disposition="accepted_red_supersession",
                    delivery_green=False,
                    staging_policy="forbidden",
                    durable_capture_required=True,
                    accepted_red_successor_plan="docs/plans/260724_0211_process_successor.md",
                    accepted_red_historical_review="docs/code_reviews/260724_0210_process_accepted_red.md",
                    accepted_red_review_bundle_sha256="a" * 64,
                    terminal_disposition_reason="fixture",
                )
                bundle = {
                    **self._bundle_payload("accepted_red_recovered"),
                    "terminal_disposition": "accepted_red_supersession",
                    "delivery_green": False,
                    "staging_policy": "forbidden",
                    "durable_capture_required": True,
                    "durable_capture_state": "cleanup_recorded",
                    "active_checkout_state": "clean",
                    "recovery_state": "completed",
                    "recovery_ref": "refs/planveyor/rejected-baselines/fixture/" + ("a" * 64),
                    "recovery_manifest_path": ".planveyor/rejected-baselines/fixture/manifest.json",
                    "recovery_cleanup_path": ".planveyor/rejected-baselines/fixture/cleanup.json",
                    "recovery_plan": "docs/plans/260724_0212_process_recovery.md",
                    "recovery_code_draft": (
                        "docs/code_drafts/260724_0212_process_recovery__code_draft.md"
                    ),
                    "recovery_targets": ["docs/rejected-overlap.md"],
                    "successor_plan": accepted.accepted_red_successor_plan,
                    "review_bundle_sha256": "a" * 64,
                    "capture_commit": "b" * 40,
                    "cleanup_commit": "c" * 40,
                    "captured_parent": "d" * 40,
                    **mutation,
                }
                with mock.patch.object(MODULE.plan_status_oracle, "oracle_result", return_value=accepted):
                    payload = MODULE.classify_docs_closeout(
                        plan_ref=plan_rel,
                        bundle_payload=bundle,
                        root=root,
                    )
                self.assertEqual(payload["state"], "blocked")
                self.assertTrue(
                    payload["reason_code"] in {
                        "accepted_red_recovery_incomplete",
                        "docs_closeout_payload_schema_invalid",
                    }
                    or str(payload["reason_code"]).startswith("accepted_red_receipt_"),
                    payload["reason_code"],
                )

    def test_layer_a_public_bundle_failure_short_circuits_before_docs_helper(self) -> None:
        accepted_schema = "planveyor_rejected_baseline_error.v1"
        accepted_reason = "accepted_red_closeout_invalid_carrier"
        accepted_payload = json.dumps(
            {
                "schema": accepted_schema,
                "state": "blocked",
                "reason_code": accepted_reason,
                "message": "accepted-red closeout is blocked",
                "cause": {"reason_code": "routing_contract_invalid"},
            },
            sort_keys=True,
        )
        rejected_payloads = {
            "flat_foreign_reason": json.dumps(
                {"reason_code": "active_checkout_drift"},
                sort_keys=True,
            ),
            "nested_accepted_reason": json.dumps(
                {
                    "schema": accepted_schema,
                    "state": "blocked",
                    "reason_code": "active_checkout_drift",
                    "cause": {"reason_code": accepted_reason},
                },
                sort_keys=True,
            ),
            "sibling_accepted_reason": json.dumps(
                {
                    "schema": accepted_schema,
                    "state": "blocked",
                    "reason_code": "active_checkout_drift",
                    "sibling": {"reason_code": accepted_reason},
                },
                sort_keys=True,
            ),
            "malformed": (
                '{"schema": "planveyor_rejected_baseline_error.v1", '
                '"state": "blocked", '
                '"reason_code": "accepted_red_closeout_invalid_carrier"'
            ),
            "nan_constant": (
                f'{{"schema": "{accepted_schema}", '
                '"state": "blocked", '
                f'"reason_code": "{accepted_reason}", '
                '"cause": NaN}'
            ),
            "infinity_constant": (
                f'{{"schema": "{accepted_schema}", '
                '"state": "blocked", '
                f'"reason_code": "{accepted_reason}", '
                '"cause": Infinity}'
            ),
            "negative_infinity_constant": (
                f'{{"schema": "{accepted_schema}", '
                '"state": "blocked", '
                f'"reason_code": "{accepted_reason}", '
                '"cause": -Infinity}'
            ),
            "multiple_objects": accepted_payload + "\n{}",
            "non_object": json.dumps(
                [
                    {
                        "schema": accepted_schema,
                        "state": "blocked",
                        "reason_code": accepted_reason,
                    }
                ],
                sort_keys=True,
            ),
            "duplicate_schema": (
                '{"schema": "foreign.v1", '
                f'"schema": "{accepted_schema}", '
                '"state": "blocked", '
                f'"reason_code": "{accepted_reason}"'
                "}"
            ),
            "duplicate_state": (
                f'{{"schema": "{accepted_schema}", '
                '"state": "foreign", '
                '"state": "blocked", '
                f'"reason_code": "{accepted_reason}"'
                "}"
            ),
            "duplicate_reason": (
                f'{{"schema": "{accepted_schema}", '
                '"state": "blocked", '
                '"reason_code": "active_checkout_drift", '
                f'"reason_code": "{accepted_reason}"'
                "}"
            ),
            "missing_schema": json.dumps(
                {
                    "state": "blocked",
                    "reason_code": accepted_reason,
                },
                sort_keys=True,
            ),
            "foreign_schema": json.dumps(
                {
                    "schema": "foreign.v1",
                    "state": "blocked",
                    "reason_code": accepted_reason,
                },
                sort_keys=True,
            ),
            "missing_state": json.dumps(
                {
                    "schema": accepted_schema,
                    "reason_code": accepted_reason,
                },
                sort_keys=True,
            ),
            "foreign_state": json.dumps(
                {
                    "schema": accepted_schema,
                    "state": "foreign",
                    "reason_code": accepted_reason,
                },
                sort_keys=True,
            ),
            "missing_reason": json.dumps(
                {
                    "schema": accepted_schema,
                    "state": "blocked",
                },
                sort_keys=True,
            ),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260724_0250_process_layer_a.md"
            (root / plan_rel).parent.mkdir(parents=True, exist_ok=True)
            (root / plan_rel).write_text("# Layer A fixture\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            shell = dedent(
                """\
                source "$1"
                test_bundle_payload="$3"
                planveyor_plan_bundle() {
                  printf '%s\\n' "$test_bundle_payload" >&2
                  return 2
                }
                functions[_planveyor_docs_closeout_real_py_any]="${functions[_planveyor_py_any]}"
                _planveyor_py_any() {
                  if [[ "${1:-}" == "-" ]]; then
                    _planveyor_docs_closeout_real_py_any "$@"
                    return $?
                  fi
                  printf '%s\\n' '__DOCS_HELPER_CALLED__'
                  return 0
                }
                planveyor_docs_closeout "$2" --json
                """
            )

            for case, payload in rejected_payloads.items():
                with self.subTest(case=case):
                    result = run_zsh_fixture(
                        shell,
                        cwd=root,
                        path=os.environ.get("PATH", os.defpath),
                        pybin=sys.executable,
                        argv0="docs-closeout-layer-a-test",
                        argv_tail=(str(MODULE_PATH.with_name("planveyor.zsh")), plan_rel, payload),
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(
                        result.returncode,
                        1,
                        result.stdout + result.stderr,
                    )
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr.rstrip("\n"), payload)
                    self.assertNotIn(
                        "__DOCS_HELPER_CALLED__",
                        result.stdout + result.stderr,
                    )

            accepted = run_zsh_fixture(
                shell,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=sys.executable,
                argv0="docs-closeout-layer-a-test",
                argv_tail=(str(MODULE_PATH.with_name("planveyor.zsh")), plan_rel, accepted_payload),
                capture_output=True,
                check=False,
            )

        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertEqual(accepted.stdout, "__DOCS_HELPER_CALLED__\n")
        self.assertEqual(accepted.stderr, "")

    def test_accepted_red_snapshot_is_consumed_without_path_reopen(self) -> None:
        target_rel = "docs/recovery-overlap.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel=target_rel,
            )
            bundle["active_checkout_state"] = "clean"
            real_snapshot = MODULE.fs_object_identity.snapshot_regular_or_absent

            def snapshot_then_replace(
                trusted_root: Path,
                relative_path: str,
            ) -> MODULE.fs_object_identity.ObjectSnapshot:
                snapshot = real_snapshot(trusted_root, relative_path)
                (trusted_root / relative_path).write_text(
                    "changed after validated snapshot\n",
                    encoding="utf-8",
                )
                return snapshot

            with mock.patch.object(
                MODULE.fs_object_identity,
                "snapshot_regular_or_absent",
                side_effect=snapshot_then_replace,
            ) as provider:
                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

        self.assertTrue(valid, reason)
        self.assertEqual(reason, "accepted_red_receipt_verified")
        provider.assert_called_once_with(root, target_rel)

    def test_accepted_red_snapshot_accepts_stable_regular_absent_and_mode_overlap(self) -> None:
        cases = (
            ("regular", True, False, "clean"),
            ("absent", False, False, "clean"),
            ("mode_overlap", True, True, "recovery_owned_overlap"),
        )
        for case, target_present, executable, expected_state in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                target_rel = "docs/recovery-overlap.md"
                source_rel, bundle = self._accepted_red_receipt_fixture(
                    root,
                    target_rel=target_rel,
                    target_present=target_present,
                )
                if executable:
                    (root / target_rel).chmod(0o755)
                bundle["active_checkout_state"] = expected_state

                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

                self.assertTrue(valid)
                self.assertEqual(reason, "accepted_red_receipt_verified")

    def test_accepted_red_receipt_survives_unrelated_head_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_rel = "docs/recovery-overlap.md"
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel=target_rel,
            )
            ref_tip = self._git(
                root,
                "rev-parse",
                str(bundle["recovery_ref"]),
            ).stdout.strip()
            (root / "docs/unrelated.md").write_text(
                "unrelated mainline advance\n",
                encoding="utf-8",
            )
            self._commit_all(root, "unrelated mainline advance")
            advanced_head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            bundle["active_checkout_state"] = "clean"

            valid, reason = MODULE.verify_accepted_red_receipt(
                root=root,
                plan_ref=source_rel,
                bundle_payload=bundle,
            )

            self.assertNotEqual(advanced_head, bundle["captured_parent"])
            self.assertEqual(
                self._git(
                    root,
                    "rev-parse",
                    str(bundle["recovery_ref"]),
                ).stdout.strip(),
                ref_tip,
            )
            self.assertEqual((root / target_rel).read_bytes(), b"baseline\n")
            self.assertTrue(valid)
            self.assertEqual(reason, "accepted_red_receipt_verified")

    def test_accepted_red_allowlisted_rebind_consumes_shared_effective_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_rel = "docs/recovery-overlap.md"
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel=target_rel,
            )
            effective_targets = [target_rel, "docs/recovery-extra.md"]
            bundle.update(
                recovery_targets=effective_targets,
                recovery_contract_state="allowlisted_terminal_rebind",
                active_checkout_state="clean",
            )
            durable = MODULE.plan_status_oracle.AcceptedRedDurableRefResult(
                state="valid_cleanup",
                reason="fixture",
                capture_commit=str(bundle["capture_commit"]),
                cleanup_commit=str(bundle["cleanup_commit"]),
                recovery_contract={
                    "recovery_plan": bundle["recovery_plan"],
                    "recovery_code_draft": bundle["recovery_code_draft"],
                    "recovery_targets": effective_targets,
                    "recovery_status": "done",
                    "snapshot_bridge": None,
                },
                recovery_contract_state="allowlisted_terminal_rebind",
            )

            with mock.patch.object(
                MODULE.plan_status_oracle,
                "validate_accepted_red_durable_ref",
                return_value=durable,
            ) as validator:
                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

            rejected = MODULE.plan_status_oracle.AcceptedRedDurableRefResult(
                "invalid",
                "digest mismatch",
            )
            with mock.patch.object(
                MODULE.plan_status_oracle,
                "validate_accepted_red_durable_ref",
                return_value=rejected,
            ):
                invalid, invalid_reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

        self.assertTrue(valid, reason)
        self.assertEqual(reason, "accepted_red_receipt_verified")
        validator.assert_called_once()
        shared_contract = validator.call_args.args[1]
        self.assertEqual(shared_contract["source_plan"], source_rel)
        self.assertEqual(
            shared_contract["targets"],
            sorted({target_rel}),
        )
        self.assertFalse(invalid)
        self.assertEqual(invalid_reason, "accepted_red_recovery_identity_invalid")

    def test_accepted_red_head_read_ignores_git_replace_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_git(root)
            payload = root / "payload.txt"
            payload.write_text("original\n", encoding="utf-8")
            self._commit_all(root, "original")
            original = self._git(root, "rev-parse", "HEAD").stdout.strip()
            payload.write_text("current\n", encoding="utf-8")
            self._commit_all(root, "current")
            current = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self._git(root, "replace", current, original)

            replaced = self._git(root, "show", "HEAD:payload.txt").stdout
            safe = MODULE._head_regular_or_absent(root, "payload.txt")

        self.assertEqual(replaced, "original\n")
        self.assertEqual(safe, ("regular", b"current\n", "100644"))

    def test_accepted_red_terminal_legacy_contract_matches_child2_state(self) -> None:
        cases = (
            ("terminal", "Done", "legacy_completed_terminal", True),
            ("nonterminal", "In progress", "legacy_completed_terminal", False),
            ("unknown_state", "Done", "legacy_pending_review", False),
        )
        for case, recovery_status, contract_state, expected_valid in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                source_rel, bundle = self._accepted_red_receipt_fixture(
                    root,
                    target_rel="docs/recovery-overlap.md",
                    frozen_recovery_contract=False,
                    recovery_status=recovery_status,
                )
                bundle["active_checkout_state"] = "clean"
                bundle["recovery_contract_state"] = contract_state
                recovery_review = (
                    root
                    / "docs/code_reviews/260724_0301_process_recovery.md"
                )

                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

                self.assertFalse(recovery_review.exists())
                self.assertEqual(valid, expected_valid)
                self.assertEqual(
                    reason,
                    (
                        "accepted_red_receipt_verified"
                        if expected_valid
                        else "accepted_red_recovery_contract_state_mismatch"
                    ),
                )

    def test_accepted_red_source_and_recovery_review_routes_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
                frozen_recovery_contract=False,
                recovery_status="In progress",
                write_recovery_review=True,
                source_review_directory="docs/doc_reviews",
                source_review_label="Code review (primary)",
                recovery_review_directory="docs/code_reviews",
                recovery_review_label="Doc review (docs-only)",
            )
            bundle["active_checkout_state"] = "clean"
            bundle["recovery_contract_state"] = "legacy_review_anchored"

            valid, reason = MODULE.verify_accepted_red_receipt(
                root=root,
                plan_ref=source_rel,
                bundle_payload=bundle,
            )
            self.assertTrue(valid)
            self.assertEqual(reason, "accepted_red_receipt_verified")
            self.assertNotIn("historical_review", bundle)
            manifest = json.loads(
                self._git(
                    root,
                    "show",
                    f"{bundle['capture_commit']}:{bundle['recovery_manifest_path']}",
                ).stdout
            )
            self.assertEqual(
                manifest["historical_review"],
                "docs/doc_reviews/260724_0300_process_source.md",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
                frozen_recovery_contract=False,
                recovery_status="In progress",
                write_recovery_review=True,
            )
            bundle["active_checkout_state"] = "clean"
            bundle["recovery_contract_state"] = "legacy_review_anchored"
            recovery_plan = root / str(bundle["recovery_plan"])
            recovery_plan.write_text(
                recovery_plan.read_text(encoding="utf-8").replace(
                    "docs/code_reviews/260724_0301_process_recovery.md",
                    "docs/code_reviews/260724_0300_process_source.md",
                ),
                encoding="utf-8",
            )

            valid, reason = MODULE.verify_accepted_red_receipt(
                root=root,
                plan_ref=source_rel,
                bundle_payload=bundle,
            )
            self.assertFalse(valid)
            self.assertEqual(reason, "accepted_red_recovery_review_missing")

    def test_accepted_red_source_review_authority_is_required_in_manifest(self) -> None:
        cases = (
            ("missing", None, True),
            (
                "recovery_substitution",
                "docs/code_reviews/260724_0301_process_recovery.md",
                False,
            ),
        )
        for case, manifest_review, omit_manifest_review in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                source_rel, bundle = self._accepted_red_receipt_fixture(
                    root,
                    target_rel="docs/recovery-overlap.md",
                    manifest_historical_review=manifest_review,
                    omit_manifest_historical_review=omit_manifest_review,
                )
                bundle["active_checkout_state"] = "clean"

                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

                self.assertNotIn("historical_review", bundle)
                self.assertFalse(valid)
                self.assertEqual(reason, "accepted_red_manifest_identity_mismatch")

    def test_accepted_red_docs_closeout_does_not_reconstruct_code_review_path(
        self,
    ) -> None:
        source = inspect.getsource(MODULE.verify_accepted_red_receipt)
        self.assertNotIn("docs/code_reviews/", source)
        self.assertEqual(source.count("resolve_accepted_red_review_path"), 2)
        self.assertNotIn('bundle_payload.get("historical_review")', source)
        self.assertIn('"historical_review": source_review_rel', source)

    def test_legacy_accepted_red_bundle_matches_public_docs_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/fixture_targets/accepted_red_legacy_fixture.md",
                frozen_recovery_contract=False,
                recovery_status="Done",
            )
            receipt["active_checkout_state"] = "clean"
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            docs_result = self._run_public_docs_closeout(root, source_rel, bundle)

        self.assertTrue(bundle["bundle_ok"])
        self.assertEqual(bundle["durable_capture_state"], "cleanup_recorded")
        self.assertEqual(bundle["recovery_state"], "completed")
        self.assertEqual(bundle["active_checkout_state"], "clean")
        self.assertEqual(docs_result.returncode, 0, docs_result.stderr)
        self.assertEqual(docs_result.stderr, "")
        docs_payload = json.loads(docs_result.stdout)
        self.assertEqual(docs_payload["state"], "completed")
        self.assertEqual(
            docs_payload["reason_code"],
            "accepted_red_recovery_completed",
        )

    def test_accepted_red_snapshot_errors_map_once_without_retry(self) -> None:
        cases = (
            ("symlink_forbidden", "accepted_red_active_checkout_aliased"),
            ("leaf_not_regular", "accepted_red_active_checkout_non_regular"),
            ("unsupported_capability", "accepted_red_active_checkout_drift"),
            ("unsafe_trusted_root", "accepted_red_active_checkout_drift"),
            ("ancestor_missing", "accepted_red_active_checkout_drift"),
            ("ancestor_not_directory", "accepted_red_active_checkout_drift"),
            ("ancestor_identity_changed", "accepted_red_active_checkout_drift"),
            ("leaf_identity_changed", "accepted_red_active_checkout_drift"),
            ("leaf_metadata_changed", "accepted_red_active_checkout_drift"),
            ("filesystem_ambiguous", "accepted_red_active_checkout_drift"),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_rel = "docs/recovery-overlap.md"
            source_rel, bundle = self._accepted_red_receipt_fixture(
                root,
                target_rel=target_rel,
            )
            for internal_reason, expected_reason in cases:
                with (
                    self.subTest(internal_reason=internal_reason),
                    mock.patch.object(
                        MODULE.fs_object_identity,
                        "snapshot_regular_or_absent",
                        side_effect=MODULE.fs_object_identity.ObjectIdentityError(
                            internal_reason,
                            "fixture",
                        ),
                    ) as provider,
                ):
                    valid, reason = MODULE.verify_accepted_red_receipt(
                        root=root,
                        plan_ref=source_rel,
                        bundle_payload=bundle,
                    )

                    self.assertFalse(valid)
                    self.assertEqual(reason, expected_reason)
                    provider.assert_called_once_with(root, target_rel)

    def test_layer_b_direct_and_public_paths_share_docs_mapper_reasons(self) -> None:
        cases = (
            ("alias", True, "accepted_red_active_checkout_aliased"),
            ("non_regular", True, "accepted_red_active_checkout_non_regular"),
            ("regular_drift", False, "accepted_red_active_checkout_drift"),
        )
        for case, recovery_owned, expected_reason in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                target_rel = "docs/rejected-target.md"
                source_rel, receipt = self._accepted_red_receipt_fixture(
                    root,
                    target_rel=target_rel,
                    target_recovery_owned=recovery_owned,
                )
                target = root / target_rel
                if case == "alias":
                    target.unlink()
                    target.symlink_to("missing-target")
                elif case == "non_regular":
                    target.unlink()
                    target.mkdir()
                else:
                    target.write_text("regular drift\n", encoding="utf-8")
                bundle = self._accepted_red_completed_bundle(source_rel, receipt)

                direct_valid, direct_reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )
                public = self._run_public_docs_closeout(
                    root,
                    source_rel,
                    bundle,
                )

                self.assertFalse(direct_valid)
                self.assertEqual(direct_reason, expected_reason)
                self.assertEqual(public.returncode, 0, public.stderr)
                self.assertEqual(public.stderr, "")
                public_payload = json.loads(public.stdout)
                self.assertEqual(public_payload["state"], "blocked")
                self.assertEqual(public_payload["reason_code"], direct_reason)

    def test_accepted_red_absence_readback_is_lexical_for_broken_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken-target"
            path.symlink_to("missing-target")

            self.assertFalse(path.exists())
            self.assertTrue(MODULE.lexical_exists(path))

    def test_accepted_red_overlap_requires_a_regular_non_symlink_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            regular = root / "regular"
            regular.write_text("recovery delta\n", encoding="utf-8")
            broken = root / "broken"
            broken.symlink_to("missing-target")
            live_target = root / "live-target"
            live_target.write_text("live\n", encoding="utf-8")
            live = root / "live"
            live.symlink_to(live_target)
            directory = root / "directory"
            directory.mkdir()
            fifo = root / "fifo"
            os.mkfifo(fifo)

            self.assertTrue(MODULE.regular_file_exists(regular))
            for path in (broken, live, directory, fifo):
                with self.subTest(path=path.name):
                    self.assertTrue(MODULE.lexical_exists(path))
                    self.assertFalse(MODULE.regular_file_exists(path))

    def test_accepted_red_receipt_rejects_symlinked_target_ancestors(self) -> None:
        target_rel = "docs/recovery-owned/nested-overlap.md"
        for alias_kind in ("in_repo", "out_of_repo"):
            with (
                self.subTest(alias_kind=alias_kind),
                tempfile.TemporaryDirectory() as tmpdir,
                tempfile.TemporaryDirectory() as outside_tmpdir,
            ):
                root = Path(tmpdir)
                source_rel, bundle = self._accepted_red_receipt_fixture(
                    root,
                    target_rel=target_rel,
                )
                target = root / target_rel
                ancestor = target.parent
                target.unlink()
                ancestor.rmdir()
                alias_root = (
                    root / "foreign-recovery-owned"
                    if alias_kind == "in_repo"
                    else Path(outside_tmpdir)
                )
                alias_root.mkdir(parents=True, exist_ok=True)
                (alias_root / target.name).write_text("aliased recovery delta\n", encoding="utf-8")
                ancestor.symlink_to(alias_root, target_is_directory=True)

                self.assertFalse(
                    MODULE.path_components_are_symlink_free(root, target_rel)
                )
                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

                self.assertFalse(valid)
                self.assertEqual(reason, "accepted_red_active_checkout_aliased")

    def test_accepted_red_receipt_rejects_post_receipt_non_regular_overlap(self) -> None:
        source_rel = "docs/plans/260724_0300_process_source.md"
        recovery_rel = "docs/plans/260724_0301_process_recovery.md"
        recovery_draft_rel = "docs/code_drafts/260724_0301_process_recovery__code_draft.md"
        target_rel = "docs/recovery-overlap.md"
        review_sha = "a" * 64
        ref = f"refs/planveyor/rejected-baselines/fixture/{review_sha}"
        manifest_rel = ".planveyor/rejected-baselines/fixture/manifest.json"
        cleanup_rel = ".planveyor/rejected-baselines/fixture/cleanup.json"
        successor_rel = "docs/plans/260724_0302_process_successor.md"
        source_review_rel = (
            "docs/code_reviews/260724_0300_process_source.md"
        )

        for entry_kind in ("broken_symlink", "live_symlink", "directory", "fifo"):
            with self.subTest(entry_kind=entry_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                for rel in (
                    source_rel,
                    source_review_rel,
                    recovery_rel,
                    recovery_draft_rel,
                    target_rel,
                ):
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / source_rel).write_text(
                    "# Source\n\n"
                    "## Review artifacts\n"
                    f"- Code review (primary): `{source_review_rel}`\n",
                    encoding="utf-8",
                )
                (root / source_review_rel).write_text(
                    "# Source review\n",
                    encoding="utf-8",
                )
                (root / recovery_rel).write_text(
                    "# Recovery\n\n"
                    "**Status:** In progress\n\n"
                    f"- Superseded incident plan: `{source_rel}`.\n"
                    f"- Code draft(s): `{recovery_draft_rel}`\n",
                    encoding="utf-8",
                )
                recovery_meta = {
                    "code_draft_meta": {
                        "plan": recovery_rel,
                        "cluster": "process",
                        "targets": [{"path": target_rel, "kind": "doc"}],
                        "deleted_paths": [],
                    }
                }
                (root / recovery_draft_rel).write_text(
                    f"# Draft\n\n```json\n{json.dumps(recovery_meta, indent=2)}\n```\n",
                    encoding="utf-8",
                )
                target = root / target_rel
                target.write_text("baseline\n", encoding="utf-8")
                self._init_git(root)
                self._commit_all(root)
                captured_parent = self._git(root, "rev-parse", "HEAD").stdout.strip()

                manifest = {
                    "schema": "planveyor_rejected_baseline.v1",
                    "source_plan": source_rel,
                    "recovery_plan": recovery_rel,
                    "recovery_code_draft": recovery_draft_rel,
                    "recovery_targets": [target_rel],
                    "successor_plan": successor_rel,
                    "historical_review": source_review_rel,
                    "review_bundle_sha256": review_sha,
                    "recovery_ref": ref,
                    "recovery_manifest_path": manifest_rel,
                    "recovery_cleanup_path": cleanup_rel,
                    "captured_parent": captured_parent,
                    "targets": [{"path": target_rel}],
                }
                manifest_path = root / manifest_rel
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                self._commit_all(root, "capture")
                capture_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()

                cleanup = {
                    "schema": "planveyor_rejected_baseline_cleanup.v1",
                    "source_plan": source_rel,
                    "recovery_plan": recovery_rel,
                    "recovery_code_draft": recovery_draft_rel,
                    "recovery_targets": [target_rel],
                    "recovery_ref": ref,
                    "review_bundle_sha256": review_sha,
                    "capture_commit": capture_commit,
                    "captured_parent": captured_parent,
                    "cleanup_head": captured_parent,
                }
                cleanup_path = root / cleanup_rel
                cleanup_path.write_text(json.dumps(cleanup), encoding="utf-8")
                self._commit_all(root, "cleanup")
                cleanup_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
                self._git(root, "update-ref", ref, cleanup_commit)
                self._git(root, "reset", "--hard", captured_parent)

                target.unlink()
                if entry_kind == "broken_symlink":
                    target.symlink_to("missing-target")
                elif entry_kind == "live_symlink":
                    live_target = root / "live-target"
                    live_target.write_text("live\n", encoding="utf-8")
                    target.symlink_to(live_target)
                elif entry_kind == "directory":
                    target.mkdir()
                else:
                    os.mkfifo(target)
                bundle = {
                    "recovery_ref": ref,
                    "recovery_manifest_path": manifest_rel,
                    "recovery_cleanup_path": cleanup_rel,
                    "recovery_plan": recovery_rel,
                    "recovery_code_draft": recovery_draft_rel,
                    "recovery_targets": [target_rel],
                    "successor_plan": successor_rel,
                    "review_bundle_sha256": review_sha,
                    "capture_commit": capture_commit,
                    "cleanup_commit": cleanup_commit,
                    "captured_parent": captured_parent,
                    "active_checkout_state": "recovery_owned_overlap",
                }

                valid, reason = MODULE.verify_accepted_red_receipt(
                    root=root,
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                )

                self.assertFalse(valid)
                self.assertEqual(
                    reason,
                    (
                        "accepted_red_active_checkout_aliased"
                        if entry_kind in {"broken_symlink", "live_symlink"}
                        else "accepted_red_active_checkout_non_regular"
                    ),
                )

    def test_schema_validation_blocks_missing_nested_payload_and_text_is_renderable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1040_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        malformed = self._clone_payload(payload)
        del malformed["followups_reconciliation"]
        del malformed["terminal_closeout_fast_path"]

        validated = MODULE.validate_docs_closeout_payload(malformed)
        text = MODULE.render_text(validated)

        self.assertEqual(validated["state"], "blocked")
        self.assertEqual(validated["reason_code"], "docs_closeout_payload_schema_invalid")
        self.assertEqual(validated["schema"], "docs_closeout_payload.v1")
        self.assertEqual(validated["schema_state"], "blocked")
        self.assertTrue(
            any("followups_reconciliation: missing required object" in item for item in validated["schema_errors"])
        )
        self.assertTrue(
            any("terminal_closeout_fast_path: missing required object" in item for item in validated["schema_errors"])
        )
        self.assertIn("schema_state=blocked", text)
        self.assertIn("schema_errors=followups_reconciliation: missing required object", text)

    def test_schema_validation_blocks_inconsistent_fast_path_and_architect_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1041_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])
        self.assertEqual(payload["schema_state"], "ok")

        fast_path_inconsistent = self._clone_payload(payload)
        fast_path_inconsistent["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"] = [
            "final_docs_commit_clean"
        ]
        validated_fast_path = MODULE.validate_docs_closeout_payload(fast_path_inconsistent)
        self.assertEqual(validated_fast_path["schema_state"], "blocked")
        self.assertTrue(
            any(
                "eligible=true with non-empty missing_or_dirty_preconditions" in item
                for item in validated_fast_path["schema_errors"]
            )
        )

        handoff_inconsistent = self._clone_payload(payload)
        handoff_inconsistent["architect_final_handoff"]["required"] = True
        validated_handoff = MODULE.validate_docs_closeout_payload(handoff_inconsistent)
        self.assertEqual(validated_handoff["schema_state"], "blocked")
        self.assertTrue(
            any("must be false when final_docs_commit=no_op|landed" in item for item in validated_handoff["schema_errors"])
        )

    def test_schema_validation_fails_closed_for_protected_reclassification_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260729_1909_fixture.md"
            protected_rel = "docs/tools/prompts/fixture_prompt.md"
            self._write_plan(root, plan_rel, status="Done")
            protected_path = root / protected_rel
            protected_path.parent.mkdir(parents=True, exist_ok=True)
            protected_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            protected_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            MODULE.PROTECTED_RECLASSIFICATION_REASON,
        )
        handoff = payload["architect_final_handoff"]
        assert isinstance(handoff, dict)
        self.assertEqual(handoff["task"], MODULE.PROTECTED_DOCS_RECLASSIFICATION_TASK)

        missing_carriers = self._clone_payload(payload)
        missing_carriers["protected_docs_delta_paths"] = []
        missing_handoff = missing_carriers["architect_final_handoff"]
        assert isinstance(missing_handoff, dict)
        missing_handoff["protected_docs_delta_paths"] = []

        mismatched_handoff_carrier = self._clone_payload(payload)
        mismatched_handoff = mismatched_handoff_carrier["architect_final_handoff"]
        assert isinstance(mismatched_handoff, dict)
        mismatched_handoff["protected_docs_delta_paths"] = [
            "docs/tools/prompts/other_fixture.md"
        ]

        mismatched_handoff_final_paths = self._clone_payload(payload)
        mismatched_handoff_final = mismatched_handoff_final_paths["architect_final_handoff"]
        assert isinstance(mismatched_handoff_final, dict)
        mismatched_handoff_final["final_docs_diff_paths"] = []

        staging_authority = self._clone_payload(payload)
        staging_handoff = staging_authority["architect_final_handoff"]
        assert isinstance(staging_handoff, dict)
        staging_handoff["followups_staging_expectations"] = [
            {
                "path": "docs/followups/fixture.md",
                "ownership_class": "ordinary_followup",
                "capture_cycle_id": "fixture-cycle",
                "receipt_content_sha256": "fixture-sha256",
                "receipt_revision": 1,
                "receipt_object_identity": {},
                "expected_object": {},
                "expected_staged_mode": "100644",
            }
        ]

        noncanonical_path_order = self._clone_payload(payload)
        unordered_paths = [
            "docs/tools/prompts/z_fixture.md",
            "docs/tools/prompts/a_fixture.md",
        ]
        noncanonical_path_order["final_docs_diff_paths"] = unordered_paths
        noncanonical_path_order["protected_docs_delta_paths"] = unordered_paths
        unordered_handoff = noncanonical_path_order["architect_final_handoff"]
        assert isinstance(unordered_handoff, dict)
        unordered_handoff["final_docs_diff_paths"] = unordered_paths
        unordered_handoff["protected_docs_delta_paths"] = unordered_paths

        non_reclassification_handoff = self._clone_payload(payload)
        non_reclassification = non_reclassification_handoff["architect_final_handoff"]
        assert isinstance(non_reclassification, dict)
        non_reclassification["required"] = False
        non_reclassification["task"] = "Make one exact docs-only commit."

        for name, malformed in (
            ("missing_carriers", missing_carriers),
            ("mismatched_handoff_carrier", mismatched_handoff_carrier),
            ("mismatched_handoff_final_paths", mismatched_handoff_final_paths),
            ("staging_authority", staging_authority),
            ("noncanonical_path_order", noncanonical_path_order),
            ("non_reclassification_handoff", non_reclassification_handoff),
        ):
            with self.subTest(mutation=name):
                validated = MODULE.validate_docs_closeout_payload(malformed)
                self.assertEqual(validated["state"], "blocked")
                self.assertEqual(validated["reason_code"], "docs_closeout_payload_schema_invalid")
                self.assertEqual(validated["schema_state"], "blocked")
                self.assertTrue(validated["schema_errors"])

    def test_terminal_docs_delta_read_failure_blocks_before_explicit_overrides(self) -> None:
        plan_rel = "docs/plans/260729_1909_fixture.md"
        for explicit in (None, "landed", "required"):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan(root, plan_rel, status="Done")
                self._init_committed_fixture_repo(root)
                with mock.patch.object(
                    MODULE,
                    "_git_status_docs_paths",
                    return_value=([], False),
                ) as status_read:
                    payload = MODULE.classify_docs_closeout(
                        plan_ref=plan_rel,
                        bundle_payload=self._bundle_payload(
                            "already_materialized",
                            final_docs_commit=explicit,
                        ),
                        root=root,
                    )

            handoff = payload["architect_final_handoff"]
            assert isinstance(handoff, dict)
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["reason_code"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
            self.assertEqual(payload["schema_state"], "ok")
            self.assertEqual(payload["final_docs_commit"], "no_op")
            self.assertEqual(payload["final_docs_commit_reason"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
            self.assertEqual(payload["final_docs_diff_paths"], [])
            self.assertEqual(payload["protected_docs_delta_paths"], [])
            self.assertFalse(handoff["required"])
            self.assertEqual(handoff["skip_reason"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
            self.assertEqual(handoff["followups_staging_expectations"], [])
            self.assertEqual(handoff["task"], MODULE.TERMINAL_DOCS_DELTA_UNKNOWN_TASK)
            self.assertEqual(status_read.call_count, 1)

    def test_terminal_docs_delta_snapshot_prevents_success_then_failure_reread(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260729_1909_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            with mock.patch.object(
                MODULE,
                "_git_status_docs_paths",
                side_effect=[([], True), ([], False), ([], False)],
            ) as status_read:
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload("already_materialized"),
                    root=root,
                )

        handoff = payload["architect_final_handoff"]
        assert isinstance(handoff, dict)
        self.assertEqual(status_read.call_count, 1)
        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["reason_code"], "semantic_closeout_materialized")
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "no_net_docs_diff")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["followups_capture_reason"], "capture_cycle_not_requested")
        self.assertEqual(payload["foreign_docs_delta_paths"], [])
        self.assertFalse(handoff["required"])
        self.assertEqual(handoff["skip_reason"], "no_op")

    def test_accepted_red_docs_delta_read_failure_blocks_before_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/tools/prompts/fixture_prompt.md",
            )
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            accepted = self._accepted_red_oracle(root / source_rel, receipt)

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
                mock.patch.object(
                    MODULE,
                    "_git_status_docs_paths",
                    return_value=([], False),
                ) as status_read,
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                )

        handoff = payload["architect_final_handoff"]
        assert isinstance(handoff, dict)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
        self.assertFalse(handoff["required"])
        self.assertEqual(handoff["followups_staging_expectations"], [])
        self.assertEqual(handoff["skip_reason"], MODULE.DOCS_DELTA_UNKNOWN_REASON)
        self.assertEqual(status_read.call_count, 1)

    def test_non_terminal_status_returns_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1001_fixture.md"
            self._write_plan(root, plan_rel, status="Ready for Review")
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "no_op")
        self.assertEqual(payload["reason_code"], "semantic_status_not_terminal")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")
        self.assertEqual(payload["runtime_context"]["latest_stop_reason"], "unknown")
        self.assertEqual(payload["runtime_context"]["latest_stop_reason_scope"], "none")
        self.assertEqual(payload["runtime_context"]["historical_stop_reason"], "unknown")
        self.assertEqual(payload["runtime_context"]["root_cause_class"], "unknown")

    def test_parked_umbrella_ready_for_planner_returns_no_op_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1005_parked_umbrella.md"
            child_rel = "docs/plans/260418_1006_parked_child.md"
            parked_handoffs = dedent(
                """\
                - `Ready for Planner` — Architect
                - `Ready for Coder` — `N/A (parked umbrella)`
                - `Ready for Review` — `N/A (parked umbrella)`
                - `Ready for Arch review` — `N/A (parked umbrella)`
                - `Done` — Architect
                """
            ).rstrip()
            parked_meta = dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "parked",
                    "parent": null,
                    "next_plans": ["__CHILD__"],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                """
            ).replace("__CHILD__", child_rel).strip()
            parent = self._write_plan(
                root,
                plan_rel,
                status="Ready for Planner",
                handoff_statuses=parked_handoffs,
                context_links="- Code draft(s): `N/A (why=parked umbrella)`",
                meta_json=parked_meta,
            )
            child = self._write_plan(root, child_rel, status="Ready for Coder")
            child.write_text(
                child.read_text(encoding="utf-8")
                + dedent(
                    """\

                    ## Small-model-ready child contract
                    | Field | Value |
                    | --- | --- |
                    | Task outcome | fixture child produces one observable helper result |
                    | Local context bundle | `docs/plans/260418_1005_parked_umbrella.md`, `docs/playbooks/decomposition_wave.md` |
                    | Mutable surfaces | `scripts/fixture.py`, `scripts/test_fixture.py` |
                    | Read-only surfaces | `docs/playbooks/decomposition_wave.md` |
                    | Forbidden scope | model defaults and external runner wrappers |
                    | Inputs from parent/predecessor | `docs/plans/260418_1005_parked_umbrella.md` queue row |
                    | Output to consumer | `docs/plans/260418_1006_parked_child.md` status/evidence for Reviewer |
                    | Acceptance/proof lane | `python -m unittest scripts.test_docs_closeout` |
                    | Stop condition | return to Planner if new helper CLI semantics are needed |
                    | Expected reviewer lane | code |
                    | Runner suitability | small runner OK; fallback to Coder if target bundle expands |
                    | Task size/complexity | small; focused helper change |
                    | Readiness notes | no known clarity gaps |
                    """
                ),
                encoding="utf-8",
            )
            parent.write_text(
                parent.read_text(encoding="utf-8")
                + f"\n## Execution queue\n- Plan: `{child_rel}`\n",
                encoding="utf-8",
            )
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "no_op")
        self.assertEqual(payload["reason_code"], "non_terminal_non_executable_queue_context")
        self.assertEqual(payload["runtime_context"]["closeout_runtime_class"], "parked_umbrella")
        self.assertEqual(payload["runtime_context"]["queue_closeout_kind"], "non_executable_ready")

    def test_terminal_strict_na_parent_with_missing_graph_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260823_1509_terminal_strict_na_parent.md"
            strict_meta = dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                """
            ).strip()
            parent = self._write_plan(
                root,
                plan_rel,
                status="Done",
                context_links="- Code draft(s): `N/A (why=strict terminal fixture)`",
                meta_json=strict_meta,
            )
            parent.write_text(
                "\n".join(
                    line[16:] if line.startswith("                ") else line
                    for line in parent.read_text(encoding="utf-8").splitlines()
                )
                + "\n",
                encoding="utf-8",
            )
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(
            payload["reason_code"],
            "oracle_terminal_admission_blocked:decomposition_children_missing",
        )
        self.assertEqual(payload["final_docs_commit"], "no_op")

    def test_terminal_commit_ready_remains_blocked_until_semantic_commit_materializes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1002_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("commit_ready"),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "semantic_closeout_commit_pending")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")

    def test_final_docs_commit_no_op_when_completed_and_no_docs_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1006_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "no_net_docs_diff")
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["skip_reason"], "no_op")
        self.assertEqual(payload["architect_final_handoff"]["plan_ref"], plan_rel)
        self.assertIn("No Architect handoff required", payload["architect_final_handoff"]["proof_expectation"])

    def test_process_improvement_capture_is_pending_before_general_family_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1014_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_capture_state"], "pending")
        self.assertEqual(payload["process_improvement_capture_reason"], "awaiting_general_docs_finalize_capture")
        self.assertEqual(payload["process_improvement_capture_roles"], [])
        self.assertEqual(
            payload["process_improvement_missing_roles"],
            ["Architect", "Coder", "Planner", "Reviewer"],
        )
        self.assertIn("process_improvement_capture_state=pending", payload["dispatch_context_block"])
        self.assertIn("process_improvement_capture_state=pending", MODULE.render_text(payload))

    def test_process_improvement_capture_clean_noop_after_all_role_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1015_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_capture_state"], "clean_noop")
        self.assertEqual(payload["process_improvement_capture_reason"], "all_roles_clean_noop")
        self.assertEqual(payload["process_improvement_capture_roles"], ["Architect", "Coder", "Planner", "Reviewer"])
        self.assertEqual(payload["process_improvement_backlog_paths"], [])
        self.assertEqual(payload["process_improvement_missing_roles"], [])
        self.assertIn("process_improvement_capture_state=clean_noop", payload["dispatch_context_block"])

    def test_dispatch_family_orders_general_then_followups(self) -> None:
        pairs = [(role, lane) for role, lane, _prompt, _wrapper in MODULE.DISPATCH_FAMILY]
        self.assertEqual(
            pairs,
            [
                ("Architect", "general"),
                ("Coder", "general"),
                ("Planner", "general"),
                ("Reviewer", "general"),
                ("Architect", "followups"),
                ("Coder", "followups"),
                ("Planner", "followups"),
                ("Reviewer", "followups"),
            ],
        )
        self.assertEqual(len(pairs), 8)
        self.assertNotIn(("checkpoint-general-pi", "checkpoint"), pairs)

    def test_default_and_planveyor_dispatch_root_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "planveyor"
            root.mkdir()
            plan_rel = "docs/plans/260418_1018_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            direct = MODULE.classify_docs_closeout(plan_ref=plan_rel, bundle_payload=bundle, root=root)
            default = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                content_profile_id="default",
            )
            planveyor = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                content_profile_id="planveyor",
            )
            expected_prompts = [item[2] for item in MODULE.DISPATCH_FAMILY]
            for payload in (direct, default, planveyor):
                self.assertEqual(
                    [record["prompt_file"] for record in payload["dispatch_family"]],
                    expected_prompts,
                )
                self.assertEqual(
                    {key: value for key, value in payload.items() if key != "dispatch_family"},
                    {key: value for key, value in direct.items() if key != "dispatch_family"},
                )
            public = self._run_public_docs_closeout(root, plan_rel, bundle)
            self.assertEqual(public.returncode, 0, public.stderr)
            payload = json.loads(public.stdout)
            self.assertEqual([record["prompt_file"] for record in payload["dispatch_family"]], expected_prompts)
            self.assertEqual(
                {key: value for key, value in payload.items() if key != "dispatch_family"},
                {key: value for key, value in direct.items() if key != "dispatch_family"},
            )

    def test_planveyor_dispatches_shared_root_family(self) -> None:
        self.assertEqual(MODULE._dispatch_family_for_profile("planveyor"), MODULE.DISPATCH_FAMILY)

    def test_nonpublic_content_profile_blocks_before_source_selection(self) -> None:
        for content_profile_id in ("unknown", "retired_profile"):
            with self.subTest(content_profile_id=content_profile_id), self.assertRaises(MODULE.ProfilePromptError):
                MODULE._dispatch_family_for_profile(content_profile_id)

    def test_target_local_dispatch_requires_engaged_declared_read(self) -> None:
        legacy_context = mock.Mock()
        legacy_context.state = "legacy"
        for context in (None, legacy_context):
            with self.subTest(context=context), self.assertRaises(MODULE.ProfilePromptError):
                MODULE._dispatch_family_for_profile("target-local", context=context)

        engaged_context = mock.Mock()
        engaged_context.state = "engaged"
        consumer_root = Path("/fixture/consumer")

        def declared_read(context: object, prompt_file: str, purpose: str) -> Path:
            self.assertIs(context, engaged_context)
            self.assertEqual(purpose, "docs-closeout dispatch prompt")
            return consumer_root / prompt_file

        with mock.patch.object(MODULE, "require_declared_read", side_effect=declared_read) as reader:
            selected = MODULE._dispatch_family_for_profile("target-local", context=engaged_context)
        self.assertEqual(
            [prompt_file for _role, _lane, prompt_file, _wrapper in selected],
            [str(consumer_root / item[2]) for item in MODULE.DISPATCH_FAMILY],
        )
        self.assertEqual(
            reader.call_args_list,
            [
                mock.call(engaged_context, prompt_file, "docs-closeout dispatch prompt")
                for _role, _lane, prompt_file, _wrapper in MODULE.DISPATCH_FAMILY
            ],
        )
        with self.assertRaises(MODULE.ProfilePromptError):
            MODULE._dispatch_family_for_profile("default", context=engaged_context)

    def test_terminal_fast_path_eligible_for_clean_noop_materialized_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1020_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        fast_path = payload["terminal_closeout_fast_path"]
        self.assertTrue(fast_path["eligible"])
        self.assertEqual(fast_path["schema"], "terminal_closeout_fast_path.v1")
        self.assertEqual(fast_path["reason"], "clean_terminal_materialized_noop")
        self.assertEqual(fast_path["missing_or_dirty_preconditions"], [])
        self.assertIn("Coder:followups", fast_path["skipped_lanes"])
        self.assertIn("Architect:final_docs_handoff", fast_path["skipped_lanes"])
        self.assertEqual(fast_path["fallback_lanes"], [])
        self.assertEqual(payload["followups_reconciliation"]["state"], "clean_noop")
        self.assertIn("terminal_closeout_fast_path_eligible=true", payload["dispatch_context_block"])
        self.assertIn("terminal_closeout_fast_path_eligible=true", MODULE.render_text(payload))

    def test_terminal_fast_path_eligible_for_explicit_landed_materialized_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1021_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel, state_by_role={"Coder": "materialized"})
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized", final_docs_commit="landed"),
                root=root,
            )

        self.assertEqual(payload["final_docs_commit"], "landed")
        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])
        self.assertEqual(payload["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"], [])

    def test_terminal_fast_path_fails_closed_for_pending_or_blocked_process_improvements(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1022_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            pending = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self._assert_fast_path_blocked(pending, "pi_capture_clean")
        self.assertEqual(pending["process_improvement_capture_state"], "pending")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1023_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel, state_by_role={"Reviewer": "blocked"})
            self._init_git(root)
            self._commit_all(root)

            blocked = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self._assert_fast_path_blocked(blocked, "pi_capture_clean")
        self.assertEqual(blocked["process_improvement_capture_state"], "blocked")

    def test_blocked_followups_capture_cannot_be_misread_as_green_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260801_1734_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            before_family = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
            )
            cycle_id = str(MODULE.followups_capture.begin_cycle(root, plan_rel, before_family)["capture_cycle_id"])

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        handoff = payload["architect_final_handoff"]
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "followup_capture_blocked")
        self.assertEqual(payload["blocked_docs_delta_paths"], [])
        self.assertFalse(handoff["required"])
        self.assertEqual(handoff["skip_reason"], "blocked")
        self.assertEqual(handoff["followups_staging_expectations"], [])
        self.assertIn("Blocked capture is not a green no-op", handoff["proof_expectation"])
        self.assertFalse(payload["terminal_closeout_fast_path"]["eligible"])

    def test_blocked_followups_capture_overrides_accepted_red_noop_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260801_1734_accepted_red_fixture.md"
            plan = self._write_plan(root, plan_rel, status="Superseded")
            self._init_git(root)
            self._commit_all(root)
            ordinary = MODULE.plan_status_oracle.oracle_result(plan)
            review_rel = "docs/code_reviews/260801_1734_accepted_red_fixture.md"
            successor_rel = "docs/plans/260801_1734_accepted_red_successor.md"
            accepted = replace(
                ordinary,
                terminal_disposition="accepted_red_supersession",
                delivery_green=False,
                staging_policy="forbidden",
                durable_capture_required=True,
                accepted_red_successor_plan=successor_rel,
                accepted_red_historical_review=review_rel,
                accepted_red_review_bundle_sha256="a" * 64,
                terminal_disposition_reason="fixture",
            )
            bundle = {
                **self._bundle_payload("accepted_red_recovered"),
                "terminal_disposition": "accepted_red_supersession",
                "delivery_green": False,
                "staging_policy": "forbidden",
                "durable_capture_required": True,
                "durable_capture_state": "cleanup_recorded",
                "active_checkout_state": "clean",
                "recovery_state": "completed",
                "recovery_ref": "refs/planveyor/rejected-baselines/fixture/" + ("a" * 64),
                "recovery_manifest_path": ".planveyor/rejected-baselines/fixture/manifest.json",
                "recovery_cleanup_path": ".planveyor/rejected-baselines/fixture/cleanup.json",
                "recovery_plan": "docs/plans/260801_1734_accepted_red_recovery.md",
                "recovery_code_draft": (
                    "docs/code_drafts/260801_1734_accepted_red_recovery__code_draft.md"
                ),
                "recovery_targets": ["docs/rejected-overlap.md"],
                "successor_plan": successor_rel,
                "review_bundle_sha256": "a" * 64,
                "capture_commit": "b" * 40,
                "cleanup_commit": "c" * 40,
                "captured_parent": "d" * 40,
            }
            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                before_capture = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=bundle,
                    root=root,
                )
                cycle_id = str(
                    MODULE.followups_capture.begin_cycle(root, plan_rel, before_capture)["capture_cycle_id"]
                )
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=bundle,
                    root=root,
                    followups_capture_cycle_id=cycle_id,
                )

        handoff = payload["architect_final_handoff"]
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "followup_capture_blocked")
        self.assertFalse(handoff["required"])
        self.assertEqual(handoff["skip_reason"], "blocked")
        self.assertEqual(handoff["followups_staging_expectations"], [])
        self.assertIn("Blocked capture is not a green no-op", handoff["proof_expectation"])
        self.assertFalse(payload["terminal_closeout_fast_path"]["eligible"])

    def test_accepted_red_current_cycle_owned_tail_requires_exact_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            ordinary_rel = "docs/followups/260801_1303_owned.md"
            foreign_rel = "docs/code_drafts/260801_1303_foreign.md"
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
            )
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(source_rel)
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._commit_all(root, "prepare process-improvement baseline")
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            accepted = self._accepted_red_oracle(root / source_rel, receipt)

            def materialize_pi(cycle_id: str) -> None:
                before_pi = MODULE.followups_capture.snapshot_process_improvement_data_files(
                    root,
                    source_rel,
                )
                self._write_pi_backlog(
                    root,
                    backlog_rel,
                    source_ref=source_rel,
                    entries=[{"status": "open"}],
                )
                COLLECT.rebuild_derived_surfaces(root)
                after_pi = MODULE.followups_capture.snapshot_process_improvement_data_files(
                    root,
                    source_rel,
                )
                self._write_capture_receipts(
                    root,
                    source_rel,
                    state_by_role={"Coder": "materialized"},
                    backlog_paths=[backlog_rel],
                    followups_capture_cycle_id=cycle_id,
                    pi_chain_by_role={
                        "Architect": (before_pi, before_pi),
                        "Coder": (before_pi, after_pi),
                        "Planner": (after_pi, after_pi),
                        "Reviewer": (after_pi, after_pi),
                    },
                )

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                cycle_id = self._finalize_followups_cycle(
                    root,
                    source_rel,
                    bundle,
                    created_rel=ordinary_rel,
                    prepare_general=materialize_pi,
                )
                foreign = root / foreign_rel
                foreign.parent.mkdir(parents=True, exist_ok=True)
                foreign.write_text("foreign\n", encoding="utf-8")
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                    followups_capture_cycle_id=cycle_id,
                )

        expected_paths = sorted(
            [
                ordinary_rel,
                backlog_rel,
                "docs/process_improvements/deferred.md",
                "docs/process_improvements/index.md",
                "docs/process_improvements/promotion_surface.md",
            ]
        )
        expectations = payload["architect_final_handoff"]["followups_staging_expectations"]
        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "materialized")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], expected_paths)
        self.assertEqual(payload["foreign_docs_delta_paths"], [foreign_rel])
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(payload["final_docs_diff_paths"], expected_paths)
        self.assertEqual([item["path"] for item in expectations], expected_paths)
        self.assertTrue(payload["architect_final_handoff"]["required"])
        self._assert_fast_path_blocked(payload, "final_docs_commit_clean")
        self.assertNotIn(receipt["recovery_targets"][0], payload["final_docs_diff_paths"])

    def test_accepted_red_current_cycle_no_owned_tail_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
            )
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            accepted = self._accepted_red_oracle(root / source_rel, receipt)

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                cycle_id = self._finalize_followups_cycle(root, source_rel, bundle)
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                    followups_capture_cycle_id=cycle_id,
                )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "accepted_red_evidence_ref_materialized",
        )
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])

    def test_accepted_red_current_cycle_no_owned_tail_preserves_landed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
            )
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            bundle["final_docs_commit"] = "landed"
            accepted = self._accepted_red_oracle(root / source_rel, receipt)

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                cycle_id = self._finalize_followups_cycle(root, source_rel, bundle)
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                    followups_capture_cycle_id=cycle_id,
                )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["final_docs_commit"], "landed")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "accepted_red_routing_docs_landed",
        )
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])

    def test_accepted_red_current_cycle_post_commit_readback_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            owned_rel = "docs/followups/260801_1303_owned.md"
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel="docs/recovery-overlap.md",
            )
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            accepted = self._accepted_red_oracle(root / source_rel, receipt)

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                cycle_id = self._finalize_followups_cycle(
                    root,
                    source_rel,
                    bundle,
                    created_rel=owned_rel,
                )
                self._git(root, "add", owned_rel)
                self._git(root, "commit", "-m", "land owned followup")
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                    followups_capture_cycle_id=cycle_id,
                )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "accepted_red_evidence_ref_materialized",
        )
        self.assertFalse(payload["architect_final_handoff"]["required"])

    def test_blocked_mixed_capture_clears_staging_expectations(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260801_1734_mixed_capture_fixture.md"
            ordinary_rel = "docs/followups/260801_1734_mixed_capture.md"
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(plan_rel)
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")

            def materialize_pi_tail(role: str, _cycle_id: str) -> None:
                if role != "Coder":
                    return
                self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
                COLLECT.rebuild_derived_surfaces(root)

            cycle_id = self._finalize_followups_cycle(
                root,
                plan_rel,
                bundle,
                created_rel=ordinary_rel,
                before_finalize=materialize_pi_tail,
            )
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "blocked"},
                reason_by_role={"Coder": "collector_blocked"},
                backlog_paths=[backlog_rel],
                followups_capture_cycle_id=cycle_id,
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        handoff = payload["architect_final_handoff"]
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertEqual(payload["process_improvement_capture_state"], "blocked")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [])
        self.assertIn(backlog_rel, payload["blocked_docs_delta_paths"])
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "followup_capture_blocked")
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(handoff["required"])
        self.assertEqual(handoff["skip_reason"], "blocked")
        self.assertEqual(handoff["followups_staging_expectations"], [])
        self.assertIn("Blocked capture is not a green no-op", handoff["proof_expectation"])
        self.assertFalse(payload["terminal_closeout_fast_path"]["eligible"])

    def test_terminal_fast_path_fails_closed_for_final_docs_commit_required_and_protected_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1024_fixture.md"
            protected_rel = "docs/tools/prompts/fixture_prompt.md"
            self._write_plan(root, plan_rel, status="Done")
            protected_path = root / protected_rel
            protected_path.parent.mkdir(parents=True, exist_ok=True)
            protected_path.write_text("before\n", encoding="utf-8")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)
            protected_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(payload["protected_docs_delta_paths"], [protected_rel])
        self._assert_fast_path_blocked(payload, "final_docs_commit_clean")
        self._assert_fast_path_blocked(payload, "protected_docs_clean")

    def test_terminal_fast_path_fails_closed_for_open_or_unknown_followups_proof(self) -> None:
        open_followup_meta = dedent(
            """\
            {
              "plan_meta": {
                "cluster": "process",
                "tags": [],
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [
                  {"cluster": "process", "summary": "Needs another terminal receipt follow-up.", "plan": null}
                ],
                "canon_updates": [],
                "machine_authority_decision": {
                  "schema_version": "machine_authority_decision.v1",
                  "applicability": "not_applicable",
                  "reason_code": "docs_or_tests_only"
                }
              }
            }
            """
        ).strip()
        unknown_followup_meta = dedent(
            """\
            {
              "plan_meta": {
                "cluster": "process",
                "tags": [],
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "canon_updates": [],
                "machine_authority_decision": {
                  "schema_version": "machine_authority_decision.v1",
                  "applicability": "not_applicable",
                  "reason_code": "docs_or_tests_only"
                }
              }
            }
            """
        ).strip()
        for plan_rel, meta_json, expected_state in (
            ("docs/plans/260418_1025_open_followup.md", open_followup_meta, "open"),
            ("docs/plans/260418_1026_unknown_followup.md", unknown_followup_meta, "unknown"),
        ):
            with self.subTest(expected_state=expected_state), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_plan(root, plan_rel, status="Done", meta_json=meta_json)
                self._write_capture_receipts(root, plan_rel)
                self._init_git(root)
                self._commit_all(root)

                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload("already_materialized"),
                    root=root,
                )

            self.assertEqual(payload["followups_reconciliation"]["state"], expected_state)
            self._assert_fast_path_blocked(payload, "followups_clean")

    def test_open_followups_reconciliation_items_include_actionable_repair_readback(self) -> None:
        meta_json = dedent(
            """\
            {
              "plan_meta": {
                "cluster": "process",
                "tags": [],
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [
                  {
                    "cluster": "process",
                    "summary": "Operator secret storage standard remains separate.",
                    "plan": null
                  }
                ],
                "canon_updates": [],
                "machine_authority_decision": {
                  "schema_version": "machine_authority_decision.v1",
                  "applicability": "not_applicable",
                  "reason_code": "docs_or_tests_only"
                }
              }
            }
            """
        ).strip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1031_open_followup_readback.md"
            self._write_plan(root, plan_rel, status="Done", meta_json=meta_json)
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        followups = payload["followups_reconciliation"]
        self.assertEqual(followups["state"], "open")
        self.assertEqual(followups["reason"], "open_plan_meta_followups_out")
        self.assertEqual(followups["proof_host"], f"{plan_rel}::plan_meta.followups_out")
        self.assertEqual(len(followups["open_items"]), 1)
        item = followups["open_items"][0]
        self.assertEqual(item["index"], 1)
        self.assertEqual(item["row_ref"], "plan_meta.followups_out[1]")
        self.assertEqual(item["current_plan_value"], "null")
        self.assertEqual(item["summary"], "Operator secret storage standard remains separate.")
        self.assertIn("source_ref", " ".join(item["accepted_repair_shapes"]))
        self.assertIn("followups_reconciliation_open_item[1]=row_ref=plan_meta.followups_out[1]", payload["dispatch_context_block"])
        self.assertIn("repair_shapes=", payload["dispatch_context_block"])
        self.assertIn("followups_reconciliation_proof_host=", MODULE.render_text(payload))
        self._assert_fast_path_blocked(payload, "followups_clean")

    def test_row_local_terminal_followup_disposition_is_clean_noop(self) -> None:
        meta_json = dedent(
            """\
            {
              "plan_meta": {
                "cluster": "process",
                "tags": [],
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [
                  {
                    "cluster": "process",
                    "summary": "Operator secret storage standard remains separate.",
                    "plan": null,
                    "status": "handled",
                    "disposition": "already tracked in followups backlog",
                    "source_ref": "docs/followups/260418_1032_followups_memory_architect.md",
                    "reason": "same requirement already tracked as ordinary lifecycle follow-up"
                  }
                ],
                "canon_updates": [],
                "machine_authority_decision": {
                  "schema_version": "machine_authority_decision.v1",
                  "applicability": "not_applicable",
                  "reason_code": "docs_or_tests_only"
                }
              }
            }
            """
        ).strip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1032_handled_followup.md"
            self._write_plan(root, plan_rel, status="Done", meta_json=meta_json)
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        followups = payload["followups_reconciliation"]
        self.assertEqual(followups["state"], "clean_noop")
        self.assertEqual(followups["open_items"], [])
        self.assertEqual(followups["closed_or_promoted_items"][0]["summary"], "Operator secret storage standard remains separate.")
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])
        self.assertEqual(payload["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"], [])

    def test_process_improvement_materialized_does_not_close_open_followups_out(self) -> None:
        meta_json = dedent(
            """\
            {
              "plan_meta": {
                "cluster": "process",
                "tags": [],
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [
                  {
                    "cluster": "process",
                    "summary": "Ordinary follow-up still needs row-local fate.",
                    "plan": null
                  }
                ],
                "machine_authority_decision": {
                  "schema_version": "machine_authority_decision.v1",
                  "applicability": "not_applicable",
                  "reason_code": "docs_or_tests_only"
                },
                "canon_updates": []
              }
            }
            """
        ).strip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1033_pi_materialized_followup_open.md"
            backlog_rel = "docs/process_improvements/260418_1033_fixture__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done", meta_json=meta_json)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                reason_by_role={"Coder": "structured_suggestions_materialized"},
                backlog_paths=[backlog_rel],
            )
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["process_improvement_backlog_paths"], [backlog_rel])
        self.assertEqual(payload["followups_reconciliation"]["state"], "open")
        self.assertFalse(payload["terminal_closeout_fast_path"]["eligible"])
        self._assert_fast_path_blocked(payload, "followups_clean")
        self.assertNotIn("pi_capture_clean", payload["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"])
        self.assertIn("process_improvement_capture_state=materialized", payload["dispatch_context_block"])
        self.assertIn("followups_reconciliation_state=open", payload["dispatch_context_block"])

    def test_terminal_fast_path_fails_closed_for_non_completed_or_invalid_bundle(self) -> None:
        cases = (
            (
                "docs/plans/260418_1027_non_terminal.md",
                "Ready for Review",
                self._bundle_payload("already_materialized"),
                "docs_closeout_completed",
            ),
            (
                "docs/plans/260418_1028_invalid_bundle.md",
                "Done",
                self._bundle_payload("already_materialized", bundle_ok=False, errors=["fixture bundle error"]),
                "bundle_materialized",
            ),
            (
                "docs/plans/260418_1029_commit_ready.md",
                "Done",
                self._bundle_payload("commit_ready"),
                "semantic_materialized",
            ),
        )
        for plan_rel, status, bundle_payload, precondition in cases:
            with self.subTest(precondition=precondition), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_plan(root, plan_rel, status=status)
                self._write_capture_receipts(root, plan_rel)
                self._init_git(root)
                self._commit_all(root)

                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=bundle_payload,
                    root=root,
                )

            self._assert_fast_path_blocked(payload, precondition)

    def test_terminal_fast_path_fails_closed_for_live_blocker_runtime_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1030_fixture.md"
            review_rel = "docs/code_reviews/260418_1030_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                dedent(
                    """\
                    # Review

                    - Loop signal: `yes`
                    - Root cause class: `same-contract reroute`
                    - Next owner: `Coder`
                    - Blocker IDs considered: `docs/code_reviews/260418_1030_fixture.md#B1`
                    """
                ),
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self._assert_fast_path_blocked(payload, "runtime_context_clean")
        self.assertIn("loop_detected=yes", payload["terminal_closeout_fast_path"]["dirty_runtime_signals"])
        self.assertIn("latest_blocker_ids=docs/code_reviews/260418_1030_fixture.md#B1", payload["terminal_closeout_fast_path"]["dirty_runtime_signals"])

    def test_terminal_fast_path_fails_closed_for_red_review_artifact_without_optional_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1031_fixture.md"
            review_rel = "docs/code_reviews/260418_1031_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                dedent(
                    """\
                    # Review

                    **Status:** ❌ S1 blocker(ы)

                    ## S1 Blocker
                    ### B1
                    - Blocker ID: `B1`
                    - Current state: `live`
                    - Required closure: fixture blocker.
                    """
                ),
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self._assert_fast_path_blocked(payload, "runtime_context_clean")
        self.assertEqual(payload["runtime_context"]["review_blocker_status"], "blocking")
        self.assertEqual(payload["runtime_context"]["review_blocker_sources"], [review_rel])
        self.assertEqual(payload["runtime_context"]["latest_blocker_ids"], [f"{review_rel}#B1"])
        self.assertIn("review_blocker_status=blocking", payload["terminal_closeout_fast_path"]["dirty_runtime_signals"])
        self.assertIn(f"latest_blocker_ids={review_rel}#B1", payload["terminal_closeout_fast_path"]["dirty_runtime_signals"])

    def test_green_closed_only_review_excludes_historical_ids_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260804_1558_fixture.md"
            review_rel = "docs/code_reviews/260804_1558_fixture.md"
            self._write_plan(
                root,
                plan_rel,
                status="Done",
                review_artifact=review_rel,
                evidence_tail=dedent(
                    """\
                    - Root cause class: `independent-plan-signal`
                    - Extraordinary action: `retain independent producer`
                    - Next owner: `Planner`
                    - Blocker IDs considered: `B9`
                    """
                ).strip(),
            )
            self._write_review(
                root,
                review_rel,
                dedent(
                    f"""\
                    # Review

                    **Status:** ✅ OK

                    ## S1 Blocker

                    ### B1) historical fix
                    - Blocker ID: `B1`
                    - Current state: `historical-fixed`

                    ### B2) scoped supersession
                    - Blocker ID: `B2`
                    - Current state: `superseded`

                    ## Evidence
                    - Root cause class: `historical review value`
                    - Extraordinary action: `historical action`
                    - Next owner: `Coder`
                    - Blocker IDs considered: `{review_rel}#B1`, `{review_rel}#B2`
                    """
                ),
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["review_blocker_status"], "none")
        self.assertEqual(runtime["review_blocker_sources"], [])
        self.assertEqual(runtime["review_blocker_ids"], [])
        self.assertEqual(runtime["latest_blocker_ids"], ["B9"])
        self.assertEqual(runtime["root_cause_class"], "independent-plan-signal")
        self.assertEqual(runtime["extraordinary_action"], "retain independent producer")
        self.assertEqual(runtime["next_owner"], "Planner")
        self.assertEqual(runtime["root_cause_class_source"], plan_rel)
        self.assertEqual(runtime["extraordinary_action_source"], plan_rel)
        self.assertEqual(runtime["next_owner_source"], plan_rel)
        self.assertEqual(runtime["blocker_ids_source"], plan_rel)
        self.assertIsInstance(runtime["review_blocker_sources"], list)
        self.assertIsInstance(runtime["review_blocker_ids"], list)

    def test_s1_blocker_records_are_exact_and_fail_closed(self) -> None:
        review_rel = "docs/code_reviews/260804_1558_fixture.md"
        cases = (
            (
                "green_closed_only",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ### B2
                - Blocker ID: `B2`
                - Current state: `superseded`
                - Classification: `superseded_by_scope_contraction`
                """,
                [],
                True,
            ),
            (
                "green_closed_only_with_descriptive_prose",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Required closure: Current state history is retained as descriptive context.
                """,
                [],
                True,
            ),
            (
                "green_empty",
                "**Status:** ✅ OK",
                "",
                [],
                False,
            ),
            (
                "green_explicit_na",
                "**Status:** ✅ OK",
                "N/A (why=no canonical B records)",
                [],
                False,
            ),
            (
                "green_bullet_explicit_na",
                "**Status:** ✅ OK",
                "- N/A (why=no canonical B records)",
                [],
                False,
            ),
            (
                "green_russian_absent",
                "**Status:** ✅ OK",
                "Отсутствуют",
                [],
                False,
            ),
            (
                "green_russian_annotated_j1",
                "**Status:** ✅ OK",
                "Отсутствуют (green verdict; канонические `B<N>` не открывались).",
                [],
                False,
            ),
            (
                "green_bullet_russian_none",
                "**Status:** ✅ OK",
                "- Нет.",
                [],
                False,
            ),
            (
                "green_bullet_russian_not_detected",
                "**Status:** ✅ OK",
                "* Не выявлено.",
                [],
                False,
            ),
            (
                "russian_absent_near_match",
                "**Status:** ✅ OK",
                "Отсутствуют, кроме B1",
                [],
                False,
            ),
            (
                "russian_none_near_match",
                "**Status:** ✅ OK",
                "Нет current S1",
                [],
                False,
            ),
            (
                "russian_not_detected_near_match",
                "**Status:** ✅ OK",
                "Не выявлено: требуется проверка",
                [],
                False,
            ),
            (
                "russian_none_backticked_alias",
                "**Status:** ✅ OK",
                "`Нет`",
                [],
                False,
            ),
            (
                "russian_none_backticked_dot_alias",
                "**Status:** ✅ OK",
                "`Нет.`",
                [],
                False,
            ),
            (
                "russian_none_non_markdown_bullet",
                "**Status:** ✅ OK",
                "-Нет.",
                [],
                False,
            ),
            (
                "russian_sentinel_plus_unknown_prose",
                "**Status:** ✅ OK",
                "Нет.\nТребуется дополнительная проверка.",
                [],
                False,
            ),
            (
                "red_russian_none",
                "**Status:** ❌ S1 blocker(ы)",
                "Нет.",
                [],
                False,
            ),
            (
                "missing_header_russian_none",
                "",
                "Не выявлено.",
                [],
                False,
            ),
            (
                "noncanonical_header_russian_none",
                "**Status:** ✅ OK, no blockers",
                "Отсутствуют.",
                [],
                False,
            ),
            (
                "duplicate_s1_sections_with_allowed_sentinels",
                "**Status:** ✅ OK",
                "Нет.\n\n## S1 Blocker\n\nОтсутствуют.",
                [],
                False,
            ),
            (
                "russian_sentinel_plus_open_record",
                "**Status:** ✅ OK",
                """\
                Нет.

                ### B1
                - Blocker ID: `B1`
                - Current state: `open`
                """,
                ["B1"],
                False,
            ),
            (
                "russian_sentinel_plus_malformed_record",
                "**Status:** ✅ OK",
                "Нет.\n\n### B1\n- Blocker ID: `B1`\n- Current state: `historical-fixed\n",
                ["B1"],
                False,
            ),
            (
                "russian_sentinel_plus_duplicate_record",
                "**Status:** ✅ OK",
                """\
                Нет.

                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ### B1
                - Blocker ID: `B1`
                - Current state: `superseded`
                """,
                ["B1"],
                False,
            ),
            (
                "russian_sentinel_plus_mismatched_record",
                "**Status:** ✅ OK",
                """\
                Нет.

                ### B1
                - Blocker ID: `B2`
                - Current state: `historical-fixed`
                """,
                ["B1", "B2"],
                False,
            ),
            (
                "russian_sentinel_plus_unknown_prose_before_closed_record",
                "**Status:** ✅ OK",
                """\
                Нет.
                Неизвестная standalone-строка.

                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                """,
                [],
                False,
            ),
            (
                "green_mixed",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ### B2
                - Blocker ID: `B2`
                - Current state: `open`
                """,
                ["B2"],
                False,
            ),
            (
                "duplicate_s1_sections_hide_open_record",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ## S1 Blocker

                ### B2
                - Blocker ID: `B2`
                - Current state: `open`
                """,
                ["B2"],
                False,
            ),
            (
                "duplicate_s1_sections_hide_malformed_record",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ## S1 Blocker

                ### B2
                - Blocker ID: `B2`
                - Current state: `fixed-ish`
                """,
                ["B2"],
                False,
            ),
            (
                "red_open",
                "**Status:** ❌ S1 blocker(ы)",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `open`
                """,
                ["B1"],
                False,
            ),
            (
                "red_closed_only",
                "**Status:** ❌ S1 blocker(ы)",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                """,
                [],
                False,
            ),
            (
                "missing_header",
                "",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                """,
                [],
                False,
            ),
            (
                "noncanonical_green_status",
                "**Status:** ✅ OK, historical-only",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                """,
                [],
                False,
            ),
            (
                "unknown_alias",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `superseded_by_scope_contraction`
                """,
                ["B1"],
                False,
            ),
            (
                "legacy_live_state",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `live`
                """,
                ["B1"],
                False,
            ),
            (
                "malformed_backticks",
                "**Status:** ✅ OK",
                "### B1\n- Blocker ID: `B1`\n- Current state: `historical-fixed\n",
                ["B1"],
                False,
            ),
            (
                "malformed_blocker_id_dangling_backtick",
                "**Status:** ✅ OK",
                "### B1\n- Blocker ID: `B1\n- Current state: `historical-fixed`\n",
                ["B1"],
                False,
            ),
            (
                "malformed_blocker_id_trailing_token",
                "**Status:** ✅ OK",
                "### B1\n- Blocker ID: B1 trailing\n- Current state: `historical-fixed`\n",
                ["B1"],
                False,
            ),
            (
                "missing_state",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                """,
                ["B1"],
                False,
            ),
            (
                "duplicate_blocker_id",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                """,
                ["B1"],
                False,
            ),
            (
                "duplicate_state",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state: `superseded`
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_malformed_competing_state_prefix",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state open
                """,
                ["B1"],
                False,
            ),
            (
                "open_record_with_malformed_competing_state_prefix",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `open`
                - Current state historical-fixed
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_malformed_competing_blocker_id_prefix",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID B1
                """,
                ["B1"],
                False,
            ),
            (
                "open_record_with_malformed_competing_blocker_id_prefix",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `open`
                - Blocker ID B1
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_equals_state_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state=VALUE
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_attached_backtick_state_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state`open`
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_equals_blocker_id_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID=B1
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_attached_backtick_blocker_id_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID`B1`
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_slash_state_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state/VALUE
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_semicolon_state_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state;VALUE
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_closing_bracket_state_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Current state]VALUE
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_slash_blocker_id_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID/B1
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_semicolon_blocker_id_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID;B1
                """,
                ["B1"],
                False,
            ),
            (
                "closed_record_with_closing_bracket_blocker_id_delimiter",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`
                - Blocker ID]B1
                """,
                ["B1"],
                False,
            ),
            (
                "mismatched_id",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B2`
                - Current state: `historical-fixed`
                """,
                ["B1", "B2"],
                False,
            ),
            (
                "duplicate_record",
                "**Status:** ✅ OK",
                """\
                ### B1
                - Blocker ID: `B1`
                - Current state: `historical-fixed`

                ### B1
                - Blocker ID: `B1`
                - Current state: `superseded`
                """,
                ["B1"],
                False,
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / review_rel
            for name, status_line, records, expected_ids, expected_closed_only in cases:
                with self.subTest(name=name):
                    header = f"{status_line}\n\n" if status_line else ""
                    context, closed_only_sources = MODULE._review_blocker_context(
                        [
                            (
                                source_path,
                                f"# Review\n\n{header}## S1 Blocker\n\n{dedent(records)}",
                            )
                        ],
                        root,
                    )
                    expected_blocking = name not in {
                        "green_closed_only",
                        "green_closed_only_with_descriptive_prose",
                        "green_empty",
                        "green_explicit_na",
                        "green_bullet_explicit_na",
                        "green_russian_absent",
                        "green_russian_annotated_j1",
                        "green_bullet_russian_none",
                        "green_bullet_russian_not_detected",
                    }
                    self.assertEqual(
                        context["review_blocker_status"],
                        "blocking" if expected_blocking else "none",
                    )
                    self.assertEqual(
                        context["review_blocker_sources"],
                        [review_rel] if expected_blocking else [],
                    )
                    self.assertEqual(
                        context["review_blocker_ids"],
                        [f"{review_rel}#{blocker_id}" for blocker_id in expected_ids],
                    )
                    self.assertEqual(
                        source_path.resolve() in closed_only_sources,
                        expected_closed_only,
                    )

    def test_j1_annotated_s1_none_sentinel_does_not_create_review_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260817_1045_j1_shape.md"
            review_rel = "docs/code_reviews/260817_1045_j1_shape.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                dedent(
                    """\
                    # Review

                    **Status:** ✅ OK

                    ## S1 Blocker

                    Отсутствуют (green verdict; канонические `B<N>` не открывались).
                    """
                ),
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["review_blocker_status"], "none")
        self.assertEqual(runtime["review_blocker_sources"], [])
        self.assertEqual(runtime["review_blocker_ids"], [])
        self.assertNotIn(
            "review_blocker_status=blocking",
            payload["terminal_closeout_fast_path"]["dirty_runtime_signals"],
        )

    def test_body_review_status_does_not_override_preamble_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1032_fixture.md"
            review_rel = "docs/code_reviews/260418_1032_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                dedent(
                    """\
                    # Review

                    **Status:** ✅ OK

                    ОК: current review is green.

                    ```text
                    **Status:** ❌ S1 blocker(ы)
                    ```
                    """
                ),
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["runtime_context"]["review_blocker_status"], "none")
        self.assertEqual(payload["runtime_context"]["review_blocker_sources"], [])

    def test_duplicate_preamble_review_status_blocks_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1033_fixture.md"
            review_rel = "docs/code_reviews/260418_1033_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                "# Review\n\n**Status:** ✅ OK\n**Status :** ❌ S1 blocker(ы)\n",
            )
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["runtime_context"]["review_blocker_status"], "blocking")
        self.assertEqual(payload["runtime_context"]["review_blocker_sources"], [review_rel])

    def test_noncanonical_single_review_status_blocks_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1034_fixture.md"
            review_rel = "docs/code_reviews/260418_1034_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(root, review_rel, "# Review\n\n**Status :** ✅ OK\n")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["runtime_context"]["review_blocker_status"], "blocking")
        self.assertEqual(payload["runtime_context"]["review_blocker_sources"], [review_rel])

    def test_process_improvement_capture_materialized_and_blocked_receipts_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1016_fixture.md"
            backlog_rel = "docs/process_improvements/260418_1016_fixture__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                reason_by_role={"Coder": "structured_suggestions_materialized"},
                backlog_paths=[backlog_rel],
            )
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["process_improvement_capture_reason"], "process_improvements_materialized")
        self.assertEqual(payload["process_improvement_backlog_paths"], [backlog_rel])
        self.assertIn(f"process_improvement_backlog_paths={backlog_rel}", payload["dispatch_context_block"])

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1017_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Reviewer": "blocked"},
                reason_by_role={"Reviewer": "collector_error"},
            )
            self._init_git(root)
            self._commit_all(root)

            blocked = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(blocked["process_improvement_capture_state"], "blocked")
        self.assertEqual(blocked["process_improvement_capture_reason"], "collector_error")
        self.assertIn("process_improvement_capture_state=blocked", blocked["dispatch_context_block"])

    def test_process_improvement_capture_stale_blocked_receipt_requires_fresh_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260624_1441_process_planner_coder_handoff_digest_analysis.md"
            backlog_rel = "docs/process_improvements/260624_1441_process_planner_coder_handoff_digest_analysis__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Architect": "blocked"},
                reason_by_role={"Architect": "collector_error"},
            )
            self._init_git(root)
            self._commit_all(root)

            blocked = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

            self.assertEqual(blocked["process_improvement_capture_state"], "blocked")
            self.assertEqual(blocked["process_improvement_capture_reason"], "collector_error")
            self._assert_fast_path_blocked(blocked, "pi_capture_clean")

            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Architect": "materialized"},
                reason_by_role={"Architect": "structured_suggestions_materialized"},
                backlog_paths=[backlog_rel],
            )

            replaced = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(replaced["process_improvement_capture_state"], "materialized")
        self.assertEqual(replaced["process_improvement_capture_reason"], "process_improvements_materialized")
        self.assertEqual(replaced["process_improvement_backlog_paths"], [backlog_rel])
        self.assertIn("process_improvement_capture_state=materialized", replaced["dispatch_context_block"])

    def test_staged_empty_same_plan_process_improvement_tail_blocks_without_capture_stage_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            backlog_rel = "docs/process_improvements/260704_2043_process_docs_closeout_post_done_pi_tail_handoff__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)

            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                reason_by_role={"Coder": "structured_suggestions_materialized"},
                backlog_paths=[backlog_rel],
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("staged_empty"),
                root=root,
            )

        expected_paths = [
            backlog_rel,
            "docs/process_improvements/deferred.md",
            "docs/process_improvements/index.md",
            "docs/process_improvements/promotion_surface.md",
        ]
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["semantic_closeout_kind"], "staged_empty")
        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], expected_paths)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertEqual(payload["protected_docs_delta_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["final_docs_diff_paths"], [])
        self.assertEqual(payload["architect_final_handoff"]["skip_reason"], "blocked")
        self.assertEqual(payload["architect_final_handoff"]["followups_staging_expectations"], [])
        self.assertIn("docs_closeout_state=blocked", payload["dispatch_context_block"])
        self.assertIn(
            f"docs_closeout_reason={MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON}",
            payload["dispatch_context_block"],
        )
        self._assert_fast_path_blocked(payload, "docs_closeout_completed")

    def test_no_cycle_historical_reviewer_assets_are_foreign_only_and_never_commit_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1909_process_terminal_memory_finalize_canon_scope_expiry_guard.md"
            historical_paths = [
                "docs/code_reviews/assets/260729_1909/reviewer_code_risk_T190258.json",
                "docs/code_reviews/assets/260729_1909/reviewer_code_risk_T194820.json",
            ]
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)
            for rel_path in historical_paths:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("historical support bytes\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(payload["foreign_docs_delta_paths"], historical_paths)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["followups_staging_expectations"], [])

    def test_no_cycle_mixed_bundle_support_blocks_without_exact_stage_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1909_process_terminal_memory_finalize_canon_scope_expiry_guard.md"
            owned_rel = "docs/code_reviews/assets/260729_1909/reviewer_code_risk_T204740.json"
            historical_paths = [
                "docs/code_reviews/assets/260729_1909/reviewer_code_risk_T190258.json",
                "docs/code_reviews/assets/260729_1909/reviewer_code_risk_T194820.json",
            ]
            self._write_plan(root, plan_rel, status="Done")
            owned_path = root / owned_rel
            owned_path.parent.mkdir(parents=True, exist_ok=True)
            owned_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            owned_path.write_text("current support bytes\n", encoding="utf-8")
            for rel_path in historical_paths:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("historical support bytes\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized", bundle_paths=[owned_rel]),
                root=root,
            )
            with self.assertRaises(MODULE.followups_capture.CaptureError) as stage_error:
                MODULE.followups_capture.stage_docs_closeout(root, plan_rel, payload, mutate=False)

        self.assertEqual(stage_error.exception.reason_code, "followup_staging_payload_invalid")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [owned_rel])
        self.assertEqual(payload["foreign_docs_delta_paths"], historical_paths)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["skip_reason"], "blocked")
        self.assertEqual(payload["architect_final_handoff"]["followups_staging_expectations"], [])

    def test_same_plan_process_improvement_tail_is_fast_path_eligible_after_docs_commit_lands(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            backlog_rel = "docs/process_improvements/260704_2043_process_docs_closeout_post_done_pi_tail_handoff__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
            )
            self._commit_all(root, "land same-plan process improvement tail")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["reason_code"], "semantic_closeout_materialized")
        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "no_net_docs_diff")
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])
        self.assertEqual(payload["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"], [])

    def test_staged_empty_foreign_process_improvement_docs_stay_blocked(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            foreign_plan_rel = "docs/plans/260704_9999_foreign.md"
            foreign_backlog_rel = "docs/process_improvements/260704_9999_foreign__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)

            self._write_pi_backlog(root, foreign_backlog_rel, source_ref=foreign_plan_rel, entries=[{"status": "open"}])
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[foreign_backlog_rel],
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("staged_empty"),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "semantic_closeout_has_unstaged_delta")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")
        self.assertEqual(payload["final_docs_diff_paths"], [])

    def test_staged_empty_backlog_only_tail_requires_fresh_generated_surfaces(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            backlog_rel = "docs/process_improvements/260704_2043_process_docs_closeout_post_done_pi_tail_handoff__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)

            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
            )

            derived_check = COLLECT.check_derived_surfaces(root)
            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("staged_empty"),
                root=root,
            )

        self.assertFalse(derived_check["ok"])
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "semantic_closeout_has_unstaged_delta")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")
        self.assertEqual(payload["final_docs_diff_paths"], [])

    def test_capture_rejects_same_plan_pi_backlog_dirty_before_cycle_even_if_modified_after_begin(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(plan_rel)
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            COLLECT.rebuild_derived_surfaces(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)
            self._write_pi_backlog(
                root,
                backlog_rel,
                source_ref=plan_rel,
                entries=[{"status": "open"}, {"status": "open"}],
            )
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
                followups_capture_cycle_id=cycle_id,
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertIn(backlog_rel, payload["blocked_docs_delta_paths"])
        self.assertEqual(payload["final_docs_diff_paths"], [])

    def test_staged_empty_same_plan_process_improvement_tail_requires_fresh_generated_surfaces(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            backlog_rel = "docs/process_improvements/260704_2043_process_docs_closeout_post_done_pi_tail_handoff__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)

            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            (root / "docs/process_improvements/index.md").write_text("bad generated surface\n", encoding="utf-8")
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("staged_empty"),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "semantic_closeout_has_unstaged_delta")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")

    def test_staged_empty_true_semantic_docs_miss_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260704_2043_process_docs_closeout_post_done_pi_tail_handoff.md"
            docs_rel = "docs/finalize.md"
            self._write_plan(root, plan_rel, status="Done")
            docs_path = root / docs_rel
            docs_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            docs_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("staged_empty"),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "semantic_closeout_has_unstaged_delta")
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], "docs_closeout_not_completed")
        self.assertEqual(payload["final_docs_diff_paths"], [])

    def test_process_improvement_advisory_summary_is_clean_without_backlogs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1032_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel)
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_advisory_state"], "clean_noop")
        self.assertEqual(payload["process_improvement_advisory_reason"], "no_backlog_files")
        self.assertEqual(payload["process_improvement_advisory_counts"]["advisory_rows"], 0)
        self.assertIn("process_improvement_advisory_state=clean_noop", payload["dispatch_context_block"])
        self.assertIn("process_improvement_advisory_state=clean_noop", MODULE.render_text(payload))
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])

    def test_process_improvement_advisory_backlog_is_readback_only_for_materialized_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1033_fixture.md"
            backlog_rel = "docs/process_improvements/260418_1033_fixture__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_pi_backlog(
                root,
                backlog_rel,
                source_ref=plan_rel,
                entries=[
                    {
                        "status": "open",
                        "delivery_refs": "null",
                    },
                    {
                        "status": "promoted",
                        "target_canon_path": "docs/process_improvements/README.md",
                        "target_repo_scope": "planveyor",
                        "delivery_mode": "source_only",
                        "execution_kind": "plan",
                        "execution_ref": "docs/plans/260418_1033_fixture.md",
                        "delivery_refs": "docs/plans/260418_1033_fixture.md",
                        "promoted_at": "2026-04-18_10:20_MSK",
                    },
                ],
            )
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
            )
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        counts = payload["process_improvement_advisory_counts"]
        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["process_improvement_advisory_state"], "advisory_backlog")
        self.assertEqual(payload["process_improvement_advisory_reason"], "open_process_improvement_rows")
        self.assertEqual(counts["open"], 1)
        self.assertEqual(counts["promoted"], 1)
        self.assertEqual(counts["advisory_rows"], 2)
        self.assertEqual(counts["null_execution_rows"], 1)
        self.assertEqual(counts["delivery_ref_rows"], 1)
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])
        self.assertNotIn("advisory", payload["terminal_closeout_fast_path"]["missing_or_dirty_preconditions"])
        self.assertIn("process_improvement_advisory_state=advisory_backlog", payload["dispatch_context_block"])

    def test_process_improvement_advisory_backlog_does_not_block_already_tracked_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1034_fixture.md"
            backlog_rel = "docs/process_improvements/260418_1034_fixture__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_pi_backlog(
                root,
                backlog_rel,
                source_ref=plan_rel,
                entries=[{"status": "triaged"}],
            )
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Reviewer": "already_tracked"},
                backlog_paths=[backlog_rel],
            )
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(payload["process_improvement_advisory_counts"]["triaged"], 1)
        self.assertTrue(payload["terminal_closeout_fast_path"]["eligible"])

    def test_process_improvement_advisory_summary_does_not_override_pending_or_blocked_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1035_pending.md"
            backlog_rel = "docs/process_improvements/260418_1035_pending__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            self._init_git(root)
            self._commit_all(root)

            pending = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(pending["process_improvement_capture_state"], "pending")
        self.assertEqual(pending["process_improvement_advisory_state"], "advisory_backlog")
        self._assert_fast_path_blocked(pending, "pi_capture_clean")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1036_blocked.md"
            self._write_plan(root, plan_rel, status="Done")
            self._write_capture_receipts(root, plan_rel, state_by_role={"Coder": "blocked"})
            self._init_git(root)
            self._commit_all(root)

            blocked = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(blocked["process_improvement_capture_state"], "blocked")
        self.assertEqual(blocked["process_improvement_advisory_state"], "clean_noop")
        self._assert_fast_path_blocked(blocked, "pi_capture_clean")

    def test_capture_scopes_owned_followup_and_reports_foreign_incident_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            owned_rel = "docs/followups/260721_0210_followups_2058.md"
            foreign_rel = "docs/plans/260711_0136_process_custom_dirty_state_porcelain_z_parser.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            plan_hash_before = (root / plan_rel).read_bytes()
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(
                root,
                plan_rel,
                bundle,
                created_rel=owned_rel,
            )
            foreign = root / foreign_rel
            foreign.parent.mkdir(parents=True, exist_ok=True)
            foreign.write_text("foreign active workstream\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )
            plan_hash_after = (root / plan_rel).read_bytes()

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["followups_capture_state"], "materialized")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [owned_rel])
        self.assertEqual(payload["foreign_docs_delta_paths"], [foreign_rel])
        self.assertEqual(payload["blocked_docs_delta_paths"], [])
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(payload["final_docs_diff_paths"], [owned_rel])
        self.assertEqual(
            payload["architect_final_handoff"]["followups_staging_expectations"][0]["path"],
            owned_rel,
        )
        self.assertEqual(plan_hash_before, plan_hash_after)

    def test_capture_aware_general_checkpoint_full_family_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260803_1605_capture_aware_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)
            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["process_improvement_capture_state"], "clean_noop")
        self.assertEqual(payload["followups_capture_roles"], ["Architect", "Coder", "Planner", "Reviewer"])
        capture = payload["followups_capture"]
        self.assertIsNotNone(capture["general_pi_checkpoint"])
        self.assertIsNotNone(capture["general_pi_checkpoint_proof"])

    def test_capture_aware_general_checkpoint_rejects_legacy_or_wrong_cycle_receipts(self) -> None:
        def completed_fixture() -> tuple[Path, tempfile.TemporaryDirectory[str], str, dict[str, object], str]:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name).resolve()
            plan_rel = "docs/plans/260803_1605_legacy_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)
            return root, temp, plan_rel, bundle, cycle_id

        legacy_root, _legacy_temp, legacy_plan, legacy_bundle, legacy_cycle = completed_fixture()
        legacy_path = (
            legacy_root
            / ".tmp/followups_capture"
            / Path(legacy_plan).stem
            / legacy_cycle
            / MODULE.followups_capture.RECEIPT_NAME
        )
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        legacy.pop("general_pi_checkpoint")
        legacy["receipt_content_sha256"] = MODULE.followups_capture.receipt_content_sha256(legacy)
        legacy_path.write_bytes(MODULE.followups_capture.persisted_receipt_bytes(legacy))
        legacy_payload = MODULE.classify_docs_closeout(
            plan_ref=legacy_plan,
            bundle_payload=legacy_bundle,
            root=legacy_root,
            followups_capture_cycle_id=legacy_cycle,
        )

        wrong_root, _wrong_temp, wrong_plan, wrong_bundle, wrong_cycle = completed_fixture()
        wrong_path = wrong_root / COLLECT.capture_receipt_rel_path(wrong_plan, "Planner", wrong_cycle)
        wrong = json.loads(wrong_path.read_text(encoding="utf-8"))
        wrong["followups_capture_cycle_id"] = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        wrong_path.write_text(json.dumps(wrong, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        wrong_payload = MODULE.classify_docs_closeout(
            plan_ref=wrong_plan,
            bundle_payload=wrong_bundle,
            root=wrong_root,
            followups_capture_cycle_id=wrong_cycle,
        )

        self.assertEqual(legacy_payload["followups_capture_state"], "blocked")
        self.assertEqual(wrong_payload["followups_capture_state"], "blocked")
        self.assertEqual(wrong_payload["process_improvement_capture_state"], "blocked")

    def test_explicit_cycle_pi_reader_is_v2_only_and_rejects_unsafe_or_malformed_receipts(self) -> None:
        plan_rel = "docs/plans/260817_1731_cycle_reader_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        for case in ("leaf_symlink", "ancestor_symlink", "broken_ancestor_symlink", "non_regular", "malformed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_capture_receipts(root, plan_rel)
                self._write_capture_receipts(root, plan_rel, followups_capture_cycle_id=cycle_id)
                legacy = MODULE.classify_process_improvement_capture(root, plan_rel)
                self.assertEqual(legacy["process_improvement_capture_state"], "clean_noop")
                leaf = root / COLLECT.capture_receipt_rel_path(plan_rel, "Architect", cycle_id)
                if case == "leaf_symlink":
                    target = leaf.with_name("architect.real.json")
                    leaf.rename(target)
                    leaf.symlink_to(target.name)
                elif case == "ancestor_symlink":
                    cycle_dir = leaf.parent
                    target = cycle_dir.with_name(f"{cycle_dir.name}.real")
                    cycle_dir.rename(target)
                    cycle_dir.symlink_to(target.name, target_is_directory=True)
                elif case == "broken_ancestor_symlink":
                    cycle_dir = leaf.parent
                    cycle_dir.rename(cycle_dir.with_name(f"{cycle_dir.name}.saved"))
                    cycle_dir.symlink_to("missing-cycle", target_is_directory=True)
                elif case == "non_regular":
                    leaf.unlink()
                    leaf.mkdir()
                else:
                    leaf.write_bytes(b"not-json\n")

                payload = MODULE.classify_process_improvement_capture(
                    root,
                    plan_rel,
                    capture_cycle_id=cycle_id,
                )

                self.assertEqual(payload["process_improvement_capture_state"], "blocked")
                self.assertEqual(payload["process_improvement_capture_reason"], "invalid_capture_receipt")
                self.assertEqual(
                    payload["process_improvement_receipt_path"],
                    COLLECT.capture_receipt_dir_rel_path(plan_rel, cycle_id).as_posix(),
                )
                self.assertTrue(payload["process_improvement_capture_errors"])

    def test_capture_emits_complete_object_proof_for_owned_followup_and_pi_tail(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            followup_rel = "docs/followups/260721_0210_followups_2058.md"
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(plan_rel)
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")

            def materialize_pi(cycle_id: str) -> None:
                before_pi = MODULE.followups_capture.snapshot_process_improvement_data_files(root, plan_rel)
                self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
                COLLECT.rebuild_derived_surfaces(root)
                after_pi = MODULE.followups_capture.snapshot_process_improvement_data_files(root, plan_rel)
                self._write_capture_receipts(
                    root,
                    plan_rel,
                    state_by_role={"Coder": "materialized"},
                    backlog_paths=[backlog_rel],
                    followups_capture_cycle_id=cycle_id,
                    pi_chain_by_role={
                        "Architect": (before_pi, before_pi),
                        "Coder": (before_pi, after_pi),
                        "Planner": (after_pi, after_pi),
                        "Reviewer": (after_pi, after_pi),
                    },
                )

            cycle_id = self._finalize_followups_cycle(
                root,
                plan_rel,
                bundle,
                created_rel=followup_rel,
                prepare_general=materialize_pi,
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )
            stage = MODULE.followups_capture.stage_docs_closeout(
                root,
                plan_rel,
                payload,
                mutate=True,
            )

        expected_paths = sorted(
            [
                followup_rel,
                backlog_rel,
                "docs/process_improvements/deferred.md",
                "docs/process_improvements/index.md",
                "docs/process_improvements/promotion_surface.md",
            ]
        )
        expectations = payload["architect_final_handoff"]["followups_staging_expectations"]
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], expected_paths)
        self.assertEqual(payload["final_docs_diff_paths"], expected_paths)
        self.assertEqual([item["path"] for item in expectations], expected_paths)
        self.assertEqual(
            {item["ownership_class"] for item in expectations},
            {"ordinary_followup", "process_improvement"},
        )
        self.assertEqual(
            [item["path"] for item in stage["staging_verifications"]],
            expected_paths,
        )
        self.assertEqual(stage["state"], "prepared")
        self.assertTrue(all(item["blob_mode"] == "100644" for item in stage["staging_verifications"]))
        self.assertTrue(
            all(item.get("ownership_proof", {}).get("source_ref") == plan_rel for item in expectations[1:])
        )
        self.assertIn(
            f"--followups-capture-cycle-id {cycle_id}",
            payload["architect_final_handoff"]["proof_expectation"],
        )

    def test_post_checkpoint_pi_mutation_blocks_docs_closeout_projection(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260801_1734_retry_projection.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)

            (root / "docs/process_improvements/index.md").write_text("drifted\n", encoding="utf-8")
            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertEqual(payload["final_docs_commit"], "no_op")

    def test_capture_rejects_stale_pi_receipts_and_preexisting_same_plan_delta(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(plan_rel)
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
            )
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertIn(backlog_rel, payload["blocked_docs_delta_paths"])
        self.assertTrue(
            set(payload["blocked_docs_delta_paths"]).isdisjoint(payload["foreign_docs_delta_paths"])
        )
        self.assertEqual(payload["final_docs_commit"], "no_op")

    def test_capture_blocks_current_pi_projection_when_foreign_pi_backlog_is_dirty(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            backlog_rel = COLLECT.backlog_rel_path_for_source_ref(plan_rel)
            foreign_rel = "docs/process_improvements/260721_9999_foreign__process_improvements_backlog.md"
            self._write_plan(root, plan_rel, status="Done")
            COLLECT.ensure_derived_surface_docs(root)
            COLLECT.rebuild_derived_surfaces(root)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)
            self._write_pi_backlog(root, backlog_rel, source_ref=plan_rel, entries=[{"status": "open"}])
            self._write_pi_backlog(
                root,
                foreign_rel,
                source_ref="docs/plans/260721_9999_foreign.md",
                entries=[{"status": "open"}],
            )
            COLLECT.rebuild_derived_surfaces(root)
            self._write_capture_receipts(
                root,
                plan_rel,
                state_by_role={"Coder": "materialized"},
                backlog_paths=[backlog_rel],
                followups_capture_cycle_id=cycle_id,
            )

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["followups_capture_state"], "blocked")
        self.assertIn(backlog_rel, payload["blocked_docs_delta_paths"])
        self.assertIn(foreign_rel, payload["foreign_docs_delta_paths"])
        self.assertTrue(
            set(payload["blocked_docs_delta_paths"]).isdisjoint(payload["foreign_docs_delta_paths"])
        )
        self.assertEqual(payload["final_docs_diff_paths"], [])

    def test_capture_foreign_only_delta_is_completed_noop_not_empty_required_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            foreign_rel = "docs/code_drafts/260711_0136_process_custom_dirty_state_porcelain_z_parser__code_draft.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle)
            foreign = root / foreign_rel
            foreign.parent.mkdir(parents=True, exist_ok=True)
            foreign.write_text("foreign\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(payload["foreign_docs_delta_paths"], [foreign_rel])
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])

    def test_capture_aware_post_commit_readback_preserves_foreign_docs_as_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            owned_rel = "docs/followups/260721_0212_followups_2058.md"
            foreign_rel = "docs/code_drafts/260711_0136_process_custom_dirty_state_porcelain_z_parser__code_draft.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle, created_rel=owned_rel)
            foreign = root / foreign_rel
            foreign.parent.mkdir(parents=True, exist_ok=True)
            foreign.write_text("foreign\n", encoding="utf-8")
            self._git(root, "add", owned_rel)
            self._git(root, "commit", "-m", "land owned followup")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "clean_noop")
        self.assertEqual(payload["foreign_docs_delta_paths"], [foreign_rel])
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertFalse(payload["architect_final_handoff"]["required"])

    def test_receipted_same_plan_followup_same_content_replacement_is_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260715_2058_process_machine_owned_role_outcome_receipt.md"
            owned_rel = "docs/followups/260721_0211_followups_2058.md"
            self._write_plan(root, plan_rel, status="Done")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized")
            cycle_id = self._finalize_followups_cycle(root, plan_rel, bundle, created_rel=owned_rel)
            original = (root / owned_rel).read_bytes()
            replacement = root / "docs/followups/replacement.tmp"
            replacement.write_bytes(original)
            replacement.replace(root / owned_rel)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["followups_capture_state"], "materialized")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [owned_rel])
        self.assertEqual(payload["blocked_docs_delta_paths"], [])
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(payload["final_docs_diff_paths"], [owned_rel])

    def test_final_docs_commit_required_when_docs_delta_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1007_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            docs_rel = "docs/finalize.md"
            docs_path = root / docs_rel
            docs_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            docs_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized", bundle_paths=[docs_rel]),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertEqual(payload["protected_docs_delta_paths"], [])
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["plan_ref"], plan_rel)
        self.assertIn("Blocked capture is not a green no-op", payload["architect_final_handoff"]["proof_expectation"])
        self.assertEqual(payload["architect_final_handoff"]["final_docs_diff_paths"], [])
        self.assertEqual(payload["architect_final_handoff"]["protected_docs_delta_paths"], [])
        self.assertIn("- final_docs_diff_paths=none", payload["dispatch_context_block"])
        self.assertEqual(payload["process_improvement_seed"]["final_docs_diff_paths"], [])
        self.assertIn("final_docs_diff_paths=none", MODULE.render_text(payload))

    def test_final_docs_commit_allows_followup_and_process_improvement_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1011_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            followup_rel = "docs/followups/260418_1011_followups_memory_coder.md"
            process_rel = "docs/process_improvements/260418_1011__process_improvements_backlog.md"
            for rel_path in (followup_rel, process_rel):
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            for rel_path in (followup_rel, process_rel):
                (root / rel_path).write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload(
                    "already_materialized",
                    bundle_paths=[followup_rel, process_rel],
                ),
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_commit"], "no_op")
        self.assertEqual(payload["final_docs_commit_reason"], MODULE.NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON)
        self.assertEqual(payload["final_docs_diff_paths"], [])
        self.assertEqual(payload["protected_docs_delta_paths"], [])

    def test_final_docs_commit_blocks_unowned_protected_review_canon_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1012_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            protected_rel = "docs/code_reviews/_template_single_commit.md"
            protected_path = root / protected_rel
            protected_path.parent.mkdir(parents=True, exist_ok=True)
            protected_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            protected_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(payload["final_docs_commit_reason"], "canon_delta_requires_process_improvement")
        self.assertEqual(payload["final_docs_diff_paths"], [protected_rel])
        self.assertEqual(payload["protected_docs_delta_paths"], [protected_rel])
        self.assertEqual(payload["architect_final_handoff"]["final_docs_diff_paths"], [protected_rel])
        self.assertEqual(payload["architect_final_handoff"]["protected_docs_delta_paths"], [protected_rel])
        self.assertIn(
            f"- protected_docs_delta_paths={protected_rel}",
            payload["dispatch_context_block"],
        )
        self.assertIn(
            f"- final_docs_diff_paths={protected_rel}",
            payload["dispatch_context_block"],
        )
        self.assertIn(
            protected_rel,
            payload["process_improvement_seed"]["protected_docs_delta_paths"],
        )

    def test_russian_copy_keeps_original_docs_protection(self) -> None:
        runbook = "docs/tools/owner_runbook_codex.md"
        runbook_copy = "docs/tools/owner_runbook_codex.ru.md"
        pairs = (
            (runbook, runbook_copy),
            # Copies under protected prefixes are covered by the prefix itself.
            ("docs/tools/prompts/README.md", "docs/tools/prompts/README.ru.md"),
            ("docs/playbooks/analysis_wave.md", "docs/playbooks/analysis_wave.ru.md"),
            # Unprotected human documents stay unprotected in both languages.
            ("docs/guides/stack-sibling.md", "docs/guides/stack-sibling.ru.md"),
            ("docs/guides/learn/README.md", "docs/guides/learn/README.ru.md"),
            ("docs/tools/verify_suite.md", "docs/tools/verify_suite.ru.md"),
        )
        for original, russian_copy in pairs:
            with self.subTest(path=russian_copy):
                self.assertEqual(
                    MODULE._is_protected_docs_path(russian_copy),
                    MODULE._is_protected_docs_path(original),
                )
        self.assertTrue(MODULE._is_protected_docs_path(runbook_copy))

        for changed_rel in (runbook, runbook_copy):
            with self.subTest(changed=changed_rel), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_rel = "docs/plans/260418_1012_fixture.md"
                self._write_plan(root, plan_rel, status="Done")
                for rel_path in (runbook, runbook_copy):
                    path = root / rel_path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("before\n", encoding="utf-8")
                self._init_git(root)
                self._commit_all(root)
                (root / changed_rel).write_text("after\n", encoding="utf-8")

                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload("already_materialized"),
                    root=root,
                )

                self.assertEqual(payload["final_docs_commit"], "required")
                self.assertEqual(payload["final_docs_commit_reason"], "canon_delta_requires_process_improvement")
                self.assertEqual(payload["final_docs_diff_paths"], [changed_rel])
                self.assertEqual(payload["protected_docs_delta_paths"], [changed_rel])

    def test_preterminal_exact_bundle_allows_reviewed_protected_canon_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1013_fixture.md"
            protected_rel = "docs/code_reviews/README.md"
            protected_path = root / protected_rel
            protected_path.parent.mkdir(parents=True, exist_ok=True)
            protected_path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            protected_path.write_text("after\n", encoding="utf-8")

            final_docs = MODULE.classify_final_docs_commit(
                root=root,
                state="completed",
                bundle_payload=self._bundle_payload(
                    "already_materialized",
                    bundle_paths=[protected_rel],
                ),
            )

        self.assertEqual(final_docs["final_docs_commit"], "required")
        self.assertEqual(final_docs["final_docs_commit_reason"], "docs_delta_present")
        self.assertEqual(final_docs["final_docs_diff_paths"], [protected_rel])
        self.assertEqual(final_docs["protected_docs_delta_paths"], [])

    def test_terminal_historical_scope_and_explicit_override_cannot_bypass_protected_delta(self) -> None:
        protected_rel = "docs/tools/prompts/fixture_prompt.md"
        for explicit in (None, "landed", "required"):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_rel = "docs/plans/260729_1909_fixture.md"
                self._write_plan(root, plan_rel, status="Done")
                protected_path = root / protected_rel
                protected_path.parent.mkdir(parents=True, exist_ok=True)
                protected_path.write_text("before\n", encoding="utf-8")
                self._init_git(root)
                self._commit_all(root)
                protected_path.write_text("after\n", encoding="utf-8")

                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload(
                        "already_materialized",
                        final_docs_commit=explicit,
                        bundle_paths=[protected_rel],
                    ),
                    root=root,
                )

            self.assertEqual(payload["schema_state"], "ok")
            self.assertEqual(payload["state"], "completed")
            self.assertEqual(payload["final_docs_commit"], "required")
            self.assertEqual(
                payload["final_docs_commit_reason"],
                "canon_delta_requires_process_improvement",
            )
            self.assertEqual(payload["final_docs_diff_paths"], [protected_rel])
            self.assertEqual(payload["protected_docs_delta_paths"], [protected_rel])
            self.assertTrue(payload["architect_final_handoff"]["required"])
            self.assertEqual(
                payload["architect_final_handoff"]["followups_staging_expectations"],
                [],
            )
            self.assertIn(
                "Review/reclassify protected docs-closeout canon delta",
                payload["architect_final_handoff"]["task"],
            )
            self._assert_fast_path_blocked(payload, "protected_docs_clean")

    def test_terminal_plan_draft_and_review_are_immutable_even_when_listed_in_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260729_1909_fixture.md"
            draft_rel = "docs/code_drafts/260729_1909_fixture__code_draft.md"
            review_rel = "docs/code_reviews/260729_1909_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            for rel_path in (draft_rel, review_rel):
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if rel_path == draft_rel:
                    path.write_text(
                        path.read_text(encoding="utf-8") + "before\n",
                        encoding="utf-8",
                    )
                else:
                    path.write_text("before\n", encoding="utf-8")
            self._init_git(root)
            self._commit_all(root)
            for rel_path in (plan_rel, draft_rel, review_rel):
                with (root / rel_path).open("a", encoding="utf-8") as handle:
                    handle.write("after\n")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload(
                    "already_materialized",
                    bundle_paths=[plan_rel, draft_rel, review_rel],
                ),
                root=root,
            )

        expected_paths = sorted([plan_rel, draft_rel, review_rel])
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "canon_delta_requires_process_improvement",
        )
        self.assertEqual(payload["final_docs_diff_paths"], expected_paths)
        self.assertEqual(payload["protected_docs_delta_paths"], expected_paths)

    def test_capture_aware_foreign_protected_delta_requires_reclassification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1909_fixture.md"
            owned_rel = "docs/followups/260729_1909_owned.md"
            protected_rel = "docs/tools/prompts/fixture_prompt.md"
            self._write_plan(root, plan_rel, status="Done")
            protected_path = root / protected_rel
            protected_path.parent.mkdir(parents=True, exist_ok=True)
            protected_path.write_text("before\n", encoding="utf-8")
            (root / "docs/followups").mkdir(parents=True, exist_ok=True)
            self._init_git(root)
            self._commit_all(root)
            bundle = self._bundle_payload("already_materialized", bundle_paths=[protected_rel])
            cycle_id = self._finalize_followups_cycle(
                root,
                plan_rel,
                bundle,
                created_rel=owned_rel,
            )
            protected_path.write_text("after\n", encoding="utf-8")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=bundle,
                root=root,
                followups_capture_cycle_id=cycle_id,
            )

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["current_plan_owned_docs_delta_paths"], [owned_rel])
        self.assertEqual(payload["foreign_docs_delta_paths"], [protected_rel])
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "canon_delta_requires_process_improvement",
        )
        self.assertEqual(payload["final_docs_diff_paths"], [protected_rel])
        self.assertEqual(payload["protected_docs_delta_paths"], [protected_rel])
        self.assertTrue(payload["architect_final_handoff"]["required"])
        self.assertEqual(
            payload["architect_final_handoff"]["followups_staging_expectations"],
            [],
        )

    def test_accepted_red_protected_delta_requires_reclassification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            protected_rel = "docs/tools/prompts/fixture_prompt.md"
            source_rel, receipt = self._accepted_red_receipt_fixture(
                root,
                target_rel=protected_rel,
            )
            bundle = self._accepted_red_completed_bundle(source_rel, receipt)
            accepted = self._accepted_red_oracle(root / source_rel, receipt)
            (root / protected_rel).write_text("after\n", encoding="utf-8")

            with (
                mock.patch.object(
                    MODULE.plan_status_oracle,
                    "oracle_result",
                    return_value=accepted,
                ),
                mock.patch.object(
                    MODULE,
                    "verify_accepted_red_receipt",
                    return_value=(True, "accepted_red_receipt_verified"),
                ),
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=source_rel,
                    bundle_payload=bundle,
                    root=root,
                )

        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["state"], "completed")
        self.assertFalse(payload["delivery_green"])
        self.assertEqual(payload["staging_policy"], "forbidden")
        self.assertEqual(payload["final_docs_commit"], "required")
        self.assertEqual(
            payload["final_docs_commit_reason"],
            "canon_delta_requires_process_improvement",
        )
        self.assertEqual(payload["protected_docs_delta_paths"], [protected_rel])
        self.assertTrue(payload["architect_final_handoff"]["required"])

    def test_final_docs_commit_landed_uses_explicit_repo_backed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260418_1008_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_git(root)
            self._commit_all(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized", final_docs_commit="landed"),
                root=root,
            )

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["final_docs_commit"], "landed")
        self.assertEqual(payload["final_docs_commit_reason"], "explicit_bundle_payload")
        self.assertFalse(payload["architect_final_handoff"]["required"])
        self.assertEqual(payload["architect_final_handoff"]["skip_reason"], "landed")
        self.assertEqual(payload["architect_final_handoff"]["plan_ref"], plan_rel)
        self.assertIn("No Architect handoff required", payload["architect_final_handoff"]["proof_expectation"])

    def test_runtime_context_uses_queue_history_and_latest_artifact_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1003_fixture.md"
            review_rel = "docs/code_reviews/260418_1003_fixture.md"
            self._write_plan(root, plan_rel, status="Done", review_artifact=review_rel)
            self._write_review(
                root,
                review_rel,
                dedent(
                    """\
                    # Review

                    - Loop signal: `yes`
                    - Root cause class: `same-contract reroute`
                    - Extraordinary action: `spawn follow-up after queue checkpoint`
                    - Next owner: `Architect`
                    - Blocker IDs considered: `docs/code_reviews/260418_1003_fixture.md#B1`, `B2`
                    """
                ),
            )
            self._init_committed_fixture_repo(root)

            paths = self._queue_paths(root)
            PLAN_QUEUE.set_queue(paths, plans=[plan_rel], now="2026-04-18T07:00:00Z")
            self._activate_runtime_fixture(paths, now="2026-04-18T07:01:00Z")
            PLAN_QUEUE.stop_queue(paths, "max_iterations_reached", now="2026-04-18T07:02:00Z")
            PLAN_QUEUE.stop_queue(paths, "max_iterations_reached", now="2026-04-18T07:03:00Z")

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["loop_detected"], "yes")
        self.assertEqual(runtime["repeated_blocker_detected"], "yes")
        self.assertEqual(runtime["max_iterations_reached"], "yes")
        self.assertEqual(runtime["latest_stop_reason"], "max_iterations_reached")
        self.assertEqual(runtime["latest_stop_reason_scope"], "current_active")
        self.assertEqual(runtime["latest_stop_item_ref"], f"1:{plan_rel}")
        self.assertEqual(runtime["historical_stop_reason"], "none")
        self.assertEqual(runtime["latest_blocker_ids"], [f"{review_rel}#B1", "B2"])
        self.assertEqual(runtime["root_cause_class"], "same-contract reroute")
        self.assertEqual(runtime["next_owner"], "Architect")
        self.assertIn("- latest_stop_reason_scope=current_active", payload["dispatch_context_block"])
        self.assertIn("- historical_stop_reason=none", payload["dispatch_context_block"])
        self.assertEqual(payload["process_improvement_seed"]["latest_stop_reason_scope"], "current_active")
        self.assertEqual(payload["process_improvement_seed"]["historical_stop_reason"], "none")

    def test_runtime_context_uses_recovery_aware_shared_queue_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1042_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_committed_fixture_repo(root)
            queue_module = MODULE.plan_queue
            paths = queue_module.queue_paths(root)
            queue_module.set_queue(paths, plans=[plan_rel], now="2026-04-18T10:42:00Z")
            expected_context = queue_module.queue_runtime_context(
                paths,
                queue_module.load_state(paths),
                plan=plan_rel,
            )

            with mock.patch.object(
                queue_module,
                "queue_runtime_context_snapshot",
                return_value=expected_context,
            ) as snapshot_read, mock.patch.object(
                queue_module,
                "load_state",
                side_effect=AssertionError("docs_closeout must not read queue state outside the shared snapshot"),
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload("already_materialized"),
                    root=root,
                )

        snapshot_read.assert_called_once_with(mock.ANY, plan=plan_rel)
        self.assertEqual(payload["runtime_context"]["latest_stop_reason"], "none")
        self.assertTrue(payload["runtime_context"]["queue_context_source"]["history_available"])

    def test_runtime_context_fails_closed_when_queue_recovery_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1043_fixture.md"
            self._write_plan(root, plan_rel, status="Done")
            self._init_committed_fixture_repo(root)
            queue_module = MODULE.plan_queue
            paths = queue_module.queue_paths(root)
            queue_module.set_queue(paths, plans=[plan_rel], now="2026-04-18T10:43:00Z")
            after_state = queue_module.load_state(paths)
            assert after_state is not None
            after_state["updated_at"] = "2026-04-18T10:44:00Z"

            def interrupt(phase: str, _paths: object, _marker: object) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:docs-closeout-state")

            queue_module._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:docs-closeout-state"):
                    with queue_module.queue_lock(paths, "exclusive", command="docs-closeout-fixture", timeout=0.1):
                        queue_module._commit_transaction(
                            paths,
                            operation="docs-closeout-fixture",
                            after_state=after_state,
                            audit_rows=[queue_module._audit_row("fixture", at="2026-04-18T10:44:00Z")],
                        )
            finally:
                queue_module._TRANSACTION_PHASE_HOOK = None

            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()
            log_before = paths.log_path.read_bytes()
            with self.assertRaises(queue_module.QueueError) as error:
                MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload=self._bundle_payload("already_materialized"),
                    root=root,
                )
            state_after = paths.state_path.read_bytes()
            marker_after = paths.txn_path.read_bytes()
            log_after = paths.log_path.read_bytes()
            bundle_path = root / "bundle.json"
            bundle_path.write_text(
                json.dumps(self._bundle_payload("already_materialized")),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                main_result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--plan",
                        plan_rel,
                        "--bundle-json",
                        str(bundle_path),
                        "--json",
                    ]
                )
            main_payload = json.loads(stdout.getvalue())
            state_after_main = paths.state_path.read_bytes()
            marker_after_main = paths.txn_path.read_bytes()
            log_after_main = paths.log_path.read_bytes()

        self.assertEqual(error.exception.payload["error"], "recovery_required")
        self.assertEqual(error.exception.payload["classification"], "state_applied_history_missing")
        self.assertFalse(error.exception.payload["mutation_performed"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(marker_after, marker_before)
        self.assertEqual(log_after, log_before)
        self.assertEqual(main_result, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(main_payload["schema"], "docs_closeout_payload.v1")
        self.assertEqual(main_payload["schema_state"], "blocked")
        self.assertEqual(main_payload["state"], "blocked")
        self.assertEqual(main_payload["reason_code"], "queue_runtime_context_unavailable")
        self.assertEqual(main_payload["queue_error"]["error"], "recovery_required")
        self.assertEqual(
            main_payload["queue_error"]["classification"],
            "state_applied_history_missing",
        )
        self.assertEqual(state_after_main, state_before)
        self.assertEqual(marker_after_main, marker_before)
        self.assertEqual(log_after_main, log_before)

    def test_runtime_context_propagates_historical_queue_stop_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            first_plan_rel = "docs/plans/260418_1009_first.md"
            second_plan_rel = "docs/plans/260418_1010_second.md"
            self._write_plan(root, first_plan_rel, status="Done")
            self._write_plan(root, second_plan_rel, status="Done")
            self._init_committed_fixture_repo(root)

            paths = self._queue_paths(root)
            PLAN_QUEUE.set_queue(
                paths,
                plans=[first_plan_rel, second_plan_rel],
                now="2026-04-18T08:00:00Z",
            )
            self._activate_runtime_fixture(paths, now="2026-04-18T08:01:00Z")
            PLAN_QUEUE.stop_queue(paths, "unchanged_status", now="2026-04-18T08:02:00Z")
            self._advance_runtime_fixture(paths, "Done", now="2026-04-18T08:03:00Z")

            payload = MODULE.classify_docs_closeout(
                plan_ref=second_plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["latest_stop_reason"], "none")
        self.assertEqual(runtime["latest_stop_reason_scope"], "historical")
        self.assertEqual(runtime["latest_stop_item_ref"], "none")
        self.assertEqual(runtime["historical_stop_reason"], "unchanged_status")
        self.assertEqual(runtime["historical_stop_plan"], first_plan_rel)
        self.assertEqual(runtime["historical_stop_item_ref"], f"1:{first_plan_rel}")
        self.assertTrue(runtime["queue_context_source"]["history_available"])
        self.assertIn("- latest_stop_reason_scope=historical", payload["dispatch_context_block"])
        self.assertIn("- historical_stop_reason=unchanged_status", payload["dispatch_context_block"])
        self.assertEqual(payload["process_improvement_seed"]["latest_stop_reason_scope"], "historical")
        self.assertEqual(payload["process_improvement_seed"]["historical_stop_reason"], "unchanged_status")

    def test_terminal_tail_stop_is_secondary_and_does_not_dirty_terminal_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_plan_rel = "docs/plans/260418_1044_first.md"
            second_plan_rel = "docs/plans/260418_1045_second.md"
            self._write_plan(root, first_plan_rel, status="Done")
            self._write_plan(root, second_plan_rel, status="Done")
            self._write_capture_receipts(root, first_plan_rel)
            self._init_git(root)
            self._commit_all(root)

            paths = self._queue_paths(root)
            PLAN_QUEUE.set_queue(
                paths,
                plans=[first_plan_rel, second_plan_rel],
                now="2026-04-18T10:44:00Z",
            )
            self._activate_runtime_fixture(paths, now="2026-04-18T10:45:00Z")
            self._advance_runtime_fixture(paths, "Done", now="2026-04-18T10:46:00Z")
            PLAN_QUEUE.stop_queue(
                paths,
                "docs_closeout_blocked",
                source_plan=first_plan_rel,
                now="2026-04-18T10:47:00Z",
            )

            tail_payload = MODULE.classify_docs_closeout(
                plan_ref=first_plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )
            PLAN_QUEUE.stop_queue(
                paths,
                "max_iterations_reached",
                now="2026-04-18T10:48:00Z",
            )
            current_payload = MODULE.classify_docs_closeout(
                plan_ref=first_plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = tail_payload["runtime_context"]
        self.assertEqual(runtime["latest_stop_reason"], "none")
        self.assertEqual(runtime["latest_stop_reason_scope"], "historical")
        self.assertEqual(runtime["historical_stop_reason"], "docs_closeout_blocked")
        self.assertEqual(runtime["historical_stop_plan"], first_plan_rel)
        self.assertEqual(runtime["historical_stop_item_ref"], f"1:{first_plan_rel}")
        self.assertEqual(runtime["terminal_tail_stop_reason"], "docs_closeout_blocked")
        self.assertEqual(runtime["terminal_tail_stop_source_plan"], first_plan_rel)
        self.assertEqual(runtime["terminal_tail_stop_source_item_ref"], f"1:{first_plan_rel}")
        self.assertEqual(runtime["terminal_tail_stop_active_item_ref"], f"2:{second_plan_rel}")
        self.assertEqual(runtime["loop_detected"], "no")
        self.assertEqual(runtime["repeated_blocker_detected"], "no")
        self.assertEqual(runtime["max_iterations_reached"], "no")
        self.assertTrue(
            tail_payload["terminal_closeout_fast_path"]["eligible"],
            tail_payload["terminal_closeout_fast_path"],
        )
        self.assertTrue(
            tail_payload["terminal_closeout_fast_path"]["precondition_results"][
                "runtime_context_clean"
            ]
        )
        self.assertIn(
            f"- terminal_tail_stop_source_plan={first_plan_rel}",
            tail_payload["dispatch_context_block"],
        )
        self.assertEqual(
            tail_payload["process_improvement_seed"]["terminal_tail_stop_source_plan"],
            first_plan_rel,
        )

        current_runtime = current_payload["runtime_context"]
        self.assertEqual(current_runtime["latest_stop_reason"], "max_iterations_reached")
        self.assertEqual(current_runtime["latest_stop_reason_scope"], "current_active")
        self.assertEqual(current_runtime["terminal_tail_stop_source_plan"], first_plan_rel)
        self.assertFalse(current_payload["terminal_closeout_fast_path"]["eligible"])
        self.assertIn(
            "latest_stop_reason_scope=current_active",
            current_payload["terminal_closeout_fast_path"]["dirty_runtime_signals"],
        )

    def test_runtime_context_ignores_historical_review_refs_outside_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260418_1004_fixture.md"
            review_rel = "docs/code_reviews/260418_1004_fixture.md"
            stale_review_rel = "docs/doc_reviews/260418_0999_historical.md"
            evidence_tail = dedent(
                f"""\
                - [2026-04-18 10:00 MSK] (Reviewer) Historical anchor only:
                  stale ref `{stale_review_rel}`
                """
            ).strip()
            self._write_plan(
                root,
                plan_rel,
                status="Done",
                review_artifact=review_rel,
                evidence_tail=evidence_tail,
            )
            self._write_review(
                root,
                review_rel,
                dedent(
                    f"""\
                    # Review

                    - Root cause class: `shared contract carrier bounded fan-out`
                    - Next owner: `Reviewer`
                    - Blocker IDs considered: `{review_rel}#B4`
                    """
                ),
            )
            self._write_review(
                root,
                stale_review_rel,
                dedent(
                    f"""\
                    # Historical review

                    - Root cause class: `historical stale value`
                    - Next owner: `Architect`
                    - Blocker IDs considered: `{stale_review_rel}#B99`
                    """
                ),
            )
            self._init_committed_fixture_repo(root)

            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload=self._bundle_payload("already_materialized"),
                root=root,
            )

        runtime = payload["runtime_context"]
        self.assertEqual(runtime["artifact_sources"], [plan_rel, review_rel])
        self.assertEqual(runtime["root_cause_class"], "shared contract carrier bounded fan-out")
        self.assertEqual(runtime["next_owner"], "Reviewer")
        self.assertEqual(runtime["latest_blocker_ids"], [f"{review_rel}#B4"])


class DocsCloseoutV2FollowupsTests(unittest.TestCase):
    plan_ref = "docs/plans/260811_0020_terminal.md"
    post_cas_draft_ref = "docs/code_drafts/260811_0020_terminal__code_draft.md"
    post_cas_review_ref = "docs/code_reviews/260811_0020_terminal.md"
    post_cas_target_ref = "scripts/post_cas_canonical_bundle_fixture.py"

    def _machine_authority_decision(self) -> dict[str, str]:
        return {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }

    def _machine_authority_ref(self, decision: dict[str, str]) -> dict[str, str]:
        return {
            "applicability": "not_applicable",
            "reason_code": decision["reason_code"],
            "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(
                decision
            ),
        }

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _unreachable_source_commits(self, root: Path) -> tuple[str, str]:
        tree_oid = self._git(root, "rev-parse", "HEAD^{tree}")
        dangling = self._git(root, "commit-tree", tree_oid, "-m", "dangling closeout source")
        unrelated = self._git(root, "commit-tree", tree_oid, "-m", "unrelated closeout source")
        self._git(root, "update-ref", "refs/heads/unrelated", unrelated)
        return dangling, unrelated

    def _manifest(self, root: Path, commit: str, blob: str) -> dict[str, object]:
        try:
            from scripts import followups_capture, followups_lint
        except ModuleNotFoundError:
            import followups_capture
            import followups_lint

        row = {
            "priority": "P1", "summary": "Closeout V2 proof", "cluster": "process", "to": "coder",
            "status": "open", "plan": None, "why": "open debt is not delivery failure", "tags": [],
            "item_id": "closeout-001", "source_ref": self.plan_ref,
            "disposition_kind": None, "disposition_ref": None, "disposition_commit_oid": None, "reason": None,
        }
        snapshot, _ = followups_capture.snapshot_followups(root, include_bytes=True)
        source_bytes = subprocess.run(
            ["git", "show", f"{commit}:{self.plan_ref}"],
            cwd=root,
            capture_output=True,
            check=False,
        ).stdout
        key = f"{self.plan_ref}\u0000closeout-001"
        return {
            "schema_version": "followups_capture_cycle.v2", "plan_ref": self.plan_ref,
            "source_terminal_commit_oid": commit, "source_plan_blob_oid": blob,
            "source_plan_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "baseline_followups_snapshot": snapshot,
            "baseline_followups_snapshot_sha256": followups_capture._sha256(
                followups_capture._canonical_json_bytes(snapshot)
            ),
            "declaration_roles": ["Architect", "Coder", "Planner", "Reviewer"],
            "expected_owned_tuples": [{"source_ref": self.plan_ref, "item_id": "closeout-001"}],
            "tuple_owners": {key: "Coder"}, "expected_zero_reason": None,
            "proposed_rows": [{
                "followup_path": "docs/followups/process_followups_master.md", "payload": row,
                "row_digest": followups_lint.v2_row_digest(row),
            }],
        }

    def _captured_v2_cycle(
        self,
        root: Path,
        *,
        with_process_improvements: bool = False,
        foreign_binding: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object], str]:
        try:
            from scripts import followups_apply, followups_capture, followups_lint
        except ModuleNotFoundError:
            import followups_apply
            import followups_capture
            import followups_lint

        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / self.plan_ref).write_text(
            "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n",
            encoding="utf-8",
        )
        foreign_plan_ref = "docs/plans/260811_0021_foreign_terminal.md"
        if foreign_binding is not None:
            self.assertIn(foreign_binding, {"manifest", "row"})
            (root / foreign_plan_ref).write_text(
                "# foreign terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n",
                encoding="utf-8",
            )
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Test")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid')
        self._git(root, "add", "docs/plans")
        self._git(root, "commit", "-qm", "terminal source")
        commit = self._git(root, "rev-parse", "HEAD")
        blob = self._git(root, "rev-parse", f"HEAD:{self.plan_ref}")
        manifest = self._manifest(root, commit, blob)
        manifest_for_apply = manifest
        manifest_for_persistence = manifest
        if foreign_binding is not None:
            foreign_blob = self._git(root, "rev-parse", f"HEAD:{foreign_plan_ref}")
            foreign_bytes = subprocess.run(
                ["git", "show", f"{commit}:{foreign_plan_ref}"],
                cwd=root,
                capture_output=True,
                check=False,
            ).stdout
            foreign_payload = dict(manifest["proposed_rows"][0]["payload"])
            foreign_payload["source_ref"] = foreign_plan_ref
            foreign_manifest = json.loads(json.dumps(manifest))
            foreign_manifest.update(
                {
                    "plan_ref": foreign_plan_ref,
                    "source_plan_blob_oid": foreign_blob,
                    "source_plan_sha256": hashlib.sha256(foreign_bytes).hexdigest(),
                }
            )
            foreign_manifest["expected_owned_tuples"] = [
                {"source_ref": foreign_plan_ref, "item_id": "closeout-001"},
            ]
            foreign_manifest["tuple_owners"] = {f"{foreign_plan_ref}\u0000closeout-001": "Coder"}
            foreign_manifest["proposed_rows"] = [
                {
                    "followup_path": "docs/followups/process_followups_master.md",
                    "payload": foreign_payload,
                    "row_digest": followups_lint.v2_row_digest(foreign_payload),
                },
            ]
            manifest_for_apply = foreign_manifest
            if foreign_binding == "manifest":
                manifest_for_persistence = foreign_manifest
            else:
                manifest_for_persistence = json.loads(json.dumps(manifest))
                for key in ("expected_owned_tuples", "tuple_owners", "proposed_rows"):
                    manifest_for_persistence[key] = foreign_manifest[key]
        followups_apply.apply_frozen_rows(root, manifest_for_apply, mutate=True)
        followups_capture.persist_v2_frozen_manifest(root, self.plan_ref, manifest_for_persistence)
        begin = followups_capture.begin_cycle(
            root,
            self.plan_ref,
            {
                "schema": "docs_closeout_payload.v1",
                "schema_state": "ok",
                "plan_ref": self.plan_ref,
                "semantic_status": "Done",
                "semantic_status_norm": "done",
                "semantic_closeout_kind": "already_materialized",
                "final_docs_commit": "no_op",
            },
        )
        cycle_id = str(begin["capture_cycle_id"])
        for role in followups_capture.REQUIRED_ROLES:
            collector_text = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
            if with_process_improvements and role == "Coder":
                collector_text = (
                    "## Process improvements\n"
                    "### Suggestion 1\n"
                    "- symptom: V2 projection fixture needs the existing PI tail\n"
                    "- process_gap: whole-file ownership must remain separate from PI ownership\n"
                    "- suggested_fix: retain one exact merged staging allowlist\n"
                    "- owner: Architect\n"
                    "- promotion_class: helper_change\n"
                    "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                    f"- source_ref: {self.plan_ref}\n"
                )
            followups_capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=self.plan_ref,
                text=collector_text,
                followups_capture_cycle_id=cycle_id,
            )
        followups_capture.checkpoint_general_pi(root, self.plan_ref, cycle_id)
        for role in followups_capture.REQUIRED_ROLES:
            followups_capture.prepare_role(root, self.plan_ref, cycle_id, role)
            followups_capture.finalize_role(root, self.plan_ref, cycle_id, role, b"NO FOLLOWUPS\n")
        capture = followups_capture.read_capture(
            root,
            self.plan_ref,
            cycle_id,
            semantic_fields=("Done", "done", "already_materialized"),
        )
        carrier_path = str(manifest["proposed_rows"][0]["followup_path"])
        return manifest, capture, carrier_path

    def _captured_ordinary_compact_v2_cycle(
        self,
        root: Path,
        *,
        with_row: bool = True,
        with_index: bool = False,
        declared_index: bool = False,
        root_target: bool = False,
        semantic_closeout_kind: str = "already_materialized",
    ) -> tuple[dict[str, object], dict[str, object], str]:
        try:
            from scripts import followups_apply, followups_capture
        except ModuleNotFoundError:
            import followups_apply
            import followups_capture

        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/code_drafts").mkdir(parents=True)
        (root / "docs/code_reviews").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / "scripts").mkdir(parents=True)
        decision = self._machine_authority_decision()
        (root / self.post_cas_target_ref).write_text("# canonical post-CAS target\n", encoding="utf-8")
        (root / self.post_cas_draft_ref).write_text(
            "\n".join(
                [
                    "# Code draft: post-CAS fixture",
                    "",
                    "```json",
                    json.dumps(
                        {
                            "code_draft_meta": {
                                "plan": self.plan_ref,
                                "cluster": "process",
                                "targets": [{"path": self.post_cas_target_ref, "kind": "py"}] + ([{"path": "docs/followups/index.md", "kind": "doc"}] if declared_index else []) + ([{"path": "SECURITY.md", "kind": "doc"}] if declared_index or root_target else []),
                                "deleted_paths": [],
                                "machine_authority_decision_ref": self._machine_authority_ref(decision),
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
        (root / self.post_cas_review_ref).write_text(
            "# Code review — post-CAS fixture\n\n**Status:** ✅ OK\n",
            encoding="utf-8",
        )
        (root / self.plan_ref).write_text(
            "\n".join(
                [
                    "# terminal",
                    "",
                    "**Status:** Done",
                    "**Schema version:** plan.v2",
                    "",
                    "**Context links (source of truth):**",
                    f"- Code draft(s): `{self.post_cas_draft_ref}`",
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    json.dumps(
                        {"plan_meta": {"cluster": "process", "machine_authority_decision": decision}},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "```",
                    "",
                    "## Review artifacts",
                    f"- Code review (primary): `{self.post_cas_review_ref}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if declared_index or root_target:
            (root / "SECURITY.md").write_text("# root-level canonical policy\n", encoding="utf-8")
        if declared_index:
            DocsCloseoutTests._write_plan(
                self, root, self.plan_ref, status="Done",
                review_artifact=self.post_cas_review_ref,
                context_links=f"- Code draft(s): `{self.post_cas_draft_ref}`",
                meta_json=json.dumps(
                    {"plan_meta": {"cluster": "process", "machine_authority_decision": decision}},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            plan = root / self.plan_ref
            plan.write_text(plan.read_text().replace("**Status:** Done", "**Status:** Done\n**Schema version:** plan.v2"))
        if with_index:
            (root / "docs/followups/index.md").write_text(
                "# Follow-ups — index\n\nfixture manual header\n",
                encoding="utf-8",
            )
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Test")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid')
        initial_paths = ["docs/plans", "docs/code_drafts", "docs/code_reviews", "scripts"]
        if with_index:
            initial_paths.append("docs/followups/index.md")
        if declared_index or root_target:
            initial_paths.append("SECURITY.md")
        self._git(root, "add", *initial_paths)
        self._git(root, "commit", "-qm", "terminal source")
        commit = self._git(root, "rev-parse", "HEAD")
        blob = self._git(root, "rev-parse", f"HEAD:{self.plan_ref}")
        declared = self._manifest(root, commit, blob)["proposed_rows"][0]
        admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
        begin = followups_capture.begin_cycle(
            root,
            self.plan_ref,
            {
                "schema": "docs_closeout_payload.v1",
                "schema_state": "ok",
                "plan_ref": self.plan_ref,
                "semantic_status": "Done",
                "semantic_status_norm": "done",
                "semantic_closeout_kind": semantic_closeout_kind,
                "final_docs_commit": "no_op",
                "followups_bootstrap_admission": admission,
            },
        )
        cycle_id = str(begin["capture_cycle_id"])
        general_receipts: list[str] = []
        for role in followups_capture.REQUIRED_ROLES:
            collected = followups_capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=self.plan_ref,
                text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                followups_capture_cycle_id=cycle_id,
            )
            self.assertEqual(collected["process_improvement_capture_state"], "clean_noop")
            general_receipts.append(str(collected["process_improvement_receipt_path"]))
        self.assertEqual(
            general_receipts,
            [
                followups_capture.process_improvements_collect.capture_receipt_rel_path(
                    self.plan_ref, role, cycle_id
                ).as_posix()
                for role in followups_capture.REQUIRED_ROLES
            ],
        )
        checkpoint = followups_capture.checkpoint_general_pi(root, self.plan_ref, cycle_id)
        self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")
        for role in followups_capture.REQUIRED_ROLES:
            followups_capture.prepare_role(root, self.plan_ref, cycle_id, role)
            compact = {
                "role": role,
                "proposed_rows": [declared] if with_row and role == "Coder" else [],
                "role_no_items_reason": None if with_row and role == "Coder" else f"{role} found no compact rows.",
            }
            followups_capture.submit_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role=role,
                raw_input=json.dumps(compact, separators=(",", ":")).encode("utf-8"),
                write=True,
            )
            followups_capture.bind_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                role=role,
                submission_current=True,
                write=True,
            )
        frozen = followups_capture.freeze_ordinary_v2(
            root,
            plan_ref=self.plan_ref,
            capture_cycle_id=cycle_id,
            write=True,
        )
        manifest = json.loads((root / str(frozen["frozen_manifest_path"])).read_text(encoding="utf-8"))
        if with_row:
            followups_apply.apply_frozen_rows(root, manifest, mutate=True)
        capture = followups_capture.read_capture(
            root,
            self.plan_ref,
            cycle_id,
            semantic_fields=("Done", "done", semantic_closeout_kind),
        )
        return manifest, capture, str(declared["followup_path"])

    def _pending_closeout(self, root: Path, cycle: str, kind: str = "staged_empty") -> dict:
        paths = MODULE.followups_capture._post_cas_semantic_identity_canonical_bundle_paths(root, plan_ref=self.plan_ref)
        return MODULE.classify_docs_closeout(
            root=root, plan_ref=self.plan_ref, followups_capture_cycle_id=cycle,
            bundle_payload={"plan": self.plan_ref, "bundle_ok": True, "errors": [],
                            "closeout_kind": kind,
                            "repo_roots": [{"repo_root": str(root), "bundle_paths": list(paths)}]},
        )

    def _forward_repair(self, root: Path) -> str:
        (root / "scripts/disjoint_repair.py").write_text("# reviewed repair\n")
        self._git(root, "add", "scripts/disjoint_repair.py")
        self._git(root, "commit", "-qm", "disjoint repair")
        return self._git(root, "rev-parse", "HEAD")

    def test_pending_generated_pair_survives_forward_repair_and_exact_cas(self) -> None:
        for forward in (False, True):
            with self.subTest(forward=forward), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                manifest, capture, carrier = self._captured_ordinary_compact_v2_cycle(root, with_index=True, declared_index=True)
                cycle = str(capture["capture_cycle_id"])
                frozen_files = {p: p.read_bytes() for p in (root / ".tmp/followups_capture").rglob("*.json")}
                plan_before = (root / self.plan_ref).read_bytes()
                parent = self._forward_repair(root) if forward else self._git(root, "rev-parse", "HEAD")
                self.assertEqual(manifest["source_terminal_commit_oid"], self._git(root, "rev-parse", "HEAD^") if forward else parent)
                # The shared index remains outside the exact transaction.
                (root / "unrelated.txt").write_text("keep staged\n")
                self._git(root, "add", "unrelated.txt")
                payload = self._pending_closeout(root, cycle)
                self.assertEqual(payload["schema_state"], "ok", payload)
                self.assertEqual(payload["state"], "completed", payload)
                self.assertEqual(payload["semantic_closeout_kind"], "staged_empty")
                self.assertEqual(payload["final_docs_commit"], "required")
                self.assertFalse(payload["terminal_closeout_fast_path"]["eligible"])
                self.assertEqual(payload["final_docs_diff_paths"], sorted([carrier, "docs/followups/index.md"]))
                self.assertNotIn("_pending_index_transition", json.dumps(payload))
                preflight = MODULE.followups_capture.commit_preflight(root, self.plan_ref, payload)
                self.assertEqual(preflight["expected_parent_oid"], parent)
                landed = MODULE.followups_capture.commit_exact(root, self.plan_ref, preflight, message_auto=True)
                self.assertEqual(self._git(root, "rev-parse", "HEAD^"), parent)
                self.assertEqual(self._git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines(), sorted([carrier, "docs/followups/index.md"]))
                self.assertEqual(self._git(root, "diff", "--cached", "--name-only"), "unrelated.txt")
                # A later disjoint commit is also a valid landed-state readback.
                self._git(root, "commit", "-qm", "later unrelated change")
                post = self._pending_closeout(root, cycle, "already_materialized")
                self.assertEqual(post["final_docs_commit"], "no_op", post)
                self.assertEqual(post["state"], "completed", post)
                self.assertEqual((root / self.plan_ref).read_bytes(), plan_before)
                self.assertEqual({p: p.read_bytes() for p in frozen_files}, frozen_files)
                self.assertEqual(landed["expected_parent_oid"], parent)

    def test_pending_generated_pair_rejects_scoped_drift_and_partial_landing(self) -> None:
        for case in ("target", "assume_unchanged_target", "draft_omission", "review", "staged_index", "staged_carrier", "extra_followup", "partial_index", "partial_carrier", "manual_index", "source_plan"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _, capture, carrier = self._captured_ordinary_compact_v2_cycle(root, with_index=True, declared_index=True)
                cycle = str(capture["capture_cycle_id"])
                self._forward_repair(root)
                if case == "target":
                    (root / self.post_cas_target_ref).write_text("# changed target\n")
                    self._git(root, "add", self.post_cas_target_ref)
                    self._git(root, "commit", "-qm", "changed canonical target")
                elif case == "assume_unchanged_target":
                    self._git(root, "update-index", "--assume-unchanged", self.post_cas_target_ref)
                    (root / self.post_cas_target_ref).write_text("# invisible to git diff\n")
                    self.assertEqual(self._git(root, "diff", "--name-only", "HEAD", "--", self.post_cas_target_ref), "")
                elif case == "draft_omission":
                    draft = root / self.post_cas_draft_ref
                    draft.write_text(draft.read_text().replace(self.post_cas_target_ref, "scripts/disjoint_repair.py"))
                    (root / self.post_cas_target_ref).write_text("# hidden drift\n")
                elif case == "review":
                    (root / self.post_cas_review_ref).write_text("# changed review\n")
                elif case in {"staged_index", "staged_carrier", "partial_index", "partial_carrier"}:
                    path = "docs/followups/index.md" if case.endswith("index") else carrier
                    self._git(root, "add", path)
                    if case.startswith("partial"):
                        self._git(root, "commit", "-qm", "partial generated pair")
                elif case == "extra_followup":
                    (root / "docs/followups/foreign.md").write_text("# foreign\n")
                    self._git(root, "add", "docs/followups/foreign.md")
                    self._git(root, "commit", "-qm", "extra followup")
                elif case == "source_plan":
                    (root / self.plan_ref).write_text((root / self.plan_ref).read_text() + "\nchanged\n")
                else:
                    index = root / "docs/followups/index.md"
                    index.write_text(index.read_text().replace("fixture manual header", "altered manual header"))
                    sidecar = root / MODULE.followups_capture.followups_index_refresh_receipt_relpath(self.plan_ref, cycle)
                    data = json.loads(sidecar.read_text())
                    data["index_after_sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
                    sidecar.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                before = self._git(root, "rev-parse", "HEAD")
                with self.assertRaises(MODULE.followups_capture.CaptureError):
                    MODULE.followups_capture.read_capture(root, self.plan_ref, cycle, semantic_fields=("Done", "done", "staged_empty"))
                self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)

    def test_pending_promotion_preserves_protected_docs_reclassification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _, capture, _ = self._captured_ordinary_compact_v2_cycle(root, with_index=True, declared_index=True)
            protected = root / "docs/tools/prompts/foreign.md"
            protected.parent.mkdir(parents=True)
            protected.write_text("# protected\n")
            payload = self._pending_closeout(root, str(capture["capture_cycle_id"]))
            self.assertEqual(payload["schema_state"], "ok", payload)
            self.assertEqual(payload["final_docs_commit_reason"], "canon_delta_requires_process_improvement", payload)
            self.assertEqual(payload["architect_final_handoff"]["followups_staging_expectations"], [])
            with self.assertRaises(MODULE.followups_capture.CaptureError):
                MODULE.followups_capture.stage_docs_closeout(root, self.plan_ref, payload, mutate=True)

    def test_nonempty_v2_carrier_projects_one_strict_ordinary_expectation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_v2_cycle(root)
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path], True),
            )

        self.assertEqual(projection["followups_capture_state"], "materialized")
        self.assertEqual(projection["followups_capture_reason"], "capture_owned_delta")
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], [carrier_path])
        self.assertEqual(projection["blocked_docs_delta_paths"], [])
        expectation = projection["followups_staging_expectations"]
        self.assertEqual(len(expectation), 1)
        self.assertEqual(expectation[0]["ownership_class"], "ordinary_followup")
        proof = expectation[0]["ownership_proof"]
        self.assertEqual(set(proof), MODULE.V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_KEYS)
        self.assertEqual(proof["carrier_path"], carrier_path)
        self.assertEqual(proof["carrier_absence"], {
            "baseline": True,
            "source_terminal_commit": True,
            "expected_parent": True,
        })
        self.assertTrue(proof["expected_rows"])

    def test_ordinary_compact_v2_lifecycle_projects_existing_closeout_staging_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root)
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path], True),
            )

        self.assertEqual(capture["state"], "clean_noop")
        self.assertEqual(projection["followups_capture_state"], "materialized")
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], [carrier_path])
        self.assertEqual(projection["blocked_docs_delta_paths"], [])
        self.assertEqual(len(projection["followups_staging_expectations"]), 1)
        self.assertEqual(projection["followups_staging_expectations"][0]["path"], carrier_path)

    def test_ordinary_compact_v2_index_projection_requires_the_full_raw_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root, with_index=True)
            index_path = "docs/followups/index.md"
            pair = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path, index_path], True),
            )
            index_only = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([index_path], True),
            )

        self.assertEqual(pair["followups_capture_state"], "materialized")
        self.assertEqual(pair["current_plan_owned_docs_delta_paths"], [index_path, carrier_path])
        self.assertEqual(
            [item["path"] for item in pair["followups_staging_expectations"]],
            [index_path, carrier_path],
        )
        self.assertEqual(index_only["followups_capture_state"], "blocked")
        self.assertEqual(index_only["followups_staging_expectations"], [])
        self.assertEqual(index_only["blocked_docs_delta_paths"], [index_path])

    def test_ordinary_compact_v2_stale_generated_index_has_no_staging_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root, with_index=True)
            index_path = "docs/followups/index.md"
            (root / index_path).write_text("# stale generated index\n", encoding="utf-8")
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path, index_path], True),
            )

        self.assertEqual(projection["followups_capture_state"], "blocked")
        self.assertEqual(projection["followups_staging_expectations"], [])
        self.assertEqual(projection["blocked_docs_delta_paths"], [index_path, carrier_path])

    def test_ordinary_compact_v2_foreign_refresh_receipt_has_no_staging_allowance(self) -> None:
        try:
            from scripts import followups_capture
        except ModuleNotFoundError:
            import followups_capture

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root, with_index=True)
            cycle_id = str(capture["capture_cycle_id"])
            receipt_path = root / followups_capture.followups_index_refresh_receipt_relpath(
                self.plan_ref,
                cycle_id,
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["owner_id"] = "foreign_terminal_owner"
            receipt_path.write_text(
                json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path, "docs/followups/index.md"], True),
            )

        self.assertEqual(projection["followups_capture_state"], "blocked")
        self.assertEqual(projection["followups_capture_reason"], "followups_index_refresh_receipt_invalid")
        self.assertEqual(projection["followups_staging_expectations"], [])
        self.assertEqual(
            projection["blocked_docs_delta_paths"],
            ["docs/followups/index.md", carrier_path],
        )

    def test_ordinary_compact_v2_post_commit_readback_stays_closeout_clean_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root)
            self._git(root, "add", carrier_path)
            self._git(root, "commit", "-qm", "land canonical ordinary compact carrier")
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([], True),
            )

        self.assertEqual(projection["followups_capture_state"], "clean_noop")
        self.assertEqual(projection["followups_capture_reason"], "capture_finalized_noop")
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(projection["blocked_docs_delta_paths"], [])
        self.assertEqual(projection["capture_readback"]["state"], "clean_noop")

    def test_post_cas_semantic_identity_transition_rederives_current_bundle_before_clean_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(
                root,
                semantic_closeout_kind="staged_empty",
                root_target=True,
            )
            cycle_id = str(capture["capture_cycle_id"])
            receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / MODULE.followups_capture.RECEIPT_NAME
            receipt_before = receipt_path.read_bytes()
            self._git(root, "add", carrier_path)
            self._git(root, "commit", "-qm", "land exact terminal docs semantic CAS")
            bundle_payload = {
                "plan": self.plan_ref,
                "bundle_ok": True,
                "closeout_kind": "already_materialized",
                "repo_roots": [
                    {
                        "repo_root": str(root),
                        "bundle_paths": list(
                            MODULE.followups_capture._post_cas_semantic_identity_canonical_bundle_paths(
                                root,
                                plan_ref=self.plan_ref,
                            )
                        ),
                    }
                ],
            }
            self.assertIn("SECURITY.md", bundle_payload["repo_roots"][0]["bundle_paths"])
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=cycle_id,
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={
                    "process_improvement_capture_state": "clean_noop",
                    "followups_reconciliation_state": "external_clean",
                    "followups_reconciliation_open_items": 0,
                },
                bundle_payload=bundle_payload,
                docs_status_snapshot=([], True),
            )
            receipt_after = receipt_path.read_bytes()

        self.assertEqual(projection["followups_capture_state"], "clean_noop")
        self.assertEqual(projection["followups_capture_reason"], "capture_finalized_noop")
        self.assertEqual(projection["capture_readback"]["state"], "clean_noop")
        self.assertEqual(receipt_after, receipt_before)

    def test_post_cas_semantic_identity_transition_rejects_empty_delta_false_greens(self) -> None:
        for case in (
            "bundle_not_green",
            "extra_bundle_entry",
            "omitted_required_member",
            "cross_root_member",
            "worktree_delta",
            "staged_delta",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(
                    root,
                    semantic_closeout_kind="staged_empty",
                )
                cycle_id = str(capture["capture_cycle_id"])
                receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / MODULE.followups_capture.RECEIPT_NAME
                receipt_before = receipt_path.read_bytes()
                self._git(root, "add", carrier_path)
                self._git(root, "commit", "-qm", "land exact terminal docs semantic CAS")
                bundle_paths = list(
                    MODULE.followups_capture._post_cas_semantic_identity_canonical_bundle_paths(
                        root,
                        plan_ref=self.plan_ref,
                    )
                )
                bundle_ok = True
                repo_root = str(root)
                if case == "bundle_not_green":
                    bundle_ok = False
                elif case == "extra_bundle_entry":
                    extra_path = "docs/code_reviews/noncanonical_existing_member.md"
                    (root / extra_path).write_text("# existing but noncanonical\n", encoding="utf-8")
                    self._git(root, "add", extra_path)
                    self._git(root, "commit", "-qm", "commit noncanonical existing member")
                    bundle_paths = sorted([*bundle_paths, extra_path])
                elif case == "omitted_required_member":
                    self.assertIn(self.post_cas_target_ref, bundle_paths)
                    bundle_paths.remove(self.post_cas_target_ref)
                elif case == "cross_root_member":
                    repo_root = str(root.parent)
                else:
                    (root / carrier_path).write_text("# staged-only false green\n", encoding="utf-8")
                    if case == "staged_delta":
                        self._git(root, "add", carrier_path)
                projection = MODULE.classify_followups_capture(
                    root=root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=cycle_id,
                    semantic_fields=("Done", "done", "already_materialized"),
                    pi_capture={
                        "process_improvement_capture_state": "clean_noop",
                        "followups_reconciliation_state": "external_clean",
                        "followups_reconciliation_open_items": 0,
                    },
                    bundle_payload={
                        "plan": self.plan_ref,
                        "bundle_ok": bundle_ok,
                        "closeout_kind": "already_materialized",
                        "repo_roots": [{"repo_root": repo_root, "bundle_paths": bundle_paths}],
                    },
                    # These output-only derived values cannot substitute for
                    # the fresh current-tree check above.
                    docs_status_snapshot=([], True),
                )

                self.assertEqual(projection["followups_capture_state"], "blocked")
                self.assertEqual(projection["followups_capture_reason"], "followup_capture_semantic_identity_mismatch")
                self.assertIsNone(projection["capture_readback"])
                self.assertEqual(receipt_path.read_bytes(), receipt_before)

    def test_ordinary_compact_v2_zero_union_stays_existing_clean_noop_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(
                root,
                with_row=False,
            )
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([], True),
            )

        self.assertEqual(manifest["expected_owned_tuples"], [])
        self.assertFalse((root / carrier_path).exists())
        self.assertEqual(capture["state"], "clean_noop")
        self.assertEqual(projection["followups_capture_state"], "clean_noop")
        self.assertEqual(projection["followups_staging_expectations"], [])

    def test_ordinary_compact_v2_foreign_post_apply_delta_is_not_staging_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_ordinary_compact_v2_cycle(root)
            foreign_path = root / "docs/followups/foreign_post_apply.md"
            foreign_path.write_text("# foreign post-apply delta\n", encoding="utf-8")
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "clean_noop"},
                docs_status_snapshot=([carrier_path, "docs/followups/foreign_post_apply.md"], True),
            )

        self.assertEqual(projection["followups_capture_state"], "blocked")
        self.assertEqual(projection["followups_staging_expectations"], [])
        self.assertIn("docs/followups/foreign_post_apply.md", projection["blocked_docs_delta_paths"])

    def test_v2_apply_before_capture_joins_four_pi_paths_into_exact_staging_allowlist(self) -> None:
        try:
            from scripts import followups_capture
        except ModuleNotFoundError:
            import followups_capture
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, carrier_path = self._captured_v2_cycle(
                root,
                with_process_improvements=True,
            )
            pi_capture = MODULE.classify_process_improvement_capture(
                root,
                self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
            )
            proof = followups_capture.process_improvement_cycle_proof(root, self.plan_ref, capture)
            dirty_paths = sorted([carrier_path, *proof["changed_data_paths"]])
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture=pi_capture,
                docs_status_snapshot=(dirty_paths, True),
            )

        self.assertEqual(pi_capture["process_improvement_capture_state"], "materialized")
        self.assertEqual(projection["followups_capture_state"], "materialized")
        self.assertEqual(projection["blocked_docs_delta_paths"], [])
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], dirty_paths)
        self.assertEqual(
            [item["path"] for item in projection["followups_staging_expectations"]],
            dirty_paths,
        )
        v2_expectation = next(
            item
            for item in projection["followups_staging_expectations"]
            if item["path"] == carrier_path
        )
        self.assertEqual(v2_expectation["ownership_class"], "ordinary_followup")
        self.assertEqual(v2_expectation["ownership_proof"]["carrier_path"], carrier_path)

    def test_v2_projection_rejects_foreign_manifest_or_row_binding(self) -> None:
        for foreign_binding in ("manifest", "row"):
            with self.subTest(foreign_binding=foreign_binding), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _manifest, capture, carrier_path = self._captured_v2_cycle(
                    root,
                    foreign_binding=foreign_binding,
                )
                projection = MODULE.classify_followups_capture(
                    root=root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=str(capture["capture_cycle_id"]),
                    semantic_fields=("Done", "done", "already_materialized"),
                    pi_capture={"process_improvement_capture_state": "clean_noop"},
                    docs_status_snapshot=([carrier_path], True),
                )

                self.assertEqual(projection["followups_capture_state"], "blocked")
                self.assertEqual(projection["followups_capture_reason"], "missing_or_mismatched_v2_tuple_proof")
                self.assertEqual(projection["current_plan_owned_docs_delta_paths"], [])
                self.assertEqual(projection["followups_staging_expectations"], [])
                self.assertEqual(projection["blocked_docs_delta_paths"], [carrier_path])

    def test_v2_projection_rejects_manifest_drift_without_pi_ownership_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            manifest, capture, carrier_path = self._captured_v2_cycle(root)
            manifest["tuple_owners"] = {
                f"{self.plan_ref}\u0000closeout-001": "Owner",
            }
            try:
                from scripts import followups_capture
            except ModuleNotFoundError:
                import followups_capture
            followups_capture.persist_v2_frozen_manifest(root, self.plan_ref, manifest)
            projection = MODULE.classify_followups_capture(
                root=root,
                plan_ref=self.plan_ref,
                capture_cycle_id=str(capture["capture_cycle_id"]),
                semantic_fields=("Done", "done", "already_materialized"),
                pi_capture={"process_improvement_capture_state": "materialized"},
                docs_status_snapshot=([carrier_path], True),
            )

        self.assertEqual(projection["followups_capture_state"], "blocked")
        self.assertEqual(projection["followups_capture_reason"], "missing_or_mismatched_v2_tuple_proof")
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], [])
        self.assertEqual(projection["followups_staging_expectations"], [])
        self.assertEqual(projection["blocked_docs_delta_paths"], [carrier_path])

    def test_v2_ownership_proof_schema_rejects_unknown_missing_and_duplicate_rows(self) -> None:
        try:
            from scripts import followups_capture
        except ModuleNotFoundError:
            import followups_capture
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _manifest, capture, _carrier_path = self._captured_v2_cycle(root)
            expectation = followups_capture.v2_external_followup_staging_expectations(
                root,
                self.plan_ref,
                capture_binding=capture,
            )[0]
        for mutation in ("unknown", "missing", "duplicate"):
            with self.subTest(mutation=mutation):
                proof = json.loads(json.dumps(expectation["ownership_proof"]))
                if mutation == "unknown":
                    proof["unexpected"] = True
                elif mutation == "missing":
                    proof.pop("carrier_absence")
                else:
                    proof["expected_rows"].append(dict(proof["expected_rows"][0]))
                errors: list[str] = []
                MODULE._validate_v2_external_staging_proof(proof, errors, path="proof")
                self.assertTrue(errors, errors)

    def test_open_v2_row_with_exact_frozen_proof_is_external_clean(self) -> None:
        try:
            from scripts import followups_apply
        except ModuleNotFoundError:
            import followups_apply

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            self._git(root, "init", "-q")
            self._git(root, "config", "user.name", "Test")
            self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid')
            self._git(root, "add", self.plan_ref)
            self._git(root, "commit", "-qm", "terminal source")
            commit = self._git(root, "rev-parse", "HEAD")
            blob = self._git(root, "rev-parse", f"HEAD:{self.plan_ref}")
            manifest = self._manifest(root, commit, blob)
            followups_apply.apply_frozen_rows(root, manifest, mutate=True)
            manifest_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / "v2_frozen_manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual(result["state"], "external_clean")
            self.assertEqual(result["open_items"], [])
            self.assertEqual(result["proof_host"], "docs/followups/process_followups_master.md#closeout-001")

            foreign = root / "docs/followups/foreign.md"
            foreign.write_text(
                "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n",
                encoding="utf-8",
            )
            blocked = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual(blocked["state"], "external_invalid")
            self.assertEqual(blocked["reason"], "v2_integrity_blocker")

            foreign.write_text(
                "# V1 compatibility\n\n**Schema version:** followups.v1\n\n## Follow-ups\n- P1 [ ] malformed V1 row\n",
                encoding="utf-8",
            )
            compatibility = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual(compatibility["state"], "external_clean")

    def test_unsupported_plan_schema_never_uses_legacy_followups_out_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v9\n\n"
                "```json\n{\"plan_meta\": {\"followups_out\": [{\"plan\": \"docs/plans/child.md\"}]}}\n```\n",
                encoding="utf-8",
            )

            result = MODULE.classify_followups_reconciliation(root, self.plan_ref)

        self.assertEqual(result["state"], "external_invalid")
        self.assertEqual(result["reason"], "unsupported_plan_schema_for_legacy_followups")

    def test_v2_missing_frozen_manifest_stays_external_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            result = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual(result["state"], "external_unknown")
            self.assertEqual(result["reason"], "missing_v2_frozen_manifest")

    def test_v2_readback_reports_exact_unreachable_source_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "docs/plans").mkdir(parents=True)
            (root / "docs/followups").mkdir(parents=True)
            (root / self.plan_ref).write_text(
                "# terminal\n\n**Status:** Done\n**Schema version:** plan.v2\n", encoding="utf-8"
            )
            self._git(root, "init", "-q")
            self._git(root, "config", "user.name", "Test")
            self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid')
            self._git(root, "add", self.plan_ref)
            self._git(root, "commit", "-qm", "terminal source")
            blob = self._git(root, "rev-parse", f"HEAD:{self.plan_ref}")
            manifest_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / "v2_frozen_manifest.json"
            manifest_path.parent.mkdir(parents=True)
            for source_commit in self._unreachable_source_commits(root):
                manifest_path.write_text(json.dumps(self._manifest(root, source_commit, blob)), encoding="utf-8")
                result = MODULE.classify_followups_reconciliation(root, self.plan_ref)
                self.assertEqual(result["state"], "external_invalid")
                self.assertEqual(result["reason"], "followup_v2_source_commit_unreachable")


class DocsCloseoutFormatCorrectionTests(unittest.TestCase):
    def _fixture(self, root):
        try:
            from scripts.test_followups_capture import GeneralPIFormatCorrectionTests
        except ModuleNotFoundError:
            from test_followups_capture import GeneralPIFormatCorrectionTests
        proof = GeneralPIFormatCorrectionTests()
        return proof, proof.fixture(root, "Coder")

    def test_format_correction_schema_parity_and_authoritative_red(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); proof, (fixture, module, cap, cycle, leaf) = self._fixture(root)
            payload = proof.payload(root, fixture, module, cycle)
            admission = payload["general_pi_format_correction_admission"]
            self.assertEqual((admission["state"], payload["state"], payload["process_improvement_capture_state"]), ("retryable", "blocked", "blocked"))
            self.assertEqual((admission["role"], admission["attempts_reserved"], admission["max_extra_attempts"]), ("Coder", 0, 1))
            self.assertIn("general_pi_format_correction_state=retryable", module.render_text(payload))
            self.assertIn("general_pi_format_correction_state=retryable", payload["dispatch_context_block"])
            for variant in ("unknown_key", "budget", "proof", "cycle", "false_green"):
                candidate = json.loads(json.dumps(payload))
                nested = candidate["general_pi_format_correction_admission"]
                if variant == "unknown_key": nested["unknown"] = 1
                elif variant == "budget": nested["attempts_reserved"] = True
                elif variant == "proof": nested["proof"] = []
                elif variant == "cycle": nested["capture_cycle_id"] = "foreign"
                else: candidate["state"] = "completed"
                result = module.finalize_docs_closeout_payload(candidate)
                self.assertEqual((result["schema_state"], result["state"]), ("blocked", "blocked"))
            original = leaf.read_bytes(); untyped = json.loads(original); untyped.pop("error_type"); leaf.write_text(json.dumps(untyped))
            red = proof.payload(root, fixture, module, cycle)
            self.assertEqual(red["general_pi_format_correction_admission"]["state"], "blocked")
            self.assertEqual(red["process_improvement_capture_state"], "blocked")

    def test_corrected_cycle_reaches_ordinary_compact_terminal_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); proof, (fixture, module, cap, cycle, leaf) = self._fixture(root)
            reserved, _ = proof.reserve(root, fixture, module, cap, cycle, "Coder")
            cap.process_improvements_collect.collect_process_improvements(project_root=root, role="Coder", source_ref=fixture.plan_ref,
                text=proof.clean, followups_capture_cycle_id=cycle)
            for role in ("Planner", "Reviewer"):
                cap.process_improvements_collect.collect_process_improvements(project_root=root, role=role, source_ref=fixture.plan_ref,
                    text=proof.clean, followups_capture_cycle_id=cycle)
            continuation = proof.payload(root, fixture, module, cycle)
            self.assertEqual(continuation["followups_continuation_admission"]["state"], "ready")
            cap.checkpoint_general_pi(root, fixture.plan_ref, cycle)
            for role in cap.REQUIRED_ROLES:
                cap.prepare_role(root, fixture.plan_ref, cycle, role)
                raw = json.dumps({"role": role, "proposed_rows": [], "role_no_items_reason": "No new fixture followups."}).encode()
                cap.submit_ordinary_v2(root, plan_ref=fixture.plan_ref, capture_cycle_id=cycle, role=role, raw_input=raw, write=True)
                cap.bind_ordinary_v2(root, plan_ref=fixture.plan_ref, capture_cycle_id=cycle, role=role, submission_current=True, write=True)
            cap.freeze_ordinary_v2(root, plan_ref=fixture.plan_ref, capture_cycle_id=cycle, write=True)
            final = proof.payload(root, fixture, module, cycle)
            self.assertEqual((final["schema_state"], final["state"], final["final_docs_commit"]), ("ok", "completed", "no_op"), final)
            self.assertEqual(final["general_pi_format_correction_admission"]["state"], "not_applicable")


class DocsCloseoutContinuationAdmissionTests(unittest.TestCase):
    plan_ref = "docs/plans/260902_0010_continuation_fixture.md"

    def _fixture(self, root: Path, *, materialized: bool = False) -> str:
        capture = MODULE.followups_capture
        review_ref = f"docs/code_reviews/{Path(self.plan_ref).stem}.md"
        plan = DocsCloseoutTests()._write_plan(root, self.plan_ref, review_artifact=review_ref)
        DocsCloseoutTests()._write_review(root, review_ref, "# Code review: fixture\n\n**Status:** ✅ OK\n")
        (root / "docs/fixture.md").write_text("# Committed fixture bundle target\n")
        plan.write_text(plan.read_text().replace(
            "**Status:** Done", "**Status:** Done\n**Schema version:** plan.v2"
        ).replace('"cluster": "process",', '"cluster": "process",\n  "required_manager_mode": "either",'))
        (root / "docs/followups").mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "add", "docs"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "terminal source"],
                       check=True, capture_output=True)
        cycle = str(capture.begin_cycle(root, self.plan_ref, {
            "schema": "docs_closeout_payload.v1", "schema_state": "ok", "plan_ref": self.plan_ref,
            "semantic_status": "Done", "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
            "followups_bootstrap_admission": MODULE.classify_followups_bootstrap_admission(root, self.plan_ref),
        })["capture_cycle_id"])
        self._collect(root, cycle, materialized=materialized)
        return cycle

    def _collect(self, root: Path, cycle: str, *, materialized: bool = False) -> None:
        for role in MODULE.followups_capture.REQUIRED_ROLES:
            text = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
            if materialized and role == "Coder":
                text = ("## Process improvements\n### Suggestion 1\n"
                        "- symptom: continuation fixture needs a materialized effect\n"
                        "- process_gap: pre-first-followups proof needs coverage\n"
                        "- suggested_fix: preserve the exact collector chain\n"
                        "- owner: Architect\n- promotion_class: helper_change\n"
                        "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                        f"- source_ref: {self.plan_ref}\n")
            if materialized and role == "Reviewer":
                text = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n"
            MODULE.followups_capture.process_improvements_collect.collect_process_improvements(
                project_root=root, role=role, source_ref=self.plan_ref, text=text,
                followups_capture_cycle_id=cycle)

    def _bundle(self) -> dict[str, object]:
        return {"plan": self.plan_ref, "bundle_ok": True, "errors": [],
                "closeout_kind": "already_materialized", "repo_roots": []}

    def _admission(self, root: Path, cycle: str) -> dict[str, object]:
        return MODULE.classify_followups_continuation_admission(
            root, self.plan_ref, cycle, bundle_payload=self._bundle())

    def test_pre_first_followups_admission_preserves_incomplete_outer_state(self) -> None:
        for materialized in (False, True):
            with self.subTest(materialized=materialized), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve(); cycle = self._fixture(root, materialized=materialized)
                admission = self._admission(root, cycle)
                self.assertEqual((admission["state"], admission["reason"]),
                                 ("ready", "pre_first_followups"), admission)
                self.assertEqual(admission["next_dispatch"], "Architect:followups")
                payload = MODULE.classify_docs_closeout(
                    root=root, plan_ref=self.plan_ref, bundle_payload=self._bundle(),
                    followups_capture_cycle_id=cycle)
                self.assertEqual(payload["schema_state"], "ok", payload.get("schema_errors"))
                self.assertEqual(payload["state"], "blocked")
                self.assertEqual(payload["followups_continuation_admission"], admission)
                states = admission["proof"]["collector_states"]
                self.assertIn("clean_noop", states.values())
                if materialized:
                    self.assertIn("materialized", states.values())
                    self.assertIn("already_tracked", states.values())

    def _receipt_path(self, root: Path, cycle: str) -> Path:
        return root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle / MODULE.followups_capture.RECEIPT_NAME

    def _edit_receipt(self, root: Path, cycle: str, edit: Callable) -> None:
        capture = MODULE.followups_capture
        path = self._receipt_path(root, cycle)
        receipt = json.loads(path.read_bytes()); edit(receipt)
        path.write_bytes(capture.persisted_receipt_bytes(capture._set_receipt_digest(receipt)))

    def _objects(self, root: Path) -> dict[str, tuple[bytes, int]]:
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mode)
                for folder in (root / "docs", root / ".tmp") for p in folder.rglob("*")
                if p.is_file() and not p.is_symlink()}

    def test_continuation_refuses_drift_without_writing_any_docs_or_receipts(self) -> None:
        variants = ("plan", "source_schema", "mode", "owner_qna", "semantic", "bundle", "pi", "followups",
                    "foreign", "protected", "manifest", "unsafe_manifest", "phase", "blocked", "legacy",
                    "revision", "pi_baseline", "binding", "submission", "ambiguous", "collector_cycle", "host")
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve(); cycle = self._fixture(root, materialized=variant == "pi")
                plan = root / self.plan_ref; bundle = self._bundle(); capture = MODULE.followups_capture
                if variant in {"plan", "source_schema", "mode", "owner_qna"}:
                    text = plan.read_text()
                    if variant == "source_schema": text = text.replace("plan.v2", "plan.v1")
                    elif variant == "mode": text = text.replace('"either"', '"manager-custom"')
                    elif variant == "owner_qna": text += "\n## Q&A log\n- id=Q1 status=open to=Owner (Architect) — question\n"
                    else: text += "\nplan drift\n"
                    plan.write_text(text)
                elif variant == "semantic": bundle["closeout_kind"] = "staged_empty"
                elif variant == "bundle": bundle["bundle_ok"] = False
                elif variant == "pi": (root / "docs/process_improvements/index.md").write_text("stale derived surface\n")
                elif variant in {"followups", "foreign", "protected"}:
                    rel = {"followups": "docs/followups/unrecorded.md", "foreign": "docs/foreign.md",
                           "protected": "docs/roles/manager.md"}[variant]
                    path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("delta\n")
                elif variant in {"manifest", "unsafe_manifest"}:
                    manifest = capture.v2_frozen_manifest_path(root, self.plan_ref)
                    if variant == "manifest": manifest.write_text("{}\n")
                    else: manifest.symlink_to(root / "absent")
                elif variant == "phase": capture.checkpoint_general_pi(root, self.plan_ref, cycle); capture.prepare_role(root, self.plan_ref, cycle, "Architect")
                elif variant == "blocked": self._edit_receipt(root, cycle, lambda r: r.update(blocked_roles=["Architect"]))
                elif variant == "legacy": self._edit_receipt(root, cycle, lambda r: r.pop("general_pi_checkpoint"))
                elif variant == "revision": self._edit_receipt(root, cycle, lambda r: r.update(receipt_revision=3))
                elif variant == "pi_baseline": self._edit_receipt(root, cycle, lambda r: r.update(baseline_dirty_process_improvement_paths=["docs/process_improvements/index.md"]))
                elif variant == "binding": self._edit_receipt(root, cycle, lambda r: r.update({capture.ORDINARY_V2_BINDING_KEY: {}}))
                elif variant == "submission": (self._receipt_path(root, cycle).parent / capture.ORDINARY_V2_SUBMISSION_DIRECTORY).mkdir()
                elif variant == "ambiguous":
                    receipt = json.loads(self._receipt_path(root, cycle).read_bytes()); other = str(uuid.uuid4())
                    directory = self._receipt_path(root, other).parent; directory.mkdir()
                    receipt.update(capture_cycle_id=other, pi_lineage_root_cycle_id=other,
                                   cycle_directory_identity=capture._cycle_dir_identity(self.plan_ref, other, directory.stat()))
                    self._receipt_path(root, other).write_bytes(capture.persisted_receipt_bytes(capture._set_receipt_digest(receipt)))
                elif variant == "collector_cycle":
                    path = root / capture.process_improvements_collect.capture_receipt_rel_path(self.plan_ref, "Coder", cycle)
                    receipt = json.loads(path.read_bytes()); receipt["followups_capture_cycle_id"] = str(uuid.uuid4()); path.write_text(json.dumps(receipt))
                elif variant == "host": self._edit_receipt(root, cycle, lambda r: r["transaction_host_identity"].update(project_root=str(root / "foreign")))
                before = self._objects(root)
                admission = MODULE.classify_followups_continuation_admission(root, self.plan_ref, cycle, bundle_payload=bundle)
                self.assertEqual(admission["state"], "blocked", (variant, admission))
                self.assertIsNone(admission["proof"])
                self.assertEqual(before, self._objects(root))

    def test_continuation_reads_delta_even_when_incomplete_projection_lists_are_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); cycle = self._fixture(root)
            (root / "docs/foreign.md").write_text("foreign dirty docs\n")
            payload = MODULE.classify_docs_closeout(root=root, plan_ref=self.plan_ref,
                bundle_payload=self._bundle(), followups_capture_cycle_id=cycle)
            self.assertEqual(payload["final_docs_diff_paths"], [])
            self.assertEqual(payload["protected_docs_delta_paths"], [])
            self.assertEqual(payload["followups_continuation_admission"]["state"], "blocked")
            with mock.patch.object(MODULE, "_git_status_docs_paths", return_value=([], False)):
                self.assertEqual(self._admission(root, cycle)["reason"], "continuation_docs_delta_unknown")

    def test_continuation_payload_schema_refuses_missing_and_malformed_permission(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); cycle = self._fixture(root)
            payload = MODULE.classify_docs_closeout(root=root, plan_ref=self.plan_ref,
                bundle_payload=self._bundle(), followups_capture_cycle_id=cycle)
            for variant in ("missing", "selector", "semantic", "source", "inputs", "phase", "next", "proof"):
                with self.subTest(variant=variant):
                    mutant = json.loads(json.dumps(payload)); a = mutant["followups_continuation_admission"]
                    if variant == "missing": mutant.pop("followups_continuation_admission")
                    elif variant == "selector": a["capture_cycle_id"] = str(uuid.uuid4())
                    elif variant == "semantic": a["proof"]["identity_payload"]["semantic_status"] = "Superseded"
                    elif variant == "source": a["proof"]["source_identity"]["source_plan_blob_oid"] = "invalid"
                    elif variant == "inputs": a["proof"]["collector_inputs"] = {}
                    elif variant == "phase": a["phase"] = "followups"
                    elif variant == "next": a["next_dispatch"] = "Coder:followups"
                    else: a["proof"] = {}
                    self.assertEqual(MODULE.validate_docs_closeout_payload(mutant)["schema_state"], "blocked")


class DocsCloseoutBootstrapAdmissionTests(unittest.TestCase):
    plan_ref = "docs/plans/260824_generic_terminal_bootstrap_fixture.md"

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _root(self, tmpdir: str, *, schema: str | None = "plan.v2", status: str = "Done") -> Path:
        root = Path(tmpdir).resolve()
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        schema_line = f"**Schema version:** {schema}\n" if schema is not None else ""
        (root / self.plan_ref).write_text(
            f"# terminal bootstrap fixture\n\n**Status:** {status}\n{schema_line}",
            encoding="utf-8",
        )
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Fixture")
        self._git(root, "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'invalid')
        self._git(root, "add", self.plan_ref)
        self._git(root, "commit", "-qm", "terminal bootstrap source")
        return root

    def _manifest_path(self, root: Path) -> Path:
        return MODULE.followups_capture.v2_frozen_manifest_path(root, self.plan_ref)

    def _persist_valid_manifest(self, root: Path) -> Path:
        try:
            from scripts import followups_apply, followups_capture, followups_lint
        except ModuleNotFoundError:
            import followups_apply
            import followups_capture
            import followups_lint

        commit = self._git(root, "rev-parse", "HEAD")
        blob = self._git(root, "rev-parse", f"HEAD:{self.plan_ref}")
        source_bytes = subprocess.run(
            ["git", "show", f"{commit}:{self.plan_ref}"],
            cwd=root,
            capture_output=True,
            check=False,
        ).stdout
        snapshot, _ = followups_capture.snapshot_followups(root, include_bytes=True)
        row = {
            "priority": "P1", "summary": "Bootstrap manifest proof", "cluster": "process", "to": "coder",
            "status": "open", "plan": None, "why": "fixture proof", "tags": [],
            "item_id": "bootstrap-001", "source_ref": self.plan_ref,
            "disposition_kind": None, "disposition_ref": None, "disposition_commit_oid": None, "reason": None,
        }
        key = f"{self.plan_ref}\u0000bootstrap-001"
        manifest = {
            "schema_version": "followups_capture_cycle.v2", "plan_ref": self.plan_ref,
            "source_terminal_commit_oid": commit, "source_plan_blob_oid": blob,
            "source_plan_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "baseline_followups_snapshot": snapshot,
            "baseline_followups_snapshot_sha256": followups_capture._sha256(
                followups_capture._canonical_json_bytes(snapshot)
            ),
            "declaration_roles": ["Architect", "Coder", "Planner", "Reviewer"],
            "expected_owned_tuples": [{"source_ref": self.plan_ref, "item_id": "bootstrap-001"}],
            "tuple_owners": {key: "Coder"}, "expected_zero_reason": None,
            "proposed_rows": [{
                "followup_path": "docs/followups/bootstrap_manifest_proof.md", "payload": row,
                "row_digest": followups_lint.v2_row_digest(row),
            }],
        }
        followups_apply.apply_frozen_rows(root, manifest, mutate=True)
        followups_capture.persist_v2_frozen_manifest(root, self.plan_ref, manifest)
        return self._manifest_path(root)

    def _all_other_fast_path_green(self, reconciliation: dict[str, object]) -> dict[str, object]:
        return MODULE.classify_terminal_closeout_fast_path(
            plan_ref=self.plan_ref,
            state="completed",
            closeout_kind="already_materialized",
            bundle_ok=True,
            bundle_errors=[],
            final_docs_commit="no_op",
            protected_docs_delta_paths=[],
            process_improvement_capture_state="clean_noop",
            process_improvement_receipt_path=".tmp/bootstrap-fixture-pi-receipt",
            followups_reconciliation=reconciliation,
            runtime_context={},
        )

    def test_exact_absence_is_ready_without_changing_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
            reconciliation = MODULE.classify_followups_reconciliation(root, self.plan_ref)

        self.assertEqual(set(admission), MODULE.FOLLOWUPS_BOOTSTRAP_ADMISSION_KEYS)
        self.assertEqual(admission["schema"], "followups_bootstrap_admission.v1")
        self.assertEqual(admission["state"], "ready")
        self.assertEqual(admission["reason"], "missing_v2_frozen_manifest")
        self.assertEqual(admission["plan_ref"], self.plan_ref)
        self.assertEqual(
            admission["canonical_manifest_path"],
            ".tmp/followups_capture/260824_generic_terminal_bootstrap_fixture/v2_frozen_manifest.json",
        )
        self.assertTrue(all(admission[key] for key in (
            "source_terminal_commit_oid", "source_plan_blob_oid", "source_plan_sha256",
        )))
        self.assertEqual(reconciliation["state"], "external_unknown")
        self.assertEqual(reconciliation["reason"], "missing_v2_frozen_manifest")
        fast_path = self._all_other_fast_path_green(reconciliation)
        self.assertFalse(fast_path["eligible"])
        self.assertIn("followups_clean", fast_path["missing_or_dirty_preconditions"])

    def test_exact_valid_regular_manifest_is_positive_reconciliation_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            manifest = self._persist_valid_manifest(root)
            admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
            reconciliation = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            fast_path = self._all_other_fast_path_green(reconciliation)
            self.assertTrue(manifest.exists())

        self.assertEqual(admission["state"], "blocked")
        self.assertEqual(admission["reason"], "bootstrap_manifest_present")
        self.assertEqual(reconciliation["state"], "external_clean")
        self.assertEqual(reconciliation["reason"], "exact_v2_tuple_proof")
        self.assertTrue(fast_path["eligible"])

    def test_present_or_unsafe_manifest_never_becomes_absence_or_fast_path_green(self) -> None:
        for kind in (
            "empty", "malformed", "stale", "foreign", "directory", "fifo",
            "valid_symlink", "dangling_symlink", "unsafe_ancestor",
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                manifest = self._manifest_path(root)
                if kind == "unsafe_ancestor":
                    (root / ".tmp").mkdir()
                    backing = root / "manifest-store"
                    backing.mkdir()
                    (root / ".tmp" / "followups_capture").symlink_to(backing, target_is_directory=True)
                    manifest = self._persist_valid_manifest(root)
                else:
                    manifest.parent.mkdir(parents=True)
                if kind == "unsafe_ancestor":
                    pass
                elif kind == "empty":
                    manifest.write_bytes(b"")
                elif kind == "malformed":
                    manifest.write_bytes(b"{not-json}\n")
                elif kind == "stale":
                    manifest.write_text('{"schema_version":"followups_frozen_manifest.v0"}\n', encoding="utf-8")
                elif kind == "foreign":
                    manifest.write_text(
                        '{"plan_ref":"docs/plans/foreign.md","proposed_rows":[]}\n',
                        encoding="utf-8",
                    )
                elif kind == "directory":
                    manifest.mkdir()
                elif kind == "fifo":
                    os.mkfifo(manifest)
                elif kind == "valid_symlink":
                    self._persist_valid_manifest(root)
                    target = root / "manifest-target.json"
                    target.write_bytes(manifest.read_bytes())
                    manifest.unlink()
                    os.symlink(target, manifest)
                elif kind == "dangling_symlink":
                    manifest.symlink_to("missing-manifest-target.json")
                else:
                    self.fail(f"unhandled manifest kind: {kind}")

                admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
                reconciliation = MODULE.classify_followups_reconciliation(root, self.plan_ref)
                fast_path = self._all_other_fast_path_green(reconciliation)

                self.assertEqual(admission["state"], "blocked")
                self.assertIn(
                    admission["reason"],
                    {"bootstrap_manifest_present", "bootstrap_manifest_path_unsafe"},
                )
                self.assertEqual(reconciliation["state"], "external_invalid")
                self.assertNotEqual(reconciliation["reason"], "missing_v2_frozen_manifest")
                self.assertEqual(
                    reconciliation["proof_host"],
                    ".tmp/followups_capture/260824_generic_terminal_bootstrap_fixture/v2_frozen_manifest.json",
                )
                self.assertFalse(fast_path["eligible"])
                self.assertIn("followups_clean", fast_path["missing_or_dirty_preconditions"])

    def test_source_and_capture_drift_are_blocked(self) -> None:
        for source_case, schema, status in (
            ("worktree_drift", "plan.v2", "Done"),
            ("v1", "plan.v1", "Done"),
            ("versionless", None, "Done"),
            ("nonterminal", "plan.v2", "In progress"),
        ):
            with self.subTest(source_case=source_case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir, schema=schema, status=status)
                if source_case == "worktree_drift":
                    (root / self.plan_ref).write_text(
                        "# drift\n\n**Status:** Done\n**Schema version:** plan.v2\n",
                        encoding="utf-8",
                    )
                admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
                self.assertEqual(admission["state"], "blocked")
                self.assertIn(
                    admission["reason"],
                    {"bootstrap_plan_schema_invalid", "bootstrap_source_identity_invalid"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            started = MODULE.followups_capture.begin_cycle(
                root,
                self.plan_ref,
                {
                    "schema": "docs_closeout_payload.v1",
                    "schema_state": "ok",
                    "plan_ref": self.plan_ref,
                    "semantic_status": "Done",
                    "semantic_status_norm": "done",
                    "semantic_closeout_kind": "already_materialized",
                    "followups_bootstrap_admission": MODULE.classify_followups_bootstrap_admission(
                        root,
                        self.plan_ref,
                    ),
                },
            )
            admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)

        self.assertTrue(started["capture_cycle_id"])
        self.assertEqual(admission["state"], "blocked")
        self.assertEqual(admission["reason"], "bootstrap_capture_active")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            family = root / ".tmp/followups_capture" / Path(self.plan_ref).stem
            (family / "12345678-1234-4234-8234-123456789abc").mkdir(parents=True)
            admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)

        self.assertEqual(admission["state"], "blocked")
        self.assertEqual(admission["reason"], "bootstrap_capture_invalid")

    def test_two_valid_active_cycles_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            payload = {
                "schema": "docs_closeout_payload.v1",
                "schema_state": "ok",
                "plan_ref": self.plan_ref,
                "semantic_status": "Done",
                "semantic_status_norm": "done",
                "semantic_closeout_kind": "already_materialized",
                "followups_bootstrap_admission": MODULE.classify_followups_bootstrap_admission(
                    root,
                    self.plan_ref,
                ),
            }
            first = MODULE.followups_capture.begin_cycle(root, self.plan_ref, payload)
            first_id = str(first["capture_cycle_id"])
            family = root / ".tmp/followups_capture" / Path(self.plan_ref).stem
            first_receipt_path = family / first_id / MODULE.followups_capture.RECEIPT_NAME
            duplicate_id = str(uuid.uuid4())
            duplicate_dir = family / duplicate_id
            duplicate_dir.mkdir(mode=0o700)
            duplicate_receipt_path = duplicate_dir / MODULE.followups_capture.RECEIPT_NAME
            duplicate_receipt_path.touch(mode=0o600)
            duplicate = json.loads(first_receipt_path.read_text(encoding="utf-8"))
            duplicate["capture_cycle_id"] = duplicate_id
            duplicate["pi_lineage_root_cycle_id"] = duplicate_id
            duplicate["cycle_directory_identity"] = MODULE.followups_capture._cycle_dir_identity(
                self.plan_ref,
                duplicate_id,
                duplicate_dir.stat(),
            )
            duplicate["receipt_object_identity"] = MODULE.followups_capture._receipt_identity(
                self.plan_ref,
                duplicate_id,
                duplicate_receipt_path.stat(),
            )
            duplicate["receipt_content_sha256"] = MODULE.followups_capture.receipt_content_sha256(
                duplicate
            )
            duplicate_receipt_path.write_bytes(
                MODULE.followups_capture.persisted_receipt_bytes(duplicate)
            )

            admission = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)

        self.assertEqual(admission["state"], "blocked")
        self.assertEqual(admission["reason"], "bootstrap_capture_ambiguous")


class DocsCloseoutBlockedPredecessorRecoveryTests(unittest.TestCase):
    """Exercise the injected recovery classifier with a self-contained fixture."""

    plan_ref = "docs/plans/270101_0101_recovery_fixture.md"

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _payload(self) -> dict[str, object]:
        return {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": self.plan_ref,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
        }

    def _root(self, tmpdir: str) -> Path:
        root = Path(tmpdir).resolve()
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        (root / self.plan_ref).write_text(
            "# recovery fixture\n\n**Status:** Done\n**Schema version:** plan.v2\n",
            encoding="utf-8",
        )
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Fixture")
        self._git(root, "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'invalid')
        self._git(root, "add", self.plan_ref)
        self._git(root, "commit", "-qm", "terminal recovery source")
        return root

    def _blocked_predecessor(
        self,
        root: Path,
        *,
        materialize_coder_pi: bool = False,
    ) -> tuple[str, dict[str, str], bytes]:
        capture = MODULE.followups_capture
        payload = self._payload()
        payload["followups_bootstrap_admission"] = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
        cycle_id = str(capture.begin_cycle(root, self.plan_ref, payload)["capture_cycle_id"])
        clean = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        coder_suggestion = (
            "## Process improvements\n"
            "### Suggestion 1\n"
            "- symptom: recovery negative fixture needs an exact PI after-map\n"
            "- process_gap: synthetic predecessor must preserve a materialized PI checkpoint\n"
            "- suggested_fix: retain the exact current-cycle PI object chain\n"
            "- owner: Architect\n"
            "- promotion_class: helper_change\n"
            "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
            f"- source_ref: {self.plan_ref}\n"
        )
        for role in capture.REQUIRED_ROLES:
            capture.process_improvements_collect.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=self.plan_ref,
                text=coder_suggestion if role == "Coder" and materialize_coder_pi else clean,
                followups_capture_cycle_id=cycle_id,
            )
        capture.checkpoint_general_pi(root, self.plan_ref, cycle_id)
        capture.prepare_role(root, self.plan_ref, cycle_id, "Architect")
        blocked = capture.prepare_role(root, self.plan_ref, cycle_id, "Coder")
        self.assertEqual(blocked["state"], "blocked")
        receipt_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / cycle_id / capture.RECEIPT_NAME
        raw = receipt_path.read_bytes()
        profile = {
            "plan_ref": self.plan_ref,
            "predecessor_capture_cycle_id": cycle_id,
            "source_terminal_commit_oid": self._git(root, "rev-parse", "HEAD"),
            "source_plan_blob_oid": self._git(root, "rev-parse", f"HEAD:{self.plan_ref}"),
            "source_plan_sha256": capture._sha256((root / self.plan_ref).read_bytes()),
            "predecessor_receipt_sha256": capture._sha256(raw),
        }
        return cycle_id, profile, raw

    def _completed_recovery_replay(
        self,
        root: Path,
    ) -> tuple[dict[str, object], dict[str, str]]:
        """Finish a synthetic recovery family whose PI collectors replay only."""

        _predecessor_id, profile, _raw = self._blocked_predecessor(root, materialize_coder_pi=True)
        capture = MODULE.followups_capture
        with mock.patch.object(capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
            admission = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
            self.assertEqual((admission["state"], admission["reason"]), ("ready", "blocked_predecessor_recovery_ready"))
            payload = self._payload()
            payload["followups_blocked_predecessor_recovery_admission"] = admission
            successor = capture.begin_cycle_blocked_predecessor_recovery(root, self.plan_ref, payload)
            successor_id = str(successor["capture_cycle_id"])
            replay = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n"
            for role in capture.REQUIRED_ROLES:
                result = capture.process_improvements_collect.collect_process_improvements(
                    project_root=root,
                    role=role,
                    source_ref=self.plan_ref,
                    text=replay,
                    followups_capture_cycle_id=successor_id,
                )
                self.assertEqual(result["process_improvement_capture_state"], "already_tracked")
                self.assertEqual(result["backlog_files"], [])
            capture.checkpoint_general_pi(root, self.plan_ref, successor_id)
            for role in capture.REQUIRED_ROLES:
                capture.prepare_role(root, self.plan_ref, successor_id, role)
                compact = json.dumps(
                    {
                        "role": role,
                        "proposed_rows": [],
                        "role_no_items_reason": f"{role} has no recovery fixture rows.",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                capture.submit_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=successor_id,
                    role=role,
                    raw_input=compact,
                    write=True,
                )
                capture.bind_ordinary_v2(
                    root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=successor_id,
                    role=role,
                    submission_current=True,
                    write=True,
                )
            capture.freeze_ordinary_v2(
                root,
                plan_ref=self.plan_ref,
                capture_cycle_id=successor_id,
                write=True,
            )
            readback = capture.read_capture(
                root,
                self.plan_ref,
                successor_id,
                semantic_fields=("Done", "done", "already_materialized"),
            )
        return readback, profile

    def _family_path(self, root: Path) -> Path:
        return root / ".tmp/followups_capture" / Path(self.plan_ref).stem

    def _cycle_path(self, root: Path, cycle_id: str) -> Path:
        return self._family_path(root) / cycle_id

    def _snapshot_tree(self, root: Path) -> dict[str, tuple[str, bytes | str]]:
        """Capture every mutable recovery surface without following symlinks."""

        snapshot: dict[str, tuple[str, bytes | str]] = {}

        def visit(path: Path) -> None:
            rel_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[rel_path] = ("symlink", os.readlink(path))
            elif path.is_dir():
                snapshot[rel_path] = ("directory", "")
                for child in sorted(path.iterdir(), key=lambda item: item.name):
                    visit(child)
            elif path.is_file():
                snapshot[rel_path] = ("regular", path.read_bytes())
            else:
                snapshot[rel_path] = ("other", "")

        for rel_path in (
            f".tmp/followups_capture/{Path(self.plan_ref).stem}",
            ".tmp/process_improvements_capture",
            "docs/followups",
            "docs/process_improvements",
        ):
            path = root / rel_path
            if path.exists() or path.is_symlink():
                visit(path)
        return snapshot

    def _regular_tree_bytes(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
            if path.is_file() and not path.is_symlink()
        }

    def _mutate_predecessor(
        self,
        root: Path,
        cycle_id: str,
        mutate: Callable[[dict[str, object]], None],
    ) -> bytes:
        """Publish one syntactically valid synthetic receipt mutation for a branch test."""

        capture = MODULE.followups_capture
        with capture.CaptureHost(root, self.plan_ref) as host:
            cycle_fd, _identity = capture._open_cycle(host, cycle_id)
            try:
                receipt, raw, _receipt_identity = capture._read_receipt(cycle_fd, self.plan_ref, cycle_id)
                next_receipt = capture._next_receipt(receipt)
                mutate(next_receipt)
                capture._publish_mutation(host, cycle_fd, cycle_id, raw, next_receipt)
            finally:
                os.close(cycle_fd)
        return (self._cycle_path(root, cycle_id) / capture.RECEIPT_NAME).read_bytes()

    def _profile_with_current_receipt(
        self,
        profile: dict[str, str],
        raw: bytes,
    ) -> dict[str, str]:
        current = dict(profile)
        current["predecessor_receipt_sha256"] = MODULE.followups_capture._sha256(raw)
        return current

    def _start_second_nonfinalized_candidate(self, root: Path) -> str:
        """Create an independently valid second candidate before applying the fixture profile."""

        capture = MODULE.followups_capture
        payload = self._payload()
        payload["followups_bootstrap_admission"] = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
        return str(capture.begin_cycle(root, self.plan_ref, payload)["capture_cycle_id"])

    def _assert_recovery_rejected_without_mutation(
        self,
        root: Path,
        *,
        predecessor_id: str,
        profile: dict[str, str],
        expected_reason: str,
        expected_state: str = "blocked",
        expected_dedicated_reason: str = "followup_capture_blocked_predecessor_recovery_admission_invalid",
    ) -> None:
        """Every negative branch must fail before any successor or durable publication."""

        capture = MODULE.followups_capture
        family = self._family_path(root)
        predecessor_path = self._cycle_path(root, predecessor_id)
        predecessor_receipt = predecessor_path / capture.RECEIPT_NAME
        before_tree = self._snapshot_tree(root)
        before_predecessor = self._regular_tree_bytes(predecessor_path)
        before_receipt = predecessor_receipt.read_bytes()
        before_cycle_names = sorted(path.name for path in family.iterdir())

        with mock.patch.object(capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
            recovery = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
            self.assertEqual((recovery["state"], recovery["reason"]), (expected_state, expected_reason))

            with self.assertRaises(capture.CaptureError) as bare:
                capture.begin_cycle(root, self.plan_ref, self._payload())
            self.assertEqual(bare.exception.reason_code, "followup_capture_blocked_predecessor_recovery_required")

            recovery_payload = self._payload()
            recovery_payload["followups_blocked_predecessor_recovery_admission"] = recovery
            with self.assertRaises(capture.CaptureError) as dedicated:
                capture.begin_cycle_blocked_predecessor_recovery(root, self.plan_ref, recovery_payload)
            self.assertEqual(
                dedicated.exception.reason_code,
                expected_dedicated_reason,
            )

        self.assertEqual(sorted(path.name for path in family.iterdir()), before_cycle_names)
        self.assertEqual(predecessor_receipt.read_bytes(), before_receipt)
        self.assertEqual(self._regular_tree_bytes(predecessor_path), before_predecessor)
        self.assertEqual(self._snapshot_tree(root), before_tree)

    def test_absent_profile_is_explicit_not_applicable_and_ordinary_bootstrap_stays_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            recovery = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
            bootstrap = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
            payload = self._payload()
            payload["followups_bootstrap_admission"] = bootstrap
            started = MODULE.followups_capture.begin_cycle(root, self.plan_ref, payload)

        self.assertEqual((recovery["state"], recovery["reason"]), ("not_applicable", "no_blocked_predecessor"))
        self.assertIsNone(recovery["source_terminal_commit_oid"])
        self.assertIsNone(recovery["predecessor_capture_cycle_id"])
        self.assertEqual((bootstrap["state"], bootstrap["reason"]), ("ready", "missing_v2_frozen_manifest"))
        self.assertEqual(started["state"], "started")

    def test_present_malformed_profile_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            capture = MODULE.followups_capture
            with mock.patch.object(capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: {}}):
                recovery = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
                bootstrap = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
                with self.assertRaises(capture.CaptureError):
                    capture.begin_cycle(root, self.plan_ref, self._payload())

        self.assertEqual((recovery["state"], recovery["reason"]), ("blocked", "recovery_source_identity_invalid"))
        self.assertEqual((bootstrap["state"], bootstrap["reason"]), ("blocked", "bootstrap_blocked_predecessor_present"))

    def test_blocked_predecessor_recovery_negative_matrix_is_fail_closed_without_mutation(self) -> None:
        """Each non-exact recovery shape remains blocked before a successor can publish."""

        cases = (
            "ambiguous_candidates",
            "malformed_candidate",
            "foreign_profile",
            "wrong_reason",
            "partially_completed",
            "ordinary_marker",
            "manifest_present",
            "final_pi_objects",
            "checkpoint_missing",
            "checkpoint_drift",
            "current_pi_drift",
            "dirty_followups_baseline",
            "transaction_drift",
            "worktree_source_drift",
            "terminal_commit_drift",
        )
        expected_reasons = {
            "ambiguous_candidates": "recovery_predecessor_ambiguous",
            "malformed_candidate": "recovery_capture_invalid",
            "foreign_profile": "recovery_predecessor_foreign",
            "wrong_reason": "recovery_predecessor_topology_invalid",
            "partially_completed": "recovery_predecessor_topology_invalid",
            "ordinary_marker": "recovery_predecessor_marker_present",
            "manifest_present": "recovery_predecessor_manifest_present",
            "final_pi_objects": "recovery_predecessor_topology_invalid",
            "checkpoint_missing": "recovery_predecessor_checkpoint_invalid",
            "checkpoint_drift": "recovery_predecessor_checkpoint_invalid",
            "current_pi_drift": "recovery_predecessor_pi_drift",
            "dirty_followups_baseline": "blocked_predecessor_recovery_ready",
            "transaction_drift": "recovery_predecessor_identity_drift",
            "worktree_source_drift": "recovery_source_identity_invalid",
            "terminal_commit_drift": "recovery_source_identity_invalid",
        }

        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                needs_pi = case in {"final_pi_objects", "checkpoint_drift", "current_pi_drift"}
                predecessor_id, profile, _raw = self._blocked_predecessor(root, materialize_coder_pi=needs_pi)
                capture = MODULE.followups_capture

                if case == "ambiguous_candidates":
                    self._start_second_nonfinalized_candidate(root)
                elif case == "malformed_candidate":
                    (self._family_path(root) / str(uuid.uuid4())).mkdir()
                elif case == "foreign_profile":
                    profile = dict(profile)
                    profile["predecessor_capture_cycle_id"] = str(uuid.uuid4())
                elif case == "wrong_reason":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt.update(reason_code="followup_capture_changed_duplicate"),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "partially_completed":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt.update(completed_roles=["Architect"]),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "ordinary_marker":
                    (self._cycle_path(root, predecessor_id) / capture.ORDINARY_V2_BOUND_DIRECTORY).mkdir()
                elif case == "manifest_present":
                    capture.v2_frozen_manifest_path(root, self.plan_ref).write_text("{}\n", encoding="utf-8")
                elif case == "final_pi_objects":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt.update(
                            pi_ownership_state="finalized",
                            pi_final_objects=dict(receipt["current_process_improvement_files"]),
                        ),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "checkpoint_missing":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt.update(general_pi_checkpoint=None),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "checkpoint_drift":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt["role_results"]["Architect"].update(
                            checkpoint_before_process_improvement_files=dict(receipt["baseline_process_improvement_files"]),
                            prepared_process_improvement_files=dict(receipt["baseline_process_improvement_files"]),
                            process_improvement_path_results=[],
                        ),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "current_pi_drift":
                    receipt = json.loads(
                        (self._cycle_path(root, predecessor_id) / capture.RECEIPT_NAME).read_text(encoding="utf-8")
                    )
                    pi_path = next(iter(receipt["current_process_improvement_files"]))
                    target = root / pi_path
                    target.write_bytes(target.read_bytes() + b"\n")
                elif case == "dirty_followups_baseline":
                    (root / "docs/followups/foreign-drift.md").write_text("# foreign drift\n", encoding="utf-8")
                elif case == "transaction_drift":
                    raw = self._mutate_predecessor(
                        root,
                        predecessor_id,
                        lambda receipt: receipt.update(transaction_host_identity={"root": "drift"}),
                    )
                    profile = self._profile_with_current_receipt(profile, raw)
                elif case == "worktree_source_drift":
                    plan_path = root / self.plan_ref
                    plan_path.write_bytes(plan_path.read_bytes() + b"\n")
                elif case == "terminal_commit_drift":
                    plan_path = root / self.plan_ref
                    plan_path.write_bytes(plan_path.read_bytes() + b"\n")
                    self._git(root, "add", self.plan_ref)
                    self._git(root, "commit", "-qm", "terminal source drift")
                else:  # pragma: no cover - exhaustive literal case matrix above
                    self.fail(f"unhandled recovery matrix case: {case}")

                self._assert_recovery_rejected_without_mutation(
                    root,
                    predecessor_id=predecessor_id,
                    profile=profile,
                    expected_reason=expected_reasons[case],
                    expected_state="ready" if case == "dirty_followups_baseline" else "blocked",
                    expected_dedicated_reason=(
                        "followup_capture_blocked_predecessor_recovery_followups_drift"
                        if case == "dirty_followups_baseline"
                        else "followup_capture_blocked_predecessor_recovery_admission_invalid"
                    ),
                )

    def test_exact_blocked_predecessor_preempts_bootstrap_and_starts_fresh_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            predecessor_id, profile, predecessor_raw = self._blocked_predecessor(root)
            with mock.patch.object(MODULE.followups_capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
                admission = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
                self.assertEqual(admission["state"], "ready")
                self.assertEqual(admission["reason"], "blocked_predecessor_recovery_ready")
                bootstrap = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)
                self.assertEqual(bootstrap["state"], "blocked")
                self.assertEqual(bootstrap["reason"], "bootstrap_blocked_predecessor_present")
                before_names = sorted((root / ".tmp/followups_capture" / Path(self.plan_ref).stem).iterdir())
                with self.assertRaises(MODULE.followups_capture.CaptureError) as bare:
                    MODULE.followups_capture.begin_cycle(root, self.plan_ref, self._payload())
                self.assertEqual(bare.exception.reason_code, "followup_capture_blocked_predecessor_recovery_required")
                self.assertEqual(sorted((root / ".tmp/followups_capture" / Path(self.plan_ref).stem).iterdir()), before_names)
                recovery_payload = self._payload()
                recovery_payload["followups_blocked_predecessor_recovery_admission"] = admission
                successor = MODULE.followups_capture.begin_cycle_blocked_predecessor_recovery(
                    root,
                    self.plan_ref,
                    recovery_payload,
                )
                successor_id = str(successor["capture_cycle_id"])
                successor_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / successor_id / MODULE.followups_capture.RECEIPT_NAME
                receipt = json.loads(successor_path.read_text(encoding="utf-8"))
                binding = receipt[MODULE.followups_capture.BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY]
                self._assert_recovery_rejected_without_mutation(
                    root,
                    predecessor_id=predecessor_id,
                    profile=profile,
                    expected_reason="recovery_already_consumed",
                )

            predecessor_path = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / predecessor_id / MODULE.followups_capture.RECEIPT_NAME
            self.assertNotEqual(successor_id, predecessor_id)
            self.assertIsNone(receipt["retry_of_capture_cycle_id"])
            self.assertEqual(receipt["pi_lineage_root_cycle_id"], successor_id)
            self.assertEqual(receipt["pi_adopted_from_cycle_ids"], [])
            self.assertEqual(binding["predecessor_capture_cycle_id"], predecessor_id)
            self.assertEqual(predecessor_path.read_bytes(), predecessor_raw)

    def test_recovery_replay_pi_ownership_projects_the_exact_staging_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            capture, profile = self._completed_recovery_replay(root)
            with mock.patch.object(MODULE.followups_capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
                pi_capture = MODULE.classify_process_improvement_capture(
                    root,
                    self.plan_ref,
                    capture_cycle_id=str(capture["capture_cycle_id"]),
                )
                proof = MODULE.followups_capture.process_improvement_staging_proof(
                    root,
                    self.plan_ref,
                    capture_binding=capture,
                )
                dirty_paths = proof["cycle_proof"]["changed_data_paths"]
                projection = MODULE.classify_followups_capture(
                    root=root,
                    plan_ref=self.plan_ref,
                    capture_cycle_id=str(capture["capture_cycle_id"]),
                    semantic_fields=("Done", "done", "already_materialized"),
                    pi_capture=pi_capture,
                    docs_status_snapshot=(dirty_paths, True),
                )

        expected = sorted(MODULE.followups_capture._process_improvement_data_paths(self.plan_ref))
        self.assertEqual(pi_capture["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(pi_capture["process_improvement_backlog_paths"], [])
        self.assertEqual(proof["proof_kind"], "recovery_replay")
        self.assertEqual(proof["backlog_path"], expected[0])
        self.assertEqual(projection["followups_capture_state"], "materialized")
        self.assertEqual(projection["current_plan_owned_docs_delta_paths"], expected)
        self.assertEqual(projection["blocked_docs_delta_paths"], [])
        self.assertEqual(
            [item["path"] for item in projection["followups_staging_expectations"]],
            expected,
        )

    def test_recovery_replay_pi_ownership_matrix_fails_closed(self) -> None:
        cases = (
            "ordinary_empty_union",
            "binding_source_drift",
            "current_map_drift",
            "checkpoint_missing",
            "mixed_receipt_chain",
            "nonempty_receipt_chain",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                capture, profile = self._completed_recovery_replay(root)
                candidate = json.loads(json.dumps(capture))
                if case == "ordinary_empty_union":
                    candidate.pop(MODULE.followups_capture.BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY)
                elif case == "binding_source_drift":
                    binding = candidate[MODULE.followups_capture.BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY]
                    binding["source_plan_sha256"] = "0" * 64
                elif case == "current_map_drift":
                    candidate["current_process_improvement_files"] = {}
                elif case == "checkpoint_missing":
                    candidate["general_pi_checkpoint"] = None
                elif case in {"mixed_receipt_chain", "nonempty_receipt_chain"}:
                    receipt_path = (
                        root
                        / MODULE.process_improvements_collect.capture_receipt_rel_path(
                            self.plan_ref,
                            "Architect",
                            str(capture["capture_cycle_id"]),
                        )
                    )
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if case == "mixed_receipt_chain":
                        receipt["capture_state"] = "clean_noop"
                        receipt["reason_code"] = "clean_run"
                    else:
                        receipt["backlog_paths"] = [
                            str(MODULE.process_improvements_collect.backlog_rel_path_for_source_ref(self.plan_ref))
                        ]
                    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                else:  # pragma: no cover - exhaustive literal matrix above
                    self.fail(f"unhandled recovery replay case: {case}")
                before = self._snapshot_tree(root)
                with mock.patch.object(MODULE.followups_capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
                    with self.assertRaises(MODULE.followups_capture.CaptureError):
                        MODULE.followups_capture.process_improvement_staging_proof(
                            root,
                            self.plan_ref,
                            capture_binding=candidate,
                        )
                self.assertEqual(self._snapshot_tree(root), before)

    def test_recovery_replay_staging_rejects_foreign_or_unknown_pi_paths(self) -> None:
        for case in ("foreign_backlog", "unknown_path"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = self._root(tmpdir)
                capture, profile = self._completed_recovery_replay(root)
                expected = MODULE.followups_capture._process_improvement_data_paths(self.plan_ref)
                if case == "foreign_backlog":
                    foreign = root / "docs/process_improvements/260821_9999_foreign__process_improvements_backlog.md"
                    foreign.write_text("# foreign backlog\n", encoding="utf-8")
                    paths = expected
                else:
                    paths = [*expected, "docs/process_improvements/unknown.md"]
                before = self._snapshot_tree(root)
                with mock.patch.object(MODULE.followups_capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
                    with self.assertRaises(MODULE.followups_capture.CaptureError):
                        MODULE.followups_capture.process_improvement_staging_expectations(
                            root,
                            self.plan_ref,
                            paths,
                            capture_binding=capture,
                        )
                self.assertEqual(self._snapshot_tree(root), before)

    def test_present_invalid_predecessor_never_falls_back_to_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._root(tmpdir)
            predecessor_id, profile, _raw = self._blocked_predecessor(root)
            marker = root / ".tmp/followups_capture" / Path(self.plan_ref).stem / predecessor_id / MODULE.followups_capture.ORDINARY_V2_BOUND_DIRECTORY
            marker.mkdir()
            with mock.patch.object(MODULE.followups_capture, "BLOCKED_PREDECESSOR_RECOVERY_PROFILES", {self.plan_ref: profile}):
                recovery = MODULE.classify_followups_blocked_predecessor_recovery(root, self.plan_ref)
                bootstrap = MODULE.classify_followups_bootstrap_admission(root, self.plan_ref)

        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["reason"], "recovery_predecessor_marker_present")
        self.assertEqual(bootstrap["state"], "blocked")
        self.assertEqual(bootstrap["reason"], "bootstrap_blocked_predecessor_present")


class DocsCloseoutV1CompatibilityTests(unittest.TestCase):
    plan_ref = "docs/plans/270101_0105_v1_terminal_fixture.md"
    owner_ref = "docs/plans/270101_0106_v1_owner_fixture.md"
    delivery_ref = "docs/plans/270101_0107_v1_delivery_fixture.md"
    carrier_ref = "docs/followups/270101_0105_v1_compatibility.md"

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _setup_source(self, root: Path) -> tuple[list[dict[str, object]], str]:
        (root / "docs/plans").mkdir(parents=True)
        (root / "docs/followups").mkdir(parents=True)
        rows: list[dict[str, object]] = [
            {
                "summary": "Keep the one deferred command-owner item external",
                "plan": None,
                "status": "open",
                "reason": "awaiting compatibility proof",
            },
            {
                "summary": "Keep the terminal delivery evidence external",
                "plan": None,
                "status": "open",
                "reason": "awaiting compatibility proof",
            },
        ]
        source = root / self.plan_ref
        source.write_text(
            "# terminal source\n\n"
            "**Status:** Done\n"
            "**Schema version:** plan.v1\n\n"
            "```json\n"
            + json.dumps({"plan_meta": {"followups_out": rows}}, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        (root / self.owner_ref).write_text("# deferred owner\n\n**Status:** In progress\n", encoding="utf-8")
        (root / self.delivery_ref).write_text("# terminal delivery\n\n**Status:** Done\n", encoding="utf-8")
        self._git(root, "init", "-q")
        self._git(root, "config", "user.name", "Fixture")
        self._git(root, "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'test')
        self._git(root, "add", ".")
        self._git(root, "commit", "-qm", "v1 compatibility source")
        return rows, self._git(root, "rev-parse", "HEAD")

    def _payload(
        self,
        root: Path,
        rows: list[dict[str, object]],
        commit: str,
        *,
        index: int,
        status: str = "open",
    ) -> dict[str, object]:
        source_bytes = (root / self.plan_ref).read_bytes()
        payload: dict[str, object] = {
            "priority": "P1",
            "summary": str(rows[index - 1]["summary"]),
            "cluster": "process",
            "to": "architect",
            "status": status,
            "plan": None,
            "why": "prove terminal V1 compatibility from current durable bytes",
            "tags": ["v1-compatibility"],
            "item_id": f"v1-compatibility-{index}",
            "source_ref": self.plan_ref,
            "disposition_kind": None,
            "disposition_ref": None,
            "disposition_commit_oid": None,
            "reason": None,
            "legacy_row_ref": f"plan_meta.followups_out[{index}]",
            "legacy_plan_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "legacy_row_sha256": hashlib.sha256(
                json.dumps(rows[index - 1], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }
        if status == "cancelled":
            payload.update(
                {
                    "disposition_kind": "cancelled_decision",
                    "disposition_ref": f"{self.owner_ref}#plan_meta.followups_out[4]",
                    "disposition_commit_oid": commit,
                    "reason": "the deferred owner remains the one live owner",
                }
            )
        elif status == "handled":
            payload.update(
                {
                    "disposition_kind": "terminal_delivery",
                    "disposition_ref": self.delivery_ref,
                    "disposition_commit_oid": commit,
                    "reason": "the terminal delivery is already durable",
                }
            )
        return payload

    def _write_carrier(self, root: Path, payloads: list[dict[str, object]], *, rel_path: str | None = None) -> Path:
        path = root / (rel_path or self.carrier_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# fixture compatibility\n\n"
            "**Schema version:** followups.v2\n\n"
            "## Follow-ups\n"
            + "\n".join(MODULE.followups_lint.render_v2_row(payload) for payload in payloads)
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_v1_compatibility_requires_complete_current_inventory_and_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rows, commit = self._setup_source(root)
            source_before = (root / self.plan_ref).read_bytes()
            first = self._payload(root, rows, commit, index=1)
            second = self._payload(root, rows, commit, index=2)

            missing = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((missing["state"], missing["reason"]), ("open", "open_plan_meta_followups_out"))

            self._write_carrier(root, [first])
            partial = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((partial["state"], partial["reason"]), ("open", "open_plan_meta_followups_out"))

            self._write_carrier(root, [first, second])
            with mock.patch.object(
                MODULE.followups_lint,
                "v2_row_digest",
                wraps=MODULE.followups_lint.v2_row_digest,
            ) as digest:
                complete = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((complete["state"], complete["reason"]), ("external_clean", "exact_legacy_v2_bridge_proof"))
            self.assertEqual(complete["open_items"], [])
            self.assertFalse((root / ".tmp/followups_capture").exists())
            self.assertEqual([row["v2_status"] for row in complete["closed_or_promoted_items"]], ["open", "open"])
            self.assertEqual(
                [row["legacy_plan_sha256"] for row in complete["closed_or_promoted_items"]],
                [hashlib.sha256(source_before).hexdigest(), hashlib.sha256(source_before).hexdigest()],
            )
            self.assertEqual(
                [row["legacy_row_sha256"] for row in complete["closed_or_promoted_items"]],
                [
                    hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                    for row in rows
                ],
            )
            self.assertEqual(
                [row["applied_row_digest"] for row in complete["closed_or_promoted_items"]],
                [MODULE.followups_lint.v2_row_digest(first), MODULE.followups_lint.v2_row_digest(second)],
            )
            self.assertEqual(digest.call_count, 2)
            self.assertEqual((root / self.plan_ref).read_bytes(), source_before)

            (root / "docs/followups/v1-companion.md").write_text(
                "# V1 compatibility\n\n**Schema version:** followups.v1\n\n## Follow-ups\n- P1 [ ] malformed V1 row\n",
                encoding="utf-8",
            )
            compatible = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual(compatible["state"], "external_clean")

    def test_v1_compatibility_fails_closed_for_invalid_or_summary_only_candidates(self) -> None:
        invalidators: dict[str, Callable[[dict[str, object]], None]] = {
            "wrong_source": lambda payload: payload.update(source_ref=f"{self.plan_ref}#not-a-legacy-source"),
            "wrong_row_ref": lambda payload: payload.update(legacy_row_ref="plan_meta.followups_out[3]"),
            "stale_plan_hash": lambda payload: payload.update(legacy_plan_sha256="a" * 64),
            "stale_row_hash": lambda payload: payload.update(legacy_row_sha256="b" * 64),
        }
        for name, invalidate in invalidators.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                rows, commit = self._setup_source(root)
                first = self._payload(root, rows, commit, index=1)
                second = self._payload(root, rows, commit, index=2)
                invalidate(second)
                self._write_carrier(root, [first, second])
                result = MODULE.classify_followups_reconciliation(root, self.plan_ref)
                self.assertEqual((result["state"], result["reason"]), ("external_invalid", "v2_integrity_blocker"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rows, commit = self._setup_source(root)
            summary_only = self._payload(root, rows, commit, index=1)
            for field in ("legacy_row_ref", "legacy_plan_sha256", "legacy_row_sha256"):
                summary_only.pop(field)
            self._write_carrier(root, [summary_only])
            result = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((result["state"], result["reason"]), ("open", "open_plan_meta_followups_out"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rows, commit = self._setup_source(root)
            first = self._payload(root, rows, commit, index=1)
            second = self._payload(root, rows, commit, index=2)
            self._write_carrier(root, [first, first, second])
            duplicate = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((duplicate["state"], duplicate["reason"]), ("external_invalid", "v2_integrity_blocker"))

            (root / "docs/followups/foreign.md").write_text(
                "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n",
                encoding="utf-8",
            )
            foreign = MODULE.classify_followups_reconciliation(root, self.plan_ref)
            self.assertEqual((foreign["state"], foreign["reason"]), ("external_invalid", "v2_integrity_blocker"))

    def test_v1_compatibility_exposes_non_open_v2_proof_without_new_terminal_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rows, commit = self._setup_source(root)
            cancelled = self._payload(root, rows, commit, index=1, status="cancelled")
            handled = self._payload(root, rows, commit, index=2, status="handled")
            self._write_carrier(root, [cancelled, handled])

            result = MODULE.classify_followups_reconciliation(root, self.plan_ref)

        self.assertEqual((result["state"], result["reason"]), ("external_clean", "exact_legacy_v2_bridge_proof"))
        self.assertEqual(result["open_items"], [])
        self.assertEqual(
            result["proof_host"],
            "docs/followups/270101_0105_v1_compatibility.md#v1-compatibility-1|"
            "docs/followups/270101_0105_v1_compatibility.md#v1-compatibility-2",
        )
        self.assertEqual(
            [row["v2_status"] for row in result["closed_or_promoted_items"]],
            ["cancelled", "handled"],
        )
        self.assertEqual(result["closed_or_promoted_items"][0]["v2_disposition_ref"], f"{self.owner_ref}#plan_meta.followups_out[4]")
        self.assertEqual(result["closed_or_promoted_items"][1]["v2_disposition_ref"], self.delivery_ref)


class MachineAuthorityCloseoutAdmissionTests(unittest.TestCase):
    def test_terminal_already_materialized_cannot_bypass_oracle_admission_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'test'], cwd=root, check=True)
            plan_rel = "docs/plans/260814_0917_machine_authority_terminal.md"
            plan = root / plan_rel
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: terminal authority fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Done\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            payload = MODULE.classify_docs_closeout(
                plan_ref=plan_rel,
                bundle_payload={
                    "bundle_ok": True,
                    "closeout_kind": "already_materialized",
                    "repo_roots": [{"repo_root": None, "bundle_paths": []}],
                },
                root=root,
            )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(
            payload["reason_code"],
            "oracle_terminal_admission_blocked:machine_authority_decision_missing_required_carrier",
        )
        self.assertNotEqual(payload["reason_code"], "semantic_closeout_materialized")
        self.assertFalse(payload["runtime_context"]["queue_closeout_ready"])

    def test_current_review_proof_block_is_projected_before_bundle_closeout_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", 'fixture' + '@' + 'example' + '.' + 'test'],
                cwd=root,
                check=True,
            )
            plan_rel = "docs/plans/260817_1047_current_proof_closeout.md"
            plan = root / plan_rel
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: current proof closeout fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Review\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture baseline"], cwd=root, check=True)
            blocked = MODULE.plan_lint.CurrentReviewProofPreflight(
                state="blocked",
                reason_code="current_review_proof_compact_snapshot_invalid",
                message="fixture compact projection is invalid",
                plan_path=str(plan),
                review_path=None,
                target="BUNDLE=current bundle_sha256=" + "a" * 64,
            )
            with mock.patch.object(
                MODULE.plan_lint,
                "preflight_current_review_proof",
                return_value=blocked,
            ):
                payload = MODULE.classify_docs_closeout(
                    plan_ref=plan_rel,
                    bundle_payload={
                        "bundle_ok": True,
                        "closeout_kind": "already_materialized",
                        "repo_roots": [{"repo_root": None, "bundle_paths": []}],
                    },
                    root=root,
                )

        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["reason_code"], "current_review_proof_compact_snapshot_invalid")
        self.assertNotEqual(payload["reason_code"], "semantic_closeout_materialized")


if __name__ == "__main__":
    unittest.main()

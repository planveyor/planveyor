#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import hashlib
import inspect
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from textwrap import dedent
from unittest import mock

try:
    from test_support.process_contract_fixtures import standalone_git_root, temporary_git_root
except ModuleNotFoundError:
    from scripts.test_support.process_contract_fixtures import standalone_git_root, temporary_git_root


MODULE_PATH = Path(__file__).with_name("plan_status_oracle.py")
SPEC = importlib.util.spec_from_file_location("plan_status_oracle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def ensure_fixture_git(root: Path) -> None:
    """Commit the smallest real Git fixture when a test opted into Git."""

    if not (root / ".git").exists():
        return
    # Read only this fixture's metadata: Git discovery would skip an empty
    # .git directory and answer for an enclosing work tree around TMPDIR.
    head = subprocess.run(
        ["git", f"--git-dir={root / '.git'}", "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode == 0:
        return
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", 'oracle' + '@' + 'example' + '.' + 'invalid'], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Oracle fixture"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "--allow-empty", "-m", "fixture"],
        check=True,
    )


def selective_current_bundle_snapshot_run(snapshot: object):
    """Mock only the snapshot helper, leaving authority Git probes real."""

    real_run = MODULE.subprocess.run
    snapshot_helper = str(MODULE_PATH.with_name("review_target_snapshot.py").resolve())

    def run(command: object, *args: object, **kwargs: object) -> object:
        if isinstance(command, (list, tuple)) and snapshot_helper in {
            str(part) for part in command
        }:
            return snapshot
        return real_run(command, *args, **kwargs)

    return mock.patch.object(MODULE.subprocess, "run", side_effect=run)


class PlanStatusOracleTests(unittest.TestCase):
    def _write_plan(self, root: Path, rel_path: str, body: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        ensure_fixture_git(root)
        return path

    def _attach_not_applicable_machine_authority(
        self,
        root: Path,
        plan: Path,
        *,
        draft_targets: list[dict[str, str]] | None = None,
        strict_decomposition_parent: bool = False,
    ) -> None:
        """Make a non-authority fixture explicit at a downstream status."""

        plan_rel = plan.relative_to(root).as_posix()
        decision: dict[str, object] = {
            "schema_version": MODULE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "docs_or_tests_only",
        }
        text = plan.read_text(encoding="utf-8")
        strict = MODULE.strict_plan_meta_json(text)
        if strict.state == "valid" and strict.plan_meta is not None:
            plan_meta = copy.deepcopy(dict(strict.plan_meta))
            plan_meta["machine_authority_decision"] = decision
            meta_heading = text.index("## Meta")
            meta_start = text.index("```json\n", meta_heading) + len("```json\n")
            meta_end = text.index("\n```", meta_start)
            text = (
                text[:meta_start]
                + json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)
                + text[meta_end:]
            )
        else:
            text += "\n## Meta\n```json\n" + json.dumps(
                {"plan_meta": {"machine_authority_decision": decision}},
                ensure_ascii=False,
                indent=2,
            ) + "\n```\n"
        if strict_decomposition_parent:
            meta_heading = text.index("\n## Meta")
            text = (
                text[:meta_heading]
                + "\n**Context links (source of truth):**\n"
                + "- Code draft(s): `N/A (why=fixture decomposition parent)`\n"
                + text[meta_heading:]
            )
        plan.write_text(text, encoding="utf-8")

        if strict_decomposition_parent:
            return

        digest = MODULE.machine_authority_decision_sha256(decision)
        ref: dict[str, object] = {
            "applicability": "not_applicable",
            "reason_code": "docs_or_tests_only",
            "carrier_sha256": digest,
        }
        draft_meta: dict[str, object] = {
            "plan": plan_rel,
            "machine_authority_decision_ref": ref,
        }
        if draft_targets is not None:
            draft_meta.update(
                {
                    "cluster": "process",
                    "targets": draft_targets,
                    "deleted_paths": [],
                }
            )
        draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: explicit N-A fixture\n\n```json\n"
            + json.dumps({"code_draft_meta": draft_meta}, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )

    def _json_payload(self, plan: Path) -> dict[str, object]:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = MODULE.main([str(plan), "--json"])
        self.assertEqual(result, 0)
        return json.loads(stdout.getvalue())

    def _current_state_payload(self, plan: Path) -> dict[str, object]:
        payload = self._json_payload(plan)
        current_state = payload["current_state"]
        self.assertIsInstance(current_state, dict)
        return current_state

    def _current_state_plain(self, plan: Path) -> dict[str, str]:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = MODULE.main([str(plan), "--current-state"])
        self.assertEqual(result, 0)
        return dict(line.split("=", 1) for line in stdout.getvalue().splitlines())

    def _write_plan_vocab(self, root: Path) -> None:
        vocab_path = root / "docs/_meta/plan_vocab.json"
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        vocab_path.write_text(
            json.dumps(
                {
                    "planning_contour": {
                        "accepted_routes": [
                            "developer_wave",
                            "decomposition_wave",
                            "human_gate",
                            "defer",
                            "reject",
                        ],
                        "promoted_artifact_kinds": [
                            "seed_dev_plan",
                            "decomposition_umbrella",
                            "owner_gate",
                            "followup",
                            "rejection_receipt",
                        ],
                        "queue_admission": [
                            "queueable_now",
                            "needs_planner",
                            "needs_owner",
                            "not_queueable",
                        ],
                        "runner_admission": [
                            "frontier_only",
                            "small_runner_ok",
                            "small_runner_blocked",
                        ],
                        "queue_activation_states": [
                            "not_requested",
                            "owner_approved",
                            "architect_approved",
                            "n/a",
                        ],
                        "scope_expansion_states": [
                            "n/a",
                            "suspected",
                            "reroute_required",
                            "architect_accepted",
                        ],
                        "analysis_route_lifecycle_states": [
                            "ok",
                            "warning",
                            "architect_stop",
                            "stale_needs_architect_review",
                            "not_applicable",
                        ],
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        ensure_fixture_git(root)

    def _write_accepted_red_fixture(
        self,
        root: Path,
        *,
        scope_state: str = "architect_accepted",
        successor_count: int = 1,
        backlink_matches: bool = True,
        review_red: bool = True,
        blocker_ids: tuple[str, ...] = ("B1", "B2", "B3"),
        inherited_ids: tuple[str, ...] | None = None,
        source_ref_id: str | None = None,
        historical_text: str = "",
        review_directory: str = "docs/code_reviews",
        review_label: str = "Code review (primary)",
    ) -> tuple[Path, str]:
        source_rel = "docs/plans/accepted_red_fixture.md"
        successor_rel = "docs/plans/accepted_red_successor_fixture.md"
        draft_rel = "docs/code_drafts/accepted_red_fixture__code_draft.md"
        review_rel = f"{review_directory}/accepted_red_fixture.md"
        review_sha = "a" * 64
        inherited_ids = blocker_ids if inherited_ids is None else inherited_ids
        source_ref_id = source_ref_id or blocker_ids[-1]
        next_plans = [successor_rel] if successor_count == 1 else [successor_rel, "docs/plans/other.md"]
        meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": next_plans,
                "scope_expansion": {
                    "state": scope_state,
                    "target_contour": "decomposition_wave",
                    "source_ref": f"{review_rel}#{source_ref_id}",
                    "reason": "accepted fixture",
                },
            }
        }
        plan = self._write_plan(
            root,
            source_rel,
            "# Plan: accepted red fixture\n\n"
            "**Plan type:** dev\n"
            "**Status:** Superseded\n\n"
            f"```json\n{json.dumps(meta, indent=2)}\n```\n\n"
            "## Review artifacts\n"
            f"- {review_label}: `{review_rel}`\n",
        )
        draft_meta = {
            "code_draft_meta": {
                "plan": source_rel,
                "cluster": "process",
                "targets": [{"path": "scripts/rejected.py", "kind": "py"}],
                "deleted_paths": [],
            }
        }
        self._write_plan(root, draft_rel, f"# Draft\n\n```json\n{json.dumps(draft_meta, indent=2)}\n```\n")
        successor_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": source_rel if backlink_matches else "docs/plans/wrong.md",
                "next_plans": [],
                "scope_expansion": {"state": "n/a"},
            }
        }
        self._write_plan(
            root,
            successor_rel,
            "# Successor\n\n"
            + "".join(f"`{review_rel}#{blocker}`\n" for blocker in inherited_ids)
            + "\n"
            f"```json\n{json.dumps(successor_meta, indent=2)}\n```\n",
        )
        blocker_sections = "\n\n".join(
            f"### {blocker}) blocker {blocker[1:]}\n\n"
            f"- Blocker ID: `{blocker}`\n"
            "- Current state: `open`"
            for blocker in blocker_ids
        )
        self._write_plan(
            root,
            review_rel,
            "# Review\n\n"
            f"**Target:** BUNDLE=current bundle_sha256={review_sha}\n"
            f"**Status:** {'❌ S1 blocker(ы)' if review_red else '✅ OK'}\n\n"
            f"## S1 Blocker\n\n{blocker_sections}\n"
            f"{historical_text}",
        )
        self._write_plan(root, "scripts/rejected.py", "print('rejected')\n")
        return plan, review_sha

    def _git(self, root: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _topology_entry_with_digest(
        self,
        entry: object,
        **changes: object,
    ) -> object:
        candidate = replace(entry, **changes, entry_sha256="")
        digest = hashlib.sha256(
            json.dumps(
                MODULE._accepted_red_topology_rebind_identity(candidate),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return replace(candidate, entry_sha256=digest)

    def _write_topology_rebind_fixture(
        self,
        root: Path,
    ) -> tuple[object, str, str]:
        source_rel = "docs/plans/fixture_topology_source.md"
        successor_rel = "docs/plans/fixture_topology_successor.md"
        source_draft = f"docs/code_drafts/{Path(source_rel).stem}__code_draft.md"
        successor_draft = f"docs/code_drafts/{Path(successor_rel).stem}__code_draft.md"
        source_review = f"docs/code_reviews/{Path(source_rel).stem}.md"
        successor_review = f"docs/code_reviews/{Path(successor_rel).stem}.md"
        target_paths = (
            "scripts/fixture_topology_alpha.py",
            "scripts/fixture_topology_beta.py",
        )

        def write(rel: str, body: str) -> None:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

        source_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": [successor_rel],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": [],
                "scope_expansion": {
                    "state": "architect_accepted",
                    "target_contour": "decomposition_wave",
                    "source_ref": f"{source_review}#B1",
                    "reason": "fixture topology rebind",
                },
            }
        }
        successor_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": [],
                "depends_on": [source_rel],
                "followups_out": [],
                "canon_updates": [],
                "scope_expansion": {"state": "n/a"},
            }
        }
        source_draft_meta = {
            "code_draft_meta": {
                "plan": source_rel,
                "cluster": "process",
                "targets": [{"path": path, "kind": "py"} for path in target_paths],
                "deleted_paths": [],
            }
        }
        successor_draft_meta = {
            "code_draft_meta": {
                "plan": successor_rel,
                "cluster": "process",
                "targets": [],
                "deleted_paths": [],
            }
        }

        write(
            source_rel,
            "# Plan: fixture topology source\n\n"
            "**Plan type:** dev\n"
            "**Status:** Superseded\n\n"
            f"```json\n{json.dumps(source_meta, indent=2)}\n```\n\n"
            "## Review artifacts\n"
            f"- Code review (primary): `{source_review}`\n",
        )
        write(
            successor_rel,
            "# Plan: fixture topology successor\n\n"
            "**Plan type:** dev\n"
            "**Status:** Done\n\n"
            f"`{source_review}#B1`\n\n"
            f"```json\n{json.dumps(successor_meta, indent=2)}\n```\n",
        )
        write(source_draft, f"# Draft\n\n```json\n{json.dumps(source_draft_meta, indent=2)}\n```\n")
        write(
            successor_draft,
            f"# Draft\n\n```json\n{json.dumps(successor_draft_meta, indent=2)}\n```\n",
        )

        def source_review_text(bundle_sha256: str) -> str:
            return (
                "# Review\n\n"
                f"**Target:** BUNDLE=current bundle_sha256={bundle_sha256}\n"
                "**Status:** ❌ S1 blocker\n\n"
                "## S1 Blocker\n\n"
                "### B1) fixture blocker\n\n"
                "- Blocker ID: `B1`\n"
                "- Current state: `open`\n"
            )

        write(source_review, source_review_text("0" * 64))
        write(
            successor_review,
            "# Review\n\n"
            "**Status:** ✅ OK\n",
        )
        write(target_paths[0], "print('fixture topology alpha')\n")
        write(target_paths[1], "print('fixture topology beta')\n")

        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "target snapshot")
        target_commit = self._git(root, "rev-parse", "HEAD")
        target_snapshot_ref = "refs/planveyor/recovery-inputs/fixture/targets"
        self._git(root, "update-ref", target_snapshot_ref, target_commit)
        target_bundle, target_records = MODULE._accepted_red_revision_bundle(
            root,
            target_commit,
            target_paths,
        )

        write(source_review, source_review_text(target_bundle))
        self._git(root, "add", source_review)
        self._git(root, "commit", "-m", "carrier set")
        carrier_commit = self._git(root, "rev-parse", "HEAD")
        carrier_set_ref = "refs/planveyor/recovery-inputs/fixture/carrier-set-v1"
        self._git(root, "update-ref", carrier_set_ref, carrier_commit)

        entry = MODULE.AcceptedRedSuccessorTopologyRebind(
            schema="planveyor_accepted_red_successor_topology_rebind.v1",
            rebind_id="fixture-topology-rebind",
            source_plan=source_rel,
            source_draft_rule="same_stem_code_draft",
            source_review=source_review,
            source_review_bundle_sha256=target_bundle,
            source_open_blockers=("B1",),
            source_scope_ref=f"{source_review}#B1",
            successor_plan=successor_rel,
            successor_commit=carrier_commit,
            successor_plan_blob_oid=self._git(
                root,
                "rev-parse",
                f"{carrier_commit}:{successor_rel}",
            ),
            successor_review=successor_review,
            successor_review_blob_oid=self._git(
                root,
                "rev-parse",
                f"{carrier_commit}:{successor_review}",
            ),
            successor_expected_parent=None,
            successor_requires_source_in_depends_on=True,
            carrier_set_ref=carrier_set_ref,
            carrier_set_commit=carrier_commit,
            carrier_set_tree=self._git(root, "rev-parse", f"{carrier_commit}^{{tree}}"),
            carrier_set_parent=target_commit,
            carrier_paths=(
                "@source_same_stem_code_draft",
                "@successor_same_stem_code_draft",
                source_review,
                successor_review,
                source_rel,
                successor_rel,
            ),
            target_snapshot_ref=target_snapshot_ref,
            target_snapshot_commit=target_commit,
            targets=target_records,
            entry_sha256="",
        )
        entry = self._topology_entry_with_digest(entry)
        return entry, source_rel, successor_rel

    def _topology_rebind_semantic_mutation_cases(
        self,
        entry: object,
    ) -> tuple[tuple[str, object], ...]:
        """Return one-field frozen-identity drift cases with fresh digests."""

        def candidate(name: str, **changes: object) -> tuple[str, object]:
            return name, self._topology_entry_with_digest(entry, **changes)

        cases: list[tuple[str, object]] = [
            candidate("schema", schema="planveyor_accepted_red_successor_topology_rebind.v2"),
            candidate("source_plan", source_plan="docs/plans/other-source.md"),
            candidate("source_draft_rule", source_draft_rule="other_draft_rule"),
            candidate("source_review", source_review="docs/code_reviews/other-source.md"),
            candidate("source_review_bundle", source_review_bundle_sha256="0" * 64),
            candidate("source_open_blockers", source_open_blockers=("B7",)),
            candidate(
                "source_scope_ref",
                source_scope_ref=f"{entry.source_review}#B7",
            ),
            candidate("successor_plan", successor_plan="docs/plans/other-successor.md"),
            candidate("successor_commit", successor_commit="0" * 40),
            candidate("successor_plan_blob", successor_plan_blob_oid="0" * 40),
            candidate("successor_review", successor_review="docs/code_reviews/other-successor.md"),
            candidate("successor_review_blob", successor_review_blob_oid="0" * 40),
            candidate("successor_expected_parent", successor_expected_parent="unexpected"),
            candidate(
                "successor_depends_requirement",
                successor_requires_source_in_depends_on=False,
            ),
            candidate(
                "carrier_set_ref",
                carrier_set_ref="refs/planveyor/recovery-inputs/fixture/other-carrier-set",
            ),
            candidate("carrier_set_commit", carrier_set_commit="0" * 40),
            candidate("carrier_set_tree", carrier_set_tree="0" * 40),
            candidate("carrier_set_parent", carrier_set_parent="0" * 40),
            candidate(
                "target_snapshot_ref",
                target_snapshot_ref="refs/planveyor/recovery-inputs/fixture/other-targets",
            ),
            candidate("target_snapshot_commit", target_snapshot_commit="0" * 40),
            candidate(
                "carrier_source_token",
                carrier_paths=(
                    "@unknown_source_draft",
                    *entry.carrier_paths[1:],
                ),
            ),
            candidate(
                "carrier_successor_token",
                carrier_paths=(
                    entry.carrier_paths[0],
                    "@unknown_successor_draft",
                    *entry.carrier_paths[2:],
                ),
            ),
            candidate(
                "carrier_membership",
                carrier_paths=(
                    *entry.carrier_paths[:-1],
                    "docs/plans/260900_0000_unrelated.md",
                ),
            ),
            candidate("carrier_cardinality", carrier_paths=entry.carrier_paths[:-1]),
            candidate(
                "carrier_order",
                carrier_paths=(
                    entry.carrier_paths[1],
                    entry.carrier_paths[0],
                    *entry.carrier_paths[2:],
                ),
            ),
            candidate("target_cardinality", targets=entry.targets[:-1]),
            candidate(
                "target_order",
                targets=(entry.targets[1], entry.targets[0], *entry.targets[2:]),
            ),
        ]
        for index, record in enumerate(entry.targets):
            for field, value in (
                ("path", f"{record['path']}.wrong"),
                ("mode", "100755" if record["mode"] == "100644" else "100644"),
                ("blob_oid", "0" * 40),
                ("size_bytes", int(record["size_bytes"]) + 1),
                ("sha256", "0" * 64),
            ):
                targets = [dict(item) for item in entry.targets]
                targets[index][field] = value
                cases.append(
                    candidate(
                        f"target_{index + 1}_{field}",
                        targets=tuple(targets),
                    )
                )
        return tuple(cases)

    def _scope_expansion_body(
        self,
        *,
        status: str,
        scope_expansion: object = None,
        include_scope_expansion: bool = True,
        plan_type: str = "dev",
        wave_family: str | None = None,
        phase_overlay: str | None = None,
        phase_state: str | None = None,
    ) -> str:
        meta: dict[str, object] = {
            "cluster": "process",
            "tags": [],
            "wave_family": wave_family,
            "phase_overlay": phase_overlay,
            "phase_state": phase_state,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        if include_scope_expansion:
            meta["scope_expansion"] = scope_expansion
        carrier = json.dumps({"plan_meta": meta}, ensure_ascii=False, indent=2)
        return (
            "# Plan: scope expansion fixture\n\n"
            "**Date:** 2026-07-22 19:42 MSK\n"
            "**Stage:** Stage 1\n"
            "**Priority:** P1\n"
            f"**Plan type:** {plan_type}\n"
            f"**Status:** {status}\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            f"{carrier}\n"
            "```\n"
        )

    def _analysis_source_body(
        self,
        *,
        source_rel: str,
        target_rel: str,
        queue_admission: str = "needs_planner",
        runner_admission: str = "frontier_only",
    ) -> str:
        return dedent(
            f"""\
            # Plan: analysis source

            **Date:** 2026-06-14 01:42 MSK
            **Stage:** Stage 1
            **Priority:** P1
            **Plan type:** dev
            **Status:** Done

            ## Meta (machine-readable JSON; required for new plans)
            ```json
            {{
              "plan_meta": {{
                "cluster": "process",
                "tags": [],
                "wave_family": "analysis_wave",
                "phase_overlay": null,
                "phase_state": null,
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": []
              }}
            }}
            ```

            ## Promoted route artifact
            | Field | Value |
            | --- | --- |
            | `source_analysis_plan` | `{source_rel}` |
            | `source_analysis_pack_ref` | `{source_rel}#Analysis-pack` |
            | `accepted_route` | `decomposition_wave` |
            | `promoted_artifact_kind` | `decomposition_umbrella` |
            | `promoted_artifact_ref` | `{target_rel}` |
            | `queue_admission` | `{queue_admission}` |
            | `runner_admission` | `{runner_admission}` |
            """
        )

    def _analysis_lifecycle_body(self, *, analysis_rows: str) -> str:
        return dedent(
            f"""\
            # Plan: analysis lifecycle

            **Date:** 2026-06-19 00:28 MSK
            **Stage:** Stage 2
            **Priority:** P1
            **Plan type:** dev
            **Status:** Done

            ## Meta (machine-readable JSON; required for new plans)
            ```json
            {{
              "plan_meta": {{
                "cluster": "process",
                "tags": [],
                "wave_family": "analysis_wave",
                "phase_overlay": null,
                "phase_state": null,
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": []
              }}
            }}
            ```

            ## Analysis pack
            | Field | Value |
            | --- | --- |
            {analysis_rows}

            ## Promoted route artifact
            | Field | Value |
            | --- | --- |
            | `source_analysis_plan` | `docs/plans/260619_0028_analysis_lifecycle.md` |
            | `source_analysis_pack_ref` | `docs/plans/260619_0028_analysis_lifecycle.md#Analysis-pack` |
            | `accepted_route` | `developer_wave` |
            | `promoted_artifact_kind` | `seed_dev_plan` |
            | `promoted_artifact_ref` | `docs/plans/260619_0028_seed.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        )

    def _write_analysis_lifecycle_fixture(
        self,
        root: Path,
        rel_path: str,
        *,
        analysis_rows: str,
    ) -> Path:
        """Write a real external analysis-pack authority for an analysis-wave test."""

        pack_rel = f"docs/analysis_packs/{Path(rel_path).stem}.md"
        plan = self._write_plan(
            root,
            rel_path,
            self._analysis_lifecycle_body(
                analysis_rows=f"| `analysis_pack_ref` | `{pack_rel}#Analysis-pack` |"
            ),
        )
        pack = root / pack_rel
        pack.parent.mkdir(parents=True, exist_ok=True)
        pack.write_text(
            "# Analysis pack\n\n## Analysis pack\n| Field | Value |\n| --- | --- |\n"
            + analysis_rows
            + "\n",
            encoding="utf-8",
        )
        self._attach_not_applicable_machine_authority(
            root,
            plan,
            draft_targets=[{"path": pack_rel, "kind": "doc"}],
        )
        return plan

    def test_json_output_uses_single_header_status_and_ignores_body_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_oracle_fixture.md",
                dedent(
                    """\
                    # Plan: oracle fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder

                    ## Evidence
                    - Body note keeps a historical `**Status:** Done` string but it is not a header carrier.
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status_norm"], "ready for coder")
        self.assertEqual(payload["status_line"], "7:**Status:** Ready for Coder")
        self.assertEqual(payload["plan_path"], str(plan))
        self.assertEqual(len(payload["plan_hash"]), 64)
        self.assertTrue(payload["oracle_run_id"])
        current_state = payload["current_state"]
        required_fields = {
            "schema",
            "plan_path",
            "status_value",
            "status_norm",
            "status_source",
            "runtime_class",
            "queue_closeout_kind",
            "review_readback_state",
            "review_readback_reason",
            "source_route_state",
            "promoted_from_state",
            "queue_activation_state",
            "route_guard_kind",
            "docs_closeout_state",
            "final_docs_commit",
            "followups_reconciliation_state",
            "process_improvement_capture_state",
            "terminal_ready_state",
            "blocker_state",
            "authorities",
        }
        self.assertLessEqual(required_fields, set(current_state))
        self.assertEqual(current_state["schema"], "plan_current_state.v1")
        self.assertEqual(current_state["plan_path"], str(plan))
        self.assertEqual(current_state["status_norm"], "ready for coder")
        self.assertEqual(current_state["docs_closeout_state"], "contextual_unavailable")
        self.assertEqual(current_state["final_docs_commit"], "contextual_unavailable")
        self.assertEqual(current_state["followups_reconciliation_state"], "contextual_unavailable")
        self.assertEqual(current_state["process_improvement_capture_state"], "contextual_unavailable")
        self.assertEqual(current_state["terminal_ready_state"], "not_ready")
        self.assertEqual(current_state["blocker_state"], "unknown")
        self.assertIn("status_header", current_state["authorities"])
        self.assertIn("docs_closeout", current_state["authorities"])
        self.assertEqual(payload["owner_qna_readback_state"], "clean")
        self.assertEqual(payload["open_owner_questions"], [])

    def test_exact_accepted_red_conjunction_is_non_delivery_and_staging_forbidden(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan, review_sha = self._write_accepted_red_fixture(root)
            snapshot = mock.Mock(
                returncode=0,
                stdout="{}",
                stderr="",
            )

            with (
                selective_current_bundle_snapshot_run(snapshot),
                mock.patch.object(
                    MODULE.review_target_snapshot,
                    "validate_snapshot_payload",
                    return_value={"bundle_sha256": review_sha},
                ),
                mock.patch.object(
                    MODULE,
                    "validate_accepted_red_durable_ref",
                    return_value=MODULE.AcceptedRedDurableRefResult(
                        "missing",
                        "fixture ref absent",
                    ),
                ),
            ):
                payload = self._json_payload(plan)

        self.assertEqual(payload["terminal_disposition"], "accepted_red_supersession")
        self.assertFalse(payload["delivery_green"])
        self.assertEqual(payload["staging_policy"], "forbidden")
        self.assertTrue(payload["durable_capture_required"])
        self.assertEqual(
            payload["terminal_disposition_reason"],
            "accepted_red_current_snapshot",
        )
        self.assertEqual(
            payload["accepted_red_successor_plan"],
            "docs/plans/accepted_red_successor_fixture.md",
        )
        self.assertEqual(payload["accepted_red_review_bundle_sha256"], review_sha)
        current = payload["current_state"]
        self.assertEqual(current["terminal_disposition"], "accepted_red_supersession")
        self.assertFalse(current["delivery_green"])

    def test_accepted_red_review_route_is_label_independent_in_active_and_committed_modes(
        self,
    ) -> None:
        cases = (
            ("docs/code_reviews", "Doc review (docs-only)"),
            ("docs/doc_reviews", "Code review (primary)"),
        )
        for review_directory, review_label in cases:
            with self.subTest(review_directory=review_directory), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, _ = self._write_accepted_red_fixture(
                    root,
                    review_directory=review_directory,
                    review_label=review_label,
                )
                expected = f"{review_directory}/{plan.stem}.md"
                active = MODULE.resolve_accepted_red_review_path(
                    root,
                    plan.relative_to(root).as_posix(),
                    plan_text=plan.read_text(encoding="utf-8"),
                )
                self._git(root, "init")
                self._git(root, "config", "user.name", "Test User")
                self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
                self._git(root, "add", ".")
                self._git(root, "commit", "-m", "fixture")
                committed = MODULE.resolve_accepted_red_review_path(
                    root,
                    plan.relative_to(root).as_posix(),
                    carrier_commit="HEAD",
                )

                self.assertEqual(active, expected)
                self.assertEqual(committed, expected)

    def test_accepted_red_review_route_deduplicates_identical_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan, _ = self._write_accepted_red_fixture(root)
            plan_rel = plan.relative_to(root).as_posix()
            review_rel = f"docs/code_reviews/{plan.stem}.md"
            plan_text = plan.read_text(encoding="utf-8").replace(
                f"- Code review (primary): `{review_rel}`\n",
                (
                    f"- Code review (primary): `{review_rel}`\n"
                    f"- Historical note: `{review_rel}`\n"
                ),
            )
            plan.write_text(plan_text, encoding="utf-8")

            active = MODULE.resolve_accepted_red_review_path(
                root,
                plan_rel,
                plan_text=plan_text,
            )
            self._git(root, "init")
            self._git(root, "config", "user.name", "Test User")
            self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "fixture")
            committed = MODULE.resolve_accepted_red_review_path(
                root,
                plan_rel,
                carrier_commit="HEAD",
            )

        self.assertEqual(active, review_rel)
        self.assertEqual(committed, review_rel)

    def test_accepted_red_review_route_rejects_missing_both_and_wrong_identity(self) -> None:
        cases = ("missing", "both", "distinct", "wrong_stem", "wrong_path")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, _ = self._write_accepted_red_fixture(root)
                plan_text = plan.read_text(encoding="utf-8")
                review_rel = f"docs/code_reviews/{plan.stem}.md"
                review = root / review_rel
                if case == "missing":
                    plan_text = plan_text.replace(
                        f"- Code review (primary): `{review_rel}`\n",
                        "",
                    )
                elif case == "both":
                    counterpart = root / f"docs/doc_reviews/{plan.stem}.md"
                    counterpart.parent.mkdir(parents=True, exist_ok=True)
                    counterpart.write_bytes(review.read_bytes())
                elif case == "distinct":
                    plan_text += (
                        f"- Doc review (docs-only): `docs/doc_reviews/{plan.stem}.md`\n"
                    )
                elif case == "wrong_stem":
                    plan_text = plan_text.replace(
                        f"- Code review (primary): `{review_rel}`",
                        f"- Code review (primary): `docs/code_reviews/{plan.stem}_other.md`",
                    )
                else:
                    plan_text = plan_text.replace(
                        review_rel,
                        f"docs/reviews/{plan.stem}.md",
                    )

                with self.assertRaises(MODULE.AcceptedRedDurableValidationError):
                    MODULE.resolve_accepted_red_review_path(
                        root,
                        plan.relative_to(root).as_posix(),
                        plan_text=plan_text,
                    )

    def test_accepted_red_snapshot_bridge_registry_defaults_empty_and_requires_explicit_injection(
        self,
    ) -> None:
        self.assertEqual(MODULE.ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST, {})
        root = Path("/synthetic/repo")
        source_plan = "docs/plans/fixture_source.md"
        source_review = "docs/code_reviews/fixture_source.md"
        source_targets = ("scripts/fixture_target.py",)
        review_bundle = "a" * 64
        producer_commit = "b" * 40
        producer_blob_oid = "c" * 40
        bridge: dict[str, object] = {
            "schema": "planveyor_accepted_red_snapshot_bridge.v1",
            "bridge_id": "fixture-bridge-v1",
            "bridge_sha256": "",
            "source_plan": source_plan,
            "review_bundle_sha256": review_bundle,
            "legacy_hash_basis_schema": "review_target_snapshot.hash_basis.v1",
            "legacy_hash_basis": "sha256-canonical-json-v1-path-sha256-size",
            "producer_commit": producer_commit,
            "producer_path": "scripts/review_target_snapshot.py",
            "producer_blob_oid": producer_blob_oid,
            "current_hash_basis_schema": MODULE.review_target_snapshot.HASH_BASIS_SCHEMA_VERSION,
            "current_hash_basis": "sha256-canonical-json-v2-path-sha256-size-git_mode",
            "current_bundle_sha256": "d" * 64,
            "targets": [
                {
                    "path": source_targets[0],
                    "sha256": "e" * 64,
                    "size_bytes": 17,
                    "git_mode": "100644",
                    "git_blob_oid": "f" * 40,
                }
            ],
        }
        digest_payload = dict(bridge)
        digest_payload.pop("bridge_sha256")
        bridge_digest = hashlib.sha256(
            json.dumps(
                digest_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        bridge["bridge_sha256"] = bridge_digest
        recovery_text = (
            "```json\n"
            + json.dumps({"accepted_red_snapshot_bridge": bridge}, indent=2)
            + "\n```\n"
        )
        producer_text = (
            b'SNAPSHOT_SCHEMA_VERSION = "review_target_snapshot.v1"\n'
            b'HASH_BASIS_SCHEMA_VERSION = "review_target_snapshot.hash_basis.v1"\n'
        )
        review_text = (
            "# Review\n\n"
            f"**Target:** BUNDLE=current bundle_sha256={review_bundle}\n"
        )
        git_ok = subprocess.CompletedProcess([], 0, producer_text, b"")
        patches = (
            mock.patch.object(MODULE, "resolve_accepted_red_review_path", return_value=source_review),
            mock.patch.object(MODULE, "_accepted_red_carrier_text", return_value=review_text),
            mock.patch.object(MODULE, "_accepted_red_git", return_value=git_ok),
            mock.patch.object(MODULE, "_accepted_red_git_text", return_value=producer_blob_oid),
        )

        def invoke() -> dict[str, object] | None:
            return MODULE._accepted_red_snapshot_bridge(
                root,
                recovery_text,
                source_plan,
                source_targets,
            )

        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "snapshot bridge is not allowlisted",
            ):
                invoke()
            allowlist_key = (source_plan, review_bundle, "fixture-bridge-v1")
            with mock.patch.object(
                MODULE,
                "ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST",
                {allowlist_key: bridge_digest},
            ):
                result = invoke()
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["bridge_id"], "fixture-bridge-v1")
            with mock.patch.object(
                MODULE,
                "ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST",
                {allowlist_key: "0" * 64},
            ), self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "snapshot bridge is not allowlisted",
            ):
                invoke()

    def test_accepted_red_rebind_registry_defaults_empty_and_requires_explicit_injection(
        self,
    ) -> None:
        self.assertEqual(MODULE.ACCEPTED_RED_RECOVERY_CONTRACT_REBIND_ALLOWLIST, {})
        key = (
            "docs/plans/fixture_source.md",
            "a" * 64,
            "b" * 40,
            "c" * 40,
            "docs/plans/fixture_recovery.md",
            "docs/code_drafts/fixture_recovery__code_draft.md",
        )
        entry = MODULE.AcceptedRedRecoveryContractRebind(
            recovery_revision="d" * 40,
            recovery_review="docs/code_reviews/fixture_recovery.md",
            recovery_bundle_sha256="e" * 64,
            recovery_targets=("scripts/fixture_target.py",),
            binding_sha256="f" * 64,
        )
        contract = {
            "source_plan": key[0],
            "review_sha": key[1],
        }
        manifest = {
            "captured_parent": key[3],
            "recovery_plan": key[4],
            "recovery_code_draft": key[5],
        }
        self.assertIsNone(
            MODULE._accepted_red_recovery_contract_rebind_entry(
                contract,
                manifest,
                key[2],
            )
        )
        with mock.patch.object(
            MODULE,
            "ACCEPTED_RED_RECOVERY_CONTRACT_REBIND_ALLOWLIST",
            {key: entry},
        ):
            self.assertIs(
                MODULE._accepted_red_recovery_contract_rebind_entry(
                    contract,
                    manifest,
                    key[2],
                ),
                entry,
            )
            self.assertIsNone(
                MODULE._accepted_red_recovery_contract_rebind_entry(
                    contract,
                    manifest,
                    "0" * 40,
                )
            )

    def test_accepted_red_successor_topology_rebind_defaults_empty_and_is_fail_closed(
        self,
    ) -> None:
        self.assertEqual(MODULE.ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST, ())
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            entry, source_rel, successor_rel = self._write_topology_rebind_fixture(root)
            source_text = (root / source_rel).read_text(encoding="utf-8")
            successor_text = (root / successor_rel).read_text(encoding="utf-8")

            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "topology rebind is not a unique incident authority",
            ):
                MODULE.validate_accepted_red_successor_topology_rebind(
                    root,
                    source_rel,
                    source_text,
                    successor_rel,
                    successor_text,
                )
            default_disposition = MODULE.classify_accepted_red_disposition(
                plan_path=root / source_rel,
                plan_text=source_text,
                status_norm="superseded",
                meta=MODULE.parse_plan_meta(source_text),
            )
            self.assertEqual(default_disposition.reason, "accepted_red_carrier_invalid")

            with mock.patch.object(
                MODULE,
                "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST",
                (entry,),
            ):
                MODULE.validate_accepted_red_successor_topology_rebind(
                    root,
                    source_rel,
                    source_text,
                    successor_rel,
                    successor_text,
                )
                disposition = MODULE.classify_accepted_red_disposition(
                    plan_path=root / source_rel,
                    plan_text=source_text,
                    status_norm="superseded",
                    meta=MODULE.parse_plan_meta(source_text),
                )

                self.assertEqual(
                    disposition.terminal_disposition,
                    "accepted_red_supersession",
                )
                self.assertFalse(disposition.delivery_green)
                self.assertEqual(disposition.staging_policy, "forbidden")
                self.assertTrue(disposition.durable_capture_required)
                self.assertEqual(
                    disposition.review_bundle_sha256,
                    entry.source_review_bundle_sha256,
                )

                raw_digest_cases = (
                    ("entry_digest", replace(entry, entry_sha256="0" * 64)),
                )
                semantic_cases = self._topology_rebind_semantic_mutation_cases(entry)
                for case, candidate in (*raw_digest_cases, *semantic_cases):
                    with self.subTest(case=case), mock.patch.object(
                        MODULE,
                        "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST",
                        (candidate,),
                    ):
                        if case != "entry_digest":
                            self.assertEqual(
                                candidate.entry_sha256,
                                hashlib.sha256(
                                    json.dumps(
                                        MODULE._accepted_red_topology_rebind_identity(
                                            candidate
                                        ),
                                        ensure_ascii=False,
                                        sort_keys=True,
                                        separators=(",", ":"),
                                    ).encode("utf-8")
                                ).hexdigest(),
                            )
                        with self.assertRaises(MODULE.AcceptedRedDurableValidationError):
                            MODULE.validate_accepted_red_successor_topology_rebind(
                                root,
                                source_rel,
                                source_text,
                                successor_rel,
                                successor_text,
                            )
                        invalid = MODULE.classify_accepted_red_disposition(
                            plan_path=root / source_rel,
                            plan_text=source_text,
                            status_norm="superseded",
                            meta=MODULE.parse_plan_meta(source_text),
                        )
                        self.assertEqual(
                            invalid.reason,
                            "accepted_red_carrier_invalid",
                        )

                with self.subTest(case="active_source"):
                    with self.assertRaises(MODULE.AcceptedRedDurableValidationError):
                        MODULE.validate_accepted_red_successor_topology_rebind(
                            root,
                            source_rel,
                            source_text + "\nchanged\n",
                            successor_rel,
                            successor_text,
                        )
                    invalid = MODULE.classify_accepted_red_disposition(
                        plan_path=root / source_rel,
                        plan_text=source_text + "\nchanged\n",
                        status_norm="superseded",
                        meta=MODULE.parse_plan_meta(source_text),
                    )
                    self.assertEqual(invalid.reason, "accepted_red_carrier_invalid")

                with mock.patch.object(
                    MODULE,
                    "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST",
                    (entry, entry),
                ):
                    with self.assertRaises(MODULE.AcceptedRedDurableValidationError):
                        MODULE.validate_accepted_red_successor_topology_rebind(
                            root,
                            source_rel,
                            source_text,
                            successor_rel,
                                successor_text,
                            )

    def test_accepted_red_topology_rebind_rejects_ambient_git_authority_overrides(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            entry, source_rel, successor_rel = self._write_topology_rebind_fixture(root)
            source_text = (root / source_rel).read_text(encoding="utf-8")
            successor_text = (root / successor_rel).read_text(encoding="utf-8")

            for name in MODULE.ACCEPTED_RED_GIT_AUTHORITY_ENVIRONMENT_NAMES:
                with self.subTest(name=name), mock.patch.object(
                    MODULE,
                    "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST",
                    (entry,),
                ), mock.patch.dict(MODULE.os.environ, {name: "fixture-override"}):
                    with self.assertRaisesRegex(
                        MODULE.AcceptedRedDurableValidationError,
                        rf"ambient Git authority override\(s\): {name}",
                    ):
                        MODULE.validate_accepted_red_successor_topology_rebind(
                            root,
                            source_rel,
                            source_text,
                            successor_rel,
                            successor_text,
                        )
                    disposition = MODULE.classify_accepted_red_disposition(
                        plan_path=root / source_rel,
                        plan_text=source_text,
                        status_norm="superseded",
                        meta=MODULE.parse_plan_meta(source_text),
                    )
                    self.assertEqual(
                        disposition.reason,
                        "accepted_red_carrier_invalid",
                    )

    def test_accepted_red_git_ignores_replace_objects_and_rejects_rewrite_topology(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._git(root, "init")
            self._git(root, "config", "user.name", "Test User")
            self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
            payload = root / "payload.txt"
            payload.write_text("original\n", encoding="utf-8")
            self._git(root, "add", "payload.txt")
            self._git(root, "commit", "-m", "original")
            original = self._git(root, "rev-parse", "HEAD")
            payload.write_text("current\n", encoding="utf-8")
            self._git(root, "commit", "-am", "current")
            current = self._git(root, "rev-parse", "HEAD")
            self._git(root, "replace", current, original)

            replaced = self._git(root, "show", f"{current}:payload.txt")
            safe = MODULE._accepted_red_git(
                root,
                "show",
                f"{current}:payload.txt",
            )

            self.assertEqual(replaced, "original")
            self.assertEqual(safe.returncode, 0)
            self.assertEqual(safe.stdout, b"current\n")
            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "replace refs are forbidden",
            ):
                MODULE._accepted_red_assert_no_object_rewrite_topology(root)

            self._git(root, "replace", "-d", current)
            MODULE._accepted_red_assert_no_object_rewrite_topology(root)
            graft_path = Path(
                self._git(root, "rev-parse", "--git-path", "info/grafts")
            )
            if not graft_path.is_absolute():
                graft_path = root / graft_path
            graft_path.parent.mkdir(parents=True, exist_ok=True)
            graft_path.write_text(f"{current} {original}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "graft topology is forbidden",
            ):
                MODULE._accepted_red_assert_no_object_rewrite_topology(root)

        with mock.patch.dict(
            MODULE.os.environ,
            {"GIT_REPLACE_REF_BASE": "refs/test-replacements/"},
        ):
            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "custom Git replace-ref namespace is forbidden",
            ):
                MODULE._accepted_red_assert_no_object_rewrite_topology(Path("."))

    def test_accepted_red_rebind_requires_exact_canonical_digest(self) -> None:
        root = Path("/synthetic/repo")
        revision = "a" * 40
        source_plan = "docs/plans/source.md"
        source_review = "docs/code_reviews/source.md"
        recovery_plan = "docs/plans/recovery.md"
        recovery_draft = "docs/code_drafts/recovery__code_draft.md"
        recovery_review = "docs/code_reviews/recovery.md"
        manifest_path = ".planveyor/rejected/source/manifest.json"
        cleanup_path = ".planveyor/rejected/source/cleanup.json"
        legacy_tip = "b" * 40
        captured_parent = "c" * 40
        review_sha = "d" * 64
        recovery_bundle = "e" * 64
        frozen_targets = ["scripts/old.py"]
        effective_targets = ("scripts/new.py", "scripts/old.py")
        contract = {
            "source_plan": source_plan,
            "review": source_review,
            "review_sha": review_sha,
            "successor": "docs/plans/successor.md",
            "ref": "refs/planveyor/rejected/source/hash",
            "manifest_path": manifest_path,
            "cleanup_path": cleanup_path,
            "targets": ["scripts/source.py"],
            "routing": [source_plan, source_review],
        }
        manifest = {
            "captured_parent": captured_parent,
            "recovery_plan": recovery_plan,
            "recovery_code_draft": recovery_draft,
            "recovery_targets": frozen_targets,
        }
        effective = {
            "recovery_plan": recovery_plan,
            "recovery_code_draft": recovery_draft,
            "recovery_targets": list(effective_targets),
            "recovery_status": "done",
            "snapshot_bridge": None,
        }
        target_records = tuple(
            {
                "path": path,
                "mode": "100644",
                "blob_oid": f"{index:040x}",
                "sha256": f"{index:064x}",
                "size_bytes": index,
            }
            for index, path in enumerate(effective_targets, start=1)
        )
        blob_oids = {
            manifest_path: "1" * 40,
            cleanup_path: "2" * 40,
            recovery_plan: "3" * 40,
            recovery_draft: "4" * 40,
            recovery_review: "5" * 40,
        }

        def blob_record(
            _root: Path,
            _revision: str,
            rel: str,
            *,
            label: str,
        ) -> dict[str, object]:
            del label
            return {
                "path": rel,
                "mode": "100644",
                "blob_oid": blob_oids[rel],
                "sha256": "6" * 64,
                "size_bytes": 1,
            }

        identity = {
            "schema": "accepted_red_recovery_contract_rebind.v1",
            "source_plan": source_plan,
            "historical_review": source_review,
            "review_bundle_sha256": review_sha,
            "successor_plan": contract["successor"],
            "legacy_ref": contract["ref"],
            "legacy_tip": legacy_tip,
            "captured_parent": captured_parent,
            "legacy_manifest_path": manifest_path,
            "legacy_manifest_blob_oid": blob_oids[manifest_path],
            "legacy_cleanup_path": cleanup_path,
            "legacy_cleanup_blob_oid": blob_oids[cleanup_path],
            "frozen_recovery_plan": recovery_plan,
            "frozen_recovery_code_draft": recovery_draft,
            "frozen_recovery_targets": frozen_targets,
            "recovery_revision": revision,
            "recovery_plan": recovery_plan,
            "recovery_plan_blob_oid": blob_oids[recovery_plan],
            "recovery_code_draft": recovery_draft,
            "recovery_code_draft_blob_oid": blob_oids[recovery_draft],
            "recovery_review": recovery_review,
            "recovery_review_blob_oid": blob_oids[recovery_review],
            "recovery_bundle_sha256": recovery_bundle,
            "recovery_targets": [dict(record) for record in target_records],
        }
        digest = hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        entry = MODULE.AcceptedRedRecoveryContractRebind(
            recovery_revision=revision,
            recovery_review=recovery_review,
            recovery_bundle_sha256=recovery_bundle,
            recovery_targets=effective_targets,
            binding_sha256=digest,
        )
        git_ok = subprocess.CompletedProcess([], 0, b"", b"")
        patches = (
            mock.patch.object(MODULE, "_accepted_red_git", return_value=git_ok),
            mock.patch.object(
                MODULE,
                "parse_accepted_red_recovery_contract",
                return_value=effective,
            ),
            mock.patch.object(
                MODULE,
                "resolve_accepted_red_review_path",
                return_value=recovery_review,
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_carrier_text",
                return_value=(
                    "# Review\n\n"
                    f"**Target:** BUNDLE=current bundle_sha256={recovery_bundle}\n"
                    "**Status:** ✅ OK\n"
                ),
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_revision_bundle",
                return_value=(recovery_bundle, target_records),
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_revision_blob_record",
                side_effect=blob_record,
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = MODULE._accepted_red_validate_recovery_contract_rebind(
                root,
                contract,
                manifest,
                legacy_tip,
                entry,
            )
            with self.assertRaisesRegex(
                MODULE.AcceptedRedDurableValidationError,
                "rebind digest mismatch",
            ):
                MODULE._accepted_red_validate_recovery_contract_rebind(
                    root,
                    contract,
                    manifest,
                    legacy_tip,
                    MODULE.AcceptedRedRecoveryContractRebind(
                        recovery_revision=revision,
                        recovery_review=recovery_review,
                        recovery_bundle_sha256=recovery_bundle,
                        recovery_targets=effective_targets,
                        binding_sha256="0" * 64,
                    ),
                )

        self.assertEqual(result, effective)

    def test_accepted_red_invalid_review_route_and_green_review_stay_non_delivery(self) -> None:
        for case in ("missing_route", "green", "malformed_blocker"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, _ = self._write_accepted_red_fixture(
                    root,
                    review_red=case != "green",
                )
                if case == "missing_route":
                    plan.write_text(
                        re.sub(
                            r"^## Review artifacts\n[\s\S]*\Z",
                            "## Review artifacts\n",
                            plan.read_text(encoding="utf-8"),
                            flags=re.MULTILINE,
                        ),
                        encoding="utf-8",
                    )
                elif case == "malformed_blocker":
                    review = root / f"docs/code_reviews/{plan.stem}.md"
                    review.write_text(
                        review.read_text(encoding="utf-8").replace(
                            "### B1) blocker 1",
                            "### B1 arbitrary suffix",
                        ),
                        encoding="utf-8",
                    )
                result = MODULE.classify_accepted_red_disposition(
                    plan_path=plan,
                    plan_text=plan.read_text(encoding="utf-8"),
                    status_norm="superseded",
                    meta=MODULE.parse_plan_meta(plan.read_text(encoding="utf-8")),
                )

                self.assertEqual(result.terminal_disposition, "accepted_red_supersession")
                self.assertFalse(result.delivery_green)
                self.assertEqual(result.staging_policy, "forbidden")
                self.assertTrue(result.reason.startswith("accepted_red_review_"))

    def test_accepted_red_oracle_consumers_do_not_reconstruct_code_review_path(self) -> None:
        for consumer in (
            MODULE._accepted_red_snapshot_bridge,
            MODULE._accepted_red_validate_legacy_review,
            MODULE.classify_accepted_red_disposition,
        ):
            with self.subTest(consumer=consumer.__name__):
                source = inspect.getsource(consumer)
                self.assertNotIn("docs/code_reviews/", source)
                self.assertIn("resolve_accepted_red_review_path", source)

    def test_current_open_blocker_ids_is_numeric_generic_and_ignores_historical_sections(self) -> None:
        review_text = dedent(
            """\
            # Review

            ## S1 Blocker

            ### B12

            - Blocker ID: `B12`
            - Current state: `open`

            ### B4) earlier numeric blocker

            - Blocker ID: B4
            - Current state: open

            ## Historical blocker reconciliation

            ### B1) historical only

            - Blocker ID: B1
            - Current state: open
            """
        )

        self.assertEqual(MODULE.current_open_blocker_ids(review_text), ("B4", "B12"))

    def test_current_open_blocker_ids_accepts_titleless_heading(self) -> None:
        review_text = dedent(
            """\
            ## S1 Blocker

            ### B1

            - Blocker ID: `B1`
            - Current state: `open`
            """
        )

        self.assertEqual(MODULE.current_open_blocker_ids(review_text), ("B1",))

    def test_current_open_blocker_ids_fails_closed_on_malformed_or_duplicate_grammar(self) -> None:
        valid = dedent(
            """\
            ## S1 Blocker

            ### B7) current blocker

            - Blocker ID: B7
            - Current state: open
            """
        )
        cases = {
            "missing_section": "## Historical blocker reconciliation\n",
            "duplicate_section": valid + "\n## S1 Blocker\n",
            "empty_titled_suffix": valid.replace(
                "### B7) current blocker",
                "### B7)",
            ),
            "arbitrary_suffix": valid.replace(
                "### B7) current blocker",
                "### B7 arbitrary suffix",
            ),
            "zero_id": valid.replace("B7", "B0"),
            "mismatched_id": valid.replace("- Blocker ID: B7", "- Blocker ID: B8"),
            "duplicate_id": valid
            + dedent(
                """\

                ### B7) duplicate blocker

                - Blocker ID: B7
                - Current state: open
                """
            ),
            "missing_state": valid.replace("- Current state: open\n", ""),
            "unsupported_state": valid.replace("Current state: open", "Current state: historical-fixed"),
            "duplicate_state": valid.replace(
                "- Current state: open",
                "- Current state: open\n- Current state: open",
            ),
        }
        for case, review_text in cases.items():
            with self.subTest(case=case):
                with self.assertRaises(MODULE.CurrentOpenBlockerError):
                    MODULE.current_open_blocker_ids(review_text)

    def test_accepted_red_exact_successor_set_and_scope_ref_drift_fail_closed(self) -> None:
        cases = {
            "missing": {
                "inherited_ids": ("B1", "B3"),
            },
            "extra": {
                "inherited_ids": ("B1", "B2", "B3", "B9"),
            },
            "duplicate": {
                "inherited_ids": ("B1", "B2", "B3", "B3"),
            },
            "source_ref_outside": {
                "source_ref_id": "B9",
            },
        }
        for case, options in cases.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, review_sha = self._write_accepted_red_fixture(root, **options)
                snapshot = mock.Mock(
                    returncode=0,
                    stdout=json.dumps({"bundle_sha256": review_sha}),
                    stderr="",
                )
                with selective_current_bundle_snapshot_run(snapshot):
                    result = MODULE.oracle_result(plan)
                self.assertEqual(
                    result.terminal_disposition,
                    "accepted_red_supersession",
                )
                self.assertFalse(result.delivery_green)
                self.assertEqual(result.staging_policy, "forbidden")
                self.assertEqual(
                    result.terminal_disposition_reason,
                    "accepted_red_review_invalid",
                )

    def test_accepted_red_synthetic_carriers_derive_exact_current_sets(self) -> None:
        cases = (
            ("three_current_blockers", ("B1", "B2", "B3"), ""),
            (
                "one_current_blocker_with_history",
                ("B5",),
                dedent(
                    """\
                    ## Historical blocker reconciliation

                    ### B1) resolved historical blocker

                    - Blocker ID: `B1`
                    - Current state: `historical-fixed`
                    """
                ),
            ),
        )
        for case, expected, historical_text in cases:
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, review_sha = self._write_accepted_red_fixture(
                    root,
                    blocker_ids=expected,
                    historical_text=historical_text,
                )
                review = root / "docs/code_reviews/accepted_red_fixture.md"
                self.assertEqual(
                    MODULE.current_open_blocker_ids(review.read_text(encoding="utf-8")),
                    expected,
                )
                snapshot = mock.Mock(returncode=0, stdout="{}", stderr="")
                with (
                    selective_current_bundle_snapshot_run(snapshot),
                    mock.patch.object(
                        MODULE.review_target_snapshot,
                        "validate_snapshot_payload",
                        return_value={"bundle_sha256": review_sha},
                    ),
                    mock.patch.object(
                        MODULE,
                        "validate_accepted_red_durable_ref",
                        return_value=MODULE.AcceptedRedDurableRefResult(
                            "missing",
                            "synthetic fixture has no durable ref",
                        ),
                    ),
                ):
                    plan_text = plan.read_text(encoding="utf-8")
                    disposition = MODULE.classify_accepted_red_disposition(
                        plan_path=plan,
                        plan_text=plan_text,
                        status_norm="superseded",
                        meta=MODULE.parse_plan_meta(plan_text),
                    )
                self.assertEqual(disposition.terminal_disposition, "accepted_red_supersession")
                self.assertFalse(disposition.delivery_green)
                self.assertEqual(disposition.staging_policy, "forbidden")
                self.assertTrue(disposition.durable_capture_required)
                self.assertEqual(disposition.reason, "accepted_red_current_snapshot")

    def test_superseded_near_misses_and_green_review_fail_closed(self) -> None:
        cases = (
            (
                {"scope_state": "n/a"},
                "ordinary",
                "allowed",
                False,
                "accepted-red conjunction is not applicable",
            ),
            (
                {"successor_count": 2},
                "ordinary",
                "allowed",
                False,
                "accepted-red conjunction is not applicable",
            ),
            (
                {"backlink_matches": False},
                "accepted_red_supersession",
                "forbidden",
                True,
                "accepted_red_carrier_invalid",
            ),
            (
                {"review_red": False},
                "accepted_red_supersession",
                "forbidden",
                True,
                "accepted_red_review_invalid",
            ),
        )
        for (
            options,
            expected_disposition,
            expected_staging_policy,
            expected_durable_capture,
            expected_reason,
        ) in cases:
            with self.subTest(options=options), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, review_sha = self._write_accepted_red_fixture(root, **options)
                snapshot = mock.Mock(
                    returncode=0,
                    stdout=json.dumps({"bundle_sha256": review_sha}),
                    stderr="",
                )
                with selective_current_bundle_snapshot_run(snapshot):
                    payload = self._json_payload(plan)
                self.assertEqual(
                    payload["terminal_disposition"],
                    expected_disposition,
                )
                self.assertFalse(payload["delivery_green"])
                self.assertEqual(
                    payload["staging_policy"],
                    expected_staging_policy,
                )
                self.assertEqual(
                    payload["durable_capture_required"],
                    expected_durable_capture,
                )
                self.assertEqual(
                    payload["terminal_disposition_reason"],
                    expected_reason,
                )

    def test_structural_accepted_red_missing_or_wrong_lineage_fails_closed(
        self,
    ) -> None:
        cases = (
            "missing_successor",
            "missing_draft",
            "wrong_draft_plan",
        )
        for case in cases:
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan, review_sha = self._write_accepted_red_fixture(root)
                if case == "missing_successor":
                    (
                        root
                        / "docs/plans/accepted_red_successor_fixture.md"
                    ).unlink()
                else:
                    draft = (
                        root
                        / "docs/code_drafts/"
                        "accepted_red_fixture__code_draft.md"
                    )
                    if case == "missing_draft":
                        draft.unlink()
                    else:
                        draft.write_text(
                            draft.read_text(encoding="utf-8").replace(
                                "docs/plans/accepted_red_fixture.md",
                                "docs/plans/foreign.md",
                            ),
                            encoding="utf-8",
                        )
                snapshot = mock.Mock(
                    returncode=0,
                    stdout=json.dumps({"bundle_sha256": review_sha}),
                    stderr="",
                )

                with selective_current_bundle_snapshot_run(snapshot):
                    payload = self._json_payload(plan)

                self.assertEqual(
                    payload["terminal_disposition"],
                    "accepted_red_supersession",
                )
                self.assertFalse(payload["delivery_green"])
                self.assertEqual(payload["staging_policy"], "forbidden")
                self.assertTrue(payload["durable_capture_required"])
                self.assertEqual(
                    payload["terminal_disposition_reason"],
                    "accepted_red_carrier_invalid",
                )

    def test_accepted_red_snapshot_mismatch_without_evidence_ref_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan, _review_sha = self._write_accepted_red_fixture(root)
            snapshot_mismatch = mock.Mock(
                returncode=0,
                stdout=json.dumps({"bundle_sha256": "b" * 64}),
                stderr="",
            )
            with (
                selective_current_bundle_snapshot_run(snapshot_mismatch),
                mock.patch.object(
                    MODULE,
                    "validate_accepted_red_durable_ref",
                    return_value=MODULE.AcceptedRedDurableRefResult(
                        "missing",
                        "fixture ref absent",
                    ),
                ),
            ):
                payload = self._json_payload(plan)

        self.assertEqual(payload["terminal_disposition"], "accepted_red_supersession")
        self.assertEqual(payload["staging_policy"], "forbidden")
        self.assertTrue(payload["durable_capture_required"])
        self.assertEqual(
            payload["terminal_disposition_reason"],
            "accepted_red_snapshot_mismatch_without_durable_ref",
        )

    def test_accepted_red_snapshot_consumer_rejects_v1_mixed_and_malformed_payloads(
        self,
    ) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan, original_review_sha = self._write_accepted_red_fixture(root)
            plan.write_text(
                plan.read_text(encoding="utf-8")
                + "\n- Draft: `docs/code_drafts/accepted_red_fixture__code_draft.md`\n",
                encoding="utf-8",
            )
            valid = MODULE.review_target_snapshot.build_current_bundle_snapshot(
                plan,
                project_root=root,
            )
            review = root / "docs/code_reviews/accepted_red_fixture.md"
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    original_review_sha,
                    str(valid["bundle_sha256"]),
                ),
                encoding="utf-8",
            )
            cases: dict[str, dict[str, object]] = {}
            v1 = json.loads(json.dumps(valid))
            v1["schema_version"] = "review_target_snapshot.v1"
            cases["v1"] = v1
            mixed = json.loads(json.dumps(valid))
            mixed["hash_basis_payload"]["schema_version"] = (
                "review_target_snapshot.hash_basis.v1"
            )
            cases["mixed"] = mixed
            malformed = json.loads(json.dumps(valid))
            del malformed["files"][0]["git_mode"]
            cases["malformed"] = malformed

            for case, snapshot_payload in cases.items():
                with (
                    self.subTest(case=case),
                    selective_current_bundle_snapshot_run(
                        mock.Mock(
                            returncode=0,
                            stdout=json.dumps(snapshot_payload),
                            stderr="",
                        )
                    ),
                    mock.patch.object(
                        MODULE,
                        "validate_accepted_red_durable_ref",
                        return_value=MODULE.AcceptedRedDurableRefResult(
                            "missing",
                            "fixture ref absent",
                        ),
                    ),
                ):
                    payload = self._json_payload(plan)
                self.assertEqual(
                    payload["terminal_disposition_reason"],
                    "accepted_red_snapshot_mismatch_without_durable_ref",
                )

    def test_accepted_red_invalid_durable_ref_overrides_matching_current_snapshot(
        self,
    ) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan, original_review_sha = self._write_accepted_red_fixture(root)
            plan.write_text(
                plan.read_text(encoding="utf-8")
                + "\n- Draft: `docs/code_drafts/accepted_red_fixture__code_draft.md`\n",
                encoding="utf-8",
            )
            snapshot = MODULE.review_target_snapshot.build_current_bundle_snapshot(
                plan,
                project_root=root,
            )
            review = root / "docs/code_reviews/accepted_red_fixture.md"
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    original_review_sha,
                    str(snapshot["bundle_sha256"]),
                ),
                encoding="utf-8",
            )
            with (
                selective_current_bundle_snapshot_run(
                    mock.Mock(
                        returncode=0,
                        stdout=json.dumps(snapshot),
                        stderr="",
                    )
                ),
                mock.patch.object(
                    MODULE,
                    "validate_accepted_red_durable_ref",
                    return_value=MODULE.AcceptedRedDurableRefResult(
                        "invalid",
                        "fixture malformed ref",
                    ),
                ),
            ):
                payload = self._json_payload(plan)

        self.assertEqual(
            payload["terminal_disposition_reason"],
            "accepted_red_snapshot_mismatch_without_valid_durable_ref",
        )

    def test_accepted_red_cleanup_candidate_public_validator_checks_frozen_identity(
        self,
    ) -> None:
        root = Path("/synthetic/repo")
        capture_commit = "a" * 40
        captured_parent = "b" * 40
        target_rel = "scripts/target.py"
        target_bytes = b"target bytes\n"
        target_record = {
            "path": target_rel,
            "state": "head",
            "sha256": hashlib.sha256(target_bytes).hexdigest(),
            "size_bytes": len(target_bytes),
            "mode": "100644",
            "blob_oid": "c" * 40,
        }
        routing = [{"path": "docs/plans/source.md", "blob_oid": "d" * 40}]
        contract = {
            "cleanup_path": ".planveyor/rejected/source/cleanup.json",
            "source_plan": "docs/plans/source.md",
            "ref": "refs/planveyor/rejected-baselines/source/fixture",
            "review_sha": "e" * 64,
            "targets": [target_rel],
        }
        manifest = {
            "captured_parent": captured_parent,
            "recovery_plan": "docs/plans/recovery.md",
            "recovery_code_draft": "docs/code_drafts/recovery__code_draft.md",
            "recovery_targets": [target_rel],
            "routing_carriers": routing,
        }
        cleanup = {
            "schema": "planveyor_rejected_baseline_cleanup.v1",
            "source_plan": contract["source_plan"],
            "recovery_plan": manifest["recovery_plan"],
            "recovery_code_draft": manifest["recovery_code_draft"],
            "recovery_targets": manifest["recovery_targets"],
            "recovery_ref": contract["ref"],
            "review_bundle_sha256": contract["review_sha"],
            "capture_commit": capture_commit,
            "captured_parent": captured_parent,
            "cleanup_head": captured_parent,
            "targets": [target_record],
            "routing_carriers": routing,
        }

        def validate(payload: dict[str, object]) -> dict[str, object]:
            with (
                mock.patch.object(
                    MODULE,
                    "_accepted_red_commit_parent",
                    return_value=capture_commit,
                ),
                mock.patch.object(
                    MODULE,
                    "_accepted_red_changed_paths",
                    return_value=[contract["cleanup_path"]],
                ),
                mock.patch.object(
                    MODULE,
                    "_accepted_red_json_blob",
                    return_value=payload,
                ),
                mock.patch.object(
                    MODULE,
                    "_accepted_red_tree_entry",
                    return_value=("100644", target_record["blob_oid"], target_bytes),
                ),
            ):
                return MODULE.validate_accepted_red_cleanup_candidate(
                    root,
                    "f" * 40,
                    capture_commit,
                    contract,
                    manifest,
                    {},
                    "manifest_frozen",
                )

        self.assertEqual(validate(cleanup), cleanup)
        malformed = dict(cleanup)
        malformed["cleanup_head"] = "0" * 40
        with self.assertRaisesRegex(
            MODULE.AcceptedRedDurableValidationError,
            "cleanup identity mismatch: cleanup_head",
        ):
            validate(malformed)
        malformed_target = dict(cleanup)
        malformed_target["targets"] = [
            {**target_record, "blob_oid": "0" * 40}
        ]
        with self.assertRaisesRegex(
            MODULE.AcceptedRedDurableValidationError,
            "cleanup HEAD record mismatch: scripts/target.py",
        ):
            validate(malformed_target)
        malformed_routing = dict(cleanup)
        malformed_routing["routing_carriers"] = [
            {"path": "docs/plans/source.md", "blob_oid": "0" * 40}
        ]
        with self.assertRaisesRegex(
            MODULE.AcceptedRedDurableValidationError,
            "cleanup routing-carrier readback mismatch",
        ):
            validate(malformed_routing)

    def test_accepted_red_durable_ref_delegates_to_public_cleanup_validator(
        self,
    ) -> None:
        root = Path("/synthetic/repo")
        capture_commit = "a" * 40
        cleanup_commit = "b" * 40
        cleanup_path = ".planveyor/rejected/source/cleanup.json"
        contract = {
            "ref": "refs/planveyor/rejected-baselines/source/fixture",
            "cleanup_path": cleanup_path,
            "manifest_path": ".planveyor/rejected/source/manifest.json",
        }
        manifest = {"captured_parent": "c" * 40}
        targets = ({"path": "scripts/target.py"},)
        routing = ({"path": "docs/plans/source.md"},)
        recovery_contract = {"recovery_status": "in_progress"}
        cleanup = {"schema": "planveyor_rejected_baseline_cleanup.v1"}
        git_ok = subprocess.CompletedProcess([], 0, b"", b"")

        with (
            mock.patch.object(
                MODULE,
                "_accepted_red_assert_no_object_rewrite_topology",
            ),
            mock.patch.object(MODULE, "_accepted_red_git", return_value=git_ok),
            mock.patch.object(
                MODULE,
                "_accepted_red_git_text",
                return_value=cleanup_commit,
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_tree_entry",
                return_value=("100644", "d" * 40, b"{}"),
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_commit_parent",
                return_value=capture_commit,
            ),
            mock.patch.object(
                MODULE,
                "_accepted_red_validate_manifest",
                return_value=(
                    manifest,
                    targets,
                    routing,
                    recovery_contract,
                    "manifest_frozen",
                ),
            ),
            mock.patch.object(
                MODULE,
                "validate_accepted_red_cleanup_candidate",
                return_value=cleanup,
            ) as candidate_validator,
        ):
            result = MODULE.validate_accepted_red_durable_ref(root, contract)

        self.assertEqual(result.state, "valid_cleanup")
        self.assertEqual(result.cleanup, cleanup)
        candidate_validator.assert_called_once_with(
            root,
            cleanup_commit,
            capture_commit,
            contract,
            manifest,
            recovery_contract,
            "manifest_frozen",
        )

    def test_owner_qna_latest_status_closes_old_open_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_closed.md",
                dedent(
                    """\
                    # Plan: owner qna fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] id=Q1 status=open to=Owner: Which path?
                    - [2026-03-29 17:02 MSK] id=Q1 status=closed to=Owner: Answered by Owner.
                    - [2026-03-29 17:03 MSK] id=Q2 status=open to=Owner: Pick runner.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "open")
        self.assertEqual(payload["owner_qna_readback_reason"], "open_owner_questions")
        self.assertEqual(
            [(item["id"], item["state"]) for item in payload["open_owner_questions"]],
            [("Q2", "open")],
        )

    def test_owner_qna_arrow_carrier_is_open_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_arrow_open.md",
                dedent(
                    """\
                    # Plan: owner qna arrow fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Which path?
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "open")
        self.assertEqual(
            [(item["id"], item["state"]) for item in payload["open_owner_questions"]],
            [("Q1", "open")],
        )

    def test_owner_qna_arrow_question_closes_with_documented_close_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_arrow_closed.md",
                dedent(
                    """\
                    # Plan: owner qna arrow closed fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] (Architect → Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Which path?
                    - [2026-03-29 17:02 MSK] (Architect, id=Q1, status=closed) CLOSED: Owner answered.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "clean")
        self.assertEqual(payload["open_owner_questions"], [])

    def test_owner_qna_malformed_owner_line_blocks_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_malformed.md",
                dedent(
                    """\
                    # Plan: owner qna malformed fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] status=open to=Owner: Missing stable id.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "blocked")
        self.assertEqual(payload["owner_qna_readback_reason"], "malformed_owner_qna_entries")
        self.assertEqual(payload["owner_qna_issues"][0]["kind"], "malformed_owner_qna")
        self.assertIn("id=Qn", payload["owner_qna_issues"][0]["message"])

    def test_owner_qna_legacy_closed_no_questions_line_is_not_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_closed_no_questions.md",
                dedent(
                    """\
                    # Plan: owner qna no questions fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] (Architect, to=Owner, needs_owner=no, status=closed) NO QUESTIONS.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "clean")
        self.assertEqual(payload["owner_qna_issues"], [])

    def test_owner_qna_legacy_id_open_then_closed_is_not_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_legacy_id_closed.md",
                dedent(
                    """\
                    # Plan: owner qna legacy id fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Q&A log
                    - [2026-03-29 17:01 MSK] (A1, Architect, to=Owner, needs_owner=yes, status=open) Choose a path.
                    - [2026-03-29 17:02 MSK] (A1, Architect, to=Owner, needs_owner=no, status=closed) Owner answered.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "clean")
        self.assertEqual(payload["owner_qna_issues"], [])

    def test_owner_qna_quoted_pattern_in_prose_is_not_a_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_owner_qna_prose.md",
                dedent(
                    """\
                    # Plan: owner qna prose fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Evidence
                    - [2026-03-29 17:01 MSK] Provenance refs: custom prompt naively parses `to=Owner status=open`.
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["owner_qna_readback_state"], "clean")
        self.assertEqual(payload["owner_qna_issues"], [])

    def test_current_state_plain_mode_matches_json_semantic_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_oracle_plain_current_state.md",
                dedent(
                    """\
                    # Plan: oracle plain current state fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `docs/code_reviews/missing_fixture.md`
                    """
                ),
            )

            current_state = self._current_state_payload(plan)
            plain = self._current_state_plain(plan)

        parity_fields = (
            "schema",
            "plan_path",
            "status_value",
            "status_norm",
            "status_source",
            "runtime_class",
            "queue_closeout_kind",
            "review_readback_state",
            "review_readback_reason",
            "source_route_state",
            "promoted_from_state",
            "queue_activation_state",
            "route_guard_kind",
            "docs_closeout_state",
            "final_docs_commit",
            "followups_reconciliation_state",
            "process_improvement_capture_state",
            "terminal_ready_state",
            "blocker_state",
        )
        for field in parity_fields:
            with self.subTest(field=field):
                self.assertEqual(plain[field], str(current_state[field]))
        self.assertEqual(json.loads(plain["authorities"]), current_state["authorities"])

    def test_current_state_ignores_long_evidence_tail_for_closeout_facts(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_oracle_long_evidence.md",
                dedent(
                    """\
                    # Plan: long evidence tail fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Evidence
                    - Historical docs closeout prose says final_docs_commit=landed.
                    - Historical followups prose says followups_reconciliation_state=clean_noop.
                    - Historical PI prose says process_improvement_capture_state=materialized.
                    - Historical last green gate: test_plan_status_oracle.py passed.
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)

            current_state = self._current_state_payload(plan)

        self.assertEqual(current_state["queue_closeout_kind"], "terminal_status")
        self.assertEqual(current_state["final_docs_commit"], "contextual_unavailable")
        self.assertEqual(current_state["followups_reconciliation_state"], "contextual_unavailable")
        self.assertEqual(current_state["process_improvement_capture_state"], "contextual_unavailable")
        self.assertEqual(current_state["terminal_ready_state"], "unknown")
        self.assertNotEqual(current_state["terminal_ready_state"], "ready")

    def test_current_state_done_with_green_review_still_requires_closeout_context(self) -> None:
        review_rel = "docs/code_reviews/260329_1700_green_review.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(
                root,
                review_rel,
                dedent(
                    """\
                    # Code review

                    **Date:** 2026-03-29 17:10 MSK
                    **Status:** ✅ OK
                    """
                ),
            )
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_terminal_green_contextual.md",
                dedent(
                    f"""\
                    # Plan: terminal green contextual fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)

            with mock.patch.object(
                MODULE.review_artifact_lint,
                "lint_review_artifacts",
                return_value=[],
            ):
                current_state = self._current_state_payload(plan)

        self.assertEqual(current_state["review_readback_state"], "ok")
        self.assertEqual(current_state["queue_closeout_kind"], "terminal_status")
        self.assertEqual(current_state["blocker_state"], "none")
        self.assertEqual(current_state["terminal_ready_state"], "unknown")
        self.assertIn("docs-closeout", current_state["terminal_ready_reason"])

    def test_duplicate_green_and_red_review_status_fails_closed(self) -> None:
        review_rel = "docs/code_reviews/260329_1700_duplicate_status.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(
                root,
                review_rel,
                dedent(
                    """\
                    # Code review

                    **Date:** 2026-03-29 17:10 MSK
                    **Status:** ✅ OK
                    **Status:** ❌ S1 blocker(ы)
                    """
                ),
            )
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_duplicate_status.md",
                dedent(
                    f"""\
                    # Plan: duplicate review status fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["review_readback_state"], "unknown")
        self.assertEqual(payload["review_route"], "review_readback_unknown")
        self.assertEqual(payload["review_next_owner"], "Architect")
        self.assertEqual(payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(payload["current_state"]["terminal_ready_state"], "blocked")

    def test_empty_duplicate_review_status_fails_closed(self) -> None:
        review_rel = "docs/code_reviews/260329_1700_empty_duplicate_status.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(
                root,
                review_rel,
                "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n"
                "**Status:** ✅ OK\n**Status:**\n",
            )
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_empty_duplicate_status.md",
                "# Plan\n\n**Status:** Ready for Review\n\n## Review artifacts\n"
                f"- Code review (primary): `{review_rel}`\n",
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["review_readback_state"], "unknown")
        self.assertEqual(payload["review_route"], "review_readback_unknown")
        self.assertEqual(payload["current_state"]["blocker_state"], "blocked")

    def test_whitespace_normalized_duplicate_review_status_fails_closed(self) -> None:
        statuses = (
            "**Status:** ✅ OK\n**Status :** ❌ S1 blocker(ы)\n",
            "**Status:** ❌ S1 blocker(ы)\n**Status :** ✅ OK\n",
        )
        for index, status_block in enumerate(statuses, start=1):
            with self.subTest(index=index), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260329_1700_normalized_duplicate_status_{index}.md"
                self._write_plan(
                    root,
                    review_rel,
                    "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n" + status_block,
                )
                plan = self._write_plan(
                    root,
                    f"docs/plans/260329_1700_normalized_duplicate_status_{index}.md",
                    "# Plan\n\n**Status:** Ready for Review\n\n## Review artifacts\n"
                    f"- Code review (primary): `{review_rel}`\n",
                )

                payload = self._json_payload(plan)

            self.assertEqual(payload["review_readback_state"], "unknown")
            self.assertEqual(payload["review_route"], "review_readback_unknown")
            self.assertEqual(payload["current_state"]["blocker_state"], "blocked")

    def test_noncanonical_single_review_status_fails_closed_without_mock(self) -> None:
        review_rel = "docs/code_reviews/260329_1700_noncanonical_single_status.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(
                root,
                review_rel,
                "# Code review\n\n**Status :** ✅ OK\n",
            )
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_noncanonical_single_status.md",
                "# Plan\n\n**Status:** Ready for Review\n\n## Review artifacts\n"
                f"- Code review (primary): `{review_rel}`\n",
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["review_readback_state"], "unknown")
        self.assertEqual(payload["review_route"], "review_readback_unknown")
        self.assertEqual(payload["current_state"]["blocker_state"], "blocked")

    def test_quoted_historical_review_status_is_not_a_header(self) -> None:
        review_rel = "docs/code_reviews/260329_1700_quoted_status.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(
                root,
                review_rel,
                "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n"
                "**Status:** ✅ OK\n\n> **Status:** ❌ S1 blocker(ы)\n",
            )
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_quoted_status.md",
                "# Plan\n\n**Status:** Ready for Arch review\n\n## Review artifacts\n"
                f"- Code review (primary): `{review_rel}`\n",
            )

            with mock.patch.object(
                MODULE.review_artifact_lint,
                "lint_review_artifacts",
                return_value=[],
            ):
                payload = self._json_payload(plan)

        self.assertEqual(payload["review_readback_state"], "ok")
        self.assertEqual(payload["review_route"], "review_green")

    def test_fenced_or_indented_historical_review_status_is_not_a_header(self) -> None:
        examples = {
            "fenced": "\n```text\n**Status:** ❌ S1 blocker(ы)\n```\n",
            "indented": "\n    **Status:** ❌ S1 blocker(ы)\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260329_1700_{case}_status.md"
                self._write_plan(
                    root,
                    review_rel,
                    "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n"
                    "**Status:** ✅ OK\n" + example,
                )
                plan = self._write_plan(
                    root,
                    f"docs/plans/260329_1700_{case}_status.md",
                    "# Plan\n\n**Status:** Ready for Arch review\n\n## Review artifacts\n"
                    f"- Code review (primary): `{review_rel}`\n",
                )

                with mock.patch.object(
                    MODULE.review_artifact_lint,
                    "lint_review_artifacts",
                    return_value=[],
                ):
                    payload = self._json_payload(plan)

            self.assertEqual(payload["review_readback_state"], "ok")
            self.assertEqual(payload["review_route"], "review_green")

    def test_body_fence_content_cannot_override_green_header(self) -> None:
        examples = {
            "invalid_fence_info": "\n```bad`info\n**Status:** ❌ S1 blocker(ы)\n",
            "html_comment_fence": "\n<!--\n```text\n-->\n**Status:** ❌ S1 blocker(ы)\n```\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260329_1700_{case}.md"
                self._write_plan(
                    root,
                    review_rel,
                    "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n"
                    "**Status:** ✅ OK\n" + example,
                )
                plan = self._write_plan(
                    root,
                    f"docs/plans/260329_1700_{case}.md",
                    "# Plan\n\n**Status:** Ready for Review\n\n## Review artifacts\n"
                    f"- Code review (primary): `{review_rel}`\n",
                )

                with mock.patch.object(
                    MODULE.review_artifact_lint,
                    "lint_review_artifacts",
                    return_value=[],
                ):
                    payload = self._json_payload(plan)

            self.assertEqual(payload["review_readback_state"], "ok")
            self.assertEqual(payload["review_route"], "review_green")

    def test_list_item_fenced_status_does_not_block_green_header(self) -> None:
        examples = {
            "bullet": "\n- ```text\n  **Status:** ❌ S1 blocker(ы)\n  ```\n",
            "ordered": "\n1. ```text\n   **Status:** ❌ S1 blocker(ы)\n   ```\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260329_1700_{case}_list_fence.md"
                self._write_plan(
                    root,
                    review_rel,
                    "# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n"
                    "**Status:** ✅ OK\n" + example,
                )
                plan = self._write_plan(
                    root,
                    f"docs/plans/260329_1700_{case}_list_fence.md",
                    "# Plan\n\n**Status:** Ready for Arch review\n\n## Review artifacts\n"
                    f"- Code review (primary): `{review_rel}`\n",
                )

                with mock.patch.object(
                    MODULE.review_artifact_lint,
                    "lint_review_artifacts",
                    return_value=[],
                ):
                    payload = self._json_payload(plan)

            self.assertEqual(payload["review_readback_state"], "ok")
            self.assertEqual(payload["review_route"], "review_green")

    def test_body_date_is_not_header_metadata(self) -> None:
        date_value, status_value = MODULE._review_header_values(
            "# Review\n\n**Status:** ✅ OK\n\nSummary body.\n"
            "**Date:** 2026-03-29 17:10 MSK\n"
        )

        self.assertIsNone(date_value)
        self.assertEqual(status_value, "✅ OK")

    def test_noncanonical_red_like_review_status_fails_closed_to_unknown(self) -> None:
        for index, status in enumerate(
            ("resolved after S1 blocker", "✅ OK / ❌ S1 blocker(ы)"),
            start=1,
        ):
            with self.subTest(status=status), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260329_1700_red_like_{index}.md"
                self._write_plan(
                    root,
                    review_rel,
                    f"# Code review\n\n**Date:** 2026-03-29 17:10 MSK\n**Status:** {status}\n",
                )
                plan = self._write_plan(
                    root,
                    f"docs/plans/260329_1700_red_like_{index}.md",
                    "# Plan\n\n**Status:** Ready for Review\n\n## Review artifacts\n"
                    f"- Code review (primary): `{review_rel}`\n",
                )

                payload = self._json_payload(plan)

            self.assertEqual(payload["review_readback_state"], "unknown")
            self.assertEqual(payload["review_route"], "review_readback_unknown")
            self.assertEqual(payload["review_next_owner"], "Architect")

    def test_current_state_missing_declared_review_artifact_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1700_missing_review_artifact.md",
                dedent(
                    """\
                    # Plan: missing review fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Review artifacts
                    - Code review (primary): `docs/code_reviews/missing_fixture.md`
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)

            current_state = self._current_state_payload(plan)

        self.assertEqual(current_state["review_readback_state"], "none")
        self.assertEqual(current_state["blocker_state"], "unknown")
        self.assertEqual(current_state["terminal_ready_state"], "unknown")
        self.assertNotEqual(current_state["terminal_ready_state"], "ready")


    def test_duplicate_header_status_fails_with_line_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1701_oracle_duplicate_status.md",
                dedent(
                    """\
                    # Plan: broken oracle fixture

                    **Date:** 2026-03-29 17:01 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder
                    **Status:** In progress

                    ## Problem
                    - Duplicate header status should fail.
                    """
                ),
            )
            stderr = io.StringIO()

            with mock.patch("sys.stderr", stderr):
                result = MODULE.main([str(plan)])

        self.assertEqual(result, 3)
        output = stderr.getvalue()
        self.assertIn("expected exactly 1 header **Status:** line, got 2", output)
        self.assertIn("7:**Status:** Ready for Coder", output)
        self.assertIn("8:**Status:** In progress", output)

    def test_json_output_exposes_parked_umbrella_runtime_class_and_non_executable_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1702_oracle_parked_umbrella.md",
                dedent(
                    """\
                    # Plan: parked umbrella fixture

                    **Date:** 2026-03-29 17:02 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Planner

                    **Handoff statuses (кто ставит):**
                    - `Ready for Planner` — Architect
                    - `Ready for Coder` — `N/A (parked umbrella)`
                    - `Ready for Review` — `N/A (parked umbrella)`
                    - `Ready for Arch review` — `N/A (parked umbrella)`
                    - `Done` — Architect

                    **Context links (source of truth):**
                    - Code draft(s): `N/A (parked umbrella)`

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "parked",
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime_class"], "parked_umbrella")
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "decomposition_children_missing")
        self.assertEqual(payload["decomposition_child_state"], "missing")

    def test_json_output_accepts_ascii_handoff_separators_for_parked_umbrella(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1704_oracle_parked_umbrella_ascii_handoff.md",
                dedent(
                    """\
                    # Plan: parked umbrella ASCII separator fixture

                    **Date:** 2026-03-29 17:04 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Planner

                    **Handoff statuses (кто ставит):**
                    - `Ready for Planner` - Architect
                    - `Ready for Coder` - `N/A (parked umbrella)`
                    - `Ready for Review` - `N/A (parked umbrella)`
                    - `Ready for Arch review` - `N/A (parked umbrella)`
                    - `Done` - Architect

                    **Context links (source of truth):**
                    - Code draft(s): `N/A (parked umbrella)`

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "parked",
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime_class"], "parked_umbrella")
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "decomposition_children_missing")
        self.assertEqual(payload["decomposition_child_state"], "missing")

    def test_json_output_keeps_phase_state_parked_executable_when_markers_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1705_oracle_parked_missing_markers.md",
                dedent(
                    """\
                    # Plan: parked missing markers fixture

                    **Date:** 2026-03-29 17:05 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Planner

                    **Handoff statuses (кто ставит):**
                    - `Ready for Planner` — Architect
                    - `Ready for Coder` — Planner
                    - `Ready for Review` — Coder
                    - `Ready for Arch review` — Reviewer
                    - `Done` — Architect

                    **Context links (source of truth):**
                    - Code draft(s): `docs/code_drafts/260329_1705_oracle_parked_missing_markers__code_draft.md`

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "parked",
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime_class"], "executable")
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "decomposition_children_missing")
        self.assertIn("without complete repo-backed non-executable markers", payload["runtime_class_reason"])

    def test_json_output_keeps_ready_for_planner_executable_when_markers_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1703_oracle_ambiguous_ready_for_planner.md",
                dedent(
                    """\
                    # Plan: ambiguous ready-for-planner fixture

                    **Date:** 2026-03-29 17:03 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Planner

                    **Handoff statuses (кто ставит):**
                    - `Ready for Planner` — Architect
                    - `Ready for Coder` — Planner
                    - `Ready for Review` — Coder
                    - `Ready for Arch review` — Reviewer
                    - `Done` — Architect

                    **Context links (source of truth):**
                    - Code draft(s): `docs/code_drafts/260329_1703_oracle_ambiguous_ready_for_planner__code_draft.md`

                    ## Problem
                    1. Fixture.
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["runtime_class"], "executable")
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "not_ready")
        self.assertEqual(payload["plan_type_norm"], "dev")
        self.assertFalse(payload["route_guard_triggered"])
        self.assertEqual(payload["route_guard_kind"], "none")

    def test_scope_expansion_absent_readback_matches_json_and_current_state_plain(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260722_1942_scope_absent.md",
                self._scope_expansion_body(
                    status="Ready for Coder",
                    include_scope_expansion=False,
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)

            payload = self._json_payload(plan)
            current_state = payload["current_state"]
            plain = self._current_state_plain(plan)

        expected = {
            "scope_expansion_carrier_state": "absent",
            "scope_expansion_state": "absent",
            "scope_expansion_target_contour": "",
            "scope_expansion_source_ref": "",
            "scope_expansion_reason": "",
        }
        for field, value in expected.items():
            with self.subTest(field=field):
                self.assertEqual(payload[field], value)
                self.assertEqual(current_state[field], value)
                self.assertEqual(plain[field], value)
        self.assertEqual(current_state["authorities"]["scope_expansion"]["state"], "absent")
        self.assertFalse(payload["route_guard_triggered"])

    def test_scope_expansion_valid_nonblocking_states_preserve_ordinary_route(self) -> None:
        for state in ("n/a", "suspected"):
            with self.subTest(state=state), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                plan = self._write_plan(
                    root,
                    f"docs/plans/260722_1942_scope_{state.replace('/', '_')}.md",
                    self._scope_expansion_body(
                        status="In progress",
                        scope_expansion={
                            "state": f"  {state.upper()}  ",
                            "target_contour": "  analysis_wave  ",
                            "source_ref": "  docs/plans/source.md#Evidence  ",
                            "reason": "  bounded evidence  ",
                        },
                    ),
                )
                self._attach_not_applicable_machine_authority(root, plan)

                payload = self._json_payload(plan)

                self.assertEqual(payload["scope_expansion_carrier_state"], "valid")
                self.assertEqual(payload["scope_expansion_state"], state)
                self.assertEqual(payload["scope_expansion_target_contour"], "analysis_wave")
                self.assertEqual(payload["scope_expansion_source_ref"], "docs/plans/source.md#Evidence")
                self.assertEqual(payload["scope_expansion_reason"], "bounded evidence")
                self.assertFalse(payload["route_guard_triggered"])
                self.assertEqual(payload["route_guard_kind"], "none")

    def test_scope_expansion_malformed_carriers_fail_closed(self) -> None:
        malformed_cases = {
            "null": None,
            "non_object": ["reroute_required"],
            "missing_reason": {
                "state": "reroute_required",
                "target_contour": "analysis_wave",
                "source_ref": "docs/plans/source.md#Evidence",
            },
            "invalid_state": {
                "state": "automatic_decomposition",
                "target_contour": "decomposition_wave",
                "source_ref": "docs/plans/source.md#Evidence",
                "reason": "invalid state fixture",
            },
            "wrong_type_state": {
                "state": ["reroute_required"],
                "target_contour": "decomposition_wave",
                "source_ref": "docs/plans/source.md#Evidence",
                "reason": "wrong state type fixture",
            },
            "wrong_type_target_contour": {
                "state": "reroute_required",
                "target_contour": {"name": "decomposition_wave"},
                "source_ref": "docs/plans/source.md#Evidence",
                "reason": "wrong contour type fixture",
            },
            "wrong_type_source_ref": {
                "state": "reroute_required",
                "target_contour": "decomposition_wave",
                "source_ref": ["docs/plans/source.md#Evidence"],
                "reason": "wrong source type fixture",
            },
            "wrong_type_reason": {
                "state": "reroute_required",
                "target_contour": "decomposition_wave",
                "source_ref": "docs/plans/source.md#Evidence",
                "reason": {"text": "wrong reason type fixture"},
            },
        }
        for name, carrier in malformed_cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                plan = self._write_plan(
                    root,
                    f"docs/plans/260722_1942_scope_malformed_{name}.md",
                    self._scope_expansion_body(
                        status="Ready for Coder",
                        scope_expansion=carrier,
                    ),
                )

                payload = self._json_payload(plan)

                self.assertEqual(payload["scope_expansion_carrier_state"], "malformed")
                self.assertEqual(payload["scope_expansion_state"], "unknown")
                self.assertEqual(payload["scope_expansion_target_contour"], "")
                self.assertEqual(payload["scope_expansion_source_ref"], "")
                self.assertEqual(payload["scope_expansion_reason"], "")
                self.assertTrue(payload["route_guard_triggered"])
                self.assertEqual(payload["route_guard_kind"], "scope_expansion_malformed")
                self.assertEqual(payload["route_guard_next_owner"], "Architect")
                self.assertIn("plan_meta.scope_expansion", payload["route_guard_reason"])
                self.assertEqual(payload["current_state"]["blocker_state"], "blocked")
                if name.startswith("wrong_type_"):
                    self.assertIn("must be strings", payload["route_guard_reason"])

    def test_scope_expansion_reroute_required_precedes_downstream_status_route(self) -> None:
        statuses = (
            "Ready for Coder",
            "In progress",
            "Ready for Review",
            "Reviewer intake",
            "Reviewer code review",
        )
        for status in statuses:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                plan = self._write_plan(
                    root,
                    "docs/plans/260722_1942_scope_reroute.md",
                    self._scope_expansion_body(
                        status=status,
                        scope_expansion={
                            "state": "reroute_required",
                            "target_contour": "decomposition_wave",
                            "source_ref": "docs/plans/source.md#Evidence",
                            "reason": "one executable contour no longer holds",
                        },
                    ),
                )

                payload = self._json_payload(plan)

                self.assertTrue(payload["route_guard_triggered"])
                self.assertEqual(payload["route_guard_kind"], "scope_expansion_reroute_required")
                self.assertEqual(payload["route_guard_next_owner"], "Architect")

    def test_scope_expansion_guard_precedes_existing_review_only_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260722_1942_scope_review_only_precedence.md",
                self._scope_expansion_body(
                    status="Ready for Coder",
                    plan_type="review-only",
                    scope_expansion={
                        "state": "reroute_required",
                        "target_contour": "analysis_wave",
                        "source_ref": "docs/plans/source.md#Evidence",
                        "reason": "scope signal owns guard precedence",
                    },
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["route_guard_kind"], "scope_expansion_reroute_required")
        self.assertNotEqual(payload["route_guard_kind"], "review_only_wrong_status")

    def test_scope_expansion_architect_accepted_blocks_every_downstream_status_group(self) -> None:
        for status in (
            "Ready for Planner",
            "Planner intake",
            "Planner finalize",
            "Ready for Coder",
            "Coder intake",
            "In progress",
            "Ready for Review",
            "Reviewer intake",
            "Reviewer code review",
            "Reviewer visual review",
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                plan = self._write_plan(
                    root,
                    "docs/plans/260722_1942_scope_accepted_wrong_status.md",
                    self._scope_expansion_body(
                        status=status,
                        scope_expansion={
                            "state": "architect_accepted",
                            "target_contour": "analysis_wave",
                            "source_ref": "docs/plans/source.md#Evidence",
                            "reason": "Architect accepted a new contour",
                        },
                    ),
                )

                payload = self._json_payload(plan)

                self.assertTrue(payload["route_guard_triggered"])
                self.assertEqual(
                    payload["route_guard_kind"],
                    "scope_expansion_architect_accepted_wrong_status",
                )
                self.assertEqual(payload["route_guard_next_owner"], "Architect")

    def test_scope_expansion_architect_accepted_allows_architect_and_superseded_release_states(self) -> None:
        for status in ("Architect response", "Ready for Arch review", "Superseded"):
            with self.subTest(status=status), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                plan = self._write_plan(
                    root,
                    "docs/plans/260722_1942_scope_accepted_release.md",
                    self._scope_expansion_body(
                        status=status,
                        scope_expansion={
                            "state": "architect_accepted",
                            "target_contour": "decomposition_wave",
                            "source_ref": "docs/plans/source.md#Evidence",
                            "reason": "Architect is materializing the successor",
                        },
                    ),
                )
                self._attach_not_applicable_machine_authority(root, plan)

                payload = self._json_payload(plan)

                self.assertFalse(payload["route_guard_triggered"])
                self.assertEqual(payload["route_guard_kind"], "none")

    def test_scope_expansion_architect_accepted_done_blocks_raw_terminal_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260722_2016_scope_accepted_done.md",
                self._scope_expansion_body(
                    status="Done",
                    scope_expansion={
                        "state": "architect_accepted",
                        "target_contour": "decomposition_wave",
                        "source_ref": "docs/plans/source.md#Evidence",
                        "reason": "Architect accepted a new contour",
                    },
                ),
            )

            payload = self._json_payload(plan)

        self.assertTrue(payload["route_guard_triggered"])
        self.assertEqual(
            payload["route_guard_kind"],
            "scope_expansion_architect_accepted_wrong_status",
        )
        self.assertEqual(payload["route_guard_next_owner"], "Architect")
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "route_guard_blocked")
        self.assertFalse(payload["current_state"]["queue_closeout_ready"])
        self.assertEqual(payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(payload["current_state"]["terminal_ready_state"], "blocked")

    def test_active_planning_contours_do_not_infer_scope_guard_without_explicit_stop(self) -> None:
        cases = (
            ("analysis", "analysis_wave", None, None),
            ("decomposition", None, "decomposition_wave", "active"),
        )
        for name, wave_family, phase_overlay, phase_state in cases:
            for scope_state in ("n/a", "suspected"):
                with self.subTest(name=name, scope_state=scope_state), temporary_git_root() as tmpdir:
                    root = Path(tmpdir).resolve()
                    self._write_plan_vocab(root)
                    plan = self._write_plan(
                        root,
                        f"docs/plans/260722_1942_scope_active_{name}_{scope_state.replace('/', '_')}.md",
                        self._scope_expansion_body(
                            status="In progress",
                            wave_family=wave_family,
                            phase_overlay=phase_overlay,
                            phase_state=phase_state,
                            scope_expansion={
                                "state": scope_state,
                                "target_contour": "N/A",
                                "source_ref": "N/A (why=active planning contour fixture)",
                                "reason": "N/A (why=no ordinary developer-wave reroute)",
                            },
                        ),
                    )
                    self._attach_not_applicable_machine_authority(
                        root,
                        plan,
                        strict_decomposition_parent=name == "decomposition",
                    )

                    payload = self._json_payload(plan)

                    self.assertFalse(payload["route_guard_triggered"])
                    self.assertEqual(payload["route_guard_kind"], "none")

    def test_review_only_ready_for_planner_triggers_route_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1706_oracle_review_only_wrong_status.md",
                dedent(
                    """\
                    # Plan: review-only wrong status fixture

                    **Date:** 2026-03-29 17:06 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** review-only
                    **Status:** Ready for Planner

                    ## Problem
                    Review-only plan should not enter Planner silently.
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["plan_type"], "review-only")
        self.assertEqual(payload["plan_type_norm"], "review-only")
        self.assertTrue(payload["route_guard_triggered"])
        self.assertEqual(payload["route_guard_kind"], "review_only_wrong_status")
        self.assertEqual(payload["route_guard_next_owner"], "Architect")
        self.assertIn("Planner/Coder implementation lane", payload["route_guard_reason"])

    def test_review_only_reviewer_intake_does_not_trigger_route_guard(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1707_oracle_review_only_reviewer_intake.md",
                dedent(
                    """\
                    # Plan: review-only reviewer status fixture

                    **Date:** 2026-03-29 17:07 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** review-only
                    **Status:** Reviewer intake

                    ## Problem
                    Review-only plan starts directly in Reviewer lane.
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["plan_type_norm"], "review-only")
        self.assertFalse(payload["route_guard_triggered"])
        self.assertEqual(payload["route_guard_kind"], "none")

    def test_review_only_explicit_architect_override_does_not_trigger_route_guard(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260329_1708_oracle_review_only_override.md",
                dedent(
                    """\
                    # Plan: review-only override fixture

                    **Date:** 2026-03-29 17:08 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** review-only
                    **Status:** Ready for Coder

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": [],
                        "review_only_route_override": {
                          "owner": "Architect",
                          "allow_planner_coder_lane": true,
                          "reason": "Fixture explicitly validates an exceptional review-only implementation carrier."
                        }
                      }
                    }
                    ```
                    """
                ),
            )
            self._attach_not_applicable_machine_authority(root, plan)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["plan_type_norm"], "review-only")
        self.assertFalse(payload["route_guard_triggered"])
        self.assertEqual(payload["route_guard_kind"], "none")
        self.assertIn("review_only_route_override", payload["route_guard_reason"])

    def test_active_decomposition_without_child_graph_exposes_missing_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan = self._write_plan(
                root,
                "docs/plans/260517_1623_active_decomposition_missing_children.md",
                dedent(
                    """\
                    # Plan: active decomposition missing children

                    **Date:** 2026-05-17 16:23 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
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
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["queue_closeout_ready"])
        self.assertEqual(payload["queue_closeout_kind"], "decomposition_children_missing")
        self.assertEqual(payload["decomposition_child_state"], "missing")
        self.assertEqual(payload["decomposition_child_issues"][0]["kind"], "decomposition_children_missing")

    def test_active_decomposition_with_three_children_requires_small_model_contracts(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            child_paths = [
                "docs/plans/260517_1630_child_a.md",
                "docs/plans/260517_1631_child_b.md",
                "docs/plans/260517_1632_child_c.md",
            ]
            for rel_path in child_paths:
                self._write_plan(
                    root,
                    rel_path,
                    dedent(
                        """\
                        # Plan: child fixture

                        **Date:** 2026-05-17 16:30 MSK
                        **Stage:** Stage 1
                        **Priority:** P1
                        **Plan type:** dev
                        **Status:** Ready for Coder
                        """
                    ),
                )
            next_plans_json = json.dumps(child_paths, indent=8)
            execution_rows = "\n".join(f"                    - Plan: `{rel_path}`" for rel_path in child_paths)
            child_map_rows = "\n".join(
                f"                    | {idx} | `{rel_path}` | child {idx} |"
                for idx, rel_path in enumerate(child_paths, start=1)
            )
            plan = self._write_plan(
                root,
                "docs/plans/260517_1624_active_decomposition_three_children.md",
                dedent(
                    f"""\
                    # Plan: active decomposition three children

                    **Date:** 2026-05-17 16:24 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": {next_plans_json},
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    ```

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
{child_map_rows}

                    ## Execution queue
                    - Resume parent: `run-parent-once`
{execution_rows}
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["decomposition_child_state"], "queue_ready")
        self.assertEqual(payload["decomposition_child_paths"], child_paths)
        self.assertEqual(payload["decomposition_child_issues"], [])
        self.assertEqual(payload["small_model_ready_child"], "false")
        self.assertEqual(payload["small_model_readiness_state"], "blocked")
        self.assertEqual(payload["queue_closeout_kind"], "small_model_ready_child_blocked")
        self.assertEqual(payload["small_model_readiness_findings"][0]["field"], "Task outcome")

    def test_active_decomposition_reports_small_model_readiness_blocker(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            child_rel = "docs/plans/260611_2101_child_missing_context.md"
            self._write_plan(
                root,
                child_rel,
                dedent(
                    """\
                    # Plan: child missing context

                    **Date:** 2026-06-11 21:01 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder

                    ## Small-model-ready child contract
                    | Field | Value |
                    | --- | --- |
                    | Task outcome | fixture child produces one observable helper result |
                    | Mutable surfaces | `scripts/fixture.py` |
                    | Read-only surfaces | `docs/playbooks/decomposition_wave.md` |
                    | Forbidden scope | model defaults |
                    | Inputs from parent/predecessor | `docs/plans/parent.md` |
                    | Output to consumer | `docs/plans/child.md` status/evidence |
                    | Acceptance/proof lane | `python -m unittest scripts.test_plan_status_oracle` |
                    | Stop condition | return to Planner if new helper CLI semantics are needed |
                    | Expected reviewer lane | code |
                    | Runner suitability | small runner OK; fallback to Coder if target bundle expands |
                    | Task size/complexity | small; focused helper change |
                    | Readiness notes | no known clarity gaps |
                    """
                ),
            )
            plan = self._write_plan(
                root,
                "docs/plans/260611_2100_active_decomposition_blocked_child.md",
                dedent(
                    f"""\
                    # Plan: active decomposition blocked child

                    **Date:** 2026-06-11 21:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": ["{child_rel}"],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    ```

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | missing context child |

                    ## Execution queue
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["small_model_ready_child"], "false")
        self.assertEqual(payload["small_model_readiness_state"], "blocked")
        self.assertEqual(payload["queue_closeout_kind"], "small_model_ready_child_blocked")
        finding = payload["small_model_readiness_findings"][0]
        self.assertEqual(finding["child_path"], child_rel)
        self.assertEqual(finding["field"], "Local context bundle")
        self.assertEqual(finding["severity"], "hard")
        self.assertTrue(finding["blocks_queue"])

    def test_small_model_readiness_treats_template_angle_values_as_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            child_rel = "docs/plans/260611_2102_child_template_placeholders.md"
            child = self._write_plan(
                root,
                child_rel,
                dedent(
                    """\
                    # Plan: child template placeholders

                    **Date:** 2026-06-11 21:02 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder

                    ## Small-model-ready child contract
                    | Field | Value |
                    | --- | --- |
                    | Task outcome | <one observable result> |
                    | Local context bundle | <exact docs/plans/reviews/helpers to read first> |
                    | Mutable surfaces | <exact paths/path families allowed to change> |
                    | Read-only surfaces | <anchors allowed for reading only> |
                    | Forbidden scope | <explicit non-goals / nearby tempting changes> |
                    | Inputs from parent/predecessor | <artifact paths and dependency gates> |
                    | Output to consumer | <artifact/status/queue effect and consumer> |
                    | Acceptance/proof lane | <exact commands/checks/receipts/review lane> |
                    | Stop condition | <when to return upstream instead of guessing> |
                    | Expected reviewer lane | <docs-only/code/risk/contracts/visual> |
                    | Runner suitability | <recommended runner class plus fallback/degraded condition> |
                    | Task size/complexity | <small|medium|large and why> |
                    | Readiness notes | <known clarity gaps / confidence notes> |
                    """
                ),
            )

            findings = MODULE.small_model_ready_child_findings(child, child_path=child_rel, promoted=True)

        self.assertGreaterEqual(len(findings), 13)
        self.assertTrue(all(finding.finding_kind == "placeholder" for finding in findings), findings)
        self.assertTrue(any(finding.field == "Task outcome" and finding.blocks_queue for finding in findings))
        self.assertTrue(any(finding.field == "Runner suitability" and not finding.blocks_queue for finding in findings))

    def test_active_decomposition_execution_queue_can_exceed_bounded_next_plans(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            child_paths = [
                "docs/plans/260517_1640_child_a.md",
                "docs/plans/260517_1641_child_b.md",
                "docs/plans/260517_1642_child_c.md",
                "docs/plans/260517_1643_child_d.md",
                "docs/plans/260517_1644_child_e.md",
            ]
            for rel_path in child_paths:
                self._write_plan(
                    root,
                    rel_path,
                    dedent(
                        """\
                        # Plan: child fixture

                        **Date:** 2026-05-17 16:40 MSK
                        **Stage:** Stage 1
                        **Priority:** P1
                        **Plan type:** dev
                        **Status:** Ready for Coder
                        """
                    ),
                )
            next_plans_json = json.dumps(child_paths[:2], indent=8)
            execution_rows = "\n".join(f"                    - Plan: `{rel_path}`" for rel_path in child_paths)
            child_map_rows = "\n".join(
                f"                    | {idx} | `{rel_path}` | child {idx} |"
                for idx, rel_path in enumerate(child_paths, start=1)
            )
            plan = self._write_plan(
                root,
                "docs/plans/260517_1639_active_decomposition_full_queue_bounded_next.md",
                dedent(
                    f"""\
                    # Plan: active decomposition full queue bounded next

                    **Date:** 2026-05-17 16:39 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": {next_plans_json},
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    ```

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
{child_map_rows}

                    ## Execution queue
                    - Resume parent: `run-parent-once`
{execution_rows}
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(plan), "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["decomposition_child_state"], "queue_ready")
        self.assertEqual(payload["decomposition_child_paths"], child_paths)
        self.assertEqual(payload["decomposition_child_issues"], [])

    def test_analysis_source_route_artifact_readback_is_additive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_0142_analysis_source.md",
                dedent(
                    """\
                    # Plan: analysis source

                    **Date:** 2026-06-14 01:42 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": "analysis_wave",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Promoted route artifact
                    | Field | Value |
                    | --- | --- |
                    | `source_analysis_plan` | `docs/plans/260614_0142_analysis_source.md` |
                    | `source_analysis_pack_ref` | `docs/plans/260614_0142_analysis_source.md#Analysis-pack` |
                    | `accepted_route` | `decomposition_wave` |
                    | `promoted_artifact_kind` | `decomposition_umbrella` |
                    | `promoted_artifact_ref` | `docs/plans/260614_1432_process_post_e2_enforcement_decomposition_umbrella.md` |
                    | `queue_admission` | `needs_planner` |
                    | `runner_admission` | `frontier_only` |
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["planning_contour_marker"], "analysis_wave")
        self.assertEqual(payload["planning_contour_role"], "source_analysis")
        self.assertEqual(payload["planning_contour_readback_state"], "valid")
        self.assertEqual(payload["source_route_state"], "valid")
        self.assertEqual(payload["source_route_accepted_route"], "decomposition_wave")
        self.assertEqual(payload["source_route_promoted_artifact_kind"], "decomposition_umbrella")
        self.assertEqual(
            payload["source_route_promoted_artifact_ref"],
            "docs/plans/260614_1432_process_post_e2_enforcement_decomposition_umbrella.md",
        )
        self.assertEqual(payload["source_route_queue_admission"], "needs_planner")
        self.assertEqual(payload["source_route_runner_admission"], "frontier_only")
        self.assertEqual(payload["promoted_from_state"], "not_applicable")
        self.assertEqual(payload["queue_activation_carrier_state"], "not_applicable")
        current_state = payload["current_state"]
        self.assertEqual(current_state["source_route_state"], "valid")
        self.assertEqual(current_state["source_route_queue_admission"], "needs_planner")
        self.assertEqual(current_state["source_route_runner_admission"], "frontier_only")
        self.assertEqual(current_state["authorities"]["source_promoted_route"]["state"], "valid")

    def test_analysis_route_lifecycle_green_readback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_green.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard; "
                    "source_refs_baseline=docs/playbooks/analysis_wave.md; current_source_refs=docs/playbooks/analysis_wave.md |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "ok")
        self.assertEqual(payload["analysis_route_lifecycle_stale_trigger_state"], "unchanged")
        self.assertEqual(payload["analysis_route_lifecycle_needs_analysis_depth_cap"], "2")
        self.assertEqual(payload["analysis_route_lifecycle_current_needs_analysis_depth"], "1")

    def test_analysis_route_lifecycle_missing_budget_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_missing.md",
                analysis_rows="| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard |",
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "warning")
        self.assertIn("missing lifecycle budget", payload["analysis_route_lifecycle_reason"])

    def test_analysis_route_lifecycle_malformed_budget_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_malformed.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=two; current_needs_analysis_depth=one; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "warning")
        self.assertIn("depth values must be numeric", payload["analysis_route_lifecycle_reason"])

    def test_analysis_route_lifecycle_ambiguous_source_baseline_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_ambiguous.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "warning")
        self.assertEqual(payload["analysis_route_lifecycle_stale_trigger_state"], "unknown")
        self.assertIn("source subject/ref baseline", payload["analysis_route_lifecycle_reason"])

    def test_analysis_route_lifecycle_exhausted_stops_to_architect(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_exhausted.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=exhausted; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "architect_stop")
        self.assertEqual(payload["analysis_route_lifecycle_next_owner"], "Architect")
        self.assertIn("budget_status=exhausted", payload["analysis_route_lifecycle_reason"])

    def test_analysis_route_lifecycle_depth_override_allows_green(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_override.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=3; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck; override_ref=docs/plans/260619_0028_override.md#Architect-QA |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "ok")

    def test_analysis_route_lifecycle_source_change_is_stale(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_stale.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_subject_baseline=budget guard; current_source_subject=budget guard v2; "
                    "change_ref=docs/plans/260619_0028_changed.md; action=architect_recheck |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "stale_needs_architect_review")
        self.assertEqual(payload["analysis_route_lifecycle_next_owner"], "Architect")
        self.assertEqual(payload["analysis_route_lifecycle_stale_trigger_state"], "changed")

    def test_analysis_route_lifecycle_comma_source_refs_change_is_stale(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_analysis_lifecycle_fixture(
                root,
                "docs/plans/260619_0028_analysis_lifecycle_comma_refs_stale.md",
                analysis_rows=(
                    "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                    "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; "
                    "exhaustion_action=architect_recheck |\n"
                    "| `stale_trigger` | source_refs_baseline=docs/a.md, docs/b.md; "
                    "current_source_refs=docs/a.md, docs/c.md |"
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["analysis_route_lifecycle_state"], "stale_needs_architect_review")
        self.assertEqual(payload["analysis_route_lifecycle_next_owner"], "Architect")
        self.assertEqual(payload["analysis_route_lifecycle_stale_trigger_state"], "changed")
        self.assertIn("source refs changed", payload["analysis_route_lifecycle_reason"])

    def test_analysis_source_route_invalid_enum_values_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_0143_analysis_source_invalid_enums.md",
                dedent(
                    """\
                    # Plan: analysis source invalid enums

                    **Date:** 2026-06-14 01:43 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": "analysis_wave",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Promoted route artifact
                    | Field | Value |
                    | --- | --- |
                    | `accepted_route` | `typo_wave` |
                    | `promoted_artifact_kind` | `bogus_kind` |
                    | `promoted_artifact_ref` | `docs/plans/260614_1432_process_post_e2_enforcement_decomposition_umbrella.md` |
                    | `queue_admission` | `whatever` |
                    | `runner_admission` | `wrong_runner` |
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["source_route_state"], "missing_required")
        self.assertEqual(payload["planning_contour_readback_state"], "warning")
        self.assertIn("source_route_state=missing_required", payload["planning_contour_readback_reason"])

    def test_non_executable_defer_route_reports_missing_revisit_when(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_0144_analysis_defer_missing_revisit.md",
                dedent(
                    """\
                    # Plan: analysis defer source

                    **Date:** 2026-06-14 01:44 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": "analysis_wave",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Promoted route artifact
                    | Field | Value |
                    | --- | --- |
                    | `accepted_route` | `defer` |
                    | `promoted_artifact_kind` | `followup` |
                    | `promoted_artifact_ref` | `docs/followups/260614_0144_followup.md` |
                    | `queue_admission` | `not_queueable` |
                    | `runner_admission` | `frontier_only` |
                    | `subject_identity` | `exact(qa_wave public command carrier)` |
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["source_route_state"], "valid")
        self.assertEqual(payload["source_route_non_executable_carrier_state"], "missing_required")
        self.assertIn("revisit_when", payload["source_route_non_executable_carrier_reason"])
        self.assertEqual(payload["planning_contour_readback_state"], "warning")
        self.assertIn("source_route_non_executable_carrier_state=missing_required", payload["planning_contour_readback_reason"])
        current_state = payload["current_state"]
        self.assertEqual(current_state["source_route_non_executable_carrier_state"], "missing_required")
        self.assertEqual(current_state["authorities"]["source_promoted_route"]["non_executable_carrier_state"], "missing_required")

    def test_non_executable_defer_route_reports_valid_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_0145_analysis_defer_valid.md",
                dedent(
                    """\
                    # Plan: analysis defer source

                    **Date:** 2026-06-14 01:45 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Done

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": "analysis_wave",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Promoted route artifact
                    | Field | Value |
                    | --- | --- |
                    | `accepted_route` | `defer` |
                    | `promoted_artifact_kind` | `followup` |
                    | `promoted_artifact_ref` | `docs/followups/260614_0145_followup.md` |
                    | `queue_admission` | `not_queueable` |
                    | `runner_admission` | `frontier_only` |
                    | `revisit_when` | `owner accepts future QA carrier/public command surface` |
                    | `subject_identity` | `exact(qa_wave public command carrier)` |
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["source_route_state"], "valid")
        self.assertEqual(payload["source_route_non_executable_carrier_state"], "valid")
        self.assertEqual(payload["planning_contour_readback_state"], "valid")

    def test_promoted_decomposition_target_readback_uses_derived_carriers(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            self._write_plan(
                root,
                "docs/plans/260614_0142_analysis_source.md",
                self._analysis_source_body(
                    source_rel="docs/plans/260614_0142_analysis_source.md",
                    target_rel="docs/plans/260614_1432_promoted_umbrella.md",
                    queue_admission="needs_planner",
                    runner_admission="frontier_only",
                ),
            )
            plan = self._write_plan(
                root,
                "docs/plans/260614_1432_promoted_umbrella.md",
                dedent(
                    """\
                    # Plan: promoted umbrella

                    **Date:** 2026-06-14 14:32 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect initial draft

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": null,
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": "docs/plans/260614_0142_analysis_source.md",
                        "next_plans": [],
                        "depends_on": [],
                        "promoted_from": {
                          "authority_note": "derived_read_only; source artifact is writable truth",
                          "source_plan": "docs/plans/260614_0142_analysis_source.md",
                          "source_route_ref": "docs/plans/260614_0142_analysis_source.md#Promoted-route-artifact",
                          "accepted_route": "decomposition_wave",
                          "promoted_artifact_kind": "decomposition_umbrella",
                          "promoted_artifact_ref": "docs/plans/260614_1432_promoted_umbrella.md",
                          "queue_admission_at_acceptance": "needs_planner",
                          "runner_admission_at_acceptance": "frontier_only"
                        },
                        "queue_activation": {
                          "state": "architect_approved",
                          "source_ref": "docs/plans/260614_0142_analysis_source.md#Promoted-route-artifact",
                          "reason": "Architect accepted the reviewed route."
                        },
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["planning_contour_marker"], "decomposition_wave")
        self.assertEqual(payload["planning_contour_role"], "active_decomposition")
        self.assertEqual(payload["planning_contour_readback_state"], "valid")
        self.assertEqual(payload["promoted_from_state"], "valid")
        self.assertEqual(
            payload["promoted_from_authority_note"],
            "derived_read_only; source artifact is writable truth",
        )
        self.assertEqual(payload["queue_activation_carrier_state"], "valid")
        self.assertEqual(payload["queue_activation_state"], "architect_approved")
        self.assertEqual(payload["source_route_state"], "not_applicable")
        current_state = payload["current_state"]
        self.assertEqual(current_state["promoted_from_state"], "valid")
        self.assertEqual(current_state["promoted_from_accepted_route"], "decomposition_wave")
        self.assertEqual(current_state["promoted_from_queue_admission"], "needs_planner")
        self.assertEqual(current_state["promoted_from_runner_admission"], "frontier_only")
        self.assertEqual(current_state["queue_activation_state"], "architect_approved")
        self.assertEqual(current_state["authorities"]["promoted_from"]["state"], "valid")
        self.assertEqual(
            current_state["authorities"]["promoted_from"]["queue_admission_at_acceptance"],
            "needs_planner",
        )

    def test_promoted_decomposition_target_source_route_parity_failures_warn(self) -> None:
        cases = [
            ("missing_source", None, "docs/plans/missing_source.md", "docs/plans/missing_source.md#Promoted-route-artifact"),
            (
                "mismatched_source_route",
                self._analysis_source_body(
                    source_rel="docs/plans/source.md",
                    target_rel="docs/plans/other_target.md",
                    queue_admission="needs_planner",
                    runner_admission="frontier_only",
                ),
                "docs/plans/source.md",
                "docs/plans/source.md#Promoted-route-artifact",
            ),
            (
                "source_route_ref_without_artifact_anchor",
                self._analysis_source_body(
                    source_rel="docs/plans/source.md",
                    target_rel="docs/plans/260614_1432_promoted_umbrella.md",
                    queue_admission="needs_planner",
                    runner_admission="frontier_only",
                ),
                "docs/plans/source.md",
                "docs/plans/source.md#Evidence",
            ),
        ]
        for label, source_body, source_plan, source_route_ref in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_plan_vocab(root)
                if source_body is not None:
                    self._write_plan(root, source_plan, source_body)
                plan = self._write_plan(
                    root,
                    "docs/plans/260614_1432_promoted_umbrella.md",
                    "# Plan: promoted umbrella\n\n"
                    "**Date:** 2026-06-14 14:32 MSK\n"
                    "**Stage:** Stage 1\n"
                    "**Priority:** P1\n"
                    "**Plan type:** dev\n"
                    "**Status:** Architect initial draft\n\n"
                    "## Meta (machine-readable JSON; required for new plans)\n"
                    "```json\n"
                    + json.dumps(
                        {
                            "plan_meta": {
                                "cluster": "process",
                                "tags": [],
                                "wave_family": None,
                                "phase_overlay": "decomposition_wave",
                                "phase_state": "active",
                                "parent": source_plan,
                                "next_plans": [],
                                "depends_on": [],
                                "promoted_from": {
                                    "authority_note": "derived_read_only; source artifact is writable truth",
                                    "source_plan": source_plan,
                                    "source_route_ref": source_route_ref,
                                    "accepted_route": "decomposition_wave",
                                    "promoted_artifact_kind": "decomposition_umbrella",
                                    "promoted_artifact_ref": "docs/plans/260614_1432_promoted_umbrella.md",
                                    "queue_admission_at_acceptance": "needs_planner",
                                    "runner_admission_at_acceptance": "frontier_only",
                                },
                                "queue_activation": {
                                    "state": "architect_approved",
                                    "source_ref": source_route_ref,
                                    "reason": "Architect accepted the reviewed route.",
                                },
                                "followups_out": [],
                                "canon_updates": [],
                            }
                        },
                        indent=2,
                    )
                    + "\n```\n",
                )

                payload = self._json_payload(plan)

            self.assertEqual(payload["promoted_from_state"], "missing_required")
            self.assertEqual(payload["planning_contour_readback_state"], "warning")
            self.assertIn("promoted_from_state=missing_required", payload["planning_contour_readback_reason"])

    def test_direct_owner_decomposition_target_source_plan_na_stays_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_1432_direct_owner_umbrella.md",
                "# Plan: direct owner umbrella\n\n"
                "**Date:** 2026-06-14 14:32 MSK\n"
                "**Stage:** Stage 1\n"
                "**Priority:** P1\n"
                "**Plan type:** dev\n"
                "**Status:** Architect initial draft\n\n"
                "## Meta (machine-readable JSON; required for new plans)\n"
                "```json\n"
                + json.dumps(
                    {
                        "plan_meta": {
                            "cluster": "process",
                            "tags": [],
                            "wave_family": None,
                            "phase_overlay": "decomposition_wave",
                            "phase_state": "active",
                            "parent": None,
                            "next_plans": [],
                            "depends_on": [],
                            "promoted_from": {
                                "authority_note": "derived_read_only; source artifact is writable truth",
                                "source_plan": "N/A (why=direct Owner/external reviewer intake)",
                                "source_route_ref": "Owner message on 2026-06-19",
                                "accepted_route": "decomposition_wave",
                                "promoted_artifact_kind": "decomposition_umbrella",
                                "promoted_artifact_ref": "docs/plans/260614_1432_direct_owner_umbrella.md",
                                "queue_admission_at_acceptance": "needs_planner",
                                "runner_admission_at_acceptance": "frontier_only",
                            },
                            "queue_activation": {
                                "state": "architect_approved",
                                "source_ref": "Owner message on 2026-06-19",
                                "reason": "Owner accepted direct decomposition intake.",
                            },
                            "followups_out": [],
                            "canon_updates": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["promoted_from_state"], "valid")
        self.assertEqual(payload["planning_contour_readback_state"], "valid")

    def test_promoted_from_invalid_enum_values_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_1433_promoted_invalid_enums.md",
                dedent(
                    """\
                    # Plan: promoted target invalid enums

                    **Date:** 2026-06-14 14:33 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect initial draft

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "wave_family": null,
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": "docs/plans/260614_0142_analysis_source.md",
                        "next_plans": [],
                        "depends_on": [],
                        "promoted_from": {
                          "authority_note": "derived_read_only; source artifact is writable truth",
                          "source_plan": "docs/plans/260614_0142_analysis_source.md",
                          "source_route_ref": "docs/plans/260614_0142_analysis_source.md#Promoted-route-artifact",
                          "accepted_route": "typo_wave",
                          "promoted_artifact_kind": "bogus_kind",
                          "promoted_artifact_ref": "docs/plans/260614_1433_promoted_invalid_enums.md",
                          "queue_admission_at_acceptance": "whatever",
                          "runner_admission_at_acceptance": "wrong_runner"
                        },
                        "queue_activation": {
                          "state": "architect_approved",
                          "source_ref": "docs/plans/260614_0142_analysis_source.md#Promoted-route-artifact",
                          "reason": "Architect accepted the reviewed route."
                        },
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertEqual(payload["promoted_from_state"], "missing_required")
        self.assertEqual(payload["planning_contour_readback_state"], "warning")
        self.assertIn("promoted_from_state=missing_required", payload["planning_contour_readback_reason"])

    def test_object_carrier_shape_matrix_is_reported_for_promoted_targets(self) -> None:
        valid_promoted_from = {
            "authority_note": "derived_read_only; source artifact is writable truth",
            "source_plan": "docs/plans/source.md",
            "source_route_ref": "docs/plans/source.md#Promoted-route-artifact",
            "accepted_route": "decomposition_wave",
            "promoted_artifact_kind": "decomposition_umbrella",
            "promoted_artifact_ref": "docs/plans/260614_1500_promoted_from_valid.md",
            "queue_admission_at_acceptance": "needs_planner",
            "runner_admission_at_acceptance": "frontier_only",
        }
        valid_queue_activation = {
            "state": "architect_approved",
            "source_ref": "docs/plans/source.md#Promoted-route-artifact",
            "reason": "fixture",
        }
        cases = [
            ("absent", "__omit__"),
            ("null", None),
            ("non_object", "bad"),
            ("missing_required", {}),
            ("valid", valid_promoted_from),
        ]

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            for expected_state, promoted_from_value in cases:
                meta = {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": "docs/plans/source.md",
                    "next_plans": [],
                    "depends_on": [],
                    "queue_activation": valid_queue_activation,
                    "followups_out": [],
                    "canon_updates": [],
                }
                if promoted_from_value != "__omit__":
                    meta["promoted_from"] = promoted_from_value
                plan = self._write_plan(
                    root,
                    f"docs/plans/260614_1500_promoted_from_{expected_state}.md",
                    "# Plan: matrix\n\n"
                    "**Date:** 2026-06-14 15:00 MSK\n"
                    "**Stage:** Stage 1\n"
                    "**Priority:** P1\n"
                    "**Plan type:** dev\n"
                    "**Status:** Architect initial draft\n\n"
                    "## Meta (machine-readable JSON; required for new plans)\n"
                    "```json\n"
                    + json.dumps({"plan_meta": meta}, indent=2)
                    + "\n```\n",
                )
                if expected_state == "valid":
                    self._write_plan(
                        root,
                        "docs/plans/source.md",
                        self._analysis_source_body(
                            source_rel="docs/plans/source.md",
                            target_rel="docs/plans/260614_1500_promoted_from_valid.md",
                            queue_admission="needs_planner",
                            runner_admission="frontier_only",
                        ),
                    )

                with self.subTest(promoted_from=expected_state):
                    payload = self._json_payload(plan)
                    self.assertEqual(payload["promoted_from_state"], expected_state)

            queue_cases = [
                ("absent", "__omit__"),
                ("null", None),
                ("non_object", "bad"),
                ("missing_required", {"state": "invalid", "source_ref": "docs/plans/source.md"}),
                ("valid", valid_queue_activation),
            ]
            for expected_state, queue_activation_value in queue_cases:
                meta = {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": "docs/plans/source.md",
                    "next_plans": [],
                    "depends_on": [],
                    "promoted_from": valid_promoted_from,
                    "followups_out": [],
                    "canon_updates": [],
                }
                if queue_activation_value != "__omit__":
                    meta["queue_activation"] = queue_activation_value
                plan = self._write_plan(
                    root,
                    f"docs/plans/260614_1510_queue_activation_{expected_state}.md",
                    "# Plan: queue matrix\n\n"
                    "**Date:** 2026-06-14 15:10 MSK\n"
                    "**Stage:** Stage 1\n"
                    "**Priority:** P1\n"
                    "**Plan type:** dev\n"
                    "**Status:** Architect initial draft\n\n"
                    "## Meta (machine-readable JSON; required for new plans)\n"
                    "```json\n"
                    + json.dumps({"plan_meta": meta}, indent=2)
                    + "\n```\n",
                )

                with self.subTest(queue_activation=expected_state):
                    payload = self._json_payload(plan)
                    self.assertEqual(payload["queue_activation_carrier_state"], expected_state)

    def test_pending_activation_readback_flags_not_requested_queue_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_1520_pending_activation.md",
                dedent(
                    """\
                    # Plan: pending activation

                    **Date:** 2026-06-14 15:20 MSK
                    **Stage:** Stage 2
                    **Priority:** P2
                    **Plan type:** dev
                    **Status:** Architect draft

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "queue_activation": {
                          "state": "not_requested",
                          "source_ref": "docs/plans/parent.md#Architect-Q&A",
                          "reason": "Owner has not selected the first child."
                        },
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertTrue(payload["pending_activation"])
        self.assertIn("queue_activation.state=not_requested", payload["pending_activation_reason"])

    def test_pending_activation_readback_flags_malformed_queue_activation_carriers(self) -> None:
        malformed_cases = {
            "null": None,
            "non_object": "bad",
            "missing_required": {"state": "owner_approved"},
            "invalid_enum": {
                "state": "bogus_state",
                "source_ref": "docs/plans/parent.md#Architect-Q&A",
                "reason": "Fixture.",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            for case_name, queue_activation in malformed_cases.items():
                plan = self._write_plan(
                    root,
                    f"docs/plans/260614_1521_pending_activation_{case_name}.md",
                    "# Plan: malformed pending activation\n\n"
                    "**Date:** 2026-06-14 15:21 MSK\n"
                    "**Stage:** Stage 2\n"
                    "**Priority:** P2\n"
                    "**Plan type:** dev\n"
                    "**Status:** Ready for Planner\n\n"
                    "## Meta (machine-readable JSON; required for new plans)\n"
                    "```json\n"
                    + json.dumps(
                        {
                            "plan_meta": {
                                "cluster": "process",
                                "tags": [],
                                "phase_overlay": "decomposition_wave",
                                "phase_state": "active",
                                "queue_activation": queue_activation,
                                "parent": "docs/plans/parent.md",
                                "next_plans": [],
                                "depends_on": [],
                                "followups_out": [],
                                "canon_updates": [],
                            }
                        },
                        indent=2,
                    )
                    + "\n```\n",
                )

                with self.subTest(case_name=case_name):
                    payload = self._json_payload(plan)
                    self.assertTrue(payload["pending_activation"])
                    self.assertIn("queue_activation_carrier_state", payload["pending_activation_reason"])

    def test_pending_activation_readback_flags_approved_child_queue_with_empty_next_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_1522_pending_activation_empty_next_plans.md",
                dedent(
                    """\
                    # Plan: approved activation without imported children

                    **Date:** 2026-06-14 15:22 MSK
                    **Stage:** Stage 2
                    **Priority:** P2
                    **Plan type:** dev
                    **Status:** Ready for Planner

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "parked",
                        "queue_activation": {
                          "state": "owner_approved",
                          "source_ref": "docs/plans/parent.md#Owner-answers",
                          "reason": "Owner selected the first child."
                        },
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Execution queue
                    - Resume parent: `owner-restamp-required`
                    - Plan: `docs/plans/260614_1523_child.md`
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertTrue(payload["pending_activation"])
        self.assertIn("next_plans", payload["pending_activation_reason"])

    def test_pending_activation_readback_ignores_na_execution_queue_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260614_1524_pending_activation_na_queue.md",
                dedent(
                    """\
                    # Plan: approved activation without child queue

                    **Date:** 2026-06-14 15:24 MSK
                    **Stage:** Stage 2
                    **Priority:** P2
                    **Plan type:** dev
                    **Status:** Architect initial draft

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "queue_activation": {
                          "state": "architect_approved",
                          "source_ref": "docs/plans/current.md#Architect-Q&A",
                          "reason": "Architect approved queue import for this ordinary child."
                        },
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Execution queue
                    - Resume parent: `N/A (why=not a queue carrier)`
                    - Plan: `N/A (why=no child queue)`
                    """
                ),
            )

            payload = self._json_payload(plan)

        self.assertFalse(payload["pending_activation"])
        self.assertEqual(payload["pending_activation_reason"], "")

    def test_review_readback_routes_stale_red_after_fix_without_terminal_readiness(self) -> None:
        review_rel = "docs/code_reviews/260614_1600_review_readback.md"
        review_text = dedent(
            """\
            # Code review

            **Date:** 2026-06-14 16:00 MSK
            **Target:** current
            **Status:** ❌ S1 blocker(ы)

            Findings: blocker before coder rerun.
            """
        )
        fresh_review_rel = "docs/code_reviews/260614_1605_review_readback.md"
        fresh_review_text = dedent(
            """\
            # Code review

            **Date:** 2026-06-14 16:05 MSK
            **Target:** current
            **Status:** ❌ S1 blocker(ы)

            ## Lane synthesis / aggregate verdict
            - Aggregate status: `❌ S1 blocker(ы)`

            ## S1 Blocker

            ### B1
            - Blocker ID: B1
            - Current state: open
            - Classification: same-contract reroute
            - Primary owner gap: Coder
            - Evidence refs: `docs/code_reviews/260614_1605_review_readback.md#B1`
            """
        )
        same_minute_review_rel = "docs/code_reviews/260614_1602_same_minute_review_readback.md"
        same_minute_review_text = dedent(
            """\
            # Code review

            **Date:** 2026-06-14 16:02 MSK
            **Target:** current
            **Status:** ❌ S1 blocker(ы)

            ## Lane synthesis / aggregate verdict
            - Aggregate status: `❌ S1 blocker(ы)`

            ## S1 Blocker

            ### B1
            - Blocker ID: B1
            - Current state: open
            - Classification: same-contract reroute
            - Primary owner gap: Coder
            - Evidence refs: `docs/code_reviews/260614_1602_same_minute_review_readback.md#B1`
            """
        )

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_plan(root, review_rel, review_text)
            self._write_plan(root, fresh_review_rel, fresh_review_text)
            self._write_plan(root, same_minute_review_rel, same_minute_review_text)
            live_plan = self._write_plan(
                root,
                "docs/plans/260614_1601_live_review_blocker.md",
                dedent(
                    f"""\
                    # Plan: live blocker

                    **Date:** 2026-06-14 16:01 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** In progress

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    """
                ),
            )
            stale_plan = self._write_plan(
                root,
                "docs/plans/260614_1602_stale_review_blocker.md",
                dedent(
                    f"""\
                    # Plan: stale blocker

                    **Date:** 2026-06-14 16:02 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    - Stale note (2026-06-14 16:01 MSK, Coder): previous blocker verdict in `{review_rel}` is historical until reviewer rerun completes.
                    - Rerun note (2026-06-14 16:01 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.
                    """
                ),
            )
            stale_after_fix_plan = self._write_plan(
                root,
                "docs/plans/260614_1603_stale_after_fix.md",
                dedent(
                    f"""\
                    # Plan: stale blocker after fix

                    **Date:** 2026-06-14 16:03 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    - Stale note (2026-06-14 16:01 MSK, Coder): previous blocker verdict in `{review_rel}` is historical until reviewer rerun completes.
                    - Rerun note (2026-06-14 16:01 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.

                    ## Evidence
                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:oracle:20260614T160200", "target_snapshot": "current", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                      ```
                    """
                ),
            )
            fresh_contracts_plan = self._write_plan(
                root,
                "docs/plans/260614_1605_fresh_contracts_blocker.md",
                dedent(
                    f"""\
                    # Plan: stale baseline with fresh contracts blocker

                    **Date:** 2026-06-14 16:05 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{fresh_review_rel}`
                    - Stale note (2026-06-14 16:06 MSK, Coder): previous blocker verdict in `{fresh_review_rel}` is historical until reviewer rerun completes.
                    - Rerun note (2026-06-14 16:06 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.

                    ## Evidence
                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:oracle:20260614T160200", "target_snapshot": "current", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                      ```
                    """
                ),
            )
            same_minute_contracts_plan = self._write_plan(
                root,
                "docs/plans/260614_1606_same_minute_contracts_blocker.md",
                dedent(
                    f"""\
                    # Plan: stale baseline with same-minute contracts blocker

                    **Date:** 2026-06-14 16:06 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{same_minute_review_rel}`
                    - Stale note (2026-06-14 16:03 MSK, Coder): previous blocker verdict in `{same_minute_review_rel}` is historical until reviewer rerun completes.
                    - Rerun note (2026-06-14 16:03 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.

                    ## Evidence
                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:oracle:20260614T160244", "target_snapshot": "current", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                      ```
                    """
                ),
            )
            stale_after_bad_status_plans = {}
            for label, lane_status in {
                "blocked": "blocked",
                "incomplete": "incomplete",
                "unknown": "unknown",
                "missing": None,
            }.items():
                payload = {
                    "lane_id": "reviewer_code_risk",
                    "run_id": f"reviewer_code_risk:oracle:20260614T1602_{label}",
                    "target_snapshot": "current",
                    "findings": [],
                    "current": True,
                }
                if lane_status is not None:
                    payload["lane_status"] = lane_status
                stale_after_bad_status_plans[label] = self._write_plan(
                    root,
                    f"docs/plans/260614_1604_stale_after_fix_{label}.md",
                    dedent(
                        f"""\
                        # Plan: stale blocker after fix with bad lane status

                        **Date:** 2026-06-14 16:04 MSK
                        **Stage:** Stage 1
                        **Priority:** P1
                        **Plan type:** dev
                        **Status:** Ready for Review

                        ## Review artifacts
                        - Code review (primary): `{review_rel}`
                        - Stale note (2026-06-14 16:01 MSK, Coder): previous blocker verdict in `{review_rel}` is historical until reviewer rerun completes.
                        - Rerun note (2026-06-14 16:01 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.

                        ## Evidence
                        - reviewer_code_risk lane-run artifact:
                          ```json
                          {json.dumps(payload, indent=2)}
                          ```
                        """
                    ),
                )

            live_payload = self._json_payload(live_plan)
            stale_payload = self._json_payload(stale_plan)
            stale_after_fix_payload = self._json_payload(stale_after_fix_plan)
            fresh_contracts_payload = self._json_payload(fresh_contracts_plan)
            same_minute_contracts_payload = self._json_payload(same_minute_contracts_plan)
            stale_after_bad_status_payloads = {
                label: self._json_payload(plan) for label, plan in stale_after_bad_status_plans.items()
            }

        self.assertEqual(live_payload["review_readback_state"], "live_blocker")
        self.assertEqual(live_payload["review_route"], "review_blocker_requires_resolution")
        self.assertEqual(live_payload["review_next_owner"], "Coder")
        self.assertEqual(live_payload["planning_contour_readback_state"], "warning")
        self.assertEqual(live_payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(live_payload["current_state"]["terminal_ready_state"], "blocked")
        self.assertEqual(stale_payload["review_readback_state"], "live_blocker")
        self.assertEqual(stale_payload["review_next_owner"], "Coder")
        self.assertEqual(stale_payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(stale_payload["current_state"]["terminal_ready_state"], "blocked")
        self.assertIn("fixed evidence is not proven", stale_payload["review_readback_reason"])
        self.assertEqual(stale_after_fix_payload["review_readback_state"], "stale_red_after_fix")
        self.assertEqual(stale_after_fix_payload["review_route"], "reviewer_same_file_rewrite_required")
        self.assertEqual(stale_after_fix_payload["review_next_owner"], "Reviewer")
        self.assertEqual(stale_after_fix_payload["current_state"]["review_route"], "reviewer_same_file_rewrite_required")
        self.assertEqual(stale_after_fix_payload["current_state"]["review_next_owner"], "Reviewer")
        self.assertEqual(stale_after_fix_payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(stale_after_fix_payload["current_state"]["terminal_ready_state"], "blocked")
        self.assertEqual(fresh_contracts_payload["review_readback_state"], "live_blocker")
        self.assertEqual(fresh_contracts_payload["review_route"], "review_blocker_requires_resolution")
        self.assertEqual(fresh_contracts_payload["review_next_owner"], "Coder")
        self.assertEqual(fresh_contracts_payload["current_state"]["review_next_owner"], "Coder")
        self.assertNotEqual(fresh_contracts_payload["review_route"], "reviewer_same_file_rewrite_required")
        self.assertIn("newer than the selected fixed risk-lane evidence", fresh_contracts_payload["review_readback_reason"])
        self.assertEqual(same_minute_contracts_payload["review_readback_state"], "live_blocker")
        self.assertEqual(same_minute_contracts_payload["review_route"], "review_blocker_requires_resolution")
        self.assertEqual(same_minute_contracts_payload["review_next_owner"], "Coder")
        self.assertNotEqual(same_minute_contracts_payload["review_route"], "reviewer_same_file_rewrite_required")
        self.assertIn("same-minute freshness ordering", same_minute_contracts_payload["review_readback_reason"])
        for label, payload in stale_after_bad_status_payloads.items():
            with self.subTest(lane_status=label):
                self.assertEqual(payload["review_readback_state"], "live_blocker")
                self.assertEqual(payload["review_next_owner"], "Coder")
                self.assertEqual(payload["current_state"]["blocker_state"], "blocked")
                self.assertEqual(payload["current_state"]["terminal_ready_state"], "blocked")
                self.assertIn("lane_status", payload["review_readback_reason"])

    def test_green_review_change_during_lint_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            review_rel = "docs/code_reviews/260712_snapshot_race.md"
            review = root / review_rel
            review.parent.mkdir(parents=True, exist_ok=True)
            review.write_text(
                "# Review\n\n**Date:** 2026-07-12 22:17 MSK\n**Status:** ✅ OK\n",
                encoding="utf-8",
            )
            plan = root / "docs/plans/260712_snapshot_race.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan_text = (
                "# Plan\n\n**Status:** Ready for Arch review\n\n"
                "## Review artifacts\n"
                f"- Code review (primary): `{review_rel}`\n"
            )
            plan.write_text(plan_text, encoding="utf-8")

            def rewrite_after_snapshot(artifacts, **_kwargs):
                self.assertEqual(len(artifacts), 1)
                self.assertIn("**Status:** ✅ OK", artifacts[0].lines)
                review.write_text(
                    "# Review\n\n**Date:** 2026-07-12 22:18 MSK\n"
                    "**Status:** ❌ S1 blocker(ы)\n",
                    encoding="utf-8",
                )
                return []

            with mock.patch.object(
                MODULE.review_artifact_lint,
                "load_review_artifacts",
                side_effect=AssertionError("oracle must not re-read the live review"),
            ), mock.patch.object(
                MODULE.review_artifact_lint,
                "lint_review_artifacts",
                side_effect=rewrite_after_snapshot,
            ):
                state, reason = MODULE.classify_review_readback(
                    plan_text,
                    root=root,
                    plan_path=plan,
                )

        self.assertEqual(state, "unknown")
        self.assertIn("changed during validation", reason)

    def test_green_review_snapshot_mismatch_routes_to_reviewer_and_blocks_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260712_2218_stale_green_fixture.md"
            review_rel = "docs/code_reviews/260712_2218_stale_green_fixture.md"
            plan = self._write_plan(
                root,
                plan_rel,
                dedent(
                    f"""\
                    # Plan: stale green fixture

                    **Date:** 2026-07-12 22:18 MSK
                    **Stage:** Stage 1
                    **Priority:** P0
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    """
                ),
            )
            review = root / review_rel
            review.parent.mkdir(parents=True, exist_ok=True)
            review.write_text(
                dedent(
                    f"""\
                    # Код-ревью - stale green fixture

                    **Date:** 2026-07-12 22:17 MSK
                    **Target:** PLAN={plan_rel}
                    **Spec:** {plan_rel}
                    **Status:** ✅ OK
                    """
                ),
                encoding="utf-8",
            )

            for finding_code in (
                "current_bundle_target_snapshot_mismatch",
                "dual_lane_target_snapshot_mismatch",
            ):
                with self.subTest(finding_code=finding_code), mock.patch.object(
                    MODULE.review_artifact_lint,
                    "lint_review_artifacts",
                    return_value=[mock.Mock(code=finding_code)],
                ) as lint_mock:
                    payload = self._json_payload(plan)

                lint_mock.assert_called_once()
                self.assertEqual(len(lint_mock.call_args.args), 1)
                self.assertEqual(
                    lint_mock.call_args.kwargs,
                    {
                        "project_root": root.resolve(),
                        "origin_plan": plan,
                        "require_dual_lane_origin": True,
                    },
                )
                self.assertEqual(payload["review_readback_state"], "stale_green_review")
                self.assertEqual(payload["review_route"], "reviewer_same_file_rewrite_required")
                self.assertEqual(payload["review_next_owner"], "Reviewer")
                self.assertEqual(payload["current_state"]["blocker_state"], "blocked")
                self.assertEqual(payload["current_state"]["terminal_ready_state"], "blocked")

            for finding_code in (
                "missing_review_target_snapshot",
                "missing_plan_resident_risk_lane",
                "ambiguous_plan_resident_risk_lane",
                "current_bundle_target_snapshot_unavailable",
            ):
                with self.subTest(finding_code=finding_code), mock.patch.object(
                    MODULE.review_artifact_lint,
                    "lint_review_artifacts",
                    return_value=[mock.Mock(code=finding_code)],
                ):
                    lint_error_payload = self._json_payload(plan)

                self.assertEqual(lint_error_payload["review_readback_state"], "unknown")
                self.assertEqual(lint_error_payload["review_route"], "review_readback_unknown")
                self.assertEqual(lint_error_payload["review_next_owner"], "Architect")
                self.assertEqual(lint_error_payload["current_state"]["blocker_state"], "blocked")
                self.assertEqual(lint_error_payload["current_state"]["terminal_ready_state"], "blocked")
                self.assertIn(finding_code, lint_error_payload["review_readback_reason"])

            with mock.patch.object(
                MODULE.review_artifact_lint,
                "lint_review_artifacts",
                return_value=[
                    mock.Mock(code="current_bundle_target_snapshot_mismatch"),
                    mock.Mock(code="current_bundle_target_snapshot_unavailable"),
                ],
            ):
                mixed_payload = self._json_payload(plan)

            self.assertEqual(mixed_payload["review_readback_state"], "unknown")
            self.assertEqual(mixed_payload["review_next_owner"], "Architect")

            with mock.patch.object(
                MODULE.review_artifact_lint,
                "lint_review_artifacts",
                side_effect=RuntimeError("fixture linter failure"),
            ):
                error_payload = self._json_payload(plan)

            unknown_path_state, unknown_path_reason = MODULE.classify_review_readback(
                plan.read_text(encoding="utf-8"),
                root=root,
                plan_path=None,
            )

        self.assertEqual(error_payload["review_readback_state"], "unknown")
        self.assertEqual(error_payload["review_route"], "review_readback_unknown")
        self.assertEqual(error_payload["review_next_owner"], "Architect")
        self.assertEqual(error_payload["current_state"]["blocker_state"], "blocked")
        self.assertEqual(error_payload["current_state"]["terminal_ready_state"], "blocked")
        self.assertIn("fixture linter failure", error_payload["review_readback_reason"])
        self.assertEqual(unknown_path_state, "unknown")
        self.assertIn("requires a known plan path", unknown_path_reason)

    def test_canonical_current_proof_block_precedes_green_review_header(self) -> None:
        """The oracle must project the sole reader, never a header-only green."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260817_1047_current_proof_oracle.md"
            draft_rel = "docs/code_drafts/260817_1047_current_proof_oracle__code_draft.md"
            review_rel = "docs/code_reviews/260817_1047_current_proof_oracle.md"
            target_rel = "scripts/current_proof_target.py"
            plan = self._write_plan(
                root,
                plan_rel,
                dedent(
                    f"""\
                    # Plan: current-proof oracle fixture

                    **Plan type:** dev
                    **Status:** Ready for Review

                    **Context links (source of truth):**
                    - Code draft(s): `{draft_rel}`

                    ## Review artifacts
                    - Code review (primary): `{review_rel}`
                    """
                ),
            )
            self._write_plan(
                root,
                draft_rel,
                "# Draft\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": plan_rel,
                            "cluster": "process",
                            "targets": [{"path": target_rel, "kind": "py"}],
                            "deleted_paths": [],
                        }
                    },
                    sort_keys=True,
                )
                + "\n```\n",
            )
            self._write_plan(root, target_rel, "print('fixture')\n")
            self._write_plan(
                root,
                review_rel,
                "# Review\n\n"
                f"**Target:** BUNDLE=current bundle_sha256={'a' * 64}\n"
                "**Status:** ✅ OK\n",
            )

            state, reason = MODULE.classify_review_readback(
                plan.read_text(encoding="utf-8"),
                root=root,
                plan_path=plan,
            )

        self.assertEqual(state, "live_blocker")
        self.assertIn("missing_plan_resident_risk_lane", reason)


class PlanStatusOracleManagerModeTests(unittest.TestCase):
    def _run(self, metadata: str, actual: str = "manager-collab") -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260712_1255_mode_fixture.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: mode fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Architect initial draft\n\n"
                "## Meta\n```json\n"
                f"{metadata}\n"
                "```\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                rc = MODULE.main([str(plan), "--json", "--manager-mode", actual])
            return rc, stdout.getvalue(), stderr.getvalue()

    def test_admission_matrix_and_json_types(self) -> None:
        cases = (
            ("manager-collab", "manager-collab", 0, "admitted", "mode_match", True),
            ("manager-custom-pipeline", "manager-custom-pipeline", 0, "admitted", "mode_match", True),
            ("either", "manager-collab", 0, "admitted", "plan_allows_either", True),
            ("manager-custom-pipeline", "manager-collab", 4, "mismatch", "required_mode_mismatch", False),
        )
        for required, actual, expected_rc, state, reason, admitted in cases:
            with self.subTest(required=required, actual=actual):
                metadata = json.dumps(
                    {"plan_meta": {"cluster": "process", "required_manager_mode": required}}
                )
                rc, stdout, stderr = self._run(metadata, actual)
                self.assertEqual((rc, stderr), (expected_rc, ""))
                payload = json.loads(stdout)
                self.assertEqual(payload["required_manager_mode"], required)
                self.assertEqual(payload["actual_manager_mode"], actual)
                self.assertEqual(payload["manager_mode_state"], state)
                self.assertEqual(payload["manager_mode_reason"], reason)
                self.assertIs(payload["manager_mode_admitted"], admitted)

    def test_admission_uses_the_same_captured_plan_as_oracle_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260712_1255_mode_fixture.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            version_a = (
                "# Plan: mode fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Architect initial draft\n\n"
                "## Meta\n```json\n"
                '{"plan_meta": {"cluster": "process", '
                '"required_manager_mode": "manager-collab"}}\n'
                "```\n"
            )
            version_b = version_a.replace(
                "Architect initial draft",
                "Done",
            ).replace(
                "manager-collab",
                "manager-custom-pipeline",
            )
            plan.write_text(version_a, encoding="utf-8")
            original_oracle_result = MODULE.oracle_result

            def replace_after_oracle_capture(
                plan_path: Path,
                *,
                context: object | None = None,
            ) -> object:
                result = original_oracle_result(plan_path, context=context)
                plan.write_text(version_b, encoding="utf-8")
                return result

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.object(
                MODULE,
                "oracle_result",
                side_effect=replace_after_oracle_capture,
            ), mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                rc = MODULE.main(
                    [
                        str(plan),
                        "--json",
                        "--manager-mode",
                        "manager-custom-pipeline",
                    ]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual((rc, stderr.getvalue()), (4, ""))
        self.assertEqual(payload["status_value"], "Architect initial draft")
        self.assertEqual(payload["required_manager_mode"], "manager-collab")
        self.assertIs(payload["manager_mode_admitted"], False)
        self.assertEqual(
            payload["plan_hash"],
            hashlib.sha256(version_a.encode("utf-8")).hexdigest(),
        )
        self.assertNotEqual(
            payload["plan_hash"],
            hashlib.sha256(version_b.encode("utf-8")).hexdigest(),
        )

    def test_missing_and_invalid_are_rejections_with_json(self) -> None:
        cases = (
            ({"cluster": "process"}, "missing", "unclassified_missing", "required_mode_missing"),
            (
                {"cluster": "process", "required_manager_mode": ["manager-collab"]},
                "plan_meta.required_manager_mode",
                "invalid_required_mode",
                "required_mode_invalid",
            ),
            (
                {"cluster": "process", "required_manager_mode": "native"},
                "plan_meta.required_manager_mode",
                "invalid_required_mode",
                "required_mode_invalid",
            ),
        )
        for meta, source, state, reason in cases:
            with self.subTest(meta=meta):
                rc, stdout, stderr = self._run(json.dumps({"plan_meta": meta}))
                self.assertEqual((rc, stderr), (4, ""))
                payload = json.loads(stdout)
                self.assertIsNone(payload["required_manager_mode"])
                self.assertEqual(payload["manager_mode_source"], source)
                self.assertEqual(payload["manager_mode_state"], state)
                self.assertEqual(payload["manager_mode_reason"], reason)
                self.assertIs(payload["manager_mode_admitted"], False)

    def test_carrier_errors_exit_three_without_admission_json(self) -> None:
        malformed = '{"plan_meta": {"cluster": "process",}'
        rc, stdout, stderr = self._run(malformed)
        self.assertEqual((rc, stdout), (3, ""))
        self.assertIn("malformed plan_meta", stderr)

        duplicate = (
            '{"plan_meta": {"cluster": "process", "required_manager_mode": "either"}}\n'
            "```\n```json\n"
            '{"plan_meta": {"cluster": "process", "required_manager_mode": "either"}}'
        )
        rc, stdout, stderr = self._run(duplicate)
        self.assertEqual((rc, stdout), (3, ""))
        self.assertIn("got 2", stderr)

        rc, stdout, stderr = self._run('{"other": {}}')
        self.assertEqual((rc, stdout), (3, ""))
        self.assertIn("got 0", stderr)

    def test_admission_ignores_plan_meta_prose_in_other_json_carriers(self) -> None:
        metadata = (
            '{"plan_meta": {"cluster": "process", "required_manager_mode": "manager-collab"}}\n'
            "```\n\n"
            "## Evidence\n"
            "```json\n"
            + json.dumps(
                {
                    "schema_version": "reviewer_code_risk_lane_run.v1",
                    "findings": [
                        {
                            "evidence": [
                                "docs_closeout reads PLAN_PATH::plan_meta.followups_out"
                            ]
                        }
                    ],
                }
            )
        )

        rc, stdout, stderr = self._run(metadata)

        self.assertEqual((rc, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["manager_mode_state"], "admitted")
        self.assertIs(payload["manager_mode_admitted"], True)

    def test_no_manager_mode_json_is_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260712_1255_mode_fixture.md"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                "# Plan\n\n**Status:** Architect initial draft\n\n"
                '```json\n{"plan_meta": {"cluster": "process"}}\n```\n',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                rc = MODULE.main([str(plan), "--json"])
            payload = json.loads(stdout.getvalue())
        self.assertEqual(rc, 0)
        self.assertNotIn("manager_mode_state", payload)


class AnalysisPackAuthorityResolverTests(unittest.TestCase):
    STEM = "260729_0959_process_external_authority"

    def _write_external(
        self,
        root: Path,
        *,
        stem: str | None = None,
        ref_value: str | None = None,
        origin_rows: str = "",
        pack_rows: str = "",
        draft_targets: list[dict[str, str]] | None = None,
        write_draft: bool = True,
        write_pack: bool = True,
    ) -> tuple[Path, Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            standalone_git_root(root)
        stem = stem or self.STEM
        plan_rel = f"docs/plans/{stem}.md"
        pack_rel = f"docs/analysis_packs/{stem}.md"
        draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
        canonical_ref = f"{pack_rel}#Analysis-pack"
        ref_value = f"`{canonical_ref}` (refs-only annotation)" if ref_value is None else ref_value
        ref_row = f"| `analysis_pack_ref` | {ref_value} |\n" if ref_value else ""
        plan_text = dedent(
            f"""\
            # Plan: external authority

            **Plan type:** dev
            **Status:** Ready for Review
            **Code draft:** `{draft_rel}`

            ```json
            {json.dumps({"plan_meta": {"cluster": "process", "wave_family": "analysis_wave"}}, indent=2)}
            ```

            ## Analysis pack
            | Field | Value |
            | --- | --- |
            {ref_row}| `authority_boundary` | `standalone_pack_only` |
            {origin_rows}

            ## Promoted route artifact
            | Field | Value |
            | --- | --- |
            | `accepted_route` | `developer_wave` |
            | `promoted_artifact_kind` | `seed_dev_plan` |
            | `promoted_artifact_ref` | `docs/plans/260729_1000_seed.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        )
        plan = root / plan_rel
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(plan_text, encoding="utf-8")
        pack = root / pack_rel
        if write_pack:
            pack.parent.mkdir(parents=True, exist_ok=True)
            pack.write_text(
                dedent(
                    f"""\
                    # Analysis pack

                    ## Analysis pack
                    | Field | Value |
                    | --- | --- |
                    | `route_recommendation` | `developer_wave` |
                    | `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; exhaustion_action=architect_recheck |
                    | `stale_trigger` | source_subject_baseline=authority; current_source_subject=authority |
                    {pack_rows}
                    """
                ),
                encoding="utf-8",
            )
        draft = root / draft_rel
        if write_draft:
            draft.parent.mkdir(parents=True, exist_ok=True)
            targets = [{"path": pack_rel, "kind": "doc"}] if draft_targets is None else draft_targets
            draft.write_text(
                "# Code draft\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": plan_rel,
                            "cluster": "process",
                            "targets": targets,
                            "deleted_paths": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
                encoding="utf-8",
            )
        return plan, pack, draft

    @staticmethod
    def _header_status(plan_text: str) -> str | None:
        match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", plan_text, re.MULTILINE)
        return match.group(1) if match else None

    def _resolve(self, plan: Path, *, effective_status: str | None = None) -> object:
        plan_text = plan.read_text(encoding="utf-8")
        return MODULE.resolve_analysis_pack_authority(
            origin_plan_path=plan,
            plan_text=plan_text,
            effective_status=(
                self._header_status(plan_text) if effective_status is None else effective_status
            ),
        )

    def _write_plan_resident(self, root: Path, *, status: str, rows: str = "") -> Path:
        plan = root / f"docs/plans/{self.STEM}.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            f"# Plan: plan-resident pack\n\n**Plan type:** dev\n**Status:** {status}\n\n"
            '```json\n{"plan_meta": {"cluster": "process", "wave_family": "analysis_wave"}}\n```\n\n'
            "## Analysis pack\n| Field | Value |\n| --- | --- |\n"
            "| `analysis_subject` | plan-resident fixture subject |\n"
            "| `route_recommendation` | `developer_wave` |\n"
            f"{rows}\n",
            encoding="utf-8",
        )
        return plan

    def _replace_with_outside_symlink(self, source: Path, outside: Path) -> None:
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(outside)

    def _replacement_snapshot(
        self,
        root: Path,
        selected_rel: str,
        replacement_data: bytes,
    ) -> tuple[object, list[str]]:
        target = root / selected_rel
        replacement = target.with_name(f".{target.name}.replacement")
        replacement.write_bytes(replacement_data)
        real_snapshot = MODULE.snapshot_regular_or_absent
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

    def test_annotated_same_stem_ref_resolves_and_pack_owns_lifecycle(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan, pack, _ = self._write_external(root)

            resolved = self._resolve(plan)
            before = MODULE.oracle_result(plan)
            snapshot_before = MODULE.review_target_snapshot.build_current_bundle_snapshot(
                plan,
                project_root=root,
            )
            plan.write_text(
                plan.read_text(encoding="utf-8") + "\n## Evidence\n- lifecycle-only append\n",
                encoding="utf-8",
            )
            after_plan_append = MODULE.oracle_result(plan)
            snapshot_after_plan_append = MODULE.review_target_snapshot.build_current_bundle_snapshot(
                plan,
                project_root=root,
            )
            pack.write_text(
                pack.read_text(encoding="utf-8").replace("budget_status=active", "budget_status=exhausted"),
                encoding="utf-8",
            )
            after_pack_mutation = MODULE.oracle_result(plan)
            snapshot_after_pack_mutation = MODULE.review_target_snapshot.build_current_bundle_snapshot(
                plan,
                project_root=root,
            )

        self.assertEqual(resolved.mode, "external")
        self.assertTrue(resolved.is_valid)
        self.assertEqual(before.analysis_route_lifecycle_state, "ok")
        self.assertEqual(after_plan_append.analysis_route_lifecycle_state, "ok")
        self.assertEqual(snapshot_before["bundle_sha256"], snapshot_after_plan_append["bundle_sha256"])
        self.assertEqual(after_pack_mutation.analysis_route_lifecycle_state, "architect_stop")
        self.assertNotEqual(snapshot_before["bundle_sha256"], snapshot_after_pack_mutation["bundle_sha256"])

    def test_stable_external_authority_never_reopens_carriers_with_path_read_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan, _, _ = self._write_external(Path(tmpdir))
            plan_text = plan.read_text(encoding="utf-8")
            with mock.patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("resolver reopened a carrier path"),
            ):
                resolved = MODULE.resolve_analysis_pack_authority(
                    origin_plan_path=plan,
                    plan_text=plan_text,
                    effective_status=self._header_status(plan_text),
                )

        self.assertTrue(resolved.is_valid)
        self.assertIn("budget_status=active", resolved.authority_text)

    def test_synchronized_draft_and_pack_replacement_fail_closed(self) -> None:
        for carrier, expected in (
            ("draft", "draft_malformed"),
            ("pack", "pack_unreadable"),
        ):
            with self.subTest(carrier=carrier), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan, pack, draft = self._write_external(root)
                draft_rel = f"docs/code_drafts/{self.STEM}__code_draft.md"
                pack_rel = f"docs/analysis_packs/{self.STEM}.md"
                if carrier == "draft":
                    selected_rel = draft_rel
                    replacement_data = draft.read_bytes().replace(b'"cluster": "process"', b'"cluster": "changed"')
                    expected_calls = [draft_rel]
                else:
                    selected_rel = pack_rel
                    replacement_data = pack.read_bytes().replace(
                        b"budget_status=active",
                        b"budget_status=exhausted",
                    ).replace(b"developer_wave", b"reject")
                    expected_calls = [draft_rel, pack_rel]
                wrapped, calls = self._replacement_snapshot(root, selected_rel, replacement_data)
                plan_text = plan.read_text(encoding="utf-8")

                with mock.patch.object(
                    MODULE,
                    "snapshot_regular_or_absent",
                    side_effect=wrapped,
                ):
                    resolved = MODULE.resolve_analysis_pack_authority(
                        origin_plan_path=plan,
                        plan_text=plan_text,
                        effective_status=self._header_status(plan_text),
                    )

                self.assertEqual(calls, expected_calls)
                self.assertFalse(resolved.is_valid)
                self.assertEqual(resolved.error_token, "analysis_pack_authority_invalid")
                self.assertEqual(resolved.detail_category, expected)
                self.assertEqual(resolved.authority_text, "")
                self.assertNotIn("budget_status=exhausted", resolved.authority_text)
                self.assertNotIn("reject", resolved.authority_text)

    def test_synchronized_replacement_leaks_no_oracle_lifecycle_budget(self) -> None:
        for carrier, expected in (
            ("draft", "draft_malformed"),
            ("pack", "pack_unreadable"),
        ):
            with self.subTest(carrier=carrier), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan, pack, draft = self._write_external(root)
                draft_rel = f"docs/code_drafts/{self.STEM}__code_draft.md"
                pack_rel = f"docs/analysis_packs/{self.STEM}.md"
                selected_rel = draft_rel if carrier == "draft" else pack_rel
                expected_calls = [draft_rel] if carrier == "draft" else [draft_rel, pack_rel]
                source = draft if carrier == "draft" else pack
                replacement_data = source.read_bytes().replace(
                    b"budget_status=active",
                    b"budget_status=exhausted",
                )
                wrapped, calls = self._replacement_snapshot(root, selected_rel, replacement_data)

                with mock.patch.object(
                    MODULE,
                    "snapshot_regular_or_absent",
                    side_effect=wrapped,
                ):
                    result = MODULE.oracle_result(plan)

                self.assertEqual(calls, expected_calls)
                self.assertEqual(result.analysis_route_lifecycle_state, "warning")
                self.assertEqual(
                    result.analysis_route_lifecycle_reason,
                    f"analysis_pack_authority_invalid:{expected}",
                )
                self.assertEqual(result.analysis_route_lifecycle_budget_status, "")
                self.assertEqual(result.analysis_route_lifecycle_needs_analysis_depth_cap, "")
                self.assertEqual(result.analysis_route_lifecycle_current_needs_analysis_depth, "")

    def test_operational_duplicate_warns_but_scalars_stay_pack_derived(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan, _, _ = self._write_external(
                Path(tmpdir),
                origin_rows="| `execution_budget` | budget_status=exhausted; needs_analysis_depth_cap=0; current_needs_analysis_depth=9 |",
            )

            resolved = self._resolve(plan)
            result = MODULE.oracle_result(plan)

        self.assertEqual(resolved.detail_category, "operational_duplicate")
        self.assertTrue(resolved.authority_text)
        self.assertEqual(result.analysis_route_lifecycle_state, "warning")
        self.assertEqual(
            result.analysis_route_lifecycle_reason,
            "analysis_pack_authority_invalid:operational_duplicate",
        )
        self.assertEqual(result.analysis_route_lifecycle_budget_status, "active")
        self.assertEqual(result.analysis_route_lifecycle_current_needs_analysis_depth, "1")
        self.assertEqual(result.source_route_accepted_route, "developer_wave")

    def test_identity_failure_maps_to_empty_non_green_oracle_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan, _, _ = self._write_external(Path(tmpdir), write_pack=False)
            result = MODULE.oracle_result(plan)

        self.assertEqual(result.analysis_route_lifecycle_state, "warning")
        self.assertEqual(
            result.analysis_route_lifecycle_reason,
            "analysis_pack_authority_invalid:pack_missing",
        )
        self.assertEqual(result.analysis_route_lifecycle_budget_status, "")
        self.assertEqual(result.analysis_route_lifecycle_needs_analysis_depth_cap, "")
        self.assertEqual(result.analysis_route_lifecycle_current_needs_analysis_depth, "")
        self.assertEqual(result.analysis_route_lifecycle_stale_trigger_state, "unknown")

    def test_symlinked_pack_and_draft_fail_closed_before_external_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cases = (
                ("pack", "pack_unreadable"),
                ("draft", "draft_malformed"),
            )
            for carrier, expected in cases:
                with self.subTest(carrier=carrier):
                    root = base / f"repo-{carrier}"
                    plan, pack, draft = self._write_external(root)
                    source = pack if carrier == "pack" else draft
                    self._replace_with_outside_symlink(
                        source,
                        base / "outside" / f"{carrier}.md",
                    )

                    resolved = self._resolve(plan)
                    result = MODULE.oracle_result(plan)

                    self.assertFalse(resolved.is_valid)
                    self.assertEqual(resolved.detail_category, expected)
                    self.assertEqual(resolved.authority_text, "")
                    self.assertEqual(result.analysis_route_lifecycle_state, "warning")
                    self.assertEqual(
                        result.analysis_route_lifecycle_reason,
                        f"analysis_pack_authority_invalid:{expected}",
                    )
                    self.assertEqual(result.analysis_route_lifecycle_budget_status, "")
                    with self.assertRaisesRegex(
                        MODULE.review_target_snapshot.SnapshotError,
                        "outside project root",
                    ):
                        MODULE.review_target_snapshot.build_current_bundle_snapshot(
                            plan,
                            project_root=root,
                        )

    def test_parent_symlink_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            root = base / "repo"
            plan, pack, _ = self._write_external(root)
            outside_dir = base / "outside-analysis-packs"
            outside_dir.mkdir()
            (outside_dir / pack.name).write_bytes(pack.read_bytes())
            pack.unlink()
            pack.parent.rmdir()
            pack.parent.symlink_to(outside_dir, target_is_directory=True)

            resolved = self._resolve(plan)
            result = MODULE.oracle_result(plan)

        self.assertFalse(resolved.is_valid)
        self.assertEqual(resolved.detail_category, "pack_unreadable")
        self.assertEqual(resolved.authority_text, "")
        self.assertEqual(result.analysis_route_lifecycle_budget_status, "")

    def test_bounded_identity_failures_have_no_authority_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pack_rel = f"docs/analysis_packs/{self.STEM}.md"
            cases: list[tuple[str, Path]] = []

            plan, _, _ = self._write_external(root / "missing-ref", ref_value="")
            cases.append(("ref_missing", plan))
            plan, _, _ = self._write_external(root / "malformed-ref", ref_value=pack_rel)
            cases.append(("ref_malformed", plan))
            plan, _, _ = self._write_external(
                root / "noncanonical-ref",
                ref_value=f"`{pack_rel}#Analysis-pack` plus docs/other.md",
            )
            cases.append(("ref_noncanonical", plan))
            plan, _, _ = self._write_external(
                root / "second-fragment",
                ref_value=f"`{pack_rel}#Analysis-pack` plus #Analysis-pack",
            )
            cases.append(("ref_noncanonical", plan))
            plan, _, _ = self._write_external(
                root / "operational-key",
                ref_value=f"`{pack_rel}#Analysis-pack` route_recommendation is elsewhere",
            )
            cases.append(("ref_noncanonical", plan))
            plan, _, _ = self._write_external(
                root / "redirect",
                ref_value="`docs/analysis_packs/other.md#Analysis-pack`",
            )
            cases.append(("ref_noncanonical", plan))
            plan, _, _ = self._write_external(
                root / "path-escape",
                ref_value=f"`docs/analysis_packs/../{self.STEM}.md#Analysis-pack`",
            )
            cases.append(("ref_malformed", plan))
            plan, _, _ = self._write_external(
                root / "duplicate-row",
                origin_rows=f"| `analysis_pack_ref` | `{pack_rel}#Analysis-pack` |",
            )
            cases.append(("ref_malformed", plan))
            plan, _, _ = self._write_external(root / "draft-missing", write_draft=False)
            cases.append(("draft_missing", plan))
            plan, _, draft = self._write_external(root / "draft-malformed")
            draft.write_text("# malformed\n", encoding="utf-8")
            cases.append(("draft_malformed", plan))
            plan, _, draft = self._write_external(root / "draft-invalid-utf8")
            draft.write_bytes(b"\xff\xfe")
            cases.append(("draft_malformed", plan))
            plan, _, _ = self._write_external(root / "target-missing", draft_targets=[])
            cases.append(("target_missing", plan))
            duplicate = [{"path": pack_rel, "kind": "doc"}, {"path": pack_rel, "kind": "doc"}]
            plan, _, _ = self._write_external(root / "target-ambiguous", draft_targets=duplicate)
            cases.append(("target_ambiguous", plan))
            plan, _, _ = self._write_external(root / "pack-missing", write_pack=False)
            cases.append(("pack_missing", plan))
            plan, pack, _ = self._write_external(root / "pack-unreadable")
            pack.write_bytes(b"\xff\xfe")
            cases.append(("pack_unreadable", plan))

            for expected, plan in cases:
                with self.subTest(expected=expected):
                    resolved = self._resolve(plan)
                    self.assertEqual(resolved.error_token, "analysis_pack_authority_invalid")
                    self.assertEqual(resolved.detail_category, expected)
                    self.assertEqual(resolved.authority_text, "")

            misplaced = root / "misplaced" / f"{self.STEM}.md"
            misplaced.parent.mkdir(parents=True)
            misplaced.write_text(
                "```json\n"
                '{"plan_meta":{"wave_family":"analysis_wave"}}\n'
                "```\n\n## Analysis pack\n"
                f"| `analysis_pack_ref` | `{pack_rel}#Analysis-pack` |\n",
                encoding="utf-8",
            )
            misplaced_result = self._resolve(misplaced)

        self.assertEqual(misplaced_result.detail_category, "repo_root_unresolved")

    def test_legacy_text_classifier_remains_backward_compatible(self) -> None:
        legacy = dedent(
            """\
            ## Analysis pack
            | Field | Value |
            | --- | --- |
            | `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=1; current_needs_analysis_depth=0; stop_owner=Architect; exhaustion_action=architect_recheck |
            | `stale_trigger` | source_subject_baseline=legacy; current_source_subject=legacy |
            """
        )
        result = MODULE.classify_analysis_route_lifecycle(legacy)
        self.assertEqual(result.state, "ok")

    def test_explicit_external_ref_selects_external_mode_before_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan, _, _ = self._write_external(
                Path(tmpdir),
                stem="260729_0958_process_explicit_external_authority",
            )
            resolved = self._resolve(plan)

        self.assertEqual(resolved.mode, "external")
        self.assertTrue(resolved.is_valid)

    def test_preboundary_angle_annotation_never_restores_mirror_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stem = "260729_0958_process_angle_external_authority"
            pack_ref = f"docs/analysis_packs/{stem}.md#Analysis-pack"
            plan, _, _ = self._write_external(
                root / "valid",
                stem=stem,
                ref_value=f"`{pack_ref}` <human-note>",
                origin_rows=(
                    "| `execution_budget` | budget_status=exhausted; "
                    "needs_analysis_depth_cap=0; current_needs_analysis_depth=9 |"
                ),
            )
            resolved = self._resolve(plan)
            result = MODULE.oracle_result(plan)

            invalid_stem = "260729_0958_process_invalid_angle_external_authority"
            invalid_ref = f"docs/analysis_packs/{invalid_stem}.md#Analysis-pack"
            invalid_plan, _, _ = self._write_external(
                root / "invalid",
                stem=invalid_stem,
                ref_value=f"`{invalid_ref}` <docs/other.md>",
            )
            invalid = self._resolve(invalid_plan)

            sentinel_plan, _, _ = self._write_external(
                root / "sentinel",
                stem="260729_0958_process_unexpanded_analysis_sentinel",
                ref_value=MODULE.ANALYSIS_PACK_TEMPLATE_SENTINEL,
            )
            sentinel = self._resolve(sentinel_plan)
            sentinel_on_intake = self._resolve(sentinel_plan, effective_status="Ready for Planner")

        self.assertEqual(resolved.mode, "external")
        self.assertEqual(resolved.detail_category, "operational_duplicate")
        self.assertEqual(result.analysis_route_lifecycle_state, "warning")
        self.assertEqual(result.analysis_route_lifecycle_budget_status, "active")
        self.assertNotEqual(result.analysis_route_lifecycle_state, "architect_stop")
        self.assertEqual(invalid.mode, "external")
        self.assertEqual(invalid.detail_category, "ref_noncanonical")
        # The unexpanded template sentinel is no ref at all: missing once the pack
        # must be standalone, and no reason to leave the plan-resident pack on intake.
        self.assertEqual(sentinel.mode, "external")
        self.assertEqual(sentinel.detail_category, "ref_missing")
        self.assertEqual(sentinel_on_intake.mode, "legacy")
        self.assertTrue(sentinel_on_intake.is_valid)

    PLAN_RESIDENT_STATUSES = (
        "Architect initial draft",
        "Architect draft",
        "Ready for Planner",
        "Planner intake",
        "Ready for Architect response",
        "Architect response",
        "Superseded",
    )
    STANDALONE_REQUIRED_STATUSES = (
        "Planner finalize",
        "Ready for Coder",
        "Coder intake",
        "In progress",
        "Ready for Review",
        "Reviewer intake",
        "Reviewer code review",
        "Reviewer visual review",
        "Ready for Arch review",
        "Architect arch review",
        "Done",
    )

    def test_plan_resident_statuses_are_exactly_the_statuses_without_code_draft(self) -> None:
        vocab_path = MODULE_PATH.parent.parent / "docs/_meta/plan_vocab.json"
        statuses = json.loads(vocab_path.read_text(encoding="utf-8"))["plan_statuses"]
        canonical = {" ".join(value.lower().split()) for value in statuses["canonical"]}
        code_draft_required = set(statuses["groups"]["code_draft_required"])

        self.assertEqual(
            MODULE.ANALYSIS_PACK_PLAN_RESIDENT_STATUS_NORMS,
            frozenset(canonical - code_draft_required),
        )
        self.assertEqual(
            {" ".join(value.lower().split()) for value in self.PLAN_RESIDENT_STATUSES},
            set(MODULE.ANALYSIS_PACK_PLAN_RESIDENT_STATUS_NORMS),
        )
        self.assertEqual(
            {" ".join(value.lower().split()) for value in self.STANDALONE_REQUIRED_STATUSES},
            code_draft_required,
        )

    def test_resolver_reads_only_the_explicit_effective_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # The header status is deliberately a standalone-required one: the
            # resolver must decide only from the status the caller passes.
            plan = self._write_plan_resident(Path(tmpdir), status="Ready for Review")
            plan_text = plan.read_text(encoding="utf-8")

            def resolve(status: str | None) -> object:
                return MODULE.resolve_analysis_pack_authority(
                    origin_plan_path=plan,
                    plan_text=plan_text,
                    effective_status=status,
                )

            resident = {
                status: resolve(status)
                for status in (*self.PLAN_RESIDENT_STATUSES, "`Superseded`", "  ready  for PLANNER ")
            }
            standalone = {
                status: resolve(status)
                for status in (*self.STANDALONE_REQUIRED_STATUSES, None, "", "Cancelled")
            }

        for status, resolved in resident.items():
            with self.subTest(status=status):
                self.assertEqual(resolved.mode, "legacy")
                self.assertTrue(resolved.is_valid)
                self.assertEqual(resolved.authority_text, plan_text)
        for status, resolved in standalone.items():
            with self.subTest(status=status):
                self.assertEqual(resolved.mode, "external")
                self.assertEqual(resolved.error_token, "analysis_pack_authority_invalid")
                self.assertEqual(resolved.detail_category, "ref_missing")
                self.assertEqual(resolved.authority_text, "")

    def test_explicit_ref_keeps_external_checks_on_intake_and_terminal_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid, _, _ = self._write_external(root / "valid")
            duplicate, _, _ = self._write_external(
                root / "duplicate",
                origin_rows="| `route_recommendation` | `reject` |",
            )
            missing_pack, _, _ = self._write_external(root / "missing-pack", write_pack=False)
            results = {
                (label, status): self._resolve(plan, effective_status=status)
                for label, plan in (
                    ("valid", valid),
                    ("duplicate", duplicate),
                    ("missing_pack", missing_pack),
                )
                for status in ("Architect draft", "Superseded", "Done")
            }

        for (label, status), resolved in results.items():
            with self.subTest(carrier=label, status=status):
                self.assertEqual(resolved.mode, "external")
                expected = {
                    "valid": "",
                    "duplicate": "operational_duplicate",
                    "missing_pack": "pack_missing",
                }[label]
                self.assertEqual(resolved.detail_category, expected)

    def test_oracle_authority_readback_follows_the_header_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            intake = self._write_plan_resident(root / "intake", status="Ready for Planner")
            superseded = self._write_plan_resident(root / "superseded", status="Superseded")
            review = self._write_plan_resident(root / "review", status="Ready for Review")
            results = {
                "intake": MODULE.oracle_result(intake),
                "superseded": MODULE.oracle_result(superseded),
                "review": MODULE.oracle_result(review),
            }

        for label in ("intake", "superseded"):
            with self.subTest(status=label):
                self.assertEqual(results[label].planning_contour_role, "source_analysis")
                self.assertNotIn(
                    "analysis_pack_authority_invalid",
                    results[label].analysis_route_lifecycle_reason,
                )
        self.assertEqual(results["review"].planning_contour_role, "source_analysis")
        self.assertEqual(results["review"].analysis_route_lifecycle_state, "warning")
        self.assertEqual(
            results["review"].analysis_route_lifecycle_reason,
            "analysis_pack_authority_invalid:ref_missing",
        )

    def test_semantic_checkpoint_guard_uses_only_generic_route_fields(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            helper = PlanStatusOracleTests(methodName="runTest")
            helper._write_plan_vocab(root)
            plan = helper._write_plan(
                root,
                "docs/plans/260802_2341_checkpoint_guard.md",
                helper._scope_expansion_body(
                    status="Ready for Coder",
                    scope_expansion={
                        "state": "n/a",
                        "target_contour": "developer_wave",
                        "source_ref": "docs/plans/fixture.md#Evidence",
                        "reason": "checkpoint fixture",
                    },
                ),
            )
            helper._attach_not_applicable_machine_authority(root, plan)
            checkpoint = {
                "state": "required",
                "reason_code": "resolution_required",
                "authority_decision_id": "mad-260815-0100",
                "authority_carrier_sha256": "a" * 64,
                "grammar_contour_id": "gc_" + "b" * 64,
            }
            with mock.patch.object(MODULE, "semantic_cycle_checkpoint_report", return_value=checkpoint):
                payload = helper._json_payload(plan)

            self.assertTrue(payload["route_guard_triggered"])
            self.assertEqual(payload["route_guard_kind"], "semantic_cycle_checkpoint_required")
            self.assertEqual(payload["route_guard_next_owner"], "Architect")
            self.assertIn("resolution_required", payload["route_guard_reason"])
            self.assertFalse(any("checkpoint" in key for key in payload if key not in {"route_guard_kind", "route_guard_reason"}))
            self.assertNotIn("grammar_contour_id", payload)
            self.assertNotIn("authority_decision_id", payload)

    def test_semantic_checkpoint_scope_precedence_and_architect_normalization(self) -> None:
        checkpoint = {"state": "blocked", "reason_code": "resolution_next_status_mismatch"}
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            helper = PlanStatusOracleTests(methodName="runTest")
            helper._write_plan_vocab(root)
            scope_plan = helper._write_plan(
                root,
                "docs/plans/260802_2341_checkpoint_scope_precedence.md",
                helper._scope_expansion_body(
                    status="Ready for Review",
                    scope_expansion={
                        "state": "reroute_required",
                        "target_contour": "decomposition_wave",
                        "source_ref": "docs/plans/fixture.md#Evidence",
                        "reason": "existing scope guard wins",
                    },
                ),
            )
            architect_plan = helper._write_plan(
                root,
                "docs/plans/260802_2341_checkpoint_architect_response.md",
                helper._scope_expansion_body(
                    status="Architect response",
                    scope_expansion={
                        "state": "n/a",
                        "target_contour": "developer_wave",
                        "source_ref": "docs/plans/fixture.md#Evidence",
                        "reason": "Architect owns normalization",
                    },
                ),
            )
            with mock.patch.object(MODULE, "semantic_cycle_checkpoint_report", return_value=checkpoint):
                scope_payload = helper._json_payload(scope_plan)
                architect_payload = helper._json_payload(architect_plan)

        self.assertEqual(scope_payload["route_guard_kind"], "scope_expansion_reroute_required")
        self.assertEqual(scope_payload["route_guard_next_owner"], "Architect")
        self.assertFalse(architect_payload["route_guard_triggered"])
        self.assertEqual(architect_payload["route_guard_kind"], "none")


class MachineAuthorityAdmissionOracleTests(unittest.TestCase):
    SOURCE_REL = "docs/plans/260814_0900_machine_authority_fixture.md"
    DRAFT_REL = "docs/code_drafts/260814_0900_machine_authority_fixture__code_draft.md"

    def _required_decision(
        self,
        *,
        cutover_policy: object | None = None,
        cardinality: str = "exactly_one_per_downstream_handoff",
    ) -> dict[str, object]:
        """Build the smallest valid required carrier for this matrix."""

        decision: dict[str, object] = {
            "schema_version": MODULE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "decision_id": "mad-260814-0900",
            "applicability": "required",
            "state": "frozen",
            "impacts": ["authorization", "routing"],
            "cutover_policy": copy.deepcopy(
                MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY
                if cutover_policy is None
                else cutover_policy
            ),
            "recommended_route": {
                "id": "meta_json_v1",
                "kind": "structured_carrier",
                "authority_host": {
                    "repo": "current",
                    "path": self.SOURCE_REL,
                    "locator": "json_pointer:/plan_meta/machine_authority_decision",
                },
                "canonical_writer": "fixture-writer",
                "canonical_reader": "scripts/plan_lint.py:strict_plan_meta_json",
                "derived_consumers": ["fixture_censor", "fixture_oracle"],
                "schema": MODULE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                "identity_fields": ["decision_id", "plan_path"],
                "cardinality": cardinality,
                "failure_behavior": {
                    key: "fail_closed" for key in MODULE.MACHINE_AUTHORITY_DECISION_FAILURE_KEYS
                },
            },
            "alternatives": [
                {
                    "id": "fixture_free_form",
                    "kind": "fixture",
                    "disposition": "rejected",
                    "tradeoff": "fixture",
                },
                {
                    "id": "fixture_prose",
                    "kind": "fixture",
                    "disposition": "rejected",
                    "tradeoff": "fixture",
                },
            ],
            "owner_confirmation": {
                "state": "confirmed",
                "question_ref": "Q5",
                "decision_id": "mad-260814-0900",
                "route_id": "meta_json_v1",
                "carrier_sha256": "",
            },
        }
        confirmation = decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        confirmation["carrier_sha256"] = MODULE.machine_authority_decision_sha256(decision)
        return decision

    def _write_draft_ref(self, root: Path, plan_rel: str, decision: dict[str, object]) -> Path:
        draft = root / f"docs/code_drafts/{Path(plan_rel).stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: machine-authority fixture\n\n```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": plan_rel,
                        "machine_authority_decision_ref": {
                            "applicability": "required",
                            "decision_id": decision["decision_id"],
                            "carrier_sha256": MODULE.machine_authority_decision_sha256(decision),
                        },
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        return draft

    def _write_required_fixture(
        self,
        root: Path,
        *,
        decision: dict[str, object] | None = None,
        status: str = "Ready for Coder",
    ) -> Path:
        decision = self._required_decision() if decision is None else decision
        plan = root / self.SOURCE_REL
        plan.parent.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            standalone_git_root(root)
        plan.write_text(
            "# Plan: machine-authority fixture\n\n"
            "**Plan type:** dev\n"
            f"**Status:** {status}\n\n"
            "## Meta\n```json\n"
            + json.dumps(
                {"plan_meta": {"cluster": "process", "machine_authority_decision": decision}},
                indent=2,
            )
            + "\n```\n\n"
            "## Q&A log\n\n"
            "- [2026-08-14 18:20 MSK] (Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
            "- [2026-08-14 18:21 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: fixture\n",
            encoding="utf-8",
        )
        self._write_draft_ref(root, self.SOURCE_REL, decision)
        return plan

    def _write_plan(self, root: Path, rel_path: str, *, status: str, meta: dict[str, object]) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not (root / ".git").exists():
            standalone_git_root(root)
        path.write_text(
            "# Plan: machine-authority fixture\n\n"
            "**Plan type:** dev\n"
            f"**Status:** {status}\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": meta}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        ensure_fixture_git(root)
        return path

    def _write_rejected_source_with_successor(
        self,
        root: Path,
        *,
        successor_rel: str,
        successor_id: str,
        successor_status: str,
        confirmation_state: str,
        defect: str | None = None,
        source_policy: object | None = None,
        successor_policy: object | None = None,
    ) -> Path:
        root.joinpath(".git").mkdir(exist_ok=True)
        source_meta = {
            "cluster": "process",
            "machine_authority_decision": self._required_decision(cutover_policy=source_policy),
        }
        source_decision = source_meta["machine_authority_decision"]
        assert isinstance(source_decision, dict)
        source_meta["next_plans"] = [successor_rel]
        source_confirmation = source_decision["owner_confirmation"]
        assert isinstance(source_confirmation, dict)
        source_confirmation.update(
            {
                "state": "rejected",
                "successor_plan_ref": successor_rel,
            }
        )

        source = self._write_plan(root, self.SOURCE_REL, status="Superseded", meta=source_meta)
        source_qna = (
            "\n## Q&A log\n\n"
            "- [2026-08-14 18:20 MSK] (Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
            "- [2026-08-14 18:21 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: fixture\n"
        )
        if defect == "source_missing_answer":
            source_qna = source_qna.rsplit("\n- [2026-08-14 18:21 MSK]", 1)[0] + "\n"
        source.write_text(source.read_text(encoding="utf-8") + source_qna, encoding="utf-8")
        self._write_draft_ref(root, self.SOURCE_REL, source_decision)

        successor_meta = json.loads(json.dumps(source_meta))
        successor_meta["depends_on"] = [self.SOURCE_REL]
        successor_meta["next_plans"] = []
        successor_decision = successor_meta["machine_authority_decision"]
        assert isinstance(successor_decision, dict)
        successor_decision["decision_id"] = successor_id
        if successor_policy is not None:
            successor_decision["cutover_policy"] = copy.deepcopy(successor_policy)
        route = successor_decision["recommended_route"]
        assert isinstance(route, dict)
        authority_host = route["authority_host"]
        assert isinstance(authority_host, dict)
        authority_host["path"] = successor_rel
        confirmation = successor_decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        confirmation.clear()
        confirmation.update(
            {
                "state": confirmation_state,
                "question_ref": "Q3",
                "decision_id": successor_id,
                "route_id": route["id"],
                "carrier_sha256": MODULE.machine_authority_decision_sha256(successor_decision),
            }
        )
        if defect == "malformed":
            successor_decision["unexpected"] = "no"
        elif defect == "wrong_digest":
            confirmation["carrier_sha256"] = "0" * 64
        elif defect == "wrong_route":
            confirmation["route_id"] = "wrong_route"

        successor = root / successor_rel
        successor.parent.mkdir(parents=True, exist_ok=True)
        qna = ""
        if confirmation_state == "confirmed":
            qna = (
                "\n## Q&A log\n\n"
                "- [2026-08-14 18:20 MSK] (Architect -> Owner, id=Q3, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
                "- [2026-08-14 18:21 MSK] (Owner -> Architect, id=Q3, blocker=no, needs_owner=no, status=closed) A: fixture\n"
            )
        successor.write_text(
            "# Plan: machine-authority successor fixture\n\n"
            "**Plan type:** dev\n"
            f"**Status:** {successor_status}\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": successor_meta}, indent=2)
            + "\n```\n"
            + qna,
            encoding="utf-8",
        )
        if confirmation_state == "confirmed":
            successor_digest = MODULE.machine_authority_decision_sha256(successor_decision)
            successor_draft = root / f"docs/code_drafts/{successor.stem}__code_draft.md"
            successor_draft.parent.mkdir(parents=True, exist_ok=True)
            successor_draft.write_text(
                "# Code draft: machine-authority successor fixture\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": successor_rel,
                            "cluster": "process",
                            "machine_authority_decision_ref": {
                                "applicability": "required",
                                "decision_id": successor_id,
                                "carrier_sha256": successor_digest,
                            },
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
                encoding="utf-8",
            )
        return source

    def test_terminal_missing_carrier_blocks_queue_closeout_before_raw_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan(
                Path(tmpdir),
                "docs/plans/260814_0917_machine_authority_terminal.md",
                status="Done",
                meta={"cluster": "process"},
            )
            result = MODULE.oracle_result(plan)
            payload = MODULE.json_payload(result, plan)

        self.assertEqual(result.machine_authority_decision_state, "missing")
        self.assertTrue(result.route_guard_triggered)
        self.assertEqual(result.route_guard_kind, "machine_authority_decision_missing_required_carrier")
        self.assertFalse(result.queue_closeout_ready)
        self.assertEqual(result.queue_closeout_kind, "route_guard_blocked")
        self.assertEqual(payload["machine_authority_decision_state"], "missing")
        self.assertEqual(payload["machine_authority_decision_reason"], "missing_required_carrier")

    def test_scope_expansion_guard_keeps_precedence_over_machine_authority_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            PlanStatusOracleTests(methodName="runTest")._write_plan_vocab(root)
            plan = self._write_plan(
                root,
                "docs/plans/260814_0918_machine_authority_scope.md",
                status="Ready for Coder",
                meta={
                    "cluster": "process",
                    "scope_expansion": {
                        "state": "reroute_required",
                        "target_contour": "developer_wave",
                        "source_ref": "docs/code_reviews/fixture.md#B1",
                        "reason": "fixture scope guard",
                    },
                },
            )
            result = MODULE.oracle_result(plan)

        self.assertEqual(result.machine_authority_decision_state, "missing")
        self.assertTrue(result.route_guard_triggered)
        self.assertEqual(result.route_guard_kind, "scope_expansion_reroute_required")

    def test_machine_authority_guard_precedes_semantic_checkpoint_after_scope_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan(
                Path(tmpdir),
                "docs/plans/260814_0925_machine_authority_checkpoint.md",
                status="Ready for Coder",
                meta={"cluster": "process"},
            )
            with mock.patch.object(
                MODULE,
                "semantic_cycle_checkpoint_report",
                return_value={"state": "required", "reason_code": "fixture_checkpoint"},
            ):
                result = MODULE.oracle_result(plan)

        self.assertTrue(result.route_guard_triggered)
        self.assertEqual(result.route_guard_kind, "machine_authority_decision_missing_required_carrier")
        self.assertEqual(result.route_guard_next_owner, "Architect")

    def test_required_projection_keeps_authority_fields_in_json_and_plain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_required_fixture(root)
            result = MODULE.oracle_result(plan)
            payload = MODULE.json_payload(result, plan)
            current = MODULE.build_current_state(result, plan)
            plain = dict(
                line.split("=", 1)
                for line in MODULE.format_current_state_plain(current).splitlines()
                if "=" in line
            )

        expected_fields = {
            "machine_authority_decision_state": "frozen_confirmed",
            "machine_authority_decision_reason": "ok",
            "machine_authority_decision_id": "mad-260814-0900",
            "machine_authority_decision_route": "meta_json_v1",
            "machine_authority_decision_confirmation_state": "confirmed",
            "machine_authority_decision_ref_state": "valid",
        }
        for key, value in expected_fields.items():
            self.assertEqual(payload[key], value)
            self.assertEqual(current[key], value)
            self.assertEqual(plain[key], value)
        self.assertEqual(
            current["authorities"]["machine_authority_decision"]["carrier_sha256"],
            payload["machine_authority_decision_carrier_sha256"],
        )

    def test_exact_two_cutover_policies_preserve_required_lifecycle(self) -> None:
        policies = (
            ("handoff", MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY),
            ("legacy", MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY),
        )
        cases = (
            ("draft", "Architect draft", "draft", "pending", "draft", "ok", False),
            ("frozen_confirmed", "Ready for Coder", "frozen", "confirmed", "frozen_confirmed", "ok", False),
            ("frozen_pending", "Architect draft", "frozen", "pending", "frozen_pending", "ok", False),
            ("pending_downstream", "Ready for Coder", "frozen", "pending", "invalid", "owner_confirmation_pending", True),
            ("pending_planner_intake", "Planner intake", "frozen", "pending", "invalid", "owner_confirmation_pending", True),
            ("pending_arch_review", "Architect arch review", "frozen", "pending", "invalid", "owner_confirmation_pending", True),
            ("rejected_planner_intake", "Planner intake", "frozen", "rejected", "invalid", "owner_confirmation_rejected", True),
            ("rejected_arch_review", "Architect arch review", "frozen", "rejected", "invalid", "owner_confirmation_rejected", True),
        )
        for policy_name, policy in policies:
            for label, status, decision_state, confirmation_state, expected_state, expected_reason, expected_guard in cases:
                with self.subTest(policy=policy_name, case=label), tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    policy_before = copy.deepcopy(policy)
                    decision = self._required_decision(cutover_policy=policy)
                    decision["state"] = decision_state
                    confirmation = decision["owner_confirmation"]
                    assert isinstance(confirmation, dict)
                    confirmation["state"] = confirmation_state
                    if confirmation_state == "rejected":
                        confirmation["successor_plan_ref"] = "docs/plans/fixture_successor.md"
                    confirmation["carrier_sha256"] = MODULE.machine_authority_decision_sha256(decision)
                    decision_before = copy.deepcopy(decision)
                    plan = self._write_required_fixture(root, decision=decision, status=status)
                    readback = MODULE.machine_authority_decision_readback(plan)

                self.assertEqual((readback.state, readback.reason_code), (expected_state, expected_reason))
                self.assertEqual(readback.route_guard_required, expected_guard)
                self.assertEqual(decision, decision_before)
                self.assertEqual(policy, policy_before)

    def test_planner_intake_allows_confirmed_carrier_before_draft_materialization(self) -> None:
        policies = (
            ("handoff", MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY),
            ("legacy", MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY),
        )
        for policy_name, policy in policies:
            with self.subTest(policy=policy_name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan = self._write_required_fixture(
                    root,
                    decision=self._required_decision(cutover_policy=policy),
                    status="Planner intake",
                )
                (root / self.DRAFT_REL).unlink()
                readback = MODULE.machine_authority_decision_readback(plan)
                result = MODULE.oracle_result(plan)

                self.assertEqual(
                    (readback.state, readback.reason_code, readback.ref_state, readback.route_guard_required),
                    ("frozen_confirmed", "ok", "missing", False),
                )
                self.assertFalse(result.route_guard_triggered)

    def test_arch_review_requires_valid_current_draft_ref_for_confirmed_carrier(self) -> None:
        policies = (
            ("handoff", MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY),
            ("legacy", MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY),
        )
        cases = (
            ("valid", None, "frozen_confirmed", "ok", False),
            ("missing", "missing", "invalid", "code_draft_ref_invalid", True),
            ("stale", "stale", "invalid", "code_draft_ref_invalid", True),
        )
        for policy_name, policy in policies:
            for label, defect, expected_state, expected_reason, expected_guard in cases:
                with self.subTest(policy=policy_name, case=label), tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    decision = self._required_decision(cutover_policy=policy)
                    plan = self._write_required_fixture(root, decision=decision, status="Architect arch review")
                    draft = root / self.DRAFT_REL
                    if defect == "missing":
                        draft.unlink()
                    elif defect == "stale":
                        digest = MODULE.machine_authority_decision_sha256(decision)
                        draft.write_text(draft.read_text(encoding="utf-8").replace(digest, "0" * 64, 1), encoding="utf-8")
                    readback = MODULE.machine_authority_decision_readback(plan)
                    result = MODULE.oracle_result(plan)

                self.assertEqual((readback.state, readback.reason_code), (expected_state, expected_reason))
                self.assertEqual(readback.route_guard_required, expected_guard)
                self.assertEqual(result.route_guard_triggered, expected_guard)
                if label == "valid":
                    self.assertEqual(readback.ref_state, "valid")
                elif label == "missing":
                    self.assertIn("missing current-plan code draft", readback.reason)
                else:
                    self.assertIn("drifts from validated carrier", readback.reason)

    def test_cutover_policy_rejects_non_exact_values(self) -> None:
        legacy_policy = MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY
        invalid_policies = (
            ("third", {"kind": "third_policy"}),
            (
                "mixed",
                {
                    "kind": "status_and_purpose_handoff",
                    "legacy_behavior": "read_only_no_backfill",
                },
            ),
            ("wrong_type", "status_and_purpose_handoff"),
            ("legacy_missing_key", {key: value for key, value in legacy_policy.items() if key != "snapshot_rule"}),
            ("legacy_extra_key", {**legacy_policy, "unexpected": True}),
            ("legacy_altered_text", {**legacy_policy, "legacy_behavior": "read_only_without_backfill"}),
        )
        for label, policy in invalid_policies:
            for status in ("Architect initial draft", "Architect draft", "Ready for Coder"):
                with self.subTest(policy=label, status=status), tempfile.TemporaryDirectory() as tmpdir:
                    decision = self._required_decision(cutover_policy=policy)
                    plan = self._write_required_fixture(Path(tmpdir), decision=decision, status=status)
                    readback = MODULE.machine_authority_decision_readback(plan)

                self.assertEqual((readback.state, readback.reason_code), ("invalid", "cutover_policy_invalid"))
                self.assertTrue(readback.route_guard_required)

    def test_legacy_cutover_policy_has_stable_golden_digest_without_mutation(self) -> None:
        legacy_policy = MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY
        policy_before = copy.deepcopy(legacy_policy)
        decision = self._required_decision(
            cutover_policy=legacy_policy,
            cardinality="exactly_one_per_post_cutover_plan",
        )
        decision_before = copy.deepcopy(decision)
        expected_digest = "48610e1029bfbf4e45ea830faabe30dfc8089755cce605b4402a9b895a529f0c"

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_required_fixture(Path(tmpdir), decision=decision)
            readback = MODULE.machine_authority_decision_readback(plan)

        self.assertEqual(MODULE.machine_authority_decision_sha256(decision), expected_digest)
        self.assertEqual(readback.carrier_sha256, expected_digest)
        self.assertEqual((readback.state, readback.reason_code, readback.ref_state), ("frozen_confirmed", "ok", "valid"))
        self.assertEqual(legacy_policy, policy_before)
        self.assertEqual(decision, decision_before)

    def test_policy_replacement_requires_matching_confirmation_and_ref(self) -> None:
        legacy_decision = self._required_decision(
            cutover_policy=MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY,
            cardinality="exactly_one_per_post_cutover_plan",
        )
        legacy_digest = MODULE.machine_authority_decision_sha256(legacy_decision)
        handoff_decision = self._required_decision()
        handoff_digest = MODULE.machine_authority_decision_sha256(handoff_decision)
        stale_confirmation = copy.deepcopy(handoff_decision)
        stale_confirmation_owner = stale_confirmation["owner_confirmation"]
        assert isinstance(stale_confirmation_owner, dict)
        stale_confirmation_owner["carrier_sha256"] = legacy_digest

        with tempfile.TemporaryDirectory() as tmpdir:
            mismatch_plan = self._write_required_fixture(Path(tmpdir), decision=stale_confirmation)
            confirmation_readback = MODULE.machine_authority_decision_readback(mismatch_plan)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ref_plan = self._write_required_fixture(root, decision=handoff_decision)
            draft = root / self.DRAFT_REL
            draft.write_text(
                draft.read_text(encoding="utf-8").replace(handoff_digest, legacy_digest, 1),
                encoding="utf-8",
            )
            ref_readback = MODULE.machine_authority_decision_readback(ref_plan)

        self.assertEqual((confirmation_readback.state, confirmation_readback.reason_code), ("invalid", "owner_confirmation_mismatch"))
        self.assertEqual((ref_readback.state, ref_readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_nonstandard_successor_name_with_valid_carrier_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = self._write_rejected_source_with_successor(
                Path(tmpdir),
                successor_rel="docs/plans/260813_1917renamed.md",
                successor_id="mad-260813-1917",
                successor_status="Ready for Planner",
                confirmation_state="confirmed",
            )
            successor = source.parents[2] / "docs/plans/260813_1917renamed.md"
            readback = MODULE.machine_authority_decision_readback(successor)
            result = MODULE.oracle_result(successor)

        self.assertEqual((readback.state, readback.reason_code, readback.ref_state), ("frozen_confirmed", "ok", "valid"))
        self.assertFalse(readback.route_guard_required)
        self.assertFalse(result.route_guard_triggered)
        self.assertEqual(result.route_guard_kind, "none")

    def test_rejected_source_requires_full_successor_lifecycle_without_name_gate(self) -> None:
        cases = (
            ("pending", "docs/plans/260814_0930_pending_successor.md", "mad-260814-0930", "Architect draft", "pending", None, True),
            ("confirmed", "docs/plans/260814_0931_confirmed_successor.md", "mad-260814-0931", "Ready for Planner", "confirmed", None, True),
            ("malformed", "docs/plans/260814_0932_malformed_successor.md", "mad-260814-0932", "Architect draft", "pending", "malformed", False),
            ("old_name", "docs/plans/260813_1915_old_name_successor.md", "mad-260813-1916", "Architect draft", "pending", None, True),
            ("wrong_digest", "docs/plans/260814_0933_digest_successor.md", "mad-260814-0933", "Architect draft", "pending", "wrong_digest", False),
            ("wrong_route", "docs/plans/260814_0934_route_successor.md", "mad-260814-0934", "Architect draft", "pending", "wrong_route", False),
            ("terminal", "docs/plans/260814_0935_terminal_successor.md", "mad-260814-0935", "Done", "pending", None, False),
        )
        for label, successor_rel, successor_id, status, confirmation, defect, green in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                source = self._write_rejected_source_with_successor(
                    Path(tmpdir),
                    successor_rel=successor_rel,
                    successor_id=successor_id,
                    successor_status=status,
                    confirmation_state=confirmation,
                    defect=defect,
                )
                readback = MODULE.machine_authority_decision_readback(source)
                result = MODULE.oracle_result(source)

                if green:
                    expected_state = "frozen_pending" if confirmation == "pending" else "frozen_confirmed"
                    self.assertEqual((readback.state, readback.reason_code), ("frozen_rejected_successor", "ok"))
                    self.assertFalse(readback.route_guard_required)
                    self.assertFalse(result.route_guard_triggered)
                    successor = source.parents[2] / successor_rel
                    successor_readback = MODULE.machine_authority_decision_readback(successor)
                    self.assertEqual((successor_readback.state, successor_readback.reason_code), (expected_state, "ok"))
                else:
                    self.assertEqual((readback.state, readback.reason_code), ("invalid", "rejected_successor_invalid"))
                    self.assertTrue(result.route_guard_triggered)
                    self.assertIn("rejected_successor_invalid", result.route_guard_kind)

    def test_rejected_successor_accepts_mixed_policies_and_rejects_third_policy(self) -> None:
        cases = (
            (
                "legacy_to_handoff",
                MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY,
                MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY,
                True,
            ),
            (
                "handoff_to_legacy",
                MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY,
                MODULE.MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY,
                True,
            ),
            (
                "third_successor",
                MODULE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY,
                {"kind": "third_policy"},
                False,
            ),
        )
        for label, source_policy, successor_policy, admitted in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                successor_rel = f"docs/plans/{label}-successor.md"
                source = self._write_rejected_source_with_successor(
                    Path(tmpdir),
                    successor_rel=successor_rel,
                    successor_id="mad-260814-0940",
                    successor_status="Architect draft",
                    confirmation_state="pending",
                    source_policy=source_policy,
                    successor_policy=successor_policy,
                )
                source_readback = MODULE.machine_authority_decision_readback(source)
                successor = source.parents[2] / successor_rel
                successor_readback = MODULE.machine_authority_decision_readback(successor)

            if admitted:
                self.assertEqual((source_readback.state, source_readback.reason_code), ("frozen_rejected_successor", "ok"))
                self.assertEqual((successor_readback.state, successor_readback.reason_code), ("frozen_pending", "ok"))
            else:
                self.assertEqual((source_readback.state, source_readback.reason_code), ("invalid", "rejected_successor_invalid"))
                self.assertEqual((successor_readback.state, successor_readback.reason_code), ("invalid", "cutover_policy_invalid"))

    def test_rejected_source_requires_its_canonical_question_and_answer_before_successor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = self._write_rejected_source_with_successor(
                Path(tmpdir),
                successor_rel="docs/plans/260814_0936_missing_source_answer.md",
                successor_id="mad-260814-0936",
                successor_status="Architect draft",
                confirmation_state="pending",
                defect="source_missing_answer",
            )
            readback = MODULE.machine_authority_decision_readback(source)
            result = MODULE.oracle_result(source)

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "owner_qna_lifecycle_invalid"))
        self.assertTrue(result.route_guard_triggered)
        self.assertIn("owner_qna_lifecycle_invalid", result.route_guard_kind)


class StrictNoParentDraftOracleTests(unittest.TestCase):
    """Regression matrix for the narrow active/parked parent exception."""

    PARENT_REL = "docs/plans/260823_1509_strict_na_parent.md"

    def _write_parent(
        self,
        root: Path,
        *,
        status: str = "Coder intake",
        phase_state: str = "active",
        code_draft_entry: str = "`N/A (why=strict parent fixture)`.",
        children: tuple[str, ...] = (),
        next_plans: tuple[str, ...] | None = None,
        child_map: bool = True,
        execution_queue: bool = True,
    ) -> Path:
        parent = root / self.PARENT_REL
        parent.parent.mkdir(parents=True, exist_ok=True)
        for child_rel in children:
            child = root / child_rel
            child.parent.mkdir(parents=True, exist_ok=True)
            child.write_text(
                "# Plan: strict N-A child fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Coder\n",
                encoding="utf-8",
            )

        decision = {
            "schema_version": MODULE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        meta = {
            "cluster": "process",
            "tags": [],
            "phase_overlay": "decomposition_wave",
            "phase_state": phase_state,
            "parent": None,
            "next_plans": list(children if next_plans is None else next_plans),
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
            "machine_authority_decision": decision,
        }
        child_map_rows = "\n".join(
            f"| {index} | `{child_rel}` | fixture child |"
            for index, child_rel in enumerate(children, start=1)
        )
        execution_rows = "\n".join(f"- Plan: `{child_rel}`" for child_rel in children)
        child_map_section = (
            "## Child plan map\n"
            "| Queue order | Plan | Summary |\n"
            "| --- | --- | --- |\n"
            + child_map_rows
            + "\n\n"
            if child_map
            else ""
        )
        execution_section = (
            "## Execution queue\n"
            "- Resume parent: `fixture`\n"
            + execution_rows
            + "\n"
            if execution_queue
            else ""
        )
        parent.write_text(
            "# Plan: strict N-A parent fixture\n\n"
            "**Plan type:** dev\n"
            f"**Status:** {status}\n\n"
            "**Context links (source of truth):**\n"
            f"- Code draft(s): {code_draft_entry}\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": meta}, indent=2)
            + "\n```\n\n"
            + child_map_section
            + execution_section,
            encoding="utf-8",
        )
        return parent

    def test_strict_na_parent_is_not_required_across_lifecycle_statuses(self) -> None:
        statuses = (
            "Architect draft",
            "Planner finalize",
            "Ready for Coder",
            "Coder intake",
            "In progress",
            "Ready for Review",
            "Reviewer intake",
            "Reviewer review",
            "Ready for Arch review",
            "Done",
            "Superseded",
        )
        for status in statuses:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                parent = self._write_parent(Path(tmpdir), status=status)
                readback = MODULE.machine_authority_decision_readback(parent)

                self.assertEqual((readback.state, readback.reason_code), ("not_applicable", "ok"))
                self.assertEqual(readback.ref_state, "not_required")

    def test_strict_na_parent_rejects_nonliteral_or_conflicting_current_draft_carriers(self) -> None:
        cases = {
            "bare": "`N/A`",
            "missing_slash": "`N A (why=fixture)`",
            "trailing": "`N/A (why=fixture)` plus a live carrier",
            "live_ref": "`docs/code_drafts/260823_1509_strict_na_parent__code_draft.md`",
        }
        for label, entry in cases.items():
            with self.subTest(case=label), temporary_git_root() as tmpdir:
                parent = self._write_parent(
                    Path(tmpdir),
                    status="Ready for Coder",
                    code_draft_entry=entry,
                )
                readback = MODULE.machine_authority_decision_readback(parent)
                self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            parent = self._write_parent(root, status="Ready for Coder")
            draft = root / "docs/code_drafts/260823_1509_strict_na_parent__code_draft.md"
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text("# Conflicting current draft\n", encoding="utf-8")
            readback = MODULE.machine_authority_decision_readback(parent)
        self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

        with temporary_git_root() as tmpdir:
            parent = self._write_parent(Path(tmpdir), status="Ready for Coder")
            parent.write_text(
                parent.read_text(encoding="utf-8").replace(
                    "- Code draft(s): `N/A (why=strict parent fixture)`.\n",
                    "- Code draft(s): `N/A (why=strict parent fixture)`.\n"
                    "- Parent draft mirror: `docs/code_drafts/260823_1509_strict_na_parent__code_draft.md`\n",
                ),
                encoding="utf-8",
            )
            readback = MODULE.machine_authority_decision_readback(parent)
        self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_strict_na_parent_uses_authoritative_meta_not_a_preamble_decoy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = self._write_parent(Path(tmpdir), status="Ready for Coder")
            body = parent.read_text(encoding="utf-8").replace(
                '"phase_overlay": "decomposition_wave"',
                '"phase_overlay": "routing_only_baseline"',
                1,
            )
            parent.write_text(
                "```json\n"
                '{"plan_meta":{"phase_overlay":"decomposition_wave","phase_state":"active"}}\n'
                "```\n\n"
                + body,
                encoding="utf-8",
            )
            readback = MODULE.machine_authority_decision_readback(parent)

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_strict_na_child_graph_ignores_a_preamble_meta_decoy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parent = self._write_parent(root, status="Ready for Review")
            decoy_child = "docs/plans/260823_1510_preamble_decoy_child.md"
            child_path = root / decoy_child
            child_path.parent.mkdir(parents=True, exist_ok=True)
            child_path.write_text(
                "# Plan: preamble decoy child\n\n**Plan type:** dev\n**Status:** Ready for Coder\n",
                encoding="utf-8",
            )
            parent.write_text(
                "```json\n"
                + json.dumps(
                    {
                        "plan_meta": {
                            "phase_overlay": "decomposition_wave",
                            "phase_state": "active",
                            "next_plans": [decoy_child],
                        }
                    }
                )
                + "\n```\n\n"
                + parent.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            child_state = MODULE.decomposition_child_state(
                parent.read_text(encoding="utf-8"),
                root=root,
            )

        self.assertEqual(child_state.state, "missing")
        self.assertEqual(child_state.concrete_child_paths, ())
        self.assertNotIn(decoy_child, child_state.reason)

    def test_strict_na_parent_rejects_duplicate_context_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = self._write_parent(Path(tmpdir), status="Ready for Coder")
            parent.write_text(
                parent.read_text(encoding="utf-8").replace(
                    "- Code draft(s): `N/A (why=strict parent fixture)`.\n",
                    "- Code draft(s): `N/A (why=strict parent fixture)`.\n"
                    "- Code draft(s): `N/A (why=duplicate fixture)`.\n",
                ),
                encoding="utf-8",
            )
            readback = MODULE.machine_authority_decision_readback(parent)

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_required_1125_shaped_plan_without_own_draft_remains_red(self) -> None:
        plan_rel = "docs/plans/260823_1125_process_decomposition_parent_no_draft_admission_and_bundle.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan = root / plan_rel
            plan.parent.mkdir(parents=True, exist_ok=True)
            fixture = MachineAuthorityAdmissionOracleTests(methodName="runTest")
            decision = fixture._required_decision()
            decision["decision_id"] = "mad-260823-1125"
            route = decision["recommended_route"]
            assert isinstance(route, dict)
            authority_host = route["authority_host"]
            assert isinstance(authority_host, dict)
            authority_host["path"] = plan_rel
            confirmation = decision["owner_confirmation"]
            assert isinstance(confirmation, dict)
            confirmation["decision_id"] = "mad-260823-1125"
            confirmation["carrier_sha256"] = MODULE.machine_authority_decision_sha256(decision)
            plan.write_text(
                "# Plan: required no-draft fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Coder\n\n"
                "## Meta\n```json\n"
                + json.dumps({"plan_meta": {"cluster": "process", "machine_authority_decision": decision}}, indent=2)
                + "\n```\n\n"
                "## Q&A log\n\n"
                "- [2026-08-23 11:25 MSK] (Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
                "- [2026-08-23 11:26 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: fixture\n",
                encoding="utf-8",
            )
            readback = MODULE.machine_authority_decision_readback(plan)

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_active_to_parked_preserves_materialized_child_paths_and_partial_parked_is_missing(self) -> None:
        children = (
            "docs/plans/260823_1510_child_a.md",
            "docs/plans/260823_1511_child_b.md",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            active = self._write_parent(root, children=children, phase_state="active")
            active_state = MODULE.decomposition_child_state(active.read_text(encoding="utf-8"), root=root)
            parked = self._write_parent(root, children=children, phase_state="parked")
            parked_state = MODULE.decomposition_child_state(parked.read_text(encoding="utf-8"), root=root)
            partial = self._write_parent(
                root,
                children=children,
                phase_state="parked",
                next_plans=(),
                execution_queue=False,
            )
            partial_state = MODULE.decomposition_child_state(partial.read_text(encoding="utf-8"), root=root)

        self.assertEqual((active_state.state, active_state.expansion_source), ("queue_ready", "execution_queue"))
        self.assertEqual(active_state.concrete_child_paths, children)
        self.assertEqual((parked_state.state, parked_state.expansion_source), ("queue_ready", "execution_queue"))
        self.assertEqual(parked_state.concrete_child_paths, children)
        self.assertEqual(partial_state.state, "missing")
        self.assertEqual(partial_state.issues[0].kind, "decomposition_children_missing")

    def test_bounded_next_plans_keeps_routing_public_and_canonical_membership_complete(self) -> None:
        children = (
            "docs/plans/260823_1510_child_a.md",
            "docs/plans/260823_1511_child_b.md",
        )
        for phase_state in ("active", "parked"):
            with self.subTest(phase_state=phase_state), tempfile.TemporaryDirectory() as tmpdir:
                parent = self._write_parent(
                    Path(tmpdir),
                    children=children,
                    phase_state=phase_state,
                    next_plans=(children[0],),
                    execution_queue=False,
                )
                state = MODULE.decomposition_child_state(
                    parent.read_text(encoding="utf-8"),
                    root=parent.parents[2],
                )

            self.assertEqual((state.state, state.expansion_source), ("queue_ready", "next_plans"))
            self.assertEqual(state.concrete_child_paths, (children[0],))
            self.assertEqual(state.canonical_planning_child_paths, children)

    def test_canonical_member_and_next_only_graph_fail_closed(self) -> None:
        children = (
            "docs/plans/260823_1510_child_a.md",
            "docs/plans/260823_1511_child_b.md",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parent = self._write_parent(
                root,
                children=children,
                next_plans=(children[0],),
                execution_queue=False,
            )
            (root / children[1]).unlink()
            missing_member = MODULE.decomposition_child_state(
                parent.read_text(encoding="utf-8"),
                root=root,
            )

        self.assertEqual(missing_member.state, "missing")
        self.assertEqual(missing_member.concrete_child_paths, (children[0],))
        self.assertEqual(missing_member.canonical_planning_child_paths, children)
        self.assertEqual(missing_member.issues[0].kind, "decomposition_child_missing_file")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            parent = self._write_parent(
                root,
                children=children,
                next_plans=(children[0],),
                child_map=False,
                execution_queue=False,
            )
            next_only = MODULE.decomposition_child_state(
                parent.read_text(encoding="utf-8"),
                root=root,
            )

        self.assertEqual(next_only.state, "missing")
        self.assertEqual(next_only.concrete_child_paths, (children[0],))
        self.assertEqual(next_only.canonical_planning_child_paths, ())
        self.assertEqual(next_only.issues[0].kind, "decomposition_children_missing")

    def test_conflicting_child_carriers_fail_closed_for_active_and_parked(self) -> None:
        children = (
            "docs/plans/260823_1510_child_a.md",
            "docs/plans/260823_1511_child_b.md",
            "docs/plans/260823_1512_child_c.md",
        )
        for phase_state in ("active", "parked"):
            with self.subTest(phase_state=phase_state), tempfile.TemporaryDirectory() as tmpdir:
                parent = self._write_parent(
                    Path(tmpdir),
                    children=children,
                    phase_state=phase_state,
                    next_plans=(children[0], children[2]),
                )
                state = MODULE.decomposition_child_state(parent.read_text(encoding="utf-8"), root=parent.parents[2])

                self.assertEqual(state.state, "missing")
                self.assertEqual(state.issues[0].kind, "decomposition_child_graph_mismatch")

    def test_active_map_only_graph_remains_drafted(self) -> None:
        children = ("docs/plans/260823_1510_child_a.md",)
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = self._write_parent(
                Path(tmpdir),
                children=children,
                phase_state="active",
                next_plans=(),
                execution_queue=False,
            )
            state = MODULE.decomposition_child_state(parent.read_text(encoding="utf-8"), root=parent.parents[2])

        self.assertEqual((state.state, state.expansion_source), ("drafted", "child_plan_map"))


if __name__ == "__main__":
    unittest.main()

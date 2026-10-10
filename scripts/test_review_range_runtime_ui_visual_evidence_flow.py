#!/usr/bin/env python3
"""Pinned producer-to-closeout runtime-UI visual evidence flow."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import sys
from textwrap import dedent
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from authority_bootstrap_test_support import run_python_stdin
from test_contract_authority_support import AuthorityFixture, git, write


_PROBE_SOURCE = r'''
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest import mock


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


mode = sys.argv[1]
request = json.loads(sys.argv[2])
root = Path.cwd()

if mode == "inventory":
    import contract_authority_context as authority
    import review_range_scaffold_engine as engine

    emit({
        "merge_paths": list(authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS),
        "review_paths": [
            str(spec["path"])
            for spec in engine.PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["inputs"].values()
        ],
    })
elif mode == "tracker_headers":
    import contract_authority_context as authority
    import merge_gate_policy

    authority.ENGAGED_ADMISSION_COMPLETE = True
    context, policy = merge_gate_policy.policy_for_root(root)
    if context is None or policy is None:
        raise RuntimeError("missing engaged merge policy")
    emit({
        "POLICY_SCHEMA": merge_gate_policy.POLICY_SCHEMA,
        "POLICY_SHA256": policy.raw_sha256,
        "AUTHORITY_GENERATION": context.generation_sha256,
    })
elif mode == "legacy":
    import contract_authority_context as authority
    import review_visual_lane_contract as visual

    authority.ENGAGED_ADMISSION_COMPLETE = True
    contract = visual.discover_review_visual_lane(
        project_root=root,
        profile_id="default",
        changed_entries=visual.git_changed_entries(root, request["base"], request["head"]),
        exclude_docs=False,
        review_basename="raw_legacy_runtime_ui",
        plan_ref="docs/plans/260917_raw_legacy_runtime_ui.md",
    )
    emit({
        "availability_state": contract["availability_state"],
        "runtime_ui_kind": contract["runtime_ui_kind"],
        "reason": contract["reason"],
        "runtime_ui_paths": [
            path
            for row in contract["changed_path_evidence"]
            if row["runtime_ui"]
            for path in row["runtime_ui_paths"]
        ],
        "mandatory_modes": contract["mandatory_modes"],
        "comparator_command": contract["comparator_command"],
        "contract_errors": visual.validate_contract(contract),
    })
elif mode == "materialized":
    import contract_authority_context as authority
    import plan_lint
    import review_visual_lane_contract as visual

    authority.ENGAGED_ADMISSION_COMPLETE = True
    plan_rel = request["plan_rel"]
    plan_path = root / plan_rel
    plan_text = plan_path.read_text(encoding="utf-8")
    draft_rel = next(
        line.split(chr(96), 2)[1]
        for line in plan_text.splitlines()
        if line.startswith("- Code draft(s): ")
    )
    draft_text = (root / draft_rel).read_text(encoding="utf-8")
    plan_contract, plan_errors = visual.parse_materialized_contract(
        plan_text,
        project_root=root,
        expected_plan_ref=plan_rel,
    )
    draft_contract, draft_errors = visual.parse_materialized_contract(
        draft_text,
        project_root=root,
        expected_plan_ref=plan_rel,
    )
    previous_root = plan_lint.REPO_ROOT
    try:
        plan_lint.REPO_ROOT = root
        lint = plan_lint.validate_materialized_review_visual_lane_contract(
            plan_path, plan_text.splitlines()
        )
    finally:
        plan_lint.REPO_ROOT = previous_root
    emit({
        "plan_contract_errors": plan_errors,
        "draft_contract_errors": draft_errors,
        "contracts_equal": plan_contract == draft_contract,
        "contract": plan_contract,
        "plan_has_ref": "review_visual_lane_contract_ref.v1" in plan_text,
        "plan_has_target_scope_note": request["expected_scope_note"] in plan_text,
        "draft_has_target_scope_note": request["expected_scope_note"] in draft_text,
        "plan_has_initial_scope_note": "initial local scope note" in plan_text,
        "draft_has_initial_scope_note": "initial local scope note" in draft_text,
        "plan_has_runtime_decoy": "RUNTIME_DECOY" in plan_text,
        "draft_has_runtime_decoy": "RUNTIME_DECOY" in draft_text,
        "lint_codes": [getattr(item, "code", str(item)) for item in lint],
    })
elif mode == "evidence":
    import contract_authority_context as authority
    import merge_bundle_report
    import post_merge_audit_lint
    import range_review_risk_packet
    import review_artifact_lint

    authority.ENGAGED_ADMISSION_COMPLETE = True
    review_rel = request["review_rel"]
    audit_rel = request["audit_rel"]
    tracker_rel = request["tracker_rel"]
    readback = review_artifact_lint.evaluate_runtime_ui_visual_evidence(
        project_root=root,
        review_path=review_rel,
    )
    artifacts = post_merge_audit_lint.load_audit_artifacts(root, [audit_rel])
    authority_codes = sorted({
        finding.code
        for artifact in artifacts
        for finding in post_merge_audit_lint._lint_current_audit_status_authority(artifact)
    })
    report = merge_bundle_report.build_report(root, root / tracker_rel)
    preflight = merge_bundle_report.validate_post_merge_receipt_preflight(
        root=root,
        step="post_merge_audit",
        path=audit_rel,
    )
    packet, packet_errors = range_review_risk_packet.build_packet_payload(
        repo_root=root,
        range_ref=request["range_ref"],
        out_path=root / request["risk_rel"],
        host_paths={name: root / path for name, path in request["host_paths"].items()},
        changed_files=["templates/runtime/page.html"],
    )
    emit({
        "visual_state": readback.state,
        "visual_reason_codes": list(readback.reason_codes),
        "authority_codes": authority_codes,
        "report_state": report["post_merge_audit_authority"]["state"],
        "preflight_codes": [error["code"] for error in preflight["errors"]],
        "packet_is_none": packet is None,
        "packet_error_codes": [error.code for error in packet_errors],
        "packet_visual_status": None if packet is None else packet["visual_status"]["status"],
    })
elif mode == "ready":
    import contract_authority_context as authority
    import merge_bundle_report
    import post_merge_ready_to_push_closeout

    authority.ENGAGED_ADMISSION_COMPLETE = True
    tracker = root / request["tracker_rel"]
    green_report = merge_bundle_report.build_report(root, tracker)
    # This retained narrow seam only exercises the already-closed result after
    # real authority, report, preflight, packet, and visual readbacks above.  It
    # deliberately does not claim a clean-worktree closeout transaction.
    ready_report = {
        "status": "ok",
        "errors": [],
        "range": {
            "range": request["range_ref"],
            "base_short": request["base_short"],
            "head_short": request["head_short"],
        },
        "tracker": {
            "current_step": "",
            "steps": [{"key": "step:ready_to_push", "checked": True}],
        },
        "git_status": {"required": [], "candidate_contextual": [], "suspicious": []},
        "post_merge_audit_authority": green_report["post_merge_audit_authority"],
    }
    with mock.patch.object(
        post_merge_ready_to_push_closeout.merge_bundle_report,
        "build_report",
        return_value=ready_report,
    ):
        ready = post_merge_ready_to_push_closeout.close_ready_to_push(root, tracker)
    emit({"status": ready["status"], "action": ready.get("action")})
else:
    raise RuntimeError(f"unknown probe mode: {mode}")
'''


class ReviewRangeRuntimeUiVisualEvidenceFlowTest(unittest.TestCase):
    @staticmethod
    def _review_range_policy_bytes(scope_note: str) -> bytes:
        return json.dumps(
            {
                "schema_version": "review_range_policy.v1",
                "corpus_rule": "planveyor.v1",
                "visual_rule": "planveyor.v1",
                "render_profile": "planveyor.review_only.v1",
                "section_prose": {
                    "review_scope_note": scope_note,
                    "reviewability_note": "fixture reviewability note",
                    "runtime_lane_note": "fixture runtime lane note",
                    "verification_handoff_note": "fixture verification handoff note",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8") + b"\n"

    @staticmethod
    def _target_visual_lane_sources() -> dict[str, bytes]:
        comparator = (
            "./scripts/run_visual_check.sh --run-id review --repeat 2 "
            "--logs-dir .tmp/visual-regression/logs"
        )
        primary = (
            "./scripts/review_visual_design_audit.sh --mode primary --plan docs/plans/<plan>.md "
            "--port 8073 --assets-dir .tmp/human-visual-review/primary"
        )
        secondary = (
            "./scripts/review_visual_design_audit.sh --mode secondary --plan docs/plans/<plan>.md "
            "--port 8074 --assets-dir .tmp/human-visual-review/secondary"
        )
        fence = chr(96) * 3
        commands = "\n".join((comparator, primary, secondary))
        return {
            "docs/smoke_visual.md": (
                "<!-- verification-receipt lane=visual.check_1 lane=visual.check_2 "
                "lane=vis.human_visual_review_local -->\n"
                f"{fence}bash\n{commands}\n{fence}\n"
            ).encode("utf-8"),
            "docs/testing_runbook.md": f"{fence}bash\n{commands}\n{fence}\n".encode("utf-8"),
        }

    def _run_probe(
        self,
        fixture: AuthorityFixture,
        mode: str,
        request: dict[str, object],
    ) -> dict[str, object]:
        environment = fixture.environment()
        environment["PYBIN"] = str(Path(sys.executable).resolve())
        environment["PLANVEYOR_RUNTIME_SOURCE_KIND"] = "git"
        result = run_python_stdin(
            fixture,
            _PROBE_SOURCE,
            mode,
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            cwd=fixture.target_root,
            environment=environment,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def _activate_engaged_fixture(self, fixture: AuthorityFixture) -> str:
        inventory = self._run_probe(fixture, "inventory", {})
        merge_paths = inventory["merge_paths"]
        review_paths = inventory["review_paths"]
        self.assertIsInstance(merge_paths, list)
        self.assertIsInstance(review_paths, list)
        self.assertEqual(len(merge_paths), 60)
        self.assertEqual(len(set(merge_paths)), 60)
        self.assertEqual(len(review_paths), 9)
        fixture.activate_planveyor(
            (*merge_paths, *review_paths),
            overrides={
                "docs/_meta/review_range_policy.v1.json": self._review_range_policy_bytes(
                    "initial local scope note"
                ),
                **self._target_visual_lane_sources(),
            },
        )
        write(fixture.runtime_root, "docs/smoke_visual.md", "RUNTIME_DECOY\n")
        write(fixture.runtime_root, "docs/testing_runbook.md", "RUNTIME_DECOY\n")
        for script_name in ("run_visual_check.sh", "review_visual_design_audit.sh"):
            write(
                fixture.target_root,
                f"scripts/{script_name}",
                "#!/bin/sh\n",
                executable=True,
            )
        current_scope_note = "current target-local scope note"
        write(
            fixture.target_root,
            "docs/_meta/review_range_policy.v1.json",
            self._review_range_policy_bytes(current_scope_note),
        )
        return current_scope_note

    @staticmethod
    def _write(root: Path, rel_path: str, body: str) -> Path:
        return write(root, rel_path, body)

    def _materialize_runtime_ui_range(
        self,
        root: Path,
        *,
        extra_changed_paths: int = 0,
    ) -> tuple[str, str]:
        base = git(root, "rev-parse", "HEAD")
        write(root, "templates/runtime/page.html", "<main>runtime UI</main>\n")
        for index in range(extra_changed_paths):
            write(root, f"templates/runtime/generated_{index:04d}.html", "<main>fixture</main>\n")
        git(root, "add", "--", "templates/runtime")
        git(root, "commit", "--quiet", "-m", "runtime UI range")
        return base, git(root, "rev-parse", "HEAD")

    def _run_producer(self, fixture: AuthorityFixture, base: str, head: str) -> str:
        environment = fixture.environment()
        environment["PYBIN"] = str(Path(sys.executable).resolve())
        environment["PLANVEYOR_RUNTIME_SOURCE_KIND"] = "git"
        facade = shlex.quote(str(fixture.runtime_root / "scripts" / "planveyor.zsh"))
        program = (
            fixture.shell_loader()
            + f"\nplanveyor_source_runtime {facade} || exit $?;\n"
            + f"planveyor_review_range_init {shlex.quote(base)} {shlex.quote(head)} 0\n"
        )
        result = subprocess.run(
            ["/bin/zsh", "-dfc", program],
            cwd=fixture.target_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def _write_review(self, root: Path, plan_rel: str, review_rel: str, target: str) -> None:
        tick = chr(96)
        self._write(
            root,
            review_rel,
            dedent(
                f"""\
                # Код-ревью - runtime UI range

                **Schema version:** review.v1
                **Date:** 2026-07-22 23:00 MSK
                **Target:** {target}
                **Spec:** {plan_rel}
                **Status:** ✅ OK

                ОК: code lanes green; visual evidence is read independently.

                ## reviewer_code_risk
                - Lane status: {tick}no_findings{tick}
                - Target snapshot: {tick}{target}{tick}

                ## reviewer_code_contracts
                - Lane status: {tick}complete{tick}
                - Target snapshot: {tick}{target}{tick}

                ## Lane synthesis / aggregate verdict
                - Aggregate status: {tick}✅ OK{tick}
                - source_lane: {tick}reviewer_code_risk+reviewer_code_contracts+reviewer_visual{tick}
                - lane_finding_id: {tick}N/A (no lane findings){tick}
                - synthesis_disposition: {tick}no_findings{tick}
                - canonical_ref: {tick}{review_rel}#Lane-synthesis--aggregate-verdict{tick}
                - audit_status: {tick}pending_post_merge_audit{tick}
                - followup_plan: {tick}N/A{tick}

                ## S1 Blocker
                N/A (why=no live blockers).

                ## Визуальные доказательства
                - Runtime UI visual evidence state: {tick}red{tick}
                - Comparator command: {tick}pending{tick}
                - Comparator result: {tick}blocked{tick}
                """
            ),
        )

    def _green_review(
        self,
        root: Path,
        review_rel: str,
        contract: dict[str, object],
    ) -> None:
        review_stem = Path(review_rel).stem
        assets: dict[str, str] = {}
        mandatory_modes = contract["mandatory_modes"]
        index_paths = contract["human_index_paths_by_mode"]
        commands = contract["human_commands_by_mode"]
        self.assertIsInstance(mandatory_modes, list)
        self.assertIsInstance(index_paths, dict)
        self.assertIsInstance(commands, dict)
        for mode in mandatory_modes:
            self.assertIsInstance(mode, str)
            rel = f"docs/code_reviews/assets/{review_stem}/{mode}.png"
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(f"{mode}-proof".encode())
            assets[mode] = rel

        tick = chr(96)
        review = root / review_rel
        prefix = review.read_text(encoding="utf-8").split("## Визуальные доказательства", 1)[0]
        rows = [
            "## Визуальные доказательства",
            f"- Runtime UI visual evidence state: {tick}green{tick}",
            f"- Comparator command: {tick}{contract['comparator_command']}{tick}",
            f"- Comparator claim: {tick}mechanical{tick}",
            f"- Comparator result: {tick}pass{tick}",
            f"- Capture status: {tick}complete{tick}",
            f"- Complete index inspected: {tick}yes{tick}",
            f"- Design verdict: {tick}no_findings{tick}",
            f"- Finding dispositions: {tick}N/A{tick}",
            "- Mandatory modes: " + tick + ", ".join(mandatory_modes) + tick,
        ]
        for mode in mandatory_modes:
            rows.append(f"- Human index ({mode}): {tick}{index_paths[mode]}{tick}")
            rows.append(f"- Durable asset ({mode}): {tick}{assets[mode]}{tick}")
        review.write_text(prefix + "\n".join(rows) + "\n", encoding="utf-8")

    def _append_risk_lane(self, root: Path, plan_rel: str, target: str) -> None:
        fence = chr(96) * 3
        payload = {
            "lane_id": "reviewer_code_risk",
            "run_id": "reviewer_code_risk-flow",
            "target_snapshot": target,
            "lane_status": "no_findings",
            "current": True,
            "written_at": "2026-07-22T23:00:00Z",
        }
        plan = root / plan_rel
        plan.write_text(
            plan.read_text(encoding="utf-8")
            + f"\n## Integration risk lane\n\n{fence}json\n"
            + json.dumps(payload, indent=2, sort_keys=True)
            + f"\n{fence}\n",
            encoding="utf-8",
        )

    def _write_audit(self, root: Path, audit_rel: str, review_rel: str) -> None:
        tick = chr(96)
        self._write(
            root,
            audit_rel,
            dedent(
                f"""\
                # Review: Post-merge audit - runtime UI

                **Status:** ✅ Done
                **Schema version:** review.v1

                ## Audit matrix (summary)
                ### A1) Runtime UI evidence
                - Lane synthesis source: {tick}{review_rel}#Lane synthesis / aggregate verdict{tick}
                - source_lane: {tick}synthesized{tick}
                - lane_finding_id: {tick}N/A (no lane findings){tick}
                - synthesis_disposition: {tick}no_findings{tick}
                - canonical_ref: {tick}{review_rel}#Lane-synthesis--aggregate-verdict{tick}
                - audit_status: {tick}done{tick}
                - followup_plan: {tick}N/A{tick}
                - Blocker refs: {tick}N/A (no live blocker lineage){tick}
                - Status: ✅ Done
                """
            ),
        )

    def _write_truth_hosts(self, root: Path, audit_rel: str) -> dict[str, Path]:
        tick = chr(96)
        fence = tick * 3
        return {
            "post_merge_audit": root / audit_rel,
            "operational_receipt": self._write(
                root,
                "docs/reviews/operational.md",
                "# Receipt\n\n**Status:** ✅ Done\n\n"
                f"{tick}post_merge_operational_receipt.v1{tick}\n",
            ),
            "ready_to_push_closeout": self._write(
                root,
                "docs/reviews/ready.md",
                "# Closeout\n\n**Status:** ✅ Done\n\n"
                f"{tick}ready_to_push_closeout_receipt.v1{tick}\n",
            ),
            "packetization_report": self._write(
                root,
                "docs/reviews/packetization.md",
                f'# Packetization\n\n**Status:** Done\n\n{fence}json\n'
                '{"packetization_gate":{"schema_version":"packetization_gate.v1","blocking_count":0}}\n'
                f"{fence}\n",
            ),
        }

    def test_raw_legacy_runtime_ui_has_no_declared_lane(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            base, head = self._materialize_runtime_ui_range(fixture.target_root)
            legacy = self._run_probe(fixture, "legacy", {"base": base, "head": head})
            self.assertEqual(legacy["availability_state"], "not_applicable")
            self.assertEqual(legacy["runtime_ui_kind"], "web")
            self.assertEqual(legacy["reason"], "no_declared_runtime_visual_lane:default")
            self.assertIn("templates/runtime/page.html", legacy["runtime_ui_paths"])
            self.assertEqual(legacy["mandatory_modes"], [])
            self.assertEqual(legacy["comparator_command"], "")
            self.assertEqual(legacy["contract_errors"], [])

    def test_full_red_green_route(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            current_scope_note = self._activate_engaged_fixture(fixture)
            root = fixture.target_root
            base, head = self._materialize_runtime_ui_range(root, extra_changed_paths=940)
            self.assertIn(
                "?? docs/_meta/planveyor_contract_authority.v1.json",
                git(root, "status", "--short").splitlines(),
            )

            plan_rel = self._run_producer(fixture, base, head)
            materialized = self._run_probe(
                fixture,
                "materialized",
                {"plan_rel": plan_rel, "expected_scope_note": current_scope_note},
            )
            self.assertEqual(materialized["plan_contract_errors"], [])
            self.assertEqual(materialized["draft_contract_errors"], [])
            self.assertTrue(materialized["contracts_equal"])
            contract = materialized["contract"]
            self.assertIsInstance(contract, dict)
            self.assertEqual(contract["availability_state"], "available")
            self.assertGreater(len(contract["changed_path_evidence"]), 120)
            self.assertTrue(materialized["plan_has_ref"])
            self.assertTrue(materialized["plan_has_target_scope_note"])
            self.assertFalse(materialized["draft_has_target_scope_note"])
            self.assertFalse(materialized["plan_has_initial_scope_note"])
            self.assertFalse(materialized["draft_has_initial_scope_note"])
            self.assertFalse(materialized["plan_has_runtime_decoy"])
            self.assertFalse(materialized["draft_has_runtime_decoy"])
            self.assertEqual(materialized["lint_codes"], [])
            self.assertTrue(
                all(
                    f"--plan {plan_rel}" in command and "<plan>" not in command
                    for command in contract["human_commands_by_mode"].values()
                )
            )

            review_rel = f"docs/code_reviews/{Path(plan_rel).stem}.md"
            target = f"RANGE={base}..{head} (EXCLUDE_DOCS=0)"
            self._write_review(root, plan_rel, review_rel, target)
            self._append_risk_lane(root, plan_rel, target)
            audit_rel = f"docs/reviews/260722_2300_post_merge_audit_range_{base[:7]}_{head[:7]}.md"
            self._write_audit(root, audit_rel, review_rel)
            self._write(root, ".planveyor.range.base", base + "\n")
            self._write(root, ".planveyor.range.head", head + "\n")
            headers = self._run_probe(fixture, "tracker_headers", {})
            tracker = self._write(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    f"""\
                    # Merge tracker
                    BASE={base}
                    HEAD={head}
                    RANGE={base}..{head}
                    RANGE_ID=range_{base[:7]}_{head[:7]}
                    POLICY_SCHEMA={headers["POLICY_SCHEMA"]}
                    POLICY_SHA256={headers["POLICY_SHA256"]}
                    AUTHORITY_GENERATION={headers["AUTHORITY_GENERATION"]}
                    ## Checklist
                    - [x] step:review_range
                    - [x] step:post_merge_audit
                    - [ ] step:ready_to_push
                    """
                ),
            )
            hosts = {
                "review_artifact": review_rel,
                **{
                    name: str(path.relative_to(root))
                    for name, path in self._write_truth_hosts(root, audit_rel).items()
                },
            }
            evidence_request = {
                "review_rel": review_rel,
                "audit_rel": audit_rel,
                "tracker_rel": str(tracker.relative_to(root)),
                "range_ref": f"{base}..{head}",
                "risk_rel": "docs/reviews/risk.md",
                "host_paths": hosts,
            }

            red = self._run_probe(fixture, "evidence", evidence_request)
            self.assertEqual(red["visual_state"], "red")
            self.assertIn(
                "audit_status_done_conflicts_with_visual_evidence",
                red["authority_codes"],
            )
            self.assertEqual(red["report_state"], "blocked")
            self.assertIn(
                "post_merge_audit_authority_blocked",
                red["preflight_codes"],
            )
            self.assertTrue(red["packet_is_none"])
            self.assertEqual(red["packet_error_codes"], ["runtime_ui_visual_evidence_red"])

            self._green_review(root, review_rel, contract)
            green = self._run_probe(fixture, "evidence", evidence_request)
            self.assertEqual(green["visual_state"], "green", green["visual_reason_codes"])
            self.assertEqual(green["authority_codes"], [])
            self.assertEqual(green["report_state"], "green")
            self.assertNotIn(
                "post_merge_audit_authority_blocked",
                green["preflight_codes"],
            )
            self.assertFalse(green["packet_is_none"])
            self.assertEqual(green["packet_error_codes"], [])
            self.assertEqual(green["packet_visual_status"], "green")

            git(
                root,
                "add",
                "--",
                ".planveyor.range.base",
                ".planveyor.range.head",
                ".planveyor.merge_tracker.md",
                "docs/plans",
                "docs/code_drafts",
                "docs/code_reviews",
                "docs/reviews",
            )
            git(root, "commit", "--quiet", "-m", "green closeout fixture")
            self.assertIn(
                "?? docs/_meta/planveyor_contract_authority.v1.json",
                git(root, "status", "--short").splitlines(),
            )
            ready = self._run_probe(
                fixture,
                "ready",
                {
                    "tracker_rel": str(tracker.relative_to(root)),
                    "range_ref": f"{base}..{head}",
                    "base_short": base[:7],
                    "head_short": head[:7],
                },
            )
            self.assertEqual(ready["status"], "ok", ready)
            self.assertEqual(ready["action"], "already_closed", ready)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import censor_receipts_harvest as HARVEST


class CensorPromptContractTest(unittest.TestCase):
    def test_censor_prompts_name_machine_readback_labels(self) -> None:
        prompt_paths = (
            ROOT / "docs" / "tools" / "prompts" / "architect_censor.md",
            ROOT / "docs" / "tools" / "prompts" / "planner_censor.md",
            ROOT / "docs" / "tools" / "prompts" / "coder_censor.md",
        )
        exact_labels = (
            "Second opinion",
            "Context reconciliation",
            "Counterfactuals considered",
            "Fixes",
            "Artifacts opened",
            "Review verdict seen",
            "Blocker IDs considered",
            "Role-owned finding",
            "Reconciliation",
            "Final censor verdict",
        )
        for prompt_path in prompt_paths:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                role = prompt_path.stem.split("_", 1)[0].title()
                self.assertIn("Machine-readback labels", text)
                self.assertIn("colon required", text)
                self.assertIn("`Addendum (new angle)` (или `Addendum`)", text)
                for label in exact_labels:
                    self.assertIn(f"- `{label}`", text)
                self.assertIn("`Fixes` обязателен всегда", text)
                self.assertIn("Fixes: none (NO FINDINGS; no plan/status changes required)", text)
                self.assertIn("same-role/same-status", text)
                self.assertIn("current=true", text)
                self.assertIn(f"({role} CENSOR)", text)
                self.assertIn("reserved only for actual helper-readable `## Evidence` receipt rows", text)
                self.assertIn("censor_receipts_harvest.py", text)

    def test_route_accepted_stale_live_wording_guard_is_pinned(self) -> None:
        required_by_file = {
            ROOT / "docs" / "tools" / "prompts" / "planner_censor.md": (
                "route-accepted stale live wording audit",
                "Done-plan fixtures must cover stale current `## Promoted route artifact`",
            ),
            ROOT / "docs" / "tools" / "prompts" / "coder_censor.md": (
                "stale live wording audit before `Ready for Review`",
                "Done-plan fixtures should include current `## Promoted route artifact`",
            ),
            ROOT / "docs" / "tools" / "prompts" / "planner_status_driven.md": (
                "stale live wording scan",
                "Done-plan fixtures для этого guard",
            ),
            ROOT / "docs" / "code_drafts" / "_template.md": (
                "quarantine stale live wording to `historical evidence`",
                "Done-plan fixtures should cover stale current `## Promoted route artifact`",
            ),
        }
        common_terms = (
            "route acceptance",
            "exact target refresh",
            "state-token",
            "historical evidence",
            "historical anchor only",
            "routing/handoff `N/A` reason text",
        )
        stale_examples = (
            "until route acceptance",
            "not accepted yet",
            "old bundle path count",
            "mixed underscore/hyphen state-token spelling",
        )
        for path, local_terms in required_by_file.items():
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                for term in (*common_terms, *stale_examples, *local_terms):
                    self.assertIn(term, text)

    def test_coder_prompts_require_ac_to_test_checklist(self) -> None:
        canonical_outcomes = (
            "AC-to-test checklist",
            "explicit assertion",
            "existing proof",
            "N/A (why=...)",
            "reroute",
        )
        prompt_paths = (
            ROOT / "docs" / "tools" / "prompts" / "coder_status_driven.md",
            ROOT / "docs" / "tools" / "prompts" / "coder_censor.md",
        )
        for prompt_path in prompt_paths:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                for literal in canonical_outcomes:
                    self.assertIn(literal, text)
        # durable role-doc pointer (durable reference, not authoritative prompt)
        role_doc = (ROOT / "docs" / "roles" / "coder.md").read_text(encoding="utf-8")
        self.assertIn("AC-to-test checklist", role_doc)

    def test_decomposition_candidate_only_materialization_contract_is_role_parity(self) -> None:
        required_by_file = {
            ROOT / "docs" / "plans" / "README.md": (
                "Candidate-only materialization corridor",
                "Planner finalize -> Ready for Coder",
                "files-first, linkage-second",
                "Ready for Review",
            ),
            ROOT / "docs" / "playbooks" / "decomposition_wave.md": (
                "Candidate-only materialization corridor",
                "strict structural absence",
                "Ready for Planner",
                "Ready for Review",
            ),
            ROOT / "docs" / "roles" / "planner.md": (
                "candidate-only pack",
                "Planner finalize -> Ready for Coder",
                "same-contract reroute",
            ),
            ROOT / "docs" / "roles" / "coder.md": (
                "candidate-only handoff",
                "files-first, linkage-second",
                "Ready for Planner",
                "Ready for Review",
            ),
            ROOT / "docs" / "tools" / "prompts" / "planner_status_driven.md": (
                "complete candidate-only pack",
                "Planner finalize -> Ready for Coder",
                "strict structural-absence",
            ),
            ROOT / "docs" / "tools" / "prompts" / "coder_status_driven.md": (
                "candidate-only materialization lane",
                "files-first, linkage-second",
                "Ready for Planner",
                "Ready for Review",
            ),
        }
        for path, required_literals in required_by_file.items():
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                for literal in required_literals:
                    self.assertIn(literal, text)

    def test_strict_na_parent_no_draft_contract_is_thirteen_surface_parity(self) -> None:
        required_by_file = {
            ROOT / "docs" / "adr" / "004-exact-bundle-truth-and-closeout.md",
            ROOT / "docs" / "plans" / "README.md",
            ROOT / "docs" / "plans" / "_template.md",
            ROOT / "docs" / "playbooks" / "decomposition_wave.md",
            ROOT / "docs" / "roles" / "architect.md",
            ROOT / "docs" / "roles" / "planner.md",
            ROOT / "docs" / "roles" / "coder.md",
            ROOT / "docs" / "roles" / "reviewer.md",
            ROOT / "docs" / "tools" / "prompts" / "architect_status_driven.md",
            ROOT / "docs" / "tools" / "prompts" / "planner_status_driven.md",
            ROOT / "docs" / "tools" / "prompts" / "planner_censor.md",
            ROOT / "docs" / "tools" / "prompts" / "coder_status_driven.md",
            ROOT / "docs" / "tools" / "prompts" / "reviewer_status_driven.md",
        }
        self.assertEqual(len(required_by_file), 13)
        required_literals = (
            "Strict N-A parent",
            "not_required",
            "inspection-only",
            "files-first materialization",
            "derived parent planning bundle",
            "literal review assets",
            "no recursive child-target import",
            "active-to-parked child-path continuity",
            "no fabricated parent draft",
        )
        for path in required_by_file:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                for literal in required_literals:
                    self.assertIn(literal, text)

    def test_architect_censor_consumes_machine_authority_helper_without_writing_core(self) -> None:
        text = (ROOT / "docs" / "tools" / "prompts" / "architect_censor.md").read_text(encoding="utf-8")
        helper = '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_status_oracle.py "$PLAN_PATH" --json'
        required_fields = (
            "machine_authority_decision_state",
            "machine_authority_decision_reason",
            "machine_authority_decision_id",
            "machine_authority_decision_route",
            "machine_authority_decision_carrier_sha256",
            "machine_authority_decision_confirmation_state",
        )
        self.assertIn(helper, text)
        for field in required_fields:
            self.assertIn(field, text)
        self.assertIn("plus no admission route guard", text)
        self.assertIn("Do not parse/rewrite the semantic core or draft ref", text)
        self.assertIn("missing/unknown/red is a\n  FAIL routed to Architect", text)
        self.assertIn("separately admitted bounded-grammar V2", text)
        self.assertIn("`grammar_contour_id`", text)
        self.assertIn("Do not write/reparse a V2 resolution", text)
        self.assertIn("V2 `stop` or a second contour permit is FAIL", text)

    def test_native_censors_require_distinct_manager_dispatch(self) -> None:
        cases = (
            (
                "architect",
                "Architect",
                "planveyor_arch_censor",
                "architect_censor",
                ("Architect draft", "Architect draft", "Ready for Planner", "Ready for Planner"),
            ),
            (
                "planner",
                "Planner",
                "planveyor_planner_censor",
                "planner_censor",
                ("Ready for Coder", "Ready for Coder"),
            ),
            (
                "coder",
                "Coder",
                "planveyor_coder_censor",
                "coder_censor",
                ("Ready for Review", "Ready for Review"),
            ),
        )
        for role, display_role, wrapper, role_key, expected_handoff_statuses in cases:
            with self.subTest(role=role):
                role_text = (ROOT / "docs" / "roles" / f"{role}.md").read_text(encoding="utf-8")
                status_text = (
                    ROOT / "docs" / "tools" / "prompts" / f"{role}_status_driven.md"
                ).read_text(encoding="utf-8")
                censor_text = (
                    ROOT / "docs" / "tools" / "prompts" / f"{role}_censor.md"
                ).read_text(encoding="utf-8")

                for text in (role_text, status_text):
                    self.assertIn(f"status-driven {display_role}", text)
                    self.assertIn(wrapper, text)
                    self.assertIn(f"planveyor_role_run {role_key}", text)
                    self.assertIn("не читает", text)
                    self.assertIn(f"не добавляет `({display_role} CENSOR)` receipt", text)
                    self.assertIn("`followup_task`", text)
                    self.assertNotIn("send_input", text)
                    self.assertIn("primary role wait", text)

                self.assertIn("Manager `followup_task`", censor_text)
                self.assertNotIn("send_input", censor_text)
                self.assertIn("CENSOR_DISPATCH_ID", censor_text)
                self.assertIn("exact field `Censor dispatch id: <value>`", censor_text)
                self.assertIn("No material delta since previous CENSOR", censor_text)
                self.assertIn("в applicable OK/FAIL ветке добавляет ровно одну fresh", censor_text)
                self.assertIn("Ранний canonical `needs_owner` до verdict завершается без receipt/handoff", censor_text)
                self.assertIn("custom/manual flow", censor_text)
                self.assertIn("header marker `current=true`", censor_text)
                recipe_pattern = re.compile(
                    rf"\({display_role} CENSOR\) (?:OK|FAIL):[^\n]*?"
                    r"Censor dispatch id: <exact supplied value>\."
                )
                recipes = [match.group(0) for match in recipe_pattern.finditer(censor_text)]
                self.assertEqual(len(recipes), len(expected_handoff_statuses), recipes)
                parsed_statuses = []
                for recipe in recipes:
                    materialized = "- " + recipe.replace(
                        "<exact supplied value>",
                        f"censor:{role}:fixture",
                    )
                    self.assertTrue(HARVEST._has_censor_current_marker(materialized), materialized)
                    self.assertEqual(
                        HARVEST._extract_censor_dispatch_id(materialized),
                        f"censor:{role}:fixture",
                    )
                    parsed_status = HARVEST._extract_censor_handoff_status(materialized)
                    self.assertIsNotNone(parsed_status, materialized)
                    parsed_statuses.append(parsed_status)
                self.assertEqual(sorted(parsed_statuses), sorted(expected_handoff_statuses))

        manager_role = (ROOT / "docs" / "roles" / "manager.md").read_text(encoding="utf-8")
        plans_readme = (ROOT / "docs" / "plans" / "README.md").read_text(encoding="utf-8")
        for text in (manager_role, plans_readme):
            self.assertIn("legacy/custom/manual no-selector", text)
            self.assertIn("CENSOR_DISPATCH_ID", text)
            self.assertIn("planveyor_q_small_slice_json", text)
            self.assertIn("role-authored hint", text)

    def test_supplied_dispatch_self_check_and_canonical_grammar_are_role_parity(self) -> None:
        expected = {
            "architect_censor.md": ("Architect", ("Architect draft", "Ready for Planner")),
            "planner_censor.md": ("Planner", ("Ready for Coder",)),
            "coder_censor.md": ("Coder", ("Ready for Review",)),
        }
        for prompt_name, (role, handoff_statuses) in expected.items():
            with self.subTest(prompt=prompt_name):
                text = (
                    ROOT / "docs" / "tools" / "prompts" / prompt_name
                ).read_text(encoding="utf-8")
                self.assertIn("Mandatory supplied-ID post-write self-check", text)
                self.assertIn('planveyor_runtime_py censor_receipts_harvest.py --plan "$PLAN_PATH"', text)
                self.assertIn(f"--censor-role {role}", text)
                self.assertIn('--censor-dispatch-id "$CENSOR_DISPATCH_ID"', text)
                self.assertIn("censor_evidence_lint.state=complete", text)
                self.assertIn("no-selector self-check", text)
                self.assertIn("ровно один raw `Censor dispatch id: <exact supplied value>.`", text)
                self.assertIn("ровно одну `Observations:` boundary", text)
                self.assertIn("env-style `CENSOR_DISPATCH_ID=...`", text)
                self.assertIn("Markdown-backticks", text)
                self.assertIn("No material semantic delta; provenance correction only", text)
                for handoff_status in handoff_statuses:
                    command = (
                        '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py censor_receipts_harvest.py --plan "$PLAN_PATH" '
                        f"--censor-role {role} --handoff-status \"{handoff_status}\" "
                        '--censor-dispatch-id "$CENSOR_DISPATCH_ID" --format json'
                    )
                    self.assertIn(command, text)

    def test_copier_censor_prompts_deliver_the_shared_final_readback_contract(self) -> None:
        for role in ("architect", "planner", "coder"):
            with self.subTest(role=role):
                relative = Path("docs/tools/prompts") / (role + "_censor.md")
                self.assertEqual((ROOT / "copier_template" / relative).read_bytes(),
                                 (ROOT / relative).read_bytes())

    def test_final_readback_instruction_controls_are_explicit(self) -> None:
        from test_plan_lint import MODULE as PLAN_LINT

        for role in ("architect", "planner", "coder"):
            with self.subTest(role=role):
                prompt = (ROOT / "docs/tools/prompts" / (role + "_censor.md")).read_text()
                recipe = prompt.split("Final report and final readback", 1)[1].split(
                    "Mandatory supplied-ID post-write self-check:", 1)[0]
                for token in PLAN_LINT.SCOPE_ROUTE_CLASSIFICATION_TOKENS:
                    self.assertIn(token, recipe)
                for instruction in ('planveyor_runtime_py plan_lint.py "$PLAN_PATH"',
                    "В ТОЙ ЖЕ СТРОКЕ", "Сразу следующей строкой", "same-role/current-handoff",
                    "machine-visible blocker", "nonmatching", "отсутствием role/status", "БЕЗ суффикса CENSOR",
                    "до verdict", "каноническом `## Q&A log`", "после последней записи"):
                    self.assertIn(instruction, recipe)
                self.assertIn("запрет same-ID repair", recipe)
                self.assertIn("FAIL/rollback остаётся отказом", recipe)
                applicable = prompt.split("STATUS BLOCKS:", 1)[1].split("NOT_APPLICABLE]", 1)[0]
                self.assertNotIn("остановись", applicable.lower())
                self.assertIn("post-write lint и финальный exact readback", applicable)
        architect = (ROOT / "docs/tools/prompts/architect_censor.md").read_text()
        self.assertIn("без перехода к нижней OK/FAIL записи", architect)
        self.assertIn("Иначе, только если чеклист выполнен", architect)

    def test_final_report_lint_and_exact_readback_for_every_handoff(self) -> None:
        from test_plan_lint import MODULE as PLAN_LINT, PlanLintReviewRouteDeterminismTests
        from test_censor_receipts_harvest import _complete_censor_row

        PLAN_LINT.load_and_apply_plan_vocab(ROOT / "docs/_meta/plan_vocab.json")
        recipe = None
        cases = (("Architect", "Architect draft"), ("Architect", "Ready for Planner"),
                 ("Planner", "Ready for Coder"), ("Coder", "Ready for Review"))
        for role, status in cases:
            with self.subTest(role=role, status=status), tempfile.TemporaryDirectory() as temporary:
                prompt = (ROOT / "docs/tools/prompts" / (role.lower() + "_censor.md")).read_text()
                current_recipe = prompt.split("Final report and final readback", 1)[1].split(
                    "Mandatory supplied-ID post-write self-check:", 1)[0]
                if recipe is None:
                    recipe = current_recipe
                self.assertEqual(current_recipe, recipe)

                root = Path(temporary)
                stem = "261006_1200_censor_route_fixture"
                plan = PlanLintReviewRouteDeterminismTests()._write_fixture(
                    root, plan_stem=stem, plan_status=status, target_paths=["scripts/plan_lint.py"],
                    review_artifact_lines=[f"- Code review (primary): `docs/code_reviews/{stem}.md`"],
                    complete=True)
                target = root / "scripts/plan_lint.py"
                target.parent.mkdir()
                target.write_text("# Disposable unchanged fixture target.\n")
                base = plan.read_text()
                anchor = "- [2026-03-25 20:20 MSK] (Planner) Fixture materialized."
                self.assertEqual(base.count(anchor), 1)
                self.assertEqual(PLAN_LINT.lint_plan(plan), [])
                dispatch = "censor:" + role.lower() + ":fixture-lint"
                ambiguous = _complete_censor_row(role, status, censor_dispatch_id=dispatch).replace(
                    "Fixes: none.", "Fixes: none; no scope expansion.")

                def write_rows(rows):
                    plan.write_text(base.replace(anchor, anchor + "\n" + rows))

                def exact(selected_id=dispatch):
                    payload, rc = HARVEST.build_payload(str(plan), [], role, status, selected_id)
                    self.assertEqual(rc, 0)
                    return payload["censor_evidence_lint"]

                # Pre-write lint cannot validate wording introduced by receipt.
                write_rows(ambiguous)
                findings = PLAN_LINT.lint_plan(plan)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "ERROR")
                self.assertIn("Ambiguous scope/follow-up routing", findings[0].message)
                self.assertEqual(exact()["state"], "complete")

                # Unsafe repair controls: the lint window accepts a nearby
                # class without matching provenance. The prompt must forbid it.
                other_role = "Planner" if role == "Coder" else "Coder"
                masks = ("- [2026-10-06 01:01 +0300] Classification: same-contract reroute.",
                         f"- [2026-10-06 01:01 +0300] ({role}) Classification: same-contract reroute.",
                         f"- [2026-10-06 01:01 +0300] ({other_role}) {status}: same-contract reroute.")
                for mask in masks:
                    with self.subTest(unsafe_nonmatching_mask=mask):
                        write_rows(ambiguous + "\n" + mask)
                        self.assertEqual(PLAN_LINT.lint_plan(plan), [])
                        self.assertEqual(exact()["state"], "complete")
                        self.assertIn(ambiguous, plan.read_text())

                # Reproduce the incident: lint turns green after a same-role
                # append, but a previously green supplied-ID readback is stale.
                late = (f"- [2026-10-06 01:01 +0300] ({role}) Routing clarification for {status}: "
                        "same-contract reroute.")
                write_rows(ambiguous + "\n" + late)
                self.assertEqual(PLAN_LINT.lint_plan(plan), [])
                stale = exact()
                self.assertEqual(stale["state"], "incomplete")
                self.assertEqual(stale["reason_code"], "missing_current_receipt")
                self.assertIn("stale_current_receipt_after_later_matching_event", stale["invalid_reasons"])

                # Existing separate replacement: only a distinct supplied ID,
                # after the adjacent truthful repair, can become current green.
                replacement_id = "censor:" + role.lower() + ":fixture-replacement"
                replacement = _complete_censor_row(role, status, timestamp="02:03",
                    censor_dispatch_id=replacement_id).replace("Fixes: none.",
                    "Fixes: none; no scope expansion; route class: same-contract reroute.")
                write_rows(ambiguous + "\n" + late + "\n" + replacement)
                self.assertEqual(PLAN_LINT.lint_plan(plan), [])
                self.assertEqual(exact(replacement_id)["state"], "complete")
                self.assertEqual(exact()["state"], "incomplete")
                self.assertIn(ambiguous, plan.read_text())

                # A distant replacement cannot repair an old local lint error.
                padding = "\n".join(f"- [2026-10-06 01:02 +0300] Supporting fact {i}." for i in range(6))
                write_rows(ambiguous + "\n" + padding + "\n" + replacement)
                self.assertEqual(exact(replacement_id)["state"], "complete")
                distant = PLAN_LINT.lint_plan(plan)
                self.assertEqual(len(distant), 1)
                self.assertIn("Ambiguous scope/follow-up routing", distant[0].message)

                # Leave the original failed project with its stale original ID.
                write_rows(ambiguous + "\n" + late)
                self.assertEqual(exact()["state"], "incomplete")

                # A separate disposable project models a clean report; the
                # failed project/receipt above remains intact, not same-ID repair.
                correct = ambiguous.replace("Fixes: none; no scope expansion.",
                    "Fixes: none; no scope expansion; route class: same-contract reroute.")
                with tempfile.TemporaryDirectory() as clean_temporary:
                    clean_root = Path(clean_temporary)
                    clean_plan = PlanLintReviewRouteDeterminismTests()._write_fixture(
                        clean_root, plan_stem=stem, plan_status=status,
                        target_paths=["scripts/plan_lint.py"],
                        review_artifact_lines=[f"- Code review (primary): `docs/code_reviews/{stem}.md`"],
                        complete=True)
                    clean_target = clean_root / "scripts/plan_lint.py"
                    clean_target.parent.mkdir()
                    clean_target.write_text("# Disposable unchanged fixture target.\n")
                    clean_plan.write_text(clean_plan.read_text().replace(anchor, anchor + "\n" + correct))
                    self.assertEqual(PLAN_LINT.lint_plan(clean_plan), [])
                    payload, rc = HARVEST.build_payload(str(clean_plan), [], role, status, dispatch)
                    self.assertEqual(rc, 0)
                    final = payload["censor_evidence_lint"]
                    self.assertEqual(final["state"], "complete")
                    self.assertEqual(final["missing_fields"], [])
                    self.assertEqual(final["invalid_reasons"], [])
                    # A real product edit and an unrelated-role Evidence line
                    # do not blanket-invalidate this exact supplied-ID receipt.
                    clean_target.write_text("# Changed disposable product comment.\n")
                    nonmatching = f"- [2026-10-06 02:04 +0300] ({other_role}) {status}: unrelated supporting fact."
                    clean_plan.write_text(clean_plan.read_text().replace(correct, correct + "\n" + nonmatching))
                    self.assertEqual(PLAN_LINT.lint_plan(clean_plan), [])
                    payload, rc = HARVEST.build_payload(str(clean_plan), [], role, status, dispatch)
                    self.assertEqual(rc, 0)
                    self.assertEqual(payload["censor_evidence_lint"]["state"], "complete")
                self.assertEqual(exact()["state"], "incomplete")

    def test_literal_supplied_dispatch_grammar_incidents_fail_exact_selector(self) -> None:
        dispatch_id = "censor:architect:fixture"
        fields = (
            "Second opinion: FOUND AND FIXED. Addendum (new angle): checked grammar. "
            "Context reconciliation: current handoff checked. Fixes: canonicalized receipt. "
            "Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. "
            "Blocker IDs considered: N/A (why=no live blocker). Role-owned finding: grammar gap. "
            "Reconciliation: no live blocker. Final censor verdict: OK."
        )

        def lint(
            row: str,
            *,
            exact: bool,
            handoff_status: str = "Ready for Planner",
        ) -> dict[str, object]:
            markdown = HARVEST.MarkdownInput(
                kind="plan",
                display_path="fixture.md",
                path=ROOT / "fixture.md",
                text=f"# Plan\n\n## Evidence\n{row}\n",
            )
            return HARVEST.build_censor_evidence_lint(
                markdown,
                role="Architect",
                handoff_status=handoff_status,
                censor_dispatch_id=dispatch_id if exact else None,
            )

        legacy_false_green = (
            "- [2026-07-17 13:11 MSK] (Architect CENSOR) "
            "OK: initial-draft captured; ready to work on Architect draft. "
            f"`CENSOR_DISPATCH_ID={dispatch_id}`. {fields}"
        )
        self.assertNotIn("current=true", legacy_false_green)
        self.assertNotIn("OK: Ready for Planner validated", legacy_false_green)
        self.assertNotIn("Observations:", legacy_false_green)
        self.assertEqual(
            lint(
                legacy_false_green,
                exact=False,
                handoff_status="Architect draft",
            )["state"],
            "complete",
        )
        exact_legacy = lint(
            legacy_false_green,
            exact=True,
            handoff_status="Architect draft",
        )
        self.assertEqual(exact_legacy["state"], "incomplete")
        self.assertEqual(
            exact_legacy["reason_code"],
            "missing_current_receipt",
        )

        duplicate_backticked_missing_boundary = (
            "- [2026-07-21 10:50 MSK] (Architect CENSOR) "
            "OK: Ready for Planner validated; current=true. "
            f"CENSOR_DISPATCH_ID={dispatch_id}. Censor dispatch id: `{dispatch_id}`. {fields}"
        )
        exact_duplicate = lint(duplicate_backticked_missing_boundary, exact=True)
        self.assertEqual(exact_duplicate["state"], "incomplete")
        self.assertIn(
            exact_duplicate["reason_code"],
            {"ambiguous_censor_dispatch_id", "missing_or_mismatched_censor_dispatch_id"},
        )

        canonical = (
            "- [2026-07-21 10:51 MSK] (Architect CENSOR) "
            "OK: Ready for Planner validated; current=true. "
            f"Censor dispatch id: {dispatch_id}. Observations: {fields}"
        )
        exact_canonical = lint(canonical, exact=True)
        self.assertEqual(exact_canonical["state"], "complete")
        self.assertEqual(exact_canonical["reason_code"], "complete_current_receipt")
        self.assertEqual(canonical.count("Censor dispatch id:"), 1)
        self.assertEqual(canonical.count("Observations:"), 1)


if __name__ == "__main__":
    unittest.main()

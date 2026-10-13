import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import plan_status_oracle as PLAN_STATUS_ORACLE

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_PROMPT = ROOT / "docs" / "tools" / "prompts" / "manager_custom_pipeline.md"
COLLAB_PROMPT = ROOT / "docs" / "tools" / "prompts" / "manager_collab_pipeline.md"
ROUTER_PROMPT = ROOT / "docs" / "tools" / "prompts" / "manager_router.md"
ARCHITECT_PROMPT = ROOT / "docs" / "tools" / "prompts" / "architect_status_driven.md"
PLAN_README = ROOT / "docs" / "plans" / "README.md"
ARCHITECT_ROLE = ROOT / "docs" / "roles" / "architect.md"
MANAGER_ROLE = ROOT / "docs" / "roles" / "manager.md"
OWNER_RUNBOOK = ROOT / "docs" / "tools" / "owner_runbook_codex.md"
OWNER_RUNBOOK_RU = ROOT / "docs" / "tools" / "owner_runbook_codex.ru.md"
PROCESS_IMPROVEMENTS_README = ROOT / "docs" / "process_improvements" / "README.md"
PLANNER_PROMPT = ROOT / "docs" / "tools" / "prompts" / "planner_status_driven.md"
CODER_PROMPT = ROOT / "docs" / "tools" / "prompts" / "coder_status_driven.md"
REVIEWER_PROMPT = ROOT / "docs" / "tools" / "prompts" / "reviewer_status_driven.md"
PLAN_QUEUE = ROOT / "scripts" / "plan_queue.py"


class ManagerCustomPipelinePromptContractTest(unittest.TestCase):
    def test_explicit_continuation_routes_to_existing_followups_phase_without_restarting_family(self) -> None:
        prompt = COLLAB_PROMPT.read_text()
        start = prompt.index("2b0) Explicit pre-first-followups continuation")
        bootstrap = prompt.index("2b) Generic ordinary-terminal V2 bootstrap")
        branch = prompt[start:bootstrap]
        self.assertLess(start, bootstrap)
        self.assertLess(bootstrap, prompt.index("3) Выбери, какую роль запускать дальше", bootstrap))
        for marker in ("FOLLOWUPS_CAPTURE_CYCLE_ID", "schema_state=ok", "schema_errors=[]",
                       "followups_continuation_admission.v1", "state=ready", "phase=pre_first_followups",
                       "next_dispatch=Architect:followups", "checkpoint-general-pi", "--docs-closeout-json -",
                       "followup_capture_pi_general_checkpoint_already_published", "fresh capture-aware",
                       "Architect → Coder → Planner → Reviewer", "Не выполняй `begin`, general dispatch или collector replay",
                       "submit-ordinary-v2", "bind-ordinary-v2", "freeze-ordinary-v2",
                       "без automatic retry/new cycle", "external_clean_noop|external_clean", "final_docs_commit=no_op|landed"):
            self.assertIn(marker, branch)
        self.assertLess(branch.index("checkpoint-general-pi"), branch.index("Shared followups phase")
                        if "Shared followups phase" in branch else branch.index("shared followups phase"))
        self.assertIn("Shared followups phase (ordinary full family и admitted explicit continuation 2b0)", prompt)
        self.assertIn("selector отдельным invocation payload field", prompt)
        self.assertIn("При `COMMIT_POLICY=native_existing` whole-tail completion требует `final_docs_commit=no_op|landed`", branch)
        self.assertIn("При `COMMIT_POLICY=human_explicit` и `final_docs_commit=required`", branch)
        self.assertIn("existing shared human preview branch без writer/continuation", branch)
        self.assertIn("незавершённый preview, не whole-tail completion", branch)
        template = ROOT / "copier_template/docs/tools/prompts/manager_collab_pipeline.md"
        self.assertEqual(template.read_bytes(), COLLAB_PROMPT.read_bytes())

    def test_sid_bound_preflight_proof_is_exact_and_never_ambient_authority(self) -> None:
        custom = " ".join(CUSTOM_PROMPT.read_text(encoding="utf-8").split())

        for marker in (
            "Runner selection принадлежит Owner/runtime policy.",
            "preflight возвращает non-green reason/remediation, остановись до child",
            "Один blocking role step получает fresh preflight только для своей invocation.",
            "Green summary, chat prose, cached environment или старый receipt не являются child-start authority.",
            "Runtime проверяет identity, selection и current SID перед запуском; mismatch или drift остаются fail-closed.",
            "Dirty-state ownership и runner-readiness prechecks принадлежат `planveyor_custom_role_step` и выполняются там ровно один раз до child.",
            "`dirty_state_blocked` / `runner_preflight_blocked` означает no-child stop",
        ):
            self.assertIn(marker, custom)

    def test_approval_delivery_readback_is_public_report_only_and_nonsemantic(self) -> None:
        approval_docs = (
            COLLAB_PROMPT,
            ARCHITECT_PROMPT,
            ARCHITECT_ROLE,
            MANAGER_ROLE,
        )
        required_markers = (
            "visible direct closeout helper",
            "not a semantic plan failure",
            "planveyor_entry_doctor",
            "fresh task",
            "unknown_without_session_launch_receipt",
            "current-task hot reload",
            "queue write",
        )
        stale_markers = (
            "approval delivery / bare-shim readback",
            "required_after_write",
            "planveyor_bare_entrypoints_doctor",
        )
        self.assertEqual(len(approval_docs), 4)
        for document in approval_docs:
            with self.subTest(document=document.name):
                text = document.read_text(encoding="utf-8")
                lowered = text.lower()
                for marker in required_markers:
                    self.assertIn(marker, lowered)
                for marker in stale_markers:
                    self.assertNotIn(marker, lowered)

        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        self.assertIn(
            '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project /absolute/path/to/selected-consumer <same command>',
            collab,
        )
        self.assertIn("`/absolute/path/to/selected-consumer` — корень current plan/Manager.", collab)
        self.assertIn("live consumer-configuration mutation", collab)
        self.assertIn("live consumer configuration", MANAGER_ROLE.read_text(encoding="utf-8").lower())

        runbook = OWNER_RUNBOOK.read_text(encoding="utf-8")
        for marker in (
            "child-only facade",
            "Do not source implementation shell files into a parent shell.",
            "Owner chooses the operating mode and any runner available to the installed runtime.",
        ):
            self.assertIn(marker, runbook)
        runbook_ru = OWNER_RUNBOOK_RU.read_text(encoding="utf-8")
        for marker in (
            "фасад, который выполняет команды только в дочернем процессе",
            "Не подключайте shell-скрипты реализации к родительской оболочке через `source`.",
            "Owner выбирает режим работы и любой агентный харнес, который доступен установленной копии Planveyor.",
        ):
            self.assertIn(marker, runbook_ru)

        custom = CUSTOM_PROMPT.read_text(encoding="utf-8")
        self.assertIn(
            '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project /absolute/path/to/selected-consumer '
            'planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json',
            custom,
        )
        for marker in (
            "runner_preflight_blocked",
            "no-child stop",
            "schema_version=role_execution_receipt.v1",
            "matching `target_plan`, `session_key`, `pre_status`, just-returned `run_id`",
        ):
            self.assertIn(marker, custom)

        role_runtime = (ROOT / "scripts" / "planveyor" / "role_runtime.zsh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'preflight_json="$(planveyor_role_runner_preflight "$role_arg" --json 2>/dev/null)" || {',
            role_runtime,
        )
        self.assertIn(
            "_planveyor_custom_role_step_emit blocked runner_preflight_blocked",
            role_runtime,
        )
        preflight_start = role_runtime.index(
            'preflight_json="$(planveyor_role_runner_preflight "$role_arg" --json 2>/dev/null)" || {'
        )
        preflight_block = role_runtime[preflight_start : preflight_start + 600]
        self.assertIn("return 125", preflight_block)

    def test_semantic_role_prompts_emit_scope_expansion_stop_carrier(self) -> None:
        for prompt_path in (
            ARCHITECT_PROMPT,
            PLANNER_PROMPT,
            CODER_PROMPT,
            REVIEWER_PROMPT,
        ):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                evidence_index = text.index("bounded append-only evidence")
                carrier_index = text.index("`plan_meta.scope_expansion`", evidence_index)
                state_index = text.index("`state=reroute_required`", carrier_index)
                status_index = text.index("`**Status:** Ready for Architect response`", state_index)
                stop_index = text.index("немедленно остановись", status_index)

                self.assertLess(evidence_index, carrier_index)
                self.assertLess(carrier_index, state_index)
                self.assertLess(state_index, status_index)
                self.assertLess(status_index, stop_index)
                for field in ("`target_contour`", "`source_ref`", "`reason`"):
                    self.assertIn(field, text[carrier_index:status_index])
                self.assertIn("`same-contract reroute`", text[stop_index:])
                self.assertIn("`de-scoped follow-up`", text[stop_index:])

        architect = ARCHITECT_PROMPT.read_text(encoding="utf-8")
        self.assertIn("`plan_meta.scope_expansion.state=reroute_required`", architect)
        self.assertIn("`state=architect_accepted` только как transition state", architect)
        self.assertIn("`**Status:** Superseded`", architect)
        self.assertIn("верни carrier в `state=n/a`", architect)
        self.assertIn("`architect_accepted` нельзя передавать в Planner/Coder/Reviewer status group", architect)

    def test_external_followups_v2_contract_is_readonly_and_manager_frozen(self) -> None:
        role_prompts = (
            ARCHITECT_PROMPT,
            PLANNER_PROMPT,
            CODER_PROMPT,
            REVIEWER_PROMPT,
        )
        for prompt_path in role_prompts:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                boundary_index = text.index("V2 external follow-up boundary")
                self.assertIn("`plan.v2`", text[boundary_index:])
                self.assertIn("`plan_meta.followups_out`", text[boundary_index:])
                self.assertIn("`scripts/followups_apply.py`", text[boundary_index:])
                self.assertIn("`open + exact proof`", text[boundary_index:])
                self.assertIn("V2", text[boundary_index:])

        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        ordinary_start = collab.index("## Ordinary terminal `plan.v2` compact follow-ups")
        diagnostic_start = collab.index(
            "## V2 external-only terminal follow-ups — diagnostic compatibility",
            ordinary_start,
        )
        ordinary = collab[ordinary_start:diagnostic_start]
        helper = '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_capture.py '
        prepare_index = ordinary.index(helper + "prepare-role")
        submit_index = ordinary.index(helper + "submit-ordinary-v2")
        bind_index = ordinary.index(helper + "bind-ordinary-v2")
        architect_index = ordinary.index("Architect -> Coder -> Planner -> Reviewer")
        freeze_index = ordinary.index("freeze-ordinary-v2")
        writer_index = ordinary.index("scripts/followups_apply.py")
        self.assertLess(prepare_index, submit_index)
        self.assertLess(submit_index, bind_index)
        self.assertLess(bind_index, architect_index)
        self.assertLess(architect_index, freeze_index)
        self.assertLess(freeze_index, writer_index)
        for token in (
            "prepare-role",
            "submit-ordinary-v2",
            "ordinary_v2_role_submission_ack.v1",
            "diagnostic acknowledgement",
            "never pipes returned chat bytes",
            "followups_capture_cycle_id",
            "complete follow-ups baseline",
            "external_clean_noop",
            "`followups_declaration.v2` envelope",
            "generic `freeze-v2`",
        ):
            self.assertIn(token, ordinary)
        self.assertNotIn("finalize-role", ordinary)
        self.assertNotIn("freeze-v2 --input", ordinary)
        self.assertNotIn("bind-ordinary-v2 --input -", ordinary)
        self.assertIn("ordinary_v2_inputs/<Role>.json", ordinary)
        self.assertIn("explicit same-cycle redispatch", ordinary)
        self.assertIn("automatic Manager retry/new begin", ordinary)
        ordinary_submit_lines = [line for line in collab.splitlines() if "submit-ordinary-v2" in line]
        self.assertEqual(len(ordinary_submit_lines), 4)
        for line in ordinary_submit_lines:
            with self.subTest(manager_submit=line[:80]):
                submit_fragment = line.split("submit-ordinary-v2", 1)[1].split("bind-ordinary-v2", 1)[0]
                self.assertIn("--input-current --write", submit_fragment)
                self.assertNotIn("--input -", submit_fragment)

        diagnostic = collab[diagnostic_start:]
        self.assertIn("Public full-envelope `freeze-v2 --input <declarations.json>`", diagnostic)
        self.assertIn("diagnostic compatibility API", diagnostic)
        self.assertIn("never the ordinary Manager happy path", diagnostic)
        self.assertIn("sole durable writer", diagnostic)
        self.assertIn("queue-imported", diagnostic)

        for prompt_path in (
            ("Architect", ROOT / "docs" / "tools" / "prompts" / "architect_docs_finalize_followups.md"),
            ("Planner", ROOT / "docs" / "tools" / "prompts" / "planner_docs_finalize_followups.md"),
            ("Coder", ROOT / "docs" / "tools" / "prompts" / "coder_docs_finalize_followups.md"),
            ("Reviewer", ROOT / "docs" / "tools" / "prompts" / "reviewer_docs_finalize_followups.md"),
        ):
            role, prompt_path = prompt_path
            with self.subTest(finalizer=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                self.assertIn("V2 external-only boundary", text)
                self.assertIn("`followups.v2`", text)
                self.assertIn("`source_ref=<plan_ref>`", text)
                self.assertIn("Human summary не добавляй", text)
                compact_start = text.index("## Ordinary terminal `plan.v2` compact declaration")
                compact = text[compact_start:]
                for token in (
                    "Ровно три ключа",
                    "`role`, `proposed_rows`, `role_no_items_reason`",
                    "`16384` UTF-8 bytes",
                    "`followups_declaration.v2`",
                    "Не создавай durable файл",
                    "sole durable writer",
                    "submit-ordinary-v2",
                    "ordinary_v2_role_submission_ack.v1",
                    "diagnostic acknowledgement",
                    "Не возвращай compact declaration",
                    "bind-ordinary-v2 --submission-current",
                ):
                    self.assertIn(token, compact)
                self.assertIn(f"ordinary_v2_inputs/{role}.json", compact)
                self.assertIn("file-write/edit tool", compact)
                self.assertIn("--input-current --write", compact)
                self.assertIn("same-cycle redispatch", compact)
                self.assertIn("automatic Manager retry/new begin", compact)
                self.assertNotIn("finite stdin", compact)
                for line in compact.splitlines():
                    if "submit-ordinary-v2" in line:
                        self.assertIn("--input-current --write", line)
                        self.assertNotIn("--input -", line)

        readme = (ROOT / "docs" / "plans" / "README.md").read_text(encoding="utf-8")
        for text in (readme,):
            self.assertIn("submit-ordinary-v2", text)
            self.assertIn("ordinary_v2_role_submission_ack.v1", text)
            self.assertIn("bind-ordinary-v2", text)
            self.assertIn("freeze-ordinary-v2", text)
            self.assertIn("external_clean_noop", text)
            self.assertIn("diagnostic", text)
            self.assertIn("compatibility", text)
            self.assertIn("full-envelope `freeze-v2`", text)

        manager = MANAGER_ROLE.read_text(encoding="utf-8")
        for document in (manager, readme):
            with self.subTest(current_transport=document[:24]):
                self.assertIn("ordinary_v2_inputs/<Role>.json", document)
                self.assertIn("--input-current", document)
                self.assertIn("same-cycle redispatch", document)
                self.assertIn("automatic", document)

    def test_ordinary_v2_cli_routes_remain_available(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "followups_capture.py"), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for marker in ("begin", "submit-ordinary-v2", "bind-ordinary-v2", "freeze-ordinary-v2"):
            self.assertIn(marker, result.stdout)

    def test_generic_terminal_v2_bootstrap_is_exact_and_one_family_only(self) -> None:
        temporary_plan = "docs/plans/generic_terminal_bootstrap_fixture.md"
        canonical_manifest_path = (
            ".tmp/followups_capture/generic_terminal_bootstrap_fixture/"
            "v2_frozen_manifest.json"
        )
        source_identity = {
            "plan_ref": temporary_plan,
            "canonical_manifest_path": canonical_manifest_path,
            "source_terminal_commit_oid": "a" * 40,
            "source_plan_blob_oid": "b" * 40,
            "source_plan_sha256": "c" * 64,
        }

        admitted_outer_clause = (
            "      - Единственные admissible outer tuples: (a) `state=completed`, "
            "`followups_reconciliation.state=external_unknown`, "
            "`followups_reconciliation.reason=missing_v2_frozen_manifest`; либо "
            "(b) `state=blocked`, `reason_code=no_cycle_staging_proof_unavailable`, "
            "та же exact reconciliation tuple. В обоих случаях потребуй "
            "helper-derived `followups_bootstrap_admission.v1` с `state=ready`, "
            "`reason=missing_v2_frozen_manifest` и complete exact identity "
            "`plan_ref`, `canonical_manifest_path`, `source_terminal_commit_oid`, "
            "`source_plan_blob_oid`, `source_plan_sha256`."
        )
        family_entry_clause = (
            "      - Только при полном exact tuple сохрани verbatim fresh pre-family "
            "JSON как invocation-local `ORDINARY_V2_BOOTSTRAP_PAYLOAD`, установи "
            "`ORDINARY_V2_BOOTSTRAP_READY=true` и "
            "`docs_closeout_family_entry=ordinary_v2_bootstrap_ready`, затем войди "
            "ровно один раз в shared `full docs-finalize family tail` ниже с уже "
            "зафиксированными `docs_closeout_plan`/`plan_ref`. `begin` получает именно "
            "этот verbatim payload и сам немедленно rederive-ит admission before mutable "
            "cycle publication. Это bypass только pre-family `followups_clean`, не "
            "reconciliation и не terminal success."
        )
        rejected_outer_clause = (
            "      - `state=no_op + ready`, любой иной/missing `blocked.reason_code`, "
            "non-exact reconciliation, missing/malformed/tampered/stale admission or "
            "identity, present/unsafe manifest, active/ambiguous cycle, source drift, "
            "schema drift или unknown outer state не устанавливает local bootstrap flag и "
            "остаётся fail-closed на ordinary rejection path; не создавай "
            "manifest/receipt/row руками и не используй generic `freeze-v2`, retry, "
            "blocked-predecessor recovery или historical fallback. "
            "После full family потребуй existing fresh capture-aware `external_clean_noop|external_clean`, "
            "PI green, schema/capture/ownership proof и отсутствие foreign/protected delta. "
            "При `COMMIT_POLICY=native_existing` whole-tail completion требует `final_docs_commit=no_op|landed`. "
            "При `COMMIT_POLICY=human_explicit` и `final_docs_commit=required` перейди в existing shared human preview branch без writer/continuation; это незавершённый preview, не whole-tail completion. "
            "Clean `no_op|landed` с полным fresh proof завершает tail; никакой receipt не inject-ится в downstream semantic role message."
        )

        def assert_prompt_matrix_is_exclusive(prompt: str) -> tuple[str, str, str]:
            bootstrap_start = prompt.index("2b) Generic ordinary-terminal V2 bootstrap")
            role_choice_index = prompt.index(
                "3) Выбери, какую роль запускать дальше", bootstrap_start
            )
            bootstrap = prompt[bootstrap_start:role_choice_index]
            terminal_closeout_start = prompt.index(
                "Docs-closeout (single-plan + queue; только после terminal semantic closeout):",
                role_choice_index,
            )
            generic_blocked_start = prompt.index(
                "      - Если helper вернул `state=blocked`:",
                terminal_closeout_start,
            )
            downstream_no_op_start = prompt.index(
                "      - Если helper вернул `state=no_op`:",
                generic_blocked_start,
            )
            completed_start = prompt.index(
                "      - Если helper вернул `state=completed`:",
                downstream_no_op_start,
            )
            downstream_no_op_branch = prompt[downstream_no_op_start:completed_start]

            # These byte-exact clauses are the executable prompt grammar.  The
            # payload matrix below is intentionally coupled to this assertion so
            # it cannot prove a broader local model than Manager is instructed
            # to execute.
            self.assertEqual(
                bootstrap.count(admitted_outer_clause),
                1,
                "bootstrap prompt must name exactly the two admitted outer tuples",
            )
            self.assertEqual(
                bootstrap.count(family_entry_clause),
                1,
                "only the exact admitted tuple may enter the shared family",
            )
            self.assertEqual(
                bootstrap.count(rejected_outer_clause),
                1,
                "bootstrap prompt must retain the complete fail-closed complement",
            )
            self.assertEqual(
                bootstrap.count("`state=no_op + ready`"),
                1,
                "a competing no_op bootstrap admission is forbidden",
            )
            self.assertEqual(
                bootstrap.count("`state=no_op"),
                1,
                "no alternate no_op spelling may add a route instruction",
            )
            self.assertEqual(
                bootstrap.count("state=no_op"),
                1,
                "an unquoted no_op route instruction is forbidden too",
            )
            self.assertEqual(
                bootstrap.count("`ORDINARY_V2_BOOTSTRAP_READY=true`"),
                1,
                "only the exact tuple may set the bootstrap flag",
            )
            self.assertEqual(
                bootstrap.count("ORDINARY_V2_BOOTSTRAP_READY=true"),
                1,
                "an unquoted competing bootstrap flag assignment is forbidden too",
            )
            self.assertEqual(
                bootstrap.count("`docs_closeout_family_entry=ordinary_v2_bootstrap_ready`"),
                1,
                "only the exact tuple may select the bootstrap family entry",
            )
            self.assertEqual(
                bootstrap.count("docs_closeout_family_entry=ordinary_v2_bootstrap_ready"),
                1,
                "an unquoted competing family-entry assignment is forbidden too",
            )
            self.assertEqual(
                bootstrap.count("shared `full docs-finalize family tail`"),
                1,
                "only the exact tuple may enter the shared family",
            )
            for marker in (
                "`state=no_op + ready`",
                "любой иной/missing `blocked.reason_code`",
                "non-exact reconciliation",
                "missing/malformed/tampered/stale admission or identity",
                "present/unsafe manifest",
                "active/ambiguous cycle",
                "source drift",
                "schema drift",
                "unknown outer state",
                "не устанавливает local bootstrap flag",
                "fail-closed на ordinary rejection path",
            ):
                self.assertIn(marker, rejected_outer_clause)
            self.assertEqual(
                downstream_no_op_branch.count("`state=no_op`"),
                1,
                "downstream no_op branch must name only its no-op state",
            )
            for forbidden in (
                "ORDINARY_V2_BOOTSTRAP_PAYLOAD",
                "ORDINARY_V2_BOOTSTRAP_READY=true",
                "docs_closeout_family_entry=ordinary_v2_bootstrap_ready",
                "shared `full docs-finalize family tail`",
            ):
                self.assertNotIn(
                    forbidden,
                    downstream_no_op_branch,
                    "downstream no_op branch must not become a bootstrap family entry",
                )
            return bootstrap, rejected_outer_clause, downstream_no_op_branch

        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        architect = ARCHITECT_PROMPT.read_text(encoding="utf-8")
        bootstrap, current_rejection_clause, downstream_no_op_branch = (
            assert_prompt_matrix_is_exclusive(collab)
        )

        competing_no_op = (
            "      - `state=no_op + ready` MUST set "
            "`ORDINARY_V2_BOOTSTRAP_READY=true`, select "
            "`docs_closeout_family_entry=ordinary_v2_bootstrap_ready` and enter the "
            "shared `full docs-finalize family tail`."
        )
        mutated_collab = collab.replace(
            current_rejection_clause,
            f"{competing_no_op}\n{current_rejection_clause}",
            1,
        )
        self.assertNotEqual(mutated_collab, collab)
        with self.assertRaises(AssertionError):
            assert_prompt_matrix_is_exclusive(mutated_collab)

        equivalent_competing_route = (
            "      - A ready `state=no_op` payload is another bootstrap family entry: "
            "set `ORDINARY_V2_BOOTSTRAP_READY=true` and "
            "`docs_closeout_family_entry=ordinary_v2_bootstrap_ready`."
        )
        equivalent_mutant = collab.replace(
            family_entry_clause,
            f"{family_entry_clause}\n{equivalent_competing_route}",
            1,
        )
        self.assertNotEqual(equivalent_mutant, collab)
        with self.assertRaises(AssertionError):
            assert_prompt_matrix_is_exclusive(equivalent_mutant)

        unquoted_competing_route = (
            "      - state=no_op + ready must set ORDINARY_V2_BOOTSTRAP_READY=true "
            "and docs_closeout_family_entry=ordinary_v2_bootstrap_ready."
        )
        unquoted_mutant = collab.replace(
            current_rejection_clause,
            f"{unquoted_competing_route}\n{current_rejection_clause}",
            1,
        )
        self.assertNotEqual(unquoted_mutant, collab)
        with self.assertRaises(AssertionError):
            assert_prompt_matrix_is_exclusive(unquoted_mutant)

        downstream_competing_no_op = (
            "        - A ready `state=no_op` payload MUST set "
            "`ORDINARY_V2_BOOTSTRAP_READY=true`, select "
            "`docs_closeout_family_entry=ordinary_v2_bootstrap_ready` and enter the "
            "shared `full docs-finalize family tail`."
        )
        downstream_mutant = collab.replace(
            downstream_no_op_branch,
            f"{downstream_no_op_branch}{downstream_competing_no_op}\n",
            1,
        )
        self.assertNotEqual(downstream_mutant, collab)
        with self.assertRaises(AssertionError):
            assert_prompt_matrix_is_exclusive(downstream_mutant)

        def is_admitted(payload: dict[str, object]) -> bool:
            admission = payload.get("followups_bootstrap_admission")
            reconciliation = payload.get("followups_reconciliation")
            if not isinstance(admission, dict) or not isinstance(reconciliation, dict):
                return False
            outer = (
                payload.get("state") == "completed"
                or (
                    payload.get("state") == "blocked"
                    and payload.get("reason_code") == "no_cycle_staging_proof_unavailable"
                )
            )
            return bool(
                payload.get("schema") == "docs_closeout_payload.v1"
                and payload.get("schema_state") == "ok"
                and payload.get("schema_errors") == []
                and payload.get("plan_ref") == temporary_plan
                and outer
                and reconciliation.get("state") == "external_unknown"
                and reconciliation.get("reason") == "missing_v2_frozen_manifest"
                and admission == {
                    "schema": "followups_bootstrap_admission.v1",
                    "state": "ready",
                    "reason": "missing_v2_frozen_manifest",
                    **source_identity,
                }
            )

        def route_outcome(payload: dict[str, object]) -> tuple[str, int, bool]:
            assert_prompt_matrix_is_exclusive(collab)
            if is_admitted(payload):
                return ("ordinary_v2_bootstrap_ready", 1, True)
            return ("ordinary_rejection", 0, False)

        base = {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "schema_errors": [],
            "plan_ref": temporary_plan,
            "followups_reconciliation": {
                "state": "external_unknown",
                "reason": "missing_v2_frozen_manifest",
                "proof_host": canonical_manifest_path,
            },
            "followups_bootstrap_admission": {
                "schema": "followups_bootstrap_admission.v1",
                "state": "ready",
                "reason": "missing_v2_frozen_manifest",
                **source_identity,
            },
        }
        admitted_outers = (
            ("completed", {"state": "completed"}),
            (
                "blocked_no_cycle_staging_proof_unavailable",
                {"state": "blocked", "reason_code": "no_cycle_staging_proof_unavailable"},
            ),
        )
        for outer_name, outer in admitted_outers:
            with self.subTest(outer=outer_name):
                outcome, family_count, begin_called = route_outcome({**base, **outer})
                self.assertEqual(outcome, "ordinary_v2_bootstrap_ready")
                self.assertEqual(family_count, 1)
                self.assertTrue(begin_called)

        def assert_rejected(label: str, payload: dict[str, object]) -> None:
            with self.subTest(negative=label):
                outcome, family_count, begin_called = route_outcome(payload)
                self.assertEqual(outcome, "ordinary_rejection")
                self.assertEqual(family_count, 0)
                self.assertFalse(begin_called)

        negative_payloads = (
            {**base, "state": "no_op"},
            {**base, "state": "blocked"},
            {**base, "state": "blocked", "reason_code": "other"},
            {**base, "state": "unknown"},
            {**base, "schema_state": "blocked", "state": "completed"},
            {**base, "schema_errors": ["bad"], "state": "completed"},
            {**base, "state": "completed", "plan_ref": "docs/plans/foreign.md"},
        )
        for index, payload in enumerate(negative_payloads):
            assert_rejected(f"outer_{index}", payload)

        admission_negative_cases = (
            ("missing", None),
            ("malformed", {"state": "ready"}),
            (
                "blocked",
                {**base["followups_bootstrap_admission"], "state": "blocked"},
            ),
            (
                "stale",
                {
                    **base["followups_bootstrap_admission"],
                    "source_terminal_commit_oid": "d" * 40,
                },
            ),
            (
                "incomplete_identity",
                {
                    key: value
                    for key, value in base["followups_bootstrap_admission"].items()
                    if key != "source_plan_sha256"
                },
            ),
            (
                "foreign_identity",
                {
                    **base["followups_bootstrap_admission"],
                    "plan_ref": "docs/plans/foreign.md",
                },
            ),
        )
        reconciliation_negative_cases = (
            ("missing", None),
            ("malformed", {"state": "external_unknown"}),
            (
                "nonexact",
                {"state": "external_clean", "reason": "exact_v2_tuple_proof"},
            ),
        )
        for outer_name, outer in admitted_outers:
            for admission_name, admission in admission_negative_cases:
                assert_rejected(
                    f"{outer_name}_admission_{admission_name}",
                    {**base, **outer, "followups_bootstrap_admission": admission},
                )
            for reconciliation_name, reconciliation in reconciliation_negative_cases:
                assert_rejected(
                    f"{outer_name}_reconciliation_{reconciliation_name}",
                    {**base, **outer, "followups_reconciliation": reconciliation},
                )

        bootstrap_start = collab.index("2b) Generic ordinary-terminal V2 bootstrap")
        role_choice_index = collab.index("3) Выбери, какую роль запускать дальше", bootstrap_start)
        bootstrap = collab[bootstrap_start:role_choice_index]
        for marker in (
            "MANAGER_CMD=run",
            "MANAGER_CMD=run Q` никогда не входит",
            "route_guard_triggered=false",
            "status_norm=done|superseded",
            "docs_closeout_plan=PLAN_PATH",
            "plan_ref=PLAN_PATH",
            "state=completed",
            "state=blocked",
            "reason_code=no_cycle_staging_proof_unavailable",
            "followups_reconciliation.state=external_unknown",
            "followups_reconciliation.reason=missing_v2_frozen_manifest",
            "followups_bootstrap_admission.v1",
            "canonical_manifest_path",
            "source_terminal_commit_oid",
            "source_plan_blob_oid",
            "source_plan_sha256",
            "ORDINARY_V2_BOOTSTRAP_PAYLOAD",
            "ORDINARY_V2_BOOTSTRAP_READY=true",
            "docs_closeout_family_entry=ordinary_v2_bootstrap_ready",
            "shared `full docs-finalize family tail`",
            "state=no_op + ready",
            "generic `freeze-v2`",
            "retry",
            "historical fallback",
            "external_clean_noop|external_clean",
        ):
            self.assertIn(marker, bootstrap)
        for forbidden in (
            "Exact pre-commit bootstrap transition",
            "precommit_docs_closeout_plan",
            "PRECOMMIT_1013_",
        ):
            self.assertNotIn(forbidden, bootstrap)
        self.assertNotIn("PRECOMMIT_1013_", collab)
        self.assertNotIn("Narrow pre-commit bootstrap gate", bootstrap)
        for retired_marker in (
            "Narrow pre-commit bootstrap gate",
            "current bootstrap recovery plan",
            "current runner execution plan",
            "followups_bootstrap_admission.v1",
            "missing_v2_frozen_manifest",
            "generic historical selector",
        ):
            self.assertNotIn(retired_marker, architect)
        self.assertIn("final materialization path", architect)
        self.assertNotIn("2b) Generic ordinary-terminal V2 bootstrap", architect)

    def test_generic_terminal_v2_bootstrap_preempts_nonterminal_and_blocked_stops(self) -> None:
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")

        transition_index = collab.index("2b) Generic ordinary-terminal V2 bootstrap")
        role_choice_index = collab.index("3) Выбери, какую роль запускать дальше", transition_index)
        nonterminal_skip_index = collab.index(
            "Если `status_norm` не `done|superseded` — этот step skip.",
            role_choice_index,
        )
        generic_blocked_index = collab.index(
            "Если helper вернул `state=blocked`:",
            nonterminal_skip_index,
        )
        no_op_index = collab.index(
            "Если helper вернул `state=no_op`:",
            generic_blocked_index,
        )
        completed_index = collab.index(
            "Если helper вернул `state=completed`:",
            no_op_index,
        )
        clean_only_gate_index = collab.index(
            "Если `terminal_closeout_fast_path.eligible=true`",
            completed_index,
        )
        shared_tail_index = collab.index("Shared `full docs-finalize family tail`", completed_index)
        transition = collab[transition_index:role_choice_index]
        blocked_branch = collab[generic_blocked_index:no_op_index]
        completed_branch = collab[completed_index:shared_tail_index]
        shared_tail = collab[shared_tail_index:]

        self.assertLess(transition_index, role_choice_index)
        self.assertLess(transition_index, nonterminal_skip_index)
        self.assertLess(transition_index, generic_blocked_index)
        self.assertLess(transition_index, clean_only_gate_index)
        self.assertLess(generic_blocked_index, shared_tail_index)
        self.assertLess(no_op_index, completed_index)
        self.assertLess(completed_index, shared_tail_index)
        for marker in (
            "Установи только local `docs_closeout_plan=PLAN_PATH`",
            "state=completed",
            "state=blocked",
            "reason_code=no_cycle_staging_proof_unavailable",
            "ORDINARY_V2_BOOTSTRAP_READY=true",
            "ORDINARY_V2_BOOTSTRAP_PAYLOAD",
            "docs_closeout_family_entry=ordinary_v2_bootstrap_ready",
            "не устанавливает local bootstrap flag",
            "не inject-ится в downstream semantic role message",
        ):
            self.assertIn(marker, transition)
        for marker in (
            "не выполняй generic blocked stop",
            "немедленно пропусти ветки `state=no_op` и `state=completed`",
            "retained `ORDINARY_V2_BOOTSTRAP_PAYLOAD`",
            "не current blocked re-readback",
        ):
            self.assertIn(marker, blocked_branch)
        for marker in (
            "не применяй fast-path/normal-clean gate",
            "не выполняй остальные подпункты `state=completed`",
            "retained `ORDINARY_V2_BOOTSTRAP_PAYLOAD`",
        ):
            self.assertIn(marker, completed_branch)
        self.assertIn("(b) `docs_closeout_family_entry=ordinary_v2_bootstrap_ready`", shared_tail)
        self.assertIn("direct transfer буквально пропускает ordinary `state=blocked`/`state=completed` stops", shared_tail)
        self.assertIn("before generic blocked stop and clean-only gate", shared_tail)

    def test_manager_prompts_consume_any_oracle_route_guard_before_raw_status(self) -> None:
        prompt_paths = (ROUTER_PROMPT, COLLAB_PROMPT, CUSTOM_PROMPT)
        for prompt_path in prompt_paths:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                guard_index = text.index("Generic route-guard rule")
                raw_route_index = text.index("raw `status_norm` route", guard_index)
                next_owner_index = text.index("`route_guard_next_owner`", guard_index)

                self.assertLess(guard_index, raw_route_index)
                self.assertLess(guard_index, next_owner_index)
                self.assertIn("любой `route_guard_triggered=true`", text[guard_index:raw_route_index + 80])
                self.assertIn("`route_guard_kind` — diagnostic reason", text[guard_index:raw_route_index + 180])
                self.assertIn("не выводит `real scope expansion` из target count/prose/lint warning", text)
                self.assertIn("не запускает `planveyor_decomposition_init` автоматически из route guard", text)

        self.assertIn(
            "`route_guard_triggered=true` → роль из `route_guard_next_owner`",
            ROUTER_PROMPT.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "`route_guard_triggered=true` → роль из `route_guard_next_owner`",
            COLLAB_PROMPT.read_text(encoding="utf-8"),
        )
        custom = CUSTOM_PROMPT.read_text(encoding="utf-8")
        self.assertIn("если `route_guard_triggered=true`, пропусти terminal closeout и cold-start CENSOR", custom)
        self.assertIn("`route_guard_triggered=true` → role-run key из `route_guard_next_owner`", custom)

    def test_manager_route_guard_contract_stays_generic_to_machine_authority_semantics(self) -> None:
        for prompt_path in (ROUTER_PROMPT, COLLAB_PROMPT, CUSTOM_PROMPT):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                self.assertIn("Generic route-guard rule", text)
                self.assertIn("`route_guard_kind` — diagnostic reason", text)
                self.assertIn("`route_guard_next_owner`", text)
                self.assertNotIn("machine_authority_decision", text)
                self.assertNotIn("strict_plan_meta_json", text)
                self.assertNotIn("machine_authority_decision_ref", text)

    def test_manager_mode_admission_precedes_dynamic_writes_and_dispatch(self) -> None:
        custom = CUSTOM_PROMPT.read_text(encoding="utf-8")
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        router = ROUTER_PROMPT.read_text(encoding="utf-8")

        self.assertIn("--manager-mode manager-custom-pipeline", custom)
        self.assertIn("--manager-mode manager-collab", collab)
        self.assertIn("--manager-mode manager-collab", router)
        for text, marker in (
            (custom, "до write/dispatch вызови mode oracle"),
            (collab, "до любых writes/dispatch вызови"),
        ):
            self.assertIn("planveyor_q_stop_json manager_mode_mismatch", text)
            self.assertIn("required_mode_mismatch", text)
            self.assertIn("auto-switch", text)
            active_plan_index = text.index(marker)
            plan_set_index = text.index("planveyor_plan_set <active_plan>", active_plan_index)
            self.assertLess(active_plan_index, plan_set_index)

        for text in (custom, collab):
            with self.subTest(prompt="custom" if text is custom else "collab"):
                advisory_index = text.index("advisory preview")
                qualified_closeout = (
                    "planveyor_q_closeout_json --manager-mode manager-custom-pipeline"
                    if text is custom
                    else "planveyor_q_closeout_json --manager-mode manager-collab"
                )
                closeout_index = text.index(qualified_closeout, advisory_index)
                rejection_index = text.index("closeout_kind=manager_mode_mismatch", closeout_index)
                carrier_error_index = text.index("manager_mode_admission_carrier_error", rejection_index)
                success_index = text.index("exit `0`", carrier_error_index)
                self.assertLess(advisory_index, closeout_index)
                self.assertLess(closeout_index, rejection_index)
                self.assertLess(rejection_index, carrier_error_index)
                self.assertLess(carrier_error_index, success_index)
                self.assertIn("advisory", text[advisory_index:closeout_index])
                self.assertIn("existing exclusive lock", text[closeout_index:rejection_index])
                self.assertIn("planveyor_q_stop_json manager_mode_mismatch", text[rejection_index:carrier_error_index])
                self.assertIn("ровно один subsequent", text[rejection_index:carrier_error_index])
                self.assertIn("без `planveyor_q_stop_json manager_mode_mismatch`", text[carrier_error_index:success_index])

    def test_terminal_queue_admission_contract_is_identical_across_manager_carriers(self) -> None:
        carriers = (MANAGER_ROLE, COLLAB_PROMPT, CUSTOM_PROMPT)
        required_markers = (
            "Done|Superseded",
            "terminal_disposition=ordinary",
            "queue_closeout_kind=terminal_status",
            "queue_closeout_ready=true",
            "error=terminal_closeout_admission_rejected",
            "accepted_red_reconciliation_required",
            "terminal_status_assertion_mismatch",
            "terminal_disposition_invalid",
            "terminal_closeout_not_ready",
            "zero-write/no-fallback",
            "exact payload",
            "Owner",
        )
        self.assertEqual(len(carriers), 3)
        for carrier in carriers:
            with self.subTest(carrier=carrier.name):
                text = carrier.read_text(encoding="utf-8")
                for marker in required_markers:
                    self.assertIn(marker, text)
                self.assertIn("Accepted-red reconciliation", text)

        for carrier in (COLLAB_PROMPT, CUSTOM_PROMPT):
            with self.subTest(mode_carrier=carrier.name):
                self.assertIn("closeout_kind=manager_mode_mismatch", carrier.read_text(encoding="utf-8"))

    def test_terminal_dependency_blocker_has_bounded_mode_specific_routing(self) -> None:
        custom = CUSTOM_PROMPT.read_text(encoding="utf-8")
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")

        for text in (custom, collab):
            with self.subTest(prompt="custom" if text is custom else "collab"):
                self.assertIn("activation_blocker=depends_on_skipped_incompatible", text)
                self.assertIn("successful terminal transaction", text)
                self.assertIn("повторный closeout", text)
                self.assertIn("auto-switch", text)

        blocker_index = collab.index("activation_blocker=depends_on_skipped_incompatible")
        next_plan_index = collab.index("advanced=true` и `next_plan", blocker_index)
        blocker_lane = collab[blocker_index:next_plan_index]
        self.assertIn("docs_closeout_plan=<finalized_plan>", blocker_lane)
        self.assertIn("Next: Owner", blocker_lane)
        self.assertIn("skipped_incompatible[]", blocker_lane)

        custom_blocker_index = custom.index("activation_blocker=depends_on_skipped_incompatible")
        custom_lane = custom[custom_blocker_index : custom.index("иначе вызови", custom_blocker_index)]
        self.assertIn("Next: Owner", custom[:custom_blocker_index])
        self.assertIn("skipped_incompatible[]", custom[:custom_blocker_index])
        self.assertIn("planveyor_plan_set", custom_lane)
        self.assertIn("role dispatch", custom_lane)

    def test_native_queue_helper_inventory_requires_closeout_mode_carrier(self) -> None:
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        inventory = collab.split("Queue helper contract", 1)[1].split(
            "Post-review exact-bundle closeout",
            1,
        )[0]

        self.assertIn(
            "- `planveyor_q_closeout_json --manager-mode manager-collab`",
            inventory,
        )
        self.assertNotRegex(
            inventory,
            r"(?m)^\s*-\s+`planveyor_q_closeout_json`\s*$",
        )

    def test_terminal_queue_mode_handles_pending_skip_and_resumed_parent_rejection(self) -> None:
        canonical_vocab_bytes = (ROOT / "docs" / "_meta" / "plan_vocab.json").read_bytes()

        def write_plan(root: Path, rel_path: str, *, status: str, required_mode: str) -> None:
            plan_path = root / rel_path
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            stem = plan_path.stem
            machine_authority_decision = {
                "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                "applicability": "not_applicable",
                "reason_code": "docs_or_tests_only",
            }
            machine_authority_decision_ref = {
                "applicability": "not_applicable",
                "reason_code": machine_authority_decision["reason_code"],
                "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(
                    machine_authority_decision
                ),
            }
            target_rel = "scripts/queue_mode_fixture_target.py"
            target_path = root / target_rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text("# synthetic queue fixture target\n", encoding="utf-8")
            draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
            draft_path = root / draft_rel
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(
                "# Code draft: queue mode fixture\n\n"
                "```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": rel_path,
                            "cluster": "process",
                            "targets": [{"path": target_rel, "kind": "py"}],
                            "deleted_paths": [],
                            "machine_authority_decision_ref": machine_authority_decision_ref,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            review_rel = f"docs/code_reviews/{stem}.md"
            if status == "Done":
                review_path = root / review_rel
                review_path.parent.mkdir(parents=True, exist_ok=True)
                review_path.write_text(
                    "# Код-ревью — queue mode fixture\n\n"
                    "**Date:** 2026-07-17 20:40 MSK\n"
                    "**Target:** BUNDLE=fixture\n"
                    "**Status:** ✅ OK\n",
                    encoding="utf-8",
                )
            plan_path.write_text(
                "# Plan: terminal mode fixture\n\n"
                "**Date:** 2026-07-17 20:40 MSK\n"
                "**Plan type:** dev\n"
                f"**Status:** {status}\n\n"
                "## Как я понял задачу\n\n"
                "Временный fixture сохраняет проверку Manager-mode через real queue subprocess.\n\n"
                "## Meta (machine-readable JSON; required for new plans)\n"
                "```json\n"
                + json.dumps(
                    {
                        "plan_meta": {
                            "cluster": "process",
                            "required_manager_mode": required_mode,
                            "machine_authority_decision": machine_authority_decision,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
                "```\n\n"
                "## Context links\n\n"
                f"- Code draft(s): `{draft_rel}`\n\n"
                "## Rollout packet handoff\n\n"
                "- Role: N/A (why=temporary fixture has no rollout packet)\n"
                "- Packet path: N/A (why=temporary fixture has no rollout packet)\n"
                "- Target repo: N/A (why=temporary fixture has no rollout packet)\n"
                "- Suggested target plan slug: N/A (why=temporary fixture has no rollout packet)\n"
                "- Queue after import: N/A (why=temporary fixture has no rollout packet)\n\n"
                "## Close-out routing\n\n"
                "- Roadmap/queue sync: N/A (why=temporary fixture has no roadmap)\n"
                "- Follow-up sync: N/A (why=temporary fixture has no follow-ups)\n"
                "- Next bounded slice: N/A (why=temporary fixture has no next slice)\n"
                "- Terminal outcome: no (why=temporary fixture only)\n\n"
                "## Verification rerun / exec handoff\n\n"
                "- Mode: fresh-exec\n"
                "- Context source: temporary queue fixture\n"
                "- Prompt: exercise the real queue subprocess\n"
                "- Command: queue next\n"
                "- Expected artifact: temporary queue state\n\n"
                "## Review artifacts\n\n"
                f"- Code review (primary): `{review_rel}`"
                + ("\n" if status == "Done" else " (PLANNED)\n"),
                encoding="utf-8",
            )

        def queue_json(root: Path, *args: str) -> dict[str, object]:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(PLAN_QUEUE),
                    "--project-root",
                    str(root),
                    *args,
                    "--json",
                ],
                cwd=root,
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        cases = (
            ("manager-collab", "manager-custom-pipeline"),
            ("manager-custom-pipeline", "manager-collab"),
        )
        for actual_mode, required_mode in cases:
            for candidate_kind in ("next_plan", "resume_parent_plan"):
                with self.subTest(actual_mode=actual_mode, candidate_kind=candidate_kind):
                    with tempfile.TemporaryDirectory(prefix="manager_terminal_mode_") as tmpdir:
                        root = Path(tmpdir)
                        (root / ".git").mkdir()
                        fixture_vocab = root / "docs" / "_meta" / "plan_vocab.json"
                        fixture_vocab.parent.mkdir(parents=True, exist_ok=True)
                        fixture_vocab.write_bytes(canonical_vocab_bytes)
                        self.assertEqual(fixture_vocab.read_bytes(), canonical_vocab_bytes)
                        active_rel = "docs/plans/260717_2040_active_done.md"
                        candidate_rel = f"docs/plans/260717_2041_{candidate_kind}.md"
                        write_plan(root, active_rel, status="Done", required_mode="either")
                        write_plan(root, candidate_rel, status="Ready for Coder", required_mode="either")
                        subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True)
                        subprocess.run(
                            ["git", "-C", str(root), "config", "user.email", 'manager-contract' + '@' + 'example' + '.' + 'invalid'],
                            check=True,
                        )
                        subprocess.run(
                            ["git", "-C", str(root), "config", "user.name", "Manager contract fixture"],
                            check=True,
                        )
                        subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
                        subprocess.run(
                            ["git", "-C", str(root), "commit", "--quiet", "--allow-empty", "-m", "fixture"],
                            check=True,
                        )

                        set_args = ["set", active_rel]
                        if candidate_kind == "next_plan":
                            set_args.append(candidate_rel)
                        else:
                            set_args.extend(["--resume-parent", "run-parent-once"])
                        set_args.extend(["--for-manager-mode", actual_mode])
                        queue_json(root, *set_args)
                        queue_json(root, "next", "--manager-mode", actual_mode)

                        if candidate_kind == "resume_parent_plan":
                            state_path = root / ".planveyor.planqueue.json"
                            state = json.loads(state_path.read_text(encoding="utf-8"))
                            state["parent_plan"] = candidate_rel
                            state_path.write_text(
                                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8",
                            )
                        write_plan(root, candidate_rel, status="Ready for Coder", required_mode=required_mode)

                        before = queue_json(root, "show")
                        candidate = before["next_pending_plan"]
                        if candidate is None and (
                            before["resume_parent"] == "run-parent-once"
                            and before["parent_plan"]
                            and not before["parent_resume_pending_at"]
                            and not before["parent_resumed_at"]
                        ):
                            candidate = before["parent_plan"]
                        self.assertEqual(candidate, candidate_rel)
                        state_path = root / ".planveyor.planqueue.json"
                        log_path = root / ".planveyor.planqueue.log"
                        state_before = state_path.read_bytes()
                        log_before = log_path.read_bytes()
                        closeout = subprocess.run(
                            [
                                sys.executable,
                                "-B",
                                str(PLAN_QUEUE),
                                "--project-root",
                                str(root),
                                "closeout",
                                "--manager-mode",
                                actual_mode,
                                "--json",
                            ],
                            cwd=root,
                            check=False,
                            text=True,
                            capture_output=True,
                        )
                        closeout_payload = json.loads(closeout.stdout)
                        if candidate_kind == "next_plan":
                            self.assertEqual(closeout.returncode, 0, closeout.stderr)
                            self.assertTrue(closeout_payload["advanced"])
                            self.assertTrue(closeout_payload["queue_complete"])
                            receipt = closeout_payload["skipped_incompatible"][0]
                            self.assertEqual(receipt["plan"], candidate_rel)
                            self.assertEqual(receipt["skip_phase"], "activation")
                            self.assertEqual(receipt["actual_manager_mode"], actual_mode)
                            self.assertEqual(receipt["manager_mode_state"], "mismatch")
                            self.assertEqual(receipt["manager_mode_reason"], "required_mode_mismatch")
                            after = queue_json(root, "show")
                            self.assertEqual(after["items"][1]["state"], "skipped_manager_mode")
                            appended_log = log_path.read_bytes()[len(log_before) :].decode("utf-8")
                            self.assertEqual(appended_log.count("\tskip_manager_mode\t"), 1)
                            self.assertNotIn("\tstop\t", appended_log)
                            continue

                        self.assertEqual(closeout.returncode, 1, closeout.stderr)
                        self.assertFalse(closeout_payload["advanced"])
                        self.assertEqual(closeout_payload["closeout_kind"], "manager_mode_mismatch")
                        self.assertEqual(closeout_payload["candidate_kind"], candidate_kind)
                        self.assertEqual(closeout_payload["candidate_plan"], candidate_rel)
                        self.assertEqual(closeout_payload["actual_manager_mode"], actual_mode)
                        self.assertEqual(closeout_payload["manager_mode_state"], "mismatch")
                        self.assertEqual(closeout_payload["manager_mode_reason"], "required_mode_mismatch")
                        self.assertEqual(state_path.read_bytes(), state_before)
                        self.assertEqual(log_path.read_bytes(), log_before)
                        self.assertFalse((root / ".planveyor.planqueue.txn.json").exists())

                        stopped = queue_json(root, "stop", "--reason", "manager_mode_mismatch")
                        after = queue_json(root, "show")

                        self.assertEqual(stopped["last_stop"]["reason"], "manager_mode_mismatch")
                        self.assertEqual(after["items"], before["items"])
                        self.assertEqual(after["cursor"], before["cursor"])
                        self.assertEqual(after["last_transition"], before["last_transition"])
                        self.assertEqual(after["active_plan"], active_rel)
                        self.assertEqual(after["next_pending_plan"], before["next_pending_plan"])
                        self.assertEqual(after["parent_resume_pending_at"], before["parent_resume_pending_at"])
                        self.assertEqual(after["parent_resumed_at"], before["parent_resumed_at"])
                        appended_log = log_path.read_bytes()[len(log_before) :].decode("utf-8")
                        self.assertEqual(appended_log.count("\tstop\t"), 1)
                        self.assertNotIn("\tadvance\t", appended_log)
                        self.assertNotIn("\tcomplete\t", appended_log)
                        self.assertFalse((root / "role_invocations.log").exists())

    def test_role_dispatch_uses_child_bin_launch_form_not_sourced_fallback(self) -> None:
        text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        selected_entry = '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project /absolute/path/to/selected-consumer'

        self.assertEqual(text.count(selected_entry), 6)
        self.assertIn(
            "для выбранного consumer — корня current `PLAN_PATH` и Manager",
            text,
        )
        censor_launch = (
            selected_entry
            + ' planveyor_custom_role_step <architect_censor|planner_censor|coder_censor> '
            + '--plan "$PLAN_PATH" --json'
        )
        self.assertEqual(text.count(censor_launch), 2)
        self.assertIn("через public child facade выбранного consumer", text)
        self.assertNotIn("required login-shell form", text)
        for marker in (
            "matching `REDUCED_REVALIDATION_FAILURE_KEY` запрещает `state=skipped_by_valid_hint` как route authority",
            "state=complete|skipped_by_valid_hint",
            "reason_code=missing_current_receipt",
            "После fallback wrapper перечитай oracle и тот же exact helper",
            "censor_evidence_lint.state != complete",
        ):
            self.assertIn(marker, text)
        self.assertIn(
            selected_entry + " <planveyor_function> [args…]",
            text,
        )
        self.assertIn(
            selected_entry
            + ' planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json',
            text,
        )
        self.assertIn(
            selected_entry
            + ' planveyor_custom_role_step planner --plan "$PLAN_PATH" --json',
            text,
        )
        self.assertNotIn("<CENSOR_WRAPPER>", text)
        self.assertNotIn("`zsh -lc 'root=", text)
        self.assertNotIn("Direct `source scripts/planveyor.zsh && <ROLE_WRAPPER>` is forbidden", text)
        self.assertIn("Не вызывай raw shell wrapper", text)
        self.assertIn("не подключай implementation shell file через `source`", text)

        bin_text = (ROOT / "bin" / "planveyor").read_text(encoding="utf-8")
        for marker in (
            "zsh -df",
            "--project requires an absolute directory",
            "canonical_external_dir \"$1\" 'project root'",
            "PLANVEYOR_CHILD_SHELL_V1='planveyor-child-shell.v1'",
            'PLANVEYOR_PROJECT_ROOT="$project_root"',
            'cd -- "$PLANVEYOR_PROJECT_ROOT" || exit 1',
            'planveyor_cli "$@"',
        ):
            self.assertIn(marker, bin_text)

        facade = (ROOT / "scripts" / "planveyor.zsh").read_text(encoding="utf-8")
        for marker in (
            "_planveyor_cli_require_attested_child()",
            "planveyor: commands must run through bin/planveyor",
            "planveyor_role_run_child_dispatch()",
            "Usage: planveyor_role_run_child_dispatch <wrapper> <runner_role> <runner>",
            "child project root does not match its authority context",
        ):
            self.assertIn(marker, facade)
        dispatch_start = facade.index("planveyor_role_run_child_dispatch()")
        dispatch = facade[dispatch_start : dispatch_start + 3200]
        self.assertIn("_planveyor_cli_require_attested_child || return $?", dispatch)
    def test_custom_manager_supervises_planner_coder_censors_before_semantic_harvest(self) -> None:
        text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        for role in ("planner_censor", "coder_censor"):
            self.assertIn(
                f'planveyor_custom_role_step {role} --plan "$PLAN_PATH" --json',
                text,
            )
        self.assertIn("planveyor_role_run_receipt_check <receipt_path>", text)
        self.assertIn("same-run receipt", text)
        self.assertIn("не заменяет semantic CENSOR PASS", text)
        self.assertIn("отдельно запускай `censor_receipts_harvest.py`", text)
        self.assertIn("требуй current `complete`", text)
        self.assertIn("manual compatibility wrappers", text)
        self.assertNotIn("`Ready for Coder` → запусти `planveyor_planner_censor`", text)
        self.assertNotIn("`Ready for Review` → запусти `planveyor_coder_censor`", text)

    def test_custom_and_collab_censor_gate_use_helper_readback(self) -> None:
        for prompt_path in (CUSTOM_PROMPT, COLLAB_PROMPT):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")

                self.assertIn("CENSOR evidence gate helper-backed", text)
                command = (
                    '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py censor_receipts_harvest.py --plan "$PLAN_PATH" '
                    "--censor-role <Architect|Planner|Coder> "
                    '--handoff-status "<post-status>" '
                )
                if prompt_path == COLLAB_PROMPT:
                    command += '--censor-dispatch-id "$CENSOR_DISPATCH_ID" '
                command += "--format json"
                self.assertIn(command, text)
                self.assertIn("censor_evidence_lint.state", text)
                self.assertIn("reason_code=missing_current_receipt", text)
                self.assertIn("state=skipped_by_valid_hint", text)
                self.assertIn("helper state=incomplete", text)

    def test_native_collab_coder_censor_uses_fresh_dispatch_provenance(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")

        self.assertIn("Same-session` = новый отдельный Manager `followup_task`", text)
        self.assertIn("дождись завершения primary role", text)
        self.assertIn("Только после этого wait", text)
        self.assertIn(
            "`CENSOR_DISPATCH_ID=censor:<role-token>:<post-role oracle_run_id>`",
            text,
        )
        self.assertIn('--censor-dispatch-id "$CENSOR_DISPATCH_ID"', text)
        self.assertIn("CENSOR_DISPATCH_ID=<fresh value created after primary role wait>", text)
        self.assertIn("pre-dispatch complete receipt", text)
        self.assertIn("не может удовлетворить fresh expected ID", text)
        self.assertIn("missing_or_mismatched_censor_dispatch_id", text)
        self.assertIn("ambiguous_censor_dispatch_id|stale_censor_dispatch_id", text)
        self.assertIn("Role-authored `Censor hint: skip` не отменяет", text)
        self.assertIn("Reduced-conveyor skip", text)
        self.assertIn("PRE_ROLE_SMALL_SLICE_PAYLOAD", text)
        self.assertIn("POST_ROLE_SMALL_SLICE_PAYLOAD", text)
        self.assertIn("exact pre/post parity", text)
        self.assertIn("Primary role не может впервые materialize/restamp classifier", text)
        self.assertIn("немедленно `continue` к следующей Manager iteration", text)
        self.assertIn("**do not create `CENSOR_DISPATCH_ID`**", text)
        self.assertIn(
            "reason_code` не входит в "
            "`missing_current_receipt|missing_or_mismatched_censor_dispatch_id`",
            text,
        )
        precheck_index = text.index("До primary `followup_task` для Architect/Planner/Coder")
        primary_send_index = text.index("Запусти роль через `followup_task` (persistent)")
        wait_index = text.index("Сначала обязательно дождись завершения primary role")
        small_slice_index = text.index("Перед выбором цензора повторно вызови `planveyor_q_small_slice_json")
        status_route_index = text.index("Определи необходимость по post-статусу")
        dispatch_id_index = text.index("Только после этого wait и после доказанного non-skip routing")
        skip_continue_index = text.index("немедленно `continue` к следующей Manager iteration")
        self.assertLess(precheck_index, primary_send_index)
        self.assertLess(primary_send_index, wait_index)
        self.assertLess(wait_index, small_slice_index)
        self.assertLess(small_slice_index, status_route_index)
        self.assertLess(status_route_index, dispatch_id_index)
        self.assertLess(skip_continue_index, status_route_index)

    def test_native_collab_pending_handoff_recovery_matrix_is_complete(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")

        self.assertIn("Native cold-start CENSOR gate before ordinary status routing", text)
        self.assertIn("`MANAGER_CMD=run` и `MANAGER_CMD=run Q`", text)
        for mapping in (
            "`Architect draft|Ready for Planner` -> `Architect`",
            "`Ready for Coder` -> `Planner`",
            "`Ready for Review` -> `Coder`",
        ):
            self.assertIn(mapping, text)
        self.assertIn(
            "verified_handoff(plan_ref, handoff_status, censor_role, proof_kind, "
            "proof_id, top_level_invocation_lineage, downstream_role_handle_lineage)",
            text,
        )
        self.assertIn("proof_kind=censor_receipt", text)
        self.assertIn("proof_id=censor_dispatch_id", text)
        self.assertIn("single-use", text)
        self.assertIn("diagnostic-only no-selector", text)
        self.assertIn("complete|missing|stale|skip", text)
        self.assertIn("malformed|ambiguous|conflicting", text)
        self.assertIn("cold_start_dispatch_attempted", text)
        self.assertIn(
            "`CENSOR_DISPATCH_ID=censor:<role-token>:<current cold-start oracle_run_id>`",
            text,
        )
        self.assertIn("same persistent role thread", text)
        self.assertIn("No material semantic delta; provenance correction only", text)
        self.assertIn("replacement_dispatch_attempted", text)
        self.assertIn("second non-green replacement", text)
        self.assertIn("failed dispatch ID", text)
        self.assertIn("Не редактируй и не удаляй malformed receipt", text)
        self.assertIn("не вызывай `planveyor_role_run *_censor`", text)

        for path in (MANAGER_ROLE, PLAN_README):
            with self.subTest(canon_doc=path.name):
                canon = path.read_text(encoding="utf-8")
                self.assertIn("Native collab cold-start CENSOR gate", canon)
                self.assertIn(
                    "`Architect draft|Ready for Planner -> Architect`; "
                    "`Ready for Coder -> Planner`; `Ready for Review -> Coder`",
                    canon,
                )
                self.assertIn("verified_handoff", canon)
                self.assertIn("diagnostic-only", canon)
                self.assertIn("invocation-wide", canon)
                self.assertIn("downstream role-handle lineage", canon)
                self.assertIn(
                    "cold-start cap exhausted after downstream handle replacement",
                    canon,
                )
                self.assertIn("Owner-authorized replacement", canon)
                self.assertIn("No material semantic delta; provenance correction only", canon)

        gate_index = text.index("Native cold-start CENSOR gate before ordinary status routing")
        route_index = text.index("Выбери, какую роль запускать дальше", gate_index)
        self.assertLess(gate_index, route_index)

    def test_verified_handoff_guard_precedes_every_downstream_send_path(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")

        cold_gate_index = text.index(
            "Native cold-start CENSOR gate before ordinary status routing"
        )
        ready_for_review_index = text.index(
            "`Ready for Review` -> `Coder`;",
            cold_gate_index,
        )
        exact_green_index = text.index(
            "только `censor_evidence_lint.state=complete`",
            ready_for_review_index,
        )
        create_handoff_index = text.index(
            "создаёт invocation-local `verified_handoff`",
            exact_green_index,
        )
        guard_index = text.index(
            "Verified handoff consumption guard before any downstream send",
            create_handoff_index,
        )
        pre_role_capture_index = text.index(
            "Pre-role small-slice capture for Architect/Planner/Coder"
        )
        reviewer_dispatch_index = text.index(
            "Reviewer logical dispatch (обязательно для reviewer statuses)",
            guard_index,
        )
        reviewer_risk_send_index = text.index(
            "2. отправь Reviewer-run",
            reviewer_dispatch_index,
        )
        reviewer_contracts_send_index = text.index(
            "7. отправь Reviewer-run",
            reviewer_risk_send_index,
        )
        generic_send_index = text.index(
            "Запусти роль через `followup_task` (persistent)",
            reviewer_contracts_send_index,
        )
        self.assertLess(pre_role_capture_index, guard_index)
        self.assertLess(guard_index, reviewer_dispatch_index)
        self.assertLess(guard_index, reviewer_risk_send_index)
        self.assertLess(guard_index, reviewer_contracts_send_index)
        self.assertLess(guard_index, generic_send_index)

        guard_block = text[guard_index:reviewer_dispatch_index]
        self.assertIn("VERIFIED_HANDOFF_CONSUME_PENDING=true", guard_block)
        self.assertIn("consume и очисти `verified_handoff`", guard_block)
        self.assertIn("запрещает любой downstream send", guard_block)
        self.assertIn("`continue` к fresh cold-start gate", guard_block)

        ready_for_review_trace = [
            event
            for _, event in sorted(
                (
                    (ready_for_review_index, "ready_for_review"),
                    (exact_green_index, "coder_exact_green"),
                    (create_handoff_index, "create_verified_handoff"),
                    (guard_index, "consume_verified_handoff"),
                    (reviewer_risk_send_index, "reviewer_code_risk_first_message"),
                )
            )
        ]
        self.assertEqual(
            ready_for_review_trace,
            [
                "ready_for_review",
                "coder_exact_green",
                "create_verified_handoff",
                "consume_verified_handoff",
                "reviewer_code_risk_first_message",
            ],
        )
        self.assertEqual(ready_for_review_trace.count("consume_verified_handoff"), 1)

    def test_cross_iteration_small_slice_handoff_contract_is_shared(self) -> None:
        prompts = {
            "native": COLLAB_PROMPT.read_text(encoding="utf-8"),
            "custom": CUSTOM_PROMPT.read_text(encoding="utf-8"),
        }
        readme = PLAN_README.read_text(encoding="utf-8")
        parity_fields = (
            "plan",
            "requested_profile",
            "expected_bundle_family",
            "helper_validation",
            "drift_behavior",
            "code_draft_path",
            "target_paths",
            "actual_bundle_family",
            "live_review_artifact",
            "review_route_kind",
            "rollout_packet_is_na",
            "visual_acceptance_is_na",
        )
        shared_anchors = (
            "Cross-iteration reduced handoff (`small_slice_parity`)",
            "proof_kind=censor_receipt",
            "proof_id=censor_dispatch_id",
            "proof_kind=small_slice_parity",
            "proof_id=(PRE_ROLE_SMALL_SLICE_PAYLOAD, POST_ROLE_SMALL_SLICE_PAYLOAD, post_role_oracle_run_id)",
            "discovery-or-seed",
            "receipt-reuse-only",
            "current-helper-revalidation",
            "notice/success text != mutation truth",
            "не выбирает status/role",
            "не меняет plan/queue",
        )

        for carrier, text in (*prompts.items(), ("README", readme)):
            with self.subTest(carrier=carrier):
                for anchor in shared_anchors:
                    self.assertIn(anchor, text)
                for field in parity_fields:
                    self.assertIn(f"`{field}`", text)
                self.assertIn(
                    "(plan_ref, handoff_status, censor_role, proof_kind, proof_id, "
                    "top_level_invocation_lineage, downstream_role_handle_lineage)",
                    text,
                )

        native = prompts["native"]
        self.assertIn("current persistent downstream role handle", native)
        self.assertIn("native `run|run Q`", native)
        self.assertIn("cold-start cap exhausted after downstream handle replacement", native)
        native_seed = native.index(
            "Small-slice parity discovery-or-seed after primary completion"
        )
        native_next = native.index(
            "Native cold-start CENSOR gate before ordinary status routing"
        )
        native_pending_refresh = native.index(
            "Current small-slice revalidation before pending",
            native_next,
        )
        native_pending_set = native.index(
            "VERIFIED_HANDOFF_CONSUME_PENDING=true",
            native_pending_refresh,
        )
        native_consume = native.index(
            "Verified handoff consumption guard before any downstream send"
        )
        native_consume_refresh = native.index(
            "Current small-slice revalidation immediately before consume",
            native_consume,
        )
        native_send = native.index("Запусти роль через `followup_task` (persistent)")
        self.assertLess(native_next, native_pending_refresh)
        self.assertLess(native_pending_refresh, native_pending_set)
        self.assertLess(native_pending_set, native_consume)
        self.assertLess(native_consume, native_consume_refresh)
        self.assertLess(native_consume_refresh, native_send)
        self.assertIn("POST_ROLE_SMALL_SLICE_PAYLOAD", native[native_seed:])

        custom = prompts["custom"]
        self.assertIn("current downstream role `session_key+SID`", custom)
        self.assertIn("custom single-plan/queue", custom)
        self.assertIn("helper-owned non-green stop", custom)
        custom_cold = custom.index("Cold-start CENSOR gate before downstream routing")
        custom_pending_refresh = custom.index(
            "Current small-slice revalidation before pending",
            custom_cold,
        )
        custom_pending_set = custom.index(
            "VERIFIED_HANDOFF_CONSUME_PENDING=true",
            custom_pending_refresh,
        )
        custom_consume = custom.index(
            "Verified handoff consume-before-send guard for custom mode",
            custom_cold,
        )
        custom_consume_refresh = custom.index(
            "Current small-slice revalidation immediately before consume",
            custom_consume,
        )
        custom_send = custom.index("Запусти роль через blocking receipt helper", custom_consume)
        custom_seed = custom.index(
            "Small-slice parity discovery-or-seed after custom primary completion",
            custom_send,
        )
        self.assertLess(custom_cold, custom_pending_refresh)
        self.assertLess(custom_pending_refresh, custom_pending_set)
        self.assertLess(custom_pending_set, custom_consume)
        self.assertLess(custom_consume, custom_consume_refresh)
        self.assertLess(custom_consume_refresh, custom_send)
        self.assertLess(custom_send, custom_seed)

        for mode, text in prompts.items():
            with self.subTest(current_helper_route=mode):
                self.assertIn(
                    "для любого mapped downstream route, включая Reviewer",
                    text,
                )
                self.assertIn(
                    "exact-equal stored PRE/POST payloads",
                    text,
                )
                self.assertGreaterEqual(
                    text.count("planveyor_q_small_slice_json <PLAN_PATH>"),
                    4,
                )

    def test_custom_reduced_failure_requires_actual_censor_completion(self) -> None:
        custom = CUSTOM_PROMPT.read_text(encoding="utf-8")
        readme = PLAN_README.read_text(encoding="utf-8")
        failure_key = (
            "REDUCED_REVALIDATION_FAILURE_KEY="
            "(plan_ref,handoff_status,censor_role)"
        )

        self.assertIn(failure_key, custom)
        self.assertIn(failure_key, readme)
        self.assertIn(
            "matching `REDUCED_REVALIDATION_FAILURE_KEY` запрещает "
            "`state=skipped_by_valid_hint`",
            custom,
        )
        self.assertIn(
            "только helper-confirmed `state=complete` снимает failure key",
            custom,
        )
        self.assertIn(
            "только если реально существующий `proof_kind=small_slice_parity` "
            "tuple или matching reduced pending",
            custom,
        )
        self.assertIn(
            "Штатный `verified_handoff=null` или non-opted ordinary "
            "`proof_kind=censor_receipt`",
            custom,
        )
        self.assertIn(
            "только после failed revalidation реально существующего "
            "`proof_kind=small_slice_parity` tuple или matching reduced pending",
            readme,
        )
        self.assertIn(
            "Штатный `verified_handoff=null` и non-opted ordinary "
            "`proof_kind=censor_receipt` не создают key",
            readme,
        )
        self.assertNotIn(
            "verified_handoff(plan_ref, handoff_status, censor_role, "
            "censor_dispatch_id)",
            readme,
        )

        def ordinary_baseline(
            entry_kind: str,
            selector_state: str,
        ) -> list[str]:
            self.assertIn(
                entry_kind,
                {"verified_handoff_null", "ordinary_censor_receipt_non_opted"},
            )
            self.assertIn(selector_state, {"complete", "skipped_by_valid_hint"})
            return [
                entry_kind,
                "no_reduced_attempt",
                "ordinary_cold_gate",
                f"ordinary_selector_{selector_state}",
                "downstream_send",
            ]

        def custom_fallback(
            selector_state: str,
            *,
            post_censor_state: str | None = None,
        ) -> list[str]:
            trace = [
                "current_helper_revalidation_failed",
                "clear_reduced_tuple_pending",
                "set_failure_key",
                "ordinary_cold_gate",
            ]
            if selector_state in {"complete", "skipped_by_valid_hint"}:
                if selector_state == "skipped_by_valid_hint":
                    trace.append("reject_role_authored_skip")
                trace.append("run_ordinary_censor")
                if post_censor_state == "complete":
                    return trace + [
                        "actual_ordinary_censor_complete",
                        "clear_failure_key",
                        "downstream_send",
                    ]
                return trace + ["no_downstream_send"]
            return trace + ["no_downstream_send"]

        for entry_kind in (
            "verified_handoff_null",
            "ordinary_censor_receipt_non_opted",
        ):
            for selector_state in ("complete", "skipped_by_valid_hint"):
                with self.subTest(
                    entry_kind=entry_kind,
                    selector_state=selector_state,
                ):
                    baseline = ordinary_baseline(entry_kind, selector_state)
                    self.assertIn("downstream_send", baseline)
                    self.assertNotIn("set_failure_key", baseline)
                    self.assertNotIn("run_ordinary_censor", baseline)

        skipped = custom_fallback("skipped_by_valid_hint")
        self.assertIn("reject_role_authored_skip", skipped)
        self.assertIn("run_ordinary_censor", skipped)
        self.assertNotIn("downstream_send", skipped)
        self.assertEqual(skipped[-1], "no_downstream_send")

        preexisting_complete = custom_fallback("complete")
        self.assertIn("run_ordinary_censor", preexisting_complete)
        self.assertNotIn("downstream_send", preexisting_complete)

        completed = custom_fallback(
            "skipped_by_valid_hint",
            post_censor_state="complete",
        )
        self.assertLess(
            completed.index("actual_ordinary_censor_complete"),
            completed.index("downstream_send"),
        )
        self.assertEqual(completed[-1], "downstream_send")

    def test_cross_iteration_small_slice_full_loop_and_failure_matrix(self) -> None:
        parity_fields = (
            "plan",
            "requested_profile",
            "expected_bundle_family",
            "helper_validation",
            "drift_behavior",
            "code_draft_path",
            "target_paths",
            "actual_bundle_family",
            "live_review_artifact",
            "review_route_kind",
            "rollout_packet_is_na",
            "visual_acceptance_is_na",
        )
        base_payload = {field: f"value:{field}" for field in parity_fields}
        routing_truth = {
            "plan": "docs/plans/current.md",
            "status": "Ready for Coder",
            "censor_role": "Planner",
            "downstream_role": "Coder",
            "queue_cursor": 7,
        }

        def seed(
            pre: dict[str, object] | None,
            post: dict[str, object] | None,
            *,
            pre_green: bool = True,
            post_green: bool = True,
            oracle_run_id: str | None = "oracle-post",
            invocation: str = "invocation-1",
            lineage: str = "lineage-1",
        ) -> dict[str, object] | None:
            if not pre_green or not post_green or not oracle_run_id:
                return None
            if pre is None or post is None:
                return None
            if set(pre) != set(parity_fields) or set(post) != set(parity_fields):
                return None
            if any(pre[field] != post[field] for field in parity_fields):
                return None
            return {
                "plan_ref": routing_truth["plan"],
                "handoff_status": routing_truth["status"],
                "censor_role": routing_truth["censor_role"],
                "proof_kind": "small_slice_parity",
                "proof_id": (pre.copy(), post.copy(), oracle_run_id),
                "top_level_invocation_lineage": invocation,
                "downstream_role_handle_lineage": lineage,
                "eligible_iteration": 2,
                "consumed": False,
            }

        def consume(
            handoff: dict[str, object] | None,
            *,
            current_payload: dict[str, object] | None,
            current_green: bool = True,
            plan_ref: str = "docs/plans/current.md",
            handoff_status: str = "Ready for Coder",
            censor_role: str = "Planner",
            proof_kind: str = "small_slice_parity",
            proof_id_override: object | None = None,
            invocation: str = "invocation-1",
            lineage: str = "lineage-1",
            current_iteration: int = 2,
        ) -> str:
            if handoff is None or handoff.get("consumed"):
                return "ordinary_censor"
            if not current_green or current_payload is None:
                handoff.clear()
                return "ordinary_censor"
            stored_pre, stored_post, _stored_oracle = handoff["proof_id"]
            if set(current_payload) != set(parity_fields):
                handoff.clear()
                return "ordinary_censor"
            if any(
                current_payload[field] != stored_pre[field]
                or current_payload[field] != stored_post[field]
                for field in parity_fields
            ):
                handoff.clear()
                return "ordinary_censor"
            if current_iteration != handoff["eligible_iteration"]:
                handoff.clear()
                return "ordinary_censor"
            identity = (
                plan_ref,
                handoff_status,
                censor_role,
                proof_kind,
                (
                    handoff["proof_id"]
                    if proof_id_override is None
                    else proof_id_override
                ),
                invocation,
                lineage,
            )
            expected = (
                handoff["plan_ref"],
                handoff["handoff_status"],
                handoff["censor_role"],
                handoff["proof_kind"],
                handoff["proof_id"],
                handoff["top_level_invocation_lineage"],
                handoff["downstream_role_handle_lineage"],
            )
            if identity != expected:
                handoff.clear()
                return "ordinary_censor"
            handoff["consumed"] = True
            return "downstream_send"

        for mode in ("native run", "native run Q", "custom single-plan", "custom queue"):
            with self.subTest(mode=mode):
                before = routing_truth.copy()
                handoff = seed(base_payload, base_payload.copy())
                self.assertIsNotNone(handoff)
                self.assertEqual(
                    consume(handoff, current_payload=base_payload.copy()),
                    "downstream_send",
                )
                self.assertTrue(handoff["consumed"])
                self.assertEqual(
                    consume(handoff, current_payload=base_payload.copy()),
                    "ordinary_censor",
                )
                self.assertEqual(routing_truth, before)

        for field in parity_fields:
            with self.subTest(seed_time_drift=field):
                drifted = base_payload.copy()
                drifted[field] = f"drift:{field}"
                self.assertIsNone(seed(base_payload, drifted))

        incomplete_seed = base_payload.copy()
        incomplete_seed.pop("visual_acceptance_is_na")
        for reason, handoff in (
            ("missing_pre", seed(None, base_payload)),
            ("missing_post", seed(base_payload, None)),
            ("missing_field", seed(base_payload, incomplete_seed)),
            ("pre_red", seed(base_payload, base_payload, pre_green=False)),
            ("post_red", seed(base_payload, base_payload, post_green=False)),
            ("missing_oracle", seed(base_payload, base_payload, oracle_run_id=None)),
            ("restart", None),
        ):
            with self.subTest(reason=reason):
                self.assertIsNone(handoff)
                self.assertEqual(
                    consume(handoff, current_payload=base_payload.copy()),
                    "ordinary_censor",
                )

        for field in parity_fields:
            with self.subTest(post_seed_pre_consume_drift=field):
                current_payload = base_payload.copy()
                current_payload[field] = f"current-drift:{field}"
                handoff = seed(base_payload, base_payload.copy())
                self.assertEqual(
                    consume(handoff, current_payload=current_payload),
                    "ordinary_censor",
                )
                self.assertEqual(handoff, {})

        incomplete_current = base_payload.copy()
        incomplete_current.pop("visual_acceptance_is_na")
        for reason, current_payload, current_green in (
            ("missing_current_helper", None, True),
            ("red_current_helper", base_payload.copy(), False),
            ("current_shape_drift", incomplete_current, True),
        ):
            with self.subTest(reason=reason):
                handoff = seed(base_payload, base_payload.copy())
                self.assertEqual(
                    consume(
                        handoff,
                        current_payload=current_payload,
                        current_green=current_green,
                    ),
                    "ordinary_censor",
                )
                self.assertEqual(handoff, {})

        mismatch_cases = (
            {"plan_ref": "docs/plans/other.md"},
            {"handoff_status": "Ready for Review"},
            {"censor_role": "Coder"},
            {"proof_kind": "censor_receipt"},
            {"proof_id_override": ("other-pre", "other-post", "other-oracle")},
            {"invocation": "invocation-2"},
            {"lineage": "lineage-2"},
            {"current_iteration": 3},
        )
        for mismatch in mismatch_cases:
            with self.subTest(mismatch=mismatch):
                handoff = seed(base_payload, base_payload.copy())
                self.assertEqual(
                    consume(
                        handoff,
                        current_payload=base_payload.copy(),
                        **mismatch,
                    ),
                    "ordinary_censor",
                )
                self.assertEqual(handoff, {})

        def post_consume_loss(mode: str, *, cold_start_cap_spent: bool) -> list[str]:
            trace = ["consume", "first_send_non_green", "clear_tuple_pending_consumed", "no_resend"]
            if mode == "native":
                if cold_start_cap_spent:
                    return trace + [
                        "no_second_censor",
                        "owner_stop:cold-start cap exhausted after downstream handle replacement",
                    ]
                return trace + [
                    "one_ordinary_cold_start_censor",
                    "ordinary_receipt_seed",
                    "consume_new_ordinary_handoff",
                    "downstream_send",
                ]
            return trace + ["helper_owned_non_green_stop", "no_manager_recovery"]

        self.assertEqual(
            post_consume_loss("native", cold_start_cap_spent=False)[-4:],
            [
                "one_ordinary_cold_start_censor",
                "ordinary_receipt_seed",
                "consume_new_ordinary_handoff",
                "downstream_send",
            ],
        )
        self.assertIn(
            "owner_stop:cold-start cap exhausted after downstream handle replacement",
            post_consume_loss("native", cold_start_cap_spent=True),
        )
        custom_loss = post_consume_loss("custom", cold_start_cap_spent=False)
        self.assertEqual(
            custom_loss[-2:],
            ["helper_owned_non_green_stop", "no_manager_recovery"],
        )
        self.assertIn("no_resend", custom_loss)

    def test_post_consume_lost_handle_respawn_respects_invocation_wide_cap(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")

        self.assertIn(
            "cold_start_dispatch_attempted` key включает exact "
            "`plan_ref + handoff_status + censor_role`",
            text,
        )
        self.assertIn("downstream role-handle lineage не входит в key", text)
        self.assertNotIn(
            "`plan_ref + handoff_status + censor_role + current downstream "
            "role-handle lineage`",
            text,
        )
        exhausted_reason = (
            "cold-start cap exhausted after downstream handle replacement"
        )
        self.assertIn(exhausted_reason, text)

        exact_green_index = text.index(
            "только `censor_evidence_lint.state=complete`"
        )
        consume_index = text.index(
            "consume и очисти `verified_handoff`",
            exact_green_index,
        )
        reviewer_send_index = text.index(
            "2. отправь Reviewer-run",
            consume_index,
        )
        generic_send_index = text.index(
            "Запусти роль через `followup_task` (persistent)",
            reviewer_send_index,
        )
        failure_index = text.index(
            "Post-consume lost-handle recovery for mapped handoffs",
            generic_send_index,
        )
        respawn_index = text.index("materialize versioned task этой роли", failure_index)
        no_resend_index = text.index(
            "не повторяй `followup_task`",
            respawn_index,
        )
        cap_check_index = text.index(
            "проверь тот же invocation-wide cap key",
            no_resend_index,
        )
        unspent_index = text.index("если key отсутствует", cap_check_index)
        spent_index = text.index("если key уже есть", unspent_index)
        self.assertLess(consume_index, reviewer_send_index)
        self.assertLess(consume_index, generic_send_index)
        self.assertLess(generic_send_index, failure_index)
        self.assertLess(failure_index, respawn_index)
        self.assertLess(respawn_index, no_resend_index)
        self.assertLess(no_resend_index, cap_check_index)
        self.assertLess(cap_check_index, unspent_index)
        self.assertLess(unspent_index, spent_index)

        failure_block = text[failure_index:spent_index + 500]
        self.assertIn("VERIFIED_HANDOFF_CONSUMED_FOR_SEND=true", failure_block)
        self.assertIn(
            "Reviewer lanes и generic Architect/Planner/Coder mechanics",
            failure_block,
        )
        self.assertIn("сбрось consumed/pending routing state", failure_block)
        self.assertIn("VERIFIED_HANDOFF_CONSUMED_FOR_SEND=false", failure_block)
        self.assertIn("VERIFIED_HANDOFF_CONSUME_PENDING=false", failure_block)
        self.assertIn("не dispatch второй CENSOR", failure_block)
        self.assertIn(exhausted_reason, failure_block)

        unspent_transition = (
            "ordinary post-handoff exact green -> consume -> first followup gets "
            "missing-task -> bounded rematerialize/liveness -> no resend -> one cold-start "
            "CENSOR -> new consume -> first successful downstream followup"
        )
        spent_transition = (
            "cold-start exact green -> consume -> first followup gets missing-task -> "
            "bounded rematerialize/liveness -> no resend -> no second CENSOR -> Owner "
            "stop: cold-start cap exhausted after downstream handle replacement"
        )
        self.assertIn(unspent_transition, failure_block)
        self.assertIn(spent_transition, failure_block)

        def post_consume_lost_handle_trace(
            mechanic: str,
            *,
            proof_source: str,
        ) -> list[str]:
            cap_key = ("plan", "status", "censor")
            attempted_cold_keys: set[tuple[str, str, str]] = set()
            if proof_source == "cold-start":
                attempted_cold_keys.add(cap_key)
            old_lineage = f"{mechanic}:handle-v1"
            new_lineage = f"{mechanic}:handle-v2"
            self.assertNotEqual(old_lineage, new_lineage)

            trace = [
                f"{proof_source} exact green",
                "consume",
                "first followup gets missing-task",
                "bounded rematerialize/liveness",
                "no resend",
            ]
            consumed_for_send = False
            verified_handoff = None
            self.assertFalse(consumed_for_send)
            self.assertIsNone(verified_handoff)

            if cap_key in attempted_cold_keys:
                trace.extend(["no second CENSOR", f"Owner stop: {exhausted_reason}"])
                return trace

            attempted_cold_keys.add(cap_key)
            trace.extend(
                [
                    "one cold-start CENSOR",
                    "new consume",
                    "first successful downstream followup",
                ]
            )
            self.assertIn(cap_key, attempted_cold_keys)
            return trace

        expected_unspent = unspent_transition.split(" -> ")
        expected_spent = spent_transition.split(" -> ")
        for mechanic in ("reviewer", "generic"):
            with self.subTest(mechanic=mechanic, cap="unspent"):
                self.assertEqual(
                    post_consume_lost_handle_trace(
                        mechanic,
                        proof_source="ordinary post-handoff",
                    ),
                    expected_unspent,
                )
            with self.subTest(mechanic=mechanic, cap="spent"):
                self.assertEqual(
                    post_consume_lost_handle_trace(
                        mechanic,
                        proof_source="cold-start",
                    ),
                    expected_spent,
                )

    def test_fake_persistent_thread_timeline_covers_reuse_restart_and_replacement(self) -> None:
        def run_timeline(
            *,
            tuple_matches: bool,
            no_selector: str,
            exact_results: tuple[str, ...] = (),
            owner_authorized_replacement: bool = False,
        ) -> list[str]:
            trace: list[str] = []
            if tuple_matches:
                return ["consume_verified_handoff", "downstream_send"]
            trace.append(f"diagnostic:{no_selector}")
            if no_selector in {"malformed", "ambiguous", "conflicting"}:
                return trace + ["owner_stop"]
            trace.extend(["fresh_dispatch", "same_thread_wait"])
            first = exact_results[0] if exact_results else "incomplete"
            trace.append(f"exact:{first}")
            if first == "complete":
                return trace + ["create_verified_handoff", "next_iteration", "consume_verified_handoff", "downstream_send"]
            trace.append("owner_stop")
            if not owner_authorized_replacement:
                return trace
            trace.extend(["fresh_replacement_id", "correction_only_same_thread_wait"])
            replacement = exact_results[1] if len(exact_results) > 1 else "incomplete"
            trace.append(f"replacement_exact:{replacement}")
            if replacement == "complete":
                return trace + ["create_verified_handoff", "next_iteration", "consume_verified_handoff", "downstream_send"]
            return trace + ["terminal_owner_stop", "no_third_censor"]

        self.assertEqual(
            run_timeline(tuple_matches=True, no_selector="complete"),
            ["consume_verified_handoff", "downstream_send"],
        )
        recovered = run_timeline(
            tuple_matches=False,
            no_selector="complete",
            exact_results=("complete",),
        )
        self.assertEqual(recovered.count("fresh_dispatch"), 1)
        self.assertLess(recovered.index("exact:complete"), recovered.index("downstream_send"))
        self.assertEqual(
            run_timeline(tuple_matches=False, no_selector="ambiguous"),
            ["diagnostic:ambiguous", "owner_stop"],
        )
        replaced = run_timeline(
            tuple_matches=False,
            no_selector="missing",
            exact_results=("incomplete", "complete"),
            owner_authorized_replacement=True,
        )
        self.assertEqual(replaced.count("fresh_dispatch"), 1)
        self.assertIn("fresh_replacement_id", replaced)
        self.assertEqual(replaced[-1], "downstream_send")
        terminal = run_timeline(
            tuple_matches=False,
            no_selector="skip",
            exact_results=("incomplete", "incomplete"),
            owner_authorized_replacement=True,
        )
        self.assertEqual(terminal[-2:], ["terminal_owner_stop", "no_third_censor"])

    def test_fake_native_cold_start_matrix_covers_both_modes_and_all_handoffs(self) -> None:
        mapping = {
            "Architect draft": ("Architect", "Planner"),
            "Ready for Planner": ("Architect", "Planner"),
            "Ready for Coder": ("Planner", "Coder"),
            "Ready for Review": ("Coder", "Reviewer"),
        }

        def cold_start(mode: str, status: str, no_selector: str) -> list[str]:
            self.assertIn(mode, {"run", "run Q"})
            censor_role, downstream_role = mapping[status]
            trace = [f"oracle:{mode}:{status}", f"diagnostic:{no_selector}"]
            if no_selector in {"malformed", "ambiguous", "conflicting"}:
                return trace + ["owner_stop:no_dispatch"]
            return trace + [
                f"fresh_dispatch:{censor_role}",
                f"exact_complete:{censor_role}",
                "create_verified_handoff",
                "next_iteration",
                "consume_verified_handoff",
                f"downstream_send:{downstream_role}",
            ]

        for mode in ("run", "run Q"):
            for status in mapping:
                for no_selector in ("complete", "missing", "stale", "skip"):
                    with self.subTest(
                        mode=mode,
                        status=status,
                        no_selector=no_selector,
                    ):
                        trace = cold_start(mode, status, no_selector)
                        self.assertEqual(
                            len([event for event in trace if event.startswith("fresh_dispatch:")]),
                            1,
                        )
                        self.assertLess(
                            next(i for i, event in enumerate(trace) if event.startswith("exact_complete:")),
                            next(i for i, event in enumerate(trace) if event.startswith("downstream_send:")),
                        )

        item_8 = cold_start("run", "Architect draft", "invalid_skip_hint")
        self.assertLess(
            item_8.index("fresh_dispatch:Architect"),
            item_8.index("downstream_send:Planner"),
        )
        for provenance_failure in ("malformed", "ambiguous", "conflicting"):
            self.assertEqual(
                cold_start("run Q", "Ready for Review", provenance_failure)[-1],
                "owner_stop:no_dispatch",
            )

    def test_native_cold_explicit_plan_path_wins_over_cached_pointer(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")
        self.assertIn("Cold explicit-path recovery regression", text)
        self.assertIn("unusable or stale `.planveyor.planpath`", text)
        self.assertIn("explicit `PLAN_PATH` remains the only plan identity", text)

        def resolve_plan(explicit_plan: str | None, cached_plan: str | None) -> str | None:
            return explicit_plan if explicit_plan else cached_plan

        self.assertEqual(
            resolve_plan("docs/plans/explicit.md", "docs/plans/stale.md"),
            "docs/plans/explicit.md",
        )

    def _direct_recovery_contract_line(self) -> str:
        anchor = "Для Owner-authorized direct recovery `MANAGER_CMD=run current docs-finalize plan`"
        return next(
            line
            for line in COLLAB_PROMPT.read_text(encoding="utf-8").splitlines()
            if anchor in line
        )

    def test_direct_phase_boundary_recovery_does_not_use_queue(self) -> None:
        direct_line = self._direct_recovery_contract_line()

        self.assertIn("literal explicit plan path", direct_line)
        self.assertIn("не читает `.planveyor.planpath`", direct_line)
        self.assertIn("не вызывает queue advance/rebuild/dispatch helpers", direct_line)
        self.assertIn("не читает/не продолжает saved queue plan", direct_line)

    def test_direct_phase_boundary_recovery_stops_at_owner(self) -> None:
        direct_line = self._direct_recovery_contract_line()

        self.assertIn(
            "После green capture-aware closeout этого single-plan recovery terminal stop = `Next: Owner`.",
            direct_line,
        )

    def test_general_checkpoint_phase_order_and_canon_contract_are_literal(self) -> None:
        prompt = COLLAB_PROMPT.read_text(encoding="utf-8")
        readme = PROCESS_IMPROVEMENTS_README.read_text(encoding="utf-8")
        general_order = prompt.index("Architect -> Coder -> Planner -> Reviewer")
        checkpoint = prompt.index("checkpoint-general-pi", general_order)
        followups = prompt.index("ровно четыре `followups` lanes", checkpoint)
        self.assertLess(general_order, checkpoint)
        self.assertLess(checkpoint, followups)
        self.assertIn("eight-record `dispatch_family`", prompt)
        self.assertIn("не является synthetic role/lane", prompt)
        self.assertIn("После returned green receipt четвёртого `general` role", prompt)
        self.assertIn("before_process_improvement_files", readme)
        self.assertIn("after_process_improvement_files", readme)
        self.assertIn("process_improvement_path_results", readme)
        self.assertIn("followup_capture_pi_general_checkpointed", readme)
        self.assertIn("followup_capture_pi_general_checkpoint_already_published", readme)
        for forbidden in ("pathname", "latest", "mtime"):
            self.assertIn(forbidden, readme.lower())

    def test_custom_and_collab_censor_recovery_is_bounded(self) -> None:
        for prompt_path in (CUSTOM_PROMPT, COLLAB_PROMPT):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")

                self.assertIn("reason_code=ambiguous_current_receipt", text)
                self.assertIn("multiple_same_role_status_receipts_without_current_selector", text)
                self.assertIn("не запускай blind rerun", text)
                self.assertIn("не выбирай latest unmarked receipt в Manager", text)
                self.assertIn("complete same-role/status receipt with `current=true`", text)
                self.assertIn("reason_code=missing_or_invalid_fields", text)
                self.assertIn("не запускай repeated blind CENSOR rerun", text)
                self.assertIn("one full structured `current=true` receipt", text)
                self.assertIn("missing_fields", text)
                self.assertIn("invalid_reasons", text)

    def test_custom_and_collab_prompts_do_not_duplicate_censor_marker_checklist(self) -> None:
        forbidden_manual_markers = (
            "`Second opinion:`",
            "`Addendum`",
            "`Context reconciliation:`",
            "`Fixes:`",
            "`Counterfactuals considered:`",
            "missing Second opinion/Addendum/Context reconciliation/Fixes",
        )
        for prompt_path in (CUSTOM_PROMPT, COLLAB_PROMPT):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                for marker in forbidden_manual_markers:
                    self.assertNotIn(marker, text)

    def test_custom_manager_has_cold_start_censor_gate(self) -> None:
        text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        self.assertIn("Cold-start CENSOR gate before downstream routing", text)
        self.assertIn("completed handoff to the next role", text)
        self.assertIn("Ready for Coder` → `<censor-role>=Planner`", text)
        self.assertIn("Ready for Review` → `<censor-role>=Coder`", text)
        self.assertIn("canonical current handoff truth = top-level `censor_evidence_lint.state`", text)
        self.assertIn("summary.complete_receipt_count", text)
        self.assertIn("receipts[].status", text)
        self.assertIn("reason_code=missing_current_receipt", text)
        self.assertIn("не запускай downstream role", text)

    def test_custom_manager_uses_oracle_owner_qna_and_prestatus_readback(self) -> None:
        text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        self.assertIn("plan_status_oracle.py", text)
        self.assertIn("owner_qna_readback_state", text)
        self.assertIn("open_owner_questions[]", text)
        self.assertIn("owner_qna_issues[]", text)
        self.assertIn("PRE_STATUS_LINE` mismatch", text)
        self.assertIn("diagnostic snapshot", text)
        self.assertIn("routing truth = oracle", text)
        self.assertNotIn("Plan changed concurrently", text)
        self.assertNotIn("его значение `**Status:**` совпадает", text)
        self.assertNotIn("`to=Owner` и `status=open`", text)

    def test_custom_manager_role_step_owns_prechecks_and_terminal_closeout_rechecks_dirty(self) -> None:
        text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        for required in (
            "planveyor_runtime_py custom_pipeline_dirty_state.py",
            "schema=custom_pipeline_dirty_state.v1",
            "verdict=continue|stop",
            "files[].ownership_class",
            "safe_next_action",
            "planveyor_custom_role_step",
            "выполняются там ровно один раз до child",
            "dirty_state_blocked",
            "runner_preflight_blocked",
            "terminal closeout",
            "не запускай closeout",
            "не stage/restore/delete/stash/commit",
        ):
            self.assertIn(required, text)

    def test_custom_manager_exact_step_and_invocation_receipt_contract_is_shared(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        role_text = (ROOT / "docs" / "roles" / "manager.md").read_text(encoding="utf-8")
        runtime_text = (ROOT / "scripts" / "planveyor" / "role_runtime.zsh").read_text(
            encoding="utf-8"
        )

        for text in (custom_text, role_text):
            self.assertIn("planveyor_custom_role_step", text)
            self.assertIn("manager_invocation_receipt.v1", text)
            self.assertIn(".planveyor.manager_runs/<invocation_id>.json", text)
            self.assertIn("MANAGER_INVOCATION_ID", text)
            self.assertIn("MANAGER_INVOCATION_RECEIPT_PATH", text)
            self.assertIn("immutable_identity_sha256", text)
            self.assertIn("planveyor_manager_invocation_checkpoint", text)
            self.assertIn("compatibility", text.lower())
            self.assertIn("post-exit queue lineage", text)
            self.assertIn("atomic compatibility publication", text.lower())

        for required in ("not_applicable", "not_evaluated_by_helper"):
            self.assertIn(required, role_text)

        self.assertIn(
            'planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json',
            custom_text,
        )
        self.assertIn("не вызывай `q_next` второй раз", custom_text)
        self.assertIn("не может self-cite", custom_text)
        self.assertIn("status|plan_set", role_text)
        self.assertIn("approval_policy=\"on-request\"", role_text)
        self.assertIn("sandbox_mode=\"workspace-write\"", role_text)
        self.assertIn("compatibility_pointer_write_failed", role_text)
        for reason_code in ("receipt_seed_failed", "receipt_finalization_failed"):
            self.assertIn(reason_code, runtime_text)

        for function_name in (
            "_planveyor_role_run_execute_for_plan",
            "planveyor_custom_role_step",
            "planveyor_manager_invocation_checkpoint",
            "_planveyor_manager_custom_pipeline_supervise",
        ):
            self.assertIn(f"{function_name}()", runtime_text)
        custom_runtime = runtime_text.split(
            "_planveyor_manager_custom_pipeline_supervise()", 1
        )[1]
        self.assertNotIn("--full-auto", custom_runtime)

    def test_collab_manager_names_oracle_owner_qna_fields(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")

        self.assertIn("owner_qna_readback_state", text)
        self.assertIn("open_owner_questions[]", text)
        self.assertIn("owner_qna_issues[]", text)
        self.assertNotIn("не считай “open” по первому совпадению `status=open`", text)

    def test_planning_contour_structural_checks_are_helper_readback_owned(self) -> None:
        required_readback_refs = (
            "planning_contour_role=active_decomposition",
            "planning_contour_role=source_analysis",
            "planning_contour_role=promoted_target|parked_decomposition",
            "planning_contour_readback_state=warning",
            "decomposition_child_state",
            "source_route_state",
            "promoted_from_state",
            "queue_activation_carrier_state",
            "pending_activation",
            "runtime_class",
        )
        forbidden_private_checklist = (
            "owner-visible preview должен назвать child count",
            "если parent описывает широкую бизнес-задачу",
            "promoted child gate должен быть visible",
            "accepted route без materialized",
            "downstream handoff'ы в `**Handoff statuses:**`",
            "Code draft(s): N/A",
        )

        for prompt_path in (COLLAB_PROMPT, ROUTER_PROMPT):
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                for readback_ref in required_readback_refs:
                    self.assertIn(readback_ref, text)
                for private_check in forbidden_private_checklist:
                    self.assertNotIn(private_check, text)

    def test_human_policy_stops_before_both_native_materialization_branches(self) -> None:
        architect = ARCHITECT_PROMPT.read_text(encoding="utf-8")
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        ordinary = architect.split("  - Если это обычный dev-plan:", 1)[1].split("[/E_ARCH_REVIEW]", 1)[0]
        human, native = ordinary.split("Если `COMMIT_POLICY=native_existing`", 1)
        for required in ("COMMIT_POLICY=human_explicit", "Вердикт: принято.",
                         "Architect arch review", "не требуй `staged_exact`/`commit_ready`",
                         "до первого `--stage`", "parent-complete sync", "sibling close --commit"):
            self.assertIn(required, human)
        self.assertNotIn("сделай exact `--stage` accepted bundle", human)
        self.assertNotIn("поставь `**Status:** Done`", human)
        self.assertIn("сделай exact `--stage` accepted bundle", native)
        self.assertIn("planveyor_plan_closeout_preflight", native)
        self.assertIn("safe_command", native)
        docs_human = collab.split("При `COMMIT_POLICY=human_explicit` и fresh `final_docs_commit=required`", 1)[1]
        docs_human, docs_native = docs_human.split("Только при `COMMIT_POLICY=native_existing` выполняй automatic final writer branch:", 1)
        for required in ("до automatic writer-handoff", "не dispatch-ь Architect final commit task",
                         "не stage/commit/amend", "existing `planveyor sibling close`", "exact current plan/cycle"):
            self.assertIn(required, docs_human)
        self.assertNotIn("planveyor_plan_bundle --commit-exact", docs_human)
        self.assertIn("planveyor_plan_bundle --commit-exact", docs_native)
        self.assertIn("final docs-only handoff did not land proof", docs_native)

    def test_current_policy_forwarding_covers_bootstrap_reused_and_capture_messages(self) -> None:
        collab = COLLAB_PROMPT.read_text(encoding="utf-8")
        forwarding = next(line for line in collab.splitlines() if line.startswith("- В каждом role message передавай"))
        for required in ("ровно одно literal `COMMIT_POLICY", "fresh bootstrap/init", "persistent `followup_task`",
                         "CENSOR", "Reviewer lanes", "docs-finalize lanes", "Manager → Architect semantic Arch review",
                         "reused/resumed", "reset/bootstrap", "История thread не заменяет"):
            self.assertIn(required, forwarding)
        self.assertIn("<prepared_message>` содержит current literal `COMMIT_POLICY`", collab)
        self.assertIn("Human semantic pause проверяй перед любым downstream dispatch", collab)
        self.assertIn("current green review", collab)
        self.assertIn("не является human blocker", collab)
        for prompt in (collab, ARCHITECT_PROMPT.read_text(encoding="utf-8")):
            self.assertIn("control header **текущего task**", prompt)
            self.assertIn("Present-empty, неизвестное", prompt)
            self.assertIn("quoted Owner answers", prompt)

    def test_closeout_preflight_state_split_is_prompt_contract(self) -> None:
        manager_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        architect_text = ARCHITECT_PROMPT.read_text(encoding="utf-8")

        self.assertIn('planveyor_plan_closeout_preflight "$PLAN_PATH"', manager_text)
        self.assertIn("closeout_state", manager_text)
        self.assertIn("next_owner", manager_text)
        self.assertIn("safe_command", manager_text)
        self.assertIn("closeout-only blocker", manager_text)
        self.assertIn("не повод запускать full semantic rerun narration", manager_text)
        for readback_ref in (
            "Owner-facing terminal readback block",
            "status_line",
            "status_norm",
            "git status --short",
            "git log -1 --oneline",
            "single-plan `planveyor_plan_closeout_preflight`",
            "docs-closeout family",
            "planveyor_q_closeout_json",
        ):
            self.assertIn(readback_ref, manager_text)

        self.assertIn("planveyor_plan_closeout_preflight <PLAN_PATH>", architect_text)
        self.assertIn("closeout_state=commit_ready", architect_text)
        self.assertIn("git_writable=true", architect_text)
        self.assertIn("safe_command!=null", architect_text)
        self.assertIn("closeout_state=closeout_blocked_git_metadata", architect_text)
        self.assertIn("не запускай full semantic rerun narration", architect_text)
        self.assertNotIn("сначала запиши `**Status:** Done`", architect_text)
        self.assertIn("не меняя `**Status:**` на `Done`", architect_text)
        self.assertIn("pre-Done `planveyor_plan_closeout_preflight <PLAN_PATH>`", architect_text)
        self.assertLess(
            architect_text.index("не меняя `**Status:**` на `Done`"),
            architect_text.index("поставь `**Status:** Done`"),
        )
        self.assertIn("parent/umbrella sync", architect_text)
        self.assertIn("closeout_state=already_materialized", architect_text)
        self.assertIn("closeout_pending", architect_text)
        for transactional_ref in (
            "Pre-Done `CURRENT-REVIEW-RED`",
            "authoritative review artifact/oracle/lint readback for current bundle is green",
            "stale red without fixed evidence",
            "fail-closed",
            "не дописывай новый plan evidence tail",
            "post-commit dirty plan state",
        ):
            self.assertIn(transactional_ref, architect_text)

    def test_architect_predone_simulated_lint_and_cleanup_order_is_contract(self) -> None:
        architect_text = ARCHITECT_PROMPT.read_text(encoding="utf-8")
        readme_text = PLAN_README.read_text(encoding="utf-8")
        runtime_lint = '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py'

        for carrier, text, first_stage_marker, restage_marker, lint_prefix in (
            (
                "architect prompt",
                architect_text,
                "сделай exact `--stage` accepted bundle",
                "повтори exact `--stage`",
                runtime_lint,
            ),
            (
                "plan README",
                readme_text,
                "green разрешает первую exact `--stage`",
                "exact restage",
                runtime_lint,
            ),
        ):
            with self.subTest(carrier=carrier):
                simulated_command = lint_prefix + ' --as-status Done "$PLAN_PATH"'
                ordinary_command = lint_prefix + ' "$PLAN_PATH"'
                simulated_index = text.index(simulated_command)
                first_stage_index = text.index(first_stage_marker, simulated_index)
                provisional_index = text.index("provisional `Done`", first_stage_index)
                ordinary_index = text.index(ordinary_command, provisional_index)
                restage_index = text.index(restage_marker, ordinary_index)
                commit_index = text.index("exact local commit", restage_index)

                self.assertLess(simulated_index, first_stage_index)
                self.assertLess(first_stage_index, provisional_index)
                self.assertLess(provisional_index, ordinary_index)
                self.assertLess(ordinary_index, restage_index)
                self.assertLess(restage_index, commit_index)
                provisional_window = text[provisional_index : ordinary_index + len(ordinary_command)]
                self.assertIn(
                    "до любого повторного exact `--stage`, final preflight или commit",
                    provisional_window,
                )
                self.assertIn("failed terminal transition cleanup", text[ordinary_index:commit_index])
                self.assertIn("Architect arch review", text[ordinary_index:commit_index])
                self.assertIn("worktree", text[ordinary_index:commit_index])
                self.assertIn("index", text[ordinary_index:commit_index])

        self.assertIn("это existing lint pipeline, а не отдельная authority", architect_text)
        self.assertIn("не создаёт отдельную lint authority", readme_text)

    def test_docs_closeout_payload_schema_gate_is_prompt_contract(self) -> None:
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        manager_role_text = (ROOT / "docs" / "roles" / "manager.md").read_text(encoding="utf-8")
        adr_text = (ROOT / "docs" / "adr" / "004-exact-bundle-truth-and-closeout.md").read_text(encoding="utf-8")

        for text in (collab_text, manager_role_text, adr_text):
            self.assertIn("schema=docs_closeout_payload.v1", text)
            self.assertIn("schema_state=ok|blocked", text)
            self.assertIn("schema_errors=[]", text)

        self.assertIn("docs_closeout_payload_schema_blocked", collab_text)
        self.assertIn(
            'planveyor_q_stop_json docs_closeout_payload_schema_blocked --source-plan "$docs_closeout_plan"',
            collab_text,
        )
        self.assertIn(
            'planveyor_q_stop_json docs_closeout_blocked --source-plan "$docs_closeout_plan"',
            collab_text,
        )
        self.assertEqual(
            collab_text.count(
                'planveyor_q_stop_json docs_closeout_process_improvement_capture_blocked '
                '--source-plan "$docs_closeout_plan"'
            ),
            2,
        )
        self.assertNotIn("`planveyor_q_stop_json docs_closeout_payload_schema_blocked`", collab_text)
        self.assertNotIn("`planveyor_q_stop_json docs_closeout_blocked`", collab_text)
        self.assertNotIn(
            "`planveyor_q_stop_json docs_closeout_process_improvement_capture_blocked`",
            collab_text,
        )
        self.assertIn("literal `schema_errors`", collab_text)
        self.assertIn("не делай ручную nested-field validation", collab_text)
        self.assertIn("не пытайся вручную дочитать/исправить missing nested fields", collab_text)

        self.assertIn("custom не dispatch-ит docs-closeout family", custom_text)
        self.assertIn("не добавляет docs-closeout automation", custom_text)

    def test_terminal_docs_closeout_lifecycle_catch_all_preserves_source_scope(self) -> None:
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")

        queue_advance_index = collab_text.index(
            "если helper вернул `advanced=true` и `next_plan`"
        )
        source_materialized_index = collab_text.index(
            "Иначе определи `docs_closeout_plan`",
            queue_advance_index,
        )
        final_handoff_failure_index = collab_text.index(
            "Если после одного automatic Architect handoff",
            source_materialized_index,
        )
        terminal_catch_all_index = collab_text.index(
            "Любой bounded exit path внутри terminal docs-closeout tail",
            final_handoff_failure_index,
        )
        ordinary_catch_all_index = collab_text.index(
            "Любой ordinary non-terminal exit path вне terminal docs-closeout tail",
            terminal_catch_all_index,
        )

        self.assertLess(queue_advance_index, source_materialized_index)
        self.assertLess(source_materialized_index, final_handoff_failure_index)
        self.assertLess(final_handoff_failure_index, terminal_catch_all_index)
        self.assertLess(terminal_catch_all_index, ordinary_catch_all_index)
        self.assertIn(
            "final docs-only handoff did not land proof",
            collab_text[final_handoff_failure_index:terminal_catch_all_index],
        )
        self.assertIn(
            "source-aware terminal-tail catch-all ниже",
            collab_text[final_handoff_failure_index:terminal_catch_all_index],
        )

        terminal_line_end = collab_text.index("\n", terminal_catch_all_index)
        terminal_line = collab_text[terminal_catch_all_index:terminal_line_end]
        self.assertIn("final docs-only handoff did not land proof", terminal_line)
        self.assertIn(
            'planveyor_q_stop_json <bounded_reason> --source-plan "$docs_closeout_plan"',
            terminal_line,
        )
        self.assertNotIn(
            "`planveyor_q_stop_json <bounded_reason>`",
            collab_text[source_materialized_index:terminal_line_end],
        )

        ordinary_line_end = collab_text.index("\n", ordinary_catch_all_index)
        ordinary_line = collab_text[ordinary_catch_all_index:ordinary_line_end]
        self.assertIn("planveyor_q_stop_json <bounded_reason>", ordinary_line)
        self.assertNotIn("--source-plan", ordinary_line)

    def test_terminal_tail_source_checkpoint_blocks_future_role_dispatch(self) -> None:
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")

        source_index = collab_text.index("Иначе определи `docs_closeout_plan`")
        blocked_index = collab_text.index("Если helper вернул `state=blocked`", source_index)
        required_index = collab_text.index(
            "Если fresh helper вернул `final_docs_commit=required`",
            source_index,
        )
        clean_index = collab_text.index(
            "Если fresh helper вернул `final_docs_commit=no_op|landed`",
            required_index,
        )
        checkpoint_index = collab_text.index(
            "Queue mode не должен терять continuation checkpoint",
            clean_index,
        )

        self.assertLess(source_index, blocked_index)
        self.assertLess(blocked_index, required_index)
        self.assertLess(required_index, clean_index)
        self.assertLess(clean_index, checkpoint_index)
        self.assertIn(
            'planveyor_q_stop_json docs_closeout_blocked --source-plan "$docs_closeout_plan"',
            collab_text[blocked_index:required_index],
        )
        self.assertIn(
            "Dispatch'ь Architect final docs-only handoff",
            collab_text[required_index:clean_index],
        )
        self.assertIn(
            "fresh helper proof = `final_docs_commit=no_op|landed`",
            collab_text[required_index:checkpoint_index],
        )
        checkpoint_window = collab_text[checkpoint_index:]
        self.assertIn("docs-closeout tail для `docs_closeout_plan`", checkpoint_window)
        self.assertIn("role execution следующего active item не стартует", checkpoint_window)

    def test_terminal_canon_scope_expiry_precedes_generic_exact_commit(self) -> None:
        general_prompts = (
            ROOT / "docs" / "tools" / "prompts" / "architect_docs_finalize_general.md",
            ROOT / "docs" / "tools" / "prompts" / "planner_docs_finalize_general.md",
            ROOT / "docs" / "tools" / "prompts" / "coder_docs_finalize_general.md",
            ROOT / "docs" / "tools" / "prompts" / "reviewer_docs_finalize_general.md",
        )
        for prompt_path in general_prompts:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                self.assertIn("semantic `Done|Superseded`", text)
                self.assertIn("historical `code_draft_meta.targets`", text)
                self.assertIn("только provenance", text)
                self.assertIn("отдельный live non-terminal execution carrier", text)
                self.assertIn("pre-terminal exact-bundle closeout", text)
                self.assertNotIn("через уже explicit terminal plan scope", text)

        architect_text = general_prompts[0].read_text(encoding="utf-8")
        self.assertIn("не дописывай даже append-only findings", architect_text)

        pi_readme = PROCESS_IMPROVEMENTS_README.read_text(encoding="utf-8")
        self.assertIn("historical `code_draft_meta.targets`", pi_readme)
        self.assertIn("отдельный live non-terminal execution carrier", pi_readme)
        self.assertIn("исходным pre-terminal exact-bundle closeout", pi_readme)

        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        self.assertIn("Узкий terminal protected verdict", collab_text)
        self.assertIn("Historical target membership и promoted PI pointer здесь только provenance", collab_text)
        protected_index = collab_text.index(
            "Если fresh helper вернул `final_docs_commit_reason=canon_delta_requires_process_improvement`"
        )
        generic_required_index = collab_text.index(
            "Если fresh helper вернул `final_docs_commit=required`",
            protected_index,
        )
        exact_commit_index = collab_text.index(
            "planveyor_plan_bundle --commit-exact",
            generic_required_index,
        )
        self.assertLess(protected_index, generic_required_index)
        self.assertLess(generic_required_index, exact_commit_index)
        protected_window = collab_text[protected_index:generic_required_index]
        self.assertIn("не запускай `planveyor_plan_bundle --commit-exact`", protected_window)
        self.assertIn("отдельно promoted live non-terminal execution carrier", protected_window)
        self.assertIn("fresh `final_docs_commit=no_op|landed`", protected_window)
        self.assertIn("future role не dispatch-ится", protected_window)

    def test_docs_finalize_followups_output_contract_is_not_collector_input(self) -> None:
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        followups_prompts = (
            ROOT / "docs" / "tools" / "prompts" / "architect_docs_finalize_followups.md",
            ROOT / "docs" / "tools" / "prompts" / "coder_docs_finalize_followups.md",
            ROOT / "docs" / "tools" / "prompts" / "planner_docs_finalize_followups.md",
            ROOT / "docs" / "tools" / "prompts" / "reviewer_docs_finalize_followups.md",
        )

        self.assertIn("для `general` docs-finalize lanes stdout является collector input", collab_text)
        self.assertIn("parseable `Process improvements` section", collab_text)
        self.assertIn("для `followups` docs-finalize lanes stdout не является collector input", collab_text)
        self.assertIn("валидный no-op output = exact `NO FOLLOWUPS`", collab_text)
        self.assertIn('`Created: <path>` только после `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_lint.py <path>` exit 0', collab_text)
        self.assertIn("без leading `-` = role/output blocker", collab_text)
        self.assertIn("scripts/process_improvements_collect.py", collab_text)
        self.assertIn("--followups-capture-cycle-id <capture_cycle_id> --input - --json", collab_text)
        self.assertIn("PI capture clean/materialized/already_tracked не закрывает ordinary followups proof", collab_text)
        self.assertIn("Terminal plan не ремонтируй", collab_text)
        self.assertIn("followups_capture_cycle_id", collab_text)
        self.assertIn("prepare-role", collab_text)
        self.assertIn("finalize-role", collab_text)
        self.assertIn("Не представляй `process_improvement_capture_state=clean_noop|materialized|already_tracked`", collab_text)

        for prompt_path in followups_prompts:
            with self.subTest(prompt=prompt_path.name):
                text = prompt_path.read_text(encoding="utf-8")
                self.assertIn("exact shared heading token `Process improvements`", text)
                self.assertIn("здесь не дублируй их отдельной псевдосекцией", text)
                self.assertIn("NO FOLLOWUPS", text)
                self.assertIn("не меняй ни при каких `followups_reconciliation_state`", text)
                self.assertIn("`plan_meta.followups_out` byte-immutable", text)
                self.assertIn("`open|unknown` = blocker upstream pre-Done contract", text)
                self.assertIn("не ремонтируй terminal plan", text)
                self.assertIn("exact `source_ref=<Manager-fed plan_ref>`", text)
                self.assertIn("ровно одной active lint-green row", text)
                self.assertIn("один bare `Created: docs/followups/<name>.md`", text)
                self.assertIn("output ровно `NO FOLLOWUPS`", text)
                self.assertIn(
                    "Успешный output `Created:` разрешён только после того, как "
                    '`"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_lint.py <created path>` завершился с exit 0',
                    text,
                )
                self.assertIn("без leading `-` malformed", text)
                self.assertIn("а не created follow-up", text)
                self.assertNotIn("кроме bounded repair", text)
                self.assertNotIn("## Process improvements", text)

    def test_terminal_followups_capture_and_exact_commit_contract_is_explicit(self) -> None:
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        architect_text = ARCHITECT_PROMPT.read_text(encoding="utf-8")
        template_text = (
            ROOT / "docs" / "followups" / "_template_followups_backlog.md"
        ).read_text(encoding="utf-8")

        for text in (collab_text,):
            self.assertIn("followups_capture_cycle_id", text)
            self.assertIn("prepare-role", text)
            self.assertIn("finalize-role", text)
            self.assertIn("--retry-of-capture-cycle-id", text)
            self.assertIn("--followups-capture-cycle-id <capture_cycle_id>", text)
            self.assertIn("current_plan_owned_docs_delta_paths", text)
            self.assertIn("foreign_docs_delta_paths", text)
            self.assertIn("blocked_docs_delta_paths", text)

        self.assertIn("создаёт новый UUID", collab_text)

        exact_pipeline = (
            "planveyor_docs_closeout <plan_ref> --followups-capture-cycle-id <capture_cycle_id> --json | "
            "planveyor_plan_closeout_preflight --docs-closeout-json - --json <plan_ref> | "
            "planveyor_plan_bundle --commit-exact --preflight-json - --message-auto <plan_ref>"
        )
        for text in (collab_text, architect_text):
            self.assertIn(exact_pipeline, text)
        self.assertNotIn("--message-file <message_file>", collab_text)
        self.assertNotIn("--message-file <message_file>", architect_text)
        self.assertNotIn("private transient `0600` message file", architect_text)
        self.assertIn("whole machine payload", collab_text)
        self.assertIn("independent workstream/queue stop", collab_text)
        self.assertIn("commit-tree", architect_text)
        self.assertIn("update-ref", architect_text)

        self.assertIn("terminal plan byte-immutable", template_text)
        self.assertIn("exact `source_ref=<terminal plan path>`", template_text)
        self.assertIn("transient-only", template_text)
        self.assertIn("source_ref=<exact source path>", template_text)

    def test_generic_claude_runner_preflight_is_custom_pipeline_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        runbook_text = OWNER_RUNBOOK.read_text(encoding="utf-8")
        runbook_ru_text = OWNER_RUNBOOK_RU.read_text(encoding="utf-8")
        facade_text = (ROOT / "scripts" / "planveyor.zsh").read_text(encoding="utf-8")
        provider_text = (
            ROOT / "scripts" / "planveyor" / "provider_runtime.zsh"
        ).read_text(encoding="utf-8")
        role_runtime_text = (
            ROOT / "scripts" / "planveyor" / "role_runtime.zsh"
        ).read_text(encoding="utf-8")

        for marker in (
            "Runner selection принадлежит Owner/runtime policy.",
            "preflight возвращает non-green reason/remediation, остановись до child",
            "fresh preflight только для своей invocation",
            "runner_preflight_blocked",
            "no-child stop",
            'planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json',
            "schema_version=role_execution_receipt.v1",
            "matching `target_plan`, `session_key`, `pre_status`, just-returned `run_id`",
        ):
            self.assertIn(marker, custom_text)

        for marker in (
            "child-only facade",
            "Do not source implementation shell files into a parent shell.",
            "Owner chooses the operating mode and any runner available to the installed runtime.",
            "Manager may coordinate the selected roles, but it does not silently change the Owner-controlled runner, authentication source, project, or plan.",
            "Do not resolve a runtime or authorization blocker by copying credentials, sourcing implementation files",
        ):
            self.assertIn(marker, runbook_text)
        for marker in (
            "фасад, который выполняет команды только в дочернем процессе",
            "Не подключайте shell-скрипты реализации к родительской оболочке через `source`.",
            "Owner выбирает режим работы и любой агентный харнес, который доступен установленной копии Planveyor.",
            "Manager может координировать выбранные роли, но не меняет молча агентный харнес, источник аутентификации, проект или план, которыми распоряжается Owner.",
            "Если мешает блокер среды выполнения или авторизации, не копируйте учётные данные, не подключайте файлы реализации через `source`",
        ):
            self.assertIn(marker, runbook_ru_text)

        self.assertIn(
            "architect:codex|coder:codex|manager:codex|planner:codex|planner:claude|reviewer:codex|reviewer:claude",
            facade_text,
        )
        for marker in (
            "provider_provenance_invalid",
            "configured_model_mismatch",
            "configured_effort_mismatch",
            "missing_init_run_capture",
            "init_run_nonzero",
            "init_run_configured_model_mismatch",
            "init_run_configured_effort_mismatch",
            "use_consumer_claude_cli",
            "set_or_clear_PLANVEYOR_CLAUDE_MODEL",
            "set_or_clear_PLANVEYOR_CLAUDE_EFFORT",
            "rerun_role_init_after_fix",
            "inspect_init_meta_then_rerun_init",
            "configured_model_id",
            "model_id_state",
            "configured_effort",
            "effort_state",
            "configured_explicit",
            "consumer_default",
            "execution_ready",
            "remediation",
        ):
            self.assertIn(marker, facade_text)

        for marker in (
            "PLANVEYOR_CLAUDE_COMMAND",
            "PLANVEYOR_CLAUDE_MODEL",
            "PLANVEYOR_CLAUDE_EFFORT",
            "print -r -- 'direct_child'",
        ):
            self.assertIn(marker, provider_text)

        preflight_start = role_runtime_text.index(
            'preflight_json="$(planveyor_role_runner_preflight "$role_arg" --json 2>/dev/null)"'
        )
        execute_start = role_runtime_text.index(
            "_planveyor_role_run_execute_for_plan", preflight_start
        )
        preflight_block = role_runtime_text[preflight_start:execute_start]
        self.assertIn(
            "_planveyor_custom_role_step_emit blocked runner_preflight_blocked",
            preflight_block,
        )
        self.assertIn("return 125", preflight_block)

        for text in (custom_text, runbook_text, runbook_ru_text):
            for obsolete_contract in (
                "planveyor_zsh_dotfiles_install",
                "missing_login_shell_runner",
                "run_dotfiles_check_then_explicit_install",
                "align_zai_",
                "glm-5.3[1m]",
                "full `.zshrc`",
            ):
                self.assertNotIn(obsolete_contract, text)

    def test_role_execution_receipts_are_custom_pipeline_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        for marker in (
            "fresh proof = `.planveyor.role_runs/<run_id>.json`",
            "`schema_version=role_execution_receipt.v1`",
            "matching `target_plan`, `session_key`, `pre_status`, just-returned `run_id`",
            "canonical `elapsed_seconds`/`terminated_by_timeout`",
            "retained aliases `duration_seconds`/`timed_out`",
        ):
            self.assertIn(marker, custom_text)

        runtime_text = (ROOT / "scripts" / "planveyor" / "role_runtime.zsh").read_text(
            encoding="utf-8"
        )
        execute_start = runtime_text.index("_planveyor_role_run_execute_for_plan() {")
        custom_start = runtime_text.index("planveyor_custom_role_step() {")
        execute_text = runtime_text[execute_start:custom_start]
        custom_end = runtime_text.index("planveyor_arch() {", custom_start)
        custom_runtime = runtime_text[custom_start:custom_end]

        capture = 'status_pre="$(planveyor_status_line "$plan_path")" || { popd >/dev/null; return 1; }'
        receipt_pre = '"pre_status=${status_pre}"'
        primary_check = (
            'primary_readback="$(_planveyor_role_run_check_json "$receipt_path" "$run_id" '
            '"$session_key" "$plan_path" "$status_pre")"'
        )
        for marker in (capture, receipt_pre, primary_check):
            self.assertIn(marker, execute_text)
        self.assertLess(execute_text.index(capture), execute_text.index(receipt_pre))
        self.assertLess(execute_text.index(receipt_pre), execute_text.index(primary_check))

        execution_call = (
            'execution_json="$(_planveyor_role_run_execute_for_plan "${execute_args[@]}" '
            '--preflight-proof "$preflight_json")"'
        )
        readback_propagation = (
            'readback_state=*) execution_readback_state="${row#readback_state=}"'
        )
        readback_gate = (
            'if (( execution_rc != 0 )) || [[ "$execution_state" != "success" '
            '|| "$execution_readback_state" != "ok" ]]; then'
        )
        completed = "_planveyor_custom_role_step_emit completed execution_receipt_valid"
        for marker in (execution_call, readback_propagation, readback_gate, completed):
            self.assertIn(marker, custom_runtime)
        self.assertLess(custom_runtime.index(execution_call), custom_runtime.index(readback_propagation))
        self.assertLess(custom_runtime.index(readback_propagation), custom_runtime.index(readback_gate))
        self.assertLess(custom_runtime.index(readback_gate), custom_runtime.index(completed))

    def test_role_outcome_receipt_activation_and_placement_matrix(self) -> None:
        planner_text = PLANNER_PROMPT.read_text(encoding="utf-8")
        coder_text = CODER_PROMPT.read_text(encoding="utf-8")
        reviewer_text = REVIEWER_PROMPT.read_text(encoding="utf-8")

        for text in (planner_text, coder_text, reviewer_text):
            self.assertIn("Profile-scoped role outcome receipt", text)
            self.assertIn("exact row `Mode: manager-custom-pipeline`", text)
            self.assertIn("ordinary plan или missing/alternate mode row", text)
            self.assertIn("successful handoff, blocker или reroute", text)
            self.assertIn("ровно один block с exact marker row `- Role outcome semantic draft`", text)
            self.assertIn("`worked`, `blocked_by`, `helped_by`, `residuals`, `candidate_followups`, `gates`", text)
            self.assertIn("любой другой envelope запрещены", text)

        self.assertIn("`PLAN_PATH::## Evidence`", planner_text)
        self.assertIn("Current-run identity и canonical placement принадлежат supervisor/family helper", planner_text)
        self.assertIn("`PLAN_PATH::## Evidence`", coder_text)
        self.assertIn("Current-run identity и canonical placement принадлежат supervisor/family helper", coder_text)
        self.assertIn("`reviewer_code_risk` пишет draft только в plan-resident lane evidence", reviewer_text)
        self.assertIn("`reviewer_code_contracts` пишет draft только в единственный live review artifact", reviewer_text)
        self.assertIn("Не дублируй outcome между plan и review artifact", reviewer_text)

    def test_role_outcome_receipt_shape_identity_and_missing_run_blocker(self) -> None:
        emitter_texts = (
            PLANNER_PROMPT.read_text(encoding="utf-8"),
            CODER_PROMPT.read_text(encoding="utf-8"),
            REVIEWER_PROMPT.read_text(encoding="utf-8"),
        )
        semantic = "`worked`, `blocked_by`, `helped_by`, `residuals`, `candidate_followups`, `gates`"

        for text in emitter_texts:
            self.assertIn(semantic, text)
            self.assertIn("`1..3` коротких nested bullets", text)
            self.assertIn("ровно один `N/A (why=...)`", text)
            self.assertIn("JSON, fenced transcript, raw logs", text)
            self.assertIn("`plan=null` с причиной и promotion trigger", text)
            for field in ("`role`", "`lane`", "`run_id`", "`target_plan`", "`artifact_ref`", "`written_at`", "`state`"):
                self.assertIn(field, text)
            self.assertIn("не читает и не копирует `PLANVEYOR_ROLE_RUN_ID`", text)
            self.assertIn("не создаёт fallback identity", text)
            self.assertIn("не пишет finalized `Role outcome receipt`", text)
            self.assertIn("helper атомарно добавляет", text)

    def test_role_outcome_semantic_lint_and_bounded_recovery_contract(self) -> None:
        emitter_texts = (
            PLANNER_PROMPT.read_text(encoding="utf-8"),
            CODER_PROMPT.read_text(encoding="utf-8"),
            REVIEWER_PROMPT.read_text(encoding="utf-8"),
        )
        lint_command = (
            '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py role_outcome_receipt.py lint-draft '
            '--project-root "$root" --plan "$PLAN_PATH" --role "$role" --format json'
        )

        for text in emitter_texts:
            for marker in (
                lint_command,
                "state=valid/reason_code=ok",
                "`rc=125/state=invalid`",
                "`rc=126/state=blocked`",
                "Lint ничего не мутирует",
                "не заменяет authoritative post-exit finalizer",
            ):
                self.assertIn(marker, text)

    def test_manager_exact_matches_role_outcome_and_fails_closed(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        runtime_text = (ROOT / "scripts" / "planveyor" / "role_runtime.zsh").read_text(
            encoding="utf-8"
        )

        for marker in (
            'planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json',
            "`runner_preflight_blocked` означает no-child stop",
            "fresh proof = `.planveyor.role_runs/<run_id>.json`",
            "Не меняй routing по одному `exit_code=0`",
        ):
            self.assertIn(marker, custom_text)

        receipt_start = runtime_text.index(
            'if [[ -z "${receipt_path//[[:space:]]/}" || ! -f "$receipt_path" ]]; then'
        )
        completed_marker = "_planveyor_custom_role_step_emit completed execution_receipt_valid"
        receipt_end = runtime_text.index(completed_marker, receipt_start) + len(completed_marker)
        receipt_block = runtime_text[receipt_start:receipt_end]
        missing = receipt_block.index("execution_receipt_missing")
        checked = receipt_block.index("! planveyor_role_run_receipt_check")
        invalid = receipt_block.index("execution_receipt_invalid", checked)
        completed = receipt_block.index(completed_marker)
        self.assertLess(missing, checked)
        self.assertLess(checked, invalid)
        self.assertLess(invalid, completed)

    def test_role_outcome_does_not_expand_native_execution_receipt_schema(self) -> None:
        for text in (
            PLANNER_PROMPT.read_text(encoding="utf-8"),
            CODER_PROMPT.read_text(encoding="utf-8"),
            REVIEWER_PROMPT.read_text(encoding="utf-8"),
        ):
            self.assertIn("semantic draft", text)
            self.assertIn("не создаёт fallback identity", text)
            self.assertIn("не пишет finalized `Role outcome receipt`", text)

    def test_reviewer_risk_lane_selector_readback_is_helper_backed_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        reviewer_text = REVIEWER_PROMPT.read_text(encoding="utf-8")
        reviewer_role_text = (ROOT / "docs" / "roles" / "reviewer.md").read_text(encoding="utf-8")
        canon_text = (ROOT / "docs" / "playbooks" / "review_route_and_receipt_canon.md").read_text(encoding="utf-8")
        selector_command = (
            '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --project-root "$root" '
            '--select-risk-lane --origin-plan "$PLAN_PATH" --json'
        )

        for text in (custom_text, collab_text, reviewer_text):
            self.assertIn(selector_command, text)
            self.assertIn("schema_version=reviewer_risk_lane_selection.v1", text)
            self.assertIn("state=selected", text)
            self.assertIn("state=missing|blocked", text)

        self.assertIn("canonical current risk-lane truth", custom_text)
        self.assertIn("а не первый JSON block/thread memory", custom_text)
        self.assertIn("helper-selected current block", reviewer_text)
        self.assertNotIn("current выбирается helper semantics (`current=true`", custom_text)
        self.assertNotIn("explicit `current=true`, иначе latest sortable", reviewer_text)

        custom_risk = custom_text.index('planveyor_custom_role_step reviewer_code_risk --plan "$PLAN_PATH" --json')
        custom_selector = custom_text.index(selector_command, custom_risk)
        custom_contracts = custom_text.index('planveyor_custom_role_step reviewer_code_contracts --plan "$PLAN_PATH" --json', custom_selector)
        self.assertLess(custom_risk, custom_selector)
        self.assertLess(custom_selector, custom_contracts)

        collab_section = collab_text[
            collab_text.index("4c) Reviewer logical dispatch") : collab_text.index("5) Consumption permission")
        ]
        collab_risk = collab_section.index("REVIEWER_LANE=reviewer_code_risk")
        collab_selector = collab_section.index(selector_command)
        collab_contracts = collab_section.index("REVIEWER_LANE=reviewer_code_contracts")
        self.assertLess(collab_risk, collab_selector)
        self.assertLess(collab_selector, collab_contracts)
        self.assertNotIn("current=true` wins, otherwise latest sortable", collab_section)

        for text in (custom_text, collab_text, reviewer_text, reviewer_role_text, canon_text):
            self.assertIn("state=selected` + exit `0`", text)
            self.assertIn("Manager/Owner не редактируют", text)
            self.assertIn("immutable support/compact pair", text)
        for text in (custom_text, collab_text):
            self.assertIn("не dispatch-ь `reviewer_code_contracts`", text)

        final_lint_command = (
            '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py '
            '--origin-plan "$PLAN_PATH" <review_artifact>'
        )
        legacy_final_lint_command = (
            "scripts/review_artifact_lint.py --origin-plan PLAN_PATH <review_artifact>"
        )
        for document, text, expected_count in (
            ("reviewer role", reviewer_role_text, 1),
            ("review route canon", canon_text, 2),
            ("reviewer status prompt", reviewer_text, 1),
        ):
            with self.subTest(document=document):
                self.assertEqual(text.count(final_lint_command), expected_count)
                self.assertNotIn(legacy_final_lint_command, text)

    def test_current_review_proof_has_one_strict_reader_and_no_header_only_fallback(self) -> None:
        reviewer_text = REVIEWER_PROMPT.read_text(encoding="utf-8")
        reviewer_role_text = (ROOT / "docs" / "roles" / "reviewer.md").read_text(encoding="utf-8")
        canon_text = (ROOT / "docs" / "playbooks" / "review_route_and_receipt_canon.md").read_text(encoding="utf-8")
        adr_text = (ROOT / "docs" / "adr" / "004-exact-bundle-truth-and-closeout.md").read_text(encoding="utf-8")
        strict_target = "BUNDLE=current bundle_sha256=<64 lowercase hex>"

        for text in (reviewer_text, reviewer_role_text, canon_text, adr_text):
            self.assertIn("preflight_current_review_proof", text)
            self.assertIn(strict_target, text)
            self.assertIn("review_target_snapshot.v2", text)
            self.assertIn("fresh", text)
            self.assertIn("producer", text)
            self.assertIn("alias", text.lower())
            self.assertIn("blocked", text)

        self.assertIn("exact двухключевой compact", reviewer_text)
        self.assertIn("compact object ровно", reviewer_role_text)
        self.assertIn("compact `target_snapshot` с ровно двумя ключами", canon_text)
        self.assertIn("two-key", adr_text)
        self.assertIn("не создают второй parser/green verdict", reviewer_text)
        self.assertIn("не пересобирая свой current-proof parser", reviewer_role_text)
        self.assertIn("не запускают второй current-proof parser", canon_text)
        self.assertIn("read-only projectors", adr_text)

    def test_role_run_carrier_post_exit_and_env_precedence_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")

        for marker in (
            "`.planveyor.session.<role>` = attach pointer; это не proof surface",
            "`.planveyor.init_runs/{pending,by_sid}`",
            "session pointer не заменяет этот per-run artifact carrier.",
            "Current run carrier содержит identity/readback handles, а не final state.",
            "Manager не ищет receipt по mtime, не повторяет child автоматически, не",
        ):
            self.assertIn(marker, custom_text)

    def test_custom_pipeline_queue_mode_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        runbook_texts = tuple(path.read_text(encoding="utf-8") for path in (OWNER_RUNBOOK, OWNER_RUNBOOK_RU))

        for required in (
            "MANAGER_CMD=run Q",
            "MANAGER_CMD=run_q",
            "planveyor_q_set <PLAN_PATH...> --for-manager-mode manager-custom-pipeline",
        ):
            self.assertIn(required, custom_text)

        self.assertIn("MANAGER_CMD=run [PLAN_PATH]", custom_text)
        self.assertIn("если указан `PLAN_PATH`", custom_text)
        for runbook_text in runbook_texts:
            self.assertIn("planveyor_plan_set docs/plans/YYYYMMDD_HHMM_topic.md", runbook_text)

        for required in (
            "planveyor_q_next_json --manager-mode manager-custom-pipeline",
            "planveyor_q_planpath_override_json",
            "queue_activation",
            "queue_resume_parent",
            "planveyor_q_stop_json",
            "planveyor_q_closeout_json",
            "Queue is empty or not initialized",
            "`Q`",
            "command sentinel",
        ):
            self.assertIn(required, custom_text)

        self.assertIn("Для этого terminal item **не** вызывай дополнительно `planveyor_q_advance_json`", custom_text)
        self.assertIn("custom не dispatch-ит docs-closeout family", custom_text)
        self.assertIn("не применяет `final_docs_commit` auto-skip", custom_text)
        self.assertIn("не добавляет docs-closeout automation", custom_text)

        for runbook_text in runbook_texts:
            self.assertIn("planveyor_manager_custom_pipeline_cmd run Q", runbook_text)

        collab_text = COLLAB_PROMPT.read_text(encoding="utf-8")
        self.assertIn("planveyor_q_next_json --manager-mode manager-collab", collab_text)
        self.assertIn("skipped_manager_mode", collab_text)
        self.assertIn("skipped_manager_mode", custom_text)
        self.assertIn("без смены Manager", collab_text)
        self.assertIn("без смены Manager", custom_text)

    def test_dirty_workstream_and_shared_core_split_are_custom_pipeline_contract(self) -> None:
        custom_text = CUSTOM_PROMPT.read_text(encoding="utf-8")
        invariant_text = (ROOT / "docs" / "playbooks" / "role_prompt_invariant_map.md").read_text(
            encoding="utf-8"
        )

        for required in (
            "verdict=continue|stop",
            "files[].ownership_class",
            "ambiguous_owner",
            "unrelated_dirty",
            "sibling evidence mismatch не закрываются chat prose",
            "выполняются там ровно один раз до child",
            "не stage/restore/delete/stash/commit",
        ):
            self.assertIn(required, custom_text)

        for required in (
            "repo-agnostic invariant",
            "alternate state / non-primary carrier proof",
            "profile-local",
        ):
            self.assertIn(required, invariant_text)

    def test_managed_role_run_probe_and_exact_retention_diagnostics_contract(self) -> None:
        runtime_text = (ROOT / "scripts" / "planveyor.zsh").read_text(encoding="utf-8")
        probe_start = runtime_text.index("planveyor_role_run_probe() {")
        probe_end = runtime_text.index("\n}\n\n", probe_start) + 3
        probe = runtime_text[probe_start:probe_end]

        for marker in (
            "planveyor_role_run_probe run --kind retention",
            "--target-plan docs/plans/<plan>.md",
            "--scenario <orphan_output|malformed_receipt|active_lease|terminal_recovery>",
            "planveyor_role_run_probe <inspect|mark-interrupted|recover> --probe-id <probe_id> --json",
            'if [[ "$probe_kind" != "retention" ]]; then',
            "orphan_output|malformed_receipt|active_lease|terminal_recovery) ;;",
            '_planveyor_role_run_probe_reject "$operation" allowlist_rejected',
        ):
            self.assertIn(marker, probe)

    def test_reviewer_status_driven_lane_override_and_docs_only_profile(self) -> None:
        text = (ROOT / "docs" / "tools" / "prompts" / "reviewer_status_driven.md").read_text(encoding="utf-8")
        # Gap 5: risk lane override precedence (contract)
        self.assertIn("REVIEWER_LANE=reviewer_code_risk", text)
        self.assertIn("overrides generic final-artifact and top-level status rules", text)
        self.assertIn("risk lane stays plan-resident", text)
        self.assertIn("reviewer_code_contracts owns synthesis", text)
        # Gap 6: docs-only/non-UI diagnostic/finalizer profile routing
        self.assertIn("docs-only/non-UI diagnostic or finalizer profile", text)
        self.assertIn("routing, not by deleting the full reviewer contract", text)

    def test_reviewer_prompt_trusted_local_git_metadata_boundary_contract(self) -> None:
        reviewer_text = REVIEWER_PROMPT.read_text(encoding="utf-8")
        policy_anchor = "docs/adr/010-trusted-local-git-metadata-boundary.md"
        ordinary_unsupported_clause = (
            "В ordinary Owner-controlled repo-local plan repro, требующий только `.git` symlink, "
            "manually substituted foreign/unregistered Git-dir или concurrent local metadata mutation, "
            "является unsupported environment и сам по себе non-blocking"
        )
        operational_red_clause = (
            "это не отменяет operational-red для missing/invalid repository, canonical root mismatch "
            "или ambient `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR`/`GIT_INDEX_FILE` override"
        )
        explicit_security_override_clause = (
            "Только explicit Owner-approved untrusted, multi-tenant или security-hardening scope "
            "отменяет default и сохраняет применимый finding blocking"
        )
        ordinary_flipped_clause = (
            "В ordinary Owner-controlled repo-local plan repro, требующий только `.git` symlink, "
            "manually substituted foreign/unregistered Git-dir или concurrent local metadata mutation, "
            "является unsupported environment и сам по себе blocking"
        )
        operational_red_flipped_clause = (
            "это отменяет operational-red для missing/invalid repository, canonical root mismatch "
            "или ambient `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR`/`GIT_INDEX_FILE` override"
        )
        explicit_security_flipped_clause = (
            "Только explicit Owner-approved untrusted, multi-tenant или security-hardening scope "
            "отменяет default и сохраняет применимый finding non-blocking"
        )

        def assert_disposition_contract(text: str) -> None:
            block_marker = "Trusted local Git metadata boundary formalized"
            self.assertEqual(text.count(block_marker), 1)
            line_start = text.rindex("\n", 0, text.index(block_marker)) + 1
            line_end = text.index("\n", line_start)
            policy_block = text[line_start:line_end]

            # positives + ordering — строго ВНУТРИ policy_block (relocation из блока = red)
            self.assertIn(policy_anchor, policy_block)
            self.assertIn("active plan threat model", policy_block)
            for complete_clause in (
                ordinary_unsupported_clause,
                operational_red_clause,
                explicit_security_override_clause,
            ):
                self.assertEqual(policy_block.count(complete_clause), 1)

            threat_model = policy_block.index("active plan threat model")
            ordinary_unsupported = policy_block.index(ordinary_unsupported_clause, threat_model)
            operational_red = policy_block.index(operational_red_clause, ordinary_unsupported)
            security_override = policy_block.index(explicit_security_override_clause, operational_red)
            self.assertLess(threat_model, ordinary_unsupported)
            self.assertLess(ordinary_unsupported, operational_red)
            self.assertLess(operational_red, security_override)

            # opposites — только внутри блока; вне блока contradiction не заявлена как покрытая
            for forbidden_opposite in (
                "сам по себе blocking",  # ordinary tampering остаётся non-blocking
                "это отменяет operational-red",  # operational-red не waiv-ится
                "сохраняет применимый finding non-blocking",  # explicit security остаётся blocking
            ):
                self.assertNotIn(forbidden_opposite, policy_block)

        assert_disposition_contract(reviewer_text)

        for name, original, inversion in (
            (
                "ordinary_unsupported_tampering_must_remain_non_blocking",
                "сам по себе non-blocking",
                "сам по себе blocking",
            ),
            (
                "operational_red_must_not_be_waived",
                "это не отменяет operational-red",
                "это отменяет operational-red",
            ),
            (
                "explicit_security_scope_must_remain_blocking",
                "сохраняет применимый finding blocking",
                "сохраняет применимый finding non-blocking",
            ),
        ):
            with self.subTest(name=name):
                self.assertEqual(reviewer_text.count(original), 1)
                mutated_text = reviewer_text.replace(original, inversion, 1)
                self.assertIn(inversion, mutated_text)
                with self.assertRaises(AssertionError):
                    assert_disposition_contract(mutated_text)

        for name, complete_clause, flipped_clause in (
            (
                "additive_ordinary_tampering_contradiction",
                ordinary_unsupported_clause,
                ordinary_flipped_clause,
            ),
            (
                "additive_operational_red_waiver_contradiction",
                operational_red_clause,
                operational_red_flipped_clause,
            ),
            (
                "additive_explicit_security_contradiction",
                explicit_security_override_clause,
                explicit_security_flipped_clause,
            ),
        ):
            with self.subTest(name=name):
                mutated_text = reviewer_text.replace(
                    complete_clause, complete_clause + " " + flipped_clause, 1
                )
                # unchanged-proof до ожидаемого failure: counts==1 всех трёх canonical clauses
                for clause in (
                    ordinary_unsupported_clause,
                    operational_red_clause,
                    explicit_security_override_clause,
                ):
                    self.assertEqual(mutated_text.count(clause), 1)
                self.assertIn(flipped_clause, mutated_text)
                with self.assertRaises(AssertionError):
                    assert_disposition_contract(mutated_text)

        # relocation-red: canonical ordinary clause вынесена из policy-строки в конец текста —
        # глобально count==1 сохранён, но block-scoped positives обязаны упасть
        with self.subTest(name="canonical_clause_relocated_out_of_policy_block_is_red"):
            relocated_text = (
                reviewer_text.replace(ordinary_unsupported_clause, "", 1)
                + "\n" + ordinary_unsupported_clause + "\n"
            )
            self.assertEqual(relocated_text.count(ordinary_unsupported_clause), 1)
            with self.assertRaises(AssertionError):
                assert_disposition_contract(relocated_text)

        # green-контроль 1: нейтральное дополнение внутри блока — validator остаётся green
        with self.subTest(name="neutral_addition_inside_policy_block_stays_green"):
            neutral_text = reviewer_text.replace(
                explicit_security_override_clause,
                explicit_security_override_clause
                + " Neutrally noted: this wording stays a bounded policy note only.",
                1,
            )
            assert_disposition_contract(neutral_text)

        # green-контроль 2: полная flipped clause вне блока — вне scope контракта, green
        for name, flipped_clause in (
            ("flipped_ordinary_outside_policy_block_stays_green", ordinary_flipped_clause),
            (
                "flipped_operational_red_outside_policy_block_stays_green",
                operational_red_flipped_clause,
            ),
            (
                "flipped_explicit_security_outside_policy_block_stays_green",
                explicit_security_flipped_clause,
            ),
        ):
            with self.subTest(name=name):
                outside_text = reviewer_text + "\n" + flipped_clause + "\n"
                assert_disposition_contract(outside_text)

        for path in (PROCESS_IMPROVEMENTS_README,):
            self.assertIn(policy_anchor, path.read_text(encoding="utf-8"))
    def test_general_pi_collector_examples_bind_cycle_stdin_and_json(self) -> None:
        prompts = (
            ("Architect", ROOT / "docs" / "tools" / "prompts" / "architect_docs_finalize_general.md"),
            ("Coder", ROOT / "docs" / "tools" / "prompts" / "coder_docs_finalize_general.md"),
            ("Planner", ROOT / "docs" / "tools" / "prompts" / "planner_docs_finalize_general.md"),
            ("Reviewer", ROOT / "docs" / "tools" / "prompts" / "reviewer_docs_finalize_general.md"),
        )
        for role, prompt_path in prompts:
            with self.subTest(prompt=prompt_path.name):
                collector_lines = [
                    line for line in prompt_path.read_text(encoding="utf-8").splitlines()
                    if "process_improvements_collect.py" in line
                ]
                self.assertEqual(len(collector_lines), 1)
                self.assertIn(
                    f"--role {role} --source-ref <plan_ref> "
                    "--followups-capture-cycle-id <capture_cycle_id> --input - --json",
                    collector_lines[0],
                )


if __name__ == "__main__":
    unittest.main()

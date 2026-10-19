# Code draft: Разделение review scope и завершённого review proof

**Date:** 2026-10-19 01:05 +0300
**Cluster:** process
**Related plan:** `docs/plans/261018_2230_review_scope_closeout.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261018_2230_review_scope_closeout.md",
    "cluster": "process",
    "targets": [
      {
        "path": "scripts/planveyor.zsh",
        "kind": "shell"
      },
      {
        "path": "scripts/plan_lint.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_planveyor_plan_bundle.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_sibling_contract_docs.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_build_role_bundles.py",
        "kind": "py"
      },
      {
        "path": "docs/playbooks/review_staged_or_commit.md",
        "kind": "doc"
      },
      {
        "path": "docs/playbooks/review_docs_staged_or_commit.md",
        "kind": "doc"
      },
      {
        "path": "docs/roles/architect.md",
        "kind": "doc"
      },
      {
        "path": "docs/roles/planner.md",
        "kind": "doc"
      },
      {
        "path": "docs/roles/reviewer.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/prompts/architect_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/prompts/planner_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/prompts/reviewer_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "docs/plans/README.md",
        "kind": "doc"
      },
      {
        "path": "docs/plans/_template.md",
        "kind": "doc"
      },
      {
        "path": "docs/code_drafts/_template.md",
        "kind": "doc"
      },
      {
        "path": "docs/code_reviews/README.md",
        "kind": "doc"
      },
      {
        "path": "docs/doc_reviews/README.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/owner_runbook_codex.md",
        "kind": "doc"
      },
      {
        "path": "skills/planveyor-plan-draft/SKILL.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/playbooks/review_staged_or_commit.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/playbooks/review_docs_staged_or_commit.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/roles/architect.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/roles/planner.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/roles/reviewer.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/tools/prompts/architect_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/tools/prompts/planner_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/tools/prompts/reviewer_status_driven.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/plans/README.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/plans/_template.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/code_drafts/_template.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/.agents/skills/planveyor-plan-draft/SKILL.md",
        "kind": "doc"
      }
    ],
    "deleted_paths": [],
    "machine_authority_decision_ref": {
      "applicability": "not_applicable",
      "reason_code": "no_machine_authority_change",
      "carrier_sha256": "d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204"
    }
  }
}
```

Derived N-A ref материализован штатным `planveyor_code_draft_stub_from_plan --role Planner` после native readback. Semantic core принадлежит Architect и сюда не копируется. `targets` содержит ровно 32 existing implementation/doc/test paths; plan, этот draft и единственный будущий review добавляются как отдельные lifecycle members, не как mutable review targets. Deletions отсутствуют.

## Provenance / session context
- Source plan provenance: отдельный Planner draft продолжает literal plan; его origin carrier не переписывается.
- Relation: `continued-here`
- Thread ID: `<REDACTED>`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-18T22:02:29Z`

Источник — actual `planveyor_plan_provenance_context --section code-draft --session-key planner --plan-path docs/plans/261018_2230_review_scope_closeout.md`; private thread ID скрыт. Missing SID/launch surface не реконструируются по Manager chat или памяти.

## Purpose
Дать Coder точный implementation/doc/test bundle и исполнимые proof lanes для выбранного `--scope-check`, сохранив прежние semantic readers, strict final gates и frozen native runtime. Реализация алгоритма принадлежит Coder; Decisions исходного plan остаются единственным semantic contract.

## Reviewability preflight receipt
- `proof-path class`: checked-in repo-local helper.
- `mandatory primary lane`: candidate source `scripts/planveyor.zsh:planveyor_plan_bundle` в isolated temporary fixtures существующего `scripts/test_planveyor_plan_bundle.py`; 26 existing + 19 new exact commands ниже, без discovery.
- `mandatory non-primary carrier / contextual lane`: реальные Reviewer pre-diff и Planner first/refinement callers; Architect inventory guidance; emitted lint guidance; source→Copier byte equality/local-tail stability; generated role-bundle source propagation. Existing semantic lint/digest regressions не получают bypass.
- `exact helper path + support files`: mutable `scripts/planveyor.zsh`; `scripts/plan_lint.py` mutable только docstring selected-support validator и emitted guidance. Existing `select_plan_risk_lane_snapshot`, `collect_plan_risk_lane_support_refs`, `preflight_selected_risk_lane_support`, `preflight_current_review_proof` сохраняют parsing/authority. `scripts/test_support/process_contract_fixtures.py` — existing read-only fixture support.
- `dependent tests / dependent docs / known consumer paths`: все 32 literal targets в Meta; read-only consumers `scripts/review_artifact_lint.py`, `scripts/plan_status_oracle.py`, `scripts/plan_handoff_digest.py`, `scripts/build_role_bundles.py`; existing exact regressions `scripts/test_plan_lint.py`, `scripts/test_plan_handoff_digest.py`. `scripts/test_review_artifact_lint.py` и `scripts/test_runtime_portability.py` contextual, без дополнительной правки/прогона.
- `preconditions / seed-discovery`: `discovery-or-seed` — существующий test fixture создаёт один synthetic repo, canonical plan/same-stem draft, declared review и support chain. Downstream calls — `receipt-reuse-only` того же fixture; silent rediscovery/reseed другого inventory запрещён. Перед test commands один раз создаётся ignored source-local TMPDIR штатным `mkdir -p .tmp/review-scope-validation`; wrapper/script scaffolds не создаются.
- `stable identity fields`: fixture repo identity, canonical plan path, same-stem draft path, sorted bundle paths/deletions, single review path, target ref/snapshot, declared support refs/SHA и before-state files/index/refs/receipts одного fixture.
- `observer boundary`: непосредственно перед и после каждого read-only scope invocation того же fixture; compare canonical bytes/index/refs/receipts. `notice/success text != mutation truth`; closure — следующий canonical snapshot/readback, а final acceptance — прежние strict gates.
- `runtime-lineage preflight`: owning source baseline и immutable external runtime = `822e3e62a2d8fb35f1a8ac7ec609c625c864a506`; candidate source меняется отдельно и проверяется только в fixtures. Перед native Manager/Reviewer invocation требуется readback фактического bundle этого caller; conflicting prompt/runtime binding либо undocumented materialized-red rerun на frozen runtime = STOP координатору. Runtime/bundles не регенерируются и candidate не активируется.
- `reroute rule`: unknown diagnostic, отсутствующий exact selector, недоказанная contextual lane, semantic fingerprint/admission gap, unexpected nonzero/UNKNOWN/timeout, недостаток remaining для cap либо неделимая длинная lane = STOP Architect/координатору до расширения targets/allowlists.
- `perceptual truth-source split`: structural/repo-backed carrier; `N/A (why=no UI; image/OCR/template/pixel proof не применяется)`.
- `receipt retention`: source-local `.tmp/` и temporary fixtures = transient local sanity only; current plan/review и explicit immutable risk support assets = durable operator/review evidence. Raw private logs не публикуются.
- `terminal sink assertion`: `N/A (why=no transient redirect/callback/auth carrier)`.
- `concurrency proof`: `N/A (why=no concurrency/lock mutation contract)`.

Truth-host fixture matrix:
- `authoritative_host`: canonical plan/draft membership, all-history support manifest, lifecycle selector, raw selected-support validator, canonical current-proof и live review completion host.
- `derived_summary_field`: `scope_ok`, typed `support` и `completion` projections, без route/admission.
- `green_case`: exact inputs/support целы; inventory допускается независимо от ещё не завершённого review; final green устанавливают отдельные strict gates.
- `missing_case`: planned first review допускается только как future output; missing target/support fail closed; no-selected = unvalidated `not_selected`.
- `ambiguous_case`: любой selector error, inconsistent selection shape/lifecycle или multiple live route блокирует scope.
- `present_but_red_or_inconsistent_case`: ранний proof projection mismatch + tampered selected support блокирует scope; stale proof + newer open blocker остаётся completion-red, без route/commit.
- `expected_fail_closed_verdict`: rc1/`scope_ok=false` для input/integrity/selection/unknown faults; scope rc0 никогда не даёт final green/role permission.

## Targeted changes (by file)
- `scripts/planveyor.zsh`: один explicit read-only `--scope-check` в existing dispatch/resolver/help, без второго resolver или нового prose parser. Independent collector, selector и raw selected-support validation выполняются до scope decision; final proof остаётся completion projection с точным source attribution.
- `scripts/plan_lint.py`: только docstring `preflight_selected_risk_lane_support` и emitted caller guidance; semantic functions/selector/admission не меняются.
- `scripts/test_planveyor_plan_bundle.py`: 17 новых selected methods ниже; isolated scope/strict-mode/support/invariance fixtures. Другие новые test methods и helper-support files не добавляются.
- `scripts/test_sibling_contract_docs.py`: один новый selected method, реальные phase-specific callers/authority; existing local-tail pins не обновляются.
- `scripts/test_build_role_bundles.py`: один новый selected method для реально rendered source refs; existing generation rules неизменны.
- `docs/playbooks/review_staged_or_commit.md`, `docs/playbooks/review_docs_staged_or_commit.md`: pre-diff scope отдельно от finished final check.
- `docs/roles/reviewer.md`, `docs/tools/prompts/reviewer_status_driven.md`, `docs/code_reviews/README.md`, `docs/doc_reviews/README.md`: inventory/planned-output/completion/current-support distinctions; final native review остаётся strict.
- `docs/roles/planner.md`, `docs/tools/prompts/planner_status_driven.md`, `docs/plans/README.md`, `docs/plans/_template.md`, `docs/code_drafts/_template.md`, `skills/planveyor-plan-draft/SKILL.md`: first handoff strict preflight; genuine materialized-review refinement inventory-only scope-check вместе с остальными gates; same-contract skip-Planner unchanged.
- `docs/roles/architect.md`, `docs/tools/prompts/architect_status_driven.md`: тот же bounded inventory/caller guidance, strict stop gates сохраняются.
- `docs/tools/owner_runbook_codex.md`: public mode/help/lifecycle wording.
- Все 12 literal `copier_template/` targets из Meta: синхронные common source counterparts существующего declared delivery contract; sibling-owned local sections byte-stable. У bucket README/owner runbook counterpart не создаётся.
- Context-only `scripts/shared_docs_mirror_drift.py`: `N/A (why=generic policy не объявляет consumer target; sibling adoption вне scope)`.
- One-shot `scripts/planveyor/role_runtime.zsh`: `N/A (why=Manager command/dispatch path не меняется; новый MANAGER_CMD не добавляется)`.

Existing baseline surfaces = existing resolver/readers/strict gates/Copier/generation rules. New targets = scope mode и caller contract в существующих 32 files; новой parser/runtime family и checked-in sample corpus нет.

### Receipt schema emitter inventory / field parity
- Family: transient diagnostic `planveyor_plan_bundle_scope.v1`, sole emitter/serializer `scripts/planveyor.zsh:planveyor_plan_bundle` — in Meta targets.
- Changed parsers/validators: `N/A (why=semantic shared readers неизменны; только independent invocation existing raw validator в resolver)`.
- Exact fields: `schema`, `plan`, `scope_ok`, `errors`, `path_problems`, `repo_roots`, `support.historical`, `support.selected`, `completion.current_review_proof`, `completion.review_artifacts`; nested fields/enums/rc строго по plan Decisions. `route`, `next_owner`, `green`, `commit_ready`, admission permission запрещены рекурсивно.
- Owner-facing skeleton/bootstrap/readback emitters: plan/code-draft templates, role/prompt/skill source и все 12 existing Copier counterparts — in Meta targets для caller wording. `scripts/build_role_bundles.py` — read-only context with `N/A (why=existing generation rules не меняются)`; generated XML только temporary test output.
- Regression/readback: new selectors 1, 2, 6, 11, 15–19 и existing source/copy/tail/generation selectors; output fields проверяются через real candidate resolver, не через самостоятельный payload parser.
- Новые owner-facing JSON consumers, external schemas/registry и Manager dispatch: `N/A (why=не объявлены; generated diagnostic не является authority)`.

## Review route
- `Primary artifact`: `docs/code_reviews/261018_2230_review_scope_closeout.md`
- `Lane type`: code review, native Risk + Contracts в одном live artifact.
- `Review target`: `BUNDLE=current` по 32 exact targets; plan/draft/review остаются отдельными lifecycle carriers.
- Первый review ещё не materialized: frozen runtime разрешает только documented planned-absence inspection с честным qualified expected nonzero. После materialization любые red/rerun условия вне его current canon требуют STOP, candidate scope mode не используется как обход.
- `Semantic review observation` / checkpoint: `N/A (why=opt-in markers не активированы этим plan)`.

## Patch sketch (keep it small)
1. Coder проверяет existing dispatch/resolver и adds explicit scope mode с прежними input/path/metadata guards.
2. Historical collector остаётся byte/path/hash authority; selector вызывается независимо. Usable selected lane проходит raw selected-support validator; no-selected явно не validated.
3. По sources различаются ровно шесть allowlisted proof debt codes и единственный selected-support `current_review_proof_producer_mismatch` после integrity; остальные/unknown failures scope-blocking. Никакого parsing human reason/message.
4. Typed JSON выводится одним document, rc0 iff scope_ok, обычный scope failure rc1; existing prerequisite/parser/transport failures остаются nonzero. Strict modes/delegated rejected branches не меняются.
5. Coder синхронизирует scoped caller/help/doc/skill/Copier wording и реализует 19 выбранных methods; затем выполняет 45 literal commands по одному с stop-first и измерениями.
6. Native reviewer proof/strict closeout самого fix остаётся на external immutable runtime; runtime не переключается на candidate.

## Critical invariants / traps / bypass paths
- Independent input integrity: early proof mismatch не скрывает tampered support; одноимённый projection code классифицируется по источнику, не тексту.
- Inventory-only rc0: `not_selected` не validated; historical integrity не получает новый schema gate; completion-red не становится route/commit.
- Caller phase split: first preflight строгий, genuine refinement не обязан impossible completed-review preflight; semantic lint/digest/status window не обходятся.
- Alternate paths: current/staged/range/legacy, strict-N-A candidate/materialized, historical/no-selected/current selected, malformed output, incompatible flags и strict/rejected modes охвачены selected methods.
- Truthful source/runtime: fixture candidate pass не доказывает native runtime adoption, final continuity или delivery.

## Tests / Commands
Trusted engine interpreter уже выбран launch environment; portable spelling во всех proof surfaces = `"$PYBIN"`. Working directory = physical owning source root; `PYTHONPATH` ровно source scripts/root, TMPDIR source-local ignored. Product DB/profile = `N/A (why=synthetic isolated process fixtures; SQL/live Э4а не используются)`.

### Existing exact selectors — 26
1. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_allows_missing_first_pass_review_artifact` — cap=60 с.
2. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_live_review_artifact_without_canonical_status` — cap=60 с.
3. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_current_red_live_review_artifact` — cap=60 с.
4. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_routes_stale_red_after_fix_to_reviewer_same_file_rewrite` — cap=60 с.
5. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_preflight_routes_newer_contracts_blocker_to_coder` — cap=60 с.
6. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_active_quarantine_without_rerun_result` — cap=60 с.
7. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_strict_na_candidate_mode_matrix_is_inspection_only_and_mutation_free` — cap=60 с.
8. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_materialized_strict_na_parent_rejects_nonregular_asset_and_mismatched_child_draft` — cap=60 с.
9. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_rejects_missing_code_draft_meta` — cap=60 с.
10. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_rejects_stale_target_inventory` — cap=60 с.
11. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_and_lint_reject_review_only_deletion_without_refs` — cap=60 с.
12. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_check_rejects_untracked_durable_review_receipt_reference` — cap=60 с.
13. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_invalid_all_history_risk_support_blocks_mutation_and_reports_closeout_needs_rerun` — cap=60 с.
14. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_current_proof_block_gates_every_bundle_mutation_mode` — cap=60 с.
15. `scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_current_proof_rejects_header_and_compact_aliases_before_any_fallback` — cap=60 с.
16. `scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_selected_current_support_preflight_matches_fresh_producer_failure_codes` — cap=60 с.
17. `scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_current_proof_rejects_missing_support_invalid_full_snapshot_and_producer_red` — cap=60 с.
18. `scripts.test_plan_handoff_digest.PlanHandoffDigestTests.test_present_but_red_review_oracle_fails_closed` — cap=60 с.
19. `scripts.test_plan_handoff_digest.PlanHandoffDigestTests.test_default_children_use_runtime_and_explicit_consumer_project` — cap=60 с.
20. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_template_copies_match_their_docs_sources_byte_for_byte` — cap=60 с.
21. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_local_section_tails_stay_byte_stable_for_sibling_upgrade` — cap=60 с.
22. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_phase_prompts_apply_local_sections_of_their_playbooks` — cap=60 с.
23. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_planner_common_rules_precede_its_trailing_local_body` — cap=60 с.
24. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_delivered_docs_call_the_engine_only_through_the_facade` — cap=60 с.
25. `scripts.test_build_role_bundles.BuildRoleBundlesSliceTests.test_required_bootstrap_slices_are_rendered` — cap=60 с.
26. `scripts.test_build_role_bundles.BuildRoleBundlesProfileContentBridgeTests.test_public_content_identities_compile_from_the_root_corpus` — cap=60 с.

### New exact selectors — 19
1. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_planned_absence_has_inventory_without_admission` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
2. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_no_selected_lane_is_unvalidated` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
3. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_materialized_non_green_is_completion_only` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
4. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_stale_proof_with_newer_blocker_has_no_route` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
5. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_early_proof_mismatch_does_not_hide_bad_support` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
6. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_proof_projection_and_support_projection_are_distinct` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
7. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_only_producer_mismatch_is_stale_support_debt` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
8. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_selector_errors_and_inconsistent_shape_fail_closed` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
9. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_historical_support_keeps_path_hash_only_contract` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
10. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_missing_tampered_or_unsafe_inputs_fail_closed` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
11. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_unknown_transport_and_input_changed_fail_closed` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
12. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_malformed_output_headers_do_not_grant_completion` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
13. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_current_staged_range_and_legacy_inventory` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
14. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_strict_na_candidate_and_materialized_parent` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
15. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_incompatible_flags_fail_before_side_effects` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
16. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_preserves_files_index_refs_and_receipts` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
17. `scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_preserves_strict_modes_and_rejected_closeout` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
18. `scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_review_scope_callers_keep_phase_specific_gate_contract` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.
19. `scripts.test_build_role_bundles.BuildRoleBundlesProfileContentBridgeTests.test_review_scope_sources_have_current_generated_references` — cap=60 с; purpose/edge matrix literal в plan, распределение 17/1/1.

### Exact invocations
Один command за раз; исполнение всего блока как script/group/loop запрещено. Coder выбирает следующую строку только после rc0 предыдущей и remaining >=60 с. В этом Planner проходе tests не запускаются.
```zsh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_allows_missing_first_pass_review_artifact
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_live_review_artifact_without_canonical_status
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_current_red_live_review_artifact
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_routes_stale_red_after_fix_to_reviewer_same_file_rewrite
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_preflight_routes_newer_contracts_blocker_to_coder
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_closeout_json_blocks_active_quarantine_without_rerun_result
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_strict_na_candidate_mode_matrix_is_inspection_only_and_mutation_free
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_materialized_strict_na_parent_rejects_nonregular_asset_and_mismatched_child_draft
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_rejects_missing_code_draft_meta
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_rejects_stale_target_inventory
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_preflight_and_lint_reject_review_only_deletion_without_refs
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_check_rejects_untracked_durable_review_receipt_reference
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_invalid_all_history_risk_support_blocks_mutation_and_reports_closeout_needs_rerun
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_current_proof_block_gates_every_bundle_mutation_mode
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_current_proof_rejects_header_and_compact_aliases_before_any_fallback
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_selected_current_support_preflight_matches_fresh_producer_failure_codes
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_plan_lint.CurrentReviewProofPreflightTests.test_current_proof_rejects_missing_support_invalid_full_snapshot_and_producer_red
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_plan_handoff_digest.PlanHandoffDigestTests.test_present_but_red_review_oracle_fails_closed
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_plan_handoff_digest.PlanHandoffDigestTests.test_default_children_use_runtime_and_explicit_consumer_project
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_template_copies_match_their_docs_sources_byte_for_byte
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_local_section_tails_stay_byte_stable_for_sibling_upgrade
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_phase_prompts_apply_local_sections_of_their_playbooks
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_planner_common_rules_precede_its_trailing_local_body
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_delivered_docs_call_the_engine_only_through_the_facade
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_build_role_bundles.BuildRoleBundlesSliceTests.test_required_bootstrap_slices_are_rendered
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_build_role_bundles.BuildRoleBundlesProfileContentBridgeTests.test_public_content_identities_compile_from_the_root_corpus
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_planned_absence_has_inventory_without_admission
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_no_selected_lane_is_unvalidated
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_materialized_non_green_is_completion_only
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_stale_proof_with_newer_blocker_has_no_route
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_early_proof_mismatch_does_not_hide_bad_support
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_proof_projection_and_support_projection_are_distinct
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_only_producer_mismatch_is_stale_support_debt
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_selector_errors_and_inconsistent_shape_fail_closed
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_historical_support_keeps_path_hash_only_contract
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_missing_tampered_or_unsafe_inputs_fail_closed
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_unknown_transport_and_input_changed_fail_closed
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_malformed_output_headers_do_not_grant_completion
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_current_staged_range_and_legacy_inventory
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_strict_na_candidate_and_materialized_parent
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_incompatible_flags_fail_before_side_effects
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_preserves_files_index_refs_and_receipts
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_planveyor_plan_bundle.PlanBundleCommitReadyTests.test_scope_check_preserves_strict_modes_and_rejected_closeout
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_sibling_contract_docs.SiblingContractDocsTest.test_review_scope_callers_keep_phase_specific_gate_contract
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts:$PWD" TMPDIR="$PWD/.tmp/review-scope-validation" "$PYBIN" -m unittest -v -f scripts.test_build_role_bundles.BuildRoleBundlesProfileContentBridgeTests.test_review_scope_sources_have_current_generated_references
```

### Caps / accounting / reuse
Общий delivery command budget = 3600 с, carry-in Planner subtotal=461.344444585 с / remaining=3138.655555415 с; pre-collab158.66 и baseline-only six-session audit0.25 включены по одному разу. При materialization после двух physical Git readbacks, draft helper и provenance context subtotal=484.576444585 с / remaining=3115.423555415 с; это измеренный checkpoint перед дальнейшими gates, не финальный remaining. Последующие actual finite commands прибавляются; Manager использует final handoff total, не удваивая additional.

| Finite command | Cap, с |
| --- | ---: |
| manager_init | 600 |
| docs_index_build_if_required | 180 |
| each_docs_retrieval | 30 |
| oracle / plan_lint / code_draft_lint / exact_doc_lint | 60 каждый |
| exact_diff_check | 30 |
| bundle_inspection_or_final_gate | 60 |
| current_snapshot_or_selected_support | 60 |
| provenance_or_capture_helper / generated_bundle_check | 60 каждый |
| semantic_commit_or_terminal_docs_closeout_helper | 120 |
| Каждый из 45 exact test commands | 60 |

- Перед finite command объявить exact argv/cap/remaining; при remaining < cap запуск запрещён. Actual start/end/rc/elapsed/stdout/stderr/timeout/evidence delta фиксируются; PTY output merged, child elapsed включён только один раз в parent.
- Manager/Architect/Planner/Coder/Risk/Contracts/CENSOR/helper commands используют один ledger; role/model waiting и обычное чтение отдельно, finite init wall time считается. Budget не reset-ится.
- 45×60=2700 с и manager_init600 дают worst-case3300 с до остальных gates; предел3600 не гарантия завершения.
- Любой unexpected failure/non-green/UNKNOWN/timeout = STOP координатору без retry/cap raise/substitution/widening. Только documented planned-first-review expected nonzero допускается с exact diagnostic qualification.
- Passed selector reuse только при unchanged relevant source/test/fixture/runtime bytes и evidence identity. После relevant mutation конкретный rerun list задаёт координатор; не повторять весь list автоматически.
- Discovery, group loops, `make test-scripts`, verify-full/all14, `scripts/run_test_shard.py` execution/--check запрещены. `test_plan_lint_changed` не запускается/не меняется. Новые methods не требуют shard manifest edit.
- Baseline audit не доказывает final session continuity. Terminal proof/clean target/followups/capture/commit выполняются admitted downstream roles; Coder/Planner не получают Done writer.

## Assumptions / risks
- 45 exact IDs и 32 targets — выбранный bounded contract; отсутствие/неделимая lane либо необходимость нового target требует STOP, не ad-hoc redesign.
- Materialized-red frozen-runtime review и conflicting caller bundle binding остаются конкретными STOP conditions.
- `LOCAL_SECTION_TAIL_SHA256` относится только к bytes от первой local heading до EOF; common edits не оправдывают смену pins.

## Notes for Coder
Plan важнее draft. Не меняй semantic core/ref policy, scope/allowlists, current-proof/fingerprint/oracle authority. Реализацию, runtime sanity и selected test mechanics выбирает Coder внутри этого contract. Missing new test methods создаются в существующих трёх test files; новые target files не нужны. Все implementation/doc targets уже существуют, planned-new stubs не создаются.

## Review stamps (append-only)
- [2026-10-19 01:05] (Planner) Draft материализован по current plan: exact32 targets, derived N-A ref, 45 literal selectors/commands и caps; semantic contract не расширен. Completion self-check: Coder/Reviewer не должны угадывать input/completion split, support источник, caller phase, proof lane или runtime boundary.
- [2026-10-19 01:15] (Planner) NO SUGGESTIONS — текущий draft перечитан; дополнительные semantic правки не требуются. По отдельному Owner-authorized bounded repair добавлен только пропущенный literal hygiene stamp; 32 targets, 45 selectors/commands и derived N-A ref неизменны, предыдущая lint failure сохранена.

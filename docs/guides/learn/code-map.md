# Code map

**English** · [Русский](code-map.ru.md)

This appendix is for Planveyor developers. The tables from all chapters are collected here: the files and functions to start reading the implementation from, and the named tests with what they check. The sections follow the order of the chapters. Line numbers in the code change, so look for a function or a test by its name.

The test descriptions are based on the test source code. Only running these tests shows whether they pass on your version: the commands are in the [verification routes](../../tools/verify_suite.md).

## Roles and task files

Chapter: [Roles and task files](roles-artifacts.md).

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| How a phase gets the prompt name | [planveyor.zsh](../../../scripts/planveyor.zsh), `_planveyor_prompt_filename_for_role_phase()` |
| How the actual prompt bytes are chosen | [planveyor.zsh](../../../scripts/planveyor.zsh), `_planveyor_prompt_file_for_role_phase()` |
| How the main roles are called | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `planveyor_arch()`, `planveyor_planner()`, `planveyor_coder()` |
| How a specific Reviewer lane is launched | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `_planveyor_reviewer_run_for_session_key()` |
| How Manager hands the work to the lanes | [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md) (in Russian), the algorithm subitem about Reviewer dispatch |
| How the ownership of a source is checked | [contract_authority_context.py](../../../scripts/contract_authority_context.py), `context_for_reader()` and `read_declared_text()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py): `test_collab_prompt_dispatches_the_configured_role_types` | Uses `assertIn` to check the pairs `architect/planner/coder → agent_type`, as well as `followup_task` and `list_agents`; forbids `planner → agent_type=default`. This checks the prompt text, not a live run of a role |
| [test_analysis_source_ownership.py](../../../scripts/test_analysis_source_ownership.py): `test_every_shipped_role_declares_shared_root_then_declared_target_local` | For Architect, Planner, Coder, and Reviewer, checks the presence and the order of the source markers of the analysis-wave playbook: the shared root, the declared target-local source, and the ban on a guessed fallback. This is a narrow check of four role documents; it does not check Manager or any other source of a role |
| [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py): `test_home_ensure_selects_consumer_home_without_rewriting_agent_roles` | The shared fixture checks code `0`, the returned directory, the unchanged file snapshot, and the absence of a new `agents/planner.toml`. The client in the fixture is replaced with a stub; the check does not prove authentication |

## Running example: which products to reorder

Chapter: [Running example: which products to reorder](sql-example.md). Here is the code of the SQL sibling from the [snapshot](examples/sql/README.md), not the code of Planveyor. The snapshot has two of the 40 harness tests; the others stayed in the sibling.

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| How the procedure computes the shortage | [GetReorderCandidates.sql](examples/sql/sql/Northwind/GetReorderCandidates.sql), `COALESCE` and `CAST(... AS INT)` inside `CROSS APPLY` |
| How the two test classes and the order check are run | [run-tests.sql](examples/sql/sql/tests/run-tests.sql), the markers `PV_TEST_RESULT`, `PV_ORDER_BEGIN`, `PV_ORDER_END` |
| What `make db-proof` does | [sql.py](examples/sql/scripts/sql.py), `db_proof()` |
| How the test sources and the run script are checked | [sql.py](examples/sql/scripts/sql.py), `verify_test_files()`, `current_test_set()` |
| How the state of the classes in the database is checked | [sql.py](examples/sql/scripts/sql.py), `existing_classes_are_safe()` |
| Which parameters the publication uses | [sql.py](examples/sql/scripts/sql.py), `publish_args()` |
| How the test results and the row order are parsed | [sql.py](examples/sql/scripts/sql.py), `parse_test_results()`, `parse_order_rows()` |
| How a run is tied to the commit and the files | [sql.py](examples/sql/scripts/sql.py), `current_proof_bytes()`, `reusable_proof()` |
| When the JUnit report is green and when it is red | [sql.py](examples/sql/scripts/sql.py), `junit_xml()`, `junit_matches()`, `failure_junit()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_sql_excerpt.py](examples/sql/test_sql_excerpt.py): `test_exact_result_and_direct_client_order_parsers` | On substituted database output, accepts eight successful results and the order `(10, 20, 30)`. Rejects a missing, repeated, extra, or failed result; output without the `PV_ORDER_BEGIN` marker and with a repeated marker; ID 30 in the second row instead of 20 (order 10, 30, 30); a missing and a corrupted row. It checks the parsing of the output; the database takes no part in the test |
| [test_sql_excerpt.py](examples/sql/test_sql_excerpt.py): `test_wrong_client_order_writes_red_junit_and_no_green_proof` | Calls `db_proof()` with substituted commands: both classes are marked, and the rows come in the order 10, 30, 30. Expects the error `order observer sequence mismatch`, three class state queries, and exactly one JUnit report with `errors="1"`, which `junit_matches()` does not accept. The build, the linter, the publication, and the database queries are substituted in the test |

## The plan and its statuses

Chapter: [The plan and its statuses](plan-lifecycle.md).

### Where to read the implementation

| Mechanism | File and symbol |
| --- | --- |
| The explicit Oracle entry point | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_status_oracle()` |
| The header, the authority, and the final readback | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `_scan_status_line()`, `machine_authority_decision_readback()`, `oracle_result()` |
| Handoff readiness checks | [plan_lint.py](../../../scripts/plan_lint.py), `validate_exact_bundle_preflight()` and `lint_plan()` |
| Creating the draft skeleton | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_code_draft_stub_from_plan()` |
| Selecting and reading the active plan | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_set()` and `planveyor_planpath()` |
| The final bundle contents and the closeout | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_bundle()` and `planveyor_plan_closeout_preflight()` |
| The separate docs closeout | [docs_closeout.py](../../../scripts/docs_closeout.py), `classify_docs_closeout()` |
| What `planveyor sibling plan` prints | [sibling_runbook.py](../../../scripts/sibling_runbook.py), `show_plan()` |
| How `planveyor sibling answer` writes the Owner answer | [sibling_runbook.py](../../../scripts/sibling_runbook.py), `handle_answer()` |
| What `planveyor sibling close` checks before `Done` and how it writes `Done` | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `validate_done_admission()` and `handle_close()`; the status itself is written by [sibling_runbook.py](../../../scripts/sibling_runbook.py), `Context.set_status()`, through `planveyor_sibling()` in [planveyor.zsh](../../../scripts/planveyor.zsh) (`--internal set-done`, and the admission is checked again) |
| Why an open `## Post-merge gate` keeps the plan from reaching `Done` | [plan_lint.py](../../../scripts/plan_lint.py), `validate_done_post_merge_gate_checklist()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_json_output_uses_single_header_status_and_ignores_body_status` | Checks code `0`, `status_norm=ready for coder`, the exact header line, the passed `plan_path`, and a hash of length `64`; a historical `Done` in the body is not selected. This is the parsing of a fixture, not a run of Coder |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_duplicate_header_status_fails_with_line_details` | Checks code `3`, the message `expected exactly 1 header **Status:** line, got 2`, and both header lines. This is the diagnosis of an ambiguous plan |
| [test_planveyor_plan_bundle.py](../../../scripts/test_planveyor_plan_bundle.py): `test_preflight_allows_missing_first_pass_review_artifact` | The preflight returns `0` and `PLANNED`; the final `--check` returns a nonzero code and `MISSING-PATH`, and the receipt names `next_owner=Reviewer`. This is the difference between the admission stages, not a finished review |
| [test_planveyor_plan_bundle.py](../../../scripts/test_planveyor_plan_bundle.py): `test_preflight_rejects_stale_target_inventory` | Checks a nonzero code and `MISSING-PATH` with the missing target. A nonexistent file is declared in `code_draft_meta.targets`; a declaration without a file on disk does not make the inventory usable |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_done_plan_with_open_post_merge_gate_checkbox_fails` | For a plan in the `Done` status with an open item `- [ ]` in `## Post-merge gate`, returns one `ERROR` finding that mentions `Post-merge gate` and `- [ ]`. The test checks the function `validate_done_post_merge_gate_checklist()` on the fixture text, without a full linter run |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_done_plan_with_post_merge_gate_section_level_na_passes` | The same `Done` plan, with the whole `## Post-merge gate` section replaced by the line `N/A (why=…)`, gives no findings |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_actual_question_closes_and_preserves_verbatim_multiline_text` | The Owner answer is appended to the plan as the line `(Owner, id=Q1, status=closed)` and the lines `  > …`, with the text unchanged; the earlier plan content is kept, `owner_qna_readback` gives `clean` after the write, and a command from the answer text is not run. In the fixture, the project check and Oracle are replaced by reading the questions section from the plan text |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_early_status_red_or_stale_review_and_owner_question_block` | Puts into the Oracle answer, one at a time, the status `ready for arch review`, the review states `stale_green_review` and `live_blocker`, an open Owner question, and `route_guard_triggered=true`; each time, `handle_close()` with `--commit` stops, and HEAD, the index, and the plan bytes do not change. In the fixture, Oracle, the bundle assembly, and the linter are replaced with controlled answers; Git is real |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_failed_final_lint_restores_only_own_plan_bytes_and_does_not_commit` | If the final linter refuses after `Done` is written, `handle_close()` stops with the message `Статус восстановлен` (status restored): the plan bytes and HEAD are unchanged, the index holds the original version of the plan, the target file is untouched, and `git reset` is not called. In the fixture, the linter is replaced with a controlled answer |

## Development, analysis, and decomposition

Chapter: [Development, analysis, and decomposition](work-contours.md).

### Where to read the implementation

| Question | File and symbol |
| --- | --- |
| Preparing an existing analysis | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_analysis_init()` |
| Preparing and launching a decomposition | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_decomposition_init()`, `planveyor_decomposition_collab_tui()` |
| How the analysis pack authority is determined | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `resolve_analysis_pack_authority()` |
| How the graph of child plans is read | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `decomposition_child_state()` |
| How the overall picture of the planning work is built | [planning_wave_readback.py](../../../scripts/planning_wave_readback.py), `build_readback()` |
| How plans are admitted to the queue | [plan_queue.py](../../../scripts/plan_queue.py), `validate_explicit_plan_for_queue()` and `set_queue()` |
| Which five analysis outcomes are allowed and what each one requires | [plan_vocab.json](../../_meta/plan_vocab.json), `planning_contour.accepted_routes` and `status_transition_matrix`; [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `NON_EXECUTABLE_ROUTE_EXPECTED_FIELDS`, `NON_EXECUTABLE_ROUTE_REVISIT_REQUIRED`, and `non_executable_source_route_carrier_issues()`; [plan_lint.py](../../../scripts/plan_lint.py) calls the last one |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_plan_resident_statuses_are_exactly_the_statuses_without_code_draft` | The plan-resident statuses (the early statuses and `Superseded`) equal the canonical statuses minus `code_draft_required`. The standalone-required set equals the `code_draft_required` group itself: here the authority is already in the external pack. The test checks the consistency of the vocabulary, not the quality of an analysis |
| [test_planning_wave_readback.py](../../../scripts/test_planning_wave_readback.py): `test_external_recommendation_uses_standalone_truth_host` | Checks the schema `planning_wave_readback.v1`, the plan reference, the external `truth_host` pack, and the recommendation `developer_wave`. A recommendation in the readback does not prove a dispatch |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_operational_duplicate_warns_but_scalars_stay_pack_derived` | Requires `operational_duplicate` and the lifecycle `warning`; with a contradicting plan budget, the returned `budget_status=active` and depth `1` come from the pack. A diagnostic warning does not mean that there is no problem |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_active_decomposition_without_child_graph_exposes_missing_blocker` | With a `Done` fixture, Oracle returns code `0`, but `queue_closeout_ready=false`, the kind `decomposition_children_missing`, and the child state `missing`. A successful readback does not equal closeout readiness |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_operational_duplicate_with_ref_holds_on_every_status_family` | For the statuses `Architect initial draft`, `Ready for Planner`, `Ready for Review`, and `Superseded`, a plan with an `analysis_pack_ref` line and a duplicated `route_recommendation` line gives exactly one `ERROR` finding with `analysis_pack_authority_invalid:operational_duplicate` |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_defer_source_route_requires_revisit_when` | For an analysis plan with the accepted outcome `defer` and no `revisit_when` line in `## Promoted route artifact`, the linter returns an `ERROR` that mentions `revisit_when` |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_human_gate_source_route_requires_revisit_when` | The same for the outcome `human_gate`: without `revisit_when`, the linter returns an `ERROR` that mentions `revisit_when` |

## Review and acceptance

Chapter: [Review and acceptance](review-acceptance.md).

### Where to read the implementation

| Question | File and symbol |
| --- | --- |
| How the current target bytes are obtained | [review_target_snapshot.py](../../../scripts/review_target_snapshot.py), `build_current_bundle_snapshot()` |
| Where the single current proof check is | [plan_lint.py](../../../scripts/plan_lint.py), `preflight_current_review_proof()` |
| How the lanes and the shared artifact are checked | [review_artifact_lint.py](../../../scripts/review_artifact_lint.py), `lint_review_artifacts()`; the CLI selector `--select-risk-lane` |
| How the current review affects the readback | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `classify_review_readback()` |
| How the acceptance of Architect is read in a sibling | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `_arch_acceptance()` and `validate_done_admission()` |
| Where the responsibility of Architect is described | [architect.md](../../roles/architect.md) (in Russian), the `Architect arch review` section |
| How Manager launches the two Reviewer lanes and the selection script between them | [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md), the subitem `4c) Reviewer logical dispatch` |
| How the command chooses the commit policy | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_sibling()` and `_planveyor_role_prompt_body()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_final_status_without_risk_lane_is_reported`, `test_final_status_without_contracts_lane_is_reported` | Each test removes the matching lane section and requires one finding `missing_final_lane_sections` with its name. This is the structural completeness of the final artifact, not the expert quality of the review |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_preflights_referenced_support_before_selected` | Checks code `0`, `state=selected`, a matching `run_id`, and unchanged plan/support bytes. The fixture uses `BUNDLE=staged`; this is not an independent proof of the whole current-bundle chain |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_final_dual_lane_rejects_stale_matching_current_bundle_hash` | Requires the finding `current_review_proof_compact_snapshot_invalid` and no `dual_lane_target_snapshot_mismatch`: two identical claims can still be an unusable current proof |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_arch_verdict_uses_only_unique_actual_section_and_first_line` | A non-acceptance, a conditional or second line, a duplicate section, and a fenced example raise `Blocked`; the state does not change. The exact verdict is accepted in upper case too. The fixture context does not prove a real role run |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_blocks_referenced_support_and_clears_identity` | The detailed record file contains an expanded path to the Homebrew interpreter: code `1`, `state=blocked`, `error_code=expanded_homebrew_python_command_evidence`; `selected_line`, `run_id`, and `target_snapshot` are empty |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_direct_native_after_human_call_ignores_ambient_selector_and_history` | After `planveyor sibling architect`, the Architect prompt contains `COMMIT_POLICY=human_explicit`; the next direct call of `planveyor_arch` through the facade gets `COMMIT_POLICY=native_existing`, although the environment sets `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; the index stays empty. In the fixture, the Codex client is replaced with a script that only records the prompt |

## Task closeout

Chapter: [Task closeout](closeout.md).

### Where to read the implementation

| Question | File and symbol |
| --- | --- |
| How `close` checks the task, makes the task commit and, if needed, the documents commit, and how `ready` reads the result | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `handle_close()` and `handle_ready()` |
| How the exact bundle is assembled, staged, and checked | [planveyor.zsh](../../../scripts/planveyor.zsh): `planveyor_plan_bundle`, `planveyor_plan_closeout_preflight` |
| How the docs closeout is classified and in which order the roles are called | [docs_closeout.py](../../../scripts/docs_closeout.py): `classify_docs_closeout` and `DISPATCH_FAMILY` |
| What launches the roles of the two stages | [docs_finalize.zsh](../../../scripts/planveyor/docs_finalize.zsh): the public role wrappers of the two families |
| Who writes the process improvements | [process_improvements_collect.py](../../../scripts/process_improvements_collect.py) |
| Who writes the follow-ups | [followups_apply.py](../../../scripts/followups_apply.py) |
| How the message of the documents commit is built | [followups_capture.py](../../../scripts/followups_capture.py), `_resolve_commit_message()` |
| Why a plan in `Done` cannot keep open `## Post-merge gate` items | [plan_lint.py](../../../scripts/plan_lint.py), `validate_done_post_merge_gate_checklist()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_docs_closeout.py](../../../scripts/test_docs_closeout.py): `test_terminal_commit_ready_remains_blocked_until_semantic_commit_materializes` | Requires `blocked` and `semantic_closeout_commit_pending`; readiness to commit does not count as the commit itself |
| [test_docs_closeout.py](../../../scripts/test_docs_closeout.py): `test_dispatch_family_orders_general_then_followups` | Checks the exact eight role/lane pairs, not a real launch of eight AI sessions |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_preview_and_declined_gates_have_no_status_index_or_history_effects` | `close` without `--commit` returns `semantic_ready`, the full list of paths, and the commit message; `HEAD`, the index, and the plan bytes do not change, no status is set, and Manager is not called |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_done_with_canonical_pending_semantic_delta_can_be_committed` | A plan in `Done` with an uncommitted bundle (`semantic_closeout_has_unstaged_delta`): `close` returns `semantic_ready`, `close --commit` returns `semantic_committed`, and the changed target file goes into the commit |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_ready_does_not_run_stack_commands_and_blocked_noop_is_not_ready` | With `state=blocked` of the docs closeout, `ready` returns `pending` and does not call `make`, `planveyor_plan_lint`, or `planveyor_manager_init` |

## Tests and evidence: what you can trust

Chapter: [Tests and evidence: what you can trust](testing-evidence.md).

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| How the form of the plan is checked | [plan_lint.py](../../../scripts/plan_lint.py), `lint_plan()` |
| How the task bundle is checked | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_bundle()` with the `--preflight`, `--scope-check`, and `--check` modes |
| How the target snapshot for the review is computed | [review_target_snapshot.py](../../../scripts/review_target_snapshot.py), `build_current_bundle_snapshot()`, `_bundle_sha256()` |
| How the review is compared with the current files | [plan_lint.py](../../../scripts/plan_lint.py), `preflight_current_review_proof()`, `select_plan_risk_lane_snapshot()` |
| How Oracle reads the review state and chooses the role | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `classify_review_readback()`, `review_operational_route()` |
| Why `planveyor sibling close` refuses with a stale review | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `validate_done_admission()`: requires `review_readback_state=ok`; `handle_close()` checks the Oracle answer again before the commit. The line `Вердикт: принято.` (verdict: accepted) is checked separately by `_arch_acceptance()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_blocks_stale_or_removed_current_producer_target` | On a temporary Git repository, the risk lane record selection first returns `selected`. After an edit of the target file, it gives code `1`, `state=blocked`, and `current_review_proof_producer_mismatch`; after the file is deleted, `current_review_proof_producer_or_support_unavailable`. The test does not launch the roles live |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_green_review_snapshot_mismatch_routes_to_reviewer_and_blocks_terminal_state` | Replaces the review lint with one that reports a snapshot mismatch (`current_bundle_target_snapshot_mismatch` or `dual_lane_target_snapshot_mismatch`) and expects `stale_green_review`, the route `reviewer_same_file_rewrite_required`, Reviewer as the next role, and `terminal_ready_state=blocked`. The review lint itself is replaced in this test |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_early_status_red_or_stale_review_and_owner_question_block` | Substitutes the Oracle answer: a status before acceptance, `stale_green_review`, `live_blocker`, an open Owner question, or a triggered route guard. In each case, `handle_close()` with `--commit` refuses, and HEAD, the index, and the plan file stay unchanged |

## Sibling: creation and upgrade

Chapter: [Sibling: creation and upgrade](sibling-lifecycle.md).

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| The human layer of selection and the next action | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_init`, `handle_upgrade` |
| Creating, checking, and carrying over the contract | [consumer_contract.py](../../../scripts/consumer_contract.py): `init`, `upgrade`, `local_sections`, `notices`, `adaptation_plan`, `doctor` |
| Why `sibling upgrade` does not show the reason when it stops with a candidate | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `Context.call` shows only stderr on a nonzero code, and `main` in [consumer_contract.py](../../../scripts/consumer_contract.py) prints JSON with `problems` and `candidate` to stdout |
| Plan commit, docs closeout, and readiness | [sibling_closeout.py](../../../scripts/sibling_closeout.py): `handle_close` shows the bundle, with `--commit` moves the accepted plan to `Done` and commits its exact bundle, and after the Manager turn commits the documents in a separate call; `handle_ready` only reads the state of the contract, the plan, and the docs closeout |

| Route | Canonical instructions | Entry point into the implementation |
| --- | --- | --- |
| Init | [Stack sibling guide](../stack-sibling.md), project creation | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_init()` → [consumer_contract.py](../../../scripts/consumer_contract.py): `init()` |
| Upgrade | [Stack sibling guide](../stack-sibling.md), getting a new version | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_upgrade()` → [consumer_contract.py](../../../scripts/consumer_contract.py): `upgrade()` and `adaptation_plan()` |

The Python function names in the table are addresses for reading the implementation. User calls come from the guide and `planveyor_help`; do not turn internal helpers into an alternative public interface.

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_compatible_upgrade_preserves_local_section_and_swaps_only_after_checks` | Checks that the original is unchanged before the swap, the section bytes in the target and in the backup, the presence of the plan, and the result `updated_pending_adaptation` |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_acceptance_refuses_uncommitted_candidate_and_preserves_original` | Requires a refusal and the unchanged state of the original; no backup appears before the acceptance |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_acceptance_refuses_lost_local_text_and_preserves_original` | Requires `blocked`, an intact original, and a retained candidate even after its commit |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_copier_and_lint_failures_retain_only_a_candidate` | On a Copier error, expects `blocked` with `Copier exited 17`; when the generated upgrade plan fails the linter, the refusal `generated adaptation plan failed lint` and `candidate retained`. In both cases, the original does not change and the candidate stays: the plan is created before the directories are swapped |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_upgrade_inside_target_refuses_before_any_swap` | `sibling upgrade` from a directory inside the project exits with a nonzero code and the word `Выйдите` (leave) in stderr; the project HEAD is unchanged, and there is no backup |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_upgrade_from_outside_preserves_local_sections_and_selects_returned_plan` | From outside, with `--project`: the output has `адаптация ещё открыта` (the adaptation is still open), the local text is kept, the current plan is `contract_upgrade_` with the status `architect initial draft`, and there is one backup |

These assertions establish the carry-over mechanics on a fixture. They do not accept a stack brief, do not launch real roles, and do not prove that your product works.

## Exchanging changes with Planveyor

Chapter: [Exchanging changes with Planveyor](change-packets.md).

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| The contract notice format and its path into the upgrade plan | [Notice format](../../contract_notices/README.md) (in Russian) and [consumer_contract.py](../../../scripts/consumer_contract.py): `validate_notice`, `notices`, `adaptation_plan` |
| Request import and ACK | [upstream_request.py](../../../scripts/upstream_request.py): `cmd_import`, `cmd_ack`. `_ensure_source_local` compares the project root with the engine root; the wrapper `_planveyor_upstream_request_helper_run` in [planveyor.zsh](../../../scripts/planveyor.zsh) passes both roots. `ack` does not accept an execution reference without a decision reference and does not check whether the files at the references exist (F28) |
| The rollout packet and the recipient's outcome | [rollout_packet.py](../../../scripts/rollout_packet.py): `cmd_create`, `cmd_adoption_plan`, `cmd_outcome_set`, `cmd_ack`; the full vocabulary of outcomes is `CANONICAL_TARGET_OUTCOMES`, and an unknown value is rejected |
| Ownership between the source and the target | [Rollout ADR](../../adr/005-rollout-packet-is-handoff-not-execution.md) (in Russian) |
| Why the post-merge check does not create packets for a sibling | [post_merge_packetization_gate.py](../../../scripts/post_merge_packetization_gate.py): the empty table `EXPLICIT_TARGET_APPLICABILITY`; the production code does not derive a sibling obligation from a guess |

| Route | Canonical instructions | Entry point into the implementation |
| --- | --- | --- |
| Upstream | [CONTRIBUTING](../../../CONTRIBUTING.md) and [Lifecycle and packets](../lifecycle-and-packets.md) | [upstream_request.py](../../../scripts/upstream_request.py): `cmd_import()` and `cmd_ack()`; [request template](../../upstream_packets/_template.md) |
| Rollout | [Lifecycle and packets](../lifecycle-and-packets.md) | [rollout_packet.py](../../../scripts/rollout_packet.py): `cmd_create()`, `cmd_adoption_plan()`, `cmd_outcome_set()`, `cmd_reconcile()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_validate_notice_requires_five_clean_fields_and_every_array_item` | Checks the format of all five fields, including every line of an array; it does not assess the semantic usefulness of the instruction |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_unreadable_non_deleted_notice_refuses_upgrade_before_candidate_or_backup` | An unreadable notice in the range gives the refusal `cannot read notice in source history`; the state of the source and the target is unchanged, and neither a candidate nor a backup appears |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_import_creates_source_local_process_row_and_updates_packet` | Requires a PI file, the status `imported`, and empty decision/execution refs: an import is not yet a decision |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_import_rejects_wrong_root_without_mutation` | An import with a repository root other than the Planveyor root exits with code 1 and the message `source-local only`; the request does not change, and `docs/process_improvements` does not appear in the target |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_ack_rejects_execution_without_decision_and_does_not_mutate` | Requires a refusal and an unchanged request for an execution ref without a decision ref |
| [test_rollout_packet.py](../../../scripts/test_rollout_packet.py): `test_target_inbox_json_exposes_imported_as_awaiting_target_outcome` | Explicitly checks that a target outcome is awaited after the import ACK |
| [test_rollout_packet.py](../../../scripts/test_rollout_packet.py): `test_reconcile_target_readback_accepts_only_structured_outcomes` | Accepts exactly the matching structured carrier and rejects prose-only carriers and mismatching id/path; the source and target bytes stay unchanged |

These are helper fixtures, not proof that a GitHub issue was sent, a fix was accepted, or a rollout was completed in your project.

## What works now and what comes next

Chapter: [What works now and what comes next](capabilities-boundaries.md).

### Where to read the implementation

| Limit | File and key symbol |
| --- | --- |
| Which Python versions the launch check lets through (3.10–3.12; only 3.12 is supported) | [_pybin.sh](../../../scripts/_pybin.sh), `planveyor_pybin_validate_version()`; `requires-python` in [pyproject.toml](../../../pyproject.toml) |
| Explicit queue recovery (F23) | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_q_recover()`; [plan_queue.py](../../../scripts/plan_queue.py), the `recover` command |
| Contract notices during a sibling upgrade (F27) | [consumer_contract.py](../../../scripts/consumer_contract.py), `validate_notice()`, `notices()`, `adaptation_plan()` |
| Rollout packets (F29) | [rollout_packet.py](../../../scripts/rollout_packet.py); the `planveyor_rollout_packet_*` commands in [planveyor.zsh](../../../scripts/planveyor.zsh) |
| Splitting paths in a range review (F43) | [range_review_risk_packet.py](../../../scripts/range_review_risk_packet.py), `RUNTIME_PREFIXES`, `classify_changed_paths()` |
| Settings files of the post-merge check in a sibling | [merge_gate_policy.py](../../../scripts/merge_gate_policy.py), `POLICY_PATH`, `_policy_for_context()`; [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_engaged_inputs()`; [contract_authority_context.py](../../../scripts/contract_authority_context.py), `read_declared_bytes()` |
| The `planveyor sibling` commands | [sibling_runbook.py](../../../scripts/sibling_runbook.py): the subcommands `init`, `plan`, `architect`, `answer`, `run`, `tui`, `close`, `ready`, `upgrade` |
| Which agent harness is allowed for which role | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_runner_set()`: Architect, Coder, and Manager only `codex`; Planner and Reviewer `codex` or `claude` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_validate_notice_requires_five_clean_fields_and_every_array_item` | A notice that lacks any of the five fields, has a field of the wrong type, or has an empty or multiline `summary` is rejected with `invalid notice schema`. The test checks the form of the notice; it does not decide when a notice is required (F27) |
| [test_planveyor_review_range_init.py](../../../scripts/test_planveyor_review_range_init.py): `test_local_v2_semantic_provenance_uses_current_content_metadata` | The helper `_run_local_v2_render` itself writes `review_range_policy.v1.json` into the temporary project and only then starts the range review preparation; the test expects code `0` and `policy_json` as the first input of the receipt. A sibling created from the template does not have this file |

## Launch: commands, wrappers, agent harnesses

Chapter: [Launch: commands, wrappers, agent harnesses](runtime-launch.md).

### Where to read the implementation

| What you want to understand | Where to read | What to look for |
| --- | --- | --- |
| How the runtime and the project are chosen | [bin/planveyor](../../../bin/planveyor) | The handling of `--project`, the separate `sibling` branch, the start of a child `zsh -df` |
| How a command name reaches its handler | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `planveyor_cli()` and `planveyor_sibling()` |
| How the ordinary Owner actions work | [scripts/sibling_runbook.py](../../../scripts/sibling_runbook.py) | `parser()`, `handle_init()`, `handle_answer()`, `handle_upgrade()`; `close` and `ready` are in [scripts/sibling_closeout.py](../../../scripts/sibling_closeout.py), `handle_close()` and `handle_ready()` |
| How `sibling architect` and `run` prepare the session | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `_planveyor_sibling_ensure_native_session()`; the receipt check is `session_check()` in [scripts/sibling_runbook.py](../../../scripts/sibling_runbook.py) |
| What a specific Architect launch looks like | [scripts/planveyor/role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh) | `planveyor_arch()`; this is an example of one route, not a universal algorithm for all roles |
| How a role session is created | [scripts/planveyor/session_init.zsh](../../../scripts/planveyor/session_init.zsh) | `planveyor_arch_init()`, `planveyor_manager_init()` |
| Where the phase prompt comes from | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `_planveyor_role_prompt_body()`, which prints `COMMIT_POLICY=…` as its first line; then [architect_status_driven.md](../../tools/prompts/architect_status_driven.md) (in Russian) |
| Which agent harness is allowed for a role | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `planveyor_runner_set()`, `_planveyor_default_runner_for_role()`; the Claude Code call is `_planveyor_private_provider_claude_direct_run()` in [scripts/planveyor/provider_runtime.zsh](../../../scripts/planveyor/provider_runtime.zsh) |
| How Manager collab is launched | [scripts/planveyor/role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh) | `planveyor_manager_collab_cmd()`; the Manager algorithm is [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md) |
| How the plan state is read | [scripts/plan_status_oracle.py](../../../scripts/plan_status_oracle.py) | `oracle_result()`; the public wrapper `planveyor_plan_status_oracle()` is defined in `scripts/planveyor.zsh` |

### What the tests check

| Test | What the test code checks | Limit of the conclusion |
| --- | --- | --- |
| `test_collab_prompt_dispatches_the_configured_role_types` in [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py) | The prompt names the exact agent types, the reuse mechanisms, and the allowed collaboration APIs | This checks the text contract, not the actual model response |
| `test_home_ensure_selects_consumer_home_without_rewriting_agent_roles` in [the same file](../../../scripts/test_planveyor_codex_agent_roles.py) | The existing configuration of the selected agent harness is kept; missing role files are not created automatically | The isolation of the setup is confirmed for the test environment; authentication is not checked |
| `test_existing_home_startup_reconcile_preserves_root_model_runtime_and_extra_agents` in [the same file](../../../scripts/test_planveyor_codex_agent_roles.py) | The model, the execution settings, and the extra agents configured by Owner stay unchanged | Support for every possible configuration does not follow from one test |
| `test_runner_matrix_readback_and_unknown_runner_fail_closed` in [test_planveyor_init_capture.py](../../../scripts/test_planveyor_init_capture.py) | After `planveyor_runner_set`, reads the choice for five roles: `claude` for Planner and Reviewer, `codex` for the others; `coder bogus` gives `Usage`, and `coder claude` gives `Unsupported runner for role=coder: claude` | Checks the choice of the agent harness; the agent harnesses themselves are not started |
| `test_custom_reviewer_lane_init_uses_distinct_session_keys_and_runner_matrix` in [the same file](../../../scripts/test_planveyor_init_capture.py) | With the `claude` agent harness for Reviewer, the two lanes get their own pointers `.planveyor.session.reviewer_code_risk` and `.planveyor.session.reviewer_code_contracts`, and there is no shared `.planveyor.session.reviewer`; the call gets `--model`, `--effort`, `-p`, and `--permission-mode acceptEdits` | Claude Code is replaced with a stub in the test |
| `test_architect_wrong_status_refuses_before_native_init` in [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py) | `sibling architect` in the `Ready for Coder` status exits with an error, does not call init, and does not create `.planveyor.session.architect` | Init and the Architect wrappers are replaced with stubs in the test |
| `test_actual_architect_cold_init_and_reused_resume_get_current_human_policy` in [the same file](../../../scripts/test_sibling_runbook.py) | Three `sibling architect` calls give four Codex calls: the first one (init) goes without `resume`, and all the next ones, including the turn in the same first `sibling architect`, go with `resume`, `PLAN_PATH`, and `PRE_STATUS_LINE`; all calls have `COMMIT_POLICY=human_explicit` | Codex is replaced with a stub that records the arguments and the message |
| `test_direct_native_after_human_call_ignores_ambient_selector_and_history` in [the same file](../../../scripts/test_sibling_runbook.py) | A direct `planveyor_arch` after `sibling architect` gets `COMMIT_POLICY=native_existing`, even if the environment has `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; nothing appears in the Git index | Codex is replaced with the same stub |
| `test_direct_manager_resume_after_human_run_uses_fresh_native_policy` in [the same file](../../../scripts/test_sibling_runbook.py) | A direct `planveyor_manager_collab_cmd run <plan>` after `sibling run` continues the same Manager session, but with `COMMIT_POLICY=native_existing`, even if the environment has `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; no queue file appears | Codex is replaced with the same stub |

## How Planveyor changes itself

Chapter: [How Planveyor changes itself](self-development.md).

### Where to read the implementation

- [Prompts README](../../tools/prompts/README.md): the shared corpus and the declared target-local sources.
- [Docs architecture](../../playbooks/docs_architecture.md) (in Russian): source ownership, delivery, and derived outputs.
- [planveyor.zsh](../../../scripts/planveyor.zsh): `_planveyor_prompt_file_for_role_phase` and the public entry points.
- [Engine modules](../../../scripts/planveyor/README.md): the purpose and the loading order of the modules.
- [check_planveyor_profile_contract.py](../../../scripts/check_planveyor_profile_contract.py): `EXACT_BUNDLE`, `INVARIANT_IDS`, `_check_doc_lint`.
- [build_role_bundles.py](../../../scripts/build_role_bundles.py): assembling the role context from the sources.
- [shared_docs_mirror_drift.py](../../../scripts/shared_docs_mirror_drift.py): the declared mirror membership and the read-only report.
- [Collect](../../../scripts/process_improvements_collect.py) and [triage](../../../scripts/process_improvements_triage.py): collecting a proposal and the decision fields.
- [Promote](../../../scripts/process_improvements_promote.py) and [reconcile](../../../scripts/process_improvements_reconcile.py): the execution pointer and the confirmation of the raw PI state.
- [Description of process improvements](../../process_improvements/README.md) (in Russian): the statuses of a PI row, the triage fields, and the commands for collection, triage, promotion, and reconciliation.
- [consumer_contract.py](../../../scripts/consumer_contract.py): `validate_notice()` checks the five fields of a notice, `notices()` reads the notices of a commit range, and `adaptation_plan()` carries into the upgrade plan the path, the commit, and the `summary` of a notice (into `## Scope`), `checks` (into `## Tests`), and `sibling_actions` (as `Действие:` (action) lines in `## Evidence`).
- [docs_closeout.py](../../../scripts/docs_closeout.py): `classify_docs_closeout()`; an edit of the shared prompts, playbooks, or some templates during the docs closeout gives `final_docs_commit_reason=canon_delta_requires_process_improvement`.
- [Contract notices](../../contract_notices/README.md): where the notices are kept and how the upgrade reads them.

### What the tests check

In [test_check_planveyor_profile_contract.py](../../../scripts/test_check_planveyor_profile_contract.py), `test_doc_lint_rejects_comment_only_dispatch` replaces the owning call with a comment and requires the finding `doc_lint_gate`.
This shows that the presence of the command text does not count as a sufficient dispatch contract.
`test_doc_lint_rejects_unrelated_function_dispatch` also rejects moving the needed text into an unrelated function.
These fixtures do not run doc lint and do not check the quality of the documents of a new change.

In [test_build_role_bundles.py](../../../scripts/test_build_role_bundles.py), `test_target_local_content_fails_closed_without_engaged_consumer_contract` requires code 3, no XML, and no call of `_build_context`.
The assertion checks the stop before a fallback is built; it does not prove that the agent harness session got the right model.

In [test_shared_docs_mirror_drift.py](../../../scripts/test_shared_docs_mirror_drift.py), `test_generic_policy_has_no_implicit_target_or_mirror_set` requires a generic set with zero paths.
`test_helper_is_read_only_against_target_files` compares the target bytes before and after the report.
They confirm the declared membership and the absence of writes, not the delivery of an update.

In [test_process_improvements_promote.py](../../../scripts/test_process_improvements_promote.py), `test_promote_apply_requires_existing_repo_local_ref_and_never_scaffolds_it` requires a refusal for a missing plan, no created file, and an unchanged `triaged` status. It checks the PI promotion, not the execution of the proposal.

In [test_sibling_contract_docs.py](../../../scripts/test_sibling_contract_docs.py), `test_template_copies_match_their_docs_sources_byte_for_byte` compares every copy in `copier_template/` with its source in `docs/` or `skills/` byte for byte and requires every copied directory to be marked as a full or partial mirror.
In [test_censor_prompt_contract.py](../../../scripts/test_censor_prompt_contract.py), `test_copier_censor_prompts_deliver_the_shared_final_readback_contract` does the same for the three CENSOR prompts.

In [test_planveyor_profile_extraction.py](../../../scripts/test_planveyor_profile_extraction.py), `test_public_checker_uses_only_root_owners_and_passes_finite_fixture` runs `check_planveyor_profile_contract` on the Planveyor root and expects an empty list of findings; the same test checks that there are nine rules. Through this test, the profile contract check is part of the full unit test run.

In [test_consumer_contract.py](../../../scripts/test_consumer_contract.py), `test_validate_notice_requires_five_clean_fields_and_every_array_item` rejects a notice that lacks any of the five fields, has a field of the wrong type, or has an empty or multiline string.
`test_unreadable_non_deleted_notice_refuses_upgrade_before_candidate_or_backup` checks that an unreadable notice stops the upgrade: the repositories do not change, and no candidate or backup is created.
`test_current_notice_history_and_strict_notice_are_valid` checks all notices in the repository history from the root commit to `HEAD` and all current files in `docs/contract_notices/`.

In [test_docs_closeout.py](../../../scripts/test_docs_closeout.py), `test_final_docs_commit_blocks_unowned_protected_review_canon_delta` changes a protected review template after `Done` and expects `final_docs_commit=required` with the reason `canon_delta_requires_process_improvement`; the template path goes into `protected_docs_delta_paths` and into the handoff to Architect.

## Post-merge check

Chapter: [Post-merge check](postmerge.md).

### Where to read the implementation

| Question | File and symbol |
| --- | --- |
| How Manager drives the tracker steps | [manager_collab_merge_pipeline.md](../../tools/prompts/manager_collab_merge_pipeline.md) (in Russian), the command `MANAGER_CMD=merge_run` |
| Which step is next | [merge_tracker_oracle.py](../../../scripts/merge_tracker_oracle.py) |
| How merge mode is launched | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `planveyor_merge_collab_cmd()` and `planveyor_merge_apply_collab_cmd()` |
| Wrappers of separate steps | [planveyor.zsh](../../../scripts/planveyor.zsh): the wrappers of the merge steps |
| Why a project with the marker needs a step policy file | [merge_gate_policy.py](../../../scripts/merge_gate_policy.py), `_policy_for_context()` |
| How the range-review scaffold is created | [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_host_family()` and `run()` |
| Which files the range review reads in a project with the marker | [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_engaged_inputs()` |
| Where the artifact check of a separate step is | [post_merge_receipt_preflight.py](../../../scripts/post_merge_receipt_preflight.py): the artifact check of a separate step |
| How the report on rollout packets is built | [post_merge_packetization_gate.py](../../../scripts/post_merge_packetization_gate.py), `build_payload()` |

### What the tests check

| Named test | Exact assertions and the limit of the conclusion |
| --- | --- |
| [test_post_merge_receipt_preflight.py](../../../scripts/test_post_merge_receipt_preflight.py): `test_post_merge_audit_shared_range_requires_active_structural_packetization_report` | Rejects missing, wrong-range, ambiguous, and malformed reports; a green fixture still has `terminal_readiness=not_evaluated` |
| [test_merge_policy_effect_boundaries.py](../../../scripts/test_merge_policy_effect_boundaries.py): `test_matching_generic_consumer_admits_merge_tracker` | A project with the Planveyor marker and a declared policy file gets the tracker: code `0`, and the header has `POLICY_SCHEMA=planveyor_merge_gate_policy.v1` and `AUTHORITY_GENERATION`. The fixture creates the policy file itself |
| [test_planveyor_review_range_init.py](../../../scripts/test_planveyor_review_range_init.py): `test_public_shell_generic_consumer_emits_lintable_matching_v2_receipt` | A project with the Planveyor marker and the file `review_range_policy.v1.json`: the public command `planveyor_review_range_init` gives code `0`, and the review plan carries the provenance record `review_range_semantic_provenance.v2` with the project identity and passes `plan_lint.py` with code `0`. The fixture creates the policy file itself |
| [test_merge_gate_policy.py](../../../scripts/test_merge_gate_policy.py): `test_invalid_generic_engaged_consumer_never_falls_back_to_legacy_policy` | A project with the marker whose identity equals `default`, contains invalid characters, or differs from the marker gets `merge_policy_capability_required`; the engine does not fall back to the built-in list of steps |

## Engine tests

Chapter: [Engine tests](engine-tests.md).

### Where to read the implementation

| Question | File and key symbol |
| --- | --- |
| Which targets run the tests and the checks | [Makefile](../../../Makefile): `test-scripts`, `verify`, `verify-full`, `doc-lint` |
| How Python is chosen and its version is checked | [_pybin.sh](../../../scripts/_pybin.sh), `planveyor_pybin_resolve()`, `planveyor_pybin_validate_version()` |
| How the facade runs the integrity checks | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_verify()` |
| How modules are registered and selected | [verify_suite.py](../../../scripts/verify_suite.py), `register()`, `_REGISTRY`, `_load_modules()` |
| Which checks the `portability` module includes and when test discovery is added | [verify_suite.py](../../../scripts/verify_suite.py), `PortabilityModule.run()`, `check_test_scripts()` |
| How the result and the exit code are computed | [verify_suite.py](../../../scripts/verify_suite.py), `Result`, `main()`, `_render_plain()`, `_render_json()` |
| Which roots and links the documentation linter checks | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_doc_lint()`; [doc_lint.py](../../../scripts/doc_lint.py), `main()`, `lint_file()` |
| What the example test of the handoff digest checks | [plan_handoff_digest.py](../../../scripts/plan_handoff_digest.py), `build_digest()`, `_read_code_draft_host()` |
| Shared fixture helpers | [process_contract_fixtures.py](../../../scripts/test_support/process_contract_fixtures.py), `run_zsh_fixture()`; [test_contract_authority_support.py](../../../scripts/test_contract_authority_support.py), `AuthorityFixture` |

### What the tests check

| File and test | Setup and assertion | Why it is needed |
| --- | --- | --- |
| [test_plan_handoff_digest.py](../../../scripts/test_plan_handoff_digest.py), `test_missing_code_draft_fails_closed` | Creates a temporary plan and review without a draft; expects `state == "missing"` and a blocker with `host == "code_draft"` | The handoff digest still stops when a source is missing |
| [test_planveyor_shared_corpus_contract.py](../../../scripts/test_planveyor_shared_corpus_contract.py), `test_generic_reviews_preserve_supplied_spec_and_diff_transport` | In two playbooks, each SPEC/DIFF marker occurs exactly once; the start comes before the end | The task context and the diff have unambiguous boundaries |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_discovery_matches_makefile_and_streams_combined_transcript` | Substitutes a process with exit `1`, one ERROR, and seven tests; checks the discovery argv and `Result(..., "fail", "Ran 7 tests, 1 FAIL/ERROR", ...)` | The aggregator builds the discovery call correctly and interprets the transcript of the substituted process |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_default_run_keeps_fast_integrity_checks_but_omits_unselected_inputs` | Checks the list of the usual integrity checks; discovery and the checks of an unselected plan/archive are not called | The fast check does not extend its claim to absent inputs |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_full_run_adds_discovery_once_and_omits_portability_module_overlap` | `check_test_scripts` is called exactly once; the old separate pass over the portability tests is gone | The full route has one canonical discovery point |
| [test_planveyor_admission_integration.py](../../../scripts/test_planveyor_admission_integration.py), `test_real_downstream_na_admission_and_public_refusal_are_state_safe` | The public lint accepts the fixture with a carrier (exit `0`) and rejects it without a carrier (exit `1`); the queue and state snapshots match before and after the refusal | The admission check works through the facade and keeps the state on a refusal |

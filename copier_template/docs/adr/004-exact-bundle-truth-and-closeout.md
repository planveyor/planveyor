---
status: "accepted"
date: 2026-04-21
decision-makers: Architect
source-range: "N/A (why=formalized from already-landed process canon rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/plans/README.md; docs/plans/_template.md; docs/roles/reviewer.md; docs/roles/architect.md"
---

# Exact bundle truth и closeout живут в explicit file-backed carriers

## Context and Problem Statement

Process closeout уже зависит от literal bundle resolve: `code_draft_meta.targets`, `PLAN_PATH`, code draft, `## Review artifacts` и explicit review assets. Без formal ADR этот contract оставался разбросан по template, reviewer/architect docs и helper prose, поэтому bundle drift легко маскировался под “ну примерно эти файлы”. Post-review materialization теперь дополнительно нуждается в отдельной preflight-классификации для runtime branch: semantic/bundle truth остаётся в exact bundle helper, а git metadata writability и safe local commit command должны быть названы отдельно.

## Decision Drivers

- deterministic selective staging / closeout без heuristic `git status`
- exact reviewer scope и exact architect closeout bundle
- один file-backed contract для implementation, review и final commit prep

## Considered Options

- Bundle собирается эвристикой из текущего diff и человеческой памяти.
- Bundle живёт только в explicit carriers: `code_draft_meta.targets` + plan + code draft + live review artifact + explicit assets.

## Decision Outcome

Выбранный вариант: **exact bundle truth materialize-ится только через explicit file-backed carriers**, потому что review scope, closeout staging и local commit должны опираться на literal paths, а не на эвристический diff summary. `code_draft_meta.targets` задаёт authoritative implementation/doc set; к нему на review/closeout добавляются `PLAN_PATH`, code draft, live review artifact и explicit asset refs.

Каждый parseable plan-resident JSON carrier с `lane_id=reviewer_code_risk`, который объявляет хотя бы один из `full_payload_ref` / `full_payload_sha256`, добавляет обязательную пару в all-history manifest exact bundle. Пара должна быть полной, repo-relative, symlink-free (leaf и каждый ancestor) и hash-valid; missing ref/hash/file, unsafe/symlink ref, hash mismatch или конфликтующие hashes одного ref блокируют bundle/closeout до staging, delegation или commit. Historical carrier доказывает только durable bytes и может оставаться legacy/red; JSON/schema/parity semantics проверяются только у helper-selected current carrier. Invalid manifest возвращает `bundle_ok=false` и non-materialized closeout, а не допускает частичную materialization.

Fresh `BUNDLE=current` review proof имеет один canonical reader: `scripts/plan_lint.py:preflight_current_review_proof`. Ordinary plan использует immutable full `review_target_snapshot.v2` из primary `code_draft_meta.targets`; admitted strict N-A `decomposition_wave` parent без parent draft использует discriminated `review_target_snapshot.v3` с `source.kind=strict_na_decomposition_graph` и exact `N` canonical child plans + `N` same-stem child drafts. Обе версии fail-close требуют exact top-level `**Target:** BUNDLE=current bundle_sha256=<64 lowercase hex>`, exact compact two-key `target_snapshot`, matching nested projection и fresh equality с canonical producer. Alias/reordered/prefix/suffix/duplicate carrier, manual SHA, partial graph, missing/stale/red support или producer failure дают `blocked`. `review_artifact_lint`, `planveyor_plan_bundle`, oracle и docs-closeout являются read-only projectors этого result; prose, header-only green, manual hash и terminal historical artifact не создают current-proof authority или второй parser.

`planveyor_plan_closeout_preflight <PLAN_PATH>` принят как thin normalization layer над `planveyor_plan_bundle --closeout-json`: он возвращает `semantic_ready`, `semantic_verdict`, `bundle_ready`, `staged_exact`, `git_writable`, `commit_ready`, `closeout_state`, `next_owner` и `safe_command`, но не резолвит bundle повторно и не расширяет explicit carriers. `safe_command` допустим только для exact staged bundle + writable git metadata + единственного source commit skeleton; staged mismatch/current-red/missing review artifact/git metadata blocker fail-closed без safe command.

Docs-closeout tail использует отдельный helper-owned payload schema gate: `planveyor_docs_closeout <PLAN_PATH> --json` возвращает `schema=docs_closeout_payload.v1`, `schema_state=ok|blocked`, `schema_errors=[]` поверх existing closeout/readback fields. Schema gate валидирует форму operator/Manager payload и fail-closed для malformed nested carriers; он не меняет semantic closeout criteria и не заменяет exact bundle/materialization preflight.

Ordinary no-cycle foreign-only docs delta остаётся diagnostic-only: он не попадает в `final_docs_diff_paths`, staging expectations или final docs commit handoff. Если no-cycle delta содержит exact-owned path, closeout остаётся `blocked` с `final_docs_commit=no_op` до finalized capture proof; fake staging expectations запрещены. Существующая protected reclassification остаётся отдельным исключением.

Финальный handoff перед push в merge-mode имеет отдельный operational report surface: `planveyor_merge_bundle_report` читает saved range, merge tracker, known range artifacts и `git status` только как read-only summary перед `step:ready_to_push`. Этот report не подменяет exact bundle truth обычного dev-plan и не даёт staging/commit authority.

## Consequences

- Плюс: Reviewer и Architect могут независимо восстановить один и тот же bundle.
- Плюс: helper surfaces вроде `planveyor_plan_bundle` остаются inspectable mirrors, а не скрытой второй истиной.
- Плюс: runtime branch отличает semantic closeout blockers от local materialization blockers через `closeout_state`, не сваливая git metadata/staged mismatch в full semantic rerun narration.
- Риск: любой stale target list или placeholder review asset сразу ломает truthful closeout.

## Canonical refs

- `docs/plans/README.md`
- `docs/plans/_template.md`
- `docs/roles/reviewer.md`
- `docs/roles/architect.md`

## Related ADRs

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/005-rollout-packet-is-handoff-not-execution.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "code_draft_meta.targets|exact bundle|Review artifacts" docs/plans/README.md docs/plans/_template.md docs/roles/reviewer.md docs/roles/architect.md`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/004-exact-bundle-truth-and-closeout.md --root docs/plans/README.md --root docs/plans/_template.md --root docs/roles/reviewer.md --root docs/roles/architect.md`

## Revisit signals

- Closeout bundle перестаёт быть file-backed и уходит в другой canonical artifact family.
- Reviewer или Architect больше не могут восстановить current bundle из plan/code draft/review artifacts без внешней эвристики.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

## Strict N-A parent no-draft contract

`strict N-A parent` is an active/parked `decomposition_wave` parent with a
valid N-A MAD, literal `Code draft(s): N/A (why=...)`, no live parent-draft
ref, and no same-stem file. Its only admission is oracle-derived
`not_required`; this never waives a required/ordinary plan draft.

- Candidate mode is inspection-only; it never grants stage, queue, or terminal authority.
- Use files-first materialization: create canonical child plans and same-stem child drafts before linkage.
- The derived parent planning bundle has one parent review and literal review assets, with no recursive child-target import.
- Preserve active-to-parked child-path continuity and no fabricated parent draft.
- Если требуется current-review proof, единственный producer выбирает v3 из полного oracle canonical child graph, а не из ограниченной routing projection `next_plans`. Его hash basis — ровно carriers child-plan/same-stem-draft `N+N→2N`; parent Evidence, review/support files и child implementation/deletion targets исключены.

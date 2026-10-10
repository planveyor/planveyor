# Playbook: Review route and receipt canon

Это компактный shared reference для process/docs slice'ов, которым нужно:
- truthfully materialize-ить `## Review artifacts`;
- быстро собрать `reviewability preflight receipt` без возврата к исторической plan-prose.

Этот playbook не переоткрывает helper/generator/lint logic. Enforcement описан в ADR; доставляемые шаблоны задают форму review artifacts:
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/code_reviews/_template_single_commit.md` и `docs/code_reviews/_template_merge_range.md`
- `docs/doc_reviews/_template_single_commit.md` и `docs/doc_reviews/_template_merge_range.md`

Принятые ADR:
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`

## Single live review route

- В active dev-plan держим ровно один live review artifact path для текущего bundle.
- Docs-only final bundle -> `docs/doc_reviews/{plan_stem}.md`.
- Любой final bundle с non-doc carrier -> `docs/code_reviews/{plan_stem}.md`.
- Если bundle flip-ится из docs-only в non-doc, plan + code draft + review host flip-ятся вместе в одном и том же literal route.
- Не держим одновременно `docs/doc_reviews/...` и `docs/code_reviews/...` как две live path-ветки “на всякий случай”.
- Historical/stale notes допустимы только как notes about the same current review file или explicit historical anchors; они не создают второй live route.

## Same-file rerun closeout states

- `current_green`: live review header is green, live synthesis is not contradictory, and no active quarantine blocks the artifact.
- `current_red`: live review header or synthesis still carries a blocker signal; this always blocks terminal closeout, even if older prose calls that blocker historical.
- `needs_reviewer_rerun`: active `Stale note` / `Rerun note` still points at the live review artifact without a later same-artifact `Rerun result`, or current verdict cannot be derived as green.
- `historical_reconciled`: the same live review file was rewritten in place and the current header is green/unambiguous, with explicit superseded/closed wording or same-artifact `Rerun result`.
- Allowed terminal-pass states are only `current_green` and `historical_reconciled`; the other two states stop `planveyor_plan_bundle` closeout.
- If current header is missing or not green, historical prose is context only, not proof of closeout.

## Reviewability preflight receipt

Минимум для compact shared receipt:
- `proof-path class`
- `mandatory primary lane`
- `mandatory non-primary carrier / contextual lane`
- `exact helper path + support files`
- `dependent tests / dependent docs / known consumer paths`
- `preconditions / seed-discovery`
- `reroute rule`
- `perceptual truth-source split`

Generic example для copy/paste полей:

```text
proof-path class: standard primitives
mandatory primary lane: PYTHONDONTWRITEBYTECODE=1 "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/YYMMDD_HHMM_topic.md
mandatory non-primary carrier / contextual lane: "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint
exact helper path + support files: docs/playbooks/<topic>.md, docs/plans/README.md
dependent tests / dependent docs / known consumer paths: future process/docs plans and quick-reference entrypoints
preconditions / seed-discovery: parked follow-up already promoted into this docs-only child; helper/lint enforcement stays read-only
reroute rule: if truthful closure requires helper/generator/lint edits instead of the bounded docs bundle, stop and open a separate follow-up
perceptual truth-source split: repo-backed canon/reference docs preferred; historical plans/followups = context only
```

Правило:
- если receipt называет non-primary lane или helper/support carrier, closure по нему должен быть literal в evidence;
- если profile-local motivating carrier нужен только для объяснения, маркируем его как motivating example, а не как default shared wording.

### State-transition declarations (opt-in)

Когда receipt должен обозначить только декларативную before/after границу, добавь literal `### State-transition declarations` с ровно четырьмя list-item rows: `before-state`, `allowed mutation inventory`, `after-state`, `protected-target post-review continuity`. Их canonical subfield grammar и plan/code-draft parity живут в `docs/plans/README.md`; `plan_lint.py` проверяет active block structural-only и не выводит runtime behavior из prose.

`protected-target ... targets` точно равен normalized `code_draft_meta.targets`, а не полному ADR 004 bundle. Поэтому `PLAN_PATH`, code draft, live review artifact, lifecycle/evidence writes и explicit assets не становятся protected target bytes. Literal `on_change=same-file-review-rerun` не создаёт новый stale verdict: same-file rerun выбирает только существующий producer-backed доказанный mismatch; unavailable/unknown producer остаётся fail-closed в текущей taxonomy.

HTML-comment examples в templates не активируют contract. Декларация additive: она не заменяет stateful `discovery-or-seed` / `receipt-reuse-only` / observer/readback / runtime-lineage rules и не разрешает ранний `Done` либо другой closeout order.

### Semantic review observation (opt-in)

Если `## Reviewability preflight receipt` plan содержит exact subsection `### Semantic review observation` с rows `schema=semantic_review_observation.v1`, `mode=required`, `writer=reviewer_code_contracts`, применяется отдельный producer-only handshake. Отсутствие marker-а — `not_available/feature_not_activated`: это legacy/non-opt-in absence, не inferred green и не задача Reviewer что-либо дописывать.

Для `BUNDLE=current` сначала materialize-ится compact selected `reviewer_code_risk` receipt в plan и immutable full versioned `review_target_snapshot` support asset: ordinary plan emits `review_target_snapshot.v2` from primary `code_draft_meta.targets`, а admitted strict N-A parent emits `review_target_snapshot.v3` from the complete canonical child graph. Plan хранит target/bundle SHA, `full_payload_ref` и `full_payload_sha256`, а asset хранит raw stdout byte-for-byte. Shared preflight в `scripts/plan_lint.py`, вызываемый selector CLI и `review_artifact_lint`, проверяет SHA, nested validated producer schema, exact target/hash projection и canonical `findings` projection по `id`, `severity`, `domain`, `title`, `source_refs`; одинаковая cardinality не доказывает parity. Raw full stdout в plan и generic large-fence exemption запрещены. Current review обязан literal-но назвать все current/historical support assets, чтобы exact bundle discovery не зависел от prose памяти.

Для fresh/current proof единственный strict reader — `scripts/plan_lint.py:preflight_current_review_proof`. Он принимает только один top-level `**Target:** BUNDLE=current bundle_sha256=<64 lowercase hex>`, compact `target_snapshot` с ровно двумя ключами `bundle_sha256` и `target`, immutable full `review_target_snapshot.v2` или discriminated strict-N-A `review_target_snapshot.v3` с той же nested projection и fresh equality с canonical producer. Current-shaped alias, reordered/prefix/suffix/duplicate carrier, mixed version, manual SHA, partial graph, missing/stale/red support или producer failure возвращают `blocked`; narrative prose не classifier input. `review_artifact_lint`, oracle, `planveyor_plan_bundle` и docs-closeout project-ят результат, не запускают второй current-proof parser. Terminal immutable history остаётся read-compatible, но никогда не даёт `current_green`.

После risk lane contracts lane сначала вызывает `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --project-root "$root" --select-risk-lane --origin-plan "$PLAN_PATH" --json`: только support-preflighted `state=selected` + exit `0` разрешает contracts finalization. `missing|blocked|non-zero` запрещает final artifact/status/P/F и возвращает ordinary recovery в `reviewer_code_risk`: новый immutable support/compact pair при необходимости, supersession old compact metadata, затем повторный selector readback; Manager/Owner не редактируют compact/support/P/F carriers вручную.

После helper-selected current `reviewer_code_risk` lane block и aggregate verdict contracts lane действует только так:

1. Вызывает read-only `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py semantic_review_observation.py --plan PLAN_PATH --format json`.
2. При `ready_to_materialize/role_proposal_required` append-ит в `PLAN_PATH::## Evidence` один fenced `semantic_review_observation_proposal.v1` с role fields `progress_verdict`, `progress_evidence_refs`, `blockers`, `resolved_predecessor_blocker_refs`. Proposal не содержит risk/snapshot/review/fingerprint/identity/family fields и не принимает unknown keys.
3. При `ready_to_materialize/observation_not_materialized` повторный helper read возвращает `materialization.observation`; contracts lane копирует этот complete final `semantic_review_observation.v1` object exactly, без ручного ID/fingerprint/family assembly.
4. Повторный read должен вернуть `valid/current_observation_valid`; это idempotent no-append readback и единственный допустимый producer result перед final Reviewer handoff.

`blocked` останавливает finalization; malformed/ambiguous selector, unbound carrier, duplicate eligible proposal, stale fingerprint/target snapshot, non-adjacent proposal/final pairing или manually typed machine fields не переходят в waiting/green. Clean active plan с zero raw risk fences и zero proposal/final carriers — отдельно `not_available/risk_generation_not_available` (active waiting).

Proposal `P` стоит физически после selected risk block. Его consuming final `F` должен быть immediately next semantic carrier после `P`, повторять helper-computed `proposal_sha256` и source generation (`risk_run_id`, `target_snapshot`, recomputed `review_generation_id`). Только accepted `F` становится append-only lineage node: первый имеет null predecessor, следующий ссылается на immediately preceding accepted head. `same_family` переиспользует family по literal `<review-artifact-path>#B<N>` из предыдущего head; `first_observation` и `independent_boundary` получают helper-seeded family. CENSOR, risk lane, Manager и transport retry не пишут P/F и не создают новую generation.

Consumers не интерпретируют prose или helper text как route authority. Только `valid/current_observation_valid` можно передавать checkpoint/metrics consumer-ам; `feature_not_activated` = legacy coverage absence, `risk_generation_not_available` = active waiting, `ready_to_materialize` = обязанность/возможность contracts lane, `blocked` = fail-closed без route/metric. Полная human schema, reason-code precedence и final field inventory живут в `docs/plans/README.md` → `Semantic review observation contract`.

При same-file rerun Coder до target mutation добавляет current-cycle `Stale note` + `Rerun note`, оставляя old compact receipt `current=true`, support asset и P/F immutable. После mutation helper остаётся blocked; единственный presentation-only Coder WARN допускается только по exact red same-file window с `semantic_current_target_snapshot_stale`, опционально вместе с одним `semantic_observation_machine_fields_mismatch` только для `contract_fingerprint`. Это не превращает historical carrier в current/green и не разрешает другой machine-field drift. Reviewer atomically переводит old compact receipt в `current=false` с `superseded_by=<new_run_id>`, пишет новый immutable asset и new compact receipt, переписывает тот же review artifact и только затем materialize-ит fresh P/F до `valid`.

### Semantic cycle checkpoint (opt-in consumer)

Checkpoint включается только paired exact marker-ом `### Semantic cycle checkpoint` (`schema=semantic_cycle_checkpoint.v1`, `mode=required`, `writer=architect`) рядом с active producer marker. Он читает только accepted `valid/current_observation_valid` sequence: raw review prose, CENSOR, risk retry, transport retry и same-snapshot rerun не являются occurrence.

`family_survival` требует adjacent heads, same family/ref и changed target snapshot; open `independent_boundary` и `scope_churn` trigger-ят сразу. Primary precedence = `family_survival > independent_boundary > scope_churn`, но required resolution exact-cover-ит sorted current family set. Architect append-ит один `semantic_cycle_checkpoint_resolution.v1` в `## Evidence`; `same_contract_once -> Coder intake`, `de_scope -> Reviewer intake`, `successor -> Superseded`, `stop -> Architect response`. Consumption `same_contract_once` family-wide: changed fingerprint проверяет freshness конкретного resolution, но не открывает второй permit для той же family. Partial/mixed/stale/reused permit fail-closed.

Сначала действует existing `scope_expansion_*`, затем checkpoint, затем review/raw-status route. Manager читает только generic oracle `route_guard_*`, не пишет JSON и не превращает prose в family/decision. Architect reread-ит oracle до и после resolution, нормализуя guarded downstream status через `Ready for Architect response -> Architect response`; same-file review reconciliation продолжает принадлежать Reviewer.

Для отдельно admitted `bounded_grammar` subject V2 сохраняет этот writer/readback
split: Architect append-ит only accepted
`semantic_cycle_checkpoint_resolution.v2` в subject Evidence, `plan_lint`
validates contour-wide history, а checkpoint CLI/oracle/CENSOR/Planner read only
the helper projection. V2 family rows exact-cover current blocker refs and axes;
`same_contract_once` is one-per-contour, `stop` is forbidden, and exhausted
contours require literal de-scope or an exact-backlink structured successor.
V1 producer/finals, review prose and transport receipts are not V2 carrier.

## Compact CENSOR / reviewer receipt

Compact receipt означает не “меньше proof”, а “меньше повторного narrative”.

- CENSOR receipt still keeps literal labels: `Second opinion`, `Fixes`, `Addendum`, `Context reconciliation`; for `NO FINDINGS` also `Counterfactuals considered`; structured labels `Artifacts opened`, `Review verdict seen`, `Blocker IDs considered`, `Role-owned finding`, `Reconciliation`, `Final censor verdict`.
- Reviewer no-findings receipt still keeps lane metadata, target snapshot parity, lane synthesis, canonical no-findings provenance and exact gates.
- Long narrative may be replaced by exact opened/read `Source refs`, concise `Delta`, and `Outcome`, when those refs were actually opened/read in the lane.
- Source-ref-only receipt is invalid if it drops mandatory labels, live/stale blocker reconciliation, dual-review lanes, target snapshot parity, or red-as-live lifecycle defaults.

## Dual-lane review carrier

Когда slice использует dual-model Reviewer contract:
- live review route всё равно остаётся ровно один: один review artifact path, один header status, один `Lane synthesis / aggregate verdict`;
- `reviewer_code_risk` сначала пишет plan-resident lane-run artifact в `PLAN_PATH` evidence с stable fields `run_id`, `lane_id`, `model`, `reasoning_effort`, `prompt_file`, `target_ref`, `target_snapshot`, `coverage_domains`, `findings`, `lane_status`, `no_findings_reason`, `limits`, `written_at`;
- `reviewer_code_contracts` не доверяет Manager memory и не synthesizes findings “из чата”: он читает этот plan-resident block, валидирует тот же `target_snapshot` и только потом materialize-ит live review artifact;
- final merge-range dual-lane lint reads explicit origin from top-level `**Spec:** docs/plans/...md`; `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --origin-plan "$PLAN_PATH" <review_artifact>` is a parity guard and must match `**Spec:**`. Legacy non-range fallback remains only one literal `PLAN=docs/plans/...` in `**Target:**`; filename inference, Manager memory и queue state не являются truth source;
- snapshot parity = normalized literal comparison between plan-resident `reviewer_code_risk.target_snapshot` and review `**Target:**` value. `**Range:**` is legacy-only fallback for non-strict historical artifacts; final merge-range artifacts must carry `**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` and `**Spec:** ...` before `**Status:**`. `target_snapshot` may be a literal string or a structured object parsed by `scripts/review_artifact_lint.py` (for example `target` + `bundle_sha256`); append-only projection blocks are not proof;
- `planveyor_review_target_snapshot <PLAN_PATH> --current-bundle` — stdout-only producer структурированных `BUNDLE=current` snapshots: ordinary plans резолвят primary `code_draft_meta.targets` и выдают v2; admitted strict N-A parents выбирают v3 из полного oracle canonical child graph с same-stem drafts. Он хеширует только документированный canonical basis и не должен мутировать `PLAN_PATH` или review artifacts;
- for `BUNDLE=current bundle_sha256=...`, final `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --origin-plan "$PLAN_PATH" <review_artifact>` treats the normalized lane/header comparison as compatibility guard and additionally recomputes the producer snapshot from disk; two matching stale manual hashes are not closeout proof;
- exact current proof is stricter than this compatibility guard: it is admitted only by `scripts/plan_lint.py:preflight_current_review_proof` with the exact header, two-key compact projection, immutable full `review_target_snapshot.v2` or strict-N-A `review_target_snapshot.v3` nested projection, hash-pinned support and fresh producer equality; facade/oracle/bundle/docs-closeout only project `current_green|blocked`;
- missing declared review artifact is wrapper/bundle receipt state, not chat truth: `planveyor_plan_bundle --closeout-json` must expose `origin_plan`, `declared_review_artifact`, `receipt_state=missing`, `blocker_code=missing_declared_review_artifact`, and `next_owner`;
- raw lane ids (`risk:R<N>`, `contracts:C<N>`, `visual:V<N>`) остаются локальными, а canonical blocker lineage `B<N>` появляется только после synthesis;
- docs-only bundle не создаёт second review family: те же две code lanes остаются обязательными внутри `docs/doc_reviews/...`.

## Motivating example only — not default vocabulary

Process/docs-only motivating example:
- historical docs-only drift materialize-ил одновременно `docs/doc_reviews/...` и parallel `docs/code_reviews/...`, хотя final bundle оставался строго docs-only;
- shared rule отсюда один: current docs-only bundle keeps only `docs/doc_reviews/...`, а route flip на `docs/code_reviews/...` допустим только после literal bundle change to non-doc carriers in plan + code draft + review host together;
- это motivating example для process/docs canon и review-route reasoning, но не default vocabulary для всех repo-profile.

## When To Link This Playbook

- из `docs/plans/README.md`, когда нужен live authoring reference про single live review route;
- из существующего project-local quick reference, когда нужен discovery entrypoint без прыжка в historical plans;
- из новых process/docs slices, которым нужен compact canon note вместо пересказа historical plans.

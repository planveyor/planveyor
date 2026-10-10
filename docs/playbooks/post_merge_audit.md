# Playbook: Post-merge audit (docs hygiene) — multi-plan темы

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

См. также:
- doc_lint policy (каноника vs история): `docs/playbooks/doc_lint.md`
- post-merge docs hygiene (что переносим, как удаляем): `docs/playbooks/post_merge_docs_hygiene.md`

Когда использовать:
- тема растянута на много планов/ревью (например, повторяющийся workflow,
  межсервисное изменение или ужесточение доступа),
- Owner уже смержил серию веток (в т.ч. с конфликтами) и нужно зафиксировать “что реально сделано”,
- после аудита планируется **удалять** закрытые `docs/plans/*` и обработанные `docs/code_reviews/*`.

Зачем:
- собрать “effective spec” и привязать к **кодовым якорям** и **каноническим докам**,
- читать merge-quality verdict из single review artifact (`Lane synthesis / aggregate verdict`) вместо запуска второй независимой reviewer wave,
- проверить, что для merged runtime UI есть post-merge visual sanity, а не только “в diff были нужные строки”,
- не тащить в main “историю” в виде audit‑plan’ов (планы = временный артефакт),
- обеспечить линк‑гигиену (чтобы later owner cleanup не ломал доки).

## Inputs / Outputs (явно)
Вход (Owner должен дать минимум, иначе audit превратится в гадание):
- TOPIC: `<short>` (часть имени для audit‑report: `YYMMDD_post_merge_audit_<topic>.md`)
- Plans in scope: список plan’ов/ревью по теме (или явная маска поиска по `docs/plans/*`)
- BASE..HEAD: диапазон git для “что реально попало в main” (если уже смержено). Если неизвестно — пометить `UNCONFIRMED` и запросить у Owner.

Выход:
- Audit-report (стабильный): `docs/reviews/YYMMDD_post_merge_audit_<topic>.md` (с code anchors + “effective spec”)
- Skeleton bootstrap: `planveyor_post_merge_receipt_skeleton post_merge_audit --out docs/reviews/YYMMDD_post_merge_audit_<topic>.md`, then replace fixture values with real audit/proof values.
- Follow-ups backlog (список, не plan): `docs/followups/YYMMDD_HHMM_followups_<topic>.md` (опционально; можно держать follow-ups прямо в audit-report)
- Для range-bound audit followups, которые materialize-ятся как durable import trail, используй supplemental filename family `docs/followups/<YYMMDD_HHMM>_post_merge_audit_followups_range_<base7>_<head7>.md`, header `**Source:** post-merge audit` и real `**Imported into:** docs/followups/...`. Такой файл не заменяет primary `plan harvest` backlog `docs/followups/*_followups_range_<base7>_<head7>.md` и не должен создавать `ambiguous_artifact` в `planveyor_merge_bundle_report`.
- Risk packet (если уже materialized): `docs/reviews/*_risk_packet_range_<base7>_<head7>.md`; audit/final digest читает его как compact readback поверх exact truth hosts, не как второй verdict source.
- (опционально) follow-up dev-plan(ы) в `docs/plans/` (`**Status:** Architect initial draft`) — только если пункт реально готов к реализации
- Cleanup list (Owner-owned): список временных артефактов, которые можно удалить после переноса знаний в канон
- (опционально) machine-input receipts: existing `planveyor_ai_gate` receipt and SATD candidate table
- Lane-specific Golden Path receipt в audit report, если range затрагивает повторяемый workflow:
  - `lane`: `product_runtime | tooling_process | target_adoption | N/A (why)`;
  - `active carrier`: доставляемый target-local path либо source-engine `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`, или `N/A (why)`;
  - `outcome`: `updated | no changes needed (why) | follow-up created | deferred (why)`.
- Docs retrieval metrics receipt в audit report or explicit pointer to the harvest receipt, если range затрагивает `docs_retrieve` / `planveyor_docs_retrieve` / `docs_get` / `docs_multi_get`, `read_open`, retrieval metrics, retrieval-index helpers, or linked docs-retrieve observability plans. Exact section heading when materialized locally: `## Docs retrieval metrics receipt`. Every row or pointer summary carries `used_for_decision=true|false`; low decision-used coverage (`outcome_evaluated_rate < 0.20` or `read_open_rate < 0.05`) must cite `follow_up_ref` or an accepted enum-like no-op reason, while telemetry-only rows must carry `accepted_no_op_reason=not_used_for_decision`.
- Docs index/context operational receipt citation: current audit reports must mention `docs_index_context` and the `docs_context_check` plans/followups coverage proof or one of the closed no-op reasons (`not_applicable_no_docs_or_followups_delta`, `not_applicable_empty_docs_corpus`, `not_applicable_bootstrap_index_unavailable`).
- Retrieval telemetry receipt в audit report, если audit prose cites `planveyor_docs_lookup` or retrieval-backed file selection as decision evidence. Exact section heading: `## Retrieval telemetry receipt`; fields: `query_event_id`, `used_for_decision`, `read_open`, `read_log_status`, `read_event_id`, `outcome`, `outcome_reason`, `cited/opened files`; no-op reason enum: `not_used_for_decision`, `retrieval_only_file_discovery`, `instrumented_read_unavailable`, `external_source_read`, `already_evaluated_in_prior_receipt`.
- Current audit reports also carry `## Post-merge audit receipt citations`: cite audit matrix, role-quality/role assessment, `Follow-up harvest triage/import receipt`, `Process-improvement promotion decisions`, `Docs retrieval metrics receipt`, `docs_index_context` / `docs_context_check`, and packetization readback `step:packetization_gate` when shared canon applies. Followups cleanup-readiness / handled-state claims must cite range-mode launch proof when the reviewed range contains memory/range inboxes, or an explicit `already tracked elsewhere` / `manual_decision_ref` / `already_tracked_ref` pointer to a durable `docs/followups/*` / `docs/plans/*` carrier; prose-only "handled" is a closeout blocker. Packetization citations must include structural `schema_version=packetization_gate.v1` when JSON exists and must distinguish source `coverage` / `packet_status` from derived `target_adoption_state`, because `blocking_count=0` is not target delivery completion. Missing citations are closeout blockers, not advisory prose.
- Step-local preflight: before marking audit complete or ticking `step:post_merge_audit`, run `planveyor_post_merge_receipt_preflight post_merge_audit --path docs/reviews/*_post_merge_audit_range_<base7>_<head7>.md`; it derives shared-canon packetization requirement from saved `.planveyor.range.*` / `--range` and validates the audit matrix, role-quality receipt and required cross-step citations. Для shared range нужен ровно один active non-superseded final report exact `BASE..HEAD` из `docs/reviews/*_packetization_gate_range_<base7>_<head7>.md` со structural `packetization_gate.v1` JSON без `missing-packet` / `unknown_target_mapping`; missing, explicit wrong-range, superseded-only, ambiguous, non-final, legacy/no-structural, malformed/unsupported schema или blocking report блокируют audit. Только valid report даёт `packetization_state=active_report_validated`; `audit_status=done` и local preflight не означают terminal readiness, которую отдельно подтверждает `planveyor_merge_bundle_report`.
- Risk packet readback: if `docs/reviews/*_risk_packet_range_<base7>_<head7>.md` exists, audit cites its `range_review_risk_packet.v1` JSON for `runtime_touched_paths`, `helper_process_touched_paths`, visual status, live/historical blockers, closure artifacts and `truth_hosts`; if it is missing when the flow expects it, audit records the missing packet as a closeout gap instead of re-stitching those fields from prose.

## Артефакт результата
- Audit-report (стабильный): `docs/reviews/YYMMDD_post_merge_audit_<topic>.md`
  - shared default template: `docs/reviews/_template_post_merge_audit.md`
- Follow-ups backlog (список, не plan): `docs/followups/YYMMDD_HHMM_followups_<topic>.md`
  - шаблон: `docs/followups/_template_followups_backlog.md`
  - range-bound post-merge audit backlog остаётся supplemental/import-trail carrier; primary ordinary harvest carrier живёт в plan-harvest backlog и может быть `NO FOLLOWUPS`.

## Compact failure attribution
- Если нужен компактный трендовый слой по `runtime/gate/review` сигналам, audit может читать `.tmp/planveyor_failure_attribution.jsonl` рядом с raw blocker refs.
- Коды первого прохода: `CONTRACT_VIOLATION`, `ROUTING_FAILURE`, `REVIEWABILITY_GAP`, `RUNTIME_ENV`, `TOOL_ERROR`, `GOVERNANCE_BLOCK`, с явными `UNKNOWN` / `MIXED` для слабого или смешанного evidence.
- Raw blocker lineage остаётся source truth: если live refs отсутствуют, фиксируем `N/A (no live blocker lineage)` или `UNCONFIRMED`, а не выдумываем certainty из derived кода.

## Compact no-findings mode
- Compact mode = presentation/schema/lint сокращение для blocker-free audits; это не audit acceptance proof и не второй verdict source.
- Включается только literal `compact_mode: enabled` в `## Compact no-findings mode`; template default остаётся `compact_mode: disabled`.
- Для `enabled` обязательны: live review `✅ OK`, `lane_finding_id: N/A (no lane findings)`, `synthesis_disposition: no_findings`, отсутствие live `#B<N>` blocker refs, отсутствие flagged role-quality candidate.
- Residual hosts `process_improvements`, `followups`, `packetization`, `ready_to_push`, `docs_index_context`, `receipt_citations` должны быть `clear` или explicit `N/A (why=...)`.
- Любой `missing`, `ambiguous`, `red`, `pending`, `blocked`, `UNCONFIRMED`, live blocker lineage или flagged role-quality candidate запрещает compact mode: оставляй full audit/Draft/blocker и фиксируй gap.

## Audit status authority mapping
- `audit_status` в post-merge audit является derived closeout/readiness status from cited live review artifact, not an independent review verdict.
- Current `review.v1` audit rows must cite a readable local `Lane synthesis / aggregate verdict`; missing/unreadable source, missing synthesis section or ambiguous `lane_finding_id` match fail closed.
- `audit_status=done` allowed only for terminal green source truth: `synthesis_disposition=no_findings`, `accepted`, `superseded` or `closed_by_same_file_rewrite`, with no live blocker refs and `followup_plan: N/A` or explicit terminal proof formatted as `done|closed|handled|terminal: <durable docs/* ref>`.
- Unresolved follow-up paths/prose that merely contain words like `done`, `closed`, `handled` or `terminal` are still non-terminal and must fail closed.
- `accepted_non_blocking_followup`, accepted rows with non-terminal `followup_plan`, `deferred`, `downgraded`, missing source truth and legacy `N/A` provenance are `partial`, `missing` or `UNCONFIRMED`, not `done`.
- `downgraded` may become `done` only after `canonical_ref` proves an accepted no-work/downscope decision and no live blocker/follow-up debt remains; otherwise keep it non-terminal.
- Live `#B<N>` blocker refs or unresolved canonical blocker refs always beat the derived summary field: a row with live blocker lineage cannot claim `done`.
- Historical/closed/superseded blocker lineage must use explicit non-live proof grammar (`historical|closed|superseded: <durable docs/* ref>`); path/prose substrings like `closed`, `historical` or `superseded` do not suppress a live `#B<N>` ref.
- Versionless historical audit artifacts remain legacy compatibility carriers unless explicitly migrated; do not bulk-rewrite them during ordinary post-merge audit lint changes.

Template ownership / resolution:
- shared default audit template живёт в `docs/reviews/_template_post_merge_audit.md`;
- optional repo-profile override, если он появится, живёт в `docs/reviews/profiles/<repo_profile>/_template_post_merge_audit.md`;
- target-local template override, если он materialized и имеет declared owner, — delivery surface, а не второй canon;
- follow-ups backlog template остаётся shared default в `docs/followups/_template_followups_backlog.md`, пока consumer не объявит другой owner contract;
- primary canon target-local consumer выбирает из своих declared paths. Отсутствующий optional carrier — `N/A (why=...)`, а не default blocker;
- derived docs-index refresh выполняется только когда consumer materialize-ит retrieval corpus и объявляет его in-scope. Тогда receipt фиксирует coverage для выбранных corpuses; index DB остаётся local derived state.

## Rerun context (обязателен, если до audit был merge-range rerun)
- В audit-report явно фиксируем `Rerun mode: incremental | full` и `Baseline artifact`.
- `incremental` позволяет audit опереться на prior accepted baseline + rerun closure только для узкого blocker scope; full-wave residual-debt extraction и post-merge sanity фиксируем отдельно, с опорой на те же blocker refs `<review_artifact_path>#B<N>` если они materialized.
- `full` означает, что rerun уже переиграл весь range; prior artifacts = history only.
- Если explicit rerun context восстановить нельзя, помечаем `UNCONFIRMED` и не притворяемся, что closure понятен по памяти.

## Процесс (high level)

1) Создать audit‑report в `docs/reviews/` и вести работу **только** через него.
   - Backlog follow-ups держим в `docs/followups/*` (а не в `docs/plans/*`).
2) Инвентаризация артефактов (полнота = критично):
   - helper-backed range stats: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_merge_range_stats_json "$BASE" "$HEAD"`; audit копирует labels `total_commits`, `first_parent_commits`, `changed_files`, `diffstat_summary`, а не пересчитывает их по prose,
   - планы по теме (включая follow-up/acceptance/ops/perf),
   - code reviews по теме: это **источник follow-up требований**,
   - visual evidence / range review artifacts: что именно было перепроверено на merged code и какими скриншотами это доказано,
   - snapshots по теме — только как historical breadcrumbs, если нужно понять эволюцию/расхождение; не как source of truth,
   - объявленные canonical docs, куда должны уехать решения: roadmap,
     declared target canon, ADR, schema/API, registry и runbooks,
   - объявленные visual source scenarios и ссылки на их sections из затронутых
     plan'ов; совместимый пример Planveyor — `docs/smoke_visual.md`,
   - framework-specific shell/layout/event files только если selected
     project/profile canon прямо их называет.
3) Effective spec (“что должно быть сейчас”):
   - базовый слой = самый поздний follow‑up plan + канонические доки + review artifacts,
   - merge-quality truth source = single review artifact, который объявлен в review-only `PLAN_PATH` из `review_range`,
   - audit читает оттуда `Lane synthesis / aggregate verdict` и per-finding/per-disposition provenance records с literal field set `source_lane`, `lane_finding_id`, `synthesis_disposition`, `canonical_ref`, `audit_status`, `followup_plan`,
   - если range risk packet уже materialized, audit использует его как компактный index/readback к тем же truth hosts; любые противоречия между packet и live review artifact решаются в пользу live review artifact,
   - для финального `✅ OK` без lane findings audit всё равно требует compact no-findings disposition record (`lane_finding_id: N/A (no lane findings)`, `synthesis_disposition: no_findings`, `canonical_ref` на `Lane synthesis / aggregate verdict`, lifecycle-aware `audit_status`, `followup_plan: N/A`), а не legacy `N/A` placeholders,
   - если review artifact или `Lane synthesis / aggregate verdict` отсутствуют, audit остаётся `Draft` и фиксирует finding `missing lane synthesis`; он не компенсирует gap новым reviewer rerun,
   - из code reviews извлечь literal `Blocker refs`/`Risk`/`Follow-up` и либо подтвердить `done` (с якорями), либо вынести в follow-up планы,
   - если live blocker ref отсутствует, не выдумывать его ретроспективно: писать `N/A (no live blocker lineage)` или `UNCONFIRMED`,
   - к ранним планам спускаться только по ссылкам/неясностям.
4) Audit-матрица (внутри audit‑report):
   - до ручного разбора можно снять SATD candidate table:
     - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py satd_scan.py --range BASE..HEAD`
   - SATD helper now emits lifecycle `created|updated|deleted` and keeps old/new anchors when diff даёт их честно; это prefill/evidence lane, а не verdict;
   - SATD output = candidate lane only; каждая строка требует manual verify (`promote | dismiss`), это не truth-gate и не замена semantic review;
   - если repo/owner уже materialize-ил pre-merge gate receipt через `planveyor_ai_gate` (`docs/reviews/*_ai_gate_*.json` или repo-local equivalent), используй его как contextual evidence, зафиксируй literal `PASS|WARN|BLOCK`, и не повторяй те же mechanical scans “по памяти” в audit prose;
   - transient proof from `planveyor_ai_gate_smoke --receipt-path .tmp/...` = wrapper sanity only; такой `.tmp/` receipt не считаем durable post-merge evidence, пока Owner явно не materialize-ил отдельный merge receipt;
   - сначала отдельно зафиксируй `closure by rerun` vs `full-wave residual-debt extraction`,
   - формат: `spec item → lane synthesis source → provenance fields (source_lane / lane_finding_id / synthesis_disposition / canonical_ref / audit_status / followup_plan) → blocker refs → code anchor (file:line/URL) → tests/smokes → docs anchors → status`,
   - правило: spec item не `done`, пока нет code anchor (и где применимо — теста/смоука).
4.1) Role-quality через same-session censor receipts (если они materialized в source plans)
   - Сначала запускай helper-backed readback по flagged plan и текущим review artifacts: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py censor_receipts_harvest.py --plan <flagged-plan> --review-artifact <current-review> --format json`.
   - Audit-report копирует facts из JSON keys `inputs`, `summary`, `receipts`, `findings`, `warnings`, `unconfirmed_reasons`; manual prose parsing допустим только как пояснение после helper output.
   - Helper вытаскивает из `## Evidence` literal `(Architect CENSOR)` / `(Planner CENSOR)` / `(Coder CENSOR)` записи и один shared field set: `Artifacts opened`, `Review verdict seen`, `Blocker IDs considered`, `Role-owned finding`, `Reconciliation`, `Final censor verdict`.
   - Для repeated same-status / same-blocker loops helper также вытаскивает deadlock addendum: `Loop signal`, `Root cause class`, `Why previous rerun did not break the loop`, `Extraordinary action`.
   - `missed live blocker` принимается только как helper-backed exact current negative evidence: current blocker refs/verdict + literal reconciliation that the live blocker belongs to this role + none-ish role finding + `OK`/`NO FINDINGS`. Current-looking blocker prose без такого exact signal остаётся `UNCONFIRMED`.
   - Сверь receipt с current review artifact / blocker refs: `NO FINDINGS` без literal reconciliation against current review verdict не засчитывается как helpful censor и уходит в audit как helper-backed `receipt missing`, `missed live blocker` или `UNCONFIRMED`.
   - Already-green append-only anchors считаются `historical anchor only` только если receipt это назвал literally; иначе статус = `UNCONFIRMED`, а не автоматический credit.
   - В audit-report держи verdict коротко и grep-friendly: `helped | missed live blocker | receipt missing | noise/no-op | UNCONFIRMED`, с pointer на helper receipt line / blocker ref.
   - `UNCONFIRMED` оставляй только когда helper вернул missing/partial receipt или explicit `UNCONFIRMED` reason; не ставь его там, где helper already extracted complete labels.
   - `scripts/post_merge_audit_lint.py` для current `review.v1` reports fail-closed сверяет `## Role assessment (censor receipts...)`: либо explicit `Receipt source: N/A (receipt missing)` + `Assessment: receipt missing`, либо copied helper counters `Helper summary` / `Helper role-quality` должны быть concrete and green (`partial=0`, `missing=0`, `unconfirmed=0`, `missed live blocker=0`, `receipt missing=0`, `UNCONFIRMED=0`). `Assessment: helped` поверх red/partial helper counters = audit blocker, а не зелёный role-quality summary.
4.2) Role-quality findings by plan/role (flagged plans only)
   - Deep role-quality matrix materialize-ится только для plans, которые plan-harvest/current range evidence уже пометили как `flagged`; остальные планы идут одной summary note `not audited`.
   - Для каждого flagged plan audit-report обязан literal-но держать:
     - `Candidate source`: exact review ref или plan evidence line;
     - `Why in matrix`: один literal Stage 1 signal (`live ❌ S1 blocker`, `same review rerun loop`, `blocker-driven follow-up`, `explicit blocker/current-plan bounce`);
     - role rows минимум для `Architect`, `Planner`, `Coder`, `Reviewer`, `Architect arch review`, `Censor`.
   - Verdict enum остаётся bounded и одинаковым по всем carriers: `caught in time | missed, downstream caught | not primary owner | evidence insufficient | receipt missing`.
   - Каждая role row опирается на exact plan/review evidence; если live blocker lineage не materialized, пишем `N/A (no live blocker lineage)` и честно деградируем verdict до `evidence insufficient`, а не ретеллим "кажется, было плохо".
   - `Censor` остаётся derived special case поверх receipt baseline: без structured receipt он не получает fake credit и остаётся `receipt missing` или `evidence insufficient`.
   - Эта matrix не спорит с `review_range`: live review artifact остаётся merge-quality truth-gate, а role-quality section объясняет процессную атрибуцию постфактум.
5) Post-merge visual sanity (для runtime UI):
   - audit **не переснимает** UI по умолчанию; он проверяет, что Reviewer уже сделал visual sanity на merged code;
   - audit перечитывает final current-review visual state через shared authority `scripts/review_artifact_lint.py`: exact comparator command/result, human per-mode index refs, complete capture/index inspection, design verdict и current-review durable assets;
   - `audit_status=done` не может override-ить `red|ambiguous` visual readback; такой row остаётся blocker для `✅ Done`, merge report, receipt preflight, ready-to-push closeout и risk packet;
   - `.tmp/**`, assets другого/historical review basename, traversal, symlink, missing/empty per-mode asset и naked `N/A` для applicable runtime UI — red evidence, а не допустимое закрытие;
   - для каждого must-not-regress сценария из затронутых plan'ов и объявленного
     visual source (совместимый пример Planveyor: `docs/smoke_visual.md`) зафиксируй:
     - source scenario,
     - где он был проверен (mode/URL/review artifact),
     - какое evidence это доказывает,
     - status: `done | partial | missing | UNCONFIRMED`.
   - если runtime UI в диапазоне менялся, но visual sanity artifact/evidence нет — это не “мелкий хвост”, а audit finding минимум уровня `missing`, обычно с follow-up dev-plan.
5.1) Golden Path lane decisions:
   - если range затрагивал UI/runtime, process workflow, rollout/import/ack flow или повторяемую review finding, audit report обязан дать lane-specific receipt:
     - `lane=product_runtime` для объявленного product UI/runtime carrier;
     - `lane=tooling_process` для source-owned process workflows в `planveyor` (post-merge audit, plan harvest, memory-finalize/docs-closeout, process-improvement promotion, source rollout packet lifecycle);
     - `lane=target_adoption` для rollout packet inbox/adoption-plan/harvest/ack flow;
     - `lane=N/A (why)` если range не породил Golden Path-worthy decision.
   - Для выбранной lane запиши доставляемый active carrier и outcome `updated | no changes needed (why) | follow-up created | deferred (why)`. Для source-owned `tooling_process` carrier — engine reference `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`.
   - Для `tooling_process` lane cite existing engine anchors such as `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-audit"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-plan-harvest"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#process-improvement-promotion"`, or `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#source-rollout-packet-lifecycle"`.
   - Если active registry не покрывает новый повторяемый workflow, outcome не может быть silent drop: либо `follow-up created`, либо `deferred (why)` с owner/next-step.
5.2) Docs retrieval metrics receipt:
   - Trigger: audit scope/report text mentions `docs_retrieve`, `planveyor_docs_retrieve`, `docs_get`, `docs_multi_get`, `read_open`, `read_events_total`, `retrieval metrics`, or a linked docs-retrieve observability plan.
   - If harvest already materialized the receipt, audit may use a pointer route: link `docs/reviews/*_plan_harvest_*.md#docs-retrieval-metrics-receipt` and copy parseable minimum summary values, not just field names: `query_total=<int>`, `evaluated_total=<int>`, `outcome_evaluated_rate=<rate>`, `read_log_status=<present|missing>`, `read_events_total=<int>`, `read_open_rate=<rate>`, `used_for_decision=<true|false>`, and `accepted_no_op_reason=<reason>` in the audit report. If audit materializes its own receipt, use exact heading `## Docs retrieval metrics receipt`.
   - Run aggregate helper for source repo: `planveyor_docs_retrieve_metrics --format json` (or `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py docs_retrieve_metrics.py --format json`). Target/sibling repos are read-only aggregate inputs only.
5.3) Retrieval telemetry receipt:
   - Trigger: audit report cites `planveyor_docs_lookup` or a retrieval-backed source-selection decision, not merely aggregate retrieval metrics.
   - Prefer `planveyor_docs_lookup <canon|followups|plans> "query"` so query + instrumented read/open + receipt skeleton come from one bounded helper.
   - Add exact section `## Retrieval telemetry receipt` with `query_event_id`, `used_for_decision`, `read_open`, `read_log_status`, `read_event_id`, `outcome`, `outcome_reason`, and `cited/opened files`, or a no-op reason from the closed enum above. If the receipt is telemetry-only, use `used_for_decision=false` with `no_op_reason=not_used_for_decision`.
   - Raw `.tmp/planveyor_docs_retrieve_*.jsonl` logs stay local runtime evidence and are not durable audit artifacts.
   - Required table columns: `repo`, `repo_role`, `query_log_status`, `query_total`, `with_hits`, `zero_hits`, `hit_rate`, `warnings_total`, `errors_total`, `with_event_id`, `evaluated_total`, `outcome_evaluated_rate`, `outcome_used`, `outcome_partial`, `outcome_miss`, `outcome_noise`, `not_evaluated_total`, `read_log_status`, `read_events_total`, `read_open_rate`, `unique_paths`, `used_for_decision`, `low_coverage_triage`, `follow_up_ref`, `accepted_no_op_reason`, `source_command`.
   - Missing query/read logs are recorded as `*_log_status=missing` with zero counts. `read_events_total=0` is a valid reported signal, not a blocker. Raw `.tmp` query/outcome/read JSONL logs stay local and uncommitted.
6) Follow-up черновики (draft-first):
   - всё `partial/missing/diverged/unknown` собрать в follow-ups backlog (audit-report или отдельный `docs/followups/*_followups_*.md`),
   - если `incremental` rerun закрыл blocker scope, но audit видит debt вне него, это отдельный follow-up/debt extraction, а не повод задним числом объявлять rerun “неполным” без явного аргумента,
   - если source plan literal-но вынес product item из active scope (`removed from active scope`, `intentionally removed`, `если по-прежнему нужно`, `отдельный follow-up`), audit обязан проверить, что item реально materialize-ился в backlog/promoted plan/already-tracked pointer; если нет, это audit finding `lost follow-up during harvest/promotion`, а не молчаливый `no new dev-plan`,
   - если follow-up **готов к реализации** (P0/P1) — создать отдельный dev-plan в `docs/plans/` (`**Status:** Architect initial draft`) и сослаться на него из backlog,
   - мультивариантность/заглушки допустимы в backlog до появления dev-plan.
7) Sync канонических доков:
   - обновлять только то, что подтверждено кодом/тестами; спорное помечать `UNCONFIRMED`,
   - отдельно проверить “фантомность” (нет упоминаний endpoints/компонентов/events, которых нет в коде).
8) Cleanup (Owner-owned):
   - **удаление** закрытых `docs/plans/*` и обработанных `docs/code_reviews/*` делает Owner,
   - задача Architect: подготовить точный список “что удаляем”, и до/после — проверить ссылочные хвосты.
   - важно: в канонических доках **не держим** inline code spans вида `docs/plans/...` / `docs/code_reviews/...` на файлы, которые будут удалены.
     - если нужна трассировка: “git history: <filename>” (без пути) или ссылка на audit‑report.
   - sibling: перед удалением прогнать `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint` по materialized canonical roots и убедиться, что ссылки не указывают на удаляемые файлы; exact artifact-root check объяви в локальной секции этой фазы.
   - Self-Planveyor only: literal `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-code-refs` остаётся source-root route.
   - Если selected consumer объявил docs retrieval in-scope, blocker-free cleanup wave требует derived-index refresh + coverage-check по declared corpuses с literal `covered/uncovered` summary в audit-report/receipt.
8.1) Финальный scrub durable artifacts:
   - audit-report / follow-ups backlog и любые другие long-lived artifacts не должны нести ложный transient session-state (`dirty`, `untracked`, “локально создали ...`);
   - audit может перечислить cleanup candidates, но не выполняет deletion; `planveyor_docs_hygiene_suggest` остаётся report-only handoff, а optional `git rm` живёт в отдельном Owner cleanup commit после fresh archive/suggest.
   - перед final `ready_to_push` audit/handoff facts должны попадать в helper-backed `planveyor_post_merge_operational_receipt`; token-only Manager prose не закрывает command/result/no-op/schema proof.
   - если audit утверждает, что followups обработаны или cleanup-ready, проверь source launch receipt: `planveyor_followups_triage --file|--range`, dry-run/apply/idempotency, `scripts/followups_index_rebuild.py`, readback docs/followups/index.md; для range-memory/range inboxes нужен `--range` proof с закрытыми duplicate/route-fallback/unparsed outcomes, иначе нужен explicit `manual_decision_ref` / `already_tracked_ref` pointer.
   - если repo-state нужен для восстановления, фиксируй exact live fact или команду проверки (`git status -sb`, `git log -1 --oneline`), а не быстро устаревающее описание;
   - `UNCONFIRMED` оставляем только для реально неизвестных устойчивых фактов, а не для того, что можно локально добрать сразу.
   - если audit рекомендует canon update, не тащи snapshot'ы в active canon/registry и не цитируй их из audit-report как normative pointer; durable факты подними прямо в канон / audit / follow-up plan.
9) Минимальная валидация (по договорённости с Owner):
   - link hygiene sibling: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`; Self-Planveyor only literal route: `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-code-refs ...`
   - docs diff sanity (текущий diff): `git diff --check -- docs`
     - полезен именно для changed docs: ловит accidental trailing whitespace, CRLF, merge markers, лишние пустые строки в EOF;
     - если ругань только на новый Markdown hard-break style, перепиши changed block структурно (bullets/paragraphs/таблица), а не оставляй сырой whitespace.
   - artifact-root hygiene после materialization audit-report/follow-up artifacts: sibling указывает target-local command в локальной секции; Self-Planveyor only literal route: `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-basic-hygiene --root <artifact paths>`;
     - этот proof читает explicit markdown files, включая newly materialized/untracked artifacts, поэтому закрывает gap, который tracked-only diff может пропустить.
  - если audit затрагивает поведение: выполни только commands, materialized
    selected profile/harness; `make`-цели и другие команды допустимы, только
    когда их буквально объявляет текущий repo.
  - если range трогал runtime UI: проверь, что audit-report содержит
    post-merge visual sanity со ссылками на объявленные source scenarios и review
    evidence (совместимый пример Planveyor: `docs/smoke_visual.md`).
  - если selected consumer объявил derived docs index, запусти его public helper через facade и coverage check для declared corpuses. В receipt нужен literal `covered/uncovered` summary или zero-uncovered proof; одного `exit 0` недостаточно.

## Команды (шпаргалка)
```bash
# Self-Planveyor only: выбери materialized canonical roots текущего проекта:
bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-code-refs --code-refs-scope repo \
  --root AGENTS.md \
  --root docs/roles \
  --root docs/playbooks \
  --root <target-declared guide carrier> \
  --root docs/arch.md \
  --exclude docs/plans --exclude docs/code_reviews --exclude docs/doc_reviews --exclude docs/snapshots

# Sibling canonical link hygiene:
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint

# Для sibling exact audit-report hygiene укажи target-local command в локальной секции.
```

## Как заполнять локальные секции sibling

Две секции ниже имеют стабильные заголовки и initial fields. После
`planveyor_consumer_init` их тело принадлежит sibling: внесите target-local
команды, данные, критерии и proof только для этой фазы. Общие lifecycle
правила, статусы и authority остаются вне секций; изменение формата требует
отдельной явной адаптации, а не обычного upgrade.

## Локальные правила стека

- Дополнительные команды и preconditions: N/A (why=stack-specific rule not configured)
- Проверяемый результат и evidence: N/A (why=stack-specific rule not configured)

## Разрешённое локальное переопределение процесса

- Переопределение: N/A (why=no local override)
- Причина и эквивалентный proof: N/A (why=no local override)

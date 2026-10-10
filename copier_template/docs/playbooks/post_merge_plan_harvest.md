# Playbook: Post-merge — plan harvest (follow-ups + canon updates)

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

Цель: перед удалением временных артефактов (plans/reviews/assets) вытащить из них всё важное:
- follow-ups (что реально осталось сделать/переосмыслить),
- canon updates (что нужно закрепить в канонике),
- key decisions/constraints (что должно жить в объявленном project canon:
  architecture/API/schema/registry/runbook/UI carriers, названные в `Context links`).

Это **не** code review и **не** заменяет `docs/playbooks/post_merge_audit.md` — это более “мелкая сетка”: пройтись по планам и ревью и убедиться, что ничего не потеряли.

## Входные
- `RANGE=BASE..HEAD` (или `BASE`/`HEAD`)
- optional contextual runtime evidence: existing pre-merge gate receipt (`docs/reviews/*_ai_gate_*.json` или repo-local equivalent); transient `.tmp/...` receipt from `planveyor_ai_gate_smoke --receipt-path ...` остаётся wrapper-sanity carrier и не считается durable harvest/backlog source

## Выходные
- Harvest report: `docs/reviews/*_plan_harvest_range_<base7>_<head7>.md`
- Skeleton bootstrap: `planveyor_post_merge_receipt_skeleton plan_harvest --out docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md`, then replace fixture values with real range/proof values.
- Follow-ups backlog: `docs/followups/*_followups_range_<base7>_<head7>.md` (шаблон: `docs/followups/_template_followups_backlog.md`; добавить в docs/followups/index.md)
- Этот backlog — primary ordinary harvest carrier для `step:plan_harvest/followups_backlog`: header должен фиксировать `**Source:** plan harvest`; файл может честно содержать `NO FOLLOWUPS`, но всё равно остаётся required primary carrier для закрытого `step:plan_harvest`.
- Audit-created same-range followups с filename family `*_post_merge_audit_followups_range_<base7>_<head7>.md` и `**Source:** post-merge audit` являются supplemental/import-trail carriers. Они не заменяют primary plan-harvest backlog и не считаются duplicate truth host, если `**Imported into:**` указывает на durable `docs/followups/*` import target.
- Process-improvement rows are a separate carrier: do not copy `triaged` / `deferred` / `rejected` PI lifecycle rows into ordinary followups. Create an ordinary delivery follow-up only when it has `status=open` / `plan=null` until promote and the raw PI row carries an explicit backlink in `delivery_refs`.
- Triage/import report: stdout от `planveyor_followups_triage` (`--file` for newly-created harvest backlog, или `--range` for already-in-range inboxes; dry-run/apply/idempotency)
- Refreshed open-followups summary in docs/followups/index.md via `scripts/followups_index_rebuild.py`
- (опционально) ADR draft(s) in `docs/adr/*.md` for durable decisions promoted from harvest
- (опционально) follow-up dev-plan(ы) в `docs/plans/` (`**Status:** Architect initial draft`)
- (опционально) обновлённая каноника (`docs/**`, `docs/snapshots/*`)
- Packetization handoff: если range/canon sweep меняет shared process canon (`docs/roles`, `docs/tools/prompts`, `docs/playbooks`, templates/ADR/guides), после `canon_sweep` обязателен `planveyor_post_merge_packetization_gate --range "$RANGE"` и report `docs/reviews/*_packetization_gate_range_<base7>_<head7>.md`; active report/stdout JSON carries `packetization_gate.schema_version=packetization_gate.v1`, а structural JSON без `schema_version` red; `missing-packet` / `unknown_target_mapping` не позволяют закрыть closeout.
- Lane-specific Golden Path receipt в harvest report, если range затрагивает повторяемый workflow:
  - `lane`: `product_runtime | tooling_process | target_adoption | N/A (why)`;
  - `active carrier`: доставляемый target-local path либо source-engine `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`, или `N/A (why)`;
  - `outcome`: `updated | no changes needed (why) | follow-up created | deferred (why)`.
- Docs retrieval metrics receipt в harvest report, если range затрагивает `docs_retrieve` / `planveyor_docs_retrieve` / `docs_get` / `docs_multi_get`, `read_open`, retrieval metrics, retrieval-index helpers, or linked docs-retrieve observability plans. Exact section heading: `## Docs retrieval metrics receipt`; every row carries `used_for_decision=true|false`, and telemetry-only rows carry `accepted_no_op_reason=not_used_for_decision`.
- Runner quality range receipt в harvest report, если range содержит `runner_quality` rows или durable evidence использования external/non-default runner'ов (`claude`, future non-Codex). Exact section heading: `## Runner quality range receipt`.
- Retrieval telemetry receipt в harvest report, если harvest prose cites `planveyor_docs_lookup` or retrieval-backed file selection as decision evidence. Exact section heading: `## Retrieval telemetry receipt`; fields: `query_event_id`, `used_for_decision`, `read_open`, `read_log_status`, `read_event_id`, `outcome`, `outcome_reason`, `cited/opened files`; no-op reason enum: `not_used_for_decision`, `retrieval_only_file_discovery`, `instrumented_read_unavailable`, `external_source_read`, `already_evaluated_in_prior_receipt`.
- Post-merge sub-step receipt matrix для current harvest report: literal sections `## Follow-up harvest triage/import receipt`, `## Process-improvement promotion decisions`, `## Docs retrieval metrics receipt`, `## Golden Path lane receipt`, `## ADR candidates / durable decisions`, and `## Canon/follow-up summary`. Если shared canon/canon sweep затронут, receipt must include `step:packetization_gate`; prose-only `N/A` валиден только с bounded reason and no open carrier.
- Step-local preflight: before marking harvest complete or ticking `step:plan_harvest`, run `planveyor_post_merge_receipt_preflight plan_harvest --path docs/reviews/*_plan_harvest_range_<base7>_<head7>.md`; it derives shared-canon packetization requirement from saved `.planveyor.range.*` / `--range` and catches missing receipt sections. Только на этом раннем `plan_harvest` шаге literal handoff `step:packetization_gate` позволяет green без future packetization report; output обязан содержать `proof_scope=step_local_receipt`, `terminal_readiness=not_evaluated`, `packetization_state=handoff_recorded_future_step_pending`. Это не ready-to-push и не замена report для следующего gate: final readiness по-прежнему подтверждает только `planveyor_merge_bundle_report`.
- Если ordinary followups пусты, но в process-improvements lane остаются `open|triaged|promoted|deferred|unconfirmed` rows, `## Process-improvement promotion decisions` обязан содержать компактную строку:

  ```text
  process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=<n>; triaged=<n>; promoted=<n>; deferred=<n>; unconfirmed=<n>; null_execution=<n>; delivery_refs=<n>; owner_or_next_step=<...>
  ```

  Эта форма применяется к материализованной PI lane. Operational receipt и bundle report читают эту строку как sibling к `followups_triage_launch_receipt`.
- Если harvest file-lane пишет `NO FOLLOWUPS`, но `followups_triage_launch` / range-lane counts non-zero, это не contradiction: final operational receipt must carry `followups_lane_reconciliation` with `harvest_file_followups_result`, `harvest_file_followups_count`, `range_triage_mode`, range counts, durable refs and `owner_summary`.
- Если target-local consumer не materialize-ит docs/followups/index.md, backlog остаётся standalone range artifact, а index/triage/import становятся `N/A (why=carrier absent)` вместо blocker'а.
- Если consumer объявил docs retrieval in-scope, blocker-free closeout обновляет derived index и записывает coverage-proof для declared corpuses; DB остаётся local derived state и не коммитится.

Template ownership / resolution:
- shared default harvest template живёт в `docs/reviews/_template_plan_harvest.md`;
- optional repo-profile override, если он появится, живёт в `docs/reviews/profiles/<repo_profile>/_template_plan_harvest.md`;
- target-local materialized template override считается delivery surface, а не вторым каноном;
- `docs/followups/_template_followups_backlog.md` остаётся shared default template для backlog-файла, пока отдельный plan явно не вводит другой ownership contract.

## Rerun vs harvest (обязательная трактовка)
- Merge-range rerun отвечает только за closure blocker scope.
- Harvest отдельно отвечает за full-wave residual-debt extraction, dedupe follow-ups и canon updates.
- Если rerun был `incremental`, сначала зафиксируй baseline artifact и reused evidence, а затем отдельно ответь, остался ли actionable debt вне rerun scope.
- `NO FOLLOWUPS` валиден только с явной причиной: `handled in follow-up`, `already tracked elsewhere`, `canon sync closed it`, `no remaining actionable debt after full-wave harvest`.
- `NO FOLLOWUPS` означает только ordinary harvest file-lane `docs/followups/*`; он не закрывает отдельные process-improvement rows и не доказывает, что range triage had zero work. Если PI rows остаются видимыми в separate lane, рядом нужен `process_improvements_open_summary`; closeout helper читает тот же класс фактов как advisory `process_improvement_advisory_*` readback, но он не делает ordinary follow-up и не блокирует queue сам по себе. Если range-lane counts non-zero, operational receipt должен нести `followups_lane_reconciliation`.
- `NO FOLLOWUPS` нельзя использовать как сокращение для “мы посмотрели только rerun scope”.
- `NO FOLLOWUPS` запрещён, если любой source plan содержит unmatched de-scoped actionable debt: literal item из `## Follow-ups (deferred)` или из `## Out of scope`, который был явно removed from active scope, но не получил ни backlog-entry, ни promoted dev-plan, ни explicit owner/canon rejection.
- `already tracked elsewhere` валиден только если pointer ведёт в durable backlog/dev-plan lane: existing `docs/followups/*` entry с тем же item и явным status/provenance, promoted `docs/plans/*.md`, literal canon closure или explicit owner rejection. Сырая ссылка только на `*_followups_memory_*.md` / `memory dump` без promoted dev-plan, backlog-row или closure note не считается достаточным handled-state.
- Этот durable-carrier contract теперь проверяется script-first через `scripts/doc_lint.py` для самих harvest receipts / range backlog files; prose-only reminder больше не считается достаточным gate.
- На target-local invoke sibling прогоняет canonical link gate через внешний
  facade; exact harvest/backlog artifact hygiene остаётся target-local командой,
  объявленной в local section, а не hidden tooling root.

## Role-quality candidate lane (Stage 1)
- Candidate selection живёт в harvest как retrospective metadata, а не как новый merge-tracker step.
- План попадает в downstream role-quality matrix только по literal merge-range сигналу:
  - live `❌ S1 blocker` в current review artifact;
  - repeated blocker / rerun loop по тому же review file;
  - blocker-driven supersede / follow-up после triage;
  - explicit `blocker=yes` / current-plan bounce в `PLAN_PATH` evidence.
- Для flagged plans harvest обязан записать literal `Candidate source` и `Why flagged` с exact review ref или plan evidence line; prose-only "кажется, процесс поплыл" не годится.
- Планы без такого сигнала остаются на summary lane `not audited`; не materialize-им пустые deep role-quality blocks "для симметрии".
- Rewritten-green append-only anchors допустимы только как `historical anchor only` proof of shape; сами по себе они не считаются current candidate signal.
- Если flagged plan содержит same-session CENSOR receipts, harvest обязан передать exact plan/review paths в helper `scripts/censor_receipts_harvest.py` и сохранить в harvest/audit handoff helper facts из `summary`, `receipts`, `findings`, `warnings`, `unconfirmed_reasons`.
- Harvest не выводит `missed live blocker` из prose-only current-looking blocker wording: это confirmed только из helper category после exact current negative evidence; ambiguous helper output и `unconfirmed_reasons` переносятся как `UNCONFIRMED`.
- `UNCONFIRMED` по CENSOR lane допустим только как helper-backed outcome для missing/partial receipt или explicit unconfirmed reason; не заменяй извлекаемые labels ручным prose-only verdict.

## Runner quality range receipt (Stage 1)
- Это task-level runner output receipt, а не model leaderboard: строки группируются по `plan`, `role_lane`, `runner_id`, `model`, `task_class` и source ref.
- Trigger: range содержит `runner_quality` row в review artifact, plan evidence с external/non-default runner summary или wrapper-visible lane metadata for `claude` or a future non-Codex runner.
- Для каждой task/lane в range запиши `row_status`:
  - `captured` = valid `runner_quality` row has a source ref;
  - `missing` = external/non-default runner usage detected, but Arch review row is absent;
  - `not_applicable` = external/non-default runner materially не участвовал, reason lives in `score_summary`.
- Summary totals покрывают runner/model/role_lane/task_class, row_status, `required_frontier_intervention` и `useful_for_future`.
- Low score не auto-fail'ит harvest; weak/poor rows требуют `follow_up_ref` или accepted no-op reason.
- Источники только durable artifacts / lane metadata. Не используй chat memory, private transcripts, provider logs или credentials как score evidence.

## Шаги

1) Инвентаризация по git (что трогали в этом диапазоне)
- планы:
  - `git diff --name-only "$RANGE" -- docs/plans`
- ревью-артефакты:
  - `git diff --name-only "$RANGE" -- docs/code_reviews docs/doc_reviews`

2) Создай/обнови harvest report
- Shared default template: `docs/reviews/_template_plan_harvest.md`
- Если для текущего repo-profile существует override в `docs/reviews/profiles/<repo_profile>/...`, используй его; иначе падай обратно на shared default.
- Не вставляй ссылки путями на файлы, которые собираешься удалять (`docs/plans/...`, `docs/*reviews/...`) — только filenames (git history) или указатели на канон / audit / follow-up. Snapshot'ы не используем как pointer/source в harvest report.
- Заведи backlog-файл в `docs/followups/*` (шаблон: `docs/followups/_template_followups_backlog.md`) и добавь ссылку на него в harvest report (если follow-ups нет — явно написать `NO FOLLOWUPS` в backlog).

3) По каждому plan из диапазона: вытащи “остатки”
Ищи в plan:
- `## Follow-ups (deferred)`
- `## Suggestions log` / `## Objections / risks log` / `## Q&A log` (что осталось открытым)
- `plan_meta.canon_updates[]` / `plan_meta.followups_out[]` (если есть)
- `## Documentation impact / provenance`: для текущих планов не оставляй drift между `Synchronous doc/registry targets` и linked `code_draft_meta.targets` на execution/review handoff statuses; это `plan_lint.py` hard error, а не harvest-only warning.
- `## Out of scope` вместе с literal формулировками `removed from active scope`, `intentionally removed`, `не в этом slice`, `если по-прежнему нужно`, `отдельный follow-up`: такие строки считаются candidate de-scoped debt, пока не доказано обратное

3.1) Guard against lost de-scoped debt
- Если plan буквально вынес item из active scope, harvest обязан назначить ему судьбу:
  - `promoted` -> создан новый dev-plan;
  - `open` / `UNCONFIRMED` -> item записан в `docs/followups/*`;
  - `handled` -> already tracked elsewhere / canon sync closed it / explicit owner rejection.
- Формулировка `это было out of scope` не считается closure.
- Если такой item не materialize-ится ни в backlog, ни в promoted plan, ни в explicit rejection note, harvest report обязан зафиксировать `lost follow-up during harvest` и не имеет права писать `NO FOLLOWUPS`.
- Если item “already tracked elsewhere” ссылается только на memory dump без literal promoted plan / backlog row / closure note, это тоже `lost follow-up during harvest`, а не легальный handled outcome.

4) Учти итоги ревью (чтобы не дублировать follow-ups и не смешивать closure с debt extraction)
Для каждого plan:
- Найди review artifact (обычно он указан в `## Review artifacts`).
- Вытащи из review artifact literal blocker refs `<review_artifact_path>#B<N>` вместе с `Current state`, `Classification`, `Primary owner gap`, `Evidence refs`; это и есть dedupe/lineage key для harvest, а не prose-only summary.
- если рядом есть runtime pre-merge gate receipt, используй его только как contextual evidence для already-materialized blocker/closure facts; transient `.tmp/` smoke receipt не промоутим в follow-up/backlog и не цитируем как durable review carrier
- Если follow-up уже:
  - зафиксирован в ревью как “resolved/merged”,
  - превращён в отдельный dev-plan,
  - или уже уехал в канон,
  — то **не создавай** дубликат. В harvest report пометь как `handled`.
- Если rerun был `incremental` и review artifact явно закрыл blocker scope, пометь это как `closure by rerun`, но не считай этим автоматически закрытым full-wave residual debt.
- Если same-contract reroute шёл по тому же blocker ref, не создавай второй backlog item только из-за нового prose: reuse/handled определяется по canonical blocker ref, а не по формулировке finding.

4.1) Пометь кандидатов для downstream role-quality audit
- После dedupe/lineage pass отдельно ответь по каждому plan из range: `flagged` или `not audited`.
- `flagged` допускается только по literal Stage 1 signals из блока `Role-quality candidate lane (Stage 1)`.
- Для `flagged` зафиксируй в harvest report:
  - `Candidate source`: exact review ref или plan evidence line;
  - `Why flagged`: один короткий literal signal (`live ❌ S1 blocker`, `same review rerun loop`, `blocker-driven follow-up`, `explicit blocker/current-plan bounce`).
- Для flagged plans с CENSOR evidence выполни readback helper: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py censor_receipts_harvest.py --plan <flagged-plan> --review-artifact <review-artifact> --format json`; если review artifacts несколько, передай `--review-artifact` повторно.
- Harvest report не обязан дублировать весь JSON, но обязан сохранить enough helper-backed facts: role-quality category (`helped | missed live blocker | receipt missing | noise/no-op | UNCONFIRMED`), receipt source line, blocker ids, и unconfirmed reason/warning если они есть.
- Для `not audited` держи одну summary note с причиной отсутствия strong signal; не превращай harvest report во вторую matrix-таблицу.

4.1a) Собери `Runner quality range receipt`
- Если range содержит `runner_quality` rows или evidence использования external/non-default runner'ов, добавь в harvest report exact section `## Runner quality range receipt`.
- Заполни одну строку на task/lane: `plan`, `role_lane`, `runner_id`, `model`, `task_class`, `row_status`, `score_summary`, `required_frontier_intervention`, `missed_blockers`, `useful_for_future`, `follow_up_ref`, `source_ref`.
- Если usage detected, но строки нет, ставь `row_status=missing` и укажи source evidence; в Stage 1 это warning-first, но missing-row count должен быть виден Owner/Architect.
- Если строка weak/poor или требовала `major|blocker` frontier intervention, добавь `follow_up_ref` или explicit accepted no-op reason.
- Не парси private transcripts/provider logs; source refs должны вести к committed plan/review artifacts or lane metadata.

4.2) Process-improvement promotion decisions
- Если PI lane материализована, открой её generated promotion surface (docs/process_improvements/promotion_surface.md) и обработай mature rows: triaged/ready строки с non-`P?` `priority`, достаточными `target_canon_path`, `target_repo_scope`, `delivery_mode` или уже материализованной execution-семантикой требуют harvest decision.
- Owner-facing urgency читается из existing `priority`; не вводи harvest-only поля `urgency`, `delivery_carrier`, `defer_reason`, `reject_reason` или `promotion_ref`.
- В harvest report заполни dedicated surface `Process-improvement promotion decisions`: одна row на один mature candidate, поля минимум `source_ref` (или exact unique plan slug), `entry_id`, `decision`, `reason`, `execution_kind`, `execution_ref`, `owner_or_next_step`.
- Если ordinary followups result = `NO FOLLOWUPS`, а PI surface показывает raw `open|triaged|promoted|deferred|unconfirmed` rows, добавь compact `process_improvements_open_summary` перед rows/decisions с counts по статусам, `null_execution` и `delivery_refs`. Это не ordinary followup и не auto-promotion; это owner-visible readback separate lane.
- Для untriaged `open` rows используй `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py process_improvements_lint.py --project-root . --format json` staged `carrier_readback`: null target/delivery/execution carrier fields должны быть видимы даже когда default lint остаётся exit 0.
- Row resolution для lint/helper-proof: explicit `source_ref` -> `entry_id` -> exact unique plan slug; ambiguous/missing match = `unresolved_process_improvement_row`.
- Допустимые terminal decisions: `promoted`, `deferred`, `rejected`, `handled`.
  - `promoted` допустим только если raw row уже `status=promoted` и хранит materialized execution carrier: `execution_kind` + `execution_ref`; `execution_kind` использует canonical values `plan | helper | canon_doc | rollout_packet | umbrella_wave | external_ref`.
  - `handled` допустим только если raw row уже `status=handled`; already-handled row нельзя описывать как fresh `promoted`.
  - `deferred` требует `reason` и `owner_or_next_step` как owner/next-step или revisit condition; ordinary `docs/followups/*` bridge должен быть backlinked в raw `delivery_refs` и не может оставлять naked raw `open` row без execution carrier.
  - `triaged` row с terminal `execution_kind=plan` / `execution_ref` и null `handled_ref` / `promoted_at` / `handled_at` = `candidate_handled` / `needs_reconcile`, а не prose-only `handled`.
  - `rejected` требует `reason` и raw/source state, который не противоречит reject outcome.
- Mature row без row в `Process-improvement promotion decisions` = harvest blocker. Отсутствующий execution carrier не становится silent `promoted`; выбери `deferred` с reason/owner или `rejected` с reason.
- Этот governance step не заменяет helper-backed state apply: terminal prose в report должно совпадать с raw `docs/process_improvements/*` row state / derived surfaces либо быть явно pending/proposal. Execution materialization остаётся отдельным bounded action.
- Перед `✅ Done` прогони `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_harvest_lint.py` по изменённому harvest report, если он содержит `Process-improvement promotion decisions`; current mismatch должен падать lint'ом, а не жить как красивый terminal prose.
- Exact heading `Process improvements` зарезервирован для raw memory-finalize suggestions; harvest terminal decisions используют только `Process-improvement promotion decisions`.

4.3) Golden Path lane decisions
- Если range затрагивал UI/runtime, process workflow, rollout/import/ack flow или повторяемую review finding, harvest report обязан дать одну lane-specific строку:
  - `lane=product_runtime` для объявленного product UI/runtime carrier;
  - `lane=tooling_process` для source-owned process workflows в `planveyor` (post-merge audit, plan harvest, memory-finalize/docs-closeout, process-improvement promotion, source rollout packet lifecycle);
  - `lane=target_adoption` для rollout packet inbox/adoption-plan/harvest/ack flow;
  - `lane=N/A (why)` если range не породил Golden Path-worthy decision.
- Для выбранной lane запиши доставляемый active carrier и outcome `updated | no changes needed (why) | follow-up created | deferred (why)`. Для source-owned process lane carrier — engine reference `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`.
- Для source-owned process lane используй existing anchors, not invented lane names: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-plan-harvest"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-audit"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#process-improvement-promotion"`, or `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#source-rollout-packet-lifecycle"`.
- Если active registry не покрывает новый повторяемый workflow, outcome не может быть silent drop: либо `follow-up created`, либо `deferred (why)` с owner/next-step.

4.4) Docs retrieval metrics receipt
- Trigger: range/report text mentions `docs_retrieve`, `planveyor_docs_retrieve`, `docs_get`, `docs_multi_get`, `read_open`, `read_events_total`, `retrieval metrics`, or a linked docs-retrieve observability plan.
- Run aggregate helper for source repo: `planveyor_docs_retrieve_metrics --format json` (or `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py docs_retrieve_metrics.py --format json`). Target/sibling repos are optional read-only aggregate inputs only.
- Add exact section `## Docs retrieval metrics receipt` to the harvest report with one aggregate table. Required columns: `repo`, `repo_role`, `query_log_status`, `query_total`, `with_hits`, `zero_hits`, `hit_rate`, `warnings_total`, `errors_total`, `with_event_id`, `evaluated_total`, `outcome_evaluated_rate`, `outcome_used`, `outcome_partial`, `outcome_miss`, `outcome_noise`, `not_evaluated_total`, `read_log_status`, `read_events_total`, `read_open_rate`, `unique_paths`, `used_for_decision`, `low_coverage_triage`, `follow_up_ref`, `accepted_no_op_reason`, `source_command`.
- `repo_role=source` for current repo; `repo_role=read_only_target` for sibling aggregate rows. Missing query/read logs are recorded as `*_log_status=missing` with zero counts. `read_events_total=0` is valid evidence and must not be silently skipped.
- Low retrieval coverage is `outcome_evaluated_rate < 0.20` or `read_open_rate < 0.05`; if `used_for_decision=true`, the row must carry `follow_up_ref` or enum-like `accepted_no_op_reason`, otherwise post-merge closeout is blocked. If `used_for_decision=false`, the row must carry literal `accepted_no_op_reason=not_used_for_decision`, and the same artifact must not cite retrieval as decision evidence.
- Raw `.tmp` query/outcome/read JSONL logs remain local/disposable and are not committed.

4.5) Retrieval telemetry receipt
- Trigger: harvest report cites `planveyor_docs_lookup` or a retrieval-backed source-selection decision, not merely aggregate retrieval metrics.
- Prefer `planveyor_docs_lookup <canon|followups|plans> "query"` so query + instrumented read/open + receipt skeleton come from one bounded helper.
- Add exact section `## Retrieval telemetry receipt` with `query_event_id`, `used_for_decision`, `read_open`, `read_log_status`, `read_event_id`, `outcome`, `outcome_reason`, and `cited/opened files`, or a no-op reason from the closed enum above. If the receipt is telemetry-only, use `used_for_decision=false` with `no_op_reason=not_used_for_decision`.
- Raw `.tmp/planveyor_docs_retrieve_*.jsonl` logs stay local runtime evidence and are not durable harvest artifacts.

5) Создай follow-ups backlog (и промоуть в dev-plan, если нужно)
Правило:
- основной “actionable список” = `docs/followups/*` (не `docs/plans/*` и не harvest report);
- перед добавлением нового пункта проверь существующие master/range backlog’и (docs/followups/index.md), если этот index вообще материализован в текущем repo; иначе честно зафиксируй `N/A (why)` и держи backlog standalone range artifact;
- если пункт уже есть в другом backlog — в текущем harvest пометь его как `handled` (с pointer на backlog), а не создавай копию;
- если пункт уже есть только в `*_followups_memory_*.md`, но не materialize-ился в bounded backlog/dev-plan/closure note, не считай его handled: либо создай backlog-row сейчас, либо промоуть в dev-plan, либо зафиксируй explicit owner/canon rejection;
- source blocker refs держи literal-но в harvest/backlog notes, если follow-up или handled-state опирается на конкретный live blocker lineage;
- если follow-up готов к реализации → создай отдельный dev-plan в `docs/plans/` (`**Status:** Architect initial draft`) и в backlog отметь `status=promoted`, `plan=docs/plans/...`;
- если follow-up требует решения Owner → в backlog ставь `status=UNCONFIRMED` и `to=Owner`.
- если пункт “из памяти/не до конца подтверждён” → тоже помечай `UNCONFIRMED` (лучше явно эскалировать, чем канонизировать догадку).
- если пункт родился из de-scoped product debt (`removed from active scope` / `отдельный follow-up` / аналогичное literal note), default outcome не может быть silent drop: минимум backlog-entry с source note, максимум promoted dev-plan.
- если follow-ups нет — пиши `NO FOLLOWUPS` только с одной из допустимых причин из блока выше.

6) Triage/import inbox followups в cluster masters (только если docs/followups/index.md существует)
- После того как backlog range создан/обновлён, запусти triage:
  - если `FOLLOWUPS_OUT` создан/изменён самим harvest и поэтому не входит в reviewed `BASE..HEAD`: `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --dry-run`;
  - затем `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --apply`;
  - затем `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --apply` (повторно; проверка idempotency);
  - если inbox-файлы уже реально входят в reviewed range, особенно `*_followups_memory_*.md` или `*_followups_range_*`, range-mode обязателен: `planveyor_followups_triage --range "$RANGE" --dry-run|--apply`. Fresh `--file "$FOLLOWUPS_OUT"` не закрывает full range-memory consolidation.
- `--file` target должен быть repo-relative inbox under `docs/followups/*.md`; `docs/reviews/*`, docs/followups/index.md, `*_master.md`, absolute paths and parent traversal are invalid command surfaces.
- В harvest report секция `## Follow-up harvest triage/import receipt` должна сохранять command-level proof: mode (`--file` или `--range`), exact target, dry-run/apply/idempotency counts, `possible_duplicate` / `route_fallback` summary, для range-mode ещё и `unparsed_bullets`, и точный запуск `scripts/followups_index_rebuild.py` с readback docs/followups/index.md. Это source proof для top-level operational row `followups_triage_launch`; голое "imported" prose не закрывает launch receipt.
- Финальный proof не зелёный, если idempotency still has `append_new`, `possible_duplicate`, `route_fallback` или actionable `unparsed_bullets` без explicit durable `manual_decision_ref` / `already_tracked_ref`.
- Final operational receipt должен переносить sibling `process_improvements_open_summary` с `ordinary_followups_result=NO FOLLOWUPS`, `lane_status=separate`, `counts_by_raw_status`, `null_execution_rows`, `delivery_ref_rows` и `decision_receipt_path=<harvest>#process-improvement-promotion-decisions`; `planveyor_merge_bundle_report` блокирует current/new receipt, если separate PI lane есть, а summary отсутствует или malformed.
- Final operational receipt является selected host для `followups_lane_reconciliation`: он сохраняет file-lane result/count, triage mode, range apply/unresolved counts, `manual_decision_ref` / `already_tracked_ref`, source command and `owner_summary`; `planveyor_merge_bundle_report` blocks current receipts without this object or with counts that do not match `followups_triage_launch_receipt`.
- Источник routing: docs/followups/index.md (`Notes: clusters=<...>` у master строк).
- Результат apply:
  - новые/уникальные пункты импортированы в `*_followups_master.md`,
  - exact duplicates схлопнуты через `sources=[...]`,
  - inbox backlog-файлы получают `**Imported into:** ...` (cleanup-ready candidate marker для docs hygiene, не deletion permission),
  - `possible_duplicate` остаются в inbox до ручного решения,
  - для пунктов, реально закрытых в текущем `RANGE`, синхронизированы статусы в master backlog’ах (`status=promoted` → `status=handled`).
- Если docs/followups/index.md отсутствует в target-local consumer, triage/import пропускаем как `N/A (why=carrier absent)`; backlog range остаётся валидным конечным артефактом и не требует скрытого scaffolding.
- `**Imported into:** N/A (...)` не является импортом и не может быть used as cleanup-ready marker. Для repo-profile с materialized docs/followups/index.md и open rows это blocker: либо импортируй через `--file/--range`, либо оставь explicit `possible_duplicate`/manual triage reason.
- Перед удалением whole `docs/followups/*` source file Owner должен иметь semantic receipt: `planveyor_followups_query cleanup-receipt --project-root ... --format json`. `cleanup-ready` показывает только кандидатов; `cleanup-receipt` классифицирует `delete-ready|retain|needs-richer-summary` с reverse-reference proof и preserved summary.
- Harvested code-review/TODO inboxes are lossless carriers: generated rows preserve source intent (`source_intent`) separately from helper-normalized `canon_summary` when a title is rewritten. Treat those fields as deletion-safety proof inputs, not cosmetic metadata.
- `planveyor_followups_reconcile --apply` may mark `promoted -> handled` only when the target has an accepted `proof_class` beyond a bare terminal `**Status:** Done` header. Bare Done targets remain report-only as `candidate_needs_closure_proof`.

6.2) Rebuild open-followups summary in docs/followups/index.md
- После triage/import обнови auto-summary:
  - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_index_rebuild.py`
- Этот шаг не заменяет curated table/notes в docs/followups/index.md; он обновляет только auto-generated summary block с живыми `open|promoted|UNCONFIRMED` items.
- Для imported inbox files summary не должен создавать второй “active source” ряд: authoritative carrier остаётся master backlog или standalone non-imported range backlog.

6.1) Derived docs index refresh / coverage gate (только declared consumer lane)
- Выполняй после materialized harvest report/backlog, когда selected consumer
  объявил retrieval corpus in-scope:
  - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_index_build all`
  - consumer-owned coverage check для каждого declared corpus.
- В receipt/evidence фиксируй literal `covered/uncovered` summary или zero-uncovered
  proof для каждого corpus; одного “command ran” недостаточно.
- Для final operational receipt row `docs_index_context` обязателен только в
  выбранной index lane. При отсутствии lane запиши `N/A (why=not declared)`.
- Derived index DB — local state: не добавляй её в git и не используй как
  durable cleanup artifact.

7) Progress sync (roadmap/todo)
- Проверь фактически завершённые работы в `RANGE` и синхронизируй прогресс в:
  - существующий roadmap/todo carrier выбранного проекта из `Context links`
- Ставь `done`/`[x]` только при подтверждённом факте завершения.
- Если roadmap/todo carriers отсутствуют или не релевантны текущему repo-profile/range — зафиксируй это явно (`NO PROGRESS UPDATES`) в harvest/snapshot notes; если carriers есть, не ставь этот marker вместо фактической проверки.

8) Каноника и snapshots
- Если всплыли новые/изменившиеся **Key decisions / Constraints / Goal** → зафиксируй это в plan (append-only; `Architect suggestions` / `Follow-ups (deferred)`) и/или создай snapshot только как history/handover artifact; канон напрямую не правь в рамках harvest (вынеси канонизацию в follow-up dev-plan).
- Если всплыла “простыня контекста” → не прикрывай её snapshot-ссылкой в harvest report/каноне. Подними durable facts в canon / follow-up / audit, а snapshot используй только как вспомогательную историю без cited pointer'ов.

8.1) ADR harvest for durable decisions
- Если `## Key decisions / constraints` явно materialize-ят durable решение, которое переживёт cleanup временных plan/review artifacts, создай ADR draft в `docs/adr/NNN-topic.md` по `docs/adr/_template.md`.
- Минимальный contract ADR:
  - frontmatter: `status`, `date`, `decision-makers`, `source-range`, `source-plan`, `code-anchor`;
  - prose sections: `Canonical refs`, `Confirmation`, `Revisit signals`, `Superseded by / Supersedes`.
- Default status для свежего harvest outcome = `proposed`; `accepted` допустим только когда `code-anchor` уже truthfully жив и решение реально закреплено в коде/каноне.
- Если supersession уже известен, держи graph edge только в `## Superseded by / Supersedes`: допустимы repo/file path до ADR markdown или bare ADR id, который резолвится в sibling `docs/adr/<id>.md`; live `status` token при этом остаётся `superseded`, а не `superseded by <ADR>`.
- Не создавай ADR для тактических implementation choice внутри bounded slice; это остаётся в plan/audit, а не в `docs/adr/*`.

9) Финальный scrub durable artifacts
- Перед тем как ссылаться на новый harvest report / backlog / snapshot из канона или audit:
  - вычисти transient repo-state (`dirty`, `untracked`, “локально создано ...”), если это уже не живая session-note, а долгоживущий артефакт;
  - если repo-state нужен для восстановления, либо подними exact live fact, либо оставь explicit “check live git status/log”, а не устаревающее описание;
  - не оставляй `UNCONFIRMED` там, где факт можно добрать локально за одну команду.
  - если потом обновляешь active canon/registry, не используй snapshot'ы как pointer/cited source; snapshot остаётся только harvest/history/handover context, а durable хвост должен жить в canon / audit / follow-up.

10) Operational receipt перед closeout / cleanup позже
- Перед final `ready_to_push` materialize committed receipt только через `planveyor_post_merge_operational_receipt`: `docs/reviews/*_post_merge_operational_receipt_range_<base7>_<head7>.md`; schema фиксирует `schema_version/range/base/head/tracker_path` и rows `step/command/exit_code-or-result/artifact_path/count_summary/no_op_reason/in_scope/captured_at/source` для `docs_finalize`, `doc_lint`, archive apply, report-only hygiene suggest, index/context checks with explicit `plans_total/covered/uncovered`, `followups_total/covered/uncovered`, `canon_state` or closed no-op, retrieval metrics with `outcome_evaluated_rate`/`read_open_rate` plus `used_for_decision` and low-coverage triage or `accepted_no_op_reason=not_used_for_decision`, `canon_sweep`, and final `planveyor_merge_bundle_report`.
- Если docs/followups/index.md materialized и followups rows находятся в scope, final receipt дополнительно обязан иметь `steps[]` row `followups_triage_launch` и top-level `followups_triage_launch_receipt` с source harvest receipt path, structural command validation (`--file` only for valid `docs/followups/*.md` inbox, `--range` matching the receipt range), triage mode, dry-run/apply/idempotency counts, index rebuild command/status/readback и `process_improvements_lane=separate`. `planveyor_merge_bundle_report` blocks current/new receipts when range diff contains memory/range inbox obligations but receipt only proves fresh file-mode import.
- Перед тем как реально удалять планы/ревью в sibling: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`; source-only literal `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" ...` остаётся Self-Planveyor route.
- Для sibling обычный doc gate: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`; локальный convenience wrapper применим только если текущий repo его действительно materialize-ит.
- Docs diff sanity по текущему doc-diff: `git diff --check -- docs`
  - это показывает accidental trailing whitespace, CRLF, merge markers и лишние пустые строки в EOF в изменённых docs;
  - если нашёлся новый Markdown hard-break style — лучше переписать changed block без raw trailing spaces, чем тащить мусор дальше в history.
- Artifact-root hygiene после materialization harvest report/backlog/snapshot: sibling указывает target-local command в local section; Self-Planveyor only literal route: `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-basic-hygiene --root <artifact paths>`.
  - этот proof обязателен для newly materialized/untracked markdown artifacts, потому что tracked-only `git diff --check -- docs` может их не увидеть.
- Потом уже `docs/playbooks/post_merge_docs_hygiene.md`.

## External-only V2 follow-up capture

For a terminal `plan.v2`, harvest does not rewrite the source plan or create a
local `followups_out` mirror. A durable follow-up is a `followups.v2` row with
exact `(source_ref,item_id)`; `open` is accepted when its current-cycle proof
is exact (`external_clean`). Collect read-only declarations in strict
`Architect -> Coder -> Planner -> Reviewer` order, bind all of them to one
terminal commit/blob plus baseline snapshot, freeze tuple owners, and route
the single durable mutation only through `scripts/followups_apply.py`.
Missing/stale proof needs a new declaration pass. V1 stays read-compatible;
V2 never backfills history or imports work into the Manager queue.

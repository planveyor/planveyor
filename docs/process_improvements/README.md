# Process improvements — семейство carrier'ов

Назначение: держать raw process/helper/prompt improvements из `memory-finalize` отдельно от обычных implementation follow-ups и от активного канона.

Границы:
- shared section token для role outputs = `Process improvements`;
- canonical literal no-op = standalone строка `NO PROCESS IMPROVEMENTS — why: <reason_code>`, где `reason_code` ∈ `clean_run | already_tracked | out_of_scope | deferred_pending_data`; role output не должен префиксить её markdown-bullet, numbering или prose;
- если suggestion есть, она materialize-ится в dedicated backlog file под `docs/process_improvements/*`, а не в `docs/followups/*` и не в prose-only note.
- memory-finalize не обходит этот carrier прямой правкой active canon/templates/prompts/playbooks. После semantic `Done|Superseded` historical `code_draft_meta.targets` и уже promoted PI pointer — только provenance: они не разрешают менять terminal plan, linked code draft, live review или protected canon. Полезное предложение остаётся raw row, затем получает отдельный live non-terminal execution carrier с exact target ownership; reviewed exact bytes materialize-ятся только исходным pre-terminal exact-bundle closeout.

Status family boundary:
- `docs/process_improvements/*__process_improvements_backlog.md` accepts PI lifecycle statuses: `open | triaged | deferred | promoted | rejected | handled | unconfirmed`.
- ordinary `docs/followups/*` accepts only follow-up delivery statuses: `open | promoted | handled | unconfirmed`.
- `triaged`, `deferred` and `rejected` are PI-only states. A visibility or delivery bridge into ordinary followups must be a separate `status=open` / `plan=null` row until promoted, with the raw PI row carrying the backlink in `delivery_refs`.

## Helper contract

- Scope = `collect + triage + bounded promote/reconcile`.
- Manager/role family reuse-ит уже-landed shared schema: exact section token `Process improvements`, literal no-op, manager-fed `plan_ref` / loop / blocker payload.
- `docs/process_improvements/index.md`, `docs/process_improvements/deferred.md`, `docs/process_improvements/promotion_surface.md` = derived surfaces; truth surface = backlog files `*__process_improvements_backlog.md`.
- `scripts/process_improvements_lint.py` is the read-only grammar gate for truth-surface backlog files. Default scope is `docs/process_improvements/*__process_improvements_backlog.md`; derived/support docs are not primary grammar truth.
- `promote/reconcile` helpers меняют только raw backlog row и regenerated derived surfaces; live canon/helper/follow-up changes остаются отдельным осознанным bounded шагом.
- Даже в wave 1 promotion state уже не должен быть vague prose: mature row triage обязан materialize-ить literal `target_canon_path`, `target_repo_scope`, `delivery_mode`.
- Owner-facing `urgency` не является вторым полем: triage carrier использует existing `priority` (`P0|P1|P2|P?`) как urgency scalar.
- Execution pointer fields для mature rows: `execution_kind`, `execution_ref`, `delivery_refs`, `handled_ref`, `promoted_at`, `handled_at`.
- Upstream request import (`docs/upstream_packets/*` + `planveyor_upstream_request_import`) = только источник raw row: helper переносит `symptom` / `process_gap` / `suggested_fix` в source-local backlog и пишет `source_import_plan`, но не approve-ит request, не выставляет `source_decision_ref` / `source_execution_ref` и не пишет sibling repo files.

## Capture receipt / docs-closeout proof

`final_docs_commit=no_op` доказывает только отсутствие pending final docs commit. Это не доказывает, что role family не потеряла process-improvement suggestion, поэтому рядом есть отдельный capture proof:

- `process_improvement_capture_state=pending`: docs-finalize general family ещё не собрана или есть missing role receipt.
- `clean_noop`: все general roles вернули literal `NO PROCESS IMPROVEMENTS — why: ...`; backlog row не создаётся.
- `materialized`: collector создал durable row в `docs/process_improvements/*`.
- `already_tracked`: collector доказал duplicate/already-tracked outcome с exact carrier/reason.
- `blocked`: collector увидел malformed structured block, mismatched `source_ref`, invalid receipt или другой fail-closed input.

Manager вызывает `scripts/process_improvements_collect.py --role <Role> --source-ref <plan_ref> --followups-capture-cycle-id <capture_cycle_id> --input - --json` после каждого general docs-finalize role output. Для explicit cycle collector пишет только `process_improvement_capture.v2` по exact пути `.tmp/process_improvements_capture/<source-slug>/<capture-cycle-id>/<role>.json`: `input_sha256` считается по raw stdin/`--input` bytes до strict UTF-8 decode, а source/role/cycle и exact before/after maps проверяются при readback. Первая continuation publication exclusive; exact leaf или proven contiguous later-role replay is no-write, а changed/corrupt/unproved duplicate fail-closed до PI mutation. Единственная разрешённая replacement transition — validated `blocked -> clean_noop|materialized|already_tracked`; v2 continuation receipt never перезаписывается. No-cycle compatibility остаётся отдельной legacy `process_improvement_capture.v1` fixed-path веткой и не может быть proof для current cycle. Только structured suggestions materialize-ятся в durable `docs/process_improvements/*`. `planveyor_docs_closeout <PLAN_PATH> --json` читает эти receipts и печатает `process_improvement_capture_state`, `process_improvement_capture_reason`, `process_improvement_capture_roles`, `process_improvement_backlog_paths`, `process_improvement_receipt_path`.

### Exact general-to-followups checkpoint

Для одного full docs-finalize cycle Manager передаёт один canonical `followups_capture_cycle_id` во все четыре general collector calls. Каждый current `process_improvement_capture.v2` receipt обязан хранить exact fields:

- `source_ref`, exact role, `followups_capture_cycle_id` и raw-byte `input_sha256`;
- `before_process_improvement_files` и `after_process_improvement_files` — sorted maps regular-file objects `{sha256,file_type,st_size}` только для current-plan PI backlog и derived surfaces;
- `process_improvement_path_results` — sorted exact delta между этими maps.

После receipts в role order `Architect -> Coder -> Planner -> Reviewer` Manager вызывает только:

```bash
$PYBIN -B scripts/followups_capture.py checkpoint-general-pi \
  --project-root <root> \
  --plan-ref <plan_ref> \
  --capture-cycle-id <capture_cycle_id>
```

У команды нет stdin и нет caller-supplied receipt paths. Она safe-open'ит ровно четыре canonical v2 receipt paths через `capture_receipt_rel_path(plan_ref, role, capture_cycle_id)`, сверяет source/role/cycle/state, input digest, object identities/content digests, contiguous before/after chain, live post-map и freshness derived surfaces. Допустимы только role outcomes `materialized|clean_noop|already_tracked`: `clean_noop|already_tracked` обязаны иметь identical before/after maps и empty exact path-result delta, а `materialized` — non-empty exact object/path delta. Explicit-cycle reader не ищет directory/latest/mtime и не fallback'ит к v1; unsafe symlink/non-regular/malformed v2 carrier — red input. Перед baseline/checkpoint scan helper без shortcut доказывает canonical Git worktree: `git rev-parse --is-inside-work-tree` должен вернуть `true`, а `--show-toplevel` — exact `<project_root>`; probe игнорирует ambient `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR` и `GIT_INDEX_FILE`, поэтому отсутствующий/invalid `.git` или root mismatch — red input. Active dirty foreign `docs/process_improvements/*__process_improvements_backlog.md` вне canonical backlog текущего `plan_ref` — red input ещё до fresh или replay checkpoint. `blocked`, missing, legacy, wrong-cycle/role, extra/deleted object, stale derived surface или object/content mismatch — red input.

Green fresh call atomically publishes nullable-to-exact `general_pi_checkpoint` inside the existing `followups_capture_receipt.v1` authority, updates `current_process_improvement_files` to its after-map and returns `state=started`, `reason_code=followup_capture_pi_general_checkpointed`. Marker содержит canonical input receipt path/object/content identities, before/after maps, sorted path results, prior aggregate revision/content-digest fence и timestamp; он не меняет `pi_ownership_state=active`, `pi_final_objects={}` или `pi_failure_checkpoint=null`. Exact replay разрешён только before first followups progress and returns `followup_capture_pi_general_checkpoint_already_published` without receipt revision bump. После любого `prepare-role`/`finalize-role` checkpoint is phase-closed.

`prepare-role` для первого и каждого следующего followups lane требует published green marker. Перед каждым незавершённым `prepare-role` и `finalize-role` helper повторно доказывает тот же isolated canonical Git worktree и проверяет active dirty foreign `docs/process_improvements/*__process_improvements_backlog.md`; отсутствующий/invalid `.git`, root mismatch, ambient Git override, foreign path или scan failure блокирует cycle as non-adoptable до role/terminal mutation. Любая PI map mutation после checkpoint блокирует cycle as non-adoptable and never updates accepted final objects, staging authority or retry adoption. `dispatch_family` при этом остаётся ровно eight real role/lane records: four general, checkpoint outside payload, four followups.

Граница trusted local Git metadata определена в `docs/adr/010-trusted-local-git-metadata-boundary.md`: она не отменяет red input для missing/invalid repository, root mismatch или ambient Git override. Только repro, требующий unsupported local metadata tampering, получает отдельную Reviewer disposition по ADR; runtime hardening и sibling write этой ссылкой не разрешаются.

Compatibility boundary: fresh `begin` always writes `general_pi_checkpoint: null`. A finalized historical aggregate receipt that predates this field remains readable for historical terminal readback only. A non-terminal receipt without the field, or a current-cycle collector receipt without the three object-chain fields, is never upgraded/reconstructed and cannot checkpoint, prepare followups, stage or prove current-cycle docs-closeout. Pathname, `latest`, mtime and chat prose are never proof substitutes.

Backcompat rule: canonical emit remains unbulleted. Collector tolerates a legacy single-line bullet no-op (`- NO PROCESS IMPROVEMENTS — why: <reason_code>` or `* NO PROCESS IMPROVEMENTS — why: <reason_code>`) only when it is the whole meaningful `Process improvements` body. No-op mixed with structured suggestions, unsupported reason codes or extra body text remains `blocked`.

Structured-field tolerance rule: role prompts still require canonical `- key: value` structured suggestions. For docs-closeout stdout intake only, collector also tolerates known fields without a markdown bullet (`symptom: ...`, `process_gap: ...`, `suggested_fix: ...`, `owner: ...`, `promotion_class: ...`, `trigger_ref: ...`, `source_ref: ...`). This tolerance is field-name bounded and receipt-backed; `* key: value`, numbered fields, free prose, unknown fields, missing required fields, mixed no-op plus suggestions and mismatched `source_ref` remain `blocked`. Backlog/import file grammar stays strict unless a separate plan changes and tests that surface.

Continuation rule: до full family `pending` валиден; после full family Manager продолжает queue/single-plan closeout только при `clean_noop|materialized|already_tracked`. `blocked` или `pending` после family completion = operational docs-closeout blocker, а не повод Manager'у писать process-improvement row руками.

Priority rule: любой `blocked` role receipt выигрывает у `pending` missing-role state. Collector failure нельзя маскировать тем, что остальные general roles ещё не прислали receipts: Manager должен остановиться на `blocked` и не ждать полного family completion как будто это обычный `pending`.

Advisory readback: `planveyor_docs_closeout <PLAN_PATH> --json` также печатает `process_improvement_advisory_state`, `process_improvement_advisory_reason`, `process_improvement_advisory_counts` и `process_improvement_advisory_proof_host`. Эти поля читают raw backlog rows из `docs/process_improvements/*__process_improvements_backlog.md` и показывают open/triaged/promoted/deferred/unconfirmed counts, `null_execution` rows и rows с `delivery_refs`, но не меняют `process_improvement_capture_state` и не участвуют в `terminal_closeout_fast_path.missing_or_dirty_preconditions`.

Advisory state contract:
- `clean_noop`: backlog files отсутствуют или не содержат advisory rows.
- `advisory_backlog`: raw PI rows ещё видимы как owner-facing backlog/readback; это context, а не semantic closeout blocker.
- `unknown`: backlog readback не смог распарсить raw carrier; capture proof всё равно остаётся отдельным fail-closed host, если collector receipt broken/blocked.

Ordinary `docs/followups/*` bridge допустим только когда raw PI row имеет явный delivery scope/backlink (`delivery_refs`) или promoted execution carrier. `process_improvement_advisory_*` не создаёт follow-up автоматически и не заменяет triage/promote/reconcile helpers.

## Structured suggestion block

Если role не пишет literal no-op, секция `Process improvements` обязана использовать exact machine-readable block:

```md
## Process improvements
### Suggestion 1
- symptom: <что болит / где loop проявился>
- process_gap: <какой process/helper/prompt gap surfaced>
- suggested_fix: <bounded fix / guardrail>
- owner: <Architect|Planner|Coder|Reviewer|Manager|Owner>
- promotion_class: <canon_update|prompt_change|helper_change|routing_change|followup_plan>
- trigger_ref: <review/blocker/plan/queue ref или unknown>
- source_ref: <manager-fed plan_ref или unknown>
```

Правила:
- `symptom`, `process_gap`, `suggested_fix` = одна bounded мысль, без free-form essay.
- `trigger_ref` и `source_ref` должны быть literal refs, а не “см. выше”.
- `scripts/process_improvements_collect.py` считает CLI `--source-ref` truth carrier: `source_ref: unknown` нормализуется к этому lane, а mismatched literal ref helper reject-ит как invalid input вместо silent reroute в чужой backlog file.
- `promotion_class` не расширяется из role output. Template/runbook/playbook/review-template canon changes классифицируются как `canon_update`; prompt changes — `prompt_change`; helper/wrapper/script changes — `helper_change`. Нелегальные удобные ярлыки вроде `template_change`, `runbook_change` или `gate_change` должны быть переформулированы в supported class; collector может нормализовать такие legacy aliases в `canon_update` только как backward-compatible intake, не как новый canonical enum.
- Если suggestion честнее оформить как отдельный backlog-item вне этого carrier, оставляй его в `Follow-ups`, а здесь используй no-op literal.

## Triage-only fields

Role output не обязан знать delivery semantics. Их добавляет triage:

- `target_canon_path`: literal canon/helper path, куда реально должен приехать change.
- `target_repo_scope`: `current-consumer | <target-repo> | multi_repo`; `shared_consumer` is only a receipt impact enum.
- `delivery_mode`: `source_only | source_plus_rollout | packet_only | umbrella_mixed`.
- `execution_kind`: `plan | helper | canon_doc | rollout_packet | umbrella_wave | external_ref`.
- `execution_ref`: primary literal execution carrier.
- `delivery_refs`: `null` или `; `-separated literal ref list.
- `handled_ref`: terminal proof carrier для `handled`.
- `promoted_at` / `handled_at`: timestamp receipts.

Минимальный смысл:
- `priority=P?` допустим для raw `open` intake, но `triaged|promoted|handled` rows должны заменить его на `P0|P1|P2`.
- `target_canon_path` без `target_repo_scope` и `delivery_mode` = всё ещё недоформулированный promotion state.
- `open` rows с `priority=P?`, null target/delivery/execution carrier fields остаются legacy-compatible, но показываются в staged `carrier_readback` как owner-facing untriaged debt.
- `source_only` = change materialize-ится только в текущем repo canon.
- `source_plus_rollout` = change сначала materialize-ится в source canon, потом едет в sibling repos через rollout packet/import path.
- `packet_only` = source repo сам не меняет свой canon, а готовит handoff для target-local adoption.
- `umbrella_mixed` = один promoted row сознательно требует отдельной umbrella/change wave, а не single-path edit.
- Packetization для backlog-change читает exact Git snapshots `BASE` и `HEAD` через тот же parser: сравнивается `(path, entry_id)` delta (add/modify/delete), а не live working tree. Fully-null `open` и valid `rejected` rows остаются `source_only`; `unconfirmed`, ambiguous/malformed fields, unsupported mode или multi-repo state fail closed.
- Если раньше target-bearing row удалён либо меняет target repo/kind/carrier, transition обязан иметь checked-in authority: для surviving HEAD row это literal `packetization_withdrawal_ref=` или `packetization_replacement_ref=` в его `triage_note`; для физически удалённой row authority host — только cancelled/superseded rollout packet из literal BASE-row `delivery_refs`, прочитанный из exact HEAD snapshot. Такой packet обязан иметь source-side acknowledgement с тем же literal withdrawal/replacement ref, включать backlog path в `source_artifacts` и точно совпадать со старым target repo/kind/carrier set. Worktree-only packet, open packet, missing reason или неточное target identity не authorise removal. Для nonempty target partition `target_canon_path`, `target_repo_scope`, `delivery_mode` и `execution_kind` дают один exact target repo/kind/carrier set, а не global sibling union.
- `promoted` requires literal `target_*` / `delivery_mode` plus `execution_kind`, `execution_ref`, `promoted_at`.
- `triaged` requires literal `target_canon_path`, `target_repo_scope`, `delivery_mode`, non-`P?` `priority`, and either execution/delivery refs or an explicit `triage_note` decision.
- `handled` additionally requires `handled_ref`, `handled_at`.
- `rejected` requires explicit reason in `triage_note`; rejected state не создаёт ordinary follow-up shadow row.
- `deferred` requires owner, `triage_note` with reason/revisit trigger, and either literal `delivery_refs` or an explicit null-delivery reason in `triage_note`.
- `delivery_refs` не принимает prose, JSON blobs, `later`, `TBD` или `unknown`; multi-ref value хранится как deterministic scalar через `; `.

## Row-state closure grammar

Post-merge harvest не закрывает process-improvement row красивой строкой в review report. Truth остаётся raw row в `docs/process_improvements/*`; derived `promotion_surface.md` / `deferred.md` и helper receipts только читают или пересобирают это состояние.

- `promoted`: raw row уже `status=promoted`, держит `target_canon_path`, `target_repo_scope`, `delivery_mode`, `execution_kind`, `execution_ref`, `promoted_at`.
- `handled`: raw row уже `status=handled`, держит весь promoted contract плюс `handled_ref` и `handled_at`.
- `deferred`: допустим как parked state только с owner, reason/revisit trigger в `triage_note`, и `delivery_refs` либо explicit null-delivery reason.
- `triaged` с `execution_kind=plan` / `execution_ref` и null terminal fields не считается закрытым. `process_improvements_reconcile.py --report --format json` должен показать такую строку как `candidate_handled` / `needs_reconcile`, если execution plan уже terminal.
- Non-plan repo-local carriers (`helper`, `canon_doc`, `rollout_packet`, `umbrella_wave`) не закрываются одним фактом существования файла: carrier должен содержать отдельную строку `process_improvement_id: PI-NNN`, совпадающую с raw row. Missing/wrong/ambiguous id остаётся `stale_promoted` и не попадает в `--apply`.
- `docs/followups/*` может быть visibility bridge. Он обязан быть backlinked из raw `delivery_refs` и не заменяет `status`, `handled_ref`, `promoted_at` или `handled_at`.

## Helpers

Public facade functions `planveyor_process_improvements_promote` and `planveyor_process_improvements_reconcile` delegate to the Python helpers below; invoke them through `./bin/planveyor <function> [args…]`.

Lint:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_lint.py --project-root .
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_lint.py --project-root . --format json
```

Правила lint:
- default scan берёт только real backlog carriers `docs/process_improvements/*__process_improvements_backlog.md`;
- positional file/dir args допустимы для focused lint;
- `README.md`, `_template_process_improvements_backlog.md`, `index.md`, `deferred.md` и `promotion_surface.md` не являются primary grammar truth в default/directory scan;
- findings возвращают non-zero exit и не мутируют input files или derived surfaces.
- JSON output включает staged `carrier_readback`: rows с missing triage carrier fields, включая `open` rows с null carrier fields, показываются owner-facing, но legacy corpus не становится hard blocker.
- `--require-triage-carrier` превращает staged `carrier_readback` rows в hard findings для focused cleanup/fixture gates; это opt-in cleanup mode, а не default queue blocker.

Collect:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_collect.py \
  --role Coder \
  --source-ref docs/plans/<PLAN_PATH>.md \
  --input -
```

External file import:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_collect.py \
  --project-root . \
  --import-file docs/process_improvements/<ROW>.md \
  --report \
  --format json

PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_collect.py \
  --project-root . \
  --import-file docs/process_improvements/<ROW>.md \
  --apply \
  --format json
```

Правила external import:
- `--import-file` принимает только explicit readable `docs/process_improvements/*.md` file paths; directory walk и glob expansion внутри helper'а запрещены;
- helper читает external file как evidence carrier, но пишет только current repo `docs/process_improvements/*`;
- source header `Status:` не становится local row status автоматически;
- external file path становится local row `source_ref`, а исходные `Plan ref:` / suggestion `source_ref:` / `trigger_ref:` сохраняются в `triage_note` / row fields для provenance;
- `--report` не пишет backlog/derived surfaces; `--apply` создаёт или переиспользует local backlog row и пересобирает `index.md`, `deferred.md`, `promotion_surface.md`.

Triage:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_triage.py \
  --backlog docs/process_improvements/<SOURCE>__process_improvements_backlog.md \
  --entry PI-001 \
  --status triaged \
  --priority P1 \
  --owner Architect \
  --target-canon-path docs/tools/owner_runbook_codex.md \
  --target-repo-scope current-consumer \
  --delivery-mode source_only \
  --execution-kind canon_doc \
  --execution-ref docs/tools/owner_runbook_codex.md \
  --delivery-refs null \
  --promoted-at "2026-04-30 12:30 +0000" \
  --triage-note "bounded canon update after first live row"
```

Promote:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_promote.py \
  --backlog docs/process_improvements/<SOURCE>__process_improvements_backlog.md \
  --entry PI-001 \
  --execution-kind plan \
  --execution-ref docs/plans/<EXECUTION_PLAN>.md \
  --promoted-at "2026-04-30 12:30 +0000" \
  --report
```

Правила promote:
- `--apply` требует literal `execution_kind`, `execution_ref`, `promoted_at`.
- Для repo-local `execution_kind` (`plan`, `helper`, `canon_doc`, `rollout_packet`, `umbrella_wave`) `execution_ref` должен уже существовать внутри repo; helper не scaffold-ит missing carrier.
- `external_ref` допустим как явный non-repo pointer, но не считается source-local terminal proof для reconcile.

Reconcile:

```bash
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_reconcile.py --report
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/process_improvements_reconcile.py \
  --apply \
  --handled-at "2026-04-30 12:45 +0000"
```

Правила reconcile:
- report разделяет `candidate_handled`, `stale_promoted`, `missing_execution_ref`.
- `plan` carriers становятся `candidate_handled` только при terminal `**Status:** Done`.
- non-plan repo-local carriers становятся `candidate_handled` только при exact row proof `process_improvement_id: PI-NNN`; reason = `verified_process_improvement_id`.
- missing/wrong/ambiguous `process_improvement_id` даёт `missing_process_improvement_id` / `process_improvement_id_mismatch` / `ambiguous_process_improvement_id` в `stale_promoted`.
- apply помечает `handled` только safe terminal rows и пишет `handled_ref` / `handled_at`.
- missing/stale/external refs остаются report-only; ambiguous state требует отдельного Architect/Planner решения.

Upstream request import:

```bash
planveyor_upstream_request_show docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md
planveyor_upstream_request_import --packet docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md
planveyor_upstream_request_query --status open --json
```

Правила upstream import:
- packet path остаётся evidence handoff, не queue item;
- import создаёт или переиспользует source-local `docs/process_improvements/*` row и обновляет только source-local upstream packet;
- дальнейшее решение materialize-ится отдельно через normal triage/promote или source-local plan.

## Derived surfaces

- `docs/process_improvements/index.md`: navigation + live backlog summary, включая promoted/handled counts.
- `docs/process_improvements/deferred.md`: open/deferred/unconfirmed tail that is not ready for promote.
- `docs/process_improvements/promotion_surface.md`: explicit promotion state with literal `target_canon_path`, `target_repo_scope`, `delivery_mode` and execution pointer fields.

## Naming

- Per-source backlog file name = `<SOURCE_STEM>__process_improvements_backlog.md`.
- `SOURCE_STEM` derives from `source_ref` stem; repeated collect on the same source appends rows to the same backlog file instead of spawning ad hoc duplicates.

## Non-goals

- Не превращать это семейство в второй `process_followups_master.md`.
- Не дублировать rows между `docs/process_improvements/*` и `docs/followups/*`.
- Не хранить promotion state только в prose.
- Не оставлять repo/delivery semantics “на потом”, если row уже matured до triage/promote discussion.

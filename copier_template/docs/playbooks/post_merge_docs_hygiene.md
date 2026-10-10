# Playbook: post-merge docs hygiene (temp docs cleanup)

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

Цель: после merge в `main` можно отдельно, по owner decision, удалить временные артефакты (`docs/plans/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`, `docs/code_drafts/*`),
**не потеряв** решения/контракты.

Правило: **удаляет файлы Owner** (агент не тратит токены на “посимвольное удаление”).

Обязательное правило процесса: post-merge semantic closeout не требует удаления temp docs. `planveyor_docs_hygiene_archive --apply`, fresh `planveyor_docs_archive_snapshot_export --backend git_text_export --output-dir docs/_meta/archive_snapshots/current --force` и automated `planveyor_post_merge_docs_hygiene_suggest_gate` в merge flow попадают в committed operational receipt, созданный через `planveyor_post_merge_operational_receipt`, `docs/reviews/*_post_merge_operational_receipt_range_<base7>_<head7>.md` как schema-backed command/result/no-op rows плюс обязательные `archive_snapshot` и `docs_hygiene_suggest_summary` блоки; summary фиксирует `report_only=true`, `deletion_executed=false`, `ready_to_push_ticked_by_suggest_gate=false`, candidate counts/top candidates/omitted count. `retrieval_metrics` row фиксирует `outcome_evaluated_rate`, `read_open_rate`, `used_for_decision`, а telemetry-only metrics carry `accepted_no_op_reason=not_used_for_decision`; low coverage blocks only when `used_for_decision=true` without `follow_up_ref` / accepted no-op reason. Если followups находятся в scope, committed receipt также несёт `followups_triage_launch` / `followups_triage_launch_receipt`: `--file` допустим только для fresh repo-relative `docs/followups/*.md` inbox, а reviewed range с memory/range inboxes требует `--range BASE..HEAD` proof. `planveyor_docs_hygiene_suggest` остаётся report-only и gate тикает только `step:docs_hygiene_suggest` после markers `[planveyor] Range:` + `[planveyor] Suggested (Owner) command:`; он не заменяет followups triage/import proof. Перед любым последующим `git rm` временных docs Owner заново проверяет range, выполняет `planveyor_docs_hygiene_archive --range BASE..HEAD --apply`, fresh snapshot export, затем `planveyor_docs_hygiene_suggest`, выбирает candidates и делает отдельный cleanup commit.

Step-local docs-finalize preflight: перед tracker tick/advance для `step:docs_finalize` сохрани materialized role output/receipt в durable path и запусти `planveyor_post_merge_receipt_preflight docs_finalize --path <saved-docs-finalize-output>`; general lane must contain parseable `Process improvements`, followups lane may be literal `NO FOLLOWUPS`. Это schema proof only: final `planveyor_merge_bundle_report` и operational receipt остаются terminal readiness gates.

Terminal docs-closeout fast-path: после semantic `Done|Superseded` Manager может пропустить full docs-finalize/followups family только по fresh `planveyor_docs_closeout <plan_ref> --json`, где `terminal_closeout_fast_path.schema=terminal_closeout_fast_path.v1`, `eligible=true`, `missing_or_dirty_preconditions=[]`, `followups_reconciliation.state=clean_noop`, `process_improvement_capture_state=clean_noop|materialized|already_tracked`, `final_docs_commit=no_op|landed`, `protected_docs_delta_paths=[]` и runtime blocker fields не содержат live signals. Readback обязан назвать `skipped_lanes` и `proof_hosts`. Любой open/unknown followups proof, pending/blocked process-improvement capture, `final_docs_commit=required`, protected docs delta, invalid/non-materialized bundle или live blocker signal fail-closed возвращает existing full family через `fallback_lanes`.

## Scope contract

- Inventory/scan roots механизма: `docs/plans/*`, `docs/followups/*`, `docs/code_drafts/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`, `docs/reviews/*`, `docs/snapshots/*`.
- Default delete targets: `docs/plans/*`, `docs/code_drafts/*`, `docs/code_reviews/*`, `docs/doc_reviews/*` + связанные `docs/code_reviews/assets/*`.
- Optional delete targets:
  - `docs/followups/*` только после import/triage, `planveyor_followups_query cleanup-receipt --project-root ... --format json`, решения `delete-ready` по каждому файлу и отсутствия “живых” reverse refs. Import/triage proof must use `--range BASE..HEAD` when the reviewed range contains `*_followups_memory_*.md` / `*_followups_range_*.md`; fresh `--file` proof closes only that new inbox file.
  - `docs/snapshots/*` только по явному owner decision / `--include-snapshots`; по умолчанию snapshots считаем историческим контекстом, а не auto-delete целью.
- `docs/reviews/*` и `docs/snapshots/*` входят в range-inventory и в проверки на живые ссылки, но **не** считаются default `git rm` кандидатами.

## Куда уезжают знания (policy)
Перед удалением временных артефактов убедись, что knowledge переехало в
объявленные canonical owners текущего project/profile:
- contracts архитектуры и поведения → выбранный architecture/runtime canon;
- API/data/component contracts → выбранные API/schema/registry carriers;
- operations/runbooks → выбранный operations carrier.

Пути architecture/API/schema/registry/UI/runtime канонов берём из `Context links`
выбранного проекта. Проверяем только существующие carriers; shared corpus
не назначает им фиксированные имена.
- Результаты аудитов/проверок (матрицы/итоги) → `docs/reviews/*`
  - В audit-report’ах не ссылаться на удаляемые `docs/plans/*` / `docs/code_reviews/*` как на файлы (не писать `docs/plans/...` / `docs/code_reviews/...` ссылками); если нужно — указывать **только имя файла** (“git history: …”) и/или ссылаться на audit-report.
- “Что сейчас важно” → существующие backlog и roadmap выбранного проекта (а конкретный текущий `PLAN_PATH` — из plan/гит‑истории, не из “бордов”).

## Pre-delete checklist (коротко)
1) Вытащить итоговые решения из plan/review и перенести в канон (см. policy выше).
   - Рекомендуемый “мелкий гребень”: `docs/playbooks/post_merge_plan_harvest.md` (follow-ups + canon updates).
2) Проверить, что в каноне нет ссылок на файлы, которые планируем удалить.
   - Для `docs/followups/*` `cleanup-ready` означает только syntactic candidate: `**Status:** ✅ Done` + real `**Imported into:** ...`; it is not range triage proof and does not allow deletion by itself.
   - Перед deletion нужен durable semantic receipt: `planveyor_followups_query cleanup-receipt --project-root ... --format json`. Только `decision=delete-ready` с reverse-reference proof, preserved summary, source status/classification readback and accepted closure `proof_class` может попасть в Owner cleanup selection; `retain` / `needs-richer-summary` остаются в git.
   - Практика для range‑cleanup: проверяем **точные basename** временных plan/review файлов по каноническим корням, чтобы не ловить ложные совпадения на общих словах (`example.md`, `guide.md` и т.п.).
   - Мини-проверка строится только по canonical roots, объявленному selected
     profile. Подставь существующие canonical roots выбранного проекта:
   ```bash
   tmp=$(mktemp)
   git diff --name-only BASE..HEAD -- docs/plans docs/code_reviews docs/doc_reviews \
     | xargs -n1 basename | rg '^[0-9]{6}.*\\.md$' | sort -u > "$tmp"
   rg -n -F -f "$tmp" <existing-canon-roots> || true
   rm -f "$tmp"
   ```
   - Быстрый process-canon guard против pinned dated refs:
   ```bash
   rg -n "docs/plans/[0-9]{6}_[0-9]{4}|docs/snapshots/[0-9]{8}_[0-9]{4}" \
     docs/tools docs/playbooks docs/roles || true
   ```
   - В этих корнях прямые dated refs считаем дефектом: historical deep dive должен идти через retrieval/archive recipe, а не через “вечные” temp-doc links.
3) Прогнать strict doc_lint по канону (см. `docs/playbooks/doc_lint.md`).
4) Зафиксировать follow-ups (если появились) в `docs/followups/*` и/или сделать snapshot `docs/snapshots/*` (если есть риск потерять контекст).
5) Убедиться, что central archive уже прогнан перед удалением temp docs:
   - в стандартном `merge_run` это делает Manager на шаге `step:docs_hygiene_archive`;
   - при ручном rerun / вне pipeline: `planveyor_docs_hygiene_archive --range BASE..HEAD --apply`;
   - минимум проверки: команда не упала и напечатала `Archive result` / `Archive candidates`, даже если кандидатов оказалось 0.

## Helper commands (inventory + report-only rm suggestions)
1) (Опционально) Инвентаризация “что вообще трогали” по диапазону:
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_hygiene_list
```
Это helper для полного touched-doc inventory; в merge-tracker это больше не отдельный gate-step.
2) Авто‑матчинг plan↔review/assets и предложение `git rm` (без удаления):
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_hygiene_suggest
```
Команда:
- группирует terminal plans (`Done` + `Superseded`) и связанные временные артефакты (`docs/code_drafts/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`, `docs/code_reviews/assets/*`, опционально `docs/followups/*` / `docs/snapshots/*`),
- печатает готовый `git rm ...` (Owner копирует/правит руками),
- предупреждает, если файлы всё ещё где-то “живы” (есть ссылки вне временных каталогов),
- использует `docs/reviews/*` и `docs/snapshots/*` как часть инвентаризации диапазона и как источники blocker-ссылок, но не как default delete targets.
- в post-merge closeout `planveyor_post_merge_docs_hygiene_suggest_gate` запускает report-only helper automatically, требует markers `[planveyor] Range:` + `[planveyor] Suggested (Owner) command:`, тикает только `step:docs_hygiene_suggest` и не выполняет suggested `git rm`; сам suggested `git rm` можно выполнить позже только после fresh archive/suggest.
- `planveyor_docs_hygiene_suggest` не импортирует followups и не закрывает range-memory obligations; если range содержит `docs/followups/*followups_memory*.md` или `*_followups_range_*`, сначала нужен `planveyor_followups_triage --range BASE..HEAD --apply` и idempotency proof.
- Для optional `docs/followups/*` deletion сначала получи semantic gate:
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_followups_query cleanup-ready --project-root .
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_followups_query cleanup-receipt --project-root . --format json
```
`cleanup-ready` = список кандидатов; `cleanup-receipt` = per-file decision. Не копируй `cleanup-ready` в `git rm`.
Если `cleanup-receipt` возвращает `missing_proof_refs` или reconcile показывает `candidate_needs_closure_proof`, это не permission bug: сначала добавь/дождись repo-backed review/merge/arch-review proof, затем повтори receipt.

3) (Обязательно перед `git rm`) Архивировать удаляемые temp-doc markdown artifacts в локальную SQLite FTS (не в git):
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_hygiene_archive --range BASE..HEAD --apply
```
В стандартном `merge_run` этот шаг может быть уже закрыт автоматически для closeout receipt, но для отдельного cleanup commit после новых doc changes Owner всё равно делает fresh run. Архив централизованный (append-only) и живёт в **main worktree**: `planveyor_docs_archive_db`.
Что именно попадает в archive по умолчанию:
- terminal plans из диапазона: `Done` + `Superseded`;
- связанные markdown temp artifacts, которые safe-to-delete: `docs/code_drafts/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`;
- опционально по флагам: `Done` followups и snapshots, если ты явно попросил `--include-followups` / `--include-snapshots`;
- не default target: `docs/reviews/*` (merge notes / harvest / post-merge audit остаются живыми файлами, их archive step по умолчанию не трогает);
- не архивируется в SQLite FTS: бинарные assets (`png/jpg/webp`) и директории `assets/`.
Если нужен smoke-check retrieval:
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_query --k 12 "<declared topic phrase>"                # wrapper default = signal profile
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_query --profile all --k 12 "<declared topic phrase>"  # deep search across all archived kinds
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_query --kind code_draft --k 12 "<declared topic phrase>"
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_show --id <doc_id>
```
Wrapper vs raw CLI:
- `planveyor_docs_archive_query` без явных фильтров = owner-facing default `--profile signal` (`plan`, `code_review`, `doc_review`).
- Raw `scripts/docs_archive.py query` без `--profile` / `--kind` сохраняет back-compat `all kinds`; для signal-first raw mode передавай `--profile signal`.

## Portable archive snapshot

Central archive DB остаётся generated/local state в `.tmp`, но переносимый слепок текущего состояния живёт в git-backed carrier:
- selected backend: `git_text_export`;
- manifest: `manifest.json` в каталоге `docs/_meta/archive_snapshots/current/`; файл появляется после первого `planveyor_docs_archive_snapshot_export`;
- artifact: `docs/_meta/archive_snapshots/current/archived_docs.jsonl`;
- readback source DB (размер, docs, distinct paths, kinds, archive range) печатает `planveyor_docs_archive_snapshot_info` текущего проекта.

Snapshot commands:
```bash
manifest=docs/_meta/archive_snapshots/current/manifest.json
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_info
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_export --backend git_text_export --output-dir docs/_meta/archive_snapshots/current --force
if test -f "$manifest"; then
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_validate --manifest "$manifest" --verify-artifact
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_restore --manifest "$manifest" --dest-db .tmp/planveyor_docs_archive_restored.sqlite --replace --query "post merge archive snapshot" --expect-min-hits 1
else
  echo "snapshot не выгружен: нет $manifest" >&2
fi
```

Fresh-clone restore:
```bash
manifest=docs/_meta/archive_snapshots/current/manifest.json
if test -f "$manifest"; then
  # proof lane: use a disposable DB first, not the old machine-local .tmp DB
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_validate --manifest "$manifest" --verify-artifact
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_restore --manifest "$manifest" --dest-db .tmp/planveyor_docs_archive_restore_check.sqlite --replace --query "post merge docs hygiene" --expect-min-hits 1
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_query --db .tmp/planveyor_docs_archive_restore_check.sqlite --profile signal --k 12 "post merge docs hygiene"

  # fresh clone local-state refresh after proof
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_restore --manifest "$manifest" --dest-db .tmp/planveyor_docs_archive.sqlite --replace --query "post merge docs hygiene" --expect-min-hits 1
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_query --db .tmp/planveyor_docs_archive.sqlite --profile signal --k 12 "post merge docs hygiene"
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_show --db .tmp/planveyor_docs_archive.sqlite --path docs/plans/<archived-plan>.md
else
  echo "snapshot не выгружен: нет $manifest" >&2
fi
```

Restore rebuilds archive SQLite tables plus `archived_chunks_fts`, so normal archive query/show helpers work after clone without the original `.tmp/planveyor_docs_archive.sqlite`. The separate current-docs retrieval index is still disposable generated state; rebuild it with `planveyor_docs_index_build all` when needed.

Object-store lane:
```bash
manifest=docs/_meta/archive_snapshots/current/manifest.json
if test -f "$manifest"; then
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_validate --manifest "$manifest" --verify-artifact --object-file .tmp/object-store/planveyor_docs_archive.sqlite
  "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_archive_snapshot_restore --manifest "$manifest" --dest-db .tmp/planveyor_docs_archive.sqlite --replace --object-file .tmp/object-store/planveyor_docs_archive.sqlite --query "post merge docs hygiene" --expect-min-hits 1
else
  echo "snapshot не выгружен: нет $manifest" >&2
fi
```

For `s3_minio_sqlite`, the repo-backed manifest is not enough by itself: restore requires explicit object bytes from configured non-secret object-store access and fails closed on missing object, size mismatch or checksum mismatch. Do not commit credentials, presigned URLs or secret-bearing endpoint strings. Deployment-specific facts remain deferred unless a dedicated proof verifies exact commands/paths without secrets.

`step:ready_to_push` receipt rule: after `docs_hygiene_archive` and before Owner push handoff, Manager must run fresh `git_text_export`, validate, restore/readback, then record the archive snapshot result in `planveyor_post_merge_operational_receipt --archive-snapshot-json ...`. Required archive receipt fields are `status`, `storage_backend`, `manifest_path`, `artifact_path` or `object_uri`, `checksum`, `format_version`, `access_status`, `export_command`, `export_status`, `snapshot_created_at_utc`, `snapshot_source_db_sha256`, `snapshot_source_docs_count`, `restore_status`, `readback_status`, `no_op_reason`, `blocker_reason`, and `source`. The same committed receipt must include `docs_hygiene_suggest_summary` with `report_only=true`, `deletion_executed=false`, `ready_to_push_ticked_by_suggest_gate=false`, candidate counts/top candidates/omitted count, and the fresh rerun/archive commands. It must also include `retrieval_metrics` with `used_for_decision=true|false`; `used_for_decision=false` requires `accepted_no_op_reason=not_used_for_decision`, while low coverage with `used_for_decision=true` requires a durable `follow_up_ref` or accepted enum-like no-op reason. When followups are in scope, it must also include `followups_triage_launch_receipt` with structural command validation, range-mode proof for memory/range inbox obligations, closed duplicate/route-fallback/unparsed outcomes or durable `manual_decision_ref` / `already_tracked_ref`, index rebuild, and docs/followups/index.md readback. `planveyor_merge_bundle_report` reads the committed receipt and blocks readiness if the snapshot block is missing, token-only, missing fresh export proof, older than the `docs_hygiene_archive` row, mismatched against manifest `created_at_utc` / `artifact.sha256` / `source_db.db_sha256` / `source_db.docs_count`, has credential-like keys/inline secret URI material, reports selected S3/MinIO access failure, checksum mismatch, restore/readback failure, tries to mark current DB migration failure as no-op, leaves new/current docs hygiene cleanup evidence only in `.tmp` stdout, accepts invalid followups file-mode targets, hides range-memory followups behind fresh file-mode import, omits retrieval metrics decision usage, or labels retrieval decision evidence as telemetry-only. `planveyor_post_merge_ready_to_push_closeout` then reports operational blockers with `why_blocked`, existing bucketized `staging_diagnostics`, `pending_owner_gate=git push`, and a safe `staging_command` or transient NUL-delimited `.tmp/planveyor_ready_to_push_closeout/<range_id>/accepted_paths.pathspec` only for dirty report-accepted paths; suspicious/unexpected/red-report blockers do not get a staging command. Exception: clean committed operational receipts generated before each receipt gate existed stay legacy-compatible historical receipts; they must not be retroactively blocked.

Backend policy:
- `git_text_export` is the current selected durable carrier and restores SQLite/FTS without the original `.tmp` DB.
- `git_whole_sqlite` remains allowed only with explicit manifest/checksum/schema/readback proof; it is currently larger and opaque.
- `s3_minio_sqlite` remains optional/hybrid: git must carry manifest/checksum/object URI metadata, credentials are never committed, and restore fails closed unless configured object access or an explicit local object file is supplied.

## Deletion (Owner)
Только после fresh archive/suggest выше Owner удаляет выбранные файлы пачкой и отдельным cleanup commit (пример):
```bash
git rm docs/plans/<...> docs/code_drafts/<...> docs/code_reviews/<...> docs/code_reviews/assets/<...>/ docs/doc_reviews/<...>
```
Если `git rm` ругается на staged изменения — привести индекс в порядок и повторить (или использовать `-f`, если осознанно).

### Followups (optional)
`docs/followups/*` удаляем **только если**:
- `**Status:** Done` в самом follow-up файле, и
- есть явный маркер `**Imported into:** ...` (заполняется triage/import шагом),
- `planveyor_followups_query cleanup-receipt --project-root ... --format json` вернул `decision=delete-ready` для этого файла,
- receipt не содержит `missing_proof_refs`, а `proof_classes` отражает accepted closure proof для terminal plan refs,
- нет “живых” ссылок на этот follow-up из канона (doc_lint/rg и receipt reverse-reference result).

Если `Imported into` нет:
- сначала прогнать triage/import (`planveyor_followups_triage --range BASE..HEAD --apply` для range-memory/range inboxes; `--file docs/followups/<fresh>.md --apply` only for a fresh inbox outside the reviewed range),
- затем снова проверить `planveyor_followups_query cleanup-receipt --project-root ... --format json`,
- затем снова проверить `planveyor_docs_hygiene_suggest --include-followups`.

## Post-delete sanity
1) Повторить strict doc_lint (канон).
2) `git diff --check -- docs` по cleanup diff.
3) `git status` должен быть чистым (кроме ожидаемых изменений).

## V2 external reconciliation

`plan.v2` terminal cleanup keeps the plan immutable: do not reconstruct or
append `plan_meta.followups_out`. The proof host is an exact current
`followups.v2` `(source_ref,item_id)` row. `open + exact proof` is a valid
`external_clean` result; stale, duplicate, source/blob or snapshot mismatch is
red and requires a fresh four-role declaration/freeze cycle, never a manual
row/terminal-plan repair. Legacy V1 rows remain compatibility-only and V2
follow-ups are not queue imports or automatic historical backfill.

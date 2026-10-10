# Follow-ups backlog — <topic>

**Date:** DD.MM.YYYY HH:MM
**Source:** <memory|post-merge audit|plan harvest|review>
**Status:** Draft | ✅ Done
**Schema version:** followups.v2

Зачем этот файл: держать список follow-ups **вне** `docs/plans/*` (планы = контракт на реализацию).
Этот backlog можно хранить под git, дополнять и позже “промоутить” отдельные пункты в полноценные dev-plans.

Правила:
- Metadata header lines are ordinary Markdown lines; do not add two-space hard-break suffixes or other raw trailing whitespace.
- Не создаём “tasks-only планы” в `docs/plans/*` (они ломают ожидания по status/pipeline и мешают `plan_lint`/роутингу).
- Прямое поручение Owner допускает независимый обычный (ordinary) plan после bounded discovery; matching open follow-up раскрывается literal `source_ref#item_id` в `Context links`. Ordinary plan не является row promotion и не разрешает automatic backlink: matching row остаётся unchanged (`status=open`, `plan=null`, null disposition fields). Если совпадений нет, не создаём искусственную row; конфликт уже активного плана требует Architect/Owner triage. Реальный plan/disposition backlink пишет только штатный promotion writer с exact proof, без ручной правки backlog. Prepare/finalize не являются предусловиями independent ordinary plan.
- Если пункт родился как `removed from active scope` / de-scoped product debt, в `why` обязателен literal source (`plan section`, `review ref` или `already tracked elsewhere`), чтобы он снова не растворился при следующем harvest.
- Schema compatibility: `current` = literal `**Schema version:** followups.v2`; explicit `followups.v1` и versionless historical backlog files остаются read-only legacy lanes; любой другой explicit value = `unsupported`.
- `**Status:** ✅ Done` + real `**Imported into:** ...` означает только `cleanup-ready` candidate. Удаление whole source file требует отдельный `cleanup-receipt` с `decision=delete-ready`; `retain` / `needs-richer-summary` остаются в git.
- Status family boundary: V2 ordinary follow-up rows accept only `open`, `promoted`, `handled`, `cancelled`; process-improvement lifecycle statuses (`triaged`, `deferred`, `rejected`) belong under `docs/process_improvements/*`.
- Если PI row требует delivery follow-up, создавай отдельный ordinary follow-up с `status=open` / `plan=null` до promote и держи backlink в PI `delivery_refs`; не копируй PI lifecycle row сюда.
- Для finding, впервые обнаруженного после terminal `Done|Superseded`, terminal plan byte-immutable. Ровно одна active V2 row в `docs/followups/*.md` является durable authority по `(source_ref,item_id)`; capture/staging/preflight receipts под `.tmp/` transient-only и не являются второй disposition authority.
- For a terminal-source row, use exact `source_ref=<terminal plan path>` (optionally with a stable anchor); `source_ref=<exact source path>` is only the compact placeholder form below, never path-similarity matching.

## Context / inputs (optional)
- RANGE (если применимо): `<base..head>`
- Related plans (filenames only; git history): `<YYMMDD_HHMM_topic.md>`
- Related reviews (filenames only; git history): `<YYMMDD_HHMM_topic.md>`
- Canon pointers: `<doc path>`

## Follow-ups (backlog)
Формат V2:
`P? [ ] <summary> — cluster=<...> — tags=<...> — to=<Planner|Architect|Coder|Owner|Reviewer|Manager> — status=<open|promoted|handled|cancelled> — plan=<docs/plans/...|null> — item_id=<stable-slug> — source_ref=<exact repo-relative source[#anchor]> — disposition_kind=<null|promoted_plan|terminal_delivery|cancelled_decision> — disposition_ref=<null|exact repo-relative ref> — disposition_commit_oid=<null|git-oid> — reason=<null|non-empty> — [legacy_row_ref=<plan_meta.followups_out[N]> — legacy_plan_sha256=<64hex> — legacy_row_sha256=<64hex>] — why: <...>`

- `cluster` должен быть из канонического enum (см. `docs/plans/README.md` → `cluster (enum; канон)`).
- `status=open` требует literal `plan=null`, `disposition_kind=null`, `disposition_ref=null`, `disposition_commit_oid=null`; это captured backlog, а не незавершённый source delivery.
- `status=promoted` требует `plan=docs/plans/*.md`, `disposition_kind=promoted_plan`, exact matching `disposition_ref`, reachable Commit A OID и non-null `reason`.
- `handled|cancelled` требуют typed disposition и commit-bound exact ref; prose, path similarity и success text не создают closure truth.
- Optional legacy bridge допускается только полным тройным carrier: exact unanchored `source_ref` на explicit `plan.v1`, `legacy_row_ref=plan_meta.followups_out[N]` и hashes exact plan bytes/one JSON row. Он read-only: не backfill-ит, не ищет summary и не меняет V1 plan; stale/missing/duplicate bridge остаётся red.
- P? [ ] <summary> — cluster=<...> — tags=<...> — to=<...> — status=open — plan=null — item_id=<stable-slug> — source_ref=<exact source path> — disposition_kind=null — disposition_ref=null — disposition_commit_oid=null — reason=null — why: <...>

## Canon updates (TODO)
- TODO `<doc>`: <что обновить> — why: <...> — to=<role>

## Notes
- <любые ограничения/оговорки/что сознательно не делали>

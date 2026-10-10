# Review: Post-merge audit — <topic>

**Date:** DD.MM.YYYY HH:MM
**Topic:** <коротко: что именно аудитим>
**Stage:** Stage 1 (post-merge docs hygiene)
**Status:** Draft | ✅ Done
**Schema version:** review.v1

Зачем этот файл: зафиксировать “что проверили и почему считаем done/partial” **без зависимости от временных** `docs/plans/*` / `docs/code_reviews/*` (которые Owner может удалить после извлечения follow-ups).

Parser-valid skeleton можно получить командой `planveyor_post_merge_receipt_skeleton post_merge_audit --out docs/reviews/<stamp>_post_merge_audit_<topic>.md`; после генерации замени fixture values на реальные audit/proof values.

Audit receipt family mapping (normalized envelope guidance):
- `schema_version`: literal header `**Schema version:**` (`review.v1`)
- `event_type`: `review.post_merge_audit`
- `ts`: literal header `**Date:**`
- `event_id`: derived from audit artifact basename + `Date`
- `trace_id`: literal only when linked plan/run receipt/post-merge gate carrier materialize-ит его explicitly; иначе держим `N/A (why=post-merge audit is a partial lineage source family)`
- `span_id`: derived from audit artifact path/basename
- `parent_span_id`: `N/A (why=post-merge audit header does not expose parent span lineage)` unless the same file literal-но anchors an upstream live blocker/ref or rerun baseline
- Schema compatibility: `current` = literal `**Schema version:** review.v1`; versionless historical audit files = `legacy`; любой другой explicit value = `unsupported`.

## Каноника (source of truth)
- <канонические доки, которые должны остаться после cleanup: declared target canon / ADR / API / Schema / Registry / Guides>

## Источники (git history; можно удалять после аудита)
Важно: чтобы не ловить `doc_lint --check-code-refs` на удалённых файлах, здесь **не** используем пути `docs/plans/...` / `docs/code_reviews/...`.

- Plans (git history):
  - `<YYMMDD_topic.md>`
- Code reviews (git history):
  - `<YYMMDD_topic.md>`
- Snapshots (обычно остаются; путь допустим):
  - `docs/snapshots/<YYYYMMDD_hhmm_role_topic>.md`
- Gate receipts (optional):
  - `<docs/reviews/*_ai_gate_*.json or N/A>`
- SATD helper output (optional, candidate-only):
  - `<created|updated|deleted table with old/new anchors when available, or N/A>`

## Rerun context (if applicable)
- Rerun mode: `incremental | full | N/A (single-pass range)`
- Baseline artifact: `<filename or N/A>`
- Closure scope: `<что именно было закрыто rerun / N/A>`
- Residual-debt extraction scope: `<что audit проверяет сверх rerun closure>`

## Range stats
- Source: `planveyor_merge_range_stats_json BASE HEAD`
- `total_commits`: <N>
- `first_parent_commits`: <N>
- `changed_files`: <N>
- `diffstat_summary`: <summary>

## Audit matrix (summary)
Рекомендуемый формат: короткие секции “A1/A2/…” с якорями в код/канон.
- Если используешь SATD helper как candidate source, фиксируй lifecycle `created|updated|deleted` и old/new anchors literally, но не подменяй этим reviewer verdict.

### A1) <item>
- Lane synthesis source: `<review artifact path>#Lane synthesis / aggregate verdict` | `UNCONFIRMED`
- source_lane: `<reviewer_code_risk | reviewer_code_contracts | synthesized>`
- lane_finding_id: `<lane finding id>` | `N/A`
- synthesis_disposition: `<no_findings | accepted | accepted_non_blocking_followup | deferred | downgraded | superseded | closed_by_same_file_rewrite | N/A>`
- canonical_ref: `<canon/follow-up pointer>` | `N/A`
- audit_status: `done | partial | missing | UNCONFIRMED`
- followup_plan: `docs/plans/<slug>.md` | `N/A`
- Blocker refs: `<review_artifact_path>#B1` | `N/A (no live blocker lineage)`
- Code anchors: `<path:line>`, `<path:line>`
- Tests/smokes: `<command or test file>`
- Docs: `<doc:line>` или `<doc path>`
- ADR: `docs/adr/<NNN-topic.md>` | `N/A`
- Status: ✅ Done | partial | missing | diverged | unknown
- Notes (optional): <что важно для понимания или для reviewer scope>

Authority mapping for current `review.v1` rows:
- `audit_status` derives from the cited live review `Lane synthesis / aggregate verdict`; it is not a second review verdict.
- `done` requires terminal green source truth (`no_findings`, `accepted`, `superseded`, `closed_by_same_file_rewrite`), no live blocker refs and `followup_plan: N/A` or explicit terminal/handled proof formatted as `done|closed|handled|terminal: <durable docs/* ref>`.
- Paths/prose that only contain `done`, `closed`, `handled` or `terminal` without that explicit proof grammar remain non-terminal.
- `accepted_non_blocking_followup`, `deferred`, `downgraded`, missing/unreadable review artifact, missing synthesis section, ambiguous `lane_finding_id` and legacy `N/A` provenance are non-terminal (`partial`, `missing` or `UNCONFIRMED`) until closure proof is cited.
- Live `#B<N>` blocker refs always forbid `audit_status=done`.
- Historical/closed/superseded blocker lineage must be explicit (`historical|closed|superseded: <durable docs/* ref>`); path/prose substrings alone do not suppress live blocker refs.

## Compact no-findings mode
По умолчанию держи `compact_mode: disabled`. Включай `enabled` только когда live review `✅ OK`, no-findings provenance и все residual truth hosts ниже explicit green/clear или `N/A (why=...)`.

- compact_mode: disabled
- review_status: `<✅ OK | Draft | ❌ blocker>`
- findings: `<no_findings | S1/S2/S3 refs>`
- live_blocker_lineage: `N/A (no live blocker lineage)` | `<review_artifact_path>#B<N>`
- role_quality_candidate: `N/A (why=no flagged role-quality candidate)` | `<flagged plan/ref>`
- process_improvements: `clear | N/A (why=...) | pending/red/missing`
- followups: `clear | N/A (why=...) | pending/red/missing`
- packetization: `clear | N/A (why=...) | pending/red/missing`
- ready_to_push: `clear | N/A (why=...) | pending/red/missing`
- docs_index_context: `clear | N/A (why=...) | pending/red/missing`
- receipt_citations: `clear | N/A (why=...) | pending/red/missing`
- producer_authority: `N/A (why=manual post-merge audit author)` | `<explicit producer/stamper carrier>`

## Role-quality findings by plan/role
- Non-flagged plans: одна summary line `not audited` с причиной отсутствия strong signal.

### RQ1) <plan filename>
- Candidate source: `<review ref or plan evidence>`
- Why in matrix: `live ❌ S1 blocker | same review rerun loop | blocker-driven follow-up | explicit blocker/current-plan bounce`
- Live review status: `❌ S1 blocker | ✅ OK (historical anchor only) | no live review artifact | N/A (no live blocker lineage)`
| Role | Verdict | Evidence |
| --- | --- | --- |
| Architect | caught in time | <plan / review evidence> |
| Planner | missed, downstream caught | <review ref + plan evidence> |
| Coder | not primary owner | <why> |
| Reviewer | evidence insufficient | <why> |
| Architect arch review | evidence insufficient | <why> |
| Censor | receipt missing | <receipt ref or why> |

## Role assessment (censor receipts, if applicable)
- Helper command: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py censor_receipts_harvest.py --plan <flagged-plan> --review-artifact <current-review> --format json` | `N/A`
- Helper summary: `receipts=<N>; complete=<N>; partial=<N>; missing=<N>; unconfirmed=<N>` | `N/A`
- Helper role-quality: `helped=<N>; missed live blocker=<N>; receipt missing=<N>; noise/no-op=<N>; UNCONFIRMED=<N>` | `N/A`
- Helper warnings/unconfirmed: `<warning or reason>` | `N/A`
- Current negative-signal policy: helper-confirmed `missed live blocker` requires exact current blocker refs/verdict plus literal live-blocker reconciliation; ambiguous current-looking prose stays `UNCONFIRMED`.
- Lint policy: current `review.v1` reports either use explicit `Receipt source: N/A (receipt missing)` + `Assessment: receipt missing`, or copied helper counters must be green (`partial=0`, `missing=0`, `unconfirmed=0`, `missed live blocker=0`, `receipt missing=0`, `UNCONFIRMED=0`).

### R1) <plan / role>
- Receipt source: `<plan evidence timestamp>` | `N/A (receipt missing)`
- Artifacts opened: `<plan>|<code draft>|<review>` | `N/A`
- Review verdict seen: `❌ S1 blocker | ✅ OK (historical anchor only) | no live review artifact | UNCONFIRMED`
- Blocker IDs considered: `<review_artifact_path>#B1` | `N/A (why)`
- Role-owned finding: `<one-line>` | `N/A`
- Reconciliation: `live blocker belongs here | live blocker does not belong here | historical anchor only | no live blocker | UNCONFIRMED`
- Final censor verdict: `NO FINDINGS | FOUND GAP | OK | receipt missing | UNCONFIRMED`
- Assessment: `helped | missed live blocker | receipt missing | noise/no-op | UNCONFIRMED`
- Deadlock addendum: `Loop signal=...; Root cause class=...; Why previous rerun did not break the loop=...; Extraordinary action=...` | `N/A`

## Post-merge audit receipt citations
- Audit matrix: `docs/reviews/<this-file>.md#audit-matrix-summary`.
- Role-quality: `Role assessment (censor receipts, if applicable)`.
- Follow-up harvest triage/import receipt: `<harvest-report>#follow-up-harvest-triageimport-receipt` | `N/A (why=no harvest carrier for this audit)`.
- Process-improvement promotion decisions: `<harvest-report>#process-improvement-promotion-decisions` | `N/A (why=no mature process-improvement rows)`.
- Docs retrieval metrics receipt: `<harvest-report>#docs-retrieval-metrics-receipt`; summary `query_total=<int>`, `evaluated_total=<int>`, `outcome_evaluated_rate=<rate>`, `read_log_status=<present|missing>`, `read_events_total=<int>`, `read_open_rate=<rate>`, `used_for_decision=<true|false>`, `accepted_no_op_reason=<reason>` | `N/A (why=no docs retrieval metrics trigger)`.
- Docs index/context: `docs_index_context`; `planveyor_docs_index_build all`; `docs_context_check corpus=plans covered=0 uncovered=0`; `docs_context_check corpus=followups covered=0 uncovered=0`; closed no-op allowed: `not_applicable_no_docs_or_followups_delta|not_applicable_empty_docs_corpus|not_applicable_bootstrap_index_unavailable`.
- Packetization: `step:packetization_gate` -> `N/A (why=no shared canon delta)` | `<packetization-report>#machine-readable-json`; summary `schema_version=packetization_gate.v1`, `blocking_count=<N>`, `packet_status=<open|imported|...>`, `target_adoption_state=<awaiting-target-import|awaiting-target-outcome|adopted|...>`.
- SATD/candidate rows: `N/A (why=no SATD candidate rows)` | `<satd table section>`.

## Post-merge visual sanity
- Final review visual readback: `not_applicable | green | red | ambiguous`
- Final review visual source: `<current review artifact>#Визуальные-доказательства | N/A (why=no runtime UI lane)`
- Current-review asset refs: `<one exact current-review asset per mandatory mode | N/A (why=no runtime UI lane)>`
- Source scenarios: `<affected plan anchors>` + `docs/smoke_visual.md#<section>`
- Evidence sources: `<review-file>#Visual evidence`, `assets/<REVIEW_BASENAME>/<file>.png`
- Matrix:
  - `<scenario>` → `mode=<declared-mode|default>` → `evidence=<path>` → `status=done|partial|missing|UNCONFIRMED`

Для runtime UI `audit_status=done` не переопределяет финальный review truth: `red` или `ambiguous` readback остаётся audit blocker. Audit не переснимает UI и не принимает `.tmp/**`, historical/другой review basename, path traversal или symlink как closing assets; он перечитывает current review, exact comparator/human commands и current-review per-mode assets.

## Follow-ups
- Backlog (список, не plan): `docs/followups/<YYMMDD_HHMM_followups_topic>.md` (опционально; можно держать прямо здесь)
- Если follow-up **промоутнули** в dev-plan — указать `docs/plans/...` (и оставить ссылку на plan).
- Если follow-up зафиксирован в канон вместо dev-plan — указать где именно.
- Если source plan literal-но вынес item из active scope, но в backlog/promoted plan/explicit owner rejection его нет, это фиксируем здесь как `lost follow-up during harvest/promotion`, а не как пустое `не создавал`.

## Примечания
- <дата-аудита, ограничения, что сознательно НЕ проверяли>

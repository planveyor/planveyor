# Review: Plan harvest — range <base7>..<head7>

**Date:** DD.MM.YYYY HH:MM
**BASE:** <sha>
**HEAD:** <sha|HEAD>
**Status:** Draft | ✅ Done
**Schema version:** review.v1

Зачем этот файл: вытащить из plan’ов и ревью “остаточные” follow-ups / canon updates / key decisions так, чтобы после cleanup можно было безопасно удалить временные `docs/plans/*` и `docs/*reviews/*` без потери смысла.

Важно:
- этот файл **остаётся** (или его можно удалить уже после того, как follow-ups и канон обновлены);
- **не** вставляй ссылки путями на удаляемые файлы (`docs/plans/...`, `docs/code_reviews/...`, `docs/doc_reviews/...`), чтобы не ловить `doc_lint --check-code-refs` после `git rm`. Пиши только имена файлов (git history) или указывай канонику/снапшоты.
- Schema compatibility: `current` = literal `**Schema version:** review.v1`; versionless historical harvest reports = `legacy`; любой другой explicit value = `unsupported`.
- Parser-valid skeleton можно получить командой `planveyor_post_merge_receipt_skeleton plan_harvest --out docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md`; после генерации замени fixture values на реальные range/proof values.

## Источники (git history; может быть удалено после harvest)
- Plans (filenames only):
  - `<YYMMDD_HHMM_topic.md>`
- Review artifacts (filenames only):
  - `<YYMMDD_HHMM_topic.md>`

## Rerun context (if applicable)
- Rerun mode: `incremental | full | N/A (single-pass range)`
- Baseline artifact: `<filename or N/A>`
- Closure scope: `<какой blocker scope закрыл rerun / N/A>`
- Reused evidence / trusted unaffected surfaces: `<что наследуем от baseline и почему / N/A>`

## Canon updates (done / TODO)
- ✅ `<doc>`: <что обновили> — why: <1 строка>
- TODO `<doc>`: <что ещё надо обновить> — why: <1 строка> (to=<role>)

## Key decisions / constraints (куда закрепили)
- `AGENTS.md`: <что добавили> (pointers)
- `docs/followups/index.md`: <что добавили> (pointers)
- `docs/roadmap.md`: <что добавили> (pointers)

## ADR candidates / durable decisions
- `docs/adr/<NNN-topic.md>` — status=`proposed|accepted|superseded` — why: <почему это durable architectural decision>
- `N/A` — why: <если все решения tactical и не переживают сам plan/review bundle>

## Process-improvement promotion decisions
Источник: `docs/process_improvements/promotion_surface.md`. Заполняй одну строку на каждый mature candidate; mature row без terminal decision блокирует `✅ Done`.

Формат: `entry_id | decision | reason | execution_kind | execution_ref | owner_or_next_step`

- `<PI-###>` | `promoted` | `<why>` | `<plan|helper|canon_doc|rollout_packet|umbrella_wave|external_ref>` | `<durable execution carrier>` | `N/A (why=already materialized)`
- `<PI-###>` | `deferred` | `<reason>` | `N/A` | `N/A` | `<owner/next-step/revisit condition>`
- `<PI-###>` | `rejected` | `<reason>` | `N/A` | `N/A` | `N/A (why=rejected)`

Правила:
- `promoted` требует уже materialized `execution_kind` + `execution_ref`; harvest не создаёт execution carrier implicit.
- `execution_kind` для `promoted` использует canonical values из process-improvements family: `plan | helper | canon_doc | rollout_packet | umbrella_wave | external_ref`.
- `deferred` требует `reason` + owner/next-step или revisit condition; `rejected` требует `reason`.
- Exact heading `Process improvements` зарезервирован для raw memory-finalize suggestions; terminal harvest decisions живут только в `Process-improvement promotion decisions`.

## Follow-ups backlog (created)
- `docs/followups/<YYMMDD_HHMM_followups_range_<base7>_<head7>.md>` (если создавали)
- Если follow-ups нет: `NO FOLLOWUPS` допустим только с явной причиной `handled in follow-up`, `already tracked elsewhere`, `canon sync closed it` или `no remaining actionable debt after full-wave harvest`.

## Follow-ups (extracted; без дублей)
Формат: `P? <topic> — to=<Planner|Architect|Coder|Owner> — status=<created|handled|needs_owner|UNCONFIRMED> — why`

- Важный guard: если source plan literal-но says `removed from active scope` / `intentionally removed` / `если по-прежнему нужно`, такой item не имеет права пропасть. Здесь должен быть либо backlog/promoted entry, либо `handled` с pointer'ом на already-tracked / explicit owner rejection.
- Если ordinary followups пусты, это означает только пустой harvest file-lane; если range triage later/apply даёт non-zero counts, authoritative explanation живёт в operational receipt `followups_lane_reconciliation`.
- P? `<topic>` — to=Planner — status=created — why: <...>
- P? `<topic>` — to=Architect — status=handled — why: already tracked in `docs/followups/<...>.md` (no duplicate created)

## Follow-up harvest triage/import receipt
- `harvest_file_followups_result`: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.
- `harvest_file_followups_count`: 0
- Для outcome `created/imported` замени result literal на `created/imported`, а count literal — на положительное точное число созданных/imported file-followups.
- `planveyor_followups_triage` (idempotency): append_new=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.
- `planveyor_followups_triage`: `N/A (why=template; fill dry-run/apply/idempotency result for concrete harvest)`.

## Packetization handoff receipt
- `step:packetization_gate`: `N/A (why=no shared canon delta)` | `docs/reviews/<stamp>_packetization_gate_range_<base7>_<head7>.md`; when structural JSON exists, expected `packetization_gate.schema_version=packetization_gate.v1`.

## Golden Path lane receipt
- `lane=tooling_process`; `active carrier="$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-plan-harvest"`; `outcome=<updated | no changes needed (why) | follow-up created | deferred (why)>`.

## Docs retrieval metrics receipt

| repo | repo_role | query_log_status | query_total | with_hits | zero_hits | hit_rate | warnings_total | errors_total | with_event_id | evaluated_total | outcome_evaluated_rate | outcome_used | outcome_partial | outcome_miss | outcome_noise | not_evaluated_total | read_log_status | read_events_total | read_open_rate | unique_paths | used_for_decision | low_coverage_triage | follow_up_ref | accepted_no_op_reason | source_command |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| `<repo>` | source | missing | 0 | 0 | 0 | 0.0% | 0 | 0 | 0 | 0 | 100.0% | 0 | 0 | 0 | 0 | 0 | missing | 0 | 100.0% | 0 | false | not_required | N/A | not_used_for_decision | scripts/docs_retrieve_metrics.py --format json |

## Runner quality range receipt

Заполняй, если range содержит `runner_quality` rows или evidence использования external/non-default runner'ов (`claude`, future non-Codex). Для cleanup-safe refs предпочитай filenames / durable refs, а не пути на temporary files, которые будут удалены.

| plan | role_lane | runner_id | model | task_class | row_status | score_summary | required_frontier_intervention | missed_blockers | useful_for_future | follow_up_ref | source_ref |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<plan filename>` | `<coder|reviewer_code_risk|...>` | `<claude|unknown|N/A>` | `<model|N/A>` | `<docs-only|process-helper|runtime-code|review-risk|review-contracts|visual|other>` | `<captured|missing|not_applicable>` | `<adherence=2 evidence=3 fix=2 or N/A (why)>` | `<none|minor|major|blocker|N/A>` | `<0|1|2|3+|unknown|N/A>` | `<yes|conditional|no|unknown|N/A>` | `<N/A|follow-up ref|accepted no-op reason>` | `<review filename#runner_quality|plan evidence ref|N/A>` |

Summary totals:
- by runner_id/model/role_lane/task_class: `<counts or N/A (why=no rows)>`
- by row_status: `<captured=0 missing=0 not_applicable=0>`
- weak/frontier intervention cases: `<refs or N/A>`

## Canon/follow-up summary
- canon_updates=0; followups=0.

## Примечания / cleanup readiness
- <что можно удалять; что нельзя удалять; что ещё проверить перед cleanup>

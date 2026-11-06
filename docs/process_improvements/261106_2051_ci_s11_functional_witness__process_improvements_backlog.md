# Process improvements backlog — 261106 2051 ci s11 functional witness

**Date:** 2026-11-07 01:35 +0300
**Source ref:** `docs/plans/261106_2051_ci_s11_functional_witness.md`
**Status:** Draft

Зачем этот файл: держать raw process-improvement suggestions отдельно от обычных follow-ups и канонических doc edits.

Правила:
- Truth surface = блоки `### PI-...` ниже; derived surfaces `index.md`, `deferred.md`, `promotion_surface.md` пересобираются helper'ом.
- Literal no-op `NO PROCESS IMPROVEMENTS — why: <reason_code>` не materialize-ится как backlog row.
- Wave 1 ограничен `collect + triage`: promotion paths фиксируются literal fields, но не auto-promote логикой.
- Owner-facing `urgency` хранится в existing `priority`; отдельное поле `urgency` не добавляется.
- Mature rows фиксируют non-`P?` `priority`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, `execution_kind`, `execution_ref`, `delivery_refs`, `handled_ref`, `promoted_at`, `handled_at`.

## Suggestions (truth)
### PI-001
- status: `open`
- priority: `P?`
- role: `Architect`
- owner: `Architect`
- promotion_class: `prompt_change`
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
- trigger_ref: `docs/plans/261106_2051_ci_s11_functional_witness.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261106_2051_ci_s11_functional_witness.md`
- symptom: `Date-only prefix Planner CENSOR receipt не прошёл historical-row detector; source-plan reference и child wording дали child-graph drift, handoff был отозван и потребовал отдельного Owner-authorized prefix recovery.`
- process_gap: `Planner CENSOR требует structured labels и append-only receipt, но его примеры не фиксируют полный timestamp prefix, необходимый INLINE_TIMESTAMP_RE для historical-row classification.`
- suggested_fix: `В docs/tools/prompts/planner_censor.md явно задать prefix YYYY-MM-DD HH:MM с timezone при наличии, показать полный пример и требовать проверки prefix до единственной append-записи; сохранить post-write lint/exact selector, запрет same-ID repair и неизменность failed historical receipts.`
- created_at: `2026-11-07 01:30 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Coder`
- owner: `Architect`
- promotion_class: `canon_update`
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
- trigger_ref: `docs/plans/261106_2051_ci_s11_functional_witness.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261106_2051_ci_s11_functional_witness.md`
- symptom: `После успешного первого F source review обнаружил гонку: background holder мог опубликовать ready раньше завершения записи caller PID, поэтому немедленное чтение PID допускало ложный FAIL.`
- process_gap: `Declared docs/testing_runbook.md не описывает проверку совместной готовности нескольких независимо публикуемых artifacts; единичный успешный runtime run не исключает source-order race.`
- suggested_fix: `Через отдельный live non-terminal carrier добавить краткое правило: ждать одновременно все необходимые artifacts и полноту payload в одном существующем finite budget, сохранять fail-closed проверки процесса и identity; не добавлять фиксированный sleep, не увеличивать timeout и не считать existence достаточным proof.`
- created_at: `2026-11-07 01:35 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

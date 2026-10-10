# Process improvements backlog — 261007 1935 owner task sibling flow

**Date:** 2026-10-09 00:08 +0300
**Source ref:** `docs/plans/261007_1935_owner_task_sibling_flow.md`
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
- owner: `Manager`
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
- trigger_ref: `docs/plans/261007_1935_owner_task_sibling_flow.md`
- source_ref: `docs/plans/261007_1935_owner_task_sibling_flow.md`
- symptom: `После четырёх green ordinary V2 binds freeze-ordinary-v2 отказал с followup_ordinary_v2_bound_family_invalid: Architect и Coder указали разные carrier для двух самостоятельных findings; immutable bound declarations уже нельзя исправить на месте.`
- process_gap: `Prompts закрепляют один допустимый carrier для ordinary family, но не задают передачу выбранного followup_path между ролями до их immutable binds; локально валидные independent submissions обнаруживают несовместимость только на общем freeze.`
- suggested_fix: `В docs/tools/prompts/manager_collab_pipeline.md и четырёх ordinary docs-finalize followups prompts явно закрепить координацию пути: первая роль с findings выбирает один fresh carrier, последующие роли читают его literal followup_path из текущего helper-owned bound proof и используют тот же путь для своих новых самостоятельных items; перед новым row-bearing submission сверять единственность carrier. Сохранить реальные независимые role submissions, distinct item_id, sole writer и действующий one-carrier отказ.`
- created_at: `2026-10-09 00:08 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

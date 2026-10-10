# Process improvements backlog — release

**Date:** N/A (why=release continuity carrier consolidates unchanged open rows)
**Source ref:** `docs/release_backlog.md#process-improvements`
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
- role: `Coder`
- owner: `Coder`
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
- trigger_ref: `docs/release_backlog.md#pi1`
- source_ref: `docs/release_backlog.md#process-improvements`
- symptom: `Review finding R1 выявил, что exact-command gate покрывал четыре команды, хотя Acceptance требовал пять и не проверял `planveyor_planpath`.`
- process_gap: `AC-to-test checklist допускает групповой command readback без one-to-one сверки literal commands и assertions.`
- suggested_fix: `В Coder status-driven prompt потребовать literal inventory каждой команды из Acceptance и code draft с отдельной assertion до `Ready for Review`.`
- created_at: `2026-09-15 13:23 MSK`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Planner`
- owner: `Planner`
- promotion_class: `helper_change`
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
- trigger_ref: `docs/release_backlog.md#pi2`
- source_ref: `docs/release_backlog.md#process-improvements`
- symptom: `При `Ready for Planner` `plan_lint` выбрал `docs/code_drafts/README.md` из `Context links` и выдал advisory про отсутствующий `code_draft_meta`, хотя same-stem draft ещё закономерно не создан.`
- process_gap: `Общий selector code-draft refs не отличает contract README/template от live draft carrier до Planner finalize.`
- suggested_fix: `Ограничить primary-draft selection live ссылкой из `Code draft(s)` либо исключить `README.md` и `_template.md` contract refs из advisory candidate discovery, сохранив поддержку явных nonstandard draft refs.`
- created_at: `2026-09-15 13:27 MSK`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
- status: `open`
- priority: `P?`
- role: `Architect`
- owner: `Manager`
- promotion_class: `routing_change`
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
- trigger_ref: `docs/release_backlog.md#pi3`
- source_ref: `docs/release_backlog.md#process-improvements`
- symptom: `В C05 промежуточная строка `Mode: manager-custom-pipeline` активировала custom-only semantic route, хотя review фактически выполнялся через native agents; до commit строку исправили на `reuse-thread`, `custom_role_step` не выполнялся и synthetic receipt не создавался.`
- process_gap: `Native Manager route не требует до первого review dispatch явной сверки plan-declared `Mode` с фактическим transport и наличием соответствующего helper proof для custom-only semantics.`
- suggested_fix: `Добавить в Manager pre-dispatch routing guard сверку actual invocation mode с `## Verification rerun / exec handoff`; при native dispatch требовать factual `reuse-thread`, а при declared custom mode без фактического custom invocation остановиться до role-send и запретить синтез отсутствующего receipt.`
- created_at: `2026-09-22 21:13 MSK`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

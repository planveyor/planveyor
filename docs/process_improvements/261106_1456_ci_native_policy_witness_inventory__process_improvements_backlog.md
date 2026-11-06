# Process improvements backlog — 261106 1456 ci native policy witness inventory

**Date:** 2026-11-06 18:39 +0300
**Source ref:** `docs/plans/261106_1456_ci_native_policy_witness_inventory.md`
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
- trigger_ref: `docs/plans/261106_1456_ci_native_policy_witness_inventory.md`
- source_ref: `docs/plans/261106_1456_ci_native_policy_witness_inventory.md`
- symptom: `Simulated Done lint отказал из-за открытого Post-merge checklist, куда попали Root p0 после local commit и последующая Manager docs/followups/PI семья.`
- process_gap: `План смешал обязательные условия semantic Done с внешними postcommit obligations; это создало циклическую зависимость, хотя порядок исполнения уже был принят.`
- suggested_fix: `В docs/plans/_template.md добавить bounded пример отдельного оформления pending postcommit obligations и проверки их порядка перед handoff; сохранить строгий Done guard и запрет отмечать ещё не выполненные проверки пройденными.`
- created_at: `2026-11-06 18:30 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Planner`
- owner: `Planner`
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
- trigger_ref: `docs/plans/261106_1456_ci_native_policy_witness_inventory.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261106_1456_ci_native_policy_witness_inventory.md`
- symptom: `Literal docs/registry внутри N/A-пояснения Synchronous doc/registry targets был распознан как обязательный target; Planner получил lint rc1 при единственном разрешённом .py target.`
- process_gap: `Planner-facing documentation не показывает, как отделять N/A rationale от path inventory; нейтральное пояснение потребовало дополнительного correction cycle.`
- suggested_fix: `Через отдельный live carrier добавить в docs/plans/README.md и docs/plans/_template.md короткий пример N/A без path-like псевдопутей; реальные context refs размещать в Source docs used или Context links. Сохранить strict target parity и hard gate.`
- created_at: `2026-11-06 18:39 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

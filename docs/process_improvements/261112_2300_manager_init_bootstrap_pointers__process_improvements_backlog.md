# Process improvements backlog — 261112 2300 manager init bootstrap pointers

**Date:** 2026-11-13 04:23 +0300
**Source ref:** `docs/plans/261112_2300_manager_init_bootstrap_pointers.md`
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
- trigger_ref: `docs/plans/261112_2300_manager_init_bootstrap_pointers.md`
- source_ref: `docs/plans/261112_2300_manager_init_bootstrap_pointers.md`
- symptom: `На Planner finalize попытка передать literal --root в planveyor_doc_lint проверила canonical roots pinned runtime; planveyor_runtime_py doc_lint.py оказался неподдерживаемым. Scoped source proof потребовал отдельного уточнения Manager.`
- process_gap: `Self-Planveyor runbook не объясняет явно проверку текущего source checkout при внешнем runtime и отсутствие forwarding произвольных --root у planveyor_doc_lint.`
- suggested_fix: `Через отдельный live plan уточнить docs/playbooks/doc_lint.md: показать scoped current-checkout validation выбранным PYBIN через scripts/doc_lint.py, различить strict source refs и lifecycle hygiene; сохранить oracle/state/bundle helpers во внешнем facade. Поведение helpers не менять.`
- created_at: `2026-11-13 04:19 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Planner`
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
- trigger_ref: `docs/plans/261112_2300_manager_init_bootstrap_pointers.md#planner-suggestions`
- source_ref: `docs/plans/261112_2300_manager_init_bootstrap_pointers.md`
- symptom: `При детализации регистрации нового теста bare --check первоначально считался доказательством полноты contracts-b; чтение runner показало, что ci_composition включается только при переданном --ci-profile.`
- process_gap: `Verify runbook описывает partition и subset ID validation, но недостаточно явно отличает их от проверки полноты policy composition.`
- suggested_fix: `Через отдельный live plan уточнить docs/tools/verify_suite.md и русскую пару: после добавления теста в policy module применять --check --ci-profile fast или full; явно указать, что bare --check не доказывает полноту contracts-b. Runner и manifest policy не менять.`
- created_at: `2026-11-13 04:23 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

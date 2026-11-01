# Process improvements backlog — 261101 0052 ci test expectations rebuild

**Date:** 2026-11-01 05:05 +0300
**Source ref:** `docs/plans/261101_0052_ci_test_expectations_rebuild.md`
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
- trigger_ref: `docs/plans/261101_0052_ci_test_expectations_rebuild.md#problem`
- source_ref: `docs/plans/261101_0052_ci_test_expectations_rebuild.md`
- symptom: `Шесть тестов зависели от строкового имени Python executable, один dashboard test — от часового пояса машины; успешный rc отдельно требовал проверки unittest summary.`
- process_gap: `Существующий verify-suite guide описывает границы платформы и aggregate proof, но не содержит кратких примеров этих CI portability pitfalls.`
- suggested_fix: `Через отдельный live non-terminal carrier добавить в docs/tools/verify_suite.md и docs/tools/verify_suite.ru.md памятку: сравнивать executable через samefile с positive alias и negative foreign-file controls; задавать TZ только дочернему процессу и проверять сохранность parent TZ; фиксировать actual rc, Ran count и zero skips/errors/failures. Сохранить действующие support policy, deadlines и границы scoped/full/hosted proof.`
- created_at: `2026-11-01 05:05 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

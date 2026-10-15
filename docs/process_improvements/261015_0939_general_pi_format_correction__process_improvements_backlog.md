# Process improvements backlog — 261015 0939 general pi format correction

**Date:** 2026-10-15 18:35 +0300
**Source ref:** `docs/plans/261015_0939_general_pi_format_correction.md`
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
- trigger_ref: `docs/plans/261015_0939_general_pi_format_correction.md#evidence`
- source_ref: `docs/plans/261015_0939_general_pi_format_correction.md`
- symptom: `Исходный Q3 candidate subprocess завершился TimeoutExpired при timeout=120; fixture была удалена, terminal native outcome не получен, причина осталась UNKNOWN. Последующий полный GREEN её не объяснил.`
- process_gap: `Раздел If it warns or fails в docs/tools/verify_suite.md не описывает минимальное evidence для timeout в disposable fixture и границу между текущим successful proof и объяснением исторического отказа.`
- suggested_fix: `Через отдельный live non-terminal carrier добавить краткое правило: до cleanup сохранять prior command trace, argv, elapsed/deadline, candidate/runtime identity и доступные partial stdout/stderr без потери raw bytes; помечать результат nonterminal без выдуманного rc, сохранять исходную попытку и не объявлять последующий GREEN объяснением причины timeout. Правило не разрешает автоматический повтор или увеличение timeout.`
- created_at: `2026-10-15 18:31 +0300`
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
- trigger_ref: `docs/plans/261015_0939_general_pi_format_correction.md`
- source_ref: `docs/plans/261015_0939_general_pi_format_correction.md`
- symptom: `В Q2 delivery guard воспринял фразу docs/file как отсутствующий путь; потребовался same-contract возврат для лексической правки без изменения поведения.`
- process_gap: `Planner handoff не выделяет проверку похожих на пути сокращений в обычной прозе доставляемых prompts; plan/bundle preflight не обнаружил эту ошибку.`
- suggested_fix: `Через отдельный live non-terminal carrier добавить краткий Planner check в docs/code_drafts/_template.md и docs/plans/README.md: использовать обычную прозу либо точный допустимый путь и выполнять существующий delivery/reference gate перед долгими runtime fixtures; не ослаблять regex, allowlist или source/copy parity.`
- created_at: `2026-10-15 18:35 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

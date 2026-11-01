# Process improvements backlog — 261101 1252 ci runtime timing diagnostics

**Date:** 2026-11-01 20:10 +0300
**Source ref:** `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md`
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
- trigger_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md`
- symptom: `После успешных scoped document checks и untracked hygiene проверок indexed diff check обнаружил лишнюю пустую строку в EOF нового review; исправление потребовалось на Architect closeout.`
- process_gap: `Существующая инструкция Reviewer явно требует проверять untracked files на trailing whitespace и merge markers, но не на лишние пустые строки в EOF; tracked-only diff check новые файлы не покрывает.`
- suggested_fix: `Через отдельный live non-terminal carrier дополнить docs/tools/prompts/reviewer_status_driven.md проверкой EOF для каждого нового Markdown-файла в exact bundle до final handoff. Использовать существующую exact-path byte проверку без staging со стороны Reviewer; сохранить обязательный итоговый git diff --check.`
- created_at: `2026-11-01 20:00 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Coder`
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
- trigger_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md`
- symptom: `В Coder CENSOR вспомогательный checker завершился rc=1 на TODO/TBD/UNCONFIRMED в собственной Evidence-записи о завершённом отрицательном поиске; открытых placeholders не было.`
- process_gap: `Completion/CENSOR guidance требует закрыть маркеры, но не поясняет обработку их упоминаний в описании уже выполненной проверки.`
- suggested_fix: `Через отдельный live non-terminal carrier уточнить оба Coder prompts: оценивать контекст каждого совпадения в Tests/Commands/Evidence; описания завершённых проверок сохранять как evidence, реальные незаполненные пункты оставлять blockers. Сохранить все обязательные gates.`
- created_at: `2026-11-01 20:05 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
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
- trigger_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md#planner-qa`
- source_ref: `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md`
- symptom: `Planner prerequisite остановился на bare login Python 3.15.2 при выбранном native Python 3.12.14; явная передача PYBIN до login shell воспроизвела 3.12.14/samefile=true без изменения HOME/config/runtime.`
- process_gap: `Launch guide сообщает о передаче PYBIN ролям, но пример prerequisite не показывает явное наследование этой переменной; parent PATH или вызов выбранного executable можно ошибочно принять за эквивалентный envelope.`
- suggested_fix: `Через отдельный live non-terminal carrier уточнить docs/guides/launch-and-role-modes.md, его русскую версию и docs/code_drafts/_template.md: показать portable supply/export выбранного PYBIN до nested login shell, outer login:false для соответствующего tool route и bare-python version/samefile/TMPDIR readback. Использовать declared launch inputs без private paths; сохранить prerequisite, hold-on-failure и запрет автоматического environment repair. При triage сверить с существующим launch-preflight PI-003 плана 261015_2304, сохранив конкретный inheritance case.`
- created_at: `2026-11-01 20:10 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

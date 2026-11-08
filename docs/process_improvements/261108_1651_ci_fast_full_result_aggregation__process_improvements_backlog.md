# Process improvements backlog — 261108 1651 ci fast full result aggregation

**Date:** 2026-11-08 22:44 +0300
**Source ref:** `docs/plans/261108_1651_ci_fast_full_result_aggregation.md`
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
- trigger_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md`
- symptom: `Первый собственный read-only audit сохранённых4+2 proofs завершился rc1 из-за ожидания одинакового verbose unittest label на Python3.10 и3.12; исходные процессы были22/OK с четырьмя rc0, исправленный reader подтвердил их без повторного исполнения.`
- process_gap: `docs/testing_runbook.md задаёт выбор declared harness, но не отделяет стабильные execution facts от зависящего от версии текстового представления и ошибок отдельного proof reader.`
- suggested_fix: `Через отдельный live non-terminal carrier добавить в docs/testing_runbook.md правило проверки saved proofs: учитывать actual Python и формат исходных данных, отдельно сверять original child/tee/final rc, Ran count и skips/errors/failures; при наличии machine JSON использовать его identity/accounting fields. Ошибку parser квалифицировать отдельно, сохраняя raw evidence, без повторного запуска bodies или переписывания исходного outcome.`
- created_at: `2026-11-08 22:31 +0300`
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
- trigger_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md`
- symptom: `После первого Ready for Review operative Problem ещё описывал baseline workflow как текущий, а source-binding/handoff prose называл выполненные checks будущими; Coder CENSOR исправил wording при неизменных implementation hashes и уже spent4+2.`
- process_gap: `Primary completion требует общего reviewer-closeability self-check, но не перечисляет явно baseline/planned/actual аудит Problem, Source binding, Commands и Verification handoff; отдельный stale-live audit подробнее описан в CENSOR для route-acceptance scenarios.`
- suggested_fix: `Через отдельный live non-terminal carrier дополнить existing Coder primary completion короткой памяткой проверить эти четыре секции: явно различать baseline, planned и actual, отделять исполненный validation recipe от оставшегося allowance, сохранять historical Evidence append-only. Не добавлять новый gate, helper или автоматический повтор tests.`
- created_at: `2026-11-08 22:38 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
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
- trigger_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261108_1651_ci_fast_full_result_aggregation.md`
- symptom: `Planner CENSOR обнаружил, что новый profile matrix выполняет canonical imports, хотя preparation job ранее запускал structural-only command и не имел явно указанных prerequisites до discovery.`
- process_gap: `Existing reviewability preconditions не требуют явно сверить зависимости каждого вызывающего job при переходе команды от structural parsing к imports/discovery; подготовленное окружение другого job можно ошибочно считать достаточным.`
- suggested_fix: `Через отдельный live non-terminal carrier дополнить существующий preconditions / seed-discovery в docs/code_drafts/_template.md короткой проверкой: для каждого caller/job назвать характер команды и необходимые interpreter/dependencies/setup до первого import. Не добавлять новый gate, helper или повтор tests.`
- created_at: `2026-11-08 22:44 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

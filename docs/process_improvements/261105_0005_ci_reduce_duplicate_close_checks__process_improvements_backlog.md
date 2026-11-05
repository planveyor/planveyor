# Process improvements backlog — 261105 0005 ci reduce duplicate close checks

**Date:** 2026-11-05 11:33 +0300
**Source ref:** `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md`
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
- trigger_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md`
- symptom: `Planner primary ошибочно подразумевал обновление provenance header после успешного вызова planveyor_plan_provenance_stamp; Planner CENSOR обнаружил прежний header и материализовал полученный carrier.`
- process_gap: `Канонический список helper surfaces не поясняет явно, что stamp только выводит Markdown и сам не изменяет plan или draft; успешный renderer можно ошибочно принять за доказательство записи.`
- suggested_fix: `Через отдельный live non-terminal carrier уточнить docs/plans/README.md и provenance bootstrap в docs/roles/architect.md: stamp является renderer; при разрешённом restamp роль явно записывает helper-derived carrier в разрешённые файлы и проверяет фактические bytes перед evidence-заявлением об обновлении.`
- created_at: `2026-11-05 11:14 +0300`
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
- trigger_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md#commands`
- source_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md`
- symptom: `Targeted proof занял 2347.016 s; p4v_record показывал сохранённые streams после завершения child, поэтому для промежуточных сообщений пришлось отдельно собирать read-only просмотр timing rows.`
- process_gap: `Recording contract сохраняет actual rc и streams, но не задаёт готовую bounded команду progress readback длительного исполнения.`
- suggested_fix: `Через отдельный live non-terminal carrier документировать в docs/plans/README.md переносимый просмотр уже записанных terminal timing rows и текущей outer scenario identity. Явно оставить progress диагностическим: отсутствие новых rows не означает timeout или success; actual child rc, запрет автоматического retry и transient retention сохраняются.`
- created_at: `2026-11-05 11:24 +0300`
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
- trigger_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md`
- symptom: `До Planner CENSOR recording prelude не проверял результат записи status; последующий return мог скрыть ошибку записи при child rc0.`
- process_gap: `Общий контракт Tests / Commands / Evidence не закрепляет проверку успешности записи собственного recording status.`
- suggested_fix: `Через отдельный live non-terminal carrier дополнить docs/plans/README.md: ошибка записи recording status останавливает proof; child/tee/final rc сохраняются раздельно, успешный child не перекрывает ошибку записи и не разрешает автоматический retry.`
- created_at: `2026-11-05 11:33 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

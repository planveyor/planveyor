# Process improvements backlog — 261018 2230 review scope closeout

**Date:** 2026-10-19 07:46 +0300
**Source ref:** `docs/plans/261018_2230_review_scope_closeout.md`
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
- trigger_ref: `docs/plans/261018_2230_review_scope_closeout.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261018_2230_review_scope_closeout.md`
- symptom: `Simulated-Done lint остановился rc1 на четырёх Post-merge checkbox, включавших будущие commit, capture, terminal docs-closeout и continuity; потребовалась correction020.`
- process_gap: `План смешал обязательства semantic materialization, subsequent native delivery и cleanup после merge в main.`
- suggested_fix: `Через отдельный live carrier добавить в docs/plans/_template.md и Copier counterpart пример раздельных фаз: semantic Done после exact commit, обязательный subsequent delivery в Close-out routing, Post-merge gate только для применимого merge/cleanup. Сохранить aggregate DoD и Owner-only deletion boundary.`
- created_at: `2026-10-19 07:34 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
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
- trigger_ref: `docs/plans/261018_2230_review_scope_closeout.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261018_2230_review_scope_closeout.md`
- symptom: `Process cap был ошибочно привязан к Date.now до ожидающего approval; координатор отменил ещё не одобренный request после292.8 с.`
- process_gap: `Общая verification guidance не задаёт отдельные clocks для approval waiting и actual process, а также полный journal readback после разрешённого запуска.`
- suggested_fix: `Через отдельный live carrier описать в docs/tools/verify_suite.md существующий journal protocol: cap от launch-side start после approval, fast polling, отдельные wrapper/native rc, обязательные полные cmd/out/err/rc, раздельные real и conservative charge. Waiting исключать, исходные failed/UNKNOWN observations сохранять, автоматические повторы не разрешать.`
- created_at: `2026-10-19 07:34 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
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
- trigger_ref: `docs/plans/261018_2230_review_scope_closeout.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261018_2230_review_scope_closeout.md`
- symptom: `Контекстная Evidence-запись со словом CENSOR внутри скобочного role tag была распознана как malformed receipt; final harvest вернул rc2 и UNCONFIRMED при structurally complete выбранной квитанции. Потребовались отдельные correction017 и continuation018.`
- process_gap: `Reserved-marker guidance показывает точный canonical tag, но не объясняет, что CENSOR_TAG_RE распознаёт более широкий класс скобочных tags со словом CENSOR.`
- suggested_fix: `Через отдельный live carrier уточнить Coder CENSOR prompt: контекстная запись использует простой tag (Coder), пояснения располагаются после него; скобочные tags со словом CENSOR зарезервированы для настоящих structured receipts. Сохранить strict harvest, append-only history и запрет автоматического replacement.`
- created_at: `2026-10-19 07:39 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-004
- status: `open`
- priority: `P?`
- role: `Reviewer`
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
- trigger_ref: `docs/code_reviews/261018_2230_review_scope_closeout.md#exact-bundle-hygiene`
- source_ref: `docs/plans/261018_2230_review_scope_closeout.md`
- symptom: `Reviewer получил missing_visual_receipt_fields и missing_exact_bundle_hygiene_receipt; потребовались отдельные bounded receipt repairs013/019.`
- process_gap: `Hygiene heading в шаблонах содержит поясняющий суффикс и распознаётся через fallback field labels. Замена этих labels на prose при сокращении отчёта делает настоящий receipt невидимым validator; обязательность сохранения machine grammar недостаточно явна.`
- suggested_fix: `Через отдельный live carrier привести hygiene heading четырёх review templates к точному ## Exact bundle hygiene и добавить короткое правило сохранения Exact bundle hygiene, Untracked files check и применимого Visual env, включая non-UI N/A. Сохранить строгий lint и исходную failure history.`
- created_at: `2026-10-19 07:46 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

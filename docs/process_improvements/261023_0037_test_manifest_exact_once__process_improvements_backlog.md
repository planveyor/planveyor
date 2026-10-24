# Process improvements backlog — 261023 0037 test manifest exact once

**Date:** 2026-10-24 04:32 +0300
**Source ref:** `docs/plans/261023_0037_test_manifest_exact_once.md`
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
- trigger_ref: `docs/code_reviews/261023_0037_test_manifest_exact_once.md#s1-blocker`
- source_ref: `docs/plans/261023_0037_test_manifest_exact_once.md`
- symptom: `Docs-closeout context сообщает review_blocker_status=blocking для accepted green review, где секция S1 содержит только «Не обнаружены.».`
- process_gap: `Review lint принимает этот русский текст, но docs_closeout.py не включает его в S1_NONE_SENTINELS и трактует как blocking содержимое.`
- suggested_fix: `Через отдельный live carrier согласовать ограниченную грамматику пустого S1 между review lint, templates и docs-closeout. Добавить regression для «Не обнаружены.» и сохранить отказ для live B records, дубликатов и malformed содержимого; глобальные none-like правила не расширять, terminal review не переписывать.`
- created_at: `2026-10-24 04:26 +0300`
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
- trigger_ref: `docs/plans/261023_0037_test_manifest_exact_once.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261023_0037_test_manifest_exact_once.md`
- symptom: `Coder completion inventory вернул raw rc1 только из-за отсутствующего planned first-review host; остальные три bundle paths были OK, но классификация потребовала отдельного Q10 triage.`
- process_gap: `Coder prompt требует read-only bundle print/check до handoff, однако не объясняет этот ожидаемый результат до создания review-файла Reviewer.`
- suggested_fix: `Через отдельный live carrier уточнить completion prompt: единственный missing declared first-review host классифицировать как diagnostic inventory при валидных остальных paths и явном Reviewer ownership. Сохранять raw rc1 и причину; не создавать placeholder review, не повторять completed print и не ослаблять обязательные lint, review и exact closeout gates.`
- created_at: `2026-10-24 04:29 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
- status: `open`
- priority: `P?`
- role: `Planner`
- owner: `Planner`
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
- trigger_ref: `docs/plans/261023_0037_test_manifest_exact_once.md#planner-owned-sync--qualification-handoff`
- source_ref: `docs/plans/261023_0037_test_manifest_exact_once.md`
- symptom: `После принятой Q12 смены execution controls в plan draft сохранял пять старых clauses: blanket STOP, fixed prefixes, pass225/450/max2 и subtraction общего времени; потребовался отдельный Planner sync.`
- process_gap: `Общая проверка согласованности plan/draft не выделяет active execution controls при prospective Owner amendment и их отличие от historical stamps.`
- suggested_fix: `Через отдельный live carrier уточнить Planner prompt: перед qualification сверять между plan и draft retained command caps, снятые total ceilings, known-result classification и fresh role/pass grammar. Historical stamps и payload bytes сохранять; docs-only sync не разрешает автоматический product rerun.`
- created_at: `2026-10-24 04:32 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

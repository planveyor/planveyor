# Process improvements backlog — 261017 1730 bounded scanner normalization f62

**Date:** 2026-10-18 12:44 +0300
**Source ref:** `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
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
- owner: `Manager`
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `AGF7 завершился успешно, но последующий AGF8 approval был создан после expiry общего deadline; отмена просроченного запроса прервала turn и потребовала восстановления сохранённого original receipt.`
- process_gap: `Native approval guidance отделяет approval от semantic failure, но не закрепляет проверку remaining общего execution budget и сохранение исходного native result перед следующим approval.`
- suggested_fix: `Через отдельный живой carrier уточнить Manager prompt: перед single-action approval сверять exact command, cap, shared deadline и positive remaining; сохранять исходный continuation handle и полученный receipt; expired request отменять без повторной команды, нового deadline или восстановления historical outcome по текущему index.`
- created_at: `2026-10-18 12:20 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#commands`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `Ordinary preflight вернул safe_command с literal message placeholder, а требование whole-string equality потребовало отдельного уточнения перед semantic commit.`
- process_gap: `Architect prompt разрешает commit по safe_command и требует содержательный subject, но не описывает точную границу заполнения placeholder в helper skeleton.`
- suggested_fix: `Через отдельный живой carrier добавить в native closeout раздел Architect prompt structured argv recipe: сверить actual final helper root, executable, flags и ordered paths; разрешить только замену единственного -m message slot согласованным subject; запретить eval, unfilled placeholder и дополнительные flags или paths.`
- created_at: `2026-10-18 12:20 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
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
- trigger_ref: `docs/code_reviews/261017_1730_bounded_scanner_normalization_f62.md#b2-keywordgroup-и-await-primary--historical-fixed`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `B2 потребовал исправления keyword-before-group; следующая попытка ошибочно признала await-group-plus статической конкатенацией и закрепила это неверной positive assertion.`
- process_gap: `Общий AC-to-test checklist не выделяет проверку grammar binding перед выбором ожидаемого результата теста для частичного parser или static evaluator.`
- suggested_fix: `Через отдельный live carrier добавить в Coder prompt условную памятку для таких задач: до validation сопоставить изменённую классификацию с первичной грамматикой, записать пару positive/negative для внешнего dynamic operand и независимого внутреннего constant fragment; blanket lexical predicate не считать доказательством binding. Использовать существующие согласованные tests без автоматического расширения selectors или бюджета.`
- created_at: `2026-10-18 12:31 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-004
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
- trigger_ref: `docs/code_reviews/261017_1730_bounded_scanner_normalization_f62.md#s2-risk`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `Source review выявил повторные обходы всех nesting pairs, raw lines и неудачных expression suffixes; текущий R2 закрыт precomputed context, memoization и deterministic internal assertion.`
- process_gap: `Coder completion guidance не предлагает отдельной проверки стоимости input-driven циклов; короткое время существующих tests само по себе не выявляет повторный полный обход на каждом fragment или match.`
- suggested_fix: `Через отдельный live carrier добавить применимый к parser/normalizer изменениям source-only checklist: определить повторно посещаемые ranges, место precomputation и границу memoization. При необходимости связывать вывод с internal work-count assertion внутри уже согласованного test module; не объявлять benchmark или глобальную сложность доказанными и не запускать дополнительные проверки автоматически.`
- created_at: `2026-10-18 12:31 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-005
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `После T-correction-3 и T-correction-5 отдельный Coder CENSOR переносил actual completion, source hashes и checklist outcomes из полных raw receipts, поскольку primary durable carrier был подготовлен до validation как anticipated.`
- process_gap: `Общая evidence guidance не описывает явно порядок завершения для режима, где matching public bytes должны быть окончательными до shared deadline и не могут дописываться после source-bound validation.`
- suggested_fix: `Через отдельный live carrier согласовать Coder primary и CENSOR prompts: pre-deadline carrier явно остаётся pending, primary сохраняет полный actual receipt и сообщает фактический outcome, отдельно dispatched CENSOR читает этот receipt и материализует durable completion перед собственными artifact gates и final exact-ID readback. Anticipated text и historical green не заменяют actual proof; новых ролей, повторов tests или allowances правило не создаёт.`
- created_at: `2026-10-18 12:31 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-006
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#planner-qa`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `В исходном Planner handoff P2 завершился rc1 из-за отсутствующего NO SUGGESTIONS stamp после полноценной materialization draft; P3 остался not-run, потребовался отдельный Q7 recovery.`
- process_gap: `Planner prompt и code draft template показывают NO SUGGESTIONS stamp для случая, когда draft не требует изменений, тогда как lint требует его также при NO SUGGESTIONS в плане после реального создания или изменения draft.`
- suggested_fix: `Через отдельный live carrier уточнить Planner prompt и code draft template: добавить отдельные правдивые примеры для неизменённого draft и изменённого draft без предложений менять принятый semantic contract; materialize соответствующий parser-compatible stamp вместе с draft до final SHA и validation deadline, сохраняя действующий lint.`
- created_at: `2026-10-18 12:39 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-007
- status: `open`
- priority: `P?`
- role: `Reviewer`
- owner: `Reviewer`
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `Первый Contracts final artifact gate завершился missing_visual_receipt_fields из-за отсутствующего Visual env в non-UI review; потребовался отдельный bounded correction.`
- process_gap: `Шаблон помещает поле Visual env под заголовком required for UI tasks, хотя validator требует literal поле и для materialized non-UI секции.`
- suggested_fix: `Через отдельный live carrier уточнить docs/code_reviews/_template_single_commit.md: дать короткий non-UI вариант с обязательным Visual env: N/A (why=...), отделив его от применимых только к UI capture fields; включить эту проверку в подготовку artifact до final bytes и deadline.`
- created_at: `2026-10-18 12:44 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-008
- status: `open`
- priority: `P?`
- role: `Reviewer`
- owner: `Reviewer`
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
- trigger_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md#reviewer-qa`
- source_ref: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
- symptom: `После успешного artifact lint CF4 остановился на CURRENT-REVIEW-RED: от корректного red review ошибочно потребовали green bundle closeout до semantic handoff Architect.`
- process_gap: `Reviewer prompt безусловно предписывает bundle --check, но не отделяет closeout readiness от проверки корректности blocker artifact и его source-owned маршрута.`
- suggested_fix: `Через отдельный live carrier добавить явную ветку red semantic handoff: сохранить blocker, проверить selected support/current target/origin lint/scoped hygiene и literal owning status/Q&A; green bundle closeout требовать после фактического green reconciliation. Не ослаблять Planner preflight, не вводить waiver и не повторять stopped family автоматически.`
- created_at: `2026-10-18 12:44 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

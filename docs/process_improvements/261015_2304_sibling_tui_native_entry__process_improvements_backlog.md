# Process improvements backlog — 261015 2304 sibling tui native entry

**Date:** 2026-10-17 15:52 +0300
**Source ref:** `docs/plans/261015_2304_sibling_tui_native_entry.md`
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
- trigger_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md#validation-policy-q8-governing-owner-override`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `После scoped proof потребовалась Q8 reconciliation старого per-plan full-gate wording; исторический полный лог содержит 3481 тест, но terminal Make run/sink/post остались UNKNOWN.`
- process_gap: `Verification guide различает scoped и full команды, однако не закрепляет текущую границу публикации всей работы, предварительного Owner approval и сохранения proof при validation-text-only delta.`
- suggested_fix: `Через отдельный живой carrier уточнить verification policy: сейчас новые verify-full/repeats/equivalent full discovery запрещены; перед публикацией всей работы необходимы отдельный decomposition plan с учётом прежней Opus work и явное Owner approval до запуска. Для отдельного плана применять затронутые scoped checks и artifact-delta qualification; изменение только текста не обнуляет неизменный proof и не разрешает автоматический повтор.`
- created_at: `2026-10-17 15:42 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
- status: `open`
- priority: `P?`
- role: `Architect`
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
- trigger_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md#payload-fields-by-phase-c5q7`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `C4/Q6 выявил неверное ожидание stdin sentinel у Manager CMD; C5/Q7 затем выявил статическое требование plan/status для cold init, хотя actual producer добавляет их только при resume.`
- process_gap: `Общее требование payload parity не фиксировало применимость полей по фазам, канал argv/stdin и границу control header/raw prompt body до дорогого proof.`
- suggested_fix: `Для многофазных native fixtures добавить в существующий Planner prompt source-backed таблицу phase→producer→header fields/cardinality→transport→raw body→same-role receipt identity и связать её с существующим early narrow prerequisite. Использовать настоящие producers и guards без новых runtime fields, helpers или schemas; выполнять только проверки, применимые к фактической delta.`
- created_at: `2026-10-17 15:42 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-003
- status: `open`
- priority: `P?`
- role: `Coder`
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
- trigger_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md#commands`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `C2/Q4 и C3/Q5 потребовали owning corrections после runtime_pin_unattested, HOME внутри actual candidate и mixed package/direct imports; green public-help prerequisite не обнаружил authority continuation failure.`
- process_gap: `Planner proof contract не выделял физические launch identities и fixture prerequisites как отдельную проверяемую матрицу до применимых дорогих scoped suites.`
- suggested_fix: `Через отдельный live carrier дополнить existing Planner proof preflight таблицей candidate/facade root, child cwd, natural package/direct origins, TMPDIR/HOME boundaries и Git/non-Git prerequisites; связать её с существующим узким composition checkpoint. Не ослаблять guards, Git discovery или environment contract и не вводить автоматический test-all.`
- created_at: `2026-10-17 15:48 +0300`
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
- trigger_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `Literal draft extraction обрезала command body на triple-backticks внутри Python regex и дала SyntaxError до candidate preparation; отдельные outer invocation quoting errors также не доходили до shell.`
- process_gap: `Общая Coder invocation guidance не закрепляет различие Markdown fence и содержимого literal body, предварительную syntax validation и отдельную квалификацию invocation failure.`
- suggested_fix: `Через отдельный live carrier закрепить в existing Coder prompt standalone-line fence extraction, проверку полного body и closing heredocs, syntax-only AST/zsh parse перед execution. Invocation syntax failure фиксировать отдельно от candidate/proof result; не выполнять preparation или следующий command до исправления syntax и не создавать новый helper автоматически.`
- created_at: `2026-10-17 15:48 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-005
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
- trigger_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `Date-only CENSOR receipt вызвала false child-plan diagnostic в post-write plan lint; потребовались отдельное Owner-authorized timestamp clarification и replacement dispatch, хотя executable contract не изменился.`
- process_gap: `Planner CENSOR prompt не закрепляет обязательный полный timestamp header, тогда как historical-row classification линтера различает date-only и дату с HH:MM.`
- suggested_fix: `Через отдельный live carrier добавить в existing Planner CENSOR prompt обязательный образец YYYY-MM-DD HH:MM и короткую проверку формата до единственной append-only записи. Сохранить post-write lint/exact-ID gates, неизменность historical receipts и запрет автоматического replacement; failed ID не превращать в success.`
- created_at: `2026-10-17 15:52 +0300`
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
- trigger_ref: `unknown`
- source_ref: `docs/plans/261015_2304_sibling_tui_native_entry.md`
- symptom: `В этой role-сессии exact helper завершился rc0, но driver JSON.parse упал на представленном tool output с префиксом Warning; complete не удалось подтвердить в первоначальном role report.`
- process_gap: `Self-check guidance требует проверки structured result, но не отделяет полный stdout helper от ограниченного tool-представления и ошибки разбора этого представления.`
- suggested_fix: `Через отдельный live carrier добавить в existing Planner CENSOR prompt recipe одного exact-helper вызова с сохранением полного stdout/stderr в supplied TMPDIR. Затем разбирать сохранённый JSON и выводить только role, handoff_status, dispatch ID, state, missing_fields и invalid_reasons. Ошибку представления не выдавать за native verdict; не повторять dispatch и не исправлять historical receipt автоматически.`
- created_at: `2026-10-17 15:52 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

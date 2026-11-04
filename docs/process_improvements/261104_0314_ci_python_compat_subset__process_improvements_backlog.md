# Process improvements backlog — 261104 0314 ci python compat subset

**Date:** 2026-11-04 12:22 +0300
**Source ref:** `docs/plans/261104_0314_ci_python_compat_subset.md`
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
- trigger_ref: `docs/plans/261104_0314_ci_python_compat_subset.md#c-p3-1-supported-i18n-command-route`
- source_ref: `docs/plans/261104_0314_ci_python_compat_subset.md`
- symptom: `Accepted Commands вызвали i18n_pairs.py через frozen runtime facade, который отверг helper с rc64; потребовались остановка Coder и owning Architect/Planner reconciliation C-P3-1.`
- process_gap: `Syntax и exact-bundle preflight не подтверждают допустимость command route; unsupported helper invocation дошёл до executable handoff.`
- suggested_fix: `Через отдельный live non-terminal carrier уточнить docs/tools/prompts/planner_status_driven.md и docs/tools/prompts/planner_censor.md: перед Ready for Coder проверять каждый literal helper route по public help и current source, явно различать product WORK tooling и frozen lifecycle facade; выполнять только read-only capability checks, без пробных stamp/mutation calls и изменения allowlist.`
- created_at: `2026-11-04 11:44 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

### PI-002
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
- trigger_ref: `docs/plans/261104_0314_ci_python_compat_subset.md#evidence-chronological-append-only`
- source_ref: `docs/plans/261104_0314_ci_python_compat_subset.md`
- symptom: `Первый strict bundle readback текущего review содержал 13 вместо 19 members: шесть durable proof assets с короткими Markdown-ссылками не попали в bundle. Добавление literal repo refs восстановило полный набор.`
- process_gap: `Review templates рекомендуют относительные ссылки assets/..., тогда как текущий bundle resolver распознаёт repo-prefixed asset paths. Корректная Markdown-ссылка сама по себе не доказывает включение evidence в exact bundle.`
- suggested_fix: `Через отдельный live non-terminal carrier уточнить docs/code_reviews/_template_single_commit.md и docs/code_reviews/_template_merge_range.md: сохранять literal repo-relative ref рядом с каждой durable asset link, переносить SHA из объявленного support carrier и до handoff сверять включение всех expected assets в exact bundle readback. Directory glob и один успешный exit code не заменяют эту сверку.`
- created_at: `2026-11-04 12:22 +0300`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.
- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.
- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.
- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.
- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.

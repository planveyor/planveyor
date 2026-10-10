# Doc review — single commit (documentation/registry)

**Date:** DD.MM.YYYY HH:MM
**Target:** COMMIT=<hash|current|staged> | BUNDLE=<current|staged>
**Scope:** docs-only (list files or areas)
**Status:** Черновик | ✅ OK | ❌ S1 blocker(ы)

ОК: <краткий итог текущего docs-review artifact; если есть blocker, замени на `Замечания:` / `Вердикт:`>

> Рекомендуемое имя файла: `YYMMDD_HHMM_topic.md` (время нужно для уникальности и сортировки).

> Если review шёл по explicit plan bundle в dirty repo, фиксируй это прямо в header, например: `**Target:** BUNDLE=staged (PLAN=docs/plans/...)`.

> Same-contract rerun переписывает этот же review artifact in place. Старый blocker/verdict внутри файла остаётся только как `historical anchor` / `superseded`, а не как второй live artifact.

> Same file rule: same-contract rerun обновляет этот artifact path; новый файл нужен только для real scope expansion / нового независимого docs-only review contract.

> Docs-only leftover route split: если current bundle сузился до docs-only cleanup over closed non-doc baseline, accepted `docs/code_reviews/...` остаётся `historical anchor only`, а single live reviewer path остаётся в `docs/doc_reviews/...`.

Языковой контракт: review artifact Russian-first; английский оставляем только для `code`, команд, путей, literal schema labels и exact error strings. Для новых artifacts предпочитай заголовок `# Док-ревью - ...`; первая summary-строка после header должна начинаться с `ОК:` / `Замечания:` / `Вердикт:`, а не с `OK:` / `Findings:` / `Conclusion:`.

Review receipt family mapping (normalized envelope guidance):
- `schema_version`: `review_receipt.v1`
- `event_type`: `review.doc.single_commit`
- `ts`: literal header `**Date:**`
- `event_id`: derived from review artifact basename + `Date`
- `trace_id`: literal only when linked plan/run receipt materialize-ит его explicitly; иначе держим `N/A (why=review artifact is a partial lineage source family)`
- `span_id`: derived from review artifact path/basename
- `parent_span_id`: `N/A (why=review artifact header does not expose parent span lineage)` unless the same file literal-но anchors an upstream live blocker/ref

Правило: пишем **только проблемы и как исправить**. Если проблем нет — одна строка `ОК:` и (опционально) 1–3 пункта “что проверено”.

Серьёзность:
- **S1 Blocker** — нельзя merge / нельзя двигать status вперёд
- **S2 Risk** — можно принять осознанно (фиксить не обязательно в этом PR)
- **S3 Nit** — мелочи/стиль

## reviewer_code_risk - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `COMMIT=<hash|current|staged> | BUNDLE=<current|staged>` (должен literal-но совпадать с header `**Target:**`)
- Docs-only narrowing: те же code lanes остаются обязательными; risk domains сужаются до documentation/process carriers внутри общего списка.
- Coverage domains: `correctness`, `tests quality`, `security/privacy`, `subprocess/timeouts`, `races/locks/atomicity`, `data/migrations`, `performance`, `observability`, `integrations`, `supply chain`, `failure semantics`
- Findings:
  - `risk:R1 severity=S2 domain=correctness summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## reviewer_code_contracts - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `COMMIT=<hash|current|staged> | BUNDLE=<current|staged>` (должен literal-но совпадать с header `**Target:**`)
- Docs-only narrowing: contract domains сужаются до documentation/process carriers, но alternate docs-only artifact family не создаётся.
- Coverage domains: `plan fidelity`, `architecture/design fit`, `maintainability`, `canon/materialization/build drift`, `API/schema`, `documentation/registry`, `integration semantics`, `config/deploy/rollout`, `review artifact truthfulness`, `accessibility/i18n`, `LLM/prompt/meta-review`
- Uses plan lane-run artifact: `<PLAN_PATH#... | N/A>`
- Finalizer proof: `<fresh commands/readback | reused evidence with reason>`; если risk lane был `plan_evidence_only`, finalizer materialize-ит этот review artifact сам и не закрывает verdict только Manager memory.
- Findings:
  - `contracts:C1 severity=S2 domain=documentation/registry summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## Lane synthesis / aggregate verdict
- Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
- Canonical mapping:
  - `risk:R1 -> B1 (status=open owner=Coder)`
  - `contracts:C1 -> accepted-risk`
- Provenance records (one per lane finding/disposition; если findings нет, всё равно оставь no-finding placeholder с теми же field labels):
  - Finding: `risk:R1 | contracts:C1`
    - source_lane: `reviewer_code_risk | reviewer_code_contracts`
    - lane_finding_id: `risk:R1 | contracts:C1`
    - synthesis_disposition: `accepted_blocker | accepted_non_blocking_followup | accepted_risk | dismissed | superseded`
    - canonical_ref: `<review_artifact_path>#B1 | <review_artifact_path>#S2-Risk | <review_artifact_path>#Lane-synthesis--aggregate-verdict`
    - audit_status: `pending_post_merge_audit | done | N/A`
    - followup_plan: `docs/plans/... | N/A`
  - Finding: `N/A (findings отсутствуют)`
    - source_lane: `reviewer_code_risk+reviewer_code_contracts`
    - lane_finding_id: `N/A (no lane findings)`
    - synthesis_disposition: `no_findings`
    - canonical_ref: `<review_artifact_path>#Lane-synthesis--aggregate-verdict`
    - audit_status: `pending_post_merge_audit | done | N/A`
    - followup_plan: `N/A`
- Aggregate status: `Черновик | ✅ OK | ❌ S1 blocker(ы)` (для final verdict должен literal-но совпадать с header `**Status:**`)
- Notes: docs-only review использует тот же dual-lane schema; final non-draft verdict невалиден без обеих code lanes и synthesis

## S1 Blocker
- Для каждого live blocker внутри этой секции держи один stable local ref:
  - `### B1) <короткий заголовок>`
  - `- Blocker ID: B1`
  - `- Current state: open | historical-fixed | superseded`
  - `- Classification: stale evidence / historical artifact mismatch | same-contract reroute | closed baseline + live blocker split | real scope expansion`
  - `- Primary owner gap: Architect | Planner | Coder | Reviewer | UNCONFIRMED`
  - `- Evidence refs: <review_artifact_path>#B1`, `docs/plans/...`, `docs/reviews/...` (только literal refs по факту)
- Same-contract rerun переписывает тот же `B<N>`; новый local id допустим только для `real scope expansion` или нового независимого defect.
- (если нет — секцию удалить)

## S2 Risk
- (если нет — секцию удалить)

## S3 Nit
- (если нет — секцию удалить)

## Follow-ups
- (если нет — секцию удалить)

## Изменения реестра (optional)
- какие изменения стоит внести в `docs/registry.md` (без применения автоматически).

## Команды / evidence (optional)
- `git show --stat <commit>` / `git diff --staged --stat`
- `rg -n "<symbol>" <target-declared source roots>` (если проверяли соответствие описаний коду)
- Если docs-only review использует screenshots/assets, literal refs указывают на `docs/doc_reviews/assets/<REVIEW_BASENAME>/...`; basename-only refs не считаются exact.

## Exact bundle hygiene (required before `✅ OK`)
- Exact bundle hygiene: `<docs-only exact-path git diff --check command>` -> `<result>`.
- Untracked files check: `<rg merge-marker/trailing-space command over new documentation/review files or N/A (why)>` -> `<result>`.

## Архитектурное ревью (Architect; optional)
- Заполняется позже на стадии `Ready for Arch review` / `Architect arch review`.
- Вердикт и весь prose внутри этой секции держим по-русски; английский допустим только для literal fragments.
- Оценка runner quality (warning-first; заполняется, если non-default runner materially contributed; иначе `row_status=not_applicable`):
  - `runner_quality: row_status=<captured|missing|not_applicable> runner_id=<claude|codex|unknown|...> role=<coder|reviewer|reviewer_code_risk|reviewer_code_contracts> model=<literal model id or N/A (why=...)> task_class=<docs-only|process-helper|runtime-code|review-risk|review-contracts|visual|other> task_fit=<good|ok|poor|unknown> instruction_adherence=<0|1|2|3> scope_discipline=<0|1|2|3> evidence_quality=<0|1|2|3> defect_detection_or_fix_quality=<0|1|2|3|N/A> autonomy_cost=<low|medium|high|blocked> required_frontier_intervention=<none|minor|major|blocker> missed_blockers=<0|1|2|3+|unknown> useful_for_future=<yes|conditional|no|unknown> source_ref=<plan/review/lane metadata ref> follow_up_ref=<N/A|docs/followups/...|docs/plans/...> notes=<short Russian reason>`
- Шкала: `0` harmful/unusable; `1` weak/substantial correction; `2` acceptable/minor correction or normal review loop; `3` strong/low correction cost.

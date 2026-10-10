# Doc review — merge-range (BASE..HEAD) (documentation/registry)

**Date:** DD.MM.YYYY HH:MM
**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)
**Spec:** docs/plans/<origin_plan>.md | N/A (origin_plan_state=manual_range_review_no_origin_plan)
**Range:** BASE=<sha> .. HEAD=<sha|HEAD> (legacy/context only; helpers read `**Target:**`)
**Scope:** docs-only (list files or areas)
**Status:** Черновик | ✅ OK | ❌ S1 blocker(ы)

ОК: <краткий итог текущего docs-review artifact; если есть blocker, замени на `Замечания:` / `Вердикт:`>

> Рекомендуемое имя файла: `YYMMDD_HHMM_topic.md` (время нужно для уникальности и сортировки).

> Same-contract rerun переписывает этот же review artifact in place. Старый blocker/verdict внутри файла остаётся только как `historical anchor` / `superseded`, а не как второй live artifact.

> Same file rule: same-contract rerun обновляет этот artifact path; новый файл нужен только для real scope expansion / нового независимого docs-only review contract.

> Docs-only leftover route split: если current range/slice сузился до docs-only cleanup over closed non-doc baseline, accepted `docs/code_reviews/...` остаётся `historical anchor only`, а single live reviewer path остаётся в `docs/doc_reviews/...`.

Языковой контракт: review artifact Russian-first; английский оставляем только для `code`, команд, путей, literal schema labels и exact error strings. Для новых artifacts предпочитай заголовок `# Док-ревью - ...`; первая summary-строка после header должна начинаться с `ОК:` / `Замечания:` / `Вердикт:`, а не с `OK:` / `Findings:` / `Conclusion:`.

Правило: пишем **только проблемы и как исправить**. Если проблем нет — одна строка `ОК:` и (опционально) 1–3 пункта “что проверено”.

## Контекст диапазона (required)
- merge list (если нужно): `git log --oneline --first-parent --merges BASE..HEAD`
- note: если были fixup‑коммиты после merge — они тоже входят в BASE..HEAD

Серьёзность:
- **S1 Blocker** — нельзя merge / нельзя двигать status вперёд
- **S2 Risk** — можно принять осознанно (фиксить не обязательно в этом PR)
- **S3 Nit** — мелочи/стиль

## reviewer_code_risk - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` (должен literal-но совпадать с header `**Target:**`; `**Range:**` — legacy fallback only)
- Docs-only narrowing: те же code lanes остаются обязательными; risk domains сужаются до documentation/process carriers внутри общего списка.
- Coverage domains: `correctness`, `tests quality`, `security/privacy`, `subprocess/timeouts`, `races/locks/atomicity`, `data/migrations`, `performance`, `observability`, `integrations`, `supply chain`, `failure semantics`
- Findings:
  - `risk:R1 severity=S2 domain=correctness summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## reviewer_code_contracts - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` (должен literal-но совпадать с header `**Target:**`; `**Range:**` — legacy fallback only)
- Docs-only narrowing: contract domains сужаются до documentation/process carriers, но alternate docs-only artifact family не создаётся.
- Coverage domains: `plan fidelity`, `architecture/design fit`, `maintainability`, `canon/materialization/build drift`, `API/schema`, `documentation/registry`, `integration semantics`, `config/deploy/rollout`, `review artifact truthfulness`, `accessibility/i18n`, `LLM/prompt/meta-review`
- Uses plan lane-run artifact: `<PLAN_PATH#... | N/A>`
- Findings:
  - `contracts:C1 severity=S2 domain=documentation/registry summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## Lane synthesis / aggregate verdict
- Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
- Canonical mapping:
  - `risk:R1 -> B1 (status=open owner=Coder)`
  - `contracts:C1 -> accepted-risk`
- Aggregate status: `Черновик | ✅ OK | ❌ S1 blocker(ы)` (для final verdict должен literal-но совпадать с header `**Status:**`)
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
- какие изменения стоит внести в `docs/registry.md`.

## Команды / evidence (optional)
- `git diff -U3 BASE..HEAD -- docs`
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint` (если прогоняли strict canonical pass; gate уже включает `--check-code-refs --code-refs-scope repo`)
- Если docs-only review использует screenshots/assets, literal refs указывают на `docs/doc_reviews/assets/<REVIEW_BASENAME>/...`; basename-only refs не считаются exact.

## Exact bundle hygiene (required before `✅ OK`)
- Exact bundle hygiene: `<docs-only range or exact-path git diff --check command>` -> `<result>`.
- Untracked files check: `<rg merge-marker/trailing-space command over new documentation/review files or N/A (why)>` -> `<result>`.

> Заполняется только current same-range Reviewer rerun после landing delivery. Raw `git diff --check` остаётся primary evidence: не меняй header/aggregate status на derived readback state и не переписывай historical carrier ради synthetic green.

> Rows sort by bytewise `path`, numeric `line`, `finding_kind`, `blob_oid`, `provenance_ref`. `Candidate set SHA-256` is SHA-256 of the UTF-8 compact JSON array of exactly the 13 nested fields, lexical keys and `separators=(',', ':')`. Architect alone may add this bare exact line under `## Архитектурное ревью`: `Historical disposition approval: state=accepted range=<base>..<head> raw_exit=<n> candidate_set_sha256=<sha256>`.

## Historical diff-check disposition (optional)

- Raw command: `git diff --check <base>..<head>`
- Raw exit: `<integer>`
- Candidate count: `<integer>`
- Candidate set SHA-256: `<sha256>`

### Candidate rows

- Candidate:
  - range: `<base>..<head>`
  - raw_command: `git diff --check <base>..<head>`
  - raw_exit: `<integer>`
  - path: `<repo-relative path>`
  - line: `<integer>`
  - blob_oid: `<range-head blob oid>`
  - finding_kind: `trailing_whitespace | blank_line_at_eof`
  - provenance_ref: `<exact repo-relative provenance path>`
  - provenance_sha256: `<sha256 of immutable bytes>`
  - lifecycle: `candidate`
  - reason_code: `intentional_markdown_hard_break | immutable_support_payload_selected_current | immutable_support_payload_historical_or_superseded`
  - owner: `Reviewer`
  - action: `record_candidate`

## Архитектурное ревью (Architect; optional)
- Заполняется позже на стадии Architect triage.
- Вердикт и весь prose внутри этой секции держим по-русски; английский допустим только для literal fragments.

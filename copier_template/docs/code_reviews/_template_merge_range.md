# Code review — merge-range (BASE..HEAD)

**Date:** DD.MM.YYYY HH:MM
**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)
**Spec:** docs/plans/<origin_plan>.md | N/A (origin_plan_state=manual_range_review_no_origin_plan)
**Range:** BASE=<sha> .. HEAD=<sha|HEAD> (legacy/context only; helpers read `**Target:**`)
**Exclude docs:** yes/no
**Status:** Черновик | ✅ OK | ❌ S1 blocker(ы)

ОК: <краткий итог текущего review artifact; если есть blocker, замени на `Замечания:` / `Вердикт:`>

> Рекомендуемое имя файла: `YYMMDD_HHMM_topic.md` (время нужно для уникальности и сортировки).

> Interim contract для status-driven reviewer flow: `Черновик` — единственный допустимый interim header status, пока plan ещё на `Reviewer code review` / `Reviewer visual review`. Если visual proof блокируется, переводи этот же файл в `❌ S1 blocker(ы)` и опиши blocker в `## Визуальные доказательства`; не выдумывай `BLOCKED` / `PARTIAL` / `FROZEN`.

Языковой контракт: review artifact Russian-first; английский оставляем только для `code`, команд, путей, literal schema labels и exact error strings. Для новых artifacts предпочитай заголовок `# Код-ревью - ...`; первая summary-строка после header должна начинаться с `ОК:` / `Замечания:` / `Вердикт:`, а не с `OK:` / `Findings:` / `Conclusion:`.

Правило: пишем **только проблемы и как исправить**. Если проблем нет — одна строка `ОК:` и (опционально) 1–3 пункта “что проверено”.

## Контекст диапазона (required)
- merge list: `git log --oneline --first-parent --merges BASE..HEAD`
- note: если были fixup‑коммиты после merge — они тоже входят в BASE..HEAD

## Контекст rerun (required for rerun after blocking follow-up)
- Rerun mode: `incremental | full | N/A (first pass)`
- Baseline artifact: `<filename or N/A>`
- Rerun scope: `<что перепроверяем сейчас>`
- Trusted unaffected surfaces: `<почему prior accepted evidence всё ещё валиден / N/A>`
- Reused evidence: `<какие prior artifacts переиспользуем и почему / N/A>`

> Same-contract rerun переписывает этот же review artifact in place. Baseline artifact остаётся внутри него только как `historical anchor` / `superseded`, а не как отдельный live verdict.

> Same file rule: same-contract rerun обновляет этот artifact path; новый файл нужен только для real scope expansion / нового независимого review contract.

Серьёзность:
- **S1 Blocker** — нельзя merge / нельзя двигать status вперёд
- **S2 Risk** — можно принять осознанно (фиксить не обязательно в этом PR)
- **S3 Nit** — мелочи/стиль

## reviewer_code_risk - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` (должен literal-но совпадать с header `**Target:**`; `**Range:**` — legacy fallback only)
- Coverage domains: `correctness`, `tests quality`, `security/privacy`, `subprocess/timeouts`, `races/locks/atomicity`, `data/migrations`, `performance`, `observability`, `integrations`, `supply chain`, `failure semantics`
- Findings:
  - `risk:R1 severity=S1 domain=correctness summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## reviewer_code_contracts - GPT-6.1 Sol ultra
- Lane status: `complete | pending | skipped(N/A) | superseded`
- Target snapshot: `RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` (должен literal-но совпадать с header `**Target:**`; `**Range:**` — legacy fallback only)
- Coverage domains: `plan fidelity`, `architecture/design fit`, `maintainability`, `canon/materialization/build drift`, `API/schema`, `documentation/registry`, `integration semantics`, `config/deploy/rollout`, `review artifact truthfulness`, `accessibility/i18n`, `LLM/prompt/meta-review`
- Uses plan lane-run artifact: `<PLAN_PATH#... | N/A>`
- Findings:
  - `contracts:C1 severity=S2 domain=plan fidelity summary=<...> evidence=<...>`
- No findings reason: `N/A | <why in Russian>`

## Lane synthesis / aggregate verdict
- Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`, `reviewer_visual (optional)`
- Canonical mapping:
  - `risk:R1 -> B1 (status=open owner=Coder)`
  - `contracts:C1 -> accepted-risk`
- Aggregate status: `Черновик | ✅ OK | ❌ S1 blocker(ы)` (для final verdict должен literal-но совпадать с header `**Status:**`)
- Provenance records (one per lane finding/disposition; если findings нет, всё равно оставь no-finding placeholder с теми же field labels):
  - Finding: `risk:R1 | contracts:C1 | visual:V1`
    - source_lane: `reviewer_code_risk | reviewer_code_contracts | reviewer_visual | manager_merge_handoff_gate`
    - lane_finding_id: `risk:R1 | contracts:C1 | visual:V1 | manager:M1`
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
- Notes: final non-draft verdict невалиден без обеих code lanes; canonical `B<N>` живёт здесь и в `## S1 Blocker`

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

## Plan gaps (plan fixes needed)
- (если нет — секцию удалить)
- сюда пишем “дыры в плане”, которые нельзя/опасно чинить только кодом:
  - отсутствуют/неполные Acceptance/DoD/Tests/Commands
  - отсутствует `## Visual Acceptance` или target-declared visual contract (modes/endpoint/account/harness), либо explicit `N/A (why)` для UI-задачи
  - в плане есть copy‑paste код/сигнатуры third‑party, которые не подтверждены (нужно пометить `UNCONFIRMED` или переписать как контракт)
  - несоответствие между реализацией и планом, которое требует возврата на `Planner finalize`/`Planner intake`

## Команды / evidence (optional)
- `git diff --check BASE..HEAD`
- `rg -n "^<<<<<<< |^======= |^>>>>>>> " .`
- `<target-declared duplicate checker> BASE HEAD` (если target его объявил)
- (если selected target объявляет migration-drift gate) `<target-declared command>` → `<expected result>`
- (если применимо) `<target-declared test/smoke command>` → `<expected result>`

## Exact bundle hygiene (required before `✅ OK`)
- Exact bundle hygiene: `<range or exact-path git diff --check command>` -> `<result>`.
- Untracked files check: `<rg merge-marker/trailing-space command over new files or N/A (why)>` -> `<result>`.

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

## Визуальные доказательства (required for UI tasks)
- Runtime UI visual evidence state: `not_applicable | green | red | ambiguous`
- Comparator command: `<exact command from origin plan Review visual lane contract | N/A (why=...)>`
- Comparator claim: `mechanical | N/A (why=...)`
- Comparator result: `pass | fail | blocked | N/A (why=...)`
- Capture status: `complete | failed | blocked | N/A (why=...)`
- Complete index inspected: `yes | no | N/A (why=...)`
- Design verdict: `no_findings | findings | N/A (why=...)`
- Finding dispositions: `N/A | status=closed|deferred reference=<durable docs/* ref>`
- Mandatory modes: `<comma-separated exact modes from origin plan | N/A (why=...)>`
- Human index (<declared mode>): `<exact command from origin plan | N/A (mode not required)>`
- Durable asset (<declared mode>): `docs/code_reviews/assets/<REVIEW_BASENAME>/<non-empty regular file> | N/A (mode not required)`
- Visual env: target-declared modes and endpoint/port, or `N/A (why=...)`.
- Runtime/harness recipe: см. plan `## Visual Acceptance` → `### How to run (Reviewer)`
- Source scenarios: `<affected plan anchors>` + `docs/smoke_visual.md#<section>`
- Post-merge visual sanity: `<scenario -> mode -> screenshot -> verdict>`
- What checked (short): …
- Если visual sanity ещё не завершён, явно напиши здесь `Pending:` / `Blocked:` и перечисли только реально существующие assets/диагностику; не заявляй “скрины будут позже”.
- Screenshots (required):
  - Store in: `docs/code_reviews/assets/<REVIEW_BASENAME>/` (folder next to this review file)
  - Add at least 1 screenshot per mode from plan `Modes to test`
  - List here (use one exact literal path per screenshot; relative preferred, e.g. `assets/<REVIEW_BASENAME>/<mode>_01_<topic>.png`):
    - `assets/<REVIEW_BASENAME>/<file>.png` — Proves: <what is clearly visible on the screenshot>

Comparator proof и human visual proof — независимые обязательные carriers: mechanical `pass` не заменяет design verdict, а human screenshot не заменяет comparator. Closing assets лежат только в current review basename, по одному non-empty regular non-symlink файлу на каждый mandatory mode; `.tmp/**`, historical/другой review basename, path traversal и symlink допустимы только как diagnostic/context evidence. Baseline-update команды не являются closing comparator proof.

## Архитектурное ревью (Architect; optional)
- Заполняется позже на стадии Architect triage.
- Вердикт и весь prose внутри этой секции держим по-русски; английский допустим только для literal fragments.

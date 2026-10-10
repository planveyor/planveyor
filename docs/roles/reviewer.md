# Роль: Reviewer (код‑ревьюер)

**Runner:** выбирается current runtime policy; Reviewer не меняет runner внутри role flow.
**Артефакт:** review‑файл + ссылка на него в plan
**Вход:** `PLAN_PATH` + review content target (`staged` / `current` / commit; если plan явно держит selective staging contract — допустим bounded `staged bundle` / `current bundle`). “Чистый коммит” не обязателен: допускается ревью по `staged`, `current` или explicit bundle, ограниченному артефактами плана. Если plan не дали — сначала создать review-only plan (см. `docs/playbooks/review_scoping_plan.md`).
**Выход:** review‑файл (`docs/code_reviews/*` или `docs/doc_reviews/*`) + обновлённый status плана + короткий wrapper-visible receipt (`artifact`, `target`, `verdict`, optional `summary`) из review header / `## Review artifacts`

Цель: найти риски и регрессии до merge и подтвердить “реализация = plan + контракты”.

Термины:
- `PLAN_PATH` — путь к файлу plan (обычно `docs/plans/YYMMDD_HHMM_topic.md`), который Owner передаёт в статусном промпте.

## Source of truth / precedence (если есть конфликт)

- Analysis logical locator `docs/playbooks/analysis_wave.md` читается из root
  shared corpus для content IDs `default` и `planveyor`.
- `target-local` может выбрать consumer-owned carrier только когда его path,
  owner и current digest явно объявлены selected target contract. Unknown,
  missing, malformed или stale selection — gap/reroute.
- Не используй target mirror, saved copy, prior map или guessed path как
  fallback. Role не создаёт source map и не восстанавливает carrier по памяти.
- Процесс и формат работы: `AGENTS.md`.
- Контракт задачи: `PLAN_PATH` и `docs/plans/README.md` /
  `docs/plans/_template.md`.
- Canonical architecture, data, interface, API, security и registry carriers
  берутся только из current `Context links` либо declared target canon.
- `docs/snapshots/*` — history/handover background, не effective spec и не
  active canon pointer.
- Shared process decisions живут в `docs/adr/*`; role открывает только
  relevant accepted decision для текущего bundle.

Правило: если plan конфликтует с canonical contract или двусмысленен, зафиксируй
это в plan и верни routing на нужный status. Не решай разрыв молча.

## Shared-core rule

В shared role doc поднимай только repo-agnostic process invariants:
`alternate state / non-primary carrier proof`, `shared contract carrier bounded
fan-out`, `truthful preconditions / harness drift vs live regression` и
`reopened-blocker classification / same-contract reroute`. Target-local UI,
transport или harness details не становятся default wording.

Правило planning/dev contour:
- `analysis_wave` и `decomposition_wave` — planning-contour review lanes; Reviewer validates packs/linkage/artifact truth, not product diff.
- Если ordinary `developer_wave` review reveals broad analytics, child graph creation or `split_required=true`, treat it as route/plan gap back to Architect/planning contour.
- Reviewer cites the active wave playbook for field semantics instead of expanding role docs into a duplicate schema.

## Границы роли (жёстко)
- Reviewer не правит код/шаблоны/миграции: только review‑артефакт + вопросы/блокеры/plan‑gaps в plan.
- Review artifact должен оставаться machine-readable для wrapper receipt: в header держи явные `**Target:**`/`**Review target:**`/`**Range:**`, `**Status:**` и короткую первую summary-строку (`OK:` / `Findings:` / `Verdict:`), а ссылку на файл сразу фиксируй в plan → `## Review artifacts`.
- Если merge-range review-only plan создан через `planveyor_review_range_init()`, generated scaffold обязан уже materialize-ить critical-path contract (`Problem / Solution / Scope / Tests / Commands / Review artifacts`), truthful объявленный visual lane и truthful generated-bundle artifact split (`docs/doc_reviews/*` пока final generated bundle остаётся docs-only; `docs/code_reviews/*` только когда final generated bundle реально включает non-doc carrier). Почти template-only scaffold, stale artifact type или invented runtime-mode defaults вне честного declared UI/profile proof = process gap, а не валидный reviewer precondition.
- Для runtime UI generated plan и code draft обязаны нести один literal `## Review visual lane contract`: bounded inline `review_visual_lane_contract.v1` либо identical hash-bound `review_visual_lane_contract_ref.v1`, который shared helper разрешает в единственный full `review_visual_lane_contract.v2`. `missing|malformed|ambiguous`, stale/foreign/hash-mismatched или unsafe ref — fail-closed technical gap к Architect; Reviewer не ставит `N/A`, не сканирует assets directory и не реконструирует команды по памяти/source docs.
- Разводи две разные сущности:
  - `review content target` = какой snapshot diff ты реально читаешь (`staged`, `current`, commit);
  - `bundle scope` = какими explicit путями этот review ограничен и что потом войдёт в post-review selective staging.
  Если plan уже держит exact-bundle contract, грязный repo вне этого bundle не blocker и не повод требовать “сначала очистить весь staged/current diff”.
- Если `PLAN_PATH` или review-only plan явно объявляет literal `Review target` / `**Target:**` (например, `COMMIT=staged`, `COMMIT=current`, `RANGE=...`, `BUNDLE=staged`), follow that target literally:
  - `COMMIT=staged` = authoritative snapshot для ревью весь index по текущему deliverable; out-of-scope staged files действительно blocker;
  - `BUNDLE=staged|current` = bounded snapshot только по explicit bundle; unrelated repo dirt вне bundle не blocker.
- Если plan опирается на deterministic staging bundle, review artifact и его asset refs должны быть concrete: без placeholder “потом приложим”, без абстрактного “см. screenshots”. Architect closeout должен уметь восстановить exact bundle по явным путям.
- Если plan явно включает post-review selective staging, используй bundle как scope limiter:
  - authoritative implementation/doc file set = `code_draft_meta.targets`;
  - final explicit bundle = `code_draft_meta.targets` + `PLAN_PATH` + code draft + `## Review artifacts` + explicit asset refs;
  - helper `planveyor_plan_bundle --print|--check <PLAN_PATH>` нужен для sanity-check bundle, а не для требования clean repo.
- Reviewer gate для `## Documentation impact / provenance`: actual diff, `code_draft_meta.targets` и carrier должны совпадать. Missing carrier, stale `Synchronous doc/registry targets`, unplanned docs diff или противоречие между carrier и exact bundle = plan gap/blocker; memory-finalize не заменяет upfront carrier.
- Если same file содержит unrelated hunks и из-за этого exact deliverable больше не восстанавливается из agreed bundle, это scope contamination / plan drift: фиксируй blocker или Q&A, а не требуй “чистое репо” как универсальный precondition.
- Для UI-задач один и тот же review artifact живёт через `Reviewer code review` -> `Reviewer visual review`: это канонический split-phase artifact, а не повод заводить второй “partial/frozen review” процесс.
- Для dual-model code review действует один file-backed contract: один Reviewer, две code lanes, один review artifact, один top-level status.
  - `reviewer_code_risk` сначала materialize-ит plan-resident lane-run artifact в `PLAN_PATH` evidence с literal полями `run_id`, `lane_id`, `runner_id`, `session_key`, `sid`, `profile`, `model`, `reasoning_effort`, `prompt_file`, `target_ref`, `target_snapshot`, `coverage_domains`, `findings`, `lane_status`, `no_findings_reason`, `limits`, `written_at`. В custom/serial pipeline runner/model truth берётся из этих полей; collab/default configured Codex suffix является display-only и не должен затирать metadata.
  - `reviewer_code_contracts` не доверяет Manager memory: перед finalization он читает plan-resident block только через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --project-root "$root" --select-risk-lane --origin-plan "$PLAN_PATH" --json`; только support-preflighted `state=selected` + exit `0` и matching `target_snapshot` разрешают один review artifact с секциями, заголовки которых начинаются с `## reviewer_code_risk` и `## reviewer_code_contracts`, `## Lane synthesis / aggregate verdict` и canonical `## S1 Blocker` / `## S2 Risk` / `## S3 Nit`. `missing|blocked|non-zero` не materialize-ит final artifact/status/P/F: recovery принадлежит `reviewer_code_risk`, который создаёт новый immutable support/compact pair при необходимости, supersedes old compact metadata и повторяет selector; Manager/Owner не редактируют carriers вручную.
  - Если compact carrier объявляет хотя бы одно из `full_payload_ref` / `full_payload_sha256`, оба поля обязательны: каждая current и historical пара входит в source-plan exact bundle по repo-relative, symlink-free (leaf и ancestor) ref и SHA. Historical payload остаётся byte-only evidence даже если legacy/red; selected current один проходит JSON/schema/parity support preflight. Missing/incomplete/unsafe/symlink/mismatched/conflicting pair блокирует bundle/closeout до staging, а Reviewer не переписывает historical asset для обхода.
  - Для `BUNDLE=current` risk lane берёт computed value из `planveyor_review_target_snapshot <PLAN_PATH> --current-bundle`, но в plan пишет только compact selector receipt с target/bundle SHA, `full_payload_ref` и `full_payload_sha256`. Полный structured `review_target_snapshot.v2` stdout хранится byte-for-byte для ordinary primary-draft branch; admitted strict N-A parent получает versioned `review_target_snapshot.v3` from complete canonical child plans plus same-stem drafts. Shared selector/final preflight проверяет SHA, nested shared-validator payload, exact target/hash projection и canonical `findings` projection (`id`, `severity`, `domain`, `title`, `source_refs`), а не только число findings. Raw full stdout в plan и generic large-fence exemption запрещены.
  - Для live `BUNDLE=current` authoritative verdict даёт только `scripts/plan_lint.py:preflight_current_review_proof`: один exact header `**Target:** BUNDLE=current bundle_sha256=<64 lowercase hex>`, compact object ровно `{"bundle_sha256":"...","target":"BUNDLE=current"}`, immutable full `review_target_snapshot.v2` или discriminated strict-N-A `review_target_snapshot.v3` и его nested compact projection должны совпасть с fresh producer bytes. Alias/reordered/prefix/suffix/duplicate, mixed/manual hash, partial graph, missing/stale support или producer-red fail-close; prose и history не являются fallback. `review_artifact_lint`, oracle, bundle и docs-closeout потребляют только этот result, не пересобирая свой current-proof parser.
  - Финальный dual-lane lint должен иметь explicit origin: preferred `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py review_artifact_lint.py --origin-plan "$PLAN_PATH" <review_artifact>`; fallback допустим только через один literal `PLAN=docs/plans/...` в `**Target:**`. `target_snapshot` сравнивается с review `**Target:**` или fallback `**Range:**`; для `BUNDLE=current bundle_sha256=...` helper дополнительно recompute-ит producer snapshot по текущим `code_draft_meta.targets`.
  - Raw lane findings используют только local ids `risk:R<N>` / `contracts:C<N>` / `visual:V<N>`; canonical blocker lineage `B<N>` появляется только после `Lane synthesis / aggregate verdict`.
  - Docs-only review не заводит alternate artifact family: тот же dual-lane schema остаётся обязательным, просто coverage/finding domains сужаются до documentation/process carriers внутри `reviewer_code_risk` и `reviewer_code_contracts`.
  - Если plan literal-но активирует `### Semantic review observation` (`schema=semantic_review_observation.v1`, `mode=required`, `writer=reviewer_code_contracts`), contracts lane получает узкую дополнительную plan-resident write duty. После selected risk lane и aggregate verdict только `reviewer_code_contracts` может append-ить один `semantic_review_observation_proposal.v1` в `PLAN_PATH::## Evidence`; это proposal-only semantic input, а не место для ручного `run_id`, snapshot, fingerprint, observation/predecessor ID или family ID.
    - Сначала вызови `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py semantic_review_observation.py --plan PLAN_PATH --format json`. `ready_to_materialize/role_proposal_required` разрешает один proposal с role fields `progress_verdict`, `progress_evidence_refs`, `blockers`, `resolved_predecessor_blocker_refs`. Для blocker допустимы только `blocker_ref`, `lineage_relation`, `predecessor_blocker_ref`; `same_family` ссылается на literal `<review-artifact-path>#B<N>` из immediately preceding final head, а `first_observation|independent_boundary` имеют null predecessor.
    - Повторный read в `ready_to_materialize/observation_not_materialized` возвращает `materialization.observation`. Скопируй complete final `semantic_review_observation.v1` exactly; helper, а не Reviewer, вычисляет `review_generation_id`, `observation_id`, predecessor, fingerprint, target/review identity, proposal digest, seeded/reused family IDs и resolved family IDs.
    - Третий read обязан стать `valid/current_observation_valid`; это единственный нормальный final handoff и idempotent no-append readback. `not_available/feature_not_activated` означает legacy/non-opt-in absence без writer duty, `not_available/risk_generation_not_available` — clean active waiting, а любой `blocked` останавливает finalization и требует обычный fail-closed plan/review gap, без второго proposal/final или status shortcut.
    - P/F pairing positional: proposal стоит после helper-selected current risk block, а accepted final — immediately next semantic carrier с matching `proposal_sha256` и той же risk generation. Accepted nodes образуют immutable linear chain; CENSOR, `reviewer_code_risk`, Manager, chat/transport retry не создают semantic carrier и не могут перезаписать accepted history.
  - `progress_verdict` остаётся role-owned (`first_observation`, `same_contract_progress`, `same_contract_stalled`, `scope_churn`, `independent_boundary`), но не является routing truth. Любой downstream consumer принимает только helper result `valid/current_observation_valid`; `not_available`, `ready_to_materialize` и `blocked` не превращаются в green, route или metric.
  - Canonical current blocker input — только `### B<N>)` record в `## S1 Blocker` с matching unique `Blocker ID` и `Current state=open|historical-fixed|superseded`: green header/aggregate требует `blockers=[]`, red — exact open refs. До Coder mutation остаются current-cycle `Stale note` + `Rerun note`; Coder не переписывает compact receipt, asset, P/F или review artifact. Reviewer rerun supersedes old compact receipt, пишет новый asset/receipt и fresh P/F в том же review file.
- Metadata reviewer lane — downstream substrate для quality attribution: держи `runner_id`, `model`, `lane_id`, `session_key` и `target_snapshot` стабильными/читаемыми для Architect-owned `runner_quality`. Reviewer не self-score'ит runner quality; task-level row заполняет Architect на Arch review.
- Header status у review artifact канонический и закрытый:
  - `Черновик` — единственный допустимый interim status, пока visual review ещё не закрыт.
  - `✅ OK` — только когда code review + visual review завершены без S1 blocker'ов.
  - `❌ S1 blocker(ы)` — любой blocking state, включая runtime/visual blocker.
  - Не выдумывай ad-hoc header labels вроде `BLOCKED`, `PARTIAL`, `FROZEN`, `PAUSED` и т.п.
- Reviewer не меняет требования/UX “втихую”: mismatch с планом = `Plan gap` (возврат на `Planner finalize`/`Ready for Architect response`).
- Если blocker повторяет предыдущий цикл или survives same-status rerun, Reviewer не ограничивается симптомом: в review-file и plan явно фиксируются `Loop signal`, `Root cause class`, `Next owner`, `same-contract reroute vs scope gap`; без этой классификации repeated loop считается reviewer-owned process miss.
- Для executable composite lane Reviewer обязан различать `same-cluster evidence reroute` и `cluster-local material delta`: первый переиспользует тот же blocker lineage в том же plan, второй требует, чтобы live blocker/новые implementation receipts уже жили в child/follow-up plan, а старый composite file оставался только `Superseded` или explicit reference-only baseline.
- Reviewer не использует Owner как first semantic sink: `reviewability gap`, canonical reviewer lane dispute и plan/contract contradictions по умолчанию возвращаются в Architect-owned зону (`Ready for Architect response`), а не в сырой Owner stop.
- Direct Owner stop из Reviewer допустим только для bounded infra/bootstrap dead-end'ов до semantic triage (`missing PLAN_PATH`, broken header/oracle before routing, collab unavailable/thread limit, unsupported manager command, missing sandbox/escalation/tool prerequisite).
- Если `plan_meta.phase_overlay = "decomposition_wave"` и `plan_meta.phase_state = "active"`, Reviewer ревьюит planning artifacts, linkage, lint/doc-lint gates и `## Mechanism coverage`, а не product code.
  - Reviewer обязан проверить `## Decomposition quality gate`: `solvability`, `completeness`, `non-redundancy`, mutable surface/runtime isolation и recomposition owner. Если child-local green не доказывает parent delivery или parallel заявлен без runtime/shared-resource policy, это plan gap.
- Если plan явно помечен как non-executable umbrella/master-plan after decomposition (`Code draft(s): N/A`, downstream handoffs `N/A`, review gates живут только в child plans) и это **не** active `decomposition_wave`, Reviewer не создаёт review-file по этому файлу. Это routing/contract drift: зафиксируй blocker в plan и верни его на `Ready for Architect response`.
- Reviewer **никогда** не ставит `**Status:** Done` (ни для dev-plan, ни для review-only). При current-task `COMMIT_POLICY=native_existing` `Done` ставит Architect на стадии `**Status:** Architect arch review`; при `COMMIT_POLICY=human_explicit` Architect останавливается на принятом Arch review, а `Done` ставит только отдельный `sibling close --commit` после preview.
- `**Status:** Ready for Arch review` = handoff на Architect.
  - Для обычного dev-plan: ставь только если в review нет **S1 blockers**, все вопросы `Reviewer Q&A` закрыты (`status=closed|superseded`), в plan заполнен `## Review artifacts`, и (если UI) выполнен visual review без визуальных поломок/ошибок.
  - Для **review-only plan**: `Ready for Arch review` означает “review report готов для triage Architect’ом”. S1/S2 замечания допускаются, но это **не** “ready-to-merge”: Architect должен принять решение и, если нужны фиксы, завести follow-up dev-plan (или вернуть на `Planner finalize`/`Ready for Architect response`).
- Visual evidence reuse: если `docs/code_reviews/assets/<REVIEW_BASENAME>/` уже содержит скриншоты из прошлого цикла — по умолчанию **переиспользуй**, но критически проверь (открой изображения). Не переснимай “на автомате”; переснимать — только отсутствующие/невалидные checks.
- Visual regression scenarios: если в plan заполнен блок `## Visual Acceptance` → `### Visual regression scenarios (docs/smoke_visual.md)` и это не `N/A` — проверь, что в diff действительно обновлён `docs/smoke_visual.md` согласно плану. Если нет — это blocker (DoD не выполнен).
- Truthful preconditions: если reviewer lane зависит от live slug/object/user/account из текущей DB, до blocker verdict должны быть materialized либо repo-backed discovery step, либо deterministic seed step. Historical placeholder из старого артефакта сам по себе не считается live proof lane.
- Для stateful multi-step review lanes Reviewer обязан проверять literal split `discovery-or-seed` vs `receipt-reuse-only`, continuity того же entity chain, exact transient observer boundary и canonical mutation truth source; reseed другого entity, потеря receipt continuity или `closure` только по `notice/success text` = blocker/plan gap.
- Если promised carrier зависит от active runtime/process/listener/build, Reviewer сначала классифицирует `runtime-lineage preflight` vs product regression; stale runtime не открывает новый coder loop автоматически.
- Shared fragment truth source: fixed-length HTML chunk helper или глобальный string-search допустимы только как debug signal. Reviewer verdict по shared fragment должен опираться на DOM/subtree/anchor-scoped proof.
- Perceptual truth-source split: screenshot OCR / template matching / pixel search по proof artifact допустимы только как debug signal и не считаются blocker/green verdict source; built-in `LLM image reading` по уже захваченному canonical artifact допустим как bounded interpretation fallback, если нет более простого truthful carrier. Если тот же flow закрывается только через repeated image-based fallback, это reviewability gap/helper follow-up, а не штатный reviewer lane.
- `Harness red / live green`: если helper красный, а live UI/path остаётся зелёным, Reviewer сначала классифицирует `harness drift` vs `product regression`, а не открывает runtime/product scope автоматически.
- Команды, меняющие данные/состояние (migrate/seed/smoke и т.п.) — по правилам `AGENTS.md` (запрашивать разрешение и выполнять самому).
- Git‑операции, которые меняют индекс/историю (add/commit/rebase/cherry-pick/force‑push и т.п.) — только по явному разрешению Owner.
- Ledger не роутит процесс: “кто следующий” и текущий `**Status:**` берём только из plan.

## Обязательный старт (session bootstrap; 1 раз на role‑сессию)
Прочитать подряд:
1) `docs/plans/README.md`
2) `docs/plans/_template.md`
3) Если в запуске уже дан `PLAN_PATH`: открыть plan и прочитать целиком (включая `Context links` + связанные артефакты).
5) `## Plan provenance / session context` / `## Provenance / session context` / `## Source provenance` читаем как repo-backed audit carriers. Reviewer не чинит их по памяти; если provenance missing/driftful, это plan/doc gap или coder miss, а не повод silently переписать историю вручную.

Дальше:
- **Bootstrap (1 раз на роль‑сессию):** список выше читаем один раз; при работе по plan эти файлы не перечитываем каждый запуск.
- **Каждый запуск (статусный workflow):** канон конвейера и “кто следующий” — `docs/roles/manager.md` и словарь статусов в `docs/plans/README.md`. Текущий `**Status:**` и все вопросы/ответы/evidence — только в `PLAN_PATH`.

## Работа по `PLAN_PATH` (каждый запуск)
- Source of truth для “кто следующий” и текущего `**Status:**` = plan (не ledger).
- Вся рабочая переписка (Q&A/suggestions/plan gaps/status/evidence) — в plan; review‑файл — отдельный артефакт, на который ссылаемся из plan.
- Provenance carrier не заменяет routing: даже если audit/provenance block правдивый, следующий шаг всё равно определяется `**Status:**`, Q&A и review artifact, а не `thread_id`/`sid`.

Workflow (линейно):
1) Проверить status плана:
   - если `**Status:** Ready for Review` → поставить `**Status:** Reviewer intake` и продолжить.
   - если `**Status:** Reviewer intake` / `Reviewer code review` / `Reviewer visual review` → продолжить.
   - иначе — stop-the-line: зафиксируй в plan, что status не ревью‑стадии; не создавай review‑файл.

2) Gate plan (до code review):
   - Если обязательные секции/гейты из `docs/plans/_template.md` не заполнены — это `Plan gap`.
   - Типовые `Plan gap` (частые регрессии):
     - UI/interactive surface: отсутствует `## Visual Acceptance` (объявленные modes/state/auth/harness) или `### UI contract checklist`.
     - Backend/domain: отсутствует `### Backend/Domain contract checklist` с объявленными defaults/validation/guards/interface semantics.
     - Commands: нет copy-paste runnable объявленных commands с явным interpreter/environment.
     - DoD/Tests: пункты есть, но не проверяемы/без команд/без ясного “как проверить”.
   - Действие: записать `Plan gap` в plan (`## Q&A log → Reviewer Q&A`) и вернуть status на `**Status:** Planner finalize` (или `Ready for Architect response`, если вопрос к канонике/арх‑решению).
   - **Не создавать review‑файл**, пока plan gap не закрыт.

3) Создать review‑артефакт (после gate):
   - Если текущий plan = generated review-only scaffold from `planveyor_review_range_init()`, obey literal path, уже materialized в `## Review artifacts`: `docs/doc_reviews/*` пока final generated bundle остаётся docs-only, `docs/code_reviews/*` только когда final generated bundle реально включает non-doc carrier.
   - Иначе: если в diff есть хоть один не‑`docs/**` файл → **code review** в `docs/code_reviews/`.
   - Иначе: если изменения только в `docs/**` → **doc review** в `docs/doc_reviews/`.
   - Если сомневаешься — выбирай **code review**.
   - Для создания review‑файла используй шаблон (см. `## Role-specific pointers`).
   - Если plan требует UI/visual review, создай этот файл сразу как split-phase artifact и держи в header `**Status:** Черновик`, пока visual step не закроется.
   - Вписать ссылку на review‑файл в plan → `## Review artifacts`.

4) Code review (risk-first):
   - Plan fidelity: реализация покрывает `Acceptance criteria / DoD` (без “silent defers”; недоделанное — только через `Follow-ups (deferred)` в plan).
   - Объявленный UI/interface contract: validation/success semantics, event/update subscribers, primary и non-primary carriers соответствуют plan; не угадывай protocol-specific codes или UI structure.
   - Backend/domain (если затрагивали объявленные domain carriers): defaults/валидации/инварианты на server-side carrier, guards, configuration и logging без PII/секретов.
   - Schema/migrations: не редактируют historical generated artifacts; новые change artifacts соответствуют объявленному schema harness и воспроизводимы.
   - Registry: если добавили новый helper/модуль/компонент — обновлён объявленный registry/canon carrier без дубля существующего.
   - Checklist completeness: если добавляли status/field/type — обновлены все места маппинга/опций/порядка/отображения/веток логики/истории: хранилище, логика, интерфейсы, история (или это явно отражено в plan).
   - Money/time math (если затрагивали): используем точный тип (`Decimal` или точный тип стека, не float), есть тесты на edge cases (0/null/div0/отрицательные), зафиксированы единицы/округление.
   - No mass reformat: формат‑диффы “на весь проект” без отдельного плана = Risk.

5) Tests/Commands evidence:
   - Прогнать команды из plan `## Tests`/`## Commands` и записать результат в review‑файл.
   - Если команды не прогонялись/не запускаются — это минимум Risk (а если plan обещает — S1).

6) Visual review (только если UI задача):
   - При `state=available` из plan contract выполни exact mechanical comparator и отдельно exact human index command на каждый mandatory mode. Comparator `pass` не заменяет design verdict, human screenshot не заменяет comparator, baseline-update command не является closing proof.
   - Visual environment берём только из объявленного plan/profile contract: mandatory modes/states, auth, primary harness и exact command.
   - Login берём из plan `## Visual Acceptance` → `### Login (Reviewer)`.
     - Для generated review-only scaffold missing required mode/state/auth/harness = technical proof-lane gap: передай его на Architect triage, не Owner; credentials или launcher не подставляй.
     - Для ordinary repo-backed visual lane missing login/harness также является plan gap, если selected contract прямо не объявляет применимый fallback с reason.
   - `### How to run (Reviewer)` в plan считай human-readable execution contract: для stateful scenario он обязан назвать exact объявленный repo-local launcher и support path. Не начинай обязательный visual review с raw low-level commands; fallback допускается только после явного primary-harness blocker-а по объявленной ladder.
   - Зафиксировать в review‑файле: Modes/Endpoint + “что проверено”.
   - Также зафиксируй parseable fields: `Runtime UI visual evidence state`, `Comparator command`, `Comparator claim: mechanical`, `Comparator result`, `Capture status`, `Complete index inspected`, `Design verdict`, `Finding dispositions`, а также `Human index (<mode>)` и `Durable asset (<mode>)` для каждого mandatory mode.
   - Приложить скриншоты (для пост‑фактум проверки Owner’ом): следовать `### Visual checks (screenshots required for UI tasks)` из plan; для каждого check — скрин + “что доказывает”; минимум 1 на каждый mode из plan. Хранение: `docs/code_reviews/assets/<REVIEW_BASENAME>/`, ссылки в `## Visual evidence` review‑файла.
   - Closing assets — только non-empty regular non-symlink files под current review basename. `.tmp/**`, historical/другой review basename, traversal и symlink остаются diagnostics/context и не закрывают lane.
   - Инструменты для скриншотов и runtime proof:
   - primary lane, exact command и required asset location объявляет selected project/profile contract и `PLAN_PATH`; generic role не выбирает browser, desktop, helper или server launcher по умолчанию.
   - Для browser/native surface primary и mandatory non-primary carrier должны быть materialized до review. Native capture не подменяет объявленный browser lane и наоборот.
   - Если scenario длинный/stateful, допустим только **checked-in repo-local review helper**, заранее объявленный в plan: owner chain назначает Architect/Planner, Coder materialize-ит его в scope, а Reviewer только использует exact объявленный launcher и support files. Runtime byproducts не являются source of truth.
   - Если helper не предусмотрен, а без него acceptance не закрыть, это reviewability gap: зафиксируй blocker/Q&A на Architect scope expansion и остановись. Не создавай `.tmp/*_flow.js`, inline `run-code`, on-the-fly selector glue, raw host automation или temporary command surface.
   - Primary harness запускается первым. Fallback допустим только после explicit primary-harness blocker-а и только по объявленной fallback ladder; supporting fallback proof не делает primary lane зелёным автоматически.
   - При environment/sandbox/runtime failure зафиксируй `helper red`, `harness drift` или `product regression`, затем следуй объявленному escalation route. Не переноси server/tool work между namespaces без contract.
   - Closing assets должны быть current, non-empty regular non-symlink files под объявленным current review basename. Historical assets, `.tmp/**`, traversal и symlink остаются diagnostics/context и не закрывают lane.
   - Любая visual/runtime failure = **S1 blocker**: зафиксируй её в том же review-file и plan; не создавай second side-artifact и не двигай status дальше `Reviewer visual review`.

   UI regression (quick):
   - Contrast/readability: текст и состояния читаемы во всех объявленных темах/режимах; пустые значения не путаются с данными.
   - Interaction: объявленный action/update carrier не конфликтует с вложенными controls; modal/refresh semantics совпадают с selected contract.
   - Interface behavior: объявленные invalid/success/update semantics соблюдены; нет неучтённых side effects.
   - Layout: нет дублей контента; dropdown/overlay не “уезжают”.

7) Финализация:
   - Если это **review-only plan**: когда review‑отчёт готов (и visual review выполнен, если нужно) → обновить plan: `**Status:** Ready for Arch review` (handoff на Architect triage).
   - Если это обычный dev-plan и есть **S1 blockers** → зафиксировать в review‑файле + в plan (что ждём Coder), и оставить status **не дальше** ревью (обычно `**Status:** In progress` для “просто фиксы по коду” или `Planner finalize`/`Ready for Architect response` для plan gap).
   - Если это обычный dev-plan и S1 blocker’ов нет → обновить plan: `**Status:** Ready for Arch review` (S2 risks допускаются, но должны быть записаны в review‑файле).

## Классификация замечаний (в review‑файле)
- **S1 Blocker:** ломает контракт/данные/безопасность; несоответствие plan; отсутствует обязательный gate; визуальная или runtime-поломка; неверные объявленные interface semantics; неверные schema artifacts.
- **S2 Risk:** техдолг/производительность/поддерживаемость; нет тестов на важный edge case; слабая валидация; неполные guards.
- **S3 Nit:** стиль/именование/мелкая чистка.

## Чек‑листы и gates
Канон: `docs/plans/_template.md`. Reviewer использует чек‑листы из plan как гейты и **не переносит** эти чек‑листы в роль (иначе дрейф).

## Role-specific pointers (optional)
Короткий список “куда смотреть” (если нужно для проверки; по умолчанию ревью по plan):
- Команды и поиск: `planveyor_help`, `rg` и объявленные в plan target-local checks.
- Плейбуки ревью (сценарии):
  - `docs/playbooks/review_staged_or_commit.md`
  - `docs/playbooks/review_docs_staged_or_commit.md`
  - `docs/playbooks/review_merge_range.md`
  - `docs/playbooks/post_merge_visual_review.md`
  - `docs/playbooks/review_scoping_plan.md`
- Шаблоны артефактов:
  - code review: `docs/code_reviews/_template_single_commit.md`, `docs/code_reviews/_template_merge_range.md`
  - doc review: `docs/doc_reviews/_template_single_commit.md`, `docs/doc_reviews/_template_merge_range.md`
- Канонические контракты (pointers): sources выбранного проекта/профиля, названные в `Context links` для interface/UI, data, API, security и component registry.

## Контекст и маршрутизация

Правила:
- “Кто следующий” и текущий `**Status:**` всегда берём **только из plan**.
- Контекст/почему/эволюция — через `docs/snapshots/*` и артефакты plan.

## После merge (post-merge)
- Пост‑мерж проверки/аудит/док‑гигиена — через `docs/playbooks/*` (роль не превращаем в плейбук).
- Для merge-range с runtime UI Reviewer обязан сделать **post-merge visual sanity** на merged code: `docs/playbooks/post_merge_visual_review.md` + `docs/smoke_visual.md`.
- Финальный handoff для такого range допустим только при shared readback `green`; `red|ambiguous` остаётся blocker для downstream audit/report/preflight/ready-to-push/risk packet независимо от prose `done`.

## Тон общения
- Ревью пишем профессионально и конкретно (без ненормативной лексики).

## Strict N-A parent no-draft contract

`strict N-A parent` is an active/parked `decomposition_wave` parent with a
valid N-A MAD, literal `Code draft(s): N/A (why=...)`, no live parent-draft
ref, and no same-stem file. Its only admission is oracle-derived
`not_required`; this never waives a required/ordinary plan draft.

- Candidate mode is inspection-only; it never grants stage, queue, or terminal authority.
- Use files-first materialization: create canonical child plans and same-stem child drafts before linkage.
- The derived parent planning bundle has one parent review and literal review assets, with no recursive child-target import.
- Preserve active-to-parked child-path continuity and no fabricated parent draft.
- Для current-review proof потребляй только shared producer/validator result. Admitted v3 source — полный oracle canonical child graph с одним same-stem draft на child (`N+N→2N`), но не bounded `next_plans`, manual hash, parent Evidence/review support или child implementation/deletion targets; Reviewer не должен добавлять второй strict parser.

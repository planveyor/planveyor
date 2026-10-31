# Code draft: Revision continuation после коррекции general PI и runbook

**Date:** 2026-10-25 15:02 +0300
**Cluster:** process
**Related plan:** `docs/plans/261025_1408_general_pi_closeout_revision_and_runbook.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261025_1408_general_pi_closeout_revision_and_runbook.md",
    "cluster": "process",
    "targets": [
      {"path": "scripts/docs_closeout.py", "kind": "py"},
      {"path": "scripts/test_docs_closeout.py", "kind": "py"},
      {"path": "scripts/test_followups_capture.py", "kind": "py"},
      {"path": "scripts/test_planveyor_bare_entrypoints.py", "kind": "py"},
      {"path": "docs/tools/owner_runbook_codex.ru.md", "kind": "doc"}
    ],
    "deleted_paths": [],
    "machine_authority_decision_ref": {
      "applicability": "not_applicable",
      "reason_code": "unchanged_structured_consumer",
      "carrier_sha256": "a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39"
    }
  }
}
```

## Provenance / session context
- Source plan provenance: `docs/plans/261025_1408_general_pi_closeout_revision_and_runbook.md#Plan-provenance--session-context`
- Relation: `created-here`
- Thread ID: `<REDACTED>`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-25T12:01:04Z`

Поля получены текущим `planveyor_plan_provenance_context --section code-draft --session-key planner`, rc=0. Origin plan не переписывается; неизвестный SID не восстанавливается из chat memory. Ref взят из current validated oracle и public stub helper; semantic MAD core здесь не копируется.

## Purpose
Закрыть расхождение producer/schema для `receipt_revision=1+N` проверенных correction records и проверить полный retained payload штатным consumer. Второй независимый пункт — точный внешний RU blob и актуальные test expectations при неизменном EN. Реализация принадлежит Coder; draft фиксирует контракт и proof.

## Targeted changes (by file)
- `scripts/docs_closeout.py`: новое обязательное поле ready continuation proof `general_pi_format_corrections`; snapshot из уже проверенного aggregate, существующая pure validation records и точная формула до checkpoint. Non-ready/no-selector и marker/replay branches сохраняются.
- `scripts/test_docs_closeout.py`: `DocsCloseoutFormatCorrectionTests` / `DocsCloseoutContinuationAdmissionTests`; полный schema-green N=0/1/2, schema deny matrix и исправление существующего full-tail теста.
- `scripts/test_followups_capture.py`: `GeneralPIFormatCorrectionTests` / `FollowupsContinuationCheckpointTests`; retained consumer после correction, same-cycle readback/replay, stale/tampered и zero-mutation доказательства без ослабления spent slots.
- `scripts/test_planveyor_bare_entrypoints.py`: только `BareEntrypointsDoctorTests.test_owner_runbook_documents_selected_gate_claims` и необходимые локальные assertions актуального EN/RU gate wording.
- `docs/tools/owner_runbook_codex.ru.md`: exact bytes согласованного blob, без редактирования или restamp.

`scripts/test_shards.json` — read-only context: `test_followups_capture` целиком в `s10`, `test_docs_closeout` в `s13`, `test_planveyor_bare_entrypoints` в `s14`. Новые методы внутри этих modules автоматически входят в partition. Нужда менять split-module selector или иной файл требует owning reroute/restamp до widening; этот draft такого изменения не разрешает. Plan, draft и единственный future review artifact добавляются helper-ом в final bundle отдельно.

## Receipt schema emitter inventory
Receipt family: `docs_closeout_payload.v1` → `followups_continuation_admission.v1`; единственное changed payload field — `proof.general_pi_format_corrections`.

| Emitter / parser / consumer | Target decision и обязательный proof |
|---|---|
| `scripts/docs_closeout.py::FOLLOWUPS_CONTINUATION_PROOF_KEYS`, `classify_followups_continuation_admission`, `_validate_followups_continuation_admission` | В targets. Producer готового proof и exact schema меняются вместе; fresh N=0/1/2 payload, missing/unknown/malformed snapshot и revision mismatch проверяются публичным validator. |
| `scripts/docs_closeout.py::classify_docs_closeout`, `finalize_docs_closeout_payload`, CLI JSON output, `render_text` / dispatch summary | В том же target; admission передаётся целиком, schema summary строится после validation. Full-tail regression требует top-level `schema_state=ok`, `schema_errors=[]`, а forced nested ready при invalid proof остаётся blocked. Нового field parser или permit из summary нет. |
| `scripts/docs_closeout.py` initial/non-ready continuation envelope и `_followups_bootstrap_admission_payload` | `N/A (why=these emitters do not create ready continuation proof)`; сохраняются `proof=null`, `next_dispatch=null` и существующая no-selector compatibility. Отдельный bootstrap family не меняется. |
| `scripts/followups_capture.py::begin_cycle`, reservation writer, `_response`, `_validate_receipt_object`, `_validate_general_pi_format_corrections` | `read-only context with N/A (why=aggregate schema, writer, slots and record validator are unchanged)`. Producer использует уже validated aggregate; public validator вызывает существующую pure record semantics на bounded projection. |
| `scripts/followups_capture.py::_revalidate_continuation_admission`, `checkpoint_general_pi` | `read-only context with N/A (why=full fresh admission equality already includes every proof field)`. Primary retained regressions обязательны для corrected N=1/2, current bytes/object/source и replay. |
| `scripts/sibling_closeout.py::_docs/_completed`, `scripts/sibling_runbook.py::show_plan` | `read-only context with N/A (why=existing schema-green full-payload readback and correction presentation are unchanged)`. Contextual runbook tests проверяют red/unknown и отсутствие write/child side effects. |
| `scripts/planveyor/role_runtime.zsh` | `read-only context with N/A (why=dispatch path unchanged; selector transport does not construct or parse ready proof fields)`. Existing public shell tests сохраняют format-correction/continuation compatibility; нового command surface нет. |
| `scripts/test_manager_custom_pipeline_prompt_contract.py` continuation grammar text и contextual shell fixture | `read-only context with N/A (why=grammar assertion and live helper readback are not independent ready-proof emitters)`. Synthetic ready skeleton вне primary modules не обнаружен current literal source search. |

Owner-facing generated skeleton/bootstrap/readback emitters перечислены выше; отдельного ready-proof generator нет. Existing canonical record validator — authority records; skeleton/test/readback не создают новую schema authority.

## Patch sketch (keep it small)
1. Сохранить exact ready proof key set, добавив только record snapshot. Для historical absent carrier вывести `null`; для существующего пустого map — `{}`; malformed present carrier не нормализовать.
2. В pure validator построить bounded receipt projection: subject `plan_ref`, `capture_cycle_id`, `receipt_revision`, `plan_sha256` из validated identity/source, `transaction_host_identity`, точный records map. При `null` опустить records key только в этой проекции. Использовать `_validate_general_pi_format_corrections`; N считать только после успешной проверки.
3. До checkpoint допускать ровно `revision == 1 + N`. После checkpoint сохранить `revision == prior_receipt_revision + 1`; records также должны проходить прежнюю validation. Public schema остаётся pure: никаких FS/Git/stat/open/read.
4. Усилить текущий `test_corrected_cycle_reaches_ordinary_compact_terminal_noop`: assert полного payload `schema_state=ok/schema_errors=[]`, передать этот же сохранённый payload в `checkpoint_general_pi(..., docs_closeout_payload=payload)`, прочитать canonical receipt и затем ordinary compact terminal `completed/no_op`.
5. Через existing fixtures покрыть N=0, N=1 и две разные роли N=2; retained replay и отказы проверять по canonical bytes/object readback того же cycle. Не создавать checked-in fixture/history carriers.
6. До переноса RU связать `RUNBOOK_SOURCE_ROOT` с exact read-only root из current `G.md`; проверить `04ce6af:docs/tools/owner_runbook_codex.ru.md` → blob `ec971593ff50e38edeb58cffa6ad91ed8dc61947`, затем перенести bytes. Missing binding/ref/blob — STOP, без другого checkout. EN SHA-256 обязан остаться `2685f36f96ebeff256df209dc0d6a3f187625c60e244f38aad4fac974ccd0e60`.
7. В runbook-тесте проверять оба текста: strict first `--preflight`, inventory/integrity `--scope-check`, `scope_ok=true` без green/route/commit permission и strict final `--check`. Снять только старые противоречащие ожидания.
8. Прогнать только selectors и lint из plan `## Commands`; финализировать test diff, выполнить единственный Coder coverage check и связать его с неизменными inputs. До `Ready for Review` нужны все primary/contextual lanes; старый runtime не является candidate-source proof.

## Reviewability preflight receipt
- `proof-path class`: `checked-in repo-local helper`; candidate-source regression в synthetic temporary Git fixtures и structural JSON/bytes readback.
- `mandatory primary lane`: три полных адресных modules `test_docs_closeout`, `test_followups_capture`, `test_planveyor_bare_entrypoints`; schema-green retained N=0/1/2 → штатный checkpoint → same-cycle canonical receipt, deny matrix и pure-schema proof.
- `mandatory non-primary carrier / contextual lane`: `test_sibling_runbook.GeneralPICorrectionRunbookTests`; два exact shell IDs из plan; exact RU blob, неизменный EN, RU doc/i18n checks. Shell N=0 compatibility и correction dispatch не подменяют primary corrected retained-payload proof.
- `exact helper path + support files`: `scripts/docs_closeout.py`, read-only `scripts/followups_capture.py`, `scripts/run_test_shard.py`, `scripts/test_shards.json`, `scripts/run_doc_lint.sh`, `scripts/i18n_pairs.py`; новых helpers/support files нет.
- `dependent tests / dependent docs / known consumer paths`: mutable tests и RU выше; unchanged EN; `scripts/sibling_closeout.py`, `scripts/sibling_runbook.py`, `scripts/planveyor/role_runtime.zsh` — read-only dependent consumers. Новый Manager command/one-shot behavior: `N/A (why=dispatch path unchanged)`.
- `preconditions / seed-discovery`: existing `DocsCloseoutContinuationAdmissionTests._fixture` и `GeneralPIFormatCorrectionTests.fixture/reserve/payload` создают subject/cycle, typed no-effect refusal и reservation. N=2 резервирует две разные роли. После discovery — `receipt-reuse-only`, без silent reseed.
- Stable identity: `plan_ref`, `capture_cycle_id`, source/semantic identity, role-map/reservation IDs, receipt revision/raw hash/object identity, cycle/transaction identities.
- Observer boundary: до checkpoint — сохранённый полный payload; mutation truth — next canonical receipt того же cycle. N=0: `1→2`; N=1: `2→3/prior=2`; N=2: `3→4/prior=3`. `notice/success text != mutation truth`. Повторный retained replay получает fresh post-checkpoint payload, прежние bytes/objects не меняются.
- `reroute rule`: invalid/stale/missing proof или current-byte/CAS mismatch → existing отказ без mutation; новые mutable paths/authority/consumer semantics → owning Architect; runtime lineage/permission/infra drift и реальная correction general PI самого Г → special STOP plan, без retry/switch/manual checkpoint.
- `perceptual truth-source split`: `N/A (why=structured JSON and exact bytes; no UI or screenshot acceptance)`.
- Runtime-lineage preflight: source branch/base и чистый immutable runtime-candidate на `7db73f17d8ff2d4eb6aa071bcc2cc0266a1e3c56` проверяются отдельно; runtime не меняется, candidate-source tests не выполняются его старым producer.
- Retention: fixture/`.tmp/g-tmp` — `transient local sanity only`; current review artifact и приватный operator journal — durable evidence. Raw private paths/logs/account/session reasoning в bundle не копируются.
- Substitute proof boundary: последовательные stale-instance/replay/CAS regressions доказывают отказ по existing optimistic guard; true concurrent process proof и новые constraints не заявляются и для этого revision-only fix не требуются.

Truth-host fixture matrix:
- `authoritative_host`: aggregate receipt с validated correction records и canonical collector receipts того же subject/cycle.
- `derived_summary_field`: continuation admission, top-level schema summary, checkpoint response/readback.
- `green_case`: N=0/1/2, exact formula, тот же retained payload и canonical post-checkpoint receipt.
- `missing_case`: missing proof/original bytes/hash/record → schema/consumer отказ без mutation.
- `ambiguous_case`: duplicate slot/ID или noncontiguous reserved revisions → отказ.
- `present_but_red_or_inconsistent_case`: nested ready плюс invalid schema, stale record snapshot или changed current receipt/object/source → отказ.
- `expected_fail_closed_verdict`: `schema_state=blocked` или existing `followup_capture_continuation_admission_invalid` / record-validation error; derived ready не перекрывает mismatch.

## Tests / proof selectors
Execution commands — точные copy-paste строки plan `## Commands`, единый trusted `"$PYBIN"`, `TMPDIR="$PWD/.tmp/g-tmp"`; facade только объявленный absolute runtime с `--project "$PWD"` и `env -u PLANVEYOR_CODEX_HOME`. Новых wrappers, environment selectors или config нет.

Первый executable Planner handoff требует canonical plan lint и strict `planveyor_plan_bundle --preflight`. Planned review artifact допустим только до Reviewer; итог требует strict `--check`.

Обязательная regression matrix:
- Existing `test_corrected_cycle_reaches_ordinary_compact_terminal_noop` + N=0/1/2 schema/retained checkpoint/replay.
- Exact null/empty map, missing/unknown/malformed proof, role/record keys, bool/invalid/wrong revision, original UTF-8/hash/object/source/host, duplicate reservation ID и noncontiguous revisions.
- Corrected retained payload stale/tamper/current bytes/source/object drift → receipt/protected fixture bytes и spent slots unchanged.
- Pure schema по уже построенному payload при запрещённых FS/Git reads; non-ready/no-selector compatibility.
- Existing crash/lost-result/reentry/spent-slot и slot-per-role guards сохраняются; runbook assertions обновляются только под exact current texts.

## Coverage ownership and receipt reuse
**Единственный producing role — Coder.** Ровно один `scripts/run_test_shard.py --check` после final execution test/manifest diff и всех test edits. Planner intake/finalize, любой CENSOR, Reviewer, Architect и Manager эту команду не выполняют; они читают один Coder receipt.

Перед check Coder сохраняет exact argv, SHA-256 test inputs/runner/manifest, current diff selectors и `git diff --exit-code -- scripts/test_shards.json` (ожидается пустой diff). До/после одного check использует одну команду `shasum -a 256 scripts/test_*.py scripts/test_shards.json scripts/run_test_shard.py` и сверяет outputs. Receipt содержит фактический child rc/duration, stdout `manifest_sha256/canonical_tests/shards` и refs на обе совпадающие input inventories; `--report` не используется. Coverage check импортирует discovery и проверяет partition, но не выполняет tests. Если inputs изменились после check или check красный — existing receipt не считается green; автоматического второго check нет, требуется Owner routing.

## Review route
- `Primary artifact`: `docs/code_reviews/261025_1408_general_pi_closeout_revision_and_runbook.md`
- `Lane type`: `code review`

Единственный current code-review host пока `PLANNED`; создаёт Reviewer, Architect дописывает arch review туда же. Scope включает пять exact targets; никаких параллельных doc-review hosts. `BUNDLE=current` proof materialize-ится штатным helper/reviewer по target snapshot, не ручным hash.

## Critical invariants / traps / bypass paths
- `Invariant: validated records, not arbitrary count`. Trap: `revision>=1` или whitelist `1|2`; bypass закрывает N=2 и corrupted record matrix.
- `Invariant: schema green is required, current equality is separate`. Trap: nested ready либо checkpoint без retained payload; bypass закрывает full payload→consumer→canonical receipt и corrected stale/tamper tests.
- `Invariant: spent correction slot remains spent`. Trap: fresh retry/reseed или count normalization; existing slot/crash/reentry guards и protected-byte comparison остаются обязательными.
- `Invariant: immutable runtime and exact external bytes`. Trap: старый runtime green как acceptance либо RU restamp ради теста; отдельные source/runtime и blob/EN/i18n checks.

## Assumptions / risks
- Trusted launch inputs и read-only RU root уже заданы Owner; отсутствующий binding — STOP.
- Application schema/API/DB/UI, target adoption, global/home config, new correction slots и runtime install — вне scope.
- Неустранённый owning ролью red lint/preflight и прочие current STOP действуют без обходов; `Done`, stage/commit и docs-closeout tail принадлежат следующим owning ролям.

## Notes for Coder
Plan — semantic source of truth; draft задаёт exact bundle и mechanics. Если существующей pure record функции недостаточно без изменения другого carrier, верни owning blocker Architect до правок scope. Не меняй read-only manifest/consumers/EN, не переоткрывай historical plan и не переносись на другой checkout/runtime.

## Review stamps (append-only)
- [2026-10-25 15:02] (Planner) Создан executable contract: пять literal targets, validated derived MAD ref, единственный review route, primary/contextual proof и sole Coder coverage producer. Implementation и execution proof ещё не выполнены.
- [2026-10-25 15:07] (Planner) NO SUGGESTIONS (reviewed; no changes required). Проверен финальный contract после materialization; новых scope решений нет.
- [2026-10-25 17:22] (Planner) NO SUGGESTIONS (reviewed; no changes required). Current plan и `OWNER_TECHNICAL_DELEGATION_Q2.txt` перечитаны; разрешённая correction/audit закрыли Q1/Q2. Restamp сохраняет пять exact targets, `deleted_paths=[]`, sole code-review route, proof/selectors/steps и sole-Coder reserved check. Fresh oracle подтвердил прежний N-A ref `valid`, SHA-256 `a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39`; source target/read-only inventory не менялся.
- [2026-10-25 17:22] (Planner) Текущий `planveyor_plan_provenance_context --section code-draft --session-key planner` rc=0, captured `2026-10-25T14:22:13Z`: тот же exposed Thread ID, SID и launch surface по-прежнему helper-reported `N/A/unknown`. Origin carrier выше сохранён; отсутствующие значения не заполнялись из Manager summary/chat memory. First strict preflight остаётся отдельным fresh gate после restamp.
- [2026-10-25 17:27] (Planner) NO SUGGESTIONS (reviewed; no changes required). Отдельный Manager-dispatched CENSOR перечитал весь plan/draft: exact five targets, strict derived N-A ref, primary/contextual proof, observer boundary и sole-Coder reserved check сохранены; это review stamp, не implementation acceptance.

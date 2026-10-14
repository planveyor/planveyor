# Plan: Согласовать general-промпты и обработку отказа collector

**Date:** 2026-10-14 20:07
**Stage:** Stage 1
**Priority:** P0
**Plan type:** dev
**Status:** Done
**Schema version:** plan.v2

**Handoff statuses (кто ставит):**
- `Ready for Planner` — Architect
- `Ready for Coder` — Planner
- `Ready for Review` — Coder
- `Ready for Arch review` — Reviewer
- `Done` — Architect

**Context links (source of truth):**
- Target canon: `docs/plans/README.md`, `docs/guides/lifecycle-and-packets.ru.md`, `docs/tools/verify_suite.ru.md`.
- Process: `docs/tools/prompts/architect_draft_discussion.md`, `docs/tools/prompts/manager_collab_pipeline.md`.
- Parser: `scripts/process_improvements_collect.py`; четыре `docs/tools/prompts/*_docs_finalize_general.md` и соответствующие копии `copier_template/docs/tools/prompts/`.
- PI canon и проверки: `docs/process_improvements/README.md`, `scripts/test_process_improvements.py`, `scripts/test_manager_custom_pipeline_prompt_contract.py`, `scripts/test_sibling_contract_docs.py`.
- Доставка и mirror policy: `scripts/shared_docs_mirror_drift.py` (`load_shared_docs_mirror_policy`: generic policy не объявляет внешний target); `scripts/test_sibling_contract_docs.py` проверяет побайтные source/copy пары и private fingerprint.
- Related context: `docs/release_backlog.md#f14` (item_id `pi-collector-fd-layer`, отдельная от этого плана граница; row не продвигается).
- Related open row: `docs/release_backlog.md#f14#pi-collector-fd-layer` в `docs/followups/release_backlog.md`; исходные `source_ref=docs/release_backlog.md#f14`, `item_id=pi-collector-fd-layer` сохраняются без promotion/backlink.
- Code draft(s): `docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md` (Planner-owned exact executable contract).
- Read-only consumer/proof anchors: `scripts/followups_capture.py:admit_active_general_pi_collection`, `scripts/followups_capture.py:general_pi_capture_receipts_proof`, `scripts/docs_closeout.py:classify_process_improvement_capture`, `scripts/contract_authority_bridge.py`, `Makefile`, `docs/playbooks/role_prompt_invariant_map.md`.
- Golden Path: N/A (why=existing registry has no general collector correction entry; ordinary single-plan contract is used).
- Process ADRs: `docs/adr/001-plan-path-single-semantic-source-of-truth.md`, `docs/adr/003-single-live-review-route.md`, `docs/adr/004-exact-bundle-truth-and-closeout.md`.
- Rollout packet(s): N/A (why=ordinary self-project plan).
- API / schema / UI: N/A (why=prompt and operator contract).

## Meta (machine-readable JSON; required for current plan.v2 plans)

```json
{
  "plan_meta": {
    "cluster": "process",
    "tags": [
      "general-prompts",
      "collector-contract",
      "manager-output"
    ],
    "required_manager_mode": "manager-collab",
    "wave_family": null,
    "phase_overlay": null,
    "phase_state": null,
    "parent": null,
    "next_plans": [],
    "depends_on": [],
    "machine_authority_decision": {
      "schema_version": "machine_authority_decision.v1",
      "applicability": "not_applicable",
      "reason_code": "unchanged_structured_consumer"
    },
    "queue_activation": {
      "state": "n/a",
      "source_ref": "N/A (why=initial draft is not queued)",
      "reason": "N/A (why=no executable child is admitted)"
    },
    "scope_expansion": {
      "state": "n/a",
      "target_contour": "N/A",
      "source_ref": "N/A (why=no scope expansion)",
      "reason": "N/A (why=initial draft has bounded scope)"
    },
    "canon_updates": []
  }
}
```

## Plan provenance / session context

- Relation: `continued-here`
- Thread ID: `N/A (why=private operator mapping is not published)`
- Parent thread ID: `N/A (why=private coordinator mapping is not published)`
- Session SID: `N/A (why=current native role identity is retained in private operator evidence)`
- Launch surface: `manager-collab`
- Captured from: `manual-owner`
- Captured at: `2026-10-14T20:05:44Z`

## Documentation impact / provenance

- Source docs used: `docs/plans/_template.md`, `docs/plans/README.md`, `docs/guides/lifecycle-and-packets.ru.md`, `docs/tools/verify_suite.ru.md`, `docs/adr/001-plan-path-single-semantic-source-of-truth.md`, `docs/adr/003-single-live-review-route.md`, `docs/adr/004-exact-bundle-truth-and-closeout.md`, четыре general-промпта, `docs/tools/prompts/manager_collab_pipeline.md`, `docs/process_improvements/README.md`; прочитаны соответствующие parser/receipt и адресные test carriers.
- Synchronous doc/registry targets: `docs/tools/prompts/architect_docs_finalize_general.md`, `docs/tools/prompts/planner_docs_finalize_general.md`, `docs/tools/prompts/coder_docs_finalize_general.md`, `docs/tools/prompts/reviewer_docs_finalize_general.md`, `docs/tools/prompts/manager_collab_pipeline.md`, `copier_template/docs/tools/prompts/architect_docs_finalize_general.md`, `copier_template/docs/tools/prompts/planner_docs_finalize_general.md`, `copier_template/docs/tools/prompts/coder_docs_finalize_general.md`, `copier_template/docs/tools/prompts/reviewer_docs_finalize_general.md`, `copier_template/docs/tools/prompts/manager_collab_pipeline.md`, `docs/process_improvements/README.md`.
- Post-merge canon updates: N/A (why=required contract wording changes synchronously).
- Deferred documentation follow-ups: N/A (why=no new deferred documentation item introduced).
- Provenance refs: поручение Owner от 2026-10-14; приватный согласованный brief А1 (И1 + И3а), без публикации служебных идентификаторов.

Все 11 synchronous doc targets входят в `code_draft_meta.targets`; ещё два target — объявленные Python tests. Registry update N/A (why=no new helper). Private fingerprint — read-only проверка `test_delivered_files_carry_no_private_fingerprints` в `scripts/test_sibling_contract_docs.py`, отдельного writable carrier нет; pinned local-section hashes этот scope не меняет.

## Problem

1. Нижний образец PI в general-промптах Architect, Planner и Coder содержит свободную прозу, которую строгий parser отвергает. Структурированный пример Reviewer корректен сам по себе, но весь нижний пример содержит поясняющую строку, не являющуюся ответом.
2. Все четыре промпта одновременно поручают роли записывать durable PI, хотя запись принадлежит collector Manager.
3. При ошибке collector потребитель может попытаться разобрать plain-text stdout как JSON. Ошибка транспорта не является действительной квитанцией и не даёт разрешения продолжать.

## Как я понял задачу

Согласовать четыре general-промпта и их копии с существующим строгим parser.
Роль возвращает структурированный PI либо точный no-op; durable PI записывает existing collector, который вызывает Manager.
В фактической general-ветке collab Manager проверяет rc и форму stdout до JSON.parse, затем читает только валидный текущий helper receipt/admission; отказ остаётся STOP с исходной причиной.
Обычный dev-conveyor продолжается в текущем Manager TUI через существующие native-роли до точного коммита и terminal docs-closeout.
Scope И1 + И3а уже принят; повтор роли, recovery, широкая типизация, scanner и другие релизные планы остаются за его границей.
Новых Owner-решений не требуется; переход в draft завершает template completion / plan hygiene после предусмотренной технической контрольной точки.

## Solution (high level)

1. Роль выдаёт только разрешённую структуру PI либо точный no-op; collector Manager остаётся единственным durable writer.
2. Все примеры и их доставляемые копии проверяются вызовом настоящего parser. Свободный хвост не удаляется и не превращается в no-op.
3. В существующей ветке после каждого general output Manager сохраняет полный tool result, сначала проверяет фактический rc и пригодность stdout как одного JSON object без произвольного prefix/suffix, затем выполняет guarded JSON.parse и проверяет форму существующих полей. Продолжение требует rc=0 и `process_improvement_capture_state=clean_noop|materialized|already_tracked` для exact current cycle. При отказе действующая current receipt/admission используется только для доказанного объяснения причины; nonzero, malformed или неизвестный результат не превращается в разрешение продолжить. Отсутствие/дрейф proof означает STOP с исходной причиной и доступной квитанцией, без повторного dispatch.

## Decisions (final)

- Scope принят Owner: И1 + И3а. Новых продуктовых решений для подготовки А1 нет.
- Strict parser сохраняется. Нельзя «починить» пример ослаблением parser или удалением ошибочной прозы.
- Коммит реализации делает Architect штатным путём после exact bundle/review. Отдельный коммит начального draft не требуется. Docs commit нужен только при `final_docs_commit=required`; `no_op` допустим.
- Runtime неизменен весь план; general-промпты закрытия читаются из проекта, Manager/helpers — из runtime. Изменение И3а действует после перехода на следующий проверенный runtime. Если закрытие А1 блокируется, STOP; следующий план не служит обходом.
- Decision lifecycle: согласованный scope — accepted Owner input; exact contract и machine-authority admission оформляет Architect до downstream handoff. Переход в Architect draft не является executable/enforcement receipt.
- Authority pre-write check: состояние решения — accepted, canonical semantic writer плана — Architect; downstream executable carrier — Planner-owned code draft. PI schema, parser, receipt/admission и единственный durable writer `scripts/process_improvements_collect.py` уже существуют и остаются неизменными. Промпт задаёт role/Manager поведение, адресные тесты доказывают его контракт; текст промпта и успешный тест сами по себе не являются runtime admission или квитанцией.
- Machine-authority decision: точный N-A `unchanged_structured_consumer`; А1 не создаёт новый machine carrier и не меняет authorization/routing/mutation/terminal semantics existing helpers. Planner связывает draft только с helper-derived `{applicability,reason_code,carrier_sha256}`; semantic core не копируется и не переизобретается.
- Bounded inventory: изменяемые carriers — десять prompt/source-copy файлов, `scripts/test_process_improvements.py`, `scripts/test_manager_custom_pipeline_prompt_contract.py`, `docs/process_improvements/README.md`. `scripts/process_improvements_collect.py`, `scripts/followups_capture.py`, `scripts/docs_closeout.py`, `scripts/contract_authority_bridge.py`, `scripts/test_sibling_contract_docs.py` — read-only contextual consumers/proof; их новый writer/schema/recovery diff не входит в А1. Существующий test carrier с именем custom проверяет также collab/general contracts; custom Manager prompt не меняется без отдельного доказанного same-contract dependency.
- Уточнение существующего guard: решение accepted в принятом И3а, author текущего prompt contract — Coder в пределах этого plan, consumer — native collab Manager; durable admission/writer остаётся за existing helpers. JSON stdout содержит existing поля `process_improvement_capture_state`, `process_improvement_capture_reason`, `process_improvement_receipt_path`, `followups_capture_cycle_id` со string values. Fresh collection также emits `input_sha256`, а replay projection может его не emit-ить: обязательная raw input identity берётся из validated v2 receipt, не выдумывается из stdout. Emitters — `scripts/process_improvements_collect.py:_collect_process_improvements` и `_v2_replay_response`; canonical readback — `scripts/docs_closeout.py` / `scripts/followups_capture.py`. Новые поля, schema и Manager-side receipt parser не вводятся.
- Порядок будущего exact closeout сохраняется: simulated Done lint до первого stage, exact stage/preflight до provisional Done, затем обычный lint записанного Done, restage/final preflight и один точный локальный commit. Отказ post-Done gate требует возврата owning non-Done bytes в plan/index без commit; Done не остаётся отдельной post-commit правкой. После успешного implementation commit terminal plan не дописывается; docs-closeout идёт отдельной helper-owned family.

## Scope

- Четыре `docs/tools/prompts/{architect,planner,coder,reviewer}_docs_finalize_general.md` и их доставляемые копии.
- `docs/tools/prompts/manager_collab_pipeline.md` и его доставляемая копия: проверка rc/stdout/current receipt до продолжения.
- Адресные existing test carriers `scripts/test_process_improvements.py`, `scripts/test_manager_custom_pipeline_prompt_contract.py`; минимальная синхронизация `docs/process_improvements/README.md`. Planner переносит этот bounded inventory в literal `code_draft_meta.targets`; новые helper/schema paths требуют upstream triage.

## Out of scope

Новый retry/admission writer, счётчик коррекции, broad JSON envelope, scanner, sibling facade, rebinding, миграция старых receipts, SQL, настройка аккаунта/окружения, публикация и push. `docs/tools/prompts/manager_custom_pipeline.md` и его копия — read-only context: same-contract зависимость, требующая их изменения, не установлена. Имя existing test suite не даёт права менять custom consumer. Если такая зависимость возникнет, Coder возвращает план Architect до расширения targets.

## Follow-ups (deferred)

Новых отложенных пунктов этим draft не создаётся. Ранее выделенные recovery/типизация и остальные релизные задачи остаются самостоятельными поручениями Owner; они не являются невыполненными AC этого плана. Контекст F7/F12/F13/F14/F24 в `docs/release_backlog.md` не разрешает расширять А1. Retrieval canon="process improvements", plans="collector", followups="collector" выполнен без query logs: canon привёл к `docs/process_improvements/README.md`, plans — только к текущему plan, followups — к `docs/followups/release_backlog.md` и row `source_ref=docs/release_backlog.md#f14`, `item_id=pi-collector-fd-layer`. Это отдельное упрощение I/O layer, не дубль результата И1+И3а; row остаётся `status=open`, `plan=null`, все disposition поля `null`. Совпадающий активный plan по И1+И3а не обнаружен; автоматический backlink/promotion не выполняется.

## Rollout packet handoff

- Role: N/A (why=ordinary self-project plan).
- Packet path: N/A (why=no cross-repo packet).
- Target repo: N/A (why=no cross-repo packet).
- Suggested target plan slug: N/A (why=no cross-repo packet).
- Queue after import: N/A (why=no import).

## Close-out routing

- Roadmap/queue sync: N/A (why=direct single-plan run; no queue or roadmap mutation).
- Follow-up sync: штатный capture новых findings; существующие backlog rows не переписывать.
- Next bounded slice: отдельный план recovery после terminal closeout и технической проверки нового runtime; автоматической активации нет.
- Terminal outcome: no — обе Reviewer lanes и Architect приняли candidate implementation; semantic Done и точный локальный implementation commit не заменяют fresh terminal docs-closeout с `final_docs_commit=no_op|landed`.

## Constraints / Assumptions


Self-Planveyor: отдельный рабочий checkout и чистый замороженный runtime одного Git common-dir; каждый вызов facade явно выбирает project. macOS и уже установленное окружение Python 3.12 выбраны через доверенный PATH; для Make/direct используется та же среда. Runtime TMPDIR — объявленный ignored каталог внутри writable scope проекта; system temp не используется. Техническая контрольная точка завершена оператором и подтверждена текущим Owner handoff. Личные пути, SID и actual настройки ходов остаются только в приватном журнале; их не заменяет название task. Runtime/env/config не меняются внутри А1.

## Risks / Open questions (summary)

Технический baseline подтверждён оператором; этот plan не повторяет bootstrap и не вводит новый lifecycle. Потеря текущего TUI/handle, authority/infrastructure failure, новый scope blocker или blocked terminal docs-closeout требуют STOP с primary evidence; ручного repair/rebinding/retry нет. И3а в замороженном runtime не становится активным во время А1: тесты проверяют candidate bytes, а исправления general-промптов доступны из проекта. Проверка candidate prompt contract не выдаётся за live adoption нового Manager guard.

## Reviewability preflight receipt

- `proof-path class`: `checked-in repo-local helper`.
- `mandatory primary lane`: адресные тесты извлекают именно нижние canonical/no-op output samples из всех четырёх working general-промптов, подставляют допустимые owner/class/source значения и вызывают настоящий `scripts/process_improvements_collect.py:parse_process_improvements_section`; PI предложение должно дать non-empty suggestions, no-op — no_process_improvements.
- `mandatory non-primary carrier / contextual lane`: те же восемь sample cases в доставляемых копиях; корректный полный `### Suggestion 1` плюс точная строка `Structured suggestion передана для штатного Manager collector; durable PI carrier этой ролью не записан.` остаётся `Unsupported line inside \`Process improvements\``/blocked без durable effect. Actual collab general consumer (`docs/tools/prompts/manager_collab_pipeline.md`, после каждого general output) получает матрицу success JSON, nonzero/plain-text, malformed/missing fields, missing/current mismatch receipt/admission, unknown error; проверка rc/shape предшествует JSON.parse, дальше только canonical helper readback, без Manager-side receipt parser.
- `exact helper path + support files`: read-only parser/collector `scripts/process_improvements_collect.py`, receipt/admission readers `scripts/followups_capture.py`, `scripts/docs_closeout.py`; test edits в `scripts/test_process_improvements.py`, `scripts/test_manager_custom_pipeline_prompt_contract.py`; parity/private fingerprint proof — `scripts/test_sibling_contract_docs.py`. Ни новый launcher, ни inline ad-hoc review automation не требуются.
- `dependent tests / dependent docs / known consumer paths`: четыре general-промпта и пять source/copy пар, фактическая collab general-to-collector ветка Manager, `docs/process_improvements/README.md`, перечисленные test/readback carriers. Collector остаётся единственным durable writer; роль и Manager не записывают PI row вручную. External mirror packet N/A (why=generic selected source mirror policy declares no external target); доставляемые copier copies входят в тот же source-owned bundle.
- `preconditions / seed-discovery`: `discovery-or-seed` — адресные synthetic fixtures в объявленном ignored TMPDIR, без secrets/SQL и без tracked sample corpus. `receipt-reuse-only` — реальные closeout шаги после helper-created current cycle: сохраняются plan/source, role, cycle и raw input digest; missing/stale receipt hard-fail, без rediscovery/reseed. `.tmp` outputs — transient local sanity only; plan/current review и explicit review assets — durable evidence. Runtime-lineage preflight использует frozen source identity и явный project; runtime-owning failure останавливает проход до product reopen. `notice/success text != mutation truth`: closure только fresh canonical docs-closeout/readback того же plan/cycle.
- `reroute rule`: при implicit/red обязательной lane downstream handoff не готов; смена scope требует Architect triage.
- `perceptual truth-source split`: structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up. Visual lane N/A (why=no visual surface).

### Exact observation boundary / field parity

- Порядок фактической collab general consumer branch после каждого role wait: сохранить полный tool result до terminal `exit_code` → проверить фактический rc → проверить stdout framing → guarded `JSON.parse` → проверить existing field shape/state/current cycle → применять только существующий collector/readback contract. Running result без exit code не является receipt; команда дочитывается через её session handle, а не повторяется. Nonzero никогда не допускает continuation, даже если stdout случайно содержит JSON.
- Framing допускает один JSON object с обычным внешним JSON whitespace; empty/plain-text, fences, произвольный prefix/suffix, второй JSON value, array/null/scalar запрещены. Guarded parse ловит syntax error, не извлекает подстроку и не отбрасывает error tail. Это guard потребителя, а не новая schema или parser роли.
- Existing обязательные stdout fields: непустые strings `process_improvement_capture_state`, `process_improvement_capture_reason`, `process_improvement_receipt_path`, `followups_capture_cycle_id`; state для успешного role collection — `clean_noop|materialized|already_tracked`, cycle literal-но равен retained current cycle. Не вводить whitelist остальных keys или новый required field. Fresh emitter `_collect_process_improvements` имеет `input_sha256`; `_v2_replay_response` может его не иметь. Raw input digest всегда принадлежит `process_improvement_capture.v2` и existing validator/readback, а не Manager-side parser.
- При refusal Manager сохраняет исходные rc/stdout/error и может вызвать только existing fresh `planveyor_docs_closeout <plan_ref> --followups-capture-cycle-id <capture_cycle_id> --json` для объяснения причины через helper-selected current receipt/admission. Результат также проверяется existing schema gate; missing/red/stale/wrong-source/role/cycle/input proof не заменяется pathname, stdout или historical receipt. Новый helper/ручной разбор receipt/повтор collector запрещены.
- До четвёртого general receipt aggregate `pending` с ещё не dispatched missing roles ожидаем и не является whole-family green. Уже текущий invalid/blocked receipt побеждает pending; после четвёртого role точный existing `checkpoint-general-pi` заново проверяет полный source/role/cycle/input/object chain до первого followups dispatch. Не требовать premature full-family admission после первой роли и не ослаблять checkpoint.
- `discovery-or-seed`: existing test fixture создаёт synthetic repo/cycle в объявленном ignored TMPDIR. `receipt-reuse-only`: production closeout использует только helper-created cycle и его receipts. Stable identity — project root, plan/source ref, exact role, retained cycle, raw-byte input digest; observer boundary — непосредственно terminal collector tool result и следующий canonical same-cycle readback, затем checkpoint перед первым followups dispatch. `notice/success text != mutation truth`; terminal sink — fresh capture-aware `final_docs_commit=no_op|landed` после whole family, не промежуточный stdout.
- `runtime-lineage preflight`: перед helper proof действует frozen runtime/source identity и явный selected project. Candidate prompt tests исполняют working bytes; они не доказывают применение И3а текущим frozen Manager. Runtime-owning failure требует STOP, без изменения runtime.
- `receipt schema emitter inventory`: changed validators/parsers/schema fields = N/A (why=existing receipt and parser schema remain unchanged). Read-only emitters/validators — `scripts/process_improvements_collect.py:_collect_process_improvements`, `_v2_replay_response`, `_validate_v2_capture_receipt`; readers — `scripts/docs_closeout.py:classify_process_improvement_capture`, `scripts/followups_capture.py:general_pi_capture_receipts_proof`. Target decision для каждого — read-only context with N/A (why=guard changes only prompt consumer and existing tests). Новый skeleton/bootstrap/schema emitter отсутствует.
- Command-surface fan-out: N/A (why=no owner-facing command or one-shot dispatch change); `scripts/planveyor/role_runtime.zsh` остаётся read-only contextual boundary, новый command/help target не появляется.

### Truth-host fixture matrix

- `authoritative_host`: canonical current `process_improvement_capture.v2` receipt, выбранный existing helper по plan/source, role и cycle; полный chain дополнительно проверяет existing checkpoint.
- `derived_summary_field`: collector stdout `process_improvement_capture_state` / `process_improvement_receipt_path`; это сообщение consumer, не заменитель durable receipt.
- `green_case`: rc=0, один object, existing fields валидны, current cycle совпадает; fresh и replay (включая replay без stdout `input_sha256`) сохраняют одну receipt authority.
- `missing_case`: green-looking stdout при missing current receipt либо missing field — STOP, без inferred proof.
- `ambiguous_case`: prefix/suffix/second JSON value или другой source/role/cycle — STOP, без substring extraction/latest fallback.
- `present_but_red_or_inconsistent_case`: green-looking stdout при current receipt `blocked/collector_error`, invalid digest либо stale/current mismatch — STOP; aggregate pending остальных ролей не скрывает authoritative red.
- `expected_fail_closed_verdict`: bounded docs-closeout blocker с исходной причиной и доступным canonical helper reason/receipt path; без retry, PI write или followups dispatch. Матрица в prompt suite проверяет literal consumer contract; live adoption нового Manager guard этим не заявляется.

## Changes (by area)

- Data/schema: N/A (why=no storage or receipt schema change).
- Logic/modules: `scripts/test_process_improvements.py` — parser-backed lower samples всех четырёх ролей/source-copy pairs, точный incident tail и отсутствие durable effect при отказе; `scripts/test_manager_custom_pipeline_prompt_contract.py` — контракт фактической collab general-to-collector ветки, порядок rc/framing/guarded parse/field checks и error matrix. Parser/receipt implementations сохраняются.
- Interfaces: в `docs/tools/prompts/{architect,planner,coder,reviewer}_docs_finalize_general.md` верхний PI contract, шаг о surfaced suggestion и нижний output sample дают один смысл: роль emit-ит только canonical structured PI либо exact standalone no-op, durable запись делает вызванный Manager collector; объяснения располагаются вне Process improvements. В `docs/tools/prompts/manager_collab_pipeline.md` уточняется фактическая general consumer branch после role wait; guard не заменяется общим disclaimer в другом разделе. Existing output fields/status enums не меняются.
- Config: N/A (why=no product configuration change).
- Docs: пять source/copy prompt pairs под `docs/tools/prompts/` и `copier_template/docs/tools/prompts/` меняются побайтно согласованно; `docs/process_improvements/README.md` кратко отражает единственный writer и fail-closed разбор tool result. Команды Manager/one-shot dispatch и их help N/A (why=no command or dispatch surface change); external mirror packet N/A (why=generic mirror set has no external target).

## Acceptance criteria / DoD

- [x] Canonical и no-op примеры всех четырёх ролей/копий действительно извлечены, конкретизированы допустимыми значениями и пропущены через parser.
- [x] Корректный блок с точным incident tail остаётся отказом; нет silent trimming и подмены предложения no-op.
- [x] Роль не пишет durable PI; Manager вызывает existing collector.
- [x] Фактическая collab general-to-collector ветка проверяет rc и ожидаемое JSON object framing stdout до guarded JSON.parse; после безопасного разбора проверяет existing required fields. Матрица включает success JSON, nonzero/plain-text, malformed shape, missing/current mismatch receipt/admission, unknown error. Helper-selected canonical receipt совпадает по source/role/cycle/input digest; stdout и pathname не являются authority. При отказе STOP с исходной причиной; нет silent trimming, no-op substitution или automatic retry.
- [x] Доставляемые копии и соответствующий fingerprint согласованы.
- [x] Обязательные проверки окончательного scope выполнены; plan/code draft/current review соответствуют exact bundle.

### Граница semantic Done и закрытия А1

Чекбоксы выше относятся к проверяемой реализации до semantic Done. Точный локальный implementation commit делает Architect после принятого review; затем Manager обязан теми же существующими ролями выполнить native terminal docs-closeout. Whole А1 завершён только по fresh capture-aware helper proof `final_docs_commit=no_op|landed`, а `required` запускает Architect final docs-only handoff. Этот post-commit operational gate не отмечается заранее и не требует редактировать immutable terminal plan. Один Done или коммит реализации А1 не закрывает; blocked docs-closeout означает STOP, переход к следующему плану запрещён.

### Backend/Domain contract checklist (required if touching data/logic/interfaces)
- [x] Ошибочные PI остаются отказом до durable effects; текущая квитанция не подменяется stdout или historical state.
- Config / storage / API migration: N/A (why=no change).

### UI contract checklist (required if touching UI)
N/A (why=no UI change).

### Handoff checklist (Architect → Planner; before `Ready for Planner`)
- [x] Architect проверил текущие carriers и материализовал machine-authority decision; scope/AC определены, admission проверен current oracle перед handoff (Evidence: Architect draft handoff).

### Handoff checklist (Planner → Coder; before `Ready for Coder`)
- [x] Code draft содержит 13 literal exact targets, обязательные lanes и команды; bundle preflight прошёл (Evidence: Planner finalize/preflight).

### Arch review checklist (Architect; before `Done`)
- [x] Один current review принят и подтверждает exact bundle; новых findings/follow-ups нет, существующие backlog rows не продвигаются.

## Visual Acceptance (browser, UI tasks)

N/A (why=no UI change).

## Tests

### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)
N/A (why=no UI/runtime layout or access change).

### Что написать / поправить
- `scripts/test_process_improvements.py`: извлечь нижний `Выход (в чат)` из четырёх source prompts и четырёх copies; взять только intended canonical/no-op sample до следующего H2. Заменить только placeholders на допустимые значения (`Suggestion 1`, supported owner/class/reason, current synthetic source ref); не удалять произвольную prose. Восемь canonical cases обязаны получить non-empty `suggestions`, восемь no-op cases — `state=no_process_improvements`, `suggestions=[]`. Raw lower sample после concretization передавать настоящему `parse_process_improvements_section`; пояснение `Либо...`/`или...` не должно оказаться частью intended role output.
- В том же existing suite: полный корректный seven-field block плюс точная строка `Structured suggestion передана для штатного Manager collector; durable PI carrier этой ролью не записан.` вызывает `Unsupported line inside \`Process improvements\``. Collector fixture подтверждает `blocked/collector_error`, сохранённый raw-input digest и отсутствие durable PI backlog/derived delta; parser implementation неизменен. Existing `test_collect_writes_blocked_receipt_for_malformed_structured_block` и cycle replay fixtures дают reusable harness, не новый helper.
- `scripts/test_manager_custom_pipeline_prompt_contract.py`: адресные assertions именно collab `После каждого general output` branch, а не общий disclaimer в preamble. Проверить порядок terminal rc → framing → guarded parse → existing fields/state/current cycle → canonical readback/STOP. Матрица — success fresh/replay, nonzero с plain-text и с JSON, empty/prefix/suffix/second value, syntax error, non-object, missing/нестроковое existing field, blocked/unknown state, wrong cycle, missing/red/current-mismatch receipt/admission, unknown error. Зафиксировать запрет manual writer/retry и отсутствие нового required stdout `input_sha256`. Это regression prompt contract; не выдать её за исполнение нового runtime.
- `scripts/test_sibling_contract_docs.py` не менять: прогнать existing byte-parity и private-fingerprint tests для доставляемых prompts. Существующие frozen local-section hashes не относятся к изменяемым general prompts/Manager и не рестампятся. Никакого отдельного fingerprint file.

### Что прогнать
Адресные existing suites `scripts/test_process_improvements.py`, `scripts/test_manager_custom_pipeline_prompt_contract.py`, `scripts/test_sibling_contract_docs.py` (source/copy parity и private fingerprint); declared Make routes `make verify`, `make doc-lint`, `make typecheck`, `make oss-release-scan` по candidate bytes, с тем же trusted Python/PATH и ignored TMPDIR. Это proof contract до реализации, ни один implementation test этим intake не засчитан. Не повторять неизменённый успешный прогон без нового основания.

## Commands

Из корня выбранного проекта; `PLANVEYOR_RUNTIME_ROOT` уже указывает на доверенный замороженный runtime:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_lint docs/plans/261014_2007_general_prompt_collector_contract.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261014_2007_general_prompt_collector_contract.md
bash scripts/run_doc_lint.sh --root docs/plans/261014_2007_general_prompt_collector_contract.md --root docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md
```

Declared implementation proof использует trusted `$PYBIN`, compatible PATH и объявленный ignored TMPDIR; личные значения в артефакт не переносятся. Планирует точный запуск Planner, после реализации выполняет Coder:

```zsh
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_process_improvements.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_manager_custom_pipeline_prompt_contract.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_sibling_contract_docs.py' -v
make verify
make doc-lint
make typecheck
make oss-release-scan
```

Success criterion: каждый адресный suite и declared Make route завершён exit 0 по final candidate bytes; `make verify` даёт GREEN, scan не содержит blocker. Все WARN читаются и получают bounded disposition по объявленному scope. `$PYBIN` — уже выбранный trusted Python 3.12 Self-Planveyor; compatible PATH и объявленный ignored TMPDIR передаются запуском, project-local executable selector не используется. Datastore/auth/SQL/visual profile N/A (why=process contract tests only). Это объявленные Coder-time checks, не выполненные этим Planner тесты; изменённые результаты после material delta требуют свежего proof, неизменённые успешные не повторяются без основания.

## Verification rerun / exec handoff

- Mode: reuse-thread
- Context source: текущий plan, exact code draft и linked source/readback carriers; agreed Owner scope.
- Prompt: проверить current exact bundle И1+И3а, все parser-backed samples, error/receipt consumer cases, copier parity/private fingerprint и границу candidate proof / frozen runtime.
- Command: `make verify` из selected project с declared trusted `$PYBIN`, compatible PATH и ignored TMPDIR; полная обязательная проверка exact bundle включает также все runnable команды `## Commands` в записанном порядке, включая три адресных unittest suites, scoped doc-lint, `make doc-lint`, `make typecheck`, `make oss-release-scan`.
- Expected artifact: `docs/code_reviews/261014_2007_general_prompt_collector_contract.md` (materialized current review; два non-doc test targets входят в exact bundle).

## Retrieval telemetry receipt

- No-op reason: `not_used_for_decision` — этот status invocation опирался на literal plan, accepted input и прямое чтение объявленных artifacts; bootstrap retrieval не использовался для изменения executable contract. Новый query event/read log не создавался, existing derived index не перестраивался.

## Evidence (chronological, append-only)

- 2026-10-14: initial draft подготовлен из `docs/plans/_template.md`; implementation AC ещё не проверялись. Provenance выведен штатным helper, служебная mapping хранится приватно.
- 2026-10-14 (Architect intake): принятые brief/answers проверены по согласованным digest; прочитаны совместный план v6 и уточняющий ход. Текущий Owner handoff подтвердил предусмотренную техническую контрольную точку и разрешил продолжение того же scope через existing handles. Private paths/identity/settings в public artifact не переносились.
- 2026-10-14 (Architect intake): retrieval canon/plans/followups выполнен с `--no-log`, existing index не перестраивался. Source parser прямо reject-ит unsupported строку; source v2 receipt validator проверяет source/role/cycle/input digest и exact object maps. Нижние samples содержат выявленное prose противоречие; текущий Manager general consumer требует exit 0/state/cycle, но ещё не задаёт rc/stdout shape guard до JSON.parse. Это source qualification, не выполненная implementation приёмка.
- 2026-10-14 (Architect intake): штатный `planveyor_plan_provenance_context` вернул continuation/manager-collab carrier с truthful N/A для непубликуемой native identity; перенесены его поля. `planveyor_runtime_info` подтвердил pinned Git source и compatible Python 3.12. Начальный `planveyor_plan_lint` завершился exit 0 с единственным ожидаемым WARN о planned отсутствующем Planner-owned code draft.
- 2026-10-14 (Architect intake): штатный mirror readback для выбранного source/self target вернул `mirror_set.id=generic`, `entry_count=0`, `recommended_outcome=no_packet_required`; внешний target не объявлен. Записанный draft прошёл plan lint с единственным planned-code-draft WARN, scoped doc-lint сообщил `OK`; oracle подтвердил `status_norm=architect draft`, `manager_mode_admitted=true`, `route_guard_triggered=false`, чистый Owner Q&A и N-A MAD `reason=ok`. Отсутствующий derived draft ref ожидаем до Planner finalize; implementation AC остаются unchecked.
- [2026-10-14 20:19] (Architect CENSOR) OK: Architect draft validated; current=true. Censor dispatch id: censor:architect:1a926e19-05ba-4b28-9784-ee3d157b68e7. Observations: первый CENSOR этого handoff; Second opinion: NO FINDINGS; Artifacts opened: docs/plans/261014_2007_general_prompt_collector_contract.md, docs/tools/prompts/coder_docs_finalize_general.md, docs/process_improvements/README.md, scripts/test_manager_custom_pipeline_prompt_contract.py; Content facts: Scope ограничен четырьмя general-промптами/копиями и collab general consumer, точный incident tail в receipt остаётся отказом без trimming; N-A MAD unchanged_structured_consumer сохраняет existing schema/writer/admission, code draft принадлежит Planner; открытый canon требует source/role/cycle и raw input_sha256, существующий prompt test связывает каждую из четырёх ролей с --input - --json и current cycle; Contradiction/deploy-safety check: plan не разрешает runtime/env/config mutation или hot reload И3а, неизменные helper admission и STOP остаются защитой при буквальном выполнении, candidate tests не выдаются за live adoption; Counterfactuals considered: canonical fields наверху могли скрыть prose снизу — primary lane требует извлечения нижних samples; success JSON/no_op могли подменить current proof — AC требуют helper-selected receipt/admission, terminal docs-closeout отдельный; Addendum (new angle): downstream-note для Planner — сохранить в адресных тестах границу пояснений Reviewer sample и full stdout incident tail, уже названную в Tests/Architect suggestions; Context reconciliation: Owner checkpoint уже закрыт без нового OK, general prompts читаются из working project при frozen Manager/helpers; draft-коммит не нужен и final docs no_op допустим; Fixes: none (NO FINDINGS; no plan/status changes required); Review verdict seen: no live review artifact; Blocker IDs considered: N/A (why=review not materialized); Role-owned finding: none, постановка достаточна для Architect draft без implementation proof; Reconciliation: no live blocker; Final censor verdict: OK, статус Architect draft сохраняется, implementation AC не закрывались.
- 2026-10-14 (Architect draft handoff): current plan и полный source prompt перечитаны; scope И1+И3а остаётся принятым ordinary developer_wave. `_collect_process_improvements` и `_v2_replay_response` подтвердили common stdout fields и отсутствие обязательного input_sha256 в replay projection; точная input identity остаётся у receipt. Конкретизированы существующие guard/field parity, точки изменений и declared test/Make commands; данные, helper implementations и runtime не менялись. Pre-handoff plan lint завершился exit 0 с ожидаемым planned-code-draft WARN; current oracle подтвердил N-A MAD reason=ok, digest=a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39, route_guard_triggered=false и чистый Owner Q&A. Derived draft ref missing ожидаем до Planner finalize.
- 2026-10-14 (Architect draft handoff): completion/self-check закрыт конкретными lanes — реальные нижние samples обеих copy surfaces, exact full-block incident tail, фактическая collab general consumer error matrix и canonical receipt/readback. Planner не должен угадывать writer, source/cycle proof или future runtime activation; его ownership — exact draft targets, derived MAD ref и детали proof. Whole А1 post-commit docs-closeout отделён от pre-Done implementation checkboxes, чтобы не требовать ложного предварительного [x] или переписывания terminal plan. Переход Ready for Planner означает готовность к Planner intake, не выполненные implementation AC; новых Owner вопросов нет. CENSOR и commit этим шагом не выполняются.
- [2026-10-14 20:42] (Architect CENSOR) OK: Ready for Planner validated; current=true. Censor dispatch id: censor:architect:463d9bf0-354b-44df-bf32-41c2757e73f1. Observations: Delta since previous CENSOR — formalization Ready for Planner с конкретными emitter/readback fields и post-commit gate, принятый результат И1+И3а сохраняется; Second opinion: NO FINDINGS; Artifacts opened: docs/plans/261014_2007_general_prompt_collector_contract.md, docs/tools/prompts/architect_censor.md, scripts/process_improvements_collect.py; Content facts: Changes называют actual collab general consumer, две existing test surfaces, пять prompt source/copy pairs и минимальный PI canon; receipt требует raw input_sha256/source/role/cycle, а открытый _v2_replay_response не emits обязательного stdout input_sha256, что literal учтено в Decisions; exact incident tail остаётся reject, full lower samples/copies и error matrix входят в mandatory lanes; Admission readback: independent current oracle — state=not_applicable, reason=ok, confirmation_state=not_applicable, id/route empty by N-A variant, carrier_sha256=a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39, route_guard_triggered=false, manager_mode_admitted=true, Owner Q&A clean; missing draft ref ожидаем до Planner finalize; Contradiction/deploy-safety check: helper/writer/schema и frozen runtime не меняются, hot reload И3а запрещён, отказ current receipt/shape требует STOP, terminal docs-closeout не заменяется Done или заранее отмеченным checkbox; Counterfactuals considered: replay без stdout input_sha256 мог ложно блокироваться — authority остаётся validated receipt; post-commit docs gate мог требовать mutable terminal plan — отдельная operational граница прямо запрещает такую правку; Addendum (new angle): downstream-note Planner — exact code draft должен сохранить уже concrete fresh/replay parity и helper-derived MAD ref вместо копии semantic core; Context reconciliation: accepted Owner checkpoint не переоткрыт, general prompts читаются из project при frozen Manager/helpers; final docs no_op законен только с fresh whole-tail proof, следующего плана при blocked нет; Fixes: none (NO FINDINGS; no plan/status changes required); Review verdict seen: no live review artifact; Blocker IDs considered: N/A (why=review not materialized); Role-owned finding: none, Architect-owned поля конкретны; Reconciliation: no live blocker; Final censor verdict: OK, Ready for Planner сохраняется; implementation tests и AC этим CENSOR не закрывались.

- 2026-10-15 (Planner finalize/preflight): создан и полностью перечитан `docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md` по canonical template. Validated upstream N-A MAD прочитан current oracle; в draft перенесён только tagged ref `{applicability,reason_code,carrier_sha256}` с unchanged digest, semantic core не менялся. Provenance получен штатным helper; unknown/missing поля сохранены правдиво, private thread mapping не опубликован.
- 2026-10-15 (Planner finalize/preflight): exact bundle preflight завершился exit 0: 13 существующих implementation targets, plan, draft и один PLANNED review; 16 paths, один root, 0 issues. Source/copy `cmp` пяти пар завершился exit 0 до реализации. Первый ordinary lint нашёл только carrier hygiene: read-only test/ref и `N/A` попали в synchronous-target row, старый `NO SUGGESTIONS` требовал canonical stamp. Строка сужена до exact 11 doc paths, proof вынесен за неё; stamp добавлен после полного draft reread. Повтор ordinary plan lint завершился exit 0 без diagnostics; scoped doc-lint по plan+draft завершился exit 0 / `OK`. Implementation tests/Make routes этим проходом не выполнялись, implementation AC остаются unchecked.
- 2026-10-15 (Planner completion): closure-path self-check — ничего не остаётся на догадку Coder/Reviewer: literal targets/commands, 16 lower sample cases, exact full-block incident negative, actual branch-local Manager error matrix, fresh/replay parity и existing canonical receipt/checkpoint proof названы в plan+draft. Обязательная contextual lane не скрыта primary green. Новых Key decisions / Constraints / Goal и Owner вопросов нет; `real scope expansion` отсутствует; role-outcome custom marker не active (`Mode: reuse-thread`). Censor hint не выдаётся для нового executable contract; primary Planner CENSOR/commit не запускал. Whole А1 остаётся post-commit operational gate текущего Manager, а candidate И3а — future runtime change.

- 2026-10-15 (Planner gate clarification): дополнительный read-only probe `plan_lint.py --as-status "Ready for Coder"` вернул exit 2: `--as-status supports only the exact value Done`; это неподдерживаемый аргумент probe, не verdict плана. Handoff опирается только на объявленный ordinary `plan_lint.py PLAN_PATH`, без simulated-status обхода. Fresh oracle после создания draft подтвердил `machine_authority_decision_ref_state=valid`, `reason=ok`, `manager_mode_admitted=true`, `route_guard_triggered=false`, Owner Q&A clean; semantic core/ref digest unchanged.

- 2026-10-15 (Planner gate clarification): повторный ordinary lint выявил в свежей completion-записи неклассифицированное wording `scope expansion нет`. Точное отрицание класса записано как `real scope expansion` отсутствует; targets, Scope/AC и code draft не менялись. Это hygiene текущей записи, не expansion/reroute.

- 2026-10-15 (Planner primary handoff): final ordinary `plan_lint.py PLAN_PATH` завершился exit 0 без diagnostics после hygiene текущей записи; fresh bundle preflight — exit 0, 16 paths / 13 implementation targets / 0 issues / один PLANNED review; final scoped doc-lint по plan+draft — exit 0 / `OK`. Derived MAD ref valid и exact executable contract сверены; gate закрывает подготовку handoff, не implementation AC или live adoption. План передан в Ready for Coder; дальнейший CENSOR выполняется только отдельным Manager dispatch.

- [2026-10-15 00:17] (Planner CENSOR) OK: Ready for Coder validated; current=true. Censor dispatch id: censor:planner:723a6c9a-d18a-433c-9236-95eb1de1187c. Observations: первый Planner CENSOR этого handoff; No material delta since previous CENSOR: N/A (why=first Planner CENSOR for this handoff), после primary contract не менялся; Second opinion: NO FINDINGS; Artifacts opened: docs/plans/261014_2007_general_prompt_collector_contract.md, docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md, scripts/process_improvements_collect.py, scripts/docs_closeout.py; Content facts: plan Tests требуют восемь canonical и восемь no-op нижних samples source/copy, точный full-block incident tail и actual collab branch-local error matrix без parser/helper mutation; draft Meta содержит ровно 13 existing targets и tagged N-A MAD ref из трёх keys, а read-only helpers/private-fingerprint suite не попали в writable set; draft Steps и plan field parity не вводят required stdout input_sha256 для replay, raw digest остаётся у validated v2 receipt; Contradiction/deploy-safety check: plan и draft запрещают менять frozen runtime/schema/writer, candidate И3а не выдаётся за live adoption, semantic Done/implementation commit не заменяют отдельный fresh terminal docs-closeout и не разрешают править terminal plan; Counterfactuals considered: корректный верхний образец мог скрыть плохой нижний — оба artifacts требуют literal lower extraction без фильтрации prose; replay без stdout digest мог блокироваться новым required field — текущая parity прямо сохраняет existing replay projection; green-looking stdout/pending остальных ролей могли скрыть authoritative red — truth-host matrix и прочитанный classify_process_improvement_capture ставят invalid/blocked перед pending, full-chain gate остаётся перед followups; Addendum (new angle): downstream-note Reviewer — при проверке sample extraction подтвердить, что concretization меняет только placeholders и не выбирает семь известных fields из более длинного body; этот запрет уже concrete в draft Step 2 и plan Tests, нового target не требует; Context reconciliation: source/copy parity и fingerprint остаются пятью парами и existing read-only suite, отдельного fingerprint carrier нет; raw receipt digest/fresh-replay split и post-commit whole-tail boundary из primary уже отражены в plan+draft; Fixes: none (NO FINDINGS; no plan/status changes required); Draft hygiene: добавлен обязательный append-only NO SUGGESTIONS stamp после полного reread без semantic delta; Gate: pre-write ordinary plan lint exit 0, post-write ordinary/scoped lint и final exact supplied-ID readback обязательны перед выходом; Review verdict seen: no live review artifact; Blocker IDs considered: N/A (why=planned review not materialized); Role-owned finding: none, Coder получает concrete targets/steps/commands и source/receipt boundary; Reconciliation: no live blocker; Final censor verdict: OK, Ready for Coder сохраняется, implementation AC не закрывались.

- 2026-10-15 (Coder intake): current plan, полный Planner-owned draft, frozen status prompt и объявленные parser/collector/readback carriers прочитаны. Все 13 targets существуют, 11 synchronous docs входят в draft; верхний contract, surfaced step и нижние samples требуют согласованной правки. Actual collab consumer находится после каждого general output; fresh/replay различаются optional stdout input_sha256, canonical input identity остаётся в v2 receipt. Runtime-info завершился exit 0: source_state=pinned, source_kind=git, selected project и trusted Python 3.12 подтверждены. Новые targets/helper/schema и Owner choice не нужны; custom marker не активен (Mode: reuse-thread). Прямое чтение literal refs, retrieval не использовался для нового решения (`not_used_for_decision`).
- 2026-10-15 (Coder, AC-to-test checklist; до implementation edits): AC1 → explicit assertion: `test_general_prompt_lower_samples_parse_canonical_and_noop` в `scripts/test_process_improvements.py`, 8 canonical + 8 no-op cases source/copy через настоящий parser без фильтрации body. AC2 → explicit assertion: `test_general_prompt_incident_tail_blocks_without_durable_effect` в том же suite, полный seven-field input + exact tail, blocked v2 receipt/raw digest/пустой durable delta. AC3 → explicit assertion: контракт sole collector writer в четырёх prompts и branch-local assertions `scripts/test_manager_custom_pipeline_prompt_contract.py`, без role-owned PI write. AC4 → explicit assertion: branch-local порядок rc/framing/guarded parse/fields/current cycle, error matrix и canonical readback boundary в `scripts/test_manager_custom_pipeline_prompt_contract.py`; existing v2 fresh/replay/chain fixtures остаются additional proof. AC5 → existing proof: `scripts/test_sibling_contract_docs.py` source/copy byte parity и private fingerprint. AC6 → explicit assertion: declared три unittest suites, Make routes, ordinary plan/scoped doc lint и read-only exact bundle preflight по финальным bytes. Backend/Domain row → explicit assertion: exact-tail v2 refusal/no durable effect плюс branch-local missing/red/stale proof contract; Config/storage/API/UI/visual gates → N/A (why=no change in accepted exact bundle). Architect final review и post-commit terminal gate остаются downstream duties и заранее не отмечаются.

- 2026-10-15 (Coder implementation): ordinary plan lint до implementation завершился exit 0; exact bundle preflight — exit 0, 16 paths / 13 targets / один PLANNED review / 0 issues; scoped doc-lint plan+draft — exit 0 / OK. Новый lower-sample regression до правки prompts завершился expected RED: все 8 source/copy carriers не содержали полного однозначно отделённого canonical/no-op примера. После правки extraction использует fullmatch всего carrier двух явно fenced variants; заменяются только объявленные placeholders, unknown prose не фильтруется. В ответ роли fences/labels не входят, что явно сказано до output sections.
- 2026-10-15 (Coder implementation): изменены ровно 13 implementation targets из draft. В четырёх general prompts согласованы upper contract, surfaced-suggestion step и нижние samples; durable writer — только existing collector Manager. В actual collab post-general branch зафиксирован порядок terminal rc → single-object framing → guarded JSON.parse → existing fields/current cycle → canonical helper proof; missing/red/stale current host и unknown error не маскируются stdout. Пять copier pairs синхронизированы побайтно, PI README обновлён минимально. Parser/collector/readback implementations, custom Manager prompt и read-only parity/fingerprint suite не менялись.
- 2026-10-15 (Coder tests): `test_process_improvements.py` — exit 0, 56 tests / OK. Проверены 8 canonical + 8 no-op извлечённых нижних samples; отдельные negative mutations доказывают отказ для prose внутри sample и между variants. Полный seven-field блок с exact incident tail даёт blocked/collector_error v2 receipt, сохраняет SHA-256 raw input, before/after object maps пусты, durable PI directory не создан. Existing leaf replay даёт тот же receipt без write; fresh stdout input_sha256 присутствует, replay projection без него проходит existing field parity.
- 2026-10-15 (Coder tests): `test_manager_custom_pipeline_prompt_contract.py` — exit 0, 68 tests / OK. New branch-local guard assertions и отрицательные relocation/removal mutations закрывают order и actual branch placement; failure matrix literal-но покрывает success fresh/replay, nonzero/plain-text и JSON, framing/syntax/non-object, missing/non-string fields, blocked/unknown/wrong cycle и missing/red/stale receipt/input proof. Это candidate prompt-contract proof, не исполнение И3а frozen Manager. `test_sibling_contract_docs.py` — exit 0, 22 tests / OK: source/copy byte parity, private fingerprints и frozen local sections прошли без изменения их carrier. `git diff --check` — exit 0.

- 2026-10-15 (Coder declared Make gates): `make verify` — exit 0, VERDICT GREEN (5 выбранных portability checks, не omitted plan/archive inputs); `make doc-lint` — exit 0 / OK; `make typecheck` — exit 0, no issues in 12 selected source files; `make oss-release-scan` — exit 0, public-copy blockers=0 / warnings=0 / no findings. Непросмотренных WARN нет. Все команды использовали уже объявленные trusted Python/PATH и ignored TMPDIR, system temp и project-local selector не использовались.
- 2026-10-15 (Coder completion/self-check): literal plan/draft, final 13-target diff, lower samples и actual Manager branch перечитаны глазами Reviewer. Reviewer может повторить 16 parser cases, exact-tail refusal, branch-local negative/error matrix и parity/fingerprint по тем же checked-in suites без нового helper, bootstrap или догадок. Mandatory contextual lane закрыта отдельно от primary; Docs impact совпадает с 11 changed doc targets. Единственный current review path согласован с draft как PLANNED; содержимое review и его verdict materialize-ит Reviewer, accepted Arch review остаётся unchecked downstream duty. AC6 здесь закрывает выполненные candidate checks и exact review-route parity, не заявляет существующий/accepted review. UI/runtime sanity/schema migration N/A (why=no such changed surface). Frozen runtime HEAD отдельно прочитан и совпал с accepted pin; кандидат И3а не hot-reload-ился. `real scope expansion` отсутствует, Key decisions/Constraints/Goal не менялись; CENSOR, stage, commit и terminal closeout primary Coder не выполняет.

- 2026-10-15 (Coder primary handoff): final ordinary `plan_lint.py PLAN_PATH` по completion bytes — exit 0 без diagnostics; exact bundle preflight — exit 0, 16 paths / 13 implementation targets / 0 issues / единственный PLANNED code review. Final scoped plan+draft doc-lint — exit 0 / OK, final `git diff --check` — exit 0. Финальный status — Ready for Review; отдельный Manager-dispatched CENSOR ещё не выполнялся. Implementation scope завершён как candidate source proof; semantic Done, accepted review/commit и fresh terminal docs-closeout остаются downstream. Evidence-only skip hint не применяется к этому implementation diff.

- [2026-10-15 00:40] (Coder CENSOR) OK: Ready for Review validated; current=true. Censor dispatch id: censor:coder:a2ce332e-f481-4b13-9433-dff859809ef2. Observations: первый отдельный Coder CENSOR после primary; implementation bytes этим проходом не менялись; Second opinion: NO FINDINGS; Artifacts opened: docs/plans/261014_2007_general_prompt_collector_contract.md, docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md, scripts/test_process_improvements.py, scripts/test_manager_custom_pipeline_prompt_contract.py, четыре source general prompts и docs/tools/prompts/manager_collab_pipeline.md через exact diff, docs/process_improvements/README.md, scripts/process_improvements_collect.py, scripts/docs_closeout.py; Content facts: AC-to-test checklist покрывает шесть implementation AC и Backend/Domain row с canonical outcomes, а primary evidence сохраняет 56/68/22 успешных tests и четыре Make routes с точными границами; lower-sample extraction начинает с последнего output marker и fullmatch всего carrier двух variants, меняет только literal placeholders, prose-mutation negatives и exact full-block incident tail не фильтруются; actual collab branch требует terminal rc до framing/guarded parse, четыре existing string fields/current cycle и canonical receipt, replay stdout input_sha256 не required, invalid/blocked host в прочитанном classify_process_improvement_capture побеждает pending; Contradiction/deploy-safety check: безопасный candidate contract не требует скрытого env/config pin или нового validator, strict parser/writer/readback не менялись, И3а не заявлен как активный в frozen runtime и post-commit whole-tail gate не заменён Done; Counterfactuals considered: корректный верхний образец мог скрывать плохой нижний — реальные lower source/copy samples и отрицательные prose mutations уже проверены настоящим parser; replay мог ошибочно требовать stdout digest — _v2_replay_response его не emits и test связывает unchanged receipt/common fields, prompt оставляет поле optional; green-looking stdout и missing roles могли скрывать current red — branch и existing reader сохраняют blocked-before-pending, full chain остаётся у checkpoint; Addendum (new angle): reviewer-only note — braces framing само по себе не green: current branch прямо требует полный guarded JSON.parse для prefix/suffix/second-value и syntax errors, а regression assertions привязаны к этой ветке, не preamble; Context reconciliation: единственный review path повторно проверен как PLANNED и пока отсутствует, поэтому AC6 в completion evidence честно ограничен checks/route parity, review verdict не заявлен; Make verify в primary evidence ограничен пятью portability checks, а полноценный обязательный набор отдельно подтверждён тремя suites и остальными Make routes; Gates: fresh pre-write ordinary plan lint exit 0, unchanged passing implementation suites/Make не повторялись; post-write plan/doc lint и final supplied-ID readback обязательны перед выходом; Fixes: none (NO FINDINGS; no plan/status changes required); Review verdict seen: no live review artifact; Blocker IDs considered: N/A (why=first planned review not materialized); Role-owned finding: none, in-scope handoff gap не найден; Reconciliation: no live blocker; Final censor verdict: OK, Ready for Review сохраняется, downstream review и terminal closeout ещё не выполнены.

- 2026-10-15 (Reviewer risk, independent checks): exact diff 13 targets и declared source/readback carriers прочитаны; новых вопросов и risk findings не найдено. Повтор объявленных suites выполнен как независимая Reviewer-проверка current candidate bytes: `test_process_improvements.py` — exit 0, 56 tests; `test_manager_custom_pipeline_prompt_contract.py` — exit 0, 68 tests; `test_sibling_contract_docs.py` — exit 0, 22 tests. Lower extraction проверяет весь carrier и только concretize-ит placeholders; exact incident tail остаётся `blocked/collector_error` с raw digest и без durable PI delta. Branch-local tests доказывают prompt contract, а не выполнение И3а frozen Manager.
- 2026-10-15 (Reviewer risk, gates): ordinary plan lint — exit 0. `planveyor_plan_bundle --check` — exit 1 только из-за отсутствующего PLANNED first-pass review; все 13 targets, plan и draft OK. Штатный `--preflight` — exit 0, 16 paths / 0 issues. `make verify` — exit 0 / GREEN, пять portability checks без claim для omitted plan/archive inputs; `make doc-lint` — exit 0 / OK; `make typecheck` — exit 0, 12 source files; `make oss-release-scan` — exit 0, blockers=0 / warnings=0. Trailing-whitespace/merge-marker поиск по exact implementation paths и новым plan/draft не дал совпадений. Все proof commands использовали declared trusted environment/TMPDIR; private значения не публикуются. Canonical producer дал current snapshot ниже; его полный stdout сохранён неизменённым как nested payload нового support asset. Top-level `Ready for Review` и PLANNED review не меняются: synthesis, final artifact и status принадлежат contracts lane. `Mode: reuse-thread` не активирует custom role-outcome carrier; retrieval не использовался для решения (`not_used_for_decision`).

```json
{
  "run_id": "reviewer_code_risk_20261014T215044Z",
  "lane_id": "reviewer_code_risk",
  "runner_id": "N/A (why=private operator mapping is retained outside public artifacts)",
  "session_key": "N/A (why=private operator mapping is retained outside public artifacts)",
  "sid": "N/A (why=private operator mapping is retained outside public artifacts)",
  "profile": "N/A (why=private operator mapping is retained outside public artifacts)",
  "model": "N/A (why=private operator mapping is retained outside public artifacts)",
  "reasoning_effort": "N/A (why=private operator mapping is retained outside public artifacts)",
  "prompt_file": "docs/tools/prompts/reviewer_status_driven.md",
  "target_ref": "BUNDLE=current",
  "target_snapshot": {"bundle_sha256":"683ef31450c3369bd89391f315642dbf86eb347b775d78ddd5fb47389783cf8e","target":"BUNDLE=current"},
  "coverage_domains": ["correctness","tests quality","security/privacy","subprocess/timeouts","failure semantics","observability","integrations"],
  "findings": [],
  "lane_status": "no_findings",
  "no_findings_reason": "В exact diff 13 targets риск-регрессий не найдено. Проверены полные lower samples обеих surfaces, exact-tail отказ без durable delta, branch-local guard и existing receipt/readback; независимые объявленные suites и Make gates прошли.",
  "source_refs": ["scripts/test_process_improvements.py","scripts/test_manager_custom_pipeline_prompt_contract.py","scripts/test_sibling_contract_docs.py","scripts/process_improvements_collect.py","scripts/docs_closeout.py","scripts/followups_capture.py"],
  "delta": "Исправлены нижние general samples и ownership PI writer; actual collab consumer требует terminal rc, framing, guarded parse, existing fields и canonical current proof.",
  "outcome": "Risk lane завершена без findings; последующая contracts lane должна независимо выбрать этот receipt и проверить тот же snapshot.",
  "limits": ["Проверены candidate source bytes; применение И3а текущим frozen Manager и terminal docs-closeout этим проходом не доказаны.","Новая data/migrations, runtime atomicity, performance и supply-chain реализация отсутствует в diff.","Идентификационные настройки роли сохраняются в приватном операторском evidence.","Роль сохраняет top-level статус и не создаёт финальный review artifact; aggregate verdict принадлежит contracts lane."],
  "full_payload_ref": "docs/code_reviews/assets/261014_2007_general_prompt_collector_contract/reviewer_code_risk_20261014T215044Z.json",
  "full_payload_sha256": "d824a2aaf7da6d43538702370cfdc80fae26745532f9f76f20548b4de338d696",
  "current": true,
  "written_at": "2026-10-14T21:50:44Z"
}
```

- 2026-10-15 (Reviewer risk, selector readback): штатный `review_artifact_lint.py --project-root . --select-risk-lane --origin-plan docs/plans/261014_2007_general_prompt_collector_contract.md --json` завершился exit 0, `schema_version=reviewer_risk_lane_selection.v1`, `state=selected`, `run_id=reviewer_code_risk_20261014T215044Z`; snapshot совпал с canonical producer. Проверены support SHA и текущая producer equality; финальный review/status этой lane не создавались. Scoped doc-lint plan+draft после compact receipt — exit 0 / OK.

- 2026-10-15 (Reviewer contracts, независимая проверка): frozen status prompt, current plan/draft и playbook прочитаны; actual exact diff 13 targets, полные четыре source general-промпта, actual collab consumer branch, адресные test changes и canonical parser/receipt/readback проверены. `review_artifact_lint.py --project-root . --select-risk-lane --origin-plan docs/plans/261014_2007_general_prompt_collector_contract.md --json` самостоятельно вернул exit 0, `schema_version=reviewer_risk_lane_selection.v1`, `state=selected`, current run `reviewer_code_risk_20261014T215044Z`; immutable support прочитан. Fresh `planveyor_review_target_snapshot ... --current-bundle` — exit 0, exact same snapshot `683ef31450c3369bd89391f315642dbf86eb347b775d78ddd5fb47389783cf8e`. Source/copy hashes совпадают попарно, actual diff и 11 synchronous doc targets согласованы; parser/helper/schema/runtime и чужие targets не менялись.
- 2026-10-15 (Reviewer contracts, proof reuse): успешные independent risk checks для того же exact snapshot переиспользованы из selected hash-pinned support: suites 56/68/22 tests, `make verify` GREEN (5 portability checks, без omitted plan/archive proof), `make doc-lint` OK, `make typecheck` 12 files, `make oss-release-scan` blockers=0 / warnings=0, все exit 0. Неизменные успешные suites/Make повторно не запускались. Это проверка candidate prompt contract; применение И3а frozen Manager, semantic Done, implementation commit и terminal docs-closeout не заявляются.
- 2026-10-15 (Reviewer contracts, artifact gates): создан единственный `docs/code_reviews/261014_2007_general_prompt_collector_contract.md` с обеими code lanes, no-findings provenance, exact target и explicit immutable risk asset. Initial bundle check честно был red из-за отсутствовавшего planned review, interim check — из-за draft header; initial artifact lint потребовал literal `Visual env`, добавлен корректный N/A в том же review. Финальный green artifact прошёл `review_artifact_lint.py --origin-plan docs/plans/261014_2007_general_prompt_collector_contract.md docs/code_reviews/261014_2007_general_prompt_collector_contract.md` — exit 0 / OK; повторный selector — selected / exit 0; `planveyor_plan_bundle --check` — exit 0, 17 paths / 0 issues. Ordinary plan lint — exit 0; scoped doc-lint plan+draft+review — exit 0 / OK. Exact-path `git diff HEAD --check` — exit 0; trailing-whitespace/merge-marker `rg` по всем 17 literal bundle paths, включая новые plan/draft/review/support, — exit 1 без совпадений. Private environment values не перенесены в команды или artifacts.
- 2026-10-15 (Reviewer contracts, completion/handoff): обе lanes no_findings, review `✅ OK`; S1/S2/S3, новых suggestions и Q&A нет. Visual/decomposition/analysis и custom outcome/semantic observation markers не активны для этого non-UI bundle. Key decisions / Constraints / Goal не менялись, `real scope expansion` отсутствует. Status передан в Ready for Arch review; Architect принимает review и выполняет только штатный exact closeout, затем Manager доказывает genuine terminal docs-closeout. Reviewer не выполнял stage/commit/Done и не менял implementation targets или risk support. Final written-carrier readback повторяется перед выходом без расширения proof scope.

- 2026-10-15 (Architect arch review): current plan, полный code draft, единственный live review и immutable selected risk support прочитаны независимо; actual diff 13 implementation targets сверён с Scope/AC и 11 synchronous docs. Fresh canonical snapshot дал прежний `683ef31450c3369bd89391f315642dbf86eb347b775d78ddd5fb47389783cf8e`, source/copy SHA совпадают попарно; selector — exit 0 / selected, run `reviewer_code_risk_20261014T215044Z`. Current oracle — exit 0, `review_green`, derived MAD ref valid, Owner Q&A clean, route guard отсутствует; native closeout-json — bundle_ok=true, 17 exact paths / errors=[], `staged_empty` до materialization ожидаем. В единственном review записано `Вердикт: принято.`; Architect implementation targets не менял.
- 2026-10-15 (Architect completion перед materialization): lower extraction fullmatch не фильтрует prose, exact incident tail остаётся blocked без durable effect, actual collab general guard упорядочен и не требует stdout digest у replay. Mandatory contextual lane закрыта тем же selected proof отдельно от primary; suites 56/68/22 и четыре Make routes переиспользованы для unchanged snapshot, а не объявлены новыми прогонами. Coder/Reviewer findings и documentation impact не оставили новых blockers/долга; private fingerprint/local sections и existing backlog rows не менялись. `runner_quality` explicit not_applicable, visual N/A. Key decisions / Constraints / Goal не менялись; `real scope expansion` отсутствует. Следующий шаг — только штатные lint/exact stage/preflight и локальный commit; успешный commit этим pre-commit evidence не заявляется. После него plan immutable, whole А1 закрывает Manager лишь fresh terminal docs-closeout, без hot reload И3а или перехода к следующему плану при blocked.

- 2026-10-15 (Architect exact closeout, pre-Done proof): ordinary `plan_lint.py PLAN_PATH`, simulated `plan_lint.py --as-status Done PLAN_PATH`, current review-artifact lint и scoped plan/draft/review doc-lint завершились exit 0; первые два без diagnostics, остальные OK. Штатный exact `planveyor_plan_bundle --stage` завершился exit 0, 17 paths / 0 issues / один root. Pre-Done `planveyor_plan_closeout_preflight` дал exit 0: semantic_ready=true, semantic_verdict=go, bundle_ready=true, staged_exact=true, git_writable=true, commit_ready=true, closeout_state=commit_ready, source_errors=[], exact safe_command предоставлен. Это разрешило provisional Done; перед commit обязательны немедленный ordinary lint фактически записанного Done, exact restage и fresh final preflight. Только их green result допускает один локальный exact commit; отказ возвращает owning non-Done bytes без commit. После materialization новый evidence tail здесь запрещён; final commit/readback и отдельный whole-А1 terminal docs-closeout остаются наблюдаемыми обязанностями текущего Manager.

## Review artifacts

- Code review (primary): `docs/code_reviews/261014_2007_general_prompt_collector_contract.md` (current; `✅ OK`, обе code lanes завершены без findings; Architect дописывает Arch review).

## Q&A log (chronological, append-only)

### Architect Q&A
NO QUESTIONS: scope И1+И3а уже разрешён Owner; technical checkpoint закрыт текущим handoff. Новая Owner-развилка не возникла; initial draft дозаполнен и переведён в Architect draft без повторного OK.
2026-10-14 (Architect): NO QUESTIONS перед handoff на Planner; существующие поля/emitter/readback и error matrix конкретизированы без нового продуктового выбора. Planner получает только детализацию exact bundle, derived MAD ref и proof steps.

### Planner Q&A
NO QUESTIONS (роль ещё не запускалась).
2026-10-14 (Planner intake): NO QUESTIONS — прочитаны current plan, canonical Planner prompt, все объявленные source families и их read-only proof surfaces; принятые scope/checkpoint не переоткрываются. Planned draft отсутствовал и создаётся этим finalize. Current oracle подтвердил N-A MAD `reason=ok`; semantic core не меняется.

### Coder Q&A
NO QUESTIONS (роль ещё не запускалась).
2026-10-15 (Coder intake): NO QUESTIONS (проверены exact targets, AC, tests/commands, mandatory lanes и current receipt boundary; принятого Owner scope достаточно).

### Reviewer Q&A
NO QUESTIONS (роль ещё не запускалась).
2026-10-15 (Reviewer contracts intake): NO QUESTIONS — current plan и draft прочитаны целиком; ordinary non-UI dev contract, 13 exact targets и 11 synchronous docs совпадают с current diff. Штатный selector самостоятельно выбрал support-preflighted risk carrier с exit 0; fresh producer дал тот же target snapshot. Ordinary plan lint — exit 0. Initial bundle check — exit 1 только из-за отсутствующего PLANNED first-pass review, остальные 16 paths OK; его materialization принадлежит текущей finalizer lane. Ни нового scope, ни Owner choice нет; custom outcome/semantic observation markers не активны.

### Owner answers (если owner хочет писать прямо сюда)
2026-10-14: согласован полный А1 (И1 + И3а), обычный lifecycle в одном видимом Manager TUI, existing native helpers; commit реализации — Architect; push не входит в поручение.
2026-10-14: Owner подтвердил завершение предусмотренной технической контрольной точки, поручил продолжить тот же full TUI через существующие роли и выполнить terminal native docs-closeout. Нового Owner решения для literal plan handoff и перехода в draft не требуется; новая продуктовая развилка вне принятого scope остаётся STOP.

## Suggestions log (chronological, append-only)

### Architect suggestions
2026-10-14 (Architect): тестировать нижние output examples настоящим parser, включая explanation tail Reviewer; не ограничиваться поиском canonical fields в верхнем contract block. Новые helper/schema/refactoring surfaces не добавлять.
2026-10-14 (Architect): учесть два существующих stdout emitter-а collector: fresh collection и replay projection различаются присутствием input_sha256; receipt остаётся raw-input authority в обеих ветках. Это конкретизация accepted И3а, не новый machine contract.
2026-10-14 (Architect): terminal docs-closeout остаётся обязательным post-commit operational gate Manager по fresh helper proof; он не становится pre-Done checkbox и не даёт права дописывать terminal plan. Existing Architect exact closeout order сохранён.

### Planner suggestions
NO SUGGESTIONS.
2026-10-14 (Planner → Architect, blocker=no): executable contract конкретизирован в пределах принятых И1+И3а: 13 literal targets, full lower samples из обеих surfaces, fresh/replay parity и branch-local error matrix. Private fingerprint — existing test, отдельного writable carrier нет. До четвёртой general роли aggregate pending ожидаем; invalid/blocked current receipt по `scripts/docs_closeout.py:classify_process_improvement_capture` побеждает pending, а full chain остаётся у checkpoint. Key decisions / Constraints / Goal не менялись; нового canon/Owner выбора нет.

### Coder suggestions
NO SUGGESTIONS.
2026-10-15 (Coder intake): NO SUGGESTIONS (executable contract не требует дополнительных targets или решений).

### Reviewer suggestions
NO SUGGESTIONS.

## Objections / risks log (chronological, append-only)

### Architect objections
Риск: исходный runtime Manager не содержит И3а до следующего плана; блок закрытия требует STOP.

### Planner objections
NO OBJECTIONS.
2026-10-14 (Planner intake): NO OBJECTIONS — helper/schema/runtime/writer остаются read-only, copier pairs входят в exact source-owned scope; custom consumer dependency не доказана. Candidate prompt contract не является live adoption И3а; весь terminal tail остаётся отдельным post-commit operational gate.

### Coder objections
NO OBJECTIONS.
2026-10-15 (Coder intake): NO OBJECTIONS (strict parser/readback и frozen runtime остаются неизменными; обязательная contextual lane явно объявлена).

### Reviewer objections
NO OBJECTIONS.

## Post-merge gate (before deleting plan)

N/A (why=no merge or deletion is authorized by preparation; terminal closeout remains required during implementation).

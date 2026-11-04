# Plan: Одна проверка совместимости Python 3.10 и полный набор Python 3.12

**Date:** 2026-11-04 03:14
**Stage:** Stage 1
**Priority:** P1
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
- `AGENTS.md`; `skills/planveyor-plan-draft/SKILL.md`; `docs/plans/_template.md`; `docs/plans/README.md`; `docs/code_drafts/_template.md`.
- `docs/roles/architect.md`; `docs/tools/prompts/architect_draft_discussion.md`; `docs/tools/prompts/architect_status_driven.md`; `docs/guides/launch-and-role-modes.md`.
- `docs/adr/004-exact-bundle-truth-and-closeout.md`; `docs/adr/006-doc-lint-scoped-closeout-gate.md`; `docs/playbooks/doc_lint.md`.
- `scripts/run_test_shard.py`; `scripts/test_shards.json`; `scripts/test_shards.schema.json`; `.github/workflows/checks.yml`; `requirements-dev.lock`; `pyproject.toml`.
- `README.md`; `README.ru.md`; `docs/tools/verify_suite.md`; `docs/tools/verify_suite.ru.md`; `i18n/terms.md`; `i18n/pairs.json`.
- `scripts/i18n_pairs.py` (`build_parser`, `stamp_copy`, `_cmd_status`) — existing product WORK CLI для двух stamp calls и status; helper/source не меняется в C-P3-1.
- `scripts/plan_status_oracle.py` (`machine_authority_decision_readback`, N-A reason enum и tagged ref validation); `scripts/plan_lint.py` (`validate_machine_authority_decision`); `docs/playbooks/role_prompt_invariant_map.md` — read-only источник MAD ownership/admission; не implementation targets П3.
- `docs/plans/261023_0037_test_manifest_exact_once.md`; `docs/plans/261101_0052_ci_test_expectations_rebuild.md`; `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md` — завершённые исторические планы, только контекст.
- Code draft(s): `docs/code_drafts/261104_0314_ci_python_compat_subset__code_draft.md`
- `.tmp/ci_p3_reference/operator_inputs.json` — transient launch inputs; абсолютные пути и приватные значения в публичный plan/draft/review не переносить.
- Постановка: принятое Owner поручение «Старт П3» от 04.11.2026, критерии подготовленного хода 09 без изменений; внешняя координация и независимые Sol/GLM reviews принадлежат root, не native ролям.
- Matching open follow-up: `N/A (why=bounded rg in docs/plans, docs/followups and docs/reviews found no matching open row for compat310 outcome)`. Три совпавших исторических плана имеют Done; активного дубля нет. Ordinary plan не изменяет rows и не выполняет promotion/backlink.

## Meta (machine-readable JSON; required for current plan.v2 plans)
```json
{
  "plan_meta": {
    "cluster": "quality",
    "tags": ["ci", "python", "compatibility", "test-subset"],
    "required_manager_mode": "manager-collab",
    "wave_family": null,
    "phase_overlay": null,
    "phase_state": null,
    "parent": null,
    "next_plans": [],
    "depends_on": [],
    "queue_activation": {
      "state": "n/a",
      "source_ref": "N/A (why=single ordinary Owner-authorized P3 plan)",
      "reason": "N/A (why=no queue materialization or activation requested)"
    },
    "scope_expansion": {
      "state": "n/a",
      "target_contour": "N/A",
      "source_ref": "N/A (why=accepted bounded P3 package)",
      "reason": "N/A (why=one compatibility subset and existing runner; later CI tiers excluded)"
    },
    "canon_updates": [],
    "machine_authority_decision": {
      "schema_version": "machine_authority_decision.v1",
      "applicability": "not_applicable",
      "reason_code": "no_machine_authority_change"
    }
  }
}
```

## Plan provenance / session context
- Relation: `continued-here`
- Thread ID: `01a1a3fe-aba4-7113-9712-75d1e2a05b74`
- Parent thread ID: `01a193fb-f568-73e3-ab81-a731ce78ee34`
- Session SID: `01a1a3fe-aba4-7113-9712-75d1e2a05b74`
- Launch surface: `manager-collab`
- Captured from: `session-stats`
- Captured at: `2026-11-04T01:23:50Z`

## Documentation impact / provenance
- Source docs used: `AGENTS.md`, draft skill, current templates and plan README, frozen Architect prompts, target-local N-A rules, launch guide, ADR 006, doc-lint playbook, verification guides, runner/schema/manifest/workflow, `scripts/plan_status_oracle.py`, `scripts/plan_lint.py`, role-prompt invariant map, i18n pair registry, accepted external Owner package.
- Synchronous doc/registry targets: `README.md`, `README.ru.md`, `docs/tools/verify_suite.md`, `docs/tools/verify_suite.ru.md`; source/hash stamps обновляются в существующих translated carriers по i18n contract. `i18n/pairs.json` и `i18n/terms.md` read-only: пары уже зарегистрированы, новая пара/терминологический словарь не нужны. Точный executable inventory — девять targets linked finalized code draft.
- Post-merge canon updates: `N/A (why=actual version and verification contract is synchronized in this slice)`.
- Deferred documentation follow-ups: `N/A (why=no documentation obligation deferred from accepted P3 scope)`.
- Provenance refs: прямое Owner поручение 04.11.2026; проверенный базовый commit `e3032d4bb5d5d949411f2dcac3004f4f7b1de979`, tree `47587c678496ed6c917444719818f1b1c7d77d72`.

## Problem
1. Полная ось Python 3.10 дублирует полный Python 3.12, хотя согласованный контракт первой версии требует полного 3.12 и одной короткой исполняемой проверки совместимости 3.10.
2. Existing runner и manifest пока не предлагают именованный exact-ID subset с проверкой всего canonical partition до отбора. Нельзя сокращать проверку, скрывая missing/duplicate IDs или дефекты полного разбиения.
3. Документация и CI matrix должны одинаково описывать фактическую ось версий, без обещания быстрого push до отдельного будущего CI tier.

## Как я понял задачу
В текущей WORK поверх завершённых П2 и отдельно принятых документов выполнить только П3: один `compat310` subset в существующих manifest и runner, 14 full rows 3.12 и одна compatibility row 3.10.
Квалифицировать начальные девять IDs реальным Python 3.10 и проверить те же bytes на 3.12; полный canonical partition проверяется до subset selection.
Native owning роли ведут plan/draft/code/review/state и обычный local terminal closeout; executable code draft и точные команды остаются Planner-owned.
Owner уже выбрал scope, приёмку, F25/scoped ADR 006, локальное исполнение и узкое v3-name исключение ниже; новых Owner-решений или изменений scope при intake не обнаружено.
Формализация закрепляет additive `subsets`/`--subset` contract, раздельную identity full/subset и N-A MAD; Planner получает конкретный контракт и derived ref, не semantic core. Публикация требует отдельной команды.

## Solution (high level)
1. Architect materialize-ит единственный N-A MAD и фиксирует bounded runner/consumer contract ниже. Planner переносит его в exact targets, derived MAD ref и executable draft, затем проходит strict preflight перед Coder.
2. Coder добавляет минимальную subset foundation в существующие runner/schema/manifest, дешёвые synthetic tests и обновляет матрицу/согласованные документы.
3. Проверки доказывают полный partition до selection, canonical instance order/hooks и actual completion/HEAD drift; реальные compatibility reports связываются с Python identity и source/manifest hashes.
4. Reviewer проверяет exact current bundle в двух canonical lanes, Architect закрывает semantic результат, Manager выполняет штатный capture/followups/PI/final docs. Root независимо валидирует concrete candidate на Sol/ultra и GLM; внешние модели из native Manager/ролей не запускаются.

## Decisions (final)
- Один именованный exact-ID subset `compat310`; расширенная fast-tier инфраструктура не входит. Полный canonical partition всегда валидируется раньше выбора subset.
- CI выдаёт ровно 15 unique rows: s01…s14 только 3.12, `compat310` только 3.10; `meta=true` ровно один раз на full 3.12. `mypy` target 3.10 сохраняется.
- `requires-python >=3.10,<3.13`, loader range 3.10–3.12, lock и продуктовые сценарии не меняются.
- Selection сохраняет существующие canonical TestCase instances, их порядок и module/class setup/teardown. Неполные started/completed и HEAD drift после existing post-discovery `head_before` дают red/nonzero; более широкий drift contract не вводится.
- Девять candidate IDs ниже — начальная гипотеза, не измеренный smoke. Достаточность и actual 3.10 qualification принадлежат этому плану. `tomli` import/parse под 3.10 проверяется отдельно, без заявления о production fallback. Public facade/Copier path остаётся настоящим.
- Baseline: WORK `e3032d4bb5d5d949411f2dcac3004f4f7b1de979`; frozen runtime `e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4` неизменяем. Прежние terminal П1/П2 и новый документальный commit не переписывать.
- F25/scoped ADR 006 уже принят Owner: canonical doc-lint движка красный на baseline из-за sibling-only `docs/README.md`. Для текущего exact bundle применять explicit-root link/basic-hygiene route из ADR 006/playbook, добавляя actual lifecycle review/assets по materialization. Это честное scoped proof, не blanket green broad doc-lint и не waiver plan lint/bundle/review gates. Unsupported `planveyor_runtime_py doc_lint.py` не использовать; read-only `run_doc_lint.sh` frozen runtime с explicit product root допустим существующим playbook.
- Никаких Home/global/target config changes. Пять actual v3 ролей проверены как `gpt-6.1-sol` / `ultra`; роль, project и model/effort берутся из actual metadata, не из имени. Их Legacy SID-cache является только diagnostic/proof carrier прямого Owner exception, не canonical V2 liveness proof. Live address остаётся `/root/<role>_sol_ultra_v3`. Manager продолжается своим существующим SID; его model/effort не выводится из назначения дочерних ролей.
- Все промежуточные stdout/stderr сохранять через tee; actual child rc и итоговый pipeline rc фиксировать отдельно. Wrapper rc=0 не доказывает business success.
- До вложенного login shell export `PYBIN`; соответствующий env/bin первым в PATH; natural bare `python3` и physical TMPDIR вне Git проверять в native контексте. Existing 3.12/3.10 envs переиспользуются, установки и Home edits не делать.
- Private scan — только independent exact-byte copy и index этой копии; source shared index/capture не использовать как scan staging area. Existing dictionary только передаётся scanner по пути из transient inputs; не открывать, не печатать и не копировать.
- Перед final local commit root получает concrete candidate/freeze SHA и evidence для независимой проверки; final local commit и terminal docs выполняются штатным owning lifecycle. После локального конечного commit свежий p0; push и GitHub writes запрещены.

### Root precommit checkpoint: принято

Root decision P3_ROOT_PRECOMMIT_ACCEPTANCE_002: ACCEPTED_CURRENT_P3_PRECOMMIT_CODE_AND_PROOF. Конкретное решение root по существующему §Decisions checkpoint П3: ACCEPTED_CURRENT_P3_PRECOMMIT_CODE_AND_PROOF. Продолжай ТОГО ЖЕ retained Manager и owning Architect от существующего checkpoint через обычный LOCAL semantic commit / capture / followups / PI / final-docs terminal route. Это итоговое root acceptance текущих code+proof, не native lifecycle receipt и не hosted/release acceptance.

| Sanitized binding / outcome | SHA-256 или факт |
| --- | --- |
| Baseline HEAD | e3032d4bb5d5d949411f2dcac3004f4f7b1de979; index пуст до effects |
| Native current target | BUNDLE=current bundle_sha256=526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d |
| Product9 freeze001 descriptor | 1f98c1be6eea3997999e1d087a23b3d5721ca87258a2d5b19a8531fb0dd11f59 |
| Product9 content+mode digest | fec957e4c19662046d98571ffcfdf5ceef7c5e32f1e3d615c9ce7a28f754a99d |
| Accepted current19 snapshot | f578333c3e03a2c069479339c57d16e8e8e74bc5f470f0dd540514567da53f46; lifecycle связывается этим current snapshot, не старыми context copies freeze001 |
| Sanitized lifecycle mode map | c1ad9c1ff988ca5fc952a85e47abc59dc429df4fc0a7ead01cdeb2c24f0bc229; у всех10 non-product lifecycle/assets expected Git100644 / Unix0644 |
| Acceptance002 evidence | 7c8fba1027626a816a0fc51faf5f98c701d337047bd47fdc44543070f2948995 |
| Sol exact-code-proof | cb2ebeec461aff8f49ba84694f67a06c74e85ed7e0d4563706c35b3ec8cd20bf; принят code/local proof без actionable findings |
| Sol native-delta | 8a7669b1d54fa99107dec70639d6321064ab514046749f2392fdb6734d594e12; принят native review delta без actionable findings |
| Sol Architect-delta | 7270bc083b12d038ef988c0cf3a7f5fb635718329e5afbe60d18bcc2ad71ce0d; принят Architect hold delta без actionable findings |
| GLM exact-candidate | 8cb247f4b47ed2dc579d1b629c7735f18d7145dfefbe843c99e3838663462234; substantive completed GLM-5.3 review принят без actionable findings, не truncated; provider/model/effort проверены root |
| Root current19 copy-only private scan | actual rc0, blockers0/warnings0; source/copy bytes+modes совпали после, source index неизменён |

Эти SHA refs/outcomes получены из прямого sanitized root decision; raw coordinator reports/private paths не переносятся и native receipt не фабрикуется. До первой semantic записи Architect самостоятельно сверил baseline HEAD/пустой index, canonical producer, bytes всех19 с сохранённым current checkpoint, modes product9 с native evidence и expected Git100644/Unix0644 остальных10 с literal operator clarification. Drift не обнаружен. Частная arithmetic typo 9M+10A не является binding: фактические exact19 = 8M+11A. Matrix остаётся structural/no-import; полный partition обязателен для check/execution.

Root precommit условие закрыто; ordinary native_existing semantic materialization разрешена только по текущим native gates и helper-derived exact safe_command. Product9/MAD/targets/predicates не меняются. Fresh final p0 на фактическом final committed clean HEAD и postcommit closeout/privacy readback новой terminal docs delta остаются root-owned; Manager выполняет capture/followups/PI/final-docs после terminal semantic commit. Эти будущие outcomes не объявляются Done evidence этой роли. Публикация и hosted/release acceptance не разрешены.

### Authority pre-write и границы применения CI
- `decision lifecycle` текущего scope = принятое Owner поручение П3; `canonical writable owner` постановки, решений и applicability/MAD = Architect в этом плане. Planner владеет derived executable draft, Coder — реализацией runner/schema/manifest/workflow, Reviewer — текущим review proof. Sole N-A object materialized в Meta; Planner получает только helper-derived tagged ref.
- Applicability установлена по фактическому writer/reader/consumer boundary, а не по имени плана, количеству targets или старому carrier: `run_selected` сохраняет существующие completion/result/HEAD основания green/red, reports/events остаются proof outputs, workflow лишь выбирает test workload. П3 не меняет authorization, role/status routing, mutation authority или terminal admission Planveyor; существующий `machine_authority_decision_readback` остаётся единственным reader, а `validate_machine_authority_decision` его проектирует. Поэтому выбран `no_machine_authority_change`, не `docs_or_tests_only`. Новые поля выбора не становятся вторым writable process authority; изменение этих оснований вне данного contract требует Architect reroute, не silent N-A reuse.
- `repo default`: текущие 28 full rows сменяются целевыми 14 full 3.12 + одной `compat310` 3.10 только после реализации; `expected live default`: до отдельной публикации действует опубликованный workflow, локальный план его не меняет.
- `missing env/config pin behavior`: существующие prerequisite/lock/Python checks останавливают запуск; установки, исправление окружения и invented fallback не разрешены.
- `safe to merge`: только после фактических bounded P3 gates, независимой проверки root и обычного локального closeout; merge/publication сами по себе этим планом не разрешены.
- `safe to deploy`: `N/A (why=CI configuration and verification tooling; no application deployment)`.
- `safe to flip + after what follow-up/condition`: активация hosted workflow требует отдельной Owner publication; только свежий hosted результат опубликованного SHA может доказать hosted green. Локальная приёмка П3 не обещает время push и не закрывает последующие CI tiers.

### C-P3-1: supported i18n command route
Классификация: `same-contract reroute`, ограниченный исправлением command route после bounded STOP. Existing product helper вызывается из physical WORK как `"$PYBIN" -B scripts/i18n_pairs.py --project-root .`; его supported subcommands — `stamp README.ru.md`, `stamp docs/tools/verify_suite.ru.md` и `status`. Только эти три active calls в Commands заменяют неподдерживаемый frozen `planveyor_runtime_py i18n_pairs.py`. Lifecycle/MAD/provenance/lint helpers сохраняют frozen facade с явным `--project`; allowlist/runtime/Home/pins и другие guards не меняются, v3-name exception не расширяется.

Источник решения — actual WORK `scripts/i18n_pairs.py` и его `--help`: stamp пишет только existing registered RU copy sync line, сохраняя body bytes; status использует те же `doc_lint.inspect_i18n_pairs` rules и сам по себе не даёт selected-pair green. Существующий `i18n-selected` predicate по двум exact source/copy `ok` rows, source inventories, all report/event/identity assertions, nine targets, Scope и Acceptance остаются byte-for-byte прежними. Это выбор existing supported route, а не разрешение обойти отказ helper.

Owning route: после Architect decision Planner синхронизирует тот же executable draft и его stamps/proof order с тремя исправленными calls, сохраняя exact targets и derived MAD ref; затем normal lint/scoped-doc/strict bundle gates возвращают работу Coder. Это bounded reconciliation текущего контракта, без нового архитектурного scope cycle и без повторного Owner вопроса. Coder начинает fresh unique proofdir и исполняет весь agreed envelope на final source; preliminary 10/10 до двух последних assertions и прежние prerequisite rc0 не подменяют final-source proof. Отказ `child_rc=64/tee_rc=0/pipeline_rc=64` и исходные logs остаются историей C-P3-1; ни один pending compatibility/source-freeze/tomli/typecheck/i18n/review outcome не объявляется выполненным этим repair. Existing root Sol+GLM exact-candidate review checkpoint перед semantic commit сохраняется вместе с normal native Review/Architect sequence.

### Контракт minimal subset foundation
- Manifest сохраняет version 1, canonical `shards`, `zero_test_modules`, weighting и local profiles. Additive optional top-level `subsets` — mapping имени в object с единственным обязательным `ids`: непустой список unique fully-qualified canonical unittest IDs. Текущий manifest задаёт ровно один subset `compat310`. Отсутствие `subsets` допустимо для прежних full-shard consumers, но явный запрос отсутствующего subset и CI matrix без обязательного `compat310` дают отказ; fallback на полный Python 3.10 запрещён.
- CLI добавляет `--subset NAME` в существующую mutually-exclusive mode group. `--shard`, `--local-profile`, `--check` и `--matrix` сохраняют отдельные назначения; mixed modes отвергаются argparse. `--matrix` остаётся structural/no-import; `--check` выполняет canonical discovery и полный exact-once partition без тел тестов. Structural subset validation не заменяет discovery: до отбора/исполнения subset runner обязан успешно проверить весь canonical partition, затем подтвердить каждый ID subset в canonical inventory.
- Missing/malformed/duplicate JSON keys, malformed subset object/IDs, empty/duplicate/unknown ID и unknown subset name дают nonzero по существующему input-error path, без test execution и без green report. Невалидный full partition блокирует любой subset, даже когда выбранные IDs сами корректны. Нельзя discovery/load по списку IDs вместо полного existing canonical discovery.
- Execution фильтрует существующие canonical TestCase instances в canonical order; список `ids` не задаёт новый execution order и не создаёт cases заново. Existing module/class setup/teardown и `TrackedResult` planned/started/completed сохраняются. Existing post-discovery `head_before`, completion accounting, interruption и green/red/exit semantics не расширяются и не ослабляются.
- Report различает режимы: additive `selected_subset` равен имени subset либо `null`; `selected_shards` содержит только настоящие full shard IDs и пуст для subset. Existing planned event получает ту же identity выбора; event types `planned`, `started`, `completed` и их смысл сохраняются, новая event infrastructure не создаётся. Manifest SHA, ordered planned/started/completed IDs, Python, HEAD pair, wall time и actual rc остаются доказательствами того же запуска. Source SHA inventories снимаются в bounded proof context отдельно, без нового authoritative report family.
- Matrix сохраняет `python-version` и `meta`; full row несёт `shard=s01…s14`, compatibility row несёт `subset=compat310`, ровно один selection key на row. В текущем manifest это ровно 14 rows 3.12 и одна row 3.10, unique по version/selection. Workflow передаёт соответственно `--shard` или `--subset`; `meta=true` только на первой full 3.12, dependency setup и остальные existing workflow параметры неизменны. `mypy` target остаётся 3.10.
- Девять начальных IDs покрывают loader stream/error, runtime-closure/policy deny-before-effect, Python resolution/cache/strict/conda, strict marker/duplicate JSON и реальный public facade + Copier init/doctor/upgrade. `tomli` import/parse под 3.10 — отдельный environment proof, не production fallback. Если candidate не проходит или не покрывает named capability, Coder документирует причину и предлагает bounded замену существующим ID той же capability; исключение обязательной capability либо новый product/helper contour возвращается Architect. Нельзя заменить настоящий facade/Copier path моками или считать обязательную skipped capability квалифицированной по одному runner green.

### Bounded dependent inventory
| Carrier | Роль в изменении и consumer contract |
| --- | --- |
| `scripts/run_test_shard.py` | Единственный reader manifest и emitter matrix/report/events; selection остаётся test workload, input errors blocking, existing result/exit meanings сохранены. |
| `scripts/test_shards.json` | Canonical full partition и exact subset IDs; synthetic module получает одного full-shard owner, остальные selectors/weights/profiles не перераспределяются. |
| `scripts/test_shards.schema.json` | Additive subset shape; actual discovered membership и full partition доказывает runner, JSON Schema отдельно их не доказывает. |
| `scripts/test_run_test_shard.py` | Новые дешёвые synthetic fixtures и negative consumer proofs; temp fixture не становится checked-in corpus. |
| `.github/workflows/checks.yml` | Known executable consumer `--matrix` и `--shard`; добавляет явный subset branch, meta lane не дублируется. |
| `README.md`, `README.ru.md`, `docs/tools/verify_suite.md`, `docs/tools/verify_suite.ru.md` | Current version/verification contract и i18n stamps; исторические hosted facts и новые mechanics links сохраняются. |
| `Makefile`, `pyproject.toml`, `requirements-dev.lock`, `i18n/pairs.json`, `i18n/terms.md` | Read-only contextual consumers: canonical full routes, mypy 3.10, lock/range и зарегистрированные пары не меняются; новых Manager commands/one-shot dispatch surfaces нет (`N/A (why=not an owner-facing Manager command change)`). |

### Узкое Owner exception для actual v3 ролей
Owner в root chat прямо разрешил: «обходите гард, не ебите мозги». Это latest override прежнего root no-UUID/no-v3-cache STOP исключительно для application canonical-v2-name predicate пяти фактических v3 ролей. Новый Manager/init/config, runtime/Home/pin patches, ручные cache/receipt writes и обход других authority/liveness/role/runtime guards не разрешены.

После natural bootstrap completed, exact `list_agents` readback со статусом `completed` и fresh actual SID/project/role/model=`gpt-6.1-sol`/effort=`ultra` Manager использовал существующий public writer через Legacy SID branch: `planveyor_collab_state_write_alive <role> <ACTUAL_V3_SID> spawn 'Owner-approved v3-name exception; actual task=/root/...v3; exact liveness/model verified'`. SID в cache остаётся diagnostic Owner exception; сообщения отправляются только actual v3 task name. Старый отказ string-name admission не является обязательной повторной проверкой после этого разрешения. Любой отказ другого guard требует STOP с фактом для root.

| Role | Live task | Actual provider SID (diagnostic exception) |
| --- | --- | --- |
| Architect | `/root/architect_sol_ultra_v3` | `01a1a3f8-4b61-7990-85a7-772617f74a7f` |
| Planner | `/root/planner_sol_ultra_v3` | `01a1a3fe-aba4-7113-9712-75d1e2a05b74` |
| Coder | `/root/coder_sol_ultra_v3` | `01a1a401-218e-70c2-9fb0-8b7f29e1d26e` |
| Reviewer risk | `/root/reviewer_code_risk_sol_ultra_v3` | `01a1a403-3d4b-7252-b2d0-14d0ba318323` |
| Reviewer contracts | `/root/reviewer_code_contracts_sol_ultra_v3` | `01a1a406-3e8f-7483-ac37-d43357c3cac7` |

Сохранённые root readbacks показывают для каждой строки actual project текущей WORK, соответствующую role и Sol/ultra; статус `completed` относится к завершённому bootstrap, не объявляет текущее semantic execution завершённым. Per-role `invocation.json`, `native-readback.json`, `stdout`, `stderr`, `result.json` под `.tmp/ci_p3_proof/manager-v3-sid-admission-*` сохраняют actual argv/streams/rc и cache hashes без переноса private local paths сюда. У всех пяти writer runs `child_rc=0`, оба tee rc=0, `overall_rc=0`, cache/log hashes изменились. Предшествующий `.tmp/ci_p3_proof/manager-v3-admission-20261104T003655Z` сохранил настоящий `child_rc=1` на incompatible V2 task name, оба tee rc=0 и равные before/after cache hashes. Это exception proof, не canonical V2 admission и не разрешение для старого П2.

## Scope
- `scripts/run_test_shard.py`, `scripts/test_shards.json`, `scripts/test_shards.schema.json` — минимальная subset selection foundation.
- Новый `scripts/test_run_test_shard.py` — дешёвые synthetic scheduling/selection tests; один full-shard owner в manifest.
- `.github/workflows/checks.yml` — ось 14×3.12 + 1×3.10, существующие прочие параметры сохраняются.
- `README.md`, `README.ru.md`, `docs/tools/verify_suite.md`, `docs/tools/verify_suite.ru.md` и их existing inline i18n stamps — фактический version/verification contract поверх нового документационного baseline.
- Authoritative exact targets — девять files linked code draft; owning lifecycle carriers plan/draft/review/support добавляются отдельно штатно.

## Out of scope
Fast witnesses/tier, новая event infrastructure, concurrency, weights/local profiles, deadline/timeouts, product cache, группа В fixes, lock/pyproject/product scenario changes; профилирование close. Runtime, gateway, прежние площадки и Home settings immutable. Push, GitHub writes, CI rerun/cancel, runner connection, cleanup запрещены.

## Follow-ups (deferred)
`N/A (why=no accepted P3 obligation deferred; later CI tiers and close profiling remain separately owned external roadmap work, not activated by this ordinary plan)`.

## Rollout packet handoff
- Role: `N/A (why=no cross-repo packet)`
- Packet path: `N/A (why=no cross-repo packet)`
- Target repo: `N/A (why=Self-Planveyor)`
- Suggested target plan slug: `N/A (why=no target import)`
- Queue after import: `N/A (why=no queue)`

## Small-slice conveyor classifier
- Requested profile: `N/A (why=normal full owning lifecycle)`
- Expected bundle family: `N/A (why=runner/schema/workflow code)`
- Helper validation: `N/A (why=no reduced censors requested)`
- Drift behavior: `N/A (why=normal conveyor guards apply)`

## Close-out routing
- Roadmap/queue sync: `N/A (why=single ordinary plan; external roadmap belongs to root)`
- Follow-up sync: штатный external followups/PI closeout, только реальные findings; terminal plan после semantic commit не переписывается.
- Next bounded slice: `N/A (why=no successor activation authorized in this plan)`
- Terminal outcome: yes — accepted code+proof переведены на ordinary native local semantic materialization; Done записывается только при helper commit_ready и подтверждается фактическим exact commit либо helper already_materialized. Root precommit Sol+GLM checkpoint и current19 copy-only scan приняты decision002. Manager capture/followups/PI/final-docs и root fresh final p0/postcommit closeout/privacy readback terminal docs delta остаются owning terminal-tail obligations; их выполнение здесь не заявляется. Push отсутствует.

## Business decomposition framing
`N/A (why=ordinary bounded technical dev plan)`.

## Child plan map
`N/A (why=no decomposition or promoted children)`.

## Small-model-ready child contract
`N/A (why=not a promoted decomposition child)`.

## Decomposition quality gate
`N/A (why=no decomposition wave)`.

## Execution queue
`N/A (why=ordinary single-plan native run without --q)`.

## Queue close-out
- On terminal child completion: `N/A (why=no queue)`
- On non-terminal stop: `N/A (why=no queue)`
- Parent resume: `N/A (why=no parent)`

## Mechanism coverage
`N/A (why=no decomposition wave)`.

## Analysis pack
`N/A (why=not an analysis_wave plan)`.

## Promoted route artifact
`N/A (why=direct Owner ordinary plan, not analysis promotion)`.

## Constraints / Assumptions
- Локальная приёмка P3 отделена от публикации и hosted CI. Полный hosted green относится только к фактическому опубликованному SHA; не объявлять его по локальным proof.
- `--matrix` — structural check, не imported discovery/exact-once proof. Исторические 3517 IDs не выдаются за текущий count; новый synthetic module меняет canonical suite.
- Запуск полного verify-full или всех 14 частей не требуется и не разрешён в этом bounded плане. Нужны адресные synthetic/affected checks, свежая canonical coverage и реальные compatibility executions.

## Risks / Open questions (summary)
- Candidate list может оказаться недостаточным либо дать skip; объяснить и квалифицировать actual subset внутри accepted scope. Не менять глобальный skip contract.
- Open Owner questions: `N/A (why=all semantic choices accepted; current Architect contract and Planner executable detailing complete)`.

## Reviewability preflight receipt
- `proof-path class`: `checked-in repo-local helper`
- `mandatory primary lane`: synthetic runner tests и свежий full canonical partition check; negative subset/partition inputs fail closed.
- `mandatory non-primary carrier / contextual lane`: реальное compat310 выполнение на 3.10 и 3.12, bootstrap/import/Copier path, matrix/meta readback и документальная пара.
- `exact helper path + support files`: `scripts/run_test_shard.py`, `scripts/test_shards.json`, `scripts/test_shards.schema.json`, новый `scripts/test_run_test_shard.py`.
- `dependent tests / dependent docs / known consumer paths`: literal inventory в `Decisions (final)`; workflow — executable matrix/report consumer, четыре RU/EN doc carriers — synchronous targets, Make/lock/typecheck/i18n registry — read-only context. Executable exact inventory = девять targets linked code draft, first strict preflight перед Coder.
- `preconditions / seed-discovery`: locked environments, Python/PATH identity, full discovery до subset, physical TMPDIR; transient launch inputs.
- `reroute rule`: mandatory lane red/missing либо текущий mandatory gate failure — `same-contract reroute` к owning роли; дополнительный implementation contour — `real scope expansion` к Architect; model/effort drift native роли — STOP. Разрешено только записанное выше v3-name exception; обход остальных guards и перенос старых recovery permissions запрещены.
- `report continuity`: Coder выполняет `discovery-or-seed` на окончательных source/manifest bytes; Reviewer и final Architect используют `receipt-reuse-only` того же proof. Identity = source/manifest SHA-256, Python identity, ordered selected IDs, report/events pair и existing `head_before`/`head_after`; потеря пары или drift требует нового owning proof, не silent rediscovery другого запуска. Exact observer boundary остаётся существующим post-discovery `head_before`; новые event families и более широкий drift contract не вводятся.
- `mutation truth / retention`: `notice/success text != mutation truth`; closure доказывается фактическим final report (`completion_exact`, `result_successful`, status и HEAD equality), matching event trace и actual child rc. `.tmp/ci_p3_proof/*` = `transient local sanity only`; Reviewer materialize-ит нужный bounded durable proof в sole review artifact и его explicit support assets, не делает transient log заменой durable review. `runtime-lineage preflight`: frozen runtime pin, actual Python и source bytes проверяются до proof; stale runtime reroute принадлежит runtime-owning root, runtime в П3 не меняется.

- `perceptual truth-source split`: structural/repo-backed JSON/events/source preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over canonical artifact = bounded fallback; repeated image fallback = helper gap. `N/A (why=no visual proof required)`.

## Changes (by area)
- `scripts/run_test_shard.py`: reader additive `subsets`, mutually-exclusive `--subset`, полный partition до фильтра original cases; emitters `--matrix`, report `selected_subset`/`selected_shards` и existing planned event согласованы. `canonical_writer` definition = Coder в checked-in manifest, consumer = existing runner; outputs derived proof, не writable process authority.
- `scripts/test_shards.json`, `scripts/test_shards.schema.json`: один `compat310` exact-ID object и additive shape; один owner нового synthetic module, прежний full partition и profiles сохраняются.
- `scripts/test_run_test_shard.py`: cheap synthetic trace для selection identity/order, module/class hooks, selected-only execution, negative full partition/subset/modes, incomplete accounting и HEAD drift на existing boundary.
- `.github/workflows/checks.yml`: 15-row matrix consume с явными full/subset branches, single meta; остальные runtime/timeout/concurrency/install параметры сохраняются.
- Четыре README/verify-suite RU/EN targets из Scope: отделить full 3.12, compat310 3.10, технический loader range и supported environment; сохранить existing links/исторические hosted facts, синхронизировать inline source stamps. Existing mypy3.10/lock/pyproject и read-only consumers не меняются.


### Executable inventory / read_set / emitter decisions
Authoritative implementation/doc inventory = девять literal `code_draft_meta.targets` linked draft; plan/draft/review/assets входят в lifecycle bundle отдельно, origin plan не является mutable current-review target.
`read_set` и exact emitter/consumer decisions перечислены в draft → `Read set / unchanged consumers` и `Receipt schema emitter inventory / payload parity`. Новый test module до Coder содержит только fail-closed path-tracking stub с plan ref и `replace before Ready for Review`; это не implemented proof.
Changed fields: optional manifest `subsets.<name>.ids`; CLI `--subset`; matrix XOR `shard`/`subset`; report и existing planned event `selected_subset` + `selected_shards`. Sole reader/emitter = `scripts/run_test_shard.py`, matrix consumer = `.github/workflows/checks.yml`, shape = `scripts/test_shards.schema.json`. Для каждой строки draft называет regression/readback; owner-facing generated skeleton/bootstrap emitters и one-shot dispatch `N/A (why=no Manager/queue/role command or process authority change)`.
Full/local legacy execution без optional subsets остаётся valid; configured CI matrix без compat310 — nonzero. `--check` сохраняет canonical imports/full partition и дополнительно доказывает membership всех configured subset IDs, без test bodies. `jsonschema` не добавлять: новых зависимостей нет, shape/reader parity удерживает cheap stdlib test.
Golden Path: `N/A (why=bounded CI runner change; no named Golden Path workflow is changed)`.

## Acceptance criteria / DoD
- [x] Непустой известный unique subset. Missing, duplicate, unknown, empty ID и unknown subset name дают отказ; дефект full partition блокирует subset.
- [x] Canonical instances/order и module/class hooks сохранены; synthetic trace доказывает planned/started/completed порядок и неисполнение невыбранных methods.
- [x] Incomplete started/completed и existing-boundary HEAD drift дают nonzero/red.
- [x] Ровно 15 unique matrix rows: s01…s14 3.12, compat310 3.10, meta=true ровно один раз на full 3.12; mypy3.10 сохранён.
- [x] Реальные 3.10/3.12 compatibility evidence содержат exact list, reports/events, source/manifest SHA, actual child rc и elapsed; нет unexplained skips/failures/errors.
- [x] Fresh canonical partition covers final source bytes exactly once; synthetic module назначен единственному full shard.
- [ ] Scoped doc checks, plan/bundle/review gates и normal terminal closeout фактически green; новые README/mechanics links сохранены.
- [ ] Private copy-only scan и финальный p0 выполнены без чтения/печати словаря; runtime/gateway/Home/old terminal artifacts неизменны; push отсутствует.
- [x] `--subset` и mixed modes, `selected_subset`/`selected_shards`, planned event и matrix selection keys соответствуют одному contract; emitter/assertion/readback parity проверены consumer tests, не только schema.

### UI contract checklist (required if touching UI)
`N/A (why=no UI change)`.

### Handoff checklist (Architect → Planner; before `Ready for Planner`)
- [x] Единственный MAD source-backed и helper-valid; Planner получает только tagged derived ref.
- [x] Literal dependent inventory, mandatory primary/contextual lanes, six rollout fields и reroute boundaries concrete; Owner Q&A clean.
- [x] Executable draft остаётся Planner-owned; missing draft до Planner и PLANNED review не выдаются за strict executable green.


### Handoff checklist (Planner → Coder; before `Ready for Coder`)
- [x] Принятые Decisions/Scope сохранены; девять exact targets, literal read_set и sole planned review совпадают между plan и code draft.
- [x] Code draft materialized public scaffold helper; только derived tagged N-A ref с validated upstream digest, без semantic core/нового authority carrier.
- [x] Новый synthetic file имеет только fail-closed path-tracking stub; fixture outcomes, report/event identity, legacy/no-subsets и matrix/missing-compat ветки executable, product implementation не выполнена Planner.
- [x] Команды используют existing transient-selected PYBIN, frozen facade для owning helpers и WORK для product proof; both-stream tee и child/tee/pipeline rc раздельны. Physical TMPDIR/prerequisites, exact-pair i18n readback и runtime/source continuity заданы буквально.
- [x] Strict first executable preflight фактически rc0: девять targets + plan/draft + sole PLANNED review, 12 paths, 0 issues. Это inventory/handoff proof, не completed product или review acceptance.
- [x] Plan lint, scoped links/basic-hygiene и shell/embedded-Python syntax фактически green; UI/visual contract N/A, открытых Planner/Owner вопросов нет.
- [x] Closure-path self-check: «если Coder/Reviewer буквально следуют plan + draft, что придётся угадывать и где выживет тот же blocker?» — ничего: каждая accepted capability имеет execution lane, каждый changed payload — emitter/consumer/assertion, report continuity и red reroute literal. Реальные outputs остаются Coder/Reviewer обязанностью.

## Retrieval telemetry receipt
- Outcome: `not_used_for_decision`.
- Reason: SQLite index отсутствует; current frozen Planner prompt разрешает bounded `rg` fallback. Использованы named repo-backed sources и literal anchors, index/retrieval не строились и retrieval qualification не заявляется.
- query_event_id / read_event_id / read_log_status: `N/A (why=no instrumented retrieval was used)`.
- Opened source carriers: runner/schema/manifest/workflow, current doc pairs, lock/pyproject/Make/i18n contract, ADR 004/006 и doc-lint playbook; конкретные readonly consumers закреплены в draft read_set.

## Visual Acceptance (browser, UI tasks)
### Visual gate (S1)
`N/A (why=CLI/CI code and documentation only; no visual UI)`.
### Visual env (обязательно для UI-задач)
- Modes to test: `N/A (why=no visual UI)`
- Endpoint/port: `N/A (why=no visual UI)`
- Visual evidence: `N/A (why=no visual UI)`
### Login (Reviewer)
- Accounts/credentials: `N/A (why=no UI login)`
### How to run (Reviewer)
- Status: `N/A (why=no visual UI)`
- Start: `N/A (why=no visual UI)`
- Stop: `N/A (why=no visual UI)`
- Preconditions: `N/A (why=no visual UI)`
### Visual checks (screenshots required for UI tasks)
`N/A (why=no visual UI)`.
### Visual regression scenarios (docs/smoke_visual.md)
`N/A (why=no visual UI)`.
### Perf checks (optional; recommended for perf tasks)
Actual compatibility elapsed фиксируется по реальному выполнению, без обещания 15 минут на push.

## Tests
### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)
`N/A (why=no UI; runner invariants explicitly covered below)`.
### Что написать / поправить
В новом `scripts/test_run_test_shard.py` обязательны proposed методы `test_subset_rejects_invalid_shape_ids_and_name`, `test_subset_requires_valid_whole_partition`, `test_subset_preserves_instances_order_and_hooks`, `test_subset_cli_report_and_events_share_identity`, `test_legacy_full_and_local_modes_without_subsets`, `test_matrix_and_workflow_selection_contract`, `test_matrix_is_structural_and_requires_compat310`, `test_incomplete_started_or_completed_is_red`, `test_interruption_retains_non_green_partial_report`, `test_existing_head_boundary_drift_is_red`. Они новые; literal fixture inputs/expected traces, parser/emitter/consumer assertions и boundaries перечислены в linked code draft → `Synthetic tests`, без product patch spec. Cheap synthetic roots под physical TMPDIR, real WORK CLI с --root fixture там, где проверяются report/matrix/CLI; heavy product modules внутри synthetic suite не исполняются. Новый whole-module selector `test_run_test_shard` принадлежит ровно `s03`, остальные assignments/weights/profiles не менять.
### Что прогнать
Сначала адресный synthetic/affected suite на финальных implementation bytes, затем fresh full canonical `--check` без исполнения всех shards и structural matrix15/meta1. После этого Coder реально исполняет `--subset compat310` на existing 3.10 и 3.12; каждый такой запуск сам повторно проверяет полный canonical partition перед selection. Captured source/manifest hashes до/после двух executions совпадают; ordered selected IDs одинаковы на обеих axes, actual rc и elapsed записаны. Проверяются locked packages, actual Python/PATH, physical TMPDIR, отдельный 3.10 `tomli` parse и настоящий facade/Copier capability. Ноль failures/errors; любой skip имеет literal reason и capability disposition, обязательная capability не считается доказанной без исполнения. Глобальный skip contract не меняется. Relevant scoped docs/i18n, lint, bundle, review и terminal gates остаются отдельными фактическими результатами; full suite/full14 не запускаются.

Начальные девять candidate IDs:
```text
test_contract_authority_loader_stream.ContractAuthorityLoaderStreamTests.test_header_is_not_executed_and_body_status_stays_in_current_shell
test_contract_authority_loader_stream.ContractAuthorityLoaderStreamTests.test_missing_supported_python_explains_how_to_select_it
test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_runtime_closure_and_runner_policy_drift_fail_before_effect_sentinel
test_pybin.PybinResolveTests.test_project_cache_is_ignored_in_favor_of_path_python3
test_pybin.PybinResolveTests.test_explicit_invalid_pybin_stays_strict
test_pybin.PybinResolveTests.test_conda_prefix_precedes_path_python3
test_contract_authority_snapshot.AuthoritySnapshotTests.test_local_marker_v3_has_exact_live_fields
test_contract_authority_snapshot.AuthoritySnapshotTests.test_duplicate_json_keys_and_non_json_bytes_are_rejected
test_consumer_contract.ConsumerContractFacadeTests.test_public_facade_init_doctor_and_compatible_upgrade
```

## Commands
Все блоки ниже запускаются из physical WORK в одном zsh после Coder implementation; до замены fail-closed synthetic stub product proof запрещён. PYBIN уже supplied trusted launch interpreter; absolute private values остаются только transient inputs/logs. Это `WORK` checks, а Planveyor helpers используют только frozen facade. Установки и полный suite/full14 не выполняются.

### Envelope и final documentation bytes
```zsh
export PYTHONDONTWRITEBYTECODE=1
P3_PY312="$("$PYBIN" -B -c 'import json,pathlib; print(json.loads(pathlib.Path(".tmp/ci_p3_reference/operator_inputs.json").read_text())["python312"])')"
P3_PY310="$("$PYBIN" -B -c 'import json,pathlib; print(json.loads(pathlib.Path(".tmp/ci_p3_reference/operator_inputs.json").read_text())["python310"])')"
export TMPDIR="$("$PYBIN" -B -c 'import json,pathlib; print(json.loads(pathlib.Path(".tmp/ci_p3_reference/operator_inputs.json").read_text())["physical_tmpdir"])')"
export PYBIN="$P3_PY312"
export PATH="$(dirname "$PYBIN"):$PATH"
P3_PROOF="$PWD/.tmp/ci_p3_proof/coder-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$P3_PROOF"
zmodload zsh/datetime
p3_run() {
  local label="$1"; shift
  local -F begun=$EPOCHREALTIME
  "$@" 2>&1 | tee "$P3_PROOF/$label.log"
  local -a p3rc=( "${pipestatus[@]}" )
  local -i final=$(( p3rc[1] != 0 ? p3rc[1] : p3rc[2] ))
  print -r -- "child_rc=$p3rc[1] tee_rc=$p3rc[2] pipeline_rc=$final elapsed_seconds=$(( EPOCHREALTIME - begun ))" | tee "$P3_PROOF/$label.status"
  return "$final"
}
set -e
for axis in 310 312; do
  if [[ "$axis" == 310 ]]; then export PYBIN="$P3_PY310"; else export PYBIN="$P3_PY312"; fi
  export PATH="$(dirname "$PYBIN"):$PATH"
  p3_run prerequisites-$axis "$PYBIN" -B -c 'import importlib.metadata as m,json,os,pathlib,shutil,subprocess,sys; assert sys.version_info[:2]==((3,10) if sys.argv[1]=="310" else (3,12)); assert all(shutil.which(t) for t in ("git","zsh","rg","make")); tmp=pathlib.Path(os.environ["TMPDIR"]); assert tmp.is_absolute() and tmp.is_dir() and tmp==tmp.resolve(); g=subprocess.run(["git","-C",str(tmp),"rev-parse","--is-inside-work-tree"],capture_output=True,text=True); assert g.returncode==128 and "not a git repository" in g.stderr; pins={"copier":"9.18.2","PyYAML":"6.0.3","mypy":"1.15.0","mypy_extensions":"1.1.0","typing_extensions":"4.15.0"}; assert all(m.version(k)==v for k,v in pins.items()); print(json.dumps({"python":sys.version,"executable":sys.executable,"locked":pins,"tmpdir_outside_git":True}))' "$axis"
done
export PYBIN="$P3_PY312"
export PATH="$(dirname "$PYBIN"):$PATH"
p3_run stamp-readme "$PYBIN" -B scripts/i18n_pairs.py --project-root . stamp README.ru.md
p3_run stamp-verify "$PYBIN" -B scripts/i18n_pairs.py --project-root . stamp docs/tools/verify_suite.ru.md
```

При nonzero сохранить этот run, исправить owning cause и начать новый unique proofdir. Existing reports не перезаписывать. Shell function — command envelope, не новая product/helper family и не canonical receipt.

### Source freeze и bounded execution
```zsh
p3_sources() {
  "$PYBIN" -B - <<'PY'
import hashlib,json,pathlib,re
root=pathlib.Path.cwd()
text=(root/"docs/code_drafts/261104_0314_ci_python_compat_subset__code_draft.md").read_text()
meta=json.loads(re.search(r"```json\n(.*?)\n```",text,re.S).group(1))["code_draft_meta"]
paths=[row["path"] for row in meta["targets"]]+["Makefile","pyproject.toml","requirements-dev.lock","i18n/pairs.json","i18n/terms.md","scripts/test_contract_authority_loader_stream.py","scripts/test_contract_authority_shell.py","scripts/test_pybin.py","scripts/test_contract_authority_snapshot.py","scripts/test_consumer_contract.py"]
print(json.dumps({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(set(paths))},sort_keys=True))
PY
}
p3_run sources-before p3_sources
p3_run synthetic-312 "$PYBIN" -B -m unittest discover -s scripts -p test_run_test_shard.py -v
p3_run coverage-312 "$PYBIN" -B scripts/run_test_shard.py --check
p3_run matrix "$PYBIN" -B scripts/run_test_shard.py --matrix
for axis in 310 312; do
  if [[ "$axis" == 310 ]]; then export PYBIN="$P3_PY310"; else export PYBIN="$P3_PY312"; fi
  export PATH="$(dirname "$PYBIN"):$PATH"
  p3_run identity-$axis "$PYBIN" -B -c 'import sys,json,hashlib,pathlib,importlib.metadata as m; exe=pathlib.Path(sys.executable).resolve(); print(json.dumps({"python":sys.version,"executable":sys.executable,"executable_basename":exe.name,"executable_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"locked":{p:m.version(p) for p in ("copier","PyYAML","mypy","mypy_extensions","typing_extensions")}})); assert m.version("copier")=="9.18.2"; assert m.version("PyYAML")=="6.0.3"; assert m.version("mypy")=="1.15.0"; assert m.version("mypy_extensions")=="1.1.0"; assert m.version("typing_extensions")=="4.15.0"'
  p3_run bare-python-$axis zsh -lc 'export PATH="$(dirname "$PYBIN"):$PATH"; python3 -c "import hashlib,json,os,pathlib,sys; assert sys.version_info[:2]==((3,10) if sys.argv[1]==\"310\" else (3,12)); assert os.path.samefile(sys.executable,sys.argv[2]); exe=pathlib.Path(sys.executable).resolve(); print(json.dumps({\"python\":sys.version,\"executable_basename\":exe.name,\"executable_sha256\":hashlib.sha256(exe.read_bytes()).hexdigest()}))" "$1" "$PYBIN"' p3 "$axis"
  p3_run compat-$axis "$PYBIN" -B scripts/run_test_shard.py --subset compat310 --report "$P3_PROOF/compat-$axis.json"
done
export PYBIN="$P3_PY310"
p3_run tomli-310 "$PYBIN" -B -c 'import tomli,importlib.metadata as m; assert m.version("tomli")=="1.1.0"; assert tomli.loads("p3 = 310")["p3"]==310; print("tomli 1.1.0 import/parse OK")'
export PYBIN="$P3_PY312"
export PATH="$(dirname "$PYBIN"):$PATH"
p3_run typecheck make typecheck
p3_run sources-after p3_sources
```

Отдельный prerequisite readback до execution подтверждает Git/zsh/rg/make, expected Python axes и physical TMPDIR вне любого Git worktree; expected nonzero Git probe не пропускать через `set -e` как success. Existing locked envs только читаются. Bare-python probe обязан assert expected version и physical same-file identity с selected PYBIN; symlink spelling не сравнивается буквально. Identity emitter захватывает executable_basename/executable_sha256 до каждого compatibility run, а same-run readback сравнивает их с bare-python capture. Identity logs могут содержать private executable path: в durable public evidence сохранять version/basename/hash и `<REDACTED>` для local path; raw identity остаётся transient. Elapsed command envelope включает discovery, report wall_seconds — только existing suite boundary.

### Same-run report/events/matrix readback
```zsh
p3_run proof-readback "$PYBIN" -B - "$P3_PROOF" <<'PY'
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
before=json.loads((p/"sources-before.log").read_text())
assert before==json.loads((p/"sources-after.log").read_text())
manifest=json.loads(pathlib.Path("scripts/test_shards.json").read_text())
matrix=json.loads((p/"matrix.log").read_text())["include"]
full=[r for r in matrix if "shard" in r]; compat=[r for r in matrix if "subset" in r]
assert len(matrix)==15 and len(full)==14 and len(compat)==1
assert {r["shard"] for r in full}=={f"s{i:02}" for i in range(1,15)}
assert all(r["python-version"]=="3.12" and "subset" not in r for r in full)
assert compat[0]=={"python-version":"3.10","subset":"compat310","meta":False}
assert sum(r["meta"] is True for r in matrix)==1 and full[0]["meta"] is True
ordered=[]
for axis,version in (("310","3.10"),("312","3.12")):
    report=json.loads((p/f"compat-{axis}.json").read_text())
    identity=json.loads((p/f"identity-{axis}.log").read_text())
    bare=json.loads((p/f"bare-python-{axis}.log").read_text())
    assert identity["python"].startswith(version) and bare["python"].startswith(version)
    assert identity["executable_basename"]==bare["executable_basename"]
    assert identity["executable_sha256"]==bare["executable_sha256"] and len(bare["executable_sha256"])==64
    assert (p/f"bare-python-{axis}.status").read_text().startswith("child_rc=0 tee_rc=0 pipeline_rc=0 ")
    events=[json.loads(line) for line in (p/f"compat-{axis}.json.events.jsonl").read_text().splitlines()]
    ids=report["planned_ids"]; ordered.append(ids)
    assert report["status"]=="green" and report["completion_exact"] is True and report["result_successful"] is True
    assert report["head_before"]==report["head_after"] and report["python"].startswith(version)
    assert report["selected_subset"]=="compat310" and report["selected_shards"]==[]
    assert ids==report["started_ids"]==report["completed_ids"] and len(ids)==len(set(ids))
    assert set(ids)==set(manifest["subsets"]["compat310"]["ids"]) and report["tests_run"]==len(ids)
    assert report["failures"]==report["errors"]==report["skipped"]==[] and report["wall_seconds"]>=0
    assert report["manifest_sha256"]==before["scripts/test_shards.json"]
    first=events[0]; assert first["event"]=="planned" and first["ids"]==ids
    assert first["manifest_sha256"]==report["manifest_sha256"] and first["head"]==report["head_before"]
    assert first["selected_subset"]=="compat310" and first["selected_shards"]==[]
    assert [(e["event"],e["id"]) for e in events[1:]]==[(kind,i) for i in ids for kind in ("started","completed")]
    assert (p/f"compat-{axis}.status").read_text().startswith("child_rc=0 tee_rc=0 pipeline_rc=0 ")
assert ordered[0]==ordered[1]
assert "test_consumer_contract.ConsumerContractFacadeTests.test_public_facade_init_doctor_and_compatible_upgrade" in ordered[0]
print(json.dumps({"proof":"bounded compat310","axes":["3.10","3.12"],"selected_ids":ordered[0],"matrix_rows":len(matrix),"manifest_sha256":before["scripts/test_shards.json"]}))
PY
```

Нужен actual executed capability mapping по всем девяти ID families; readback не заменяет чтение assertion bodies и реальный facade/Copier outcome. Bounded replacement существующим ID той же capability требует обновить exact expectation этого readback, plan/draft и evidence до повторного owning proof; mandatory capability исключать нельзя. Синтетические negative outputs и interrupted report не выдаются за real compatibility report.

### Scoped docs / i18n и role gates
```zsh
p3_run doc-links env PYBIN="$PYBIN" bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --product-root "$PWD" --root README.md --root README.ru.md --root docs/tools/verify_suite.md --root docs/tools/verify_suite.ru.md --root docs/plans/261104_0314_ci_python_compat_subset.md --root docs/code_drafts/261104_0314_ci_python_compat_subset__code_draft.md
p3_run doc-hygiene env PYBIN="$PYBIN" bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --product-root "$PWD" --check-basic-hygiene --root README.md --root README.ru.md --root docs/tools/verify_suite.md --root docs/tools/verify_suite.ru.md --root docs/plans/261104_0314_ci_python_compat_subset.md --root docs/code_drafts/261104_0314_ci_python_compat_subset__code_draft.md
p3_run i18n-status "$PYBIN" -B scripts/i18n_pairs.py --project-root . status
p3_run i18n-selected "$PYBIN" -B - "$P3_PROOF/i18n-status.log" <<'PY'
import pathlib,sys
rows=[line.split() for line in pathlib.Path(sys.argv[1]).read_text().splitlines()]
for source,copy in (("README.md","README.ru.md"),("docs/tools/verify_suite.md","docs/tools/verify_suite.ru.md")):
    matching=[r for r in rows if len(r)==4 and r[1:]==[source,"->",copy]]
    assert matching==[["ok",source,"->",copy]], (source,matching)
print("Both changed registered pairs: exact source/self hashes current; no selected-pair findings.")
PY
p3_run plan-lint "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/261104_0314_ci_python_compat_subset.md
p3_run bundle-preflight "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261104_0314_ci_python_compat_subset.md
p3_run diff-hygiene git diff --check -- scripts/run_test_shard.py scripts/test_shards.json scripts/test_shards.schema.json scripts/test_run_test_shard.py .github/workflows/checks.yml README.md README.ru.md docs/tools/verify_suite.md docs/tools/verify_suite.ru.md docs/plans/261104_0314_ci_python_compat_subset.md docs/code_drafts/261104_0314_ci_python_compat_subset__code_draft.md
```

`--i18n-strict` CLI в frozen doc_lint игнорирует root restriction для i18n и проверяет все пары. Поэтому current exact-pair gate выше читает canonical `i18n_pairs status` и требует ровно один `ok` row для каждой изменённой пары; его rc0 сам по себе не proof. Это не broad strict green и не изменение frozen helper. Scoped lint roots расширяются единственным materialized review path после его создания; assets проверяет exact bundle/current-review helper. До materialized review first executable preflight допускает только sole review как PLANNED. Final strict `--check` остаётся post-review gate.

Private copy-only scanner, independent concrete candidate/freeze review и final p0 принадлежат root; dictionary только передаётся existing scanner из external inputs, source shared index не меняется. Native роли не придумывают эти команды и не вызывают external models. No push/GitHub/CI/runner connection/cleanup/full verify/full14.

## Verification rerun / exec handoff
- Mode: reuse-thread
- Context source: literal `PLAN_PATH` + current `PRE_STATUS_LINE` + linked source/canon + finalized nine-target code draft и `## Commands`.
- Prompt: проверить только accepted compat310/full partition/matrix/identity contract и actual current proof; не расширять runtime, product scenarios, CI tier или публикацию; новый semantic gap вернуть Architect.
- Command: `N/A (why=Manager dispatches existing persistent owning roles by oracle; no alternate role runner or manual SID command)`
- Expected artifact: `docs/code_reviews/261104_0314_ci_python_compat_subset.md` — materialized, sole live review route.

## Evidence (chronological, append-only)
- 04.11.2026 operator: actual base/clean/runtime/Python prerequisites проверены до materialization; исходный optional env probe ошибочно требовал неуказанный в lock jsonschema и завершился rc=1. Исправленный read-only probe проверяет actual lock packages без установки/изменения среды. Historical plans все Done, matching open follow-up не найден. Native semantic/lifecycle результаты ещё отсутствуют.
- [2026-11-04 03:55 +0300] (Architect initial intake) Прочитаны frozen initial-draft prompt, target-local Architect rules (обе локальные секции N/A), plan и relevant source/canon. Fresh oracle `0ea9f85f-15f4-4c77-ae8b-5f5a70a41e17` дал `manager_mode_admitted=true`, initial status, `route_guard_triggered=false`, Owner Q&A clean и early MAD `not_required/initial_architect_draft_no_carrier`; это не downstream admission и не runtime acceptance. Source runner требует full partition и хранит original instances, а текущая matrix ещё 28 rows; новые 15 rows не заявлены выполненными. Повторный bounded поиск не нашёл отдельный compat310 outcome в followups/reviews; historical П1/П2/manifest plans остаются Done и read-only. Docs index отсутствует: retrieval build не выполнялся, использован bounded `rg`.
- [2026-11-04 03:55 +0300] (Architect, owning journal П3) Точное новое Owner exception и проверенные факты всех пяти Legacy SID admissions записаны в `Decisions (final)` этого П3; old string-name refusal rc1/no delta сохранён как historical failure, не замазан wrapper success. Старый П2 не менялся. Public provenance helper с supported explicit actual `--session-sid`, `--thread-id`, `--parent-thread-id` и `manager-collab` вернул rc0; его exact block materialized выше. Default wrapper SID из `.planveyor.session.architect` не использован. Streams и child/tee/pipeline rc текущего intake сохраняются в `.tmp/ci_p3_proof/architect-initial-20261104-v3/`.
- [2026-11-04 03:57 +0300] (Architect, initial gates) Frozen-facade `plan_lint.py` для текущего `Architect draft` дал actual child rc0 с единственным WARN о пока отсутствующем Planner-owned code draft. Advisory `planveyor_plan_bundle --preflight` дал настоящий child rc1/pipeline rc1, tee rc0: plan OK, code draft MISSING-PATH, sole review PLANNED; это не executable green и не основание забирать draft у Planner. Existing frozen `run_doc_lint.sh` с explicit product root и literal root только этого plan дал rc0 отдельно для link pass и basic-hygiene pass; broad canonical lint не запускался и не объявлен green. `git diff --check -- <PLAN_PATH>` rc0 учтён вместе с реальным scoped basic-hygiene: plan пока untracked, поэтому один Git diff сам по себе его bytes не проверяет. Final readbacks после этой записи сохраняются тем же proof prefix; stdout/stderr и child/tee/pipeline rc раздельны.

- [2026-11-04 04:01 +0300] (Architect CENSOR) OK: Architect draft validated; current=true. Censor dispatch id: censor:architect:eb6cd38c-52a5-49c8-9aa9-e18025c375c9. Observations: Second opinion: NO FINDINGS. Проверено: (1) постановка требует один exact-ID compat310, полный partition до выбора и 14 full rows 3.12 + одну 3.10 с meta=true ровно на одной full 3.12; (2) девять IDs явно candidate, реальные 3.10/3.12 reports/events и synthetic hooks/order/completion proof ещё обязательны, full14/full verify запрещены; (3) actual scripts/run_test_shard.py вызывает partition(cases, data) до run_selected, фильтрует original case objects и связывает green с completion_exact/result_successful/HEAD equality — новый subset не выдан за реализованный; (4) contradiction/deploy-safety: repo/live defaults разделены, missing prerequisites останавливают запуск, local closeout не активирует hosted workflow, publication требует отдельной Owner команды; runtime/Home/pins не меняются. Counterfactuals considered: matrix-only мог быть выдан за imported exact-once proof, но plan прямо разделяет structural --matrix и свежий canonical partition; Legacy SID cache мог подменить V2 admission либо разрешить иные guards, но plan буквально ограничивает exception name predicate, сохраняет rc1/no delta первого отказа и actual v3 task addresses. Fixes: none (NO FINDINGS; no plan/status changes required). Addendum (new angle): downstream-note для Architect/Planner — existing unittest result.wasSuccessful допускает skips; текущий plan уже отдельно требует отсутствие unexplained skips в compatibility evidence и запрещает менять global skip contract, поэтому qualification нужна по actual report, а не одному status=green. Context reconciliation: scoped ADR006/F25 не выдаётся за broad canonical green; public provenance block содержит actual Architect SID/parent из explicit helper, а старый wrapper SID не используется; отсутствующий executable draft остаётся Planner-owned, текущий MAD/formalization остаётся отдельным Architect шагом. Artifacts opened: полный PLAN_PATH, frozen architect_censor.md, scripts/run_test_shard.py (partition/run_selected/main), .github/workflows/checks.yml и supplied-ID pre-dispatch helper readback; planned code draft и sole review artifact ещё не существуют, visual UI N/A. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review and blocker lineage not materialized). Role-owned finding: none; initial постановка готова к обычной Architect формализации, downstream handoff этим CENSOR не выполнен. Reconciliation: no live blocker. Post-write gates: frozen-facade plan_lint.py, scoped link/basic-hygiene с explicit product root и literal plan root, actual status readback, затем exact supplied-ID censor_receipts_harvest.py; actual stdout/stderr и child/tee/pipeline rc сохраняются в .tmp/ci_p3_proof/architect-censor-initial-eb6cd38c-20261104/. Final censor verdict: OK для Architect draft только при фактически зелёных post-write gates и complete final exact readback; status не меняется, implementation/runtime/hosted acceptance не заявляется.

- [2026-11-04 04:11 +0300] (Architect formalization) Прочитаны полный frozen status-driven prompt, target-local N-A sections, current plan и actual reader/emitter/consumer sources. Единственный strict N-A MAD materialized по source-backed boundary: existing run_selected green/red completion/result/HEAD, Planveyor authorization/routing/mutation/terminal admission неизменны. Fresh oracle `582051d9-e577-4375-8b9f-987aa11df657` дал child rc0, `machine_authority_decision_state=not_applicable`, reason=ok, confirmation=not_applicable, carrier SHA-256 `d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204`, manager admitted, guard=false, Owner Q&A clean. `ref_state=missing` относится к будущему Planner draft; перед его first executable handoff нужен helper-derived tagged ref, semantic core Planner не пишет.
- [2026-11-04 04:11 +0300] (Architect formalization) Закреплены additive manifest subsets/--subset, full-before-subset/original instances, selected_subset vs selected_shards, existing planned event и explicit matrix full/subset branches; literal shared dependent inventory и proof lanes конкретны. Это формализация принятого одного bounded subset, не новый CI tier или реализация. Отдельный source-backed synthetic/environment/real compatibility proof остаётся будущим Coder результатом; `--matrix` не заменяет imported partition, skipped mandatory capability не закрывается одним green. Structural manifest readback подтвердил version1/s01…s14/profiles3,4; прежний диагностический read-only Python one-liner имел SyntaxError и не является proof, corrected standalone read дал actual child rc0. Никаких product/tests/code-draft/runtime/Home/old terminal changes, full verify/full14, external agents, commits или публикации в этом run нет.
- [2026-11-04 04:11 +0300] (Architect gates) Первый plan lint после формализации дал actual child rc1 из-за backticks вокруг literal Terminal outcome no; исправлен только carrier spelling на bare token. Scoped link/basic-hygiene с explicit product root и literal current plan root дали child rc0/tee0/pipeline0; broad canonical lint green не заявлен. Gate после этой последней правки и final status выполняется свежо; текущие streams и отдельные child/tee/pipeline rc сохраняются в .tmp/ci_p3_proof/architect-formalize-20261104-v3/. Начальный consumed CENSOR receipt не переписывается; новый primary не выполняет CENSOR и не ставит skip hint, поскольку уточнён semantic handoff contract.

- [2026-11-04 04:12 +0300] (Architect) Ready for Planner: повторный pre-handoff plan lint после исправления Terminal outcome дал actual child rc0/tee0/pipeline0, только advisory WARN о будущем Planner-owned draft. N-A core и его source-backed applicability, current Owner answers, normal full conveyor и literal primary/contextual proof family согласованы. Финальный handoff проверяется fresh oracle/lint и scoped link/basic-hygiene на записанных bytes; evidence prefixes в текущем proofdir сохраняют actual result, а отсутствующий draft/PLANNED review не являются executable или terminal green. Следующая роль Planner создаёт единственный linked draft, переносит helper-derived N-A ref и exact targets, материализует low-cost commands/proofs и проходит strict first executable preflight. После этого primary handoff роль останавливается; отдельный CENSOR dispatch принадлежит Manager.

- [2026-11-04 04:16 +0300] (Architect CENSOR) OK: Ready for Planner validated; current=true. Censor dispatch id: censor:architect:ff7a3309-147f-4d78-82cd-9be4760fca3e. Observations: Second opinion: NO FINDINGS. No material delta since previous CENSOR: N/A (why=первый Ready for Planner CENSOR после отдельной semantic формализации). Content facts: (1) optional subsets/--subset не заменяют canonical discovery: полный exact-once partition обязателен до фильтра original instances, report selected_subset отделён от selected_shards и planned event сохраняет identity; (2) matrix contract содержит 14 full 3.12 + одну subset 3.10, ровно один selection key на row и meta=true только на первой full 3.12; missing compat310 в matrix даёт отказ, хотя legacy full mode может читать manifest без optional subsets; (3) synthetic negative/hook/order/completion/HEAD cases, реальные обе compatibility axes, tomli и настоящий facade/Copier path перечислены отдельно, mandatory skipped capability не закрывается одним runner green; (4) contradiction/deploy-safety: existing post-discovery head_before и completion/result/HEAD основания green/red не меняются, missing prerequisites останавливают запуск, локальный closeout не активирует hosted workflow и не даёт publication authority. Actual source scripts/run_test_shard.py пока имеет --matrix/--check/--shard/--local-profile и existing result/HEAD green predicate; workflow ещё вызывает --shard, а schema имеет additionalProperties=false — handoff прямо относит additive reader/schema/matrix-consumer patch к будущему Coder, не выдаёт его за landed. Counterfactuals considered: optional subset мог тихо убрать 3.10 coverage, но matrix обязана отказать при missing compat310 и запрещает full-3.10 fallback; structural matrix или JSON Schema могли заменить actual membership/full partition, но plan разделяет эти proofs и требует canonical imports и consumer assertions; missing Planner ref мог стать ложным executable green, но strict first executable preflight и derived ref остаются обязательными перед Coder. Fixes: none (NO FINDINGS; no plan/status changes required). Addendum (new angle): downstream-note для Planner — проверять одновременно legacy full mode без subsets и отказ configured CI matrix без compat310; обе разные ветки уже concrete в contract, их нельзя схлопнуть в один nominal schema test. Context reconciliation: точное v3-name exception/Legacy SID diagnostic boundary и actual provenance SID/parent сохранены; F25/scoped ADR006 не объявляет broad canonical green, terminal/root review/private-copy/p0 и запрет push сохраняются; executable draft не создан этой ролью. Independent MAD gate: fresh oracle 54a500a7-09cc-4bdd-b928-b30f990ee121 child rc0, not_applicable/reason=ok, confirmation=not_applicable, carrier SHA-256 d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204, expected empty decision_id/route для N-A, guard=false, manager admitted, Owner clean; ref_state=missing относится к будущему Planner draft и не подменяет semantic core. Fresh pre-write plan lint child rc0 с единственным missing-draft WARN. Artifacts opened: полный PLAN_PATH, полный frozen architect_censor.md, scripts/run_test_shard.py (partition/run_selected/main/report/matrix), .github/workflows/checks.yml, scripts/test_shards.schema.json, pyproject.toml и requirements-dev.lock; sole review и code draft ещё PLANNED, visual N/A. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review/blocker lineage not materialized). Role-owned finding: none. Reconciliation: no live blocker. Post-write plan/scoped-doc gates, actual status и final exact supplied-ID self-check выполняются на последнем состоянии; stdout/stderr и child/tee/pipeline rc сохраняются в .tmp/ci_p3_proof/architect-censor-planner-ff7a3309-20261104/. Final censor verdict: OK для Ready for Planner только при фактически зелёных post-write gates и complete matching exact readback; implementation/strict executable/hosted/terminal green не заявляется.


- [2026-11-04 04:34 +0300] (Planner primary) Intake завершён без новых Owner вопросов. Public scaffold helper создал linked draft и единственный helper-derived N-A ref с carrier SHA-256 d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204; semantic core не копировался и не менялся. Public provenance context/stamp с explicit actual Planner SID/thread/parent дал rc0; exact generated block перенесён в plan/draft, старый wrapper SID не использован. Named current sources и existing locked 3.10/3.12 packages проверены read-only; doctor/runtime readback подтвердили supplied frozen runtime, но не объявлены consumer/runtime acceptance.
- [2026-11-04 04:34 +0300] (Planner primary) Exact bundle = девять implementation/doc files и отдельные lifecycle carriers. Новый scripts/test_run_test_shard.py содержит только role-authorized fail-closed path-tracking stub, не synthetic implementation. Материализованы proposed synthetic outcomes, original-instance/order/hooks proof, full-before-subset и legacy/matrix branches, whole-module s03 owner, receipt-schema emitter inventory, payload assertions, ordered both-axis report/events/source hash/rc/elapsed readback, prerequisite и scoped i18n commands. Current source finding: --i18n-strict frozen CLI глобален даже при --root; canonical status + exact changed-pair ok assertions проверяют только две accepted пары без helper rewrite или broad-green claim.
- [2026-11-04 04:34 +0300] (Planner gates) Первый current Planner finalize plan_lint дал actual child/tee/pipeline rc0. Strict first executable planveyor_plan_bundle --preflight дал child/tee/pipeline rc0, 12 paths/0 issues: все 9 targets, plan и draft OK, sole review PLANNED. Scoped links/basic-hygiene по literal plan+draft roots и git diff --check дали rc0; четыре zsh blocks и embedded Python parse проверены без выполнения product commands. Дополнительный scoped basic-hygiene проверяет actual untracked plan/draft bytes, один Git diff этого бы не доказал. Streams/status files лежат в .tmp/ci_p3_proof/planner-primary-20261104T012200Z/; final записанные bytes проходят fresh lint/preflight/oracle после последнего contract/provenance уточнения. Synthetic tests, full partition, обе real compat axes, private scan, root independent review, terminal closeout и final p0 в этом Planner run не выполнялись и green не объявлены. No CENSOR/skip hint, no stage/commit/push, runtime/Home/old terminal artifacts не менялись.

- [2026-11-04 04:35 +0300] (Planner) Ready for Coder: fresh final contract syntax (4 zsh blocks, 9 Python fragments), plan lint, strict first executable preflight, scoped links/basic-hygiene и diff hygiene дали actual child/tee/pipeline rc0. Fresh oracle 268b41e5-b1bd-4549-bb6a-8aeccee47172 подтвердил N-A/reason=ok, tagged ref=valid, unchanged carrier SHA-256 d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204, admitted manager-collab, guard=false, Owner Q&A clean. Executable contract и closure-path self-check закрыты; sole review пока PLANNED, product/compatibility/hosted/terminal acceptance не заявляется. После status write выполняются только fresh read-only lint/preflight/scoped-doc/oracle gates; самостоятельный CENSOR не запускается.

- [2026-11-04 04:44 +0300] (Planner CENSOR) OK: Ready for Coder validated; current=true. Censor dispatch id: censor:planner:d779e8e1-8b85-466a-96f6-4322644c34d5. Observations: Second opinion: найдены и исправлены Planner-owned proof gaps. No material delta since previous CENSOR: N/A (why=first Planner CENSOR for this Ready for Coder handoff). Content facts: plan требует полный canonical partition до subset selection, real WORK compat310 на обеих axes и matrix 14 full3.12 + 1 compat3.10/meta1; draft содержит девять exact targets, module owner s03 и original-instance/order/hooks fixture, теперь с valid fully-qualified test_alpha.AlphaTests.test_a/test_b и test_beta.BetaTests.test_c. Actual runner ещё не имеет --subset, manifest/schema ещё без subsets, workflow ещё вызывает --shard; fail-closed new test stub не выдан за implementation. Contradiction/deploy-safety: existing completion/result/post-discovery HEAD green predicate сохраняется, missing prerequisites останавливают запуск; local closeout не активирует hosted workflow и не разрешает публикацию, lock/requires-python/mypy3.10 unchanged. Counterfactuals considered: (1) successful login-shell python3 мог быть другим бинарником — теперь actual version + os.path.samefile обязательны и совпадающий basename/SHA проверяется в same-run readback; (2) valid-looking alpha.test_a shorthand не прошёл бы strict manifest reader — literal fixture IDs приведены к existing module.Class.test_method grammar; (3) strict inventory preflight мог быть принят за runtime proof — product AC unchecked, stub replacement и реальные reports/events/Copier execution обязательны отдельно. Fixes: в plan Commands добавлены expected-axis/same-file bare-python assertions, executable_basename/executable_sha256 emitter и matching identity readback; в draft те же preconditions и exact fixture names, append-only review stamps. Targets, semantic MAD core и status не менялись. Addendum (new angle): private path redaction теперь опирается на captured binary basename/SHA, а не поздний rehash другого executable; оба existing-axis read-only identity probes дали child rc0, но это не WORK runner/compatibility acceptance. Context reconciliation: WORK product scripts отделены от frozen lifecycle/MAD/provenance/lint helpers; actual Planner SID/parent уже helper-backed в plan/draft, old wrapper SID не использован; selected-pair i18n readback не назван blanket strict green. Artifacts opened: полный PLAN_PATH и same-stem draft, полный frozen planner_censor.md, actual runner partition/run_selected/main, manifest/schema/workflow, fail-closed synthetic stub, real ConsumerContractFacadeTests path и frozen i18n/doc-lint scope emitters; sole review file ещё отсутствует, visual N/A. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review/blocker lineage not materialized). Role-owned finding: три proof/actionability gaps закрыты в текущем handoff. Reconciliation: no live blocker. Gates: pre-receipt plan lint, strict preflight (12 paths/0 issues), scoped link/basic-hygiene и syntax/read-only identity checks фактически child/tee/pipeline rc0; после этой последней записи выполняются fresh plan/doc/bundle/oracle/status и exact supplied-ID self-check, streams/status под .tmp/ci_p3_proof/planner-censor-d779e8e1-20261104/. Final censor verdict: OK для Ready for Coder только при green post-write gates и complete exact final readback; product/runtime/hosted/terminal green не заявляется.

- [2026-11-04 04:55 +0300] (Coder intake, до implementation) Прочитаны полный current status prompt, его target-local N/A sections, plan/draft и actual runner/manifest/schema/workflow, docs, lock/Make и named capability bodies. NO QUESTIONS / NO SUGGESTIONS / NO OBJECTIONS записаны в соответствующих секциях; scope и nine-target inventory приняты без нового решения. AC-to-test checklist до правок: AC1 explicit assertion — test_subset_rejects_invalid_shape_ids_and_name/test_subset_requires_valid_whole_partition; AC2 explicit assertion — test_subset_preserves_instances_order_and_hooks/test_subset_cli_report_and_events_share_identity; AC3 explicit assertion — test_incomplete_started_or_completed_is_red/test_existing_head_boundary_drift_is_red/test_interruption_retains_non_green_partial_report; AC4 explicit assertion — test_matrix_and_workflow_selection_contract + matrix readback + unchanged mypy config; AC5 explicit assertion — both-axis real compat reports/events + exact same-run readback; AC6 explicit assertion — fresh WORK --check и unique s03 owner; AC7 explicit assertion — scoped docs/i18n + current lint/preflight, normal review/terminal gates остаются owning downstream; AC8 existing proof — неизменность protected inputs по source inventory, copy-only scan/final p0 принадлежат root и до их выполнения не отмечаются; AC9 explicit assertion — synthetic CLI/report/event/matrix consumer assertions. UI N/A — no UI change; Architect/Planner handoff rows existing proof — предшествующие literal receipts, не Coder product proof. Реальные результаты ещё отсутствуют; synthetic stub заменяется первым.

- [2026-11-04 04:59 +0300] (Coder, same-contract command-route blocker) Реализованы ровно девять targets: optional subsets/--subset, all-subset membership после whole partition, original-case filtering, additive report/planned identity, matrix14full3.12+1compat3.10/meta1, workflow branch, schema/manifest/s03 owner, десять synthetic methods и четыре EN/RU docs. Первый адресный synthetic run дал 10/10 за 2.057s, child/tee/pipeline rc0 в .tmp/ci_p3_proof/coder-primary-20261104T014959Z/synthetic-initial.*; после него добавлены две bounded negative assertions (all-configured membership и extra accounting), поэтому этот предварительный результат не qualified final-source proof. Protected runtime HEAD e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4 и WORK HEAD e3032d4bb5d5d949411f2dcac3004f4f7b1de979 проверены read-only. Public provenance context/stamp с actual Coder SID/thread и supplied parent дал rc0; default stale wrapper SID не использован. Отдельный diagnostic вызов stamp --help без обязательного plan argument дал rc2; корректная supported context --help и subsequent explicit stamp дали actual rc0, старый отказ не считается green.
- [2026-11-04 04:59 +0300] (Coder, blocker C-P3-1, to=Architect) Все четыре literal Commands zsh blocks извлечены без ослабления predicates и запущены на WORK. В .tmp/ci_p3_proof/coder-20261104T015724Z-74592 обе prerequisites-310/312 прошли child/tee/pipeline rc0: 3.10.22/3.12.14, все declared lock packages, Git/zsh/rg/make и physical TMPDIR вне Git. Затем stamp-readme получил actual child_rc=64, tee_rc=0, pipeline_rc=64: Unsupported runtime helper: i18n_pairs.py. Frozen scripts/planveyor.zsh::planveyor_runtime_py allowlist действительно не содержит i18n_pairs.py; этот же дефект затрагивает planned stamp-verify и i18n-status. Envelope остановился до sources-before, canonical check, matrix и real compatibility; эти результаты, tomli/typecheck и exact-pair i18n ещё отсутствуют. Command-route gap — same-contract reroute: nine targets, Scope/AC и все predicates прежние, новый contour не нужен. Требуется выбрать/зафиксировать repo-backed route существующего i18n helper в Commands/draft и вернуть owning Coder для fresh unique proofdir. Runtime allowlist, pins/Home, old terminal artifacts и source index не менялись; no commit/push. Candidate readiness=false до final WORK proofs; native/external review, copy-only scan, final p0 и terminal acceptance не заявлены.

- [2026-11-04 05:01 +0300] (Coder, blocker handoff gates) На записанных Ready for Architect response bytes frozen-facade plan lint и scoped links/basic-hygiene только plan+draft дали actual child/tee/pipeline rc0. Logs: .tmp/ci_p3_proof/coder-primary-20261104T014959Z/blocker-plan-lint.*, blocker-doc-links.*, blocker-doc-hygiene.*. Это hygiene текущего blocker handoff, не product/compatibility/review green. Непройденный stamp rc64 сохранён отдельно; Owner вопрос не нужен, repair принадлежит Architect/Planner.

- [2026-11-04 05:10 +0300] (Architect response, C-P3-1) Статус нормализован Ready for Architect response -> Architect response; fresh oracle f9ff5d16-fc6e-4b3a-a000-865b2e56cbb4 дал admitted manager-collab, guard=false, Owner clean, N-A reason=ok и valid tagged ref с прежним carrier SHA-256 d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204. Прочитаны current plan/draft, actual unsupported log/status и frozen allowlist: i18n_pairs.py отсутствует, реальный отказ child64/tee0/pipeline64 подтверждён и не переписывается. Source-backed direct WORK CLI help дал child/tee/pipeline rc0; stamp/status исполнения этой ролью не выполнялись.
- [2026-11-04 05:10 +0300] (Architect response, same-contract reroute) По конкретному root решению C-P3-1 исправлены только три command-route строки в active Commands: product WORK i18n_pairs.py вызывается выбранным PYBIN напрямую с existing --project-root/stamp/status grammar. Nine targets, Scope/Acceptance, whole proof envelope и exact two-pair predicates сохраняются; current code draft остаётся Planner-owned и этой ролью не редактируется. New proof prefix .tmp/ci_p3_proof/architect-response-cp3-1-20261104-v3/ хранит before snapshots/contract hashes, help/source readback и actual child/tee/pipeline rc; проверка после edit сравнивает все четыре Commands blocks с ровно этими тремя replacements. Preliminary 10 tests/2.057s предшествуют двум assertions; sources-before/check/matrix/real compat/tomli/typecheck/i18n qualification по остановленному envelope отсутствуют. Candidate readiness=false; no source freeze/copy scan/Review/final p0/commit/push. Fresh full envelope после owning Planner reconciliation обязателен; runtime/Home/old П1/П2 и source index не менялись.

- [2026-11-04 05:13 +0300] (Architect response -> Planner, same-contract reroute, C-P3-1) Exact before/after проверка дала child/tee/pipeline rc0: Commands отличаются ровно тремя transport replacements, все остальные Commands bytes/predicates и protected Scope/Acceptance совпали с before snapshots; same-stem draft, nine-target inventory, MAD object и scripts/i18n_pairs.py bytes неизменны. Четыре zsh blocks parse под zsh -n child0 без исполнения envelope. Direct WORK i18n status read-only дал child0, но обе selected пары фактически stale; это подтверждение supported status route, не i18n green. Stamp calls, final synthetic/source/compatibility/tomli/typecheck proofs этой ролью не исполнялись. Plan lint и scoped link/basic-hygiene по literal plan+draft roots дали child/tee/pipeline rc0; final readbacks после handoff сохраняются тем же proof prefix. Broad lint green не заявляется.
- [2026-11-04 05:13 +0300] (Architect, Ready for Planner, C-P3-1) Bounded return to owning Planner: синхронизировать существующий draft с accepted direct WORK i18n route из Decisions/Commands и повторить normal gates до возврата Coder; не создавать новый scope cycle, targets или semantic MAD. Это точное root поручение reconciliation после STOP, а не shortcut Architect -> Ready for Coder. После Planner Coder использует fresh unique proofdir и весь accepted envelope, включая actual stamp/status + неизменный i18n-selected predicate; старые rc64 и preliminary 10/10 остаются history. Candidate readiness=false до fresh final-source outputs; root Sol+GLM exact-candidate checkpoint перед semantic commit и normal native Review/Architect сохранены. Required Owner action нет. Censor hint не ставится: command-route carrier изменён; самостоятельного CENSOR этой ролью нет.

- [2026-11-04 05:20 +0300] (Architect CENSOR) OK: Ready for Planner validated; current=true. Censor dispatch id: censor:architect:9e555b25-d929-4248-9e72-4c1c64e258ab. Observations: Second opinion: NO FINDINGS для bounded C-P3-1 handoff. No material delta since previous CENSOR: N/A (why=три active i18n command routes материально исправлены после STOP; старый Ready for Planner receipt не является новым proof). Content facts: (1) оба stamp и status теперь вызывают existing WORK scripts/i18n_pairs.py через выбранный PYBIN с прежними --project-root/stamp/status arguments; frozen runtime helper allowlist действительно не содержит i18n_pairs.py, поэтому unsupported route не повторяется; (2) direct snapshot comparison подтверждает ровно три replacements и сохранность всех остальных Commands bytes, Scope/Acceptance, девяти targets, MAD, draft и helper bytes; exact two-pair ok predicate остаётся обязательным; (3) linked draft содержит девять targets, оба real compat runs и Coder stamp о preliminary 10/10 до двух assertions; его sync явно Planner-owned и пока pending, final-source proof отсутствует; (4) contradiction/deploy-safety: runtime/Home/allowlist/pins и v3-name exception не меняются, stale status с rc0 не считается i18n green, hosted activation/push не разрешены; root Sol+GLM exact-candidate checkpoint перед semantic commit и обычные native Review/Architect сохраняются. Counterfactuals considered: direct WORK CLI мог быть новым обходом guard, но actual argparse/stamp source и registry-backed product route существовали ранее, а lifecycle/MAD/provenance/lint остаются frozen-facade; status rc0 мог скрыть обе stale пары или preliminary tests могли стать final proof, но unchanged i18n-selected требует ровно две ok rows и план сохраняет C-P3-1 rc64/неполный envelope/candidate readiness=false. Fixes: none (NO FINDINGS; no plan/status changes required). Addendum (new angle): downstream-note для Planner/Coder — contract уже конкретен: sync трёх routes в owning draft, затем normal gates и fresh unique proofdir; stamps выполняются до source inventory, после чего весь agreed envelope и same-run reports/events должны быть свежими. Context reconciliation: root decision классифицирован same-contract reroute и не разрешает shortcut Architect -> Ready for Coder; old rc64 и старые receipts сохранены, отсутствие нового Owner вопроса и узкая Legacy SID diagnostic boundary отражены в плане. Локальный comparison probe rc1 был ошибкой extraction для snapshot hash, corrected direct section/byte equality дала child0; продуктовые proofs этим не выполнялись. Independent MAD gate: oracle 420ce46b-38ef-48fc-852a-57a1623f1d6c дал child0, not_applicable/reason=ok/confirmation=not_applicable, valid tagged ref, carrier SHA-256 d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204, expected empty decision_id/route, admitted manager-collab, guard=false, Owner clean; pre-write plan lint child0. Artifacts opened: полный current PLAN_PATH и same-stem draft, полный frozen architect_censor.md, actual scripts/i18n_pairs.py и frozen runtime_py allowlist, before snapshots/commands-exact.diff, failed stamp log/status и direct status readback с обеими stale selected pairs; sole review ещё PLANNED, visual N/A. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review/blocker lineage не materialized; C-P3-1 является technical command-route objection). Role-owned finding: none; выбор supported route уже закрыт, owning Planner sync и Coder qualification остаются обязательными. Reconciliation: no live blocker; live reviewer blocker отсутствует, pending technical closure C-P3-1 не объявлена product green. Post-write gates: fresh plan lint, scoped links/basic-hygiene по literal plan+draft roots, actual status и один final exact supplied-ID self-check; stdout/stderr и child/tee/pipeline rc сохраняются в .tmp/ci_p3_proof/architect-censor-cp3-1-9e555b25-20261104/. Final censor verdict: OK для Ready for Planner только при green post-write gates и complete matching final exact readback; implementation/i18n/compatibility/hosted/terminal acceptance не заявляется.

- [2026-11-04 05:29 +0300] (Planner primary, C-P3-1, same-contract reroute) Owning reconciliation завершён: existing draft синхронизирован с ровно тремя accepted direct WORK i18n calls; оба stamps остаются до sources-before, status — перед неизменным exact two-pair predicate. Current stub wording отмечено historical, Coder implementation не изменялась. Before/after comparison дал child/tee/pipeline rc0: весь Commands section, Scope/Acceptance, draft metadata с девятью targets/tagged N-A ref и SHA всех девяти product files + scripts/i18n_pairs.py неизменны. Four zsh blocks и embedded Python parsed без исполнения envelope. Fresh plan lint, strict preflight (12 paths/0 issues, sole review PLANNED), scoped links/basic-hygiene и diff hygiene дали child/tee/pipeline rc0; oracle ce917c4f-f357-4192-b622-bb5ec015a0fe подтвердил N-A/ok/ref=valid с прежним SHA d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204, admitted manager-collab, guard=false, Owner clean. Supported product --help/stamp --help и explicit actual Planner provenance context дали rc0; default wrapper SID не использован, existing actor carrier сохранён. Proof prefix .tmp/ci_p3_proof/planner-reconcile-cp3-1-20261104T022600Z/. Closure-path self-check: ничего не остаётся угадывать в route/order; Coder обязан fresh unique proofdir и полный agreed envelope на final WORK bytes. Old rc64, preliminary 10/10 до двух assertions и старые prerequisites остаются history; i18n stale/status rc0 не green, final-source qualification=false, ни один product/review/terminal outcome этим repair не закрыт. Root Sol+GLM exact-candidate checkpoint до semantic commit и normal native Review/Architect обязательны. No new Owner action, no runtime/Home/allowlist/pin/old terminal edits, no product run/stamp/status/commit/push; Censor hint не ставится, primary не вызывает CENSOR.

- [2026-11-04 05:35 +0300] (Planner CENSOR) OK: Ready for Coder validated; current=true. Censor dispatch id: censor:planner:e5cd30ea-8bde-45bc-8104-21528c18cb25. Observations: Second opinion: NO FINDINGS для bounded C-P3-1 (same-contract reroute). No material delta since previous CENSOR: N/A (why=C-P3-1 materially corrected three active command routes and owning draft steps; old d779 receipt is historical, not this dispatch proof). Content facts: (1) plan Decisions/Commands задают ровно три direct WORK i18n calls с выбранным PYBIN; draft C-P3-1 повторяет те же literal calls и размещает два stamps после prerequisites до sources-before, status — перед unchanged two-pair ok assertion; (2) свежая source-backed comparison подтвердила byte-for-byte сохранность Scope/Acceptance/Commands и all predicates, девять targets/tagged N-A ref и неизменные SHA девяти product files/helper; (3) draft требует новый unique proofdir и весь final WORK envelope, сохраняет rc64 и preliminary 10/10 до двух assertions как history, final-source qualification=false; (4) contradiction/deploy-safety: runtime/Home/allowlist/pins не меняются, supported product route не превращается в lifecycle fallback, stale status rc0 не green, hosted activation/push не разрешены; root Sol+GLM exact-candidate checkpoint до semantic commit и normal native Review/Architect обязательны. Counterfactuals considered: direct WORK CLI мог оказаться новым guard bypass, но actual existing argparse/stamp_copy source и help подтверждают registry-backed product route, а frozen runtime allowlist остаётся неизменным; status child0 или старые prerequisites могли подменить qualification, но exact two-pair predicate и fresh full envelope явно обязательны, reports/source freeze/compat/tomli/typecheck ещё pending; old receipt мог подменить новый supplied-ID proof, но он не редактируется и этот pass пишет отдельную current receipt. Fixes: none (NO FINDINGS; no plan/status changes required). Addendum (new angle): downstream-note для Coder/Reviewer — after-stamp source inventory должен относиться к тому же новому run, что reports/events и source-after; порядок уже literal в plan/draft и не разрешает объединять старые prerequisites, предварительные tests или разные proofdirs. Context reconciliation: прямые product i18n calls согласованы с WORK runner/tests и отделены от frozen lifecycle/MAD/provenance/lint; helper-backed actual Planner SID/parent и узкое v3-name exception сохранены; historical rc64 и два последних negative assertions не потеряны при reconciliation. Artifacts opened: полный current PLAN_PATH и same-stem draft, полный frozen planner_censor.md, actual scripts/i18n_pairs.py source/help, frozen runtime_py allowlist, original stamp-readme log/status, repo-local C-P3-1 before comparison inputs; sole review ещё отсутствует, UI N/A. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review/blocker lineage not materialized; C-P3-1 is technical command-route history). Role-owned finding: none; executable reconciliation complete, product qualification pending Coder. Reconciliation: no live blocker. Gates: fresh pre-write plan lint/strict preflight child/tee/pipeline rc0 (12 paths/0 issues), syntax parsed without execution; fresh oracle confirmed Ready for Coder, admitted manager-collab, guard=false, Owner clean и N-A/ok/ref=valid с прежним SHA d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204. Post-write plan/doc/bundle/oracle/status и exact supplied-ID self-check выполняются на последнем состоянии; streams/status под .tmp/ci_p3_proof/planner-censor-cp3-1-e5cd30ea-20261104/. Final censor verdict: OK для Ready for Coder только при green post-write gates и complete exact final readback; product/i18n/compatibility/hosted/terminal acceptance не заявляется.

- [2026-11-04 05:41 +0300] (Coder intake после C-P3-1) Полностью перечитаны current prompt с target-local N/A sections, текущие plan/draft и repair evidence. NO QUESTIONS / NO SUGGESTIONS / NO OBJECTIONS: accepted route теперь вызывает existing WORK i18n helper; прежний rc64 не повторяется и не переинтерпретируется. AC-to-test checklist до новых source/stamp edits подтверждён: AC1–3 explicit assertion — десять existing new synthetic methods, включая последние all-configured membership/extra accounting assertions; AC4 explicit assertion — matrix/readback + workflow execution fixture и unchanged mypy config; AC5 explicit assertion — fresh обе real compat axes/report-events/identity; AC6 explicit assertion — fresh canonical --check + s03 owner; AC7 explicit assertion — accepted scoped docs/i18n/lint/preflight, review/terminal остаются downstream; AC8 existing proof — protected inputs inventory, root copy-only scan/p0 pending; AC9 explicit assertion — actual CLI/emitter/consumer fixture/readback. UI N/A; Architect/Planner handoff rows existing proof — literal current receipts. Scope/targets/MAD не меняются. Начинается полный agreed envelope в новом unique proofdir; до результатов final-source qualification=false.

- [2026-11-04 05:46 +0300] (Coder, final WORK qualification) Весь согласованный Commands envelope исполнен заново в .tmp/ci_p3_proof/coder-20261104T024119Z-25237/; orchestration input .tmp/ci_p3_proof/coder-resume-20261104T024113Z/accepted-proof.zsh содержит четыре current blocks, дополненные только выводом proof-prefix. Все 25 required command status files имеют actual child_rc=0, tee_rc=0, pipeline_rc=0; supplemental qualification-identity.log повторно проверяет это, source equality и protected HEAD blobs. Both-axis prerequisites и два supported direct WORK stamps выполнены до sources-before. Последние negative assertions входят в текущие bytes: synthetic-312 дал 10/10 за 2.152s (command elapsed 2.2252s). Свежий WORK --check импортировал 3527 canonical tests без исполнения их тел, partition exact-once; новый module имеет sole owner s03. Matrix/readback и actual YAML-branch fixture доказали 15 unique rows, 14 full3.12/1 compat3.10, XOR selection и единственный meta=true на s01/3.12; legacy full/local без optional subsets и missing-compat matrix refusal проверены synthetic suite. JSON Schema не выдан за discovery proof.
- [2026-11-04 05:46 +0300] (Coder, реальные обе axes) compat-310.json и compat-312.json относятся к одному final-source run: Python 3.10.22 и 3.12.14 исполнили по 9/9 выбранных tests, status=green, completion_exact/result_successful=true, failures/errors/skipped=[]; ordered planned=started=completed и одинаковы между axes, selected_subset=compat310/selected_shards=[]. HEAD pair в обоих reports равен e3032d4bb5d5d949411f2dcac3004f4f7b1de979. Suite wall_seconds: 82.3776228750 / 84.7432540410; command elapsed: 83.7659101486 / 86.4051659107 соответственно. Same-run proof-readback сверил manifest/source hashes, report/events identity и ordered events, actual rc, Python version и captured binary basename/SHA с natural login-shell python3; physical samefile predicates реально выполнены. Binary identities без private path: python3.10 SHA-256 cc0939d53d6d23b36e6d02b39a43808569758bb575af507b9efa6bb4f84251ee; python3.12 SHA-256 9e78d18ffca959d9f44a7c363360a4b24f108e3eab576bd525c42031612a1505. Отдельный tomli1.1.0 import/parse под 3.10 rc0; make typecheck rc0, no issues in 12 source files, existing mypy target3.10/lock/requires-python/loader range не менялись.
- [2026-11-04 05:46 +0300] (Coder, executed capability mapping) Все девять IDs из Tests реально executed на обеих axes, без replacement/mock/skip substitution: ConsumerContractFacadeTests.test_public_facade_init_doctor_and_compatible_upgrade — настоящий facade/Copier init, read-only doctor и compatible upgrade с target-local preservation; два ContractAuthorityLoaderStreamTests — non-executed stream header/current-shell body status и explanatory missing-Python refusal; shell drift test — runtime closure/runner policy deny-before-effect; два AuthoritySnapshotTests — exact live marker-v3 fields и duplicate/non-JSON rejection; три PybinResolveTests — ignored project cache/PATH, strict explicit invalid PYBIN и conda precedence. Synthetic fixture traces не подменяют эти real capability outcomes и не являются concurrency proof.
- [2026-11-04 05:46 +0300] (Coder, exact source identity/retention) sources-before.log == sources-after.log byte-for-byte, 19 file hashes = 9 implementation/doc targets + 10 declared read-only inputs. Inventory file SHA-256 0f16c2bb6ef8449c9974c92c479693e819b0873df35bb8279ab3e7a67514024c; это diagnostic source-candidate identity для root freeze, не current-review verdict или commit identity. Manifest SHA-256 1046c7eb13b6f595b7ef784f85b3b35ef0b5f57cd761d53f80e381859ff62719. Report SHA-256: compat-310.json 003019765c495fcc9c659d4092ddfd971c4d2e16f20f7e6fa76a1b7171049af0; compat-312.json 2afdff0ab87c3274caeb1611601cc083fb876173c0f865713960f8eaade80940. Оба distinct events paths имеют одинаковый byte hash 058bbecf25f4fdb7a1a62431325c967d60278474e8c44c3ebf54a8b096e33457: schema не содержит времени/Python, а events IDs/manifest/HEAD одинаковы; это не подмена пары. Existing .tmp artifacts остаются transient local sanity only. Reviewer обязан materialize bounded redacted durable facts/assets под sole review path, сохранив receipt-reuse-only continuity; raw local executable paths не переносить.
- [2026-11-04 05:46 +0300] (Coder, hygiene и completion self-check) Scoped links/basic-hygiene по четырём docs + plan/draft дали rc0; direct WORK i18n status и unchanged exact two-pair ok assertion rc0, source/self stamps текущие. Broad strict doc-lint green не заявляется. Plan lint и strict inventory preflight rc0: 12 paths/0 issues, 9 targets+plan+draft OK, sole review PLANNED. Diff hygiene rc0; staged diff пуст, source index не использовался для staging; final runtime state clean с HEAD e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4. Protected 10 inputs совпадают с HEAD blob hashes, old terminal artifacts не входят в diff. Reviewer-closeability self-check: literal plan/draft/targets дают готовые current reports/events, exact source identity и все primary/contextual outcomes; same blocker C-P3-1 больше не survivable, unsupported call не повторялся. Documentation impact выполнен ровно в четырёх targets, новые mechanics links/исторические hosted facts сохранены; новых helpers/dependencies/targets нет. AC1–6/9 закрыты этим evidence. В AC7 Coder-owned scoped-doc/lint/preflight часть green, review/normal terminal остаются downstream; AC8 root copy-only scan/final p0 ещё pending, поэтому обе composite rows не отмечаются. Candidate готов к native/current-bundle review и root exact-candidate freeze/reviews; accepted review, semantic commit/terminal, hosted/full14/full verify и публикация не заявляются. Root Sol+GLM checkpoint до semantic commit обязателен. No stage/commit/push, runtime/Home/config/dictionary edits; обычный primary не вызывает CENSOR и не ставит skip hint.

- [2026-11-04 05:48 +0300] (Coder handoff) Completion plan lint, scoped link/basic-hygiene и exact bundle preflight после recording evidence дали actual child/tee/pipeline rc0 (completion-* в current proofdir); bundle 12 paths/0 issues, sole review PLANNED. Implementation/source inventory прежние, reviewer-closeability self-check закрыт. Поставлен Ready for Review; normal Manager-dispatched CENSOR и Reviewer — следующий owning gate. Root exact-candidate freeze/Sol+GLM review до semantic commit, copy-only scan/final p0 и normal Architect closure остаются pending. Свежие post-status plan/doc/bundle readbacks выполняются на этих последних bytes; при отказе handoff не считается ready. Новых Owner вопросов или unresolved Coder-owned blockers нет.

- [2026-11-04 05:59 +0300] (Coder CENSOR) OK: Ready for Review validated; current=true. Censor dispatch id: censor:coder:6c6d663a-39eb-47c4-9035-09332e57a1f1. Observations: Second opinion: найден и исправлен один stale current note в draft; product handoff проверен отдельным readback, не пересказом primary. No material delta since previous CENSOR: N/A (why=первый Coder CENSOR для этого handoff). Content facts: (1) actual runner вызывает partition на строке351, validate_subsets352 и run_selected358; original-case filtering сохранён, AST partition/TrackedResult/completed_exactly/green/exit совпадает с HEAD baseline, synthetic log содержит все десять current methods, включая unselected-subset membership и extra accounting; (2) заново проверены current19 source hashes, byte-identical before/after inventory с SHA-256 0f16c2bb6ef8449c9974c92c479693e819b0873df35bb8279ab3e7a67514024c, exact report/events hashes и полные ordered traces обеих axes9/9; completion/result/HEAD predicates true, failures/errors/skipped пусты, binary identity совпадает с bare probe, все40 primary/supplemental status files child/tee/pipeline0; (3) manifest меняет только compat310 и sole s03 module, schema только additive subsets shape, workflow только accepted selection branch; matrix15/meta1, legacy/missing-compat branches, unchanged Make/lock/mypy3.10/range/consumer helpers подтверждены; (4) contradiction/deploy-safety: missing prerequisites останавливают запуск, скрытой установки/fallback нет, rejected frozen i18n route не повторяется, local qualification не активирует hosted workflow и не заменяет required review/root checkpoints; AC7/8 честно остаются downstream pending. Counterfactuals considered: валидный subset мог скрыть corrupt whole partition либо unselected unknown IDs, но canonical partition сохраняется до case filtering и negative fixtures закрывают обе ветки; unittest success мог скрыть skips/incomplete/HEAD drift, но независимый report/events readback проверил все predicates, а Counter/green/exit не ослаблены. Fixes: в draft Notes устаревшее current заявление final-source proof ещё отсутствует заменено ссылкой на current qualified PLAN_PATH Evidence и сохранены pending review/root/terminal gates; route class=same-contract reroute (evidence wording only), девять product targets и qualified source bytes не менялись. Addendum (new angle): Reviewer-only note — одинаковые event hashes не объединяют две axes: retain каждый report вместе с его Python identity/status и общим inventory, как уже требует current plan; sole review/assets пока PLANNED, durable redacted retention остаётся Reviewer-owned. Context reconciliation: C-P3-1 rc64 и preliminary10/10 до двух assertions сохранены как history, их не использовали вместо fresh supported-route run; raw executable paths остаются transient, root Sol+GLM exact-candidate checkpoint до semantic commit/copy-only scan/final p0 не объявлены выполненными. Artifacts opened: полный current plan/draft и coder_censor prompt, actual runner/test module, manifest/schema/workflow и unchanged consumer bytes, оба current report/events/identity/bare/status families, synthetic/coverage/matrix/i18n/typecheck/tomli/scoped-doc outputs; отсутствие sole review path проверено. Review verdict seen: no live review artifact. Blocker IDs considered: N/A (why=live review/blocker lineage not materialized; C-P3-1 is closed technical command-route history). Role-owned finding: один stale draft note исправлен; product/reviewability blockers не обнаружены. Reconciliation: no live blocker. Gates: pre-write plan lint child/tee/pipeline0; independent current-proof и fan-out readbacks child/tee/pipeline0 в .tmp/ci_p3_proof/coder-censor-6c6d663a-20261104T025231Z/. Первый diagnostic order probe дал child1 из-за source.index, нашедшего function declaration; corrected AST-call probe дал child0 с351<352<358, исходный отказ сохранён и не выдан за product failure/green. Post-write plan/scoped-doc/bundle/status/source checks и final exact supplied-ID self-check исполняются после этой единственной receipt на последних bytes. Final censor verdict: OK для Ready for Review только при green post-write gates и matching complete exact self-check; native/external review acceptance, semantic commit/terminal и hosted/full-suite green не заявляются.

- [2026-11-04 06:13 +0300] (Reviewer, reviewer_code_risk) Независимый review текущих девяти targets: risk findings не выявлены. Новый synthetic run — 10/10, 2.356s, child/tee/pipeline rc0. Retained compatibility proof принят только после независимого receipt-reuse-only readback: current 19 hashes, обе report/events пары, ordered9/9, binary basename/SHA и все25 command statuses совпали. Полный producer stdout сохранён внутри immutable support; шесть отдельных durable evidence assets перечислены там explicit ref/SHA, исходные reports/events/source inventory перенесены byte-for-byte, локальные executable paths редактированы. `profile=unknown` оставлен по отдельному Manager readback; SID/runner/model/effort подтверждены. Это только risk lane, не aggregate verdict или финальный review. Статус и sole PLANNED review не менялись; root checkpoints и contracts/Architect/terminal gates остаются отдельными.

```json
{
  "run_id": "reviewer_code_risk_20261104T031325Z",
  "lane_id": "reviewer_code_risk",
  "runner_id": "codex",
  "session_key": "reviewer_code_risk",
  "sid": "01a1a403-3d4b-7252-b2d0-14d0ba318323",
  "profile": "unknown",
  "model": "gpt-6.1-sol",
  "reasoning_effort": "ultra",
  "prompt_file": "docs/tools/prompts/reviewer_status_driven.md",
  "target_ref": "BUNDLE=current bundle_sha256=526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d",
  "target_snapshot": {"bundle_sha256":"526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d","target":"BUNDLE=current"},
  "coverage_domains": ["correctness", "tests quality", "security/privacy", "subprocess/timeouts", "races/locks/atomicity", "data/migrations", "performance", "observability", "integrations", "supply chain", "failure semantics"],
  "findings": [],
  "lane_status": "no_findings",
  "no_findings_reason": "Независимый review девяти текущих targets и retained proof не выявил конкретных risk defects: полный partition предшествует subset, original instances/order/hooks сохраняются, negative accounting/interruption/HEAD cases краснеют, две actual compatibility axes и matrix consumer связаны с текущими source bytes.",
  "limits": [
    "Actual configured REVIEWER_PROFILE не передан и не подтверждён Manager: profile=unknown; SID/runner/model/effort подтверждены отдельно.",
    "Compatibility reports/events переиспользованы только receipt-reuse-only; исходные 19 source hashes и binary basename/SHA независимо сверены. Новые compatibility runs не создавались.",
    "Полные14 shards, verify-full и hosted CI не запускались; broader pre-discovery HEAD drift, true concurrency и изменение global skip semantics вне accepted scope.",
    "Root exact-candidate Sol+GLM checkpoint, copy-only private scan, final p0 и native contracts/Architect/terminal gates остаются отдельными обязательствами."
  ],
  "written_at": "2026-11-04T03:13:25Z",
  "current": true,
  "source_refs": [".github/workflows/checks.yml", "README.md", "README.ru.md", "docs/tools/verify_suite.md", "docs/tools/verify_suite.ru.md", "scripts/run_test_shard.py", "scripts/test_run_test_shard.py", "scripts/test_shards.json", "scripts/test_shards.schema.json"],
  "delta": "Optional strict subsets/--subset, all-subset membership после full partition, canonical-case filtering, additive report/planned identity и matrix14full3.12+compat3.10; lock и existing green predicates неизменны.",
  "outcome": "Risk lane без findings; готов только к canonical selector и независимой contracts lane, не к aggregate verdict.",
  "full_payload_ref": "docs/code_reviews/assets/261104_0314_ci_python_compat_subset/reviewer_code_risk_20261104T031325Z.json",
  "full_payload_sha256": "022e894a368c026da8f4c62f1850d2f3759a75707db4d767b728c9909159996f"
}
```

- [2026-11-04 06:15 +0300] (Reviewer, risk lane gates) После materialization compact frozen canonical selector дал `state=selected`, run_id `reviewer_code_risk_20261104T031325Z`, exact current bundle SHA и actual child/tee/pipeline rc0; это self-check, не независимый Manager readback. Frozen plan lint, scoped links/basic-hygiene по четырём docs + plan/draft и exact scope-check дали child/tee/pipeline rc0; selected и historical support validated, scope_ok=true. Sole review остаётся PLANNED, current_review_proof=planned; strict final review/bundle check принадлежит contracts finalizer после materialization. Git diff --check и отдельная проверка actual 11 source/lifecycle files на trailing whitespace/merge markers дали rc0. Streams/status сохранены в .tmp/ci_p3_proof/reviewer-risk-20261104T030517Z-51970/. Повторный final readback проверяет последние записанные bytes; native aggregate/Architect/root acceptance этими gates не заявляется.

- [2026-11-04 06:30 +0300] (Reviewer, reviewer_code_contracts) Полностью прочитаны current status prompt/локальные N-A sections, phase playbook, plan и same-stem draft; exact scope принят после canonical scope-check. Независимый frozen selector actual child/tee/pipeline0 выбрал support-preflighted current run reviewer_code_risk_20261104T031325Z, тот же bundle SHA 526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d. Выбранный compact и immutable support прочитаны напрямую; Manager memory не использовалась. Contracts findings отсутствуют; sole review materialized с обеими lanes, no-findings provenance/synthesis и семью individual refs/SHA. Actual codex/gpt-6.1-sol/ultra/SID подтверждены; profile unknown с явным limit. Public provenance context --help и explicit actual SID/thread/parent дали child/tee/pipeline0; audit carrier сохранён, stale wrapper SID не использован.
- [2026-11-04 06:30 +0300] (Reviewer, contracts proof) Fresh synthetic 10/10 за2.212s, canonical --check3527 без test bodies, matrix15/meta1, make typecheck12 files и selected-pair i18n predicate дали actual child/tee/pipeline0. Independent receipt-reuse-only readback сверил current19 source hashes,10 protected HEAD blobs, byte-identical source-before/after inventory, все25 command statuses, six durable assets с original ref/hash, оба reports/events/identity/bare/prerequisite families и текущие binary basename/SHA. Обе retained axes9/9 без failures/errors/skips, completion/result/HEAD true; nine capability assertion bodies открыты, настоящий facade/Copier path не подменён. Frozen runtime clean/pin unchanged; actual3.12 и physical TMPDIR вне Git проверены. Compatibility заново не запускалась, silent reseed и old/preliminary proof не применялись.
- [2026-11-04 06:30 +0300] (Reviewer, artifact gates) Fresh canonical producer дал тот же exact current SHA/child0. Первый review lint честно child1/tee0/pipeline1 из-за отсутствующего literal Visual env при N-A; Reviewer исправил только собственный artifact, повторный lint child0. Первый strict bundle readback имел13 members: короткие Markdown asset links не включили шесть support assets; этот inventory не принят за completed bundle. В sole review добавлены literal repo refs без изменения immutable payload/compact; fresh strict --check дал child/tee/pipeline0,19 members/0 issues, все7 assets explicit. Review lint с origin, plan lint и scoped links/basic-hygiene с actual review root дали rc0; separate hygiene проверил actual19 textual members, включая untracked test/plan/draft/review/JSON/JSONL: trailing whitespace0, merge markers0, missing final newline0. Streams/status: .tmp/ci_p3_proof/reviewer-contracts-20261104-v3/. После последней записи повторяются final read-only gates; no stage/commit/push, external models, dictionary/runtime/Home/old terminal edits.
- [2026-11-04 06:30 +0300] (Reviewer, handoff) Aggregate native review = ✅ OK, новых S1/S2/S3 и open Reviewer Q&A нет. Ready for Arch review означает только owning Architect handoff; root exact-candidate/freeze Sol+GLM reviews ПЕРЕД semantic commit остаются обязательными. Copy-only private scan, Architect/Manager normal terminal/capture/followups/PI/final-docs и fresh final p0 ещё downstream; AC7/8 остаются unchecked composite obligations. Full14/verify-full/hosted/Linux acceptance/publication не заявлены.

- [2026-11-04 06:43 +0300] (Architect arch review, checkpoint readiness) Семантическая проверка exact current bundle 526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d завершена без findings: actual nine-target diff/new synthetic module и весь plan/draft/sole review прочитаны; canonical snapshot, strict19-member preflight и independent risk selector дали child/tee/pipeline0. Независимый receipt-reuse-only readback сверил current19 source hashes/protected10 HEAD blobs, все25 required statuses, обе real report/events пары9/9, ordered IDs, manifest/binary identity и unchanged two-pair ok; qualified inventory SHA 0f16c2bb6ef8449c9974c92c479693e819b0873df35bb8279ab3e7a67514024c. Existing AST completion/result/HEAD predicate и full-before-subset порядок сохранены, N-A MAD/ref unchanged. Sole review → Архитектурное ревью содержит concrete readiness/checkpoint table и условный terminal verdict. Root Sol+GLM exact-candidate/freeze refs/outcomes ещё не представлены: closeout_pending, status Architect arch review; Done/stage/commit/amend не выполняются, COMMIT_POLICY=native_existing не меняется. Copy-only scan/final p0/Manager terminal obligations не объявлены выполненными, AC7/8 остаются unchecked. Это existing accepted checkpoint, не новый Owner вопрос или semantic rework. Current plan/review bytes после записи проходят fresh lint/review/bundle/scoped-doc/oracle gates; streams и actual child/tee/pipeline rc в .tmp/ci_p3_proof/architect-arch-review-checkpoint-20261104-v3/. Product9/draft/seven assets/runtime/Home/old terminal bytes не менялись; no CENSOR/external/nested agents/push.

- [2026-11-04 11:08 +0300] (Architect, root checkpoint accepted) Прямой sanitized root decision P3_ROOT_PRECOMMIT_ACCEPTANCE_002 принят в Decisions и sole Arch review: independent Sol/GLM code+proof и обе reviewed lifecycle deltas без actionable findings; это не native lifecycle receipt и не hosted/release acceptance. До effects сверены baseline HEAD/index, canonical BUNDLE526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d, current19 SHA/size и modes, включая literal expected Git100644/Unix0644 остальных10; все совпали. Pre-write plan/review lint и strict19-member bundle check дали child/tee/pipeline0. Current real compatibility evidence остаётся receipt-reuse-only; source9/draft/support assets не меняются. Root copy-only scan current19 принят по reported actual rc0/blockers0/warnings0; dictionary эта роль не открывала. Full native materialization далее проходит simulated Done lint до первого stage, pre-Done exact stage/preflight, provisional Done с немедленным ordinary lint и final exact stage/preflight/safe_command. Фактический commit outcome определяется helper/postcommit readback; terminal plan после успешного commit не дописывается. Manager terminal capture/followups/PI/final-docs, root fresh final p0 и postcommit privacy delta readback ещё pending; AC7/8 не выдаются за завершённый полный terminal-tail proof. Streams/child/tee/pipeline rc в .tmp/ci_p3_proof/architect-semantic-closeout-acceptance002-20261104-v3/. No external/nested agents/push/runtime/Home/old terminal/guard edits.

- [2026-11-04 11:14 +0300] (Architect, native semantic materialization) Simulated Done lint до первого stage дал actual child/tee/pipeline0; current plan/review lint, strict19-member bundle и scoped links/basic-hygiene также0. Первый exact stage сохранил реальный child2/tee0/pipeline2 из-за sandbox Operation not permitted для Git index.lock; это launch permission diagnosis, не semantic guard bypass. Та же frozen-facade команда через normal approval mechanism дала child/tee/pipeline0 и staged exact19. Pre-Done closeout preflight actual0 сообщил semantic_ready=true, staged_exact=true, git_writable=true, commit_ready=true, closeout_state=commit_ready и единственный helper-derived safe_command. На этом разрешённом final materialization path записан provisional Done; немедленно далее ordinary lint, final exact stage/preflight и helper-derived commit. При failed final gate Done подлежит canonical cleanup до owning non-Done; success подтверждает только actual postcommit helper/HEAD/index readback. Product9/draft/seven assets и accepted predicates не менялись. Root Sol+GLM acceptance002 и copy-only scan относятся к принятому code+proof; Manager capture/followups/PI/final-docs, root fresh final p0 на final committed clean HEAD и postcommit privacy delta readback этим precommit evidence не закрываются. Terminal plan после successful exact commit не дописывается; stdout/stderr и actual child/tee/pipeline rc — .tmp/ci_p3_proof/architect-semantic-closeout-acceptance002-20261104-v3/.

## Review artifacts
- Code review (primary): `docs/code_reviews/261104_0314_ci_python_compat_subset.md` — current, `✅ OK`, target `BUNDLE=current bundle_sha256=526570e3af721b8e81633fbeaf2ca593661622f291d050c72d51b99b788b8c0d`. Architect дописывает Arch review в тот же sole path; root exact-candidate Sol+GLM checkpoint до semantic commit остаётся обязательным.

## Q&A log (chronological, append-only)
### Architect Q&A
- [2026-11-04 11:08 +0300] (Architect, acceptance002) NO QUESTIONS: existing root precommit code+proof checkpoint accepted с sanitized binding и factual mode clarification; нового Owner permission/scope выбора не требуется. Ordinary native_existing local semantic closeout продолжается, postcommit root/Manager obligations отдельно.
- [2026-11-04 03:55 +0300] (Architect) NO QUESTIONS: scope, приёмка, F25/scoped ADR 006 и latest v3-name exception явно приняты Owner; новых решений, scope delta или pending activation при intake нет. Переход в `Architect draft` — template completion / plan hygiene; перед `Ready for Planner` требуется отдельная Architect формализация/MAD.
- [2026-11-04 04:11 +0300] (Architect) NO QUESTIONS: current writer/reader/consumer inspection позволила завершить N-A applicability и bounded subset contract без нового Owner choice. Scope/DoD, name exception и publication boundary прежние; queue/decomposition activation не требуется.
- [2026-11-04 05:10 +0300] (Architect, C-P3-1) NO QUESTIONS: root дал конкретное решение продолжить same-contract command-route repair; source/help подтверждают supported direct WORK i18n CLI. Required Owner action нет. Planner-owned reconciliation и повторный Coder proof остаются pending.
### Planner Q&A
- [2026-11-04 04:23 +0300] (Planner) NO QUESTIONS: проверены принятый subset/full contract, current runner/schema/workflow и locked environments; новых semantic решений и Owner вопросов нет. Missing draft и отсутствующий synthetic target — текущая Planner-owned materialization, не новое расширение scope.
- [2026-11-04 05:27 +0300] (Planner, C-P3-1) NO QUESTIONS: exact Architect/root decision разрешает только reconciliation существующего draft с тремя direct WORK i18n calls. Planner-owned steps/proof-route carrier требуют sync, поэтому это не redundant unchanged-contract Planner pass; новый Owner вопрос или architecture scope cycle не нужен.

### Coder Q&A
- [2026-11-04 05:41 +0300] (Coder, C-P3-1) NO QUESTIONS: route accepted owning ролями, fresh proof order и прежние predicates concrete.
- [2026-11-04 04:55 +0300] (Coder) NO QUESTIONS (sanity check: exact bundle, mandatory lanes, unchanged predicates и scoped docs routes заданы).
### Reviewer Q&A
- [2026-11-04 06:26 +0300] (Reviewer, contracts) NO QUESTIONS: accepted nine-target contract, retained qualified pair и root pre-commit checkpoints concrete; нового Owner choice или semantic scope gap нет.
### Owner answers (если owner хочет писать прямо сюда)
- 04.11.2026: явная команда выполнить P3 в принятом малом scope и normal native workflow; F25/scoped ADR 006 принят; push/GitHub writes/CI rerun/cancel/connection/cleanup/runtime/gateway/Home changes запрещены. Нового разрешения на старые recovery mechanisms нет.
- [2026-11-04, latest root override] Owner: «обходите гард, не ебите мозги». Исключение только для canonical-v2-name predicate фактических v3 Sol/ultra ролей через existing public Legacy SID writer после completed bootstrap и exact metadata verification. Продолжить полный П3 обычными v3 owning ролями до local terminal closeout; новых Manager/init/config, обхода иных guards или разрешения на старый П2 нет. Повторный Owner вопрос по принятому name exception не требуется.
- [2026-11-04, root decision C-P3-1, verbatim] Конкретное решение root по C-P3-1 после полученного STOP: продолжить текущий П3 штатным Architect response для same-contract command-route repair. Required Owner action нет. Исправить три i18n stamp/status команды внутри существующего принятого контракта, выбрав существующий repo-backed supported route; Scope, targets, acceptance и predicates сохранить. Frozen runtime/Home/allowlist/pins не менять, новый guard bypass не применять, предыдущее v3-name exception не расширять. Отказ rc64 и предварительный synthetic result сохранить: 10 tests до двух последующих assertions не являются final-source proof. После owning Architect/Planner reconciliation вернуть Coder по обычным gates для fresh unique proofdir и полного agreed proof envelope. Existing §Decisions checkpoint root Sol+GLM exact-candidate review перед semantic commit сохраняется; normal native Review/Architect идут по плану. Это конкретное root решение продолжить repair после остановки, а не повторить unsupported invocation и не игнорировать guard.

## Suggestions log (chronological, append-only)
### Architect suggestions
- [2026-11-04 03:55 +0300] (Architect) Сохранить минимальную foundation в существующем runner: фильтровать original canonical instances только после полного partition check, повторно использовать existing reports/events. Planner конкретизирует interface и cheap synthetic proof; отдельная fast-tier/event infrastructure не нужна.
- [2026-11-04 04:11 +0300] (Architect) Принята конкретизация existing foundation: optional subsets mapping, mutually-exclusive --subset, additive selected_subset и раздельный matrix selection key. Planner переносит этот semantic contract в exact draft/commands/tests и derived MAD ref; перечень новый test module + existing runner/schema/manifest/workflow + четыре doc pair carriers bounded, новых helper families и side-channel dispatch нет. Deadlock/anti-false-green self-check: unresolved Owner choice отсутствует; механика fixtures/report paths остаётся обычной Planner детализацией, а все named capabilities, mandatory lanes, negative cases и closure/retention criteria уже literal. Никакой promised contextual lane не оставлен implicit.
- [2026-11-04 05:10 +0300] (Architect, to=Planner, blocker=yes, C-P3-1) Выполнить только owning executable-carrier reconciliation: same draft sync для трёх direct WORK i18n calls из Decisions/Commands, без изменения nine targets, MAD и predicates; сохранить rc64/preliminary history и пройти fresh normal gates перед возвратом Coder. Same-contract reroute не разрешает silent reuse старого Censor/Ready for Coder proof и не разрешает выдать read-only --help за stamp/status или product qualification.
### Planner suggestions
- [2026-11-04 04:23 +0300] (Planner, to=Architect, blocker=no) Конкретизировать существующий контракт в одном exact draft: 9 implementation/doc targets, cheap synthetic fixture matrix, emitter/consumer parity, единый command envelope и отдельные WORK executions 3.10/3.12. Existing frozen facade остаётся только lifecycle/MAD/provenance/lint path; новый runner проверяется из WORK выбранным existing interpreter, как подтверждено root.
- [2026-11-04 05:27 +0300] (Planner, C-P3-1, to=Architect, blocker=no) Применяется принятое решение: direct WORK i18n stamp/stamp/status с existing PYBIN; frozen facade только для lifecycle/MAD/provenance/lint. Proof order сохраняет stamps до sources-before, status после executions перед unchanged two-pair assertion; fresh unique full envelope принадлежит Coder.

### Coder suggestions
- [2026-11-04 05:41 +0300] (Coder, C-P3-1) NO SUGGESTIONS: весь accepted envelope выполняется без нового contour.
- [2026-11-04 04:55 +0300] (Coder) NO SUGGESTIONS: принятый minimal subset contract исполняется в existing runner и cheap fixtures.
### Reviewer suggestions

## Objections / risks log (chronological, append-only)
### Architect objections
- [2026-11-04 03:55 +0300] (Architect) NO OBJECTIONS к принятому scope. Риски остаются обязательствами proof: девять IDs ещё candidate, skipped/failed compatibility не считается green; matrix-only не доказывает discovery; scoped docs green не исправляет broad frozen baseline. Product code, executable draft, tests/full14/full verify, config/runtime, commits и публикация в этом initial intake не выполняются.
- [2026-11-04 05:10 +0300] (Architect, C-P3-1 disposition) Root cause class: same-contract reroute. Live blocker — accepted command transport к неподдерживаемому runtime helper; существующий direct WORK CLI выбран source-backed и не требует нового helper/allowlist. Architect decision закрывает выбор маршрута, но Planner sync и Coder full fresh execution ещё блокируют product readiness. Исходная Coder objection и rc64 сохраняются; old preliminary tests не становятся final proof. Новый Owner вопрос, scope_expansion carrier, runtime patch или guard exception не нужны.
### Planner objections
- [2026-11-04 04:27 +0300] (Planner, blocker=no) Source-backed scoped i18n nuance: frozen `doc_lint --i18n-strict` глобален даже при literal --root. Executable Commands используют canonical `i18n_pairs status` плюс exact two-pair ok assertions; broad strict result не объявляется. Это bounded proof detailing без helper change или нового Owner choice.
- [2026-11-04 04:23 +0300] (Planner) NO OBJECTIONS к принятому scope: nine IDs остаются candidate до реальных runs; missing/skip capability, malformed full partition, incomplete accounting и existing-boundary HEAD drift не получают green по structural matrix. Synthetic target пока отсутствует и до strict preflight получит только fail-closed path-tracking carrier; implementation выполняет Coder.
- [2026-11-04 05:27 +0300] (Planner, C-P3-1) NO OBJECTIONS к accepted route. Initial rc64, preliminary 10/10 до двух assertions и stopped prerequisites остаются history, final-source qualification=false. Owning draft reconciliation закрывает transport carrier, не product execution; root Sol+GLM checkpoint до semantic commit и native Review/Architect обязательны.

### Coder objections
- [2026-11-04 05:41 +0300] (Coder, C-P3-1, status=closed) NO OBJECTIONS к corrected command route; technical route repair принят, real qualification остаётся текущей Coder обязанностью. Historical rc64 и preliminary proof сохранены.
- [2026-11-04 04:59 +0300] (Coder, to=Architect, blocker=yes, needs_owner=no, id=C-P3-1) Исправить accepted i18n command route: frozen facade rejects i18n_pairs.py rc64; stamp/status Commands невыполнимы. Existing direct helper сохраняет те же stamp/status predicates, но маршрут должен быть accepted upstream, а не молча заменён Coder. Evidence: .tmp/ci_p3_proof/coder-20261104T015724Z-74592/stamp-readme.log и .status; источник: frozen scripts/planveyor.zsh::planveyor_runtime_py. Product implementation сохранена; обе real compat axes и source freeze ещё не выполнены. Это same-contract command repair без scope_expansion marker.
- [2026-11-04 04:55 +0300] (Coder) NO OBJECTIONS: новые authority/schema contours не нужны; real compatibility и downstream review/terminal/root gates ещё не выполнены.
### Reviewer objections
- [2026-11-04 06:26 +0300] (Reviewer, contracts) NO OBJECTIONS: новые S1/S2/S3 не выявлены; обязательные root exact-candidate reviews/copy-only scan/final p0 и Architect/Manager terminal gates остаются downstream, AC7/8 не объявляются закрытыми этим native review.

## Post-merge gate (before deleting plan)
`N/A (why=publication/merge and cleanup are separate Owner-authorized stages; no plan deletion in this scope)`.

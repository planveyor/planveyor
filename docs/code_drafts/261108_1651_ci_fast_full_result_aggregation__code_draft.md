# Code draft: fast/full CI с независимым итогом по фактическим reports

**Date:** 2026-11-08 15:23 UTC
**Cluster:** infra
**Related plan:** `docs/plans/261108_1651_ci_fast_full_result_aggregation.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)

```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261108_1651_ci_fast_full_result_aggregation.md",
    "cluster": "infra",
    "targets": [
      {"path": "scripts/run_test_shard.py", "kind": "py"},
      {"path": "scripts/test_run_test_shard.py", "kind": "py"},
      {"path": "scripts/test_shards.json", "kind": "doc"},
      {"path": ".github/workflows/checks.yml", "kind": "doc"},
      {"path": "docs/tools/verify_suite.md", "kind": "doc"},
      {"path": "docs/tools/verify_suite.ru.md", "kind": "doc"}
    ],
    "deleted_paths": [],
    "machine_authority_decision_ref": {
      "applicability": "not_applicable",
      "reason_code": "no_machine_authority_change",
      "carrier_sha256": "d435d5a496b546069ce71672025c9ead04a3366aa611afb39abdfe8e3480e204"
    }
  }
}
```

## Provenance / session context

- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`
- Relation: `created-here`
- Thread ID: `01a1b0b3-5b5f-7ff2-8462-4c1f98b9f1d4`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-11-08T15:23:56Z`

Renderer output materialized явно; missing fields не достроены из coordination context. Derived MAD ref получен штатным stub/helper после validated upstream readback; semantic core не копируется.

## Purpose

Дать Coder точные additive CLI/report/worker/summary contracts и исполнимый бюджет проверки принятого P5b. Это contract, не implementation patch; target source в Planner pass не меняется. Все runtime результаты ниже PLANNED до actual Coder evidence.

## Reviewability preflight receipt

- `proof-path class`: `checked-in repo-local helper`.
- `mandatory primary lane`: existing `scripts/test_run_test_shard.py`, ровно4 свежих whole-module processes: prepared3.12/3.10 × physical/owned-alias TMPDIR, только дешёвые synthetic cases.
- `mandatory non-primary carrier / contextual lane`: existing source/YAML assertions с disabling mutations, independent fixed compat9 equality, два true canonical discovery/full-partition/composition `--check` без bodies; scoped ADR006 docs/basic hygiene/plan/bundle и separate dual review.
- `exact helper path + support files`: existing runner и selftests, manifest, workflow, paired verification runbooks из Meta; новый helper/schema/framework/registry не вводится.
- `dependent tests / dependent docs / known consumer paths`: CLI workers/matrix/preparation/summary; direct Python consumer `scripts/test_run_test_shard.py`; оба verify runbooks. `README.md`, `Makefile`, `scripts/plan_lint_changed.py`, `pyproject.toml`, manifest schema и public facade/verify runtime остаются read-only context.
- `preconditions / seed-discovery`: prepared interpreters/dependencies уже существуют; физический writable ignored task TMPDIR до Python/imports; каждый test создаёт свой tiny temp Git+unittest/report fixture. Checked-in seed/sample/history не нужен.
- `reroute rule`: сохранённый contract + конкретная implementation failure = `same-contract reroute`; новый target/schema/helper/API/budget/непокрытый contract = `real scope expansion` → Architect/Root ДО widening/нового runtime запуска.
- `perceptual truth-source split`: source/JSON/actual cases и terminal process returncodes; screenshots/OCR N/A (why=нет UI).
- `discovery-or-seed`: synthetic fixture или реальная discovery без bodies в двух разрешённых checks; `receipt-reuse-only`: summary читает сохранённые worker reports и workers не перезапускает.
- Stable identity: expected checkout SHA, manifest SHA256, profile, part, event, run ID/attempt, expected/observed Python, selector и ordered canonical IDs. Observer boundary: импорт/полный partition/composition до selection; actual result accounting после hooks; отдельный trusted expected context вне reports. Next canonical snapshot/readback после source edit — true checks, не ручная правка JSON.
- `runtime-lineage preflight`: current WORK source BASE/hash/modes и prepared interpreter/TMP binding до imports; frozen facade только control. Stale runtime/test copy → owning reroute до claim product failure.
- Retention: task `.tmp/ci_p5b_proof/` и disposable report/alias/Git fixtures — `transient local sanity only`; plan/draft/sole review и explicit native review assets — `durable operator/review evidence`. Hosted standard artifacts удерживаются normal artifact policy; отдельный исторический corpus не создаётся.

### Truth-host fixture matrix

| authoritative_host | derived_summary_field | green_case | missing_case | ambiguous_case | present_but_red_or_inconsistent_case | expected_fail_closed_verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Actual worker JSON + separately trusted event/run/SHA + current discovery/manifest | summary status/exit | exact expected corpus и IDs, no skips, complete | отсутствует один part | duplicate part/artifact или extra/stale run/attempt | s02 label исполнил s01, red report либо wrong SHA при success needs | nonzero; green derived label не перекрывает host |
| Actual preparation/verify/meta result через workflow needs | required ci-summary job | оба required needs success | skipped/missing/cancelled need | отсутствующий/лишний mandatory need | failed meta при green worker report | nonzero; summary всегда обязателен |

## Targeted changes (by file)

- `scripts/run_test_shard.py`: additive profile/composition policy, strict worker context/accounting и independent summary; старые CLI/report/events/local semantics совместимы.
- `scripts/test_run_test_shard.py`: сохранить все old IDs/существующие fixtures/timeout30; дополнить synthetic profile/strict/report/summary cases и фактические workflow source assertions/mutations.
- `scripts/test_shards.json`: только `contracts-a`, `contracts-b` entries и минимальная maintenance selectors для new selftest IDs; version/schema/local profiles/weights/compat9/old IDs/old full placement/order неизменны.
- `.github/workflows/checks.yml`: fast/full events, preparation, strict workers, standard artifacts, обязательный independent summary, metadata once, concurrency policy.
- `docs/tools/verify_suite.md`: события/матрицы/CLI/strict report/summary/required check/full release-SHA policy; прежний public full verification capability/default verify route сохранены.
- `docs/tools/verify_suite.ru.md`: синхронная русская пара того же operator contract. Существующий формат i18n/source metadata сохранить; если metadata присутствует, обновить штатно по final English source, без нового emitter.

Shared consumer semantics: report = execution evidence; summary = fail-closed CI verdict; neither = Planveyor lifecycle authority. `N/A (why=dispatch path unchanged/not owner-facing/not one-shot)`: Manager command/runtime fan-out отсутствует.

### Receipt schema emitter inventory

| family/surface | changed emitter/parser/readback | target decision | focused stale-emitter proof |
| --- | --- | --- | --- |
| Worker report JSON | `run_test_shard.py::run_selected/write_report`, new strict validator/summary in same file | in Meta targets | legacy report принимается старым local reader; strict summary отвергает absent CI fields, duplicate JSON keys, wrong types/context |
| Matrix JSON | existing `main/--matrix` в runner | in Meta targets | bare matrix exact old15 rows/fields/meta; explicit profiles4/15 и source-owned composition |
| Synthetic reports/expected CLI args | `test_run_test_shard.py` fixtures | in Meta targets | no fixture silently emits stale CI fields; independently declared expected literals vs actual CLI report |
| Workflow transport/expected context | `checks.yml` preparation/verify/ci-summary | in Meta targets | exact invocation/inputs/needs + source disabling negatives |
| Operator command examples | both verify runbooks | in Meta targets | doc/source CLI/field parity source assertion |
| Lifecycle scaffolds/runtime, `docs/api.md`, manifest schema | read-only context with N/A (why=no lifecycle/API/manifest-shape change) | не target | no generated lifecycle/bootstrap format affected |

## Steps / dependency order

1. Снять current source/old AST-ID/manifest placement/mode baseline; проверить clean staged area и неизменность read-only surfaces. Вне шести implementation targets не писать.
2. В runner зафиксировать independent source policy, затем profile matrix/check и strict-context validation. Только после работающего composition contract материализовать A/B exact entries из discovery в Coder lane.
3. Дополнить worker report/accounting и independent summary. Existing actual case instances/filter order/hooks, atomic reports, interruption diagnostics и local exits сохранить.
4. Добавить cheap synthetic cases и workflow parsed-source assertions; затем изменить workflow. Не создавать report-meta registry.
5. Синхронно обновить обе verification docs. Снять final static source/ID/placement/mode readback.
6. Исполнить ровно4 narrow processes и2 canonical checks ниже; final post-write plan/scoped docs/basic hygiene/bundle gates, dual review и Arch checks — обычный conveyor. Новый runtime запуск вне budget требует upstream concrete finding.
7. Перед staging/Done/semantic commit/closeout остановиться: exact UNSTAGED candidate со всеми member bytes/hash/Git+Unix modes/base/tree/index/staged0/helper/test/review proofs → Root independent physical copy/COPY-index scan. Только его scoped ACCEPT разрешает дальше native materialization. Future commit/family/finaldocs/Rootp0 — pending delivery obligations, не pre-Done фикция.

## Exact CLI contract (новый API, реализует Coder)

Общие existing `--root`/`--manifest` остаются; supported runtime3.10–3.12. Existing mutually exclusive modes сохраняются, добавляется только `--ci-summary DIRECTORY`. `--ci-profile {fast,full}` — additive option, не отдельный selector.

| invocation | обязательное поведение |
| --- | --- |
| bare `--matrix` | старый structural/no-import JSON: s01..s14 Python3.12/meta onlys01, compat3103.10/meta false; прежние fields |
| `--matrix --ci-profile fast\|full` | canonical discovery → full exact-once partition → ALL CI composition checks → selected profile rows; JSON `{"include":[...]}` |
| `--check --ci-profile fast\|full` | те же полные checks, без bodies; проверяет policy ОБОИХ profiles/всех4 subsets независимо от selected profile; selected profile только readback |
| bare legacy selectors/check | прежняя generic validation/local behavior; CI-only no-skip/expected-context strictness opt-in |
| selector + `--ci-strict --ci-profile ...` | требует полный worker context ниже; exact part→selector/Python policy ДО bodies |
| `--ci-summary DIR --ci-profile ...` | всегда strict; требует common trusted context и `--ci-needs-json JSON`; заново current discovery/partition/ALL composition, затем читает actual corpus, bodies не запускает |

Worker flags: `--ci-part NAME`, `--ci-python 3.12|3.10`, `--ci-event push|pull_request|schedule|workflow_dispatch`, `--ci-run-id POSITIVE_DECIMAL`, `--ci-run-attempt POSITIVE_DECIMAL`, `--ci-expected-sha LOWERCASE_40HEX`; только PR требует `--ci-pr-head-sha LOWERCASE_40HEX`. Non-PR PR-head field = null; недопустимый/лишний PR flag отвергается. Summary принимает те же common event/run/attempt/SHA/PR flags, но не worker part/Python/selector/`--ci-strict`; profile independently задаёт expected parts. `--ci-needs-json` только summary: object с mandatory `shard-matrix` и `verify`, оба `result="success"`; keyset needs ровно эти два job IDs, missing/лишний job/unknown result non-green; их output maps не являются expected-ID truth.

Не разрешать `--ci-strict` без profile, worker CI fields без strict, profile + local-profile, summary + selector/check/matrix/durations, либо частично заданный CI context. `--matrix/--check --ci-profile` не требуют live run context. Bare matrix не включает новую `part` field; explicit profile rows добавляют `part`: fast core/contracts-a/contracts-b/compat310, full s01..s14/compat310. Existing selector/Python/meta fields прежней формы.

Mode boundary явно: любой execution selector вместе с `--ci-profile` требует `--ci-strict` и весь worker context; profile+selector без strict не является legacy fallback. Matrix/check с profile принимают только profile, без worker/live context; summary всегда strict без worker-only flags. Cheap invalid-argv subTests входят в `test_ci_worker_context_fails_before_bodies`, новых methods/processes не требуется.

Exit contract: success0; выполненные strict cases с failure/skip/incomplete/drift → report red/exit1; malformed context/composition/report corpus/needs → nonzero (PartitionError path2 допустим). Missing worker report не заменяется synthetic success. Summary печатает computed JSON `status`, `ci_profile`, `ci_run_id`, `ci_run_attempt`, `ci_expected_sha`, `parts`, `manifest_sha256`; это verdict/readback, не новый artifact registry. На отказе stderr называет причину.

## Independent composition / preservation contract

В source runner (ВНЕ mutable `subsets.*.ids`) — fixed core16 IDs из plan §7/existing selftest `required_fast_ids`, fixed compat9 literal IDs и explicit module policy ниже. Selftests держат independent expected literals, не вычисляют expected из изменяемого subset или проверяемой runner constant.

- `fast` ровно те existing16 IDs; original timing witness остаётся full-only, F остаётся whole-method core witness. Обязательная negative: убрать known floor ID из иначе nonempty fast → отказ.
- `compat310` ровно fixed9 ниже (manifest bytes/array order неизменны). Обязательная negative: удалить последний known `test_public_facade_init_doctor_and_compatible_upgrade` из entry, оставив8 → composition отказ. Проверка generic nonempty/knownIDs отдельно недостаточна.
- A = все canonical IDs module `test_planveyor_plan_bundle`; B = все canonical IDs explicit29 ниже. Independent expected membership из actual discovered `case.id()` module, не из selector rows/serialized ID lists и не ALL-minus-A.
- Проверить каждый named module существует/даёт nonempty cases; A/B/core pairwise disjoint; A∪B = independently expected contract universe. Unknown/duplicate/missing IDs в любом configured subset non-green. New canonical methods mandatory modules включаются автоматически; snapshots3528/142/1498/1640 не ceilings.
- Canonical full partition exact once до любой selection. Full profile требует s01..s14, compat отдельно; fast union=core∪A∪B, не весь canon; compat overlaps with other profile parts допускаются только как отдельная axis.
- Existing full selectors/case order/local profiles/weights/timeouts и original init_capture module byte/mode immutable. `test_run_test_shard` уже whole-module selector в s03: новые test methods естественно принадлежат s03 и B; лишняя ID selector row не нужна. Если actual source selector окажется explicit IDs, только минимальное добавление новыхIDs в той же прежней ownership без старого reorder.
- Old tests сохраняют IDs. `test_matrix_and_workflow_selection_contract` обновляет assertions под новую workflow invocation и independent policies; прежний bare matrix/schema/default selectors checks удерживаются. `test_matrix_is_structural_and_requires_compat310` остаётся legacy3-shard/no-import fixture.

Fixed compat9:
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

Explicit B module policy:
```text
test_authority_vocabulary_prompt_contract
test_censor_prompt_contract
test_manager_custom_pipeline_prompt_contract
test_plan_lint
test_plan_lint_changed
test_review_header_metadata
test_run_test_shard
test_sibling_contract_docs
test_zcode_bootstrap_lifecycle_prompt_contract
test_plan_handoff_digest
test_plan_harvest_lint
test_plan_status_oracle
test_planning_wave_readback
test_planveyor_plan_list
test_doc_lint
test_doc_lint_policy
test_shared_docs_mirror_drift
test_review_artifact_lint
test_analysis_source_ownership
test_build_role_bundles
test_planveyor_profile_extraction
test_planveyor_shared_corpus_contract
test_check_planveyor_profile_contract
test_planveyor_codex_agent_roles
test_contract_authority_matrix_check
test_oss_release_scan
test_oss_evidence_prepare
test_docs_closeout
test_plan_queue
```

Core16 literal carrier уже целиком открыт в plan §7 и existing `test_matrix_and_workflow_selection_contract::required_fast_ids`; Coder переносит ровно его, selftest expected не заменяет импортом runner policy. Root accepted source baseline в plan и собственный preservation receipt сохраняют исходные16 bytes/IDs; дополнительный замер/whole-method run не разрешён.

## Worker report parity / exact accounting

Existing fields/local meanings сохраняются: `status,head_before,head_after,manifest_sha256,python,selected_shards,selected_subset,planned_ids,started_ids,completed_ids,tests_run,skipped,completion_exact,result_successful,failures,errors,wall_seconds,durations_source,durations`. Existing events сохраняются diagnostic-only.

Additive strict fields (не генерируются как ложный CI claim в legacy mode):

| field | strict type / origin |
| --- | --- |
| `ci_profile,ci_part,ci_event` | string, validated explicit context + independent part policy |
| `ci_run_id,ci_run_attempt` | positive decimal strings (без coercion из float/bool) |
| `ci_expected_sha` | lowercase40hex, отдельно trusted workflow github.sha |
| `ci_pr_head_sha` | lowercase40hex только PR, иначе null |
| `ci_expected_python` | exact "3.12" либо "3.10" из source part policy |
| `ci_python` | object exactly `{"major":int,"minor":int}`, actual sys.version_info; bool не int |

До bodies: все fields/type/part-policy/selector совпадают; actual Python axis совпадает; current HEAD равен trusted expectedSHA. После whole selected suite/hooks: оба observed HEAD равны тому же expectedSHA; manifest bytes/hash не дрейфуют на execution boundary; strict no skips; status green и result_successful/completion_exact строго true; failures/errors пусты; tests_run=int=len(expected)>0; planned_ids=started_ids=completed_ids=independent ordered expected IDs, каждый ровноодин. Legacy Counter semantics не ужесточаются молча: ordered/no-skip condition применяется только strict.

Python3.12 strict report требует existing `durations_source="unittest-native"` и existing native durations list объектов `{"test":string,"seconds":number}` с finite nonnegative seconds; Python3.10 требует existing `durations_source="wall-only"` и `durations=null`. Не invent durations field/schema и не сравнивать performance. Список skip из method/class/module-hook обязан давать non-green, даже если `wasSuccessful()` true; interruption сохраняет actual partial report и не green. Same wrong before=after HEAD не проходит expectedSHA.

## Workflow / standard artifact fan-in

- push(main)/pull_request → fast; `schedule: cron '17 2 * * *'` и `workflow_dispatch` → full. Ни paths/docs-only bypass, ни release event/action. Existing macos-latest/timeout105/fail-fast:false/setup/cache/path "My Planveyor"/fetch-depth0 сохраняются.
- Сохранить `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`, `actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1`, `permissions: contents: read`. Все job checkouts явно `ref: ${{ github.sha }}`; PR = synthetic merge SHA, head SHA отдельно diagnostic context, не checkout substitute.
- Workflow env: `CI_PROFILE` = fast только push/PR, иначе full; `CI_EVENT=${{ github.event_name }}`, `CI_RUN_ID=${{ github.run_id }}`, `CI_RUN_ATTEMPT=${{ github.run_attempt }}`, `CI_EXPECTED_SHA=${{ github.sha }}`, `CI_PR_HEAD_SHA=${{ github.event.pull_request.head.sha }}`. Передавать trusted strings через env/quoted argv, не shell-interpolate external PR text.
- Concurrency: fast group `workflow-fast-ref` с latest-wins cancel=true; full group `workflow-full-run_id-run_attempt` с cancel=false. В expression full содержит оба run identifiers, так что pending full не вытесняется новой full.
- `shard-matrix`: own checkout и pinned setup-python3.12, затем existing `Install shell tools` (brew ripgrep + command-v rg/zsh + zsh -df check), `Select build interpreter`/PYBIN и `make bootstrap-python` из requirements-dev.lock ДО profile matrix command; bytecode-off. Это нужно для canonical imports, bare structural matrix прежде зависимостей не требовал. Existing install policy/lock неизменны; никакого local install в Planner/Coder launch. Expose only matrix output; expected context summary не берёт из неё.
- `verify`: needs shard-matrix, selected matrix fromJSON. Strict worker invocation с exact part/selector/Python и trusted context; optional PR flag через shell array. Four metadata steps только `if: matrix.meta`: doc+i18n strict, changed-plan lint, make typecheck (mypy3.10 policy), make oss-release-scan. Fast meta только contracts-b; full meta толькоs01; compatfalse.
- Event base для changed-plan lint: PR `git merge-base "origin/$BASE_BRANCH" HEAD` обязан успешно разрешиться (не fallback при unavailable PR base); push valid nonzero BEFORE_COMMIT либо existing root commit fallback; schedule/manual HEAD^1 если существует, иначе root fallback. После branch choice явный `git cat-file -e "$base^{commit}"` и печать event/base/head; actual command `"$PYBIN" -B scripts/plan_lint_changed.py --base "$base" --head HEAD`. Никаких silent missing-base skip.
- Worker пишет только `$RUNNER_TEMP/result.json` + diagnostic events. Upload step `if: always()`, `if-no-files-found: error`, `overwrite: false`; upload только result.json (не events), artifact `planveyor-ci-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.part }}`. Setup/abort failure без report → missing artifact/не green, fake report запрещён.
- `ci-summary`: `if: always()`, `needs: [shard-matrix, verify]`, own checkout/current source/pinned setup-python3.12; те же existing shell-tools/PYBIN/`make bootstrap-python` prerequisites ДО canonical summary imports, bytecode-off. Дополнительные meta checks здесь не дублируются. Download standard current repository/current workflow run, `pattern: planveyor-ci-${{ github.run_id }}-${{ github.run_attempt }}-*`, `merge-multiple: false`, fresh `$RUNNER_TEMP/ci-reports`; без github-token/repository/run-id override/API client. Старые attempt namespaces не выбираются вместо current attempt; stale/foreign fields внутри любого полученного current artifact отвергаются. Никаких overwrite/фильтра red reports.
- Summary command из current runner с independent CI profile/event/run/attempt/SHA/PR context и `--ci-needs-json "$CI_NEEDS_JSON"`; env `CI_NEEDS_JSON=${{ toJSON(needs) }}`. Он discovery/partition/composition выводит сам, не берёт expectedIDs/prep matrix/report claims как expected truth.
- Directory corpus ровно `planveyor-ci-<run>-<attempt>-<part>/result.json` для каждого independently expected part. Extra directory/file, duplicate part, stale/foreign attempt/profile, malformed/duplicate-key JSON, interrupted/red/skip/incomplete, wrong context/selector/Python/durations/manifest/HEAD/IDs → nonzero. Summary проверяет expected current HEAD == trusted SHA и current manifest hash; all14 full ID union exactcanononce, compat отдельно; fast core/A/B exactpartition intended fast universe.
- Summary обязателен как required check `ci-summary`; docs называют его, rulesets не правятся. `needs.verify.result` остаётся дополнительным guard, expected-vs-expected/needs-only не заменяет actual reports. If summary удалён/disabled/missing needs — source tests красные; configuration не означает hosted success.

### Literal workflow argv (будущая source materialization)

Worker env дополнительно связывает `CI_PART=${{ matrix.part }}`, `CI_PYTHON=${{ matrix.python-version }}`, `CI_SHARD=${{ matrix.shard }}`, `CI_SUBSET=${{ matrix.subset }}`. Source assertion исполняет этот shell с fake PYBIN и проверяет actual argv каждой из4/15 row forms; сам fake не импортирует/не запускает WORK cases.

```bash
set -euo pipefail
ci_context=(--ci-profile "$CI_PROFILE" --ci-event "$CI_EVENT"
  --ci-run-id "$CI_RUN_ID" --ci-run-attempt "$CI_RUN_ATTEMPT"
  --ci-expected-sha "$CI_EXPECTED_SHA")
if [[ "$CI_EVENT" == pull_request ]]; then
  ci_context+=(--ci-pr-head-sha "$CI_PR_HEAD_SHA")
fi
if [[ -n "$CI_SUBSET" ]]; then
  ci_selector=(--subset "$CI_SUBSET")
else
  ci_selector=(--shard "$CI_SHARD")
fi
"$PYBIN" -B scripts/run_test_shard.py "${ci_selector[@]}" --ci-strict \
  --ci-part "$CI_PART" --ci-python "$CI_PYTHON" "${ci_context[@]}" \
  --report "$RUNNER_TEMP/result.json"
```

Summary shell независимо строит тот же common context из workflow event env (не worker output), затем единственная validator command:

```bash
"$PYBIN" -B scripts/run_test_shard.py --ci-summary "$RUNNER_TEMP/ci-reports" \
  "${ci_context[@]}" --ci-needs-json "$CI_NEEDS_JSON"
```

Preparation command после selected prepared interpreter: `"$PYBIN" -B scripts/run_test_shard.py --matrix --ci-profile "$CI_PROFILE"`. `ci_context` в summary создаётся явно теми же первыми строками common-array block; worker-only selector/part/Python flags туда не попадают.

### Immutable artifact actions — independently opened official sources

- Upload `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02`: [official v4.6.2 release](https://github.com/actions/upload-artifact/releases/tag/v4.6.2) → [exact commit](https://github.com/actions/upload-artifact/commit/ea165f8d65b6e75b540449e92b4886f43607fa02); [immutable action.yml](https://raw.githubusercontent.com/actions/upload-artifact/ea165f8d65b6e75b540449e92b4886f43607fa02/action.yml) подтверждает name/path/if-no-files-found/overwrite, node20.
- Download `actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093`: [official v4.3.0 release](https://github.com/actions/download-artifact/releases/tag/v4.3.0) → [exact commit](https://github.com/actions/download-artifact/commit/d3f86a106a0bac45b974a628896c90dbdf5c8093); [immutable action.yml](https://raw.githubusercontent.com/actions/download-artifact/d3f86a106a0bac45b974a628896c90dbdf5c8093/action.yml) подтверждает current-run default, pattern и separate named directories.
- Проверено read-only 2026-11-08. Это проверенная immutable source binding/API compatibility, не hosted run, installation или обещание latest version. Floating tags/новые permissions не нужны.

## New exact cheap test IDs / producer-negative map

Все новые methods в existing `TestRunTestShard`; canonical prefix `test_run_test_shard.TestRunTestShard.`. Старые method IDs сохраняются. Двенадцать methods ниже — точный planned delta; subTests разделяют вариации без дополнительных module processes.

| method suffix | actual producer / positive | required negatives |
| --- | --- | --- |
| `test_ci_profiles_have_exact_parts_and_composition` | source policy + tiny discovered cases, fast4/full15/bare legacy15 | unknown profile/part, empty/missing/disjointness, full partition invalid до selection |
| `test_ci_membership_comes_from_fixed_module_policy` | A module + exact29 B fixtures; extra new canonical method автоматически included | missing A/B module, ALL-minus-A/foreign module, A/B/core overlap/duplicate/stale |
| `test_ci_core_and_compat_floors_reject_nonempty_deletions` | independent literal16/9 expected + fixture composition | удалить known core ID при15 remaining; удалить known compat facadeID при8 remaining; unknown/reordered compatibility carrier |
| `test_ci_worker_context_fails_before_bodies` | real CLI tiny tempGit/loader/hooks/marker | wrong/missing type/profile/part/selector/Python/event/run/attempt/expected SHA/PR context; marker absent before body |
| `test_ci_worker_report_uses_actual_cases_and_context` | actual tiny selected cases, stdout/report/events identity | wrong ordered IDs/repeated start/completion, manifest drift/HEAD drift, equal wrong HEADs |
| `test_ci_worker_skips_fail_closed` | actual unittest method/class/module skip fixtures | successful-but-skipped/report partial; preserve legacy skip semantics separately |
| `test_ci_summary_accepts_fast_and_full_report_fixtures` | deterministic synthetic4/15-part report corpus; отдельно actual tiny strict worker current Python axis создаёт настоящий report для parser parity | compat separated, full canonicalunion vs fastintendedunion, expected rows не substituted |
| `test_ci_summary_rejects_missing_stale_and_ambiguous_reports` | mutate copies of one valid synthetic actual report corpus | missing/extra/duplicatepart/path/attempt/run, malformed/duplicatekeys, absent CI fields/strict types |
| `test_ci_summary_rejects_green_labels_with_wrong_execution` | independently expected context/IDs + mutated actual reports | s02 label/s01 IDs, wrongselector/Python/durations/manifest/HEAD, unknown/missing/duplicate/reorderedIDs, red/incomplete/skip/interrupted |
| `test_ci_summary_needs_cannot_hide_authoritative_red` | actual corpus + parsed needs | missing/skipped/cancelled/failed prepare/verify, green needs with red report, green report with failed meta/needs |
| `test_ci_workflow_contract_rejects_disabling_mutations` | parse current YAML (existing PyYAML) + assert actual commands/conditions/needs/context/pins/concurrency | delete EACH4meta steps; if:false job/eachrequiredstep; wrong/absent/duplicate matrix.meta row; continue-on-error job/requiredstep; delete summary/required needs; remove trustedSHA/artifact transport |
| `test_ci_workflow_event_bases_and_command_parity` | run extracted shell command with existing fake PYBIN + tiny Git history/event env, no WORK testbodies | PR unavailablebase mustfail, pushzero/missing fallback, schedule/manual HEAD^1/root; strictargv/summary/report fields/docs snippets parity |

Tiny CI fixture может создать exact named modules/classes/method IDs policy как no-op trace cases и14 shallow shard buckets: это synthetic corpus, не импорт настоящих WORK witnesses. Helpers ограничены этим selftest file; перед/после fixture восстановить cwd/sys.path/sys.modules по всем generated test module names. Не переиспользовать mutable report/state между independent scenarios; clone corpus только для одного negative с отдельным fresh path. Expected policies в tests literal и independent от mutated subset/runner constant. Existing raw child timeout30 сохраняется; не запускать настоящий ROOT `--matrix --ci-profile`, full discovery, core/contracts/F внутри module tests. Real ROOT bare `--matrix` и source/AST/static manifest inspection допустимы внутри budget.

B включает сам `test_run_test_shard`: synthetic fixture в текущем narrow process обязан snapshot/remove/restore exact прежний `sys.modules` object и для этого имени, включая exception path; physical WORK ROOT сохраняется до fixture chdir. Иначе loader может ошибочно взять уже импортированный настоящий module вместо tiny temp module. Это fixture isolation внутри того же selftest file; production helpers/fixtures не редактируются и WORK contract bodies не запускаются.

Один narrow process не может честно исполнить обе Python axes: actual positive worker fixture запускает только rows своей prepared axis (3.12 или compat3.10), wrong-axis negative отказывает до body. Summary positive4/15 corpus — явно synthetic JSON fixture, включая foreign-axis records, с независимо заданными expected policies; это проверка aggregation/parser, не claim actual cross-axis hosted execution. Actual current-axis producer report проверяет field/schema parity, а полный hosted4/15 actual-report fan-in остаётся будущей квалификацией Root. Не spawning второй prepared interpreter ради этих fixtures и не подменять actual sys.version_info/HEAD production claims.

Парсить YAML actual job/step controls, не только name/string presence. Проверить все required commands по tokenized argv/source и meta rowpolicy, conditions не false/removed, continue-on-error отсутствует/false, summary always+needs exact. Mutation test должен реально вызвать тот же assertion helper и получить refusal для КАЖДОЙ вариации, оставляя job/step names прежними где возможно. Existing PyYAML boolean treatment key `on` обработать явно (`workflow.get("on", workflow.get(True))`); новый dependency не добавлять.

## Runnable downstream validation — только Coder, PLANNED

Prepared `P5B_PY312`/`P5B_PY310` задаёт trusted внешний per-launch context; absolute paths публично не фиксируются. Внешний current task root уже существует, команды ниже проверяют его ДО любого Python/nested login. Shell capture сохраняет отдельные actual child/stdouttee/stderrtee/final rc; parsing только после terminal0. Это inline стандартные primitives/существующий WORK proof route, не новый checked-in wrapper/helper.

```bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export P5B_TASK_TMPDIR="$PWD/.tmp/ci_p5b_proof"
export TMPDIR="$P5B_TASK_TMPDIR"
test -d "$TMPDIR" && test -w "$TMPDIR"
test "$(cd "$TMPDIR" && pwd -P)" = "$TMPDIR"
git check-ignore -q .tmp/ci_p5b_proof
: "${P5B_PY312:?prepared interpreter required}" "${P5B_PY310:?prepared interpreter required}"
P5B_VALIDATION_ROOT="$(mktemp -d "$TMPDIR/coder-validation.XXXXXX")"
export P5B_VALIDATION_ROOT
mkdir "$P5B_VALIDATION_ROOT/physical"
ln -s "$P5B_VALIDATION_ROOT/physical" "$P5B_VALIDATION_ROOT/owned-alias"
p5b_capture() {
  local label="$1"; shift
  local d="$P5B_VALIDATION_ROOT/$label"; mkdir "$d"
  mkfifo "$d/stdout.pipe" "$d/stderr.pipe"
  tee "$d/stdout" < "$d/stdout.pipe" & local op=$!
  tee "$d/stderr" < "$d/stderr.pipe" >&2 & local ep=$!
  "$@" > "$d/stdout.pipe" 2> "$d/stderr.pipe" & local cp=$!
  local cr=0 orc=0 erc=0 final=0
  wait "$cp" || cr=$?; wait "$op" || orc=$?; wait "$ep" || erc=$?
  for rc in "$cr" "$orc" "$erc"; do
    if test "$final" = 0 && test "$rc" != 0; then final="$rc"; fi
  done
  printf 'child=%s stdouttee=%s stderrtee=%s final=%s\n' "$cr" "$orc" "$erc" "$final" | tee "$d/status"
  return "$final"
}
```

Следующий block = ровно4 whole narrow module processes. Metadata/preimport assertions находятся внутри того же module process, не отдельные measured/test processes. Не canonical discover всего WORK.

```bash
for axis in 3.12 3.10; do
  if test "$axis" = 3.12; then export PYBIN="$P5B_PY312"; else export PYBIN="$P5B_PY310"; fi
  export PATH="$(dirname "$PYBIN"):/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  export P5B_EXPECTED_EXECUTABLE="$PYBIN" P5B_AXIS="$axis"
  for mode in physical owned-alias; do
    export TMPDIR="$P5B_VALIDATION_ROOT/$mode" P5B_TMP_MODE="$mode"
    p5b_capture "selftests-$axis-$mode" "$PYBIN" -B -c '
import json, os, pathlib, subprocess, sys
root = pathlib.Path.cwd().resolve()
raw = os.environ["TMPDIR"]
physical = pathlib.Path(raw).resolve()
assert physical == pathlib.Path(os.environ["P5B_VALIDATION_ROOT"]) / "physical"
assert (raw != str(physical)) == (os.environ["P5B_TMP_MODE"] == "owned-alias")
assert root / ".tmp" in physical.parents and os.access(raw, os.W_OK)
assert subprocess.run(["git", "check-ignore", "-q", str(physical.relative_to(root))]).returncode == 0
assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1" and sys.dont_write_bytecode
assert ".".join(map(str, sys.version_info[:2])) == os.environ["P5B_AXIS"]
assert pathlib.Path(sys.executable).resolve() == pathlib.Path(os.environ["P5B_EXPECTED_EXECUTABLE"]).resolve()
probe = pathlib.Path(raw) / ("binding-" + str(os.getpid()))
with probe.open("xb") as out:
    out.write(b"task-owned\n"); out.flush(); os.fsync(out.fileno())
print(json.dumps({"python": sys.version, "executable": sys.executable, "tmp_raw": raw,
                  "tmp_physical": str(physical), "bytecode_off": True}), flush=True)
import unittest
sys.path.insert(0, str(root / "scripts"))
suite = unittest.defaultTestLoader.loadTestsFromName("test_run_test_shard")
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
'
  done
done
```

Следующий block = ровно2 true canonical checks; модуль WORK Python3.10-importable ДО compat filtering. `--ci-profile fast` по exact CLI contract проверяет обе matrices/все4 composition sets/full partition, bodies отсутствуют. Это отдельная axis discovery, не повтор narrow suite.

```bash
export TMPDIR="$P5B_TASK_TMPDIR"
for axis in 3.12 3.10; do
  if test "$axis" = 3.12; then export PYBIN="$P5B_PY312"; else export PYBIN="$P5B_PY310"; fi
  export PATH="$(dirname "$PYBIN"):/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  export P5B_EXPECTED_EXECUTABLE="$PYBIN" P5B_AXIS="$axis"
  p5b_capture "canonical-check-$axis" "$PYBIN" -B -c '
import json, os, pathlib, subprocess, sys
root = pathlib.Path.cwd().resolve()
raw = os.environ["TMPDIR"]
physical = pathlib.Path(raw).resolve()
assert raw == str(physical) == str(root / ".tmp/ci_p5b_proof")
assert os.access(raw, os.W_OK)
assert subprocess.run(["git", "check-ignore", "-q", ".tmp/ci_p5b_proof"]).returncode == 0
assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1" and sys.dont_write_bytecode
assert ".".join(map(str, sys.version_info[:2])) == os.environ["P5B_AXIS"]
assert pathlib.Path(sys.executable).resolve() == pathlib.Path(os.environ["P5B_EXPECTED_EXECUTABLE"]).resolve()
print(json.dumps({"python": sys.version, "executable": sys.executable, "tmp_raw": raw,
                  "tmp_physical": str(physical), "bytecode_off": True}), flush=True)
import runpy
sys.argv = ["scripts/run_test_shard.py", "--check", "--ci-profile", "fast"]
runpy.run_path(str(root / "scripts/run_test_shard.py"), run_name="__main__")
'
done
export PYBIN="$P5B_PY312"
export PATH="$(dirname "$PYBIN"):/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export TMPDIR="$P5B_TASK_TMPDIR"
```

Alias действует только в controlled own fixture этих четырёх test launches; он НЕ normalizes away до class/module imports. Control facade и final gates используют physical root. Fixture normal TemporaryDirectory teardown сохраняется; old task receipts/proofs и alias setup не чистить. Нет auto install/env repair.

## Static gates / preservation / honest result boundary

Текущий Planner выполняет только plan/draft/doc/parser/static source checks. Coder после edit использует тот же exact source snapshot:
- stdlib AST parse на обеих prepared axes; old selftest method IDs сохранены + ровно12 declared new IDs, source remains3.10 compatible; source bytes/modes read-only files и original init_capture module exactBASE.
- JSON strict parse с duplicate-key rejection; old manifest fields/selector segments/order/placement/local profiles/weighting/compat9 byte span unchanged; только два новых subset entries/necessary newID maintenance. A/B lists materialize из final canonical discovery, independent source policy проверяет membership; counts пересчитываются фактически, не premarked3528/1640.
- Parsed YAML event/worker/summary/meta/source assertions исполняются в четырёх narrow processes; Planner может проверить syntax только, не утверждать их runtime PASS.
- Current scoped doc/basic hygiene exact roots: PLAN_PATH, linked draft; после implementation плюс оба target runbooks; workflow обязательная broad strict/i18n command сохраняется. F25 baseline debt scoped gate не исправляет и не доказывает broad green.
- Plan control gates: `plan_lint.py PLAN_PATH`, strict `planveyor_plan_bundle --preflight PLAN_PATH` до Ready for Coder; final post-review `--check` позже по owning lane. Review PLANNED сейчас честен.
- `git diff --check` плюс UTF-8/LF/trailing-whitespace/conflict-marker/regular0644 readback untracked plan/draft (Git diff их не видит), current HEAD/tree/index/stagedempty/source hashes. No staging/commit.

Ни4 selftests, ни2 checks не исполняются в Planner. Дополнительный test/runtime process вне declared budget — конкретное finding → Architect/Root ДО запуска. Original s11/F/core16/contracts/fullsuite/all14shards/A-B/profiling/тайминги/guard/deadline изменения не разрешены. Hosted full actual release-SHA остаётся future prerequisite после отдельно разрешённой публикации; local synthetic green не hosted qualification и не one-hour promise.

## Review route

- `Primary artifact`: `docs/code_reviews/261108_1651_ci_fast_full_result_aggregation.md`.
- `Lane type`: code review (две native lanes и Architect в одном sole host).
- Сейчас PLANNED; accepted verdict/scan/commit не выдумываются.

## Patch sketch (keep it small)

Steps выше определяют interfaces и proof boundaries; production implementation принадлежит Coder. Точечные функции можно организовать внутри existing runner: source composition validator, validated CI context, profile rows, strict report validator, independent summary. Дублировать unittest objects/discover after filtering, загружать reports как expected truth или подменять skips green запрещено.

## Critical invariants / traps / bypass paths

- Invariant: actual reports подтверждают independently expected execution. Trap: expected matrix vs regenerated matrix/needs-only или два equal wrong HEADs. Bypass: wrong part label/selector/Python, missing artifact/summary; negatives выше failclosed.
- Invariant: CI composition выше mutable selector IDs. Trap: self-comparison subset to itself/ALL-minus-A/nonempty-only compat. Bypass: known mandatory ID deletion при remaining IDs; independent literal/source policy обязан отказать.
- Invariant: four meta commands и required summary реально включены. Trap: job/step name сохранился при if:false/continue-on-error/deleted needs. Bypass: parsed-source mutation matrix.
- Invariant: local/default/bare full capability и actual cases/order/hooks не регрессируют. Trap: CI strictness применяется неявно ко всем local calls; covered old methods/legacy fixtures.
- UI/Golden Path/return callback/concurrency DB proof: N/A (why=CI source/process slice; hosted overlap qualification отдельно, DB/UI нет).

## Assumptions / risks

Prepared interpreters/dependencies и task root — существующие inputs, не install task. Artifact pins verified official sources; hosted availability остаётся внешним результатом. Full required release-SHA и cancellation/queue поведение подтвердит Root отдельным hosted run после publication authority. Это не повод расширить local validation. Новая реальная потребность седьмого target/helper/schema/API или более широкого test budget — upstream stop.

## Notes for Coder

Plan важнее sketch; semantic conflict → owning Architect, без silent repair/widening. Все old receipts/Done plans byte-immutable. Новые Evidence prefixes содержат actual YYYY-MM-DD HH:MM UTC. Не исполнять raw commands до prepared env/TMP binding; не брать tests из frozen runtime. Не stage/Done/closeout до Root exact-candidate ACCEPT. Ни generic initialGO, ни другой scan не scan этого final candidate.

## Review stamps (append-only)

- [2026-11-08 15:29 UTC] (Planner) Создан executable contract по current template; actual runtime proof pending. Completion pass и финальные static gates отражаются в plan/current raw proof после materialization.
- [2026-11-08 15:40 UTC] (Planner) Повторно прочитан весь materialized contract; source-bound duration markers, current-attempt artifact namespace и current-axis actual worker/synthetic summary split уточнены до gates. NO SUGGESTIONS (completion/closure-path reviewed; новых изменений контракта не требуется). Static parsers обеих prepared axes, plan/doc/hygiene/strict preflight actual green; final-byte gates после этого stamp обязательны. Runtime budget4+2, separate CENSOR/review и Root privacy checkpoint pending.
- [2026-11-08 15:56 UTC] (Planner) Separate second pass: уточнены profile+selector strict-mode boundary, existing preparation/summary setup до canonical imports и exact self-module sys.modules restoration synthetic B fixture. Exact six targets/ref/12 IDs/budget4+2 сохранены; source/tests не менялись. Actual pre-receipt static/lint/scoped-doc/hygiene/strict-preflight/Oracle codes0/0/0/0; после final structured plan report обязательны post-write gates и exact supplied-ID readback.

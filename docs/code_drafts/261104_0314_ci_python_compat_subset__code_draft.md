# Code draft: Одна проверка совместимости Python 3.10 и полный набор Python 3.12

**Date:** 2026-11-04 04:23 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261104_0314_ci_python_compat_subset.md`
**Author role:** Planner
**Status:** draft

---

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261104_0314_ci_python_compat_subset.md",
    "cluster": "quality",
    "targets": [
      {
        "path": "scripts/run_test_shard.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_shards.json",
        "kind": "json"
      },
      {
        "path": "scripts/test_shards.schema.json",
        "kind": "json"
      },
      {
        "path": "scripts/test_run_test_shard.py",
        "kind": "py"
      },
      {
        "path": ".github/workflows/checks.yml",
        "kind": "yml"
      },
      {
        "path": "README.md",
        "kind": "doc"
      },
      {
        "path": "README.ru.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/verify_suite.md",
        "kind": "doc"
      },
      {
        "path": "docs/tools/verify_suite.ru.md",
        "kind": "doc"
      }
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
- Relation: `continued-here`
- Thread ID: `01a1a3fe-aba4-7113-9712-75d1e2a05b74`
- Parent thread ID: `01a193fb-f568-73e3-ab81-a731ce78ee34`
- Session SID: `01a1a3fe-aba4-7113-9712-75d1e2a05b74`
- Launch surface: `manager-collab`
- Captured from: `session-stats`
- Captured at: `2026-11-04T01:21:33Z`

## Purpose
Довести принятый exact-ID compat310 до реализации в существующем runner. Этот draft задаёт bounded контракт и доказательства; product implementation и реальные compatibility runs принадлежат Coder.

## Read set / unchanged consumers
`read_set` — навигация, не второй mutable target inventory:
- `Makefile`, `pyproject.toml`, `requirements-dev.lock`: full routes, Python range и mypy target 3.10 сохраняются.
- `i18n/pairs.json`, `i18n/terms.md`, `scripts/i18n_pairs.py`, `scripts/doc_lint.py`, `scripts/run_doc_lint.sh`: существующие пары и scoped readback; эти файлы не меняются.
- `scripts/test_contract_authority_loader_stream.py`, `scripts/test_contract_authority_shell.py`, `scripts/test_pybin.py`, `scripts/test_contract_authority_snapshot.py`, `scripts/test_consumer_contract.py`: реальные девять candidate IDs и их prerequisite/skip/fixture boundaries; тестовые тела не менять.
- `scripts/consumer_contract.py`, `bin/planveyor`, `scripts/contract_authority_shell_loader.zsh`: реальные unchanged consumers loader/Copier capability, не implementation targets.
- `scripts/plan_status_oracle.py`, `scripts/plan_lint.py`, `docs/adr/004-exact-bundle-truth-and-closeout.md`, `docs/adr/006-doc-lint-scoped-closeout-gate.md`, `docs/playbooks/doc_lint.md`: MAD/exact bundle/scoped-doc authority; frozen implementation immutable.
- Три terminal plans из plan Context links — historical anchor only. Их terminal bytes не менять.
- Golden Path: `N/A (why=bounded CI runner change; no named Golden Path workflow is changed)`.

## Reviewability preflight receipt
- `proof-path class`: `checked-in repo-local helper`
- `mandatory primary lane`: новый `scripts/test_run_test_shard.py` на cheap isolated fixtures; fresh WORK `--check` с canonical discovery и whole partition до любого subset selection; structural `--matrix` с literal 15/meta1 assertions.
- `mandatory non-primary carrier / contextual lane`: WORK `--subset compat310` на обеих existing locked axes 3.10/3.12; настоящий public facade/Copier test без mock substitution; отдельный 3.10 tomli import/parse; workflow selection и scoped docs/i18n readbacks.
- `exact helper path + support files`: `scripts/run_test_shard.py`, `scripts/test_shards.json`, `scripts/test_shards.schema.json`, `scripts/test_run_test_shard.py`.
- `dependent tests / dependent docs / known consumer paths`: все девять targets из Meta; readonly consumers перечислены в Read set. Единственный executable matrix consumer — `.github/workflows/checks.yml`. Input-error rc2 blocking; существующий runner green/red/result/completion/HEAD contract не меняется, outputs остаются derived test evidence.
- `preconditions / seed-discovery`: interpreter paths и physical TMPDIR читаются только из ignored `.tmp/ci_p3_reference/operator_inputs.json`; до nested login shell export PYBIN, env/bin первым PATH, PYTHONDONTWRITEBYTECODE=1. Проверить обе версии, locked dependencies, Git/zsh/rg/make и natural bare python3. Bare login-shell python3 probe требует expected version и os.path.samefile с selected PYBIN; lexical path/symlink spelling не является identity. До каждого compatibility run identity и bare probe emit executable_basename/executable_sha256; same-run readback сравнивает эти поля. Missing prerequisite = STOP без installations/Home edits.
- `reroute rule`: existing-contract failure — owning Coder fix/rerun; новый helper/schema/product contour, исключение обязательной capability или MAD/core drift — Architect. Runtime pin/model/effort drift — root STOP. Принятое v3-name exception не расширять.
- `report continuity`: Coder выполняет `discovery-or-seed` на окончательных WORK bytes. Reviewer/Architect — `receipt-reuse-only`: source inventory/manifest SHA-256, Python identity, ordered IDs, report/events pair, actual child/tee/pipeline rc и elapsed связывают один run. Изменение protected source bytes требует owning rerun; transient pair loss не заменяется silent reseed.
- `observer boundary / mutation truth`: существующий `run_selected` post-discovery `head_before` и final readback той же report/events pair. `notice/success text != mutation truth`; нужны final status, completion_exact, result_successful, HEAD equality и actual child rc0. HEAD drift до existing boundary этим П3 не расширяется.
- `runtime-lineage preflight`: frozen runtime pin, actual Python/PATH, physical TMPDIR и source/manifest bytes перед execution. Stale runtime принадлежит root; implementation проверяется WORK script, а не frozen old runner.
- `retention`: `.tmp/ci_p3_proof/*` = `transient local sanity only`. Sole review и explicit support assets = `durable operator/review evidence`; Reviewer переносит bounded reports/events/source+identity+rc facts с private local paths как <REDACTED> и version/basename/hash вместо raw executable path в literal assets под `docs/code_reviews/assets/261104_0314_ci_python_compat_subset/`. Новые assets называются и hash-bound в review, directory glob не даёт bundle authority.
- `perceptual truth-source split`: structural/repo-backed JSON/events/source preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback = helper gap/follow-up. `N/A (why=no visual proof is required here)`.
- Truth-host fixture matrix: `N/A (why=not a fan-in/readback helper with authoritative process truth hosts; runner accounting and input errors have explicit synthetic cases below)`.

## Targeted changes (by file)
| Target | Контракт и доказательство |
| --- | --- |
| `scripts/run_test_shard.py` | Additive optional subsets reader и mutually-exclusive --subset; полный existing discovery/partition до selection, canonical instances/order/hooks. Единственный emitter matrix/report/planned event; существующие exit/result/HEAD predicates сохранить. |
| `scripts/test_shards.json` | Ровно один compat310 object с непустыми unique exact IDs, исходно девять candidate IDs из plan. Новый whole-module selector test_run_test_shard добавить ровно один раз в s03; остальные selectors/weights/local profiles/baseline не перераспределять. |
| `scripts/test_shards.schema.json` | Optional subsets mapping: те же допустимые имена, strict object с единственным required ids, nonempty unique ID strings; actual membership — runner discovery, не JSON Schema. Existing version 1 и остальные schema fields сохранить. |
| `scripts/test_run_test_shard.py` | Заменить fail-closed path-tracking stub на cheap synthetic regressions из следующей таблицы; без нового checked-in sample corpus или heavy full-shard execution. |
| `.github/workflows/checks.yml` | Consuming matrix row выбирает ровно один --shard/--subset branch; 14 full 3.12 + compat310 3.10, single meta на первой full 3.12. Existing install/pins/runner/timeouts/concurrency/permissions сохраняются. |
| `README.md`, `README.ru.md` | Коротко отделить supported macOS/3.12 environment, technical loader 3.10–3.12, new full3.12/compat3.10 verification contract. Historic hosted facts, mechanics and launch links сохранить. |
| `docs/tools/verify_suite.md`, `docs/tools/verify_suite.ru.md` | Описать exact subset, full partition before selection, matrix configuration vs hosted proof и full-route boundaries. Stamp только existing RU copies после final EN/RU edits. |

## Receipt schema emitter inventory / payload parity
| Family / parser / emitter | Target decision | Regression/readback |
| --- | --- | --- |
| Manifest v1 / load_manifest и partition / checked-in test_shards.json | reader, schema и manifest входят в targets | Malformed/duplicate JSON keys, strict subset shape, empty/duplicate/unknown ID, broken full partition; legacy full/local без subsets проходит. --check валидирует full partition и membership всех configured subset IDs. |
| --matrix / main / checks.yml consumer | runner и workflow входят в targets | --matrix не импортирует tests; exact 15 unique rows, XOR shard/subset, meta exactly1/full3.12; missing compat310 — nonzero, без fallback full3.10. |
| Execution report / run_selected | runner входит в targets | selected_subset = name/null; selected_shards = [] для subset и только full IDs для full/local; planned/started/completed accounting, result/HEAD predicates прежние. |
| Existing planned event / run_selected | runner входит в targets | Additive selected_subset и selected_shards совпадают с report; existing event types planned/started/completed сохранены. |
| Owner-facing generated skeleton/bootstrap/readback emitters | `N/A (why=none for this test-workload schema; no Manager/queue/role emitter consumes these fields)` | Bounded rg found runner as sole Python manifest reader; workflow — literal matrix consumer. |
| One-shot dispatch / scripts/planveyor/role_runtime.zsh | read-only context: `N/A (why=not an owner-facing Manager command change)` | No dispatch/runtime mutation. |

## Synthetic tests — новые proposed method names
Все имена ниже новые. Coder владеет fixture construction и implementation, но обязателен каждый proof outcome.
| Method in new test_run_test_shard.py | Наблюдаемое доказательство |
| --- | --- |
| test_subset_rejects_invalid_shape_ids_and_name | absent requested name, malformed subsets/object/ids/type/unknown fields, empty/duplicate/unknown IDs и duplicate raw JSON key дают nonzero до test execution/report green; CLI mixed modes отвергаются argparse. |
| test_subset_requires_valid_whole_partition | Валидный selected subset не скрывает missing/repeated full assignment, duplicate canonical ID, loader error или unknown full selector; full partition error происходит до test body. |
| test_subset_preserves_instances_order_and_hooks | Два synthetic modules test_alpha.py/test_beta.py с classes AlphaTests/BetaTests; canonical IDs test_alpha.AlphaTests.test_a, test_alpha.AlphaTests.test_b, test_beta.BetaTests.test_c; requested IDs [test_beta.BetaTests.test_c, test_alpha.AlphaTests.test_a]. Исполняются те же objects test_alpha.AlphaTests.test_a, test_beta.BetaTests.test_c в canonical order; test_alpha.AlphaTests.test_b не исполняется; module/class setup/teardown ровно у selected modules/classes. |
| test_subset_cli_report_and_events_share_identity | Real WORK runner subprocess с --root на disposable Git fixture; exact report/event identity, ordered planned/started/completed IDs, no unselected method, existing success predicate и actual rc. |
| test_legacy_full_and_local_modes_without_subsets | Отсутствие optional subsets не ломает --check и full/local execution, selected_subset=null; явный --subset/matrix без compat310 при этом red. |
| test_matrix_and_workflow_selection_contract | Actual manifest matrix15/meta1/XOR/unique и actual YAML selection branch согласованы; schema new field и reader имеют один strict shape; jsonschema package не требуется и не добавляется. |
| test_matrix_is_structural_and_requires_compat310 | Poison synthetic test module не импортируется --matrix; malformed structural input/missing compat310 всё равно red. |
| test_incomplete_started_or_completed_is_red | Synthetic case/runner outcome независимо пропускает start/stop; missing, duplicate либо extra accounting не получает rc0, completion_exact=false. Existing Counter semantics не заменять новым global order predicate. |
| test_interruption_retains_non_green_partial_report | Controlled BaseException после начала: interrupted report с partial started/completed, не green и subprocess nonzero. |
| test_existing_head_boundary_drift_is_red | Контролируемые Git HEAD values до/после existing run_selected boundary различны; result successful/completion exact сами по себе не дают green. |

Fixture root временный под physical TMPDIR вне Git WORK; runner subprocess использует actual WORK script плюс --root fixture и synthetic manifest, local Git identity только fixture. После теста восстановить sys.path/cwd/modules при in-process discovery. Новый production helper или public sample corpus не нужен. Synthetic trace не называется true concurrency proof; concurrency `N/A (why=excluded from accepted P3 scope)`.

## C-P3-1: executable route reconciliation
Accepted source: PLAN_PATH → Decisions (final) → C-P3-1 и root/Architect response. Класс — same-contract reroute; это sync существующего executable carrier, не новый scope cycle.
- Product WORK helper source scripts/i18n_pairs.py остаётся read-only context; его три supported calls исполняет Coder выбранным existing PYBIN. Lifecycle/MAD/provenance/lint helpers сохраняют frozen facade с явным --project; unsupported runtime_py invocation и allowlist/runtime/Home/pin edits запрещены.
- До sources-before, после existing prerequisites: `p3_run stamp-readme "$PYBIN" -B scripts/i18n_pairs.py --project-root . stamp README.ru.md`.
- Там же, до sources-before: `p3_run stamp-verify "$PYBIN" -B scripts/i18n_pairs.py --project-root . stamp docs/tools/verify_suite.ru.md`.
- После existing source/compatibility/tomli/typecheck и scoped-doc steps, непосредственно перед прежним i18n-selected: `p3_run i18n-status "$PYBIN" -B scripts/i18n_pairs.py --project-root . status`.
- Status child0 не закрывает i18n gate: unchanged predicate требует ровно две exact ok rows; stale/error/missing/duplicate row остаётся red. Остальные Commands bytes, all report/event/identity/source assertions, targets, Scope/AC и derived MAD ref сохраняются.
- Начать fresh unique proofdir и исполнить весь agreed envelope на final WORK bytes. Старый stopped envelope дошёл лишь до both-axis prerequisites и stamp-readme child64/tee0/pipeline64. Preliminary synthetic 10/10 был до двух последних assertions; ни этот result, ни старые prerequisites не являются current qualification. Исходные logs/rc не переписывать.
- Initial scaffold/stub wording ниже относится к historical first handoff: Coder уже materialize-ил девять targets и заменил stub десятью synthetic methods. Candidate readiness/final-source qualification остаются false до полного fresh proof и downstream gates; этот sync не выполняет stamps, product tests или compatibility runs.

## Execution / proof order
1. Coder сверяет уже materialized девять targets и unchanged consumers на final WORK bytes; initial stub уже заменён. C-P3-1 возобновляется только полным fresh envelope в новом unique proofdir, не reuse предварительных tests/prerequisites.
2. Использовать literal `## Commands` плана: там единый runnable envelope, cheap suite, source inventories, --check/--matrix, both actual compatibility runs, result/event and scoped i18n assertions. WORK runner/tests и три product i18n calls исполняются выбранным PYBIN из WORK; lifecycle/MAD/provenance/lint идут через frozen facade --project.
3. Exact commands: `"$PYBIN" -B -m unittest discover -s scripts -p test_run_test_shard.py -v`; `"$PYBIN" -B scripts/run_test_shard.py --check`; `"$PYBIN" -B scripts/run_test_shard.py --matrix`; `"$PYBIN" -B scripts/run_test_shard.py --subset compat310 --report "$P3_PROOF/compat-$axis.json"`; `make typecheck`. PYBIN для каждой axis выбирается existing transient launch input; private executable paths в public carriers не записываются.
4. Оба real reports: status green, completion_exact/result_successful true, failures/errors/skipped empty, planned=started=completed in ordered trace, identical ordered IDs на axes, selected_subset compat310/selected_shards [], source/manifest hash agreement, Python identity/actual rc/elapsed. Mandatory skipped capability не квалифицирована; нужен existing same-capability executed ID либо Architect reroute.
5. `tomli` под 3.10 действительно import/parse; настоящий named facade/Copier method действительно executed без mock/skip substitution. Это environment/test proof, не production fallback promise.
6. Before Ready for Review: actual scoped links/basic-hygiene, changed-pair exact status assertions, plan lint, bundle/current target and sole review route. --i18n-strict CLI глобален даже при --root: не выдавать его за scoped pair gate; использовать direct WORK i18n status из C-P3-1 + прежний exact two-pair ok assertion из plan.
7. Root independently owns Sol+GLM exact-candidate/freeze review checkpoint до semantic commit, private copy-only scan и fresh final p0. Normal native Review/Architect sequence остаётся обязательной. Родные роли не придумывают p0, external-model route или scan staging в source index.

## Review route
- Primary artifact: `docs/code_reviews/261104_0314_ci_python_compat_subset.md` — sole live route, до Reviewer PLANNED.
- Lane type: `code review`; native risk и contracts lanes остаются Manager-owned, Planner их не запускает.
- Full review bundle добавляет plan, этот draft, materialized sole review и explicit review assets отдельно от девяти implementation/doc targets.

## Patch sketch (keep it small)
`N/A (why=contract and source pointers above are sufficient; production implementation belongs to Coder)`.

## Critical invariants / traps / bypass paths
- Full partition before subset: structural matrix/schema или valid selected IDs не скрывают corrupt global partition. Legacy missing optional subsets и mandatory CI compat310 — разные proof branches.
- Canonical objects/order/hooks: loadTestsFromName по IDs, sorting by requested list или recreation cases запрещены; synthetic trace ловит эти shortcuts.
- Green accounting: existing result success не закрывает incomplete/interrupted/HEAD drift; actual rc и final same-run report/events обязательны. Global skip semantics не меняются.
- Evidence scope: matrix-only != canonical imports, local green != hosted green, transient logs != durable review. Loader/Copier mandatory capability нельзя заменить mocks.
- Runtime/authority: this test-workload selection не меняет Planveyor process authority; MAD semantic core принадлежит Architect, в Meta только helper-derived ref.

## Assumptions / risks
- Nine initial IDs — candidate, не готовый compatibility report. Bounded replacement существующим ID той же named capability допускается с exact reason; capability removal/new contour требует Architect.
- Missing prerequisite, source/report drift, private-path leak либо иной guard отказ — STOP по owning route; никаких installations/Home/runtime edits.
- `requires-python`, lock, mypy 3.10, local profiles/weights и old terminal plan bytes не меняются.

## Notes for Coder
- PLAN_PATH важнее sketch; plan gaps фиксировать в plan до нового scope/target.
- Предложения изменения target set или semantic contract сначала route upstream; planned first review не означает materialized review.
- Historical first-handoff synthetic target содержал fail-closed path-tracking stub с plan ref и `replace before Ready for Review`. Текущая implementation квалифицирована full agreed envelope в .tmp/ci_p3_proof/coder-20261104T024119Z-25237/; все outcomes и source identity закреплены в PLAN_PATH::Evidence → final WORK qualification. Native/external review, root copy-only scan/final p0 и terminal closure остаются отдельными pending gates.
- Full verify/full14, push/GitHub writes/CI rerun/cancel/runner connection/cleanup и external agents запрещены.

## Review stamps (append-only)
- [2026-11-04 04:59 +0300] (Coder) Nine-target implementation materialized, synthetic stub заменён десятью cheap methods. Preliminary suite 10/10 rc0 предшествует двум последним negative assertions и не является final-source proof. Accepted Commands остановлены на frozen-facade stamp-readme rc64: i18n_pairs.py отсутствует в runtime_py allowlist. C-P3-1 в plan возвращён Architect как same-contract command-route repair; все capability/predicate/target contracts прежние. Real compat reports/source inventory и final qualification пока отсутствуют, canonical runtime не менялся.
- [2026-11-04 04:26 +0300] (Planner) Финализирован executable contract: nine targets, literal read_set, synthetic outcomes, emitter/consumer parity и proof order; фактические Coder compatibility results ещё отсутствуют.
- [2026-11-04 04:42 +0300] (Planner) Второй проход: закрыт proof gap bare login-shell Python identity через expected version/os.path.samefile и captured executable_basename/executable_sha256, включая same-run readback. Проверены syntax и read-only identity probes обеих existing axes; WORK tests/compatibility runner не запускались. Девять targets и derived MAD ref прежние.

- (Planner) Дополнение второго прохода: synthetic fixture shorthand заменён literal module.Class.test_method IDs, соответствующими existing load_manifest grammar; реализации tests не добавлено.

- [2026-11-04 05:27 +0300] (Planner, C-P3-1) Синхронизированы три exact direct WORK i18n calls, их proof order и current implementation/qualification boundary с accepted Decisions/Commands. Девять targets и tagged MAD ref сохранены. Unsupported frozen route не повторялся, old rc64/preliminary logs не менялись; Coder обязан fresh unique full envelope, root Sol+GLM checkpoint/native Review/Architect сохраняются.
- [2026-11-04 05:46 +0300] (Coder) Все девять targets окончательно materialized; fail-closed stub заменён ten-method suite. Полный fresh agreed envelope завершён; canonical результат и все proof outcomes записаны только в PLAN_PATH::Evidence (final WORK qualification / обе axes / executed capability mapping / exact source identity / completion self-check), prefix .tmp/ci_p3_proof/coder-20261104T024119Z-25237/. Target inventory/MAD ref не менялись. Diagnostic source-candidate identity = inventory-file SHA-256 0f16c2bb6ef8449c9974c92c479693e819b0873df35bb8279ab3e7a67514024c; текущая qualification относится к этим final source bytes, не preliminary history. Readiness ограничена review handoff; Manager-dispatched CENSOR, native review, root Sol+GLM exact-candidate checkpoint/copy-only scan/final p0 и Architect terminal closure остаются отдельными gates. Transient evidence требует declared durable reviewer assets; semantic commit этой ролью не выполнялся.

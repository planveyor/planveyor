# Code draft: Переносимые ожидания CI для Python и часового пояса

**Date:** 2026-11-01 02:12 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261101_0052_ci_test_expectations_rebuild.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261101_0052_ci_test_expectations_rebuild.md",
    "cluster": "quality",
    "targets": [
      {
        "path": "scripts/test_planveyor_bare_entrypoints.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_sibling_runbook.py",
        "kind": "py"
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
- Source plan provenance: исходный Architect carrier сохранён в плане; ниже текущие helper-backed факты Planner при финализации существующего draft.
- Relation: `created-here`
- Thread ID: `01a19401-95ad-7f92-a530-cfe67758df66`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-31T23:08:45Z`

## Purpose
Исполнимый контракт для Coder: перенести ровно два проверенных reference blobs и получить свежий ограниченный proof на Python 3.10/3.12. Этот draft финализирован Planner; разрешение следующего шага определяется status и отдельным Manager-dispatched CENSOR. Он не содержит реализации и не закрывает test/review gates заранее.

## Reviewability preflight receipt
- `proof-path class`: `checked-in repo-local helper`; существующие fixtures вызывают настоящие candidate facade/authority, подмена внешнего клиента ограничена тестовым harness.
- `mandatory primary lane`: семь существующих canonical methods на Python 3.10 и 3.12; сохранены mode/subcase semantics и строгие positive/negative identity controls.
- `mandatory non-primary carrier / contextual lane`: `scripts/run_test_shard.py --check`, равенство canonical ID set, неизменность product/runtime/workflow/manifest bytes, принятие alias и отклонение другого файла через `samefile`; для текущих lifecycle документов — exact scoped link check и basic hygiene по Commands.
- `exact helper path + support files`: `scripts/test_contract_authority_support.py`, `scripts/run_test_shard.py`, `scripts/test_shards.json`, `scripts/oss_release_scan.py`, `scripts/run_doc_lint.sh`, `scripts/_pybin.sh`, `scripts/doc_lint.py` — read-only.
- `dependent tests / dependent docs / known consumer paths`: два test targets; `scripts/sibling_runbook.py`, `scripts/planveyor.zsh`, `bin/planveyor`, `docs/tools/verify_suite.md`, `.github/workflows/checks.yml` — contextual read-only.
- `preconditions / seed-discovery`: reference manifest/blob hashes; physical TMPDIR outside Git; selected interpreters; only test child drops ambient `PLANVEYOR_ROOT`; existing sealed AuthorityFixture bootstrap and runtime pins unchanged.
- `reroute rule`: harness/precondition drift исправляется только в declared launch/proof contract; runtime/authority/product drift требует owning stop и не обходится.
- `perceptual truth-source split`: `N/A (why=no UI product changes; assertions and exact bytes are truth sources)`.
- Discovery-or-seed: существующий disposable `AuthorityFixture` создаёт текущий test target/runtime для объявленного method/subcase; историческое lifecycle state не импортируется.
- Receipt-reuse-only: последовательные обращения внутри одного сценария используют ту же fixture и её текущие receipts. Намеренно отсутствующий session/receipt допускается только в уже заданном negative/bootstrap subcase; произвольную потерю continuity нельзя скрывать новым seed. Исторические logs не заменяют receipts этого исполнения.
- Stable identity fields: plan path, текущие target blobs, base/runtime SHA, interpreter identity, test ID/subcase, fixture target/runtime и actual rc.
- Observer boundary: operator не меняет source/status/receipts во время native role work; `notice/success text != mutation truth`. Изменения подтверждаются следующим canonical snapshot/readback того же fixture target либо текущим oracle/docs-closeout для lifecycle плана.
- Runtime-lineage preflight: frozen external runtime остаётся на объявленной базе; `AuthorityFixture` использует текущие candidate source bytes из WORK. SHA/interpreter/fixture mismatch требует разбора launch/harness у owning роли до вывода о product regression; обход runtime pin запрещён.
- Receipt retention class: test logs в `.tmp/` — `transient local sanity only`; итоговые проверенные результаты в plan/review с locators и hashes — `durable operator/review evidence`. Raw sessions и private paths в durable artifacts не копируются.
- Truth-host fixture matrix: `N/A (why=no fan-in/readback helper implementation changes)`.

## Targeted changes (by file)
- `scripts/test_sibling_runbook.py`: final Git blob `4f85f4907f6491e6d81fdba6421e3594379d34ad`, SHA-256 `c465da3a082a129f8c0790c1a2355d64112b8e3e7fc6aeba23aa8cfc7aca4be8`, 73806 bytes. `NativeSiblingCommitPolicyTests.assert_payload_header` требует ровно один абсолютный существующий file `PYBIN` и `samefile(sys.executable)`; остальные header assertions прежние. Existing resolver method содержит positive alias и negative unrelated-file subcases. Все шесть canonical methods и их прежние guards сохраняются.
- `scripts/test_planveyor_bare_entrypoints.py`: final Git blob `7aed97ae06d4cac2a6095391a267fb9d76d39b31`, SHA-256 `6727a7e0cc2d87a0c2c454d2e834d4a701fbf7e33110456265864616e39e0c8c`, 195929 bytes. Existing dashboard method выполняет обе timezone subcases: Europe/Moscow `29.09 05:03`, UTC `29.09 02:03`; `TZ` задаётся только child environment, parent `TZ` сохраняется. Authority validation budgets и timeout/process cleanup остаются прежними.
- Read-only enforcement/consumer surfaces: `scripts/sibling_runbook.py`, `scripts/planveyor.zsh`, `scripts/planveyor/role_runtime.zsh`, `scripts/planveyor/session_init.zsh`, `bin/planveyor`, `scripts/test_contract_authority_support.py`, `scripts/run_test_shard.py`, `scripts/test_shards.json`, `.github/workflows/checks.yml`, `docs/tools/verify_suite.md`. Product, authority, receipt schemas, deadlines, supported-Python policy, manifest weights и dependencies не меняются.
- Новые implementation files и `deleted_paths`: `N/A (why=оба existing targets уже существуют; дополнительные helpers или checked-in synthetic corpus не нужны)`.
- Lifecycle members plan/draft/current review добавляет exact bundle helper отдельно; они не входят в `code_draft_meta.targets`. Review assets: `N/A (why=для этого test-only scope assets не объявлены)`.

## Review route
- `Primary artifact`: `docs/code_reviews/261101_0052_ci_test_expectations_rebuild.md`
- `Lane type`: `code review`
- Target: `BUNDLE=current` с canonical immutable target snapshot от существующего helper; manual SHA и prose summary не заменяют producer. Один review host, current proof обоих non-doc targets; review пока `PLANNED` и создаётся Reviewer.

## Steps
1. До изменения test files выполнить preflight из plan Commands: manifest bytes/hash, selected Python identities/versions, login-shell bare interpreter, physical TMPDIR outside Git, frozen runtime HEAD/clean state и current WORK base. Прочитать оба полных reference diff. Если предусловие не выполняется — owning stop, без HOME/runtime repair и без bypass.
2. До materialization сохранить baseline canonical discovery для обеих axes в transient proof directory по команде ниже. Это только import/discovery, без `.run()`/исполнения tests; require loader.errors=[] и unique IDs. Внутри одной axes файл `before` не перезаписывать после переноса bytes.
3. Только Coder копирует `.tmp/ci_p1_reference/blobs/test_planveyor_bare_entrypoints.py` и `.tmp/ci_p1_reference/blobs/test_sibling_runbook.py` на одноимённые paths в `scripts/`; затем проверяет оба Git blob IDs, bytes и SHA-256. При несовпадении не редактировать утверждённые bytes ради green: вернуть Architect.
4. Сохранить discovery `after` обеих axes тем же кодом, потребовать равенство `before==after`, затем `scripts/run_test_shard.py --check` на обеих axes. Ни один shard и полный suite не исполняются. Manifest/workflow/product helpers остаются byte-identical HEAD; allowlist actual tracked diff = ровно два target paths.
5. Выполнить plan Commands: семь явных canonical IDs × Python 3.10/3.12, каждый отдельным `unittest -v`, без новых skips, без сокращения subcases, без ambient `PLANVEYOR_ROOT` только у test child. Требуется 14 свежих actual rc=0, каждый `Ran 1 test`, `OK`, zero skips/errors/failures/expected failures/unexpected successes. Первый non-green останавливает matrix; исходный log сохраняется, retry после исправления допустим только в owning bounded contour. Исторические logs не учитываются в этих 14 результатах.
6. Результаты с axis/version, ID, log locator/hash, actual rc/count/skips и target blobs записать в plan Evidence; raw output и private paths остаются только `.tmp/`. Затем plan/scoped document lint и strict bundle preflight; Coder закрывает только фактически выполненные AC и передаёт current bundle Reviewer.
7. Reviewer независимо проверяет exact diff, primary/contextual proofs, frozen boundary и current `BUNDLE=current` snapshot, materialize-ит один review host и его mandatory receipts. Architect после accepted review выполняет штатные final lint/exact stage/check/closeout; непосредственно перед actual commit — standalone scanner по plan Commands с explicit external dictionary. Planner не stage-ит и не commit-ит.
8. Manager terminal capture/docs-closeout следуют после terminal commit по существующему lifecycle. Полный внешний p0, prepublication checks, push и hosted receipt выполняет operator отдельно; scoped document green их не отменяет.

## Input/runtime preflight
После plan prelude, до baseline discovery, выполнить этот read-only check. Он не читает dictionary contents; absolute values не выводятся. Несовпадение любого assertion — stop до materialization.

```sh
"$PYBIN" -B - <<'P1INPUT'
import ast, hashlib, json, os, pathlib, subprocess
root = pathlib.Path.cwd().resolve()
inputs = json.loads((root / '.tmp/ci_p1_reference/operator_inputs.json').read_text())
manifest = json.loads((root / '.tmp/ci_p1_reference/manifest.json').read_text())
base = 'e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4'
def git(where, *args):
    return subprocess.check_output(['git', '-C', str(where), *args], text=True).strip()
assert inputs['expected_base'] == base
assert git(root, 'rev-parse', 'HEAD') == base
runtime = pathlib.Path(os.environ['PLANVEYOR_RUNTIME_ROOT']).resolve()
assert runtime.samefile(inputs['runtime_root'])
assert git(runtime, 'rev-parse', 'HEAD') == base
assert not git(runtime, 'status', '--porcelain=v1')
tmp = pathlib.Path(os.environ['TMPDIR'])
assert tmp.is_absolute() and tmp.is_dir() and tmp == tmp.resolve()
assert tmp.samefile(inputs['physical_tmpdir'])
probe = subprocess.run(['git', '-C', str(tmp), 'rev-parse', '--is-inside-work-tree'], capture_output=True, env=dict(os.environ, LC_ALL='C'))
assert probe.returncode != 0 and b'not a git repository' in probe.stderr
pins = {'scripts/test_planveyor_bare_entrypoints.py': '7aed97ae06d4cac2a6095391a267fb9d76d39b31',
        'scripts/test_sibling_runbook.py': '4f85f4907f6491e6d81fdba6421e3594379d34ad'}
assert set(manifest['blobs']) == set(pins)
for rel, oid in pins.items():
    item = manifest['blobs'][rel]
    ref = root / '.tmp/ci_p1_reference' / item['reference_path']
    data = ref.read_bytes()
    assert item['blob_oid'] == oid and git(root, 'hash-object', str(ref)) == oid
    assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
    def ids(raw):
        tree = ast.parse(raw)
        return sorted((c.name, f.name) for c in tree.body if isinstance(c, ast.ClassDef)
                      for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
    assert ids((root / rel).read_bytes()) == ids(data)
assert len(manifest['canonical_method_ids']) == 7
assert len(manifest['canonical_method_ids']) == len(set(manifest['canonical_method_ids']))
print('input_runtime_preflight=valid; two references verified; AST IDs unchanged')
P1INPUT
```

## Canonical discovery continuity
В той же zsh-сессии после prelude из plan Commands определить функцию ниже; вызвать `p1_capture_discovery before` до materialization и `p1_capture_discovery after` после него. Первый `before` каждой axes обязан читать неизменённую базу; `after` требует оба pinned target blobs. Записи transient, не новые authority receipts.

```sh
p1_capture_discovery() {
  local p1_phase="$1" p1_axis p1_python
  for p1_axis in 3.10 3.12; do
  if [ "$p1_axis" = 3.10 ]; then p1_python="$p1_py310"; else p1_python="$PYBIN"; fi
  env -u PLANVEYOR_ROOT PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1     "$p1_python" -B - "$p1_proof_dir" "$p1_axis" "$p1_phase" <<'P1DISCOVERY' || return $?
import json, pathlib, sys, unittest
import run_test_shard
out, axis, phase = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
assert phase in ('before', 'after')
loader = unittest.TestLoader()
suite = loader.discover('scripts', pattern='test_*.py')
assert not loader.errors, 'canonical discovery errors'
ids = sorted(case.id() for case in run_test_shard.flatten(suite))
assert ids and len(ids) == len(set(ids)), 'duplicate/empty canonical IDs'
path = out / ('canonical-' + axis + '-' + phase + '.json')
if phase == 'before':
    assert not path.exists(), 'preserve original before discovery'
else:
    assert ids == json.loads((out / ('canonical-' + axis + '-before.json')).read_text())
path.write_text(json.dumps(ids, ensure_ascii=True) + '\n')
print('canonical_axis=' + axis, 'phase=' + phase, 'tests=' + str(len(ids)))
P1DISCOVERY
  "$p1_python" -B scripts/run_test_shard.py --check || return $?
  done
}
```

Функция возвращает первый failed rc и не продолжает к partition или следующей axes после ошибки discovery. При non-zero invocation не запускать следующие proof steps. Во время `after` существующий baseline не перезаписывается.

## Critical invariants / traps / bypass paths
- Interpreter identity: alias того же файла принимается; другой существующий файл отвергается. Ловушка — заменить identity на basename/existence или убрать positive/negative control; exact final blob и resolver subcases запрещают это.
- Timezone independence: обе точные строки времени проверяются внутри одного existing method; child TZ не меняет parent TZ. Ловушка — прогнать только host timezone; mandatory method уже содержит обе subcases.
- Fixture continuity: каждый NativeSibling method использует текущую disposable lineage, approved prompt body, authority context, runtime/source snapshots и same-session receipts. Намеренно missing-session path разрешён только заданным negative/bootstrap subcase; notice/success text не заменяет следующий canonical snapshot/readback того же entity.
- Synthetic proof carrier: только существующие disposable `AuthorityFixture` и `PublicSiblingTests` temp repos; они изолированы от HOME пользователя. Checked-in samples, historical state и новые helpers не добавляются.
- Command dispatch/receipt-schema/API emitter changes: `N/A (why=все эти surfaces read-only; изменяются только test assertions)`.
- Full concurrency/DB/native UI proof: `N/A (why=такие изменения или claims не входят в test-only scope)`.

## Assumptions / risks
- Python 3.12 — prepared native path; 3.10 — compatibility axis. Оба interpreter filenames и physical temp root уже предоставлены operator в ignored inputs; их значения не переносить в tracked artifacts.
- Harness failure/skip не маскируется изменением source, timeout, fixture guard или внешнего runtime. Семь methods могут занимать десятки минут; существующие deadlines не сокращаются.
- Scoped link/basic-hygiene gates относятся к текущим plan/draft; baseline frozen canonical rc=1 остаётся de-scoped debt. Optional strict code-ref диагностика не заменяет current review или final exact bundle.

## Notes for Coder
- Plan — semantic source of truth; этот draft определяет порядок proof и exact writable targets. Если для реализации нужен третий target или другой pinned blob — stop/reroute Architect, без widening.
- Полная executable matrix, exact scoped document commands, scanner invocation и frozen facade prefix находятся в plan Commands; не создавать новый Manager/init/run и не менять queue.
- `PYBIN` выбран trusted launch environment через PATH. Абсолютные персональные значения и marker dictionary contents не публиковать; fixture-local test paths и `BUNDLE=current` snapshots имеют отдельную retention boundary.
- Plan provenance, current Planner provenance, session attach pointer, transient logs, review proof и terminal capture — разные carriers. N-A ref остаётся derived binding только, semantic core не копируется.

## Review stamps (append-only)
- [2026-11-01 02:12 +0300] (Planner) Seed прочитан и финализирован: exact targets/ref сохранены, placeholders удалены; proof matrix, canonical continuity, reviewability lanes, provenance и единственный review host материализованы. Runtime tests, review, stage и commit этим stamp не объявляются завершёнными.

# Code draft: Инвентаризация native-policy witness — inventory-only результат

**Date:** 2026-11-06 16:40 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261106_1456_ci_native_policy_witness_inventory.md`
**Author role:** Planner
**Status:** draft

---

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261106_1456_ci_native_policy_witness_inventory.md",
    "cluster": "quality",
    "targets": [
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
- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`
- Relation: `continued-here`
- Thread ID: `01a1b0b3-5b5f-7ff2-8462-4c1f98b9f1d4`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-11-06T13:37:31Z`

## Purpose

Единственный writable implementation target — scripts/test_sibling_runbook.py, только существующий строковый class docstring NativeSiblingCommitPolicyTests (BASE строка 625). Coder документирует существующее coverage; новые методы, extraction и helper/report files не создаются. Plan, draft и review входят в final bundle отдельно.

## Reviewability preflight receipt

- `proof-path class`: standard primitives; ast parse/compile в памяти, git show и точное byte slicing, без нового helper/launcher.
- `mandatory primary lane`: после materialization блок Source preservation ниже: BASE SHA, один docstring node, raw prefix/suffix, полный остальной AST, ordered static IDs, все 15 method names в inventory и unchanged mode.
- `mandatory non-primary carrier / contextual lane`: блок Protected artifacts ниже: raw bytes/modes manifest, runner, всего s11 модуля, остальных floor families и producer/guard sources; manual source-bound сверка 15 rows и compound guarantees из plan.
- `exact helper path + support files`: existing scripts/test_sibling_runbook.py, PublicSiblingTests.setUpClass/tearDownClass, NATIVE_POLICY_FIXTURE_ADAPTER/PROGRAM/STATS; protected paths ниже read-only.
- `dependent tests / dependent docs / known consumer paths`: Native assertion inventory и Normative whole-floor catalogue в plan, scripts/test_contract_authority_support.py, README.md, docs/tools/verify_suite.md. Canonical full/compat310 partition прежний, discovery не запускается.
- `preconditions / seed-discovery`: physical checkout HEAD=3a1ca70cd2c170fd2d5acf82cee0299b33bc9dd5; trusted prepared PYBIN/PATH/TMPDIR, bytecode-off, frozen external facade. Existing fixture scenario здесь не запускается, новый seed не создаётся.
- `reroute rule`: неполная inventory, source/HEAD drift, forbidden byte/AST/mode/ID delta или новая helper/target потребность возвращается Architect до widening. Runtime test не легализует executable delta.
- `perceptual truth-source split`: N/A (why=нет UI/image proof).
- Truth-host fixture matrix / receipt-schema emitter inventory: N/A (why=helper/schema/readback behavior не меняется).
- Owner-facing dispatch change: N/A (why=dispatch path unchanged; one-shot/runtime paths только read-only context).
- Stateful existing scenarios: discovery-or-seed создаёт собственный target; downstream receipt-reuse-only удерживает project/runtime/role/session_key/SID. Exact observer boundary — следующий public session-check и тот же receipt bytes/readback; notice/success text != mutation truth. Runtime-lineage preflight остаётся в fixture перед consumer effects. Этот inventory pass scenarios не исполняет.
- Retention: .tmp/ci_p5a1_proof/ — transient local sanity only; durable operator/review evidence — docs/code_reviews/261106_1456_ci_native_policy_witness_inventory.md и его explicit assets. Raw logs/payload не копируются в public docstring.

## Targeted changes (by file)

- scripts/test_sibling_runbook.py: заменить только existing class docstring на source-bound inventory.
- Existing baseline surfaces = весь остальной модуль и protected files ниже; new targets = N/A (why=новых files/helpers нет).
- Imports, module code, class bases/decorators/attributes, function bodies, другие docstrings, hooks/fixtures/deadlines/modes/test IDs и manifest остаются BASE-identical. OLD=NEW для всех 15 exact Native methods.

## Review route

- `Primary artifact`: `docs/code_reviews/261106_1456_ci_native_policy_witness_inventory.md`
- `Lane type`: code review; actual target .py требует этого единственного host при string-only delta.
- Первый executable handoff требует strict bundle --preflight. PLANNED review — отсутствие первого review, не verdict. После dual review требуется strict --check.

## Patch sketch (keep it small)

1. Включить каждый из 15 exact method names из owning inventory рядом с его public path/policy/cold/resume/receipt/refusal/dependency boundary. Existing/planned/executed evidence не смешивать; машинное наличие имён не заменяет source-bound manual review semantics.
2. Compound primary остаётся одним сценарием: 6 Manager events, один init, policy sequence human_explicit,human_explicit,native_existing,human_explicit,human_explicit,native_existing; CMD 1/3/4, TUI 2/5; explicit cycle только у соответствующего CMD. Полный assert_init_event для Manager и Architect включает approved_init_body через настоящий sealed/pinned reader, exact role/policy/runtime header, unique absolute/file/samefile PYBIN, отсутствие PLAN_PATH/PRE_STATUS_LINE/FOLLOWUPS_CAPTURE_CYCLE_ID в init header, exec без resume, аргумент -, stdin=payload, отсутствие MANAGER_CMD header/trailer и exact body.
3. Architect tail: 2 events/1 init, отдельный SID, exec resume SID - через stdin; all_events[:6] == events, final unchanged Manager SID/receipt, собственный Architect receipt и no queue обязательны вместе. Header/receipt/checker helpers и реальные producers не заменяются fake rc/env presence/guessed prompt copy.
4. Все независимые scenarios сохраняют собственные target/receipt/protected inventory и setup/teardown/order/cleanup. Adapter заменяет только внешний client/stats sink: provider-free producer proof не равен live provider readiness.
5. В public docstring не переносить CI durations/run/job IDs, private paths/names, raw payload, fast/full labels или acceleration promises. Inventory-only не означает вечную невозможность будущей обоснованной extraction.
6. Выполнить оба standard proof blocks и plan/scoped documentation gates. Reviewer повторяет на final bytes; implementation/proof execution остаётся Coder/Reviewer-owned.

### Source preservation

Запустить после docstring materialization из physical WORK, с одним trusted spelling "$PYBIN". Блок только читает Git/source и compile в памяти; import/discovery/test execution/cache/helper file отсутствуют. Каждый terminal step сохраняет отдельные child/stdouttee/stderrtee/final rc существующим WORK tee harness. До выполнения PASS не заявляется.

~~~sh
"$PYBIN" -B - <<'PY'
import ast, hashlib, pathlib, re, stat, subprocess, sys
base = "3a1ca70cd2c170fd2d5acf82cee0299b33bc9dd5"
path = pathlib.Path("scripts/test_sibling_runbook.py")
def git(*args):
    return subprocess.check_output(["git", *args])
assert sys.version_info[:2] == (3, 12)
assert git("rev-parse", "HEAD").decode().strip() == base
assert path.is_file() and not path.is_symlink()
old = git("show", base + ":" + path.as_posix())
new = path.read_bytes()
assert hashlib.sha256(old).hexdigest() == "c465da3a082a129f8c0790c1a2355d64112b8e3e7fc6aeba23aa8cfc7aca4be8"
def inspect(raw):
    tree = ast.parse(raw, filename=path.as_posix(), type_comments=True)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NativeSiblingCommitPolicyTests"]
    assert len(classes) == 1
    cls = classes[0]
    doc = cls.body[0]
    assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str)
    lines = raw.splitlines(keepends=True)
    lo = sum(map(len, lines[:doc.lineno - 1])) + doc.col_offset
    hi = sum(map(len, lines[:doc.end_lineno - 1])) + doc.end_col_offset
    methods = [n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    ids = [f"test_sibling_runbook.{c.name}.{n.name}" for c in tree.body if isinstance(c, ast.ClassDef)
           for n in c.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    value = doc.value.value
    del cls.body[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.TypeIgnore):
            node.lineno = 0
    return lo, hi, ast.dump(tree, include_attributes=False), methods, ids, value
a, b = inspect(old), inspect(new)
assert old[:a[0]] == new[:b[0]] and old[a[1]:] == new[b[1]:]
assert a[2:5] == b[2:5] and len(b[3]) == 15
assert old[a[0]:a[1]] != new[b[0]:b[1]], "inventory not materialized"
assert all(re.search(r"\b" + re.escape(name) + r"\b", b[5]) for name in b[3])
mode = int(git("ls-tree", base, "--", path.as_posix()).split()[0], 8) & 0o777
assert stat.S_IMODE(path.stat().st_mode) == mode
compile(new, path.as_posix(), "exec", dont_inherit=True)
assert git("rev-parse", "HEAD").decode().strip() == base
print("source_preservation=PASS native_methods=15 static_ID_order=unchanged")
print("candidate_sha256=" + hashlib.sha256(new).hexdigest())
print("semantic_ast_sha256=" + hashlib.sha256(b[2].encode()).hexdigest())
PY
~~~

AST offsets — UTF-8 byte offsets: span считается по raw bytes, prefix/suffix сравниваются отдельно без whitespace/line-ending normalization. Удаляется только выбранный class-docstring Expr. include_attributes=False исключает source coordinates; TypeIgnore.lineno обнуляется только как coordinate field. Все другие docstrings/nodes/type comments/attributes/hooks/constants остаются в полном сравнении. Ordered static IDs доказывают сохранность source catalogue, не новый discovery 3527/9.

### Protected artifacts

~~~sh
"$PYBIN" -B - <<'PY'
import ast, hashlib, pathlib, re, stat, subprocess
base = "3a1ca70cd2c170fd2d5acf82cee0299b33bc9dd5"
paths = """scripts/test_shards.json scripts/run_test_shard.py
scripts/test_planveyor_init_capture.py scripts/test_contract_authority_shell.py
scripts/test_planveyor_bare_entrypoints.py scripts/test_contract_authority_support.py
bin/planveyor scripts/sibling_runbook.py scripts/planveyor.zsh
scripts/planveyor/role_runtime.zsh scripts/planveyor/session_init.zsh
scripts/contract_authority_bridge.py scripts/contract_authority_context.py
scripts/contract_authority_snapshot.py README.md docs/tools/verify_suite.md
requirements-dev.lock Makefile AGENTS.md""".split()
def git(*args):
    return subprocess.check_output(["git", *args])
assert git("rev-parse", "HEAD").decode().strip() == base
for name in paths:
    p = pathlib.Path(name)
    assert p.is_file() and not p.is_symlink(), name
    raw = p.read_bytes()
    assert raw == git("show", base + ":" + name), name
    mode = int(git("ls-tree", base, "--", name).split()[0], 8) & 0o777
    assert stat.S_IMODE(p.stat().st_mode) == mode, name
    print(name + " sha256=" + hashlib.sha256(raw).hexdigest())
plan = pathlib.Path("docs/plans/261106_1456_ci_native_policy_witness_inventory.md").read_text()
floor = plan.split("## Normative whole-floor catalogue\n", 1)[1].split("\n## ", 1)[0]
ids = re.findall(chr(96) + r"(test_\w+\.\w+\.test_\w+)" + chr(96), floor)
assert len(ids) == len(set(ids)) == 16
for canonical in ids:
    module, cls, method = canonical.split(".")
    tree = ast.parse(pathlib.Path("scripts", module + ".py").read_bytes(), type_comments=True)
    owners = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls]
    assert len(owners) == 1 and sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method for n in owners[0].body) == 1, canonical
assert git("rev-parse", "HEAD").decode().strip() == base
print("protected_artifacts=PASS normative_static_IDs=16 whole_s11_module=unchanged")
PY
~~~

## Critical invariants / traps / bypass paths

- Invariant: единственная delta — разрешённый docstring token. Trap: AST-only proof скрывает comments/format drift; отдельные raw prefix/suffix обязательны.
- Invariant: producers/negatives/15 exact Native IDs сохранены. Trap: список имён/fake rc не доказывает init/body/receipt; source-bound manual review обоих init helpers, Manager prefix и independent refusals обязателен.
- Invariant: весь s11, нормативные 16 IDs, hooks, manifest/runner и guards/fixtures unchanged. Trap: --matrix/unchanged manifest не являются новым exact-once/runtime/hosted proof.
- Runtime/browser proof: N/A (why=executable behavior не меняется и runtime scenarios в этом slice не исполняются).

## Assumptions / risks

- Prepared macOS/Python3.12 environment уже объявлено проектом; direct commands используют "$PYBIN", без personal absolute paths.
- F25 broad canonical doc-lint debt не закрывается; scoped plan/draft green не broad canonical green.
- Saved whole-method costs/hash/HEAD pairs — qualified plan context, не новые measurements или fast-floor budget.
- Противоречие требует Architect reroute до widening, без silent target changes.

## Notes for Coder

Plan — semantic source of truth; wording docstring выбирает Coder внутри этого контракта. Единственный target не расширяется ради seed/proof helper. Source/protected blocks — будущая Coder/Reviewer verification; Planner их не исполнял и PASS не заявляет.

После dual review/Architect checks остановиться с EXACT UNSTAGED candidate/base/tree/list/bytes/hashes/modes/helper identity/test+review refs для Root. До independent physical-copy exact scan ACCEPT запрещены stage/semantic commit/Done/closeout; scanner WORK index не использует. После scan — обычный уже разрешённый local native close/commit, затем только Root postcommit p0. P0 не precommit prerequisite; publication/cleanup отдельно.

## Review stamps (append-only)

- [2026-11-06 16:43] (Planner) Exact target/ref/review route и runnable standard proof contract финализированы; implementation ещё не начата.

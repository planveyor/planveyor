# Code draft: Сократить повторные проверки закрытия при коррекции формата

**Date:** 2026-11-05 02:50 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md",
    "cluster": "quality",
    "targets": [
      {"path": "scripts/test_contract_authority_shell.py", "kind": "py"}
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
- Source plan provenance: `docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md#Plan-provenance--session-context`
- Relation: `continued-here`
- Thread ID: `01a1a8c9-2349-70d3-96c5-e79c78df59f9`
- Parent thread ID: `01a193fb-f568-73e3-ab81-a731ce78ee34`
- Session SID: `01a1a8c9-2349-70d3-96c5-e79c78df59f9`
- Launch surface: `manager-collab`
- Captured from: `manual-owner`
- Captured at: `2026-11-05T00:09:50Z`

Источник — fresh `planveyor_plan_provenance_context` с explicit actual SID/thread/parent, не старый attach-pointer. Helper возвращает carrier; current plan/draft materialized стандартным file edit из этого exact readback. Первичный render-only вызов сам файл не менял. Semantic MAD core остаётся в plan у Architect; seed helper скопировал только validated derived ref, initial oracle подтвердил `not_applicable/ok`. Текущий Coder continuation restamp использует supported context/render с actual Coder identity; предыдущий Planner carrier сохранён в Evidence плана.

## Purpose
Передать Coder одно изменение условия в существующем методе и сохранить все остальные statements/assertions.
Первый executable handoff требует strict read-only preflight; review и terminal materialization остаются отдельными gates.

## Targeted changes (by file)
- `scripts/test_contract_authority_shell.py::ContractAuthorityShellIntegrationTests.test_public_candidate_format_correction_all_roles_and_bounded_outcomes`: прежний цикл двух retryable close-команд выполняется только при `second_malformed=False`, в прежней позиции после сохранения `head/index` и до `reserved = public(...)`. Сами command arrays и весь assertion body цикла неизменны.
- Остальные statements/assertions этого метода, другие методы, fixtures и helpers сохраняются без изменений. Новый test ID, helper или sample corpus не создаётся.
- Plan, этот draft, sole review и его explicit assets — отдельные lifecycle members, не `targets`.

## Read set / unchanged consumers
- База WORK: `2aa0d5000ca49bd4ddecd030aa5728cab6769715`, tree `a4dbdb66cf018579a8b81b508ca48e4e949a1cf3`; initial test SHA-256 `6ecc69ba0dd5f3dc87acfc762ca19bf1fd6b21c06e2f67489976963a7aa31465`.
- `scripts/test_contract_authority_shell.py`: весь selected method, `_run_public_pi_command`, `_prepare_public_pi_composition_fixture`, existing runtime hash assertions.
- `scripts/test_contract_authority_support.py::AuthorityFixture`: существующие disposable repos/runtime и synthetic setup; `scripts/sibling_closeout.py::_correction_outcome`: read-only retryable/blocked consumer. Их изменения запрещены.
- `scripts/run_test_shard.py`: read-only discovery/partition/matrix reader; initial SHA-256 `aef13a07ba03937d2d4fa2dfdd17a9aea727ee5a79cee63fdfc71a99d3c29bb1`.
- `scripts/test_shards.json`: SHA-256 `fb4b4327dcb8ed34b410495cad6b5d354af847a705b29ce7b1f0a259f0690214`; selected ID остаётся в s02, full partition = 3527, s02 = 215, `compat310` = прежние девять IDs. `--matrix` = прежние 14 rows 3.12 + одна 3.10.
- `.github/workflows/checks.yml`, runtime/config, 105 min и 120 s — read-only; без waiver, skip, retry или выполнения all14/hosted.
- `docs/adr/004-exact-bundle-truth-and-closeout.md`, `docs/adr/006-doc-lint-scoped-closeout-gate.md`, `docs/playbooks/doc_lint.md`: bundle/scoped-doc canon. Lifecycle helpers берутся только из frozen external facade.
- Shared schema emitter inventory, public API/payload parity, one-shot dispatch и truth-host fixture matrix: `N/A (why=test-only condition; no schema, emitter, command or fan-in helper change)`.
- Golden Path: `N/A (why=bounded test change; no named workflow is changed)`.

## Reviewability preflight receipt
- `proof-path class`: `checked-in repo-local helper`.
- `mandatory primary lane`: один полный selected method на selected Python 3.12, actual child rc=0, `Ran 1 test`, `OK`, zero skips/errors/failures/expected failures/unexpected successes. Future P2 rows = 107: Architect 10/10, Coder 11/11, Planner 12/12, Reviewer 28/13 по False/True; итоги 61/46. Eight `blocked-close` только False, four `consumed-close` только True. Таблица — ожидание после Coder change, не результат текущего Planner.
- `mandatory non-primary carrier / contextual lane`: exact source diff сохраняемых statements/assertions и всех восьми roots; fresh `--check` 3527 exact-once и `--matrix` 15 rows; manifest/runner/workflow bytes неизменны. Остальные test methods, вся s02, compat310 execution, all14 и hosted не запускаются.
- `exact helper path + support files`: selected test/helpers, `scripts/test_contract_authority_support.py::AuthorityFixture`, `scripts/sibling_closeout.py::_correction_outcome`, runner и manifest из read set; единственный writable implementation path указан в Meta.
- `dependent tests / dependent docs / known consumer paths`: selected canonical ID в s02; existing compat310/matrix/workflow — unchanged contextual consumers; plan/draft/sole code review — lifecycle docs. Shared public helper semantics и новые public docs targets отсутствуют.
- `preconditions / seed-discovery`: тот же trusted selected launch env перед natural login, bare `python3` 3.12 samefile(`PYBIN`), existing physical TMPDIR вне Git, pinned WORK/runtime identity. `discovery-or-seed` выполняет только existing targeted harness; один attested disposable runtime и восемь разных consumer Git roots.
- `receipt-reuse-only`: downstream шаги внутри каждого scenario используют те же `plan_ref`, `capture_cycle_id`, outer role, `reservation_id`, leaf/aggregate bytes, candidate/runtime SHA-256 и runtime commit. Повторный reserve и replay отказывают без изменения исходных bytes; ручной reseed/retry запрещён.
- `mutation truth / observer boundary`: retryable readback непосредственно до reserve; consumed state после единственной попытки; canonical aggregate/leaf bytes, HEAD/index и runtime hashes являются truth. Reviewer False сохраняет checkpoint, четыре prepare/submit/bind, freeze и final `(completed,no_op)`. `notice/success text != mutation truth`; это sequential reservation/replay proof, не полный concurrency proof.
- `runtime-lineage preflight`: source pins перед запуском, existing runtime HEAD/source hash assertions в harness; stale runtime возвращается runtime-owning triage до product reopen. Frozen lifecycle runtime не подменяет WORK product proof.
- `reroute rule`: timeout, red mandatory lane, неверный count/identity, source drift или новый target останавливают handoff и возвращаются owning triage; исходные nonterminal timeout/partial streams/prior trace/re-raise сохраняются, deadline не расширяется.
- `retention class`: argv/stdout/stderr/status/timing и expanded local paths в unique `.tmp/ci_p4v_proof/` = `transient local sanity only`. Reviewer делает bounded redacted phase summary в sole review и его explicit durable assets; private raw argv и dictionary туда не переносятся.
- `perceptual truth-source split`: `N/A (why=no visual/native proof; structured source/unittest/JSON carriers suffice)`.

## Patch sketch (keep it small)
1. Сохранить full baseline метода и test-file identity в transient source snapshot.
2. Ограничить ровно existing retryable pair False-ветвью на прежней позиции до reserve; необходимый отступ входит в это изменение.
3. Проверить exact diff: тела commands/assertions пары сохранены; все остальные statements/assertions и остальные методы прежние.
4. Выполнить полный метод и contextual proof ниже. При non-green сохранить actual evidence и остановиться.

## Proof commands / recording prelude
Команды выполняются из physical WORK в уже выбранном trusted env, переданном до natural login; outer tool использует `login:false`. Ни HOME/profile, ни runtime/account/environment installation не меняются. Во всех test/lifecycle commands используется `"$PYBIN"`; bare `python3` ниже — отдельный обязательный probe inheritance, не вторая test axis. Значения private launch paths уже даны Manager и остаются только в transient logs.

Prelude копируется один раз на новый owning proof run. Функция только записывает argv и streams; она не принимает semantic verdict и не является новым product/review helper. При каждом ненулевом final rc следующий шаг останавливается.

```zsh
: "${PYBIN:?selected Python required}"
: "${PLANVEYOR_RUNTIME_ROOT:?frozen runtime required}"
: "${TMPDIR:?existing physical temp required}"
export PYBIN PLANVEYOR_RUNTIME_ROOT TMPDIR PYTHONDONTWRITEBYTECODE=1
p4v_plan=docs/plans/261105_0005_ci_reduce_duplicate_close_checks.md
p4v_draft=docs/code_drafts/261105_0005_ci_reduce_duplicate_close_checks__code_draft.md
p4v_proof=".tmp/ci_p4v_proof/coder-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$p4v_proof" || return $?
p4v_record() {
  local label="$1"; shift
  local slot="$p4v_proof/$label"
  mkdir "$slot" || return $?
  printf '%s\0' "$@" > "$slot/argv.nul" || return $?
  "$@" > "$slot/stdout.log" 2> "$slot/stderr.log"
  local child_rc=$?
  tee "$slot/stdout.tee.log" < "$slot/stdout.log"
  local stdout_tee_rc=$?
  tee "$slot/stderr.tee.log" < "$slot/stderr.log" >&2
  local stderr_tee_rc=$?
  local final_rc=$child_rc
  if (( final_rc == 0 && (stdout_tee_rc != 0 || stderr_tee_rc != 0) )); then final_rc=1; fi
  printf 'child_rc=%s\nstdout_tee_rc=%s\nstderr_tee_rc=%s\nfinal_rc=%s\n' "$child_rc" "$stdout_tee_rc" "$stderr_tee_rc" "$final_rc" > "$slot/status.txt" || return $?
  return "$final_rc"
}
```

После source change Coder запускает ровно один метод. Его внутренние disposable init/close branches допустимы только как existing harness; отдельные live init/profile/close commands запрещены.

```zsh
p4v_record env python3 -B -c 'import json,os,pathlib,subprocess,sys; t=pathlib.Path(os.environ["TMPDIR"]); r=subprocess.run(["git","-C",str(t),"rev-parse","--show-toplevel"],capture_output=True,text=True,env=dict(os.environ,LC_ALL="C")); assert sys.version_info[:2]==(3,12) and pathlib.Path(sys.executable).samefile(os.environ["PYBIN"]); assert t.is_dir() and t==t.resolve() and r.returncode==128 and not r.stdout and "not a git repository" in r.stderr; print(json.dumps({"python":sys.version,"samefile":True,"physical_tmp_outside_git":True}))' || return $?
p4v_identity_code='import hashlib,json,os,pathlib,platform,subprocess,sys; files=("scripts/test_contract_authority_shell.py","scripts/test_contract_authority_support.py","scripts/sibling_closeout.py","scripts/run_test_shard.py","scripts/test_shards.json",".github/workflows/checks.yml"); head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(); runtime=subprocess.check_output(["git","-C",os.environ["PLANVEYOR_RUNTIME_ROOT"],"rev-parse","HEAD"],text=True).strip(); assert head=="2aa0d5000ca49bd4ddecd030aa5728cab6769715" and runtime=="e8d628c4a5114eb92ebaeaa52b2ff642d28a7be4"; print(json.dumps({"git_head":head,"frozen_runtime":runtime,"python":sys.version,"executable":sys.executable,"os":platform.platform(),"execution_surface":"local","runner":"UNKNOWN","image":"UNKNOWN","sha256":{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in files}},sort_keys=True))'
p4v_record source-before "$PYBIN" -B -c "$p4v_identity_code" || return $?
p4v_record targeted "$PYBIN" -B -m unittest discover -s scripts -p test_contract_authority_shell.py -k test_public_candidate_format_correction_all_roles_and_bounded_outcomes -v || return $?
p4v_record source-after "$PYBIN" -B -c "$p4v_identity_code" || return $?
p4v_record source-continuity cmp "$p4v_proof/source-before/stdout.log" "$p4v_proof/source-after/stdout.log" || return $?
p4v_record partition "$PYBIN" -B scripts/run_test_shard.py --check || return $?
p4v_record matrix "$PYBIN" -B scripts/run_test_shard.py --matrix || return $?
p4v_record unchanged git diff --exit-code 2aa0d5000ca49bd4ddecd030aa5728cab6769715 -- scripts/test_contract_authority_support.py scripts/sibling_closeout.py scripts/run_test_shard.py scripts/test_shards.json .github/workflows/checks.yml || return $?
p4v_record target-diff git diff 2aa0d5000ca49bd4ddecd030aa5728cab6769715 -- scripts/test_contract_authority_shell.py || return $?
```

P2 readback ниже читает завершённый run; actual expected negative public rc остаётся в rows. Counter total или unittest `OK` по отдельности недостаточны.

```zsh
p4v_record timing-readback "$PYBIN" -B - "$p4v_proof" <<'PY' || return $?
from collections import Counter, defaultdict
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
out = (root/"targeted/stdout.log").read_text()
err = (root/"targeted/stderr.log").read_text()
assert re.search(r"Ran 1 test in ", err) and re.search(r"(?m)^OK$", err)
assert not re.search(r"(?i)skipped|expected failures|unexpected successes|FAILED|ERROR", err)
all_rows = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
assert not any(r.get("schema") == "public_pi_command_timeout.v1" for r in all_rows)
rows = [r for r in all_rows if r.get("schema") == "public_pi_command_timing.v1"]
expected = {("Architect",False):10, ("Architect",True):10, ("Coder",False):11, ("Coder",True):11, ("Planner",False):12, ("Planner",True):12, ("Reviewer",False):28, ("Reviewer",True):13}
groups, roots = Counter(), defaultdict(set)
labels = Counter()
for row in rows:
    match = re.match(r"second_malformed=(False|True);", row["subcase"])
    assert match and row["argv"][1] == "--project"
    key = (row["role"], match.group(1) == "True")
    groups[key] += 1
    roots[key].add(row["argv"][2])
    labels[(key, row["label"])] += 1
    assert type(row["actual_rc"]) is int
assert len(rows) == 107 and groups == Counter(expected)
assert all(len(v) == 1 for v in roots.values())
assert len(set().union(*roots.values())) == 8
for role in ("Architect","Coder","Planner","Reviewer"):
    assert labels[((role,False),"blocked-close")] == 2
    assert labels[((role,True),"blocked-close")] == 0
    assert labels[((role,True),"consumed-close")] == 1
    assert labels[((role,False),"consumed-close")] == 0
assert json.loads((root/"partition/stdout.log").read_text())["canonical_tests"] == 3527
matrix = json.loads((root/"matrix/stdout.log").read_text())["include"]
assert len(matrix) == 15 and sum(r.get("subset") == "compat310" for r in matrix) == 1
print("P2: 107 rows; eight distinct scenario roots; False=61/True=46; blocked=8/consumed=4")
PY
```

Recording сохраняет readback stdout/stderr и actual rc; этот результат не заменяет test rc. Byte-identical manifest в `unchanged` одновременно удерживает все девять compat310 IDs и s02 membership. Source proof — `target-diff` одного метода плюс before/after identity equality; Reviewer проверяет все прежние statements/assertions непосредственно по diff.

## Lifecycle gates / Root pause
Команды ниже — только read-only validation. Первый strict `--preflight` проходит Planner до handoff; `--check` требуется после materialized review. Planned review absence на раннем preflight допустима только как canonical `PLANNED`, не как пройденное ревью.

```zsh
p4v_record plan-lint "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py "$p4v_plan" || return $?
p4v_record preflight "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight "$p4v_plan" || return $?
p4v_record scoped-links bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --product-root "$PWD" --root "$p4v_plan" --root "$p4v_draft" || return $?
p4v_record scoped-hygiene bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --product-root "$PWD" --check-basic-hygiene --root "$p4v_plan" --root "$p4v_draft" || return $?
p4v_record whitespace git diff --check -- scripts/test_contract_authority_shell.py "$p4v_plan" "$p4v_draft" || return $?
```

Reviewer добавляет materialized sole review как ещё один literal `--root` в оба scoped-doc gates; current selected risk support assets проходят canonical hash/schema validation. После review:
`"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --check "$p4v_plan"`.
Для untracked plan/draft дополнительный whitespace readback — `git diff --no-index --check /dev/null "$p4v_plan"` и `git diff --no-index --check /dev/null "$p4v_draft"`: rc1 допустим только как обычный different-file результат при пустых whitespace diagnostics; actual rc сохраняется.

До ЛЮБОГО staging для коммита/exact `--stage`, actual Done, semantic commit или closeout — обязательная остановка. Architect после Coder/dual Review/Architect checks отдаёт Root exact UNSTAGED candidate: base HEAD/tree, все implementation/lifecycle/review/support members, bytes/SHA-256/Git и Unix modes, frozen helper identity и proof refs. Root проверяет private names на независимой копии и даёт scoped решение. Решения пока нет; `native_existing` паузу не обходит. В этом draft нет stage/commit/closeout command. Dictionary не открывать/не копировать; publish, p0 и cleanup сейчас не запускать. Postcommit p0 остаётся отдельным поздним шагом после разрешённой materialization.

## Critical invariants / traps / bypass paths
- Eight-root coverage: outer `row.role` и branch/root доказывают сценарий; prefix collector `--role` не является outer identity.
- Retryable False и consumed True — разные observer boundaries; нельзя убрать True consumed-close или перенести pair после reserve.
- Initial malformed/admission, reserve/second refusal, byte preservation, обе correction outcomes, replay, HEAD/index/runtime и Reviewer completed/no_op остаются исходными.
- `N/A (why=no UI/layout/access runtime surface change)`.

## Assumptions / risks
- Удаление восьми повторов не обещает точного ускорения и не снимает timeout risk оставшегося False вызова.
- Fresh partition/matrix доказывают discovery/structure, не исполнение all14/hosted и не product acceptance.
- Source/authority drift — owning reroute; расширение target/helper/fixture scope не разрешено.

## Notes for Coder
Plan — главный контракт. При конфликте сохранить evidence и вернуть owning gap. Реализация принадлежит Coder; Planner этот test не менял и не исполнял.
Приёмка implementation review использует один `BUNDLE=current` по target; plan/draft/review/support входят в final exact bundle отдельно.

## Review route
- `Primary artifact`: `docs/code_reviews/261105_0005_ci_reduce_duplicate_close_checks.md` — PLANNED.
- `Lane type`: `code review`; dual lanes Manager-owned, implementation target один.

## Review stamps (append-only)
- [2026-11-05 02:50 +0300] (Planner) Draft финализирован: Targets/Steps/proof commands и Root pause синхронизированы с plan; template placeholders удалены. Product/targeted proof остаётся Coder-owned.
- [2026-11-05 03:01 +0300] (Planner, post-handoff verification) Current plan/draft provenance синхронизирован из fresh helper output; render-only stamp не выдан за самостоятельный file writer. Recording status write теперь сохраняет non-green, TMPDIR probe проверяет ожидаемую причину rc128. One-target implementation contract, expected 107/61/46 и Root pause сохранены.
- [2026-11-05 03:52 +0300] (Coder) Current continuation provenance materialized из supported helper render с actual Coder identity; semantic MAD/ref, один exact target, read set, commands и sole planned review route сохранены. Все execution results и proof refs находятся только в Evidence плана. Root pause перед staging/Done/semantic commit/closeout остаётся обязательной.

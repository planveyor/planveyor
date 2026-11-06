# Code draft: отдельный функциональный s11 witness для control markers и lock reentry

**Date:** 2026-11-06 22:19 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261106_2051_ci_s11_functional_witness.md`
**Author role:** Planner
**Status:** draft

---

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261106_2051_ci_s11_functional_witness.md",
    "cluster": "quality",
    "targets": [
      {
        "path": "scripts/test_planveyor_init_capture.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_shards.json",
        "kind": "json"
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
- Captured at: `2026-11-06T19:18:12Z`

## Purpose / exact targets

Только scripts/test_planveyor_init_capture.py (py): один новый exact F test_role_run_control_markers_functional_safety_witness; scripts/test_shards.json (json): одна exact-ID строка existing s11 selector. deleted_paths=[]; plan/draft/review — отдельные lifecycle bundle members. Old timing method и все existing dependencies untouched.

## Reviewability preflight receipt

- proof-path class: checked-in repo-local helper — existing InitCaptureTests/real role-run/OS lock producers; standard static primitives и stdlib exact-ID unittest. Новых helper/launcher families нет.
- mandatory primary lane: F, пять independent fresh legacy_complete fixtures; own full identity before/after каждой; реальные nofollow refusals, successful child receipts, foreign owner/contender, missing-parent→retry и interrupt→SAME-lock reacquire. Whole F/native duration и отдельный process wall только prepared3.12, после code gates и полученного scoped Root release.
- mandatory non-primary carrier / contextual lane: raw additive source/span/AST/ordered OLD IDs; one-row manifest preservation, exact11 protected paths/modes ниже; full canonical --check prepared3.10+3.12, compat310 exactly9. Static/import proof не F runtime PASS.
- exact helper path + support files: scripts/test_planveyor_init_capture.py → _prepare_repo(...,runtime_mode="legacy_complete"), _complete_runtime_manifest, _assert_legacy_complete_runtime_identity, _run, _write_runtime_plan, existing fake-client/regular shim. scripts/planveyor/role_runtime.zsh → planveyor_role_run, _planveyor_role_run_lock_holder, _planveyor_role_run_lock_release, _planveyor_role_run_publish_control_marker, _planveyor_role_run_close_transaction. Existing helper bytes read-only.
- dependent tests / dependent docs / known consumer paths: original s11 и 16 OLD floor IDs в plan, scripts/test_shards.json / scripts/run_test_shard.py / docs/tools/verify_suite.md. Changed Manager dispatch/schema/API/fan-in N/A (why=только additive test/selector).
- preconditions / seed-discovery: BASE d2e720e182ca952dd24b9c616ea6b2eae05fd7b2, trusted prepared3.12 и existing planveyor-ci310, Root-bound physical ignored task TMPDIR экспортирован ДО любого Python/nested login/imports. Каждую новую fixture создаёт existing harness внутри F.
- reroute rule: missing harness/identity drift, old-byte/helper/production change, новый target/helper family → owning Architect/Root до widening. Не выбирать fallback TMPDIR/interpreter/receipt, не снимать guards и не повторять original/A-B/PartB.
- perceptual truth-source split: source/receipt/ready/readback JSON и raw bytes/modes; UI/OCR N/A (why=no UI).
- discovery-or-seed: fresh fixture каждой строки; receipt-reuse-only: downstream reads только того же fixture/run/holder. Stable identity: physical project/runtime roots+complete manifest; role/session_key/runner_id/sid; run_id/receipt_path/stdout_path/stderr_path; literal lock_path/parent_pid/holder_pid/ready state+reason. Exact observer boundary — после real finalizer/release и bounded death/reap; notice/success text != mutation truth.
- runtime-lineage preflight: existing full identity before/after КАЖДОЙ fixture с ЕЁ expected manifest; legacy state, project identity, regular shim и closure bytes/modes. Mutable runtime/receipt между fixtures не делится.
- retention: .tmp/ci_s11_functional_proof/ и task TMPDIR — transient raw sanity/execution proof; durable review — docs/code_reviews/261106_2051_ci_s11_functional_witness.md с exact source/test/measurement refs. Новых standalone report/helper targets нет.
- truth-host fixture matrix / emitter inventory: N/A (why=validator/parser/producer contract не меняется).

## Targeted changes / insertion layout

- scripts/test_planveyor_init_capture.py: один contiguous F insertion непосредственно перед original control-marker method. Optional F-only support — nested functions ВНУТРИ F, без новых class members/imports/old helper edits. Выбранный layout обеспечивает executable raw preservation; Coder сохраняет ownership реализации.
- scripts/test_shards.json: одна новая строка exact F ID с comma непосредственно перед original s11 exact ID, в existing s11 selector module=test_planveyor_init_capture. Old bytes/order/assignment/compat310/runner/events/weights/deadlines unchanged.
- Existing baseline surfaces: весь остальной модуль, original span3812–4230 и все old class members/helpers/hooks, fake runner/writers/readers/fixtures, protected files ниже. New files/seed N/A (why=оба targets существуют).

## Review route

- Primary artifact: docs/code_reviews/261106_2051_ci_s11_functional_witness.md
- Lane type: code review, обе native lanes на actual final source/bundle/test snapshot.
- First executable handoff strict --preflight; после review strict --check. PLANNED review не verdict. Origin plan не implementation target.

## Patch sketch / five fixture contract

1. Два nofollow сценария — ДВЕ fresh TemporaryDirectory fixtures. Own legacy identity/manifest до и после; existing plan/session setup; real planveyor_role_run planner --json. Fault только в fixture planveyor_planner role-wrapper boundary, production functions не monkeypatch-ить.
2. transaction.done → outer126/blocked/transaction_done_publication_failed; lock.release → outer126/blocked/lock_release_failed. В каждой sentinel unchanged, marker actual symlink, actual persisted child receipt schema_version=role_execution_receipt.v1/state=success/exit_code=0 и identity именно этого run. Generic nonzero/existence не достаточны.
3. Foreign owner/contender fixture: first real holder acquired/ok, actual parent_pid/holder_pid из ready и подтверждённая жизнь до contender; symlink owner release не regular owned0600 marker. Distinct real contender на ТОМ ЖЕ lock_path → contended/role_run_lock_contended. Real release → rc1, _PLANVEYOR_ROLE_RUN_LOCK_RELEASE_JSON ok=false/reason=lock_release_failed; sentinel unchanged; holder_cleanup_failed=false, owner/holder actual death+reap. Не скрывать refusal через ||true вместо assertions.
4. Missing-parent fixture: first real role child удаляет только СВОЙ current output parent; outer126/blocked/lock_release_failed. ПЕРВУЮ persisted receipt открыть ДО retry: actual schema/state=success/exit0, role=planner/session_key=planner/runner_id=codex, current sid/target_plan/run_id/receipt_path. Retry real role-run в ТОМ ЖЕ project/session/lock context → rc0/state=success/readback_state=ok; его actual persisted receipt success/exit0 и current identity. run_id/receipt_path первого и второго различаются; fabricated/reused JSON запрещён.
5. Interrupt fixture: first actual ready acquired/ok и literal lock_path/holder PID; terminate caller, bounded communicate/death/reap. Только после смерти первого второй real holder получает ТОТ ЖЕ lock_path → acquired/ok; real release/reap без survivor. Новый lock в другой fixture не proof reentry.
6. В каждой из пяти fixtures own complete runtime copy и before/after identity с expected manifest. Existing fixture-derived child TMPDIR внутри новой owned fixture штатен; outer tempfile root устанавливается до module imports. Между fixtures/methods state не делится.
7. Finite fail-closed liveness: readiness500×0.01s, caller communicate/holder-death bounds5s, unchanged _run default60s и production release bounds. Exhausted/missing/malformed/wrong-identity ready/death check = FAIL до следующего шага, не skip/продолжение. Это liveness guards, не новые performance assertions.
8. F не вызывает _monotonic_timestamp_writer, _read_monotonic_timestamp, report_timing, timing sidecars/observer hooks и не добавляет elapsed<5 assertions. time.monotonic допустим для конечных readiness/death ожиданий. Original четыре5s/writers/outer checks сохраняются raw.
9. Static/source proof, functional proof и local wall — разные claims. Original s11/A-B budget SPENT; original runs/сравнения/F3.10/full3.10suite/full suite/shards/CI/PartB запрещены.

Actual ready schema для fixtures3/5: state/reason/holder_pid/parent_pid; lock_path producer не emit-ит. Проверить current parent/holder identity по этим реальным полям, SAME lock — по одному literal lock_path в аргументах двух real holder invocations внутри той же fixture. Не читать/фабриковать ready["lock_path"] и не добавлять schema/runtime edits ради такой проверки.

## Trusted launch / TMPDIR before ANY Python

S11_PY312 и S11_PY310 — explicit trusted per-launch bindings уже prepared installations; current3.12 приходит как PYBIN, existing3.10=planveyor-ci310. Manager передаёт эти известные bindings; auto env/install/activation/wrapper не вводится. Sanitized paths/modes и raw executable bindings находятся в transient .tmp/ci_s11_functional_proof/planner_primary_20261106T191737Z/input_bindings/stdout; log не выбирает executable и не является project cache.

КАЖДЫЙ fresh exec shell первым выполняет exports ниже, включая static/source/helper/measurement calls. Это уже созданный current task-owned physical ignored root; не создавать замену/system default/старую measurement copy.

~~~zsh
export S11_TASK_TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE"
export TMPDIR="$S11_TASK_TMPDIR" PYTHONDONTWRITEBYTECODE=1
[[ -n "$PYBIN" && -n "$S11_PY310" ]] || exit 2
[[ -n "$S11_PY312" ]] || export S11_PY312="$PYBIN"
export PATH="$(dirname "$PYBIN"):$PATH" GIT_OPTIONAL_LOCKS=0
[[ -d "$TMPDIR" && -x "$S11_PY312" && -x "$S11_PY310" ]] || exit 2
~~~

Каждую executable строку запускать отдельно существующим native tee capture: actual child/stdouttee/stderrtee/final rc, stdout/stderr raw logs и fresh paths. Не маскировать F rc следующим command/pipe. JSON parse только после terminal0; nonzero сохраняется честно. Normal teardown только СОБСТВЕННЫХ новых fixtures остаётся штатным; old tmp/receipt/housekeeping cleanup запрещён.

### Fresh launch evidence (до imports; повторить непосредственно перед actual F)

~~~zsh
export S11_TASK_TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE"
export TMPDIR="$S11_TASK_TMPDIR" PYTHONDONTWRITEBYTECODE=1
export PYBIN="$S11_PY312" PATH="$(dirname "$S11_PY312"):$PATH"
"$PYBIN" -B - <<'PY'
import hashlib,json,os,pathlib,subprocess,sys,tempfile
root=pathlib.Path.cwd().resolve(); tmp=pathlib.Path(os.environ["TMPDIR"])
assert tmp.is_dir() and not tmp.is_symlink() and tmp.resolve()==root/".tmp/s11-functional-tmp.iy71zE"
assert tmp.resolve()==pathlib.Path(tempfile.gettempdir()).resolve()
assert sys.version_info[:2]==(3,12) and sys.dont_write_bytecode
assert os.environ["PYTHONDONTWRITEBYTECODE"]=="1"
assert subprocess.run(["git","check-ignore","-q",str(tmp.relative_to(root))]).returncode==0
with tempfile.NamedTemporaryFile(prefix="s11-launch-probe-",dir=tmp,delete=False) as f:
    f.write(b"current launch write+fsync\n"); f.flush(); os.fsync(f.fileno()); probe=f.name
print(json.dumps({"TMPDIR":str(tmp),"physical":str(tmp.resolve()),"ignored":True,"write_fsync_probe":probe,
 "bytecode_off":True,"python":sys.executable,"version":sys.version.split()[0],
 "HEAD":subprocess.check_output(["git","rev-parse","HEAD"]).decode().strip(),
 "module_sha256":hashlib.sha256((root/"scripts/test_planveyor_init_capture.py").read_bytes()).hexdigest(),
 "manifest_sha256":hashlib.sha256((root/"scripts/test_shards.json").read_bytes()).hexdigest()}))
PY
~~~

Probe сохраняется как own task evidence, без cleanup. Actual F proof связывает эту pre-import проверку, source/manifest hashes, BASE/frozen facade/runtime identities и exact invocation; старый Root readiness report не substitute текущей measurement evidence.

### Canonical checks: prepared3.10 И3.12, no test bodies

После implementation каждую axis/version/check capture отдельно. Current baseline3527/s11=34; future expected3528/s11=35/compat310=9 становится fact только после actual results. --matrix не заменяет --check, F в3.10 не исполнять. Whole module import/discovery на3.10 нужен из-за discover-before-compat-filter.

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PYBIN="$S11_PY310" PATH="$(dirname "$S11_PY310"):$PATH"
"$PYBIN" -B -c 'import os,pathlib,sys,tempfile; assert sys.version_info[:2]==(3,10) and sys.dont_write_bytecode; assert pathlib.Path(tempfile.gettempdir()).resolve()==pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,sys.version,os.environ["TMPDIR"])'
"$PYBIN" -B scripts/run_test_shard.py --check
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PYBIN="$S11_PY312" PATH="$(dirname "$S11_PY312"):$PATH"
"$PYBIN" -B -c 'import os,pathlib,sys,tempfile; assert sys.version_info[:2]==(3,12) and sys.dont_write_bytecode; assert pathlib.Path(tempfile.gettempdir()).resolve()==pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,sys.version,os.environ["TMPDIR"])'
"$PYBIN" -B scripts/run_test_shard.py --check
~~~

### Source preservation (static; no imports/body execution)

Один contiguous F insertion перед original method; optional support nested ВНУТРИ F. Raw old prefix/suffix, original span и полный old AST/order сохраняются.

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PATH="$(dirname "$PYBIN"):$PATH"
"$PYBIN" -B - <<'PY'
import ast,hashlib,pathlib,stat,subprocess
base="d2e720e182ca952dd24b9c616ea6b2eae05fd7b2"
name="test_role_run_control_markers_functional_safety_witness"
oldname="test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe"
p=pathlib.Path("scripts/test_planveyor_init_capture.py")
def git(*a): return subprocess.check_output(["git",*a])
old=git("show",base+":"+p.as_posix()); new=p.read_bytes()
assert hashlib.sha256(old).hexdigest()=="02841e0b128d7f06bf9e24fd04ecc33a504dba36d3860045133d7940de681010"
needle=("    def "+oldname+"(").encode()
assert old.count(needle)==1
at=old.index(needle); suffix=old[at:]
assert new.startswith(old[:at]) and new.endswith(suffix)
insert=new[at:len(new)-len(suffix)]
assert insert.strip()
only=ast.parse(b"class _Insertion:\n"+insert).body
assert len(only)==1 and isinstance(only[0],ast.ClassDef)
assert len(only[0].body)==1 and isinstance(only[0].body[0],ast.FunctionDef)
assert only[0].body[0].name==name and not only[0].body[0].decorator_list
a=ast.parse(old,type_comments=True); b=ast.parse(new,type_comments=True)
def cls(t):
    found=[n for n in t.body if isinstance(n,ast.ClassDef) and n.name=="InitCaptureTests"]
    assert len(found)==1
    return found[0]
def ids(t):
    return [f"{c.name}.{n.name}" for c in t.body if isinstance(c,ast.ClassDef)
            for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith("test_")]
before=ids(a); after=ids(b)
assert after.count("InitCaptureTests."+name)==1
assert [x for x in after if x!="InitCaptureTests."+name]==before
added=[n for n in cls(b).body if isinstance(n,ast.FunctionDef) and n.name==name]
assert len(added)==1
cls(b).body.remove(added[0])
def semantic(t):
    for node in ast.walk(t):
        if isinstance(node,ast.TypeIgnore): node.lineno=0
    return ast.dump(t,include_attributes=False)
assert semantic(a)==semantic(b)
def span(raw,t):
    n=next(n for n in cls(t).body if isinstance(n,ast.FunctionDef) and n.name==oldname)
    return b"".join(raw.splitlines(keepends=True)[n.lineno-1:n.end_lineno])
expected="4981951d1b958b6baaf24c94064380dfba7024e6cacc1e0a070b26d47ddae31e"
assert hashlib.sha256(span(old,a)).hexdigest()==expected==hashlib.sha256(span(new,b)).hexdigest()
mode=int(git("ls-tree",base,"--",p.as_posix()).split()[0],8)&0o777
assert stat.S_IMODE(p.stat().st_mode)==mode and not p.is_symlink()
print("additive_source=PASS old_bytes_AST_ID_order_span=unchanged new_test_count=1")
PY
~~~

AST compare исключает только F/source-coordinate fields; TypeIgnore.lineno — coordinate field. Old imports/attributes/members/helpers/hooks/body strings сохранены; отдельные prefix/suffix гарантируют ВСЕ old bytes/comments/spacing/line endings.

### Manifest preservation (static; no discovery)

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PATH="$(dirname "$PYBIN"):$PATH"
"$PYBIN" -B - <<'PY'
import json,pathlib,stat,subprocess
base="d2e720e182ca952dd24b9c616ea6b2eae05fd7b2"
p=pathlib.Path("scripts/test_shards.json")
new_id="test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_functional_safety_witness"
old_id="test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe"
old=subprocess.check_output(["git","show",base+":"+p.as_posix()]); new=p.read_bytes()
lines=new.splitlines(keepends=True); matches=[i for i,line in enumerate(lines) if ('"'+new_id+'"').encode() in line]
assert len(matches)==1
i=matches[0]
assert lines[i].strip()==('"'+new_id+'",').encode()
assert ('"'+old_id+'"').encode() in lines[i+1]
assert b"".join(lines[:i]+lines[i+1:])==old
a=json.loads(old); b=json.loads(new)
s=next(x for x in b["shards"] if x["id"]=="s11")
selector=next(x for x in s["selectors"] if x.get("module")=="test_planveyor_init_capture")
assert selector["ids"].count(new_id)==1
selector["ids"].remove(new_id)
assert b==a and len(b["subsets"]["compat310"]["ids"])==9
mode=int(subprocess.check_output(["git","ls-tree",base,"--",p.as_posix()]).split()[0],8)&0o777
assert stat.S_IMODE(p.stat().st_mode)==mode and not p.is_symlink()
print("manifest=PASS one_additive_s11_ID old_raw_order_compat9=unchanged")
PY
~~~

### Protected files: exact eleven read-only paths

| Read-only path | Bytes | SHA-256 | Git / Unix mode |
| --- | ---: | --- | --- |
| scripts/planveyor/role_runtime.zsh | 325516 | e3ed67f8df654cb73965120c5e855dd3bbcb18bd6c542489bf4ba20dd9bc57a8 | 100644 / 0o644 |
| scripts/run_test_shard.py | 17943 | aef13a07ba03937d2d4fa2dfdd17a9aea727ee5a79cee63fdfc71a99d3c29bb1 | 100644 / 0o644 |
| scripts/test_run_test_shard.py | 18457 | 609ab0c3c4dff21c6c18ca45e92cb7633daece6df0244feed43b53d7b8f585ee | 100644 / 0o644 |
| .github/workflows/checks.yml | 3662 | 6bbdf0db77358e230159247ecb7b3a080455e733b767722e22c3aaf45a8f02aa | 100644 / 0o644 |
| Makefile | 1813 | 605c5e48913ea1a0d982d1adc15d61fc12831db26e625f7e6005734215c4443c | 100644 / 0o644 |
| scripts/contract_authority_bridge.py | 54369 | abe980ea82f96d5496e8c6875d06eb421da4bbb737c48706f45ee4acd103dad1 | 100644 / 0o644 |
| scripts/contract_authority_runtime.py | 53694 | 2fcb804b825e53e95097576387e38f73deb53ca8c458f6acc8a7471ffede4bd7 | 100644 / 0o644 |
| scripts/contract_authority_context.py | 52820 | 3d6beb01f49758337cddcb91ece0ac11075cdc10fe9648b977a8a8b04e8781aa | 100644 / 0o644 |
| scripts/contract_authority_bootstrap.py | 6164 | 2cf0b7794b8e353865ca9df9132365125a8e5013a644f8cc183f79170118014f | 100644 / 0o644 |
| scripts/fs_object_identity.py | 22536 | 8dacc1158aea76025ba6df3b1c486d007fced1f7c46692348c85d55f3540c47f | 100644 / 0o644 |
| scripts/contract_authority_snapshot.py | 53738 | afe00e6ea99faf53772d74447876ea64e9c5c84c3ebabb6b2affcf70026227c3 | 100644 / 0o644 |

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PATH="$(dirname "$PYBIN"):$PATH"
"$PYBIN" -B - <<'PY'
import hashlib,pathlib,stat,subprocess
base="d2e720e182ca952dd24b9c616ea6b2eae05fd7b2"
paths="""scripts/planveyor/role_runtime.zsh scripts/run_test_shard.py scripts/test_run_test_shard.py
.github/workflows/checks.yml Makefile scripts/contract_authority_bridge.py
scripts/contract_authority_runtime.py scripts/contract_authority_context.py scripts/contract_authority_bootstrap.py
scripts/fs_object_identity.py scripts/contract_authority_snapshot.py""".split()
assert len(paths)==11
for name in paths:
    p=pathlib.Path(name); raw=p.read_bytes()
    assert p.is_file() and not p.is_symlink()
    assert raw==subprocess.check_output(["git","show",base+":"+name]),name
    mode=int(subprocess.check_output(["git","ls-tree",base,"--",name]).split()[0],8)&0o777
    assert stat.S_IMODE(p.stat().st_mode)==mode,name
    print(name+" sha256="+hashlib.sha256(raw).hexdigest()+" mode="+oct(mode))
print("protected11=PASS")
PY
~~~

### Exact F execution / whole-method measure: prepared3.12 only

Shard CLI имеет shard/subset/local-profile, НЕ exact-ID mode; s11 shard повторил бы spent original. Поэтому применяется уже объявленный в plan stdlib exact-ID route, native3.12 unittest duration и /usr/bin/time process wall; нет нового selector/runner/report helper. Непосредственно перед ним повторить Fresh launch evidence выше; F запускается только после code/static gates.

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PYBIN="$S11_PY312" PATH="$(dirname "$S11_PY312"):$PATH"
git rev-parse HEAD
shasum -a 256 scripts/test_planveyor_init_capture.py scripts/test_shards.json
/usr/bin/time -p /usr/bin/env PYTHONPATH="$PWD/scripts" "$PYBIN" -B -m unittest -v --durations 0 test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_functional_safety_witness
git rev-parse HEAD
shasum -a 256 scripts/test_planveyor_init_capture.py scripts/test_shards.json
~~~

КАЖДУЮ executable строку capture отдельно, stop при nonzero F; последний shasum не маскирует test rc. Fresh reports: exact F identity, Ran1/skipped0/errors0/failures0, actual child/stdouttee/stderrtee/final rc0; native whole-test duration + отдельные real/user/sys process-wall fields. Whole F включает все пять fixtures/setup/teardown; process wall также включает Python/import/class/module overhead. Before/after HEAD/source/manifest hashes совпадают. Record source/runtime/facade/base identities, current pre-import physical/writable/ignored/bytecode/interpreter bindings; historical receipt/Root initial acceptance не current proof.

Local timing не hosted/fast budget, observer overhead не выводится/не вычитается. Heavy outcome materialize как actual facts + owning bounded proposal, не менять old limits/helpers ради «short» и не повторять old/A-B/PartB.

Единственный necessary targeted execution guard (prepared3.12, отдельно от F cost): test_planveyor_init_capture.InitCaptureTests.test_run_timeout_is_fail_closed_with_context. Его existing mock доказывает unchanged _run timeout behavior, не заменяет real F scenarios.

~~~zsh
export TMPDIR="$PWD/.tmp/s11-functional-tmp.iy71zE" PYTHONDONTWRITEBYTECODE=1
export PYBIN="$S11_PY312" PATH="$(dirname "$S11_PY312"):$PATH"
/usr/bin/env PYTHONPATH="$PWD/scripts" "$PYBIN" -B -m unittest -v test_planveyor_init_capture.InitCaptureTests.test_run_timeout_is_fail_closed_with_context
~~~

## Critical invariants / traps

- Child success0 и finalization failure126 — разные truth hosts; first actual receipt прочитать ДО retry, run IDs/paths не смешивать.
- Real contention/death/same-lock reacquire доказывают OS holder+ready records; mkdir/env presence/notice не proof.
- Две exact outer nofollow reasons обязательны; inner OS exception text не acceptance enum.
- Old s11/dependencies raw-protected; static/import/syntax/F green не original timing/hosted/fast-floor acceptance.
- TMPDIR export до Python/tempfile/module imports, без late tempfile reset или fixture/helper edits.
- UI/browser/screenshot proof N/A (why=no UI).

## Notes for Coder

Plan — semantic source of truth. F implementation/test/measurement commands ещё не выполнялись Planner; syntax validation не PASS будущего исполнения. Не добавлять observer-label debt, new helpers/caches/selection, не менять terminal predecessor/open follow-up row.

До stage/semantic commit/actual Done/closeout — полный exact UNSTAGED Root checkpoint: files/base HEAD/tree/index/stagedempty/bytes/SHA/Git+Unix modes/bundle+helper identity/actual tests+dual review. Root scan independent physical copy без WORK index; s11 scan ACCEPT отсутствует. После scan — штатный уже разрешённый native close. Commit/family/finaldocs/Root postcommit p0 — pending nongating delivery effects до actual выполнения, не будущие [x].

## Review stamps (append-only)

- (Planner) Exact contract для одного F/two existing targets; implementation/execution pending, отдельный Manager CENSOR после primary.
- [2026-11-06, Planner finalize] Completion/closure-path self-check завершён; exact producer/identity/negative map, independent fixtures, runnable preservation/static/F commands и current-task launch boundaries согласованы с plan. Syntax-only8 shell/4 Python blocks и first strict bundle preflight actual rc0; это не PASS будущих implementation/F/measurement/review gates.
- [2026-11-06, Planner second pass] Уточнены exact production function names и actual ready JSON keys; literal SAME-lock invocation binding отделён от отсутствующего ready lock_path field. Scope, targets, MAD ref и executable commands сохранены.
- [2026-11-06 19:51 UTC] (Planner) Current handoff blocked: post-write plan lint отклонил timestamp format CENSOR receipt; plan rolled back Planner finalize. Contract clarification выше сохранена, но Coder не запускать до разрешённого recovery и actual green lint/exact readback. Implementation/runtime/tests не выполнялись.
- [2026-11-06 20:25 UTC] (Planner) NO SUGGESTIONS (reviewed; no changes required). Полный draft/current template перечитаны; executable contract/targets/commands/MAD ref unchanged. Owner prefix exception и failed-lineage audit находятся в plan; historical blocked stamp19:51 сохранён. Ordinary finalize gates и отдельный Manager new-ID replacement CENSOR обязательны, прежний dispatch остаётся unsuccessful.

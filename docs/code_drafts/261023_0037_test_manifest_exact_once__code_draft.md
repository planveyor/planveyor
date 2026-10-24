# Code draft: актуализация test manifest — executable handoff

**Date:** 2026-10-23
**Cluster:** process
**Related plan:** `docs/plans/261023_0037_test_manifest_exact_once.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261023_0037_test_manifest_exact_once.md",
    "cluster": "process",
    "targets": [
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
- Source plan provenance: `docs/plans/261023_0037_test_manifest_exact_once.md#plan-provenance--session-context`; сохраняется существующий seed, отдельного origin/restamp нет. Новые SID не выводятся из inherited CODEX_SESSION_ID и не копируются в public artifact.
- Derived MAD ref подтверждён current собственным journal-backed `mgr-fresh4-planner-primary-mad-oracle`: applicability=not_applicable, reason_code=no_machine_authority_change, carrier_sha256 как в Meta; semantic core остаётся только в plan. Прежний fresh3 result — historical evidence.

## Purpose
Дать Coder точный manifest-only contract и независимому Reviewer тот же P0–P5 proof без запуска тестовых тел. Единственный writable implementation target — `scripts/test_shards.json`; plan/draft/review — отдельные lifecycle carriers.

## Targeted changes (by file)
- `scripts/test_shards.json`: поставить `baseline_head=e9baf7c22e49ae948a8647568e40ac5344796359`; добавить class selector `test_sibling_runbook.GeneralPICorrectionRunbookTests` в s01 (два метода из таблицы plan), добавить два Shell IDs в s01/s02 и восемь NativeSibling IDs в s05/s06 ровно по plan → «Начальные missing IDs и назначения».
- Существующие ID lists сохраняют порядок прежних элементов; новые exact IDs вставляются в соответствующий существующий selector, без нового перекрывающего selector. GeneralPI — один новый class selector в s01. Сохраняются прежние s01..s14, все остальные selectors, zero_test_modules, local_profiles3/4 и две Native fixture groups.
- Все existing weighting keys/values и historical_unsplit_seconds остаются неизменными. Две literal строки ниже добавить в конец существующего `s01.notes` (создать только этот schema-compatible shard field, если отсутствует); прежние notes всех частей сохранить. Это composition annotation, не новые measured weights; `weighting.composition_notes` не добавлять.
- Whole-module `test_planveyor_plan_bundle` + `test_build_role_bundles` в s03 уже включают18 additions, `test_sibling_contract_docs` в s05 включает ещё один. Не добавлять для этих19 exact IDs; новых assignments в s03 нет.

```text
Composition updated at e9baf7c22e49ae948a8647568e40ac5344796359: 12 previously unassigned tests added; 19 source-fix tests remain covered by whole-module selectors.
Added method costs are unknown; historical weights and two NativeSibling fixture groups are unchanged; no current timing balance or CI upper bound is claimed.
```

## Reviewability preflight receipt
- `proof-path class`: standard primitives; existing `scripts/run_test_shard.py` (read-only loader/partition, без run_selected).
- `mandatory primary lane`: P4 actual `"$PYBIN" -B scripts/run_test_shard.py --check`, natural child0/native0, полный journal, manifest SHA и exact-once canonical count. TestCase bodies не исполняются.
- `mandatory non-primary carrier / contextual lane`: P0 prerequisites; P1 exact28 matrix pairs/meta; P2/P3 RAW child2/native0; P5 связывает те же P0/P1/P4 bytes, suite/protected files/base, manifest-only delta и unchanged profiles/weights. AST/schema/matrix отдельно не заменяют P4.
- `exact helper path + support files`: `scripts/run_test_shard.py`, `scripts/test_shards.schema.json`, `scripts/test_shards.json`; read-only suite `scripts/test_*.py`, `.github/workflows/checks.yml`, `requirements-dev.lock`, `pyproject.toml`.
- `dependent tests / dependent docs / known consumer paths`: listed five modules и verify_suite/Makefile из plan; CI matrix/--shard/--report и local profiles являются unchanged consumers. Runner/schema/CI/docs/test bodies не editable targets; API/schema emitter/fan-in fixture matrix — `N/A (why=semantics не меняются)`.
- `preconditions / seed-discovery`: current trusted SOURCE/PYBIN/PLANVEYOR_RUNTIME_ROOT/TMPDIR и conda activation; P0 проверяет base/branch/detached clean runtime/versions/tools/unchanged source suite. P4 discovery imports только; DB/seed/listener отсутствуют.
- `reroute rule`: expected negative P2/P3 проверяется как RAW child2/native0/full4; planned/diagnostic inventory сохраняет raw result и точную причину (Q10 planned first-review MISSING-PATH normal print raw1 не green, не повод создавать fake review или повторять print). Известный bounded defect в уже owned same-scope contract допускает ONE owning correction и fresh relevant gate с original red/current bindings/unused labels, без generic Root approval. Semantic/infra/authority blocker, scope/identity drift, UNKNOWN/signal/timeout/outside-binding или повторный unresolved defect требуют конкретного native Q&A/status route к owning роли/Architect, Root только при необходимом technical decision; blind retry/install/config repair/silent widening запрещены. CENSOR supplied-ID replacement/single-use consume правила сохраняются.
- `perceptual truth-source split`: structural repo/JSON+journal truth; OCR/template/pixel debug-only; LLM image reading bounded fallback здесь не нужен.
- `discovery-or-seed` / `receipt-reuse-only`: P0 замораживает suite/protected hashes и root identity в собственном raw journal; P1–P5 только same pass/same manifest bytes. P5 читает только собственный PROOF_PREFIX; rediscovery другого entity/потеря full4 — STOP.
- `stable identity / observer boundary`: SOURCE/BASE/runtime HEAD, suite SHA, manifest SHA, PYBIN/version, PROOF_PREFIX и exact argv/cwd/input/start/end/rc; next canonical readback — P4 JSON, reconciled P5. `notice/success text != mutation truth`.
- `runtime-lineage preflight`: P0 и P5 проверяют base/branch/runtime HEAD+detached+clean; stale runtime — infrastructure reroute, не product bug.
- `receipt retention`: raw full4 `.tmp/manifest-gates-261023/` = transient local sanity/operator journal. Durable review `docs/code_reviews/261023_0037_test_manifest_exact_once.md` сохраняет portable refs, hashes, actual caps/rc/time и вывод; P4 не создаёт test execution report/events.

## Steps / P0–P5
1. До edit прочитать plan/этот draft и сверить native context. Coder меняет только manifest по exact delta выше; минимальный JSON diff, без mass reformat.
2. Перед pass Root/Manager даёт current trusted bindings. Экспортировать SOURCE, PYBIN, PLANVEYOR_RUNTIME_ROOT, TMPDIR, JOURNAL и BASE; RUNTIME — alias того же immutable PLANVEYOR_RUNTIME_ROOT. Deterministic PROOF_PREFIX grammar — `manifest-<coder|reviewer>-p<positive pass index>`: role literal coder/reviewer, index соответствует `[1-9][0-9]*` без leading zero. Default first Coder/INDEPENDENT Reviewer — p1; completed manifest-coder-p1 full4 immutable, manifest-reviewer-p1 ещё unused и проверяется перед стартом. Для разрешённого necessary same-scope rerun после material input change/owned resolved defect выбрать наименьший positive index своей роли, у которого отсутствуют все24 paths `<PROOF_PREFIX>-p0`…`-p5` с extensions cmd/out/err/rc (любое existing file/symlink занимает prefix). Проверить весь set до P0 и конкретный label до каждого launch; collision не разрешает overwrite/replay, а UNKNOWN/signal/timeout/outside-binding не разрешает автоматический переход на новый index. Никаких latest/mtime или произвольных retry prefixes. До нового pass owning роль фиксирует конкретную причину, previous prefix/outcome и current input identity: plan/draft/manifest/suite/protected hashes, SOURCE/BASE/runtime HEAD, PYBIN/prerequisites и новый prefix; P0/P5 связывают только эти current inputs и один PROOF_PREFIX, старые records/outcomes сохраняются. На unchanged accepted implementation новый Coder pass только ради docs sync не требуется.
3. Каждый P0–P5 — отдельный native finite PTY с canonical journal runner и exact argv из plan. Копировать payload definitions ниже в owning shell, без нового script/wrapper/config. Для P0/P5 runner получает `"$PYBIN" -B -c "$P0_PAYLOAD"` / `"$P5_PAYLOAD"`; P1–P4 используют существующий CLI.
4. Command-local caps P0/P5=30, P1/P2/P3=15, P4=120s сохраняются; перед каждой finite командой выделить observation window cap+2, threshold=cap−7/poll5/reserve2 внутри cap. Overall/role/phase/documentary cumulative/product-pass wall ceilings и absolute max2 сняты prospectively: elapsed команд/pass/межкомандных интервалов/reporting сохраняется как telemetry без subtraction из admission, старые late/red/aborted costs не сбрасываются и не получают retroPASS. Standard12 Manager итераций/real-loop/identity/scope guards сохранены. Signal/timeout/late command/UNKNOWN/outside-binding/full4 inconsistency — конкретный STOP без blind retry; known same-scope correction регулируется Reroute rule и fresh prefix/current binding из шага2. Это наблюдаемый own-handle contour, не OS watchdog и не доказательство всех descendants.
5. P2/P3 принимаются только RAW `.rc=2`, `cmd rc=2`, expected stderr, native terminal0; не оборачивать ожидаемый negative в synthetic rc0. P4 требует raw0 и canonical JSON, counts не подставляются из brief/AST.
6. P5 gate связывает same-pass P0–P4 и exact delta; default — Coder pass и отдельный INDEPENDENT Reviewer pass с собственным prefix. Necessary same-scope verification после material input change/owned resolved defect требует причины/current inputs и fresh unused prefix по шагу2, а не absolute once/max2 или blind replay; unchanged accepted inputs не перепроверяются ради docs-only tail. Independent review/current proof не заменяются old pass после input drift. Coder/Reviewer не запускают suite bodies/14 shards/verify-full/SQL/reset, не устанавливают зависимости.

### P0 payload
```zsh
P0_PAYLOAD='import hashlib, importlib.metadata as md, json, os, pathlib, shutil, subprocess, sys
root=pathlib.Path(os.environ["SOURCE"]).resolve(); runtime=pathlib.Path(os.environ["PLANVEYOR_RUNTIME_ROOT"]).resolve(); base=os.environ["BASE"]
def git(where,*args):
    return subprocess.check_output(["git","-C",str(where),*args],text=True,timeout=5).strip()
assert pathlib.Path.cwd().resolve()==root and git(root,"rev-parse","--show-toplevel")==str(root)
assert pathlib.Path(sys.executable).resolve()==pathlib.Path(os.environ["PYBIN"]).resolve() and sys.version_info[:3]==(3,12,14)
versions={k:md.version(k) for k in ("PyYAML","copier","mypy","mypy_extensions","typing_extensions")}
assert versions=={"PyYAML":"6.0.3","copier":"9.18.2","mypy":"1.15.0","mypy_extensions":"1.1.0","typing_extensions":"4.15.0"}
import yaml
assert yaml.__version__=="6.0.3" and all(shutil.which(k) for k in ("git","rg","zsh"))
assert git(root,"rev-parse","HEAD")==base and git(root,"branch","--show-current")=="codex/test-manifest-261023"
assert git(runtime,"rev-parse","--show-toplevel")==str(runtime) and git(runtime,"rev-parse","HEAD")==base
assert git(runtime,"branch","--show-current")=="" and git(runtime,"status","--porcelain")==""
suite=sorted(str(p.relative_to(root)) for p in (root/"scripts").glob("test_*.py") if p.is_file())
tracked=git(root,"ls-tree","-r","--name-only",base,"scripts").splitlines()
assert suite==sorted(p for p in tracked if pathlib.PurePosixPath(p).parent.as_posix()=="scripts" and pathlib.PurePosixPath(p).name.startswith("test_") and p.endswith(".py"))
protected=suite+["scripts/run_test_shard.py","scripts/test_shards.schema.json",".github/workflows/checks.yml","requirements-dev.lock","pyproject.toml"]
hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in protected}
assert all((root/p).read_bytes()==subprocess.check_output(["git","-C",str(root),"show",base+":"+p],timeout=5) for p in protected)
manifest=(root/"scripts/test_shards.json").read_bytes()
print(json.dumps({"base":base,"python":sys.version,"python_binding":True,"versions":versions,"protected":hashes,"manifest_sha256":hashlib.sha256(manifest).hexdigest()},sort_keys=True))'
```

### P5 payload
```zsh
P5_PAYLOAD='import ast, collections, datetime as dt, hashlib, json, os, pathlib, subprocess
root=pathlib.Path(os.environ["SOURCE"]).resolve(); runtime=pathlib.Path(os.environ["PLANVEYOR_RUNTIME_ROOT"]).resolve(); journal=pathlib.Path(os.environ["JOURNAL"]); prefix=os.environ["PROOF_PREFIX"]; base=os.environ["BASE"]
def git(where,*args):
    return subprocess.check_output(["git","-C",str(where),*args],text=True,timeout=5).strip()
def output(n):
    return json.loads((journal/(prefix+"-p"+str(n)+".out")).read_text())
for n,cap,want in ((0,30,0),(1,15,0),(2,15,2),(3,15,2),(4,120,0)):
    stem=journal/(prefix+"-p"+str(n)); files=[pathlib.Path(str(stem)+"."+e) for e in ("cmd","out","err","rc")]; assert all(p.is_file() and not p.is_symlink() for p in files)
    rows=dict(line.split("=",1) for line in files[0].read_text().splitlines()); assert rows["cwd"]==str(root) and rows["input"]=="/dev/null" and int(rows["rc"])==want and int(files[3].read_text())==want
    elapsed=(dt.datetime.fromisoformat(rows["end"].replace("Z","+00:00"))-dt.datetime.fromisoformat(rows["start"].replace("Z","+00:00"))).total_seconds(); assert 0<=elapsed<=cap
p0=output(0); matrix=output(1)["include"]; check=output(4); ids=["s"+str(i).zfill(2) for i in range(1,15)]
assert p0["base"]==base and len(matrix)==28 and collections.Counter((r["python-version"],r["shard"],r["meta"]) for r in matrix)==collections.Counter((v,s,v=="3.12" and s=="s01") for v in ("3.10","3.12") for s in ids)
assert set(check)=={"manifest_sha256","canonical_tests","shards"} and list(check["shards"])==ids and all(type(v) is int and v>0 for v in check["shards"].values()) and sum(check["shards"].values())==check["canonical_tests"]
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in p0["protected"].items())
raw=(root/"scripts/test_shards.json").read_bytes(); assert hashlib.sha256(raw).hexdigest()==check["manifest_sha256"]==p0["manifest_sha256"]
for n,message in ((2,"unknown shard: manifest_unknown"),(3,"unexpected execution arguments for matrix")):
    assert message in (journal/(prefix+"-p"+str(n)+".err")).read_text() and (journal/(prefix+"-p"+str(n)+".out")).read_text()==""
assert git(root,"rev-parse","HEAD")==base and git(root,"branch","--show-current")=="codex/test-manifest-261023" and git(runtime,"rev-parse","HEAD")==base and git(runtime,"branch","--show-current")=="" and git(runtime,"status","--porcelain")==""
old=json.loads(subprocess.check_output(["git","-C",str(root),"show",base+":scripts/test_shards.json"],timeout=5)); current=json.loads(raw); assert current["baseline_head"]==base
old_shards={s["id"]:s for s in old["shards"]}; note_additions=["Composition updated at e9baf7c22e49ae948a8647568e40ac5344796359: 12 previously unassigned tests added; 19 source-fix tests remain covered by whole-module selectors.","Added method costs are unknown; historical weights and two NativeSibling fixture groups are unchanged; no current timing balance or CI upper bound is claimed."]
current["baseline_head"]=old["baseline_head"]; additions={"s01":["test_cold_explicit_plan_cycle_uses_existing_fake_client_and_no_pointer_or_init"],"s02":["test_public_candidate_format_correction_all_roles_and_bounded_outcomes"],"s05":["test_tui_resolver_nested_and_explicit_second_checkout","test_tui_markerless_legacy_refuses_before_session_effects","test_tui_invalid_plan_session_and_foreign_receipts_are_effect_free"],"s06":["test_tui_engaged_missing_session_bootstraps_only_through_facade","test_tui_reuses_receipt_and_refreshes_current_plan_payload","test_tui_process_exit_and_missing_saved_session_use_existing_checker","test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient","test_tui_client_error_and_runtime_drift_preserve_native_outcome"]}
for shard in current["shards"]:
    for method in additions.get(shard["id"],[]):
        mod,cls=("test_contract_authority_shell","ContractAuthorityShellIntegrationTests") if shard["id"] in ("s01","s02") else ("test_sibling_runbook","NativeSiblingCommitPolicyTests"); full=mod+"."+cls+"."+method; matches=[s for s in shard["selectors"] if full in s.get("ids",[])]; assert len(matches)==1; matches[0]["ids"].remove(full)
    if shard["id"]=="s01":
        prior=old_shards["s01"]; assert shard["notes"]==prior.get("notes",[])+note_additions
        if "notes" in prior: shard["notes"]=prior["notes"]
        else: del shard["notes"]
        target={"module":"test_sibling_runbook","class":"GeneralPICorrectionRunbookTests"}; assert shard["selectors"].count(target)==1; shard["selectors"].remove(target)
assert current==old
tree=ast.parse((root/"scripts/test_sibling_runbook.py").read_text()); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="GeneralPICorrectionRunbookTests"); assert {n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith("test_")}=={"test_actual_console_plan_close_ready_outcomes_and_no_writes","test_invalid_closeout_schema_keeps_existing_nonzero"}
allowed={"scripts/test_shards.json",os.environ["PLAN_PATH"],"docs/code_drafts/261023_0037_test_manifest_exact_once__code_draft.md","docs/code_reviews/261023_0037_test_manifest_exact_once.md"}; changed=set(git(root,"diff","--name-only",base,"--").splitlines())|set(git(root,"ls-files","--others","--exclude-standard").splitlines()); assert all(p in allowed or p.startswith("docs/code_reviews/assets/261023_0037_test_manifest_exact_once/") for p in changed)
print(json.dumps({"manifest_sha256":check["manifest_sha256"],"canonical_tests":check["canonical_tests"],"shards":check["shards"],"protected_unchanged":True,"exact_delta":True,"profiles_weights_unchanged":True},sort_keys=True))'
```

P5 читает только завершённые P0–P4 records того же PROOF_PREFIX/current inputs; собственные natural P5 rc/native/full4/command-local cap проверяются owning ролью сразу после native completion. Whole-pass elapsed/reporting — telemetry без225s ceiling; prior times/costs/failed outcomes сохраняются. P0/P5 payloads не являются новым checked-in helper и не расширяют implementation targets.

## Review route
- Primary artifact: `docs/code_reviews/261023_0037_test_manifest_exact_once.md`.
- Lane type: `code review`; обе независимые native lanes проверяют current exact manifest bundle. Review до materialization — PLANNED, не PASS.

## Critical invariants / traps / bypass paths
- Canonical exact-once: только P4 связывает imports/discovery/partition; matrix/JSON/schema/AST сами не закрывают coverage, counts не являются timing proof.
- No duplication: GeneralPI2+Shell2+Native8 дают начальные12; whole-module19 не получают дополнительных selectors. P5 normalization доказывает, что никакая другая manifest семантика не изменилась.
- Raw negative outcomes: P2/P3 rc2 успешны только как expected negatives, никакой замены child rc на wrapper0; P4 rc2 никогда не зелёный.
- Shared API/payload/Manager dispatch/receipt schema changes, UI/runtime listener и truth-host helper change: `N/A (why=manifest-only assignments; consumers unchanged)`.

## Notes for Coder
- Plan важнее draft; обнаруженный gap — конкретный bounded Architect/Root route, без нового target, новой обёртки, ремонта env или тестового тела.
- Strict Planner preflight не доказывает P0–P5/product/review/commit/release. CENSOR запускает только Manager отдельным dispatch.

## Review stamps (append-only)
- 2026-10-23 (Architect): создан только минимальный seed; Planner finalization и execution не выполнены.
- [2026-10-23 15:30] (Planner): seed прочитан и финализирован; sole manifest target, exact12/19, P0–P5 payloads/raw negatives/225×2 caps и single review route согласованы. Product pass не выполнялся.
- [2026-10-23 16:23] (Planner): existing unqualified draft перечитан; Targeted changes/P5 согласованы с accepted shards[].notes: exact две строки добавляются только в s01.notes, P5 восстанавливает prior notes перед сравнением, weighting целиком совпадает с base. Sole manifest target/12/19/P0–P5/raw rc2/caps/review route сохранены; product не запускался.
- [2026-10-23 23:00] (Planner): genuine current review/Q12 sync пяти active execution clauses завершён: deterministic role/pass grammar/current-input binding/full4 collision guards, known-result classification/ONE owning correction и command-local caps согласованы с plan. Historical stamps/исходный Coder p1 сохранены; P0/P5 payload bytes, sole manifest target/12/19/two s01.notes/weights/profiles не менялись. Current lint/strict preflight ещё pending; product не запускался.

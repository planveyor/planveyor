# Code draft: Диагностика времени CI в s02 и s11

**Date:** 2026-11-01 13:55 +0300
**Cluster:** quality
**Related plan:** `docs/plans/261101_1252_ci_runtime_timing_diagnostics.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261101_1252_ci_runtime_timing_diagnostics.md",
    "cluster": "quality",
    "targets": [
      {
        "path": "scripts/test_contract_authority_shell.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_planveyor_init_capture.py",
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
- Source plan provenance: исходный manual-owner carrier плана сохранён; ниже current helper-backed Planner context при финализации existing seed.
- Relation: `created-here`
- Thread ID: `01a19401-95ad-7f92-a530-cfe67758df66`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-11-01T10:49:56Z`

## Purpose
Исполнимый observational-only контракт для Coder: добавить наружную timing diagnostics в два existing test modules, сохранив все assertions, bounds, subcases, original return/exception behavior и source/runtime guards. Cause fix, hosted CI actions и публикация П2 не разрешены; stage/commit принадлежат последующему native closeout.

## Reviewability preflight receipt
- `proof-path class`: `standard primitives`.
- `mandatory primary lane`: два существующих methods `test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_public_candidate_format_correction_all_roles_and_bounded_outcomes` и `test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe` целиком на Python 3.10/3.12; все исходные subcases, actual rc, `Ran` count, skips/errors/failures и raw timing evidence. Никакого запуска whole s02/s11 вместо этих narrow IDs.
- `mandatory non-primary carrier / contextual lane`: timeout nonterminal, оба s11 subcase, стоимость writer processes и неизменные business assertions.
- `exact helper path + support files`: `scripts/test_contract_authority_shell.py`, `scripts/test_planveyor_init_capture.py`; read-only harness `scripts/test_contract_authority_support.py`.
- `dependent tests / dependent docs / known consumer paths`: текущий AST call graph показывает 14 existing test consumers `_run_public_pi_command`, перечисленных ниже; internal adapter callers — `_run_public_pi_collection`, `_checkpoint_public_pi_after_architect`, `_run_public_pi_composition`. Они сохраняют return value, original labels/hash fields и failure semantics; новые role/subcase поля не создают required runtime inputs. `scripts/test_shards.json`, `scripts/run_test_shard.py`, `.github/workflows/checks.yml` — read-only context, новых production consumers нет.
- `preconditions / seed-discovery`: published base, clean frozen runtime, Python/TMPDIR inputs; существующие fixtures, без новой seed или runtime mutation.
- `reroute rule`: missing/red обязательная lane или widening targets перед handoff возвращаются owning Architect/Planner; никаких implicit gate substitutes.
- `perceptual truth-source split`: структурные logs, source diff и raw monotonic observations; N/A (why=no visual proof).
- Retention: raw `.tmp/` logs = transient local evidence; durable result = planned review artifact ниже.
- Observer boundary: сохранить existing fault→close; diagnostic printing/saving после его завершения. Raw timestamp location внутри существующего writer не переносится ради уменьшения elapsed; дополнительный process/I/O внутри interval отдельно указан с честной measured/unmeasured cost. Следующий canonical source diff и исходные assertions доказывают неизменность contract.
- `discovery-or-seed`: только существующие disposable `AuthorityFixture` и `legacy_complete` test fixtures; initial source/runtime identity читается до affected command. `receipt-reuse-only`: внутри уже созданного subcase продолжается тот же fixture/cycle; запрещён silent reseed для получения green.
- Stable identity: exact test ID + role/subcase + fixture identity + capture cycle/receipt, если существующий scenario их создаёт; candidate/runtime hash и source pins сохраняются. Потеря identity/receipt continuity — failure по исходному scenario, не причина придумать новый entity.
- `notice/success text != mutation truth`: verdict даётся прежними assertions, Git/receipt readback и actual rc; timing rows сами не доказывают successful runtime operation. `runtime-lineage preflight`: current WORK base/source pins, frozen runtime commit и existing fixture manifest проверяются отдельно; drift возвращается owning runtime/Architect boundary до Coder fix.

## Existing consumer inventory / authority boundary
- Writable implementation: только `scripts/test_contract_authority_shell.py` и `scripts/test_planveyor_init_capture.py`; `deleted_paths=[]`. Plan/draft/review и mandatory immutable Risk support входят в lifecycle exact bundle отдельно, не становятся implementation targets.
- Existing s02 adapters: `_run_public_pi_collection`, `_checkpoint_public_pi_after_architect`, `_run_public_pi_composition`; сохраняют вызываемые команды, payload/body, original label, stdin/stdout/stderr hashes, result object и error behavior.
- Read-set class: `test_contract_authority_shell.ContractAuthorityShellIntegrationTests`. Existing consumers: `test_public_candidate_format_correction_all_roles_and_bounded_outcomes`, `test_public_continuation_checkpoint_revalidates_fresh_bundle_and_replays_without_write`, `test_public_pi_blocked_recovery_requires_recorded_after_map_and_repairs_derived`, `test_public_pi_checkpointed_replay_pairs_semantic_reason_before_stdin`, `test_public_pi_composition_clean_noop`, `test_public_pi_composition_materialized_duplicate`, `test_public_pi_differing_input_replay_pairs_semantic_error`, `test_public_pi_facade_runs_all_general_roles_and_v2_replay`, `test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture`, `test_public_pi_partial_recovery_replaces_one_blocked_carrier_truthfully`, `test_public_pi_post_admission_body_validation_pairs_semantic_error`, `test_public_pi_rebuild_derived_flag_pairs_semantic_private_rejection`, `test_public_pi_semantic_failure_after_backlog_recovers_exact_blocked_state`, `test_public_pi_unobservable_postmap_skips_fabricated_blocked_receipt`. Это compatibility inventory; запуск всех 14 не требуется.
- Read-only consumers/enforcement: `scripts/test_contract_authority_support.py`, `scripts/planveyor.zsh`, `scripts/planveyor/role_runtime.zsh`, `scripts/run_test_shard.py`, `scripts/test_shards.json`, `.github/workflows/checks.yml`, `docs/tools/verify_suite.md`. Helper/schema/API/runtime emitter changes: `N/A (why=диагностика принадлежит test trace, runtime contracts и schemas не меняются)`.
- Owner-facing dispatch: `N/A (why=dispatch path unchanged; existing public commands используются только в disposable fixtures)`; truth-host aggregation matrix: `N/A (why=no fan-in/readback implementation change)`.

## Observational field and interval contract
### s02
- Existing `_run_public_pi_command` получает optional metadata keywords `role=None`, `subcase=None`; они не становятся required runtime inputs. `role` именует owning scenario role, `subcase` сохраняет исходные case labels/stage, включая `second_malformed=False|True` в primary. Actual primary matrix обязательно различает все восемь outer role/outcome cases. Prefix-collector `--role` может отличаться от outer correction role: executed argv/его role остаётся отдельным фактом, не подменять его outer label. Existing callers/adapters передают известные значения; для non-role context использовать `N/A`/`UNKNOWN`, без вывода по private filename.
- Terminal trace сохраняет все прежние fields и добавляет `role`, `subcase`, `clock="time.monotonic"`, `units="seconds"`, `started_monotonic`, `ended_monotonic`, `elapsed_seconds`; `argv` = реальный command list, `actual_rc` = returned CompletedProcess.returncode. Raw float samples не округлять; elapsed = end - start того же clock. Return object/stdout/stderr не заменяются diagnostic output.
- Start/end берутся непосредственно снаружи существующего `subprocess.run`; post-call trace/print/save выполняются после end sample и до caller assertions. Никакие phase timestamps внутри child не выводятся из наружного interval.
- Timeout: retained schema `public_pi_command_timeout.v1`, state `nonterminal_timeout`, command_terminal=false, deadline_seconds=120, prior_trace, identity и partial stdout/stderr сохраняются; role/subcase/end sample могут быть additive observations. Terminal actual_rc на верхнем уровне отсутствует; trace terminal rows не дописываются. Тот же TimeoutExpired re-raised без retry, return conversion или изменения timeout.
### s11
- Сохраняются existing whole-command start/end, original durable fault/close samples и все исходные bounds/assertions, включая `<60.0`, fault→close `<5.0`, две marker ветки, release symlink contention, interrupted holder и `release_parent=missing` с `126:0`.
- Отдельно представить raw `whole_command_started_monotonic`, `whole_command_ended_monotonic`, `whole_command_elapsed_seconds`; для каждого existing role call — role/subcase/call index, raw before/after boundary samples и их elapsed; original fault/close и first/retry samples остаются отдельными полями. Не подменять одно измерение другим.
- Для каждого timestamp writer отдельно показать реально наблюдённые samples/cost и точный measurement scope. Minimum: raw writer-body interval с units/clock и указанием, что Python launch/import/scheduling/неизмеренные части остаются UNKNOWN; если independently измерен whole-process interval, именовать его отдельно. Writer-body cost нельзя назвать полной process cost. Ни одна стоимость не вычитается из original fault→close/business assertion.
- Existing timestamp location сохраняется; исходное `.9f` representation business timestamp не превращать в «raw без округления». Дополнительные raw observations хранят исходный float/repr отдельно. Финальная diagnostic serialization/print/save агрегированного record выполняется после whole measured command и до rc/60 s/прочих способных оборвать сохранение assertions. Existing timestamp persistence остаётся в исходной точке; вся добавленная observation activity внутри fault→close перечисляется с actual measured scope/cost, а не скрывается переносом timestamp или вычитанием overhead.
- Сбор observations не превращает missing/malformed source timestamps, protected marker, nonzero rc или original assertion failure в pass. Если observation недоступно, сохранить UNKNOWN/error detail до исходного failure path; бизнес-проверки и cleanup не удалять.

## Targeted changes / steps
1. Прочитать plan, этот draft и оба полных relevant helper/scenario bodies. До dependent work выполнить literal plan prelude в уже объявленном process-local envelope: selected PYBIN явно supply/export до nested /bin/zsh -lc, outer tool login:false; внутри prerequisite только bare python3. Требуются version 3.12/samefile(selected PYBIN), existing physical TMPDIR outside Git; parent PATH/explicit Python не подменяют inheritance. Затем выполнить source inventory `before` из plan Commands; проверить published base `11ace6c3b3338740ea13dc9f9ef91080651e9c7f`, clean frozen runtime, prepared Python 3.10/3.12, physical TMPDIR и source hashes. Никакой установки dependencies/HOME/config repair.
2. Только Coder добавляет s02 metadata/timing в existing helper и current callers, затем s11 raw/boundary/writer observations в existing method/helpers. Не создавать новый unittest ID, production helper, wrapper или checked-in fixture. Все original assertions/limits/return and exception semantics сохраняются; new diagnostic handling не подавляет original failure.
3. Source inventory `after` требует те же 38/58 IDs, exact original assertion/fail/subTest calls и unchanged manifest/workflow; actual source diff ограничен двумя targets. Все 14 consumers/adapters проверить по literal call graph; explicit metadata не ломает caller с trace=None или existing trace list.
4. На каждой axes выполнить три literal unittest IDs из plan Commands целиком, по одному process: два mandatory primary methods и `test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture`. Итого шесть invocations, каждый actual rc=0, Ran 1 test, OK, zero skips/errors/failures/expected failures/unexpected successes. Primary s02 содержит восемь role/outcome subcases, primary s11 — все existing branches. Нельзя запускать whole class/shard/full suite вместо них.
5. На каждой axes выполнить controlled probe ниже: returned terminal rc 0/2 + TimeoutExpired bytes/text partial-output/report/re-raise parity, ровно один mocked subprocess call на случай, timeout=120. Это bounded structural/exception proof, не физическая проверка 120 s deadline, process cleanup или замена primary live fixture execution.
6. Existing `scripts/run_test_shard.py --check` на обеих axes проверяет imports/partition без исполнения suite. Сохранить actual summary/counts и неизменный manifest SHA; source-authored expectations не заменяют execution result.
7. Coder записывает в plan source-bound results/log locators/hashes и честные UNKNOWN. Reviewer materialize-ит один review с durable phase report contract ниже; затем обязательны current review proof, strict bundle --check и scoped doc gates с настоящим review/support. Architect выполняет дальнейший native closeout; Manager terminal family отдельно. Публикация П2 запрещена.

## Review route / durable phase report
- `Primary artifact`: `docs/code_reviews/261101_1252_ci_runtime_timing_diagnostics.md`; `Lane type`: code review; initial state PLANNED. Review использует current canonical `BUNDLE=current` snapshot, не manual SHA. Mandatory selected Risk support добавляет existing exact-bundle helper; raw `.tmp/` logs не становятся review assets автоматически.
- Для каждого axis/ID: UTC observation timestamp, exact git_head, `source_state` (dirty/committed), SHA-256 обоих actual test files и manifest, frozen runtime commit, actual Python version и executable identity без personal path, actual command/test ID, actual rc/Ran/skips/errors/failures и log locator/hash.
- Execution surface = local для этих commands. OS/arch берутся из фактического platform readback; runner/image = UNKNOWN, если нет независимого публичного identity carrier. Не писать private hostname и не выдавать local label за hosted runner/image. Hosted outcomes в этом report не обновляются по догадке.
- s02 table: test/role/subcase/label, sanitized argv (private components → <REDACTED>), named clock/units, raw start/end/elapsed, terminal actual_rc либо nonterminal timeout state. Raw argv/identity/partial-output остаются transient.
- s11 table: marker/release_parent/call index, original whole/fault→close/first/retry samples, raw boundary intervals, writer observed cost и его scope; added observation I/O/process count/cost и UNKNOWN components. Не вычитать overhead, не выводить причину задержки и не заменять original assertion diagnostic числом.
- Успех узких локальных проверок квалифицирует только объявленные методы и controlled assertions; не hosted/full-suite proof, не cause fix и не publication acceptance.

## Source inventory continuity
В той же shell после plan prelude определить функцию и вызвать `p2_inventory before` до edits, `p2_inventory after` после edits. Transient JSON не authority. `before` не перезаписывать.

```sh
p2_inventory() {
  "$PYBIN" -B - "$p2_proof_dir" "$1" <<'P2INVENTORY'
import ast, hashlib, json, pathlib, subprocess, sys
root = pathlib.Path.cwd(); out = pathlib.Path(sys.argv[1]); phase = sys.argv[2]
assert phase in ('before', 'after')
files = ('scripts/test_contract_authority_shell.py', 'scripts/test_planveyor_init_capture.py')
snapshot = {'files': {}, 'guards': {}}
for rel, expected_count in zip(files, (38, 58)):
    raw = (root / rel).read_bytes(); tree = ast.parse(raw); methods = []; calls = {}
    for cls in (x for x in tree.body if isinstance(x, ast.ClassDef)):
        for fn in (x for x in cls.body if isinstance(x, ast.FunctionDef)):
            key = cls.name + '.' + fn.name
            if fn.name.startswith('test_'): methods.append(key)
            calls[key] = [ast.dump(x, include_attributes=False) for x in ast.walk(fn)
                          if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                          and isinstance(x.func.value, ast.Name) and x.func.value.id == 'self'
                          and (x.func.attr.startswith('assert') or x.func.attr in ('fail', 'subTest'))]
    assert len(methods) == expected_count
    snapshot['files'][rel] = {'sha256': hashlib.sha256(raw).hexdigest(), 'ids': sorted(methods), 'calls': calls}
for rel in ('scripts/test_shards.json', '.github/workflows/checks.yml'):
    snapshot['guards'][rel] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
path = out / ('source-' + phase + '.json')
if phase == 'before':
    assert not path.exists(), 'preserve original before source inventory'
    assert snapshot['files'][files[0]]['sha256'] == 'e9bb680fa8a76fbd3fb836ea2f58a7ed80c7cb86b4586e62a7b7d0316aeffb89'
    assert snapshot['files'][files[1]]['sha256'] == 'a268e23265a8fafec812c82b27299263831cf025fd547fb0f35c7921e4a52c03'
    assert snapshot['guards']['scripts/test_shards.json'] == 'bb18fa43385c3d9bcb97eb3ada28302030e09e4ff37848519cc0d869d942c260'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == '11ace6c3b3338740ea13dc9f9ef91080651e9c7f'
else:
    before = json.loads((out / 'source-before.json').read_text())
    assert before['guards'] == snapshot['guards']
    for rel in files:
        assert before['files'][rel]['ids'] == snapshot['files'][rel]['ids']
        for key, calls in before['files'][rel]['calls'].items():
            assert calls == snapshot['files'][rel]['calls'][key], (rel, key, 'original assertions/subcases changed')
    changed = set(subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines())
    assert changed == set(files), 'missing target or out-of-scope tracked source delta'
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
    assert all(path.startswith('docs/') for path in untracked), 'new implementation paths forbidden'
path.write_text(json.dumps(snapshot, sort_keys=True) + '\n')
print('source_inventory=' + phase, 'method_counts=38,58', 'manifest_and_workflow_guarded=true')
P2INVENTORY
}
```

## Controlled terminal/timeout parity
Выполнить весь block по одному разу на каждой axes после Coder edits, с `p2_python` из plan matrix. Это standard-primitives probe existing helper в disposable AuthorityFixture; subprocess boundary замокана только внутри трёх cases. Не переносить snippet в новый checked-in test/module.

```sh
p2_controlled() {
env -u PLANVEYOR_ROOT PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1   "$p2_python" -B - <<'P2CONTROLLED'
import contextlib, hashlib, io, json, subprocess
from unittest import mock
import test_contract_authority_shell as module
from test_contract_authority_support import AuthorityFixture
case = module.ContractAuthorityShellIntegrationTests()
with AuthorityFixture() as fixture:
    for rc in (0, 2):
        trace = []; output = io.StringIO()
        result = subprocess.CompletedProcess(['controlled'], rc, 'out', 'err')
        with mock.patch.object(module.subprocess, 'run', return_value=result) as call, contextlib.redirect_stdout(output):
            actual = case._run_public_pi_command(fixture, label='controlled-terminal', arguments=['controlled'],
                       input_text='body', trace=trace, role='Planner', subcase='terminal-' + str(rc))
        assert actual is result and call.call_count == 1 and call.call_args.kwargs['timeout'] == 120
        row = trace[-1]
        assert row['actual_rc'] == rc and row['label'] == 'controlled-terminal'
        assert row['role'] == 'Planner' and row['subcase'] == 'terminal-' + str(rc)
        assert row['clock'] == 'time.monotonic' and row['units'] == 'seconds'
        assert row['ended_monotonic'] >= row['started_monotonic']
        assert row['elapsed_seconds'] == row['ended_monotonic'] - row['started_monotonic']
        assert row['stdin_sha256'] == hashlib.sha256(b'body').hexdigest()
        assert row['stdout_sha256'] == hashlib.sha256(b'out').hexdigest()
        assert row['stderr_sha256'] == hashlib.sha256(b'err').hexdigest()
    prior = [{'label': 'prior', 'actual_rc': 2}]; output = io.StringIO()
    failure = subprocess.TimeoutExpired(['controlled'], 120, output=b'partial-out', stderr='partial-err')
    with mock.patch.object(module.subprocess, 'run', side_effect=failure) as call, contextlib.redirect_stdout(output):
        try:
            case._run_public_pi_command(fixture, label='controlled-timeout', arguments=['controlled'],
                        trace=prior, role='Planner', subcase='timeout')
        except subprocess.TimeoutExpired as caught:
            assert caught is failure
        else: raise AssertionError('TimeoutExpired was swallowed')
    assert call.call_count == 1 and call.call_args.kwargs['timeout'] == 120
    assert prior == [{'label': 'prior', 'actual_rc': 2}]
    rows = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
    reports = [row for row in rows if row.get('schema') == 'public_pi_command_timeout.v1']
    assert len(reports) == 1
    report = reports[0]
    assert report['state'] == 'nonterminal_timeout' and report['command_terminal'] is False
    assert 'actual_rc' not in report and report['deadline_seconds'] == 120
    assert report['partial_stdout']['bytes_hex'] == b'partial-out'.hex()
    assert report['partial_stderr']['text'] == 'partial-err'
    assert report['prior_trace'] == prior and report['identity']['expected_runtime_commit'] == fixture.runtime_commit
print('controlled_parity=valid; cases=terminal_rc_0,terminal_rc_2,nonterminal_timeout; physical_deadline_proof=false')
P2CONTROLLED
}
```

## Notes / risks for Coder and Reviewer
- Q1 закрыта отдельным Architect response: прежний natural-login prerequisite воспроизводится при явно inherited selected PYBIN. Own Planner full-envelope probe дал actual rc=0, bare Python 3.12.14/samefile=true, physical TMPDIR outside Git. Старые failed probe/stamps остаются historical; они не становятся success. Перед каждым зависимым исполнением повторять literal prelude текущего plan с явным PYBIN/TMPDIR/frozen runtime, outer tool login:false и вложенным bare login shell. Non-green сохраняет hold без fallback/waiver/config repair; implementation допускается только после Ready for Coder и отдельного Manager handoff.
- Plan — semantic source of truth. Scope, bounds или proof route нельзя менять ради green; новый implementation target возвращается owning Architect до widening.
- При настоящем timing assertion failure сохранить diagnostic observations и исходный non-green; менять runtime, deadlines, retries или business boundary запрещено.
- Controlled timeout доказывает только retained report/exception behavior; phase component UNKNOWN нельзя подменять оценкой из outer elapsed. Сохранить current fixtures/receipt continuity и original cleanup.
- Штатные plan/scoped document gates применяются именно к этому П2, а не через П1 permission; runtime_py doc_lint route не изобретать. Full suite/all14, hosted CI actions и публикация не разрешены.

## Review stamps (append-only)
- [2026-11-01 13:23 +0300] (Architect) Seed создан только после current N-A oracle и штатного helper rc=0; минимальные path-tracking targets соответствуют Owner intent. Planner-owned executable proof и implementation ещё отсутствуют.
- [2026-11-01 13:55 +0300] (Planner) Existing seed прочитан и финализирован: два targets/ref unchanged; exact fields, consumer inventory, source/assertion guards, narrow matrix, controlled parity и durable phase-report contract материализованы. Implementation/runtime execution и review не выполнялись.

- [2026-11-01 14:05 +0300] (Planner) Финализация остановлена на source-backed launch/proof Q1; contract и syntax подготовлены, но Ready for Coder, runtime execution и acceptance не объявлены.

- [2026-11-01 14:46 +0300] (Planner) Q1 continuation синхронизирована с действующим plan: own full-envelope prerequisite rc=0, current blocked wording заменено, исторические failed probe/stamps сохранены. Это подготовка первого executable handoff с прежними gates, не runtime acceptance и не permission для cause fixes/publication.

- [2026-11-01 14:50 +0300] (Planner) First executable admission завершён после own full-envelope prerequisite rc=0 и current plan/scoped/strict-preflight gates; current launch wording согласовано с закрытой Q1. Source targets, bounds, matrix, assertions и historical stamps unchanged; это handoff contract, не runtime/review acceptance.

# Code draft: Одна штатная коррекция формата general PI

**Date:** 2026-10-15 11:04
**Cluster:** process
**Related plan:** `docs/plans/261015_0939_general_pi_format_correction.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261015_0939_general_pi_format_correction.md",
    "cluster": "process",
    "machine_authority_decision_ref": {
      "applicability": "required",
      "decision_id": "mad-261015-0939-general-pi-format-correction",
      "carrier_sha256": "564d9a4f7fc4c2b8952a21f2d33d3c02298667e01756bf71e9123c62f80a0157"
    },
    "targets": [
      {"path": "scripts/process_improvements_collect.py", "kind": "py"},
      {"path": "scripts/followups_capture.py", "kind": "py"},
      {"path": "scripts/docs_closeout.py", "kind": "py"},
      {"path": "scripts/sibling_closeout.py", "kind": "py"},
      {"path": "scripts/sibling_runbook.py", "kind": "py"},
      {"path": "scripts/test_process_improvements.py", "kind": "py"},
      {"path": "scripts/test_followups_capture.py", "kind": "py"},
      {"path": "scripts/test_docs_closeout.py", "kind": "py"},
      {"path": "scripts/test_contract_authority_shell.py", "kind": "py"},
      {"path": "scripts/test_sibling_runbook.py", "kind": "py"},
      {"path": "scripts/test_manager_custom_pipeline_prompt_contract.py", "kind": "py"},
      {"path": "docs/tools/prompts/manager_collab_pipeline.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/manager_collab_pipeline.md", "kind": "doc"},
      {"path": "docs/process_improvements/README.md", "kind": "doc"}
    ],
    "deleted_paths": []
  }
}
```

## Provenance / session context
- Source plan provenance: `docs/plans/261015_0939_general_pi_format_correction.md`, раздел Plan provenance / session context; этот draft создаётся отдельно.
- Relation: `created-here`
- Thread ID: `N/A (why=private operator mapping is not published)`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-15T08:02:08Z`

Поля получены штатным provenance helper; private identity не опубликована. Derived tagged MAD ref перенесён из fresh validated oracle, semantic core остаётся только у Architect в plan. Это provenance, не runtime admission и не доказательство TUI/SID continuity.

## Purpose
Довести принятый И2 до реализации в 14 существующих файлах: типизированный no-effect отказ, одна durable reservation на роль/cycle, один correction dispatch и truthful blocked/retryable consumers. План имеет приоритет; новый controller, support file, dispatch adapter или recovery contour не создаётся.

## Reviewability preflight receipt
- `proof-path class`: checked-in repo-local helper.
- `mandatory primary lane`: candidate suites `scripts/test_process_improvements.py`, `scripts/test_followups_capture.py`, `scripts/test_docs_closeout.py`; каждый новый predicate и transition проверяется на candidate implementation, все четыре role positions обязательны.
- `mandatory non-primary carrier / contextual lane`: `scripts/test_contract_authority_shell.py` исполняет public engaged facade с copied candidate helpers; `scripts/test_sibling_runbook.py` проверяет actual public stdout и отсутствие stage/commit; `scripts/test_manager_custom_pipeline_prompt_contract.py` проверяет branch-local Manager contract и negative mutations. `scripts/test_sibling_contract_docs.py` остаётся read-only parity/private-fingerprint proof. Статический prompt proof не является live LLM dispatch.
- `exact helper path + support files`: пять helper targets из Meta. Read-only support: `scripts/test_contract_authority_support.py:AuthorityFixture`, existing `bin/planveyor`, `scripts/contract_authority_bridge.py`, `scripts/planveyor/role_runtime.zsh`, `scripts/planveyor.zsh`. Existing fixture copying и mutable shell-test hash inventory достаточны; новый launcher/support path не нужен.
- `dependent tests / dependent docs / known consumer paths`: шесть mutable suites и три doc targets из Meta; known consumers — actual post-general branch и explicit same-cycle entry Manager, sibling plan/post-run/close/close --commit, existing checkpoint/followups/ordinary-V2 freeze и terminal docs-closeout. Schema/readback имеет blocking admission semantics, а prompt и tests остаются consumer/proof.
- `preconditions / seed-discovery`: discovery-or-seed создаёт synthetic canonical Git target и candidate Git runtime через existing fixtures внутри объявленного ignored TMPDIR; родительский enclosing Git repo не заменяет самостоятельный fixture Git root. Helper-owned begin создаёт cycle; malformed PI задаётся только fixture input, без checked-in sample corpus/backfill. Receipt-reuse-only использует те же project root, plan_ref, source terminal commit/blob и semantic identity, cycle, role, raw input SHA-256, reservation id и object/revision proof. Потеря identity/receipt continuity = STOP, без latest/reseed.
- `reroute rule`: любая missing/red mandatory lane блокирует Ready for Review независимо от primary green. Новый mutable support/helper/adapter path, новый product choice либо невозможность подтвердить accepted contract — owning Architect STOP до widening.
- `perceptual truth-source split`: structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up. Visual proof N/A (why=no visual surface).

Observer boundaries: fresh schema-green native readback непосредственно перед reservation → terminal fresh `state=reserved` result перед первым send → same invocation передаёт единственный полный corrected output → collector revalidates stored reservation/original → fresh same-cycle readback. Spent readback запрещает reserve/send, но не требует повторного retryable для уже допущенного ingest. Success text не закрывает mutation: `notice/success text != mutation truth`. После всех четырёх green leaves обязательны unchanged checkpoint, четыре followups lanes и terminal capture-aware completed proof.

Runtime-lineage preflight в public fixture сравнивает source/copy SHA-256 всех пяти helper targets, Manager source/copy и PI README до исполнения и после сценария. Расширяется только existing `_PUBLIC_PI_CANDIDATE_PATHS`/hash assertions в mutable shell-test file; `_copy_runtime` уже копирует current script bytes. Attested fixture runtime commit остаётся тем же. Frozen running helpers используются только для native plan/bundle gates и не являются доказательством А2. Fixture state/output под `.tmp` — transient local sanity only; plan, live review и explicit risk assets — durable review evidence.

Crash/reentry и stale-CAS regressions выполняются отдельными процессами. Они доказывают single-Manager serial/reentry contract; true simultaneous multiwriter concurrency этим slice не заявляется. Второй concurrent Manager, общий lock framework и новая DB uniqueness scope не вводятся; если без них выбранный single-Manager contract не удерживается, вернуть Architect с точным repro.

### Truth-host fixture matrix
| Поле | Исполнимая проверка |
| --- | --- |
| authoritative_host | Existing aggregate receipt с current source/host/object/revision proof + canonical current PI leaf chain + live PI/protected object maps. Derived stdout не является host. |
| derived_summary_field | `general_pi_format_correction_admission` в docs-closeout, collector stdout и sibling outcome. |
| green_case | Для каждой роли green contiguous prefix, один typed no-effect blocked, absent suffix, fresh source и unused slot → retryable; fresh reserve → reserved; one corrected ingest → green leaf; unchanged suffix dispatch/checkpoint/followups завершают тот же cycle. |
| missing_case | Missing carrier/leaf/source/proof/absence evidence → blocked до reservation/write/send. |
| ambiguous_case | Extra/multiple blocked leaf, conflicting source/role/cycle, stale retained payload/CAS или replaced host/object → blocked. |
| present_but_red_or_inconsistent_case | Green-looking summary при red/noncontiguous prefix, changed PI/derived/protected maps, effectful blocked, untyped/UTF-8/unknown error, spent slot, checkpoint/followups progress → blocked. |
| expected_fail_closed_verdict | Machine-readable blocked reason, preserved original error/bytes; zero new reserve/send/checkpoint/followups/stage/commit. Tests snapshot aggregate/leaf/maps/HEAD/index и spy forbidden calls; red host всегда побеждает derived green. |

## Targeted changes (by file)
- `scripts/process_improvements_collect.py`: dedicated ValueError subtype только для parser-format throw sites в `extract_process_improvements_section` / `parse_process_improvements_section`; `error_type=pi_format_error` только на таких v2 refusals. `_normalize_source_ref_for_lane`, role/cycle/source validation, UTF-8, authority/I/O и unknown errors не становятся format error. `_v2_receipt_payload`, `_validate_v2_capture_receipt`, `_admit_v2_replay`, `_collect_process_improvements` и safe v2 publication сохраняют raw digest/maps/error и допускают reserved typed replacement, включая truthful second refusal. Legacy/private primitive не становится automatic permission.
- `scripts/followups_capture.py`: fresh `begin_cycle` adds empty `general_pi_format_corrections`; existing receipt validator/read_capture и active-general admission понимают bounded optional carrier. Новый action `reserve-general-pi-correction` использует current canonical source, `_receipt_pi_lineage`, canonical leaf/object checks и existing `_publish_mutation` CAS; не создаёт новый registry/file. Existing checkpoint/role/freeze/staging readers сохраняют свои phase/identity guards.
- `scripts/docs_closeout.py`: derive complete admission из existing capture helper, включить field в `classify_docs_closeout`, schema validation, text/readback и dispatch context emitters. Retryable не очищает outer blocked, capture blocked или final-docs gates; stale/missing/red hosts не дают inferred permission.
- `scripts/sibling_closeout.py`: до docs-stage/commit и success hints классифицировать helper outcome. `handle_close`/`handle_ready`, `_docs` и `_completed` сохраняют source/cycle/schema gates; retryable/blocked не становятся semantic/docs_ready/completed.
- `scripts/sibling_runbook.py`: actual `show_plan`/post-run/main output показывает helper-derived `general_pi_format_correction_state=retryable|blocked` и honest message. Existing recognized operational rc=0 сохраняется; invalid invocation/authority/infrastructure остаются nonzero. Новый JSON envelope не нужен. Retryable указывает единственную correction в текущем живом Manager; consumed/unknown/blocked — Owner stop, без автоматического нового run/close/rebinding.
- `scripts/test_process_improvements.py`: type boundary и original-byte/ingest matrix, включая exact full-block incident tail, no-op, structured materialization, already-tracked и replay.
- `scripts/test_followups_capture.py`: all-role predicate/budget matrix, durable-before-send, retained-proof/CAS failures, independent crash/reentry processes, second malformed и original preservation.
- `scripts/test_docs_closeout.py`: schema/field parity, truth-host matrix и corrected full-family terminal sink; existing ordinary-V2 compact bind/freeze proof сохраняется.
- `scripts/test_contract_authority_shell.py`: existing candidate fixture/hash machinery, public engaged positive/negative composition и cold explicit PLAN_PATH/cycle fake-client adapter regression; no cached `.planveyor.planpath`, init/plan_set/queue effects.
- `scripts/test_sibling_runbook.py`: public run → post-run plan, plan, close и close --commit при retryable/consumed/unknown/blocked; actual console outcome/rc и forbidden-effect spies.
- `scripts/test_manager_custom_pipeline_prompt_contract.py`: branch-local actual post-general consumer + same-cycle entry before generic stop, ordered reservation/send/ingest and negative relocation/removal mutations; A1 guarded parse contract остаётся intact.
- `docs/tools/prompts/manager_collab_pipeline.md` и `copier_template/docs/tools/prompts/manager_collab_pipeline.md`: exact source/copy pair с единственным typed helper-admitted exception к refusal STOP; полная correction message и distinct reserve/send/ingest observer boundaries.
- `docs/process_improvements/README.md`: minimal type/admission/reservation/spent semantics, schema fields и honest operator output; unrelated owner guides не меняются.

### Receipt schema emitter inventory / field parity
| Family / fields | Validator и emitter | Target decision / focused proof |
| --- | --- | --- |
| `process_improvement_capture.v2`: additive `error_type=pi_format_error`; existing `capture_state`, `reason_code`, `error`, `input_sha256`, before/after/path results | Collector `_v2_receipt_payload`, `_validate_v2_capture_receipt`, safe publication and fresh/replay response; helper leaf-chain reader | Collector/helper targets; tests distinguish dedicated parser error from untyped/identity/UTF-8/I/O/unknown. Success/replay не получают ложный format type; raw bytes/digest неизменны. |
| `followups_capture_receipt.v1`: `general_pi_format_corrections`, role record `general_pi_format_correction.v1` | `begin_cycle`, receipt validator/read_capture, active-general admission, new reserve action and `_publish_mutation` | Capture target; empty fresh map, unknown/malformed/missing carrier blocks correction без historical migration; existing ordinary historical green read remains compatible. |
| Reservation binding: project/source/cycle/role, generated reservation id, `attempts_reserved=1`, original receipt canonical path/object/content identity, `original_receipt_utf8` и SHA-256 | Capture writer/validator; collector reserved-ingest reader | Same two targets; byte-for-byte original receipt restoration/hash после green replacement и second refusal, включая whitespace/newline bytes; original raw input digest/error доказуемы. |
| `docs_closeout_payload.v1.general_pi_format_correction_admission`: schema `general_pi_format_correction_admission.v1`, state, reason, plan/cycle/role, attempts/max=1, next_dispatch, helper proof | Capture derivation → docs-closeout classifier, `validate_docs_closeout_payload`, `finalize_docs_closeout_payload`, `_refresh_dispatch_context_block`, `render_text` | Capture/docs-closeout targets; schema/missing/ambiguous/red-host fixtures, malformed nested carrier не выдаётся за schema-green. Manager не собирает proof. |
| Fresh reserve transition `state=reserved` и exact identity; top-level aggregate сохраняет `state=started` | Existing capture CLI parser/main / action response | Capture target; second reserve не возвращает разрешающий reserved; retained full docs-closeout JSON stdin, source/revision/CAS independently rederived. |
| Sibling projection `general_pi_format_correction_state=retryable|blocked` | `_docs`, handle_close/handle_ready, show_plan/main | Both sibling targets; actual stdout/rc and no-stage/commit assertions. Fields не принимаются за permission на send. |
| Public facade / shell adapter / source loader | `bin/planveyor`, `scripts/planveyor/role_runtime.zsh`, `scripts/planveyor.zsh`, `scripts/contract_authority_bridge.py` | Read-only context with N/A (why=existing generic Python dispatch and explicit plan/cycle transport unchanged); cold fake-client fixture checks separate payload fields and current candidate helper proof. |

Generated skeleton/bootstrap emitters вне перечисленных families N/A (why=no new scaffold/schema family); new fields emit только existing owners выше. No-cycle v1 compatibility не открывает current-cycle correction. `schema_state=ok` означает валидную форму payload, а не semantic clean.

### Command-surface fan-out
Public entry сохраняется `planveyor_manager_collab_cmd run <explicit PLAN_PATH> --followups-capture-cycle-id <UUIDv4>`. Helper/runtime surface — existing capture CLI и Manager consumer. One-shot dispatch N/A (why=existing `scripts/planveyor/role_runtime.zsh` adapter unchanged); `scripts/planveyor.zsh` post-run plan readback остаётся context-only. Help/readback owners — три doc targets и sibling output. Cold regression проверяет separate PLAN_PATH/FOLLOWUPS_CAPTURE_CYCLE_ID и отсутствие init/pointer/queue writes; actual persistent-handle continuity удерживает Manager contract, fixture не изображает live role session.

## Review route
- `Primary artifact`: `docs/code_reviews/261015_0939_general_pi_format_correction.md`.
- `Lane type`: code review, обе independent lanes с одним exact target snapshot.

Review пока PLANNED; только pre-review `--preflight` допускает его отсутствие. Post-review `--check`, current risk support и final exact closeout обязательны. Plan и draft — отдельные lifecycle bundle members, они не входят в mutable review targets.

## Patch sketch (keep it small)
N/A (why=contract and steps below are sufficient; implementation belongs to Coder).

## Steps
1. Сначала AC-to-test checklist в plan, затем dedicated parser-format type и tests. Не определять type по error text; strict parser и full-body incident-tail rejection сохраняются.
2. Реализовать helper-owned full predicate для каждой роли: current source/host/authority; green contiguous prefix от baseline; ровно один typed no-effect blocked; absent suffix; live/derived/protected maps clean; нет checkpoint/followups/failure/final objects; unused durable slot. Все отрицательные кейсы дают отказ без writes.
3. В existing CLI action принять retained полный docs-closeout JSON через `--docs-closeout-json -`, rederive predicate/effect context/CAS и atomically сохранить единственный role record с exact original receipt bytes. Только fresh publication возвращает reserved; initial free. Restart/lost result/second reserve не восстанавливают send permission.
4. Collector revalidates stored reservation и original blocked binding для единственного already-admitted ingest, отдельно от retryable readback. Corrected raw output передаётся полностью; successful replacement или second refusal сохраняют original record/budget. Проверить changed binding и повторный input/replay без новой mutation/send authority.
5. Синхронизировать docs-closeout emit/schema/readback и sibling projections. Не позволять rc=0, retryable summary или pending missing roles скрыть current blocked; no stage/commit при blocked. Сохранить прежние error rc и unchanged unrelated commands.
6. Manager source/copy: после terminal refusal сохранить rc/stdout/error, взять fresh schema-green helper admission; retryable даёт только reserve request. Перед send дождаться terminal fresh reserved result. Отправить existing handle exact ROLE/PLAN_PATH/PRE_STATUS_LINE/cycle/error/PROMPT_FILE/full reread general prompt, запрет repeat docs edits и требование полного output с `## Process improvements`. Не trim/prose-strip/no-op-substitute. Любая утрата handle/result/invocation permission — STOP. Второй malformed — STOP без третьего dispatch.
7. Candidate public composition исполняет helper CLI и cold explicit-path adapter на настоящих fixture Git roots. All four role positions × corrected green/second malformed; materialized prefix/independent budget slots, crash/reentry, type/authority/source/map/phase negatives. Hash identity проверяется до/после. Не подменять candidate execution вызовом frozen runtime.
8. Прогнать все команды ниже, прочитать WARN и current diff; перед Ready for Review exact targets/one review route/three synchronous docs должны совпадать. Новые paths или невозможный proof требуют Architect reroute. Live rehearsal, stage/commit/push в Coder scope не входят.

## Critical invariants / traps / bypass paths
- Invariant: один EXTRA durable slot на project/source/cycle/role; trap — repeated reserved ack или reentry возвращает permission; bypass — cold explicit continuation/новый процесс. Проверка: fresh-process spent readback + no third send, initial без reservation, каждая следующая роль независима.
- Invariant: typed no-effect admission не ослабляет отказ; trap — общий ValueError, green-looking stdout или outer pending; bypass — wrong source/cycle/role, prefix/suffix/effect/live/protected drift. Проверка: таблица отрицательных predicates и current authoritative red поверх derived green.
- Invariant: единственный correction ingest и original evidence сохраняются; trap — after-reserve readback либо повторно разрешает send, либо ошибочно требует retryable для уже разрешённого ingest. Проверка: distinct boundaries, exact original bytes/hash после обеих веток и full-family terminal sink.

## Commands
Все команды из selected project с уже переданными trusted compatible PATH, `$PYBIN` и ignored TMPDIR; один interpreter spelling, без private absolute paths. Datastore/SQL/auth/visual profile N/A (why=process helper fixtures only). Native gates исполняют frozen runtime только для plan/draft; candidate suites и Make читают working bytes.

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_lint docs/plans/261015_0939_general_pi_format_correction.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261015_0939_general_pi_format_correction.md
PYBIN="$PYBIN" bash scripts/run_doc_lint.sh --root docs/plans/261015_0939_general_pi_format_correction.md --root docs/code_drafts/261015_0939_general_pi_format_correction__code_draft.md
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_process_improvements.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_followups_capture.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_docs_closeout.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_contract_authority_shell.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_sibling_runbook.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_manager_custom_pipeline_prompt_contract.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_sibling_contract_docs.py' -v
make verify
make doc-lint
make typecheck
make oss-release-scan
```

Success: каждый объявленный candidate suite и Make route exit 0; verify — GREEN только для перечисленных modules, public-copy scan — zero blockers. Known frozen canonical doc-lint RED на missing docs/README refs остаётся отдельным recorded result; scoped plan/draft pass не объявляет global GREEN. Новый red candidate gate — STOP/reroute, unrelated canon/runtime не чинить. Native helper gate не заменяет candidate proof; неизменный green не повторять без основания. Full unittest discovery не заявляется этим targeted набором.

## Assumptions / risks
Accepted single continuous native Manager/handles и frozen runtime остаются private operator conditions. Этот draft и baseline settings не доказывают terminal continuity или live adoption А2. New controller/framework, SQL, guides другого автора, old receipt migration, runtime repair, live rehearsal, push/publication/history rewrite запрещены.

## Notes for Coder
План — semantic source of truth. Только 14 literal targets выше writable; support/adapter/context refs не добавлять молча. Required implementation proof закрывается до Architect exact closeout; затем plan immutable и Manager отдельно выполняет full docs family/capture-aware completed/final_docs_commit=no_op|landed. Done или implementation commit не заменяют этот terminal sink. Raw reservation/proof command здесь описан для candidate fixture; frozen runtime action до реализации не вызывать.

## Review stamps (append-only)
- [2026-10-15 11:10] (Planner) NO SUGGESTIONS (reviewed; no changes required)

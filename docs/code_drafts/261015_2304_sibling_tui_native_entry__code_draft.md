# Code draft: тонкий sibling TUI-вход в штатный Manager

**Date:** 2026-10-16
**Cluster:** process
**Related plan:** `docs/plans/261015_2304_sibling_tui_native_entry.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)

```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261015_2304_sibling_tui_native_entry.md",
    "cluster": "process",
    "targets": [
      {"path": "scripts/sibling_runbook.py", "kind": "py"},
      {"path": "scripts/planveyor.zsh", "kind": "sh"},
      {"path": "scripts/test_sibling_runbook.py", "kind": "py"},
      {"path": "scripts/test_sibling_contract_docs.py", "kind": "py"},
      {"path": "copier_template/AGENTS.md.jinja", "kind": "template"},
      {"path": "docs/release_backlog.md", "kind": "doc"},
      {"path": "docs/followups/release_backlog.md", "kind": "doc"}
    ],
    "deleted_paths": [],
    "machine_authority_decision_ref": {
      "applicability": "required",
      "decision_id": "mad-261015-2304-sibling-tui-native-entry",
      "carrier_sha256": "7b331089b0d8741955140e63ac6ccc0e438d741086b038efb23df1666b08af71"
    }
  }
}
```

Ref выше связывает validated frozen_confirmed carrier из current oracle. Semantic core не копируется; writer остаётся Architect в plan. Checkpoint-V2 admission baseline: N/A (why=not the checkpoint-V2 implementation plan).

## Provenance / session context

- Source plan provenance: `docs/plans/261015_2304_sibling_tui_native_entry.md`; отдельное создание draft на Planner finalize.
- Relation: created-here
- Thread ID: N/A (why=private operator mapping is not published)
- Parent thread ID: N/A (why=not exposed by env, wrapper receipts, or session stats)
- Session SID: N/A (why=.planveyor.session.planner is missing or empty)
- Launch surface: unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)
- Captured from: env
- Captured at: 2026-10-15T21:16:27Z

Поля получены через `planveyor_plan_provenance_context --section code-draft --session-key planner`; private thread value не публикуется. Provenance не является proof исполнения или `Context source` rerun.

## Purpose

Добавить один явный `planveyor sibling tui` поверх existing Manager TUI, сохранив CMD/Architect `human_explicit`, resolver и native authority/session guards. Этот draft определяет контракт и proof paths; implementation ownership остаётся Coder.

## Validation policy (Q8; governing Owner override)

Последнее прямое правило Owner получено и подтверждено Manager. Source of truth — `docs/plans/261015_2304_sibling_tui_native_entry.md::Decisions::Validation policy (Q8)` и closed Q8; оно выше прежних plan/draft/prompt mandatory-full слов. **Все новые verify-full/repeats/equivalent full discovery сейчас запрещены**, включая make verify-full, make test-scripts, direct verify_suite.py --full и эквивалентный общий unittest discovery. Full discovery не gate конца В, review, Done, exact commit или terminal docs closeout. Будущий дорогой тест «на всё» возможен только перед публикацией ВСЕЙ работы в GitHub, по отдельному плану декомпозиции с учётом прежней работы Opus и после отдельного явного согласия Owner до запуска. Этим bounded plan будущая задача/публикация/push не создаются и не разрешаются; монолит для диагностики не запускать.

**Current applicability — validation-policy text only.** Implementation завершена Coder в V5. Все C2–Q7 phase/transport/assertion/preparation/parity recipes ниже сохранены как reference выполненного contract и для действительно затронутого последующего scoped execution; они не поручают повтор реализации, clone, origin, шести prerequisites, четырёх многочасовых suites или candidate doc/type из-за текущей policy-text-only delta/interrupt. Семь source/test targets, их modes, 24 readonly contexts, supplementary session_init и executed assertions unchanged; V5 results сохраняются. Настоящая новая behavior/source/test/proof-helper/runtime delta отдельно выбирает affected scoped selector/owning route; автоматического test-all или повтора всего набора нет.

V5 Evidence в plan за 2026-10-17 12:57–12:59: natural origin + шесть exact prerequisites (каждый Ran1/all subcases/no skip/actual Architect tail), native44/docs23/bare84/authority38 и doc/type имеют actual run_rc=0/sink_rc=0/post-parity=0; T01–T10 без skip. Исторический Make run_rc/sink_rc/post-parity остаётся UNKNOWN; log SHA-256 61002d1388843eb7a66fd6d8a486b55f6ac831b65342ef131c85eb18f38b53ce, 3481/10 contextual non-Git skips/GREEN — только log-content evidence, не native PASS. Десять genuine non-Git skips остаются unexecuted contextual coverage вне no-skip T01–T10, не новый gate В. UNKNOWN прежнего неприменимого full run не требует общего STOP/GO, recovery или повторного запуска. Новый applicable scoped red/missing/skip/UNKNOWN требует exact owning-role triage.

Historical executed snapshot не переписывать: source HEAD a6f8dcfe90cd9411310f5d8fcb3bd68b703ac854, fixture HEAD ca321cc33815c7ca3a9539e240ccb87aae2dd290, exact seven-target patch SHA-256 dbca61393efbd68e32435e622bac256ffd4ade133334f25c96e7d94fa9cb8961; run-set plan SHA-256 7e5586969c18125936faddb4dc88d6e03981799f77a55e133a895d10a09fcd00 и draft SHA-256 c56cf4a292ae0b3d0857160f887c6fb385b9ed7e7b495eeec2412a8db486cb34. Current plan/draft policy hashes закономерно отличаются: их проверяют отдельно как lifecycle text delta, не выдают за новый inventory33 source/copy parity и не обновляют old manifest ради fake green. Historical failed receipts/pre-recovery UNKNOWN/skips/Owner original audit сохраняются.

Сейчас нужны только короткие ordinary plan lint, scoped plan/draft/template/F12 doc lint, exact bundle preflight, actual-status oracle и static delta readback source/context/HEAD/index. Reviews, semantic Done/exact commit и terminal docs family остаются обычными downstream шагами; их готовность не объявляется заранее. Предыдущие действительные V5 suites повторять не требуется.

## Reviewability preflight receipt

- `proof-path class`: checked-in repo-local helper
- `mandatory primary lane`: `scripts/test_sibling_runbook.py`, actual public facade в `PublicSiblingTests`/`NativeSiblingCommitPolicyTests`; clean committed disposable candidate runtime, real bootstrap/resume/receipts, fake только внешний `_planveyor_codex` client boundary. `scripts/test_sibling_contract_docs.py` проверяет template/F12 projection и delivery.
- `mandatory non-primary carrier / contextual lane`: все T01–T10 из plan, retained CMD/Architect/direct-native, markerless legacy refusal T03 vs настоящий engaged success T04, invalid pointer/receipt, foreign project/runtime, exit/drift; contextual full suites `scripts/test_planveyor_bare_entrypoints.py`, `scripts/test_contract_authority_shell.py`. Green primary не снимает эти обязательства.
- `exact helper path + support files`: mutable adapter/parser `scripts/sibling_runbook.py`, writer/reader `scripts/planveyor.zsh`; existing baseline surfaces `bin/planveyor`, `scripts/planveyor/role_runtime.zsh`, `scripts/test_contract_authority_support.py`, `scripts/test_support/process_contract_fixtures.py` — read-only context. Mandatory admission `scripts/consumer_contract.py:marker_answers`, `scripts/contract_authority_snapshot.py:parse_local_marker_bytes`, `scripts/contract_authority_context.py` — также read-only; Q3/C1 не разрешает менять их. Новых helper files нет.
- `dependent tests / dependent docs / known consumer paths`: два mutable suites; `copier_template/AGENTS.md.jinja`, `docs/release_backlog.md#f12`, `docs/followups/release_backlog.md`; actual `_planveyor_role_prompt_body`, `planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd run` и Architect paths. Assigned RU/EN guides и retained init/authority consumers не становятся edit targets.
- `preconditions / seed-discovery`: `discovery-or-seed` — сначала общий clean verification checkout по C2/Q4 recipe ниже: actual source HEAD, exact seven-target плюс current plan/draft overlay, source/copy SHA-256 и mode parity, один disposable fixture commit, allowlisted child env. Supplied TMPDIR и synthetic HOME физически вне copied candidate. Только затем existing named native fixture создаёт собственные runtime/consumer/plan и client sinks под тем же supplied TMPDIR. `receipt-reuse-only` — продолжение того же native chain с теми же `project_root`, `runtime_pin`, `plan_ref`, `session_key`, `manager_sid` и actual init receipt. Missing/malformed continuity = hard-fail; explicit loss subcase T07 отделён от green chain. Для смены selected plan в T05 current `plan_ref` обновляется existing selector явно, SID/project/runtime остаются теми же.
- `Q3/C1 admission boundary`: successful sibling entry требует existing physical schema-3 marker `docs/_meta/planveyor_contract_authority.v1.json` и matching `.copier-answers.yml`. T03 — отдельный negative target после existing consumer init и plan selection: объявленно удалить только fixture marker, затем снять protected baseline; actual candidate TUI должен вернуть specific `invalid or missing contract marker`, rc=3, client events=0, unchanged session/Owner payload/queue/index/HEAD. Сохранённый `.planveyor.planpath` не заменяет marker. T04 использует настоящий schema-3 engaged consumer без Manager SID, real init receipt и один terminal resume, оба actual payload с одним current native_existing header. Markerless legacy authority context не даёт successful sibling bootstrap; engaged fixture нельзя назвать legacy.
- `runtime-lineage preflight`: actual source HEAD + exact diff и literal inventory фиксируются до copy; supplementary readonly `scripts/planveyor/session_init.zsh` source/copy SHA-256 и mode обязаны совпасть с тем же baseline source HEAD blob/tree mode до первого init/test и при каждом before/after/final parity. Primary inventory33/24 context paths не меняется; dependency не overlay-ить, не stage-ить и не instrument-ить. Existing native fixture source-lineage assertion на `scripts/test_sibling_runbook.py:315–324` до bootstrap сравнивает этот producer с verified candidate, включая SHA/mode; source/verification hashes, modes, original index/HEAD и clean copied Git root проверяются до/после runs. Source HEAD и disposable fixture HEAD различаются законно: accepted bytes связаны parity receipt, а fixture commit не является product closeout/adoption. Общий verification root не получает adapters из PublicSiblingTests; instrumentation разрешена только внутри named native tests. Frozen lifecycle runtime остаётся отдельным source-plan hygiene host. Любой source drift делает result stale; missing/red/skip/UNKNOWN prerequisite требует owning-role stop, contextual runtime contract меняет только Architect.
- `C3/Q5 namespace identity`: после C2 preparation каждый candidate Python стартует fresh interpreter через explicit chdir в manifest-bound physical candidate root и exec того же trusted Python. Canonical discover -s scripts соответствует verify_suite.py; absolute copied discovery при source cwd не executable route. До любых tests отдельный natural observer читает scripts.__path__, package test modules, docs_closeout MODULE, direct authority origin, natural alias identity и callable admission. Никаких launch writes в sys.path/sys.modules, PYTHONPATH, -t, нового initializer/helper или подмены source. Далее оба C2 narrow, existing authority checkpoint, corrected T04/T06 и шестым полный C4/C5 T08 — каждый ровно один named test/all subcases/no skip с terminal rc/parity до applicable scoped suites/doc-type по Q8. Первый red/missing/skip/UNKNOWN останавливает sequence.
- `observer boundary / closure`: actual external-client argv/stdin/payload на init/resume; первая standalone [ALWAYS START] отделяет control header от raw body, phase map ниже обязательна; approved guarded effective init bytes и positive absence/presence подтверждаются вместе с actual phase; затем public planveyor_session manager|architect + receipt того же project/runtime/role, protected plan/pointers/Owner payload/queue/index/HEAD. Metadata-bearing pointer целиком не является SID; existing corrected observers используют public reader и для foreign runtime. Open-Q&A negative seed требует canonical timestamp и explicit state=open precondition. `notice/success text != mutation truth`; next canonical readback закрывает переход. Manager CMD `_planveyor_codex exec … resume SID payload` и Manager TUI `_planveyor_codex resume … SID payload` имеют payload последним argv, captured stdin=""; Architect resume отдельно сохраняет `exec … resume SID -` и actual stdin payload. Existing sink читает stdin только при literal последнем `-`; captured empty field не является независимым OS-stdin measurement. Канал не выбирается по одному слову exec и не выбирает COMMIT_POLICY. Source refs: `scripts/planveyor/role_runtime.zsh:6427–6428` CMD, `:6222` TUI, `:5074/:5128` Architect resume; `scripts/test_sibling_runbook.py:590–604` sink и `:845–876` T08. Producers/sink/guards не переписываются ради green; fresh whole T08 обязан достичь реального Architect init+resume tail, static parse этого не доказывает.
- `retention class`: fixture homes, client logs и receipts под supplied TMPDIR — transient local sanity only. Case/result table, current target snapshot и immutable support refs в единственном review artifact/его assets — durable operator/review evidence. Без account transcripts, private paths или настоящего SID mapping.
- `reroute rule`: relevant skipped/red/missing lane, недопустимый prerequisite или расширение low-level runtime/authority/schema targets блокируют handoff и идут к Architect; существующие selectors/guards не обходятся.
- `perceptual truth-source split`: structural/repo-backed carrier preferred; screenshot OCR / template matching / pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback = helper gap/reroute. Screenshot для terminal adapter не обязателен.

### Authority и command-surface inventory

- Exact writable bundle — только семь `code_draft_meta.targets`; plan/draft/review/support входят в final bundle отдельно. New target paths/deletions: none.
- Runtime enforcement — existing readonly local policy writer в actual `planveyor_sibling` frame, `_planveyor_role_prompt_body` reader и existing native session/authority helpers. Plan/MAD reference/template/test/review не runtime selectors.
- One-shot dispatch: N/A (why=dispatch path unchanged; no new MANAGER_CMD or one-shot selector). `scripts/planveyor/role_runtime.zsh` read-only; `sibling tui` вызывает его existing TUI entry без `--q`/`--merge` ровно один раз. Нет public plan positional arg, cold missing-pointer refusal обязателен.
- Owner help/docs — parser help + mutable template/F12; assigned guides context-only. Consumer semantics — TUI `native_existing`, CMD/Architect `human_explicit`, direct-native current policy не зависит от env/history.
- Payload parity — только control header до первой standalone `[ALWAYS START]`: exact one nonempty current `ROLE`, `PYBIN`, `COMMIT_POLICY`, `PLANVEYOR_RUNTIME_ROOT` на init и resume. `PLAN_PATH`/`PRE_STATUS_LINE` обязательны ровно по одному на каждом resume и отсутствуют в init header; cycle присутствует только в explicit CMD cycle resume. Raw bootstrap/examples/answers не count-source. TUI `MANAGER_CMD=run` и CMD `MANAGER_CMD=run <plan_ref>` — отдельные final resume trailers, не init/header fields. Phase map и actual client sink/approved body/public receipt, не source substring или event index, закрывают parity.
- Receipt schema emitter inventory: N/A (why=no receipt/schema validator or schema field changes). Actual existing init receipt и bridge остаются contextual enforcement, fake report не заменяет их.
- Truth-host fixture matrix: N/A (why=thin adapter does not add a fan-in/readback summary helper). T06 всё равно проверяет present-but-invalid receipt с отсутствием effects.

## Targeted changes (by file)

- `scripts/sibling_runbook.py`: добавить parser/help/validation-only TUI action без selectors/positional plan; selected project/plan и manager mode admission проверяются до live bootstrap. Сохранить retained CMD arguments и existing `Context.plan -> require_project -> marker_answers`/`session_check` semantics; successful markerless route не создавать.
- `scripts/planveyor.zsh`: thin TUI branch в `planveyor_sibling`; valid readonly unexported current local policy до init/resume/Owner-answer consumption; reader допускает только accepted два значения из actual frame. Existing native session helper и TUI dispatch reuse-ятся; чужой frame/invalid policy fail-closed. Non-zero и native drift outcome не теряются за поздним convenience readback.
- `scripts/test_sibling_runbook.py`: exact planned cases ниже и нужное расширение существующего fake external client/stats. Real adapter, init/resume, authority bridge и receipts не stub-ить; mutable/missing/invalid policy mutation regressions обновить к current writer anchors без снижения assertions. Post-V1 public planveyor_session readers и timestamp/explicit open-Q&A seed сохраняются; их V2 green относится только к тому snapshot. C4/Q6 меняет T08 CMD assertion с sentinel/stdin на retained exec+resume argv/payload и captured stdin="". C5/Q7 добавляет phase-specific header presence/absence/cardinality по map ниже: common fields в init/resume, plan/status только resume, cycle только exact CMD cycle; first standalone body boundary и approved effective raw-init bytes через actual guarded reader обязательны. Existing native fixture lineage включает readonly session_init source/candidate SHA+mode до bootstrap. Шесть Manager events/policies/same SID+receipt и actual cold Architect init→public receipt→same-role resume tail сохраняются; phase не выводится только из index. Existing sink/runtime/guards не correction targets. Observer correction и эти prerequisites завершены в V5; current Q8 validation-only restamp сохраняет proof без повторов. Для действительно нового applicable execution порядок/observations остаются прежними, full discovery исключён Q8.
- `scripts/test_sibling_contract_docs.py`: новый T10 contract test; сохранить existing delivery/private-fingerprint/source-copy checks и manual CMD wording в назначенных context-only guides.
- `copier_template/AGENTS.md.jinja`: назвать два entrypoint modes; retained `sibling run/architect` manual и явный `close --commit`; TUI native exact closeout не требует blanket approval и не разрешает silent publication. Narrow specific permission, preview/preflight, rollback и docs `no_op` названы буквально.
- `docs/release_backlog.md`: только фактическое F12 объяснение двух modes и concrete Git prerequisite; не объявлять fixed глобальную запись `.git`, F13/rebinding или future diagnostics вне accepted scope.
- `docs/followups/release_backlog.md`: синхронизировать только F12 `why` explanation; source/item identity, summary/title, priority, assignee, open status, null plan/dispositions/reason сохраняются. Ordinary task не является promotion. Read-only `scripts/followups_index_rebuild.py:collect_rows` строит `SummaryRow` из priority/source identity/summary/assignee/status/plan, не из why: этот explanation-only change сохраняет generated index bytes. `docs/followups/index.md` не target, ручное редактирование generated block запрещено.

## Review route

- `Primary artifact`: `docs/code_reviews/261015_2304_sibling_tui_native_entry.md`
- `Lane type`: code review; обязательны независимые risk/contracts lanes и current snapshot одного семипутевого implementation bundle.

## Patch sketch (keep it small)

Это сохранённый implementation contract, выполненный V5; current Q8 поручает только validation-policy text/handoff, не повтор шагов 1–7 или изменение product/test bytes.

1. Зафиксировать current candidate/source inventory, прочитать listed existing adapter/parser/fixture sites. Не менять low-level TUI/resolver/authentication setup.
2. Реализовать только принятый thin entry и двухрежимный invocation-local writer/reader в двух source files. Не переносить алгоритм Manager в adapter.
3. Existing terminal-capable fake client/stats сохраняет natural channel observation по literal последнему argv `-`: cold Manager/Architect init и Architect resume через stdin, Manager CMD/TUI resume через argv. Observer отделяет header по первой standalone boundary, проверяет positive init absence/resume presence и approved guarded init-body bytes, public same-role SID/receipt→resume continuity. До consumer bootstrap existing fixture-lineage check включает session_init SHA/mode от verified candidate; только observation/assertions в existing test target. Менять sink, authority/init/resume producers или добавлять runtime fields запрещено. Это existing test fixture, не новый launcher/helper.
4. Materialize-ить exact case names/subcases из plan; help/refusal, nested/project, markerless legacy refusal T03 и schema-3 engaged successful bootstrap T04, reuse/loss, CMD/TUI/direct policy, native error/drift доказываются отдельно. Retained CMD refusal на том же T03 negative target — contextual regression, не замена нового actual TUI case.
5. Обновить три doc/template targets и T10 assertions. Не редактировать assigned guides и typed follow-up fields, historical notices или source runtime.
6. После C2/Q4 preparation применить C3/Q5 explicit fresh child cwd и natural origin preflight. Строго sequential: оба C2 narrow, exact authority checkpoint, corrected T04, corrected T06, затем шестым весь corrected T08 со всем Manager chain и реально достигнутым Architect tail; каждый ровно один named test/all subcases/no skip. Только затем applicable scoped suites/doc-type на том же copied snapshot по Q8; full discovery сейчас запрещён. V5 уже выполнил этот scoped contract, policy-text-only delta его не перезапускает. До следующей команды дочитать actual terminal rc и before/after parity, включая parity при non-zero; при первом red/missing/skip/UNKNOWN остановиться, не запускать parallel/hidden retry. Записать actual result каждого T-case.
7. Reconcile seven targets, single review host и current candidate bytes; handoff `Ready for Review` после required proof. Semantic Done/commit и post-commit docs family выполняют downstream owners, не тестовый fake client.

## Tests / Commands

Exact test names и все subcases — `PLAN_PATH::### Case-level proof map`. Current implementation diff сохранён; существование case не доказывает fresh execution. Все pre-recovery implementation/test/gate exits UNKNOWN. V1 — prior bytes: native44 rc=1 (1 failure/6 errors), authority38 rc=1 (16 errors), docs23/bare84 и два C2 narrow green только на V1. V2 после standalone-fence extraction correction реально прошёл origin и пять narrow; полный native suite Ran 44/6562.547s/rc=1/один T08 FAIL/errors=0/no skip, остальные 43 ok. CMD assertion ожидала argv[-1]='-', actual последний argv был Manager payload; Architect tail и последующие T08 assertions не достигнуты. Остальные full suites/Make V2 NOT_RUN. Это историческое exact-snapshot evidence V1/V2, не current acceptance. После него V5 завершил corrected Q7/T08, origin/шесть prerequisites/четыре scoped suites/doc-type с actual run/sink/post-parity rc0; точная qualification приведена в governing Q8 policy выше. Current policy-text-only delta не обнуляет эти results, historical Make UNKNOWN/log-only/skips остаются фактами. Prefixes и names сохраняются literal:

- `PublicSiblingTests.test_tui_help_and_arguments_refuse_before_effects` — T01.
- `NativeSiblingCommitPolicyTests.test_tui_resolver_nested_and_explicit_second_checkout` — T02.
- `NativeSiblingCommitPolicyTests.test_tui_markerless_legacy_refuses_before_session_effects` — T03: actual candidate parser и mandatory-marker diagnostic, rc=3/client events=0/protected bytes unchanged относительно baseline после объявленного удаления fixture marker; не unknown-command refusal и не successful bootstrap.
- `NativeSiblingCommitPolicyTests.test_tui_engaged_missing_session_bootstraps_only_through_facade` — T04: actual schema-3 engaged cold init + ровно один terminal resume, real receipt/bridge и один native_existing header в обоих actual payload; direct low-level missing-session refusal сохраняется.
- `NativeSiblingCommitPolicyTests.test_tui_reuses_receipt_and_refreshes_current_plan_payload` — T05.
- `NativeSiblingCommitPolicyTests.test_tui_invalid_plan_session_and_foreign_receipts_are_effect_free` — T06.
- `NativeSiblingCommitPolicyTests.test_tui_process_exit_and_missing_saved_session_use_existing_checker` — T07.
- `NativeSiblingCommitPolicyTests.test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient` — T08: весь six-event Manager policy/transport chain и cold Architect init+resume tail по source-backed map ниже; шестой отдельный prerequisite, не частичный rerun assertion.
- `NativeSiblingCommitPolicyTests.test_tui_client_error_and_runtime_drift_preserve_native_outcome` — T09.
- `SiblingContractDocsTest.test_sibling_tui_template_and_f12_keep_mode_and_row_contract` — T10.

Policy success доказывают T04/T05/T08. Исторический C1 retained CMD refusal probe — baseline source/admission context, не fresh TUI proof. Для действительно нового applicable behavioral execution candidate examples/reruns сохраняют C2 preparation/C3 natural-origin prerequisites ниже; current Q8 их не запускает. Retained T03 reference: `"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -k test_tui_markerless_legacy_refuses_before_session_effects -v`. Требуется ровно один actual named test со всеми subcases/no skip/terminal rc/parity; zero-test exit 0 не proof.

### C4/Q6 + C5/Q7: полный T08 transport/phase observer и narrow rerun

Retained source: Manager CMD `scripts/planveyor/role_runtime.zsh:6427–6428` передаёт exec/resume/SID/payload в argv; Manager TUI `:6222` передаёт resume/SID/payload в argv. Architect resume `:5074/:5128` pipe-ит payload на exec/resume/SID/`-`; stdin другого helper `:6002–6004` не является CMD contract. Cold Manager/Architect init собирается в `scripts/planveyor/session_init.zsh:614/:549`, pipe на :630/:556; `_planveyor_role_prompt_body` prelude на `scripts/planveyor.zsh:2728–2734`. Existing sink `scripts/test_sibling_runbook.py:590–604` читает stdin только при literal последнем `-`; его captured empty stdin не independent OS-stdin measurement. Coder меняет только in-scope expected transport/phase assertions и existing fixture lineage, transport не selector COMMIT_POLICY; producers/sink/guards не менять.

Обязательная control boundary — первая **отдельная** строка `[ALWAYS START]` в actual captured payload. Header — только prefix до неё, raw body начинается с этой строки. Missing boundary, duplicate/empty/mismatched exact key-lines fail; raw bootstrap text, примеры и Owner answers не count-source control fields. Init и resume имеют ровно по одному nonempty current `ROLE`, `PYBIN`, `COMMIT_POLICY`, `PLANVEYOR_RUNTIME_ROOT`: actual role, trusted fixture interpreter и physical native-fixture runtime, а не frozen lifecycle host. `MANAGER_CMD` — отдельный final Manager-resume trailer. Не искать field substring по whole payload.

Expected raw init body — effective approved role-init bytes, которые actual `_planveyor_role_prompt_body <manager|architect> init` выбирает через existing `_planveyor_contract_read` с purpose `role_prompt_body` в bound native fixture context/runtime pin. В engaged context это descriptor-verified declared member `docs/tools/prompts/manager_init.md` либо `docs/tools/prompts/architect_init.md` из approved contract root: `_planveyor_contract_read` (`scripts/planveyor/contract_authority.zsh:494`) → actual bridge `contract-read` (`scripts/contract_authority_bridge.py:1142`) → `read_declared_bytes` (`scripts/contract_authority_context.py:1207`). Expected bytes получают тем же guarded selected-body read/context binding; произвольное чтение prompt file из frozen/ambient/иного runtime не oracle. Сравнить captured raw body начиная с boundary с approved bytes, нормализуя только trailing newline; не снимать member/source guards, не подменять reader и не добавлять instrumentation/helper/field. Bootstrap `Provide PLAN_PATH` — raw text, не init control field.

| Actual phase / T08 event | Header presence/absence и identity | Transport / body |
| --- | --- | --- |
| Cold Manager init / event0 | ROLE=Manager/PYBIN/runtime/policy ровно по одному; human_explicit. PLAN_PATH/PRE_STATUS_LINE/FOLLOWUPS_CAPTURE_CYCLE_ID — **ноль** header entries. Для T04 cold TUI init та же applicability, policy=native_existing. Actual init producer создаёт Manager SID/receipt через public reader. | argv[0]=exec, без resume, last argv `-`, captured stdin=payload; raw body равен effective approved manager_init bytes. Init не имеет Manager command trailer. |
| Manager CMD resume / events1,3,4 | ROLE=Manager/current literal fixture PLAN_PATH/PRE_STATUS_LINE со status Blocked/PYBIN/runtime/human_explicit ровно по одному. Cycle header ровно один только event4, zero в остальных. Public SID/receipt связывает этот resume с cold init. | argv[0]=exec, suffix resume/same Manager SID/payload, last argv=payload, не `-`; captured stdin="". Final `MANAGER_CMD=run <literal selected plan>`. |
| Manager TUI/direct resume / events2,5 | ROLE=Manager/current fixture PLAN_PATH/PRE_STATUS_LINE/PYBIN/runtime/native_existing ровно по одному; cycle header zero. Тот же Manager SID/receipt, project/runtime/session_key. | argv[0]=resume, suffix same SID/payload, captured stdin=""; final `MANAGER_CMD=run` без plan suffix, `--q`/`--merge`/queue отсутствуют. |
| Cold Architect init / первый actual Architect event после Manager chain | ROLE=Architect/PYBIN/runtime/human_explicit ровно по одному; PLAN_PATH/PRE_STATUS_LINE/cycle — **ноль** header entries даже при selected plan. Actual Architect SID/receipt public reader связан с role/project/runtime, не Manager SID. | exec без resume/last `-`/stdin=payload; raw body равен effective approved architect_init bytes. |
| Architect initial-draft resume / следующий actual Architect event | ROLE=Architect/current fixture PLAN_PATH/PRE_STATUS_LINE с selected Architect initial draft status/PYBIN/runtime/human_explicit ровно по одному, cycle zero. Resume использует **тот же Architect SID**, который выдал real init/public receipt. | exec/resume/Architect SID/`-`, actual stdin=payload; отдельный retained Architect resume contract. |

Whole T08 обязан получить ровно шесть Manager events и один actual cold init; policy sequence строго human_explicit,human_explicit,native_existing,human_explicit,human_explicit,native_existing. Затем реально достигается cold Architect init и его same-role resume tail; пустой tail/vacuous loop недопустим. Phase подтверждается actual argv/init body/public SID/receipt→resume связкой, не одним event index. Current plan/status проверяются на **каждом resume**, а их отсутствие — в **каждом init header**; raw body не field carrier. Receipt bytes и public `planveyor_session manager|architect` подтверждают role/project/runtime и same identity до/после chain; metadata-bearing whole pointer не SID. Forged/mutable/invalid frame refusal regressions сохраняются.

Шестой narrow rerun после retained origin и первых пяти prerequisites: `"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -k test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient -v`. Нужно ровно Ran 1 test/OK, все assertions/subcases/phase rows и достигнутый cold Architect init+resume tail, no skip, actual terminal rc=0 и before/after/final parity с supplementary dependency readback rc=0 до следующей команды. V2 partial T08 FAIL/43 other ok и C5 pre-edit static gap не закрывали этот proof; V5 whole-T08/prerequisites уже завершены по Q8 Evidence. Current validation-only delta не требует нового rerun. При red/missing/skip/UNKNOWN остановить sequence, сохранить actual phase/header/body/approved source/case/rc/parity, без producer/sink/guard repair, удаления assertions, waiver или blind full rerun.

### Candidate verification checkout (C2/Q4)

Applicability: retained recipe для действительно нового затронутого scoped execution. В current Q8 policy-only restamp не выполнять, old V5 manifest/lifecycle hashes не менять; короткий static artifact/delta readback не является новой candidate preparation/parity.

Trusted launch задаёт один `$PYBIN`, trusted PATH и прежний supplied `$TMPDIR`; TMPDIR не переназначать. Shell/tool cwd остаётся physical selected source project, без login shell; только initial stdlib/Git preparation ниже читает source из этого cwd. После clone все candidate Python commands, включая parity, идут через C3 explicit chdir+fresh exec; tests используют canonical -s scripts из candidate cwd. Это inline transient preparation по existing clone/current-byte/commit pattern `PublicSiblingTests.setUpClass`, не новый checked-in helper. Общий copied runtime остаётся настоящим: никакого injected client/stats code. Пока идут runs, не менять source plan/draft/семь targets; logs/manifest/patch держать в workspace, durable summary записать после final parity. Current lifecycle hashes снимаются заново после последнего restamp/receipt и Coder assertion correction, V1/V2 hashes не переносить. При любом non-zero preparation/check остановиться, следующие блоки не выполнять.

Invocation safeguard из закрытого 13:31→13:35 same-contract incident сохраняется: extractor распознаёт opening/closing Markdown fences только как отдельные строки, не literal triple-backticks внутри embedded Python regex. До execution сверить полный block и оба closing PY heredocs; static-only AST embedded/inline Python и zsh -dfn всех четырёх shell blocks проверяет syntax без запуска preparation/observer/tests. Inline string не закрывает fence. Truncation/syntax rc≠0 останавливает sequence до clone/next block; отсутствие candidate/manifest означает parity NOT_AVAILABLE, а не green. Transient extractor не становится checked-in helper или новым target.

Literal context inventory в `context_paths` ниже открыт по plan source refs: physical facade и low-level role runtime; consumer admission; authority bootstrap/loader/children/bridge/context/runtime/snapshot и file identity; oracle/lint; contextual suites/support, package-import test_docs_closeout и его docs_closeout guard; Make/interpreter/doc-lint/full verification entrypoints и retained closeout consumer. Inventory33 = 24 read-only context + семь targets + два lifecycle files; новые два context paths не получают edit authority. C5 supplementary dependency `scripts/planveyor/session_init.zsh` проверяется отдельно по source/copy/HEAD SHA-256 и mode в тех же inline preparation/parity: она не входит в primary inventory/file count, не overlay-ится и не stage-ится. Это bounded transient readback в existing snapshot, не новая durable schema/helper/target. Existing native fixture source-lineage assertion до bootstrap сравнивает этот producer с verified candidate; missing/drift/foreign origin останавливает sequence без copy/fallback. Другой staged/unstaged tracked delta требует owning-role triage; untracked/ignored files, original .git, credentials и session state не копировать.

```zsh
: "${PYBIN:?trusted interpreter required}" "${TMPDIR:?supplied TMPDIR required}"
CANDIDATE_VERIFY_WORKSPACE="$(mktemp -d "$TMPDIR/sibling-tui-verify.XXXXXXXX")"
CANDIDATE_VERIFY_ROOT="$CANDIDATE_VERIFY_WORKSPACE/candidate"
CANDIDATE_VERIFY_HOME="$CANDIDATE_VERIFY_WORKSPACE/home"
mkdir "$CANDIDATE_VERIFY_HOME"
candidate_verify_env=(env -i PATH="$PATH" HOME="$CANDIDATE_VERIFY_HOME" TMPDIR="$TMPDIR" TMPPREFIX="$TMPDIR/zsh" PYBIN="$PYBIN" PYTHONDONTWRITEBYTECODE=1 LC_ALL=C)
"${candidate_verify_env[@]}" "$PYBIN" -B - "$PWD" "$CANDIDATE_VERIFY_ROOT" <<'PY'
import hashlib, json, os, pathlib, re, shutil, stat, subprocess, sys
source, copied = map(pathlib.Path, sys.argv[1:])
workspace = copied.parent
supplied_tmp = pathlib.Path(os.environ['TMPDIR']).resolve(strict=True)
test_home = pathlib.Path(os.environ['HOME']).resolve(strict=True)
assert source == source.resolve(strict=True) and not source.is_symlink()
assert workspace == workspace.resolve(strict=True) and workspace.parent == supplied_tmp
assert not workspace.is_symlink() and not copied.exists() and test_home.parent == workspace
assert not supplied_tmp.is_relative_to(copied) and not test_home.is_relative_to(copied)
targets = ['scripts/sibling_runbook.py', 'scripts/planveyor.zsh',
           'scripts/test_sibling_runbook.py', 'scripts/test_sibling_contract_docs.py',
           'copier_template/AGENTS.md.jinja', 'docs/release_backlog.md',
           'docs/followups/release_backlog.md']
lifecycle = ['docs/plans/261015_2304_sibling_tui_native_entry.md',
             'docs/code_drafts/261015_2304_sibling_tui_native_entry__code_draft.md']
context_paths = ['bin/planveyor', 'scripts/planveyor/role_runtime.zsh',
    'scripts/consumer_contract.py', 'scripts/contract_authority_bootstrap.py',
    'scripts/contract_authority_shell_loader.zsh', 'scripts/contract_authority_children.py',
    'scripts/contract_authority_bridge.py', 'scripts/contract_authority_context.py',
    'scripts/contract_authority_runtime.py', 'scripts/contract_authority_snapshot.py',
    'scripts/fs_object_identity.py', 'scripts/plan_status_oracle.py', 'scripts/plan_lint.py',
    'scripts/test_planveyor_bare_entrypoints.py', 'scripts/test_contract_authority_shell.py',
    'scripts/test_docs_closeout.py', 'scripts/docs_closeout.py',
    'scripts/test_contract_authority_support.py', 'scripts/test_support/process_contract_fixtures.py',
    'Makefile', 'scripts/_pybin.sh', 'scripts/run_doc_lint.sh', 'scripts/verify_suite.py',
    'scripts/sibling_closeout.py']
inventory = targets + lifecycle + context_paths
assert len(context_paths) == 24 and len(inventory) == len(set(inventory)) == 33
git_env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS='0')
def git(root, *args, env=git_env):
    return subprocess.check_output(['git', '-C', str(root), '-c', 'core.hooksPath=/dev/null',
        '-c', 'commit.gpgSign=false', *args], env=env)
def fingerprint(path):
    assert path.resolve(strict=True) == path and stat.S_ISREG(path.lstat().st_mode), str(path)
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'mode': stat.S_IMODE(path.stat().st_mode)}
def git_file(root, name):
    path = pathlib.Path(git(root, 'rev-parse', '--git-path', name).decode().strip())
    return fingerprint((root / path).resolve())
def snapshot():
    return {'head': git(source, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip(),
        'index': git_file(source, 'index'), 'head_file': git_file(source, 'HEAD'),
        'status': hashlib.sha256(git(source, 'status', '--porcelain=v1', '--untracked-files=no')).hexdigest(),
        'diff': hashlib.sha256(git(source, 'diff', '--binary', 'HEAD', '--', *targets)).hexdigest(),
        'files': {p: fingerprint(source / p) for p in inventory}}
assert pathlib.Path(git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == source
changed = set()
for args in [('diff', '--name-only', '-z'), ('diff', '--cached', '--name-only', '-z')]:
    changed.update(p.decode() for p in git(source, *args).split(b'\0') if p)
assert changed <= set(targets), sorted(changed - set(targets))
meta = json.loads(re.search(r'```json\s*(.*?)\s*```', (source / lifecycle[1]).read_text(), re.S)[1])['code_draft_meta']
assert [p['path'] for p in meta['targets']] == targets and meta['deleted_paths'] == []
before = snapshot()
readonly_dependency = 'scripts/planveyor/session_init.zsh'
def head_fingerprint(root, revision, relative):
    rows = git(root, 'ls-tree', '-z', revision, '--', relative).split(b'\0')
    assert len(rows) == 2 and rows[1] == b'', 'missing/ambiguous dependency HEAD member'
    entry, name = rows[0].split(b'\t', 1)
    mode, kind, oid = entry.split()
    assert name.decode() == relative and kind == b'blob' and mode in (b'100644', b'100755')
    return {'sha256': hashlib.sha256(git(root, 'cat-file', 'blob', oid.decode())).hexdigest(),
            'mode': int(mode, 8) & 0o777}
dependency_head = head_fingerprint(source, before['head'], readonly_dependency)
assert fingerprint(source / readonly_dependency) == dependency_head, 'dependency source differs from baseline HEAD'
(workspace / 'source.patch').write_bytes(git(source, 'diff', '--binary', 'HEAD', '--', *targets))
git(source, 'clone', '--quiet', '--no-local', str(source), str(copied))
assert git(copied, 'rev-parse', 'HEAD').decode().strip() == before['head']
for relative in targets + lifecycle:
    destination = copied / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert not destination.is_symlink() and destination.parent.resolve().is_relative_to(copied)
    shutil.copy2(source / relative, destination, follow_symlinks=False)
assert {p: fingerprint(copied / p) for p in inventory} == before['files']
assert snapshot() == before
assert head_fingerprint(copied, before['head'], readonly_dependency) == dependency_head
assert fingerprint(source / readonly_dependency) == fingerprint(copied / readonly_dependency) == dependency_head, 'dependency clone/HEAD parity lost'
git(copied, 'add', '--', *targets, *lifecycle)
commit_env = dict(git_env, GIT_AUTHOR_NAME='Candidate fixture',
    GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='Candidate fixture',
    GIT_COMMITTER_EMAIL='fixture@example.invalid')
git(copied, 'commit', '--quiet', '--allow-empty', '-m', 'Disposable candidate verification', env=commit_env)
assert copied.resolve(strict=True) == copied and not copied.is_symlink()
assert pathlib.Path(git(copied, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == copied
assert (copied / '.git').is_dir() and not (copied / '.git').is_symlink()
fixture_head = git(copied, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
assert not git(copied, 'status', '--porcelain=v1') and snapshot() == before
assert fingerprint(source / readonly_dependency) == fingerprint(copied / readonly_dependency) == dependency_head
dependency_readback = {'path': readonly_dependency, 'head': dependency_head,
    'source': fingerprint(source / readonly_dependency), 'copy': fingerprint(copied / readonly_dependency)}
manifest = {'source_root': str(source), 'copy_root': str(copied), 'source': before,
            'fixture_head': fixture_head, 'targets': targets, 'inventory': inventory,
            'inventory_count': len(inventory), 'readonly_dependency': dependency_readback}
(workspace / 'snapshot.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
print(json.dumps({'source_head': before['head'], 'fixture_head': fixture_head,
                  'parity': True, 'inventory': before['files'],
                  'readonly_dependency': dependency_readback}, sort_keys=True))
PY
```

Перед и после каждой candidate команды ниже выполнить `candidate_verify_parity`; failure делает её result stale/неприемлемым и останавливает дальнейшие runs. C3 wrapper меняет cwd только дочернему процессу и exec-ит fresh trusted Python; namespace/cache прежнего observer не переносится в следующий test. Parity дополнительно связывает actual child cwd с manifest copy_root. Manifest содержит private local roots и остаётся transient; в review переносить только repo-relative inventory/hash/mode, source diff/revisions, actual case/exit и protected-delta summary.

```zsh
candidate_verify_run=("${candidate_verify_env[@]}" "$PYBIN" -B -c 'import os,sys; os.chdir(sys.argv[1]); os.execv(sys.executable,[sys.executable,"-B",*sys.argv[2:]])' "$CANDIDATE_VERIFY_ROOT")
candidate_verify_parity() {
  "${candidate_verify_run[@]}" - "$CANDIDATE_VERIFY_WORKSPACE/snapshot.json" <<'PY'
import hashlib, json, os, pathlib, stat, subprocess, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text())
source, copied = pathlib.Path(m['source_root']), pathlib.Path(m['copy_root'])
assert m['inventory_count'] == len(m['inventory']) == 33
assert pathlib.Path.cwd().resolve(strict=True) == copied, 'child cwd differs from manifest candidate root'
git_env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS='0')
def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], env=git_env)
def fingerprint(path):
    assert path.resolve(strict=True) == path and stat.S_ISREG(path.lstat().st_mode), str(path)
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mode': stat.S_IMODE(path.stat().st_mode)}
def git_file(name):
    path = pathlib.Path(git(source, 'rev-parse', '--git-path', name).decode().strip())
    return fingerprint((source / path).resolve())
now = {'head': git(source, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip(),
    'index': git_file('index'), 'head_file': git_file('HEAD'),
    'status': hashlib.sha256(git(source, 'status', '--porcelain=v1', '--untracked-files=no')).hexdigest(),
    'diff': hashlib.sha256(git(source, 'diff', '--binary', 'HEAD', '--', *m['targets'])).hexdigest(),
    'files': {p: fingerprint(source / p) for p in m['inventory']}}
assert now == m['source'], 'source drift or original index/HEAD changed'
assert copied == copied.resolve(strict=True) and not (copied / '.git').is_symlink()
assert pathlib.Path(git(copied, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == copied
assert git(copied, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip() == m['fixture_head']
assert not git(copied, 'status', '--porcelain=v1'), 'verification checkout is dirty'
assert {p: fingerprint(copied / p) for p in m['inventory']} == now['files'], 'copy parity lost'
readonly_dependency = 'scripts/planveyor/session_init.zsh'
def head_fingerprint(root, revision, relative):
    rows = git(root, 'ls-tree', '-z', revision, '--', relative).split(b'\0')
    assert len(rows) == 2 and rows[1] == b'', 'missing/ambiguous dependency HEAD member'
    entry, name = rows[0].split(b'\t', 1)
    mode, kind, oid = entry.split()
    assert name.decode() == relative and kind == b'blob' and mode in (b'100644', b'100755')
    return {'sha256': hashlib.sha256(git(root, 'cat-file', 'blob', oid.decode())).hexdigest(),
            'mode': int(mode, 8) & 0o777}
dependency_head = head_fingerprint(source, now['head'], readonly_dependency)
assert head_fingerprint(copied, now['head'], readonly_dependency) == dependency_head
dependency_readback = {'path': readonly_dependency, 'head': dependency_head,
    'source': fingerprint(source / readonly_dependency), 'copy': fingerprint(copied / readonly_dependency)}
assert dependency_readback == m['readonly_dependency'], 'dependency baseline changed'
assert dependency_readback['source'] == dependency_readback['copy'] == dependency_head, 'dependency source/copy/HEAD mismatch'
print(json.dumps({'parity': True, 'inventory_count': 33,
    'readonly_dependency': dependency_readback, 'original_index_head': 'unchanged'}, sort_keys=True))
PY
}
candidate_verify_parity
```

### Narrow prerequisites, suites и gates

Applicability: reference выполненного V5 contract; current Q8 policy-only handoff не запускает следующие candidate commands повторно. Governing Q8 policy выбирает только короткие artifact/delta gates; новый scoped запуск требует фактической затронутой behavior/source/test/proof delta, full discovery запрещён.

Команды ниже — последовательность отдельных executions, блок целиком или параллельно не запускать. Перед каждой выполнить parity, дочитать именно actual terminal return code/output, затем выполнить parity даже при non-zero и только после проверки результата переходить к следующей. Живой process handle без terminal readback = UNKNOWN, следующая команда запрещена. Первый red/missing/skip/UNKNOWN останавливает sequence до следующих narrow/suites/Make; сохранить origin/case/diagnostic/actual rc и before/after parity, без silent retry/guard repair. `env -i` не наследует root/Git/Codex/Python/ZDOTDIR selectors; hostile case inputs задают только tests. Existing external client sinks и authority producers не подменять общим stub.

Первый import-only observer не исполняет fixture/lifecycle/client calls: natural imports должны показать единственный copied namespace scripts, exact package/direct file origins, обе authority aliases как один object и callable admission. Observer только читает sys.path/sys.modules, ничего туда не записывает; никакого PYTHONPATH/-t/source substitution, нового scripts/__init__.py или module-cache переноса. Standard initialization самих existing modules сохраняется. Exit 0 этого preflight не заменяет authority checkpoint или native tests.

Далее шесть narrow commands в указанном порядке. Для каждого требуется **ровно один** literal named test, `Ran 1 test`, `OK`, все assertions/subcases и no skip, actual terminal rc=0 и before/after parity. Первые два — BareEntrypointsDoctorTests: copied facade help rc=0; inside_product rc=1 и external-home missing_cli rc=127 с unchanged protected surfaces. Третий — existing ContractAuthorityShellIntegrationTests.test_public_continuation_checkpoint_revalidates_fresh_bundle_and_replays_without_write, actual public continuation/authority composition на package-import boundary. Четвёртый/пятый — corrected native T04/T06: public session reader и timestamp/explicit open seed, real engaged init/resume/refusal assertions. Шестой — весь existing T08 по C4/Q6 + C5/Q7 maps выше: six-event Manager chain, init stdin/Manager CMD+TUI resume argv/Architect resume stdin, common current headers в обеих phases, init plan/status/cycle absence и current plan/status на каждом resume, exact cycle map, approved guarded raw init-body source и real init→public SID/receipt→same-role resume identity, реально достигнутый Architect tail. До bootstrap fixture-lineage producer readback обязателен; supplementary source/copy/HEAD SHA+mode проверяется при каждом existing parity. Zero tests, неверный case, partial/empty tail или skip при exit 0 не разрешают следующую команду. Только после applicable prerequisites — затронутые declared scoped suites/doc-type строго по одному на том же snapshot; V5 полный scoped набор уже green. Full discovery не per-plan gate и сейчас запрещён Q8.

```zsh
"${candidate_verify_run[@]}" -c 'from pathlib import Path; import sys, scripts
import scripts.test_contract_authority_shell as shell_tests
import scripts.test_docs_closeout as docs_tests
import contract_authority_context as authority
root=Path.cwd().resolve(strict=True)
assert {Path(p).resolve(strict=True) for p in scripts.__path__} == {root/"scripts"}
for module, relative in ((shell_tests,"scripts/test_contract_authority_shell.py"),(docs_tests,"scripts/test_docs_closeout.py"),(docs_tests.MODULE,"scripts/docs_closeout.py"),(authority,"scripts/contract_authority_context.py")):
    assert Path(module.__file__).resolve(strict=True) == root/relative, relative
assert sys.modules.get("scripts.contract_authority_context") is authority
assert sys.modules.get("contract_authority_context") is authority
assert callable(docs_tests.MODULE.classify_followups_bootstrap_admission)
print("origin preflight: cwd=candidate; package/direct origins=ok; aliases=same; admission=callable")'
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_planveyor_bare_entrypoints.py -k test_canceled_family_is_absent_from_public_commands_and_help -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_planveyor_bare_entrypoints.py -k test_codex_home_adapter_rejects_invalid_paths_and_missing_cli_without_mutation -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_contract_authority_shell.py -k test_public_continuation_checkpoint_revalidates_fresh_bundle_and_replays_without_write -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -k test_tui_engaged_missing_session_bootstraps_only_through_facade -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -k test_tui_invalid_plan_session_and_foreign_receipts_are_effect_free -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -k test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_runbook.py -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_sibling_contract_docs.py -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_planveyor_bare_entrypoints.py -v
"${candidate_verify_run[@]}" -m unittest discover -s scripts -p test_contract_authority_shell.py -v
"${candidate_verify_env[@]}" make -C "$CANDIDATE_VERIFY_ROOT" PYBIN="$PYBIN" doc-lint
"${candidate_verify_env[@]}" make -C "$CANDIDATE_VERIFY_ROOT" PYBIN="$PYBIN" typecheck
# Full discovery/repeat/equivalent здесь отсутствует: current Q8 Owner policy запрещает новый запуск.
```

Отдельно из original selected source project — только scoped artifact hygiene и frozen lifecycle readbacks. Эти короткие команды применимы к current Q8 policy-only delta и не являются повтором candidate behavior proof; supplied trusted launch и facade prefix сохраняются:

```zsh
PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/plans/261015_2304_sibling_tui_native_entry.md --root docs/code_drafts/261015_2304_sibling_tui_native_entry__code_draft.md --root copier_template/AGENTS.md.jinja --root docs/release_backlog.md --root docs/followups/release_backlog.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/261015_2304_sibling_tui_native_entry.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261015_2304_sibling_tui_native_entry.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_status_oracle.py docs/plans/261015_2304_sibling_tui_native_entry.md --json
```

Success для current Q8 = validation-policy-only text синхронизирован с plan/closed Q8, short applicable artifact/delta gates actual rc0, source/test/context/HEAD/index unchanged и V5 exact-snapshot proof сохранён с честной qualification. V5 origin/шесть narrow/native44/docs23/bare84/authority38/doc-type actual run/sink/post-parity rc0/no relevant skip/whole Architect tail закрывают выполненный scoped contract; reviews/exact closeout ещё downstream. Full discovery/verify-full/equivalent запрещены сейчас и не являются условием review/Done/exact commit/terminal docs closeout. Historical Make run/sink/post=UNKNOWN, log-only GREEN/10 genuine non-Git skips и pre-recovery UNKNOWN не переименовываются в PASS и не превращаются в automatic STOP/rerun/GO request.

При действительно новом applicable scoped execution success = actual terminal rc0/all affected assertions/subcases/no relevant skip/required identity-tail/protected-state/parity, без zero-test/partial-tail false green. Declared C2–Q7 observer/launch recipes сохраняются; affected scoped red/missing/skip/UNKNOWN требует exact owning-role triage. Все temporary files под прежним supplied TMPDIR. Existing temporary_git_root — independent Git repository, не non-Git boundary; десять historical non-Git skips остаются unexecuted coverage вне no-skip T01–T10, external TMPDIR/discovery bypass/support edits не разрешены. Потеря existing handle/control plane — STOP без recovery/replacement/spawn/rebinding.

### Current Q8 rerun / exec handoff

- Mode: reuse-thread
- Context source: current plan/closed Q8/Validation policy, V5 Evidence 2026-10-17 12:57–12:59 и historical executed source/test snapshot; current plan/draft policy hashes qualified separately.
- Prompt: сохранить implementation и V5 scoped proof; current delta — только policy text. Выполнить короткие artifact/delta checks и обычный handoff к review без clone/origin/narrow/multi-hour suites/doc-type rerun/full discovery. Historical Make UNKNOWN/log-only GREEN/10 contextual skips/pre-recovery UNKNOWN не исправлять; old manifest не обновлять ради fake lifecycle parity. Реальная новая behavioral delta требует affected scoped selector/owning triage, не test-all.
- Command: "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/261015_2304_sibling_tui_native_entry.md
- Expected artifact: `docs/code_reviews/261015_2304_sibling_tui_native_entry.md`; single review host, independent risk/contracts lanes.

## Critical invariants / traps / bypass paths

- `Invariant: one current clean verification snapshot`. Trap: dirty source/frozen runtime, instrumented fixture как общего REPO_ROOT, inherited selector или V1/V2 history выглядит current green. Proof: actual HEAD+exact overlay, inventory33 SHA-256/mode parity, supplementary readonly session_init source/copy/HEAD SHA+mode и pre-bootstrap fixture lineage, synthetic fixture commit, independent physical root, physically external TMPDIR/home и env -i; manifest-bound cwd/parity/original index/HEAD/whole tracked status до/после каждой команды. Standalone-fence extraction и full-body syntax checks предотвращают preparation truncation; missing manifest не parity PASS. Behavioral drift/applicable red/missing/skip/UNKNOWN останавливает затронутую execution sequence; current policy-only lifecycle delta сохраняет V5 proof и проверяется отдельно, не выдаётся за новый inventory33 parity. Historical full UNKNOWN не новый gate; guards/targets не ослабляются.
- `Invariant: one natural namespace per fresh candidate child`. Trap: copied -s при source cwd смешивает package/direct origins и оставляет partial docs_closeout module; preflight cache/alias repair скрывает отказ. Proof: explicit chdir+exec нового trusted Python, canonical -s scripts, observer namespace/origins/natural aliases/callable без sys.path/sys.modules/PYTHONPATH/-t repairs; оба C2, exact authority checkpoint, corrected T04/T06 и sixth full T08 по одному/no skip/terminal/parity строго до applicable scoped suites/doc-type по Q8. Каждый вызов fresh process, first red останавливает sequence; import-only green не является actual checkpoint/native или T08-tail proof.
- `Invariant: source-backed phase, channel and policy`. Trap: each-payload wording требует resume fields от init, raw bootstrap mention выглядит control field, arbitrary prompt copy выглядит expected source, index/empty tail выглядит genuine init proof. Proof: первая standalone boundary обязательна; common ROLE/PYBIN/policy/runtime exact one в init/resume, init plan/status/cycle zero, current plan/status exact one на каждом resume/cycle только exact CMD. Approved guarded init body/source/context/runtime pin и public same-role init SID/receipt→resume identity закрывают phase; cold init stdin, CMD/TUI resume argv/captured stdin="", Architect resume actual stdin сохраняются. Six Manager events/policies и реально исполненный Architect tail проходят whole sixth T08; runtime/sink/guards не меняются, channel не COMMIT selector. First red/partial/skip/UNKNOWN останавливает expensive sequence.
- `Invariant: current invocation owns policy`. Trap: green parser/source grep при stale human header на TUI или env-selected policy. Proof: T04/T05/T08 actual init/resume argv/payload с ровно одним header; CMD/Architect/direct-native — обязательные alternate paths; invalid local frame отказывает до effects. T03 не emit-ит client payload и не доказывает successful policy propagation.
- `Invariant: one selected entity and native refusal`. Trap: markerless legacy context ошибочно считается sibling admission, пропавший plan pointer создаёт session либо wrong-root receipt заменяется новым. Proof: T03 specific marker refusal/client events=0/protected baseline, T02/T04/T06/T07 actual checker/receipt и protected before/after inventory; markerless target, explicit missing session, malformed checker/receipt и invalid plan — разные subcases. Schema-3 engaged cold init принадлежит только T04.
- `Invariant: native outcome remains observable`. Trap: fake rc=0/закрытое окно или поздний helper скрывает client error/drift и выдаёт Done/пять живых handles. Proof: T09 native rc/stderr/posthooks, T07 bounded process loss; T10 checks wording only, current semantic closeout и subsequent docs gate ещё должны дать настоящие downstream owners.

## Assumptions / risks

- Actual fixtures создают disposable committed Git repositories и synthetic HOME только под supplied TMPDIR; это не живая установка или правка глобальной configuration.
- Provider-free sink доказывает adapter composition/transport; actual interactive account approvals и five-handle liveness этим не заявляются. Новая Э4а rehearsal, SQL, Б, F7/F13/rebinding, push/publication исключены.
- Frozen runtime не редактируется. Если выбранные обязательные proof lanes требуют новый support/runtime target, Coder фиксирует gap и возвращает к Architect до widening.
- Руководства RU/EN принадлежат назначенному автору. Их concurrent content не переносить в этот bundle и не чинить broad unrelated failures молча.

## Notes for Coder

- Plan важнее sketch; semantic изменения/questions пишутся в plan, routing — к Architect.
- Existing source paths уже materialized; path-tracking stubs и `planned_new_paths` не нужны.
- Code draft metadata — exact seven targets, никакого parent-directory glob. Origin plan, draft, review и explicit support assets — separate lifecycle members.
- Current Q8 task — только validation-policy text restamp/короткие artifact-delta gates. Implementation/observer corrections и V5 origin/шесть prerequisites/четыре scoped suites/doc-type завершены; повторов clone/probes/tests/Make из-за text-only delta нет. C2–Q7 phase/header/approved guarded body/public identity/transport/fixture-lineage recipes и seven targets сохраняются. Новый full/repeat/equivalent запрещён; publication-wide будущая проверка требует отдельного decomposition plan с прежней Opus work и явного Owner consent. Historical Make UNKNOWN/log-only GREEN/10 contextual skips/pre-recovery UNKNOWN остаются квалифицированными фактами. Review/Done/exact commit/terminal docs family выполняют обычные downstream owners без нового full gate.

## Review stamps (append-only)

- [2026-10-16] (Planner) Создан executable contract из current plan, validated oracle и opened source/fixture surfaces; candidate/live behavior этим draft не проверено.
- [2026-10-16] (Planner, Q3/C1 restamp) Применён closed Architect disposition: T03 markerless refusal с новым literal selector, T04 engaged init/resume и policy invariants T04/T05/T08; narrow rerun и read-only admission inventory синхронизированы. Seven targets/required ref/review route, genuine non-Git/T05/F12 boundaries сохранены; candidate/live proof не запускался.
- [2026-10-16] (Planner) NO SUGGESTIONS (reviewed после Q3/C1 restamp; дополнительных правок executable contract не требуется).
- [2026-10-16] (Planner, C2/Q4 restamp) Применён closed Q4: copy-paste clean clone/HEAD+exact overlay/fixture commit и source/copy hash+mode inventory, original index/HEAD protection, allowlisted child env, physically external supplied TMPDIR/home. Два narrow C2 cases требуют по одному named test без skip; все suites/Make gates/T03 reruns используют copied candidate. Seven targets/required ref/T03-T04/T05/F12/non-Git boundaries и один review host сохранены; historical exits UNKNOWN. Preparation и suites этим Planner не выполнялись.
- [2026-10-16] (Planner) NO SUGGESTIONS (reviewed после C2/Q4 restamp; новый semantic выбор или дополнительный target не требуется).
- [2026-10-16] (Planner, C3/Q5 restamp) Применён closed Q5 во всех current executable surfaces: explicit child chdir+fresh exec и canonical -s scripts, inventory33/manifest/parity cwd binding, natural package/direct origin/alias/callable observer, оба C2 и exact authority/T04/T06 narrow prerequisites, затем четыре suites/Make строго sequential/stop-first с actual terminal rc/parity. C2 clone/overlay/env/fixture commit, seven targets/required ref, T03-T04/T05/F12/non-Git boundaries и один review host сохранены. Product targets не менялись, clone/probes/tests не исполнялись; V1 prior bytes/revised tests not_run/pre-recovery UNKNOWN разделены.
- [2026-10-16] (Planner) NO SUGGESTIONS (reviewed после C3/Q5 restamp; дополнительный product/core/target выбор не требуется).
- [2026-10-16 16:16] (Planner, C4/Q6 restamp) Closed Q6 перенесён во все current observer/targeted steps/Commands/invariants/rerun surfaces: retained Manager CMD argv/TUI argv/Architect resume stdin, full six-event Manager policies/headers/plan-status/cycle/same receipt и реальный cold Architect init+resume tail. Полный existing T08 materialized шестым sequential named prerequisite после retained origin/five, Ran 1/all assertions/no skip/actual terminal rc/parity до full suites/Make. Standalone-fence extraction/full-body syntax safeguards, C2/C3 clone/overlay/env-i/fresh child cwd/exec/inventory33/manifest/original index+HEAD+tracked-status parity сохранены. Семь targets/derived MAD ref неизменны; product/test/runtime не правились, execution не запускалась. V2 native44 rc1/43 ok и NOT_RUN других lanes не acceptance; corrected T08/current rerun not_run.
- [2026-10-16 16:16] (Planner) NO SUGGESTIONS (reviewed после C4/Q6 restamp; нового semantic/core/target решения не требуется).

- [2026-10-16 17:09] (Planner, C5/Q7 restamp) Closed Q7/current Architect CENSOR перенесены во все current observer/targeted steps/Commands/invariants/rerun surfaces: explicit phase/header-vs-body map, approved guarded init-body source, positive init absence и resume presence, genuine cold init→public receipt→same-role resume identity. Supplementary readonly session_init source/copy/HEAD SHA+mode в existing preparation/parity и native fixture lineage не меняет inventory33/семь targets/overlay/staging; C2/C3/Q6 и все шесть narrow/all four suites/Make stop-first сохранены. Product/test/runtime не правились, clone/probes/tests не исполнялись; C5 current execution NOT_RUN, V2 exact partial/V1 prior bytes/pre-recovery UNKNOWN не acceptance.
- [2026-10-16 17:09] (Planner) NO SUGGESTIONS (reviewed после C5/Q7 restamp; нового Owner/core/target выбора не требуется).

- [2026-10-17 13:20] (Planner, Q8 validation-policy-only restamp) Последнее правило Owner подтверждено; governing policy/Tests/Commands/Success/rerun согласованы с closed Q8. Новые verify-full/repeats/equivalent full discovery запрещены, не per-plan/review/Done/exact-commit/docs gate; будущий publication-wide test-all требует отдельного плана с учётом Opus и явного Owner consent. V5 executed source/test scoped proof сохранён; historical Make UNKNOWN/log-only/skips и run-set lifecycle hashes не переписаны. Prep/parity/phase/transport recipes и implementation bytes unchanged; только policy applicability и короткие artifact/delta checks, без behavioral rerun/decomposition.
- [2026-10-17 13:20] (Planner) NO SUGGESTIONS (reviewed после Q8 restamp; нового Owner/core/product выбора не требуется).

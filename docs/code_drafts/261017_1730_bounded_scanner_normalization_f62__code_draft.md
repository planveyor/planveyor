# Code draft: Ограниченная нормализация scanner и перенос F62

**Date:** 2026-10-17 21:27
**Cluster:** process
**Related plan:** `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`
**Author role:** Planner
**Status:** draft
**Kind:** Planner executable contract; accepted Q4 source/proof retained

## Purpose

Довести принятый scanner/F62 contract до реализации в четырёх exact files: один общий private marker matcher, finite static views с исходными spans, always-on public policy F62 и адресный proof обоих lanes. Этот Markdown сохраняет accepted Q4 operational source; product implementation принадлежит Coder.

## Meta (machine-readable JSON)

```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261017_1730_bounded_scanner_normalization_f62.md",
    "cluster": "process",
    "targets": [
      {
        "path": "scripts/oss_release_scan.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_oss_release_scan.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_sibling_contract_docs.py",
        "kind": "py"
      },
      {
        "path": "docs/tools/oss_evidence_selection.md",
        "kind": "doc"
      }
    ],
    "deleted_paths": [],
    "machine_authority_decision_ref": {
      "applicability": "not_applicable",
      "reason_code": "unchanged_structured_consumer",
      "carrier_sha256": "a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39"
    }
  }
}
```

Это единственный writable implementation/doc inventory. Plan, этот draft, единственный review artifact и explicit review assets — отдельные lifecycle members; origin plan не является current-review target. `scripts/verify_suite.py`, `scripts/test_verify_suite.py`, CI/Make и manifest/TUI carriers остаются read-only. Semantic MAD core принадлежит Architect и не копируется в draft; здесь только derived binding к свежему sole-carrier oracle readback.

## Provenance / session context

- Source plan provenance: `docs/plans/261017_1730_bounded_scanner_normalization_f62.md`; execution seed продолжен Planner после Architect, current facts получены через canonical provenance helper.
- Relation: `continued-here`
- Thread ID: `N/A (why=private operator identity is not published)`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty; native handle is independently supervised)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-17T18:24:04Z`

Canonical helper был прочитан в текущем intake; отсутствующий SID не заменяется handle из chat/memory. Public disclosure policy исходного plan сохранена; private paths/IDs/markers здесь не публикуются.

## Reviewability preflight receipt

- `proof-path class`: существующий scanner module + адресные unittest/CLI lanes; execution — exact accepted Q4 one-off body ниже, без нового launcher.
- `mandatory primary lane`: T1 — весь `test_oss_release_scan`, synthetic normalization/static-fragment/source-span/boundary/masking matrix и прежние regression cases.
- `mandatory non-primary carrier / contextual lane`: T2 — actual delivered-file F62 consumer и три controls обоих lanes; T3 — только `test_verify_suite.ScannerInputErrorTests`; T4 — public-copy generic CLI с unset dictionary.
- `exact helper path + support files`: `scripts/oss_release_scan.py::marker_findings(text, rel, scope, rules, *, source_kind="content")` — новый API внутри existing file; mapped-view/span support остаётся внутренним в том же module. Existing `load_marker_rules`, `literal_pattern`, `author_pattern`, `_line_findings`, `_path_findings`, `safe_path`, `scan` — integration points, без отдельного support file.
- `dependent tests / dependent docs / known consumer paths`: mutable tests/doc названы в metadata; read-only consumers — `Makefile::oss-release-scan`, `.github/workflows/checks.yml::Scan public contents`, `scripts/verify_suite.py::PortabilityModule.check_oss_scan_*`/`PERSONAL_PATH_RE`, `scripts/test_verify_suite.py::ScannerInputErrorTests` и explicit archive CLI из evidence policy. `Finding`/JSON/category/severity/CLI0|1|2 contract не меняется.
- `preconditions / seed-discovery`: trusted task `"$PYBIN"`/PATH/TMPDIR и immutable external runtime; accepted core/qualifier/proof ниже неизменны. Fixtures — disposable temporary Git/text roots и synthetic external marker files вне fixture root; checked-in samples, real dictionary, provider/account discovery не нужны. Public commands явно unset `PLANVEYOR_OSS_SCAN_MARKERS`.
- `reroute rule`: первый unexpected nonzero/timeout/error/lost receipt — STOP suffix без replay; недостаточный addressed set/budget, новый target или semantic gap — к Architect до дополнительного execution.
- `perceptual truth-source split`: source, mapped findings и terminal receipts; `N/A (why=no visual task)`.

Existing baseline surfaces: raw generic rules, inventory/archive guards, legal/security/version exceptions и public output schema. New behavior targets: private mapped views/common API и F62 common-private integration внутри четырёх files. Consumer output — blocker findings, не candidate/prefill; severity/exit contracts сохраняются.

Retention: raw local native receipts/stdout/stderr под task TMPDIR — `transient local sanity only`; durable reviewer verdict и explicit risk support — единственный review host/assets. Private values не копируются в durable output. Stateful runtime/process continuity, mutation readback и visual proof — `N/A (why=scanner reads disposable input and has no product-state mutation or live UI)`. Qualification — accepted history, её не запускать повторно.

Truth-host fixture matrix: `N/A (why=not a fan-in/readback helper with authoritative truth hosts)`.
Receipt schema emitter inventory: `N/A (why=no receipt/schema validator or output fields change)`.
Manager command/dispatch surface: `N/A (why=not owner-facing Manager command and dispatch path unchanged)`.
API/payload parity: `Finding(path,line,category,severity,token)`, `print_json` fields и CLI exits неизменны; T1 удерживает API/renderers, T3 — error consumers, T4 — public CLI.

## Targeted changes (by file)

- `scripts/oss_release_scan.py`: common private matcher и mapped views; canonical dictionary literals; scanner/path/metadata integration и safe masking, сохраняя raw generic lane и guards.
- `scripts/test_oss_release_scan.py`: synthetic positive/negative matrix ниже плюс прежний module целиком, без skip/removal ради нового поведения.
- `scripts/test_sibling_contract_docs.py`: public-only policy вместо mixed private regex; actual delivered-file consumer вызывает common private helper; три addressed controls используют тот же consumer seam.
- `docs/tools/oss_evidence_selection.md`: дописать finite normalization/literal/source-span/boundary/masking contract, separate F62 public/private lanes и пределы public CI/release proof; существующий archive-manifest/inventory boundary сохранить.

## Patch sketch (contract, not implementation)

1. В scanner ввести внутреннее представление candidate text + mapping каждого output character на original source span. Raw view сохраняется; canonical view выполняет NFKC → удаление только U+200B/U+200C/U+200D/U+2060/U+FEFF → только ASCII case-pairs `[Xx]`/`[xX]`. Many-to-one и expansion mapping удерживают первый contributing source character. Нормализовать целый candidate с корректным mapping, включая combining sequence через constant concat; посимвольная NFKC без composition proof недостаточна.
2. Dictionary literal payload для plain/path/author получает NFKC и тот же finite zero-width removal перед escaped pattern; separator folding/case-insensitive matching остаются прежними. Только plain names длины1–4 Unicode word characters получают обе Unicode word boundaries; path/author namespaces и уже скомпилированный `re:` не переосмысливаются. `re:` payload не переписывается.
3. На исходном UTF-8 тексте выделить только принятые STRING fragments: ordinary/u/r single/double/triple tokens, string `+`, balanced parentheses и legal adjacency. Physical newline объединяет tokens только внутри тех же parentheses либо explicit continuation. Statement/comment/dynamic boundary завершает fragment; names/calls/attributes/subscripts, f/b strings, formatting/multiply/.join не вычисляются. Один распознанный scalar STRING можно статически декодировать только с результатом str; expression не исполняется. Unsupported/incomplete fragment даёт raw-only lane, parser overflow/internal error — typed `ScanInputError`.
4. `marker_findings` применяет тот же rule set к raw и mapped canonical/decoded candidates. Raw physical-line behavior сохраняет baseline regex/occurrence semantics; обычные newlines не склеиваются. Match получает span фактических source characters, а line — первый contributing character, включая поздний token после safe prefix/escape/multiline. Дедупликация — source span + category, разные occurrences одной строки не схлопываются. Для path только text views, без literal inference; metadata сохраняет line0.
5. Из generic `_line_findings` убрать только private rule loop и подключить common matcher ровно один раз к content/path/metadata carriers; generic rules и их exceptions остаются raw. Для metadata передавать весь исходный value common matcher-у с line0. `safe_path` использует тот же внутренний mapped-match truth без рекурсивного вызова `_finding → safe_path → marker_findings`; normalized private path маскируется по safe spans либо целиком. Author allowance проверяется по исходной exact bare identity/legal guards; decoded/normalized совпадение само allowance не даёт.
6. В F62 оставить `PUBLIC_MODEL_FINGERPRINT_RE = re.compile(r"\b(?:GLM|Grok|(?<!GPT-6\.1 )Sol|Astra)\b")` как отдельный always-on raw case-sensitive policy lane. Private alternatives/реальные literals из mixed regex удалить, не копируя второй private matcher. Один internal delivered-file consumer seam в этом test file обслуживает actual test и три controls: те же file exclusions, relative paths, dictionary root guards и common `oss_release_scan.marker_findings`. Public lane работает и с empty private rules; private diagnostics используют только masked Finding fields.
7. Синхронно обновить policy doc и tests. До Coder proof нет product success: выполнить только согласованный T1–T7, затем review exact current bundle. Любой out-of-bundle need возвращается Architect.

## Synthetic test matrix

Новые T1 cases находятся в existing `OssReleaseScanTests`; названия ниже — новые test methods, покрываются module selector T1 без discovery.

| Новый method | Positive / negative / truth |
| --- | --- |
| `test_marker_normalization_nfkc_and_zero_width` | NFKC variants и каждый из пяти удаляемых points positive; near-miss/U+200E negative, raw generic lane не нормализуется |
| `test_marker_normalization_ascii_case_pairs_only` | `[Aa]`/`[aA]` positive; `[ab]`/`[a-z]`/groups/quantifiers не раскрываются |
| `test_marker_constant_literal_fragments_and_boundaries` | escapes/plain/u/r/triple/adjacent/`+`, parentheses/newline/continuation positive; logical-newline/statements/comments не объединяются |
| `test_marker_dynamic_and_unsupported_fragments_are_not_evaluated` | names/calls/attributes/subscripts/f/b/multiply/format/.join не вычисляются; independent constant argument распознаётся только как собственный fragment; unsupported escape raw-only |
| `test_marker_source_lines_spans_and_duplicate_views` | late token/escape/multiline/combining NFKC attribution; same span через views один раз, два occurrences одной строки остаются двумя |
| `test_marker_short_unicode_name_boundaries` | plain synthetic names1–4 на границах positive; Unicode word-internal near-misses negative; long/explicit namespaces baseline сохранён |
| `test_marker_raw_regex_and_author_allowance_preserved` | raw re-match не исчезает из-за canonical view; exact raw legal identity allowed, normalized/decoded-only/legal near-misses дают finding |
| `test_marker_normalized_path_and_metadata_masking` | normalized path output safe, token masked; archive metadata/static content даёт line0; path не получает STRING inference |
| `test_marker_parser_errors_fail_closed` | bounded injected parser failure/overflow даёт `ScanInputError`, не empty green; public schema/exit guards сохранены |

T1 сохраняет все existing dictionary fail-closed, author/legal, separator, tracked/symlink/archive, generic-clean и renderer tests. Synthetic private fixtures собираются так, чтобы сами public source files не нарушали generic safety checks; real private markers не используются.

T2 сохраняет actual `SiblingContractDocsTest.test_delivered_files_carry_no_private_fingerprints` и добавляет ровно три plan methods:
- `test_public_model_fingerprint_policy_and_exceptions_without_dictionary`: явный unset; GLM/Grok/bare Sol/Astra positive с physical lines; GPT-6.1 Sol/MinIO/word-internal/case negatives allowed, изменённый prefix не даёт Sol exception.
- `test_private_fingerprint_common_matcher_uses_synthetic_external_dictionary`: actual consumer + wrapped/observed common helper; synthetic normalization/static positive и near-miss negative, masked fields/lines, без private regex copy.
- `test_private_fingerprint_dictionary_unset_and_invalid_input`: unset не skip-ит consumer/public lane, common helper получает empty rules; invalid/inside-root/symlink external dictionary даёт тот же безопасный `ScanInputError`.

T3 — два existing `ScannerInputErrorTests`, file read-only. T4 — generic public CLI без dictionary. TUI selectors/manifest completeness и hosted/reachable-history release qualification этим proof не покрываются.

## Commands

Portable interpreter во всех lanes — `"$PYBIN"`, уже выбранный trusted task environment. PATH содержит его bin, TMPDIR — текущий task, runtime frozen; private absolute interpreter/runtime/project paths в artifact не записываются. Все команды идут из selected project, `login=false`, `tty=false`, через exact accepted core ниже и его unchanged command tail.

### Coder/Reviewer: T1–T7

| ID | Literal argv | Timeout |
| --- | --- | --- |
| T1 | `env -u PLANVEYOR_OSS_SCAN_MARKERS PYTHONPATH="$PWD/scripts" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest -v test_oss_release_scan` | 120 s |
| T2 | `env -u PLANVEYOR_OSS_SCAN_MARKERS PYTHONPATH="$PWD/scripts" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest -v test_sibling_contract_docs.SiblingContractDocsTest.test_delivered_files_carry_no_private_fingerprints test_sibling_contract_docs.SiblingContractDocsTest.test_public_model_fingerprint_policy_and_exceptions_without_dictionary test_sibling_contract_docs.SiblingContractDocsTest.test_private_fingerprint_common_matcher_uses_synthetic_external_dictionary test_sibling_contract_docs.SiblingContractDocsTest.test_private_fingerprint_dictionary_unset_and_invalid_input` | 120 s |
| T3 | `env -u PLANVEYOR_OSS_SCAN_MARKERS PYTHONPATH="$PWD/scripts" PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest -v test_verify_suite.ScannerInputErrorTests` | 60 s |
| T4 | `env -u PLANVEYOR_OSS_SCAN_MARKERS PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/oss_release_scan.py --root . --scope public-copy --format json --fail-on blocker` | 120 s |
| T5 | `git diff --check -- scripts/oss_release_scan.py scripts/test_oss_release_scan.py scripts/test_sibling_contract_docs.py docs/tools/oss_evidence_selection.md docs/plans/261017_1730_bounded_scanner_normalization_f62.md docs/code_drafts/261017_1730_bounded_scanner_normalization_f62__code_draft.md` | 10 s |
| T6 | `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/261017_1730_bounded_scanner_normalization_f62.md` | 60 s |
| T7 | `PYBIN="$PYBIN" PATH="${PYBIN%/*}:$PATH" TMPDIR="$TMPDIR" PLANVEYOR_PRODUCT_ROOT="$PWD" bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-basic-hygiene --root "$PWD/docs/tools/oss_evidence_selection.md" --root "$PWD/docs/plans/261017_1730_bounded_scanner_normalization_f62.md" --root "$PWD/docs/code_drafts/261017_1730_bounded_scanner_normalization_f62__code_draft.md"` | 60 s |

Total550 s; один fresh T deadline только после final writes/argv/source readback. Каждая следующая команда использует тот же receipt float; effective deadline=min(command cap,remaining total), cleanup/receipt входят в cap. Первый unexpected nonzero/timeout/error/lost receipt — STOP suffix, без automatic retry/full-set replay/discovery/shards/verify-full. Недостаточный proof/budget возвращается Architect до дополнительных checks.

### Planner: P1–P3

| ID | Literal argv | Timeout |
| --- | --- | --- |
| P1 | `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261017_1730_bounded_scanner_normalization_f62.md` | 60 s |
| P2 | `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py docs/plans/261017_1730_bounded_scanner_normalization_f62.md` | 60 s |
| P3 | `PYBIN="$PYBIN" PATH="${PYBIN%/*}:$PATH" TMPDIR="$TMPDIR" PLANVEYOR_PRODUCT_ROOT="$PWD" bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" --check-basic-hygiene --root "$PWD/docs/tools/oss_evidence_selection.md" --root "$PWD/docs/plans/261017_1730_bounded_scanner_normalization_f62.md" --root "$PWD/docs/code_drafts/261017_1730_bounded_scanner_normalization_f62__code_draft.md"` | 60 s |

Total180 s, тот же serial/stop-first/no-replay contract. P deadline создаётся после final plan+draft bytes/literal argv/source readback; mandatory intake oracle/provenance — отдельные bounded input reads60/60,total120 s и не расходуют/не reset-ят P/Q4/A/T. Product T checks в Planner не выполняются. P3 — existing Self-Planveyor explicit-root hygiene exception, с `PLANVEYOR_PRODUCT_ROOT="$PWD"`; unsupported `runtime_py doc_lint.py` и broad roots pass запрещены.

### Q7: завершённый единственный P-correction-1

Actual recovery proof прочитан при отдельном Planner CENSOR: P2 native/child0 за11.635127457993804 s, P3 native/child0 за0.08407570800045505 s, `doc-lint: OK`; оба timely/full/non-timeout/owned/reaped/group_gone/streams_complete/within_deadline=true,error=null. Evaluated plan SHA7943ea39a1d0f915a7b879e41e2216afc11c9913dc159353a9d4b6387a580c4a, draft SHA3ec67c5beb6ce96eb3772b01f55a9bb8ef33eb22eb4500a0d1dd5795ec278a56 и policy SHA совпали с entry bytes этого CENSOR; receipt SHA274b435039cbe3f2cc7ca12250f57811bba98100370bc3724ef8fdf533fdd26b. Это source-bound proof завершённого recovery, не blanket proof новых CENSOR bytes. Изменённые здесь operational records проверяет отдельная canonical CENSOR family; P-correction-1 consumed, повторять его нельзя.

Historical admission: Owner amendment и Architect triage допустили прежнему Planner только corrected P2≤60 s → previously unrun P3≤60 s, отдельный total120 s/serial/stop-first. Literal P2/P3 argv выше unchanged; P3 имел ровно три roots: evidence policy, plan и этот draft. Все recovery bytes/status, literal argv и actual source SHA были готовы до fresh shared `time.monotonic()+120.0`; следующий command сохранил тот же receipt float. Первый nonzero/timeout/error/lost receipt должен был остановить suffix без retry с canonical вопросом Architect.

Original P1 actual0/13.465209374990081 s/7 paths/0 issues, P2 actual1/12.659238874999573 s и P3not-run остаются history; missing truthful stamp исправлен ниже. Old P180 expired/remaining0, snapshot153.83910625000135 s не allowance. P1/intake oracle/provenance/Q4/A/T/full/qualification не повторяются. Core/qualifier/targets/derived ref/T selectors и Q4 ledger6.62104220801848/10,remaining3.37895779198152 unchanged. Actual два green receipts разрешили primary Ready for Coder и STOP; current Manager-dispatched Planner CENSOR завершает post-handoff verification до Coder. На этом historical Planner checkpoint product T1–T7 ещё не запускались; текущий outcome находится только в plan/Evidence.

## Review route

### Q8: единственный T-correction-1

Historical source-owned Architect disposition в plan/Q8 и explicit Owner admission разрешали прежнему Coder ровно corrected T1→previously unrun T2–T7. Этот allowance consumed; current execution outcome и source bindings находятся только в plan/Evidence, повторное выполнение не разрешено. Literal семь argv/scopes и caps120/120/60/120/10/60/60 s из таблицы выше unchanged; separate total550 s, serial/remaining-total clamp/stop-first/no automatic retry. Все recovery artifact bytes, literal argv и actual source SHA готовятся до fresh shared monotonic deadline; следующий command использует тот же receipt float. Corrected scanner SHAc9dc4bec33b64da1a66efeb9ecc3536c47d6826c94e93297f3767cda2526aefa — admitted source baseline, не test result. Old T1rc1/4.133959833008703 s и pre-fix source bindings, T2–T7not-run и expired original T550 сохраняются исторически. Это same-contract recovery без нового design/Planner cycle/bootstrap/provenance restamp; P/A/Q4/qualification/R gates не повторяются, core/qualifier/proof/ledger/targets/ref unchanged. Первый non-green требует Architect route до любого future T command; actual all7green разрешает Ready for Review и STOP, затем только отдельно Manager-dispatched Coder CENSOR и dual review. Results принадлежат plan, raw receipts — transient task TMPDIR.

- Primary artifact: `docs/code_reviews/261017_1730_bounded_scanner_normalization_f62.md`
- Lane type: code review; отдельные Risk и Contracts lanes, один current artifact.
- Plan, draft и expected review host literal совпадают. Durable risk support фиксирует current target snapshot; raw transient sanity receipt не заменяет review acceptance.

## Critical invariants / traps / bypass paths

- Common private truth: scanner/F62/path/metadata используют один matcher; trap — private regex copy или green T1 при неисполненном T2/T3/T4.
- Source truth: raw detection, original span/physical line и safe path masking не теряются; trap — normalized line numbers, line-only dedup или recursion в redaction.
- Public policy continuity: unset dictionary сохраняет always-on raw model rule и exact exception; trap — return/skip до public lane.
- Execution truth: exact core hash, actual rc/separate streams/timeout/cleanup и timely full receipt обязательны; trap — elapsed/yield как enforcement либо fresh total для каждого command.

## Notes for Coder

Plan владеет semantic scope/admission/limits, metadata — exact editable set; этот sketch не production patch. Все helper-internal algorithm choices остаются у Coder в пределах заданных invariants. Новый target/schema/helper/grammar или недостаточный proof — Architect до изменения bundle/дополнительной команды. Genesis/history/refs и внешний F62 carrier не меняются; Root сохраняет terminal-only obligation после semantic commit Б.

## Review stamps (append-only)

- [2026-10-17 21:27] (Planner) Execution-only seed финализирован: exact четыре targets, derived MAD binding, concrete patch/test guidance, T/P argv/limits и single review route синхронизированы. Core/qualifier и accepted proof/ledger ниже сохранены; qualification/product tests не запускались. P1–P3 pending до final-byte gates.
- [2026-10-17 21:35] (Planner) NO SUGGESTIONS по accepted semantic scope/Owner decisions; full draft materialization и изменения выше реально выполнены. Этот stamp закрывает только missing-stamp diagnostic P2, не означает отсутствие draft changes или green gate. Actual P1 rc0/P2 rc1, P3 not-run; corrected artifact ещё не проверен, re-entry принадлежит Architect.
- [2026-10-17] (Planner; Q7 recovery) Принятый Architect/Owner P-correction-1 синхронизирован в Commands и invocation allowance; это только operational amendment, без нового intake/design/target/ref или повторного qualification. Final-byte P2/P3 receipts pending; исторический missing-stamp failure и исходный budget сохранены.
- [2026-10-17] (Planner; separate CENSOR) Stale current pending/provisional recovery wording заменён actual source-bound outcome P2/P3rc0; прежние append-only stamps остаются historical. Новые operational bytes требуют current CENSOR post-write gates; targets/ref/T selectors/core/qualifier/proof/ledger не менялись, product checks не выполнялись.

Coder stamp: NO SUGGESTIONS по accepted Key decisions/Constraints/Goal. Реализация сохраняет exact четыре targets/ref, single review host и T1–T7/caps/total550/stop-first; новые helper files, qualification/P/A replay и external F62 writes не выполняются. Product proof определяется только fresh actual T receipts, не этим stamp.

- [2026-10-17] (Coder; Q8 corrected/not-tested checkpoint) First T1 actual/native1, 38 tests/1 failure, elapsed4.133959833008703 s; pre-fix scanner SHAc431e675ab4cbc56c8176b7b04d270992d0886d0c6d0057170e5c8ec0e080340 и evaluated draft SHA87fd070ed5db73abffeb1cc300e1dc81a6bb89e5e730508e404620d1c0b45db4 сохранены. T2–T7 not-run по stop-first. Последующее явное Owner steering разрешило только три static fixes existing scanner (call/group boundary, precomputed nesting, author-only precomputed raw lines), corrected SHAc9dc4bec33b64da1a66efeb9ecc3536c47d6826c94e93297f3767cda2526aefa **not tested**. Core/qualifier/targets/ref/selectors/caps не меняются; до любой future T команды требуется Architect disposition Q8 с explicit numeric admission, без guessed T550 reset или automatic rerun. Source-bound records — transient task TMPDIR, status/question — только plan.
- [2026-10-17] (Coder; Q8 recovery synchronization) Historical prerequisite выше закрыт repo-backed current plan/Q8 disposition и explicit separate T-correction-1 admission; только operational recovery contract синхронизирован. Product implementation/test/doc bytes не меняются, source core/qualifier/proof/ledger и metadata preserved. Product outcome записывается только в plan по actual receipts, current synchronization не объявляет proof green.

- [2026-10-17] (Coder; operational closeout) Q8 recovery admission consumed; current routing и actual source-bound outcome принадлежат plan/Evidence. Этот lifecycle stamp не меняет targets/ref/semantic contract/core/qualifier/proof/ledger и не разрешает новый T run. Final lifecycle bytes требуют отдельного Manager-dispatched Coder CENSOR.

## Exact accepted execution core

SHA-256 UTF-8 bytes содержимого следующего блока, включая последний newline: `4452e9f8e0debabc9075381e41ac059fdc95a5bf978d957245f7b202bf839b70`. Source перенесён целиком, без fence-language/chunk workaround и без нового qualification pass. `ENVELOPE_SHA256` задаётся после core в invocation tail.

```python
import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import time

CLEANUP_RESERVE_S = 0.5
TERM_GRACE_S = 0.1
RECEIPT_RESERVE_S = 0.05

def emit_json(value, deadline):
    payload = memoryview((json.dumps(value, ensure_ascii=True) + "\n").encode("ascii"))
    fd = sys.stdout.fileno()
    blocking = os.get_blocking(fd)
    try:
        os.set_blocking(fd, False)
        while payload:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                count = os.write(fd, payload[:65536])
            except BlockingIOError:
                select.select([], [fd], [], max(0.0, deadline - time.monotonic()))
                continue
            if count <= 0:
                return False
            payload = payload[count:]
        return time.monotonic() <= deadline
    except BaseException:
        return False
    finally:
        os.set_blocking(fd, blocking)

def deadline_command(command, cap_s, sequence_deadline):
    started = time.monotonic()
    hard_deadline = min(started + cap_s, sequence_deadline)
    drain_deadline = hard_deadline - RECEIPT_RESERVE_S
    proc = None
    pgid = None
    owned = False
    timed_out = False
    streams_complete = False
    stdout = b""
    stderr = b""
    sent = []
    errors = []
    group_state = "not_started"

    def error(stage, exc):
        errors.append(f"{stage}: {type(exc).__name__}: {exc}")

    def drain(until):
        nonlocal stdout, stderr, streams_complete
        remaining = min(until, drain_deadline) - time.monotonic()
        if remaining <= 0:
            return "timeout"
        try:
            stdout, stderr = proc.communicate(timeout=remaining)
            streams_complete = True
            return "complete"
        except subprocess.TimeoutExpired as exc:
            if exc.output is not None:
                stdout = exc.output
            if exc.stderr is not None:
                stderr = exc.stderr
            return "timeout"
        except BaseException as exc:
            error("bounded drain", exc)
            return "error"

    def signal_owned_group(sig):
        if proc.returncode is not None:
            errors.append("signal refused: leader already reaped")
            return False
        try:
            if not owned or not (
                os.getpgid(proc.pid) == pgid
                and os.getsid(proc.pid) == pgid
                and pgid != os.getpgrp()
            ):
                errors.append("signal refused: current owned group not established")
                return False
            os.killpg(pgid, sig)
            sent.append(sig.name)
            return True
        except ProcessLookupError:
            return True
        except BaseException as exc:
            error(f"signal {sig.name}", exc)
            return False

    try:
        if hard_deadline - started <= CLEANUP_RESERVE_S + RECEIPT_RESERVE_S:
            raise RuntimeError("remaining budget exhausted; no child started")
        proc = subprocess.Popen(
            ["/bin/zsh", "-f", "-c", command],
            cwd=os.getcwd(), env=os.environ.copy(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pgid = proc.pid
        group_state = "unknown"
        owned = (
            os.getpgid(proc.pid) == pgid
            and os.getsid(proc.pid) == pgid
            and pgid != os.getpgrp()
        )
        if not owned:
            raise RuntimeError("child process-group ownership not established")
        outcome = drain(hard_deadline - CLEANUP_RESERVE_S)
        if outcome != "complete":
            timed_out = outcome == "timeout"
            permitted = signal_owned_group(signal.SIGTERM)
            if permitted:
                outcome = drain(min(time.monotonic() + TERM_GRACE_S, drain_deadline))
                if outcome != "complete" and proc.returncode is None:
                    signal_owned_group(signal.SIGKILL)
            if not streams_complete:
                drain(drain_deadline)
    except BaseException as exc:
        error("envelope", exc)
        if proc is not None and proc.returncode is None:
            if owned:
                signal_owned_group(signal.SIGKILL)
            else:
                try:
                    proc.kill()
                    sent.append("SIGKILL-direct-child")
                except BaseException as cleanup_exc:
                    error("direct-child cleanup", cleanup_exc)
            drain(drain_deadline)

    if proc is not None:
        try:
            proc.poll()
        except BaseException as exc:
            error("nonblocking reap", exc)
        try:
            os.killpg(pgid, 0)
            group_state = "exists"
        except ProcessLookupError:
            group_state = "gone"
        except BaseException as exc:
            group_state = "unknown"
            error("group observation", exc)
    rc = None if proc is None else proc.returncode
    stdout_text = stdout.decode("utf-8", "surrogateescape")
    stderr_text = stderr.decode("utf-8", "surrogateescape")
    finished = time.monotonic()
    return {
        "command": command,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "envelope_sha256": ENVELOPE_SHA256,
        "child_pid": None if proc is None else proc.pid,
        "owned_pgid": pgid,
        "child_returncode": rc,
        "timed_out": timed_out,
        "stdout": stdout_text, "stderr": stderr_text,
        "streams_complete": streams_complete,
        "owned_group": owned, "reaped": rc is not None,
        "group_state": group_state, "group_gone": group_state == "gone",
        "signals": sent, "envelope_error": errors or None,
        "started_monotonic": started, "finished_monotonic": finished,
        "elapsed_s": finished - started,
        "hard_deadline_monotonic": hard_deadline,
        "sequence_deadline_monotonic": sequence_deadline,
        "remaining_total_s": max(0.0, sequence_deadline - finished),
        "within_deadline": finished <= drain_deadline,
    }

def transport_rc(record):
    if record["timed_out"]:
        return 124
    if record["envelope_error"] or record["child_returncode"] is None or not all(
        record[key] for key in (
            "owned_group", "reaped", "group_gone", "streams_complete", "within_deadline"
        )
    ):
        return 2
    rc = record["child_returncode"]
    return rc if rc >= 0 else 128 - rc
```

## Одноразовый invocation и command tail

Existing native `exec_command`: `login=false`, selected project `workdir`, `tty=false`, trusted `PYBIN/PATH/TMPDIR` и frozen `PLANVEYOR_RUNTIME_ROOT`. Portable argv — `"$PYBIN" -B -` с quoted heredoc `<<'PY'`. В body помещается exact core выше, затем assignment и tail ниже; file/wrapper installation отсутствует.

`COMMAND`, `CAP_S`, `SEQUENCE_DEADLINE` задаются только из допущенного literal command/численного allowance плана; они не являются новым runtime API. Один one-off body исполняет одну agreed literal-команду. Первое новое P/T семейство создаёт deadline из P=180 s/T=550 s; последующие calls используют один неизменный float из полного receipt. Паузы уменьшают remaining total. Expired A deadline не rebasing/reuse-ится; old A remaining=0. Owner отдельно допустил A-correction-2,total190 s для corrected plan+seed gates; A-correction-1 N1 rc1/N2–N4 not-run остаётся stopped/history. Fresh deadline только после final writes+SHA/argv readback; это не восстановление old A/A-correction-1 и не разрешение Q4/A1/P/T.

Q7 exception выше уже consumed actual green P-correction-1 P2→P3,total120 s; это historical admission, не permission нового запуска. Old P180 и его absolute deadline не переиспользуются; это не новое P1–P3 семейство и не reset исходного allowance. Current отдельный Planner CENSOR использует только свою canonical bounded family из plan. Exact core и command tail ниже неизменны.

```python
ENVELOPE_SHA256 = "4452e9f8e0debabc9075381e41ac059fdc95a5bf978d957245f7b202bf839b70"
record = deadline_command(COMMAND, CAP_S, SEQUENCE_DEADLINE)
emitted = emit_json(record, record["hard_deadline_monotonic"])
raise SystemExit(
    transport_rc(record)
    if emitted and time.monotonic() <= record["hard_deadline_monotonic"]
    else 2
)
```

Core обеспечивает отдельную owned process group, monotonic per-command/remaining-total deadline, cleanup reserve0.5 s/TERM grace≤0.1 s/final receipt reserve0.05 s внутри cap. Все productive/exceptional drain/reap waits bounded. После successful graceful reap SIGKILL не посылается; перед каждым signal проверяются current PGID/SID и unreaped leader. Сигналы не адресуются TUI/Manager/roles или historical PID.

`child_returncode` сохраняет настоящий returncode либо null; `timed_out` отделён. Timeout всегда даёт transport124, даже с actual child0. PermissionError не теряет structured receipt: доступные stdout/stderr раздельны, partial streams помечены, cleanup/group/reap/error state не выдумываются. Без timeout actual nonnegative rc сохраняется, negative signal переводится только в transport128+signal; envelope/ownership/cleanup/deadline/receipt error — nonzero2. Missing/truncated/late receipt означает STOP без replay. Необходимый denied cleanup допускается только через native exact-scope permission для действительно owned current child.

## Accepted qualification source — historical, не запускать

Следующий literal tail — source уже выполненного addressed proof того же core. Он перенесён для source/proof parity, не является разрешением повторного qualification. Текущий qualification allowance не тратится; текущие numbers/remaining находятся в plan.

```python
import shlex

INITIAL_PROOF_S = 1.6210422080184799
FAILED_ATTEMPT_RESERVE_S = 1.0
CARRIED_CHARGE_S = INITIAL_PROOF_S + FAILED_ATTEMPT_RESERVE_S
REMAINING_ALLOWANCE_S = 10.0 - CARRIED_CHARGE_S
ATTEMPT_RESERVATION_S = 4.0
assert ATTEMPT_RESERVATION_S <= REMAINING_ALLOWANCE_S
qualification_start = time.monotonic()
qualification_deadline = qualification_start + ATTEMPT_RESERVATION_S
records = []
qualification_errors = []

positive_source = (
    "import sys; print('positive-stdout', flush=True); "
    "print('positive-stderr', file=sys.stderr, flush=True)"
)
control_template = """import os, signal, sys, time
control = os.fork()
if control == 0:
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    while True:
        time.sleep(30)
def reap_control(signum, frame):
    until = time.monotonic() + 0.07
    while time.monotonic() < until:
        pid, status = os.waitpid(control, os.WNOHANG)
        if pid:
            print(f"control-reaped:{pid}:{os.waitstatus_to_exitcode(status)}", flush=True)
            if EXIT_ZERO:
                raise SystemExit(0)
            return
        time.sleep(0.001)
    print("control-reap-timeout", file=sys.stderr, flush=True)
    raise SystemExit(4)
signal.signal(signal.SIGTERM, reap_control)
print(f"control-pid:{control}", flush=True)
print("timeout-stderr", file=sys.stderr, flush=True)
while True:
    time.sleep(30)
"""
cases = [
    ("positive", positive_source, 1.0, 0),
    ("timeout-zero-control", control_template.replace("EXIT_ZERO", "True"), 1.0, 0),
    ("timeout-kill-control", control_template.replace("EXIT_ZERO", "False"), 1.5, -signal.SIGKILL),
    ("signal-denial-receipt", "import sys, time; print('denial-stdout', flush=True); print('denial-stderr', file=sys.stderr, flush=True); time.sleep(0.65)", 1.0, 0),
]
try:
    for name, source, cap_s, expected_child_rc in cases:
        real_killpg = os.killpg
        def synthetic_term_denial(pgid, sig):
            if sig == signal.SIGTERM:
                raise PermissionError("synthetic owned-group signal denial")
            return real_killpg(pgid, sig)
        try:
            if name == "signal-denial-receipt":
                os.killpg = synthetic_term_denial
            record = deadline_command(
                "exec " + shlex.join([sys.executable, "-B", "-c", source]),
                cap_s, qualification_deadline,
            )
        finally:
            os.killpg = real_killpg
        records.append(record)
        emitted = emit_json(
            {"case": name, "record": record, "transport_returncode": transport_rc(record)},
            record["hard_deadline_monotonic"],
        )
        assert emitted, "case receipt missing or past deadline"
        assert record["child_returncode"] == expected_child_rc, "unexpected actual child rc"
        assert all(record[key] for key in (
            "owned_group", "reaped", "group_gone", "streams_complete", "within_deadline"
        )), "incomplete owned-group cleanup"
        if name == "signal-denial-receipt":
            assert record["timed_out"] and transport_rc(record) == 124
            assert record["stdout"] == "denial-stdout\n" and record["stderr"] == "denial-stderr\n"
            assert record["signals"] == [] and len(record["envelope_error"]) == 1
            assert "PermissionError" in record["envelope_error"][0]
            assert transport_rc(dict(record, timed_out=False)) == 2
            continue
        assert record["envelope_error"] is None, "envelope error"
        if name == "positive":
            assert not record["timed_out"] and transport_rc(record) == 0
            assert record["stdout"] == "positive-stdout\n"
            assert record["stderr"] == "positive-stderr\n"
        else:
            assert record["timed_out"] and transport_rc(record) == 124
            assert record["stderr"] == "timeout-stderr\n"
            control_pid = int(record["stdout"].split("control-pid:", 1)[1].splitlines()[0])
            assert f"control-reaped:{control_pid}:{-signal.SIGTERM}\n" in record["stdout"]
            try:
                os.kill(control_pid, 0)
            except ProcessLookupError:
                control_gone = True
            else:
                control_gone = False
            assert control_gone, "control child remains"
            expected_signals = ["SIGTERM"] if expected_child_rc == 0 else ["SIGTERM", "SIGKILL"]
            assert record["signals"] == expected_signals, "unexpected termination path"
except BaseException as exc:
    qualification_errors.append(f"{type(exc).__name__}: {exc}")

observed_elapsed_s = time.monotonic() - qualification_start
accepted = (
    not qualification_errors and len(records) == 4
    and observed_elapsed_s < ATTEMPT_RESERVATION_S
)
summary = {
    "qualification": "accepted-final-core" if accepted else "refused",
    "envelope_sha256": ENVELOPE_SHA256,
    "observed_elapsed_before_final_receipt_s": observed_elapsed_s,
    "initial_proof_s": INITIAL_PROOF_S,
    "failed_attempt_reserve_s": FAILED_ATTEMPT_RESERVE_S,
    "current_attempt_charge_s": ATTEMPT_RESERVATION_S,
    "cumulative_charge_s": CARRIED_CHARGE_S + ATTEMPT_RESERVATION_S,
    "remaining_qualification_allowance_s": REMAINING_ALLOWANCE_S - ATTEMPT_RESERVATION_S,
    "total_limit_s": 10.0,
    "errors": qualification_errors,
}
summary_emitted = emit_json(summary, qualification_deadline)
raise SystemExit(0 if accepted and summary_emitted and time.monotonic() <= qualification_deadline else 2)
```

## Accepted proof и сохранённый ledger

- Actual native qualification harness rc=0, final receipt `accepted-final-core`, core SHA `4452e9f8e0debabc9075381e41ac059fdc95a5bf978d957245f7b202bf839b70`; observed elapsed перед final receipt=2.2869137920206413 s. Bounded write/deadline check завершился до4 s.
- Positive: actual child0, timeout=false, transport0, separate exact stdout/stderr, elapsed0.010554084 s.
- Graceful timeout/control-child: actual child0, timeout=true, transport124, TERM only; control child actual-15/reaped/gone, elapsed0.506405834 s.
- Escalated timeout/control-child: actual child-9, timeout=true, transport124, TERM/KILL; control child actual-15/reaped/gone, elapsed1.105773708 s.
- Synthetic TERM PermissionError: actual child0, timeout=true, transport124, signals=[], explicit error retained, separate complete streams, elapsed0.663790917 s. Non-timeout interpretation этого error record даёт transport2. Это injection proof обработки отказа, не выдача OS permission.
- Все current cases: owned/reaped/group_gone/streams_complete/within_deadline=true. Current owned groups к завершению proof отсутствуют. Historical pre-reboot missing child receipt не восстановлен; старые PID/PGID не используются.
- Qualification ledger не сброшен: initial1.6210422080184799 s + failed-attempt reserve1 s + current conservative4 s =6.62104220801848/10 s. Remaining3.37895779198152 s сохраняется нетронутым; qualification не повторять.

## Историческая передача execution-only seed (Architect → Planner)

Следующие checkpoint paragraphs сохранены как historical anchor only. Current product draft/metadata/ref и P/T contract материализованы Planner выше; прежние pending statements не являются текущим readiness/readback.

Прежний Planner после отдельного штатного handoff финализирует этот же artifact по canonical template, синхронизирует exact targets/derived MAD ref/implementation guidance и literal P/T checks с plan. Он сохраняет core bytes/SHA и accepted proof/ledger. P1–P3=180 s и T1–T7=550 s/stop-first неизменны; ни один из этих наборов ещё не запускался.

На момент materialization до A-correction-1 checks current plan/seed lint/hygiene pending. Old A allowance expired/remaining0 s, historical A2 rc=1 и A2-diff/A3/A4 not-run сохранены. Separate current Owner admission допускает только один A-correction-1,total190 s, exact argv/caps/stop-first из plan. Actual gate green определяется только полными post-write receipts, не этим seed; full Planner-ready executable contract/preflight здесь не заявляется.


## A-correction-1 checkpoint

- Actual N1 plan lint завершился child/native rc=1 из-за local route-class context historical Planner Q3 в plan; missing code_draft_meta seed дал только expected advisory WARN. N2/N3/N4 not-run по stop-first; no auto-retry.
- Plan получил adjacent Architect-owned triage resolution без изменения historical Planner row. Core/qualifier bytes, accepted SHA/proof и cumulative qualification ledger не менялись. Исправленные plan/seed bytes ещё не прошли new lint/hygiene; ни readiness, ни green не заявлены.
- Новый bounded re-entry требует explicit amendment Q6; прошлый A expired и текущий A-correction-1 stopped не превращаются в новый allowance. Full product draft/targets/derived MAD ref остаются у прежнего Planner.

## A-correction-2 admission

Owner Q6 разрешил один отдельный corrected-byte gate: plan lint60 → diff10 plan+seed → frozen scoped hygiene60 только plan+seed → final oracle60,total190 s/serial/stop-first/no auto-retry. Exact argv/scopes/caps — в plan; complete writes и actual SHA readback предшествуют fresh shared monotonic deadline. Prior A-correction-1 N1 actual rc1/10.561614542006282 s и N2–N4 not-run сохранены; old A expired/A1 rc0/A2 rc1 не reset-нуты. При non-green текущий suffix не исполняется. Q4/A1/P/T не повторяются. Этот seed хранит прежние accepted core/source/proof bytes и ledger6.62104220801848/10,remaining3.37895779198152; full targets/derived MAD ref/product finalization остаются Planner-owned. Gate outcomes определяются реальными post-write receipts, не данным admission paragraph.

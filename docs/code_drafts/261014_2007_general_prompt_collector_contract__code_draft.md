# Code draft: General-промпты и guard ответа PI collector

**Date:** 2026-10-14
**Cluster:** process
**Related plan:** `docs/plans/261014_2007_general_prompt_collector_contract.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)

```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261014_2007_general_prompt_collector_contract.md",
    "cluster": "process",
    "machine_authority_decision_ref": {
      "applicability": "not_applicable",
      "reason_code": "unchanged_structured_consumer",
      "carrier_sha256": "a7146838187c8628e5d40e7b7340ec50d9032d99856aefcc5787fd1edba32f39"
    },
    "targets": [
      {"path": "docs/tools/prompts/architect_docs_finalize_general.md", "kind": "doc"},
      {"path": "docs/tools/prompts/planner_docs_finalize_general.md", "kind": "doc"},
      {"path": "docs/tools/prompts/coder_docs_finalize_general.md", "kind": "doc"},
      {"path": "docs/tools/prompts/reviewer_docs_finalize_general.md", "kind": "doc"},
      {"path": "docs/tools/prompts/manager_collab_pipeline.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/architect_docs_finalize_general.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/planner_docs_finalize_general.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/coder_docs_finalize_general.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/reviewer_docs_finalize_general.md", "kind": "doc"},
      {"path": "copier_template/docs/tools/prompts/manager_collab_pipeline.md", "kind": "doc"},
      {"path": "scripts/test_process_improvements.py", "kind": "py"},
      {"path": "scripts/test_manager_custom_pipeline_prompt_contract.py", "kind": "py"},
      {"path": "docs/process_improvements/README.md", "kind": "doc"}
    ],
    "deleted_paths": []
  }
}
```

## Provenance / session context

- Source plan provenance: `docs/plans/261014_2007_general_prompt_collector_contract.md` → `Plan provenance / session context`; новый draft получен в current Planner invocation.
- Relation: `created-here`
- Thread ID: `N/A (why=private operator mapping is not published)`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-10-14T20:54:27Z`

Поля получены штатным `planveyor_plan_provenance_context --section code-draft --session-key planner`; actual thread mapping не публикуется по принятой границе. Provenance не заменяет routing/admission. Derived MAD ref скопирован только из validated current oracle; semantic decision core принадлежит Architect и здесь не дублируется.

## Purpose

Дать Coder точный контракт И1+И3а: canonical PI output четырёх ролей, единственный durable writer и безопасный разбор collector tool result в фактической collab general ветке. Runtime/helper/parser/schema не меняются; проверки относятся к candidate source bytes.

## Reviewability preflight receipt

- `proof-path class`: `checked-in repo-local helper`.
- `mandatory primary lane`: `scripts/test_process_improvements.py` извлекает реальные нижние canonical/no-op samples четырёх source prompts и вызывает `scripts/process_improvements_collect.py:parse_process_improvements_section`; structured cases дают non-empty suggestions, no-op — no_process_improvements. Exact incident tail остаётся parser refusal; collector fixture проверяет blocked receipt без durable PI delta.
- `mandatory non-primary carrier / contextual lane`: те же восемь sample variants у четырёх copier copies; branch-local rc/framing/parse/field/receipt matrix у collab Manager в `scripts/test_manager_custom_pipeline_prompt_contract.py`; полная existing suite `scripts/test_sibling_contract_docs.py` проверяет source/copy parity и private fingerprint.
- `exact helper path + support files`: read-only `scripts/process_improvements_collect.py` (parser, fresh/replay emitters и v2 receipt validator), `scripts/followups_capture.py` (admission/chain/checkpoint), `scripts/docs_closeout.py` (canonical capture readback), `scripts/contract_authority_bridge.py` (transport boundary). Test edits — только два Python targets из Meta; `Makefile` и `scripts/test_sibling_contract_docs.py` — read-only proof routes.
- `dependent tests / dependent docs / known consumer paths`: все 13 targets; four general output → collab Manager collector consumer → existing v2 receipt/readback → `checkpoint-general-pi` → followups → fresh terminal docs-closeout. Пять source/copy pairs меняются побайтно вместе. `manager_custom_pipeline.md`/copy — read-only context, N/A (why=no demonstrated same-contract edit dependency). External packet N/A (why=generic mirror policy declares no external target).
- `preconditions / seed-discovery`: `discovery-or-seed` — existing synthetic test repo/cycle в declared ignored TMPDIR; tracked sample corpus, live provider/auth/SQL не нужны. Production `receipt-reuse-only` сохраняет project root, plan/source ref, exact role, retained cycle и raw input digest. Observer boundary — terminal collector tool result и следующий canonical same-cycle readback, затем existing full-chain checkpoint перед первым followups dispatch. `.tmp` — transient local sanity only; plan/current review и explicit assets — durable evidence. `notice/success text != mutation truth`; terminal sink — whole-tail fresh `final_docs_commit=no_op|landed`.
- `runtime-lineage preflight`: frozen source identity + explicit selected project обязательны; tests читают working candidate prompts. Runtime-owning failure = STOP, не product reopen или runtime rewrite.
- `reroute rule`: implicit/red mandatory lane, missing current proof, дополнительный helper/schema/target или доказанная custom dependency возвращаются Architect до widening. Collector/parser refusal не чинится trimming/retry/no-op substitution.
- `perceptual truth-source split`: structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up. Visual lane N/A (why=no visual surface).

### Truth-host fixture matrix

- `authoritative_host`: existing canonical current `process_improvement_capture.v2` receipt, selected по plan/source + role + cycle; full chain у existing checkpoint.
- `derived_summary_field`: stdout `process_improvement_capture_state` и `process_improvement_receipt_path`, которые не дают отдельной durable authority.
- `green_case`: rc=0, один object, существующие fields/state/current cycle валидны; fresh/replay сохраняют одну receipt authority, replay без stdout input_sha256 допустим.
- `missing_case`: missing required stdout field или current receipt/proof при green-looking stdout → STOP.
- `ambiguous_case`: prefix/suffix/second value, другой source/role/cycle → STOP, без substring/latest/mtime inference.
- `present_but_red_or_inconsistent_case`: current receipt blocked/invalid/stale/input mismatch при green-looking stdout → STOP; pending остальных ещё не dispatched ролей не скрывает blocked.
- `expected_fail_closed_verdict`: исходный collector error/rc и доступный canonical helper reason/receipt path; без retry, PI write или next followups dispatch. Prompt-contract suite доказывает candidate instructions; не live adoption.

### Receipt schema emitter inventory / field parity

- Receipt family: existing `process_improvement_capture.v2`; changed validators/parsers/schema fields = N/A (why=existing structured contract is unchanged).
- `_collect_process_improvements` и `_v2_replay_response` в `scripts/process_improvements_collect.py`: read-only context with N/A (why=only consumer guard changes). Existing обязательные stdout strings — `process_improvement_capture_state`, `process_improvement_capture_reason`, `process_improvement_receipt_path`, `followups_capture_cycle_id`. Fresh stdout также имеет `input_sha256`, replay может его не иметь; обязательный raw digest хранится только в validated v2 receipt. Новый field/key whitelist не вводится.
- `_validate_v2_capture_receipt`, `scripts/docs_closeout.py:classify_process_improvement_capture`, `scripts/followups_capture.py:general_pi_capture_receipts_proof`: read-only context with N/A (why=existing validators/readers remain authority). Новый skeleton/bootstrap/readback emitter N/A (why=no schema change).
- Command/one-shot dispatch: N/A (why=no command or dispatch change); `scripts/planveyor/role_runtime.zsh` и owner help не входят в mutable bundle.
- Golden Path: N/A (why=registry has no general collector correction entry; ordinary plan contract is sufficient).

## Targeted changes (by file)

| Targets | Обязательное изменение |
| --- | --- |
| Четыре `docs/tools/prompts/*_docs_finalize_general.md` из Meta | Согласовать upper PI contract, surfaced-suggestion step и нижний output: canonical seven-field block либо exact standalone no-op; иных body rows нет. Убрать role-owned durable write и misleading tolerance wording; пояснения вынести из intended PI output, не из parser input. Остальные docs/followups/merge boundaries не менять. |
| `docs/tools/prompts/manager_collab_pipeline.md` | Изменить actual post-general consumer branch рядом с existing collector call. Terminal tool rc → single-object framing → guarded JSON.parse → existing field shape/state/current cycle; refusal сохраняет первопричину и использует только существующий current helper readback/admission для объяснения. Без нового schema, Manager-side receipt parser, retry или dispatch semantics. |
| Пять `copier_template/docs/tools/prompts/*` из Meta | Перенести финальные source bytes побайтно; source-owned delivery, без sibling write. |
| `scripts/test_process_improvements.py` | Восемь canonical и восемь no-op lower samples source/copy, реальный parser, точный incident tail, blocked receipt/raw digest/no durable effect. Переиспользовать existing synthetic collector/replay harness. |
| `scripts/test_manager_custom_pipeline_prompt_contract.py` | Branch-local order/shape/error matrix и existing writer/readback boundary; учитывать fresh/replay input_sha256 split. Не расширять custom prompt из-за имени suite. |
| `docs/process_improvements/README.md` | Коротко закрепить: роль выдаёт структуру, Manager вызывает existing collector, только collector записывает durable PI; strict whole input и rc/shape guard относятся к consumer. Это существующий семейный README; искусственная RU/EN пара не создаётся. |

## Review route

- Primary artifact: `docs/code_reviews/261014_2007_general_prompt_collector_contract.md` (PLANNED before Reviewer).
- Lane type: `code review` — два non-doc Python targets входят в bundle.
- Review target: `BUNDLE=current`; origin plan/draft/review входят в exact closeout отдельно, не в Meta targets. Explicit review risk support/assets выбирают existing producers, без directory glob.

## Patch sketch (keep it small)

Кодовый patch здесь не задаётся; implementation принадлежит Coder. Последовательность:

1. В каждом general prompt согласовать shared contract и role-specific surfaced step. Нижний intended PI output содержит только canonical block либо standalone no-op; labels выбора размещены вне выдаваемого body. Supported enums не расширять, `source_ref` связывать с manager-fed plan ref.
2. Извлечение тестом начать после последнего `Выход (в чат)`, выделить PI H2 до следующего H2; отделить canonical/no-op variants только по явно размеченному sample contract. Конкретизировать placeholders, не фильтровать неизвестные строки. Не копировать верхний образец вместо нижнего. Whole raw sample содержит именно то, что роль должна вернуть.
3. В actual collab general consumer сохранить полный exec result и дождаться `exit_code`; running session дочитать, не повторять collector. Nonzero остановить до parse. Framing отвергает empty/plain-text/fences/prefix/suffix/second value/non-object; обычный внешний JSON whitespace допустим. Syntax errors ловятся guarded parse. Existing fields проверяются после parse; unknown/blocked state и mismatch cycle fail-close.
4. При failure сохранить оригинальный result; existing `planveyor_docs_closeout <plan_ref> --followups-capture-cycle-id <capture_cycle_id> --json` может объяснить его через canonical current proof. Missing/red/stale proof остаётся STOP. Не читать receipt вручную и не создавать новый admission helper. До четвёртого general aggregate pending может означать ещё не dispatched roles; current invalid/blocked побеждает pending. Полную receipt/object chain до первого followups dispatch проверяет existing checkpoint.
5. Обновить две declared suites и короткий README, синхронизировать пять copies. Проверить order/error cases именно внутри actual branch и full lower samples настоящим parser. Ни success text, ни словесный disclaimer вне ветки не доказывают выполнение guard.
6. Выполнить exact команды ниже по final candidate bytes, записать фактические results в plan; AC закрывать только этим proof. Перед Ready for Review сохранить 13 literal targets и один review path. Дополнительный target/schema/helper требует upstream triage.

## Critical invariants / traps / bypass paths

- Invariant: PI предложение не теряется. Trap: верхний contract корректен, нижний output свободный; trimming превращает содержательное предложение в no-op. Bypass path: любая из четырёх source/copy surfaces, включая Reviewer explanation labels. Proof: 16 реально извлечённых parser cases и полный exact incident input.
- Invariant: durable PI записывает только existing collector. Trap: роль сначала пишет backlog, потом Manager collector повторно собирает. Proof: upper contract, surfaced step и lower sample согласованы; parser/collector negative fixture не имеет PI object delta.
- Invariant: error stdout не становится receipt. Trap: JSON.parse до rc либо удачный stdout при red current host. Proof: branch-local matrix, readback/receipt остаются existing authority; replay без stdout digest не блокируется новым required field.
- UI/runtime layout/access checks: N/A (why=no declared UI surface).

## Commands / proof order

Self-Planveyor: из selected working project, с уже выбранным trusted `$PYBIN` Python 3.12, compatible PATH и declared ignored TMPDIR. Не записывать private environment values; system temp запрещён. Facade использует frozen runtime, direct suites и Make проверяют candidate bytes.

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_lint docs/plans/261014_2007_general_prompt_collector_contract.md
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight docs/plans/261014_2007_general_prompt_collector_contract.md
bash scripts/run_doc_lint.sh --root docs/plans/261014_2007_general_prompt_collector_contract.md --root docs/code_drafts/261014_2007_general_prompt_collector_contract__code_draft.md
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_process_improvements.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_manager_custom_pipeline_prompt_contract.py' -v
PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B -m unittest discover -s scripts -p 'test_sibling_contract_docs.py' -v
make verify
make doc-lint
make typecheck
make oss-release-scan
```

Каждая команда обязана завершиться exit 0; verify — GREEN, scan — без blocker; WARN получают bounded disposition. Это future Coder/Reviewer proof contract, не результаты Planner. При неизменных успешных bytes прогон не повторяется без нового основания. Runtime/adoption/terminal success эти suites не доказывают.

## Assumptions / risks

- Existing baseline surfaces: strict parser, v2 receipt/admission/writer/readback, checkpoint и terminal docs-closeout. New helper/schema/file family N/A (why=prompt consumer and existing tests only).
- И3а не применяется текущим frozen runtime внутри А1. General closeout prompts перечитываются из working project; candidate Manager guard вступает в силу только после отдельной технической проверки следующего runtime.
- Потеря TUI/identity, authority/infrastructure failure, новый scope blocker или blocked terminal closeout = STOP; без new role, repair, migration или А2 как обхода.

## Notes for Coder

- Plan важнее draft; semantic core не менять. Только 13 targets из Meta, plan/draft lifecycle и current review — остальные paths read-only.
- Draft/реализацию Planner не коммитит. Architect выполняет существующий exact-bundle closeout после accepted review; whole А1 затем требует fresh terminal docs-closeout `final_docs_commit=no_op|landed`. Этот gate не является pre-Done checkbox и не разрешает дописывать terminal plan.
- CENSOR сам не запускать; Manager dispatch-ит его отдельным ходом. Никакого evidence-only skip hint для нового executable contract.

## Review stamps (append-only)

- 2026-10-14 (Planner): draft создан и сверен с current plan/validated derived MAD; все targets существующие, implementation proof пока не выполнен.
- [2026-10-15 00:03] (Planner) NO SUGGESTIONS (reviewed; no changes required) — после полного reread executable draft дополнительных содержательных правок не требуется; hygiene штампа не меняет контракт.
- [2026-10-15 00:17] (Planner) NO SUGGESTIONS (reviewed; no changes required) — отдельный Manager-dispatched second opinion: 13 targets, field parity, mandatory lanes и proof commands перечитаны; новых содержательных правок нет.
- 2026-10-15 (Coder) NO SUGGESTIONS (reviewed; no changes required) — exact 13 targets реализованы без изменения executable contract; primary/contextual lanes и declared commands выполнены. Один PLANNED review path сохранён, runtime/helper/parser/schema не менялись.

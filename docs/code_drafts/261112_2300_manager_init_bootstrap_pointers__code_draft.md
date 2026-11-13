# Code draft: стартовый промпт Manager ссылается на существующий раздел роли

**Date:** 2026-11-13 03:06 MSK
**Cluster:** docs
**Related plan:** `docs/plans/261112_2300_manager_init_bootstrap_pointers.md`
**Author role:** Planner
**Status:** draft

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/261112_2300_manager_init_bootstrap_pointers.md",
    "cluster": "docs",
    "targets": [
      {
        "path": "docs/tools/prompts/manager_init.md",
        "kind": "doc"
      },
      {
        "path": "copier_template/docs/tools/prompts/manager_init.md",
        "kind": "doc"
      },
      {
        "path": "scripts/test_planveyor_shared_corpus_contract.py",
        "kind": "py"
      },
      {
        "path": "scripts/test_shards.json",
        "kind": "json"
      },
      {
        "path": "docs/contract_notices/261112_2300_manager_init_bootstrap_pointers.json",
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
- Source plan provenance: `PLAN_PATH` сохраняет исходный manual-owner carrier; этот draft создан отдельно по current helper context.
- Relation: `created-here`
- Thread ID: `01a1d211-9566-7642-acd5-846e47d643f9`
- Parent thread ID: `N/A (why=not exposed by env, wrapper receipts, or session stats)`
- Session SID: `N/A (why=.planveyor.session.planner is missing or empty)`
- Launch surface: `unknown (why=no env, wrapper receipt, or session stats origin identified the launch surface)`
- Captured from: `env`
- Captured at: `2026-11-13T00:03:44Z`

Сбор выполнен внешним `planveyor_plan_provenance_context --section code-draft --session-key planner`. Это audit context; task/status truth остаётся в plan. Derived N-A ref создан `planveyor_code_draft_stub_from_plan --role Planner` по validated oracle и сохранён без изменения semantic core.

## Purpose
Исправить только bootstrap heading pointer двух Manager init копий и дать независимые relationship/parity/registration/notice proofs. Это готовый contract для реализации, а не production patch или доказательство live bootstrap/adoption.

## Reviewability preflight receipt
- `proof-path class`: standard primitives — repo-backed связь документов, unittest, existing parity, manifest composition и notice validation.
- `mandatory primary lane`: новый `SharedCorpusContractTests.test_manager_init_bootstrap_pointer_resolves_to_role_heading`, затем полный shared-corpus module; in-memory старый pointer отвергается тем же assertion predicate; `scripts/run_test_shard.py --check --ci-profile fast` подтверждает exact-once partition и полноту contracts-b.
- `mandatory non-primary carrier / contextual lane`: шесть existing `SiblingContractDocsTest` методов из plan Commands, один `PlanveyorProfileExtractionTests.test_all_public_prompt_phases_resolve_from_one_root_corpus`, один `RouterMergeBoundaryTests.test_neutral_consumer_manager_init_reaches_fake_codex_and_saves_sid`; финальный notice через `ConsumerContractNoticeTests.test_current_notice_history_and_strict_notice_are_valid`. Review проверяет смысл notice и `engine_changes=[]` отдельно от schema gate.
- `exact helper path + support files`: `scripts/test_planveyor_shared_corpus_contract.py`, `scripts/test_sibling_contract_docs.py`, `scripts/test_planveyor_profile_extraction.py`, `scripts/test_planveyor_router_merge_boundary.py`, `scripts/test_shards.json`, `scripts/run_test_shard.py`, `scripts/test_consumer_contract.py`, `scripts/consumer_contract.py`; новых helpers/support files нет.
- `dependent tests / dependent docs / known consumer paths`: runtime resolver `scripts/planveyor.zsh::manager/init`, payload builder `scripts/planveyor/session_init.zsh`, authority inventory `scripts/contract_authority_context.py`, перечисленные tests, `docs/roles/manager.md::Bootstrap Pointers`, `docs/playbooks/docs_architecture.md::Ownership и delivery`, `docs/contract_notices/README.md`; notice `validate_notice/notices` и перенос actions/checks в adaptation plan в `scripts/consumer_contract.py`. За пределами пяти targets эти пути read-only; роль Manager, ZCode command и role bundles не меняются.
- `preconditions / seed-discovery`: текущий physical Self-Planveyor checkout и HEAD; доверенный launch `PYBIN` 3.12 и его bin в PATH; внешний pinned runtime для helper gates. Target tests запускаются `"$PYBIN" -B scripts/...` из текущего checkout. Disposable fixtures только под repo-local `.tmp/manager-init-bootstrap-fixtures/` через TMPDIR. DB, provider, сеть, настоящий sibling или live Manager не нужны.
- `reroute rule`: новый helper/schema/runtime consumer, общий linter, другой target, live/sibling mutation или semantic/core/ref drift требуют Architect reroute до widening. Обязательные lanes описаны здесь; actual green получают после реализации, до Ready for Review. Missing-heading исходного prompt и fail-closed notice stub — исходное/плановое состояние, не новый runtime defect.
- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`

- Retention: `.tmp/manager-init-bootstrap-fixtures/` — transient local sanity only. Durable proof summary — `PLAN_PATH::Evidence`; independent review — primary artifact ниже. Локальные результаты не доказывают hosted CI, live Manager bootstrap или upgrade sibling.
- Stateful/runtime/Golden Path: `N/A (why=документная связь и local tests; stateful chain, transient entity carrier, runtime listener и Golden Path execution отсутствуют)`.
- Truth-host fixture matrix: `N/A (why=not a fan-in/readback helper with authoritative truth hosts)`.
- Command-surface fan-out: `N/A (why=Manager dispatch path unchanged; owner-facing commands и one-shot runtime не меняются)`.
- Receipt schema emitter / API payload fields: `N/A (why=notice является экземпляром существующей схемы; validator/parser/API fields не меняются)`.

## Targeted changes (by file)
- `docs/tools/prompts/manager_init.md`: в инструкции `2)` заменить только прежнее имя раздела на `## Bootstrap Pointers`; остальные байты сохранить.
- `copier_template/docs/tools/prompts/manager_init.md`: та же единственная замена; результат побайтно равен source.
- `scripts/test_planveyor_shared_corpus_contract.py`: один новый method `SharedCorpusContractTests.test_manager_init_bootstrap_pointer_resolves_to_role_heading`; contract и negative ниже.
- `scripts/test_shards.json`: добавить ровно один полный ID `test_planveyor_shared_corpus_contract.SharedCorpusContractTests.test_manager_init_bootstrap_pointer_resolves_to_role_heading` только в `subsets.contracts-b.ids` рядом с IDs этого module; existing whole-module `s01`, другие subsets/selectors без изменения.
- `docs/contract_notices/261112_2300_manager_init_bootstrap_pointers.json`: полностью заменить временную JSON-строку path-tracking stub final object существующего формата. До этого notice schema proof ожидаемо RED; stub нельзя stage/commit. Reader проверяет каждую historical версию, поэтому последующий fix не лечит invalid historical blob.

Existing baseline surfaces — текущие runtime resolver/payload, Manager role heading, parity test, manifest runner и notice validator. New targets — только финальный notice path; остальные четыре targets уже существуют. Новый test method не создаёт helper family/schema/route; semantic N-A admission принадлежит Architect, здесь только immutable derived ref.

## Steps / patch sketch
1. Добавить один названный method. Из root Manager init выбрать ровно одну строку инструкции `2)`, из неё извлечь единственный role path `docs/roles/manager.md` и единственный inline-code heading `## ...`. Проверить, что путь указывает на ожидаемую роль, и heading есть отдельной полной строкой в её `splitlines()`. Не сводить проверку к hardcoded наличию нового текста и не извлекать headings из всего prompt: row `2.1)` содержит отдельный provenance heading.
2. В том же method один локальный assertion predicate применить к реальной инструкции и in-memory варианту: заменить только извлечённый heading на `## Обязательный старт (session bootstrap; 1 раз на role‑сессию)` (U+2011 в `role‑сессию`). Negative должен дать именно missing-heading assertion, пойманный ожидаемым AssertionError. Ни временного изменения файлов, ни второго test method/helper/module, ни цикла ролей.
3. Пока source prompt ещё исходный, запустить только новый method из plan Commands; ожидаемый RED должен воспроизвести missing-heading defect. Затем внести единственную замену в обе prompt копии и один manifest ID. Full module после исправления проверяет positive и сохранившийся in-memory negative.
4. Заменить notice stub final JSON object: непустой однострочный `summary`; `contract_changes` описывает исправление pointer обеих source/template копий на существующий heading Manager; `engine_changes=[]`; `sibling_actions` требует обычный `planveyor sibling upgrade` в отдельном adaptation plan; `checks` требуют реальный heading в принятом prompt и байтовую сверку с Copier выбранной версии. Все array items — непустые однострочные строки. Notice не содержит получателя/ACK, не утверждает доставку, не меняет schema.
5. Выполнить весь final proof sequence ниже, затем source/helper gates из plan Commands. Результаты каждого запуска и ожидаемый первоначальный RED записать кратко в plan Evidence. Final success = rc0 и все выбранные tests выполнены без failures/errors/skips. Не превращать fixture output в durable receipt.
6. К Ready for Review проверить, что все пять targets final, notice stub отсутствует, actual diff содержит только accepted targets плюс lifecycle carriers, review host единственный и current. Stage/commit/Done не принадлежат Planner или этому handoff.

## Proof commands
Из текущего physical checkout; использовать переданный `PYBIN`, без записи его private absolute value. Сначала `export PATH="${PYBIN%/*}:$PATH"`, `mkdir -p .tmp/manager-init-bootstrap-fixtures`, `export TMPDIR="$PWD/.tmp/manager-init-bootstrap-fixtures"`.

Первоначальный RED до prompt fix:
```zsh
"$PYBIN" -B scripts/test_planveyor_shared_corpus_contract.py SharedCorpusContractTests.test_manager_init_bootstrap_pointer_resolves_to_role_heading -v
```

Final proof после всех пяти изменений:
```zsh
"$PYBIN" -B scripts/test_planveyor_shared_corpus_contract.py -v
"$PYBIN" -B scripts/test_sibling_contract_docs.py \
  SiblingContractDocsTest.test_template_copies_match_their_docs_sources_byte_for_byte \
  SiblingContractDocsTest.test_delivered_docs_call_the_engine_only_through_the_facade \
  SiblingContractDocsTest.test_delivered_code_blocks_do_not_start_with_bare_engine_functions \
  SiblingContractDocsTest.test_delivered_docs_reference_only_delivered_or_explicit_engine_paths \
  SiblingContractDocsTest.test_delivered_docs_do_not_offer_root_defaulting_helpers_directly \
  SiblingContractDocsTest.test_delivered_files_carry_no_private_fingerprints -v
"$PYBIN" -B scripts/test_planveyor_profile_extraction.py PlanveyorProfileExtractionTests.test_all_public_prompt_phases_resolve_from_one_root_corpus -v
"$PYBIN" -B scripts/test_planveyor_router_merge_boundary.py RouterMergeBoundaryTests.test_neutral_consumer_manager_init_reaches_fake_codex_and_saves_sid -v
"$PYBIN" -B scripts/run_test_shard.py --check --ci-profile fast
"$PYBIN" -B scripts/test_consumer_contract.py ConsumerContractNoticeTests.test_current_notice_history_and_strict_notice_are_valid -v
```

Helper gates — exact external facade commands с `--project "$PWD"` из plan `## Commands`: plan lint, actual-status oracle и strict first `planveyor_plan_bundle --preflight`. Scoped current-checkout source validation использует existing Self-Planveyor direct route, отдельно от runtime helpers:

```zsh
"$PYBIN" -B scripts/doc_lint.py --root docs/tools/prompts/manager_init.md --root copier_template/docs/tools/prompts/manager_init.md --check-code-refs --code-refs-scope repo
"$PYBIN" -B scripts/doc_lint.py --root docs/plans/261112_2300_manager_init_bootstrap_pointers.md --root docs/code_drafts/261112_2300_manager_init_bootstrap_pointers__code_draft.md --check-basic-hygiene
```

Source strict refs, lifecycle hygiene и exact bundle preflight — разные проверки: пока review ещё `PLANNED`, его отсутствие не закрывают fake file. `planveyor_doc_lint` проверяет canonical roots runtime и не передаёт arbitrary roots. Whitespace для tracked/untracked carriers — точные команды из plan; clean `--no-index /dev/null` здесь возвращает rc1 без stdout/stderr, любой diagnostic или иной rc — ошибка. После review final bundle truth — `planveyor_plan_bundle --check`; preflight inventory не заменяет review/runtime/adoption.

## Review route
- `Primary artifact`: `docs/code_reviews/261112_2300_manager_init_bootstrap_pointers.md`
- `Lane type`: `code review` — bundle содержит `copier_template/`, Python и manifest; второго live host нет.

## Critical invariants / traps / bypass paths
- Две одинаковые ошибочные копии проходят parity; relationship predicate обязан отдельно связать извлечённый pointer с реальной полной строкой heading.
- Bare manifest `--check` не вычисляет composition; обязательный `--ci-profile fast` ловит новый method без contracts-b ID. Один ID не создаёт duplicate shard selector.
- Fake-init smoke доказывает только init plumbing/fake invocation/SID, не исполнение bootstrap самим Manager; notice/schema доказывает source contract, не upgrade sibling.
- Notice stub должен быть fail-closed и uncommitted; ни успешный preflight inventory, ни будущая исправленная версия не делают invalid historical notice допустимым.

## Assumptions / risks
- Scope — только пять literal targets, никаких deletions. `PLAN_PATH`, этот draft, live review и его explicit support refs добавляются final bundle helper отдельно, не в `targets`.
- Plan provenance остаётся исходным audit context; actual status/Q&A/decisions — task truth. Machine-authority semantic core и V2 follow-up row остаются неизменными.
- Full suite/hosted CI/live provider/bootstrap/sibling adoption отсутствуют в acceptance; их нельзя заявить по local proof.

## Notes for Coder
Если факты расходятся с plan/draft, записать blocker в plan и запросить Architect-owned reroute; не расширять targets. Не писать production runtime, не менять другие prompts/roles, общий lint, partition policy, notice validator или credentials. Исходная V2 row остаётся open/null без promotion/backlink.

## Review stamps (append-only)
- [2026-11-13 03:06 MSK] (Planner) Draft финализирован по current source, helper-derived provenance/ref и принятому пятифайловому scope; implementation/proof green не заявлен.

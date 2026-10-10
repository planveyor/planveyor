# Code draft: <TOPIC>

**Date:** YYYY-MM-DD HH:MM
**Cluster:** UNCONFIRMED
**Related plan:** `docs/plans/YYMMDD_HHMM_topic.md`
**Author role:** Planner | Coder | Architect
**Status:** draft

---

## Meta (machine-readable JSON)
```json
{
  "code_draft_meta": {
    "plan": "docs/plans/YYMMDD_HHMM_topic.md",
    "cluster": "UNCONFIRMED",
    "targets": [
      {
        "path": "UNCONFIRMED",
        "kind": "py|template|css|js|doc"
      }
    ],
    "deleted_paths": [
      {
        "path": "OPTIONAL/repo-relative/deleted-file.ext",
        "kind": "doc"
      }
    ]
  }
}
```

> Machine-authority derived binding: для плана с validated upstream carrier
> `code_draft_meta.machine_authority_decision_ref` contains only
> one tagged active `{applicability, decision_id, carrier_sha256}` or N-A
> `{applicability, reason_code, carrier_sha256}` object. Planner copies no
> semantic decision core into this draft. Статус и назначение определяют
> обязательность ref, дата/имя плана не дают исключения. До handoff при допустимом
> отсутствии carrier ref не создаётся; exact N-A decomposition parent остаётся
> отдельным проверяемым случаем без current-plan draft. `plan_lint.py` validates
> the binding against the current plan carrier. Старый policy payload читается
> без rewrite; новый required payload создаёт Architect с HANDOFF policy.
> A separately admitted `bounded_grammar` checkpoint-V2 implementation may add
> only a distinct non-authority four-key `admission_baseline`
> `{plan_path, done_commit, decision_id, carrier_sha256}` for its terminal
> introducer. It is an immutable Git witness, never a current/subject authority,
> never a copied decision core, and its selector must not fall back to `HEAD`.

## Provenance / session context
(Keep this aligned with `PLAN_PATH` provenance. If the draft is created in the same session as the plan, reuse the same facts via `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_provenance_context --section code-draft --session-key <role>` instead of freehand copy/paste.)
- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`
- Relation: `created-here | continued-here | imported-from-packet | manual-backfill`
- Thread ID: `UUID/handle` или `N/A (why=...)`
- Parent thread ID: `UUID/handle` или `N/A (why=...)`
- Session SID: `UUID/handle` или `N/A (why=...)`
- Launch surface: `codex-desktop | codex-cli | manager-collab | manager-custom-pipeline | unknown (why=...)`
- Captured from: `env | wrapper-session-file | session-stats | packet-import | manual-owner`
- Captured at: `YYYY-MM-DDTHH:MM:SSZ`

> `code_draft_meta.targets` = authoritative implementation/doc file set. Если draft используется как input для post-review selective staging, к `Ready for Review` targets должны быть reconciled до exact final set (не seed sketch). Если seed держал abstract package/dir umbrella, а в diff materialize-ились конкретные child files, restamp targets на эти literal file paths до closeout; abstract parent dir не считается commit-ready substitute. Если same-contract reroute сужает already-closed baseline до leftover cleanup, accepted baseline carriers restamp-ятся в notes/receipt как `historical anchor only`, а live `code_draft_meta.targets` сужается до literal leftover carrier вместо повторного открытия уже принятых файлов. `code_draft_meta.deleted_paths` = optional explicit deletion carrier for files intentionally removed by this bundle; every entry must be tracked in `HEAD`, deleted paths are stageable bundle members, and they do not weaken missing/stale checks for ordinary live `targets` or existing untracked files. `PLAN_PATH`, сам code draft, review artifacts и explicit review asset refs добавляются в финальный bundle отдельно.

> Для mutable `BUNDLE=current` origin `PLAN_PATH` запрещён в `code_draft_meta.targets`, включая lexical/symlink/hardlink aliases того же file object: Reviewer обязан дописывать lane evidence в plan, поэтому такой target не имеет достижимого stable hash. `PLAN_PATH` всё равно входит в final exact bundle отдельным lifecycle carrier; valid immutable `RANGE=<base>..<head>` review остаётся в range lane. Immutable `COMMIT=<sha>` получает exemption только если ref однозначно разрешается в commit object внутри Git repo origin plan; missing/fabricated/unresolvable/ambiguous refs и mutable `COMMIT|BUNDLE=staged|current` остаются fail-closed.

> Если slice меняет documentation/registry/canon, держи exact editable doc files в `code_draft_meta.targets`, а source/rationale/lifecycle записывай в `PLAN_PATH` → `## Documentation impact / provenance`. Не дублируй этот carrier в draft как второй target list: draft отвечает за patch mechanics and exact bundle truth, plan carrier отвечает за documentation impact and deferred/post-merge lifecycle.
> Если в `code_draft_meta.targets` попадает generated/derived docs index, draft обязан назвать rebuild helper, run order и readback. Для `docs/followups/index.md` canonical helper = `scripts/followups_index_rebuild.py --project-root .`; без helper/readback lane такой target считается handoff trap, а не ordinary prose edit.

> Перед `Ready for Coder` executable draft должен проходить Planner-time `planveyor_plan_bundle --preflight <PLAN_PATH>`: invalid/missing top-level `code_draft_meta`, несовпадающий `code_draft_meta.plan`, missing/stale `targets`, malformed `deleted_paths`, and `deleted_paths` entries not tracked in `HEAD` fail-closed even if the file currently exists; отсутствующий first-pass review artifact допустим только до Reviewer как `PLANNED`. Post-review/final truth остаётся `planveyor_plan_bundle --check`.

> Для `review-only` merge-range draft `code_draft_meta.targets` должны зеркалить filtered carrier list самого reviewed range (`git diff --name-only BASE..HEAD`, с учётом `EXCLUDE_DOCS`), а не только doc wrappers вокруг plan/review artifact. Иначе route `docs/code_reviews/...` vs `docs/doc_reviews/...` перестаёт быть deterministic ещё до Reviewer handoff.

> Если draft обслуживает multi-profile process slice в `planveyor`, держи split явно: shared-core surfaces перечисляй отдельно от profile-local adaptation surfaces. Shared generic set = `alternate state / non-primary carrier proof`, `shared contract carrier bounded fan-out`, `truthful preconditions / harness drift vs live regression`, `reopened-blocker classification / same-contract reroute`; web-only `HTMX`/`OOB`/DOM/browser/visual shell/CTA не записывай как implicit default для других profiles.
> Если slice materialize-ит новую carrier/helper family поверх already-landed baseline, в receipt/notes literal-но разводи `existing baseline surfaces` и `new targets`; paired contextual/no-dup carriers (followups wrapper, manager bridge, alternate proof host) всё равно перечисляй в consumer inventory, даже если exact lane materialize-ится только в одном primary file.
> Если route acceptance, `## Promoted route artifact`, exact target refresh или helper/readback state-token introduction уже изменили live truth, draft обязан quarantine stale live wording to `historical evidence` / `historical anchor only`: current `Problem`/`Solution`/`Scope`/`Acceptance`/`Tests`/review route/target wording не должны продолжать говорить `until route acceptance`, `not accepted yet`, old bundle path count или mixed underscore/hyphen state-token spelling. Для такого guard Done-plan fixtures should cover stale current `## Promoted route artifact` and routing/handoff `N/A` reason text after terminal Architect acceptance.

## Purpose
Коротко (1–3 строки): что этот draft должен помочь реализовать/проверить.

## Reviewability preflight receipt
(Required if the handoff depends on helper family, named non-primary carrier / contextual lane, or deterministic visual/native/stateful proof. Keep it aligned with `PLAN_PATH`.)
- `proof-path class`: `N/A (why)` или UNCONFIRMED
- `mandatory primary lane`: `N/A (why)` или UNCONFIRMED
- `mandatory non-primary carrier / contextual lane`: `N/A (why)` или UNCONFIRMED
- `exact helper path + support files`: `N/A (why)` или UNCONFIRMED
- `dependent tests / dependent docs / known consumer paths`: `N/A (why)` или UNCONFIRMED
- `preconditions / seed-discovery`: `N/A (why)` или UNCONFIRMED
- `reroute rule`: `N/A (why)` или UNCONFIRMED
- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`

<!--
### State-transition declarations
(Opt-in only. Copy this block out of the comment only when the linked plan uses the declarative transition contract; ordinary drafts remain non-opt-in.)
- `before-state`: carrier=<authoritative-carrier>; identity=<stable-identity>; expected=<before-state>
- `allowed mutation inventory`: writer=<bounded-writer>; entrypoint=<bounded-entrypoint>; targets=["<canonical mutation identifier>"]
- `after-state`: carrier=<authoritative-carrier>; identity=<stable-identity>; expected=<after-state>
- `protected-target post-review continuity`: targets=["docs/<repo-relative-path>.md"]; on_change=same-file-review-rerun
-->

> Если wrapper/prompt дал concrete `PYBIN`, receipt/steps/commands в draft должны использовать тот же interpreter spelling, что и `PLAN_PATH`. Не смешивай `python3`, `$PYBIN` и absolute interpreter в одном executable handoff без явной причины.
> Если exact shared lane живёт только в одном primary carrier, paired contextual/no-dup carriers не считаются “вне scope”: они должны literal-но попасть в `mandatory non-primary carrier / contextual lane` и/или `dependent tests / dependent docs / known consumer paths`, иначе handoff оставляет implicit fan-out.
> Если draft разрешает compact CENSOR/reviewer receipt, target changes должны literal-но назвать retained mandatory labels/gates, opened/read source refs, concise delta/outcome, target snapshot parity, lane synthesis and red-as-live lifecycle. Compactness не разрешает source-ref-only proof.
> Truth-host fixture matrix (required only for fan-in/readback helpers that summarize authoritative truth hosts; otherwise `N/A (why=not a fan-in/readback helper with authoritative truth hosts)`): `authoritative_host`, `derived_summary_field`, `green_case`, `missing_case`, `ambiguous_case`, `present_but_red_or_inconsistent_case`, `expected_fail_closed_verdict`. `authoritative_host` must be the writable truth carrier, not a derived report/digest; a present-but-red/inconsistent host must fail closed even if the derived summary is green.

Truth-host fixture matrix:
- `authoritative_host`: `N/A (why=not a fan-in/readback helper with authoritative truth hosts)` или exact truth carrier/path+field
- `derived_summary_field`: `N/A (why=...)` или helper/readback field
- `green_case`: fixture/proof for authoritative green -> derived green
- `missing_case`: fixture/proof for missing host -> fail-closed
- `ambiguous_case`: fixture/proof for multiple/current ambiguity -> fail-closed
- `present_but_red_or_inconsistent_case`: fixture/proof for authoritative red/mismatch while derived summary can look green
- `expected_fail_closed_verdict`: exact error/blocker/verdict; derived green cannot override authoritative red

> Для source-owned rollout-packet refresh slice receipt/steps literal-но говорят, packet pair already materialized или создаётся впервые; primary lane обычно = `plan_lint` + packet-scoped `doc_lint`, а contextual lane читает packet на `Target writable carriers`, `Queue after import` и importable-boundary / not-yet-landed guards.
> Для stateful multi-step / transient proof lane draft тоже обязан literal-но назвать `discovery-or-seed`, downstream `receipt-reuse-only`, stable identity fields, exact observer boundary, next canonical snapshot/readback как mutation truth source и `runtime-lineage preflight` / reroute там, где stale runtime может выглядеть как новый product defect.
> Для race/lock/idempotency proof lane draft обязан literal-но отличать retry/stale-instance regression от true thread/process concurrency или DB-level uniqueness/constraint proof. Substitute proof допустим только если граница названа в receipt/AC/evidence, а full concurrency/constraint proof вынесен в явный follow-up/reroute.
> Для transient redirect/return/callback/wizard/pending carriers (`next`, return URL, callback URL, pending-auth state и аналоги) draft обязан назвать terminal sink assertion: проверяется не только intermediate carrier propagation, но и финальный successful sink того же carrier.
> Если proof lane пишет receipt/output artifact, draft тоже обязан literal-но назвать retention class для каждого path family: `transient local sanity only` vs `durable operator/review evidence`; `.tmp/...` по умолчанию не считается durable merge evidence.
> Если текущий repo/profile ещё не содержит truthful live corpus/entity set для этого контракта, draft/receipt обязан literal-но назвать synthetic proof carrier (`temp fixture`, `temp dir`, seed generator) и явно запретить silent widening через checked-in sample artifacts "только ради теста". Если closure требует historical corpus/backfill, это reroute/follow-up, а не скрытое расширение текущего bundle.

## Targeted changes (by file)
- `path/to/file.ext`: что меняем (1 строка).

> Если task меняет shared contract carrier (shared helper/adapter с externally visible HTTP/status/event/redirect/response-body semantics или repo-visible CLI/JSON/receipt fields, severity/verdict/exit-code/aggregation semantics), здесь и в `code_draft_meta.targets` обязательно назови helper/adapter path, dependent tests, dependent docs, known consumer paths и consumer contract semantics (`verdict/blocker` vs `candidate/evidence/prefill`, severity/warn/blocking behavior, schema compatibility). Формулировка `audit later` не подходит для executable handoff.
> Если task меняет parseable receipt/schema validator, parser или schema fields, draft обязан нести `receipt schema emitter inventory`: receipt family, changed validators/parsers, все owner-facing `generated skeleton/bootstrap/readback emitters`, exact `target decision` по каждому emitter и focused stale-emitter proof. Emitters остаются consumers, не schema authority; context-only emitter paths без target decision или `audit later` не подходят для executable handoff.
> Если task добавляет/меняет owner-facing Manager command surface (`MANAGER_CMD=<cmd> [PLAN_PATH]` / `planveyor_manager_collab_cmd <subcommand> [PLAN_PATH]`), draft обязан нести command-surface checklist: helper/runtime surface, one-shot dispatch surface (`scripts/planveyor/role_runtime.zsh`) или explicit `N/A (why=dispatch path unchanged/not owner-facing/not one-shot)`, owner documentation/help/readback surface, dependent tests и cold explicit-path regression без cached `.planveyor.planpath`, если `[PLAN_PATH]` публичен. Если dispatch behavior меняется, runtime/test files становятся mutable targets; если dispatch не меняется, они остаются contextual fixtures только с explicit `N/A`.
> Если task меняет API/payload canon (`docs/api.md`, response schema, helper JSON fields), здесь назови changed payload fields, exact emitter/helper path и regression assertion/readback. `docs/api.md` diff без field-level emitter/readback parity = review blocker, даже если generic suite зелёная.
> Если target file ещё не существует до Coder implementation, не оставляй missing path без carrier: либо создай минимальный fail-closed path-tracking stub с plan ref + `replace before Ready for Review`, либо верни handoff на helper/schema plan для first-class `planned_new_paths` semantics.

## Review route
- `Primary artifact`: `docs/code_reviews/YYMMDD_HHMM_topic.md` | `docs/doc_reviews/YYMMDD_HHMM_topic.md` | `N/A (why)`
- `Lane type`: `code review | docs review | hybrid (why)` или `N/A (why)`

> `Review route` в code draft должен literal-но совпадать с live review host в `PLAN_PATH` (`## Review artifacts` / generated review route), а не восстанавливаться по памяти.
> Если live bundle остаётся `docs-only` (`code_draft_meta.targets` лежат под `docs/**`), truthful host = `docs/doc_reviews/...`, даже если сам review file ещё не materialized на момент Planner handoff.
> Как только в live bundle появляется любой non-doc carrier, host flip делается сразу и single-source на `docs/code_reviews/...`; не оставляй dual route и не держи stale `docs/code_reviews/...` для docs-only slice “на вырост”.

## Patch sketch (keep it small)
Правила:
- **не вставлять целые файлы**;
- один фрагмент кода ≤ ~40–60 строк;
- если хочется вставить больше — разбей на 2–3 маленьких фрагмента или оставь как “steps + pointers”.
- это `contract, not implementation`: draft не должен превращаться в production-like patch spec.

Пример (diff‑style или snippet):
```diff
... minimal diff here ...
```

## Critical invariants / traps / bypass paths
- `N/A (why)` если task control/non-risky и отдельный runtime/bypass risk отсутствует.
- `Invariant:` <какой risky contract нельзя потерять>
  - `Trap:` <какой shortcut/ложный proof выглядит зелёным, но не доказывает live behavior>
  - `Bypass path:` <page/fragment/list/api/supporting endpoint/mode-role exception/same-surface action/mode/state/default/non-primary carrier variant> или `N/A (why)`
- Если risk живёт в default-state / non-primary carrier, называй shared invariant именно так, а `OOB`, hidden-field, selected slug и normalization cues держи как profile-local example-layer.
- Держи этот блок на уровне contract guidance; не расписывай здесь production implementation step-by-step.

## Assumptions / risks
- Assumption: ...
- Risk: ...

## Notes for Coder
- Если есть конфликт между этим sketch и plan — **plan важнее**; зафиксируй blocker в plan.
- Если в ходе реализации выяснилось, что sketch неверный — можно поправить draft, но требования/UX всё равно фиксируются в plan.
- Если plan использует post-review selective staging, не оставляй в `code_draft_meta.targets` stale/advisory пути: к `Ready for Review` это уже exact final implementation/doc file set. Если package host materialize-ился только частью файлов, перечисли именно эти concrete files, а не abstract parent directory.
- Если same-contract reroute поверх closed baseline оставил только bounded leftover cleanup, не держи принятые baseline files в live targets “для контекста”: переведи их в `historical anchor only`, а в `code_draft_meta.targets` оставь только literal leftover bundle.

## Review stamps (append-only)
Если ты **прочитал** этот draft и правки **не требуются** — всё равно оставь “штамп ревью”, чтобы было видно, что артефакт реально был просмотрен.

Пример:
- [YYYY-MM-DD HH:MM] (Planner) NO SUGGESTIONS (reviewed; no changes required)

# Role Prompt Invariant Map

Карта помогает редактировать role prompts без повторного размазывания общих
правил по каждому файлу. Это не новый runtime contract и не замена локальным
status-block алгоритмам: prompt, который владеет ролью/режимом, остаётся
операционным source of truth.

Используй этот файл как классификатор: `hard invariant`,
`role-specific delta` или `procedural noise`.

## Hard Invariants

- `PLAN_PATH` является task source of truth: `**Status:**`, Q&A,
  suggestions, objections, decisions, commands and evidence живут в plan.
- `PRE_STATUS_LINE` является anti-memory anchor, а не вторым source of truth;
  при расхождении роли перечитывают plan/oracle и не роутят по памяти.
- Chat-output для status-driven role prompts остаётся коротким:
  только `Next:` и `Open items:`.
- Queue/docs-closeout факты берутся из repo-backed payloads, helper output,
  plan/review artifacts и oracle, а не из thread memory или ledger guesses.
- Plan provenance, review route и exact bundle должны быть literal:
  concrete plan path, code draft targets, review artifact path, asset paths и
  route owner фиксируются в docs, если они нужны для handoff/review.
- Manager остаётся router-only в обычном режиме: он не правит `PLAN_PATH`,
  не меняет `**Status:**` и не вычисляет bundle вне explicit helper contract.
- Commit ownership разделён по ролям: Manager не stage/commit/push,
  Coder/Reviewer меняют index/history только по explicit Owner/mode-prompt
  разрешению, Architect делает только helper-backed local exact-bundle/final
  docs-only closeout, merge `ready_to_push` helper делает только bounded local
  closeout commit, а `git push` и manual recovery вне exact bundle остаются
  Owner-owned.
- Manager status/Owner-Q&A/PRE_STATUS readback is helper-owned: prompts route
  by oracle fields such as `status_norm`, `status_line`, `route_guard_*`,
  `owner_qna_readback_state`, `owner_qna_issues[]` and
  `open_owner_questions[]`, not by private markdown scans of
  `to=Owner status=open` or durable routing from `PRE_STATUS_LINE`.
- Manager CENSOR completeness gate is helper-backed: Manager prompts may route
  by `censor_evidence_lint.state/reason_code`, but must not duplicate the
  CENSOR evidence markdown checklist as a private parser.
- Repo boundary остаётся явным: no sibling writes, no `AGENTS.md` edits,
  no model/default/runtime/helper/queue semantics changes без отдельного plan.
- Shared process-core vs profile-local split: в общий contract поднимается
  только repo-agnostic invariant. Web carriers (`HTMX`, `OOB`, DOM/browser,
  visual shell/CTA) остаются examples, пока plan не делает их default surface.
- Канонический generic process set для таких slice'ов:
  `alternate state / non-primary carrier proof`,
  `shared contract carrier bounded fan-out`,
  `truthful preconditions / harness drift vs live regression`,
  `reopened-blocker classification / same-contract reroute`.
- Scope/follow-up route classifier дополняет reopened-blocker taxonomy:
  `same-contract reroute` = тот же bundle/contract, `real scope expansion` =
  новый Architect-owned scope/contract decision, `de-scoped follow-up` = debt
  явно убран из current scope и materialize-ится только после terminal closeout
  или explicit promote. Planner backlog не является live escape hatch.
- Reviewability proof должен называть primary lane и non-primary/contextual
  carriers; для stateful lanes нужны stable identity fields, observer boundary
  и next canonical snapshot/readback как mutation truth source.
- Для active paired `semantic_cycle_checkpoint.v1` input — только accepted
  producer observation history; Architect один пишет Evidence resolution,
  а Manager всех режимов сначала исполняет generic oracle `route_guard_*` и
  никогда не считает family, permit или decision из prose.
- Для separately admitted `bounded_grammar` checkpoint V2 semantic writer остаётся
  только Architect в subject `PLAN_PATH::Evidence`; `plan_lint` — sole selector,
  а Planner/CENSOR/oracle/Manager — derived readers. V2 `stop`, second
  contour-wide `same_contract_once` и silent V1/V2 fallback — hard invariant
  violations, не role-specific prose choice.
- Dev-test policy не размывается: если plan требует runtime tests/smokes,
  используй объявленные выбранными repo/profile/plan harness и backend. Лёгкий
  backend или bypass required check не доказывает результат без явно принятого
  contract admission. Отсутствие required harness — gap для штатного reroute,
  а не ложный pass или `N/A`.
- Authority boundary: у нормы ровно один `canonical writable owner`; candidate,
  plan, prompt, test, review, receipt и readback не создают duplicate writable
  truth, false promotion или owner mismatch. Их co-location в одном exact bundle
  допустима, но только named enforcement mechanism может fail-close либо менять state.
- Machine-authority admission is a narrower instance of that invariant: Architect
  writes the sole strict `plan_meta.machine_authority_decision`; lint/oracle/CENSOR
  read one helper result; Planner owns only the tagged code-draft ref; Manager and
  terminal consumers retain generic `route_guard_*` readback and never parse the
  semantic core or prose.

## Role-Specific Deltas

- Architect владеет semantic triage, Owner escalation и итоговым `Done`.
- Planner владеет executable contract, code draft finalization и exact-bundle
  preflight before `Ready for Coder`.
- Coder владеет implementation/evidence внутри plan bundle и ставит только
  `Ready for Review`, если proof lanes прошли.
- Reviewer владеет review artifact, severity taxonomy and review verdict;
  Reviewer не чинит код и не ставит `Done`.
- Manager владеет routing/orchestration по oracle. Collab, merge-mode,
  queue-mode and docs-closeout variants keep their own operational steps.
- Owner runbook остаётся operator surface для wrappers, profiles, commands,
  local state and human launch flow.

## Procedural Noise

Считай text block noise candidate, если он:

- пересказывает тот же `PLAN_PATH`/status/chat-output rule без новой роли,
  mode exception или recovery branch;
- копирует generic carrier examples вместо ссылки на shared map;
- дублирует runbook-level shell/operator reminders внутри status prompt,
  когда local prompt уже называет exact command/owner;
- объясняет цель invariant длинной прозой, но не добавляет stop condition,
  reroute rule, artifact path, helper path, role owner или safety boundary.

Не удаляй block как noise, если он меняет routing, queue/docs-closeout payload
truth, review route, plan provenance, Manager authority, repo boundary, model
policy, test policy, tool fallback или safety behavior.

## Edit Rule

Перед cleanup классифицируй paragraph как `hard invariant`,
`role-specific delta` или `procedural noise`. Если есть сомнение, оставь text
локально и зафиксируй в plan evidence, почему repeated prose остаётся hard
invariant или role-specific exception.

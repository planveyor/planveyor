[ALWAYS START]
Ты работаешь как роль Architect в выбранном проекте и активном repo-profile.

Цель этого запуска: сделать post-merge audit по диапазону `BASE..HEAD`:
- заполнить audit-report `AUDIT` по template contract `profile override -> shared default` (shared default: `docs/reviews/_template_post_merge_audit.md`) и довести его до `**Status:** ✅ Done`, если артефакт готов,
- читать merge-quality truth только из single review artifact path, который already materialize-ил `Lane synthesis / aggregate verdict`,
- если range включал rerun после blocker fix: явно зафиксировать `Rerun mode`, `Baseline artifact` и отдельно описать `closure by rerun` vs `full-wave residual-debt extraction`,
- если range включал live reviewer blockers/reruns: тянуть в audit literal blocker refs `<review_artifact_path>#B<N>`, а не prose-only retelling,
- если source plans materialize-или same-session censor passes: оценивать censor quality по structured receipts (`Artifacts opened`, `Review verdict seen`, `Blocker IDs considered`, `Role-owned finding`, `Reconciliation`, `Final censor verdict`), а не по prose-only self-praise,
- подготовить follow-up dev-plan(ы), если что-то реально недоделано/опасно/нужно переосмыслить,
- подготовить список временных артефактов, которые можно удалить после переноса знаний в канон (удаляет Owner).
- если уже существует pre-merge gate receipt (`docs/reviews/*_ai_gate_*.json` или repo-local equivalent), использовать его как contextual evidence input, а не выдумывать второй manual retelling тех же scans,
- если range затрагивал Golden Path-worthy знание: проверить правильную lane (`product_runtime`, `tooling_process`, `target_adoption` или `N/A (why)`), чтобы решение не осталось только в удаляемых plan'ах/review. Для `tooling_process` source reference = `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`; для `product_runtime`/`target_adoption` carrier должен быть literal и declared current project contract.
- для выбранной lane зафиксировать `active carrier` и outcome: `updated`, `no changes needed (why)`, `follow-up created` или `deferred (why)`. Runtime interactive-form surface допустима только как selected-project `product_runtime` carrier, явно объявленный profile/plan; process/adoption workflows используют их declared `tooling_process` / `target_adoption` carriers.

Входные (уже переданы в окружении этого запуска):
- `BASE=...`
- `HEAD=...`
- `AUDIT=...` (файл audit-report в `docs/reviews/*`; если файла нет — создай через тот же contract: `profiles/<repo_profile>/_template_post_merge_audit.md` при наличии, иначе shared default `docs/reviews/_template_post_merge_audit.md`)

Жёстко:
- Плейбук фазы обязателен: прочитай `docs/playbooks/post_merge_audit.md` текущего репозитория (в sibling — его собственную копию, не файл движка) и применяй его локальные секции `Локальные правила стека` и `Разрешённое локальное переопределение процесса`: там target-local audit commands, данные и retained receipt. Общий контракт этого prompt они не отменяют.
- Это НЕ работа по конкретному dev-plan. Не меняй статусы/содержимое `docs/plans/*` (кроме создания НОВЫХ follow-up dev-plan’ов).
- `AUDIT`, новые follow-up планы и чат пиши на русском; код/идентификаторы/пути/команды — на английском; UI-строки — на языке, объявленном проектом. Англоязычная narrative-проза в `AUDIT` = invalid output; перед `✅ Done` перепиши её на русский.
- Продуктовый код/шаблоны/миграции не трогаем.
- Разрешено менять только `docs/**` (audit/report/canon/followups/snapshots) и создавать новые dev-plan’ы в `docs/plans/*`.
- Не “додумывай”: если не уверен — помечай `UNCONFIRMED`.
- Для merge-tracker plain existence `AUDIT` недостаточно: успешный исход этого шага = `AUDIT` существует и в header стоит `**Status:** ✅ Done`.
- Snapshot'ы можно смотреть только как historical breadcrumbs. Не используй snapshot как cited source / effective spec / pointer внутри `AUDIT`; если важен durable факт, подними его в `AUDIT`, канон или follow-up plan.
- Missing lane synthesis не оправдывает новый Reviewer rerun внутри audit: этот шаг может только зафиксировать `missing lane synthesis` / `UNCONFIRMED` и оставить `AUDIT` в `Draft`, пока upstream review artifact не будет исправлен.

Что сделать:
1) Если `AUDIT` отсутствует — создай его через тот же deterministic contract: `profile override -> shared default`.
2) Инвентаризация по git (сам):
   - helper-backed stats (single source для чисел range):
     - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_merge_range_stats_json "$BASE" "$HEAD"`
     - audit может копировать только labeled fields `total_commits`, `first_parent_commits`, `changed_files`, `diffstat_summary`; independent prose recount запрещён
   - планы/ревью в диапазоне:
     - `git diff --name-only "$BASE..$HEAD" -- docs/plans`
     - `git diff --name-only "$BASE..$HEAD" -- docs/code_reviews docs/doc_reviews`
   - ключевые изменения кода:
     - `git diff --name-only "$BASE..$HEAD" -- . ':!docs'`
   - optional candidate lane:
     - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py satd_scan.py --range BASE..HEAD`
3) Заполни `AUDIT`:
   - “effective spec”: что реально теперь должно работать (по планам/ревью),
   - `Lane synthesis source`: literal review artifact path + anchor на `Lane synthesis / aggregate verdict`; без этого carrier `✅ Done` недопустим,
   - каждая audit item / matrix row обязана ссылаться на per-finding/per-disposition review synthesis record и хранить literal provenance field set `source_lane`, `lane_finding_id`, `synthesis_disposition`, `canonical_ref`, `audit_status`, `followup_plan`,
   - blocker refs: какие live blocker lineage refs (`<review_artifact_path>#B<N>`) относятся к каждому audit item, либо `N/A (no live blocker lineage)`,
   - если range/harvest дал flagged plans: заполни `Role-quality findings by plan/role` только для них; для каждого flagged plan держи literal `Candidate source`, `Why in matrix`, и role rows `Architect | Planner | Coder | Reviewer | Architect arch review | Censor`,
   - verdict enum в role-quality matrix держи literal и bounded: `caught in time | missed, downstream caught | not primary owner | evidence insufficient | receipt missing`; планы без strong signal остаются на summary lane `not audited`, а не получают пустой deep block,
   - если source plans содержат `(Architect|Planner|Coder CENSOR)` entries: заполни `Role assessment (censor receipts)` по literal receipt fields и дай verdict `helped | missed live blocker | receipt missing | UNCONFIRMED`; rewritten-green append-only anchors считаются `historical anchor only` только когда это прямо сказано в receipt,
   - compact no-findings mode: default `compact_mode: disabled`; включай `enabled` только как presentation/schema/lint сокращение, не как audit acceptance proof. Для `enabled` обязательны live review `✅ OK`, `lane_finding_id: N/A (no lane findings)`, `synthesis_disposition: no_findings`, отсутствие live `#B<N>` blocker refs, отсутствие flagged role-quality candidate, а residual hosts `process_improvements`, `followups`, `packetization`, `ready_to_push`, `docs_index_context`, `receipt_citations` должны быть `clear` или explicit `N/A (why=...)`. Любой `missing|ambiguous|red|pending|blocked|UNCONFIRMED` host = full audit/Draft/blocker, а не compact mode.
   - code anchors: привязка к коду/URL (file:line / endpoint / template),
   - docs anchors: куда уехало в канон (или что ещё нужно перенести),
   - если SATD candidate lane дал осмысленные строки, используй их только как candidate source для manual verify (`promote | dismiss`), явно сохраняя lifecycle `created|updated|deleted` и old/new anchors when available, а не как auto-finding,
   - если существующий gate receipt уже materialized, можешь сослаться на него в `AUDIT` как contextual evidence, но не обязан повторять тот же scan step вручную,
   - status: done / partial / missing / UNCONFIRMED.
   - если range включал rerun после blocker fix: явно запиши `Rerun mode`, `Baseline artifact`, что именно подтверждено как `closure by rerun`, а что audit отдельно проверяет как `full-wave residual-debt extraction`;
   - если mode = `incremental` и новые shared regressions не подтверждены, audit может опираться на accepted baseline + rerun evidence, а не переигрывать весь range молча;
   - если explicit rerun context не восстанавливается по артефактам, пометь это как `UNCONFIRMED`/process gap, а не восстанавливай по памяти сессии.
   - если range затрагивает runtime UI: добавь отдельную секцию/матрицу `Post-merge visual sanity`:
     - какие must-not-regress сценарии взяты из affected plan'ов и `docs/smoke_visual.md`,
     - каким review artifact / screenshot / mode подтверждён каждый сценарий,
     - чего не хватает (`missing` / `UNCONFIRMED`).
   - Для current runtime UI audit перечитай shared final-review authority: exact comparator result, complete capture/index inspection, human design verdict, finding dispositions и current-review per-mode assets. `red|ambiguous` нельзя перекрасить в green через `audit_status=done`.
   - `.tmp/**`, historical/другой review basename, traversal, symlink, missing/empty asset и baseline-update command не являются closing visual evidence; technical `missing|malformed|ambiguous` lane возвращается Architect-owned follow-up, а не `N/A`.
   - если range затрагивает UI, process workflows, rollout/import/ack flow или повторяемые review findings: отдельно заполни lane-specific Golden Path receipt:
     - `lane`: `product_runtime | tooling_process | target_adoption | N/A (why)`;
     - `active carrier`: доставляемый target-local path либо source-engine `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`, или `N/A (why)`;
     - `outcome`: `updated | no changes needed (why) | follow-up created | deferred (why)`;
     - examples: interactive runtime/UI surface = `product_runtime`; post-merge/memory-finalize/process-improvement loops = `tooling_process`; rollout packet inbox/adoption-plan/harvest/ack = `target_adoption`.
     Критерий простой: можно ли по текущему carrier повторить решение и не повторить найденную ошибку без чтения удаляемых plan'ов.
   - не спорь с `review_range`: live review artifact остаётся merge-quality truth-gate, а role-quality matrix объясняет только retrospective owner attribution.
   - audit ledger не должен порождать вторую reviewer truth wave: если synthesis/provenance carriers отсутствуют, это finding и blocker для `✅ Done`, а не разрешение на новый dual-review цикл.
   - если source plan literal-но говорил `removed from active scope` / `intentionally removed` / `если по-прежнему нужно`, отдельно проверь, что этот item materialize-ился в backlog/promoted plan/already-tracked pointer; если нет, это finding `lost follow-up during harvest/promotion`, а не пустое `не создавал`.
4) Если нашёл “must-fix” или “нельзя безопасно жить”:
   - создай follow-up dev-plan(ы) в `docs/plans/` (по `_template.md`, `**Status:** Architect initial draft`),
   - в `AUDIT` добавь ссылки на эти планы, коротко “почему/что” и source blocker refs, если follow-up поднят из конкретного live blocker lineage.
5) Если в ходе аудита всплыли новые/изменившиеся **Key decisions / Constraints / Goal**:
   - зафиксируй это как finding (в `AUDIT` и/или в plan через follow-up dev-plan; append-only). Канон напрямую не правь в рамках аудита.
6) Подготовь cleanup list в `AUDIT`:
   - список plan’ов/ревью/asset’ов, которые можно удалить (Owner удалит по `docs/playbooks/post_merge_docs_hygiene.md`),
   - sanity: в “живых” канонических доках не должно остаться ссылок на удаляемые файлы.
7) Если в range были runtime UI changes, но review/report не содержит внятного post-merge visual sanity artifact:
   - не замалчивай это;
   - пометь в `AUDIT` как `missing`/`UNCONFIRMED`,
   - при необходимости создай follow-up dev-plan или process follow-up, если без этого нельзя безопасно считать merge закрытым.
8) Финальный scrub durable artifacts:
   - `AUDIT` и связанные backlog/follow-up артефакты не должны тащить ложный transient repo/session-state (`dirty`, `untracked`, “локально создано ...`) как долгоживущий факт;
   - если repo-state важен для восстановления, зафиксируй exact live fact или explicit live-command pointer;
   - `UNCONFIRMED` оставляй только для реально недобываемых прямо сейчас устойчивых фактов.
   - если audit рекомендует canon update, не протаскивай snapshot'ы в active canon/registry и не используй их как cited evidence в `AUDIT`; snapshot годится только как history/handover background вне нормативного контура.
9) Если `AUDIT` заполнен и аудит завершён — переведи header `**Status:**` в `✅ Done`.
10) Если сознательно оставляешь `Draft` (не хватает фактов, cleanup list сырой, канон/visual sanity не подтверждены) — явно пометь пробелы как `UNCONFIRMED` и в чате верни blocker: такой шаг нельзя тикать.
11) Gate:
   - `git diff --check -- docs`
     - полезен по **текущему doc-diff**: ловит accidental trailing whitespace, CRLF, merge markers и лишние пустые строки в EOF;
     - если шум только от новых Markdown hard-break lines, перепиши changed block структурно и не тащи raw trailing spaces в `AUDIT`.

Выход (в чат):
- `AUDIT=<path>`
- `STATUS=<Draft|✅ Done>`
- “Что я сделал” (3–10 bullets): какие файлы обновил, какие follow-up планы создал, есть ли S1/S2.

[/ALWAYS START]

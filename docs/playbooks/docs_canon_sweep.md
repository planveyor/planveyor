# Playbook: Docs — canon sweep (осушение канонов)

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

Цель: после крупного merge/серии веток привести **канонические** доки к виду “коротко + pointers”, не таща туда историю/простыни и не превращая `docs/snapshots/*` в cited source/pointer.

Это **не роль**. Обычно выполняет Architect (архивариус), но Owner может сделать вручную по этому сценарию.

См. также:
- doc_lint policy: `docs/playbooks/doc_lint.md`
- post-merge docs hygiene (удаление времянки): `docs/playbooks/post_merge_docs_hygiene.md`
- post-merge audit (если тема multi-plan): `docs/playbooks/post_merge_audit.md`
- snapshot playbook: `docs/playbooks/snapshot.md`

## Когда использовать
- Тема затронула несколько планов/ревью и “накопила” много док-правок.
- После merge хочется безопасно удалять `docs/plans/*` и `docs/code_reviews/*` без страха потерять смысл.
- В каноне появились дубли/простыни/устаревшие “как было”.

## Вход / выход
Вход:
- TOPIC (опционально): `<short>` (например `schema_cleanup`, `auth_hardening`)
- RANGE: `BASE..HEAD` (sha)
- (опционально) список plan/review артефактов в scope

Выход:
- Обновлённые канонические доки (коротко, без истории).
- Snapshot(ы) в `docs/snapshots/*` допустимы только как history/handover артефакты (если нужны для восстановления контекста), но не как pointer из active canon.
- Доказательство выполнения для merge-tracker `step:canon_sweep`: либо snapshot `docs/snapshots/*range_<base7>_<head7>*`, либо durable receipt/report `docs/reviews/*_canon_sweep_receipt_range_<base7>_<head7>.md` со `**Status:** ✅ Done`, `changed_shared_canon_files_count`, `changed_shared_canon_files`, `proof_kind`, `target_repo_impact` и ровно одним closure lane (`snapshot_path` / `report_path` / `no_op_reason`).
- Для durable receipt `proof_kind` — закрытый enum `snapshot|report|no_op`. Отчётный proof закрывается как `proof_kind: report` + meaningful `report_path`; не добавляй свободные/выдуманные machine values вроде `bounded_canon_sweep_report` или `structural_skeleton`.
- Closure lane должен совпадать с `proof_kind`: `snapshot` -> `snapshot_path`, `report` -> `report_path`, `no_op` -> enum-like `no_op_reason`; остальные closure fields остаются `N/A (why=...)`.
- Если изменились shared process canon carriers (`docs/roles`, `docs/tools/prompts`, `docs/playbooks`, templates/ADR/guides), следующий merge-tracker шаг = `step:packetization_gate`: `planveyor_post_merge_packetization_gate --range "$RANGE"`. Report обязан либо показать packet coverage, либо оставить blocking `missing-packet` / `unknown_target_mapping` row.
- (Опционально) follow-up dev-plan с задачами “починить/досушить/убрать дубли”.

## Процесс

1) Зафиксировать диапазон изменений
- `git log --oneline BASE..HEAD | head`
- `git diff --name-only BASE..HEAD`

2) Выделить “канон”, который надо проверить
Канон (strict doc_lint roots):
- `docs/roles/`
- `docs/playbooks/`
- `<target-declared guide carrier>`
- `<PROJECT_ARCH_DOC>`

Важно:
- optional canon roots проверяем только если путь реально существует в текущем repo/profile;
- если declared project canon carrier отсутствует, это `N/A`, а не sweep-bug;
- перед `rg` по fixed path list сначала сузить список до существующих путей (`test -e ...` / `rg --files docs` / эквивалент), чтобы не плодить шумные `No such file or directory`.

Также часто влияет на канон, даже если файл не менялся напрямую: declared
architecture/API/schema/registry/runtime/UI carriers, названные в `Context links`
выбранного проекта. Shared corpus не назначает им фиксированные имена.

3) Осушить канон (коротко + pointers)
Правила:
- Канон должен читаться быстро (ориентир: 1–3 минуты на файл).
- В каноне не держим “историю обсуждения”, “почему 5 раз переделывали” и большие tool-output.
- Если нужен контекст/эволюция/альтернативы — подними durable fact в канон / audit / follow-up. Snapshot можно сделать отдельно только как history/handover artifact.
- Active canon не ссылается на `docs/snapshots/*`, включая merge-wave/range и topic-specific snapshot'ы: snapshot не является durable source of truth.

Рекомендуемый шаблон для переноса:
- В каноне оставить: `Decision/Constraint → pointer(s)` (1–5 буллетов), где pointer ведёт в канон / audit / follow-up, а не в snapshot.
- Если нужен отдельный history/handover artifact, его можно сохранить в `docs/snapshots/YYYYMMDD_HHMM_architect_<topic>.md`, но active canon на него не ссылается.

4) Зафиксировать найденное (если всплыло)
Если всплыли новые/изменившиеся **Key decisions / Constraints / Goal** — зафиксируй это в plan (append-only; `Architect suggestions` / `Follow-ups (deferred)`) и/или сделай snapshot (если решение/проверка неочевидные). Канон обновляем отдельным follow-up dev-plan, а не в рамках sweep.

5) Финальный scrub для durable artifacts
- Если sweep не создал snapshot, оставь durable receipt/report `docs/reviews/*_canon_sweep_receipt_range_<base7>_<head7>.md` с `**Status:** ✅ Done`; `proof_kind` должен быть одним из `snapshot`, `report`, `no_op`; `report` требует `report_path`, `snapshot` требует `snapshot_path`, а `no_op_reason` должен быть коротким enum-like token (`no_shared_canon_changes`, `source_only`, `already_current`, ...), а не свободным текстом.
- Для любого shared impact receipt обязан назвать `packetization_handoff: step:packetization_gate ...`; сам packetization report остаётся отдельным gate и не подменяет execution/no-op proof.
- Step-local preflight для `canon_sweep` запускай до tracker tick через `planveyor_post_merge_receipt_preflight canon_sweep --path <canon-sweep-receipt>`: только на этом раннем шаге literal handoff `step:packetization_gate` допускает green без future packetization report. Output обязан содержать `proof_scope=step_local_receipt`, `terminal_readiness=not_evaluated`, `packetization_state=handoff_recorded_future_step_pending`; это не ready-to-push, а передача обязательства в следующий gate. `planveyor_merge_bundle_report` остаётся terminal authority и требует active report до final readiness.
- Если ты создал новый `docs/reviews/*` / `docs/followups/*` или отдельный history snapshot, перед handoff вычисти transient session-state:
  - не оставляй ложные `dirty` / `untracked` / “только что локально создали” формулировки,
  - если repo-state важен для восстановления, либо подними exact live fact, либо замени на команду проверки (`git status -sb`, `git log -1 --oneline`),
  - не оставляй `UNCONFIRMED` там, где дешевле и честнее добрать факт локальной командой.
- Отдельно проверь snapshot-policy:
  - active canon не должен получить pointer ни на один `docs/snapshots/*`;
  - selected registry/canon carrier не должен содержать блоков с контекстом
    merge-wave snapshot[s];
  - если snapshot содержит важный факт, промоуть сам факт в канон / audit / follow-up, а не ссылку на snapshot.

6) Проверить, что канон не ссылается на времянку
Перед планируемым удалением `docs/plans/*` / `docs/code_reviews/*`:
- `rg -n "docs/plans/|docs/code_reviews/|docs/doc_reviews/" <existing canon roots>`
  - пример: `AGENTS.md docs/roles docs/playbooks <target-declared guide carrier>` + `<PROJECT_ARCH_DOC>` только если он materialized в текущем repo
- Если ссылки нужны — заменить на:
  - audit-report в `docs/reviews/*`, или
  - follow-up / audit anchor / канон, или
  - “git history: <filename>”.
- Для ADR frontmatter `source-plan` действует тот же принцип: после sweep не оставляем live-ссылку на удаляемый timestamped plan; пишем `git history: <plan_stem>`, а проверку переносим на durable canon/code-anchor.
- Дополнительный guard для canon-sweep:
  - `rg -n "docs/snapshots/[0-9]{8}_[0-9]{4}_architect_range_.*_canon_sweep\\.md|Контекст merge-wave snapshot[s]" <existing active canon roots>`
  - Добавляй declared architecture/API/schema/registry carriers только если пути реально существуют; consumer выбирает собственные declared roots.
  - Если есть совпадения в active canon: это не “ok pointer”, а sweep bug. Убираем ссылку и переносим durable fact в канон / audit / follow-up.

7) Gate: doc_lint (strict)
- Self-Planveyor only primary route: `bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" ...`
- Sibling uses `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`; target-local exact artifact hygiene belongs in this phase's local section.
- Strict details: см. `docs/playbooks/doc_lint.md`

8) Docs diff sanity (только текущий diff)
- `git diff --check -- docs`
- Что это даёт: быстро показывает accidental trailing whitespace, CRLF, merge markers и лишние пустые строки в конце файла **в изменённых doc-файлах**.
- Если `git diff --check` ругается только на новые Markdown hard-break lines, не тащи raw trailing spaces в свежий артефакт: перепиши изменённый блок в bullets/параграфы/таблицу и только потом закрывай sweep.

7) Если нашли дубли/долги — оформить follow-ups
- Либо в существующий backlog (docs/followups/index.md), если такой index materialized в текущем repo, либо:
  - backlog файл в `docs/followups/` (см. `docs/followups/_template_followups_backlog.md`),
  - либо отдельный dev-plan в `docs/plans/` (если уже готовы делать работу).
- Если target-local consumer не materialize-ит docs/followups/index.md, standalone range backlog остаётся валидным outcome; не создавай master index только ради прохождения sweep.

## Команды (шпаргалка)
```bash
git diff --name-only BASE..HEAD

# Self-Planveyor only:
bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" ...

# Self-Planveyor only:
bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" \
  --root AGENTS.md \
  --root docs/roles \
  --root docs/playbooks \
  --root <target-declared guide carrier> \
  --root docs/arch.md \
  --check-code-refs --code-refs-scope repo

# Sibling canonical link hygiene:
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint
```

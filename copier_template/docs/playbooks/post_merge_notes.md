# Playbook: Post-merge notes (step 0)

Зачем:
- быстро и по-человечески зафиксировать, что именно попало в `BASE..HEAD`, до более тяжёлых `plan_harvest` и `post_merge_audit`;
- собрать короткий owner-facing контекст, чтобы дальше не восстанавливать его по git log с нуля;
- не путать merge notes с audit: merge notes = seed/context, audit = глубокая верификация и cleanup-ready verdict.

Когда использовать:
- сразу после merge-range review / Architect triage;
- всегда перед `post_merge_plan_harvest`, даже если диапазон маленький;
- особенно полезно, если диапазон потом будет дожиматься несколькими doc/process шагами и `HEAD` ещё успеет сдвинуться.

Что это НЕ делает:
- не заменяет `docs/playbooks/post_merge_plan_harvest.md`;
- не заменяет `docs/playbooks/post_merge_audit.md`;
- не создаёт follow-up планы автоматически и не закрывает merge-quality вопросы вместо review-range.

## Входные
- `BASE..HEAD`
- shared/default template: `docs/reviews/_template_merge_notes.md`
- optional profile override: `docs/reviews/profiles/<repo_profile>/_template_merge_notes.md`
- optional contextual evidence: existing pre-merge gate receipt (`docs/reviews/*_ai_gate_*.json` или repo-local equivalent); transient `.tmp/...` receipt from `planveyor_ai_gate_smoke --receipt-path ...` = wrapper sanity only и не считается durable merge evidence

## Выходные
- merge notes artifact: `docs/reviews/*_merge_notes_range_<base7>_<head7>.md`

## Порядок

1) Создай artifact через wrapper contract
- Preferred: `planveyor_arch_merge_notes_start`
- Fallback: создать файл через template contract `profile override -> shared default`

2) Сними инвентаризацию по диапазону
- helper-backed stats: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_merge_range_stats_json "$BASE" "$HEAD"`
  - в артефакте печатай labels literal: `total_commits`, `first_parent_commits`, `changed_files`, `diffstat_summary`;
  - не смешивай unlabeled total count и first-parent count в prose.
- `git diff --name-only "$BASE..$HEAD" -- docs/plans`
- `git diff --name-only "$BASE..$HEAD"`
- по планам из диапазона вытащи хотя бы `# Plan:` и финальный `**Status:**`

3) Заполни merge notes коротко
- `TL;DR` / `Что изменилось`: 3–7 bullets максимум
- `UX / UI`: только concrete delta, mode/URL если это известно; иначе `UNCONFIRMED`
- `Data / Migrations`: только факты из range, без догадок
- `Ops / Deploy`: только реально изменившиеся env/flags/commands
- `Risks / Caveats`: не ретеллим весь review artifact, а фиксируем живые хвосты
- `Follow-ups`: seed-only pointers; canonical backlog потом materialize-ится уже через harvest/audit
- `Evidence`: команды/смоуки/visual refs коротко, без deep proof matrix
- если pre-merge gate receipt уже materialized, упомяни literal `PASS|WARN|BLOCK` как contextual seed и не пересказывай те же mechanical scans “по памяти”; `.tmp/` smoke receipt допустим только как sanity note, не как durable merge carrier

4) Зафиксируй дальнейший маршрут
- Merge notes = step 0 и human-readable context layer.
- Даже для “маленького” диапазона merge notes не отменяют downstream `plan_harvest`.
- “Lightweight range” означает только то, что downstream audit может быть компактным; он не даёт права молча пропускать `plan_harvest`/`audit`, если те всё ещё требуются текущим pipeline или owner boundary.

### Lightweight range heuristics
- обычно `≤4` commits;
- нет schema/migration drift;
- нет новых canon-contract changes (`AGENTS.md`, объявленные project canon carriers, shared prompts/playbooks);
- нет новых public API / UI contract changes;
- нет новых dependency / security-sensitive surface changes.

Если хоть один пункт спорный, merge notes фиксируют это в `Risks / Caveats`, а решение о глубине downstream audit остаётся за Architect/Owner.

## Связь с downstream steps
- `merge_notes.risks` → candidate blockers / focus points для `post_merge_audit`
- `merge_notes.follow-ups` → seed-only input для `post_merge_plan_harvest`
- `merge_notes.ui_ux_delta` → scope pointer для runtime visual sanity
- `merge_notes.data / ops` → migration/deploy notes для later audit / owner closeout

## Гейты
- внутри самого файла merge notes должны дойти до `**Status:** ✅ Done`, иначе merge-tracker step не закрыт;
- если после merge notes появились новые doc/code commits, range надо пересохранить, иначе downstream steps будут читать устаревший `HEAD`.

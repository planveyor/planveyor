[ALWAYS START]
Ты работаешь как роль Architect в выбранном проекте и активном repo-profile.

Цель этого запуска: подготовить human‑readable merge notes “что изменилось” для диапазона `BASE..HEAD` и довести файл до `**Status:** ✅ Done`, если артефакт заполнен и готов.

Входные (уже переданы в окружении этого запуска):
- `BASE=...`
- `HEAD=...`
- `OUT=...` (файл merge notes в `docs/reviews/*`; если файла нет — создай через тот же contract: `profiles/<repo_profile>/_template_merge_notes.md` при наличии, иначе shared default `docs/reviews/_template_merge_notes.md`)

Жёстко:
- Это НЕ работа по plan и НЕ routing по status.
- `OUT` и чат пиши на русском; код/идентификаторы/пути/команды — на английском; UI-строки — на языке, объявленном проектом. Англоязычная narrative-проза в `OUT` = invalid output; перед `✅ Done` перепиши её на русский.
- `docs/plans/*` не правим и статусы в планах не меняем.
- Продуктовый код/шаблоны/миграции не трогаем.
- Разрешено править только `docs/reviews/*` (включая `OUT`). Не создавай и не цитируй snapshot'ы в `OUT`: если важен durable факт, подними его прямо в merge notes или оформи follow-up / audit / canon update.
- Не “додумывай”: если не уверен — помечай `UNCONFIRMED`.
- Для merge-tracker plain existence файла недостаточно: успешный исход этого шага = `OUT` существует и в header стоит `**Status:** ✅ Done`.

Что сделать:
1) Открой `docs/playbooks/post_merge_notes.md`, затем `OUT` и заполни его по шаблону (коротко и по делу).
2) Сними инвентаризацию по git (сам, без просьб к Owner):
   - helper-backed stats (single source для чисел range): `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_merge_range_stats_json "$BASE" "$HEAD"`
   - планы в диапазоне: `git diff --name-only "$BASE..$HEAD" -- docs/plans`
   - основные изменения: `git diff --name-only "$BASE..$HEAD"`
3) По планам из (2): для каждого извлеки `# Plan:` и финальный `**Status:**` (lenient), сгруппируй по подтемам как удобно (обычно 3–6 групп).
4) В `OUT` дай:
   - “TL;DR” (3–7 bullets),
   - “Range stats”: literal labels из helper output (`total_commits`, `first_parent_commits`, `changed_files`, `diffstat_summary`); не печатай unlabeled commit count,
   - “Что изменилось” по группам/подсистемам (UI/API/Docs/Process и т.п.),
   - Если есть UI изменения: укажи конкретные declared pages/elements and runtime modes/states, критичные для ретеста (если known, иначе `UNCONFIRMED`),
   - Если в диапазоне были миграции/изменения модели — отметить (без запуска команд),
   - Follow-ups: 0–10 пунктов, только то, что реально стоит завести отдельными dev‑планами.
5) Если `OUT` заполнен и готов — переведи header `**Status:**` в `✅ Done`.
6) Если сознательно оставляешь `Draft` (например, фактов не хватает, диапазон спорный, нужен ручной добор) — явно пометь пробелы как `UNCONFIRMED` и в чате верни blocker: такой merge-notes шаг нельзя тикать.
7) Сохрани `OUT`.

Выход (в чат):
- `OUT=<path>`
- `STATUS=<Draft|✅ Done>`
- 3–10 bullets “что я нашёл/что важно” (без простыней; детали уже в `OUT`).

[/ALWAYS START]

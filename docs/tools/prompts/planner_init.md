[ALWAYS START]
Ты работаешь как роль **Planner** в выбранном проекте и активном repo-profile.

0) Если в env выставлен `ROLE_BUNDLE_PATH` и файл существует — открой его как optional compiled runtime context. Это generated-only additive artifact: source of truth остаются `AGENTS.md`, role doc и этот prompt.

1) Открой и прочитай `AGENTS.md`.
2) Открой и прочитай `docs/roles/planner.md` целиком. Выполни раздел `## Обязательный старт (session bootstrap; 1 раз на role‑сессию)` линейно.
2.1) Provenance carrier later in this role is repo-backed only: use helper surfaces from the role doc, not chat-memory guesses.
3) В этом запуске **не** работай по планам и **не** меняй репозиторий:
   - нельзя: редактировать/создавать файлы, делать git‑операции, запускать команды, которые меняют данные/состояние (migrate/seed/smoke и т.п.);
   - можно: читать файлы и делать read-only поиск/навигацию по репо (например: `rg`, `ls`, `sed -n`).

Сейчас верни в чат ТОЛЬКО:
- Next: Owner
- Open items: (to=Owner, needs_owner=yes) Provide `PLAN_PATH`
[/ALWAYS START]

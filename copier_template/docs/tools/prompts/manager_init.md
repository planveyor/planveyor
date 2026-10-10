[ALWAYS START]
Ты работаешь как роль **Manager** в выбранном проекте и активном repo-profile.

1) Открой и прочитай `AGENTS.md`.
2) Открой и прочитай `docs/roles/manager.md` целиком. Выполни раздел `## Обязательный старт (session bootstrap; 1 раз на role‑сессию)` линейно.
2.1) `## Plan provenance / session context` is repo-backed audit context only; routing still follows `**Status:**`, Q&A, and literal review/rerun carriers.
3) В этом запуске **не** работай по планам и **не** меняй репозиторий:
   - нельзя: редактировать/создавать файлы, делать git‑операции, запускать команды, которые меняют данные/состояние (migrate/seed/smoke и т.п.);
   - можно: читать файлы и делать read-only поиск/навигацию по репо (например: `rg`, `ls`, `sed -n`).

Сейчас верни в чат ТОЛЬКО:
- Next: Owner
- Open items: (to=Owner, needs_owner=yes) Provide `PLAN_PATH`
[/ALWAYS START]

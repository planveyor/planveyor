# Шаблон: docs/roles/<role>.md

Цель: держать роли **самодостаточными** (“короткая памятка + pointers”), но **без дублирования** plan‑шаблона и плейбуков.

Важно про “точку входа”:
- Процессный корень = `AGENTS.md`. Owner (или init‑prompt) читает его **перед** ролью.
- Внутри роли не дублируем “прочитать `AGENTS.md`”, чтобы не создавать петлю навигации. В роли достаточно `Source of truth / precedence` и прямых правил stop-the-line.

## Каркас роли (копируй и заполняй)

```md
# Роль: <RoleName> (<RU name>)

**Runner:** <RUNNER>
**Артефакт:** <MAIN ARTIFACT(S)>
**Вход:** <INPUT>
**Выход:** <OUTPUT>

Цель: <1–2 строки>

Термины:
- `PLAN_PATH` — путь к файлу plan (обычно `docs/plans/YYMMDD_HHMM_topic.md`), который Owner передаёт в статусном промпте.

## Source of truth / precedence (если есть конфликт)
- Процесс и формат работы роли: `AGENTS.md`.
- Контракт задачи: `PLAN_PATH` (и правила/шаблон plan: `docs/plans/README.md`, `docs/plans/_template.md`).
- Канонические контракты системы: current `PLAN_PATH -> Context links`, `AGENTS.md`, shared role/playbook corpus и declared target-local canon. Product-specific paths не являются default и не создаются как profile tree без реального consumer owner.
- Durable shared process invariants (`PLAN_PATH` truth, review-route host, exact bundle, rollout-packet boundary) не пересказываем inline: роль ссылается на accepted ADR в `docs/adr/*` и держит здесь только operational wording.

Правило: если plan конфликтует с каноникой или двусмысленен — фиксируем это в plan (Q&A/objections/suggestions) и возвращаем процесс на нужный `**Status:**`, а не “решаем молча”.

## Границы роли (жёстко)
- Можно/нужно: <что обязан делать>
- Нельзя: <что не должен делать>
- Stop-the-line: <когда обязан остановиться и вернуть статус назад>

## Обязательный старт (session bootstrap; 1 раз на role‑сессию)
Сделай в этом порядке (линейно, без неоднозначных “если нужно”):
1) Прочитать `docs/plans/README.md` + `docs/plans/_template.md`.
2) Если в запуске уже дан `PLAN_PATH`: открыть plan и прочитать целиком (включая `Context links` + связанные артефакты).
3) Если plan затрагивает важную канонику, а ссылок нет — сначала определить repo-profile/bootstrap reference bundle, затем дописать только реально существующие/объявленные profile-local anchors в `Context links` и прочитать нужные доки.

## Работа по `PLAN_PATH` (каждый запуск)
- Source of truth для “кто следующий” и текущего `**Status:**` = plan (не ledger).
- Вся рабочая переписка (Q&A/suggestions/objections/status/evidence) — в plan; в чат — только итог (Next/Open items), если это закреплено статусным промптом.

## Чек‑листы и gates
Канон: `docs/plans/_template.md`. Чек‑листы и гейты живут **в plan**, не в роли (иначе дрейф).

## Role-specific pointers (optional)
Короткий список “куда смотреть” по роли (без пересказа правил):
- <canon doc 1>
- <canon doc 2>
- <canon doc 3>

## Контекст и маршрутизация

Правила:
- “Кто следующий” и текущий `**Status:**` всегда берём **только из plan**.
- Контекст/почему/эволюция — через `docs/snapshots/*` и артефакты plan.

## После merge (post-merge)
- Пост‑мерж проверки/аудит/док‑гигиена — через `docs/playbooks/*` (роль не превращаем в плейбук).
- Удаление временных файлов делает Owner; роль готовит артефакт/список и убирает ссылки из каноники.

## Тон общения
- Профессионально и по делу, без ненормативной лексики.
```

## Напоминания (для автора роли)
- Роль не должна дублировать `docs/plans/_template.md` (чек‑листы/гейты/секции планов — только там).
- Исключение “анти‑лень” (для слабых/ленивых моделей): допускается **минимальное** дублирование, если это снижает реальные регрессии:
  - Один короткий FULL‑gate (handoff/review), который является **копией** одного чеклиста из `docs/plans/_template.md` (в тексте блока явно пометить: “DUPLICATE OF: `docs/plans/_template.md` → <section> (source of truth)”).
  - 1–2 “pointers” на быстрые инструменты проверки фактов (например, `planveyor_help` и `rg`).
  - Запрещено дублировать: статусную модель/роутинг/ownership статусов, ledger‑правила, структуру plan или большие “how‑to” фрагменты (это приводит к дрейфу и конфликтам).
- Роль может содержать короткие pointers на declared target-local canon, но не пересказывает его и не делает product-specific docs default для shared corpus.
- Любой сценарий “как делать” (review‑механика, post-merge, smoke) лучше выносить в `docs/playbooks/*`, а в роли оставлять короткую ссылку.

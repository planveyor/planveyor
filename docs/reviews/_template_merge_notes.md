# Review: Merge notes — <topic>

**Date:** DD.MM.YYYY HH:MM
**BASE:** <sha>
**HEAD:** <sha|HEAD>
**RANGE_ID:** range_<base7>_<head7>
**Topic:** <short>
**Status:** Draft | ✅ Done
**Schema version:** review.v1

Зачем этот файл: человеко‑читаемо зафиксировать “что изменилось” для диапазона `BASE..HEAD`.
Это **не финальные релиз‑ноты** — это черновик по конкретному merge/ветке, который потом можно агрегировать.

Правила:
- держим коротко (цель: 2–5 минут чтения);
- по возможности **не** ссылаться на временные `docs/plans/*` / `docs/code_reviews/*` путями (они могут быть удалены); вместо этого — название файла в git history или ссылка на audit‑report.
- Schema compatibility: `current` = literal `**Schema version:** review.v1`; versionless historical merge notes = `legacy`; любой другой explicit value = `unsupported`.

## Что изменилось (human-readable)
- <фича/поведение: что видит пользователь>

## Range stats
- Source: `planveyor_merge_range_stats_json BASE HEAD`
- Merge tracker header consistency: `.planveyor.merge_tracker.md` fields `BASE`, `HEAD`, optional `MERGE_SHA`, `RANGE` and `RANGE_ID` match saved `.planveyor.range.*`.
- `total_commits`: <N>
- `first_parent_commits`: <N>
- `changed_files`: <N>
- `diffstat_summary`: <summary>

## UX / UI
- <что изменилось в UI; какие declared modes проверены>

## Data / Migrations (если есть)
- <что поменялось в схеме/инвариантах>

## Ops / Deploy (если есть)
- <env vars, команды, фиче‑флаги, миграции>

## Risks / Caveats
- <S1/S2 риски, которые остаются>

## Follow-ups
- <куда завели follow-up (plan/backlog/guide)>

## Evidence
- Tests/smokes: <команды / краткий итог>
- Visual: <что проверили + где лежат скриншоты (если есть)>

# Git (worktree): rebase, detached HEAD, rescue

Цель: быстрые рецепты “что делать”, когда что-то пошло не так с веткой/ребейзом в окружении с `git worktree`.

## Где какая ветка (worktree)

```
git worktree list
git status -sb
git branch --show-current
```

## Rebase: конфликт → продолжить/откатить

```
git status
# resolve conflicts in files
git add -A
git rebase --continue
```

Откатить ребейз целиком:
```
git rebase --abort
```

Пропустить проблемный коммит (редко; только если точно понимаешь последствия):
```
git rebase --skip
```

## Detached HEAD (вместо имени ветки показывается “только SHA”)

Признаки:
- `git status -sb` показывает `## HEAD (no branch)` (или IDE показывает “просто номер/sha”).

Быстро вернуться на ветку:
```
git switch <branch-name>
```

Если на detached HEAD уже появился “важный” коммит — сначала сохрани его отдельной веткой:
```
git switch -c rescue/<topic>
```

Если коммит уже известен по SHA (например, из `git reflog`):
```
git branch rescue/<topic> <sha>
```

## Как понять, что уже было запушено

```
git fetch origin
git status -sb
git log --oneline --decorate -n 20
```

Посмотреть, чем локальная ветка отличается от удалённой:
```
git log --oneline origin/<branch>..HEAD
```

## Amend / rename / reflog (rescue)

Правило безопасности: если коммит уже в `origin/*`, то `--amend`/rebase = переписывание истории (нужно `git push --force-with-lease`, только осознанно).

Amend последний коммит (например, забыл файл/сообщение):
```
git add -A
git commit --amend
```

Переименовать ветку:
```
git branch -m <old> <new>
```

Восстановить “потерянный” коммит через reflog:
```
git reflog
git switch -c rescue/<topic> <sha>
```

## Подтянуть `main` в feature‑ветку (без сюрпризов)

Если ветка **ещё не пушилась** (или можно переписать историю) — можно `rebase`:
```
git fetch origin
git rebase origin/main
```

Если ветка **уже пушилась** и её могли взять другие — безопаснее `merge`:
```
git fetch origin
git merge origin/main
```

Примечание: `git push --force-with-lease` используем только осознанно и только если договорились переписывать историю ветки.


## Git: rebase после конфликтов (VS Code / terminal)

Симптом: в VS Code вместо имени ветки видишь хеш — это нормально, если rebase ещё идёт (detached HEAD).

Мини‑алгоритм (CLI — самый надёжный):
1) Проверить состояние: `git status` (должно явно говорить про rebase и что делать дальше).
2) После resolve конфликтов: `git add -A`
3) Продолжить: `git rebase --continue`
   - Если VS Code просит сообщение коммита/похоже на amend — это может быть шаг rebase. Закончить ввод и снова `git rebase --continue`, пока не закончится.
4) Если нужно отменить: `git rebase --abort`
5) Если нужно пропустить патч: `git rebase --skip`

Проверка финала:
- `git status` должен быть “clean”.
- `git branch --show-current` должен снова показывать ветку (не пусто).

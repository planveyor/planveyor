---
description: Подготовить текущую ZCode-сессию как Manager Planveyor
---

Ты работаешь как Manager Planveyor в collab pipeline. Эта команда подготавливает
только текущую main-сессию; задачи ролям и выполнение плана начинаются лишь в
следующем сообщении Owner.

Прочитай по порядку:

1. `AGENTS.md`, если он ещё не был прочитан в этой сессии.
2. `docs/roles/manager.md` целиком и выполни его обязательный session bootstrap.
3. `docs/tools/prompts/manager_init.md`.
4. `docs/tools/prompts/manager_collab_pipeline.md` целиком.
5. `docs/tools/prompts/zcode/manager_pipeline.md` целиком. Это transport
   overlay; он не заменяет семантику Manager-контракта.

## Lifecycle bootstrap before any Agent

До чтения ролями и до первого `Agent` подготовь только cooperative lineage
этой main-сессии.

1. Получи canonical absolute `PROJECT_ROOT` из явного контекста открытого
   проекта. Он должен существовать, быть директорией и не быть symlink. Не
   выводи его из домашнего каталога. Получи canonical absolute
   `PLANVEYOR_RUNTIME_ROOT` как корень этой установленной копии Planveyor; он
   тоже не выводится из `PROJECT_ROOT`.
2. Установи `PYBIN="${PYBIN:-python3}"`. Возьми exact host-provided
   `MANAGER_SESSION_ID`. На первом вызове этой команды создай fresh safe-token
   `TEAM_EPOCH` и держи оба значения только в памяти Manager.
3. До любого `Agent` вызови literal interpreter entrypoint:

   ```sh
   "$PYBIN" -B "$PLANVEYOR_RUNTIME_ROOT/scripts/zcode_bootstrap_lifecycle.py" init_epoch \
     --project-root "$PROJECT_ROOT" \
     --tooling-root "$PLANVEYOR_RUNTIME_ROOT" \
     --manager-session-identity "$MANAGER_SESSION_ID" \
     --team-epoch "$TEAM_EPOCH"
   ```

   Сразу после него вызови тем же literal interpreter entrypoint
   `read_exact_epoch` с теми же identity values. Продолжать можно только при
   `verdict=epoch_current`.
4. Повторный `/manager-init` в той же main-сессии использует retained
   `MANAGER_SESSION_ID + TEAM_EPOCH`. `init_epoch` должен быть
   exact-idempotent. Если retained values утрачены, не ищи старую запись по
   carrier, mtime или agentId: остановись и начни новую main-сессию с новым
   epoch.

Helper создаёт только runtime carrier
`<PROJECT_ROOT>/.planveyor.zcode.bootstrap.<TEAM_EPOCH>.json`. Его readback —
manager_attested_cooperative_lineage, а не security, authentication, process,
model или prompt-reading attestation.

Перед первым fresh `Agent` собери `CONTRACT_READS` по `manager_pipeline.md`.
В manifest обязательно войдут exact SHA-256 трёх public ZCode bodies: эта
команда, `.zcode/agents/planveyor-role-agent.md` и
`docs/tools/prompts/zcode/manager_pipeline.md`. Helper отвергнет reservation,
где хотя бы одного из них нет, и rehash-проверка остановит dispatch при drift.

На этом bootstrap-вызове не изменяй tracked project files, не выполняй
git-операции, не запускай роли и не начинай pipeline. Единственный допустимый
write — описанный lifecycle carrier. Direct Manager execution, role transport,
CENSOR и recovery выполняются по `manager_pipeline.md` только после явной
команды Owner.

После чтения верни в чат только:

```text
Next: Owner
Open items: (to=Owner, needs_owner=yes) Provide PLAN_PATH (следующим сообщением: MANAGER_CMD=run <PLAN_PATH>)
```

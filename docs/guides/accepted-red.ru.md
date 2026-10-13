<!-- i18n: pair=docs/guides/accepted-red.md pair-sha256=6d6f27fc7d5eab275e7d0048402374d7ec65f08bfd51c3027407973cd25baf48 self-sha256=a98765c7eb9d55b488eee81ed3bc73f8d03b9de9139e3435d784dfe499079c96 -->
# План, принятый красным, и сохранение доказательств

[English](accepted-red.md) · **Русский**

Документ описывает контракт, который реализуют `planveyor_plan_bundle` (режимы `--closeout-json`, `--capture-rejected`, `--verify-rejected`, `--cleanup-rejected`), Oracle плана, `planveyor_docs_closeout` и вспомогательный скрипт очереди. Команды ниже вызываются через фасад из корня проекта: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <command>`.

## Когда ревью «принято красным»

План закрыт не зелёной поставкой, а заменой: Reviewer оставил открытые блокеры S1, Architect принял расширение границ задачи и передал работу преемнику. Oracle (`planveyor_plan_status_oracle --json`) называет такой план `terminal_disposition=accepted_red_supersession`, если выполнены все условия:

- `**Status:** Superseded`;
- `plan_meta.scope_expansion.state` равно `architect_accepted`, а `source_ref` — `<review>#B<N>`, один из блокеров ревью;
- в `plan_meta.next_plans` ровно один преемник; у преемника `plan_meta.parent` указывает на этот план, а в шапке преемника (до первого заголовка `##`) есть ссылки `<review>#B<N>` ровно на все блокеры ревью;
- в разделе `## Review artifacts` объявлено ровно одно ревью с тем же именем, что у плана: `docs/code_reviews/<stem>.md` или `docs/doc_reviews/<stem>.md`, и второго такого файла нет;
- ревью красное: `**Status:**` содержит `❌`, есть строка `**Target:** BUNDLE=current bundle_sha256=<64 hex>` и один раздел `## S1 Blocker`, где каждый блокер — подраздел `### B<N>` с полями `- Blocker ID: B<N>` и `- Current state: open`;
- черновик кода `docs/code_drafts/<stem>__code_draft.md` ссылается на этот план в `code_draft_meta.plan` и перечисляет непустые `targets`.

Если план в статусе `Superseded`, `scope_expansion.state=architect_accepted` и преемник один, а остальное не сходится, Oracle всё равно называет план принятым красным (accepted-red), с причиной `accepted_red_carrier_invalid`, `accepted_red_review_route_invalid` или `accepted_red_review_invalid`. Так же, с `accepted_red_carrier_invalid`, читается план без этих признаков, для которого уже есть ссылка Git `refs/planveyor/rejected-baselines/<stem>/…`. Если план отвечает всем условиям, причина (`terminal_disposition_reason`) показывает этап: `accepted_red_current_snapshot` — сохранения ещё нет, отклонённые байты на месте; `accepted_red_durable_capture` — ссылка есть и цела; `accepted_red_snapshot_mismatch_without_durable_ref` — ссылки нет, а байты уже не совпадают с ревью; `accepted_red_snapshot_mismatch_without_valid_durable_ref` — ссылка повреждена.

Для плана, принятого красным, Oracle всегда отвечает `delivery_green=false`, `staging_policy=forbidden`, `durable_capture_required=true`. Байты целевых файлов, которые видел Reviewer, — доказательство, а не поставка. Их нельзя добавлять в индекс и коммитить от имени этого плана.

## Кто что запускает

- Architect принимает маршрут: ставит `architect_accepted`, заводит преемника и переводит план в `Superseded` (`docs/tools/prompts/architect_status_driven.md`).
- Исправление ведёт отдельный незавершённый план восстановления (recovery plan) обычным циклом ролей.
- Сохранение, проверку и очистку Owner запускает вручную. Manager и роли эти режимы не вызывают. Когда план, принятый красным, стоит в очереди, вспомогательный скрипт очереди отвечает на него кодом `terminal_closeout_admission_rejected` с `reason_code=accepted_red_reconciliation_required`, и Manager передаёт этот ответ Owner (`docs/roles/manager.md`). Закрытие документов такого плана остаётся `blocked`, пока нет очистки. Порядок действий Owner при инциденте описан в `docs/playbooks/manual_terminal_recovery.md`.

## Жизненный цикл

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --verify-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --capture-rejected --recovery-plan <RECOVERY_PLAN> <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --cleanup-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --closeout-json <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_closeout <SOURCE_PLAN> --json
```

Режимы `planveyor_plan_bundle` отвечают JSON `planveyor_plan_bundle_closeout.v1` в stdout с кодом 0, а при отказе — JSON `planveyor_rejected_baseline_error.v1` со `state=blocked` и `reason_code` в stderr с кодом 2. `--recovery-plan` допустим только с `--capture-rejected`. Ключи закрытия, предварительной проверки и сообщения коммита (closeout, preflight, message) в этих режимах запрещены.

1. **Проверка** (`--verify-rejected`) только читает состояние. Пока сохранения нет, ответ — `recovery_state=capture_required`, если байты целевых файлов совпадают с ревью, или `snapshot_mismatch_without_durable_ref`, если уже не совпадают. Во втором случае сохранить отклонённые байты нельзя.
2. **Сохранение** (`--capture-rejected`) записывает отклонённые байты в Git. Для него нужны:
   - `--recovery-plan`: план восстановления, отдельный от исходного плана, не в `Done` и не в `Superseded`, со строкой ``- Superseded incident plan: `<SOURCE_PLAN>`.`` и ровно одним своим черновиком кода `docs/code_drafts/<recovery plan stem>__code_draft.md`, чьи `targets` пересекаются с целевыми файлами исходного плана;
   - индекс для целевых файлов совпадает с HEAD: отклонённые байты не добавлены в индекс;
   - текущий `bundle_sha256` исходного плана совпадает с `bundle_sha256` из строки `**Target:**` ревью.

   Повторное сохранение при целой ссылке ничего не меняет и возвращает текущее состояние. После сохранения — `recovery_state=cleanup_required`.
3. **Очистка** (`--cleanup-rejected`) возвращает каждый целевой файл к байтам HEAD, а целевой файл, которого нет в HEAD, удаляет. Для неё нужны целое сохранение, тот же HEAD, что при сохранении, индекс целевых файлов, равный HEAD, и целевые файлы только в двух состояниях: отклонённые байты или байты HEAD. Поэтому план восстановления меняет эти целевые файлы только после очистки. После очистки — `recovery_state=completed`, `closeout_kind=accepted_red_recovered`, `bundle_ok=true`; `delivery_green` остаётся `false`. Повторная очистка ничего не меняет.
4. **Закрытие.** Для плана, принятого красным, `--closeout-json` печатает тот же ответ, а не обычный ответ для точного набора файлов. При повреждённой записи он отказывает с `accepted_red_closeout_invalid_carrier`. `--stage`, `--commit-ready` и `--commit-exact` отказывают с `staging_forbidden`. `planveyor_docs_closeout` отвечает `completed` с `reason_code=accepted_red_recovery_completed` только после очистки и проверки квитанции. До этого он отвечает `blocked`, обычно с `accepted_red_recovery_incomplete` или причиной `accepted_red_*`. Если других правок документов нет, ответ содержит `final_docs_commit=no_op` с причиной `accepted_red_evidence_ref_materialized`.

После очистки план восстановления может менять целевые файлы из своего черновика кода: состояние `active_checkout_state=recovery_owned_overlap` допустимо. Изменение другого отклонённого целевого файла даёт `drifted`, и проверка отказывает с `active_checkout_drift`.

## Что сохраняется

Сохранение создаёт коммит, родитель которого — текущий HEAD (`captured_parent`), и ссылку `refs/planveyor/rejected-baselines/<stem>/<review_bundle_sha256>` на него. Дерево коммита — дерево HEAD, в котором записаны:

- отклонённые байты всех целевых файлов исходного плана в том виде, в каком их видел Reviewer;
- четыре файла маршрута: исходный план, его черновик кода, ревью и преемник;
- `.planveyor/rejected-baselines/<stem>/<review_bundle_sha256>/manifest.json` со схемой `planveyor_rejected_baseline.v1`: исходный план и план восстановления, черновик кода и целевые файлы восстановления, ревью и его `bundle_sha256`, преемник, `captured_parent`, а для каждого целевого файла и файла маршрута — путь, sha256, размер, режим файла и oid blob-объекта.

Очистка добавляет дочерний коммит с `cleanup.json` рядом с манифестом (схема `planveyor_rejected_baseline_cleanup.v1`: итоговое состояние каждого целевого файла и повторная сверка файлов маршрута) и переносит ссылку на него.

Сохранение и очистка не меняют HEAD, ветки и индекс, рабочее дерево меняет только очистка. Ссылка публикуется одной транзакцией `git update-ref` при условии, что HEAD не сдвинулся. Иначе — отказ `recovery_ref_cas_conflict`.

## Как проверяется

- Каждое чтение заново проверяет ссылку целиком: цепочку родителей, манифест, квитанцию очистки и blob-объекты целевых файлов. Повреждённая ссылка даёт `durable_capture_state=invalid`, а сохранение и очистка поверх неё отказывают с `recovery_ref_invalid`.
- Четыре файла маршрута должны байт в байт совпадать с теми, что записаны при сохранении. Иначе — `routing_carrier_drift`: `--closeout-json` отказывает, а `planveyor_docs_closeout` отвечает `blocked`. Правка преемника до закрытия документов исходного плана тоже считается расхождением.
- Проверки отвергают замещающие ссылки Git (replace refs), `info/grafts` и переменные `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`, `GIT_REPLACE_REF_BASE` в окружении вспомогательного скрипта.
- В нейтральном движке не заданы обходы для исторических случаев: мост снимка (snapshot bridge) и перепривязка маршрута. Поэтому сохранение возможно, только пока текущие байты целевых файлов совпадают с ревью.

## Частые отказы

| `reason_code` | Что значит | Что делать |
|---|---|---|
| `not_accepted_red`, `routing_contract_invalid` | условия плана, принятого красным, не выполнены, записи неполны или в окружении есть переменные Git | сверить план, преемника, черновик кода и ревью с первым разделом |
| `recovery_plan_invalid` | план восстановления не подходит | поправить в нём строку исходного плана, статус или черновик кода |
| `rejected_target_staged` | отклонённые целевые файлы добавлены в индекс | убрать их из индекса |
| `snapshot_mismatch` | байты целевых файлов уже не совпадают с ревью | сохранение невозможно, решение — за Owner |
| `recovery_ref_cas_conflict` | HEAD сдвинулся во время записи ссылки или ссылка уже занята | прочитать `--verify-rejected` и повторить на неподвижном HEAD |
| `capture_required` | очистка без сохранения | сначала выполнить сохранение |
| `head_drift` | HEAD изменился после сохранения | проводить очистку на том же HEAD, что и сохранение (`captured_parent`) |
| `rejected_target_drift` | целевой файл не совпадает ни с отклонёнными байтами, ни с HEAD | разобрать изменения этого целевого файла |
| `routing_carrier_drift` | файл маршрута изменён после сохранения | вернуть байты из коммита сохранения |
| `staging_forbidden` | попытка добавить в индекс или закоммитить план, принятый красным | не добавлять в индекс, закрывать через очистку |

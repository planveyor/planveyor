# Accepted-red и forensic capture

Документ описывает контракт, который реализуют `planveyor_plan_bundle` (режимы `--closeout-json`, `--capture-rejected`, `--verify-rejected`, `--cleanup-rejected`), oracle плана, `planveyor_docs_closeout` и queue helper. Команды ниже идут через facade: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <команда>` из корня проекта.

## Когда ревью «принято красным»

Plan закрыт не зелёной поставкой, а заменой: Reviewer оставил открытые S1 blockers, Architect принял расширение scope и передал работу преемнику. Oracle (`planveyor_plan_status_oracle --json`) называет такой plan `terminal_disposition=accepted_red_supersession`, если выполнены все условия:

- `**Status:** Superseded`;
- `plan_meta.scope_expansion.state` равно `architect_accepted`, а `source_ref` — `<ревью>#B<N>`, один из blockers ревью;
- в `plan_meta.next_plans` ровно один преемник; у преемника `plan_meta.parent` указывает на этот plan, а в шапке преемника (до первого заголовка `##`) есть ссылки `<ревью>#B<N>` ровно на все blockers ревью;
- в разделе `## Review artifacts` объявлено ровно одно ревью с тем же именем, что у plan: `docs/code_reviews/<stem>.md` или `docs/doc_reviews/<stem>.md`, и второго такого файла нет;
- ревью красное: `**Status:**` содержит `❌`, есть строка `**Target:** BUNDLE=current bundle_sha256=<64 hex>` и один раздел `## S1 Blocker`, где каждый blocker — подраздел `### B<N>` с полями `- Blocker ID: B<N>` и `- Current state: open`;
- code draft `docs/code_drafts/<stem>__code_draft.md` ссылается на этот plan в `code_draft_meta.plan` и перечисляет непустые `targets`.

Если plan в `Superseded`, `scope_expansion.state=architect_accepted` и преемник один, а остальное не сходится, oracle всё равно называет plan accepted-red, с причиной `accepted_red_carrier_invalid`, `accepted_red_review_route_invalid` или `accepted_red_review_invalid`. Так же, с `accepted_red_carrier_invalid`, читается plan без этих признаков, для которого уже есть ref `refs/planveyor/rejected-baselines/<stem>/…`. У целого plan причина (`terminal_disposition_reason`) показывает этап: `accepted_red_current_snapshot` — capture ещё нет, отклонённые байты на месте; `accepted_red_durable_capture` — ref есть и цел; `accepted_red_snapshot_mismatch_without_durable_ref` — ref нет, а байты уже не совпадают с ревью; `accepted_red_snapshot_mismatch_without_valid_durable_ref` — ref битый.

Для accepted-red plan oracle всегда отвечает `delivery_green=false`, `staging_policy=forbidden`, `durable_capture_required=true`. Байты targets, которые видел Reviewer, — доказательство, а не поставка: их нельзя stage-ить и коммитить от имени этого plan.

## Кто что запускает

- Architect принимает маршрут: ставит `architect_accepted`, заводит преемника и переводит plan в `Superseded` (`docs/tools/prompts/architect_status_driven.md`).
- Исправление ведёт отдельный незавершённый plan восстановления (recovery plan) обычным циклом ролей.
- Capture, проверку и cleanup запускает владелец вручную. Manager и роли эти режимы не вызывают. В очереди queue helper на accepted-red plan отвечает `terminal_closeout_admission_rejected` с `reason_code=accepted_red_reconciliation_required`, и Manager отдаёт payload владельцу (`docs/roles/manager.md`); закрытие документов такого plan остаётся `blocked`, пока нет cleanup. Порядок действий владельца при инциденте — `docs/playbooks/manual_terminal_recovery.md`.

## Жизненный цикл

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --verify-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --capture-rejected --recovery-plan <RECOVERY_PLAN> <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --cleanup-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --closeout-json <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_closeout <SOURCE_PLAN> --json
```

Режимы `planveyor_plan_bundle` отвечают JSON `planveyor_plan_bundle_closeout.v1` в stdout с кодом 0, а при отказе — JSON `planveyor_rejected_baseline_error.v1` со `state=blocked` и `reason_code` в stderr с кодом 2. `--recovery-plan` допустим только с `--capture-rejected`; опции closeout, preflight и message в этих режимах запрещены.

1. **Проверка** (`--verify-rejected`) только читает. Пока capture нет, ответ — `recovery_state=capture_required`, если байты targets совпадают с ревью, или `snapshot_mismatch_without_durable_ref`, если уже нет: сохранить отклонённые байты тогда нельзя.
2. **Capture** (`--capture-rejected`) сохраняет отклонённые байты в Git. Он требует:
   - `--recovery-plan`: plan восстановления, отдельный от source, не в `Done` и не в `Superseded`, со строкой ``- Superseded incident plan: `<SOURCE_PLAN>`.`` и ровно одним своим code draft `docs/code_drafts/<stem плана восстановления>__code_draft.md`, чьи `targets` пересекаются с targets source;
   - index для targets совпадает с HEAD: отклонённые байты не stage-нуты;
   - текущий `bundle_sha256` source совпадает с `bundle_sha256` из `**Target:**` ревью.

   Повторный capture при целом ref ничего не меняет и возвращает текущее состояние. После capture — `recovery_state=cleanup_required`.
3. **Cleanup** (`--cleanup-rejected`) возвращает каждый target к байтам HEAD, а target, которого нет в HEAD, удаляет. Он требует целый capture, тот же HEAD, что при capture, index targets, равный HEAD, и targets только в двух состояниях: отклонённые байты или байты HEAD. Поэтому plan восстановления меняет эти targets только после cleanup. После cleanup — `recovery_state=completed`, `closeout_kind=accepted_red_recovered`, `bundle_ok=true`; `delivery_green` остаётся `false`. Повторный cleanup ничего не меняет.
4. **Закрытие.** `--closeout-json` для accepted-red plan печатает тот же payload, а не обычный exact-bundle; при битом carrier — отказ `accepted_red_closeout_invalid_carrier`. `--stage`, `--commit-ready` и `--commit-exact` отказывают с `staging_forbidden`. `planveyor_docs_closeout` отвечает `completed` с `reason_code=accepted_red_recovery_completed` только после cleanup и проверки receipt, до этого — `blocked`, обычно с `accepted_red_recovery_incomplete` или причиной `accepted_red_*`. Если других правок документов нет, ответ содержит `final_docs_commit=no_op` с причиной `accepted_red_evidence_ref_materialized`.

После cleanup plan восстановления может менять targets из своего code draft: состояние `active_checkout_state=recovery_owned_overlap` допустимо. Изменение другого отклонённого target даёт `drifted`, и проверка отказывает с `active_checkout_drift`.

## Что сохраняется

Capture создаёт commit, родитель которого — текущий HEAD (`captured_parent`), и ref `refs/planveyor/rejected-baselines/<stem>/<review_bundle_sha256>` на него. Дерево commit — дерево HEAD, в котором записаны:

- отклонённые байты всех targets source в том виде, в каком их видел Reviewer;
- четыре файла маршрута: source plan, его code draft, ревью и преемник;
- `.planveyor/rejected-baselines/<stem>/<review_bundle_sha256>/manifest.json` со схемой `planveyor_rejected_baseline.v1`: source и plan восстановления, code draft и targets восстановления, ревью и его `bundle_sha256`, преемник, `captured_parent`, для каждого target и файла маршрута — путь, sha256, размер, mode и blob oid.

Cleanup добавляет дочерний commit с `cleanup.json` рядом с manifest (схема `planveyor_rejected_baseline_cleanup.v1`: итоговое состояние каждого target и повторная сверка файлов маршрута) и переносит ref на него.

HEAD, ветки и index capture и cleanup не меняют, рабочее дерево меняет только cleanup. Ref публикуется одной транзакцией `git update-ref` при условии, что HEAD не сдвинулся; иначе отказ `recovery_ref_cas_conflict`.

## Как проверяется

- Каждое чтение заново проверяет ref целиком: цепочку родителей, manifest, receipt cleanup и blob-и targets. Битый ref даёт `durable_capture_state=invalid`; capture и cleanup поверх него отказывают с `recovery_ref_invalid`.
- Четыре файла маршрута должны совпадать байт в байт с сохранёнными при capture: иначе `routing_carrier_drift`, `--closeout-json` отказывает, а `planveyor_docs_closeout` отвечает `blocked`. Правка преемника до закрытия документов source тоже считается дрейфом.
- Проверки отвергают Git replace refs, `info/grafts` и переменные `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`, `GIT_REPLACE_REF_BASE` в окружении helper.
- Обходы для исторических случаев (snapshot bridge и перепривязка маршрута) в нейтральном движке не заданы: capture возможен, только пока текущие байты targets совпадают с ревью.

## Частые отказы

| `reason_code` | Что значит | Что делать |
|---|---|---|
| `not_accepted_red`, `routing_contract_invalid` | условия accepted-red не выполнены, carriers неполны или в окружении есть Git-переменные | сверить plan, преемника, code draft и ревью с первым разделом |
| `recovery_plan_invalid` | plan восстановления не подходит | поправить его строку source, статус или code draft |
| `rejected_target_staged` | отклонённые targets stage-нуты | убрать их из index |
| `snapshot_mismatch` | байты targets уже не совпадают с ревью | capture невозможен; решение — за владельцем |
| `recovery_ref_cas_conflict` | HEAD сдвинулся во время записи ref или ref уже занят | повторить на неподвижном HEAD, прочитав `--verify-rejected` |
| `capture_required` | cleanup без capture | сначала capture |
| `head_drift` | HEAD изменился после capture | cleanup проводят на том же HEAD, что capture (`captured_parent`) |
| `rejected_target_drift` | target не совпадает ни с отклонёнными байтами, ни с HEAD | разобрать изменения этого target |
| `routing_carrier_drift` | файл маршрута изменён после capture | вернуть байты из capture commit |
| `staging_forbidden` | попытка stage или commit accepted-red plan | не stage-ить; закрывать через cleanup |

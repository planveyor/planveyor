# Process improvements backlog — <source>

**Date:** DD.MM.YYYY HH:MM ±HHMM
**Source ref:** `docs/plans/<PLAN_PATH>.md`
**Status:** Draft

Зачем этот файл: держать raw process-improvement suggestions отдельно от обычных implementation follow-ups и от канонических doc edits.

Правила:
- Truth surface = блоки `### PI-...` ниже.
- Derived surfaces `index.md`, `deferred.md`, `promotion_surface.md` пересобираются helper'ом; не редактируй их как primary source.
- Status family boundary: PI rows accept `open`, `triaged`, `deferred`, `promoted`, `rejected`, `handled`, `unconfirmed`. Ordinary follow-up statuses live in `docs/followups/*` and are not PI lifecycle truth.
- Если нужна обычная delivery follow-up, создай отдельную row в `docs/followups/*` с `status=open` / `plan=null` до promote и сохрани ссылку здесь в `delivery_refs`.
- Owner-facing `urgency` хранится как existing `priority`; не добавляй отдельное поле `urgency`.
- `open` rows могут стартовать с `priority=P?` и null target/delivery/execution fields, но lint JSON `carrier_readback` обязан показать их как staged untriaged debt.
- Mature `triaged|promoted|handled` rows должны иметь non-`P?` `priority`, literal `target_canon_path`, `target_repo_scope`, `delivery_mode` и status-consistent execution/delivery carrier либо explicit `triage_note`.
- Literal no-op `NO PROCESS IMPROVEMENTS — why: <reason_code>` не materialize-ится как backlog row.
- Wave 1 ограничен `collect + triage`; promote/reconcile automation остаётся deferred.

## Suggestions (truth)

### PI-001
- status: `open`
- priority: `P?`
- role: `Architect`
- owner: `Architect`
- promotion_class: `canon_update`
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
- trigger_ref: `docs/code_reviews/<REVIEW>.md#B1`
- source_ref: `docs/plans/<PLAN_PATH>.md`
- symptom: `<что болит>`
- process_gap: `<какой shared process gap surfaced>`
- suggested_fix: `<bounded fix>`
- created_at: `DD.MM.YYYY HH:MM ±HHMM`
- triage_note: `auto-collected from memory-finalize general lane`

## Notes
- Если row действительно promoted в live canon/helper/follow-up work, обновляй `status` и literal `target_canon_path` / `target_repo_scope` / `delivery_mode`, а не переписывай historical symptom/process gap.
- Если row deferred/rejected, reason/revisit или reject reason живёт в `triage_note`, а не в новых `defer_reason` / `reject_reason` fields.

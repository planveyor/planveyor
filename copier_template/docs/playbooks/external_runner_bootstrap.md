# External runner bootstrap: pre-SID selection authority

## Scope and authority

`planveyor_runner_resolve_strict <role> <init_attempt_id>` is the only selection
reader for a new role init. It reads the worktree-local
`.planveyor.runner.<role>` carrier and validates it against the canonical policy
host [runner_selection_resolution.v1.json](../_meta/runner_selection_resolution.v1.json)
through `$(_planveyor_root)`. The policy host is schema/policy only: it is
not a writable selection carrier.

Only a missing carrier yields `runner=codex` with
`carrier_state=absent_default`. Any existing blank, unreadable, non-regular,
malformed, unknown, or role-invalid carrier fails closed on stderr. It never
falls back to `codex`.

The successful resolver record is exactly one compact
`runner_selection_resolution.v1` JSON document with these keys:
`carrier_state`, `init_attempt_id`, `role`, `runner`, `schema_version`, and
`selection_digest`. The digest is the lower-case SHA-256 of NFC UTF-8,
compact sorted-key JSON for exactly `runner_selection_identity.v1`,
`carrier_state`, `role`, and `runner`; it excludes `init_attempt_id`.

`_planveyor_runner_selection_init_consume` receives the captured record once for
the same role and fresh non-SID `init_attempt_id`, validates its exact-key
shape, policy matrix and digest, and returns only
`runner<TAB>selection_digest`. The caller clears the captured JSON before
branch dispatch and does not reread `.planveyor.runner.<role>`.

## Time-domain and failure boundary

Each Architect, Manager, Coder, Planner, and Reviewer init resolves and
consumes selection before its first mutable boundary. That means failure
precedes role-bundle preparation, init capture, session/SID allocation,
`.planveyor.session.*`, `.planveyor.init_runs/*`, and provider child launch. Public
Reviewer wrappers delegate to the one inner init path; they do not read an
independent runner.

The selection record is invocation-local only. It is not exported, written as
a receipt/file, placed in session metadata, used as a source-bundle claim, or
treated as a provider/model observation or child-start permission. SID,
fingerprint, provider-readiness, and replay semantics remain outside this
pre-SID slice.

`planveyor_runner()` remains the legacy reader for resume, role-runtime, status,
and preflight consumers. It is not a substitute for strict init selection.
`planveyor_runner_set` publishes a complete override atomically: a temporary file
in the carrier directory is moved into place only after its complete contents
are written. A publish failure leaves the prior complete carrier intact.

## Synthetic proof and operator boundary

The canonical proof is the focused synthetic
`scripts.test_planveyor_init_capture` fixture matrix. It verifies all 13 allowed
role×runner pairs, absent defaults, all red carrier states, policy-host
validation, exact JSON/digest readback, consumer rejection cases, no
post-resolution carrier reread, and the pre-SID no-artifact boundary. A live
provider console, configured alias, role prose, prompt text, CENSOR verdict,
review result, Manager result, or screenshot is not selection authority.

No provider command, queue action, runner-set operation, packet recovery,
packet staging, commit, or push is part of this proof lane.

## Post-commit packet delivery

Этот раздел относится к отдельно объявленным packet consumers. Для Copier-managed
sibling изменение общего контракта оформляется source-local извещением
`docs/contract_notices/<change-id>.json`, затем принимается командой upgrade
в sibling с локальным планом адаптации. Source-only packetization readback не
содержит реестр sibling, адресатов или ACK и не подтверждает их обновление.

Только после появления exact source commit/range source owner запускает
packetization gate для этого range. Gate/readback определяет, требуется ли
packet coverage; он не создаёт packet и не изменяет target.

Если coverage требуется, создай один source-local rollout packet для каждого
literal target:

~~~bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --source-plan docs/plans/<plan>.md --target-kind consumer_only \
  --queue-after-import no
~~~

Заполни exact source range, revision, artifacts и target_writable_carriers
только фактами из target-local evidence. Неизвестный carrier scope остаётся
blocking. Consumer сам проверяет packet, принимает его и фиксирует adoption
outcome/ACK.

Recovery получает только exact source-local packet paths:

~~~bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md
~~~

Recovery не создаёт packet и не авторизует source/target mutation, queue
activation, commit или push. Датированные plan IDs и private consumer names не
являются частью этого public contract.

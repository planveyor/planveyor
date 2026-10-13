# Runtime and contract source binding

**English** · [Русский](contract_authority_integration.ru.md)

This document defines the public boundary between the Planveyor runtime, the
shared lifecycle, and target-local content. It does not describe personal
loaders, home directories, or implementation-specific transport.

## Runtime entry

The only documented entry is the public facade from the physical Planveyor root:

~~~bash
./bin/planveyor <planveyor_function> [args…]
~~~

The facade determines the runtime from its own physical path. Do not source the
shell implementation, and do not override the root with an environment
variable. For a consumer project, pass it explicitly before the function:

~~~bash
./bin/planveyor --project /absolute/path/to/consumer <planveyor_function> [args…]
~~~

One call does not change cwd, session state, or consumer configuration after it
ends. If the facade, the function, or the declared runtime is unavailable, that
is a blocker with a literal diagnostic, not a reason to guess a fallback path.

## Authority hierarchy

| Question | Authority |
| --- | --- |
| Available public function and runtime boundary | facade/readback |
| Plan status and routing | selected plan + Oracle/readback |
| Shared process contract | canonical role, prompt, playbook, or template |
| Target stack, test harness, UI, and credentials | selected consumer canon/plan |
| Delivery between repositories | source-local rollout packet + target adoption outcome |
| Execution/result proof | current receipt, review artifact, and declared gate |

Chat memory, local shell aliases, stale generated copies, and historical
snapshots do not replace any of these sources.

## Content selection

The shared content IDs `default` and `planveyor` use the common public corpus.
`target-local` belongs to the consumer and is materialized only under a real
consumer contract. An unknown content profile stops the selection: do not
silently pick `default`, a profile tree, or a historical sibling.

A shared default can be overridden only by a materialized target-local carrier
with an explicit owner. A missing override returns the shared default; do not
create empty profile directories "for later".

## Runtime and content evidence

A runtime readback confirms only what it reports for the current call. It does
not prove semantic acceptance, provider availability, or delivery of consumer
content.

For each execution/review claim, keep these apart:

1. command/readback identity;
2. the current artifact and scope;
3. the semantic verdict from the owning role;
4. target-local acceptance, if it is required;
5. the packet/adoption outcome for cross-repository delivery.

A receipt must contain only portable paths, placeholders, and declared
identities. Replace secret-shaped values with `<REDACTED>`. Local derived state
stays external/disposable and does not become checked-in authority.

## Changing a shared contract

When a shared role, prompt, playbook, template, guide, or ADR changes:

1. Identify the source owner and the exact changed bundle.
2. Run the scoped lint/readback that this bundle declares.
3. If delivery membership is required, create a source-local rollout packet.
4. The target owner checks the packet and materializes the target-local adoption
   on their own.
5. Keep the current receipt or review evidence, but do not copy files by hand.

A mirror/readback is a diagnostic and proof surface. It gives no right to change
the consumer, the queue, or the runtime configuration, or to make a commit or a
push.

## Session boundary

The runtime may return a session handle, an init record, or a role receipt.
They are invocation-specific: the current handle does not replace the plan
status, and a previous green receipt does not authorize a new child run.
Manager reads the exact current readback, stops on a mismatch or missing
evidence, and does not choose a fallback runner, model, or target.

## Verification

Before publication or closeout:

- check public docs for private paths, old local loader commands, and
  secret-shaped values;
- make sure the command runs through the facade;
- check declared target-local conditions separately from the shared lifecycle;
- run the relevant public verify/lint command;
- do not claim runtime readiness or adoption without current evidence.

See `docs/guides/launch-and-role-modes.md` for launching and
`docs/playbooks/portability_substitution_rules.md` for portable output.

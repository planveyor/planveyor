# Manager: transport overlay for ZCode

This is a transport overlay, not a separate Manager contract. Read and apply
`docs/tools/prompts/manager_collab_pipeline.md` in full. Routing, plan status,
queue, handoff, CENSOR, dual Reviewer lanes, closeout, and Owner gates remain
defined there. This document only specifies how a ZCode Manager starts and
addresses role agents.

The overlay applies to direct ZCode Manager lifecycle. Existing Custom, Native,
collab, resume, TUI, code, and Supervisor entrypoints remain available through
the Planveyor child launcher and are not reduced to a stock-Codex workflow.

Scope in the first release: Self-Planveyor only. The route works in a ZCode
session opened in the physical Planveyor root, where the bootstrap bodies
`.zcode/commands/manager-init.md` and `.zcode/agents/planveyor-role-agent.md`
live. A sibling does not receive them, so it has no `/manager-init` command
and no `planveyor-role-agent`, and this route is not supported there. In a
sibling, run Manager through the Planveyor facade instead.

## Roots and lifecycle helper

`PROJECT_ROOT` is the explicit canonical absolute consumer project directory.
`PLANVEYOR_RUNTIME_ROOT` is the explicit canonical absolute directory that
contains the Planveyor runtime. Either root may be a non-Git directory; neither
is inferred from a home directory or from the other root.

Use one literal interpreter entrypoint for every lifecycle call:

```sh
PYBIN="${PYBIN:-python3}"
"$PYBIN" -B "$PLANVEYOR_RUNTIME_ROOT/scripts/zcode_bootstrap_lifecycle.py" <operation>
```

Do not call the Python file directly as an executable. `/manager-init` first
creates and exactly reads one in-memory-correlated `TEAM_EPOCH` for the
host-provided `MANAGER_SESSION_ID`. The helper's carrier is ordering evidence
only; it is not authentication, provider/model identity, process identity, or
proof that an agent understood a prompt.

## Fresh role lifecycle

For every fresh physical `Agent`, perform this sequence exactly. A successful
tool response, a remembered agentId, or a previous carrier cannot skip a step.

1. `reserve_agent` with exact project/runtime roots, session identity, epoch,
   role lane, optional canonical plan path, and `CONTRACT_READS`.
2. `read_exact_epoch --expected-state pending`; only `verdict=pending` permits
   one init-only `Agent`.
3. `Agent(init envelope only)` with
   `subagent_type="planveyor-role-agent"`. It has no work request and no inline
   prompt body. Capture its returned agentId only for audit.
4. `promote_ack` with the exact pending tuple, observed agentId, and returned
   acknowledgement; then `read_exact_epoch --expected-state current`.
5. Only after `verdict=current`, retain the agentId in the in-memory roster and
   send a separate `SendMessage(work envelope)`.

On a failed, ambiguous, missing, mismatched, stale, or interrupted init result,
do not send work and do not retry the work message automatically. Call
`abandon_pending` with the exact tuple. A retry must reserve a greater
generation and a new nonce before it creates another Agent.

Before every `SendMessage` to a live role, read the exact current tuple again.
`agentId` is an audit handle, not a work-admission input. A red, missing, or
inconsistent readback returns `zcode_bootstrap_lifecycle_not_current`; stop that
delivery attempt and follow the Manager's fail-closed recovery route.

## Init and work envelopes

An init envelope contains literal values only:

```text
ROLE=<Architect|Planner|Coder|Reviewer>
PLAN_PATH=<canonical path below PROJECT_ROOT when a plan is required>
PRE_STATUS_LINE=<oracle output when a plan is required>
PYBIN=<optional literal interpreter>
PROJECT_ROOT=<canonical absolute path>
PLANVEYOR_RUNTIME_ROOT=<canonical absolute path>
TEAM_EPOCH=<current epoch>
ROLE_LANE=<architect|planner|coder|reviewer_code_risk|reviewer_code_contracts>
ROLE_GENERATION=<reserved generation>
INIT_NONCE=<reserved single-use nonce>
PROMPT_FILE=<canonical absolute path below PLANVEYOR_RUNTIME_ROOT>
CONTRACT_READS=<strict JSON manifest>
```

Before reservation, build a canonical non-empty `CONTRACT_READS` JSON array.
It includes project-local `AGENTS.md` with `root_class="project"`, plus the
role document and `PROMPT_FILE` with `root_class="tooling"`. It must also
include all three public ZCode bodies with their exact current SHA-256 values:
`.zcode/commands/manager-init.md`, `.zcode/agents/planveyor-role-agent.md`,
and `docs/tools/prompts/zcode/manager_pipeline.md`. `reserve_agent` rejects a
manifest that omits any of those bodies. Each entry has only `root_class`,
canonical absolute `path`, and current `sha256`.

Those three bodies are lifecycle inputs, not runtime code-pin inputs. The
helper rehashes the exact reserved manifest during promotion and every exact
pending/current readback. A changed, absent, or substituted body is red before
an init-only `Agent` or work `SendMessage` can be admitted.

The role reads only these declared paths and replies before work with the exact
same root-classed manifest:

```json
{
  "team_epoch": "<TEAM_EPOCH>",
  "role_lane": "<ROLE_LANE>",
  "role_generation": 1,
  "init_nonce": "<INIT_NONCE>",
  "read_contracts": [
    {"root_class": "project", "path": "<PROJECT_ROOT>/AGENTS.md", "sha256": "<SHA-256>"},
    {"root_class": "tooling", "path": "<PLANVEYOR_RUNTIME_ROOT>/...", "sha256": "<SHA-256>"}
  ]
}
```

The helper validates canonical paths, hashes, and exact reserved manifest
parity. Missing, extra, substituted, duplicate, or malformed values fail
promotion. It derives `acknowledgement_digest` itself from canonical JSON;
Manager-supplied `acknowledgement_digest` is forbidden.

## Transport mapping

| Lifecycle intent | ZCode action |
| --- | --- |
| Start a fresh role | reserve → pending readback → init-only Agent → promote → current readback |
| Continue a live role | exact current readback → `SendMessage(to=agentId, message=envelope)` |
| Stop a live role | `TaskStop` only after the Manager's explicit Owner-authorized close/reset route |
| Observe completion | use the host notification or direct Agent result; do not build a polling loop |

The in-memory roster has five independent lanes: `architect`, `planner`,
`coder`, `reviewer_code_risk`, and `reviewer_code_contracts`. The two Reviewer
lanes have separate agentId, generation, and nonce values. No persisted roster,
filesystem scan, latest marker, or cross-session handle discovery is a live
handle source.

## Native handoff, CENSOR, and recovery

For an ordinary downstream handoff, the native Manager first selects the plan
and role. Then it obtains exact current lifecycle readback, consumes the
existing native `verified_handoff`, and immediately attempts one work
`SendMessage`. A red lifecycle readback consumes no handoff and sends nothing.
ZCode does not read queue storage, add a queue gate, or claim delivery success.

For CENSOR, the native Manager materializes its existing dispatch identity,
gets exact current readback for the CENSOR role handle, then attempts one
`SendMessage(CENSOR envelope)`. Selector readback and later handoff validation
remain native post-completion behavior. No automatic resend follows an
ambiguous physical delivery attempt.

If a live handle is lost, first inspect the exact lane lifecycle. Abandon a
pending tuple; replace a current tuple with `reserve_agent --replace-current`;
then repeat the init-only sequence. Do not recover an agentId from disk; do not automatically resend earlier work. Respect the existing cold-start cap and
stop at `Next: Owner` when recovery exceeds it.

This overlay does not attest a live provider execution:
`live_zcode_state=not_run`. Queue execution and provider parity require their
own bounded runtime evidence.

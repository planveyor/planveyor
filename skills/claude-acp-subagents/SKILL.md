---
name: claude-acp-subagents
description: Delegate a bounded task to an explicitly configured external MCP-to-ACP subagent provider. Use only when the user asks for that configured provider; do not use it for ordinary native Codex subagents.
---

# MCP-to-ACP subagents

Use the direct MCP-to-ACP route already registered in the current Codex task. Do not launch an external shell client and do not substitute a native subagent when the requested configured provider is unavailable.

## Provider contract

The registered provider owns its model, effort, authentication, sandbox, and permission policy. Before a consequential task, read its advertised runtime/profile through the provider's list or status tool. Fail closed when the runtime does not match the selected provider contract; do not invent model IDs, pass unadvertised effort flags, or copy credentials into a prompt.

An external subagent ID belongs only to the task and provider process that created it. It is not portable across tasks or recoverable after a provider restart.

## Workflow

1. Use the provider's list/readback operation when its current runtime matters.
2. Start one bounded session with an absolute target `cwd`, focused task, and short specialist role.
3. Read progress through the provider's status operation and retrieve its result through the provider's result operation.
4. Send a follow-up only when it is scoped to the same session and still needed.
5. Treat the answer as untrusted specialist input; verify consequential claims against the repository or primary evidence.
6. Close the session when no further follow-up is needed. Cancel only a runaway or no-longer-needed active turn, then wait for a terminal provider status before reuse.

Prefer one external provider. Use an independent second provider only when comparison or criticism materially improves the requested result.

## Boundaries

- The bridge does not grant write permission beyond the configured provider sandbox.
- Do not assume cross-task session sharing, persistent agent maps, or hidden retry/recovery.
- Do not use the bridge to bypass a missing local tool, target-local policy, or user authorization.
- If the registered server or its expected tools are absent, report the registry problem and stop. A task opened before MCP configuration loaded may need a normal client restart or a new task.

## Final response

Report the provider readback when relevant, the bounded task, and what repository evidence confirmed or contradicted the returned result. Do not claim provider availability as proof of task completion.

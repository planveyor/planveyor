# MCP and target-local checks

**English** · [Русский](mcp.ru.md)

MCP and browser or native tools supplement the declared verification contract
of the selected project. They do not create a universal UI, framework, or
credentials policy.

## Choosing a tool

1. Read `PLAN_PATH` and the target-local canon.
2. Choose only a tool or harness that is declared there for the current scope.
3. If a UI or runtime lane is not declared, record `N/A (why=not declared)`; do
   not substitute a browser, native helper, database, or framework command.
4. Run Planveyor functions through the public facade:

~~~bash
./bin/planveyor planveyor_verify [--format json] [--full | --module …]
~~~

Without flags, this is the fast integrity route. `--full` adds one canonical unittest discovery and cannot be combined with `--module`; the facade passes `argv` through without a branch of its own.

The facade checks its own runtime. The target application command, credentials,
and test fixtures belong to the target project.

## UI evidence

For a declared UI lane, record:

- the exact scenario and preconditions;
- the chosen browser or native helper;
- the command and its result, or a readable receipt;
- the complete set of visual artifacts;
- the human verdict and the disposition of findings.

The automation result and the human inspection are independent. One screenshot
does not prove the full UI contract, and a successful command does not close the
visual lane without a declared verdict.

## Environment limits

If the selected harness needs a browser, network, device, local service, or
elevated execution, first get a truthful result from an actual run. An
unavailable environment is a blocker or a diagnostic under the target contract;
do not replace it with another stack and do not invent credentials.

Do not store credentials, cookies, authorization headers, session identifiers,
tokens, or personal paths in a plan, receipt, review artifact, or screenshot
metadata. Use `<REDACTED>`.

## MCP boundaries

MCP tool output is supporting evidence until the plan or review states its role
in the decision. Do not take tool availability, chat prose, or a historical log
as proof of current behavior. Keep only the necessary public facts: the selected
tool, the declared target scope, the result, and a stable artifact reference.

## Closeout

After a UI or MCP lane:

1. Add the result to the role-owned review or to the plan evidence.
2. Re-check the declared gate for the exact changed bundle.
3. If shared process docs changed, handle packetization separately.
4. Stop on missing evidence; do not perform a target mutation, a queue write, a
   commit, or a push only to finish the proof lane.

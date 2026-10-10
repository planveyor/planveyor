# Contributing to Planveyor

Keep changes bounded, reviewable, and safe to publish. A Planveyor artifact should explain its purpose through the current plan, review, issue, or packet that requires it.

## Before editing

Start from the public command facade:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_help
```

Read the relevant role, prompt, playbook, and template before changing a lifecycle contract. For a consumer repository, run its own tests and follow its contribution instructions from that repository.

## Local prerequisites and verification

The first release is supported on macOS in one activated Python 3.12 environment with the pins from `requirements-dev.lock`, including Copier 9.18.2 and PyYAML. Create that environment yourself, run `make bootstrap-python` inside it once, keep it activated, and expose Git, zsh, and ripgrep on `PATH`. Planveyor does not install or repair dependencies; a missing prerequisite ends the command with an error that names it. Python 3.10–3.12 is only the loader's technical boundary, not a second supported path. The configured macOS CI matrix is not evidence of a completed hosted run; hosted CI, other Python versions, and Windows and Linux native validation are post-release follow-up work.

Use the smallest route that proves the changed contract: `make verify` is fast/default, `make test-scripts` is direct canonical full discovery, and `make verify-full` is the alternative aggregate full route. Use one of the full routes for a single full claim, never both.

## Change discipline

- Keep identifiers and commands in English; write user-facing documentation in the language appropriate to its audience.
- Preserve the distinction between current evidence and historical context.
- Use the applicable template for a new plan, review, follow-up, process-improvement, rollout packet, or upstream request.
- Name exact paths and revision ranges in handoffs and reviews.
- Keep `target-local` configuration, credentials, application details, and consumer-repository policy outside this root corpus.
- Do not include secrets, tokens, cookies, private hostnames, private paths, account data, or copied third-party prompt bodies. Use `<REDACTED>` or a neutral placeholder when needed.
- Treat generated indexes as derived views and rebuild them through their documented renderer rather than editing old rows by hand.

## Validation

Run the smallest relevant checks first, then the documentation and lifecycle checks required by the changed contract. Use `planveyor_help` and the affected playbook to identify the installed command. Include the command and its outcome in the review artifact when it is material to acceptance.

For a new or changed public artifact, also scan it for source-repository references, private local paths, and stale historical evidence before requesting review.

## Review expectations

A review should be able to identify:

- the bounded target scope;
- the plan or other authority carrier;
- validation performed on the current bytes;
- remaining limitations or follow-up ownership; and
- the next admissible lifecycle action.

If the work uncovers broader design or packaging needs, record a bounded follow-up instead of expanding the change silently.

## Proposing a change from a sibling

A sibling does not edit Planveyor files. Write the proposal in the sibling as a request from `docs/upstream_packets/_template.md`, check and commit it there, then send it as a GitHub issue with `gh`, which you install and sign in to yourself; the request file becomes the issue body (`gh issue create --body-file`). The procedure is in the “Предложить изменение Planveyor” section of the [stack sibling guide](docs/guides/stack-sibling.md#предложить-изменение-planveyor) (in Russian). An accepted change returns to the sibling as a Planveyor contract upgrade with a notice in `docs/contract_notices/`.

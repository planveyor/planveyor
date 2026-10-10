# Prompts

This directory holds the checked-in shared prompts for Planveyor roles and Manager modes. The root corpus is the source of truth for the public process; an installed prompt copy is only a delivery artifact.

## Layout

- `architect_*.md`, `planner_*.md`, `coder_*.md`, `reviewer_*.md`, `manager_*.md` — shared role and pipeline prompts.
- `*_init.md` — role bootstrap prompts.
- `*_status_driven.md` — prompts that route work from an explicit plan and its current status.
- `*_censor.md` — second-opinion prompts when a lifecycle explicitly requires CENSOR review.
- `*_docs_finalize_*.md` — documentation and evidence closeout prompts.

## Public and target-local sources

The public `default` and `planveyor` source identities resolve the root prompt corpus. They do not imply an application stack, datastore, UI harness, project path, or hidden runtime default.

A `target-local` identity belongs to the consumer repository. Its prompts, credentials, integration assumptions, and application anchors must be supplied and validated there. If that contract is absent, dispatch must stop with a clear blocker rather than selecting an implicit profile or copying a private source.

## Prompt rules

- Name the literal plan, target scope, expected artifact, and next gate.
- Keep role authority and status-machine semantics independent of product details.
- Treat target tests, UI acceptance, repository-specific commands, and deployment policy as explicit target-local input.
- Transfer prompt changes to another repository through a reviewed rollout/adoption process; do not edit a consumer copy from the source session.
- Use the public Planveyor facade from the product root when a prompt needs to name a command:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_help
```

See `docs/roles/` for role responsibilities and `docs/playbooks/` for the detailed lifecycle contracts.

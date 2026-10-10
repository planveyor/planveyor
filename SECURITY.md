# Security policy

## Reporting a vulnerability

Report suspected security vulnerabilities for the current Planveyor product to security@planveyor.dev. Maintainers handle reports on a best-effort basis.

Do not publish exploit details, credentials, or a working attack path in a public issue. Report the issue through the repository's published maintainer contact channel and include only the information needed to reproduce it safely.

A useful report names the affected Planveyor version or files, expected impact, safe reproduction steps, and the smallest practical mitigation.

## Secret and privacy handling

Do not commit secrets, API keys, access tokens, cookies, private hostnames, private local paths, account identifiers, or copied private configuration. Use neutral placeholders such as:

```text
API_TOKEN=<REDACTED>
```

Keep generated state, caches, temporary files, session artifacts, and external authentication outside the Planveyor product tree. Consumer repositories retain ownership of their own credentials, integration configuration, and target-local operational data.

Planveyor-generated dispatch identifiers, CENSOR identifiers, and a manifest run_id may appear as public operational evidence identifiers when they bind a public artifact to its run. This allowance never includes provider user, session, SID, or thread identifiers, or credentials. Provider identifiers and credentials remain private and must be redacted before publication; frozen evidence and history are not rewritten here.

## Public artifact review

Before publishing a new document, prompt, packet, or review artifact, inspect it for private local references, source-only history, secret-shaped values, and links to consumer-private systems. Automated scans help catch accidental leakage; they do not replace a focused human review of the final artifact.

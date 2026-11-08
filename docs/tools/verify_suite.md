# Owner runbook: verify suite

**English** · [Русский](verify_suite.ru.md)

`planveyor_verify` is a read-only aggregate check for the installed Planveyor corpus and its registered integrity modules. The default route is fast integrity verification; `--full` adds one canonical unittest discovery. Its implementation and exact module set are owned by the runtime; this guide explains the operator contract.

## Run it

From the physical Planveyor root, use the public facade:

```zsh
./bin/planveyor planveyor_verify
./bin/planveyor planveyor_verify --format json
./bin/planveyor planveyor_verify --module <module-name>
./bin/planveyor planveyor_verify --full
make verify
make verify-full
make test-scripts
```

The default route keeps the registered non-unittest integrity checks and does not run unittest discovery or the old per-module portability overlap. `--full` adds exactly one canonical discovery and cannot be combined with `--module`. `make verify` uses the default route, `make verify-full` forwards `--full`, and `make test-scripts` remains the standalone canonical discovery command. Choose either `make verify-full` or `make test-scripts` for one full claim; do not combine them.

## Platform and CI boundary

First-release work is supported on macOS with a prepared Python 3.12 environment and dependencies from `requirements-dev.lock`, Git, zsh, and ripgrep available. The source-identity loader technically accepts Python 3.10–3.12; this does not expand first-release support. The macOS CI profiles and mandatory summary are described below; configuration alone is not a hosted-run result. Windows and Linux native validation have not been completed.

The JSON report from `planveyor_verify --format json` names the modules run by
the installed version; pass a reported name to `--module` to select it. For consumer-project work, select the project explicitly through the facade before the command when that module is designed to inspect the consumer tree.

## CI compatibility subset

The exact IDs in `scripts/test_shards.json` define `compat310`: loader stream and failure handling, interpreter selection, source-identity parsing, and the real public facade/Copier init/doctor/upgrade path. This is a bounded compatibility check, not a full Python 3.10 suite or an expansion of the supported first-release environment. The mypy target remains Python 3.10.

From the physical checkout with the selected prepared interpreter:

```zsh
"$PYBIN" -B scripts/run_test_shard.py --matrix
"$PYBIN" -B scripts/run_test_shard.py --check
"$PYBIN" -B scripts/run_test_shard.py --subset compat310 --report <fresh-report-path>
```

`--matrix` reads structure without importing tests. `--check` imports canonical discovery and validates the full exact-once partition plus all configured subset IDs, without running test bodies. Subset execution repeats those checks before filtering the original cases in canonical order, preserving module/class hooks. Unknown, empty, duplicate or missing IDs and an invalid full partition fail closed. The report parent must exist, and report/event paths must be fresh. `--subset` cannot be combined with full-shard or local-profile selection.

The report and its `.events.jsonl` companion bind ordered IDs, manifest hash, Python identity, HEAD and completion accounting. Subsets report `selected_subset=compat310` and `selected_shards=[]`; full/local runs retain their shard IDs and `selected_subset=null`. Incomplete accounting, interruption or HEAD drift at the existing execution boundary cannot produce green. A local compatibility result does not establish hosted CI success, full-suite coverage on Python 3.10 or a push-time guarantee; the full verification routes above remain separate.

## Fast/full CI and required summary

The checked-in workflow routes push to `main` and `pull_request` to **fast**: Python 3.12 parts `core` (`--subset fast`), `contracts-a`, and `contracts-b`, plus the separate Python 3.10 `compat310` part. Daily `schedule` (`17 2 * * *` UTC) and `workflow_dispatch` use **full**: all 14 Python 3.12 shards and `compat310`. There is no docs-only bypass or release action. Bare `--matrix`, local profiles, and public full verification retain their defaults.

Before selection, CI imports canonical discovery, validates its full exact-once partition, and checks composition independently of mutable subset IDs. Core keeps the fixed 16 whole-method safety witnesses; `contracts-a` contains every discovered case in `test_planveyor_plan_bundle`; `contracts-b` contains every case in the explicit 29-module policy in `scripts/run_test_shard.py`. Core/A/B are disjoint. The fixed nine compatibility IDs are checked separately. Counts grow with canonical methods; snapshots are not ceilings.

`shard-matrix` installs the existing declared prerequisites before importing tests and runs an explicit composition check outside subset selection. Four metadata commands run once: strict docs/i18n, changed-plan lint, Python 3.10-policy typecheck, and public scan. Their row is `contracts-b` for fast or `s01` for full. PR changed-plan base is the required merge-base with the target branch; an unavailable PR base fails. Push uses a valid event-before commit or the root fallback; schedule/manual use `HEAD^1` or the root fallback. The chosen event/base/head is logged.

Strict workers require `--ci-strict`, `--ci-profile`, `--ci-part`, `--ci-python`, `--ci-event`, `--ci-run-id`, `--ci-run-attempt`, and `--ci-expected-sha`. A profile plus execution selector without strict context fails before bodies. PR additionally requires `--ci-pr-head-sha`; other events reject that flag. Trusted expected checkout is `github.sha`, including the synthetic merge commit for PR; its head SHA is separate context. Equal observed HEADs alone are insufficient.

From a prepared checkout, profile inspection does not execute test bodies:

```zsh
"$PYBIN" -B scripts/run_test_shard.py --matrix --ci-profile fast
"$PYBIN" -B scripts/run_test_shard.py --check --ci-profile full
```

Each strict report adds validated `ci_profile,ci_part,ci_event,ci_run_id,ci_run_attempt,ci_expected_sha,ci_pr_head_sha,ci_expected_python,ci_python` to the existing report. The actual Python pair, manifest, trusted expected SHA, selector, and nonempty ordered planned/started/completed IDs must match independently expected execution. Strict green requires complete accounting with no failures, errors, skips, interruption, or source drift; legacy local skip semantics remain unchanged. Python 3.12 retains native duration records; Python 3.10 retains wall-only/null durations. Timing is diagnostic.

Standard immutable-pinned artifact actions transport only `result.json` under `planveyor-ci-<run>-<attempt>-<part>`, with upload `if: always()` and missing reports treated as errors. Required check **`ci-summary`** runs `if: always()`, needs both `shard-matrix` and `verify`, and independently invokes `--ci-summary DIRECTORY --ci-profile fast|full` with trusted event/run/attempt/SHA context and `--ci-needs-json JSON`. It reads exactly the current-attempt corpus; it does not rerun workers or take expected IDs from reports or preparation output. Full shard union must equal the entire canonical suite exactly once; fast union equals core/A/B only. Compatibility is a separate axis.

Missing, extra, malformed, duplicate-key, stale, foreign, duplicate, incomplete, red, cancelled, or skipped parts/needs fail closed. A successful matrix aggregate cannot hide a missing report, s02 executing s01, two equal wrong HEADs, or a red authoritative report. Events remain diagnostics; no per-event reaggregation or GitHub API client is required.

Fast concurrency is ref-bound/latest-wins. Full groups include run ID and attempt so later full runs do not replace earlier pending full runs; this reserves no runner capacity. The mandatory summary must be retained as a required check by deployment policy; this change does not edit repository rulesets. A full green run on the actual release SHA is required before a future release. Local synthetic checks and source configuration do not establish hosted success, queue/cancellation qualification, publication, or an hour guarantee.

## What the result means

- `GREEN` / exit `0` means every required registered check passed. A `WARN` may still require the operator to read its detail and resolve a local prerequisite before treating the work as ready.
- `RED` / non-zero means at least one required check failed. Read the named module, metric, and detail before changing any artifact.
- A successful verify-suite run supports only the checks it reports. It does not prove role execution, target test success, review acceptance, packet adoption, or semantic closure.

## When to use it

Run the relevant module after changing its contract, before a public release, or when a portability/integrity concern needs a bounded readback. Prefer the smallest applicable module while investigating a blocker; use `--full` when one aggregate route must add canonical discovery across multiple registered boundaries.

## If it warns or fails

1. Read the exact module result and its detail.
2. Identify whether the finding concerns current checked-in content, an external selected project, or disposable local state.
3. Repair only the named cause through its owning lifecycle.
4. Run the same module again and record fresh evidence when the result matters to a handoff.

Do not weaken a gate, rewrite an unrelated artifact, or use a historical green result to silence a current failure.

## Related guidance

- `docs/guides/launch-and-role-modes.md` — public facade and project selection.
- `docs/guides/lifecycle-and-packets.md` — plan, review, closeout, and packet gates.
- `docs/playbooks/portability_substitution_rules.md` — portable public-artifact vocabulary.

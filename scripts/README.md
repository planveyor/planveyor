# `scripts/`

Top-level inventory для script surfaces в `planveyor`.
Durable rule: файл не считается dead только потому, что его не загружает `scripts/planveyor.zsh`.

## Entry point classes

- `wrapper entrypoint`: user-facing shell command или shim, exposed через `scripts/planveyor.zsh` или checked-in shell wrapper.
- `python CLI`: executable Python script с command-line contract, включая operator-only utilities.
- `import-only helper`: Python module, который потребляет другой script/test и обычно не запускается напрямую.
- `test carrier`: `scripts/test_*.py` regression coverage для script/helper family.
  Individual test carriers are expected to support focused direct execution from
  repo root via `"$PYBIN" -B scripts/test_<name>.py` when a plan names that lane.
- `historical/deprecated`: retained for old plans, reviews, rollout packets, compatibility notes, or bounded parity comparison.
- `candidate for removal`: no live consumer remains after bounded repo/docs/test search; removal still requires separate follow-up or child plan.

## Inventory policy

- Search must include `scripts`, `docs`, `Makefile`, and `.github`, not only `scripts/planveyor.zsh`.
- Historical references are recorded separately from live consumers before any deletion decision.
- Operator-only CLIs can be valid without wrapper exposure when the command contract is documented.
- Script deletion, wrapper exposure, generated inventory helpers, and behavior changes are out of scope for an inventory-only slice unless a child plan says otherwise.
- If a script is ever classified as `candidate for removal`, create/update a follow-up/backlog row with `plan=null` until the removal plan is promoted.

## Evidence types

- `wrapper`: direct shell wrapper or `planveyor.zsh` call.
- `test`: direct `scripts/test_*.py` import or execution coverage.
- `docs`: active runbook/playbook/process docs that tell an operator to use the script.
- `helper`: direct import/use by another checked-in script.
- `historical`: old plans/reviews/rollout packets that explain provenance but are not a live consumer by themselves.

## Current classification slice

The table records the current public entrypoints and their declared consumers.

| Script | Classification | Live evidence | Historical/context evidence | Action |
| --- | --- | --- | --- | --- |
| `followups_code_reviews_harvest.py` | `python CLI` / operator-only docs-hygiene importer | Standalone CLI imports line-by-line code-review findings into follow-up inbox files. | Historical repo-split and review cleanup docs mention it as follow-up harvest tooling. | Keep; no wrapper exposure in this slice. |
| `code_reviews_line_by_line_followups_check.py` | `python CLI` / operator-only cleanup checker | Standalone CLI verifies line-by-line review findings are imported into follow-up masters. | Architect lint-gap reviews name it as cleanup-readiness proof before deleting review sources. | Keep; no wrapper exposure in this slice. |
| `docs_corpus_stats.py` | `python CLI` / docs-retrieval sizing helper | `docs/tools/snippet.md` and retrieval-index plans document it as corpus sizing command. | An earlier script inventory flagged it as not wrapper-loaded. | Keep as docs-retrieval support CLI. |
| `planveyor_delivery_metrics.py` | `python CLI` / tested metrics helper | `scripts/test_planveyor_delivery_metrics.py`; `docs/tools/owner_runbook_codex.md` documents operator commands. | An earlier script inventory flagged it as not wrapper-loaded. | Keep as trace-derived metrics CLI. |
| `planveyor_failure_attribution.py` | `python CLI` / tested attribution helper | `scripts/test_planveyor_failure_attribution.py`; `docs/tools/owner_runbook_codex.md` documents operator commands. | Trace-attribution plans and reviews describe the compact failure output contract. | Keep as trace-derived attribution CLI. |
| `planveyor_trace_extractor.py` | `python CLI` / tested trace extractor | `scripts/test_planveyor_trace_extractor.py`; `docs/tools/owner_runbook_codex.md` documents operator commands. | Trace-extractor plans describe `.tmp/planveyor_trace_events.jsonl` and optional SQLite outputs. | Keep as repo-native trace extractor. |
| `process_improvements_collect.py` | `python CLI` / helper family root | Imported by `process_improvements_triage.py`; covered with `scripts/test_process_improvements.py`; process-improvement docs and generated surfaces reference it. | Prior process-improvement plans define it as the truth/derived-surface collector. | Keep as process-improvement collector. |
| `process_improvements_triage.py` | `python CLI` / helper-family updater | Imports `process_improvements_collect.py`; covered with `scripts/test_process_improvements.py`; owner runbook documents triage commands. | Prior process-improvement plans define it as deterministic row updater. | Keep as process-improvement triage CLI. |
| `queue_finalizer_report.py` | `python CLI` / tested queue readback helper | Public wrapper `planveyor_q_final_report` calls it; `scripts/test_queue_finalizer_report.py` covers complete, stopped, missing, ambiguous and red truth-host cases. | Queue-completion feedback plans define it as derived Owner report after `queue_complete=true`. | Keep as queue-level finalizer/readback helper; no queue mutation, staging or push authority. |
| `review_artifact_lint.py` | `python CLI` / tested review-artifact linter | `scripts/test_review_artifact_lint.py`; review/template plans and Coder/Reviewer evidence use it as the review grammar gate. | An earlier script inventory flagged it as not wrapper-loaded. | Keep as review-artifact lint gate. |
| `post_merge_audit_lint.py` | `python CLI` / tested post-merge audit linter | `scripts/test_post_merge_audit_lint.py`; post-merge audit playbooks and review plans use it as grammar gate. | An earlier script inventory flagged it as not wrapper-loaded. | Keep as post-merge audit lint gate. |
| `plan_harvest_lint.py` | `python CLI` / tested plan-harvest linter | `scripts/test_plan_harvest_lint.py`; plan-harvest review plans use it as grammar/backlog-linkage gate. | An earlier script inventory flagged it as not wrapper-loaded. | Keep as plan-harvest lint gate. |

No script in this slice is classified as `candidate for removal`; therefore no `plan=null` removal follow-up is materialized here.

## Module layer

`scripts/planveyor/README.md` owns the internal module navigation for `scripts/planveyor.zsh`.
Keep that file synchronized with the live `scripts/planveyor/*.zsh` module list and `_planveyor_source_module` load order when the module layer changes.

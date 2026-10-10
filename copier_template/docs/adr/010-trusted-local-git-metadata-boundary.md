---
status: "accepted"
date: 2026-08-04
decision-makers: Owner, Architect
source-range: "N/A (why=Owner-approved canon decision; this bundle changes policy carriers, not Git runtime)"
source-plan: "N/A (private history)"
code-anchor: "docs/tools/prompts/reviewer_status_driven.md; $PLANVEYOR_RUNTIME_ROOT/docs/process_improvements/README.md; scripts/test_manager_custom_pipeline_prompt_contract.py"
---

# Граница доверия к локальным Git metadata

## Context and Problem Statement

Одно из ревью последовательно находило всё новые cross-product'ы вокруг локальной Git metadata. Один из них требует, чтобы local actor с write-доступом к checkout намеренно подменил `.git` symlink'ом, foreign/unregistered Git-dir или metadata во время выполнения. `planveyor` не является sandbox/security boundary против владельца локальной машины, поэтому обработка такого actor как обычного runtime blocker расширила бы bounded process plan в отдельную Git-security систему.

Нужна одна durable policy authority, которая сохраняет correctness-gates для обычных рабочих копий, но не даёт Reviewer неявно превращать каждый local-tampering repro в S1 для ordinary plan.

## Decision Drivers

- Сохранять fail-close для реальных operational failures в supported checkout.
- Не расширять ordinary documentation/process plan в runtime Git hardening без explicit Owner-approved security scope.
- Давать Reviewer и target-repo adoption один проверяемый policy anchor вместо нескольких пересказов.

## Considered Options

- Считать любой repro с подменённой `.git` metadata обычным blocking defect текущего plan.
- Доверять локальной Git metadata только в Owner-controlled supported environment и выносить security hardening в отдельный scope.
- Считать любые Git/root failures unsupported environment и не блокировать их.

## Decision Outcome

Выбранный вариант: **ordinary repo-local tooling доверяет local Git metadata только в supported Owner-controlled environment**, потому что это сохраняет bounded correctness contract и не обещает защиту от local actor, который уже контролирует metadata checkout.

| Контекст | Disposition |
| --- | --- |
| Нормальный repository с обычной `.git` directory | supported |
| Git-created linked worktree с regular `.git` gitfile | supported |
| `.git` symlink | unsupported environment |
| Manually substituted foreign/unregistered Git-dir | unsupported environment |
| Concurrent local metadata mutation | unsupported environment |
| Missing/invalid repository, canonical root mismatch или ambient `GIT_DIR`/`GIT_WORK_TREE`/`GIT_COMMON_DIR`/`GIT_INDEX_FILE` override | operational-red |

Reviewer сначала фиксирует, находится ли reproduction внутри active plan threat model. Для ordinary plan finding, требующий только unsupported local metadata tampering, сам по себе non-blocking и может стать security work только через отдельный Owner-approved scope. Explicit Owner-approved untrusted, multi-tenant или security-hardening scope отменяет этот default: применимый finding остаётся blocking.

## Consequences

- Плюс: normal repository и Git-created linked worktree сохраняют обычные correctness/fail-close guarantees.
- Плюс: ADR задаёт единственный durable policy host; Reviewer prompt и PI canon держат только bounded operational pointers.
- Риск: accepted limitation не делает local metadata tampering невозможным и не заменяет отдельный security threat model.
- Риск: source-local rollout packet не доказывает adoption в target repo; target repo обязан принять или отклонить packet локальным plan/outcome.

## Canonical refs

- `docs/tools/prompts/reviewer_status_driven.md`
- `"$PLANVEYOR_RUNTIME_ROOT/docs/process_improvements/README.md"` (PI canon движка)
- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/adr/005-rollout-packet-is-handoff-not-execution.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "active plan threat model|unsupported local Git metadata tampering|operational-red|explicit Owner-approved" docs/tools/prompts/reviewer_status_driven.md`
- `$PYBIN -B -m unittest scripts.test_manager_custom_pipeline_prompt_contract`
- `bash scripts/run_doc_lint.sh --root docs/adr/010-trusted-local-git-metadata-boundary.md --root docs/adr/README.md --root docs/process_improvements/README.md --root docs/tools/prompts/reviewer_status_driven.md`

## Revisit signals

- Owner explicitly accepts untrusted, multi-tenant или security-hardening scope для repo-local Git metadata.
- Доказанный repro возникает в supported normal repository или Git-created linked worktree без local metadata tampering.
- Target-local adoption records a different truthful threat boundary that needs a source-policy review.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

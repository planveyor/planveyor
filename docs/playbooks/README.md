# Docs: Playbooks

Здесь лежат повторяемые сценарии работы. Root corpus — общее ядро Planveyor.

Content IDs `default` и `planveyor` читают root shared corpus. `target-local`
принадлежит consumer: он materialize-ится только по declared consumer contract
и при отсутствии остаётся fail-closed. Не создавай profile tree
map «на вырост».

Manager в collab/merge mode остаётся wait-only: не interrupt/close/reset
running role threads без declared stop contract.

## Как устроены документы

- Роли: `docs/roles/*.md` — границы authority, routing и escalation.
- Playbooks: `docs/playbooks/*.md` — шаги, checklists и commands для сценария.
- Templates: рядом с family результата (`docs/plans/`, `docs/code_drafts/`,
  `docs/code_reviews/`, `docs/reviews/`).

Literal repo path `docs/...` нужен там, где reader должен открыть конкретный
carrier. Narrative pointer не становится второй source of truth.

## Index

- Cross-role: `docs/playbooks/docs_architecture.md`,
  `docs/playbooks/decomposition_wave.md`,
  `docs/playbooks/manual_terminal_recovery.md`,
  `docs/playbooks/doc_lint.md`, `docs/playbooks/doc_gardening.md`,
  `docs/playbooks/external_runner_bootstrap.md`,
  `docs/playbooks/portability_substitution_rules.md`,
  `docs/playbooks/role_prompt_invariant_map.md`,
  `docs/playbooks/snapshot.md`, `docs/playbooks/worktrees_topic_split.md`.
- Review: `docs/playbooks/review_staged_or_commit.md`,
  `docs/playbooks/review_docs_staged_or_commit.md`,
  `docs/playbooks/review_merge_range.md`,
  `docs/playbooks/post_merge_visual_review.md`,
  `docs/playbooks/review_scoping_plan.md`,
  `docs/playbooks/review_route_and_receipt_canon.md`.
- UI/reference: `docs/playbooks/reference_driven_ui.md`.
- Post-merge: `docs/playbooks/post_merge_notes.md`,
  `docs/playbooks/post_merge_audit.md`,
  `docs/playbooks/post_merge_plan_harvest.md`,
  `docs/playbooks/post_merge_docs_hygiene.md`,
  `docs/playbooks/docs_canon_sweep.md`.
- Lifecycle: `docs/playbooks/followups_topic_consolidation.md`,
  `docs/playbooks/analysis_wave.md`.

# Post-merge check

**English** · [Русский](postmerge.ru.md)

This chapter is for those who maintain Planveyor itself. If you run tasks in a sibling, all you need from this topic for now is the `## Post-merge gate` section of your plan; the [Task closeout](closeout.md) chapter covers it.

The post-merge check takes a commit range `BASE..HEAD` that has already reached the main branch and looks at it as a whole. The review of each task saw only the exact bundle of its plan, while after the merge the branches have come together, the conflicts are resolved, and the tasks work together. Along the way, the check takes the decisions, rules, and deferred work out of the temporary plans and reviews before these files are deleted.

## Where it runs

Out of the box, the post-merge check currently works only in Planveyor itself. A sibling has no `planveyor sibling …` command for it. The facade accepts the low-level commands there too, but they need two settings files in the `docs/_meta/` directory of the project: `planveyor_merge_gate_policy.v1.json` and `review_range_policy.v1.json`. The sibling template does not create them, and the stack sibling guide does not explain how to write them. When these files exist, the engine creates both the tracker and the range review plan; its tests check this. Nobody has run this check in full in a sibling yet.

## Steps

Manager runs the check in a separate merge mode. The merge tracker, the local file `.planveyor.merge_tracker.md`, keeps the order of the steps; it is not committed. Each time, Manager learns the next step from the `merge_tracker_oracle.py` script. It works with one role at a time, and on any script error it stops and returns the turn to Owner.

![Post-merge check steps: from choosing the range to the audit, the archive, and the local commit](assets/postmerge-1.svg)

| Tracker step | Who does it | What it produces |
| --- | --- | --- |
| `review_range` | Reviewer in two lanes, then Architect | The range review and the decision of Architect on it |
| `merge_notes` | Architect | Notes on what went into the range |
| `plan_harvest` | Architect | The harvest report: the decisions and deferred work from the plans and the range review |
| `canon_sweep` | Architect | The shared Planveyor documents are cut down to the essentials, with links; a receipt about it |
| `packetization_gate` | Script | A report on rollout packets (more on them below) |
| `docs_finalize` | Architect | A receipt with a process improvements section |
| `doc_lint` | Script | A check of the links and the format of the documents |
| `post_merge_audit` | Architect | The audit: the requirements are compared with the code, the checks, the documents, and the range review |
| `docs_hygiene_archive` | Script | The closed plans of the range, their drafts, and their reviews are saved to a searchable archive |
| `docs_hygiene_suggest` | Script | A list of files that can be deleted, and a ready command for Owner |
| `ready_to_push` | Script | The final receipts and a local commit of the check files |

A receipt here is a file in `docs/reviews/` with a record of a completed step. Manager runs the scripts. The project policy file can add its own steps, for example a migrations check. The `planveyor_merge_bundle_report` report confirms that the whole range is ready: Manager runs it at the `ready_to_push` step, when the other steps are done. After that, the step script locally commits the check files that the report accepted, together with the final receipts. Owner runs `git push`.

## Who does what

| Participant | What they do |
| --- | --- |
| Owner | Chooses the range or the branch to merge. Answers when Manager has stopped. Runs `git push` after the local commit. Decides whether to delete the temporary files, and deletes them in a separate commit |
| Manager | Goes through the tracker steps in order and calls the roles and the scripts. Does not write the review and audit reports |
| Reviewer | Checks the range with the same two lanes as a single task |
| Architect | Examines the range review; writes the notes, the harvest report, the documents receipt, and the audit; cleans up the shared documents |
| Coder | Resolves the conflicts during the merge and fixes the migrations check that the project declared |
| Planner | Does not take part in this mode |

The `docs_hygiene_suggest` step script gives the candidates for deletion, and Architect assembles the exact list in the audit and checks that no links to these files will remain.

## Merge and launch

You can merge the branch by hand or leave it to Manager:

```sh
./bin/planveyor planveyor_merge_apply_collab_cmd --from <branch>
```

Manager merges the branch without `git push`. Coder resolves the conflicts, and a conflict in dangerous paths, for example in migrations or environment settings, goes straight back to Owner. After the merge, Manager moves on to the check by itself. If the branch is already merged, you start the check separately:

```sh
./bin/planveyor planveyor_merge_collab_cmd --range <BASE>..<HEAD>
```

Instead of a range, you can pass a merge commit (`--range <MERGE_SHA>`) or `--range auto`: then the last merge commit is taken. The interactive variant is `./bin/planveyor planveyor_merge_collab_tui`. If Manager has stopped, read the named step and the reason, fix it, and run the command again without `--range`: Manager continues with the same tracker.

Owner deletes the temporary plans and reviews in a separate commit when they decide to. Before that, Owner runs the archive and the candidate list again for the same range, because the documents may have been edited after the check:

```sh
./bin/planveyor planveyor_docs_hygiene_archive --range <BASE>..<HEAD> --apply
./bin/planveyor planveyor_docs_hygiene_suggest --range <BASE>..<HEAD>
```

## Range review

At the `review_range` step, the `planveyor_review_range_init` script creates a `review-only` plan with a code draft and records in the plan the path to the review file: in `docs/doc_reviews/` when all selected range paths are under `docs/`, otherwise in `docs/code_reviews/` (so a root `README.md` uses the latter). Reviewer writes the report from the `_template_merge_range.md` template, with the same two lanes. When the report is ready, the plan moves to `Ready for Arch review`. For a review plan, this means “the report is ready to be examined”, and S1 findings in it are allowed.

Architect examines the report:

- there are no blocking findings, and the S2 risks are accepted deliberately: the review plan is closed with `Done`, and the check goes on; non-blocking work can be moved to a new plan or to the backlog;
- a fix is needed before the check can go on: Architect creates a new plan with the `Architect initial draft` status, marks the review plan `Superseded`, and the check stops. When the fix is merged, Owner runs `planveyor_merge_collab_cmd` again on the updated range.

Architect does not make a commit for the review plan: these files go into the commit of the `ready_to_push` step. A repeated review rewrites the same file; a second review file for the same range is created only explicitly, through `planveyor_review_range_init --force-new`. The audit then reads the final section of this review (`Lane synthesis / aggregate verdict`); no separate review is run for the audit.

## Rollout packets

The `packetization_gate` step is needed when the range changes shared Planveyor documents that are delivered to other projects. A packet is needed only for paths that have a declared recipient; a sibling does not receive packets now. The script checks that rollout packets are prepared for such changes ([Exchanging changes with Planveyor](change-packets.md)), and writes a `packetization_gate.v1` report for the exact range. If a packet is missing, the step does not count until the packet is created with `planveyor_rollout_packet_create`. The audit of such a range does not pass without a valid report. The report does not show whether the recipient project adopted the packet.

## Example: the range review template

Neither the Planveyor history nor the SQL project from the running example has a real run of this check. Here is the beginning of the range review template [`_template_merge_range.md`](../../code_reviews/_template_merge_range.md) (in Russian):

```markdown
# Code review — merge-range (BASE..HEAD)

**Date:** DD.MM.YYYY HH:MM
**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)
**Spec:** docs/plans/<origin_plan>.md | N/A (origin_plan_state=manual_range_review_no_origin_plan)
**Range:** BASE=<sha> .. HEAD=<sha|HEAD> (legacy/context only; helpers read `**Target:**`)
**Exclude docs:** yes/no
**Status:** Черновик | ✅ OK | ❌ S1 blocker(ы)
[…]
## Контекст диапазона (required)
- merge list: `git log --oneline --first-parent --merges BASE..HEAD`
- note: если были fixup‑коммиты после merge — они тоже входят в BASE..HEAD
```

In the review of a single task against the current bundle, the `**Target:**` line holds the checksum of the bundle (`BUNDLE=current bundle_sha256=…`); here it holds the commit range. The `**Range:**` and `**Exclude docs:**` lines and the sections about the contents of the range are added. Then come the same sections of the two lanes, the final section, and the S1–S3 scale.

This check does not fill in the `## Post-merge gate` section in the plan of a single task: by the time the check starts, the plan is already in `Done` and does not change (the [Task closeout](closeout.md) chapter covers the section). In the final section of the review of the `GetReorderCandidates` task, the line `audit_status: pending_post_merge_audit` remained: there was no post-merge audit in that project. This value does not block the task closeout; the review linter checks only that it is one of the allowed values.

The detailed rules of the steps are in the [Lifecycle and packets](../lifecycle-and-packets.md#post-merge-and-closeout) guide and in the playbooks for the [range review](../../playbooks/review_merge_range.md) (in Russian), the [audit](../../playbooks/post_merge_audit.md) (in Russian), the [plan harvest](../../playbooks/post_merge_plan_harvest.md) (in Russian), and [docs hygiene](../../playbooks/post_merge_docs_hygiene.md) (in Russian).

The functions and tests discussed here are in the [code map](code-map.md#post-merge-check).

Next: [Engine tests](engine-tests.md).

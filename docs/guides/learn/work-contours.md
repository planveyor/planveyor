# Development, analysis, and decomposition

**English** · [Русский](work-contours.ru.md)

Planveyor distinguishes three kinds of work, or contours: development, analysis, and decomposition. Development changes the project files right away. Analysis first answers a question and chooses what to do next, and decomposition splits a large goal into several plans. All three share the roles and the statuses; they differ in the result and in how the plan ends.

## Three work contours

| Contour | When to choose it | What comes out | Marker in `plan_meta` |
| --- | --- | --- | --- |
| Development | The result and the scope are clear: you can name the files and the acceptance conditions | Changed files, check results, a review, and a commit | None: this is the default contour |
| Analysis | You need to answer a narrow question based on the repository files and compare options | A checked analysis pack and the decision of Architect about the next work | `wave_family = "analysis_wave"` |
| Decomposition | A large goal is accepted but does not fit into one plan | An umbrella plan, child plans with the execution order, and follow-ups | `phase_overlay = "decomposition_wave"` and `phase_state` |

The markers are in the `plan_meta` object of the `## Meta` block of the plan. For decomposition, the `phase_state` field is `active` while the goal is being split and `parked` when the split is accepted. The umbrella plan is the main plan of a decomposition: it holds the problem statement, the map of the child plans, and their order, and it does not change code.

Development is the default choice, small edits included. Split a task when one plan stops holding it: for example, the plan is rewritten several times, and the conditions still have not settled. A long goal description is not such a reason by itself. The [decomposition playbook](../../playbooks/decomposition_wave.md) (in Russian) suggests estimating the number of parts in advance. With one part, an ordinary development plan is almost always enough. Two or three parts give a light decomposition; four or more give a full one, with a long-lived umbrella plan and a separate review of the plans.

Analysis answers a question that can be checked against the repository files: documents, plans, code. Open market research without such sources is not part of analysis.

![Three contours: after the review and the decision of Architect, development is closed with a commit, analysis gives a decision about the next work, and the umbrella plan of a decomposition is parked, with the work going on in the child plans](assets/work-contours-1.svg)

After acceptance, a development plan and an analysis plan are closed the usual way: a commit, then the docs closeout. Architect parks the umbrella plan: it sets `phase_state = "parked"` and usually the `Ready for Planner` status, and the plan stays as a reference while the child plans run. Architect moves it to `Done` by a separate decision when all child plans are finished.

The boundary between the contours is recorded in [ADR 007](../../adr/007-planning-dev-contour-boundary.md) (in Russian). Analysis and decomposition plans change only documents: the analysis pack, plans, and follow-up records. Product code changes only in development plans. If in the middle of development it turns out that a broad analysis or a split into parts is needed, the role stops and returns the work to Architect with the `Ready for Architect response` status.

## How the roles work

The roles here are the same agent harness sessions as in development ([Roles and task files](roles-artifacts.md)), and Manager drives them through the same statuses. In analysis and decomposition plans, Coder writes the analysis pack or plans; it does not touch product code.

| Role | In analysis | In decomposition |
| --- | --- | --- |
| Architect | Sets the question, the goal, and the constraints; after the review, chooses the outcome | Describes the whole task: the result, whom it is for, what is in the way now, and what is out of scope; chooses the criterion for the split |
| Planner | Decides which sources to read and what the analysis pack should look like | Describes each part: what it receives and hands over, what it depends on, how to check it; sets the order of the parts |
| Coder | Reads the sources and records the options, the assumptions, and the recommendation in the pack | Creates the umbrella plan, the child plans, and the follow-up records |
| Reviewer | Checks the sources, the unconfirmed assumptions, and the clarity of the recommendation | Checks that the parts cover the goal, do not duplicate each other, and each can be accepted separately |

In an umbrella plan, `Ready for Review` means that the umbrella plan and the child plans are written, and `Ready for Arch review` means that these plans have passed the review ([plan rules](../../plans/README.md), in Russian). Coder creates each child plan from the template with the `Ready for Planner` status: the plan's own cycle starts from it.

The analysis pack is the `## Analysis pack` section. Until the `Planner finalize` status, Architect and Planner fill it in right in the plan. When the plan goes to `Planner finalize`, Planner moves the pack to a separate file `docs/analysis_packs/<plan_stem>.md` (`<plan_stem>` is the plan file name without `.md`) and leaves one line with the link in the plan, `analysis_pack_ref`. From then on, this file is the only target file of the code draft: Coder fills it in, and Reviewer checks it. The move is needed because the plan changes during the review (see [The plan and its statuses](plan-lifecycle.md)). If the `recommendation`, `route_recommendation`, `execution_budget`, or `stale_trigger` rows stay in the plan after the move, the plan linter reports the `operational_duplicate` error. The [analysis playbook](../../playbooks/analysis_wave.md) (in Russian) describes what to do if the status is already set but the pack has not been moved.

How the analysis pack is stored and how child plans are launched is still being refined; see the [What works now and what comes next](capabilities-boundaries.md) chapter.

## Five analysis outcomes

Coder ends the analysis with a recommendation (`route_recommendation`): which of the five outcomes it proposes and why. A recommendation is not a decision yet, and Manager does not start anything based on it. Architect chooses the outcome at acceptance (`Architect arch review`) and records it in the `## Promoted route artifact` section of the plan.

| Outcome | `accepted_route` | What appears | Next step |
| --- | --- | --- | --- |
| Development | `developer_wave` | A new development plan with a link to the analysis plan (`seed_dev_plan`); it starts at `Architect initial draft` | The usual cycle of the new plan |
| Decomposition | `decomposition_wave` | An umbrella plan of the decomposition (`decomposition_umbrella`) | The roles split the goal into child plans |
| Owner question | `human_gate` | A question or an approval request in the Q&A log (`owner_gate`) | The work waits for the decision of Owner |
| Defer | `defer` | A follow-up record in `docs/followups/` with the responsible party and the reason (`followup`) | The topic comes back when the recorded condition is met |
| Reject | `reject` | A rejection record with the reason (`rejection_receipt`) | Nothing starts |

The last three outcomes give the roles no new work for now. They are chosen when the checked analysis pack shows that starting development or decomposition now is not worth it. An Owner question and a follow-up must have a recorded trigger to come back to the topic (`revisit_when`); otherwise, the plan linter reports an error. Until the accepted outcome has a record (`promoted_artifact_ref`) and a next step (`next_action`), the analysis plan does not close.

## How it looks in the plan

The GetReorderCandidates task from the running example is ordinary development. Owner made all the decisions in advance, and in the `## Как я понял задачу` section (how I understood the task), Architect wrote: “there are no open decisions to agree on.” The contour markers in `plan_meta` are empty:

```json
"wave_family": null,
"phase_overlay": null,
"phase_state": null,
```

The plan closes the template sections for analysis and decomposition with an explicit `N/A` and the reason, quoted as written in the project, in Russian:

```markdown
## Business decomposition framing
N/A (why=одна ограниченная процедура, не decomposition wave).

## Child plan map
N/A (why=обычный dev-plan без child graph).
…
## Analysis pack
N/A (why=не analysis wave).

## Promoted route artifact
N/A (why=не analysis wave).
```

There is no real analysis plan yet, either in the Planveyor repository or in the SQL projects built on it. Its structure is set by the [plan template](../../plans/_template.md) (in Russian); this is how the analysis pack starts in the template (some rows are omitted):

```markdown
## Analysis pack
| Field | Value |
| --- | --- |
| `analysis_subject` | `<bounded subject>` |
| `desired_outcome` | `<decision/route this analysis must enable>` |
…
| `scope_refs` | `<opened/read repo-backed refs; retrieval hits not read do not count>` |
…
| `options_considered` | `<options + trade-offs + rejected alternatives>` |
| `recommendation` | `<chosen answer / decision proposal>` |
…
| `route_recommendation` | `<developer_wave|decomposition_wave|human_gate|defer|reject> + reason + prerequisites + target refs` |
…
```

Architect records the subject and the goal of the analysis (`analysis_subject`, `desired_outcome`). Coder records which sources it actually opened and read (`scope_refs`), which options it considered, and what it recommends. After acceptance, Architect fills in the `## Promoted route artifact` section: the accepted outcome (`accepted_route`), the kind and the path of the created file (`promoted_artifact_kind`, `promoted_artifact_ref`), and the next step (`next_action`).

Decomposition was tried in another SQL project on Planveyor, and it is not finished. The umbrella plan “product price history audit” stopped at the review (`Ready for Review`), and three child plans wait for Planner (`Ready for Planner`). Its markers and links to the child plans:

```json
"phase_overlay": "decomposition_wave",
"phase_state": "active",
"parent": null,
"next_plans": [
  "docs/plans/260930_2156_product_unit_price_history_table.md",
  "docs/plans/260930_2156_product_unit_price_history_trigger.md",
  "docs/plans/260930_2156_product_unit_price_history_queries.md"
],
```

The first child plan creates the price history table, the second one creates a trigger that records price changes, and the third one creates two procedures that read the history. The second plan waits for the first, and the third comes after the second. There are three parts, so the split is light. The full map of the child plans is in the `## Child plan map` section of the umbrella plan, and the order is in `## Execution queue`.

The detailed rules are in the [analysis](../../playbooks/analysis_wave.md) and [decomposition](../../playbooks/decomposition_wave.md) playbooks, and the [plan vocabulary](../../_meta/plan_vocab.json) lists the allowed values of the markers and outcomes. A [short reminder](../planning_contour_continuity.md) lists which documents the roles should reread when they come back to such a plan after a break.

## What Owner does

- When you create a plan with `$planveyor-plan-draft`, describe what you need to get: a change, an answer to a question, or a split of a large goal. The skill chooses the plan type together with Architect, and Architect makes the final decision on the contour ([stack sibling guide](../stack-sibling.md#next-task-and-readiness)).
- Run an analysis plan like an ordinary plan: in TUI mode or with the `planveyor sibling architect`, `answer`, and `run` commands of manual mode, and after acceptance, close it like an ordinary plan ([Task closeout](closeout.md)).
- Only after that, make the new plan current if Architect created one: `planveyor sibling plan docs/plans/YYMMDD_HHMM_topic.md`. The first step is the discussion with Architect: in the Manager window or with `planveyor sibling architect`.
- For decomposition, the [playbook](../../playbooks/decomposition_wave.md) suggests a separate entry point, the `planveyor_decomposition_collab_tui` wrapper. With such a launch, Architect itself sets `Done` and commits ([Who makes the commit](review-acceptance.md#who-makes-the-commit)). You can continue a decomposition with `run`, but how to finish it with the sibling commands is not described yet (see [What works now and what comes next](capabilities-boundaries.md)).
- Each child plan goes through its own cycle. `planveyor sibling run` does not create a queue of them: that is a separate Manager mode, described in the [launch guide](../launch-and-role-modes.md).

## Common mistakes

- Splitting a task because a small model will do it. The choice of model is not a reason for decomposition.
- Creating child plans inside an ordinary development plan. First, Architect moves the work to decomposition.
- Treating a parked umbrella plan as a finished task. The work goes on in the child plans.

The functions and tests discussed here are in the [code map](code-map.md#development-analysis-and-decomposition).

Next: [Review and acceptance](review-acceptance.md).

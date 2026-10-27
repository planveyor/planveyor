# Tests and evidence: what you can trust

**English** · [Русский](testing-evidence.ru.md)

While a task goes from the plan to the commit, it is checked several times: by Planveyor scripts, tests, a live run in the dev environment, Reviewer, and Architect. Each check has its own limit. Below, this is shown on the `GetReorderCandidates` task: an SQL procedure finds the products to reorder. A separate part covers when a green result stops being valid.

## Kinds of checks

Besides the roles, the harness takes part in the checks: the project scripts that build the project, deploy it to the dev environment, and run the stack tests.

| Check | Who runs it | What it proves | What it does not see |
| --- | --- | --- | --- |
| Structural checks: the plan linter, Oracle, the check of the exact bundle of the plan | The roles before a handoff, Manager, the `planveyor sibling` commands | The plan, the code draft, and the review are filled in by the rules, the status allows the transition, the declared files are in place | Whether the code works |
| Tests without a real environment | Coder | The code and the harness handle prepared inputs correctly; the project builds, the linter passes | How a real database, service, or external client will behave |
| Live check | A role with access to the dev environment, or a person | The changed behavior passed the checks in this environment on this version of the files | Other environments and later versions of the files |
| Review | Two Reviewer lanes | The result is compared with the plan, a separate lane looked for risks, the review is tied to a version of the target files | What Reviewer did not run itself; Reviewer states this in the limits |
| Acceptance | Architect | The acceptance criteria are met, the review is not stale | What the runs and the review it relies on did not see |

Structural checks find a missing plan section or a file that is not on disk, but they know nothing about the business rule. Offline tests feed fixtures, prepared inputs, to the code and compare the result with the expectation; Coder runs them during the work. A live check is slower and needs access to the environment, but it sees the real state of that environment.

The plan names the tests and checks for the changed files. The stack harness comes from the plan, `AGENTS.md`, or the project rules ([test contract](../../tests.md), [harness choice](../../testing_runbook.md)). Planveyor does not substitute its own commands for a language, framework, database, or interface. If there is no declared harness, this is a blocker or an explicit `N/A` with the reason in the plan.

![A requirement becomes a check: a test input with an expectation, the check, the observed result, and the review decision](assets/testing-evidence-1.svg)

For example, the rule “take the expected delivery into account” is checked by the `test_positive_shortage_and_units_on_order` test. In its fixture, the product One has a reorder level of 12, 3 in stock, and 4 on order, and the test expects a shortage of 5 from the procedure. The other cases are collected in a table in the [running example](sql-example.md).

## What each check saw in the GetReorderCandidates task

Who did what in this task is told in the [Roles and task files](roles-artifacts.md) chapter, and how the live run went is told in the [running example](sql-example.md). Here the same events are sorted by check. The operator made the runs on the dev database and left a receipt for each: the command, the time, the version of the files, and the result.

| Check | What it showed | What it did not see |
| --- | --- | --- |
| Plan linter | On the first run, it found three form defects | Whether the shortage formula is right |
| Bundle check | Before the code started, the bundle had 19 files, with the review among them only planned; before acceptance, 22 files, all in place | What these files say |
| 40 harness tests, the build, the SQL linter, and the secrets check, all without a database | The harness rejects missing, extra, repeated, and failed results and a wrong row order; the build passed without errors or warnings | The state of the dev database: the test class there did not have the tSQLt marker that makes a schema a test class |
| First `make db-proof` | The harness stopped before deploying to the database: the state of the test classes was ambiguous | The procedure itself: the run did not reach the SQL tests |
| Second `make db-proof` | 8 tests out of 8; products added as 30, 10, 20 came back in the order 10, 20, 30; the checksums of 15 files are recorded in the receipt | The code after the commit; why the marker disappeared: the cause was named as likely but not proven |
| Review | No findings; 15 sums out of 15 matched the files; the 40 harness tests passed again | SQL: Reviewer did not run it |
| Architect acceptance | The bundle of 22 files passed the check, the sums matched, the verdict is recorded | Architect did not run SQL either; the acceptance relies on the runs and the review |

Reviewer recorded its own limits and what it checked itself in the risk lane (the record is examined in the [Review and acceptance](review-acceptance.md#how-it-went-the-getreordercandidates-review) chapter). This way, Architect and Owner see what the conclusion of the review relies on.

## What the live check added

Before the live run, everything in the task was green: 40 out of 40 harness tests, the build, the linter, the secrets check. Coder recorded in the plan that these results do not count as an SQL success and left the run on the dev database to the operator. The records of the red run were kept, and the plan links to them.

The fix changed the harness and its tests, so Coder ran the harness tests again. The result was 39 out of 40: a fake in one test left the JUnit report path in the real project directory, and the report of the red run was already there. Coder moved this path to a temporary directory and got 40 out of 40.

## Evidence is tied to a version of the files

A green result is valid only for the files on which it was obtained. So every check record names the version. The receipt of the second run starts like this:

```text
UTC start: 2026-09-27T22:26:39.501836+00:00
UTC end: 2026-09-27T22:26:52.922543+00:00
Elapsed seconds: 13.420
Command: `/usr/bin/make db-proof`
[…]
Source HEAD before/after: `60332b46eba26a9c09cf199184c45afe10e61f1b` / `60332b46eba26a9c09cf199184c45afe10e61f1b`
Outer actual rc: 0
[…]
Exact current 8-case JUnit matches and proof green: True
```

Further down, the receipt lists the SHA-256 checksums of fifteen executable and configuration files. Reviewer and Architect compared them with the files on disk: 15 out of 15. So the run used the same 15 files that were accepted later. Coder edited `README.md` after the run: the receipt does not cover this edit; the review checked the README in its new form.

The review is tied to a version in the same way. Its header records the target snapshot:

```markdown
**Target:** BUNDLE=current bundle_sha256=d8214af66e8b6797b45ecdf059790ed5e584513a4a773d385d2ad043a22a1cb4
```

The snapshot is a checksum of the contents of all 16 target files from the code draft. Planveyor checks recompute it from the current files. If even one target file changed after the review, the sum does not match and the review stops being valid: Oracle reports a blocker, and `planveyor sibling close` refuses the commit.

The run in the example was made before the commit; SQL was not run after the commit. Reviewer wrote exactly that: the green result applies to the code before the commit.

## Mechanism, test, and accepted task

Tell three levels apart: a command exists, a test exists, a task is accepted. The table shows what follows from each.

| What you see | What follows from it | What to look at next |
| --- | --- | --- |
| A command and the code that runs it | The mechanism exists | The limits in the [launch guide](../launch-and-role-modes.md) and in the [What works now and what comes next](capabilities-boundaries.md) chapter |
| A test with a name and assertions | The behavior is defined for the inputs of this test | The test itself: its fixtures, what it fakes, and which code branch it goes through |
| A successful run report | The checked cases passed on the stated version and in the stated environment | The command, the time, the version of the files, and the full result |
| A closed plan | The task was accepted and committed | The plan, the review, the bundle, and the [task closeout](closeout.md) |
| An item in the backlog | There is an intention or a commitment | Its state and limit in the [First-release backlog](../../release_backlog.md) (in Russian) |

Each level needs its own evidence. Code that starts the roles does not yet say that the agent harness is available, and a test with a faked Codex client does not prove a live role session. An accepted task in one sibling does not confirm that Planveyor will handle another stack.

## What Owner does

You choose who runs the live stack checks in the stack brief during the sibling adaptation: either the roles get network access in the Codex settings, or a person runs the live commands. How to return the result to the role in the second case, red or green, is shown in the “What Owner does” section of the [running example](sql-example.md).

Before the commit, look at the bundle with `planveyor sibling close`. If the review is stale, `close --commit` refuses ([Task closeout](closeout.md)).

`planveyor sibling ready` does not run the live checks again. So check for yourself that the checks of this task really passed: a report of an earlier task or of another task does not replace them.

In a check record, look for five things:

1. The change and the exact version of the files that the check applies to.
2. The command, the project, and the essential conditions of the environment, without secrets.
3. The actual exit code and the case names; separately, skipped cases, warnings, and checks that do not apply.
4. Which acceptance criteria are proven and which need another check.
5. Links to the current files for Reviewer and Architect.

The version of the files, the command, and the exit code are visible in the receipt above; the rest is in the plan and the review.

## Common mistakes

- Taking a “Reviewer checked” record for a repeated run of the checks.
- Hiding a red run.
- Judging a test suite by the number of tests without reading what they check.

The functions and tests discussed here are in the [code map](code-map.md#tests-and-evidence-what-you-can-trust).

How the tests of Planveyor itself are built is told in the [Engine tests](engine-tests.md) chapter.

Next: [Sibling: creation and upgrade](sibling-lifecycle.md).

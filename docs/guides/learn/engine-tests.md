# Engine tests

**English** · [Русский](engine-tests.ru.md)

This chapter is for those who change Planveyor itself: its scripts, role rules, prompts, and templates. Before the review of such a change, you run the engine tests and the documentation checks and record the command and the result in the review if they matter for acceptance ([CONTRIBUTING](../../../CONTRIBUTING.md)). The tests of your product live in the sibling and are not part of this suite.

## How the suite is built

The engine tests are written with the standard Python `unittest` and lie next to the code, in `scripts/test_*.py` files; there are more than a hundred such files now. The `make test-scripts` target finds them with the ordinary test discovery:

```sh
"$PYBIN" -m unittest discover -s scripts -p "test_*.py" -v
```

A new `test_<topic>.py` file in `scripts/` joins the suite by itself; you do not need to edit the [Makefile](../../../Makefile) for that. The Makefile targets take the interpreter from the `PYBIN` variable, or, if it is not set, from the activated environment or `python3` on `PATH`. The `scripts/_pybin.sh` script makes this choice and checks the version.

The suite has three kinds of tests:

| Kind | Example input and what is checked | What you can conclude |
| --- | --- | --- |
| Helper script test | A temporary plan without a code draft; the result JSON | The script notices that a required file is missing and names the blocker |
| Contract test of documents and prompts | The text of a playbook or prompt; the required markers | The instruction kept the needed structure and the boundaries of context passing |
| Integration test | Temporary Git repositories; the real `bin/planveyor` and linter | The components agree with each other; after a refusal, the plan queue files do not change |

Contract tests read the documents of the repository itself. Almost all the others create a project or a Git repository in a temporary directory. The shared integration test helper `AuthorityFixture` copies the engine sources into a new temporary repository and touches neither the source checkout nor the owner's repository. If a test needs the Codex client, a fake script that records the arguments it receives stands in for it.

A live role launch and the product checks are not part of the suite. To say “the role did the work”, you need a real call of a configured agent harness and the result in the file that the plan declared; to say “the product works”, you need the sibling harness. See the [Tests and evidence: what you can trust](testing-evidence.md) chapter for details.

## How to run it

Run the commands from the root of the Planveyor checkout, in an activated environment with Python 3.12 and the dependencies from `requirements-dev.lock`. You create the environment yourself, and `make bootstrap-python` installs the dependencies into it once. The [verification routes](../../tools/verify_suite.md) separate the supported environment of the first version, macOS/Python 3.12, from the technical range of the loader, Python 3.10–3.12 ([What works now and what comes next](capabilities-boundaries.md#limits-of-the-first-version)).

| Command | What it runs |
| --- | --- |
| `make verify` or `./bin/planveyor planveyor_verify` | Quick mode: integrity checks, no tests |
| `make test-scripts` | All engine tests in one discovery |
| `make verify-full` or `./bin/planveyor planveyor_verify --full` | Integrity checks and one test discovery |
| `./bin/planveyor planveyor_verify --module portability` | Only the named check module |
| `./bin/planveyor planveyor_doc_lint` | Links and file mentions in the documentation |

Start with the smallest route that checks what you changed. To check everything, choose one of them, `make test-scripts` or `make verify-full`: run one after the other, they run all the tests twice. You cannot pass the `--full` and `--module` flags together: the command exits with an error. To run one test file, use the same discovery with a narrower pattern; in an activated environment, this is `python3 -m unittest discover -s scripts -p "test_verify_suite.py" -v`.

### Integrity checks

`make verify`, `make verify-full`, and `planveyor_verify` run [verify_suite.py](../../../scripts/verify_suite.py). It collects the results of several check modules into one report. Modules register in it with the `register()` decorator, and `_load_modules()` selects all modules or the ones named in `--module`. For now, there is one module, `portability`. Without flags, it searches the tracked files for tokens, keys, email and server addresses, and private paths, checks whether the documents refer to Python from Homebrew, and looks for traces of a failed automatic replacement. With `--full`, these checks also run one test discovery, adding the Python flag `-B` to the parameters used by `make test-scripts`.

The module checks selected plans and the archived snapshot of documents only if they were passed explicitly, with the `--portability-plan` and `--archive-snapshot` flags. Otherwise, the report says plainly that these inputs were not selected and claims nothing about them.

### Documentation linter

`./bin/planveyor planveyor_doc_lint` checks `AGENTS.md`, `docs/roles`, `docs/playbooks`, `docs/guides`, and `docs/arch.md` for broken relative links and file paths in backticks, for example `scripts/verify_suite.py`. It also checks that the required shared phrases are in place in groups of related documents: for example, `reviewability preflight receipt` in ten prompts and role definitions. `make doc-lint` runs the same [doc_lint.py](../../../scripts/doc_lint.py) with the default roots and without the check of paths in backticks.

For now, `planveyor_doc_lint` is red in the engine root. It looks for paths that exist only in a sibling in Planveyor itself (item F25 in the [First-release backlog](../../release_backlog.md), in Russian). While F25 is open, errors about such paths are expected; there must be no errors in the files you changed.

## How to read the result

Each `planveyor_verify` check returns `pass`, `warn`, or `fail`. The plain output looks like this (placeholders in angle brackets):

```text
== verify-suite: <number of modules> module(s), <number of checks> check(s) ==
[portability] <check> ........ PASS  (<metric>)
---
VERDICT: GREEN
INTERPRETATION [portability]:
  <module interpretation>
```

With `--format json`, the same result comes out as one JSON object with the `verdict` and `modules` fields.

Exit code `2` means that at least one check gave `fail` or that the command was called with wrong arguments. Code `0` means that there are no failures. `GREEN` can come with `WARN` warnings too, so read the metric, the details, and the interpretation before you consider the work ready. For the test discovery, the metric is the number of tests run and the number of `FAIL` or `ERROR` lines, and the full `unittest` output goes to the error stream.

`planveyor_verify` does not check role launches, the tests of the target project, the review acceptance, or the task closeout ([verification routes](../../tools/verify_suite.md)). After a fix, run the failed module again: `--module <name>`.

## Examples from the suite

### A helper script test

`test_missing_code_draft_fails_closed` from [test_plan_handoff_digest.py](../../../scripts/test_plan_handoff_digest.py) checks the handoff digest. This is a script that collects into one answer the state of the plan, the code draft, and the review, together with the answers of Oracle and the bundle check. It decides nothing by itself; it only reads. The test creates a plan and a review without a draft in a temporary directory, puts stubs in place of Oracle and the bundle check, and expects a refusal:

```python
self.assertEqual(payload["state"], "missing")
self.assertEqual(payload["truth_hosts"]["code_draft"]["state"], "missing")
self.assertIn("code_draft", {blocker["host"] for blocker in payload["blockers"]})
```

Without a draft, the digest stops and names the missing source.

### A contract test

The review playbooks receive the task text and the diff between markers. `test_generic_reviews_preserve_supplied_spec_and_diff_transport` from [test_planveyor_shared_corpus_contract.py](../../../scripts/test_planveyor_shared_corpus_contract.py) makes sure that the markers are not lost:

```python
for name in ("review_staged_or_commit.md", "review_docs_staged_or_commit.md"):
    with self.subTest(playbook=name):
        text = (ROOT / "docs/playbooks" / name).read_text(encoding="utf-8")
        for marker in ("<<SPEC_TEXT>>", "<<END_SPEC_TEXT>>", "<<DIFF>>", "<<END_DIFF>>"):
            self.assertEqual(text.count(marker), 1, f"{name}: {marker}")
        self.assertLess(text.index("<<SPEC_TEXT>>"), text.index("<<END_SPEC_TEXT>>"))
        self.assertLess(text.index("<<DIFF>>"), text.index("<<END_DIFF>>"))
```

Each marker must occur exactly once, and each start must come before its end. The test catches a change that breaks the boundaries. It does not check whether the model reads the text between the markers well.

### An integration test

`test_real_downstream_na_admission_and_public_refusal_are_state_safe` from [test_planveyor_admission_integration.py](../../../scripts/test_planveyor_admission_integration.py) checks plan admission through the [bin/planveyor](../../../bin/planveyor) facade, the common entry to all engine commands. The test copies the real `bin/planveyor` into a temporary Planveyor checkout, creates a temporary project, and runs the plan linter twice: `--project <project> planveyor_plan_lint <plan>`. The plans differ in one carrier, `machine_authority_decision` in `plan_meta`. This carrier is required before the plan is handed on. The code draft in the test stays the same, so the reason for the refusal is unambiguous. With the carrier, the linter returns `0`. Without it, the linter returns `1` and prints exactly one `ERROR:` line with `missing_required_carrier`. After the refusal, the plan queue files and the engine state directory are the same as before it. The facade and the linter are real here; no model and no database take part in the test.

### A test of the check suite itself

`test_discovery_matches_makefile_and_streams_combined_transcript` from [test_verify_suite.py](../../../scripts/test_verify_suite.py) replaces the test discovery process with a result that has code `1`, seven tests, and one error. The test expects the discovery parameters of `make test-scripts` with the additional Python flag `-B` and the result `fail` with the metric `Ran 7 tests, 1 FAIL/ERROR`. This way, `verify_suite.py` is tested without running the real test suite.

## How to add a test

Put a `test_<topic>.py` file with a `unittest.TestCase` class into `scripts/`, and the discovery finds it by itself. Create the project for the test in a temporary directory, outside the working copy. In the SQL example, a harness test that looked into the real project directory found the report of a red run there and failed. Helpers already exist: `run_zsh_fixture()` from `scripts/test_support/process_contract_fixtures.py` runs zsh only with the environment that the test passed, and `AuthorityFixture` builds a temporary Planveyor checkout and a temporary project. Name the rule in the test name, and besides the allowed case, check the refusal.

## Common mistakes

- Treating `make verify` as a full check. Without `--full`, the tests do not run.
- Reading only `VERDICT: GREEN` and skipping the `WARN` lines.

The functions and tests discussed here are in the [code map](code-map.md#engine-tests).

This is the last chapter of the section. The other chapters are listed in the [section map](README.md#section-map).

"""Cheap isolated regressions for canonical shard and subset execution."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import run_test_shard as shard


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts/run_test_shard.py"
A = "test_alpha.AlphaTests.test_a"
B = "test_alpha.AlphaTests.test_b"
C = "test_beta.BetaTests.test_c"


EXPECTED_CORE = (
    "test_planveyor_init_capture.InitCaptureTests.test_in_scope_init_wrappers_promote_run_artifacts_by_sid",
    "test_planveyor_init_capture.InitCaptureTests.test_failed_init_without_sid_stays_under_pending",
    "test_planveyor_init_capture.InitCaptureTests.test_runner_selection_init_precedes_artifacts_and_consumes_captured_bytes_once",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_writes_fresh_success_receipt_and_compat_readback",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_rejects_bad_or_changed_preflight_identity_before_child",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_missing_wrapper_and_spawn_error_are_not_started",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_nonzero_and_timeout_are_non_green_receipts",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_keeps_non_green_child_and_green_outcome_independent",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_functional_safety_witness",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_recovery_tuple_is_one_shot_and_exactly_once",
    "test_planveyor_init_capture.InitCaptureTests.test_role_run_carrier_is_isolated_from_manager_architect_paths",
    "test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_clean_first_source_pins_and_same_source_is_idempotent",
    "test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_runtime_closure_and_runner_policy_drift_fail_before_effect_sentinel",
    "test_sibling_runbook.NativeSiblingCommitPolicyTests.test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient",
    "test_sibling_runbook.NativeSiblingCommitPolicyTests.test_tui_markerless_legacy_refuses_before_session_effects",
    "test_planveyor_bare_entrypoints.PlanveyorFacadeDashboardTests.test_help_and_dashboards_finish_without_per_row_authority_revalidation",
)

EXPECTED_COMPAT = (
    "test_contract_authority_loader_stream.ContractAuthorityLoaderStreamTests.test_header_is_not_executed_and_body_status_stays_in_current_shell",
    "test_contract_authority_loader_stream.ContractAuthorityLoaderStreamTests.test_missing_supported_python_explains_how_to_select_it",
    "test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_runtime_closure_and_runner_policy_drift_fail_before_effect_sentinel",
    "test_pybin.PybinResolveTests.test_project_cache_is_ignored_in_favor_of_path_python3",
    "test_pybin.PybinResolveTests.test_explicit_invalid_pybin_stays_strict",
    "test_pybin.PybinResolveTests.test_conda_prefix_precedes_path_python3",
    "test_contract_authority_snapshot.AuthoritySnapshotTests.test_local_marker_v3_has_exact_live_fields",
    "test_contract_authority_snapshot.AuthoritySnapshotTests.test_duplicate_json_keys_and_non_json_bytes_are_rejected",
    "test_consumer_contract.ConsumerContractFacadeTests.test_public_facade_init_doctor_and_compatible_upgrade",
)

EXPECTED_CONTRACT_MODULES = (
    "test_authority_vocabulary_prompt_contract",
    "test_censor_prompt_contract",
    "test_manager_custom_pipeline_prompt_contract",
    "test_plan_lint",
    "test_plan_lint_changed",
    "test_review_header_metadata",
    "test_run_test_shard",
    "test_sibling_contract_docs",
    "test_zcode_bootstrap_lifecycle_prompt_contract",
    "test_plan_handoff_digest",
    "test_plan_harvest_lint",
    "test_plan_status_oracle",
    "test_planning_wave_readback",
    "test_planveyor_plan_list",
    "test_doc_lint",
    "test_doc_lint_policy",
    "test_shared_docs_mirror_drift",
    "test_review_artifact_lint",
    "test_analysis_source_ownership",
    "test_build_role_bundles",
    "test_planveyor_profile_extraction",
    "test_planveyor_shared_corpus_contract",
    "test_check_planveyor_profile_contract",
    "test_planveyor_codex_agent_roles",
    "test_contract_authority_matrix_check",
    "test_oss_release_scan",
    "test_oss_evidence_prepare",
    "test_docs_closeout",
    "test_plan_queue",
)


class TestRunTestShard(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="planveyor-subset-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.manifest = self.scripts / "test_shards.json"
        self.trace = self.root / "trace"
        for module, cls, methods in (("alpha", "AlphaTests", ("a", "b")), ("beta", "BetaTests", ("c",))):
            body = (
                "import pathlib, unittest\n"
                "def trace(value):\n"
                "    with (pathlib.Path(__file__).resolve().parent.parent / 'trace').open('a') as out:\n"
                "        out.write(value + '\\n')\n"
                f"def setUpModule(): trace('{module}:module+')\n"
                f"def tearDownModule(): trace('{module}:module-')\n"
                f"class {cls}(unittest.TestCase):\n"
                "    @classmethod\n"
                f"    def setUpClass(cls): trace('{module}:class+')\n"
                "    @classmethod\n"
                f"    def tearDownClass(cls): trace('{module}:class-')\n"
            )
            for method in methods:
                body += f"    def test_{method}(self): trace('{method}:' + str(id(self)))\n"
            (self.scripts / f"test_{module}.py").write_text(body, encoding="utf-8")
        self.data = {
            "version": 1, "baseline_head": "a" * 40, "weighting": {}, "zero_test_modules": [],
            "shards": [
                {"id": "s01", "selectors": [{"module": "test_alpha", "ids": [A]}]},
                {"id": "s02", "selectors": [{"module": "test_alpha", "ids": [B]}]},
                {"id": "s03", "selectors": [{"module": "test_beta"}]},
            ],
            "local_profiles": {"3": [
                {"id": f"g{i}", "shards": [f"s{i:02}"]} for i in range(1, 4)
            ]},
            "subsets": {"compat310": {"ids": [C, A]}},
        }
        self.write_manifest()

    def write_manifest(self, data=None):
        self.manifest.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")

    def cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(RUNNER), "--root", str(self.root), *arguments],
            text=True, capture_output=True, timeout=30,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def init_git(self):
        for arguments in (("init", "--quiet"), ("add", "."),
                          ("-c", "user.name=Subset fixture", "-c", "user.email=subset@example.invalid",
                           "commit", "--quiet", "-m", "synthetic fixture")):
            subprocess.run(["git", "-C", str(self.root), *arguments], check=True, capture_output=True)

    @contextmanager
    def discovery(self):
        old_path, old_cwd = sys.path[:], Path.cwd()
        modules = {key: sys.modules.get(key) for key in ("test_alpha", "test_beta")}
        try:
            for key in modules:
                sys.modules.pop(key, None)
            shard.prepare_discovery(self.root)
            loader = unittest.TestLoader()
            cases = list(shard.flatten(loader.discover(str(self.scripts))))
            self.assertEqual(loader.errors, [])
            yield cases
        finally:
            sys.path[:] = old_path
            os.chdir(old_cwd)
            for key, value in modules.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value

    def args(self, label="report"):
        return argparse.Namespace(root=self.root, report=self.root / f"{label}.json", durations=None,
                                  subset="compat310", shard=None, local_profile=None, local_group=None)

    def execute(self, args, cases, data=None, heads=None):
        with mock.patch.object(shard, "git_head", side_effect=heads or ["a" * 40, "a" * 40]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return shard.run_selected(args, data or self.data, "b" * 64, cases, {})


    @contextmanager
    def ci_fixture(self):
        # Exact public IDs, but only tiny generated no-op bodies: never WORK witnesses.
        with tempfile.TemporaryDirectory(prefix="ci-policy-", dir=self.root) as temporary:
            root = Path(temporary).resolve()
            scripts = root / "scripts"
            scripts.mkdir()
            ids = set(EXPECTED_CORE) | set(EXPECTED_COMPAT)
            ids.update(module + ".ContractTests.test_contract"
                       for module in ("test_planveyor_plan_bundle", *EXPECTED_CONTRACT_MODULES))
            ids.add("test_unclassified.OtherTests.test_full_only")
            module_classes = {}
            for test_id in ids:
                module, cls, method = test_id.split(".")
                module_classes.setdefault(module, {}).setdefault(cls, set()).add(method)
            for module, classes in module_classes.items():
                source = ("import pathlib,unittest\n"
                          "def trace(value):\n"
                          "    with (pathlib.Path(__file__).resolve().parent.parent/'trace').open('a') as out:\n"
                          "        out.write(value+'\\n')\n"
                          "def setUpModule(): trace('module+')\n"
                          "def tearDownModule(): trace('module-')\n")
                for cls, methods in sorted(classes.items()):
                    source += (f"class {cls}(unittest.TestCase):\n"
                               "    @classmethod\n"
                               "    def setUpClass(cls): trace('class+')\n"
                               "    @classmethod\n"
                               "    def tearDownClass(cls): trace('class-')\n")
                    for method in sorted(methods):
                        source += f"    def {method}(self): trace(self.id()+':'+str(id(self)))\n"
                (scripts / (module + ".py")).write_text(source)
            ordered = sorted(ids)
            shards = [{"id": f"s{i:02}", "selectors": []} for i in range(1, 15)]
            placement = {}
            for index, test_id in enumerate(ordered):
                owner = f"s{index % 14 + 1:02}"
                placement.setdefault(owner, []).append(test_id)
                shards[index % 14]["selectors"].append(
                    {"module": test_id.split(".")[0], "ids": [test_id]})
            subsets = {
                "fast": {"ids": list(EXPECTED_CORE)},
                "compat310": {"ids": list(EXPECTED_COMPAT)},
                "contracts-a": {"ids": [value for value in ordered
                                        if value.split(".")[0] == "test_planveyor_plan_bundle"]},
                "contracts-b": {"ids": [value for value in ordered
                                        if value.split(".")[0] in EXPECTED_CONTRACT_MODULES]},
            }
            data = {"version": 1, "baseline_head": "a" * 40, "weighting": {},
                    "zero_test_modules": [], "shards": shards, "local_profiles": {},
                    "subsets": subsets}
            manifest = scripts / "test_shards.json"
            manifest.write_text(json.dumps(data))
            for args in (("init", "--quiet"), ("add", "."),
                         ("-c", "user.name=CI fixture", "-c", "user.email=ci@example.invalid",
                          "commit", "--quiet", "-m", "synthetic CI fixture")):
                subprocess.run(["git", "-C", str(root), *args], check=True,
                               capture_output=True, timeout=30)
            yield {"root": root, "scripts": scripts, "manifest": manifest, "data": data,
                   "modules": set(module_classes), "ordered": ordered, "placement": placement,
                   "head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                                    text=True).strip()}

    @contextmanager
    def ci_cases(self, fixture):
        old_path, old_cwd = sys.path[:], Path.cwd()
        saved = {key: (key in sys.modules, sys.modules.get(key)) for key in fixture["modules"]}
        try:
            for key in saved:
                sys.modules.pop(key, None)
            shard.prepare_discovery(fixture["root"])
            loader = unittest.TestLoader()
            cases = list(shard.flatten(loader.discover(str(fixture["scripts"]))))
            self.assertEqual(loader.errors, [])
            self.assertEqual([case.id() for case in cases], fixture["ordered"])
            yield cases
        finally:
            sys.path[:] = old_path
            os.chdir(old_cwd)
            for key, (present, value) in saved.items():
                if present:
                    sys.modules[key] = value
                else:
                    sys.modules.pop(key, None)
            for key, (present, value) in saved.items():
                self.assertEqual(key in sys.modules, present)
                if present:
                    self.assertIs(sys.modules[key], value)

    def expected_ci_rows(self, profile):
        if profile == "fast":
            rows = [{"part": part, "python-version": "3.12", "subset": subset,
                     "meta": part == "contracts-b"} for part, subset in
                    (("core", "fast"), ("contracts-a", "contracts-a"), ("contracts-b", "contracts-b"))]
        else:
            rows = [{"part": f"s{i:02}", "python-version": "3.12", "shard": f"s{i:02}",
                     "meta": i == 1} for i in range(1, 15)]
        return rows + [{"part": "compat310", "python-version": "3.10",
                        "subset": "compat310", "meta": False}]

    def ci_args(self, fixture, profile="fast", part=None, label="worker"):
        if part is None:
            part = "compat310" if sys.version_info[:2] == (3, 10) else "core"
        row = next(row for row in self.expected_ci_rows(profile) if row["part"] == part)
        return argparse.Namespace(
            root=fixture["root"], manifest=fixture["manifest"], matrix=False, check=False,
            report=fixture["root"] / (label + ".json"), durations=None, subset=row.get("subset"),
            shard=row.get("shard"), local_profile=None, local_group=None, ci_summary=None,
            ci_profile=profile, ci_strict=True, ci_part=part, ci_python=row["python-version"],
            ci_event="push" if profile == "fast" else "schedule", ci_run_id="42", ci_run_attempt="1",
            ci_expected_sha=fixture["head"], ci_pr_head_sha=None, ci_needs_json=None)

    def ci_argv(self, args):
        values = ["--ci-profile", args.ci_profile, "--ci-event", args.ci_event,
                  "--ci-run-id", args.ci_run_id, "--ci-run-attempt", args.ci_run_attempt,
                  "--ci-expected-sha", args.ci_expected_sha]
        if args.ci_pr_head_sha is not None:
            values += ["--ci-pr-head-sha", args.ci_pr_head_sha]
        return [*values, "--ci-strict", "--ci-part", args.ci_part, "--ci-python", args.ci_python,
                "--subset" if args.subset is not None else "--shard",
                args.subset if args.subset is not None else args.shard,
                "--report", str(args.report)]

    def ci_cli(self, fixture, *args):
        return subprocess.run([sys.executable, "-B", str(RUNNER), "--root", str(fixture["root"]), *args],
                              text=True, capture_output=True, timeout=30,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def ci_execute(self, fixture, args, cases):
        data = fixture["data"]
        assignments = shard.partition(cases, data)
        shard.ci_composition(cases, data)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = shard.run_selected(args, data, hashlib.sha256(fixture["manifest"].read_bytes()).hexdigest(),
                                    cases, assignments)
        return rc, json.loads(args.report.read_text())

    def ci_corpus(self, fixture, cases, profile):
        args = self.ci_args(fixture, profile=profile, part="compat310")
        args.ci_strict = False
        args.ci_part = args.ci_python = args.subset = args.report = None
        args.ci_summary = fixture["root"] / "reports"
        args.ci_summary.mkdir()
        args.ci_needs_json = json.dumps({"shard-matrix": {"result": "success", "outputs": {}},
                                        "verify": {"result": "success", "outputs": {}}})
        manifest_hash = hashlib.sha256(fixture["manifest"].read_bytes()).hexdigest()
        paths = {}
        # Deliberately synthetic cross-axis records; current-axis producer parity is tested separately.
        for row in self.expected_ci_rows(profile):
            wanted = (set(fixture["data"]["subsets"][row["subset"]]["ids"]) if "subset" in row
                      else set(fixture["placement"][row["shard"]]))
            selected = [case.id() for case in cases if case.id() in wanted]
            version = row["python-version"]
            payload = {
                "status": "green", "head_before": fixture["head"], "head_after": fixture["head"],
                "manifest_sha256": manifest_hash, "python": version + ".0 (synthetic)",
                "selected_shards": [row["shard"]] if "shard" in row else [],
                "selected_subset": row.get("subset"), "planned_ids": selected,
                "started_ids": selected[:], "completed_ids": selected[:], "tests_run": len(selected),
                "skipped": [], "wall_seconds": 0.0, "durations_source":
                "unittest-native" if version == "3.12" else "wall-only",
                "durations": [] if version == "3.12" else None,
                "completion_exact": True, "result_successful": True, "failures": [], "errors": [],
                "ci_profile": profile, "ci_part": row["part"], "ci_event": args.ci_event,
                "ci_run_id": "42", "ci_run_attempt": "1", "ci_expected_sha": fixture["head"],
                "ci_pr_head_sha": None, "ci_expected_python": version,
                "ci_python": {"major": 3, "minor": int(version.split(".")[1])},
            }
            directory = args.ci_summary / ("planveyor-ci-42-1-" + row["part"])
            directory.mkdir()
            paths[row["part"]] = directory / "result.json"
            paths[row["part"]].write_text(json.dumps(payload))
        return args, paths

    def ci_aggregate(self, fixture, args, cases):
        with redirect_stdout(io.StringIO()) as output:
            result = shard.ci_summary(args, fixture["data"],
                                      hashlib.sha256(fixture["manifest"].read_bytes()).hexdigest(),
                                      cases, shard.partition(cases, fixture["data"]),
                                      shard.ci_composition(cases, fixture["data"]))
        self.assertEqual(result, 0)
        return json.loads(output.getvalue())

    def workflow(self):
        import yaml
        return yaml.safe_load((ROOT / ".github/workflows/checks.yml").read_text())

    def assert_workflow(self, workflow, matrices=None):
        events = workflow.get("on", workflow.get(True))
        self.assertEqual(set(events), {"push", "pull_request", "schedule", "workflow_dispatch"})
        self.assertEqual(events["push"], {"branches": ["main"]})
        self.assertEqual(events["schedule"], [{"cron": "17 2 * * *"}])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        concurrency = workflow["concurrency"]
        for token in ("fast", "full", "github.ref", "github.run_id", "github.run_attempt"):
            self.assertIn(token, concurrency["group"])
        self.assertEqual(concurrency["group"], "${{ (github.event_name == 'push' || github.event_name == 'pull_request') && format('{0}-fast-{1}', github.workflow, github.ref) || format('{0}-full-{1}-{2}', github.workflow, github.run_id, github.run_attempt) }}")
        self.assertEqual(concurrency["cancel-in-progress"], "${{ github.event_name == 'push' || github.event_name == 'pull_request' }}")
        for key, value in {
            "CI_EVENT": "${{ github.event_name }}", "CI_RUN_ID": "${{ github.run_id }}",
            "CI_RUN_ATTEMPT": "${{ github.run_attempt }}", "CI_EXPECTED_SHA": "${{ github.sha }}",
            "CI_PR_HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
            "PYTHONDONTWRITEBYTECODE": "1",
        }.items():
            self.assertEqual(workflow["env"][key], value)
        self.assertIn("'fast'", workflow["env"]["CI_PROFILE"])
        self.assertIn("'full'", workflow["env"]["CI_PROFILE"])
        jobs = workflow["jobs"]
        self.assertEqual(set(jobs), {"shard-matrix", "verify", "ci-summary"})
        self.assertEqual(jobs["ci-summary"]["needs"], ["shard-matrix", "verify"])
        self.assertEqual(jobs["ci-summary"]["if"], "always()")
        self.assertEqual(jobs["verify"]["needs"], "shard-matrix")
        self.assertIs(jobs["verify"]["strategy"]["fail-fast"], False)
        self.assertEqual(jobs["verify"]["strategy"]["matrix"], "${{ fromJSON(needs.shard-matrix.outputs.matrix) }}")
        meta_commands = {
            "Lint documentation and translation pairs": "bash scripts/run_doc_lint.sh --i18n-strict",
            "Lint changed plans": '"$PYBIN" -B scripts/plan_lint_changed.py --base "$base" --head HEAD',
            "Typecheck": "make typecheck", "Scan public contents": "make oss-release-scan",
        }
        for job_name, job in jobs.items():
            self.assertEqual(job.get("if"), "always()" if job_name == "ci-summary" else None)
            self.assertIs(job.get("continue-on-error", False), False)
            self.assertEqual(job["runs-on"], "macos-latest")
            self.assertEqual(job["timeout-minutes"], 105)
            steps = job["steps"]
            for step in steps:
                self.assertIn(step.get("if"), (None, "matrix.meta", "always()"))
                self.assertIs(step.get("continue-on-error", False), False)
            checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
            self.assertEqual(checkout["uses"], "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09")
            self.assertEqual(checkout["with"], {"fetch-depth": 0, "path": "My Planveyor", "ref": "${{ github.sha }}"})
            setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
            self.assertEqual(setup["uses"], "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1")
            names = [step.get("name") for step in steps]
            for prerequisite in ("Install shell tools", "Select build interpreter", "Install development dependencies"):
                self.assertIn(prerequisite, names)
            dependency = next(step for step in steps if step.get("name") == "Install development dependencies")
            self.assertEqual(dependency["run"].strip(), "make bootstrap-python")
            if job_name != "verify":
                first_import = next(i for i, step in enumerate(steps)
                                    if "scripts/run_test_shard.py" in step.get("run", ""))
                self.assertLess(names.index("Install development dependencies"), first_import)
                self.assertEqual(setup["with"]["python-version"], "3.12")
            else:
                self.assertEqual(setup["with"]["python-version"], "${{ matrix.python-version }}")
                self.assertEqual(setup["with"]["cache"], "pip")
                self.assertEqual(setup["with"]["cache-dependency-path"], "My Planveyor/requirements-dev.lock")
                for name, command in meta_commands.items():
                    matches = [step for step in steps if step.get("name") == name]
                    self.assertEqual(len(matches), 1)
                    self.assertEqual(matches[0].get("if"), "matrix.meta")
                    self.assertIn(command, matches[0]["run"])
                self.assertEqual(sum(step.get("if") == "matrix.meta" for step in steps), 4)
        prepare = jobs["shard-matrix"]["steps"]
        self.assertTrue(any('--check --ci-profile "$CI_PROFILE"' in step.get("run", "") for step in prepare))
        self.assertTrue(any('--matrix --ci-profile "$CI_PROFILE"' in step.get("run", "") for step in prepare))
        upload = next(step for step in jobs["verify"]["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["uses"], "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02")
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"], {
            "name": "planveyor-ci-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.part }}",
            "path": "${{ runner.temp }}/result.json", "if-no-files-found": "error", "overwrite": False})
        download = next(step for step in jobs["ci-summary"]["steps"] if step.get("uses", "").startswith("actions/download-artifact@"))
        self.assertEqual(download["uses"], "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093")
        self.assertEqual(download["with"], {
            "pattern": "planveyor-ci-${{ github.run_id }}-${{ github.run_attempt }}-*",
            "path": "${{ runner.temp }}/ci-reports", "merge-multiple": False})
        summary = next(step for step in jobs["ci-summary"]["steps"] if step.get("name") == "Validate actual CI reports")
        self.assertEqual(summary["env"], {"CI_NEEDS_JSON": "${{ toJSON(needs) }}"})
        self.assertIn('--ci-summary "$RUNNER_TEMP/ci-reports"', summary["run"])
        self.assertIn('--ci-needs-json "$CI_NEEDS_JSON"', summary["run"])
        worker = next(step for step in jobs["verify"]["steps"] if step.get("name") == "Test workflow shard")
        self.assertIn("--ci-strict", worker["run"])
        self.assertIn('--report "$RUNNER_TEMP/result.json"', worker["run"])
        for step in (worker, summary):
            for token in ('--ci-expected-sha "$CI_EXPECTED_SHA"', '--ci-run-id "$CI_RUN_ID"',
                          '--ci-run-attempt "$CI_RUN_ATTEMPT"', '--ci-event "$CI_EVENT"',
                          '--ci-pr-head-sha "$CI_PR_HEAD_SHA"'):
                self.assertIn(token, step["run"])
        if matrices is None:
            matrices = {profile: self.expected_ci_rows(profile) for profile in ("fast", "full")}
        for profile, rows in matrices.items():
            self.assertEqual(rows, self.expected_ci_rows(profile))
            self.assertEqual([row["part"] for row in rows if row["meta"]],
                             ["contracts-b" if profile == "fast" else "s01"])
        self.assertNotIn("paths-ignore", json.dumps(events))
        self.assertNotIn("paths:", json.dumps(events))

    def test_subset_rejects_invalid_shape_ids_and_name(self):
        malformed = [None, [], {"Bad": {"ids": [A]}}, {"compat310": []},
                     {"compat310": {}}, {"compat310": {"ids": [A], "extra": 1}}]
        malformed += [{"compat310": {"ids": ids}} for ids in
                      (None, "bad", [], [A, A], [1], ["alpha.test_a"],
                       ["test_alpha.AlphaTests.test_unknown"])]
        for index, subsets in enumerate(malformed):
            with self.subTest(subsets=subsets):
                data = copy.deepcopy(self.data)
                data["subsets"] = subsets
                self.write_manifest(data)
                report = self.root / f"invalid-{index}.json"
                result = self.cli("--subset", "compat310", "--report", str(report))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(report.exists())
                self.assertFalse(self.trace.exists())
        self.write_manifest()
        for mode in (("--subset", "absent"), ("--subset", "compat310", "--local-group", "g1"),
                     ("--subset", "compat310", "--shard", "s01"),
                     ("--subset", "compat310", "--local-profile", "3"),
                     ("--subset", "compat310", "--check"), ("--subset", "compat310", "--matrix")):
            with self.subTest(mode=mode):
                self.assertEqual(self.cli(*mode).returncode, 2)
        self.manifest.write_text(self.manifest.read_text().replace('"version": 1', '"version": 1, "version": 1'))
        self.assertEqual(self.cli("--subset", "compat310").returncode, 2)
        self.assertFalse(self.trace.exists())
        data = copy.deepcopy(self.data)
        data["subsets"]["other"] = {"ids": ["test_alpha.AlphaTests.test_unknown"]}
        self.write_manifest(data)
        self.assertEqual(self.cli("--check").returncode, 2)
        self.assertEqual(self.cli("--subset", "compat310").returncode, 2)
        self.assertFalse(self.trace.exists())

    def test_subset_requires_valid_whole_partition(self):
        missing = copy.deepcopy(self.data)
        missing["shards"].pop(1)
        repeated = copy.deepcopy(self.data)
        repeated["shards"][1]["selectors"][0]["ids"] = [A, B]
        unknown = copy.deepcopy(self.data)
        unknown["shards"][1]["selectors"] = [{"module": "test_alpha", "class": "Unknown"}]
        for data in (missing, repeated, unknown):
            with self.subTest(data=data):
                data["local_profiles"] = {}
                self.write_manifest(data)
                result = self.cli("--subset", "compat310", "--report", str(self.root / "bad.json"))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(self.trace.exists())
        self.write_manifest()
        alpha = self.scripts / "test_alpha.py"
        alpha.write_text(alpha.read_text() + "\ndef load_tests(loader, tests, pattern):\n"
                         "    return unittest.TestSuite([AlphaTests('test_a'), AlphaTests('test_a'), AlphaTests('test_b')])\n")
        self.assertIn("duplicate canonical IDs", self.cli("--subset", "compat310").stderr)
        (self.scripts / "test_beta.py").write_text("raise RuntimeError('synthetic loader error')\n")
        self.assertIn("canonical discovery errors", self.cli("--subset", "compat310").stderr)
        self.assertFalse(self.trace.exists())

    def test_subset_preserves_instances_order_and_hooks(self):
        observed = []
        original_run = unittest.TextTestRunner.run
        def capture(runner, suite):
            observed.extend(list(suite))
            return original_run(runner, suite)
        with self.discovery() as cases, mock.patch.object(unittest.TextTestRunner, "run", capture):
            self.assertEqual([case.id() for case in cases], [A, B, C])
            self.assertEqual(self.execute(self.args(), cases), 0)
            self.assertIs(observed[0], cases[0])
            self.assertIs(observed[1], cases[2])
            self.assertEqual(self.trace.read_text().splitlines(), [
                "alpha:module+", "alpha:class+", f"a:{id(cases[0])}", "alpha:class-", "alpha:module-",
                "beta:module+", "beta:class+", f"c:{id(cases[2])}", "beta:class-", "beta:module-",
            ])

    def test_subset_cli_report_and_events_share_identity(self):
        self.init_git()
        report = self.root / "cli.json"
        result = self.cli("--subset", "compat310", "--report", str(report))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(report.read_text())
        events = [json.loads(line) for line in report.with_name(report.name + ".events.jsonl").read_text().splitlines()]
        self.assertEqual(json.loads(result.stdout), payload)
        self.assertEqual(payload["planned_ids"], [A, C])
        self.assertEqual(payload["started_ids"], [A, C])
        self.assertEqual(payload["completed_ids"], [A, C])
        self.assertEqual(payload["selected_subset"], "compat310")
        self.assertEqual(payload["selected_shards"], [])
        self.assertEqual(payload["status"], "green")
        self.assertTrue(payload["completion_exact"])
        self.assertTrue(payload["result_successful"])
        self.assertEqual(payload["tests_run"], 2)
        self.assertEqual(payload["head_before"], payload["head_after"])
        self.assertEqual(payload["manifest_sha256"], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(events[0], {"event": "planned", "head": payload["head_before"],
                                    "manifest_sha256": payload["manifest_sha256"], "ids": [A, C],
                                    "selected_subset": "compat310", "selected_shards": []})
        self.assertEqual(events[1:], [{"event": kind, "id": test_id}
                                      for test_id in (A, C) for kind in ("started", "completed")])
        self.assertFalse(any(line.startswith("b:") for line in self.trace.read_text().splitlines()))

    def test_legacy_full_and_local_modes_without_subsets(self):
        del self.data["subsets"]
        self.write_manifest()
        self.init_git()
        self.assertEqual(self.cli("--check").returncode, 0)
        for label, mode in (("full", ("--shard", "s01")),
                            ("local", ("--local-profile", "3", "--local-group", "g1"))):
            report = self.root / f"{label}.json"
            result = self.cli(*mode, "--report", str(report))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(report.read_text())
            self.assertIsNone(payload["selected_subset"])
            self.assertEqual(payload["selected_shards"], ["s01"])
            self.assertEqual(payload["planned_ids"], [A])
        self.assertEqual(self.cli("--subset", "compat310").returncode, 2)
        self.assertEqual(self.cli("--matrix").returncode, 2)

    def test_matrix_and_workflow_selection_contract(self):
        data, _ = shard.load_manifest(ROOT / "scripts/test_shards.json", ROOT / "scripts")
        required_fast_ids = {
            'test_planveyor_init_capture.InitCaptureTests.test_in_scope_init_wrappers_promote_run_artifacts_by_sid',
            'test_planveyor_init_capture.InitCaptureTests.test_failed_init_without_sid_stays_under_pending',
            'test_planveyor_init_capture.InitCaptureTests.test_runner_selection_init_precedes_artifacts_and_consumes_captured_bytes_once',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_writes_fresh_success_receipt_and_compat_readback',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_rejects_bad_or_changed_preflight_identity_before_child',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_missing_wrapper_and_spawn_error_are_not_started',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_nonzero_and_timeout_are_non_green_receipts',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_keeps_non_green_child_and_green_outcome_independent',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_functional_safety_witness',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_recovery_tuple_is_one_shot_and_exactly_once',
            'test_planveyor_init_capture.InitCaptureTests.test_role_run_carrier_is_isolated_from_manager_architect_paths',
            'test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_clean_first_source_pins_and_same_source_is_idempotent',
            'test_contract_authority_shell.ContractAuthorityShellIntegrationTests.test_runtime_closure_and_runner_policy_drift_fail_before_effect_sentinel',
            'test_sibling_runbook.NativeSiblingCommitPolicyTests.test_tui_cmd_architect_and_direct_policy_sequence_ignores_ambient',
            'test_sibling_runbook.NativeSiblingCommitPolicyTests.test_tui_markerless_legacy_refuses_before_session_effects',
            'test_planveyor_bare_entrypoints.PlanveyorFacadeDashboardTests.test_help_and_dashboards_finish_without_per_row_authority_revalidation',
        }

        def assert_fast_composition(manifest):
            fast_ids = manifest.get("subsets", {}).get("fast", {}).get("ids", [])
            missing = required_fast_ids - set(fast_ids)
            self.assertFalse(missing, f"missing fast safety floor IDs: {sorted(missing)}")
            self.assertNotIn(
                "test_planveyor_init_capture.InitCaptureTests.test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe", fast_ids,
                "original timing witness must remain full-only")

        original_data = copy.deepcopy(data)
        assert_fast_composition(data)
        for required_id in sorted(required_fast_ids):
            with self.subTest(missing_fast_id=required_id):
                missing = copy.deepcopy(data)
                missing["subsets"]["fast"]["ids"].remove(required_id)
                with self.assertRaisesRegex(AssertionError, "missing fast safety floor IDs"):
                    assert_fast_composition(missing)
        self.assertEqual(data, original_data)
        result = subprocess.run([sys.executable, "-B", str(RUNNER), "--matrix"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = json.loads(result.stdout)["include"]
        self.assertEqual(rows, [{"python-version": "3.12", "shard": f"s{i:02}", "meta": i == 1}
                                for i in range(1, 15)] +
                         [{"python-version": "3.10", "subset": "compat310", "meta": False}])
        self.assertEqual(len({json.dumps(row, sort_keys=True) for row in rows}), 15)
        self.assertTrue(all(("shard" in row) != ("subset" in row) for row in rows))
        import yaml
        workflow = yaml.safe_load((ROOT / ".github/workflows/checks.yml").read_text())
        step = next(step for step in workflow["jobs"]["verify"]["steps"] if step.get("name") == "Test workflow shard")
        self.assertIn("--ci-strict", step["run"])
        self.assertIn('--report "$RUNNER_TEMP/result.json"', step["run"])
        self.assert_workflow(workflow, {profile: shard.ci_rows(profile) for profile in ("fast", "full")})
        schema = json.loads((ROOT / "scripts/test_shards.schema.json").read_text())["properties"]["subsets"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["propertyNames"]["pattern"], "^[a-z][a-z0-9_-]*$")
        subset = schema["additionalProperties"]
        self.assertEqual(subset["required"], ["ids"])
        self.assertFalse(subset["additionalProperties"])
        ids = subset["properties"]["ids"]
        self.assertEqual((ids["type"], ids["minItems"], ids["uniqueItems"]), ("array", 1, True))
        self.assertEqual(ids["items"]["type"], "string")
        self.assertTrue(all(re.fullmatch(ids["items"]["pattern"], value) for value in data["subsets"]["compat310"]["ids"]))
        owners = [row["id"] for row in data["shards"] for selector in row["selectors"]
                  if selector["module"] == "test_run_test_shard"]
        self.assertEqual(owners, ["s03"])

    def test_matrix_is_structural_and_requires_compat310(self):
        (self.scripts / "test_alpha.py").write_text("raise RuntimeError('matrix must not import')\n")
        self.assertEqual(self.cli("--matrix").returncode, 0)
        del self.data["subsets"]["compat310"]
        self.write_manifest()
        self.assertEqual(self.cli("--matrix").returncode, 2)
        self.data["subsets"] = {"compat310": {"ids": []}}
        self.write_manifest()
        self.assertEqual(self.cli("--matrix").returncode, 2)

    def odd_case(self, action):
        def run(case, result):
            action(case, result)
        return type("AlphaTests", (unittest.TestCase,), {
            "__module__": "test_alpha", "test_a": lambda case: None, "run": run,
        })("test_a")

    def test_incomplete_started_or_completed_is_red(self):
        def accounting(case, result, starts, stops):
            for _ in range(starts):
                result.startTest(case)
            result.addSuccess(case)
            for _ in range(stops):
                result.stopTest(case)
        data = copy.deepcopy(self.data)
        data["subsets"]["compat310"]["ids"] = [A]
        for index, (starts, stops) in enumerate(((0, 1), (1, 0), (2, 1), (1, 2))):
            with self.subTest(starts=starts, stops=stops):
                args = self.args(f"incomplete-{index}")
                case = self.odd_case(lambda case, result: accounting(case, result, starts, stops))
                self.assertEqual(self.execute(args, [case], data), 1)
                payload = json.loads(args.report.read_text())
                self.assertEqual(payload["status"], "red")
                self.assertFalse(payload["completion_exact"])
                self.assertTrue(payload["result_successful"])
        def extra(case, result):
            accounting(case, result, 1, 1)
            result.started_ids.append(B)
            result.completed_ids.append(B)
        args = self.args("extra-accounting")
        self.assertEqual(self.execute(args, [self.odd_case(extra)], data), 1)
        self.assertFalse(json.loads(args.report.read_text())["completion_exact"])
        self.assertFalse(shard.completed_exactly([A], [A, B], [A]))
        self.assertTrue(shard.completed_exactly([A, C], [C, A], [A, C]))

    def test_interruption_retains_non_green_partial_report(self):
        self.init_git()
        (self.scripts / "test_alpha.py").write_text(
            "import unittest\nclass AlphaTests(unittest.TestCase):\n"
            "    def test_a(self): pass\n    def test_b(self): pass\n"
            "    def run(self, result):\n        result.startTest(self)\n        raise KeyboardInterrupt()\n")
        report = self.root / "interrupted.json"
        result = self.cli("--subset", "compat310", "--report", str(report))
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["status"], "interrupted")
        self.assertEqual(payload["interruption"], "KeyboardInterrupt")
        self.assertEqual(payload["started_ids"], [A])
        self.assertEqual(payload["completed_ids"], [])
        self.assertFalse(payload["completion_exact"])
        self.assertIsNone(payload["result_successful"])

    def test_existing_head_boundary_drift_is_red(self):
        with self.discovery() as cases:
            args = self.args()
            self.assertEqual(self.execute(args, cases, heads=["a" * 40, "c" * 40]), 1)
        payload = json.loads(args.report.read_text())
        self.assertEqual(payload["status"], "red")
        self.assertTrue(payload["completion_exact"])
        self.assertTrue(payload["result_successful"])
        self.assertNotEqual(payload["head_before"], payload["head_after"])



    def test_ci_profiles_have_exact_parts_and_composition(self):
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            assignments = shard.partition(cases, fixture["data"])
            composition = shard.ci_composition(cases, fixture["data"])
            for profile in ("fast", "full"):
                self.assertEqual(shard.ci_rows(profile), self.expected_ci_rows(profile))
                cli = self.ci_cli(fixture, "--matrix", "--ci-profile", profile)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                self.assertEqual(json.loads(cli.stdout)["include"], self.expected_ci_rows(profile))
            self.assertEqual(set(composition), {"fast", "compat310", "contracts-a", "contracts-b"})
            self.assertEqual(set(assignments), {f"s{i:02}" for i in range(1, 15)})
            with self.assertRaises(shard.PartitionError):
                shard.ci_rows("other")
            broken = copy.deepcopy(fixture["data"])
            broken["shards"][1]["selectors"] += broken["shards"][0]["selectors"]
            fixture["manifest"].write_text(json.dumps(broken))
            rejected = self.ci_cli(fixture, "--matrix", "--ci-profile", "fast")
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("coverage mismatch", rejected.stderr)
            self.assertFalse((fixture["root"] / "trace").exists())

    def test_ci_membership_comes_from_fixed_module_policy(self):
        self.assertEqual(tuple(shard.CI_CONTRACT_MODULES), EXPECTED_CONTRACT_MODULES)
        for module, subset in (("test_planveyor_plan_bundle", "contracts-a"),
                               (EXPECTED_CONTRACT_MODULES[0], "contracts-b")):
            with self.subTest(module=module), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                added = type("AddedTests", (unittest.TestCase,), {
                    "__module__": module, "test_added": lambda case: None})("test_added")
                all_cases = [*cases, added]
                with self.assertRaises(shard.PartitionError):
                    shard.ci_composition(all_cases, fixture["data"])
                fixture["data"]["subsets"][subset]["ids"].append(added.id())
                self.assertIn(added.id(), shard.ci_composition(all_cases, fixture["data"])[subset])
                missing = [case for case in cases if case.__class__.__module__ != module]
                with self.assertRaises(shard.PartitionError):
                    shard.ci_composition(missing, fixture["data"])
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            for changed in ("foreign", "duplicate", "overlap"):
                with self.subTest(changed=changed):
                    data = copy.deepcopy(fixture["data"])
                    if changed == "foreign":
                        data["subsets"]["contracts-b"]["ids"].append("test_unclassified.OtherTests.test_full_only")
                    elif changed == "duplicate":
                        data["subsets"]["contracts-a"]["ids"] *= 2
                    else:
                        data["subsets"]["contracts-b"]["ids"].extend(data["subsets"]["contracts-a"]["ids"])
                    with self.assertRaises(shard.PartitionError):
                        shard.ci_composition(cases, data)
            # A mutated source policy must still reject overlap rather than silently accepting it.
            data = copy.deepcopy(fixture["data"])
            data["subsets"]["contracts-b"]["ids"] += data["subsets"]["contracts-a"]["ids"]
            with mock.patch.object(shard, "CI_CONTRACT_MODULES",
                                   (*EXPECTED_CONTRACT_MODULES, "test_planveyor_plan_bundle")):
                with self.assertRaisesRegex(shard.PartitionError, "overlap"):
                    shard.ci_composition(cases, data)
            module = "test_planveyor_plan_bundle"
            changed_core = (fixture["data"]["subsets"]["contracts-a"]["ids"][0], *EXPECTED_CORE[1:])
            data = copy.deepcopy(fixture["data"])
            data["subsets"]["fast"]["ids"] = list(changed_core)
            with mock.patch.object(shard, "CI_CORE_IDS", changed_core):
                with self.assertRaisesRegex(shard.PartitionError, "overlap"):
                    shard.ci_composition(cases, data)

    def test_ci_core_and_compat_floors_reject_nonempty_deletions(self):
        self.assertEqual(set(shard.CI_CORE_IDS), set(EXPECTED_CORE))
        self.assertEqual(tuple(shard.CI_COMPAT_IDS), EXPECTED_COMPAT)
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            for subset, removed in (("fast", EXPECTED_CORE[0]), ("compat310", EXPECTED_COMPAT[-1])):
                with self.subTest(subset=subset):
                    data = copy.deepcopy(fixture["data"])
                    data["subsets"][subset]["ids"].remove(removed)
                    self.assertTrue(data["subsets"][subset]["ids"])
                    shard.validate_subsets(cases, data)  # Generic known/nonempty validation is insufficient.
                    with self.assertRaisesRegex(shard.PartitionError, "composition mismatch"):
                        shard.ci_composition(cases, data)
            data = copy.deepcopy(fixture["data"])
            data["subsets"]["compat310"]["ids"].reverse()
            with self.assertRaisesRegex(shard.PartitionError, "order"):
                shard.ci_composition(cases, data)
            data["subsets"]["compat310"]["ids"] = list(EXPECTED_COMPAT[:-1]) + ["test_unknown.X.test_y"]
            with self.assertRaises(shard.PartitionError):
                shard.ci_composition(cases, data)

    def test_ci_worker_context_fails_before_bodies(self):
        with self.ci_fixture() as fixture:
            args = self.ci_args(fixture)
            base = self.ci_argv(args)
            variants = [
                ["--subset", args.subset, "--ci-profile", "fast"],
                ["--subset", args.subset, "--ci-strict"],
                ["--matrix", "--ci-profile", "fast", "--ci-run-id", "42"],
                ["--check", "--ci-profile", "fast", "--ci-strict"],
                ["--local-profile", "3", "--local-group", "g1", "--ci-profile", "fast", "--ci-strict"],
                ["--ci-summary", str(fixture["root"]), "--ci-profile", "fast", "--ci-strict"],
                ["--subset", args.subset, "--ci-needs-json", "{}"],
            ]
            for key in ("--ci-profile", "--ci-part", "--ci-python", "--ci-run-id",
                        "--ci-run-attempt", "--ci-expected-sha", "--ci-event"):
                i = base.index(key)
                variants.append(base[:i] + base[i + 2:])
            for key, value in (
                ("--ci-part", "s02"), ("--ci-python", "3.10" if args.ci_python == "3.12" else "3.12"),
                ("--ci-run-id", "0"), ("--ci-run-id", "True"), ("--ci-run-attempt", "1.0"),
                ("--ci-expected-sha", "a" * 40), ("--ci-expected-sha", "A" * 40),
                ("--ci-event", "schedule"), ("--ci-event", "pull_request"),
            ):
                changed = base[:]
                changed[changed.index(key) + 1] = value
                variants.append(changed)
            variants.append(base + ["--ci-pr-head-sha", "b" * 40])
            variants.append([item for item in base if item != "--ci-strict"])
            for variant in variants:
                with self.subTest(argv=variant):
                    result = self.ci_cli(fixture, *variant)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertFalse(args.report.exists())
                    self.assertFalse((fixture["root"] / "trace").exists())

    def test_ci_worker_report_uses_actual_cases_and_context(self):
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            args = self.ci_args(fixture)
            wanted = set(EXPECTED_COMPAT if args.ci_part == "compat310" else EXPECTED_CORE)
            selected = [case for case in cases if case.id() in wanted]
            observed = []
            original = unittest.TextTestRunner.run
            def capture(runner, suite):
                observed.extend(list(suite))
                return original(runner, suite)
            with mock.patch.object(unittest.TextTestRunner, "run", capture):
                rc, payload = self.ci_execute(fixture, args, cases)
            self.assertEqual(rc, 0, payload)
            self.assertEqual(payload["ci_python"], {"major": sys.version_info.major, "minor": sys.version_info.minor})
            for key in ("planned_ids", "started_ids", "completed_ids"):
                self.assertEqual(payload[key], [case.id() for case in selected])
            for actual, expected in zip(observed, selected):
                self.assertIs(actual, expected)
            self.assertEqual(len(observed), len(selected))
            trace = (fixture["root"] / "trace").read_text()
            self.assertIn("module+", trace)
            self.assertIn("class+", trace)
            self.assertIn("class-", trace)
            self.assertIn("module-", trace)
            events = [json.loads(line) for line in args.report.with_name(args.report.name + ".events.jsonl").read_text().splitlines()]
            self.assertEqual(events[0]["ids"], payload["planned_ids"])
            self.assertEqual(events[1:], [{"event": kind, "id": value}
                                         for value in payload["planned_ids"] for kind in ("started", "completed")])
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            args = self.ci_args(fixture)
            args.ci_event, args.ci_pr_head_sha = "pull_request", "b" * 40
            rc, payload = self.ci_execute(fixture, args, cases)
            self.assertEqual(rc, 0, payload)
            self.assertEqual(payload["head_before"], fixture["head"])
            self.assertEqual(payload["ci_pr_head_sha"], "b" * 40)
        for fault in ("extra-start", "missing-stop", "manifest", "head"):
            with self.subTest(fault=fault), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                args = self.ci_args(fixture)
                wanted = set(EXPECTED_COMPAT if args.ci_part == "compat310" else EXPECTED_CORE)
                case = next(case for case in cases if case.id() in wanted)
                original_run = case.run
                def faulty(result):
                    if fault in ("extra-start", "missing-stop"):
                        result.startTest(case)
                        result.addSuccess(case)
                        if fault == "extra-start":
                            result.startTest(case)
                            result.stopTest(case)
                        return
                    original_run(result)
                    if fault == "manifest":
                        with fixture["manifest"].open("a") as out:
                            out.write(" ")
                    else:
                        subprocess.run(["git", "-C", str(fixture["root"]), "-c", "user.name=CI fixture",
                                        "-c", "user.email=ci@example.invalid", "commit", "--allow-empty",
                                        "--quiet", "-m", "synthetic body drift"], check=True, timeout=30)
                with mock.patch.object(case, "run", faulty):
                    rc, payload = self.ci_execute(fixture, args, cases)
                self.assertEqual(rc, 1, payload)
                self.assertEqual(payload["status"], "red")

    def test_ci_worker_skips_fail_closed(self):
        for kind in ("method", "class", "module"):
            with self.subTest(kind=kind), self.ci_fixture() as fixture:
                args = self.ci_args(fixture)
                module, cls, method = (EXPECTED_COMPAT[0] if args.ci_part == "compat310" else EXPECTED_CORE[0]).split(".")
                path = fixture["scripts"] / (module + ".py")
                source = path.read_text()
                if kind == "method":
                    source = source.replace("    def " + method, "    @unittest.skip('synthetic method skip')\n    def " + method)
                elif kind == "class":
                    source = source.replace("class " + cls + "(", "@unittest.skip('synthetic class skip')\nclass " + cls + "(")
                else:
                    source += "\ndef setUpModule(): raise unittest.SkipTest('synthetic module skip')\n"
                path.write_text(source)
                result = self.ci_cli(fixture, *self.ci_argv(args))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = json.loads(args.report.read_text())
                self.assertEqual(payload["status"], "red")
                self.assertTrue(payload["skipped"])
        # Opt-in strictness must not silently change the legacy successful-skip contract.
        self.init_git()
        path = self.scripts / "test_alpha.py"
        path.write_text(path.read_text().replace("    def test_a", "    @unittest.skip('legacy skip')\n    def test_a"))
        report = self.root / "legacy-skip.json"
        result = self.cli("--subset", "compat310", "--report", str(report))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(report.read_text())["skipped"])

    def test_ci_summary_accepts_fast_and_full_report_fixtures(self):
        for profile in ("fast", "full"):
            with self.subTest(profile=profile), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                args, paths = self.ci_corpus(fixture, cases, profile)
                actual = self.ci_args(fixture, profile=profile,
                                      part="compat310" if sys.version_info[:2] == (3, 10) else
                                      ("core" if profile == "fast" else "s01"))
                rc, payload = self.ci_execute(fixture, actual, cases)
                self.assertEqual(rc, 0, payload)
                paths[actual.ci_part].write_bytes(actual.report.read_bytes())
                summary = self.ci_aggregate(fixture, args, cases)
                self.assertEqual(summary["parts"], [row["part"] for row in self.expected_ci_rows(profile)])
                self.assertEqual(summary["ci_expected_sha"], fixture["head"])
                self.assertEqual(summary["status"], "green")

    def test_ci_summary_rejects_missing_stale_and_ambiguous_reports(self):
        for fault in ("missing-part", "missing-file", "extra-directory", "extra-file", "extra-member",
                      "stale-attempt", "malformed", "duplicate-key", "absent-context", "integer-run",
                      "boolean-python", "unknown-fields", "symlink-report"):
            with self.subTest(fault=fault), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                args, paths = self.ci_corpus(fixture, cases, "fast")
                path = paths["core"]
                payload = json.loads(path.read_text())
                if fault == "missing-part":
                    path.unlink()
                    path.parent.rmdir()
                elif fault == "missing-file":
                    path.unlink()
                elif fault == "extra-directory":
                    (args.ci_summary / "planveyor-ci-42-1-core-copy").mkdir()
                elif fault == "extra-file":
                    (args.ci_summary / "other.json").write_text("{}")
                elif fault == "extra-member":
                    path.with_name("extra.json").write_text("{}")
                elif fault == "stale-attempt":
                    path.parent.rename(path.parent.with_name("planveyor-ci-42-2-core"))
                elif fault == "malformed":
                    path.write_text("{")
                elif fault == "duplicate-key":
                    path.write_text(path.read_text().replace('"ci_run_id": "42"', '"ci_run_id": "42", "ci_run_id": "42"'))
                elif fault == "symlink-report":
                    saved = fixture["root"] / "saved.json"
                    path.rename(saved)
                    path.symlink_to(saved)
                else:
                    if fault == "absent-context":
                        del payload["ci_expected_sha"]
                    elif fault == "integer-run":
                        payload["ci_run_id"] = 42
                    elif fault == "boolean-python":
                        payload["ci_python"]["major"] = True
                    else:
                        payload["extra"] = "not part of the report contract"
                    path.write_text(json.dumps(payload))
                with self.assertRaises((shard.PartitionError, json.JSONDecodeError)):
                    self.ci_aggregate(fixture, args, cases)

    def test_ci_summary_rejects_green_labels_with_wrong_execution(self):
        mutations = [
            ("status", "red"), ("status", "interrupted"), ("ci_part", "s01"),
            ("ci_run_id", "43"), ("ci_run_attempt", "2"), ("ci_profile", "fast"),
            ("ci_event", "workflow_dispatch"), ("ci_pr_head_sha", "b" * 40),
            ("ci_expected_python", "3.10"), ("ci_python", {"major": 3, "minor": 10}),
            ("python", "3.10.0 synthetic"), ("selected_shards", ["s01"]),
            ("selected_subset", "fast"), ("manifest_sha256", "f" * 64),
            ("durations_source", "wall-only"), ("durations", None),
            ("durations", [{"test": "x", "seconds": -1}]),
            ("durations", [{"test": "x", "seconds": float("inf")}]),
            ("completion_exact", False), ("result_successful", False),
            ("skipped", [{"id": "x", "reason": "skip"}]), ("errors", ["x"]), ("failures", ["x"]),
            ("tests_run", True), ("head_before", "b" * 40),
            ("equal-wrong-heads", None), ("wrong-s01-ids", None), ("missing-ids", None),
            ("duplicate-ids", None), ("reordered-ids", None), ("unknown-ids", None),
        ]
        for key, value in mutations:
            with self.subTest(field=key), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                args, paths = self.ci_corpus(fixture, cases, "full")
                path = paths["s02"]
                payload = json.loads(path.read_text())
                if key == "equal-wrong-heads":
                    payload["head_before"] = payload["head_after"] = "b" * 40
                elif key.endswith("-ids"):
                    ids = payload["planned_ids"][:]
                    if key == "wrong-s01-ids":
                        ids = json.loads(paths["s01"].read_text())["planned_ids"]
                    elif key == "missing-ids":
                        ids.pop()
                    elif key == "duplicate-ids":
                        ids.append(ids[0])
                    elif key == "reordered-ids":
                        ids.reverse()
                    else:
                        ids[0] = "test_unknown.X.test_y"
                    for field in ("planned_ids", "started_ids", "completed_ids"):
                        payload[field] = ids[:]
                    payload["tests_run"] = len(ids)
                else:
                    payload[key] = value
                path.write_text(json.dumps(payload))
                with self.assertRaises(shard.PartitionError):
                    self.ci_aggregate(fixture, args, cases)
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            args, _ = self.ci_corpus(fixture, cases, "fast")
            args.ci_expected_sha = "b" * 40
            with self.assertRaisesRegex(shard.PartitionError, "checkout"):
                self.ci_aggregate(fixture, args, cases)

    def test_ci_summary_needs_cannot_hide_authoritative_red(self):
        variants = []
        for job in ("shard-matrix", "verify"):
            for result in ("failure", "cancelled", "skipped", "unknown", True):
                value = {"shard-matrix": {"result": "success"}, "verify": {"result": "success"}}
                value[job]["result"] = result
                variants.append(json.dumps(value))
            value = {"shard-matrix": {"result": "success"}, "verify": {"result": "success"}}
            del value[job]
            variants.append(json.dumps(value))
        variants += ['{"shard-matrix":{"result":"success"},"verify":{"result":"success"},"extra":{"result":"success"}}',
                     '{"shard-matrix":{"result":"success"},"verify":{"result":"success"},"verify":{"result":"success"}}']
        for needs in variants:
            with self.subTest(needs=needs), self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
                args, _ = self.ci_corpus(fixture, cases, "fast")
                args.ci_needs_json = needs
                with self.assertRaises(shard.PartitionError):
                    self.ci_aggregate(fixture, args, cases)
        with self.ci_fixture() as fixture, self.ci_cases(fixture) as cases:
            args, paths = self.ci_corpus(fixture, cases, "fast")
            payload = json.loads(paths["contracts-b"].read_text())
            payload["status"] = "red"
            paths["contracts-b"].write_text(json.dumps(payload))
            with self.assertRaises(shard.PartitionError):
                self.ci_aggregate(fixture, args, cases)

    def test_ci_workflow_contract_rejects_disabling_mutations(self):
        workflow = self.workflow()
        self.assert_workflow(workflow, {profile: shard.ci_rows(profile) for profile in ("fast", "full")})
        variants = []
        for name in ("Lint documentation and translation pairs", "Lint changed plans", "Typecheck", "Scan public contents"):
            changed = copy.deepcopy(workflow)
            changed["jobs"]["verify"]["steps"] = [step for step in changed["jobs"]["verify"]["steps"] if step.get("name") != name]
            variants.append(changed)
            changed = copy.deepcopy(workflow)
            next(step for step in changed["jobs"]["verify"]["steps"] if step.get("name") == name)["run"] = "echo disabled"
            variants.append(changed)
        for job_name, job in workflow["jobs"].items():
            for field in ("if", "continue-on-error"):
                changed = copy.deepcopy(workflow)
                changed["jobs"][job_name][field] = False if field == "if" else True
                variants.append(changed)
            for index, _ in enumerate(job["steps"]):
                for field in ("if", "continue-on-error"):
                    changed = copy.deepcopy(workflow)
                    changed["jobs"][job_name]["steps"][index][field] = False if field == "if" else True
                    variants.append(changed)
        changed = copy.deepcopy(workflow)
        del changed["jobs"]["ci-summary"]
        variants.append(changed)
        for need in ("shard-matrix", "verify"):
            changed = copy.deepcopy(workflow)
            changed["jobs"]["ci-summary"]["needs"].remove(need)
            variants.append(changed)
        changed = copy.deepcopy(workflow)
        changed["env"]["CI_EXPECTED_SHA"] = "${{ github.event.pull_request.head.sha }}"
        variants.append(changed)
        changed = copy.deepcopy(workflow)
        changed["jobs"]["verify"]["steps"] = [step for step in changed["jobs"]["verify"]["steps"]
                                               if not step.get("uses", "").startswith("actions/upload-artifact@")]
        variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(mutation=index), self.assertRaises((AssertionError, KeyError, StopIteration)):
                self.assert_workflow(changed)
        for profile in ("fast", "full"):
            original = shard.ci_rows(profile)
            for variant in ("missing", "wrong", "duplicate"):
                rows = copy.deepcopy(original)
                for row in rows:
                    row["meta"] = False
                if variant != "missing":
                    rows[-1]["meta"] = True
                if variant == "duplicate":
                    rows[0]["meta"] = True
                with self.subTest(profile=profile, variant=variant), self.assertRaises(AssertionError):
                    self.assert_workflow(workflow, {profile: rows})

    def test_ci_workflow_event_bases_and_command_parity(self):
        workflow = self.workflow()
        jobs = workflow["jobs"]
        worker = next(step for step in jobs["verify"]["steps"] if step.get("name") == "Test workflow shard")
        summary = next(step for step in jobs["ci-summary"]["steps"] if step.get("name") == "Validate actual CI reports")
        fake = self.root / "fake python"
        fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        fake.chmod(0o700)
        for event, profile in (("push", "fast"), ("pull_request", "fast"),
                               ("schedule", "full"), ("workflow_dispatch", "full")):
            common = ["--ci-profile", profile, "--ci-event", event, "--ci-run-id", "42",
                      "--ci-run-attempt", "1", "--ci-expected-sha", "a" * 40]
            if event == "pull_request":
                common += ["--ci-pr-head-sha", "b" * 40]
            env = {**os.environ, "PYBIN": str(fake), "RUNNER_TEMP": str(self.root),
                   "CI_PROFILE": profile, "CI_EVENT": event, "CI_RUN_ID": "42",
                   "CI_RUN_ATTEMPT": "1", "CI_EXPECTED_SHA": "a" * 40,
                   "CI_PR_HEAD_SHA": "b" * 40, "CI_NEEDS_JSON": "{}"}
            for row in self.expected_ci_rows(profile):
                row_env = {**env, "CI_PART": row["part"], "CI_PYTHON": row["python-version"],
                           "CI_SHARD": row.get("shard", ""), "CI_SUBSET": row.get("subset", "")}
                result = subprocess.run(["bash", "-eu", "-c", worker["run"]], env=row_env,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                key = "subset" if "subset" in row else "shard"
                self.assertEqual(result.stdout.splitlines(), [
                    "-B", "scripts/run_test_shard.py", "--" + key, row[key], "--ci-strict",
                    "--ci-part", row["part"], "--ci-python", row["python-version"], *common,
                    "--report", str(self.root / "result.json")])
            result = subprocess.run(["bash", "-eu", "-c", summary["run"]], env=env,
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["-B", "scripts/run_test_shard.py",
                "--ci-summary", str(self.root / "ci-reports"), *common, "--ci-needs-json", "{}"])
        base_step = next(step for step in jobs["verify"]["steps"] if step.get("name") == "Lint changed plans")
        with self.ci_fixture() as fixture:
            first = fixture["head"]
            subprocess.run(["git", "-C", str(fixture["root"]), "update-ref", "refs/remotes/origin/main", first], check=True, timeout=30)
            subprocess.run(["git", "-C", str(fixture["root"]), "-c", "user.name=CI fixture", "-c",
                            "user.email=ci@example.invalid", "commit", "--allow-empty", "--quiet",
                            "-m", "second synthetic commit"], check=True, timeout=30)
            for event, before, branch, green in (
                ("pull_request", "", "main", True), ("pull_request", "", "missing", False),
                ("push", first, "", True), ("push", "0" * 40, "", True),
                ("push", "", "", True), ("push", "unresolvable", "", True),
                ("schedule", "", "", True), ("workflow_dispatch", "", "", True),
            ):
                result = subprocess.run(["bash", "-eu", "-c", base_step["run"]], cwd=fixture["root"],
                    env={**os.environ, "PYBIN": str(fake), "EVENT_NAME": event,
                         "BASE_BRANCH": branch, "BEFORE_COMMIT": before}, capture_output=True,
                    text=True, timeout=30)
                self.assertEqual(result.returncode == 0, green, result.stdout + result.stderr)
                if green:
                    self.assertEqual(result.stdout.splitlines()[-6:],
                                     ["-B", "scripts/plan_lint_changed.py", "--base", first, "--head", "HEAD"])
                    self.assertIn("event=" + event, result.stdout)
        with self.ci_fixture() as initial:
            first = initial["head"]
            for event in ("schedule", "workflow_dispatch"):
                result = subprocess.run(["bash", "-eu", "-c", base_step["run"]], cwd=initial["root"],
                    env={**os.environ, "PYBIN": str(fake), "EVENT_NAME": event,
                         "BASE_BRANCH": "", "BEFORE_COMMIT": ""}, capture_output=True,
                    text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines()[-6:],
                                 ["-B", "scripts/plan_lint_changed.py", "--base", first, "--head", "HEAD"])
        for path in ("docs/tools/verify_suite.md", "docs/tools/verify_suite.ru.md"):
            text = (ROOT / path).read_text()
            for token in ("--ci-profile", "--ci-strict", "--ci-summary", "--ci-needs-json",
                          "contracts-a", "contracts-b", "ci-summary", "workflow_dispatch",
                          "compat310", "github.sha"):
                self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()

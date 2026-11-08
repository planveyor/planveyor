#!/usr/bin/env python3
"""Run an exact manifest partition of canonical unittest discovery.

Bare --matrix reads files and JSON only; CI profiles, --check and execution
import the canonical suite. This script creates no environments or parallel workers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest


class PartitionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PartitionError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def keys(value, required, optional=()):
    require(isinstance(value, dict), "expected JSON object")
    require(set(required) <= set(value), f"missing fields: {set(required) - set(value)}")
    require(set(value) <= set(required) | set(optional), f"unknown fields: {set(value) - set(required) - set(optional)}")


def name(value, pattern, label):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
            f"invalid {label}: {value!r}")


def load_manifest(path, scripts):
    raw = path.read_bytes()
    data = json.loads(raw, object_pairs_hook=unique_object)
    keys(data, ("version", "baseline_head", "weighting", "zero_test_modules", "shards", "local_profiles"), ("$schema", "subsets"))
    require(type(data["version"]) is int and data["version"] == 1, "unsupported manifest version")
    name(data["baseline_head"], r"[0-9a-f]{40}", "baseline HEAD")
    require(isinstance(data["weighting"], dict), "weighting must be an object")
    files = {path.stem for path in scripts.glob("test_*.py") if path.is_file()}
    require(files, "no canonical test files")
    zero = data["zero_test_modules"]
    require(isinstance(zero, list) and all(isinstance(item, str) for item in zero), "zero_test_modules must be a string list")
    require(len(set(zero)) == len(zero) and set(zero) <= files, "duplicate or unknown zero-test module")
    shards = data["shards"]
    require(isinstance(shards, list) and shards, "empty shard list")
    shard_ids = []
    mentions = Counter()
    for shard in shards:
        keys(shard, ("id", "selectors"), ("historical_unsplit_seconds", "notes"))
        name(shard["id"], r"[a-z][a-z0-9_-]*", "shard ID")
        shard_ids.append(shard["id"])
        selectors = shard["selectors"]
        require(isinstance(selectors, list) and selectors, f"empty shard: {shard['id']}")
        for selector in selectors:
            keys(selector, ("module",), ("class", "ids"))
            module = selector["module"]
            name(module, r"test_[A-Za-z0-9_]+", "module")
            require(module in files, f"unknown test file: {module}.py")
            mentions[module] += 1
            require(not ("class" in selector and "ids" in selector), "class and ids are mutually exclusive")
            if "class" in selector:
                name(selector["class"], r"[A-Za-z_][A-Za-z0-9_]*", "class")
            if "ids" in selector:
                ids = selector["ids"]
                require(isinstance(ids, list) and ids, "empty exact-ID selector")
                for test_id in ids:
                    name(test_id, re.escape(module) + r"\.[A-Za-z_][A-Za-z0-9_]*\.test_[A-Za-z0-9_]+", "test ID")
                require(len(set(ids)) == len(ids), "duplicate selector ID")
            if module in zero:
                require(set(selector) == {"module"}, "zero-test file needs a whole-module selector")
    require(len(set(shard_ids)) == len(shard_ids), "duplicate shard ID")
    require(set(mentions) == files, f"unassigned test files: {sorted(files - set(mentions))}")
    require(all(mentions[module] == 1 for module in zero), "zero-test file must be assigned exactly once")
    profiles = data["local_profiles"]
    require(isinstance(profiles, dict) and set(profiles) <= {"3", "4"}, "unknown local profile")
    for width, groups in profiles.items():
        require(isinstance(groups, list) and len(groups) == int(width), f"profile {width} group count mismatch")
        group_ids = []
        selected = []
        for group in groups:
            keys(group, ("id", "shards"))
            name(group["id"], r"[a-z][a-z0-9_-]*", "local group ID")
            group_ids.append(group["id"])
            require(isinstance(group["shards"], list) and group["shards"], "empty local group")
            require(all(isinstance(item, str) for item in group["shards"]), "invalid local shard ID")
            selected.extend(group["shards"])
        require(len(set(group_ids)) == len(group_ids), "duplicate local group ID")
        require(Counter(selected) == Counter(shard_ids), f"profile {width} must cover every shard exactly once")
    subsets = data.get("subsets", {})
    require(isinstance(subsets, dict), "subsets must be an object")
    for subset_name, subset in subsets.items():
        name(subset_name, r"[a-z][a-z0-9_-]*", "subset name")
        keys(subset, ("ids",))
        ids = subset["ids"]
        require(isinstance(ids, list) and ids, "empty subset IDs")
        for test_id in ids:
            name(test_id, r"test_[A-Za-z0-9_]+\.[A-Za-z_][A-Za-z0-9_]*\.test_[A-Za-z0-9_]+", "subset test ID")
        require(len(set(ids)) == len(ids), "duplicate subset ID")
    return data, hashlib.sha256(raw).hexdigest()


def prepare_discovery(root):
    # Match `python -m unittest discover -s scripts` from the physical root:
    # root starts first; TestLoader inserts scripts ahead of it on discovery.
    scripts = root / "scripts"
    os.chdir(root)
    sys.path[:] = [str(root), *(value for value in sys.path
                              if Path(value or str(root)).resolve() not in (root, scripts))]


def flatten(suite):
    require(type(suite) is unittest.TestSuite, "custom TestSuite subclasses are unsupported; preserve their run semantics explicitly before sharding")
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            require(isinstance(test, unittest.TestCase), "unsupported discovery leaf")
            yield test


def partition(cases, data):
    canonical = [case.id() for case in cases]
    require(all(isinstance(item, str) and item for item in canonical), "empty canonical ID")
    duplicates = [item for item, count in Counter(canonical).items() if count != 1]
    require(not duplicates, f"duplicate canonical IDs: {duplicates}")
    require(canonical, "canonical discovery is empty")
    by_module = {}
    by_class = {}
    for case in cases:
        by_module.setdefault(case.__class__.__module__, set()).add(case.id())
        by_class.setdefault((case.__class__.__module__, case.__class__.__name__), set()).add(case.id())
    for module in data["zero_test_modules"]:
        require(not by_module.get(module), f"declared zero-test module now has tests: {module}")
    assignments = {}
    coverage = Counter()
    all_ids = set(canonical)
    for shard in data["shards"]:
        selected = Counter()
        for selector in shard["selectors"]:
            module = selector["module"]
            if "ids" in selector:
                matches = set(selector["ids"])
                require(matches <= by_module.get(module, set()), f"unknown exact IDs: {sorted(matches - by_module.get(module, set()))}")
            elif "class" in selector:
                matches = by_class.get((module, selector["class"]), set())
            else:
                matches = by_module.get(module, set())
            require(matches or module in data["zero_test_modules"], f"empty or unknown selector: {selector}")
            selected.update(matches)
        assignments[shard["id"]] = selected
        coverage.update(selected)
    require(coverage == Counter(canonical),
            f"coverage mismatch: missing={sorted(all_ids - set(coverage))}, repeated={sorted(item for item, count in coverage.items() if count != 1)}")
    return assignments


def choose_shards(args, data):
    known = [shard["id"] for shard in data["shards"]]
    if args.local_profile:
        require(args.local_group is not None, "--local-profile requires --local-group")
        groups = data["local_profiles"].get(args.local_profile, [])
        selected = [group["shards"] for group in groups if group["id"] == args.local_group]
        require(len(selected) == 1, f"unknown local group: {args.local_group}")
        return selected[0]
    require(args.local_group is None, "--local-group requires --local-profile")
    require(args.shard is not None and args.shard in known, f"unknown shard: {args.shard}")
    return [args.shard]


def choose_subset(args, data):
    require(args.local_group is None, "--local-group requires --local-profile")
    require(args.subset in data.get("subsets", {}), f"unknown subset: {args.subset}")
    return set(data["subsets"][args.subset]["ids"])


def validate_subsets(cases, data):
    canonical = {case.id() for case in cases}
    for subset_name, subset in data.get("subsets", {}).items():
        unknown = set(subset["ids"]) - canonical
        require(not unknown, f"unknown subset IDs in {subset_name}: {sorted(unknown)}")


# These contracts are deliberately independent of mutable manifest subsets.
CI_CORE_IDS = (
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

CI_COMPAT_IDS = (
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

CI_CONTRACT_MODULES = (
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


def ci_composition(cases, data):
    require([row["id"] for row in data["shards"]] == [f"s{i:02}" for i in range(1, 15)],
            "CI requires the complete ordered s01..s14 partition")
    expected = {"fast": set(CI_CORE_IDS), "compat310": set(CI_COMPAT_IDS)}
    by_module = {}
    for case in cases:
        by_module.setdefault(case.__class__.__module__, set()).add(case.id())
    for module in ("test_planveyor_plan_bundle", *CI_CONTRACT_MODULES):
        require(by_module.get(module), f"missing CI contract module: {module}")
    expected["contracts-a"] = by_module["test_planveyor_plan_bundle"]
    expected["contracts-b"] = set().union(*(by_module[module] for module in CI_CONTRACT_MODULES))
    canonical = {case.id() for case in cases}
    for subset, wanted in expected.items():
        actual = data.get("subsets", {}).get(subset, {}).get("ids", [])
        require(wanted <= canonical, f"missing canonical CI floor: {subset}")
        require(len(actual) == len(wanted) and set(actual) == wanted,
                f"CI composition mismatch: {subset}")
    require(data["subsets"]["compat310"]["ids"] == list(CI_COMPAT_IDS),
            "CI compat310 order differs from fixed contract")
    for left, right in (("fast", "contracts-a"), ("fast", "contracts-b"),
                        ("contracts-a", "contracts-b")):
        require(not expected[left] & expected[right], f"CI composition overlap: {left}/{right}")
    return {key: [case.id() for case in cases if case.id() in wanted]
            for key, wanted in expected.items()}


def ci_rows(profile):
    require(profile in ("fast", "full"), "unknown CI profile")
    if profile == "fast":
        rows = [{"part": part, "python-version": "3.12", "subset": subset,
                 "meta": part == "contracts-b"}
                for part, subset in (("core", "fast"), ("contracts-a", "contracts-a"),
                                     ("contracts-b", "contracts-b"))]
    else:
        rows = [{"part": f"s{i:02}", "python-version": "3.12",
                 "shard": f"s{i:02}", "meta": i == 1} for i in range(1, 15)]
    return rows + [{"part": "compat310", "python-version": "3.10",
                    "subset": "compat310", "meta": False}]


def ci_context(args):
    require(args.ci_profile in ("fast", "full"), "CI context requires profile")
    require(args.ci_event in ("push", "pull_request", "schedule", "workflow_dispatch"),
            "invalid CI event")
    require(args.ci_profile == ("fast" if args.ci_event in ("push", "pull_request") else "full"),
            "CI event/profile mismatch")
    for key in ("ci_run_id", "ci_run_attempt"):
        name(getattr(args, key), r"[1-9][0-9]*", key)
    name(args.ci_expected_sha, r"[0-9a-f]{40}", "CI expected SHA")
    if args.ci_event == "pull_request":
        name(args.ci_pr_head_sha, r"[0-9a-f]{40}", "PR head SHA")
    else:
        require(args.ci_pr_head_sha is None, "PR head SHA is only valid for pull_request")
    return {key: getattr(args, key) for key in
            ("ci_profile", "ci_event", "ci_run_id", "ci_run_attempt",
             "ci_expected_sha", "ci_pr_head_sha")}


def ci_mode(args):
    live = (args.ci_part, args.ci_python, args.ci_event, args.ci_run_id,
            args.ci_run_attempt, args.ci_expected_sha, args.ci_pr_head_sha)
    if args.ci_summary is not None:
        require(not args.ci_strict and args.ci_part is None and args.ci_python is None,
                "summary does not accept worker-only flags")
        require(args.local_group is None and args.report is None and args.durations is None,
                "unexpected execution arguments for summary")
        require(args.ci_needs_json is not None, "summary requires --ci-needs-json")
        ci_context(args)
    elif args.matrix or args.check:
        require(not args.ci_strict and not any(value is not None for value in live)
                and args.ci_needs_json is None, "matrix/check do not accept live CI context")
    else:
        require(args.ci_needs_json is None, "--ci-needs-json requires summary")
        if args.ci_profile is not None or args.ci_strict or any(value is not None for value in live):
            require(args.ci_strict and args.ci_profile is not None,
                    "CI execution requires --ci-strict and --ci-profile")
            require(args.local_profile is None and args.local_group is None,
                    "CI does not accept local-profile selection")
            ci_context(args)
            rows = [row for row in ci_rows(args.ci_profile) if row["part"] == args.ci_part]
            require(len(rows) == 1, "unknown CI part")
            row = rows[0]
            require(args.ci_python == row["python-version"], "CI part/Python mismatch")
            require(args.subset == row.get("subset") and args.shard == row.get("shard"),
                    "CI part/selector mismatch")
            require(".".join(map(str, sys.version_info[:2])) == args.ci_python,
                    "actual Python differs from CI expected Python")


def ci_selection(row, composition, assignments, cases):
    wanted = (set(composition[row["subset"]]) if "subset" in row
              else set(assignments[row["shard"]]))
    return [case.id() for case in cases if case.id() in wanted]


def ci_report_valid(report, context, row, expected_ids, manifest_hash):
    required = ("status", "head_before", "head_after", "manifest_sha256", "python",
                "selected_shards", "selected_subset", "planned_ids", "started_ids",
                "completed_ids", "tests_run", "skipped", "wall_seconds", "durations_source",
                "durations", "completion_exact", "result_successful", "failures", "errors",
                "ci_part", "ci_expected_python", "ci_python", *context)
    keys(report, required)
    for key, value in context.items():
        require(report[key] == value and type(report[key]) is type(value), f"CI context mismatch: {key}")
    require(report["ci_part"] == row["part"], "CI report part mismatch")
    expected_python = row["python-version"]
    require(report["ci_expected_python"] == expected_python, "CI report expected Python mismatch")
    observed = report["ci_python"]
    keys(observed, ("major", "minor"))
    require(all(type(value) is int for value in observed.values()), "invalid CI Python types")
    require(f'{observed["major"]}.{observed["minor"]}' == expected_python, "wrong CI Python")
    require(isinstance(report["python"], str) and
            re.match(re.escape(expected_python) + r"\.[0-9]+(?:\s|$)", report["python"]) is not None,
            "Python report string mismatch")
    require(report["status"] == "green" and report["completion_exact"] is True
            and report["result_successful"] is True, "CI report is not complete green")
    require(report["head_before"] == report["head_after"] == context["ci_expected_sha"],
            "CI report HEAD differs from trusted expected SHA")
    require(report["manifest_sha256"] == manifest_hash, "CI manifest mismatch")
    require(report["selected_shards"] == ([row["shard"]] if "shard" in row else [])
            and report["selected_subset"] == row.get("subset"), "CI report selector mismatch")
    require(expected_ids and len(set(expected_ids)) == len(expected_ids), "empty/duplicate expected IDs")
    for key in ("planned_ids", "started_ids", "completed_ids"):
        require(report[key] == expected_ids, f"CI ordered accounting mismatch: {key}")
    require(type(report["tests_run"]) is int and report["tests_run"] == len(expected_ids),
            "CI tests_run mismatch")
    require(report["skipped"] == report["failures"] == report["errors"] == [], "CI skips/failures/errors")
    wall = report["wall_seconds"]
    require(type(wall) in (int, float) and math.isfinite(wall) and wall >= 0, "invalid wall seconds")
    if expected_python == "3.12":
        require(report["durations_source"] == "unittest-native" and isinstance(report["durations"], list),
                "invalid native durations")
        for duration in report["durations"]:
            keys(duration, ("test", "seconds"))
            seconds = duration["seconds"]
            require(isinstance(duration["test"], str) and bool(duration["test"])
                    and type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0,
                    "invalid duration record")
    else:
        require(report["durations_source"] == "wall-only" and report["durations"] is None,
                "invalid wall-only durations")


def ci_json(raw):
    def reject(value):
        raise PartitionError(f"non-JSON numeric constant: {value}")
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject)


def ci_summary(args, data, manifest_hash, cases, assignments, composition):
    context = ci_context(args)
    require(git_head(args.root) == args.ci_expected_sha, "summary checkout differs from trusted expected SHA")
    needs = ci_json(args.ci_needs_json)
    keys(needs, ("shard-matrix", "verify"))
    for job, result in needs.items():
        keys(result, ("result",), ("outputs",))
        require(result["result"] == "success", f"required need is not successful: {job}")
    rows = ci_rows(args.ci_profile)
    directory = args.ci_summary
    require(directory.is_dir() and not directory.is_symlink(), "missing or unsafe CI report directory")
    expected = {f'planveyor-ci-{args.ci_run_id}-{args.ci_run_attempt}-{row["part"]}': row for row in rows}
    require({path.name for path in directory.iterdir()} == set(expected), "missing/extra CI artifact parts")
    union = []
    for artifact, row in expected.items():
        part_dir = directory / artifact
        require(part_dir.is_dir() and not part_dir.is_symlink(), "unsafe CI artifact directory")
        require({path.name for path in part_dir.iterdir()} == {"result.json"}, "extra/missing report members")
        path = part_dir / "result.json"
        require(path.is_file() and not path.is_symlink(), "unsafe CI report")
        report = ci_json(path.read_bytes())
        wanted = ci_selection(row, composition, assignments, cases)
        ci_report_valid(report, context, row, wanted, manifest_hash)
        if row["part"] != "compat310":
            union.extend(report["completed_ids"])
    intended = ([case.id() for case in cases] if args.ci_profile == "full"
                else [value for subset in ("fast", "contracts-a", "contracts-b") for value in composition[subset]])
    require(Counter(union) == Counter(intended) and all(count == 1 for count in Counter(union).values()),
            "CI actual union differs from independent expected universe")
    manifest = args.manifest or args.root / "scripts/test_shards.json"
    require(hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_hash
            and git_head(args.root) == args.ci_expected_sha, "summary source drift")
    print(json.dumps({"status": "green", **context, "parts": [row["part"] for row in rows],
                      "manifest_sha256": manifest_hash}))
    return 0


def git_head(root):
    completed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, capture_output=True, check=True)
    value = completed.stdout.strip()
    name(value, r"[0-9a-f]{40}", "HEAD")
    return value


def write_report(path, report):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class TrackedResult(unittest.TextTestResult):
    def __init__(self, *args, events, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_ids = []
        self.completed_ids = []
        self.events = events

    def event(self, kind, test):
        self.events.write(json.dumps({"event": kind, "id": test.id()}) + "\n")
        self.events.flush()

    def startTest(self, test):
        self.started_ids.append(test.id())
        self.event("started", test)
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        self.completed_ids.append(test.id())
        self.event("completed", test)


def completed_exactly(planned, started, completed):
    return Counter(planned) == Counter(started) == Counter(completed)


def run_selected(args, data, manifest_hash, cases, assignments):
    if args.subset is not None:
        selected_shards = []
        selected_ids = choose_subset(args, data)
    else:
        selected_shards = choose_shards(args, data)
        selected_ids = set().union(*(set(assignments[item]) for item in selected_shards))
    selected = [case for case in cases if case.id() in selected_ids]
    require(selected, "selected suite is empty")
    require(args.report is not None, "execution requires --report")
    require(args.report.parent.is_dir(), "report parent must already exist")
    require(not args.report.exists(), "report already exists; use a fresh path")
    events_path = args.report.with_name(args.report.name + ".events.jsonl")
    require(not events_path.exists(), "event log already exists; use a fresh path")
    native_durations = sys.version_info >= (3, 12)
    require(native_durations or args.durations is None, "--durations requires Python 3.12; Python 3.10 records suite wall time only")
    report = {
        "status": "running", "head_before": git_head(args.root), "head_after": None,
        "manifest_sha256": manifest_hash, "python": sys.version,
        "selected_shards": selected_shards, "selected_subset": args.subset,
        "planned_ids": [case.id() for case in selected],
        "started_ids": [], "completed_ids": [], "tests_run": None, "skipped": [],
        "wall_seconds": None, "durations_source": "unittest-native" if native_durations else "wall-only",
        "durations": None, "completion_exact": False, "result_successful": None,
    }
    strict = getattr(args, "ci_strict", False)
    if strict:
        context = ci_context(args)
        require(report["head_before"] == args.ci_expected_sha,
                "worker checkout differs from trusted expected SHA")
        report.update(context, ci_part=args.ci_part, ci_expected_python=args.ci_python,
                      ci_python={"major": sys.version_info.major, "minor": sys.version_info.minor})
    write_report(args.report, report)
    with events_path.open("x", encoding="utf-8") as events:
        events.write(json.dumps({"event": "planned", "head": report["head_before"], "manifest_sha256": manifest_hash,
                                 "ids": report["planned_ids"], "selected_subset": args.subset,
                                 "selected_shards": selected_shards}) + "\n")
        events.flush()
        observed_results = []
        def result_factory(*values, **kwargs):
            value = TrackedResult(*values, events=events, **kwargs)
            observed_results.append(value)
            return value
        runner_kwargs = {"verbosity": 2, "resultclass": result_factory}
        if native_durations:
            runner_kwargs["durations"] = 0 if args.durations is None else args.durations
        started = time.perf_counter()
        try:
            result = unittest.TextTestRunner(**runner_kwargs).run(unittest.TestSuite(selected))
        except BaseException as error:
            report.update(status="interrupted", wall_seconds=time.perf_counter() - started,
                          interruption=type(error).__name__)
            if observed_results:
                interrupted_result = observed_results[0]
                report.update(started_ids=interrupted_result.started_ids,
                              completed_ids=interrupted_result.completed_ids,
                              tests_run=interrupted_result.testsRun)
            write_report(args.report, report)
            raise
    report.update(
        head_after=git_head(args.root), started_ids=result.started_ids, completed_ids=result.completed_ids,
        tests_run=result.testsRun, skipped=[{"id": test.id(), "reason": reason} for test, reason in result.skipped],
        wall_seconds=time.perf_counter() - started,
        completion_exact=completed_exactly(report["planned_ids"], result.started_ids, result.completed_ids),
        result_successful=result.wasSuccessful(), errors=[test.id() for test, _ in result.errors],
        failures=[test.id() for test, _ in result.failures],
    )
    if native_durations:
        report["durations"] = [{"test": str(test), "seconds": seconds} for test, seconds in result.collectedDurations]
    green = report["completion_exact"] and report["result_successful"] and report["head_before"] == report["head_after"]
    report["status"] = "green" if green else "red"
    if strict:
        manifest = args.manifest or args.root / "scripts/test_shards.json"
        try:
            require(hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_hash,
                    "manifest changed during CI execution")
            row = next(row for row in ci_rows(args.ci_profile) if row["part"] == args.ci_part)
            ci_report_valid(report, context, row, report["planned_ids"], manifest_hash)
        except PartitionError as error:
            green = False
            report["status"] = "red"
            print(f"test-shard: {error}", file=sys.stderr)
    write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if green else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--manifest", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--matrix", action="store_true", help="emit include matrix; bare mode does not import tests")
    mode.add_argument("--check", action="store_true", help="discover and validate coverage; do not execute")
    mode.add_argument("--shard")
    mode.add_argument("--subset")
    mode.add_argument("--local-profile", choices=("3", "4"))
    mode.add_argument("--ci-summary", type=Path)
    parser.add_argument("--local-group")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--durations", type=int)
    parser.add_argument("--ci-profile", choices=("fast", "full"))
    parser.add_argument("--ci-strict", action="store_true")
    parser.add_argument("--ci-part")
    parser.add_argument("--ci-python", choices=("3.12", "3.10"))
    parser.add_argument("--ci-event", choices=("push", "pull_request", "schedule", "workflow_dispatch"))
    parser.add_argument("--ci-run-id")
    parser.add_argument("--ci-run-attempt")
    parser.add_argument("--ci-expected-sha")
    parser.add_argument("--ci-pr-head-sha")
    parser.add_argument("--ci-needs-json")
    args = parser.parse_args(argv)
    try:
        require((3, 10) <= sys.version_info[:2] <= (3, 12), "supported Python versions: 3.10–3.12")
        require(args.durations is None or args.durations >= 0, "negative durations")
        ci_mode(args)
        args.root = args.root.resolve()
        if args.report is not None:
            args.report = args.report.resolve()
        manifest = args.manifest or args.root / "scripts/test_shards.json"
        data, manifest_hash = load_manifest(manifest, args.root / "scripts")
        if args.matrix and args.ci_profile is None:
            require(args.local_group is None and args.report is None and args.durations is None, "unexpected execution arguments for matrix")
            require("compat310" in data.get("subsets", {}), "matrix requires compat310 subset")
            print(json.dumps({"include": [
                {"python-version": "3.12", "shard": shard["id"], "meta": index == 0}
                for index, shard in enumerate(data["shards"])
            ] + [{"python-version": "3.10", "subset": "compat310", "meta": False}]}, separators=(",", ":")))
            return 0
        if not args.check and not args.matrix and args.ci_summary is None:
            if args.subset is not None:
                choose_subset(args, data)
            else:
                choose_shards(args, data)
            require(sys.version_info >= (3, 12) or args.durations is None,
                    "--durations requires Python 3.12; Python 3.10 records suite wall time only")
        prepare_discovery(args.root)
        loader = unittest.TestLoader()
        discovered = loader.discover(str(args.root / "scripts"), pattern="test_*.py")
        require(not loader.errors, "canonical discovery errors:\n" + "\n".join(loader.errors))
        cases = list(flatten(discovered))
        assignments = partition(cases, data)
        validate_subsets(cases, data)
        composition = ci_composition(cases, data) if args.ci_profile is not None else None
        if args.matrix:
            require(args.local_group is None and args.report is None and args.durations is None,
                    "unexpected execution arguments for matrix")
            print(json.dumps({"include": ci_rows(args.ci_profile)}, separators=(",", ":")))
            return 0
        if args.ci_summary is not None:
            return ci_summary(args, data, manifest_hash, cases, assignments, composition)
        if args.check:
            require(args.local_group is None and args.report is None and args.durations is None, "unexpected execution arguments for check")
            result = {"manifest_sha256": manifest_hash, "canonical_tests": len(cases),
                      "shards": {key: sum(value.values()) for key, value in assignments.items()}}
            if composition is not None:
                result.update(ci_profile=args.ci_profile,
                              ci_composition={key: len(value) for key, value in composition.items()})
            print(json.dumps(result))
            return 0
        return run_selected(args, data, manifest_hash, cases, assignments)
    except (PartitionError, OSError, UnicodeError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"test-shard: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

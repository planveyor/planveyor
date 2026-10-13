#!/usr/bin/env python3
"""Run an exact manifest partition of canonical unittest discovery.

--matrix reads files and JSON only; --check and execution import the canonical
suite. This script does not create environments or launch parallel workers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
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
    keys(data, ("version", "baseline_head", "weighting", "zero_test_modules", "shards", "local_profiles"), ("$schema",))
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
        "selected_shards": selected_shards, "planned_ids": [case.id() for case in selected],
        "started_ids": [], "completed_ids": [], "tests_run": None, "skipped": [],
        "wall_seconds": None, "durations_source": "unittest-native" if native_durations else "wall-only",
        "durations": None, "completion_exact": False, "result_successful": None,
    }
    write_report(args.report, report)
    with events_path.open("x", encoding="utf-8") as events:
        events.write(json.dumps({"event": "planned", "head": report["head_before"], "manifest_sha256": manifest_hash,
                                 "ids": report["planned_ids"]}) + "\n")
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
    write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if green else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--manifest", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--matrix", action="store_true", help="emit include matrix without test imports")
    mode.add_argument("--check", action="store_true", help="discover and validate coverage; do not execute")
    mode.add_argument("--shard")
    mode.add_argument("--local-profile", choices=("3", "4"))
    parser.add_argument("--local-group")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--durations", type=int)
    args = parser.parse_args(argv)
    try:
        require((3, 10) <= sys.version_info[:2] <= (3, 12), "supported Python versions: 3.10–3.12")
        require(args.durations is None or args.durations >= 0, "negative durations")
        args.root = args.root.resolve()
        if args.report is not None:
            args.report = args.report.resolve()
        manifest = args.manifest or args.root / "scripts/test_shards.json"
        data, manifest_hash = load_manifest(manifest, args.root / "scripts")
        if args.matrix:
            require(args.local_group is None and args.report is None and args.durations is None, "unexpected execution arguments for matrix")
            print(json.dumps({"include": [
                {"python-version": version, "shard": shard["id"], "meta": version == "3.12" and index == 0}
                for version in ("3.10", "3.12") for index, shard in enumerate(data["shards"])
            ]}, separators=(",", ":")))
            return 0
        if not args.check:
            choose_shards(args, data)
            require(sys.version_info >= (3, 12) or args.durations is None,
                    "--durations requires Python 3.12; Python 3.10 records suite wall time only")
        prepare_discovery(args.root)
        loader = unittest.TestLoader()
        discovered = loader.discover(str(args.root / "scripts"), pattern="test_*.py")
        require(not loader.errors, "canonical discovery errors:\n" + "\n".join(loader.errors))
        cases = list(flatten(discovered))
        assignments = partition(cases, data)
        if args.check:
            require(args.local_group is None and args.report is None and args.durations is None, "unexpected execution arguments for check")
            print(json.dumps({"manifest_sha256": manifest_hash, "canonical_tests": len(cases),
                              "shards": {key: sum(value.values()) for key, value in assignments.items()}}))
            return 0
        return run_selected(args, data, manifest_hash, cases, assignments)
    except (PartitionError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"test-shard: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

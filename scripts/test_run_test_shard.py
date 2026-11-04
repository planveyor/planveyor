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
        fake = self.root / "fake-python"
        fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
        fake.chmod(0o700)
        for row in (rows[0], rows[-1]):
            command = re.sub(r"\$\{\{ matrix\.(shard|subset) \}\}",
                             lambda match: row.get(match[1], ""), step["run"])
            executed = subprocess.run(["bash", "-eu", "-c", command], capture_output=True, text=True,
                                      env={**os.environ, "PYBIN": str(fake), "RUNNER_TEMP": str(self.root)})
            self.assertEqual(executed.returncode, 0, executed.stderr)
            arguments = executed.stdout.splitlines()
            key = "shard" if "shard" in row else "subset"
            self.assertEqual(arguments, ["-B", "scripts/run_test_shard.py", f"--{key}", row[key],
                                         "--report", str(self.root / "test-shard.json")])
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


if __name__ == "__main__":
    unittest.main()

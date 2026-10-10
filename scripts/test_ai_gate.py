#!/usr/bin/env python3
"""Regression tests for scripts/ai_gate.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

MODULE_PATH = SCRIPT_DIR / "ai_gate.py"
SPEC = importlib.util.spec_from_file_location("ai_gate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AIGateTests(unittest.TestCase):
    def _repo(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name).resolve()
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", 'test' + '@' + 'example' + '.' + 'com'], cwd=root, check=True)
        (root / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "tools").mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=root, check=True, capture_output=True, text=True)
        return root

    def _write(self, root: Path, rel: str, body: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _commit(self, root: Path, rel: str, body: str, message: str) -> None:
        self._write(root, rel, body)
        subprocess.run(["git", "add", rel], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=root, check=True, capture_output=True, text=True)

    def _policy_path(self, root: Path, *, gitleaks_enabled: bool = False, semgrep_enabled: bool = False) -> Path:
        payload = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {
                "security_scans": {
                    "gitleaks": {"enabled": gitleaks_enabled, "required": False},
                    "semgrep": {"enabled": semgrep_enabled, "required": False, "config": ""},
                }
            },
        )
        path = root / "docs" / "tools" / "policy.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _write_policy_payload(self, root: Path, payload: dict[str, object]) -> Path:
        path = root / "docs" / "tools" / "policy.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_load_policy_accepts_example_policy(self) -> None:
        policy_path = SCRIPT_DIR.parent / "docs" / "tools" / "ai_gate_policy.example.json"

        policy = MODULE.load_policy(policy_path)

        self.assertEqual(policy["schema_version"], "ai_gate_policy.v1")
        self.assertEqual(policy["verdict_defaults"]["unconfirmed_detection"], "WARN")

    def test_load_policy_rejects_missing_required_raw_key_before_merge(self) -> None:
        root = self._repo()
        payload = dict(MODULE.DEFAULT_POLICY)
        payload.pop("detection")
        policy_path = self._write_policy_payload(root, payload)

        with self.assertRaisesRegex(ValueError, "missing required key.*detection"):
            MODULE.load_policy(policy_path)

    def test_load_policy_rejects_invalid_verdict_default(self) -> None:
        root = self._repo()
        payload = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {"verdict_defaults": {"scanner_error": "ALLOW"}},
        )
        policy_path = self._write_policy_payload(root, payload)

        with self.assertRaisesRegex(ValueError, "verdict_defaults.scanner_error"):
            MODULE.load_policy(policy_path)

    def test_load_policy_rejects_empty_detection_marker_list(self) -> None:
        root = self._repo()
        payload = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {"detection": {"author_markers": []}},
        )
        policy_path = self._write_policy_payload(root, payload)

        with self.assertRaisesRegex(ValueError, "detection.author_markers"):
            MODULE.load_policy(policy_path)

    def test_load_policy_rejects_non_string_detection_marker(self) -> None:
        root = self._repo()
        payload = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {"detection": {"message_markers": ["codex", 123]}},
        )
        policy_path = self._write_policy_payload(root, payload)

        with self.assertRaisesRegex(ValueError, "detection.message_markers"):
            MODULE.load_policy(policy_path)

    def test_detection_confirms_repo_backed_markers(self) -> None:
        commits = [
            {
                "commit": "abc123",
                "author_name": "Test User",
                "author_email": 'test' + '@' + 'example' + '.' + 'com',
                "subject": "AI-assisted: add gate lane",
                "body": "trace_id=123",
            }
        ]

        detection = MODULE.evaluate_detection(commits, MODULE.DEFAULT_POLICY)

        self.assertEqual(detection["status"], "CONFIRMED")
        self.assertTrue(detection["ai_assisted"])
        self.assertEqual(detection["signal_count"], 1)

    def test_policy_blocks_blocked_paths(self) -> None:
        policy = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {
                "path_rules": {
                    "allow": ["scripts/**"],
                    "block": [".github/workflows/**"],
                    "warn_outside_allowlist": True,
                }
            },
        )

        policy_lane = MODULE.evaluate_policy(
            {
                "files": [".github/workflows/test.yml"],
                "changed_file_count": 1,
                "lines_added": 5,
                "lines_removed": 0,
            },
            policy,
        )

        self.assertEqual(policy_lane["status"], "BLOCK")
        self.assertIn(".github/workflows/test.yml", policy_lane["path_rules"]["blocked_paths"])

    def test_warns_when_detection_unconfirmed_and_optional_scanner_missing(self) -> None:
        root = self._repo()
        self._commit(root, "scripts/example.py", "print('ok')\n", "Add helper")
        policy_path = self._policy_path(root, gitleaks_enabled=True, semgrep_enabled=False)

        with mock.patch.object(MODULE.shutil, "which", return_value=None):
            receipt = MODULE.build_receipt("HEAD~1..HEAD", root, MODULE.load_policy(policy_path))

        self.assertEqual(receipt["detection"]["status"], "UNCONFIRMED")
        self.assertEqual(receipt["security_scans"]["lanes"][0]["status"], "SKIPPED")
        self.assertEqual(receipt["security_scans"]["lanes"][0]["reason"], "tool_not_found")
        self.assertEqual(receipt["verdict"]["status"], "WARN")

    def test_security_scans_only_materialize_changed_range_files(self) -> None:
        root = self._repo()
        self._commit(root, "docs/history.txt", "password = OLD_SECRET\n", "Add historical debt")
        self._commit(root, "scripts/clean.py", "print('ok')\n", "AI-assisted: add helper")
        policy = MODULE._deep_merge(
            MODULE.DEFAULT_POLICY,
            {
                "security_scans": {
                    "gitleaks": {"enabled": True, "required": False},
                    "semgrep": {
                        "enabled": True,
                        "required": False,
                        "config": ".semgrep.yml",
                    },
                }
            },
        )
        self._write(root, ".semgrep.yml", "rules: []\n")
        scan_roots: list[Path] = []

        def fake_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if command[1] == "detect":
                scan_root = Path(command[command.index("--source") + 1])
                report_path = Path(command[command.index("--report-path") + 1])
                self.assertEqual(cwd, scan_root)
                self.assertTrue((scan_root / "scripts" / "clean.py").exists())
                self.assertFalse((scan_root / "docs" / "history.txt").exists())
                report_path.write_text("[]", encoding="utf-8")
                scan_roots.append(scan_root)
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[1] == "scan":
                scan_root = Path(command[-1])
                self.assertEqual(cwd, scan_root)
                self.assertTrue((scan_root / "scripts" / "clean.py").exists())
                self.assertFalse((scan_root / "docs" / "history.txt").exists())
                scan_roots.append(scan_root)
                return subprocess.CompletedProcess(command, 0, json.dumps({"results": []}), "")
            raise AssertionError(f"Unexpected command: {command}")

        with (
            mock.patch.object(MODULE.shutil, "which", side_effect=lambda name: f"/mock/{name}"),
            mock.patch.object(MODULE, "run_external_command", side_effect=fake_run),
        ):
            receipt = MODULE.build_receipt("HEAD~1..HEAD", root, policy)

        self.assertEqual(receipt["security_scans"]["status"], "PASS")
        self.assertEqual(receipt["verdict"]["status"], "PASS")
        self.assertEqual(receipt["security_scans"]["scope"]["scan_ref"], "HEAD")
        self.assertEqual(receipt["security_scans"]["scope"]["file_count"], 1)
        self.assertEqual(receipt["security_scans"]["scope"]["files"], ["scripts/clean.py"])
        self.assertEqual(len(scan_roots), 2)
        self.assertNotEqual(scan_roots[0], root)
        self.assertEqual(scan_roots[0], scan_roots[1])

    def test_main_writes_receipt_and_passes_for_confirmed_ai_range(self) -> None:
        root = self._repo()
        self._commit(root, "scripts/example.py", "print('ok')\n", "AI-assisted: add helper")
        policy_path = self._policy_path(root, gitleaks_enabled=False, semgrep_enabled=False)
        receipt_path = root / "docs" / "reviews" / "receipt_ai_gate.json"

        exit_code = MODULE.main(
            [
                "--project-root",
                str(root),
                "--range",
                "HEAD~1..HEAD",
                "--policy",
                str(policy_path),
                "--receipt-path",
                str(receipt_path),
            ]
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["verdict"]["status"], "PASS")
        self.assertEqual(payload["detection"]["status"], "CONFIRMED")

    def test_main_returns_block_for_policy_violation(self) -> None:
        root = self._repo()
        self._commit(root, ".github/workflows/test.yml", "name: test\n", "AI-assisted: add workflow")
        policy_path = self._policy_path(root, gitleaks_enabled=False, semgrep_enabled=False)
        receipt_path = root / "docs" / "reviews" / "block_ai_gate.json"

        exit_code = MODULE.main(
            [
                "--project-root",
                str(root),
                "--range",
                "HEAD~1..HEAD",
                "--policy",
                str(policy_path),
                "--receipt-path",
                str(receipt_path),
            ]
        )

        self.assertEqual(exit_code, 2)
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["verdict"]["status"], "BLOCK")
        self.assertIn(".github/workflows/test.yml", payload["policy"]["path_rules"]["blocked_paths"])

    def test_main_returns_zero_for_warn_verdict(self) -> None:
        root = self._repo()
        self._commit(
            root,
            "scripts/example.py",
            dedent(
                """\
                def run():
                    # TODO tighten retry window
                    return 1
                """
            ),
            "AI-assisted: add helper",
        )
        policy_path = self._policy_path(root, gitleaks_enabled=False, semgrep_enabled=False)
        receipt_path = root / "docs" / "reviews" / "warn_ai_gate.json"

        exit_code = MODULE.main(
            [
                "--project-root",
                str(root),
                "--range",
                "HEAD~1..HEAD",
                "--policy",
                str(policy_path),
                "--receipt-path",
                str(receipt_path),
            ]
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["verdict"]["status"], "WARN")

    def test_main_returns_one_for_policy_load_error(self) -> None:
        root = self._repo()
        self._commit(root, "scripts/example.py", "print('ok')\n", "AI-assisted: add helper")
        policy_path = root / "docs" / "tools" / "invalid_policy.json"
        policy_path.write_text("{not-json\n", encoding="utf-8")
        receipt_path = root / "docs" / "reviews" / "invalid_policy_ai_gate.json"

        exit_code = MODULE.main(
            [
                "--project-root",
                str(root),
                "--range",
                "HEAD~1..HEAD",
                "--policy",
                str(policy_path),
                "--receipt-path",
                str(receipt_path),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(receipt_path.exists())

    def test_satd_candidates_stay_candidate_only_and_warn(self) -> None:
        root = self._repo()
        self._commit(
            root,
            "scripts/example.py",
            dedent(
                """\
                def run():
                    # TODO tighten retry window
                    return 1
                """
            ),
            "AI-assisted: add helper",
        )
        policy_path = self._policy_path(root, gitleaks_enabled=False, semgrep_enabled=False)

        receipt = MODULE.build_receipt("HEAD~1..HEAD", root, MODULE.load_policy(policy_path))

        self.assertEqual(receipt["satd_candidates"]["count"], 1)
        self.assertEqual(receipt["satd_candidates"]["warnable_count"], 1)
        self.assertEqual(receipt["satd_candidates"]["deleted_count"], 0)
        self.assertEqual(receipt["satd_candidates"]["status"], "WARN")
        self.assertEqual(receipt["verdict"]["status"], "WARN")
        self.assertTrue(receipt["satd_candidates"]["manual_review_required"])
        candidate = receipt["satd_candidates"]["candidates"][0]
        self.assertEqual(candidate["lifecycle"], "created")
        self.assertIsNone(candidate["old_line"])
        self.assertEqual(candidate["new_line"], 2)

    def test_deleted_satd_candidates_enrich_receipt_without_warning(self) -> None:
        root = self._repo()
        self._commit(
            root,
            "scripts/example.py",
            "print('ok')\n",
            "AI-assisted: remove debt marker",
        )
        policy_path = self._policy_path(root, gitleaks_enabled=False, semgrep_enabled=False)
        deleted_candidate = MODULE.satd_scan.Candidate(
            file="scripts/example.py",
            line=2,
            keyword="TODO",
            blocker_signal=False,
            test_context=False,
            snippet="# TODO remove legacy path",
            lifecycle="deleted",
            old_line=2,
            new_line=None,
            old_snippet="# TODO remove legacy path",
            new_snippet="",
        )

        with mock.patch.object(MODULE.satd_scan, "scan_range", return_value=[deleted_candidate]):
            receipt = MODULE.build_receipt("HEAD~1..HEAD", root, MODULE.load_policy(policy_path))

        self.assertEqual(receipt["satd_candidates"]["count"], 1)
        self.assertEqual(receipt["satd_candidates"]["warnable_count"], 0)
        self.assertEqual(receipt["satd_candidates"]["deleted_count"], 1)
        self.assertEqual(receipt["satd_candidates"]["status"], "CLEAN")
        self.assertFalse(receipt["satd_candidates"]["manual_review_required"])
        self.assertEqual(receipt["verdict"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

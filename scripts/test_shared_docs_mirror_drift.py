#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest import mock
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import shared_docs_mirror_drift as drift
from scripts.test_support.process_contract_fixtures import run_zsh_fixture
from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write


CONSUMER_FIXTURE_POLICY = drift.MirrorPolicy(
    set_id="consumer-fixture-shared-docs",
    static_paths=(
        "docs/plans/README.md",
        "docs/plans/_template.md",
    ),
    glob_patterns=(
        "docs/reviews/_template_*.md",
        "docs/code_reviews/_template_*.md",
        "docs/doc_reviews/_template_*.md",
    ),
    target_repo="consumer-fixture",
    target_kind="mirror_sync",
)


def _write(root: Path, rel_path: str, text: str) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SharedDocsMirrorDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source_root = Path(self.tmp.name) / "source"
        self.target_root = Path(self.tmp.name) / "target"
        self.source_root.mkdir()
        self.target_root.mkdir()

        self.mirror_paths = [
            "docs/plans/README.md",
            "docs/plans/_template.md",
            "docs/reviews/_template_merge_notes.md",
            "docs/code_reviews/_template_single_commit.md",
            "docs/doc_reviews/_template_merge_range.md",
        ]
        for idx, rel_path in enumerate(self.mirror_paths):
            _write(self.source_root, rel_path, f"source {idx}\n")
            _write(self.target_root, rel_path, f"source {idx}\n")

    def test_expands_exact_mirror_set(self) -> None:
        self.assertEqual(
            drift.expand_mirror_set(self.source_root, policy=CONSUMER_FIXTURE_POLICY),
            sorted(self.mirror_paths),
        )

    def test_declared_applicability_is_pure_and_component_bounded(self) -> None:
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("filesystem access is forbidden")):
            applicability = drift.declared_mirror_target_applicability(
                "docs/reviews/_template_merge_notes.md",
                policy=CONSUMER_FIXTURE_POLICY,
            )
            self.assertTrue(drift.is_declared_mirror_path("docs/reviews/_template_merge_notes.md", policy=CONSUMER_FIXTURE_POLICY))
            self.assertFalse(drift.is_declared_mirror_path("docs/reviews/nested/_template_merge_notes.md", policy=CONSUMER_FIXTURE_POLICY))
            self.assertFalse(drift.is_declared_mirror_path("../docs/plans/_template.md", policy=CONSUMER_FIXTURE_POLICY))
        self.assertEqual(
            applicability,
            {
                "target_repo": "consumer-fixture",
                "target_kind": "mirror_sync",
                "target_writable_carriers": ["docs/reviews/_template_merge_notes.md"],
                "authority": "shared_docs_mirror_drift declared static_paths/glob_patterns",
            },
        )

    def test_generic_policy_has_no_implicit_target_or_mirror_set(self) -> None:
        for profile_id in ("default", "planveyor", "target-local"):
            self.assertEqual(
                drift.load_shared_docs_mirror_policy(content_profile_id=profile_id),
                drift.GENERIC_MIRROR_POLICY,
            )
        with self.assertRaises(drift.MirrorPolicyError):
            drift.load_shared_docs_mirror_policy(content_profile_id="unknown-consumer")
        self.assertFalse(drift.is_declared_mirror_path("docs/plans/README.md"))
        self.assertIsNone(drift.declared_mirror_target_applicability("docs/plans/README.md"))
        report = drift.build_report(self.source_root, self.target_root)
        self.assertEqual(report["mirror_set"]["id"], "generic")
        self.assertEqual(report["summary"]["total"], 0)

    def test_reports_no_drift(self) -> None:
        report = drift.build_report(self.source_root, self.target_root, policy=CONSUMER_FIXTURE_POLICY)
        self.assertEqual(report["recommended_outcome"], "no_packet_required")
        self.assertEqual(report["mirror_set"]["id"], CONSUMER_FIXTURE_POLICY.set_id)
        self.assertEqual(report["mirror_set"]["static_paths"], list(CONSUMER_FIXTURE_POLICY.static_paths))
        self.assertEqual(report["mirror_set"]["glob_patterns"], list(CONSUMER_FIXTURE_POLICY.glob_patterns))
        self.assertEqual(report["mirror_set"]["entry_count"], len(self.mirror_paths))
        self.assertEqual(report["summary"]["total"], len(self.mirror_paths))
        self.assertEqual(report["summary"]["drift"], 0)
        self.assertEqual(report["summary"]["missing_target"], 0)
        self.assertEqual(report["summary"]["missing_source"], 0)
        self.assertEqual(report["summary"]["in_sync"], len(self.mirror_paths))
        self.assertTrue(all(entry["status"] == "in_sync" for entry in report["entries"]))

    def test_reports_content_drift_as_packet_required(self) -> None:
        _write(self.target_root, "docs/plans/README.md", "target changed\n")
        report = drift.build_report(self.source_root, self.target_root, policy=CONSUMER_FIXTURE_POLICY)
        by_source = {entry["source"]: entry for entry in report["entries"]}
        self.assertEqual(report["recommended_outcome"], "packet_required")
        self.assertEqual(report["summary"]["drift"], 1)
        self.assertEqual(by_source["docs/plans/README.md"]["status"], "drift")
        self.assertEqual(
            by_source["docs/plans/README.md"]["recommended_outcome"],
            "packet_required",
        )

    def test_reports_missing_target_as_packet_required(self) -> None:
        (self.target_root / "docs/doc_reviews/_template_merge_range.md").unlink()
        report = drift.build_report(self.source_root, self.target_root, policy=CONSUMER_FIXTURE_POLICY)
        by_source = {entry["source"]: entry for entry in report["entries"]}
        self.assertEqual(report["recommended_outcome"], "packet_required")
        self.assertEqual(report["summary"]["missing_target"], 1)
        self.assertEqual(
            by_source["docs/doc_reviews/_template_merge_range.md"]["status"],
            "missing_target",
        )

    def test_missing_source_fails_closed_with_source_error(self) -> None:
        (self.source_root / "docs/plans/README.md").unlink()
        report = drift.build_report(self.source_root, self.target_root, policy=CONSUMER_FIXTURE_POLICY)
        by_source = {entry["source"]: entry for entry in report["entries"]}
        self.assertEqual(report["recommended_outcome"], "source_error")
        self.assertEqual(report["summary"]["missing_source"], 1)
        self.assertEqual(by_source["docs/plans/README.md"]["status"], "missing_source")
        self.assertEqual(
            by_source["docs/plans/README.md"]["recommended_outcome"],
            "source_error",
        )
        with (
            mock.patch.object(
                drift,
                "load_shared_docs_mirror_policy",
                return_value=CONSUMER_FIXTURE_POLICY,
            ),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            rc = drift.main(
                [
                    "--source-root",
                    str(self.source_root),
                    "--target-root",
                    str(self.target_root),
                    "--content-profile-id",
                    "target-local",
                    "--json",
                ]
            )
        self.assertEqual(rc, 2)

    def test_json_field_stability(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                drift,
                "load_shared_docs_mirror_policy",
                return_value=CONSUMER_FIXTURE_POLICY,
            ),
            mock.patch("sys.stdout", stdout),
        ):
            rc = drift.main(
                [
                    "--source-root",
                    str(self.source_root),
                    "--target-root",
                    str(self.target_root),
                    "--content-profile-id",
                    "planveyor",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(
            sorted(payload.keys()),
            ["entries", "mirror_set", "recommended_outcome", "source_root", "summary", "target_root"],
        )
        self.assertEqual(payload["mirror_set"]["id"], CONSUMER_FIXTURE_POLICY.set_id)
        self.assertEqual(payload["mirror_set"]["static_paths"], list(CONSUMER_FIXTURE_POLICY.static_paths))
        self.assertEqual(payload["mirror_set"]["glob_patterns"], list(CONSUMER_FIXTURE_POLICY.glob_patterns))
        self.assertEqual(payload["mirror_set"]["entry_count"], len(payload["entries"]))
        self.assertEqual(payload["recommended_outcome"], "no_packet_required")
        self.assertEqual(payload["summary"]["total"], len(payload["entries"]))
        self.assertEqual(
            sorted({entry["status"] for entry in payload["entries"]}),
            ["in_sync"],
        )
        self.assertEqual(
            sorted(payload["entries"][0].keys()),
            [
                "recommended_outcome",
                "source",
                "source_bytes",
                "source_sha256",
                "status",
                "target",
                "target_bytes",
                "target_sha256",
            ],
        )

    def test_profile_scan_has_no_implicit_mirror_set(self) -> None:
        _write(self.target_root, "docs/plans/_template.md", "target changed\n")
        with mock.patch("sys.stdout", io.StringIO()):
            default_rc = drift.main(
                [
                    "--source-root",
                    str(self.source_root),
                    "--target-root",
                    str(self.target_root),
                    "--content-profile-id",
                    "planveyor",
                ]
            )
        with mock.patch("sys.stdout", io.StringIO()):
            fail_rc = drift.main(
                [
                    "--source-root",
                    str(self.source_root),
                    "--target-root",
                    str(self.target_root),
                    "--content-profile-id",
                    "planveyor",
                    "--fail-on-drift",
                ]
            )
        self.assertEqual(default_rc, 0)
        self.assertEqual(fail_rc, 0)

    def test_injected_policy_fail_on_drift_is_nonzero(self) -> None:
        _write(self.target_root, "docs/plans/_template.md", "target changed\n")
        args = [
            "--source-root",
            str(self.source_root),
            "--target-root",
            str(self.target_root),
            "--content-profile-id",
            "target-local",
        ]
        with mock.patch.object(
            drift,
            "load_shared_docs_mirror_policy",
            return_value=CONSUMER_FIXTURE_POLICY,
        ):
            with mock.patch("sys.stdout", io.StringIO()):
                default_rc = drift.main(args)
            with mock.patch("sys.stdout", io.StringIO()):
                fail_rc = drift.main([*args, "--fail-on-drift"])
        self.assertEqual(default_rc, 0)
        self.assertEqual(fail_rc, 1)

    def test_helper_is_read_only_against_target_files(self) -> None:
        before = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        with mock.patch("sys.stdout", io.StringIO()):
            rc = drift.main(
                [
                    "--source-root",
                    str(self.source_root),
                    "--target-root",
                    str(self.target_root),
                    "--content-profile-id",
                    "planveyor",
                    "--json",
                ]
            )
        after = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        self.assertEqual(rc, 0)
        self.assertEqual(after, before)

    def test_zsh_wrapper_dispatches_to_helper_read_only(self) -> None:
        before = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        command = (
            f"source {shlex.quote(str(drift.REPO_ROOT / 'scripts/planveyor.zsh'))} && "
            "planveyor_shared_docs_mirror_drift "
            f"--source-root {shlex.quote(str(self.source_root))} "
            f"--target-root {shlex.quote(str(self.target_root))} "
            "--content-profile-id planveyor "
            "--json"
        )
        result = run_zsh_fixture(
            command,
            cwd=drift.REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            check=False,
        )
        after = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["source_root"], self.source_root.resolve().as_posix())
        self.assertEqual(payload["target_root"], self.target_root.resolve().as_posix())
        self.assertEqual(payload["mirror_set"]["id"], "generic")
        self.assertEqual(payload["summary"]["total"], 0)
        self.assertEqual(after, before)

    def test_zsh_strict_gate_has_no_implicit_target_on_drift_and_is_read_only(self) -> None:
        _write(self.target_root, "docs/plans/README.md", "target changed\n")
        before = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        command = (
            f"source {shlex.quote(str(drift.REPO_ROOT / 'scripts/planveyor.zsh'))} && "
            "planveyor_mirror_strict_gate "
            f"--source-root {shlex.quote(str(self.source_root))} "
            f"--target-root {shlex.quote(str(self.target_root))} "
            "--content-profile-id planveyor "
            "--json"
        )
        result = run_zsh_fixture(
            command,
            cwd=drift.REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            check=False,
        )
        after = {
            rel_path: (self.target_root / rel_path).read_bytes()
            for rel_path in self.mirror_paths
        }
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["recommended_outcome"], "no_packet_required")
        self.assertEqual(payload["summary"]["total"], 0)
        self.assertEqual(after, before)

    def test_zsh_strict_gate_returns_zero_when_in_sync(self) -> None:
        command = (
            f"source {shlex.quote(str(drift.REPO_ROOT / 'scripts/planveyor.zsh'))} && "
            "planveyor_mirror_strict_gate "
            f"--source-root {shlex.quote(str(self.source_root))} "
            f"--target-root {shlex.quote(str(self.target_root))} "
            "--content-profile-id planveyor "
            "--json"
        )
        result = run_zsh_fixture(
            command,
            cwd=drift.REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["recommended_outcome"], "no_packet_required")


class SharedDocsMirrorFacadeProjectRootTests(unittest.TestCase):
    """Relative roots resolve in the selected project; the source stays the engine."""

    def test_public_mirror_routes_resolve_relative_roots_in_project(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            runtime_commit = commit_all(fixture.runtime_root, "public mirror drift facade")
            target = fixture.target_root
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            results = {}
            for command_name in ("planveyor_shared_docs_mirror_drift", "planveyor_mirror_strict_gate"):
                results[command_name] = subprocess.run(
                    [str(entry), "--project", str(target), command_name, "--target-root", ".", "--json"],
                    cwd=target,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            runtime_status = git(fixture.runtime_root, "status", "--short", "--untracked-files=all")
            runtime_head = git(fixture.runtime_root, "rev-parse", "HEAD")

        for command_name, result in results.items():
            with self.subTest(route=command_name):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["target_root"], target.as_posix())
                # The shared-docs source of truth is the runtime checkout by the
                # helper's own default, independent of the facade's cwd.
                self.assertEqual(payload["source_root"], fixture.runtime_root.as_posix())
                self.assertEqual(payload["mirror_set"]["id"], "generic")
        self.assertEqual(runtime_status, "")
        self.assertEqual(runtime_head, runtime_commit)


if __name__ == "__main__":
    unittest.main()

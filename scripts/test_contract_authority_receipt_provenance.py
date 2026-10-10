"""Receipt binding across v1/v2 entry-observation provenance transitions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as authority  # noqa: E402
from authority_bootstrap_test_support import run_bootstrapped_bridge  # noqa: E402
from test_contract_authority_support import AuthorityFixture, commit_all, git, write  # noqa: E402


_SID = "00000000-0000-4000-8000-00000000c901"
_SESSION_KEY = "architect"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _seal(envelope: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(envelope)
    result.pop("context_sha256")
    result["context_sha256"] = hashlib.sha256(_canonical_json(result).encode("utf-8")).hexdigest()
    return result


def _different_hex(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise AssertionError("expected a nonempty hexadecimal value")
    return ("0" if value[0] != "0" else "1") + value[1:]


class ContractAuthorityReceiptProvenanceTests(unittest.TestCase):
    """The receipt is historical, while the child labels supplied facts honestly."""

    def _runtime_pin(self, fixture: AuthorityFixture) -> str:
        result = run_bootstrapped_bridge(
            fixture,
            "runtime-pin",
            "--runtime-root",
            str(fixture.runtime_root),
            "--entrypoint",
            str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def _context(self, fixture: AuthorityFixture, *, expected: dict[str, object] | None = None) -> dict[str, object]:
        arguments = [
            "context",
            "--project-root",
            str(fixture.target_root),
            "--runtime-pin-summary",
            self._runtime_pin(fixture),
        ]
        if expected is not None:
            arguments.extend(("--expected", _canonical_json(expected)))
        result = run_bootstrapped_bridge(fixture, *arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def _seed_receipt(self, fixture: AuthorityFixture, envelope: dict[str, object]) -> None:
        write(
            fixture.target_root,
            f".planveyor.init_runs/by_sid/{_SID}/meta.json",
            _canonical_json(
                {
                    "outcome": "success",
                    "sid": _SID,
                    "session_key": _SESSION_KEY,
                    "authority_context": envelope,
                }
            )
            + "\n",
        )

    def _validate_receipt(
        self,
        fixture: AuthorityFixture,
        envelope: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        return run_bootstrapped_bridge(
            fixture,
            "receipt-validate",
            "--project-root",
            str(fixture.target_root),
            "--session-key",
            _SESSION_KEY,
            "--sid",
            _SID,
            "--mode",
            "engaged",
            "--context",
            _canonical_json(envelope),
        )

    def _assert_matched(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"mode": "engaged", "receipt": "matched", "ok": True})

    def _assert_semantic_mismatch(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("receipt_authority_mismatch", result.stderr)

    def test_v3_child_reuses_observed_receipt_after_unrelated_target_evolution(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            observed = self._context(fixture)
            self._seed_receipt(fixture, observed)
            self._assert_matched(self._validate_receipt(fixture, observed))

            write(fixture.target_root, "notes/unrelated-evolution.md", "unrelated target evolution\n")
            git(fixture.target_root, "add", "--", "notes/unrelated-evolution.md")
            git(fixture.target_root, "commit", "--quiet", "-m", "unrelated target evolution")

            inherited = self._context(fixture, expected=observed)
            self.assertEqual(inherited["schema_version"], "planveyor_contract_context.v3")
            self.assertEqual(inherited["entry_observation_provenance"], "inherited_supplied_unverified")
            self.assertEqual(inherited["entry_observation"], observed["entry_observation"])
            self.assertEqual(inherited["project_root"], observed["project_root"])
            self.assertEqual(inherited["generation_sha256"], observed["generation_sha256"])
            self.assertEqual(inherited["runtime_pin"], observed["runtime_pin"])
            self.assertNotEqual(inherited["context_sha256"], observed["context_sha256"])
            self._assert_matched(self._validate_receipt(fixture, inherited))

    def test_historical_v1_receipt_is_passive_but_not_an_active_context(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            observed = self._context(fixture)
            historical = copy.deepcopy(observed)
            historical["schema_version"] = "planveyor_contract_context.v1"
            historical.pop("entry_observation_provenance")
            historical = _seal(historical)
            self._seed_receipt(fixture, historical)
            self._assert_matched(self._validate_receipt(fixture, historical))
            failed = run_bootstrapped_bridge(
                fixture,
                "context",
                "--project-root", str(fixture.target_root),
                "--runtime-pin-summary", self._runtime_pin(fixture),
                "--expected", _canonical_json(historical),
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("context_active_schema_unsupported", failed.stderr)

    def test_receipt_rejects_changed_entry_root_and_generation_facts(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            observed = self._context(fixture)
            self._seed_receipt(fixture, observed)

            changed_head = copy.deepcopy(observed)
            changed_head["entry_observation"]["head"] = _different_hex(changed_head["entry_observation"]["head"])

            changed_tree = copy.deepcopy(observed)
            changed_tree["entry_observation"]["tree"] = _different_hex(changed_tree["entry_observation"]["tree"])

            changed_index = copy.deepcopy(observed)
            changed_index["entry_observation"]["index_sha256"] = _different_hex(
                changed_index["entry_observation"]["index_sha256"]
            )

            changed_root = copy.deepcopy(observed)
            alternate_root = fixture.root / "alternate-target"
            changed_root["project_root"] = str(alternate_root)
            changed_root["entry_observation"]["root"] = str(alternate_root)
            changed_root["entry_observation"]["git_dir"] = str(alternate_root / ".git")

            changed_generation = copy.deepcopy(observed)
            changed_generation["generation_sha256"] = _different_hex(changed_generation["generation_sha256"])

            for name, candidate in {
                "entry-head": changed_head,
                "entry-tree": changed_tree,
                "entry-index": changed_index,
                "project-root": changed_root,
                "generation": changed_generation,
            }.items():
                with self.subTest(field=name):
                    self._assert_semantic_mismatch(self._validate_receipt(fixture, _seal(candidate)))

    def test_receipt_rejects_a_real_changed_runtime_pin(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            observed = self._context(fixture)
            self._seed_receipt(fixture, observed)

            changed_source = fixture.runtime_root / "scripts" / "plan_lint.py"
            changed_source.write_bytes(changed_source.read_bytes() + b"\n# receipt provenance runtime evolution\n")
            commit_all(fixture.runtime_root, "receipt provenance runtime evolution")

            changed_runtime = self._context(fixture)
            self.assertEqual(changed_runtime["entry_observation"], observed["entry_observation"])
            self.assertNotEqual(changed_runtime["runtime_pin"], observed["runtime_pin"])
            self._assert_semantic_mismatch(self._validate_receipt(fixture, changed_runtime))

            # Keep every other semantic field stable to prove that the runtime
            # pin itself is bound.  This value came from the real changed
            # runtime context above; it is not a fabricated capsule.
            changed_pin_only = copy.deepcopy(observed)
            changed_pin_only["runtime_pin"] = changed_runtime["runtime_pin"]
            self._assert_semantic_mismatch(self._validate_receipt(fixture, _seal(changed_pin_only)))


if __name__ == "__main__":
    unittest.main()

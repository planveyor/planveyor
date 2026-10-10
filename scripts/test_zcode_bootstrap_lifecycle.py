#!/usr/bin/env python3
"""Focused synthetic tests for the ZCode bootstrap lifecycle helper."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from zcode_bootstrap_lifecycle import (
    MAX_CARRIER_BYTES,
    REQUIRED_ZCODE_TOOLING_CONTRACT_PATHS,
    VALID_LANES,
    LifecycleError,
    acknowledgement_digest,
    abandon_pending,
    init_epoch,
    promote_ack,
    read_exact_epoch,
    reserve_agent,
)


class ZCodeBootstrapLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="zcode-bootstrap-lifecycle-")
        self.root = Path(self.temp.name).resolve()
        self.project_root = self.root / "project"
        self.tooling_root = self.root / "tooling"
        self.project_root.mkdir()
        self.tooling_root.mkdir()
        self.project_contract_path = self.project_root / "AGENTS.md"
        self.project_contract_path.write_text("# project instructions\n", encoding="utf-8")
        self.role_contract_path = self.tooling_root / "docs" / "roles" / "coder.md"
        self.role_contract_path.parent.mkdir(parents=True)
        self.role_contract_path.write_text("# role contract\n", encoding="utf-8")
        self.contract_path = self.tooling_root / "docs" / "tools" / "prompts" / "coder_init.md"
        self.contract_path.parent.mkdir(parents=True)
        self.contract_path.write_text("# role init\n", encoding="utf-8")
        self.extra_contract_path = self.tooling_root / "docs" / "tools" / "prompts" / "extra.md"
        self.extra_contract_path.write_text("# extra contract\n", encoding="utf-8")
        self.zcode_contract_paths: list[Path] = []
        for relative_path in REQUIRED_ZCODE_TOOLING_CONTRACT_PATHS:
            path = self.tooling_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {relative_path}\n", encoding="utf-8")
            self.zcode_contract_paths.append(path)
        self.session = "manager-session-a"
        self.epoch = "team-epoch-a"

    def tearDown(self) -> None:
        self.temp.cleanup()

    @property
    def identity(self) -> dict[str, str]:
        return {
            "project_root": str(self.project_root),
            "tooling_root": str(self.tooling_root),
            "manager_session_identity": self.session,
            "team_epoch": self.epoch,
        }

    @property
    def carrier_path(self) -> Path:
        return self.project_root / f".planveyor.zcode.bootstrap.{self.epoch}.json"

    def _init(self) -> dict[str, object]:
        return init_epoch(**self.identity)

    def _contract_reads(self) -> list[dict[str, str]]:
        manifest = [
            {
                "root_class": "project",
                "path": str(self.project_contract_path),
                "sha256": hashlib.sha256(self.project_contract_path.read_bytes()).hexdigest(),
            },
            {
                "root_class": "tooling",
                "path": str(self.role_contract_path),
                "sha256": hashlib.sha256(self.role_contract_path.read_bytes()).hexdigest(),
            },
            {
                "root_class": "tooling",
                "path": str(self.contract_path),
                "sha256": hashlib.sha256(self.contract_path.read_bytes()).hexdigest(),
            },
            *[
                {
                    "root_class": "tooling",
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in self.zcode_contract_paths
            ],
        ]
        return sorted(manifest, key=lambda item: (item["root_class"], item["path"]))

    def _reserve(
        self,
        role_lane: str,
        *,
        contract_reads: list[dict[str, str]] | None = None,
        replace_current: bool = False,
    ) -> dict[str, object]:
        return reserve_agent(
            **self.identity,
            role_lane=role_lane,
            contract_reads=self._contract_reads() if contract_reads is None else contract_reads,
            replace_current=replace_current,
        )

    def _ack(
        self,
        reservation: dict[str, object],
        *,
        contract_reads: list[dict[str, str]] | None = None,
        key_order: bool = False,
    ) -> dict[str, object]:
        values: list[tuple[str, object]] = [
            ("team_epoch", self.epoch),
            ("role_lane", reservation["role_lane"]),
            ("role_generation", reservation["role_generation"]),
            ("init_nonce", reservation["init_nonce"]),
            (
                "read_contracts",
                self._contract_reads() if contract_reads is None else contract_reads,
            ),
        ]
        if key_order:
            values.reverse()
        return dict(values)

    def _promote(
        self,
        reservation: dict[str, object],
        *,
        agent_id: str = "agent-1",
        acknowledgement: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return promote_ack(
            **self.identity,
            role_lane=str(reservation["role_lane"]),
            role_generation=int(reservation["role_generation"]),
            init_nonce=str(reservation["init_nonce"]),
            agent_identity_audit=agent_id,
            acknowledgement=self._ack(reservation) if acknowledgement is None else acknowledgement,
        )

    def test_init_epoch_is_idempotent_and_uses_exact_project_carrier(self) -> None:
        first = self._init()
        second = self._init()

        self.assertEqual("epoch_current", first["verdict"])
        self.assertEqual(first, second)
        self.assertTrue(self.carrier_path.is_file())
        self.assertEqual(0o600, stat.S_IMODE(os.lstat(self.carrier_path).st_mode))
        self.assertFalse(list(self.project_root.glob(f".{self.carrier_path.name}.*")))
        self.assertFalse((self.tooling_root / self.carrier_path.name).exists())

    def test_non_git_standalone_may_use_one_root_for_project_and_runtime(self) -> None:
        standalone = self.root / "standalone"
        standalone.mkdir()
        agents = standalone / "AGENTS.md"
        role = standalone / "docs" / "roles" / "coder.md"
        prompt = standalone / "docs" / "tools" / "prompts" / "coder_init.md"
        agents.write_text("# project instructions\n", encoding="utf-8")
        role.parent.mkdir(parents=True)
        prompt.parent.mkdir(parents=True)
        role.write_text("# role contract\n", encoding="utf-8")
        prompt.write_text("# role prompt\n", encoding="utf-8")
        zcode_paths: list[Path] = []
        for relative_path in REQUIRED_ZCODE_TOOLING_CONTRACT_PATHS:
            path = standalone / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {relative_path}\n", encoding="utf-8")
            zcode_paths.append(path)
        identity = {
            "project_root": str(standalone),
            "tooling_root": str(standalone),
            "manager_session_identity": "standalone-manager",
            "team_epoch": "standalone-epoch",
        }
        manifest = [
            {
                "root_class": "project",
                "path": str(agents),
                "sha256": hashlib.sha256(agents.read_bytes()).hexdigest(),
            },
            {
                "root_class": "tooling",
                "path": str(role),
                "sha256": hashlib.sha256(role.read_bytes()).hexdigest(),
            },
            {
                "root_class": "tooling",
                "path": str(prompt),
                "sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
            },
            *[
                {
                    "root_class": "tooling",
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in zcode_paths
            ],
        ]
        manifest = sorted(manifest, key=lambda item: (item["root_class"], item["path"]))

        self.assertEqual("epoch_current", init_epoch(**identity)["verdict"])
        reservation = reserve_agent(
            **identity,
            role_lane="coder",
            contract_reads=manifest,
        )
        acknowledgement = {
            "team_epoch": identity["team_epoch"],
            "role_lane": "coder",
            "role_generation": reservation["role_generation"],
            "init_nonce": reservation["init_nonce"],
            "read_contracts": manifest,
        }
        current = promote_ack(
            **identity,
            role_lane="coder",
            role_generation=int(reservation["role_generation"]),
            init_nonce=str(reservation["init_nonce"]),
            agent_identity_audit="standalone-agent",
            acknowledgement=acknowledgement,
        )
        self.assertEqual("current", current["verdict"])
        self.assertTrue((standalone / ".planveyor.zcode.bootstrap.standalone-epoch.json").is_file())

    def test_cli_emits_deterministic_exact_epoch_readback(self) -> None:
        helper = Path(__file__).with_name("zcode_bootstrap_lifecycle.py")
        command = [
            sys.executable,
            "-B",
            str(helper),
            "init_epoch",
            "--project-root",
            str(self.project_root),
            "--tooling-root",
            str(self.tooling_root),
            "--manager-session-identity",
            self.session,
            "--team-epoch",
            self.epoch,
        ]
        initialized = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        self.assertEqual("epoch_current", json.loads(initialized.stdout)["verdict"])
        command[3] = "read_exact_epoch"
        readback = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(0, readback.returncode, readback.stderr)
        self.assertEqual(json.loads(initialized.stdout), json.loads(readback.stdout))

    def test_documented_interpreter_entrypoint_is_executable(self) -> None:
        helper = Path(__file__).with_name("zcode_bootstrap_lifecycle.py")
        result = subprocess.run(
            [os.environ.get("PYBIN", sys.executable), "-B", str(helper), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("zcode_bootstrap_lifecycle", result.stdout)

    def test_cli_reservation_binds_contract_reads_manifest(self) -> None:
        self._init()
        helper = Path(__file__).with_name("zcode_bootstrap_lifecycle.py")
        command = [
            os.environ.get("PYBIN", sys.executable),
            "-B",
            str(helper),
            "reserve_agent",
            "--project-root",
            str(self.project_root),
            "--tooling-root",
            str(self.tooling_root),
            "--manager-session-identity",
            self.session,
            "--team-epoch",
            self.epoch,
            "--role-lane",
            "coder",
            "--contract-reads-json",
            json.dumps(self._contract_reads()),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("pending", payload["verdict"])
        self.assertIn("expected_contract_reads_digest", payload)

    def test_public_zcode_assets_are_bound_and_drift_fails_before_agent_dispatch(self) -> None:
        self._init()
        manifest = self._contract_reads()
        for path in self.zcode_contract_paths:
            self.assertIn(
                ("tooling", str(path)),
                {(item["root_class"], item["path"]) for item in manifest},
            )
            missing = [item for item in manifest if item["path"] != str(path)]
            with self.assertRaises(LifecycleError) as rejected:
                self._reserve("coder", contract_reads=missing)
            self.assertEqual("zcode_contract_assets_missing", rejected.exception.reason_code)

        reservation = self._reserve("coder", contract_reads=manifest)
        self.zcode_contract_paths[1].write_text("# changed role definition\n", encoding="utf-8")
        with self.assertRaises(LifecycleError) as promotion_drift:
            self._promote(reservation)
        self.assertEqual("contract_reads_mismatch", promotion_drift.exception.reason_code)
        with self.assertRaises(LifecycleError) as drift:
            read_exact_epoch(
                **self.identity,
                role_lane="coder",
                role_generation=int(reservation["role_generation"]),
                init_nonce=str(reservation["init_nonce"]),
                expected_state="pending",
            )
        self.assertEqual("malformed_state", drift.exception.reason_code)

    def test_five_lanes_reserve_generation_one_and_block_second_pending(self) -> None:
        self._init()
        for lane in sorted(VALID_LANES):
            with self.subTest(lane=lane):
                reservation = self._reserve(lane)
                self.assertEqual("pending", reservation["verdict"])
                self.assertEqual(1, reservation["role_generation"])
                pending = read_exact_epoch(
                    **self.identity,
                    role_lane=lane,
                    role_generation=1,
                    init_nonce=str(reservation["init_nonce"]),
                    expected_state="pending",
                )
                self.assertEqual("pending", pending["verdict"])
                with self.assertRaises(LifecycleError) as error:
                    self._reserve(lane)
                self.assertEqual("pending_attempt_exists", error.exception.reason_code)

    def test_promote_derives_canonical_digest_and_requires_exact_acknowledgement(self) -> None:
        self._init()
        reservation = self._reserve("coder")
        acknowledgement = self._ack(reservation)
        reordered = self._ack(reservation, key_order=True)
        self.assertEqual(acknowledgement_digest(acknowledgement), acknowledgement_digest(reordered))

        mismatched = {**acknowledgement, "init_nonce": "q" * 24}
        with self.assertRaises(LifecycleError) as wrong_nonce:
            promote_ack(
                **self.identity,
                role_lane="coder",
                role_generation=1,
                init_nonce=str(reservation["init_nonce"]),
                agent_identity_audit="agent-coder-1",
                acknowledgement=mismatched,
            )
        self.assertEqual("acknowledgement_mismatch", wrong_nonce.exception.reason_code)
        wrong_hash = self._ack(reservation)
        wrong_hash["read_contracts"][0]["sha256"] = "0" * 64
        with self.assertRaises(LifecycleError) as wrong_contract_hash:
            promote_ack(
                **self.identity,
                role_lane="coder",
                role_generation=1,
                init_nonce=str(reservation["init_nonce"]),
                agent_identity_audit="agent-coder-1",
                acknowledgement=wrong_hash,
            )
        self.assertEqual("acknowledgement_mismatch", wrong_contract_hash.exception.reason_code)

        current = self._promote(reservation, agent_id="agent-coder-1")
        self.assertEqual("current", current["verdict"])
        self.assertEqual(acknowledgement_digest(acknowledgement), current["acknowledgement_digest"])
        self.assertEqual("agent-coder-1", current["agent_identity_audit"])
        self.assertEqual(
            sorted(self._contract_reads(), key=lambda item: (item["root_class"], item["path"])),
            current["expected_contract_reads"],
        )
        exact = read_exact_epoch(
            **self.identity,
            role_lane="coder",
            role_generation=1,
            init_nonce=str(reservation["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("current", exact["verdict"])

        with self.assertRaises(LifecycleError) as supplied_digest:
            promote_ack(
                **self.identity,
                role_lane="coder",
                role_generation=1,
                init_nonce=str(reservation["init_nonce"]),
                agent_identity_audit="agent-coder-1",
                acknowledgement={**acknowledgement, "acknowledgement_digest": "0" * 64},
            )
        self.assertEqual("manager_digest_forbidden", supplied_digest.exception.reason_code)
        with self.assertRaises(LifecycleError) as non_finite:
            acknowledgement_digest(
                '{"team_epoch":"team-epoch-a","role_lane":"coder","role_generation":NaN,'
                '"init_nonce":"abcdefghijklmnop","read_contracts":[]}'
            )
        self.assertEqual("malformed_state", non_finite.exception.reason_code)

    def test_promote_requires_exact_reserved_contract_manifest(self) -> None:
        self._init()
        self.assertNotEqual(self.project_root, self.tooling_root)
        self.assertEqual("project", self._contract_reads()[0]["root_class"])
        self.assertTrue(self._contract_reads()[0]["path"].endswith("/AGENTS.md"))
        reservation = self._reserve("coder")
        reordered = list(reversed(self._contract_reads()))
        current = self._promote(
            reservation,
            acknowledgement=self._ack(reservation, contract_reads=reordered),
        )
        self.assertEqual("current", current["verdict"])
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    current["expected_contract_reads"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            current["expected_contract_reads_digest"],
        )

        cases = {
            "missing": self._contract_reads()[1:],
            "extra": self._contract_reads()
            + [
                {
                    "root_class": "tooling",
                    "path": str(self.extra_contract_path),
                    "sha256": hashlib.sha256(self.extra_contract_path.read_bytes()).hexdigest(),
                }
            ],
            "substituted": [
                {
                    "root_class": "tooling",
                    "path": str(self.extra_contract_path),
                    "sha256": hashlib.sha256(self.extra_contract_path.read_bytes()).hexdigest(),
                },
                *self._contract_reads()[1:],
            ],
        }
        for lane, contract_reads in zip(
            ("architect", "planner", "reviewer_code_risk"),
            cases.values(),
            strict=True,
        ):
            with self.subTest(case=lane):
                pending = self._reserve(lane)
                with self.assertRaises(LifecycleError) as mismatch:
                    self._promote(
                        pending,
                        acknowledgement=self._ack(pending, contract_reads=contract_reads),
                    )
                self.assertEqual("contract_reads_mismatch", mismatch.exception.reason_code)

        invalid_manifest = self._contract_reads()
        invalid_manifest[0]["sha256"] = "0" * 64
        with self.assertRaises(LifecycleError) as invalid_reservation:
            self._reserve("reviewer_code_contracts", contract_reads=invalid_manifest)
        self.assertEqual("contract_reads_mismatch", invalid_reservation.exception.reason_code)

    def test_same_handle_reuse_does_not_increment_and_lost_handle_rolls_over(self) -> None:
        self._init()
        first = self._reserve("planner")
        self._promote(first, agent_id="agent-planner-1")
        current = read_exact_epoch(
            **self.identity,
            role_lane="planner",
            role_generation=1,
            init_nonce=str(first["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("current", current["verdict"])

        with self.assertRaises(LifecycleError) as direct_replacement:
            self._reserve("planner")
        self.assertEqual("current_attempt_exists", direct_replacement.exception.reason_code)
        replacement = self._reserve("planner", replace_current=True)
        self.assertEqual(2, replacement["role_generation"])
        self.assertNotEqual(first["init_nonce"], replacement["init_nonce"])
        stale = read_exact_epoch(
            **self.identity,
            role_lane="planner",
            role_generation=1,
            init_nonce=str(first["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("zcode_bootstrap_lifecycle_not_current", stale["verdict"])

    def test_contract_drift_blocks_old_current_but_allows_replacement_and_other_lane(self) -> None:
        self._init()
        first = self._reserve("coder")
        self._promote(first, agent_id="agent-coder-1")
        self.contract_path.write_text("# updated role init\n", encoding="utf-8")

        with self.assertRaises(LifecycleError) as stale_current:
            read_exact_epoch(
                **self.identity,
                role_lane="coder",
                role_generation=1,
                init_nonce=str(first["init_nonce"]),
                expected_state="current",
            )
        self.assertEqual("malformed_state", stale_current.exception.reason_code)

        unrelated = self._reserve("planner")
        self.assertEqual("pending", unrelated["verdict"])
        self.assertEqual(1, unrelated["role_generation"])

        replacement = self._reserve("coder", replace_current=True)
        self.assertEqual("pending", replacement["verdict"])
        self.assertEqual(2, replacement["role_generation"])
        self.assertNotEqual(first["init_nonce"], replacement["init_nonce"])
        self.assertEqual("current", self._promote(replacement, agent_id="agent-coder-2")["verdict"])
        refreshed = read_exact_epoch(
            **self.identity,
            role_lane="coder",
            role_generation=2,
            init_nonce=str(replacement["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("current", refreshed["verdict"])

    def test_abandon_consumes_generation_and_rejects_late_ack(self) -> None:
        self._init()
        first = self._reserve("architect")
        abandoned = abandon_pending(
            **self.identity,
            role_lane="architect",
            role_generation=1,
            init_nonce=str(first["init_nonce"]),
        )
        self.assertEqual("abandoned", abandoned["verdict"])
        with self.assertRaises(LifecycleError) as late_ack:
            self._promote(first, agent_id="late-agent")
        self.assertEqual("pending_identity_mismatch", late_ack.exception.reason_code)

        retry = self._reserve("architect")
        self.assertEqual(2, retry["role_generation"])
        self.assertNotEqual(first["init_nonce"], retry["init_nonce"])

    def test_reviewer_lanes_have_independent_lineage(self) -> None:
        self._init()
        risk = self._reserve("reviewer_code_risk")
        contracts = self._reserve("reviewer_code_contracts")
        self._promote(risk, agent_id="risk-1")
        self._promote(contracts, agent_id="contracts-1")
        risk_replacement = self._reserve("reviewer_code_risk", replace_current=True)
        self.assertEqual(2, risk_replacement["role_generation"])
        contracts_current = read_exact_epoch(
            **self.identity,
            role_lane="reviewer_code_contracts",
            role_generation=1,
            init_nonce=str(contracts["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("current", contracts_current["verdict"])

    def test_roots_session_and_plan_path_are_fail_closed(self) -> None:
        self._init()
        other_tooling = self.root / "other-tooling"
        other_tooling.mkdir()
        with self.assertRaises(LifecycleError) as wrong_tooling:
            read_exact_epoch(**{**self.identity, "tooling_root": str(other_tooling)})
        self.assertEqual("identity_mismatch", wrong_tooling.exception.reason_code)
        with self.assertRaises(LifecycleError) as wrong_session:
            init_epoch(**{**self.identity, "manager_session_identity": "manager-session-b"})
        self.assertEqual("identity_mismatch", wrong_session.exception.reason_code)

        outside_plan = self.root / "outside-plan.md"
        outside_plan.write_text("# outside\n", encoding="utf-8")
        with self.assertRaises(LifecycleError) as cross_root_plan:
            init_epoch(**self.identity, plan_path=outside_plan)
        self.assertEqual("cross_root", cross_root_plan.exception.reason_code)

        fresh_epoch = init_epoch(**{**self.identity, "team_epoch": "team-epoch-b"})
        self.assertEqual("epoch_current", fresh_epoch["verdict"])
        fresh_generation = reserve_agent(
            **{**self.identity, "team_epoch": "team-epoch-b"},
            role_lane="architect",
            contract_reads=self._contract_reads(),
        )
        self.assertEqual(1, fresh_generation["role_generation"])

    def test_optional_audit_handle_never_replaces_exact_lifecycle_carrier(self) -> None:
        audit_path = self.project_root / ".planveyor.zcode.agent.coder"
        audit_path.write_text("agentId=old-agent\n", encoding="utf-8")
        with self.assertRaises(LifecycleError) as absent_bootstrap:
            read_exact_epoch(**self.identity)
        self.assertEqual("missing_state", absent_bootstrap.exception.reason_code)

    def test_malformed_duplicate_oversized_and_nonregular_carriers_fail_closed(self) -> None:
        self._init()
        self.carrier_path.write_text(
            '{"schema_version":"zcode_bootstrap_lifecycle.v1","schema_version":"zcode_bootstrap_lifecycle.v1"}',
            encoding="utf-8",
        )
        with self.assertRaises(LifecycleError) as duplicate:
            read_exact_epoch(**self.identity)
        self.assertEqual("malformed_state", duplicate.exception.reason_code)

        self.carrier_path.write_bytes(b"x" * (MAX_CARRIER_BYTES + 1))
        with self.assertRaises(LifecycleError) as oversized:
            read_exact_epoch(**self.identity)
        self.assertEqual("malformed_state", oversized.exception.reason_code)

        self.carrier_path.unlink()
        directory = self.project_root / self.carrier_path.name
        directory.mkdir()
        with self.assertRaises(LifecycleError) as nonregular:
            read_exact_epoch(**self.identity)
        self.assertEqual("malformed_state", nonregular.exception.reason_code)

    def test_stale_carrier_generation_fails_before_work_admission(self) -> None:
        self._init()
        reservation = self._reserve("coder")
        payload = json.loads(self.carrier_path.read_text(encoding="utf-8"))
        payload["lanes"]["coder"]["generation_high_water"] = 0
        self.carrier_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(LifecycleError) as stale:
            read_exact_epoch(
                **self.identity,
                role_lane="coder",
                role_generation=int(reservation["role_generation"]),
                init_nonce=str(reservation["init_nonce"]),
                expected_state="current",
        )
        self.assertEqual("malformed_state", stale.exception.reason_code)

    def test_upward_generation_high_water_mismatch_fails_before_work_admission(self) -> None:
        self._init()
        reservation = self._reserve("coder")
        self._promote(reservation, agent_id="agent-coder")
        current = read_exact_epoch(
            **self.identity,
            role_lane="coder",
            role_generation=int(reservation["role_generation"]),
            init_nonce=str(reservation["init_nonce"]),
            expected_state="current",
        )
        self.assertEqual("current", current["verdict"])

        payload = json.loads(self.carrier_path.read_text(encoding="utf-8"))
        self.assertEqual(1, payload["lanes"]["coder"]["generation_high_water"])
        payload["lanes"]["coder"]["generation_high_water"] = 2
        self.carrier_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(LifecycleError) as stale:
            read_exact_epoch(
                **self.identity,
                role_lane="coder",
                role_generation=int(reservation["role_generation"]),
                init_nonce=str(reservation["init_nonce"]),
                expected_state="current",
            )
        self.assertEqual("malformed_state", stale.exception.reason_code)

    def test_cross_root_contract_manifest_fails_before_work_admission(self) -> None:
        self._init()
        reservation = self._reserve("coder")
        payload = json.loads(self.carrier_path.read_text(encoding="utf-8"))
        attempt = payload["lanes"]["coder"]["attempt"]
        attempt["expected_contract_reads"][0]["path"] = str(
            self.extra_contract_path
        )
        attempt["expected_contract_reads_digest"] = hashlib.sha256(
            json.dumps(
                attempt["expected_contract_reads"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.carrier_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(LifecycleError) as cross_root:
            read_exact_epoch(
                **self.identity,
                role_lane="coder",
                role_generation=int(reservation["role_generation"]),
                init_nonce=str(reservation["init_nonce"]),
                expected_state="pending",
            )
        self.assertEqual("cross_root", cross_root.exception.reason_code)


if __name__ == "__main__":
    unittest.main()

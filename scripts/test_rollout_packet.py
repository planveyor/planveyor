#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

try:
    from scripts.test_support.process_contract_fixtures import (
        NON_GIT_ROOT_SKIP_REASON,
        inside_git_work_tree,
        run_zsh_fixture,
        standalone_git_root,
    )
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import (
        NON_GIT_ROOT_SKIP_REASON,
        inside_git_work_tree,
        run_zsh_fixture,
        standalone_git_root,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "rollout_packet.py"
PACKETIZATION_GATE_SCRIPT = REPO_ROOT / "scripts" / "post_merge_packetization_gate.py"
CARRIER_BEGIN = "<!-- planveyor:rollout_packet_carrier.v1:begin"
CARRIER_END = "planveyor:rollout_packet_carrier.v1:end -->"


def _structured_carrier_text(
    plan_rel: str,
    items: list[dict[str, object]],
    *,
    target_repo: str = "planveyor",
    extra_top_level: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "rollout_packet_import": {
            "source_repo": "current-consumer",
            "source_root": "/tmp/source",
            "target_repo": target_repo,
            "imported_at": "2026-08-08T13:30:00",
            "target_import_receipt": plan_rel,
            "target_local_plan": plan_rel,
            "queue_result": "not_queued_yet",
            "packet_count": len(items),
            "excluded_packet_count": 0,
            "packet_rows": "see ## Imported rollout packets",
        },
        "rollout_packet_outcomes": {
            "schema_version": "rollout_packet_outcomes.v1",
            "items": items,
        },
    }
    if extra_top_level:
        payload.update(extra_top_level)
    return f"{CARRIER_BEGIN}\n{json.dumps(payload, indent=2)}\n{CARRIER_END}\n"


def _structured_item(
    packet_id: str,
    packet_path: str,
    plan_rel: str,
    *,
    decision_state: str = "pending",
    outcome: str | None = None,
) -> dict[str, object]:
    return {
        "packet_id": packet_id,
        "packet_path": packet_path,
        "target_import_receipt": plan_rel,
        "target_local_plan": plan_rel,
        "decision_state": decision_state,
        "outcome": outcome,
    }


def _raw_structured_carrier_text(payload: str) -> str:
    return f"{CARRIER_BEGIN}\n{payload}\n{CARRIER_END}\n"


def _structured_negative_carrier_matrix(
    plan_rel: str,
    packet_id: str,
    packet_path: str,
    *,
    target_repo: str = "planveyor",
) -> list[tuple[str, str, str, str]]:
    base = _carrier_payload_from_text(
        _structured_carrier_text(
            plan_rel,
            [_structured_item(packet_id, packet_path, plan_rel)],
            target_repo=target_repo,
        )
    )

    def clone_payload() -> dict[str, object]:
        return json.loads(json.dumps(base))

    def render(payload: dict[str, object]) -> str:
        return _raw_structured_carrier_text(json.dumps(payload, indent=2))

    raw_payload = json.dumps(base, indent=2)
    duplicate_raw_payload = (
        "{"
        f'"rollout_packet_import": {json.dumps(base["rollout_packet_import"])}, '
        f'"rollout_packet_import": {json.dumps(base["rollout_packet_import"])}, '
        f'"rollout_packet_outcomes": {json.dumps(base["rollout_packet_outcomes"])}'
        "}"
    )

    unknown_top_level = clone_payload()
    unknown_top_level["unexpected"] = True
    unknown_import_key = clone_payload()
    unknown_import_key["rollout_packet_import"]["unexpected"] = True
    unknown_outcomes_key = clone_payload()
    unknown_outcomes_key["rollout_packet_outcomes"]["unexpected"] = True
    unknown_item_key = clone_payload()
    unknown_item_key["rollout_packet_outcomes"]["items"][0]["unexpected"] = True
    pending_with_outcome = clone_payload()
    pending_with_outcome["rollout_packet_outcomes"]["items"][0]["outcome"] = "adopted"
    recorded_with_null = clone_payload()
    recorded_with_null["rollout_packet_outcomes"]["items"][0]["decision_state"] = "recorded"
    recorded_with_unknown_outcome = clone_payload()
    recorded_with_unknown_outcome["rollout_packet_outcomes"]["items"][0]["decision_state"] = "recorded"
    recorded_with_unknown_outcome["rollout_packet_outcomes"]["items"][0]["outcome"] = "unexpected"
    duplicate_identity = clone_payload()
    duplicate_items = duplicate_identity["rollout_packet_outcomes"]["items"]
    duplicate_items[0]["decision_state"] = "recorded"
    duplicate_items[0]["outcome"] = "adopted"
    conflicting_item = dict(duplicate_items[0])
    conflicting_item["outcome"] = "cancelled"
    duplicate_items.append(conflicting_item)
    duplicate_identity["rollout_packet_import"]["packet_count"] = 2
    top_level_pointer_mismatch = clone_payload()
    top_level_pointer_mismatch["rollout_packet_import"]["target_local_plan"] = "docs/plans/other.md"
    item_pointer_mismatch = clone_payload()
    item_pointer_mismatch["rollout_packet_outcomes"]["items"][0]["target_local_plan"] = "docs/plans/other.md"
    near_packet_path = clone_payload()
    near_packet_path["rollout_packet_outcomes"]["items"][0]["packet_path"] = (
        "docs/rollout_packets/negative-near.md"
    )
    invalid_schema = clone_payload()
    invalid_schema["rollout_packet_outcomes"]["schema_version"] = "rollout_packet_outcomes.v0"

    return [
        (
            "duplicate_raw_json_key",
            _raw_structured_carrier_text(duplicate_raw_payload),
            "duplicate JSON key",
            "duplicate JSON key",
        ),
        (
            "nan_constant",
            _raw_structured_carrier_text(raw_payload.replace('"packet_count": 1', '"packet_count": NaN', 1)),
            "non-finite JSON constant `NaN`",
            "non-finite JSON constant `NaN`",
        ),
        (
            "infinity_constant",
            _raw_structured_carrier_text(raw_payload.replace('"packet_count": 1', '"packet_count": Infinity', 1)),
            "non-finite JSON constant `Infinity`",
            "non-finite JSON constant `Infinity`",
        ),
        (
            "missing_begin_sentinel",
            f"{raw_payload}\n{CARRIER_END}\n",
            "exactly one begin and one end sentinel",
            "exactly one begin and one end sentinel",
        ),
        (
            "missing_end_sentinel",
            f"{CARRIER_BEGIN}\n{raw_payload}\n",
            "exactly one begin and one end sentinel",
            "exactly one begin and one end sentinel",
        ),
        (
            "duplicate_begin_sentinel",
            f"{CARRIER_BEGIN}\n{CARRIER_BEGIN}\n{raw_payload}\n{CARRIER_END}\n",
            "exactly one begin and one end sentinel",
            "exactly one begin and one end sentinel",
        ),
        (
            "duplicate_end_sentinel",
            f"{CARRIER_BEGIN}\n{raw_payload}\n{CARRIER_END}\n{CARRIER_END}\n",
            "exactly one begin and one end sentinel",
            "exactly one begin and one end sentinel",
        ),
        (
            "reordered_sentinels",
            f"{CARRIER_END}\n{raw_payload}\n{CARRIER_BEGIN}\n",
            "sentinels must be ordered and non-nesting",
            "sentinels must be ordered and non-nesting",
        ),
        (
            "invalid_schema_version",
            render(invalid_schema),
            "rollout_packet_outcomes.schema_version is invalid",
            "rollout_packet_outcomes.schema_version is invalid",
        ),
        (
            "unknown_top_level_key",
            render(unknown_top_level),
            "structured carrier must have exactly the documented keys",
            "structured carrier must have exactly the documented keys",
        ),
        (
            "unknown_import_key",
            render(unknown_import_key),
            "rollout_packet_import must have exactly the documented keys",
            "rollout_packet_import must have exactly the documented keys",
        ),
        (
            "unknown_outcomes_key",
            render(unknown_outcomes_key),
            "rollout_packet_outcomes must have exactly the documented keys",
            "rollout_packet_outcomes must have exactly the documented keys",
        ),
        (
            "unknown_item_key",
            render(unknown_item_key),
            "rollout_packet_outcomes.items[0] must have exactly the documented keys",
            "rollout_packet_outcomes.items[0] must have exactly the documented keys",
        ),
        (
            "pending_with_outcome",
            render(pending_with_outcome),
            "pending state requires outcome=null",
            "pending state requires outcome=null",
        ),
        (
            "recorded_with_null",
            render(recorded_with_null),
            "recorded state requires a canonical outcome",
            "recorded state requires a canonical outcome",
        ),
        (
            "recorded_with_unknown_outcome",
            render(recorded_with_unknown_outcome),
            "recorded state requires a canonical outcome",
            "recorded state requires a canonical outcome",
        ),
        (
            "duplicate_item_identity",
            render(duplicate_identity),
            "must not contain duplicate packet identities",
            "must not contain duplicate packet identities",
        ),
        (
            "top_level_pointer_mismatch",
            render(top_level_pointer_mismatch),
            "rollout_packet_import pointer pair must equal the current target plan",
            "rollout_packet_import pointer pair must equal the current target plan",
        ),
        (
            "item_pointer_mismatch",
            render(item_pointer_mismatch),
            "rollout_packet_outcomes.items[0] pointer pair must equal the current target plan",
            "rollout_packet_outcomes.items[0] pointer pair must equal the current target plan",
        ),
        (
            "near_packet_path",
            render(near_packet_path),
            "outcome-set requires exactly one matching packet id/path item",
            "target readback found structured carriers but no exact packet item",
        ),
    ]


def _carrier_payload_from_text(text: str) -> dict[str, object]:
    start = text.index(CARRIER_BEGIN) + len(CARRIER_BEGIN)
    end = text.index(CARRIER_END, start)
    return json.loads(text[start:end].strip())


def _carrier_outer_bytes(raw: bytes) -> tuple[bytes, bytes]:
    begin = raw.index(CARRIER_BEGIN.encode("utf-8"))
    payload_start = raw.index(b"\n", begin) + 1
    payload_end = raw.index(CARRIER_END.encode("utf-8"), payload_start)
    return raw[:payload_start], raw[payload_end:]


def _packet_text(
    *,
    packet_id: str = "260329_1545_planveyor_helper",
    target_repo: str = "planveyor",
    status: str = "open",
    header_status: str | None = None,
    source_plan: str = "docs/plans/260329_0028_process_rollout_packet_helper_scaffold_without_cross_repo_writes.md",
    date: str = "2026-03-29 15:45",
    target_import_receipt: str | None = None,
    target_local_plan: str | None = None,
    context_target_import_receipt: str | None = None,
    context_target_local_plan: str | None = None,
    reason: str | None = None,
    include_source_acknowledgement: bool = False,
    extra_body: str = "",
    source_range: str | None = None,
    source_revision: str | None = None,
    source_artifacts: list[str] | None = None,
    target_writable_carriers: list[str] | None = None,
    target_kind: str = "plan_adoption",
) -> str:
    packet_meta = {
        "packet_meta": {
            "id": packet_id,
            "source_repo": "current-consumer",
            "source_plan": source_plan,
            "target_repo": target_repo,
            "target_kind": target_kind,
            "status": status,
            "depends_on_packets": [],
            "queue_after_import": True,
            "suggested_target_plan_slug": "helper_scaffold",
            "target_import_receipt": target_import_receipt,
            "target_local_plan": target_local_plan,
        }
    }
    if include_source_acknowledgement or reason is not None:
        packet_meta["packet_meta"]["source_acknowledgement"] = {
            "status": status,
            "target_import_receipt": target_import_receipt,
            "target_local_plan": target_local_plan,
            "reason": reason,
            "acknowledged_at": "2026-03-29T15:45:00",
        }
    if source_range is not None:
        packet_meta["packet_meta"]["source_range"] = source_range
    if source_revision is not None:
        packet_meta["packet_meta"]["source_revision"] = source_revision
    if source_artifacts is not None:
        packet_meta["packet_meta"]["source_artifacts"] = source_artifacts
    if target_writable_carriers is not None:
        packet_meta["packet_meta"]["target_writable_carriers"] = target_writable_carriers
    context_target_import_receipt = context_target_import_receipt if context_target_import_receipt is not None else target_import_receipt
    context_target_local_plan = context_target_local_plan if context_target_local_plan is not None else target_local_plan
    target_import_receipt_line = (
        f"`{context_target_import_receipt}`"
        if context_target_import_receipt
        else "`N/A (why=not imported yet; default target_import_receipt == target_local_plan after target import)`"
    )
    target_local_plan_line = (
        f"`{context_target_local_plan}`"
        if context_target_local_plan
        else "`N/A (why=not imported yet; target repo has not materialized the adoption plan/import receipt)`"
    )
    return textwrap.dedent(
        f"""\
        # Rollout packet: Helper Scaffold

        **Date:** {date}
        **Source repo:** current-consumer
        **Target repo:** {target_repo}
        **Target kind:** {target_kind}
        **Status:** {header_status or status}

        **Context links (source of truth):**
        - Source plan: `{source_plan}`
        - Target import receipt: {target_import_receipt_line}
        - Target local plan: {target_local_plan_line}

        ## Meta (machine-readable JSON)
        ```json
        {json.dumps(packet_meta, indent=2)}
        ```
        {extra_body}
        """
    )


def _lint_sections(extra: str = "") -> str:
    sections = textwrap.dedent(
        """\

        ## Source provenance
        - Relation: `created-here`
        - Thread ID: `N/A (why=test fixture)`
        - Session SID: `N/A (why=test fixture)`
        - Launch surface: `codex-cli`
        - Captured from: `manual-owner`
        - Captured at: `2026-03-29T12:45:00Z`
        - Target import expectation: target repo records source packet path/id and one local outcome

        ## Why target repo action exists
        - Shared/source change: test fixture
        - Why target repo must react: test fixture
        - Why this is not safe/clean as live cross-repo write: test fixture

        ## Source artifacts
        - Exact source files/contracts: `scripts/rollout_packet.py`
        - Required canon/docs/tests from source repo: `scripts/test_rollout_packet.py`
        - Bounded proof that the shared change is already materialized: test fixture

        ## Target writable carriers
        - Expected target-local files/surfaces: `docs/plans/helper_scaffold.md`
        - Required local plan/import receipt: default same-path carrier
        - Queue after import: `yes`
        - Required-check / branch-protection closeout: `N/A (why=test fixture)`

        ## Import recipe
        1. Open this packet in the target repo context.
        2. Materialize a target-local adoption plan as the import receipt.

        ## Stop conditions / not-in-scope
        - Do not write target repo files from source repo.
        - Do not treat this packet as executable queue item.

        ## Adoption completion signal
        - Receipt path: same as target local plan path by default
        - Target local plan path:
        - Local terminal condition:
        - Source-side follow-up needed after import/closure: `yes`

        ## Source-side acknowledgement
        - `N/A (why=packet is still open; source-side ack is written by planveyor_rollout_packet_ack)`
        """
    )
    return sections + extra


def _current_delivery_sections(*, source_artifacts: list[str], target_writable_carriers: list[str]) -> str:
    source_lines = "\n".join(f"- `{path}`" for path in source_artifacts)
    target_lines = "\n".join(f"- `{path}`" for path in target_writable_carriers)
    return textwrap.dedent(
        f"""\

        ## Source provenance
        - Relation: `test fixture`

        ## Why target repo action exists
        - Structural source-side handoff only.

        ## Source artifacts
        {source_lines}

        ## Target writable carriers
        {target_lines}

        ## Import recipe
        - Target repo owns any import/adoption.

        ## Stop conditions / not-in-scope
        - No sibling read or write occurs here.

        ## Adoption completion signal
        - Target-local outcome remains target-local.

        ## Source-side acknowledgement
        - `N/A (why=packet is open)`
        """
    )


def _replace_meta_payload(text: str, payload: dict[str, object]) -> str:
    marker = "```json\n"
    start = text.index(marker) + len(marker)
    end = text.index("```", start)
    return f"{text[:start]}{json.dumps(payload, indent=2)}{text[end:]}"


def _malformed_packet_text(*, target_repo: str = "consumer-fixture") -> str:
    return textwrap.dedent(
        f"""\
        # Rollout packet: Broken Packet

        **Date:** 2026-03-29 15:46
        **Source repo:** current-consumer
        **Target repo:** {target_repo}
        **Target kind:** plan_adoption
        **Status:** open

        ## Meta (machine-readable JSON)
        ```json
        {{
          "packet_meta": {{
            "id": "260329_1546_broken",
            "target_repo": "{target_repo}",
          }}
        }}
        ```
        """
    )


class RolloutPacketCliTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_file(self, root: Path, relative_path: str, content: str) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _packet_meta_from_text(self, text: str) -> dict[str, object]:
        marker = "```json\n"
        start = text.index(marker) + len(marker)
        end = text.index("```", start)
        payload = json.loads(text[start:end])
        return payload["packet_meta"]

    def _run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_with_tooling(root, root, *args)

    def _run_with_tooling(self, root: Path, tooling_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(root),
                "--tooling-root",
                str(tooling_root),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _lint_plan(self, plan_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "scripts" / "plan_lint.py"), str(plan_path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_structured_plan(
        self,
        root: Path,
        plan_rel: str,
        items: list[dict[str, object]],
        *,
        target_repo: str = "planveyor",
        extra_before: str = "# Plan\n\n",
        extra_after: str = "\n## Notes\n- outside carrier bytes stay intact\n",
    ) -> Path:
        return self._write_file(
            root,
            plan_rel,
            extra_before + _structured_carrier_text(plan_rel, items, target_repo=target_repo) + extra_after,
        )

    def test_lint_valid_packet_json_and_no_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text(extra_body=_lint_sections()))
            before = packet_path.read_text(encoding="utf-8")

            text_result = self._run(root, "lint", packet_relative)
            json_result = self._run(root, "lint", packet_relative, "--json")

            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            self.assertIn("rollout-packet-lint: OK", text_result.stdout)
            self.assertIn("files checked: 1", text_result.stdout)
            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            payload = json.loads(json_result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["files_checked"], 1)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_lint_rejects_noncanonical_target_repo_carriers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            canonical_text = _packet_text(
                target_repo="consumer-fixture",
                extra_body=_lint_sections(),
            )
            self._write_file(root, "docs/rollout_packets/canonical.md", canonical_text)
            self._write_file(
                root,
                "docs/rollout_packets/header_alias.md",
                canonical_text.replace(
                    "**Target repo:** consumer-fixture\n",
                    "**Target repo:** consumer_fixture\n",
                    1,
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/meta_alias.md",
                canonical_text.replace(
                    '"target_repo": "consumer-fixture",',
                    '"target_repo": "consumer_fixture",',
                    1,
                ),
            )
            for label, value in (
                ("space", "consumer fixture"),
                ("slash", "consumer/fixture"),
                ("quote", 'consumer"fixture'),
                ("tab", "consumer\tfixture"),
            ):
                self._write_file(
                    root,
                    f"docs/rollout_packets/header_{label}.md",
                    canonical_text.replace(
                        "**Target repo:** consumer-fixture\n",
                        f"**Target repo:** {value}\n",
                        1,
                    ),
                )
                self._write_file(
                    root,
                    f"docs/rollout_packets/meta_{label}.md",
                    canonical_text.replace(
                        '"target_repo": "consumer-fixture",',
                        f'"target_repo": {json.dumps(value)},',
                        1,
                    ),
                )
            newline_target_repo = json.dumps("consumer\nfixture")
            self._write_file(
                root,
                "docs/rollout_packets/meta_newline.md",
                canonical_text.replace(
                    '"target_repo": "consumer-fixture",',
                    f'"target_repo": {newline_target_repo},',
                    1,
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/header_collapse.md",
                canonical_text.replace(
                    "**Target repo:** consumer-fixture\n",
                    "**Target repo:** ___\n",
                    1,
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/meta_collapse.md",
                canonical_text.replace(
                    '"target_repo": "consumer-fixture",',
                    '"target_repo": "---",',
                    1,
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/meta_padded.md",
                canonical_text.replace(
                    '"target_repo": "consumer-fixture",',
                    '"target_repo": " consumer-fixture",',
                    1,
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/meta_number.md",
                canonical_text.replace(
                    "**Target repo:** consumer-fixture\n",
                    "**Target repo:** 123\n",
                    1,
                ).replace(
                    '"target_repo": "consumer-fixture",',
                    '"target_repo": 123,',
                    1,
                ),
            )

            canonical_result = self._run(root, "lint", "docs/rollout_packets/canonical.md", "--json")

            self.assertEqual(canonical_result.returncode, 0, canonical_result.stderr)
            self.assertTrue(json.loads(canonical_result.stdout)["ok"])
            self.assertIn('"source_repo": "current-consumer"', canonical_text)

            for packet_relative, carrier, expected_literal in (
                ("docs/rollout_packets/header_alias.md", "header Target repo", "consumer_fixture"),
                ("docs/rollout_packets/meta_alias.md", "packet_meta.target_repo", "consumer_fixture"),
                *((f"docs/rollout_packets/header_{label}.md", "header Target repo", value) for label, value in (
                    ("space", "consumer fixture"),
                    ("slash", "consumer/fixture"),
                    ("quote", 'consumer"fixture'),
                    ("tab", "consumer\tfixture"),
                )),
                *((f"docs/rollout_packets/meta_{label}.md", "packet_meta.target_repo", value) for label, value in (
                    ("space", "consumer fixture"),
                    ("slash", "consumer/fixture"),
                    ("quote", 'consumer"fixture'),
                    ("tab", "consumer\tfixture"),
                )),
                ("docs/rollout_packets/meta_newline.md", "packet_meta.target_repo", "consumer\nfixture"),
                ("docs/rollout_packets/header_collapse.md", "header Target repo", "___"),
                ("docs/rollout_packets/meta_collapse.md", "packet_meta.target_repo", "---"),
                ("docs/rollout_packets/meta_padded.md", "packet_meta.target_repo", " consumer-fixture"),
                ("docs/rollout_packets/meta_number.md", "packet_meta.target_repo", 123),
            ):
                with self.subTest(packet_relative=packet_relative):
                    result = self._run(root, "lint", packet_relative, "--json")

                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    findings = json.loads(result.stdout)["findings"]
                    errors = [finding for finding in findings if finding["severity"] == "error"]
                    noncanonical = [finding for finding in errors if finding["code"] == "noncanonical_target_repo"]
                    self.assertTrue(noncanonical, errors)
                    self.assertIn(carrier, noncanonical[0]["message"])
                    self.assertIn(
                        f"`{json.dumps(expected_literal, ensure_ascii=False)}`",
                        noncanonical[0]["message"],
                    )

    def test_lint_requires_exact_current_consumer_source_literal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            canonical_text = _packet_text(target_repo="consumer-fixture", extra_body=_lint_sections())
            self._write_file(root, "docs/rollout_packets/canonical.md", canonical_text)
            cases = (
                ("header_alias", "header Source repo", "**Source repo:** current-consumer\n", "**Source repo:** current_consumer\n", "current_consumer"),
                ("meta_alias", "packet_meta.source_repo", '"source_repo": "current-consumer",', '"source_repo": "current_consumer",', "current_consumer"),
                ("header_legacy", "header Source repo", "**Source repo:** current-consumer\n", "**Source repo:** planveyor\n", "planveyor"),
                ("meta_legacy", "packet_meta.source_repo", '"source_repo": "current-consumer",', '"source_repo": "planveyor",', "planveyor"),
            )

            for label, carrier, needle, replacement, _literal in cases:
                self._write_file(
                    root,
                    f"docs/rollout_packets/{label}.md",
                    canonical_text.replace(needle, replacement, 1),
                )

            for label, carrier, _needle, _replacement, literal in cases:
                with self.subTest(label=label):
                    result = self._run(root, "lint", f"docs/rollout_packets/{label}.md", "--json")

                    self.assertEqual(result.returncode, 1, result.stderr)
                    findings = json.loads(result.stdout)["findings"]
                    errors = [finding for finding in findings if finding["code"] == "invalid_source_repo"]
                    self.assertTrue(errors, findings)
                    self.assertIn(carrier, errors[0]["message"])
                    self.assertIn("current-consumer", errors[0]["message"])
                    self.assertIn(literal, errors[0]["message"])

    def test_lint_accepts_literal_target_repo_that_matches_impact_vocabulary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/shared-consumer.md"
            self._write_file(
                root,
                packet_relative,
                _packet_text(target_repo="shared-consumer", extra_body=_lint_sections()),
            )

            result = self._run(root, "lint", packet_relative, "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["findings"], [])

    def test_lint_reports_header_meta_section_json_and_enum_errors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            valid_text = _packet_text(extra_body=_lint_sections())
            self._write_file(
                root,
                "docs/rollout_packets/missing_header.md",
                valid_text.replace("**Date:** 2026-03-29 15:45\n", "", 1),
            )
            self._write_file(
                root,
                "docs/rollout_packets/duplicate_header.md",
                valid_text.replace("**Status:** open\n", "**Status:** open\n**Status:** imported\n", 1),
            )
            self._write_file(
                root,
                "docs/rollout_packets/malformed_json.md",
                valid_text.replace('"target_repo": "planveyor",', '"target_repo": "planveyor",,', 1),
            )
            self._write_file(
                root,
                "docs/rollout_packets/non_object_meta.md",
                _replace_meta_payload(valid_text, {"packet_meta": []}),
            )
            missing_key_payload = {"packet_meta": dict(self._packet_meta_from_text(valid_text))}
            missing_key_payload["packet_meta"].pop("target_kind")
            self._write_file(
                root,
                "docs/rollout_packets/missing_meta_key.md",
                _replace_meta_payload(valid_text, missing_key_payload),
            )
            self._write_file(
                root,
                "docs/rollout_packets/missing_section.md",
                valid_text.replace("## Import recipe\n", "## Import recipe missing\n", 1),
            )
            self._write_file(
                root,
                "docs/rollout_packets/bad_enum.md",
                valid_text.replace('"target_kind": "plan_adoption"', '"target_kind": "not_a_kind"', 1),
            )

            result = self._run(root, "lint", "docs/rollout_packets", "--json")

            self.assertEqual(result.returncode, 1, result.stdout)
            payload = json.loads(result.stdout)
            codes = {finding["code"] for finding in payload["findings"] if finding["severity"] == "error"}
            self.assertIn("missing_header", codes)
            self.assertIn("duplicate_header", codes)
            self.assertIn("invalid_json", codes)
            self.assertIn("invalid_packet_meta", codes)
            self.assertIn("missing_meta_key", codes)
            self.assertIn("missing_section", codes)
            self.assertIn("bad_target_kind", codes)

    def test_lint_reports_context_and_header_meta_mismatches(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/rollout_packets/header_drift.md",
                _packet_text(header_status="imported", extra_body=_lint_sections()),
            )
            self._write_file(
                root,
                "docs/rollout_packets/context_drift.md",
                _packet_text(
                    context_target_import_receipt="docs/plans/visible_import.md",
                    extra_body=_lint_sections(),
                ),
            )

            result = self._run(root, "lint", "docs/rollout_packets")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("header_meta_mismatch", result.stdout)
            self.assertIn("context_meta_mismatch", result.stdout)

    def test_lint_scope_missing_path_mixed_batch_and_warning_only_extra_section(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/rollout_packets/valid.md",
                _packet_text(extra_body=_lint_sections("\n## Backlog wave classification\n- legacy extension\n")),
            )
            self._write_file(
                root,
                "docs/rollout_packets/bad.md",
                _packet_text(header_status="imported", extra_body=_lint_sections()),
            )
            self._write_file(root, "docs/rollout_packets/_template.md", "not a live packet\n")

            no_scope = self._run(root, "lint")
            missing = self._run(root, "lint", "docs/rollout_packets/missing.md", "--json")
            mixed = self._run(root, "lint", "docs/rollout_packets", "--json")
            warning_only = self._run(root, "lint", "docs/rollout_packets/valid.md")

            self.assertEqual(no_scope.returncode, 1, no_scope.stdout)
            self.assertIn("missing_scope", no_scope.stdout)
            self.assertEqual(missing.returncode, 1, missing.stdout)
            self.assertEqual(json.loads(missing.stdout)["findings"][0]["code"], "missing")
            self.assertEqual(mixed.returncode, 1, mixed.stdout)
            mixed_payload = json.loads(mixed.stdout)
            self.assertEqual(mixed_payload["files_checked"], 2)
            self.assertTrue(any(finding["code"] == "extra_section" for finding in mixed_payload["findings"]))
            self.assertTrue(any(finding["code"] == "header_meta_mismatch" for finding in mixed_payload["findings"]))
            self.assertEqual(warning_only.returncode, 0, warning_only.stdout)
            self.assertIn("rollout-packet-lint: OK", warning_only.stdout)
            self.assertIn("warning docs/rollout_packets/valid.md: extra_section", warning_only.stdout)

    def test_lint_all_treats_historical_section_shape_as_warning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            historical = _packet_text(
                target_import_receipt="docs/plans/packet_inbox_adoption.md",
                target_local_plan="docs/plans/packet_inbox_adoption.md",
                status="imported",
                extra_body=textwrap.dedent(
                    """\

                    ## Source artifacts
                    - `scripts/rollout_packet.py`

                    ## Target writable carriers
                    - `docs/plans/packet_inbox_adoption.md`

                    ## Source-side acknowledgement
                    - [2026-03-29 15:45 MSK] source-side acknowledgement: status=`imported`; target_import_receipt=`docs/plans/packet_inbox_adoption.md`; target_local_plan=`docs/plans/packet_inbox_adoption.md`; reason=`N/A (why=imported uses target-local plan/import receipt)`.
                    """
                ),
            )
            self._write_file(root, "docs/rollout_packets/historical.md", historical)

            result = self._run(root, "lint", "--all", "--json")

            self.assertEqual(result.returncode, 0, result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["files_checked"], 1)
            self.assertTrue(payload["findings"])
            self.assertEqual({finding["severity"] for finding in payload["findings"]}, {"warning"})
            self.assertIn("missing_section", {finding["code"] for finding in payload["findings"]})

    def test_rollout_packet_lint_wrapper_help_is_registered(self) -> None:
        result = run_zsh_fixture(
            (
                "source scripts/planveyor.zsh; "
                "whence -w planveyor_rollout_packet_lint; "
                "_planveyor_help_cmd_usage planveyor_rollout_packet_lint; "
                "_planveyor_help_cmd_example planveyor_rollout_packet_lint; "
                "_planveyor_help_cmd_summary planveyor_rollout_packet_lint"
            ),
            cwd=REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("planveyor_rollout_packet_lint: function", result.stdout)
        self.assertIn("planveyor_rollout_packet_lint (--all | docs/rollout_packets/<packet>.md|docs/rollout_packets)", result.stdout)
        self.assertIn("planveyor_rollout_packet_lint --all --json", result.stdout)
        self.assertIn("grammar lint", result.stdout)

    def test_ack_imported_updates_header_meta_context_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text())

            # The receipt stamp follows the local time zone of the run, not a fixed one.
            with mock.patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
                result = self._run(
                    root,
                    "ack",
                    "--packet",
                    packet_relative,
                    "--status",
                    "imported",
                    "--target-plan",
                    "docs/plans/packet_inbox_adoption.md",
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Result: source-side acknowledgement written", result.stdout)
            text = packet_path.read_text(encoding="utf-8")
            meta = self._packet_meta_from_text(text)
            self.assertIn("**Status:** imported", text)
            self.assertIn("- Target import receipt: `docs/plans/packet_inbox_adoption.md`", text)
            self.assertIn("- Target local plan: `docs/plans/packet_inbox_adoption.md`", text)
            self.assertIn("source-side acknowledgement: status=`imported`", text)
            self.assertRegex(
                text,
                r"(?m)^- \[\d{4}-\d{2}-\d{2} \d{2}:\d{2} \+0900\] source-side acknowledgement: status=`imported`",
            )
            self.assertEqual(meta["status"], "imported")
            self.assertEqual(meta["target_import_receipt"], "docs/plans/packet_inbox_adoption.md")
            self.assertEqual(meta["target_local_plan"], "docs/plans/packet_inbox_adoption.md")
            self.assertEqual(meta["source_acknowledgement"]["status"], "imported")

            query_result = self._run(root, "query", "--status", "imported", "--json")

            self.assertEqual(query_result.returncode, 0, query_result.stderr)
            query_payload = json.loads(query_result.stdout)
            self.assertEqual(query_payload["packets"][0]["target_adoption_state"], "awaiting-target-outcome")

    def test_ack_imported_is_idempotent_for_same_target_plan_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(
                root,
                packet_relative,
                _packet_text(
                    status="imported",
                    target_import_receipt="docs/plans/packet_inbox_adoption.md",
                    target_local_plan="docs/plans/packet_inbox_adoption.md",
                    reason=None,
                    include_source_acknowledgement=True,
                ),
            )
            before = packet_path.read_text(encoding="utf-8")

            result = self._run(
                root,
                "ack",
                "--packet",
                packet_relative,
                "--status",
                "imported",
                "--target-plan",
                "docs/plans/packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Result: source-side acknowledgement already recorded", result.stdout)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_ack_imported_rejects_different_target_plan_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(
                root,
                packet_relative,
                _packet_text(
                    status="imported",
                    target_import_receipt="docs/plans/packet_inbox_adoption.md",
                    target_local_plan="docs/plans/packet_inbox_adoption.md",
                    include_source_acknowledgement=True,
                ),
            )
            before = packet_path.read_text(encoding="utf-8")

            result = self._run(
                root,
                "ack",
                "--packet",
                packet_relative,
                "--status",
                "imported",
                "--target-plan",
                "docs/plans/different_packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("packet status must be open before ack; found `imported`", result.stderr)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_ack_superseded_and_cancelled_require_reason_and_leave_pointers_unset(self) -> None:
        for status in ("superseded", "cancelled"):
            with self.subTest(status=status), tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
                root = Path(tmpdir)
                packet_relative = f"docs/rollout_packets/{status}_packet.md"
                packet_path = self._write_file(root, packet_relative, _packet_text(packet_id=f"{status}_packet"))

                missing_reason = self._run(root, "ack", "--packet", packet_relative, "--status", status)

                self.assertEqual(missing_reason.returncode, 1, missing_reason.stdout)
                self.assertIn(f"{status} ack requires --reason", missing_reason.stderr)
                self.assertIn('"status": "open"', packet_path.read_text(encoding="utf-8"))

                result = self._run(
                    root,
                    "ack",
                    "--packet",
                    packet_relative,
                    "--status",
                    status,
                    "--reason",
                    "target repo already handled this packet locally",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                text = packet_path.read_text(encoding="utf-8")
                meta = self._packet_meta_from_text(text)
                self.assertIn(f"**Status:** {status}", text)
                self.assertIn("reason=`target repo already handled this packet locally`", text)
                self.assertEqual(meta["status"], status)
                self.assertIsNone(meta["target_import_receipt"])
                self.assertIsNone(meta["target_local_plan"])

    def test_ack_rejects_unknown_status_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text())
            before = packet_path.read_text(encoding="utf-8")

            result = self._run(root, "ack", "--packet", packet_relative, "--status", "adopted")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("unknown ack status `adopted`", result.stderr)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_ack_rejects_imported_missing_or_invalid_target_plan_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text())

            for args, message in (
                (("ack", "--packet", packet_relative, "--status", "imported"), "imported ack requires --target-plan"),
                (
                    (
                        "ack",
                        "--packet",
                        packet_relative,
                        "--status",
                        "imported",
                        "--target-plan",
                        "docs/not_plans/packet_inbox_adoption.md",
                    ),
                    "target plan path must stay under docs/plans/",
                ),
                (
                    (
                        "ack",
                        "--packet",
                        packet_relative,
                        "--status",
                        "imported",
                        "--target-plan",
                        "/tmp/packet_inbox_adoption.md",
                    ),
                    "target plan path must be repo-relative under docs/plans/",
                ),
            ):
                with self.subTest(args=args):
                    before = packet_path.read_text(encoding="utf-8")
                    result = self._run(root, *args)

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn(message, result.stderr)
                    self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_ack_rejects_non_packet_path_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_file(root, "docs/plans/example.md", "# Not a packet\n")

            result = self._run(
                root,
                "ack",
                "--packet",
                "docs/plans/example.md",
                "--status",
                "imported",
                "--target-plan",
                "docs/plans/packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("packet path must stay under docs/rollout_packets/", result.stderr)
            self.assertEqual(plan_path.read_text(encoding="utf-8"), "# Not a packet\n")

    def test_ack_rejects_target_repo_execution_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir(parents=True)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(tooling_root, packet_relative, _packet_text())
            before = packet_path.read_text(encoding="utf-8")

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "ack",
                "--packet",
                packet_relative,
                "--status",
                "imported",
                "--target-plan",
                "docs/plans/packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("rollout packet helpers are source-local only", result.stderr)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_ack_rejects_non_open_packet_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text(status="imported"))
            before = packet_path.read_text(encoding="utf-8")

            result = self._run(
                root,
                "ack",
                "--packet",
                packet_relative,
                "--status",
                "cancelled",
                "--reason",
                "duplicate",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("packet status must be open before ack; found `imported`", result.stderr)
            self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_query_json_lists_explicit_fields_with_status_filter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            root.mkdir(exist_ok=True)
            standalone_git_root(root)
            fixture_git = self._git(root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), root.resolve())

            self._write_file(
                root,
                "docs/rollout_packets/open_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_open", target_repo="planveyor"),
            )
            tracked_packet = self._git(root, "add", "--", 'docs/rollout_packets/open_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            self._write_file(
                root,
                "docs/rollout_packets/imported_packet.md",
                _packet_text(
                    packet_id="260329_1546_planveyor_imported",
                    target_repo="consumer-fixture",
                    status="imported",
                    target_import_receipt="docs/plans/packet_inbox_adoption.md",
                    target_local_plan="docs/plans/packet_inbox_adoption.md",
                ),
            )
            tracked_packet = self._git(root, "add", "--", 'docs/rollout_packets/imported_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run(root, "query", "--status", "open", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            row = payload["packets"][0]
            self.assertEqual(row["packet_path"], "docs/rollout_packets/open_packet.md")
            self.assertEqual(row["id"], "260329_1545_planveyor_open")
            self.assertEqual(row["target_repo"], "planveyor")
            self.assertEqual(row["status"], "open")
            self.assertEqual(
                row["source_plan"],
                "docs/plans/260329_0028_process_rollout_packet_helper_scaffold_without_cross_repo_writes.md",
            )
            self.assertTrue(row["queue_after_import"])
            self.assertEqual(row["target_adoption_state"], "awaiting-target-import")
            self.assertIsNone(row["target_import_receipt"])
            self.assertIsNone(row["target_local_plan"])

    def test_target_inbox_json_exposes_imported_as_awaiting_target_outcome(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/rollout_packets/imported_packet.md",
                _packet_text(
                    packet_id="260329_1546_planveyor_imported",
                    target_repo="consumer-fixture",
                    status="imported",
                    target_import_receipt="docs/plans/packet_inbox_adoption.md",
                    target_local_plan="docs/plans/packet_inbox_adoption.md",
                ),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/imported_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(target_root, tooling_root, "inbox", "--status", "imported", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["packets"][0]["target_adoption_state"], "awaiting-target-outcome")

    def test_query_json_exposes_packet_git_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self.assertEqual(self._git(root, "init").returncode, 0)
            self._write_file(
                root,
                "docs/rollout_packets/tracked_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_tracked"),
            )
            self.assertEqual(self._git(root, "add", "docs/rollout_packets/tracked_packet.md").returncode, 0)
            self._write_file(
                root,
                "docs/rollout_packets/untracked_packet.md",
                _packet_text(packet_id="260329_1546_planveyor_untracked"),
            )

            result = self._run(root, "query", "--status", "all", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            states = {row["id"]: row["git_state"] for row in payload["packets"]}
            self.assertEqual(states["260329_1545_planveyor_tracked"], "tracked")
            self.assertEqual(states["260329_1546_planveyor_untracked"], "untracked")

    def test_target_inbox_excludes_untracked_by_default_and_opt_in_includes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir()
            self.assertEqual(self._git(tooling_root, "init").returncode, 0)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/tracked_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_tracked", target_repo="consumer-fixture"),
            )
            self.assertEqual(self._git(tooling_root, "add", "docs/rollout_packets/tracked_packet.md").returncode, 0)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/untracked_packet.md",
                _packet_text(packet_id="260329_1546_planveyor_untracked", target_repo="consumer-fixture"),
            )

            default_result = self._run_with_tooling(target_root, tooling_root, "inbox", "--json")
            opt_in_result = self._run_with_tooling(
                target_root, tooling_root, "inbox", "--include-untracked", "--json"
            )

            self.assertEqual(default_result.returncode, 0, default_result.stderr)
            default_payload = json.loads(default_result.stdout)
            self.assertEqual(default_payload["count"], 1)
            self.assertEqual(default_payload["excluded_count"], 1)
            self.assertEqual(default_payload["packets"][0]["id"], "260329_1545_planveyor_tracked")
            self.assertEqual(default_payload["excluded_packets"][0]["id"], "260329_1546_planveyor_untracked")
            self.assertIn("include draft packets", default_payload["excluded_packets"][0]["excluded_reason"])

            self.assertEqual(opt_in_result.returncode, 0, opt_in_result.stderr)
            opt_in_payload = json.loads(opt_in_result.stdout)
            self.assertEqual(opt_in_payload["count"], 2)
            self.assertEqual(opt_in_payload["excluded_count"], 0)

    def test_target_inbox_no_git_root_keeps_unknown_packets_visible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(
                    packet_id="260329_1545_planveyor_unknown",
                    target_repo="consumer-fixture",
                ),
            )

            spec = importlib.util.spec_from_file_location(
                "rollout_packet_for_non_git_inbox_unit_model", SCRIPT
            )
            self.assertIsNotNone(spec)
            assert spec is not None and spec.loader is not None
            loaded_module = importlib.util.module_from_spec(spec)
            with mock.patch.dict(sys.modules, {spec.name: loaded_module}):
                spec.loader.exec_module(loaded_module)
                original_is_git_worktree = loaded_module._is_git_worktree

                def is_git_for_fixture(repo_root):
                    if Path(repo_root).resolve() == tooling_root.resolve():
                        return False
                    return original_is_git_worktree(repo_root)

                argv = [
                    "--repo-root", str(target_root),
                    "--tooling-root", str(tooling_root), "inbox", "--json",
                ]
                captured_stdout = io.StringIO()
                captured_stderr = io.StringIO()
                with (
                    mock.patch.object(
                        loaded_module, "_is_git_worktree", side_effect=is_git_for_fixture
                    ),
                    contextlib.redirect_stdout(captured_stdout),
                    contextlib.redirect_stderr(captured_stderr),
                ):
                    return_code = loaded_module.main(argv)
                result = subprocess.CompletedProcess(
                    args=argv, returncode=return_code,
                    stdout=captured_stdout.getvalue(), stderr=captured_stderr.getvalue(),
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["excluded_count"], 0)
            self.assertEqual(payload["packets"][0]["git_state"], "unknown")

    def test_target_inbox_no_git_root_keeps_unknown_packets_visible_real_non_git(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            if inside_git_work_tree(base):
                self.skipTest(NON_GIT_ROOT_SKIP_REASON)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(
                    packet_id="260329_1545_planveyor_unknown",
                    target_repo="consumer-fixture",
                ),
            )

            result = self._run_with_tooling(target_root, tooling_root, "inbox", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["excluded_count"], 0)
            self.assertEqual(payload["packets"][0]["git_state"], "unknown")

    def test_reconcile_report_json_classifies_seeded_buckets_and_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            paths = [
                self._write_file(
                    root,
                    "docs/rollout_packets/stale_open.md",
                    _packet_text(packet_id="010101_0000_planveyor_stale", date="2001-01-01 00:00"),
                ),
                self._write_file(
                    root,
                    "docs/rollout_packets/imported_missing.md",
                    _packet_text(packet_id="260329_1546_planveyor_missing", status="imported"),
                ),
                self._write_file(
                    root,
                    "docs/rollout_packets/imported_mismatch.md",
                    _packet_text(
                        packet_id="260329_1547_planveyor_mismatch",
                        status="imported",
                        target_import_receipt="docs/plans/packet_inbox_adoption.md",
                        target_local_plan="docs/plans/packet_inbox_adoption.md",
                        context_target_import_receipt="docs/plans/other_receipt.md",
                    ),
                ),
                self._write_file(
                    root,
                    "docs/rollout_packets/cancelled_without_reason.md",
                    _packet_text(packet_id="260329_1548_planveyor_cancelled", status="cancelled"),
                ),
                self._write_file(
                    root,
                    "docs/rollout_packets/date_warning.md",
                    _packet_text(packet_id="not_a_timestamp", date="not-a-date"),
                ),
                self._write_file(
                    root,
                    "docs/rollout_packets/status_mismatch.md",
                    _packet_text(
                        packet_id="260329_1549_planveyor_status_mismatch",
                        status="imported",
                        header_status="open",
                        target_import_receipt="docs/plans/packet_inbox_adoption.md",
                        target_local_plan="docs/plans/packet_inbox_adoption.md",
                    ),
                ),
            ]
            before = {path: path.read_text(encoding="utf-8") for path in paths}

            result = self._run(root, "reconcile", "--report", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            buckets = {row["bucket"] for row in payload["rows"]}
            self.assertTrue(
                {
                    "stale_open",
                    "missing_pointers",
                    "imported_without_target_path",
                    "terminal_without_reason",
                    "date_warning",
                    "status_mismatch",
                }.issubset(buckets)
            )
            self.assertGreaterEqual(payload["buckets"]["missing_pointers"], 1)
            for path, content in before.items():
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_reconcile_target_readback_accepts_only_structured_outcomes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            source_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            source_root.mkdir()
            target_root.mkdir()
            self._write_file(source_root, ".planveyor.planpath", "docs/plans/current.md\n")
            self._write_file(source_root, "docs/plans/done.md", "# Plan\n\n**Status:** Done\n")
            self._write_file(source_root, "docs/plans/current.md", "# Plan\n\n**Status:** In progress\n")

            packet_specs = {
                "green": ("260808_1500_planveyor_green", "docs/plans/green.md", "imported"),
                "pending": ("260808_1501_planveyor_pending", "docs/plans/pending.md", "imported"),
                "legacy": ("260808_1502_planveyor_legacy", "docs/plans/legacy.md", "imported"),
                "prose": ("260808_1503_planveyor_prose", "docs/plans/prose.md", "imported"),
                "near": ("260808_1504_planveyor_near", "docs/plans/near.md", "imported"),
                "mismatch": ("260808_1505_planveyor_mismatch", "docs/plans/expected.md", "imported"),
                "current": ("260808_1506_planveyor_current", "docs/plans/current.md", "open"),
            }
            for name, (packet_id, plan_rel, status) in packet_specs.items():
                self._write_file(
                    source_root,
                    f"docs/rollout_packets/{name}.md",
                    _packet_text(
                        packet_id=packet_id,
                        source_plan="docs/plans/current.md" if name == "current" else "docs/plans/done.md",
                        target_repo="consumer-fixture",
                        status=status,
                        target_import_receipt=plan_rel,
                        target_local_plan=plan_rel,
                    ),
                )

            green_id, green_plan, _ = packet_specs["green"]
            pending_id, pending_plan, _ = packet_specs["pending"]
            near_id, near_plan, _ = packet_specs["near"]
            mismatch_id, _expected_plan, _ = packet_specs["mismatch"]
            current_id, current_plan, _ = packet_specs["current"]
            self._write_structured_plan(
                target_root,
                green_plan,
                [_structured_item(green_id, "docs/rollout_packets/green.md", green_plan, decision_state="recorded", outcome="adopted")],
                target_repo="consumer-fixture",
            )
            self._write_structured_plan(
                target_root,
                pending_plan,
                [_structured_item(pending_id, "docs/rollout_packets/pending.md", pending_plan)],
                target_repo="consumer-fixture",
            )
            self._write_structured_plan(
                target_root,
                near_plan,
                [_structured_item(f"{near_id}_extra", "docs/rollout_packets/near.md", near_plan, decision_state="recorded", outcome="adopted")],
                target_repo="consumer-fixture",
            )
            self._write_structured_plan(
                target_root,
                "docs/plans/other.md",
                [_structured_item(mismatch_id, "docs/rollout_packets/mismatch.md", "docs/plans/other.md", decision_state="recorded", outcome="adopted")],
                target_repo="consumer-fixture",
            )
            self._write_structured_plan(
                target_root,
                current_plan,
                [_structured_item(current_id, "docs/rollout_packets/current.md", current_plan, decision_state="recorded", outcome="adopted")],
                target_repo="consumer-fixture",
            )
            legacy_id, legacy_plan, _ = packet_specs["legacy"]
            self._write_file(
                target_root,
                legacy_plan,
                "# Legacy\n\n```json\n"
                + json.dumps(
                    {
                        "rollout_packet_import": {
                            "packet_id": legacy_id,
                            "packet_path": "docs/rollout_packets/legacy.md",
                        }
                    }
                )
                + "\n```\n",
            )
            prose_id, prose_plan, _ = packet_specs["prose"]
            self._write_file(
                target_root,
                prose_plan,
                "# Prose\n\n"
                f"- `docs/rollout_packets/prose.md` id=`{prose_id}` local outcome=`adopted`.\n",
            )

            source_before = {path: path.read_bytes() for path in source_root.rglob("*.md") if path.is_file()}
            target_before = {path: path.read_bytes() for path in target_root.rglob("*.md") if path.is_file()}
            result = self._run(
                source_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = {row["id"]: row for row in json.loads(result.stdout)["rows"]}
            self.assertEqual(rows[green_id]["bucket"], "candidate_imported")
            self.assertEqual(rows[green_id]["target_adoption_state"], "adopted")
            self.assertEqual(rows[green_id]["target_outcome"], "adopted")
            self.assertEqual(rows[pending_id]["bucket"], "unproven_target_outcome")
            self.assertEqual(rows[pending_id]["target_adoption_state"], "awaiting-target-outcome")
            self.assertEqual(rows[pending_id]["target_import_receipt"], pending_plan)
            for packet_id in (legacy_id, prose_id):
                with self.subTest(packet_id=packet_id):
                    self.assertEqual(rows[packet_id]["bucket"], "unproven_target_outcome")
                    self.assertEqual(rows[packet_id]["target_adoption_state"], "awaiting-target-outcome")
                    self.assertIsNone(rows[packet_id]["target_outcome"])
            self.assertEqual(rows[near_id]["bucket"], "unproven_target_outcome")
            self.assertEqual(rows[near_id]["target_import_receipt"], near_plan)
            self.assertEqual(rows[mismatch_id]["bucket"], "unproven_target_outcome")
            self.assertEqual(rows[mismatch_id]["target_import_receipt"], "docs/plans/expected.md")
            self.assertIn("incompatible with the source default pointer pair", rows[mismatch_id]["message"])
            self.assertEqual(rows[current_id]["bucket"], "pending-current-source-plan")
            self.assertEqual(rows[current_id]["target_adoption_state"], "adoption-plan-created")

            plain = self._run(
                source_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
            )
            self.assertEqual(plain.returncode, 0, plain.stderr)
            for row in rows.values():
                self.assertIn(f"message={row['message']}", plain.stdout)
            for path, content in source_before.items():
                self.assertEqual(path.read_bytes(), content)
            for path, content in target_before.items():
                self.assertEqual(path.read_bytes(), content)

            invalid_root = base / "consumer-fixture-invalid"
            invalid_root.mkdir()
            self._write_structured_plan(
                invalid_root,
                green_plan,
                [_structured_item(green_id, "docs/rollout_packets/green.md", green_plan, decision_state="recorded", outcome="adopted")],
                target_repo="consumer-fixture",
            )
            self._write_file(
                invalid_root,
                "docs/plans/malformed.md",
                "# Bad\n\n"
                + _structured_carrier_text(
                    "docs/plans/malformed.md",
                    [_structured_item("other", "docs/rollout_packets/other.md", "docs/plans/malformed.md")],
                    target_repo="consumer-fixture",
                    extra_top_level={"unexpected": True},
                ),
            )
            invalid_result = self._run(
                source_root,
                "reconcile",
                "--report",
                "--target-root",
                str(invalid_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(invalid_result.returncode, 0, invalid_result.stderr)
            invalid_row = {row["id"]: row for row in json.loads(invalid_result.stdout)["rows"]}[green_id]
            self.assertEqual(invalid_row["bucket"], "unproven_target_outcome")
            self.assertIn("structured carrier validation failed", invalid_row["message"])

            duplicate_root = base / "consumer-fixture-duplicate"
            duplicate_root.mkdir()
            for name in ("a.md", "b.md"):
                self._write_structured_plan(
                    duplicate_root,
                    f"docs/plans/{name}",
                    [_structured_item(green_id, "docs/rollout_packets/green.md", f"docs/plans/{name}", decision_state="recorded", outcome="adopted")],
                    target_repo="consumer-fixture",
                )
            duplicate_result = self._run(
                source_root,
                "reconcile",
                "--report",
                "--target-root",
                str(duplicate_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(duplicate_result.returncode, 0, duplicate_result.stderr)
            duplicate_row = {row["id"]: row for row in json.loads(duplicate_result.stdout)["rows"]}[green_id]
            self.assertEqual(duplicate_row["bucket"], "unproven_target_outcome")
            self.assertIn("exactly one valid matching recorded item", duplicate_row["message"])

    def test_outcome_set_rejects_structured_negative_matrix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            tooling_root.mkdir()
            target_root.mkdir()
            plan_rel = "docs/plans/negative.md"
            packet_id = "260808_1600_planveyor_negative"
            packet_path = "docs/rollout_packets/negative.md"
            self._write_file(tooling_root, "docs/plans/done.md", "# Plan\n\n**Status:** Done\n")
            self._write_file(
                tooling_root,
                packet_path,
                _packet_text(
                    packet_id=packet_id,
                    source_plan="docs/plans/done.md",
                    target_repo="consumer-fixture",
                    status="imported",
                    target_import_receipt=plan_rel,
                    target_local_plan=plan_rel,
                ),
            )
            target_plan = target_root / plan_rel

            for name, carrier_text, writer_error, _readback_error in _structured_negative_carrier_matrix(
                plan_rel,
                packet_id,
                packet_path,
                target_repo="consumer-fixture",
            ):
                with self.subTest(case=name):
                    self._write_file(target_root, plan_rel, f"# Negative\n\n{carrier_text}\n## Notes\n")
                    before = target_plan.read_bytes()
                    result = self._run_with_tooling(
                        target_root,
                        tooling_root,
                        "outcome-set",
                        "--target-plan",
                        plan_rel,
                        "--packet-id",
                        packet_id,
                        "--packet-path",
                        packet_path,
                        "--outcome",
                        "adopted",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(writer_error, result.stderr)
                    self.assertEqual(target_plan.read_bytes(), before)
                    self.assertEqual(list(target_plan.parent.glob(f".{target_plan.name}.*.tmp")), [])

    def test_reconcile_structured_negative_matrix_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            source_root = base / "planveyor"
            source_root.mkdir()
            plan_rel = "docs/plans/negative.md"
            packet_id = "260808_1600_planveyor_negative"
            packet_path = "docs/rollout_packets/negative.md"
            self._write_file(source_root, ".planveyor.planpath", "docs/plans/current.md\n")
            self._write_file(source_root, "docs/plans/current.md", "# Plan\n\n**Status:** In progress\n")
            self._write_file(source_root, "docs/plans/done.md", "# Plan\n\n**Status:** Done\n")
            self._write_file(
                source_root,
                packet_path,
                _packet_text(
                    packet_id=packet_id,
                    source_plan="docs/plans/done.md",
                    target_repo="consumer-fixture",
                    status="imported",
                    target_import_receipt=plan_rel,
                    target_local_plan=plan_rel,
                ),
            )
            source_before = {path: path.read_bytes() for path in source_root.rglob("*.md") if path.is_file()}
            readback_cases = [
                (name, {plan_rel: carrier_text}, readback_error)
                for name, carrier_text, _writer_error, readback_error in _structured_negative_carrier_matrix(
                    plan_rel,
                    packet_id,
                    packet_path,
                    target_repo="consumer-fixture",
                )
            ]
            readback_cases.append(
                (
                    "conflicting_carriers",
                    {
                        plan_rel: _structured_carrier_text(
                            plan_rel,
                            [
                                _structured_item(
                                    packet_id,
                                    packet_path,
                                    plan_rel,
                                    decision_state="recorded",
                                    outcome="adopted",
                                )
                            ],
                            target_repo="consumer-fixture",
                        ),
                        "docs/plans/conflict.md": _structured_carrier_text(
                            "docs/plans/conflict.md",
                            [
                                _structured_item(
                                    packet_id,
                                    packet_path,
                                    "docs/plans/conflict.md",
                                    decision_state="recorded",
                                    outcome="cancelled",
                                )
                            ],
                            target_repo="consumer-fixture",
                        ),
                    },
                    "target readback needs exactly one valid matching recorded item",
                )
            )

            for name, target_files, readback_error in readback_cases:
                with self.subTest(case=name):
                    target_root = base / f"consumer-fixture_{name}"
                    target_root.mkdir()
                    for target_plan_rel, carrier_text in target_files.items():
                        self._write_file(target_root, target_plan_rel, f"# Negative\n\n{carrier_text}\n## Notes\n")
                    target_before = {
                        path: path.read_bytes() for path in target_root.rglob("*.md") if path.is_file()
                    }
                    result = self._run(
                        source_root,
                        "reconcile",
                        "--report",
                        "--target-root",
                        str(target_root),
                        "--target-repo",
                        "consumer-fixture",
                        "--json",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    row = {row["id"]: row for row in json.loads(result.stdout)["rows"]}[packet_id]
                    self.assertEqual(row["bucket"], "unproven_target_outcome")
                    self.assertEqual(row["target_adoption_state"], "awaiting-target-outcome")
                    self.assertEqual(row["target_import_receipt"], plan_rel)
                    self.assertEqual(row["target_local_plan"], plan_rel)
                    self.assertIsNone(row["target_outcome"])
                    self.assertIn(readback_error, row["message"])

                    plain = self._run(
                        source_root,
                        "reconcile",
                        "--report",
                        "--target-root",
                        str(target_root),
                        "--target-repo",
                        "consumer-fixture",
                    )
                    self.assertEqual(plain.returncode, 0, plain.stderr)
                    self.assertIn(f"message={row['message']}", plain.stdout)
                    self.assertEqual(
                        {path: path.read_bytes() for path in source_root.rglob("*.md") if path.is_file()},
                        source_before,
                    )
                    self.assertEqual(
                        {path: path.read_bytes() for path in target_root.rglob("*.md") if path.is_file()},
                        target_before,
                    )

    def test_reconcile_target_readback_is_report_only_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            source_root = base / "source-repo"
            target_root = base / "consumer-fixture"
            source_root.mkdir()
            target_root.mkdir()
            target_repo = "consumer-fixture"
            target_plan = "docs/plans/structured_readback.md"
            source_plan = "docs/plans/done.md"
            pending_source_plan = "docs/plans/pending.md"

            source_root.mkdir(exist_ok=True)
            standalone_git_root(source_root)
            fixture_git = self._git(source_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), source_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(source_root, ".planveyor.planpath", "docs/plans/current.md\n")
            self._write_file(source_root, source_plan, "# Plan\n\n**Status:** Done\n")
            self._write_file(source_root, "docs/plans/current.md", "# Plan\n\n**Status:** In progress\n")
            self._write_file(source_root, pending_source_plan, "# Plan\n\n**Status:** In progress\n")

            outcome_cases = (
                ("imported", "candidate_imported", "adopted"),
                ("adopted", "candidate_imported", "adopted"),
                ("already-handled", "pointer-preserved candidate", "pointer-preserved"),
                ("pointer-preserved", "pointer-preserved candidate", "pointer-preserved"),
                ("parked", "parked candidate", "parked"),
                ("no-op", "pointer-preserved candidate", "pointer-preserved"),
                ("superseded", "cancelled/superseded candidate", "cancelled"),
                ("forward-adopted", "candidate_imported", "adopted"),
                ("cancelled", "cancelled/superseded candidate", "cancelled"),
                ("rejected", "cancelled/superseded candidate", "cancelled"),
            )
            carrier_items: list[dict[str, object]] = []
            outcome_ids: dict[str, str] = {}
            for index, (outcome, _bucket, _adoption_state) in enumerate(outcome_cases):
                slug = outcome.replace("-", "_")
                packet_id = f"260922_{1200 + index:04d}_planveyor_{slug}"
                packet_path = f"docs/rollout_packets/outcome_{slug}.md"
                outcome_ids[outcome] = packet_id
                self._write_file(
                    source_root,
                    packet_path,
                    _packet_text(
                        packet_id=packet_id,
                        source_plan=source_plan,
                        target_repo=target_repo,
                        target_import_receipt=target_plan,
                        target_local_plan=target_plan,
                    ),
                )
                tracked_packet = self._git(source_root, "add", "--", packet_path)
                self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
                carrier_items.append(
                    _structured_item(
                        packet_id,
                        packet_path,
                        target_plan,
                        decision_state="recorded",
                        outcome=outcome,
                    )
                )

            pending_id = "260922_1210_planveyor_pending_target"
            pending_path = "docs/rollout_packets/pending_target.md"
            partial_id = "260922_1211_planveyor_partial_pointer"
            partial_path = "docs/rollout_packets/partial_pointer.md"
            split_id = "260922_1212_planveyor_split_pointer"
            split_path = "docs/rollout_packets/split_pointer.md"
            special_packets = (
                (pending_id, pending_path, target_plan, target_plan),
                (partial_id, partial_path, target_plan, None),
                (split_id, split_path, target_plan, "docs/plans/other.md"),
            )
            for packet_id, packet_path, receipt, local_plan in special_packets:
                self._write_file(
                    source_root,
                    packet_path,
                    _packet_text(
                        packet_id=packet_id,
                        source_plan=source_plan,
                        target_repo=target_repo,
                        status="imported",
                        target_import_receipt=receipt,
                        target_local_plan=local_plan,
                    ),
                )
                tracked_packet = self._git(source_root, "add", "--", packet_path)
                self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            carrier_items.extend(
                (
                    _structured_item(pending_id, pending_path, target_plan),
                    _structured_item(
                        partial_id,
                        partial_path,
                        target_plan,
                        decision_state="recorded",
                        outcome="adopted",
                    ),
                    _structured_item(
                        split_id,
                        split_path,
                        target_plan,
                        decision_state="recorded",
                        outcome="adopted",
                    ),
                )
            )

            pending_source_cases = (
                (
                    "260922_1213_planveyor_pending_current_source",
                    "docs/rollout_packets/pending_current_source.md",
                    "docs/plans/current.md",
                    "pending-current-source-plan",
                ),
                (
                    "260922_1214_planveyor_pending_source",
                    "docs/rollout_packets/pending_source.md",
                    pending_source_plan,
                    "pending-source",
                ),
            )
            for packet_id, packet_path, packet_source_plan, _expected_bucket in pending_source_cases:
                self._write_file(
                    source_root,
                    packet_path,
                    _packet_text(
                        packet_id=packet_id,
                        source_plan=packet_source_plan,
                        target_repo=target_repo,
                        target_import_receipt=target_plan,
                        target_local_plan=target_plan,
                    ),
                )
                tracked_packet = self._git(source_root, "add", "--", packet_path)
                self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
                carrier_items.append(
                    _structured_item(
                        packet_id,
                        packet_path,
                        target_plan,
                        decision_state="recorded",
                        outcome="adopted",
                    )
                )

            no_pointer_id = "260922_1215_planveyor_no_pointer"
            no_pointer_path = "docs/rollout_packets/no_pointer.md"
            no_carrier_id = "260922_1216_planveyor_no_carrier"
            no_carrier_path = "docs/rollout_packets/no_carrier.md"
            no_carrier_plan = "docs/plans/no_carrier.md"
            self._write_file(
                source_root,
                no_pointer_path,
                _packet_text(
                    packet_id=no_pointer_id,
                    source_plan=source_plan,
                    target_repo=target_repo,
                ),
            )
            tracked_packet = self._git(source_root, "add", "--", no_pointer_path)
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            self._write_file(
                source_root,
                no_carrier_path,
                _packet_text(
                    packet_id=no_carrier_id,
                    source_plan=source_plan,
                    target_repo=target_repo,
                    status="imported",
                    target_import_receipt=no_carrier_plan,
                    target_local_plan=no_carrier_plan,
                ),
            )
            tracked_packet = self._git(source_root, "add", "--", no_carrier_path)
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            def snapshot(root: Path) -> dict[str, bytes]:
                return {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                }

            def report_pair() -> tuple[dict[str, object], str]:
                source_before = snapshot(source_root)
                target_before = snapshot(target_root)
                args = (
                    "reconcile",
                    "--report",
                    "--target-root",
                    str(target_root),
                    "--target-repo",
                    target_repo,
                )
                json_result = self._run(source_root, *args, "--json")
                self.assertEqual(json_result.returncode, 0, json_result.stderr)
                self.assertEqual(snapshot(source_root), source_before)
                self.assertEqual(snapshot(target_root), target_before)
                plain_result = self._run(source_root, *args)
                self.assertEqual(plain_result.returncode, 0, plain_result.stderr)
                self.assertEqual(snapshot(source_root), source_before)
                self.assertEqual(snapshot(target_root), target_before)
                return json.loads(json_result.stdout), plain_result.stdout

            no_carrier_payload, no_carrier_plain = report_pair()
            self.assertEqual(no_carrier_payload["mode"], "target-readback")
            no_carrier_rows = {row["id"]: row for row in no_carrier_payload["rows"]}
            no_pointer_row = no_carrier_rows[no_pointer_id]
            self.assertEqual(no_pointer_row["bucket"], "needs_explicit_target_receipt")
            self.assertEqual(no_pointer_row["target_adoption_state"], "awaiting-target-import")
            self.assertIsNone(no_pointer_row["target_import_receipt"])
            self.assertIsNone(no_pointer_row["target_local_plan"])
            self.assertIsNone(no_pointer_row["target_outcome"])
            no_carrier_row = no_carrier_rows[no_carrier_id]
            self.assertEqual(no_carrier_row["bucket"], "needs_explicit_target_receipt")
            self.assertEqual(no_carrier_row["target_adoption_state"], "awaiting-target-outcome")
            self.assertEqual(no_carrier_row["target_import_receipt"], no_carrier_plan)
            self.assertEqual(no_carrier_row["target_local_plan"], no_carrier_plan)
            self.assertIsNone(no_carrier_row["target_outcome"])
            for row in (no_pointer_row, no_carrier_row):
                self.assertIn(f"message={row['message']}", no_carrier_plain)

            self._write_structured_plan(
                target_root,
                target_plan,
                carrier_items,
                target_repo=target_repo,
            )
            payload, plain = report_pair()
            self.assertEqual(payload["mode"], "target-readback")
            rows = {row["id"]: row for row in payload["rows"]}
            for outcome, expected_bucket, expected_state in outcome_cases:
                with self.subTest(outcome=outcome):
                    row = rows[outcome_ids[outcome]]
                    self.assertEqual(row["bucket"], expected_bucket)
                    self.assertEqual(row["target_adoption_state"], expected_state)
                    self.assertEqual(row["target_import_receipt"], target_plan)
                    self.assertEqual(row["target_local_plan"], target_plan)
                    self.assertEqual(row["target_outcome"], outcome)
                    self.assertIn(f"message={row['message']}", plain)
                    self.assertIn(
                        f"target_import_receipt={target_plan} target_local_plan={target_plan} "
                        f"target_outcome={outcome}",
                        plain,
                    )

            pending_row = rows[pending_id]
            self.assertEqual(pending_row["bucket"], "unproven_target_outcome")
            self.assertEqual(pending_row["target_adoption_state"], "awaiting-target-outcome")
            self.assertEqual(pending_row["target_import_receipt"], target_plan)
            self.assertEqual(pending_row["target_local_plan"], target_plan)
            self.assertIsNone(pending_row["target_outcome"])
            self.assertIn("matching item is pending", pending_row["message"])
            self.assertIn(f"message={pending_row['message']}", plain)

            for packet_id, _packet_path, _source_plan, expected_bucket in pending_source_cases:
                with self.subTest(packet_id=packet_id):
                    row = rows[packet_id]
                    self.assertEqual(row["bucket"], expected_bucket)
                    self.assertEqual(row["source_plan_readiness"], expected_bucket)
                    self.assertEqual(row["source_plan_status"], "In progress")
                    self.assertEqual(row["target_adoption_state"], "adoption-plan-created")
                    self.assertEqual(row["target_import_receipt"], target_plan)
                    self.assertEqual(row["target_local_plan"], target_plan)
                    self.assertEqual(row["target_outcome"], "adopted")
                    self.assertIn("report-only until source closes", row["message"])
                    self.assertIn(f"message={row['message']}", plain)

            for packet_id in (partial_id, split_id):
                with self.subTest(packet_id=packet_id):
                    row = rows[packet_id]
                    self.assertEqual(row["bucket"], "unproven_target_outcome")
                    self.assertEqual(row["target_adoption_state"], "awaiting-target-outcome")
                    self.assertIsNone(row["target_import_receipt"])
                    self.assertIsNone(row["target_local_plan"])
                    self.assertIsNone(row["target_outcome"])
                    self.assertIn("incompatible with the source default pointer pair", row["message"])
                    self.assertIn(f"message={row['message']}", plain)

    def test_reconcile_older_than_days_threshold_controls_stale_open_bucket(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/rollout_packets/open_old.md",
                _packet_text(packet_id="010101_0000_planveyor_stale", date="2001-01-01 00:00"),
            )

            result = self._run(root, "reconcile", "--report", "--older-than-days", "99999", "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            buckets = {row["bucket"] for row in payload["rows"]}
            self.assertNotIn("stale_open", buckets)

    def test_reconcile_reads_new_explicit_offset_header_without_packet_id_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root, "docs/rollout_packets/offset_date.md",
                _packet_text(packet_id="no_filename_timestamp", date="2001-01-01 00:00 +0900"),
            )
            for zone in ("UTC", "Asia/Tokyo"):
                with self.subTest(zone=zone), mock.patch.dict(os.environ, {"TZ": zone}):
                    result = self._run(root, "reconcile", "--report", "--older-than-days", "1", "--json")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    buckets = {row["bucket"] for row in json.loads(result.stdout)["rows"]}
                    self.assertIn("stale_open", buckets)
                    self.assertNotIn("date_warning", buckets)

    def test_query_and_reconcile_reject_target_repo_execution_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir(parents=True)
            packet_path = self._write_file(tooling_root, "docs/rollout_packets/sample_packet.md", _packet_text())
            before = packet_path.read_text(encoding="utf-8")

            for command in (("query",), ("reconcile", "--report")):
                with self.subTest(command=command):
                    result = self._run_with_tooling(target_root, tooling_root, *command)

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("rollout packet helpers are source-local only", result.stderr)
                    self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_query_and_reconcile_reject_malformed_packet_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(root, "docs/rollout_packets/broken.md", _malformed_packet_text(target_repo="planveyor"))

            for command in (("query",), ("reconcile", "--report")):
                with self.subTest(command=command):
                    result = self._run(root, *command)

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("docs/rollout_packets/broken.md: malformed packet JSON", result.stderr)

    def test_reconcile_requires_report_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(root, "docs/rollout_packets/sample_packet.md", _packet_text())

            result = self._run(root, "reconcile")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("reconcile currently supports --report only", result.stderr)

    def test_query_rejects_unknown_status_filter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(root, "docs/rollout_packets/sample_packet.md", _packet_text())

            result = self._run(root, "query", "--status", "adopted")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("unknown packet status filter: adopted", result.stderr)

    def test_show_and_import_instructions_reject_non_packet_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_file(root, "docs/plans/example.md", "# Not a packet\n")

            for command in ("show", "import-instructions"):
                with self.subTest(command=command, path="docs/plans/example.md"):
                    result = self._run(root, command, "docs/plans/example.md")

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("packet path must stay under docs/rollout_packets/", result.stderr)

                with self.subTest(command=command, path="absolute"):
                    result = self._run(root, command, str(plan_path))

                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("packet path must be repo-relative under docs/rollout_packets/", result.stderr)

    def test_import_instructions_target_plan_seed_uses_repo_relative_packet_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            packet_path = self._write_file(root, packet_relative, _packet_text())

            result = self._run(root, "import-instructions", packet_relative, "--print-target-plan-seed")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"Source packet: {packet_relative}", result.stdout)
            self.assertIn(f"Source rollout packet: `{packet_relative}`", result.stdout)
            self.assertNotIn(str(packet_path), result.stdout)

    def test_target_inbox_lists_matching_open_packets_from_tooling_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="consumer-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/planveyor_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/consumer_packet.md",
                _packet_text(packet_id="260329_1546_consumer_helper", target_repo="partner-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/consumer_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(target_root, tooling_root, "inbox")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Rollout packet inbox for target repo: consumer-fixture", result.stdout)
            self.assertIn("Matching packets: 1", result.stdout)
            self.assertIn("260329_1545_planveyor_helper", result.stdout)
            self.assertNotIn("260329_1546_consumer_helper", result.stdout)

    def test_target_inbox_accepts_hyphen_and_underscore_repo_aliases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer_fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/rollout_packets/consumer_packet.md",
                _packet_text(packet_id="260329_1546_consumer_helper", target_repo="consumer-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/consumer_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(target_root, tooling_root, "inbox")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Rollout packet inbox for target repo: consumer-fixture", result.stdout)
            self.assertIn("Matching packets: 1", result.stdout)
            self.assertIn("260329_1546_consumer_helper", result.stdout)

    def test_target_inbox_ignores_malformed_unrelated_target_packets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="consumer-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/planveyor_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/consumer_broken.md",
                _malformed_packet_text(target_repo="partner-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/consumer_broken.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(target_root, tooling_root, "inbox")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Matching packets: 1", result.stdout)
            self.assertIn("260329_1545_planveyor_helper", result.stdout)
            self.assertNotIn("260329_1546_broken", result.stdout)

    def test_target_inbox_rejects_malformed_matching_target_packet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_broken.md",
                _malformed_packet_text(target_repo="consumer-fixture"),
            )

            result = self._run_with_tooling(target_root, tooling_root, "inbox")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("docs/rollout_packets/planveyor_broken.md: malformed packet JSON", result.stderr)

    def test_adoption_plan_emits_single_structured_outcome_carrier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            packet_path = self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="consumer-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/planveyor_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--out",
                "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            target_plan = target_root / "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md"
            self.assertTrue(target_plan.is_file())
            plan_text = target_plan.read_text(encoding="utf-8")
            self.assertIn("target-local import receipt", plan_text)
            self.assertIn("**Schema version:** plan.v2", plan_text)
            self.assertNotIn('"followups_out"', plan_text)
            self.assertIn('"required_manager_mode": "either"', plan_text)
            self.assertIn('"queue_activation": {', plan_text)
            self.assertIn('"state": "owner_approved"', plan_text)
            self.assertIn("## Documentation impact / provenance", plan_text)
            self.assertIn(
                "- Target import receipt / local adoption plan: "
                "`docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md`",
                plan_text,
            )
            self.assertIn(
                '"target_import_receipt": "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md"',
                plan_text,
            )
            self.assertIn(
                '"target_local_plan": "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md"',
                plan_text,
            )
            self.assertIn("- Playbooks: `N/A (why=process/helper import plan; no UI surface)`", plan_text)
            self.assertIn("- Role: `target-import`", plan_text)
            self.assertIn("- Mode: fresh-exec", plan_text)
            self.assertIn("## Rollout packet outcome carrier", plan_text)
            self.assertEqual(plan_text.count(CARRIER_BEGIN), 1)
            self.assertEqual(plan_text.count(CARRIER_END), 1)
            self.assertNotIn("## Import receipt (compact JSON)", plan_text)
            carrier = _carrier_payload_from_text(plan_text)
            self.assertEqual(set(carrier), {"rollout_packet_import", "rollout_packet_outcomes"})
            self.assertEqual(
                carrier["rollout_packet_outcomes"]["schema_version"], "rollout_packet_outcomes.v1"
            )
            self.assertEqual(
                carrier["rollout_packet_outcomes"]["items"],
                [
                    _structured_item(
                        "260329_1545_planveyor_helper",
                        "docs/rollout_packets/planveyor_packet.md",
                        "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md",
                    )
                ],
            )
            self.assertNotIn('"absolute_path"', plan_text)
            self.assertNotIn('"packets": [', plan_text)
            self.assertIn(
                "`rollout_packet_import.target_import_receipt` and "
                "`rollout_packet_import.target_local_plan` both point to "
                "`docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md`",
                plan_text,
            )
            carrier_start = plan_text.index(CARRIER_BEGIN)
            carrier_end = plan_text.index(CARRIER_END, carrier_start)
            self.assertNotIn("```json", plan_text[carrier_start:carrier_end])
            self.assertIn(str(packet_path.resolve()), plan_text)
            self.assertIn("260329_1545_planveyor_helper", plan_text)
            self.assertIn(
                "Validation: run `<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py "
                "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md`",
                result.stdout,
            )
            expected_lint_command = (
                "<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py "
                "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md"
            )
            self.assertEqual(plan_text.count(expected_lint_command), 4)
            self.assertNotIn("$HOME/planveyor", plan_text)
            self.assertNotIn("python3 -B", plan_text)
            self.assertNotIn("planveyor_plan_lint", plan_text)
            self.assertNotIn("$HOME/planveyor", result.stdout)
            self.assertNotIn("python3 -B", result.stdout)
            self.assertNotIn("planveyor_plan_lint", result.stdout)
            self.assertIn(
                "Queue hint: after validation exits 0, choose the actual Manager mode:",
                result.stdout,
            )
            concrete_plan = "docs/plans/260617_1204_review_helpers_assets_dir_allowlist_hardening.md"
            self.assertIn(
                f"`planveyor_q_set {concrete_plan} --for-manager-mode manager-collab`",
                result.stdout,
            )
            self.assertIn(
                f"`planveyor_q_set {concrete_plan} --for-manager-mode manager-custom-pipeline`",
                result.stdout,
            )
            self.assertLess(result.stdout.index("Validation:"), result.stdout.index("Queue hint:"))
            self.assertNotIn(f"`planveyor_q_set {concrete_plan}`", result.stdout)
            self.assertNotIn("<PLAN", result.stdout)
            lint_result = self._lint_plan(target_plan)
            self.assertEqual(lint_result.returncode, 0, lint_result.stdout + lint_result.stderr)

    def test_outcome_set_validates_and_updates_structured_carrier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            tooling_root.mkdir()
            target_root.mkdir()
            plan_rel = "docs/plans/260808_1400_structured.md"
            packet_id = "260808_1400_planveyor_structured"
            packet_path = "docs/rollout_packets/structured.md"
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/plans/done.md",
                "# Plan\n\n**Status:** Done\n",
            )
            self._write_file(
                tooling_root,
                packet_path,
                _packet_text(
                    packet_id=packet_id,
                    source_plan="docs/plans/done.md",
                    target_repo="consumer-fixture",
                    status="imported",
                    target_import_receipt=plan_rel,
                    target_local_plan=plan_rel,
                ),
            )
            tracked_packet = self._git(tooling_root, "add", "--", packet_path)
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            generated = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--status",
                "all",
                "--out",
                plan_rel,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            target_plan = target_root / plan_rel
            target_plan.chmod(0o640)
            before = target_plan.read_bytes()
            before_outer = _carrier_outer_bytes(before)

            def outcome_set(target_plan_arg: str, *, packet_id_arg: str = packet_id, outcome: str = "adopted") -> subprocess.CompletedProcess[str]:
                return self._run_with_tooling(
                    target_root,
                    tooling_root,
                    "outcome-set",
                    "--target-plan",
                    target_plan_arg,
                    "--packet-id",
                    packet_id_arg,
                    "--packet-path",
                    packet_path,
                    "--outcome",
                    outcome,
                )

            invalid_paths = (
                str(target_plan),
                "docs/plans/../outside.md",
                "docs/plans/missing.md",
                "docs/plans/not_markdown.txt",
            )
            directory_path = target_root / "docs/plans/directory.md"
            directory_path.mkdir()
            invalid_paths += ("docs/plans/directory.md",)
            symlink_path = target_root / "docs/plans/symlink.md"
            symlink_path.symlink_to(target_plan)
            invalid_paths += ("docs/plans/symlink.md",)
            for target_plan_arg in invalid_paths:
                with self.subTest(target_plan=target_plan_arg):
                    result = outcome_set(target_plan_arg)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(target_plan.read_bytes(), before)
                    self.assertEqual(list(target_plan.parent.glob(f".{target_plan.name}.*.tmp")), [])
            symlink_path.unlink()
            directory_path.rmdir()

            for packet_id_arg, outcome in (("wrong-id", "adopted"), (packet_id, "adopted please")):
                with self.subTest(packet_id=packet_id_arg, outcome=outcome):
                    result = outcome_set(plan_rel, packet_id_arg=packet_id_arg, outcome=outcome)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(target_plan.read_bytes(), before)

            spec = importlib.util.spec_from_file_location("rollout_packet_for_atomic_test", SCRIPT)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            failed_write_args = argparse.Namespace(
                repo_root=str(target_root),
                tooling_root=str(tooling_root),
                target_plan=plan_rel,
                packet_id=packet_id,
                packet_path=packet_path,
                outcome="adopted",
            )
            failure_stdout = io.StringIO()
            failure_stderr = io.StringIO()
            with (
                mock.patch.object(module.os, "replace", side_effect=OSError("forced atomic replace failure")),
                contextlib.redirect_stdout(failure_stdout),
                contextlib.redirect_stderr(failure_stderr),
            ):
                self.assertEqual(module.cmd_outcome_set(failed_write_args), 1)
            self.assertIn("forced atomic replace failure", failure_stderr.getvalue())
            self.assertEqual(target_plan.read_bytes(), before)
            self.assertEqual(list(target_plan.parent.glob(f".{target_plan.name}.*.tmp")), [])

            result = outcome_set(plan_rel, outcome="NOOP")
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = target_plan.read_bytes()
            self.assertEqual(stat.S_IMODE(target_plan.stat().st_mode), 0o640)
            self.assertEqual(_carrier_outer_bytes(recorded), before_outer)
            payload = _carrier_payload_from_text(recorded.decode("utf-8"))
            item = payload["rollout_packet_outcomes"]["items"][0]
            self.assertEqual(item["decision_state"], "recorded")
            self.assertEqual(item["outcome"], "no-op")
            self.assertIn("Result: target outcome recorded", result.stdout)

            replay = outcome_set(plan_rel, outcome="no op")
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertIn("already recorded", replay.stdout)
            self.assertEqual(target_plan.read_bytes(), recorded)
            conflict = outcome_set(plan_rel, outcome="adopted")
            self.assertNotEqual(conflict.returncode, 0)
            self.assertEqual(target_plan.read_bytes(), recorded)

            source_before_readback = {
                path: path.read_bytes() for path in tooling_root.rglob("*.md") if path.is_file()
            }
            target_before_readback = {
                path: path.read_bytes() for path in target_root.rglob("*.md") if path.is_file()
            }
            reconcile_json = self._run(
                tooling_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(reconcile_json.returncode, 0, reconcile_json.stderr)
            row = json.loads(reconcile_json.stdout)["rows"][0]
            self.assertEqual(row["bucket"], "pointer-preserved candidate")
            self.assertEqual(row["target_adoption_state"], "pointer-preserved")
            self.assertEqual(row["target_outcome"], "no-op")
            reconcile_plain = self._run(
                tooling_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
            )
            self.assertEqual(reconcile_plain.returncode, 0, reconcile_plain.stderr)
            self.assertIn(f"message={row['message']}", reconcile_plain.stdout)
            self.assertIn("target_outcome=no-op", reconcile_plain.stdout)
            for path, content in source_before_readback.items():
                self.assertEqual(path.read_bytes(), content)
            for path, content in target_before_readback.items():
                self.assertEqual(path.read_bytes(), content)

            for name, content in (
                (
                    "unknown.md",
                    "# Plan\n\n"
                    + _structured_carrier_text(
                        "docs/plans/unknown.md",
                        [_structured_item(packet_id, packet_path, "docs/plans/unknown.md")],
                        target_repo="consumer-fixture",
                        extra_top_level={"unexpected": True},
                    ),
                ),
                (
                    "duplicate.md",
                    "# Plan\n\n"
                    + _structured_carrier_text(
                        "docs/plans/duplicate.md",
                        [
                            _structured_item(packet_id, packet_path, "docs/plans/duplicate.md"),
                            _structured_item(packet_id, packet_path, "docs/plans/duplicate.md"),
                        ],
                        target_repo="consumer-fixture",
                    ),
                ),
                (
                    "wrong_repo.md",
                    "# Plan\n\n"
                    + _structured_carrier_text(
                        "docs/plans/wrong_repo.md",
                        [_structured_item(packet_id, packet_path, "docs/plans/wrong_repo.md")],
                        target_repo="planveyor",
                    ),
                ),
            ):
                with self.subTest(name=name):
                    path = self._write_file(target_root, f"docs/plans/{name}", content)
                    original = path.read_bytes()
                    result = outcome_set(f"docs/plans/{name}")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

            reconcile_json = self._run(
                tooling_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(reconcile_json.returncode, 0, reconcile_json.stderr)
            row = json.loads(reconcile_json.stdout)["rows"][0]
            self.assertEqual(row["bucket"], "unproven_target_outcome")
            self.assertEqual(row["target_adoption_state"], "awaiting-target-outcome")
            self.assertIsNone(row["target_outcome"])
            self.assertIn("structured carrier validation failed", row["message"])
            self.assertEqual(target_plan.read_bytes(), recorded)

    def test_adoption_plan_excludes_untracked_by_default_and_records_excluded_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir()
            self.assertEqual(self._git(tooling_root, "init").returncode, 0)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/tracked_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_tracked", target_repo="consumer-fixture"),
            )
            self.assertEqual(self._git(tooling_root, "add", "docs/rollout_packets/tracked_packet.md").returncode, 0)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/untracked_packet.md",
                _packet_text(packet_id="260329_1546_planveyor_untracked", target_repo="consumer-fixture"),
            )

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--out",
                "docs/plans/260524_2036_process_rollout_packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Imported packets: 1", result.stdout)
            self.assertIn("Excluded untracked packets: 1", result.stdout)
            target_plan = target_root / "docs/plans/260524_2036_process_rollout_packet_inbox_adoption.md"
            plan_text = target_plan.read_text(encoding="utf-8")
            self.assertIn("260329_1545_planveyor_tracked", plan_text)
            self.assertIn("260329_1546_planveyor_untracked", plan_text)
            self.assertIn("### Imported packet rows", plan_text)
            self.assertIn("### Excluded packet rows", plan_text)
            self.assertIn('"excluded_packet_count": 1', plan_text)
            self.assertIn('"packet_count": 1', plan_text)
            lint_result = self._lint_plan(target_plan)
            self.assertEqual(lint_result.returncode, 0, lint_result.stdout + lint_result.stderr)

    def test_import_instructions_seed_uses_one_carrier_receipt_wording(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            root = Path(tmpdir)
            packet_relative = "docs/rollout_packets/sample_packet.md"
            self._write_file(root, packet_relative, _packet_text())

            result = self._run(root, "import-instructions", packet_relative, "--print-target-plan-seed")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Materialize one target-local adoption plan as the import receipt", result.stdout)
        self.assertIn("planveyor_rollout_packet_outcome_set --target-plan", result.stdout)
        self.assertIn("prose and legacy fenced JSON are not authority", result.stdout)
        self.assertIn("Target import receipt: same path as target local adoption plan by default", result.stdout)
        self.assertNotIn("Target import receipt: `docs/...`", result.stdout)
        self.assertNotIn("local decision, local plan path/no-plan reason", result.stdout)

    def test_adoption_plan_rejects_source_repo_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="planveyor"),
            )

            result = self._run_with_tooling(
                tooling_root,
                tooling_root,
                "adoption-plan",
                "--target-repo",
                "planveyor",
                "--out",
                "docs/plans/should_not_exist.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("adoption-plan must run from the target repo", result.stderr)
            self.assertFalse((tooling_root / "docs/plans/should_not_exist.md").exists())

    def test_adoption_plan_rejects_target_repo_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="planveyor"),
            )

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--target-repo",
                "planveyor",
                "--out",
                "docs/plans/should_not_exist.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("current repo id `consumer-fixture` does not match target repo `planveyor`", result.stderr)
            self.assertFalse((target_root / "docs/plans/should_not_exist.md").exists())

    def test_adoption_plan_ignores_malformed_unrelated_target_packets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            tooling_root.mkdir(exist_ok=True)
            standalone_git_root(tooling_root)
            fixture_git = self._git(tooling_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), tooling_root.resolve())
            target_root.mkdir(exist_ok=True)
            standalone_git_root(target_root)
            fixture_git = self._git(target_root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), target_root.resolve())

            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="consumer-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/planveyor_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)
            self._write_file(
                tooling_root,
                "docs/rollout_packets/consumer_broken.md",
                _malformed_packet_text(target_repo="partner-fixture"),
            )
            tracked_packet = self._git(tooling_root, "add", "--", 'docs/rollout_packets/consumer_broken.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--out",
                "docs/plans/packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            target_plan = target_root / "docs/plans/packet_inbox_adoption.md"
            self.assertTrue(target_plan.is_file())
            plan_text = target_plan.read_text(encoding="utf-8")
            self.assertIn("260329_1545_planveyor_helper", plan_text)
            self.assertNotIn("260329_1546_broken", plan_text)

    def test_adoption_plan_rejects_output_outside_docs_plans(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_cli_") as tmpdir:
            base = Path(tmpdir)
            tooling_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            target_root.mkdir()
            self._write_file(
                tooling_root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(packet_id="260329_1545_planveyor_helper", target_repo="consumer-fixture"),
            )

            result = self._run_with_tooling(
                target_root,
                tooling_root,
                "adoption-plan",
                "--out",
                "docs/not_plans/packet_inbox_adoption.md",
            )

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("target plan output must stay under docs/plans/", result.stderr)


class PostMergePacketizationGateTests(unittest.TestCase):
    def _write_file(self, root: Path, relative_path: str, content: str) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _run_gate(
        self,
        root: Path,
        *args: str,
        content_profile_id: str = "planveyor",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACKETIZATION_GATE_SCRIPT),
                "--repo-root",
                str(root),
                "--range",
                "a" * 40 + ".." + "b" * 40,
                "--now",
                "2026-05-11T10:00:00",
                "--content-profile-id",
                content_profile_id,
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_gate_for_range(
        self,
        root: Path,
        *,
        range_ref: str,
        args: list[str],
        content_profile_id: str = "planveyor",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACKETIZATION_GATE_SCRIPT),
                "--repo-root",
                str(root),
                "--range",
                range_ref,
                "--now",
                "2026-05-11T10:00:00",
                "--content-profile-id",
                content_profile_id,
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _pi_backlog_text(
        self,
        *,
        status: str,
        priority: str,
        target_canon_path: str,
        target_repo_scope: str,
        delivery_mode: str,
        execution_kind: str,
        execution_ref: str,
        delivery_refs: str,
        triage_note: str,
    ) -> str:
        return self._pi_backlog_entries_text(
            [
                {
                    "entry_id": "PI-001",
                    "status": status,
                    "priority": priority,
                    "target_canon_path": target_canon_path,
                    "target_repo_scope": target_repo_scope,
                    "delivery_mode": delivery_mode,
                    "execution_kind": execution_kind,
                    "execution_ref": execution_ref,
                    "delivery_refs": delivery_refs,
                    "triage_note": triage_note,
                }
            ]
        )

    def _pi_backlog_entries_text(self, entries: list[dict[str, str]]) -> str:
        rendered_entries = []
        for entry in entries:
            rendered_entries.append(
                textwrap.dedent(
                    f"""\
                    ### {entry['entry_id']}
                    - status: `{entry['status']}`
                    - priority: `{entry['priority']}`
                    - role: `Coder`
                    - owner: `Architect`
                    - promotion_class: `helper_change`
                    - target_canon_path: `{entry['target_canon_path']}`
                    - target_repo_scope: `{entry['target_repo_scope']}`
                    - delivery_mode: `{entry['delivery_mode']}`
                    - execution_kind: `{entry['execution_kind']}`
                    - execution_ref: `{entry['execution_ref']}`
                    - delivery_refs: `{entry['delivery_refs']}`
                    - handled_ref: `null`
                    - promoted_at: `null`
                    - handled_at: `null`
                    - trigger_ref: `docs/code_reviews/current.md#B1`
                    - source_ref: `docs/plans/pi_source.md`
                    - symptom: `range PI applicability needs exact evidence`
                    - process_gap: `packetization must not infer target intent`
                    - suggested_fix: `derive the target partition from the snapshot delta`
                    - created_at: `2026-05-11 10:00 MSK`
                    - triage_note: `{entry['triage_note']}`
                    """
                )
            )
        return textwrap.dedent(
            f"""\
            # Process improvements backlog - packetization fixture

            **Date:** 2026-05-11 10:00 MSK
            **Source ref:** `docs/plans/pi_source.md`
            **Status:** Draft

            ## Suggestions (truth)
            """
        ) + "\n".join(rendered_entries)

    def _gate_payload(self, stdout: str) -> dict[str, object]:
        return json.loads(stdout)["packetization_gate"]

    def _consumer_mirror_policy(self, source_artifacts: list[str]):
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import shared_docs_mirror_drift

        return shared_docs_mirror_drift.MirrorPolicy(
            set_id="consumer-fixture",
            static_paths=tuple(source_artifacts),
            glob_patterns=(),
            target_repo="consumer-fixture",
            target_kind="mirror_sync",
        )

    def _build_payload_with_consumer_mirror(self, root: Path, source_artifacts: list[str]) -> dict[str, object]:
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import post_merge_packetization_gate as packetization

        return packetization.build_payload(
            root,
            range_ref="a" * 40 + ".." + "b" * 40,
            changed_files=source_artifacts,
            create_drafts=False,
            now=packetization.parse_now("2026-05-11T10:00:00"),
            mirror_policy=self._consumer_mirror_policy(source_artifacts),
        )

    def _build_payload_with_explicit_consumer_mapping(
        self,
        root: Path,
        *,
        changed_file: str,
        target_carrier: str,
        target_kind: str = "consumer_only",
    ) -> dict[str, object]:
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import post_merge_packetization_gate as packetization

        mapping = {
            changed_file: (
                (
                    "consumer-fixture",
                    target_kind,
                    (target_carrier,),
                    "test declared consumer applicability",
                ),
            )
        }
        with mock.patch.dict(packetization.EXPLICIT_TARGET_APPLICABILITY, mapping, clear=True):
            return packetization.build_payload(
                root,
                range_ref="a" * 40 + ".." + "b" * 40,
                changed_files=[changed_file],
                create_drafts=False,
                now=packetization.parse_now("2026-05-11T10:00:00"),
            )

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def _commit_all(self, root: Path, message: str) -> str:
        add = self._git(root, "add", "-A")
        self.assertEqual(add.returncode, 0, add.stderr)
        commit = self._git(root, "commit", "-m", message)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        head = self._git(root, "rev-parse", "HEAD")
        self.assertEqual(head.returncode, 0, head.stderr)
        return head.stdout.strip()

    def _run_recovery(
        self,
        root: Path,
        *,
        range_ref: str,
        source_plan: str | None = None,
        args: list[str],
        content_profile_id: str = "planveyor",
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(PACKETIZATION_GATE_SCRIPT),
            "--repo-root",
            str(root),
            "--recover",
            "--range",
            range_ref,
            "--content-profile-id",
            content_profile_id,
        ]
        if source_plan is not None:
            command.extend(("--source-plan", source_plan))
        command.extend(
            (
                "--now",
                "2026-05-11T10:00:00",
                *args,
            )
        )
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    def _init_recovery_repo(self, root: Path) -> tuple[str, str, str, str]:
        init = self._git(root, "init")
        self.assertEqual(init.returncode, 0, init.stderr)
        self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
        self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
        self._write_file(root, "README.md", "seed\n")
        base = self._commit_all(root, "seed")
        source_plan = "docs/plans/260511_1000_process_packetization.md"
        unrelated_done_plan = "docs/plans/260511_1001_process_unrelated.md"
        changed_file = "docs/process_improvements/recovery__process_improvements_backlog.md"
        consumer_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        partner_carrier = "docs/tools/prompts/owner_merge_pipeline.md"
        self._write_file(root, source_plan, "# Packetization\n\n**Status:** Done\n")
        self._write_file(root, unrelated_done_plan, "# Unrelated\n\n**Status:** Done\n")
        self._write_file(
            root,
            changed_file,
            self._pi_backlog_entries_text(
                [
                    {
                        "entry_id": "PI-001",
                        "status": "triaged",
                        "priority": "P1",
                        "target_canon_path": consumer_carrier,
                        "target_repo_scope": "consumer-fixture",
                        "delivery_mode": "source_plus_rollout",
                        "execution_kind": "canon_doc",
                        "execution_ref": "docs/plans/consumer_packet.md",
                        "delivery_refs": "docs/rollout_packets/consumer_packet.md",
                        "triage_note": "first literal consumer delivery",
                    },
                    {
                        "entry_id": "PI-002",
                        "status": "triaged",
                        "priority": "P1",
                        "target_canon_path": partner_carrier,
                        "target_repo_scope": "partner-fixture",
                        "delivery_mode": "source_plus_rollout",
                        "execution_kind": "canon_doc",
                        "execution_ref": "docs/plans/partner_packet.md",
                        "delivery_refs": "docs/rollout_packets/partner_packet.md",
                        "triage_note": "second literal consumer delivery",
                    },
                ]
            ),
        )
        head = self._commit_all(root, "literal consumer packetization change")
        self._recovery_changed_files = [changed_file]
        self._recovery_target_carriers = {
            "consumer-fixture": consumer_carrier,
            "partner-fixture": partner_carrier,
        }
        return base, head, source_plan, changed_file

    def _write_recovery_packet(
        self,
        root: Path,
        *,
        name: str,
        target_repo: str,
        source_plan: str,
        target_carrier: str,
        status: str = "open",
    ) -> Path:
        return self._write_file(
            root,
            f"docs/rollout_packets/{name}.md",
            _packet_text(
                packet_id=f"260511_1000_{name}",
                target_repo=target_repo,
                status=status,
                source_plan=source_plan,
                source_artifacts=["docs/stale.md"],
                target_writable_carriers=[target_carrier],
                target_kind="consumer_only",
                extra_body=_current_delivery_sections(
                    source_artifacts=["docs/stale.md"],
                    target_writable_carriers=[target_carrier],
                ),
            ),
        )

    def _packet_meta(self, packet_path: Path) -> dict[str, object]:
        text = packet_path.read_text(encoding="utf-8")
        start = text.index("```json\n") + len("```json\n")
        end = text.index("```", start)
        return json.loads(text[start:end])["packet_meta"]

    def test_generic_consumer_packet_adoption_outcome_and_source_ack_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rollout_packet_generic_consumer_") as tmpdir:
            base = Path(tmpdir)
            source_root = base / "planveyor"
            target_root = base / "consumer-fixture"
            source_root.mkdir()
            target_root.mkdir()

            def run(repo_root: Path, tooling_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--repo-root",
                        str(repo_root),
                        "--tooling-root",
                        str(tooling_root),
                        *args,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )

            self.assertEqual(self._git(source_root, "init").returncode, 0)
            self.assertEqual(self._git(source_root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
            self.assertEqual(self._git(source_root, "config", "user.name", "Packet Tests").returncode, 0)
            self._write_file(source_root, "docs/plans/source.md", "# Source\n\n**Status:** Done\n")
            self._write_file(
                source_root,
                "docs/rollout_packets/_template.md",
                (REPO_ROOT / "docs/rollout_packets/_template.md").read_text(encoding="utf-8"),
            )
            self._commit_all(source_root, "seed source packet corpus")

            create = run(
                source_root,
                source_root,
                "create",
                "consumer-fixture",
                "generic_lifecycle",
                "--source-plan",
                "docs/plans/source.md",
                "--target-kind",
                "plan_adoption",
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            packet_rel = next(
                line.removeprefix("Packet path: ")
                for line in create.stdout.splitlines()
                if line.startswith("Packet path: ")
            )
            packet_path = source_root / packet_rel
            packet_meta = self._packet_meta(packet_path)
            self.assertEqual(packet_meta["source_repo"], "current-consumer")
            self.assertEqual(packet_meta["target_repo"], "consumer-fixture")
            self._commit_all(source_root, "record generic consumer packet")

            adoption = run(
                target_root,
                source_root,
                "adoption-plan",
                "--target-repo",
                "consumer-fixture",
                "--out",
                "docs/plans/adoption.md",
            )
            self.assertEqual(adoption.returncode, 0, adoption.stderr)
            plan_rel = "docs/plans/adoption.md"
            self.assertTrue((target_root / plan_rel).is_file())
            adoption_carrier = _carrier_payload_from_text((target_root / plan_rel).read_text(encoding="utf-8"))
            self.assertEqual(adoption_carrier["rollout_packet_import"]["source_repo"], "current-consumer")

            outcome = run(
                target_root,
                source_root,
                "outcome-set",
                "--target-plan",
                plan_rel,
                "--packet-id",
                str(packet_meta["id"]),
                "--packet-path",
                packet_rel,
                "--outcome",
                "adopted",
            )
            self.assertEqual(outcome.returncode, 0, outcome.stderr)

            ack = run(
                source_root,
                source_root,
                "ack",
                "--packet",
                packet_rel,
                "--status",
                "imported",
                "--target-plan",
                plan_rel,
            )
            self.assertEqual(ack.returncode, 0, ack.stderr)

            query = run(source_root, source_root, "query", "--status", "imported", "--json")
            self.assertEqual(query.returncode, 0, query.stderr)
            rows = json.loads(query.stdout)["packets"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["target_repo"], "consumer-fixture")
            self.assertEqual(rows[0]["target_local_plan"], plan_rel)

            reconcile = run(
                source_root,
                source_root,
                "reconcile",
                "--report",
                "--target-root",
                str(target_root),
                "--target-repo",
                "consumer-fixture",
                "--json",
            )
            self.assertEqual(reconcile.returncode, 0, reconcile.stderr)
            readback = json.loads(reconcile.stdout)["rows"]
            self.assertEqual(len(readback), 1)
            self.assertEqual(readback[0]["target_outcome"], "adopted")

    def test_source_owned_paths_retired_profile_carriers_and_explicit_target_mapping(self) -> None:
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import post_merge_packetization_gate as packetization
        import shared_docs_mirror_drift

        for path in (
            "docs/roles/architect.md",
            "docs/playbooks/analysis_wave.md",
            "docs/tools/prompts/decomposition.md",
        ):
            with self.subTest(path=path):
                result = packetization.resolve_target_applicability(REPO_ROOT, changed_files=[path])
                self.assertEqual(result.partitions, ())
                self.assertEqual(len(result.records), 1)
                record = result.records[0]
                self.assertEqual(record.target_repo, "current-consumer")
                self.assertEqual(record.target_kind, "source_only")
                self.assertEqual(record.source_only_reason, "tooling-owned canon has no explicit target mapping")
                self.assertEqual(record.authority, "checked-in source ownership policy")
                self.assertFalse(record.target_writable_carriers)
                self.assertEqual(
                    packetization.classify_changed_file(path).targets,
                    ("current-consumer",),
                )

        for source_repo, expected in (
            ("current-consumer", True),
            ("current_consumer", False),
            ("planveyor", False),
            ("wrong-source", False),
        ):
            for target_repo in ("consumer-fixture", "planveyor"):
                with self.subTest(source_repo=source_repo, target_repo=target_repo):
                    self.assertEqual(
                        packetization.packet_matches_envelope(
                            {
                                "source_repo": source_repo,
                                "target_repo": target_repo,
                                "target_kind": "consumer_only",
                                "status": "open",
                            },
                            target_repo=target_repo,
                            target_kind="consumer_only",
                        ),
                        expected,
                    )
        self.assertTrue(
            packetization.packet_matches_envelope(
                {
                    "source_repo": "current-consumer",
                    "target_repo": "shared-consumer",
                    "target_kind": "consumer_only",
                    "status": "open",
                },
                target_repo="shared-consumer",
                target_kind="consumer_only",
            )
        )

        profile_prompt = "docs/tools/prompts/profiles/retired/manager_collab_pipeline.md"
        prompt_result = packetization.resolve_target_applicability(REPO_ROOT, changed_files=[profile_prompt])
        self.assertEqual(len(prompt_result.records), 1)
        prompt_record = prompt_result.records[0]
        self.assertEqual(prompt_record.target_repo, "unknown")
        self.assertEqual(prompt_record.target_kind, "unknown")
        self.assertEqual(
            prompt_record.blocking_reason,
            "unknown target mapping: retired profile carrier has no public source or consumer mapping",
        )
        self.assertEqual(prompt_record.authority, "public corpus boundary")

        empty_mapping = "docs/tools/prompts/fixture_empty_target_mapping.md"
        with mock.patch.dict(packetization.EXPLICIT_TARGET_APPLICABILITY, {empty_mapping: ()}):
            empty_result = packetization.resolve_target_applicability(REPO_ROOT, changed_files=[empty_mapping])
        self.assertEqual(empty_result.partitions, ())
        self.assertEqual(len(empty_result.records), 1)
        self.assertEqual(empty_result.records[0].blocking_reason, "explicit target applicability is empty")

        explicit_mapping = "docs/tools/prompts/owner_merge_pipeline.md"
        with mock.patch.dict(
            packetization.EXPLICIT_TARGET_APPLICABILITY,
            {
                explicit_mapping: (
                    (
                        "consumer-fixture",
                        "consumer_only",
                        ("docs/tools/prompts/owner_merge_pipeline.md",),
                        "test declared consumer applicability",
                    ),
                )
            },
        ):
            explicit_result = packetization.resolve_target_applicability(REPO_ROOT, changed_files=[explicit_mapping])
        self.assertEqual(len(explicit_result.partitions), 1)
        explicit_partition = explicit_result.partitions[0]
        self.assertEqual((explicit_partition.target_repo, explicit_partition.target_kind), ("consumer-fixture", "consumer_only"))
        self.assertEqual(explicit_partition.target_writable_carriers, (explicit_mapping,))

        mirror_path = "docs/plans/_template.md"
        for profile_id in ("default", "planveyor", "target-local"):
            self.assertEqual(
                shared_docs_mirror_drift.load_shared_docs_mirror_policy(content_profile_id=profile_id),
                shared_docs_mirror_drift.GENERIC_MIRROR_POLICY,
            )
        mirror_policy = shared_docs_mirror_drift.MirrorPolicy(
            set_id="consumer-fixture",
            static_paths=(mirror_path,),
            glob_patterns=(),
            target_repo="consumer-fixture",
            target_kind="mirror_sync",
        )
        mirror_result = packetization.resolve_target_applicability(
            REPO_ROOT,
            changed_files=[mirror_path],
            mirror_policy=mirror_policy,
        )
        self.assertEqual(len(mirror_result.records), 1)
        mirror_record = mirror_result.records[0]
        self.assertEqual(mirror_record.target_repo, "consumer-fixture")
        self.assertEqual(mirror_record.target_kind, "mirror_sync")
        self.assertEqual(mirror_record.target_writable_carriers, (mirror_path,))
        self.assertEqual(
            mirror_record.authority,
            "declared mirror policy; shared_docs_mirror_drift declared static_paths/glob_patterns",
        )
        self.assertEqual(len(mirror_result.partitions), 1)
        mirror_partition = mirror_result.partitions[0]
        self.assertEqual((mirror_partition.target_repo, mirror_partition.target_kind), ("consumer-fixture", "mirror_sync"))
        self.assertEqual(mirror_partition.target_source_artifacts, (mirror_path,))
        self.assertEqual(mirror_partition.target_writable_carriers, (mirror_path,))
        self.assertEqual(mirror_partition.authority, mirror_record.authority)

    def test_russian_copies_keep_original_packetization_classification(self) -> None:
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import post_merge_packetization_gate as packetization

        def projection(path: str) -> tuple[object, ...]:
            result = packetization.resolve_target_applicability(REPO_ROOT, changed_files=[path])
            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            return (
                record.target_repo,
                record.target_kind,
                record.authority,
                record.source_only_reason,
                record.blocking_reason,
                record.ignored_reason,
                result.packetization_report_required,
                packetization.classify_changed_file(path),
            )

        runbook_copy = "docs/tools/owner_runbook_codex.ru.md"
        self.assertEqual(
            projection(runbook_copy),
            (
                "current-consumer",
                "source_only",
                "checked-in source-only root policy",
                "owner runbook is planveyor operator guidance",
                None,
                None,
                True,
                packetization.Classification(
                    ("current-consumer",),
                    source_only_reason="owner runbook is planveyor operator guidance",
                ),
            ),
        )
        for original, russian_copy in (
            ("docs/tools/owner_runbook_codex.md", runbook_copy),
            ("docs/guides/stack-sibling.md", "docs/guides/stack-sibling.ru.md"),
            ("docs/guides/learn/README.md", "docs/guides/learn/README.ru.md"),
            ("docs/tools/prompts/README.md", "docs/tools/prompts/README.ru.md"),
            ("docs/tools/verify_suite.md", "docs/tools/verify_suite.ru.md"),
        ):
            with self.subTest(path=russian_copy):
                self.assertEqual(projection(russian_copy), projection(original))

    def test_packetization_gate_reports_missing_packet_for_declared_consumer_mirror(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            source_artifacts = ["docs/plans/_template.md"]
            payload = self._build_payload_with_consumer_mirror(root, source_artifacts)
            self.assertEqual(payload["schema_version"], "packetization_gate.v1")
            rows = payload["rows"]
            self.assertEqual({row["target_repo"] for row in rows}, {"consumer-fixture"})
            self.assertEqual({row["target_kind"] for row in rows}, {"mirror_sync"})
            self.assertEqual({row["coverage"] for row in rows}, {"missing-packet"})
            self.assertEqual(payload["blocking_count"], 1)
            scripts_dir = str(REPO_ROOT / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import post_merge_packetization_gate as packetization

            report = packetization.render_report(payload)
            self.assertIn("missing-packet", report)
            self.assertIn("**Schema version:** `packetization_gate.v1`", report)
            self.assertIn(
                'planveyor_post_merge_packetization_gate_recover --range "$(planveyor_range_base)..$(planveyor_range_head)"',
                report,
            )

    def test_packetization_gate_generic_profile_has_no_implicit_mirror_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            result = self._run_gate(
                root,
                "--changed-file",
                "docs/plans/_template.md",
                "--out",
                "docs/reviews/report.md",
                "--json",
                content_profile_id="default",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertFalse(payload["target_packet_required"])
            self.assertEqual(payload["target_partitions"], [])
            self.assertEqual(payload["rows"], [])
            self.assertEqual(payload["ignored_changed_files_count"], 1)

    def test_packetization_gate_aggregates_mirror_members_into_one_target_partition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            source_artifacts = [
                "docs/plans/_template.md",
                "docs/reviews/_template_plan_harvest.md",
            ]
            self._write_file(
                root,
                "docs/rollout_packets/mirror_partition.md",
                _packet_text(
                    packet_id="260511_1000_mirror_partition",
                    target_repo="consumer-fixture",
                    source_artifacts=source_artifacts,
                    target_writable_carriers=source_artifacts,
                    target_kind="mirror_sync",
                    extra_body=_current_delivery_sections(
                        source_artifacts=source_artifacts,
                        target_writable_carriers=source_artifacts,
                    ),
                ),
            )

            payload = self._build_payload_with_consumer_mirror(root, source_artifacts)
            self.assertEqual(payload["blocking_count"], 0)
            self.assertEqual(
                payload["target_partitions"],
                [
                    {
                        "target_repo": "consumer-fixture",
                        "target_kind": "mirror_sync",
                        "target_source_artifacts": source_artifacts,
                        "target_writable_carriers": source_artifacts,
                        "authority": "declared mirror policy; shared_docs_mirror_drift declared static_paths/glob_patterns",
                    }
                ],
            )
            self.assertEqual({row["packet_path"] for row in payload["rows"]}, {"docs/rollout_packets/mirror_partition.md"})
            self.assertEqual(
                {tuple(row["target_writable_carriers"]) for row in payload["rows"]},
                {tuple(source_artifacts)},
            )

    def test_packetization_gate_rejects_split_packets_for_one_aggregate_mirror_partition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            source_artifacts = [
                "docs/plans/_template.md",
                "docs/reviews/_template_plan_harvest.md",
            ]
            for index, path in enumerate(source_artifacts, start=1):
                self._write_file(
                    root,
                    f"docs/rollout_packets/mirror_split_{index}.md",
                    _packet_text(
                        packet_id=f"260511_1000_mirror_split_{index}",
                        target_repo="consumer-fixture",
                        source_artifacts=[path],
                        target_writable_carriers=[path],
                        target_kind="mirror_sync",
                        extra_body=_current_delivery_sections(
                            source_artifacts=[path],
                            target_writable_carriers=[path],
                        ),
                    ),
                )

            payload = self._build_payload_with_consumer_mirror(root, source_artifacts)
            self.assertEqual(payload["blocking_count"], 2)
            self.assertEqual(len(payload["target_partitions"]), 1)
            self.assertEqual({row["coverage"] for row in payload["rows"]}, {"missing-packet"})

    def test_packetization_gate_source_only_only_range_requires_report_but_no_packet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/tools/owner_runbook_codex.md",
                "--out",
                "docs/reviews/report.md",
                "--json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertTrue(payload["packetization_report_required"])
            self.assertFalse(payload["target_packet_required"])
            self.assertEqual(payload["target_partitions"], [])
            self.assertEqual(payload["blocking_count"], 0)
            self.assertEqual(payload["report_accepted_packet_paths"], [])
            self.assertEqual(payload["rows"][0]["coverage"], "source_only")
            self.assertFalse(payload["rows"][0]["blocking"])
            self.assertTrue((root / "docs/reviews/report.md").is_file())

    def test_packetization_gate_process_improvement_delta_uses_exact_partition_and_transition_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_pi_") as tmpdir:
            root = Path(tmpdir)
            self.assertEqual(self._git(root, "init").returncode, 0)
            self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
            self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
            backlog_path = "docs/process_improvements/pi__process_improvements_backlog.md"
            self._write_file(root, "README.md", "seed\n")
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="open",
                    priority="P?",
                    target_canon_path="null",
                    target_repo_scope="null",
                    delivery_mode="null",
                    execution_kind="null",
                    execution_ref="null",
                    delivery_refs="null",
                    triage_note="new source-only observation",
                ),
            )
            base = self._commit_all(root, "source-only PI")

            target_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="triaged",
                    priority="P1",
                    target_canon_path=target_carrier,
                    target_repo_scope="consumer-fixture",
                    delivery_mode="source_plus_rollout",
                    execution_kind="plan",
                    execution_ref="docs/plans/pi_target.md",
                    delivery_refs="docs/rollout_packets/pi_target.md",
                    triage_note="target adoption selected",
                ),
            )
            head = self._commit_all(root, "target-bearing PI")
            self._write_file(
                root,
                "docs/rollout_packets/pi_target.md",
                _packet_text(
                    packet_id="260511_1000_pi_target",
                    target_repo="consumer-fixture",
                    source_artifacts=[backlog_path],
                    target_writable_carriers=[target_carrier],
                    target_kind="plan_adoption",
                    extra_body=_current_delivery_sections(
                        source_artifacts=[backlog_path],
                        target_writable_carriers=[target_carrier],
                    ),
                ),
            )

            green = self._run_gate_for_range(
                root,
                range_ref=f"{base}..{head}",
                args=["--out", "docs/reviews/pi-green.md", "--json"],
            )
            self.assertEqual(green.returncode, 0, green.stderr + green.stdout)
            green_payload = self._gate_payload(green.stdout)
            self.assertEqual(green_payload["source_artifacts"], [backlog_path])
            self.assertEqual(
                green_payload["target_partitions"],
                [
                    {
                        "target_repo": "consumer-fixture",
                        "target_kind": "plan_adoption",
                        "target_source_artifacts": [backlog_path],
                        "target_writable_carriers": [target_carrier],
                        "authority": f"process-improvements {backlog_path}#PI-001",
                    }
                ],
            )
            self.assertEqual(green_payload["rows"][0]["coverage"], "covered")

            changed_carrier = "docs/tools/prompts/other.md"
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="triaged",
                    priority="P1",
                    target_canon_path=changed_carrier,
                    target_repo_scope="consumer-fixture",
                    delivery_mode="source_plus_rollout",
                    execution_kind="plan",
                    execution_ref="docs/plans/pi_target.md",
                    delivery_refs="docs/rollout_packets/pi_target.md",
                    triage_note="target carrier changed without authority",
                ),
            )
            add = self._git(root, "add", "--", backlog_path)
            self.assertEqual(add.returncode, 0, add.stderr)
            commit = self._git(root, "commit", "-m", "unauthorized PI target transition")
            self.assertEqual(commit.returncode, 0, commit.stderr)
            changed_head = self._git(root, "rev-parse", "HEAD").stdout.strip()

            red = self._run_gate_for_range(
                root,
                range_ref=f"{head}..{changed_head}",
                args=["--out", "docs/reviews/pi-red.md", "--json"],
            )
            self.assertEqual(red.returncode, 2, red.stderr)
            red_payload = self._gate_payload(red.stdout)
            self.assertTrue(red_payload["target_packet_required"])
            self.assertTrue(
                any(
                    "without packetization withdrawal/replacement authority" in str(row["action"])
                    for row in red_payload["rows"]
                ),
                red.stdout,
            )

    def test_packetization_gate_aggregates_same_target_process_improvement_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_pi_") as tmpdir:
            root = Path(tmpdir)
            self.assertEqual(self._git(root, "init").returncode, 0)
            self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
            self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
            backlog_path = "docs/process_improvements/pi__process_improvements_backlog.md"
            self._write_file(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            target_carriers = [
                "docs/tools/prompts/manager_collab_merge_pipeline.md",
                "docs/tools/prompts/owner_merge_pipeline.md",
            ]
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_entries_text(
                    [
                        {
                            "entry_id": "PI-001",
                            "status": "triaged",
                            "priority": "P1",
                            "target_canon_path": target_carriers[0],
                            "target_repo_scope": "consumer-fixture",
                            "delivery_mode": "source_plus_rollout",
                            "execution_kind": "plan",
                            "execution_ref": "docs/plans/pi_target.md",
                            "delivery_refs": "docs/rollout_packets/pi_target.md",
                            "triage_note": "first exact target carrier",
                        },
                        {
                            "entry_id": "PI-002",
                            "status": "triaged",
                            "priority": "P1",
                            "target_canon_path": target_carriers[1],
                            "target_repo_scope": "consumer-fixture",
                            "delivery_mode": "source_plus_rollout",
                            "execution_kind": "plan",
                            "execution_ref": "docs/plans/pi_target.md",
                            "delivery_refs": "docs/rollout_packets/pi_target.md",
                            "triage_note": "second exact target carrier",
                        },
                    ]
                ),
            )
            head = self._commit_all(root, "same target PI entries")
            self._write_file(
                root,
                "docs/rollout_packets/pi_target.md",
                _packet_text(
                    packet_id="260511_1000_pi_target",
                    target_repo="consumer-fixture",
                    source_artifacts=[backlog_path],
                    target_writable_carriers=target_carriers,
                    target_kind="plan_adoption",
                    extra_body=_current_delivery_sections(
                        source_artifacts=[backlog_path],
                        target_writable_carriers=target_carriers,
                    ),
                ),
            )

            result = self._run_gate_for_range(
                root,
                range_ref=f"{base}..{head}",
                args=["--out", "docs/reviews/pi-aggregate.md", "--json"],
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(
                payload["target_partitions"],
                [
                    {
                        "target_repo": "consumer-fixture",
                        "target_kind": "plan_adoption",
                        "target_source_artifacts": [backlog_path],
                        "target_writable_carriers": target_carriers,
                        "authority": (
                            f"process-improvements {backlog_path}#PI-001; "
                            f"process-improvements {backlog_path}#PI-002"
                        ),
                    }
                ],
            )
            self.assertEqual({row["coverage"] for row in payload["rows"]}, {"covered"})
            self.assertEqual({row["packet_path"] for row in payload["rows"]}, {"docs/rollout_packets/pi_target.md"})
            self.assertEqual(
                {tuple(row["target_writable_carriers"]) for row in payload["rows"]},
                {tuple(target_carriers)},
            )

    def test_packetization_gate_process_improvement_removal_uses_head_packet_authority(self) -> None:
        backlog_path = "docs/process_improvements/pi__process_improvements_backlog.md"
        old_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        old_packet_path = "docs/rollout_packets/pi_old.md"

        def initialise_base(root: Path, *, delivery_refs: str = old_packet_path) -> str:
            self.assertEqual(self._git(root, "init").returncode, 0)
            self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
            self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
            self._write_file(root, "README.md", "seed\n")
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="triaged",
                    priority="P1",
                    target_canon_path=old_carrier,
                    target_repo_scope="consumer-fixture",
                    delivery_mode="source_plus_rollout",
                    execution_kind="plan",
                    execution_ref="docs/plans/pi_target.md",
                    delivery_refs=delivery_refs,
                    triage_note="old target delivery selected",
                ),
            )
            return self._commit_all(root, "old target PI")

        def cancelled_old_packet(
            *,
            status: str = "cancelled",
            reason: str | None = "packetization_withdrawal_ref=docs/rollout_packets/pi_old.md",
            target_carrier: str = old_carrier,
            source_artifacts: list[str] | None = None,
        ) -> str:
            artifacts = source_artifacts if source_artifacts is not None else [backlog_path]
            return _packet_text(
                packet_id="260511_1000_pi_old",
                target_repo="consumer-fixture",
                status=status,
                reason=reason,
                source_artifacts=artifacts,
                target_writable_carriers=[target_carrier],
                target_kind="plan_adoption",
                extra_body=_current_delivery_sections(
                    source_artifacts=artifacts,
                    target_writable_carriers=[target_carrier],
                ),
            )

        with tempfile.TemporaryDirectory(prefix="packetization_gate_pi_delete_") as tmpdir:
            root = Path(tmpdir)
            base = initialise_base(root)
            (root / backlog_path).unlink()
            self._write_file(root, old_packet_path, cancelled_old_packet())
            head = self._commit_all(root, "withdraw old PI through HEAD packet")

            green = self._run_gate_for_range(
                root,
                range_ref=f"{base}..{head}",
                args=["--out", "docs/reviews/pi-delete-green.md", "--json"],
            )

            self.assertEqual(green.returncode, 0, green.stderr + green.stdout)
            green_payload = self._gate_payload(green.stdout)
            self.assertEqual(green_payload["target_partitions"], [])
            self.assertFalse(green_payload["target_packet_required"])

        negative_packets: dict[str, tuple[str | None, str]] = {
            "missing": (None, old_packet_path),
            "non_packet_ref": (None, "docs/reviews/pi_old.md"),
            "open": (cancelled_old_packet(status="open"), old_packet_path),
            "missing_reason": (cancelled_old_packet(reason=None), old_packet_path),
            "unrelated_ref": (
                cancelled_old_packet(reason="packetization_withdrawal_ref=docs/rollout_packets/unrelated.md"),
                old_packet_path,
            ),
            "duplicate_ref": (
                cancelled_old_packet(
                    reason=(
                        f"packetization_withdrawal_ref={old_packet_path}; "
                        f"packetization_withdrawal_ref={old_packet_path}"
                    )
                ),
                old_packet_path,
            ),
            "ambiguous_refs": (
                cancelled_old_packet(
                    reason=(
                        f"packetization_withdrawal_ref={old_packet_path}; "
                        f"packetization_replacement_ref={old_packet_path}"
                    )
                ),
                old_packet_path,
            ),
            "malformed_ref": (
                cancelled_old_packet(reason="packetization_withdrawal_ref=docs/reviews/pi_old.md"),
                old_packet_path,
            ),
            "wrong_carrier": (cancelled_old_packet(target_carrier="docs/tools/prompts/other.md"), old_packet_path),
            "wrong_source_artifact": (cancelled_old_packet(source_artifacts=["docs/unrelated.md"]), old_packet_path),
            "malformed": (_malformed_packet_text(target_repo="consumer-fixture"), old_packet_path),
        }
        for name, (packet_text, delivery_refs) in negative_packets.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="packetization_gate_pi_delete_") as tmpdir:
                root = Path(tmpdir)
                base = initialise_base(root, delivery_refs=delivery_refs)
                (root / backlog_path).unlink()
                if packet_text is not None:
                    self._write_file(root, old_packet_path, packet_text)
                head = self._commit_all(root, f"invalid deletion authority {name}")
                red = self._run_gate_for_range(
                    root,
                    range_ref=f"{base}..{head}",
                    args=["--out", f"docs/reviews/pi-delete-{name}.md", "--json"],
                )
                self.assertNotEqual(red.returncode, 0, red.stderr + red.stdout)
                if name != "malformed":
                    self.assertEqual(red.returncode, 2, red.stderr + red.stdout)
                    self.assertTrue(
                        any(
                            "without packetization withdrawal/replacement authority" in str(row["action"])
                            for row in self._gate_payload(red.stdout)["rows"]
                        ),
                        red.stdout,
                    )

        with tempfile.TemporaryDirectory(prefix="packetization_gate_pi_worktree_") as tmpdir:
            root = Path(tmpdir)
            base = initialise_base(root)
            (root / backlog_path).unlink()
            head = self._commit_all(root, "delete PI without committed authority")
            self._write_file(root, old_packet_path, cancelled_old_packet())
            red = self._run_gate_for_range(
                root,
                range_ref=f"{base}..{head}",
                args=["--out", "docs/reviews/pi-worktree-authority.md", "--json"],
            )
            self.assertEqual(red.returncode, 2, red.stderr + red.stdout)

        with tempfile.TemporaryDirectory(prefix="packetization_gate_pi_replace_") as tmpdir:
            root = Path(tmpdir)
            base = initialise_base(root)
            new_carrier = "docs/tools/prompts/owner_merge_pipeline.md"
            new_packet_path = "docs/rollout_packets/pi_new.md"
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="triaged",
                    priority="P1",
                    target_canon_path=new_carrier,
                    target_repo_scope="consumer-fixture",
                    delivery_mode="source_plus_rollout",
                    execution_kind="plan",
                    execution_ref="docs/plans/pi_target.md",
                    delivery_refs=f"{old_packet_path}; {new_packet_path}",
                    triage_note="new target delivery selected",
                ),
            )
            self._write_file(root, old_packet_path, cancelled_old_packet())
            self._write_file(
                root,
                new_packet_path,
                _packet_text(
                    packet_id="260511_1000_pi_new",
                    target_repo="consumer-fixture",
                    source_artifacts=[backlog_path],
                    target_writable_carriers=[new_carrier],
                    target_kind="plan_adoption",
                    extra_body=_current_delivery_sections(
                        source_artifacts=[backlog_path],
                        target_writable_carriers=[new_carrier],
                    ),
                ),
            )
            head = self._commit_all(root, "replace PI target through HEAD packet")
            green = self._run_gate_for_range(
                root,
                range_ref=f"{base}..{head}",
                args=["--out", "docs/reviews/pi-replace-green.md", "--json"],
            )
            self.assertEqual(green.returncode, 0, green.stderr + green.stdout)
            payload = self._gate_payload(green.stdout)
            self.assertEqual(payload["target_partitions"][0]["target_writable_carriers"], [new_carrier])
            self.assertEqual(payload["rows"][0]["packet_path"], new_packet_path)

    def test_packetization_gate_process_improvement_transition_note_requires_one_base_packet_ref(self) -> None:
        backlog_path = "docs/process_improvements/pi__process_improvements_backlog.md"
        old_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        new_carrier = "docs/tools/prompts/owner_merge_pipeline.md"
        old_packet_path = "docs/rollout_packets/pi_old.md"
        new_packet_path = "docs/rollout_packets/pi_new.md"

        def initialise_base(root: Path) -> str:
            self.assertEqual(self._git(root, "init").returncode, 0)
            self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
            self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
            self._write_file(root, "README.md", "seed\n")
            self._write_file(
                root,
                backlog_path,
                self._pi_backlog_text(
                    status="triaged",
                    priority="P1",
                    target_canon_path=old_carrier,
                    target_repo_scope="consumer-fixture",
                    delivery_mode="source_plus_rollout",
                    execution_kind="plan",
                    execution_ref="docs/plans/pi_target.md",
                    delivery_refs=old_packet_path,
                    triage_note="old target delivery selected",
                ),
            )
            return self._commit_all(root, "old target PI")

        cases = (
            ("matching", f"packetization_replacement_ref={old_packet_path}", 0),
            ("unrelated", "packetization_replacement_ref=docs/rollout_packets/unrelated.md", 2),
            (
                "duplicate",
                (
                    f"packetization_replacement_ref={old_packet_path}; "
                    f"packetization_replacement_ref={old_packet_path}"
                ),
                2,
            ),
            (
                "ambiguous",
                (
                    f"packetization_withdrawal_ref={old_packet_path}; "
                    f"packetization_replacement_ref={old_packet_path}"
                ),
                2,
            ),
            ("malformed", "packetization_replacement_ref=docs/reviews/pi_old.md", 2),
        )
        for name, triage_note, expected_returncode in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="packetization_gate_pi_note_") as tmpdir:
                root = Path(tmpdir)
                base = initialise_base(root)
                self._write_file(
                    root,
                    backlog_path,
                    self._pi_backlog_text(
                        status="triaged",
                        priority="P1",
                        target_canon_path=new_carrier,
                        target_repo_scope="consumer-fixture",
                        delivery_mode="source_plus_rollout",
                        execution_kind="plan",
                        execution_ref="docs/plans/pi_target.md",
                        delivery_refs=new_packet_path,
                        triage_note=triage_note,
                    ),
                )
                self._write_file(
                    root,
                    new_packet_path,
                    _packet_text(
                        packet_id=f"260511_1000_pi_note_{name}",
                        target_repo="consumer-fixture",
                        source_artifacts=[backlog_path],
                        target_writable_carriers=[new_carrier],
                        target_kind="plan_adoption",
                        extra_body=_current_delivery_sections(
                            source_artifacts=[backlog_path],
                            target_writable_carriers=[new_carrier],
                        ),
                    ),
                )
                head = self._commit_all(root, f"PI transition note {name}")

                result = self._run_gate_for_range(
                    root,
                    range_ref=f"{base}..{head}",
                    args=["--out", f"docs/reviews/pi-note-{name}.md", "--json"],
                )

                self.assertEqual(result.returncode, expected_returncode, result.stderr + result.stdout)
                payload = self._gate_payload(result.stdout)
                if expected_returncode == 0:
                    self.assertEqual(payload["rows"][0]["coverage"], "covered")
                    self.assertEqual(payload["rows"][0]["packet_path"], new_packet_path)
                else:
                    self.assertTrue(
                        any(
                            "without packetization withdrawal/replacement authority" in str(row["action"])
                            for row in payload["rows"]
                        ),
                        result.stdout,
                    )

    def test_packetization_gate_process_improvement_status_mode_matrix_fails_closed(self) -> None:
        target_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        target_fields = {
            "priority": "P1",
            "target_canon_path": target_carrier,
            "target_repo_scope": "consumer-fixture",
            "delivery_mode": "source_plus_rollout",
            "execution_kind": "plan",
            "execution_ref": "docs/plans/pi_target.md",
            "delivery_refs": "docs/rollout_packets/pi_target.md",
            "triage_note": "target delivery selected",
        }
        cases = (
            (
                "fully_null_open",
                {
                    "status": "open",
                    "priority": "P?",
                    "target_canon_path": "null",
                    "target_repo_scope": "null",
                    "delivery_mode": "null",
                    "execution_kind": "null",
                    "execution_ref": "null",
                    "delivery_refs": "null",
                    "triage_note": "new source-only observation",
                },
                0,
                "source_only",
            ),
            (
                "fully_null_rejected",
                {
                    "status": "rejected",
                    "priority": "P?",
                    "target_canon_path": "null",
                    "target_repo_scope": "null",
                    "delivery_mode": "null",
                    "execution_kind": "null",
                    "execution_ref": "null",
                    "delivery_refs": "null",
                    "triage_note": "rejected duplicate observation",
                },
                0,
                "source_only",
            ),
            ("unconfirmed", {"status": "unconfirmed", **target_fields}, 2, "invalid_applicability"),
            ("deferred", {"status": "deferred", **target_fields}, 2, "invalid_applicability"),
            (
                "multi_repo",
                {"status": "triaged", **target_fields, "target_repo_scope": "multi_repo"},
                2,
                "invalid_applicability",
            ),
            (
                "umbrella_mixed",
                {"status": "triaged", **target_fields, "delivery_mode": "umbrella_mixed"},
                2,
                "invalid_applicability",
            ),
            (
                "partial_open",
                {
                    "status": "open",
                    "priority": "P1",
                    "target_canon_path": target_carrier,
                    "target_repo_scope": "consumer-fixture",
                    "delivery_mode": "source_plus_rollout",
                    "execution_kind": "null",
                    "execution_ref": "null",
                    "delivery_refs": "null",
                    "triage_note": "partial open carrier",
                },
                2,
                "invalid_applicability",
            ),
        )
        for name, fields, expected_returncode, expected_coverage in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="packetization_gate_pi_") as tmpdir:
                root = Path(tmpdir)
                self.assertEqual(self._git(root, "init").returncode, 0)
                self.assertEqual(self._git(root, "config", "user.email", 'tests' + '@' + 'example' + '.' + 'invalid').returncode, 0)
                self.assertEqual(self._git(root, "config", "user.name", "Packet Tests").returncode, 0)
                self._write_file(root, "README.md", "seed\n")
                base = self._commit_all(root, "seed")
                backlog_path = "docs/process_improvements/pi__process_improvements_backlog.md"
                self._write_file(root, backlog_path, self._pi_backlog_text(**fields))
                head = self._commit_all(root, f"PI {name}")

                result = self._run_gate_for_range(
                    root,
                    range_ref=f"{base}..{head}",
                    args=["--out", "docs/reviews/report.md", "--json"],
                )

                self.assertEqual(result.returncode, expected_returncode, result.stderr + result.stdout)
                payload = self._gate_payload(result.stdout)
                self.assertEqual(payload["rows"][0]["coverage"], expected_coverage)
                self.assertEqual(payload["blocking_count"], 0 if expected_returncode == 0 else 1)

    def test_packetization_gate_plain_output_prints_recovery_command(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)

            result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--out",
                "docs/reviews/report.md",
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("Recovery command:", result.stdout)
            self.assertIn(
                'planveyor_post_merge_packetization_gate_recover --range "$(planveyor_range_base)..$(planveyor_range_head)"',
                result.stdout,
            )

    def test_packetization_gate_reports_coverage_for_open_matching_packet(self) -> None:
        changed_file = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            root.mkdir(exist_ok=True)
            standalone_git_root(root)
            fixture_git = self._git(root, "rev-parse", "--show-toplevel")
            self.assertEqual(fixture_git.returncode, 0, fixture_git.stderr)
            self.assertEqual(Path(fixture_git.stdout.strip()).resolve(), root.resolve())

            self._write_file(
                root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(
                    packet_id="260511_1000_consumer_packetization",
                    target_repo="consumer-fixture",
                    source_artifacts=[changed_file],
                    target_writable_carriers=["docs/tools/prompts/manager_collab_merge_pipeline.md"],
                    target_kind="consumer_only",
                    extra_body=(
                        f"\n## Source artifacts\n- `{changed_file}`\n\n"
                        "## Target writable carriers\n- `docs/tools/prompts/manager_collab_merge_pipeline.md`\n"
                    ),
                ),
            )
            tracked_packet = self._git(root, "add", "--", 'docs/rollout_packets/planveyor_packet.md')
            self.assertEqual(tracked_packet.returncode, 0, tracked_packet.stderr)

            payload = self._build_payload_with_explicit_consumer_mapping(
                root,
                changed_file=changed_file,
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            self.assertEqual(payload["blocking_count"], 0)
            row = payload["rows"][0]
            self.assertEqual(row["coverage"], "covered")
            self.assertEqual(row["packet_status"], "open")
            self.assertEqual(row["target_adoption_state"], "awaiting-target-import")
            self.assertEqual(row["packet_path"], "docs/rollout_packets/planveyor_packet.md")
            scripts_dir = str(REPO_ROOT / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)
            import post_merge_packetization_gate as packetization

            self.assertIn("target_adoption_state", packetization.render_report(payload))

    def test_packetization_gate_uses_meta_source_artifacts_not_target_carriers(self) -> None:
        changed_file = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/rollout_packets/planveyor_packet.md",
                _packet_text(
                    packet_id="260511_1001_consumer_packetization_wrong_carrier",
                    target_repo="consumer-fixture",
                    source_artifacts=[changed_file],
                    target_writable_carriers=["docs/unrelated.md"],
                    target_kind="consumer_only",
                    extra_body=(
                        f"\n## Source artifacts\n- `{changed_file}`\n\n"
                        "## Target writable carriers\n- `docs/unrelated.md`\n"
                    ),
                ),
            )

            payload = self._build_payload_with_explicit_consumer_mapping(
                root,
                changed_file=changed_file,
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            self.assertEqual(payload["blocking_count"], 1)
            row = payload["rows"][0]
            self.assertEqual(row["coverage"], "missing-packet")
            self.assertEqual(row["packet_path"], "N/A")

    def test_packetization_gate_rejects_same_repo_wrong_target_kind(self) -> None:
        changed_file = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/rollout_packets/planveyor_wrong_kind.md",
                _packet_text(
                    packet_id="260511_1002_consumer_packetization_wrong_kind",
                    target_repo="consumer-fixture",
                    source_artifacts=[changed_file],
                    target_writable_carriers=["docs/tools/prompts/manager_collab_merge_pipeline.md"],
                    target_kind="mirror_sync",
                    extra_body=_current_delivery_sections(
                        source_artifacts=[changed_file],
                        target_writable_carriers=["docs/tools/prompts/manager_collab_merge_pipeline.md"],
                    ),
                ),
            )

            payload = self._build_payload_with_explicit_consumer_mapping(
                root,
                changed_file=changed_file,
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            self.assertEqual(payload["blocking_count"], 1)
            self.assertEqual(payload["rows"][0]["target_repo"], "consumer-fixture")
            self.assertEqual(payload["rows"][0]["target_kind"], "consumer_only")
            self.assertEqual(payload["rows"][0]["coverage"], "missing-packet")

    def test_packetization_gate_rejects_nonliteral_partition_artifact_or_carrier_lists(self) -> None:
        changed_file = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        target_carrier = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        cases = (
            ("duplicate_artifact", [changed_file, changed_file], [target_carrier]),
            ("duplicate_carrier", [changed_file], [target_carrier, target_carrier]),
            ("whitespace_artifact", [f"{changed_file} "], [target_carrier]),
        )
        for name, source_artifacts, target_writable_carriers in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
                root = Path(tmpdir)
                self._write_file(
                    root,
                    "docs/rollout_packets/planveyor_nonliteral.md",
                    _packet_text(
                        packet_id=f"260511_1003_consumer_{name}",
                        target_repo="consumer-fixture",
                        source_artifacts=source_artifacts,
                        target_writable_carriers=target_writable_carriers,
                        target_kind="consumer_only",
                        extra_body=_current_delivery_sections(
                            source_artifacts=source_artifacts,
                            target_writable_carriers=target_writable_carriers,
                        ),
                    ),
                )

                payload = self._build_payload_with_explicit_consumer_mapping(
                    root,
                    changed_file=changed_file,
                    target_carrier=target_carrier,
                )
                self.assertEqual(payload["blocking_count"], 1)
                self.assertEqual(payload["rows"][0]["coverage"], "missing-packet")

    def test_packetization_gate_create_drafts_is_zero_write_legacy_recipe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/plans/_template.md",
                "--out",
                "docs/reviews/report.md",
                "--create-drafts",
                "--json",
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertGreater(payload["blocking_count"], 0)
            self.assertEqual(payload["created_packets"], [])
            self.assertEqual(payload["draft_packets_created_count"], 0)
            self.assertEqual(payload["draft_packets_created_paths"], [])
            self.assertFalse((root / "docs/rollout_packets").exists())
            self.assertIn("legacy-create-drafts-refused", {row["coverage"] for row in payload["rows"]})
            self.assertIn(
                "planveyor_rollout_packet_create <target_repo> <topic_slug> "
                "[--source-plan <provenance-plan>] --target-kind <target-kind>",
                payload["recovery_command"],
            )
            report_text = (root / "docs/reviews/report.md").read_text(encoding="utf-8")
            self.assertIn("planveyor_rollout_packet_create", report_text)
            self.assertIn("planveyor_post_merge_packetization_gate_recover", report_text)

    def test_packetization_gate_emits_actual_coverage_count_map(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            args = ["--create-drafts", "--out", "docs/reviews/report.md", "--json"]
            for index in range(154):
                args.extend(("--changed-file", f"docs/playbooks/matrix_{index:03d}.md"))
            args.extend(
                (
                    "--changed-file",
                    "docs/tools/owner_runbook_codex.md",
                    "--changed-file",
                    "docs/tools/prompts/profiles/retired/local.md",
                    "--changed-file",
                    "docs/plans/_template.md",
                )
            )

            result = self._run_gate(root, *args)

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(
                payload["blocking_coverage_counts"],
                {
                    "legacy-create-drafts-refused": 1,
                    "missing-packet": 0,
                    "source_only": 155,
                    "unknown_target_mapping": 1,
                },
            )
            self.assertEqual(
                payload["blocking_coverages"],
                ["legacy-create-drafts-refused", "unknown_target_mapping"],
            )
            self.assertIn("unknown_target_mapping", payload["blocking_coverages"])

    def test_create_serializes_literal_target_repo_and_current_delivery_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, source_plan, changed_file = self._init_recovery_repo(root)
            target_carrier = self._recovery_target_carriers["consumer-fixture"]
            template = (REPO_ROOT / "docs/rollout_packets/_template.md").read_text(encoding="utf-8")
            template = template.replace("<full-base-oid>..<full-head-oid>", f"{base}..{head}")
            template = template.replace("<full-head-oid>", head)
            template = template.replace("docs/<exact-source-artifact>.md", changed_file)
            template = template.replace("docs/<truthful-target-carrier>.md", target_carrier)
            self._write_file(root, "docs/rollout_packets/_template.md", template)
            create_command = [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(root),
                "--tooling-root",
                str(root),
                "create",
            ]
            create_args = [
                "literal_target_repo_identity",
                "--source-plan",
                source_plan,
                "--target-kind",
                "consumer_only",
            ]
            before_invalid_create = sorted(
                path.relative_to(root).as_posix() for path in (root / "docs/rollout_packets").glob("*.md")
            )
            for invalid_target_repo in ("consumer fixture", "consumer/fixture", 'consumer"fixture', "consumer\nfixture"):
                invalid_create_result = subprocess.run(
                    [*create_command, invalid_target_repo, *create_args],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(invalid_create_result.returncode, 1, invalid_create_result.stdout)
                self.assertIn(
                    "target repo must normalize to a lowercase hyphenated repo id",
                    invalid_create_result.stderr,
                )
                self.assertNotIn("Packet path:", invalid_create_result.stdout)
                self.assertEqual(
                    sorted(path.relative_to(root).as_posix() for path in (root / "docs/rollout_packets").glob("*.md")),
                    before_invalid_create,
                )

            shared_target_result = subprocess.run(
                [*create_command, "shared-consumer", "literal_shared_target", *create_args[1:]],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(shared_target_result.returncode, 0, shared_target_result.stderr)
            shared_packet_line = next(
                (line for line in shared_target_result.stdout.splitlines() if line.startswith("Packet path: ")),
                "",
            )
            self.assertTrue(shared_packet_line, shared_target_result.stdout)
            shared_packet = root / shared_packet_line.removeprefix("Packet path: ")
            shared_packet_text = shared_packet.read_text(encoding="utf-8")
            self.assertIn("**Target repo:** shared-consumer", shared_packet_text)
            self.assertIn('"target_repo": "shared-consumer"', shared_packet_text)

            create_result = subprocess.run(
                [*create_command, "consumer-fixture", *create_args],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(create_result.returncode, 0, create_result.stderr)
            packet_line = next(
                (line for line in create_result.stdout.splitlines() if line.startswith("Packet path: ")),
                "",
            )
            self.assertTrue(packet_line, create_result.stdout)
            packet_relative = packet_line.removeprefix("Packet path: ")
            self.assertIn("_consumer_fixture_", packet_relative)
            packet_path = root / packet_relative
            before = packet_path.read_text(encoding="utf-8")
            before_meta = self._packet_meta(packet_path)
            source_header = "**Source repo:** current-consumer"
            source_meta = '"source_repo": "current-consumer",'
            target_header = "**Target repo:** consumer-fixture"
            target_meta = '"target_repo": "consumer-fixture",'
            before_source_carrier_lines = [
                line
                for line in before.splitlines()
                if line.startswith("**Source repo:**") or '"source_repo":' in line
            ]
            before_target_carrier_lines = [
                line
                for line in before.splitlines()
                if line.startswith("**Target repo:**") or '"target_repo":' in line
            ]

            self.assertIn(source_header, before)
            self.assertIn(source_meta, before)
            self.assertEqual(before_source_carrier_lines, [source_header, f"    {source_meta}"])
            self.assertEqual(before_meta["source_repo"], "current-consumer")
            self.assertIn(target_header, before)
            self.assertIn(target_meta, before)
            self.assertEqual(before_target_carrier_lines, [target_header, f"    {target_meta}"])
            self.assertEqual(before_meta["target_repo"], "consumer-fixture")
            self.assertIn("_consumer_fixture_", str(before_meta["id"]))
            self.assertEqual(before_meta["source_range"], f"{base}..{head}")
            self.assertEqual(before_meta["source_revision"], head)
            self.assertEqual(before_meta["source_artifacts"], [changed_file])
            self.assertEqual(before_meta["target_writable_carriers"], [target_carrier])

            lint_result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(root),
                    "--tooling-root",
                    str(root),
                    "lint",
                    packet_relative,
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(lint_result.returncode, 0, lint_result.stderr)
            self.assertTrue(json.loads(lint_result.stdout)["ok"])

            planveyor_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="partner-fixture",
                source_plan=source_plan,
                target_carrier=self._recovery_target_carriers["partner-fixture"],
            )
            recovery_result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                source_plan=source_plan,
                args=[
                    "--packet",
                    planveyor_packet.relative_to(root).as_posix(),
                    "--packet",
                    packet_relative,
                    "--stage-packets",
                    "--json",
                ],
            )

            self.assertEqual(recovery_result.returncode, 0, recovery_result.stderr)
            payload = self._gate_payload(recovery_result.stdout)
            self.assertEqual(payload["delivery_mode"], "discovery-or-seed")
            self.assertEqual(payload["blocking_count"], 0)
            self.assertEqual(
                payload["report_accepted_packet_paths"],
                sorted([planveyor_packet.relative_to(root).as_posix(), packet_relative]),
            )
            after = packet_path.read_text(encoding="utf-8")
            after_meta = self._packet_meta(packet_path)
            after_source_carrier_lines = [
                line
                for line in after.splitlines()
                if line.startswith("**Source repo:**") or '"source_repo":' in line
            ]
            after_target_carrier_lines = [
                line
                for line in after.splitlines()
                if line.startswith("**Target repo:**") or '"target_repo":' in line
            ]

            self.assertIn(source_header, after)
            self.assertIn(source_meta, after)
            self.assertEqual(after_source_carrier_lines, before_source_carrier_lines)
            self.assertEqual(after_meta["source_repo"], before_meta["source_repo"])
            self.assertIn(target_header, after)
            self.assertIn(target_meta, after)
            self.assertEqual(after_target_carrier_lines, before_target_carrier_lines)
            self.assertEqual(after_meta["target_repo"], before_meta["target_repo"])
            self.assertEqual(after_meta["id"], before_meta["id"])
            self.assertEqual(after_meta["source_range"], f"{base}..{head}")
            self.assertEqual(after_meta["source_revision"], head)
            self.assertEqual(after_meta["source_artifacts"], [changed_file])
            self.assertEqual(after_meta["target_writable_carriers"], [target_carrier])
            tracked = self._git(root, "ls-files", "--error-unmatch", "--", packet_relative)
            self.assertEqual(tracked.returncode, 0, tracked.stderr)

    def test_current_recovery_restamps_explicit_open_packets_and_stages_exact_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, changed_file = self._init_recovery_repo(root)
            planveyor_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/planveyor_packet_provenance.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            consumer_packet = self._write_recovery_packet(
                root,
                name="consumer_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/consumer_packet_provenance.md",
                target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
            )
            self._write_file(root, "unrelated-sentinel.txt", "keep untracked\n")
            before_target_carriers = {
                planveyor_packet: self._packet_meta(planveyor_packet)["target_writable_carriers"],
                consumer_packet: self._packet_meta(consumer_packet)["target_writable_carriers"],
            }

            result = self._run_recovery(
                root,
                range_ref=f"{base[:7]}..{head[:7]}",
                args=[
                    "--packet",
                    "docs/rollout_packets/planveyor_packet.md",
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--stage-packets",
                    "--json",
                ],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self._gate_payload(result.stdout)
            expected_paths = sorted(
                [
                    "docs/rollout_packets/planveyor_packet.md",
                    "docs/rollout_packets/consumer_packet.md",
                ]
            )
            self.assertEqual(payload["delivery_mode"], "discovery-or-seed")
            self.assertEqual(payload["report_accepted_packet_paths"], expected_paths)
            self.assertEqual(payload["source_artifacts"], self._recovery_changed_files)
            self.assertEqual(payload["blocking_count"], 0)
            expected_packet_provenance = {
                planveyor_packet: "docs/plans/planveyor_packet_provenance.md",
                consumer_packet: "docs/plans/consumer_packet_provenance.md",
            }
            expected_packet_artifacts = {
                planveyor_packet: [changed_file],
                consumer_packet: [changed_file],
            }
            self.assertEqual(payload["range"], f"{base}..{head}")
            self.assertEqual(payload["source_plan"], "N/A (why=range identity has no single source plan)")
            for packet_path in (planveyor_packet, consumer_packet):
                meta = self._packet_meta(packet_path)
                self.assertEqual(meta["source_plan"], expected_packet_provenance[packet_path])
                self.assertEqual(meta["source_range"], f"{base}..{head}")
                self.assertEqual(meta["source_revision"], head)
                self.assertEqual(meta["source_artifacts"], expected_packet_artifacts[packet_path])
                self.assertEqual(meta["target_writable_carriers"], before_target_carriers[packet_path])
                tracked = self._git(root, "ls-files", "--error-unmatch", "--", packet_path.relative_to(root).as_posix())
                self.assertEqual(tracked.returncode, 0, tracked.stderr)
            status = self._git(root, "status", "--short", "--untracked-files=all")
            self.assertIn("?? unrelated-sentinel.txt", status.stdout)

    def test_current_recovery_wrapper_requires_only_range_and_documents_optional_provenance(self) -> None:
        result = subprocess.run(
            [
                "zsh",
                "-fc",
                f"source {shlex.quote(str(REPO_ROOT / 'scripts' / 'planveyor.zsh'))}; planveyor_help planveyor_post_merge_packetization_gate_recover; planveyor_post_merge_packetization_gate_recover",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("[--source-plan docs/plans/<provenance-plan>.md]", result.stdout)
        self.assertIn("usage: planveyor_post_merge_packetization_gate_recover", result.stderr)

    def test_current_recovery_receipt_reuse_preserves_packet_bytes_and_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)
            planveyor_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/stale.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            consumer_packet = self._write_recovery_packet(
                root,
                name="consumer_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/stale.md",
                target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
            )
            seeded = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=[
                    "--packet",
                    "docs/rollout_packets/planveyor_packet.md",
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--stage-packets",
                    "--json",
                ],
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            before_bytes = {path: path.read_bytes() for path in (planveyor_packet, consumer_packet)}
            before_index = self._git(root, "diff", "--cached", "--name-only").stdout

            result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=["--json"],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(payload["delivery_mode"], "receipt-reuse-only")
            self.assertEqual(payload["report_accepted_packet_paths"], sorted(path.relative_to(root).as_posix() for path in before_bytes))
            self.assertEqual({path: path.read_bytes() for path in before_bytes}, before_bytes)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, before_index)

    def test_current_recovery_rejects_immutable_or_invalid_input_before_packet_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)
            packet = self._write_recovery_packet(
                root,
                name="imported_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/stale.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
                status="imported",
            )
            before = packet.read_bytes()
            before_index = self._git(root, "diff", "--cached", "--name-only").stdout

            result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=["--packet", "docs/rollout_packets/imported_packet.md", "--stage-packets", "--json"],
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("only open packets", result.stderr)
            self.assertEqual(packet.read_bytes(), before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, before_index)

    def test_current_recovery_rejects_legacy_source_before_packet_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)
            packet = self._write_recovery_packet(
                root,
                name="legacy_source_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/stale.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            packet.write_text(
                packet.read_text(encoding="utf-8")
                .replace("**Source repo:** current-consumer", "**Source repo:** planveyor")
                .replace('"source_repo": "current-consumer"', '"source_repo": "planveyor"'),
                encoding="utf-8",
            )
            before = packet.read_bytes()
            before_index = self._git(root, "diff", "--cached", "--name-only").stdout

            result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=["--packet", "docs/rollout_packets/legacy_source_packet.md", "--stage-packets", "--json"],
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("not admissible for recovery", result.stderr)
            self.assertIn("current-consumer", result.stderr)
            self.assertEqual(packet.read_bytes(), before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, before_index)

    def test_current_recovery_source_plan_hint_is_provenance_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, changed_file = self._init_recovery_repo(root)
            planveyor_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/planveyor_packet_provenance.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            consumer_packet = self._write_recovery_packet(
                root,
                name="consumer_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/consumer_packet_provenance.md",
                target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
            )
            result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                source_plan="docs/plans/not_in_range.md",
                args=[
                    "--packet",
                    "docs/rollout_packets/planveyor_packet.md",
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--stage-packets",
                    "--json",
                ],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(payload["source_plan"], "docs/plans/not_in_range.md")
            self.assertEqual(payload["source_artifacts"], self._recovery_changed_files)
            self.assertEqual(
                self._packet_meta(planveyor_packet)["source_plan"],
                "docs/plans/planveyor_packet_provenance.md",
            )
            self.assertEqual(
                self._packet_meta(consumer_packet)["source_plan"],
                "docs/plans/consumer_packet_provenance.md",
            )

    def test_current_recovery_range_identity_is_invariant_across_optional_source_plan_hints(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)
            planveyor_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/planveyor_packet_provenance.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            consumer_packet = self._write_recovery_packet(
                root,
                name="consumer_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/consumer_packet_provenance.md",
                target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
            )
            seeded = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=[
                    "--packet",
                    "docs/rollout_packets/planveyor_packet.md",
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--stage-packets",
                    "--json",
                ],
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            no_hint = self._gate_payload(seeded.stdout)

            hinted = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                source_plan="docs/plans/260511_1001_process_unrelated.md",
                args=["--json"],
            )

            self.assertEqual(hinted.returncode, 0, hinted.stderr)
            with_hint = self._gate_payload(hinted.stdout)
            self.assertEqual(no_hint["source_plan"], "N/A (why=range identity has no single source plan)")
            self.assertEqual(with_hint["source_plan"], "docs/plans/260511_1001_process_unrelated.md")
            for key in (
                "range",
                "source_range",
                "source_revision",
                "source_artifacts",
                "rows",
                "blocking_count",
                "report_accepted_packet_paths",
            ):
                self.assertEqual(with_hint[key], no_hint[key], key)
            self.assertEqual(
                self._packet_meta(planveyor_packet)["source_plan"],
                "docs/plans/planveyor_packet_provenance.md",
            )
            self.assertEqual(
                self._packet_meta(consumer_packet)["source_plan"],
                "docs/plans/consumer_packet_provenance.md",
            )

    def test_report_only_uses_resolved_range_not_untracked_planpath(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_report_only_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, changed_file = self._init_recovery_repo(root)
            planpath = self._write_file(root, ".planveyor.planpath", "docs/plans/not_committed_or_done.md\n")
            before_planpath = planpath.read_bytes()

            result = self._run_gate(
                root,
                "--range",
                f"{base[:7]}..{head[:7]}",
                "--out",
                "docs/reviews/report.md",
                "--json",
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(payload["delivery_mode"], "report-only")
            self.assertEqual(payload["range"], f"{base}..{head}")
            self.assertEqual(payload["source_range"], f"{base}..{head}")
            self.assertEqual(payload["source_revision"], head)
            self.assertEqual(payload["source_artifacts"], self._recovery_changed_files)
            self.assertEqual(payload["source_plan"], "N/A (why=report-only range identity has no single source plan)")
            self.assertEqual(planpath.read_bytes(), before_planpath)

    def test_packetization_gate_rejects_envelope_only_and_noncovering_candidates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_candidates_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, changed_file = self._init_recovery_repo(root)
            self._write_file(
                root,
                "docs/rollout_packets/historical_envelope.md",
                _packet_text(
                    packet_id="260511_1000_historical",
                    target_repo="consumer-fixture",
                    source_range="c" * 40 + ".." + "d" * 40,
                    source_revision="d" * 40,
                    source_artifacts=[changed_file],
                    target_writable_carriers=["docs/plans/historical_target.md"],
                ),
            )
            self._write_file(
                root,
                "docs/rollout_packets/noncovering_current.md",
                _packet_text(
                    packet_id="260511_1001_noncovering",
                    target_repo="consumer-fixture",
                    source_range=f"{base}..{head}",
                    source_revision=head,
                    source_artifacts=["docs/playbooks/not_changed.md"],
                    target_writable_carriers=["docs/plans/current_target.md"],
                ),
            )

            result = self._run_gate(
                root,
                "--range",
                f"{base[:7]}..{head[:7]}",
                "--out",
                "docs/reviews/report.md",
                "--json",
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self._gate_payload(result.stdout)
            consumer_row = next(row for row in payload["rows"] if row["target_repo"] == "consumer-fixture")
            self.assertEqual(consumer_row["coverage"], "missing-packet")
            self.assertEqual(consumer_row["packet_path"], "N/A")
            self.assertEqual(consumer_row["packet_status"], "missing")

    def test_current_recovery_rejects_later_malformed_packet_before_packet_or_index_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)
            valid_packet = self._write_recovery_packet(
                root,
                name="planveyor_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/planveyor_packet_provenance.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            )
            malformed_packet = self._write_file(
                root,
                "docs/rollout_packets/consumer_packet.md",
                _packet_text(
                    packet_id="260511_1000_consumer_packet",
                    target_repo="partner-fixture",
                    source_plan="docs/plans/consumer_packet_provenance.md",
                    source_artifacts=["docs/stale.md"],
                    target_writable_carriers="docs/plans/not-a-list.md",  # type: ignore[arg-type]
                    target_kind="consumer_only",
                    extra_body=_current_delivery_sections(
                        source_artifacts=["docs/stale.md"],
                        target_writable_carriers=["docs/plans/target_consumer_packetization.md"],
                    ),
                ),
            )
            before_bytes = {
                valid_packet: valid_packet.read_bytes(),
                malformed_packet: malformed_packet.read_bytes(),
            }

            result = self._run_recovery(
                root,
                range_ref=f"{base}..{head}",
                args=[
                    "--packet",
                    "docs/rollout_packets/planveyor_packet.md",
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--stage-packets",
                    "--json",
                ],
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("target_writable_carriers", result.stderr)
            self.assertEqual({path: path.read_bytes() for path in before_bytes}, before_bytes)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, "")
            self.assertFalse((root / "docs/reviews").exists())

    def test_current_recovery_ignores_committed_plan_status_decoys(self) -> None:
        cases = {
            "missing_header": "# Packetization\n\n## Evidence\n- no lifecycle status\n",
            "body_decoy": "# Packetization\n\n**Status:** In progress\n\n## Evidence\n**Status:** Done\n",
            "fenced_decoy": (
                "# Packetization\n\n**Status:** In progress\n\n## Evidence\n```md\n**Status:** Done\n```\n"
            ),
            "list_nested_fence": (
                "# Packetization\n\n- ```md\n  **Status:** Done\n  ```\n\n## Evidence\n- nested example\n"
            ),
            "html_comment": "# Packetization\n\n<!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "inline_html_comment": "# Packetization\n\nnotes <!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "reopened_html_comment": "# Packetization\n\nnotes <!-- closed --> <!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "lazy_blockquote": "# Packetization\n\n> quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_blockquote_one": "# Packetization\n\n > quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_blockquote_three": "# Packetization\n\n   > quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_code": "# Packetization\n\n    **Status:** Done\n\n## Evidence\n- code example\n",
            "duplicate_header": "# Packetization\n\n**Status:** Done\n**Status:** Done\n\n## Evidence\n- duplicate\n",
        }
        for case, source_text in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="packetization_recovery_") as tmpdir:
                root = Path(tmpdir)
                base, _, source_plan, _ = self._init_recovery_repo(root)
                planveyor_packet = self._write_recovery_packet(
                    root,
                    name="planveyor_packet",
                    target_repo="consumer-fixture",
                    source_plan="docs/plans/planveyor_packet_provenance.md",
                    target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
                )
                consumer_packet = self._write_recovery_packet(
                    root,
                    name="consumer_packet",
                    target_repo="partner-fixture",
                    source_plan="docs/plans/consumer_packet_provenance.md",
                    target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
                )
                self._write_file(root, source_plan, source_text)
                added = self._git(root, "add", "--", source_plan)
                self.assertEqual(added.returncode, 0, added.stderr)
                committed = self._git(root, "commit", "-m", f"reject {case} source plan status")
                self.assertEqual(committed.returncode, 0, committed.stderr)
                head = self._git(root, "rev-parse", "HEAD")
                self.assertEqual(head.returncode, 0, head.stderr)
                result = self._run_recovery(
                    root,
                    range_ref=f"{base}..{head.stdout.strip()}",
                    args=[
                        "--packet",
                        "docs/rollout_packets/planveyor_packet.md",
                        "--packet",
                        "docs/rollout_packets/consumer_packet.md",
                        "--stage-packets",
                        "--json",
                    ],
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    self._packet_meta(planveyor_packet)["source_plan"],
                    "docs/plans/planveyor_packet_provenance.md",
                )
                self.assertEqual(
                    self._packet_meta(consumer_packet)["source_plan"],
                    "docs/plans/consumer_packet_provenance.md",
                )

    def test_packetization_gate_recovery_reuses_prior_same_range_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)

            blocking_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--json",
            )
            self.assertEqual(blocking_result.returncode, 2, blocking_result.stderr)
            blocking_payload = self._gate_payload(blocking_result.stdout)
            blocking_report = root / str(blocking_payload["report_path"])

            recovery_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--now",
                "2026-05-11T10:01:00",
                "--create-drafts",
                "--json",
            )

            self.assertEqual(recovery_result.returncode, 2, recovery_result.stderr)
            recovery_payload = self._gate_payload(recovery_result.stdout)
            self.assertEqual(recovery_payload["report_path"], blocking_payload["report_path"])
            self.assertEqual(recovery_payload["superseded_reports"], [])
            self.assertEqual(recovery_payload["created_packets"], [])
            self.assertIn("**Status:** Blocked", blocking_report.read_text(encoding="utf-8"))
            self.assertNotIn("## Supersession", blocking_report.read_text(encoding="utf-8"))

    def test_packetization_gate_same_minute_recovery_reuses_canonical_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)

            blocking_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--json",
            )
            self.assertEqual(blocking_result.returncode, 2, blocking_result.stderr)
            blocking_payload = self._gate_payload(blocking_result.stdout)
            blocking_report = root / str(blocking_payload["report_path"])

            recovery_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--create-drafts",
                "--json",
            )

            self.assertEqual(recovery_result.returncode, 2, recovery_result.stderr)
            recovery_payload = self._gate_payload(recovery_result.stdout)
            recovery_report = root / str(recovery_payload["report_path"])
            self.assertEqual(recovery_payload["report_path"], blocking_payload["report_path"])
            self.assertNotIn("_02_packetization_gate_range_", str(recovery_payload["report_path"]))
            self.assertEqual(recovery_payload["superseded_reports"], [])
            self.assertEqual(blocking_report, recovery_report)
            self.assertNotIn("**Status:** Superseded", recovery_report.read_text(encoding="utf-8"))
            self.assertNotIn("## Supersession", recovery_report.read_text(encoding="utf-8"))
            self.assertIn("Superseded previous reports: 0", recovery_report.read_text(encoding="utf-8"))
            same_range_reports = sorted(
                path.name
                for path in (root / "docs/reviews").glob("*_packetization_gate_range_*.md")
            )
            self.assertEqual(len(same_range_reports), 1)
            active_reports = [
                path.name
                for path in (root / "docs/reviews").glob("*_packetization_gate_range_*.md")
                if "**Status:** Superseded" not in path.read_text(encoding="utf-8")
            ]
            self.assertEqual(active_reports, [recovery_report.name])

    def test_packetization_gate_repeated_recovery_keeps_one_durable_report_and_no_new_packets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)

            first_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--create-drafts",
                "--json",
            )
            self.assertEqual(first_result.returncode, 2, first_result.stderr)
            first_payload = self._gate_payload(first_result.stdout)

            second_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--now",
                "2026-05-11T10:01:00",
                "--create-drafts",
                "--json",
            )

            self.assertEqual(second_result.returncode, 2, second_result.stderr)
            second_payload = self._gate_payload(second_result.stdout)
            self.assertEqual(second_payload["report_path"], first_payload["report_path"])
            self.assertEqual(second_payload["created_packets"], [])
            self.assertEqual(second_payload["superseded_reports"], [])
            same_range_reports = [
                path
                for path in (root / "docs/reviews").glob("*_packetization_gate_range_*.md")
            ]
            self.assertEqual([path.name for path in same_range_reports], [Path(str(second_payload["report_path"])).name])

    def test_packetization_gate_explicit_out_can_create_second_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            base, head, _, _ = self._init_recovery_repo(root)

            first_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--create-drafts",
                "--json",
            )
            self.assertEqual(first_result.returncode, 2, first_result.stderr)
            first_payload = self._gate_payload(first_result.stdout)
            first_report = root / str(first_payload["report_path"])
            before_bytes = first_report.read_bytes()
            before_digest = hashlib.sha256(before_bytes).hexdigest()
            before_sections = tuple(
                line for line in first_report.read_text(encoding="utf-8").splitlines() if line.startswith("## ")
            )
            self.assertIn(b"**Status:** Blocked", before_bytes)

            explicit_out = f"docs/reviews/260511_1001_packetization_gate_range_{base[:7]}_{head[:7]}.md"
            second_result = self._run_gate(
                root,
                "--range",
                f"{base}..{head}",
                "--out",
                explicit_out,
                "--json",
            )

            self.assertEqual(second_result.returncode, 2, second_result.stderr)
            second_payload = self._gate_payload(second_result.stdout)
            self.assertEqual(second_payload["report_path"], explicit_out)
            self.assertEqual(second_payload["superseded_packetization_reports"], second_payload["superseded_reports"])
            self.assertEqual(second_payload["superseded_reports"], [])
            self.assertEqual(first_report.read_bytes(), before_bytes)
            self.assertEqual(hashlib.sha256(first_report.read_bytes()).hexdigest(), before_digest)
            self.assertIn("**Status:** Blocked", first_report.read_text(encoding="utf-8"))
            self.assertEqual(
                tuple(line for line in first_report.read_text(encoding="utf-8").splitlines() if line.startswith("## ")),
                before_sections,
            )
            same_range_reports = sorted(
                path.name
                for path in (root / "docs/reviews").glob("*_packetization_gate_range_*.md")
            )
            self.assertEqual(
                same_range_reports,
                [
                    Path(str(first_payload["report_path"])).name,
                    Path(explicit_out).name,
                ],
            )

    def test_packetization_gate_default_fails_closed_on_duplicate_active_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/reviews/260511_1000_packetization_gate_range_aaaaaaa_bbbbbbb.md",
                "# Packetization\n\n**Status:** Done\n",
            )
            self._write_file(
                root,
                "docs/reviews/260511_1001_packetization_gate_range_aaaaaaa_bbbbbbb.md",
                "# Packetization\n\n**Status:** Done\n",
            )

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/playbooks/post_merge_plan_harvest.md",
                "--json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("ambiguous same-range packetization reports", result.stderr)

    def test_packetization_gate_default_fails_closed_before_draft_creation_on_duplicate_active_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/reviews/260511_1000_packetization_gate_range_aaaaaaa_bbbbbbb.md",
                "# Packetization\n\n**Status:** Done\n",
            )
            self._write_file(
                root,
                "docs/reviews/260511_1001_packetization_gate_range_aaaaaaa_bbbbbbb.md",
                "# Packetization\n\n**Status:** Done\n",
            )

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/playbooks/post_merge_plan_harvest.md",
                "--create-drafts",
                "--json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("ambiguous same-range packetization reports", result.stderr)
            packet_dir = root / "docs/rollout_packets"
            self.assertFalse(packet_dir.exists())

    def test_packetization_gate_default_fails_closed_on_only_superseded_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)
            self._write_file(
                root,
                "docs/reviews/260511_1000_packetization_gate_range_aaaaaaa_bbbbbbb.md",
                "# Packetization\n\n**Status:** Superseded\n",
            )

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/playbooks/post_merge_plan_harvest.md",
                "--json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("same-range packetization reports are all superseded", result.stderr)

    def test_packetization_gate_reports_unknown_target_mapping(self) -> None:
        with tempfile.TemporaryDirectory(prefix="packetization_gate_") as tmpdir:
            root = Path(tmpdir)

            result = self._run_gate(
                root,
                "--changed-file",
                "docs/tools/prompts/profiles/future_repo/manager_collab_merge_pipeline.md",
                "--out",
                "docs/reviews/report.md",
                "--json",
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = self._gate_payload(result.stdout)
            self.assertEqual(payload["rows"][0]["coverage"], "unknown_target_mapping")
            self.assertEqual(payload["blocking_coverage_counts"]["unknown_target_mapping"], 1)
            self.assertIn("unknown_target_mapping", (root / "docs/reviews/report.md").read_text(encoding="utf-8"))


class WriterCardinalityInvarianceTests(unittest.TestCase):
    """J1 writer-cardinality invariance for the rollout-packet Meta writer.

    ``_replace_meta_json`` must keep the strict single-carrier shape: exactly
    one ``## Meta`` heading, exactly one Meta JSON fence, and the strict routing
    reader (``plan_status_oracle.strict_plan_meta_json``) stays green across
    roundtrips.  The synthetic packet-shaped carrier carries both a
    ``packet_meta`` writer shape and a ``plan_meta`` routing anchor so the
    strict reader can judge the writer output; packet-only carriers stay out of
    routing scope by design.
    """

    def _load_modules(self) -> tuple[object, object]:
        if str(REPO_ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import plan_status_oracle

        spec = importlib.util.spec_from_file_location("rollout_packet_for_invariance_test", SCRIPT)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module, plan_status_oracle

    def _carrier_text(self, meta: dict[str, object]) -> str:
        return (
            "# Rollout packet: Invariance Fixture\n\n"
            "**Status:** open\n\n"
            "## Meta (machine-readable JSON)\n"
            "```json\n"
            + json.dumps(meta, indent=2, ensure_ascii=False)
            + "\n```\n"
        )

    def test_replace_meta_json_roundtrip_keeps_strict_single_carrier_shape(self) -> None:
        rollout_packet, plan_status_oracle = self._load_modules()
        plan_meta = {
            "cluster": "process",
            "tags": ["fixture"],
            "next_plans": [],
            "depends_on": [],
        }
        packet_meta = {
            "packet_meta": {
                "id": "260829_1710_invariance",
                "status": "open",
                "queue_after_import": True,
            }
        }
        first_meta = {"plan_meta": dict(plan_meta), **packet_meta}
        text = self._carrier_text(first_meta)

        updated_packet_meta = {
            "packet_meta": {
                "id": "260829_1710_invariance",
                "status": "acknowledged",
                "queue_after_import": False,
            }
        }
        second_meta = {"plan_meta": {**plan_meta, "tags": ["fixture", "ack"]}, **updated_packet_meta}
        first_roundtrip = rollout_packet._replace_meta_json(text, second_meta)

        self.assertEqual(len(rollout_packet.META_JSON_RE.findall(first_roundtrip)), 1)
        self.assertEqual(
            [line for line in first_roundtrip.splitlines() if line.startswith("## Meta ")],
            ["## Meta (machine-readable JSON)"],
        )
        result = plan_status_oracle.strict_plan_meta_json(first_roundtrip)
        self.assertEqual(result.state, "valid")
        self.assertEqual(result.plan_meta, second_meta["plan_meta"])

        third_meta = {"plan_meta": {**plan_meta, "tags": ["fixture", "ack", "again"]}, **updated_packet_meta}
        second_roundtrip = rollout_packet._replace_meta_json(first_roundtrip, third_meta)

        self.assertEqual(len(rollout_packet.META_JSON_RE.findall(second_roundtrip)), 1)
        self.assertEqual(
            [line for line in second_roundtrip.splitlines() if line.startswith("## Meta ")],
            ["## Meta (machine-readable JSON)"],
        )
        result = plan_status_oracle.strict_plan_meta_json(second_roundtrip)
        self.assertEqual(result.state, "valid")
        self.assertEqual(result.plan_meta, third_meta["plan_meta"])

    def test_replace_meta_json_requires_an_existing_single_meta_block(self) -> None:
        rollout_packet, _plan_status_oracle = self._load_modules()
        text_without_meta_block = (
            "# Rollout packet: No Meta Fixture\n\n"
            "**Status:** open\n"
        )

        with self.assertRaises(ValueError):
            rollout_packet._replace_meta_json(text_without_meta_block, {"plan_meta": {"cluster": "process"}})


if __name__ == "__main__":
    unittest.main()

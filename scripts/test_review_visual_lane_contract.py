from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import review_visual_lane_contract as contract
from scripts.test_support.process_contract_fixtures import standalone_git_root


MARKER = "<!-- verification-receipt lane=visual.check_1 lane=visual.check_2 lane=vis.human_visual_review_local -->"
COMPARATOR = "./scripts/run_visual_check.sh --run-id review --repeat 2 --logs-dir .tmp/visual-regression/logs"
PLAN_REF = "docs/plans/260722_2206_reviewer_range_aaaaaaa_bbbbbbb.md"
HUMAN = {
    "primary": "./scripts/review_visual_design_audit.sh --mode primary --plan docs/plans/<plan>.md --port 8073 --assets-dir .tmp/human-visual-review/primary",
    "secondary": "./scripts/review_visual_design_audit.sh --mode secondary --plan docs/plans/<plan>.md --port 8074 --assets-dir .tmp/human-visual-review/secondary",
}
MATERIALIZED_HUMAN = {
    mode: command.replace("docs/plans/<plan>.md", PLAN_REF)
    for mode, command in HUMAN.items()
}


class ReviewVisualLaneContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = standalone_git_root(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "scripts").mkdir()
        for name in ("run_visual_check.sh", "review_visual_design_audit.sh"):
            path = self.root / "scripts" / name
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(0o755)
        payload = self.root / "scripts" / "payload.sh"
        payload.write_text("#!/bin/sh\n", encoding="utf-8")
        payload.chmod(0o755)
        self.write_sources()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_sources(
        self,
        *,
        smoke_marker: str = MARKER,
        smoke_commands: list[str] | None = None,
        runbook_commands: list[str] | None = None,
    ) -> None:
        commands = [COMPARATOR, HUMAN["primary"], HUMAN["secondary"]]
        effective_smoke_commands = commands if smoke_commands is None else smoke_commands
        effective_runbook_commands = commands if runbook_commands is None else runbook_commands
        smoke = "\n".join([smoke_marker, "```bash", *effective_smoke_commands, "```", ""])
        runbook = "\n".join(["```bash", *effective_runbook_commands, "```", ""])
        (self.root / "docs" / "smoke_visual.md").write_text(smoke, encoding="utf-8")
        (self.root / "docs" / "testing_runbook.md").write_text(runbook, encoding="utf-8")

    def discover(self, entries: list[dict[str, str]] | None = None, **kwargs: object) -> dict[str, object]:
        profile_id = str(kwargs.get("profile_id", "default"))
        content_profile_id = kwargs.get(
            "content_profile_id",
            profile_id,
        )
        declared = bool(kwargs.get("declared", True))
        call_kwargs = {
            "project_root": self.root,
            "profile_id": profile_id,
            "content_profile_id": content_profile_id,
            "changed_entries": entries or [{"status": "M", "path": "templates/dashboard.html"}],
            "exclude_docs": bool(kwargs.get("exclude_docs", False)),
            "review_basename": "260722_2206_reviewer_range_aaaaaaa_bbbbbbb",
            "plan_ref": str(kwargs.get("plan_ref", PLAN_REF)),
        }
        if not declared:
            return contract.discover_review_visual_lane(**call_kwargs)

        def read_fixture_source(_context: object, source_ref: str, *, purpose: str) -> str:
            del purpose
            return (self.root / source_ref).read_text(encoding="utf-8")

        context = SimpleNamespace(state="engaged", behavior_identity=profile_id)
        with (
            mock.patch.object(contract, "context_for_reader", return_value=context),
            mock.patch.object(contract, "read_declared_text", side_effect=read_fixture_source),
        ):
            return contract.discover_review_visual_lane(**call_kwargs)

    def test_available_exact_v1_field_set_and_commands(self) -> None:
        payload = self.discover()
        self.assertEqual(set(payload), set(contract.CONTRACT_FIELDS))
        self.assertEqual(payload["schema_version"], contract.SCHEMA_VERSION)
        self.assertEqual(payload["availability_state"], "available")
        self.assertEqual(payload["mandatory_modes"], ["primary", "secondary"])
        self.assertEqual(payload["comparator_command"], COMPARATOR)
        self.assertEqual(payload["comparator_claim"], "mechanical")
        self.assertFalse(payload["baseline_update_allowed"])
        self.assertTrue(payload["complete_index_required"])
        self.assertEqual(payload["human_commands_by_mode"], MATERIALIZED_HUMAN)
        self.assertTrue(
            all(
                contract._shell_safety_error(command) is None
                for command in payload["human_commands_by_mode"].values()
            )
        )
        self.assertEqual(
            payload["human_index_paths_by_mode"],
            {
                "primary": ".tmp/human-visual-review/primary/human_visual_review_primary.md",
                "secondary": ".tmp/human-visual-review/secondary/human_visual_review_secondary.md",
            },
        )
        self.assertFalse(contract.validate_contract(payload))

    def test_raw_default_profile_has_no_implicit_planveyor_lane(self) -> None:
        payload = self.discover(content_profile_id=None, declared=False)
        self.assertEqual(payload["availability_state"], "not_applicable")
        self.assertEqual(payload["reason"], "no_declared_runtime_visual_lane:default")
        self.assertEqual(payload["profile_id"], "default")
        rendered = contract.render_materialized_contract(payload)
        parsed, errors = contract.parse_materialized_contract(rendered)
        self.assertFalse(errors)
        self.assertEqual(parsed, payload)

    def test_missing_marker_or_command_is_missing(self) -> None:
        self.write_sources(runbook_commands=[])
        self.assertEqual(self.discover()["availability_state"], "missing")
        self.write_sources(smoke_marker="<!-- verification-receipt lane=visual.check_1 -->")
        self.assertEqual(self.discover()["availability_state"], "missing")

    def test_malformed_missing_executable_and_unsafe_output(self) -> None:
        (self.root / "scripts" / "run_visual_check.sh").unlink()
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("does not exist", str(payload["reason"]))
        comparator = self.root / "scripts" / "run_visual_check.sh"
        comparator.write_text("#!/bin/sh\n", encoding="utf-8")
        comparator.chmod(0o755)
        unsafe = HUMAN["primary"].replace(".tmp/human-visual-review/primary", "../escape")
        self.write_sources(smoke_commands=[COMPARATOR, unsafe, HUMAN["secondary"]], runbook_commands=[COMPARATOR, unsafe, HUMAN["secondary"]])
        self.assertEqual(self.discover()["availability_state"], "malformed")

    def test_malformed_duplicate_path_option_and_executable_mode(self) -> None:
        duplicate = COMPARATOR + " --logs-dir /tmp/escape"
        self.write_sources(
            smoke_commands=[duplicate, *HUMAN.values()],
            runbook_commands=[duplicate, *HUMAN.values()],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("duplicate path-bearing option", str(payload["reason"]))

        unsafe_plan = HUMAN["primary"].replace("docs/plans/<plan>.md", "docs/plans/../escape.md")
        self.write_sources(
            smoke_commands=[COMPARATOR, unsafe_plan, HUMAN["secondary"]],
            runbook_commands=[COMPARATOR, unsafe_plan, HUMAN["secondary"]],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("unsafe path-bearing option --plan", str(payload["reason"]))

        unsafe_placeholder = HUMAN["primary"].replace("<plan>", "<arbitrary>")
        self.write_sources(
            smoke_commands=[COMPARATOR, unsafe_placeholder, HUMAN["secondary"]],
            runbook_commands=[COMPARATOR, unsafe_placeholder, HUMAN["secondary"]],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("shell control syntax", str(payload["reason"]))

        self.write_sources()
        (self.root / "scripts" / "run_visual_check.sh").chmod(0o644)
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("is not executable", str(payload["reason"]))

        payload = self.discover(plan_ref="docs/plans/../escape.md")
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("generated plan path is unsafe", str(payload["reason"]))

    def test_ambiguous_duplicate_or_source_disagreement(self) -> None:
        alternate = COMPARATOR.replace("--repeat 2", "--repeat 3")
        self.write_sources(smoke_commands=[COMPARATOR, alternate, *HUMAN.values()])
        self.assertEqual(self.discover()["availability_state"], "ambiguous")
        self.write_sources(runbook_commands=[alternate, *HUMAN.values()])
        self.assertEqual(self.discover()["availability_state"], "ambiguous")

    def test_baseline_update_is_rejected(self) -> None:
        update = (
            "./scripts/run_visual_check.sh --run-id review --repeat 2 "
            "--logs-dir .tmp/visual-regression/logs --visual-baseline-update"
        )
        self.write_sources(smoke_commands=[update, *HUMAN.values()], runbook_commands=[update, *HUMAN.values()])
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("baseline_update", str(payload["reason"]))

    def test_placeholder_comparator_example_is_not_a_runnable_candidate(self) -> None:
        placeholder = (
            "./scripts/run_visual_check.sh --run-id <id> --repeat 2 "
            "--logs-dir <dir>"
        )
        self.write_sources(
            smoke_commands=[COMPARATOR, *HUMAN.values()],
            runbook_commands=[placeholder, COMPARATOR, *HUMAN.values()],
        )

        payload = self.discover()

        self.assertEqual(payload["availability_state"], "available")
        self.assertEqual(payload["comparator_command"], COMPARATOR)

    def test_command_shape_discovers_renamed_repo_helpers_without_basename_hardcode(self) -> None:
        comparator = "./scripts/compare_ui.sh --run-id review --repeat 2 --logs-dir .tmp/visual/logs"
        humans = {
            "primary": "./scripts/inspect_ui.sh --mode primary --plan docs/plans/<plan>.md --port 8073 --assets-dir .tmp/human/primary",
            "secondary": "./scripts/inspect_ui.sh --mode secondary --plan docs/plans/<plan>.md --port 8074 --assets-dir .tmp/human/secondary",
        }
        for name in ("compare_ui.sh", "inspect_ui.sh"):
            path = self.root / "scripts" / name
            path.write_text("#!/bin/sh\n", encoding="utf-8")
            path.chmod(0o755)
        self.write_sources(
            smoke_commands=[comparator, *humans.values()],
            runbook_commands=[comparator, *humans.values()],
        )

        payload = self.discover()

        self.assertEqual(payload["availability_state"], "available")
        self.assertEqual(payload["comparator_command"], comparator)
        self.assertEqual(
            payload["human_commands_by_mode"],
            {
                mode: command.replace("docs/plans/<plan>.md", PLAN_REF)
                for mode, command in humans.items()
            },
        )

    def test_shell_control_matrix_rejected_for_comparator_and_human_commands(self) -> None:
        command_variants = (
            lambda command: command + " ; ./scripts/payload.sh",
            lambda command: command + " && ./scripts/payload.sh",
            lambda command: command + " || ./scripts/payload.sh",
            lambda command: command + " | ./scripts/payload.sh",
            lambda command: command + " > .tmp/injected-output",
            lambda command: command + " <(./scripts/payload.sh)",
            lambda command: command + " >(./scripts/payload.sh)",
            lambda command: command.replace("--port 8073", "--port $(./scripts/payload.sh)")
            if "--port 8073" in command
            else command.replace("--run-id review", "--run-id $(./scripts/payload.sh)"),
            lambda command: command.replace("--port 8073", "--port `./scripts/payload.sh`")
            if "--port 8073" in command
            else command.replace("--run-id review", "--run-id `./scripts/payload.sh`"),
            lambda command: "UNSAFE_ENV=1 " + command,
        )
        for mutate in command_variants:
            with self.subTest(lane="comparator", mutation=mutate(COMPARATOR)):
                injected = mutate(COMPARATOR)
                commands = [injected, *HUMAN.values()]
                self.write_sources(smoke_commands=commands, runbook_commands=commands)
                self.assertEqual(self.discover()["availability_state"], "malformed")
            with self.subTest(lane="human", mutation=mutate(HUMAN["primary"])):
                injected = mutate(HUMAN["primary"])
                commands = [COMPARATOR, injected, HUMAN["secondary"]]
                self.write_sources(smoke_commands=commands, runbook_commands=commands)
                self.assertEqual(self.discover()["availability_state"], "malformed")

        for command in (COMPARATOR, HUMAN["primary"]):
            with self.subTest(lane="direct-newline", command=command):
                error = contract._validate_command(
                    self.root,
                    command + "\n./scripts/payload.sh",
                )
                self.assertIn("single line", str(error))

    def test_unquoted_shell_comments_are_rejected_but_quoted_hash_is_allowed(self) -> None:
        commented_comparator = COMPARATOR.replace(
            "--run-id review",
            "# required options are now ignored --run-id review",
        )
        self.write_sources(
            smoke_commands=[commented_comparator, *HUMAN.values()],
            runbook_commands=[commented_comparator, *HUMAN.values()],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("unquoted shell comments", str(payload["reason"]))

        commented_human = HUMAN["primary"].replace(
            "--mode primary",
            "# required options are now ignored --mode primary",
        )
        self.write_sources(
            smoke_commands=[COMPARATOR, commented_human, HUMAN["secondary"]],
            runbook_commands=[COMPARATOR, commented_human, HUMAN["secondary"]],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "malformed")
        self.assertIn("unquoted shell comments", str(payload["reason"]))

        quoted_hash = COMPARATOR + " --label '#visual-review'"
        self.write_sources(
            smoke_commands=[quoted_hash, *HUMAN.values()],
            runbook_commands=[quoted_hash, *HUMAN.values()],
        )
        payload = self.discover()
        self.assertEqual(payload["availability_state"], "available")
        self.assertEqual(payload["comparator_command"], quoted_hash)

    def test_not_applicable_for_docs_non_ui_and_undeclared_profile(self) -> None:
        docs = self.discover([{"status": "M", "path": "docs/guide.md"}])
        self.assertEqual(docs["availability_state"], "not_applicable")
        non_ui = self.discover([{"status": "M", "path": "scripts/tool.py"}])
        self.assertEqual(non_ui["availability_state"], "not_applicable")
        target_local = self.discover(profile_id="target-local", declared=False)
        self.assertEqual(target_local["availability_state"], "not_applicable")
        self.assertEqual(target_local["reason"], "no_declared_runtime_visual_lane:target-local")

    def test_declared_default_planveyor_and_target_local_use_explicit_reader(self) -> None:
        default = self.discover(profile_id="default")
        planveyor = self.discover(profile_id="planveyor")
        target_local = self.discover(profile_id="target-local")
        for payload in (default, planveyor, target_local):
            self.assertEqual(payload["availability_state"], "available")
        self.assertEqual(planveyor["comparator_command"], default["comparator_command"])
        self.assertEqual(target_local["human_commands_by_mode"], default["human_commands_by_mode"])

    def test_exclude_docs_does_not_hide_repo_backed_sources(self) -> None:
        payload = self.discover(
            [
                {"status": "M", "path": "templates/dashboard.html"},
                {"status": "M", "path": "docs/smoke_visual.md"},
            ],
            exclude_docs=True,
        )
        self.assertEqual(payload["availability_state"], "available")
        self.assertTrue(all(not item["path"].startswith("docs/") for item in payload["changed_path_evidence"]))

    def test_module_names_are_not_ui_and_deleted_or_renamed_ui_paths_count(self) -> None:
        # The engine knows no product layout: a Python module is not a UI
        # path because of its package or module name.
        backend_entries = [
            {"status": "M", "path": "apps/catalog/views/dashboard.py"},
            {"status": "D", "path": "apps/catalog/admin/forms.py"},
            {
                "status": "R100",
                "old_path": "apps/catalog/services/report.py",
                "path": "apps/catalog/domain/report.py",
            },
            {"status": "M", "path": "apps/catalog/selectors/dashboard.py"},
        ]
        backend = self.discover(backend_entries)
        self.assertEqual(backend["availability_state"], "not_applicable")
        self.assertEqual(backend["reason"], "no_runtime_ui_paths")
        self.assertEqual(
            [item["runtime_ui_paths"] for item in backend["changed_path_evidence"]],
            [[], [], [], []],
        )
        deleted = self.discover([{"status": "D", "path": "templates/legacy.html"}])
        self.assertEqual(deleted["availability_state"], "available")
        renamed = self.discover(
            [{"status": "R100", "old_path": "templates/old.html", "path": "backend/renamed.txt"}]
        )
        self.assertEqual(renamed["availability_state"], "available")
        self.assertEqual(
            renamed["changed_path_evidence"][0]["runtime_ui_paths"],
            ["templates/old.html"],
        )

    def test_parser_rejects_duplicate_or_wrong_fields(self) -> None:
        payload = self.discover()
        rendered = contract.render_materialized_contract(payload)
        parsed, errors = contract.parse_materialized_contract(rendered + "\n" + rendered)
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["multiple_materialized_visual_lane_contracts"])
        bad = dict(payload)
        bad["extra"] = True
        self.assertIn("field_set_mismatch", contract.validate_contract(bad)[0])

    def _large_payload(self, *, count: int = 940) -> dict[str, object]:
        payload = self.discover()
        payload["changed_path_evidence"] = [
            {
                "status": "R100" if index == 0 else "M",
                "path": f"apps/generated/path_{index:04d}_with_a_long_name.py",
                "old_path": "templates/legacy_dashboard.html" if index == 0 else "",
                "runtime_ui": index == 0,
                "runtime_ui_paths": ["templates/legacy_dashboard.html"] if index == 0 else [],
            }
            for index in range(count)
        ]
        return payload

    def _render_markdown_args(self) -> list[str]:
        return [
            "--project-root",
            str(self.root),
            "--profile-id",
            "default",
            "--base",
            "a" * 40,
            "--head",
            "b" * 40,
            "--exclude-docs",
            "0",
            "--review-artifact",
            "docs/code_reviews/260830_0241_cli_fixture.md",
            "--plan-artifact",
            "docs/plans/260830_0241_cli_fixture.md",
            "--render-markdown",
        ]

    def test_public_render_markdown_preserves_small_inline_v1(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        entries = [{"status": "M", "path": "templates/dashboard.html"}]

        with (
            mock.patch.object(contract, "git_changed_entries", return_value=entries),
            mock.patch.object(contract, "prepare_materialized_contract", wraps=contract.prepare_materialized_contract) as prepare,
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = contract.main(self._render_markdown_args())

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(prepare.call_count, 1)
        rendered = stdout.getvalue()
        payload, errors = contract.parse_materialized_contract(rendered)
        self.assertEqual(errors, [])
        self.assertIsNotNone(payload)
        self.assertIn(contract.SCHEMA_VERSION, rendered)
        self.assertNotIn(contract.REF_SCHEMA_VERSION, rendered)

    def test_public_render_markdown_large_payload_fails_closed_before_stdout(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        entries = [
            {"status": "M", "path": f"templates/generated_{index:04d}.html"}
            for index in range(940)
        ]

        with (
            mock.patch.object(contract, "git_changed_entries", return_value=entries),
            mock.patch.object(contract, "prepare_materialized_contract", wraps=contract.prepare_materialized_contract) as prepare,
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = contract.main(self._render_markdown_args())

        self.assertEqual(exit_code, 2)
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn('"changed_path_evidence":', stdout.getvalue())
        self.assertNotIn(contract.REF_SCHEMA_VERSION, stdout.getvalue())
        self.assertIn("external materialization requires canonical scaffold publication", stderr.getvalue())

    def test_external_v2_ref_round_trip_preserves_full_evidence(self) -> None:
        payload = self._large_payload()
        plan_ref = "docs/plans/260830_0241_fixture.md"
        review_ref = "docs/code_reviews/260830_0241_fixture.md"
        materialization = contract.prepare_materialized_contract(
            payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )

        self.assertEqual(materialization["mode"], "external")
        self.assertIn(contract.REF_SCHEMA_VERSION, str(materialization["markdown"]))
        self.assertNotIn('"changed_path_evidence":', str(materialization["markdown"]))
        self.assertEqual(
            materialization["support_ref"],
            "docs/code_reviews/assets/260830_0241_fixture/review_visual_lane_contract.v2.json",
        )

        plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=plan,
            draft_ref="docs/code_drafts/260830_0241_fixture__code_draft.md",
            draft_text=draft,
            materialization=materialization,
        )
        parsed, errors = contract.parse_materialized_contract(
            plan,
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertEqual(errors, [])
        self.assertEqual(parsed, payload)
        full_path = self.root / str(materialization["support_ref"])
        self.assertTrue(full_path.is_file())
        self.assertEqual(
            full_path.read_bytes(),
            contract.canonical_json_bytes(json.loads(full_path.read_text(encoding="utf-8"))),
        )

    def test_external_ref_rejects_coherent_wrong_scaffold_range_identity(self) -> None:
        payload = self._large_payload()
        expected_identity = ("a" * 40, "b" * 40, 0)
        cases = (
            ("base", "c" * 40, "b" * 40, 0),
            ("head", "a" * 40, "d" * 40, 0),
            ("exclude_docs", "a" * 40, "b" * 40, 1),
        )
        for field, base, head, exclude_docs in cases:
            with self.subTest(field=field):
                plan_ref = f"docs/plans/260830_0241_{field}_fixture.md"
                review_ref = f"docs/code_reviews/260830_0241_{field}_fixture.md"
                materialization = contract.prepare_materialized_contract(
                    payload,
                    base=base,
                    head=head,
                    exclude_docs=exclude_docs,
                    plan_ref=plan_ref,
                    review_artifact_ref=review_ref,
                )
                plan = (
                    "# Plan\n\n"
                    f"- Review target: `RANGE={expected_identity[0]}..{expected_identity[1]} "
                    f"(EXCLUDE_DOCS={expected_identity[2]})`\n\n"
                    "## Review visual lane contract\n\n"
                    + str(materialization["markdown"])
                    + "\n"
                )
                draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
                contract.publish_generated_scaffold(
                    project_root=self.root,
                    plan_ref=plan_ref,
                    plan_text=plan,
                    draft_ref=f"docs/code_drafts/260830_0241_{field}_fixture__code_draft.md",
                    draft_text=draft,
                    materialization=materialization,
                )

                parsed, errors = contract.parse_materialized_contract(
                    plan,
                    project_root=self.root,
                    expected_plan_ref=plan_ref,
                    expected_range_identity=expected_identity,
                )

                self.assertIsNone(parsed)
                self.assertEqual(errors, ["identity_mismatch"])

    def test_external_ref_requires_one_canonical_full_review_target(self) -> None:
        payload = self._large_payload()
        canonical_base = "a" * 40
        canonical_head = "b" * 40
        cases = {
            "missing": "",
            "short": f"- Review target: `RANGE={canonical_base[:7]}..{canonical_head[:7]} (EXCLUDE_DOCS=0)`\n\n",
            "uppercase": f"- Review target: `RANGE={canonical_base.upper()}..{canonical_head.upper()} (EXCLUDE_DOCS=0)`\n\n",
            "symbolic": "- Review target: `RANGE=HEAD~1..HEAD (EXCLUDE_DOCS=0)`\n\n",
            "duplicate": (
                f"- Review target: `RANGE={canonical_base}..{canonical_head} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={canonical_base}..{canonical_head} (EXCLUDE_DOCS=0)`\n\n"
            ),
            "mixed": (
                f"- Review target: `RANGE={canonical_base}..{canonical_head} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={canonical_base[:7]}..{canonical_head[:7]} (EXCLUDE_DOCS=0)`\n\n"
            ),
        }
        for name, target_lines in cases.items():
            with self.subTest(target=name):
                plan_ref = f"docs/plans/260830_0241_{name}_target_fixture.md"
                materialization = contract.prepare_materialized_contract(
                    payload,
                    base=canonical_base,
                    head=canonical_head,
                    exclude_docs=0,
                    plan_ref=plan_ref,
                    review_artifact_ref=f"docs/code_reviews/260830_0241_{name}_target_fixture.md",
                )
                plan = (
                    "# Plan\n\n"
                    + target_lines
                    + "## Review visual lane contract\n\n"
                    + str(materialization["markdown"])
                    + "\n"
                )
                draft_ref = f"docs/code_drafts/260830_0241_{name}_target_fixture__code_draft.md"
                draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
                contract.publish_generated_scaffold(
                    project_root=self.root,
                    plan_ref=plan_ref,
                    plan_text=plan,
                    draft_ref=draft_ref,
                    draft_text=draft,
                    materialization=materialization,
                )

                parsed, errors = contract.parse_materialized_contract(
                    plan,
                    project_root=self.root,
                    expected_plan_ref=plan_ref,
                    require_review_target_identity=True,
                )

                self.assertIsNone(parsed)
                self.assertEqual(errors, ["review_target_identity_invalid"])

    def test_malformed_changed_path_evidence_fails_closed_before_digest(self) -> None:
        malformed_values = {
            "scalar": "not-a-list",
            "list": ["not-an-entry"],
            "null": None,
            "nested": [
                {
                    "status": "M",
                    "path": "templates/page.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": ["templates/page.html", None],
                }
            ],
        }
        for name, evidence in malformed_values.items():
            with self.subTest(carrier="inline", evidence=name):
                payload = self.discover()
                payload["changed_path_evidence"] = evidence
                parsed, errors = contract.parse_materialized_contract(
                    contract.render_materialized_contract(payload)
                )
                self.assertIsNotNone(parsed)
                self.assertEqual(errors, ["changed_path_evidence_malformed"])

        payload = self._large_payload()
        plan_ref = "docs/plans/260830_0241_malformed_evidence_fixture.md"
        materialization = contract.prepare_materialized_contract(
            payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref="docs/code_reviews/260830_0241_malformed_evidence_fixture.md",
        )
        plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=plan,
            draft_ref="docs/code_drafts/260830_0241_malformed_evidence_fixture__code_draft.md",
            draft_text=draft,
            materialization=materialization,
        )
        support = self.root / str(materialization["support_ref"])
        original_full = json.loads(support.read_text(encoding="utf-8"))
        wrapper = json.loads(str(materialization["markdown"]).split("\n", 1)[1].rsplit("\n```", 1)[0])
        reference = wrapper["review_visual_lane_contract_ref"]
        for name, evidence in malformed_values.items():
            with self.subTest(carrier="external", evidence=name):
                full = dict(original_full)
                full["changed_path_evidence"] = evidence
                full["changed_path_count"] = 0
                full["changed_path_evidence_sha256"] = "0" * 64
                altered = contract.canonical_json_bytes(full)
                support.write_bytes(altered)
                altered_reference = dict(reference)
                altered_reference["full_payload_sha256"] = hashlib.sha256(altered).hexdigest()
                parsed, errors = contract.parse_materialized_contract(
                    contract.render_materialized_contract(altered_reference),
                    project_root=self.root,
                    expected_plan_ref=plan_ref,
                )
                self.assertIsNone(parsed)
                self.assertEqual(errors, ["changed_path_evidence_malformed"])

    def test_one_line_large_inline_payload_is_rejected_by_byte_limit(self) -> None:
        payload = self._large_payload()
        compact = json.dumps(
            {"review_visual_lane_contract": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(len(compact.splitlines()), 1)
        self.assertGreater(len(compact.encode("utf-8")), contract.MAX_INLINE_UTF8_BYTES)

        parsed, errors = contract.parse_materialized_contract(f"```json\n{compact}\n```")

        self.assertIsNone(parsed)
        self.assertEqual(errors, ["inline_content_byte_limit_exceeded"])

    def test_inline_line_and_utf8_byte_boundaries_are_exact(self) -> None:
        line_payload = self.discover()
        line_payload["source_refs"] = []
        while True:
            markdown = contract.render_materialized_contract(line_payload)
            body = contract.JSON_BLOCK_RE.fullmatch(markdown.strip()).group("body")  # type: ignore[union-attr]
            if len(body.splitlines()) == contract.MAX_INLINE_CONTENT_LINES:
                break
            self.assertLess(len(body.splitlines()), contract.MAX_INLINE_CONTENT_LINES)
            line_payload["source_refs"].append(f"docs/source_{len(line_payload['source_refs']):03d}.md")  # type: ignore[index]
        parsed, errors = contract.parse_materialized_contract(markdown)
        self.assertEqual(errors, [])
        self.assertEqual(parsed, line_payload)
        line_payload["source_refs"].append("docs/over_limit.md")  # type: ignore[index]
        parsed, errors = contract.parse_materialized_contract(
            contract.render_materialized_contract(line_payload)
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["inline_content_line_limit_exceeded"])

        byte_payload = self.discover()
        byte_payload["reason"] = ""
        base_markdown = contract.render_materialized_contract(byte_payload)
        base_body = contract.JSON_BLOCK_RE.fullmatch(base_markdown.strip()).group("body")  # type: ignore[union-attr]
        byte_payload["reason"] = "x" * (contract.MAX_INLINE_UTF8_BYTES - len(base_body.encode("utf-8")))
        bounded = contract.render_materialized_contract(byte_payload)
        bounded_body = contract.JSON_BLOCK_RE.fullmatch(bounded.strip()).group("body")  # type: ignore[union-attr]
        self.assertEqual(len(bounded_body.encode("utf-8")), contract.MAX_INLINE_UTF8_BYTES)
        bounded_materialization = contract.prepare_materialized_contract(
            byte_payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref="docs/plans/260830_0241_byte_boundary_fixture.md",
            review_artifact_ref="docs/code_reviews/260830_0241_byte_boundary_fixture.md",
        )
        self.assertEqual(bounded_materialization["mode"], "inline")
        parsed, errors = contract.parse_materialized_contract(bounded)
        self.assertEqual(errors, [])
        self.assertEqual(parsed, byte_payload)
        byte_payload["reason"] += "x"
        over_limit = contract.render_materialized_contract(byte_payload)
        over_limit_materialization = contract.prepare_materialized_contract(
            byte_payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref="docs/plans/260830_0241_byte_boundary_fixture.md",
            review_artifact_ref="docs/code_reviews/260830_0241_byte_boundary_fixture.md",
        )
        self.assertEqual(over_limit_materialization["mode"], "external")
        parsed, errors = contract.parse_materialized_contract(over_limit)
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["inline_content_byte_limit_exceeded"])

    def test_changed_path_digest_binds_only_documented_path_tuples(self) -> None:
        entries = [
            {
                "status": "R100",
                "path": "templates/new.html",
                "old_path": "templates/old.html",
                "runtime_ui": True,
                "runtime_ui_paths": ["templates/new.html", "templates/old.html"],
            },
            {
                "status": "M",
                "path": "apps/example.py",
                "old_path": "",
                "runtime_ui": False,
                "runtime_ui_paths": [],
            },
        ]
        expected_tuples = [
            {"status": "R100", "path": "templates/new.html", "old_path": "templates/old.html"},
            {"status": "M", "path": "apps/example.py", "old_path": ""},
        ]
        expected = hashlib.sha256(contract.canonical_json_bytes(expected_tuples)).hexdigest()
        changed_classification = json.loads(json.dumps(entries))
        changed_classification[0]["runtime_ui"] = False
        changed_classification[0]["runtime_ui_paths"] = []

        self.assertEqual(contract.changed_path_evidence_sha256(entries), expected)
        self.assertEqual(
            contract.changed_path_evidence_sha256(changed_classification),
            expected,
        )

    def test_external_ref_fails_closed_for_traversal_hash_and_projection_drift(self) -> None:
        payload = self._large_payload()
        plan_ref = "docs/plans/260830_0241_fixture.md"
        materialization = contract.prepare_materialized_contract(
            payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref="docs/code_reviews/260830_0241_fixture.md",
        )
        plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=plan,
            draft_ref="docs/code_drafts/260830_0241_fixture__code_draft.md",
            draft_text=draft,
            materialization=materialization,
        )
        wrapper = json.loads(str(materialization["markdown"]).split("\n", 1)[1].rsplit("\n```", 1)[0])
        reference = wrapper["review_visual_lane_contract_ref"]

        traversal = dict(reference)
        traversal["full_payload_ref"] = "../outside.json"
        parsed, errors = contract.parse_materialized_contract(
            "```json\n" + json.dumps({"review_visual_lane_contract_ref": traversal}) + "\n```",
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["ref_unsafe"])

        foreign_asset = dict(reference)
        foreign_asset["full_payload_ref"] = (
            "docs/code_reviews/assets/adjacent/review_visual_lane_contract.v2.json"
        )
        parsed, errors = contract.parse_materialized_contract(
            "```json\n" + json.dumps({"review_visual_lane_contract_ref": foreign_asset}) + "\n```",
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["identity_mismatch"])

        hash_drift = dict(reference)
        hash_drift["full_payload_sha256"] = "0" * 64
        parsed, errors = contract.parse_materialized_contract(
            "```json\n" + json.dumps({"review_visual_lane_contract_ref": hash_drift}) + "\n```",
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["full_payload_sha256_mismatch"])

        projection_drift = dict(reference)
        projection_drift["reason"] = "tampered"
        parsed, errors = contract.parse_materialized_contract(
            "```json\n" + json.dumps({"review_visual_lane_contract_ref": projection_drift}) + "\n```",
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["projection_mismatch"])

    def test_full_payload_missing_identity_count_digest_and_symlink_fail_closed(self) -> None:
        payload = self._large_payload()
        plan_ref = "docs/plans/260830_0241_fixture.md"
        materialization = contract.prepare_materialized_contract(
            payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref="docs/code_reviews/260830_0241_fixture.md",
        )
        plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=plan,
            draft_ref="docs/code_drafts/260830_0241_fixture__code_draft.md",
            draft_text=draft,
            materialization=materialization,
        )
        support = self.root / str(materialization["support_ref"])
        original_support = support.read_bytes()
        wrapper = json.loads(str(materialization["markdown"]).split("\n", 1)[1].rsplit("\n```", 1)[0])
        reference = wrapper["review_visual_lane_contract_ref"]

        support.unlink()
        parsed, errors = contract.parse_materialized_contract(
            str(materialization["markdown"]),
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["full_payload_missing"])
        support.write_bytes(original_support)

        def assert_full_error(mutate: object, expected_error: str) -> None:
            full = json.loads(original_support.decode("utf-8"))
            mutate(full)  # type: ignore[operator]
            altered = contract.canonical_json_bytes(full)
            support.write_bytes(altered)
            altered_reference = dict(reference)
            altered_reference["full_payload_sha256"] = hashlib.sha256(altered).hexdigest()
            parsed, errors = contract.parse_materialized_contract(
                contract.render_materialized_contract(altered_reference),
                project_root=self.root,
                expected_plan_ref=plan_ref,
            )
            self.assertIsNone(parsed)
            self.assertEqual(errors, [expected_error])

        assert_full_error(lambda full: full.__setitem__("base", "c" * 40), "identity_mismatch")
        assert_full_error(
            lambda full: full.__setitem__("changed_path_count", 0),
            "changed_path_count_mismatch",
        )
        assert_full_error(
            lambda full: full.__setitem__("changed_path_evidence_sha256", "0" * 64),
            "changed_path_digest_mismatch",
        )

        support.write_bytes(original_support)
        outside = self.root / "outside-support.json"
        outside.write_bytes(original_support)
        support.unlink()
        support.symlink_to(outside)
        parsed, errors = contract.parse_materialized_contract(
            str(materialization["markdown"]),
            project_root=self.root,
            expected_plan_ref=plan_ref,
        )
        self.assertIsNone(parsed)
        self.assertEqual(errors, ["ref_unsafe"])

    def test_same_identity_external_to_inline_allows_nonidentity_change_and_ignores_orphan_history(self) -> None:
        base = "a" * 40
        head = "b" * 40
        plan_ref = "docs/plans/260911_w4_same_identity.md"
        draft_ref = "docs/code_drafts/260911_w4_same_identity__code_draft.md"
        review_ref = "docs/code_reviews/260911_w4_same_identity.md"
        payload = self._large_payload(count=3)
        payload["reason"] = "verbose_generation_note:" + "x" * 20_000

        old_full = contract._full_contract_from_v1(
            payload,
            base=base,
            head=head,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )
        old_hash = hashlib.sha256(contract.canonical_json_bytes(old_full)).hexdigest()
        external = contract.prepare_materialized_contract(
            payload,
            base=base,
            head=head,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )
        self.assertEqual(external["mode"], "external")
        external_plan = "# Plan\n\n## Review visual lane contract\n\n" + str(external["markdown"]) + "\n"
        external_draft = "# Draft\n\n## Review visual lane contract\n\n" + str(external["markdown"]) + "\n"
        # Unrelated JSON blocks retain their existing last-member semantics.
        external_plan += '\n```json\n{"unrelated": 1, "unrelated": 2}\n```\n'
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=external_plan,
            draft_ref=draft_ref,
            draft_text=external_draft,
            materialization=external,
        )

        plan_path = self.root / plan_ref
        draft_path = self.root / draft_ref
        support_path = self.root / str(external["support_ref"])
        support_before = support_path.read_bytes()
        payload["reason"] = "repo_backed_visual_lane"
        requested_full = contract._full_contract_from_v1(
            payload,
            base=base,
            head=head,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )
        self.assertEqual(
            tuple(old_full[field] for field in contract.FULL_IDENTITY_FIELDS),
            tuple(requested_full[field] for field in contract.FULL_IDENTITY_FIELDS),
        )
        self.assertNotEqual(old_full, requested_full)
        self.assertNotEqual(
            old_hash,
            hashlib.sha256(contract.canonical_json_bytes(requested_full)).hexdigest(),
        )

        inline = contract.prepare_materialized_contract(
            payload,
            base=base,
            head=head,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )
        self.assertEqual(inline["mode"], "inline")
        inline_plan = "# Plan\n\n## Review visual lane contract\n\n" + str(inline["markdown"]) + "\n"
        inline_draft = "# Draft\n\n## Review visual lane contract\n\n" + str(inline["markdown"]) + "\n"
        # One declared old ref plus a separate valid inline draft is allowed;
        # the publisher heals both derived carriers to the incoming inline form.
        draft_path.write_text(inline_draft, encoding="utf-8")
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=inline_plan,
            draft_ref=draft_ref,
            draft_text=inline_draft,
            materialization=inline,
        )
        self.assertEqual(plan_path.read_bytes(), inline_plan.encode("utf-8"))
        self.assertEqual(draft_path.read_bytes(), inline_draft.encode("utf-8"))
        self.assertEqual(support_path.read_bytes(), support_before)

        refreshed = contract.prepare_materialized_contract(
            payload,
            base=base,
            head=head,
            exclude_docs=1,
            plan_ref=plan_ref,
            review_artifact_ref=review_ref,
        )
        self.assertEqual(refreshed["mode"], "inline")
        refreshed_plan = "# Refreshed plan\n\n## Review visual lane contract\n\n" + str(refreshed["markdown"]) + "\n"
        refreshed_draft = "# Refreshed draft\n\n## Review visual lane contract\n\n" + str(refreshed["markdown"]) + "\n"
        contract.publish_generated_scaffold(
            project_root=self.root,
            plan_ref=plan_ref,
            plan_text=refreshed_plan,
            draft_ref=draft_ref,
            draft_text=refreshed_draft,
            materialization=refreshed,
        )
        self.assertEqual(plan_path.read_bytes(), refreshed_plan.encode("utf-8"))
        self.assertEqual(draft_path.read_bytes(), refreshed_draft.encode("utf-8"))
        self.assertEqual(support_path.read_bytes(), support_before)

    def test_inline_replacement_refuses_unverifiable_declared_old_authority(self) -> None:
        for fixture, carrier in (
            ("missing_support", "plan"),
            ("malformed_support", "plan"),
            ("support_body_drift", "plan"),
            ("identity_drift", "plan"),
            ("profile_drift", "plan"),
            ("review_ref_drift", "plan"),
            ("evidence_drift", "plan"),
            ("malformed_ref", "plan"),
            ("malformed_ref", "draft"),
            ("hash_drift", "draft"),
            ("wrong_schema", "plan"),
            ("malformed_ref_json", "plan"),
            ("multiple_ref", "plan"),
            ("inline_and_ref", "plan"),
        ):
            with self.subTest(fixture=fixture, carrier=carrier):
                base = "a" * 40
                head = "b" * 40
                plan_ref = f"docs/plans/260911_w4_{fixture}_{carrier}.md"
                draft_ref = f"docs/code_drafts/260911_w4_{fixture}_{carrier}__code_draft.md"
                review_ref = f"docs/code_reviews/260911_w4_{fixture}_{carrier}.md"
                payload = self._large_payload(count=3)
                payload["reason"] = "old_external:" + "x" * 20_000
                external = contract.prepare_materialized_contract(
                    payload, base=base, head=head, exclude_docs=0,
                    plan_ref=plan_ref, review_artifact_ref=review_ref,
                )
                self.assertEqual(external["mode"], "external")
                external_markdown = str(external["markdown"])
                external_plan = "# Plan\n\n## Review visual lane contract\n\n" + external_markdown + "\n"
                external_draft = "# Draft\n\n## Review visual lane contract\n\n" + external_markdown + "\n"
                contract.publish_generated_scaffold(
                    project_root=self.root, plan_ref=plan_ref, plan_text=external_plan,
                    draft_ref=draft_ref, draft_text=external_draft, materialization=external,
                )
                plan_path = self.root / plan_ref
                draft_path = self.root / draft_ref
                support_path = self.root / str(external["support_ref"])
                if fixture == "missing_support":
                    support_path.unlink()
                elif fixture == "malformed_support":
                    support_path.write_bytes(b"{}")
                elif fixture == "support_body_drift":
                    old_full = json.loads(support_path.read_text(encoding="utf-8"))
                    old_full["reason"] = "tampered_support_body"
                    support_path.write_bytes(contract.canonical_json_bytes(old_full))
                elif fixture == "malformed_ref":
                    path = plan_path if carrier == "plan" else draft_path
                    original = path.read_text(encoding="utf-8")
                    corrupted = original.replace('"full_payload_sha256":', '"broken_full_payload_sha256":', 1)
                    self.assertNotEqual(corrupted, original)
                    path.write_text(corrupted, encoding="utf-8")
                elif fixture == "hash_drift":
                    original = draft_path.read_text(encoding="utf-8")
                    old_hash = str(external["support_sha256"])
                    bad_hash = "0" * 64 if old_hash != "0" * 64 else "1" * 64
                    corrupted = original.replace(old_hash, bad_hash, 1)
                    self.assertNotEqual(corrupted, original)
                    draft_path.write_text(corrupted, encoding="utf-8")
                elif fixture == "wrong_schema":
                    original = plan_path.read_text(encoding="utf-8")
                    corrupted = original.replace(
                        '"schema_version": "review_visual_lane_contract_ref.v1"',
                        '"schema_version": "review_visual_lane_contract_ref.v0"',
                        1,
                    )
                    self.assertNotEqual(corrupted, original)
                    plan_path.write_text(corrupted, encoding="utf-8")
                elif fixture == "malformed_ref_json":
                    original = plan_path.read_text(encoding="utf-8")
                    corrupted = original.replace(
                        '"review_visual_lane_contract_ref": {',
                        '"review_visual_lane_contract_ref": {,',
                        1,
                    )
                    self.assertNotEqual(corrupted, original)
                    plan_path.write_text(corrupted, encoding="utf-8")
                elif fixture == "multiple_ref":
                    plan_path.write_text(
                        plan_path.read_text(encoding="utf-8") + "\n" + external_markdown + "\n",
                        encoding="utf-8",
                    )
                elif fixture == "inline_and_ref":
                    plan_path.write_text(
                        plan_path.read_text(encoding="utf-8")
                        + "\n"
                        + contract.render_materialized_contract(self.discover())
                        + "\n",
                        encoding="utf-8",
                    )
                before = (
                    plan_path.read_bytes(),
                    draft_path.read_bytes(),
                    support_path.read_bytes() if support_path.exists() else None,
                )

                payload["reason"] = "repo_backed_visual_lane"
                incoming_exclude_docs = 1 if fixture == "identity_drift" else 0
                incoming_review_ref = review_ref
                if fixture == "profile_drift":
                    payload["profile_id"] = "other-profile"
                elif fixture == "review_ref_drift":
                    incoming_review_ref = "docs/code_reviews/260911_w4_other_artifact.md"
                elif fixture == "evidence_drift":
                    payload["changed_path_evidence"][0]["path"] = "apps/other_requested_path.py"
                inline = contract.prepare_materialized_contract(
                    payload, base=base, head=head, exclude_docs=incoming_exclude_docs,
                    plan_ref=plan_ref, review_artifact_ref=incoming_review_ref,
                )
                self.assertEqual(inline["mode"], "inline")
                inline_plan = "# Plan\n\n## Review visual lane contract\n\n" + str(inline["markdown"]) + "\n"
                inline_draft = "# Draft\n\n## Review visual lane contract\n\n" + str(inline["markdown"]) + "\n"
                with mock.patch.object(
                    contract, "_atomic_write", wraps=contract._atomic_write
                ) as atomic_write:
                    with self.assertRaisesRegex(contract.PublicationError, "^publication_conflict$"):
                        contract.publish_generated_scaffold(
                            project_root=self.root, plan_ref=plan_ref, plan_text=inline_plan,
                            draft_ref=draft_ref, draft_text=inline_draft, materialization=inline,
                        )
                atomic_write.assert_not_called()
                self.assertEqual(
                    (
                        plan_path.read_bytes(),
                        draft_path.read_bytes(),
                        support_path.read_bytes() if support_path.exists() else None,
                    ),
                    before,
                )

    def test_inline_replacement_normalizes_malformed_data_and_duplicate_ref_members(self) -> None:
        for fixture in (
            "ref_exclude_docs_list",
            "ref_exclude_docs_dict",
            "support_mandatory_modes_nested_list",
            "duplicate_outer_ref_member",
            "duplicate_escaped_outer_ref_member",
            "duplicate_nested_ref_identity_member",
        ):
            with self.subTest(fixture=fixture):
                base = "a" * 40
                head = "b" * 40
                plan_ref = f"docs/plans/260911_w4_private_guard_{fixture}.md"
                draft_ref = (
                    f"docs/code_drafts/260911_w4_private_guard_{fixture}__code_draft.md"
                )
                review_ref = f"docs/code_reviews/260911_w4_private_guard_{fixture}.md"
                payload = self._large_payload(count=3)
                payload["reason"] = "old_external:" + "x" * 20_000
                external = contract.prepare_materialized_contract(
                    payload,
                    base=base,
                    head=head,
                    exclude_docs=0,
                    plan_ref=plan_ref,
                    review_artifact_ref=review_ref,
                )
                self.assertEqual(external["mode"], "external")
                external_markdown = str(external["markdown"])
                external_plan = (
                    "# Plan\n\n## Review visual lane contract\n\n"
                    + external_markdown
                    + "\n"
                )
                external_draft = (
                    "# Draft\n\n## Review visual lane contract\n\n"
                    + external_markdown
                    + "\n"
                )
                contract.publish_generated_scaffold(
                    project_root=self.root,
                    plan_ref=plan_ref,
                    plan_text=external_plan,
                    draft_ref=draft_ref,
                    draft_text=external_draft,
                    materialization=external,
                )

                plan_path = self.root / plan_ref
                draft_path = self.root / draft_ref
                support_path = self.root / str(external["support_ref"])
                wrapper = json.loads(
                    external_markdown.split("\n", 1)[1].rsplit("\n```", 1)[0]
                )
                reference = dict(wrapper["review_visual_lane_contract_ref"])

                if fixture in {"ref_exclude_docs_list", "ref_exclude_docs_dict"}:
                    path = plan_path if fixture.endswith("list") else draft_path
                    original = path.read_text(encoding="utf-8")
                    replacement = "[]" if fixture.endswith("list") else "{}"
                    corrupted = original.replace(
                        '"exclude_docs": 0',
                        f'"exclude_docs": {replacement}',
                        1,
                    )
                    self.assertNotEqual(corrupted, original)
                    path.write_text(corrupted, encoding="utf-8")
                elif fixture == "support_mandatory_modes_nested_list":
                    old_full = json.loads(support_path.read_text(encoding="utf-8"))
                    old_full["mandatory_modes"] = [[]]
                    support_bytes = contract.canonical_json_bytes(old_full)
                    rebased_reference = contract._reference_from_full(
                        old_full,
                        full_payload_ref=str(external["support_ref"]),
                        full_payload_sha256=hashlib.sha256(support_bytes).hexdigest(),
                    )
                    rebased_markdown = contract.render_materialized_contract(rebased_reference)
                    plan_path.write_text(
                        "# Plan\n\n## Review visual lane contract\n\n"
                        + rebased_markdown
                        + "\n",
                        encoding="utf-8",
                    )
                    draft_path.write_text(
                        "# Draft\n\n## Review visual lane contract\n\n"
                        + rebased_markdown
                        + "\n",
                        encoding="utf-8",
                    )
                    support_path.write_bytes(support_bytes)
                elif fixture in {
                    "duplicate_outer_ref_member",
                    "duplicate_escaped_outer_ref_member",
                }:
                    first_reference = dict(reference)
                    first_reference["exclude_docs"] = 1
                    second_key = (
                        r'"review\u005fvisual_lane_contract_ref"'
                        if fixture == "duplicate_escaped_outer_ref_member"
                        else '"review_visual_lane_contract_ref"'
                    )
                    duplicate_markdown = (
                        "```json\n"
                        + '{"review_visual_lane_contract_ref": '
                        + json.dumps(first_reference, ensure_ascii=False, sort_keys=True)
                        + ", " + second_key + ": "
                        + json.dumps(reference, ensure_ascii=False, sort_keys=True)
                        + "}\n```"
                    )
                    plan_path.write_text(
                        "# Plan\n\n## Review visual lane contract\n\n"
                        + duplicate_markdown
                        + "\n",
                        encoding="utf-8",
                    )
                elif fixture == "duplicate_nested_ref_identity_member":
                    reference_json = json.dumps(reference, ensure_ascii=False, sort_keys=True)
                    self.assertIn('"exclude_docs": 0', reference_json)
                    duplicate_reference_json = reference_json.replace(
                        '"exclude_docs": 0',
                        '"exclude_docs": 1, "exclude_docs": 0',
                        1,
                    )
                    duplicate_markdown = (
                        "```json\n"
                        + '{"review_visual_lane_contract_ref": '
                        + duplicate_reference_json
                        + "}\n```"
                    )
                    plan_path.write_text(
                        "# Plan\n\n## Review visual lane contract\n\n"
                        + duplicate_markdown
                        + "\n",
                        encoding="utf-8",
                    )
                else:
                    self.fail(f"unknown fixture: {fixture}")

                before = (
                    plan_path.read_bytes(),
                    draft_path.read_bytes(),
                    support_path.read_bytes(),
                )
                payload["reason"] = "repo_backed_visual_lane"
                inline = contract.prepare_materialized_contract(
                    payload,
                    base=base,
                    head=head,
                    exclude_docs=0,
                    plan_ref=plan_ref,
                    review_artifact_ref=review_ref,
                )
                self.assertEqual(inline["mode"], "inline")
                inline_plan = (
                    "# Inline plan\n\n## Review visual lane contract\n\n"
                    + str(inline["markdown"])
                    + "\n"
                )
                inline_draft = (
                    "# Inline draft\n\n## Review visual lane contract\n\n"
                    + str(inline["markdown"])
                    + "\n"
                )
                with mock.patch.object(
                    contract, "_atomic_write", wraps=contract._atomic_write
                ) as atomic_write:
                    with self.assertRaisesRegex(
                        contract.PublicationError,
                        "^publication_conflict$",
                    ):
                        contract.publish_generated_scaffold(
                            project_root=self.root,
                            plan_ref=plan_ref,
                            plan_text=inline_plan,
                            draft_ref=draft_ref,
                            draft_text=inline_draft,
                            materialization=inline,
                        )
                atomic_write.assert_not_called()
                self.assertEqual(
                    (
                        plan_path.read_bytes(),
                        draft_path.read_bytes(),
                        support_path.read_bytes(),
                    ),
                    before,
                )

    def test_publication_rolls_back_injected_failure_and_refuses_conflict(self) -> None:
        payload = self._large_payload()
        plan_ref = "docs/plans/260830_0241_fixture.md"
        materialization = contract.prepare_materialized_contract(
            payload,
            base="a" * 40,
            head="b" * 40,
            exclude_docs=0,
            plan_ref=plan_ref,
            review_artifact_ref="docs/code_reviews/260830_0241_fixture.md",
        )
        plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
        with self.assertRaises(contract.PublicationError):
            contract.publish_generated_scaffold(
                project_root=self.root,
                plan_ref=plan_ref,
                plan_text=plan,
                draft_ref="docs/code_drafts/260830_0241_fixture__code_draft.md",
                draft_text=draft,
                materialization=materialization,
                inject_failure_after="support",
            )
        self.assertFalse((self.root / str(materialization["support_ref"])).exists())
        self.assertFalse((self.root / plan_ref).exists())

        support = self.root / str(materialization["support_ref"])
        support.parent.mkdir(parents=True, exist_ok=True)
        support.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(contract.PublicationError, "publication_conflict"):
            contract.publish_generated_scaffold(
                project_root=self.root,
                plan_ref=plan_ref,
                plan_text=plan,
                draft_ref="docs/code_drafts/260830_0241_fixture__code_draft.md",
                draft_text=draft,
                materialization=materialization,
            )

    def test_publication_lock_serializes_overlapping_scaffolds(self) -> None:
        plan_refs = (
            "docs/plans/260830_0241_concurrent_first_fixture.md",
            "docs/plans/260830_0241_concurrent_second_fixture.md",
        )
        draft_refs = (
            "docs/code_drafts/260830_0241_concurrent_first_fixture__code_draft.md",
            "docs/code_drafts/260830_0241_concurrent_second_fixture__code_draft.md",
        )
        review_ref = "docs/code_reviews/260830_0241_concurrent_shared_support_fixture.md"
        first_payload = self._large_payload()
        second_payload = json.loads(json.dumps(first_payload))
        second_payload["reason"] = "distinct_snapshot"
        materializations: list[tuple[str, str, dict[str, object], str, str]] = []
        for plan_ref, draft_ref, payload, base, head in (
            (plan_refs[0], draft_refs[0], first_payload, "a" * 40, "b" * 40),
            (plan_refs[1], draft_refs[1], second_payload, "c" * 40, "d" * 40),
        ):
            materialization = contract.prepare_materialized_contract(
                payload,
                base=base,
                head=head,
                exclude_docs=0,
                plan_ref=plan_ref,
                review_artifact_ref=review_ref,
            )
            plan = "# Plan\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            draft = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            materializations.append((plan_ref, draft_ref, materialization, plan, draft))

        worker = """
import json
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[1])
from scripts import review_visual_lane_contract as contract

try:
    contract.publish_generated_scaffold(
        project_root=sys.argv[2],
        plan_ref=sys.argv[3],
        plan_text=sys.argv[5],
        draft_ref=sys.argv[4],
        draft_text=sys.argv[6],
        materialization=json.loads(sys.argv[7]),
    )
except contract.PublicationError as exc:
    print(f"error:{exc}")
    raise SystemExit(1)
print("ok")
"""
        processes: list[subprocess.Popen[str]] = []
        with contract._scaffold_publication_lock(self.root):
            for plan_ref, draft_ref, materialization, plan, draft in materializations:
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-B",
                            "-c",
                            worker,
                            str(REPO_ROOT),
                            str(self.root),
                            plan_ref,
                            draft_ref,
                            plan,
                            draft,
                            json.dumps(materialization),
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                )
            time.sleep(0.2)
            self.assertTrue(all(process.poll() is None for process in processes))

        results = [
            (process.returncode, stdout.strip(), stderr)
            for process in processes
            for stdout, stderr in [process.communicate(timeout=10)]
        ]
        self.assertEqual(sorted(result[0] for result in results), [0, 1], results)
        self.assertEqual(sorted(result[1] for result in results), ["error:publication_conflict", "ok"])

        winners: list[dict[str, object]] = []
        for plan_ref, draft_ref, _materialization, _plan, _draft in materializations:
            plan_path = self.root / plan_ref
            draft_path = self.root / draft_ref
            self.assertEqual(plan_path.exists(), draft_path.exists())
            if not plan_path.exists():
                continue
            plan_payload, plan_errors = contract.parse_materialized_contract(
                plan_path.read_text(encoding="utf-8"),
                project_root=self.root,
                expected_plan_ref=plan_ref,
            )
            draft_payload, draft_errors = contract.parse_materialized_contract(
                draft_path.read_text(encoding="utf-8"),
                project_root=self.root,
                expected_plan_ref=plan_ref,
            )
            self.assertEqual(plan_errors, [])
            self.assertEqual(draft_errors, [])
            self.assertEqual(plan_payload, draft_payload)
            assert plan_payload is not None
            winners.append(plan_payload)

        self.assertEqual(len(winners), 1)
        self.assertIn(winners[0], [first_payload, second_payload])
        lock_path = self.root / ".tmp/review_visual_lane_contract_locks/publication.lock"
        self.assertTrue(lock_path.is_file())
        self.assertFalse(lock_path.is_symlink())


if __name__ == "__main__":
    unittest.main()

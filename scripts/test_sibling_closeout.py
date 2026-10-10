from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import sibling_closeout as MODULE


PLAN = "docs/plans/261003_0100_fixture.md"
REVIEW = "docs/code_reviews/261003_0100_fixture.md"
TARGET = "target with spaces $(touch injected).txt"


class Blocked(RuntimeError):
    pass


class FixtureContext:
    """Disposable real Git with controlled canonical command verdicts."""
    def __init__(self, root: Path):
        self.project = self.runtime = root
        self.plan_ref = PLAN
        self.paths = [PLAN, REVIEW, TARGET]
        self.calls = []
        self.oracle_override = {}
        self.bundle_override = None
        self.preflight_override = None
        self.fail_final_lint = False
        self.fail_setter = False
        self.drift_during_final_preflight = False
        self.docs_payload = None

    def fail(self, message):
        raise Blocked(message)

    def git(self, *args, root=None):
        self.calls.append(("git", *args))
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        result = subprocess.run(["git", "-C", str(root or self.project), *args],
                                env=env, capture_output=True, text=True, check=False)
        if result.returncode:
            self.fail(result.stderr)
        return result

    def plan(self):
        rows = (self.project / self.plan_ref).read_text(encoding="utf-8").splitlines()
        line = next(row for row in rows if row.startswith("**Status:**"))
        oracle = {"status_norm": line.split("**Status:**", 1)[1].strip().casefold(),
                  "route_guard_triggered": False, "review_readback_state": "ok",
                  "owner_qna_readback_state": "clean", "owner_qna_issues": [],
                  "open_owner_questions": [], "queue_closeout_ready": True}
        return self.plan_ref, {**oracle, **self.oracle_override}

    def before_effect(self):
        self.calls.append(("before_effect",))

    def set_status(self, plan, status):
        self.calls.append(("set_status", plan, status))
        path = self.project / plan
        rows = path.read_text(encoding="utf-8").splitlines()
        rows = [re.sub(r"^(\*\*Status:\*\*\s*).*$", r"\g<1>Done  ", row) for row in rows]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        if self.fail_setter:
            self.fail("setter failure after write")

    def _bundle(self):
        if self.bundle_override is not None:
            return copy.deepcopy(self.bundle_override)
        staged = self.git("diff", "--cached", "--name-only", "-z").stdout.split("\0")
        staged = sorted(item for item in staged if item)
        unstaged = self.git("--literal-pathspecs", "diff", "--name-only", "-z", "--", *self.paths).stdout.split("\0")
        unstaged = sorted(item for item in unstaged if item)
        extra = sorted(set(staged) - set(self.paths))
        untracked = self.git("--literal-pathspecs", "ls-files", "--others", "--exclude-standard", "-z", "--", *self.paths).stdout.split("\0")
        untracked = sorted(item for item in untracked if item)
        kind = ("staged_mismatch" if extra else "needs_rerun" if staged and (unstaged or untracked)
                else "commit_ready" if staged else "staged_empty" if unstaged or untracked else "already_materialized")
        return {"plan": self.plan_ref, "bundle_ok": True, "errors": [], "closeout_kind": kind,
                "repo_roots": [{"repo_root": str(self.project), "bundle_paths": sorted(self.paths),
                                "staged_extra_paths": extra, "staged_bundle_paths": sorted(set(staged) & set(self.paths)),
                                "unstaged_bundle_paths": unstaged, "untracked_bundle_paths": untracked}]}

    def json_call(self, command, *args):
        self.calls.append((command, *args))
        if command == "planveyor_plan_bundle":
            return self._bundle()
        if command == "planveyor_plan_status_oracle":
            oracle = self.plan()[1]
            # --json emits the complete diagnostic payload even when the
            # plain-output --current-state flag is also supplied.
            oracle["oracle_run_id"] = str(uuid.uuid4())
            return oracle
        if command == "planveyor_consumer_doctor":
            if args:
                raise AssertionError("consumer doctor uses the facade's --project selector, with no positional arguments")
            return {"state": "ok"}
        if command == "planveyor_docs_closeout":
            return copy.deepcopy(self.docs_payload)
        if command == "planveyor_plan_closeout_preflight":
            if self.preflight_override is not None:
                return copy.deepcopy(self.preflight_override)
            kind = self._bundle()["closeout_kind"]
            ready = kind == "commit_ready"
            if self.drift_during_final_preflight and self.plan()[1]["status_norm"] == "done":
                (self.project / TARGET).write_text("unreviewed bytes\n", encoding="utf-8")
            return {"semantic_ready": True, "bundle_ready": True, "git_writable": True,
                    "staged_exact": ready, "commit_ready": ready, "closeout_state": kind,
                    "safe_command": "DO NOT EXECUTE $(touch injected)" if ready else None}
        raise AssertionError((command, args))

    def call(self, command, *args, input_text=None, check=True):
        self.calls.append((command, *args))
        if command == "planveyor_plan_lint":
            failed = self.fail_final_lint and "--as-status" not in args
            return subprocess.CompletedProcess(args, int(failed), "final lint rejected" if failed else "", "")
        if command == "planveyor_plan_bundle" and args[0] == "--stage":
            self.git("--literal-pathspecs", "add", "--", *self.paths)
            return subprocess.CompletedProcess(args, 0, "staged", "")
        raise AssertionError((command, args))


class SiblingCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.context = FixtureContext(self.root)
        self.context.git("init")
        self.context.git("config", "user.name", "Fixture")
        self.context.git("config", "user.email", "fixture@example.invalid")
        for relative, text in ((PLAN, f"# Проверенная задача\n\n**Status:** Architect arch review\n\n## Review artifacts\n- Code review (primary): `{REVIEW}`\n"),
                               (REVIEW, "# Review\n\n## Архитектурное ревью\nВердикт: принято.\nОбоснование: проверенная fixture scope.\n"),
                               (TARGET, "reviewed baseline\n")):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.context.git("add", "--", *self.context.paths)
        self.context.git("commit", "-m", "baseline")
        (self.root / TARGET).write_text("reviewed delivery\n", encoding="utf-8")
        self.context.calls.clear()

    def tearDown(self):
        self.temp.cleanup()

    def _args(self, commit=False, message=None, cycle=None):
        return SimpleNamespace(commit=commit, message=message, cycle=cycle)

    def _state(self):
        return (self.context.git("rev-parse", "HEAD").stdout,
                self.context.git("diff", "--cached", "--binary").stdout,
                (self.root / PLAN).read_bytes())

    def test_preview_and_declined_gates_have_no_status_index_or_history_effects(self):
        before = self._state()
        result = MODULE.handle_close(self.context, self._args())
        self.assertEqual(result["state"], "semantic_ready")
        self.assertEqual(set(result["paths"]), set(self.context.paths))
        self.assertIn("Проверенная задача", result["commit_message"])
        self.assertEqual(before, self._state())
        self.assertNotIn(("planveyor_plan_closeout_preflight", "--json", PLAN), self.context.calls)
        self.assertFalse(any(call[0] == "set_status" for call in self.context.calls))
        self.assertFalse(any(call[0].startswith("planveyor_manager") for call in self.context.calls))

    def test_foreign_staged_and_multi_root_fail_before_first_mutation(self):
        foreign = self.root / "foreign.txt"
        foreign.write_text("keep staged\n")
        self.context.git("add", "--", "foreign.txt")
        before = self._state()
        with self.assertRaisesRegex(Blocked, "вне выбранного bundle"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(before, self._state())
        self.assertFalse(any(call[0] == "set_status" for call in self.context.calls))
        self.context.bundle_override = self.context._bundle()
        self.context.bundle_override["repo_roots"].append(copy.deepcopy(self.context.bundle_override["repo_roots"][0]))
        with self.assertRaisesRegex(Blocked, "одного однозначного Git root"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(before, self._state())

    def test_arch_verdict_uses_only_unique_actual_section_and_first_line(self):
        bad_sections = (
            "## Архитектурное ревью\nВердикт: не принято.\nВердикт: принято.\n",
            "## Архитектурное ревью\n```text\nВердикт: принято.\n```\n",
            "## Архитектурное ревью\nВывод: требуется исправление.\nОК: принято.\n",
            "## Архитектурное ревью\nВердикт: принято условно после проверки.\n",
            "## Архитектурное ревью\nВердикт: принято. Требуется исправление перед Done.\n",
            "## Архитектурное ревью\nОК: нет согласования.\n",
            "## Архитектурное ревью\nВердикт: принято в пределах ещё не проверенного остатка.\n",
            "## Архитектурное ревью\nВердикт: принято в пределах exact contract-only G12.\n",
            "## Архитектурное ревью\nВердикт: архитектурная приёмка G11 подтверждена.\n",
            "## Архитектурное ревью\nВердикт: архитектурная приёмка подтверждена.\n",
            "## Архитектурное ревью\nВывод: принято.\n",
            "## Архитектурное ревью\nОК: реализация соответствует плану, замечаний нет.\n",
            "## Архитектурное ревью\nВердикт: принято.\n## Arch review\nВердикт: принято.\n",
            "```text\n## Архитектурное ревью\nВердикт: принято.\n```\n",
        )
        for text in bad_sections:
            with self.subTest(text=text):
                (self.root / REVIEW).write_text(text, encoding="utf-8")
                before = self._state()
                with self.assertRaises(Blocked) as rejected:
                    MODULE.handle_close(self.context, self._args(True))
                self.assertIn("planveyor sibling architect", str(rejected.exception))
                if text == bad_sections[0]:
                    self.assertIn("'Вердикт: не принято.'", str(rejected.exception))
                    self.assertIn("Вердикт: принято.", str(rejected.exception))
                self.assertEqual(before, self._state())
        for line in ("Вердикт: принято.", "ВЕРДИКТ: ПРИНЯТО."):
            (self.root / REVIEW).write_text("## Архитектурное ревью\n" + line + "\n", encoding="utf-8")
            self.assertEqual(MODULE._arch_acceptance(self.context, PLAN)["verdict"], line)

    def test_early_status_red_or_stale_review_and_owner_question_block(self):
        for override in ({"status_norm": "ready for arch review"}, {"review_readback_state": "stale_green_review"},
                         {"review_readback_state": "live_blocker"}, {"open_owner_questions": [{"id": "Q1"}]},
                         {"route_guard_triggered": True}):
            with self.subTest(override=override):
                self.context.oracle_override = override
                before = self._state()
                with self.assertRaises(Blocked):
                    MODULE.handle_close(self.context, self._args(True))
                self.assertEqual(before, self._state())

    def test_commit_uses_fresh_array_paths_and_literal_message_then_returns_run(self):
        message = "reviewed 'quotes' $(touch injected) `touch injected`\nactual second line"
        result = MODULE.handle_close(self.context, self._args(True, message))
        self.assertEqual(result["state"], "semantic_committed")
        self.assertEqual(result["next_command"], "planveyor sibling run")
        self.assertFalse((self.root / "injected").exists())
        commits = [call for call in self.context.calls if call[:3] == ("git", "--literal-pathspecs", "commit")]
        self.assertEqual(commits, [("git", "--literal-pathspecs", "commit", "-m", message, "--", PLAN, TARGET)])
        self.assertIn("**Status:** Done", self.context.git("show", f"HEAD:{PLAN}").stdout)
        self.assertEqual(self.context.git("show", f"HEAD:{TARGET}").stdout, "reviewed delivery\n")
        self.assertFalse(any(call[0].startswith("planveyor_manager") for call in self.context.calls))
        readings = [call for call in self.context.calls if call[0] == "planveyor_plan_status_oracle"]
        self.assertTrue(readings)
        self.assertTrue(all("--current-state" in call for call in readings))

    def test_real_oracle_uuid_is_the_only_ephemeral_fingerprint_exclusion(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        readings = []
        for _ in range(2):
            completed = subprocess.run([sys.executable, str(SCRIPT_ROOT / "plan_status_oracle.py"),
                "--json", "--current-state", str(self.root / PLAN)], cwd=self.root,
                env=env, capture_output=True, text=True, check=True)
            readings.append(json.loads(completed.stdout))
        self.assertNotEqual(readings[0]["oracle_run_id"], readings[1]["oracle_run_id"])
        evidence = [{key: value for key, value in reading.items() if key != "oracle_run_id"} for reading in readings]
        self.assertEqual(evidence[0], evidence[1])
        for field in ("plan_hash", "plan_mtime", "current_state"):
            self.assertIn(field, evidence[0])
        first = MODULE._fingerprint(self.context, self.context.paths, readings[0])
        self.assertEqual(first, MODULE._fingerprint(self.context, self.context.paths, readings[1]))
        for field in ("plan_hash", "plan_mtime", "current_state"):
            changed = copy.deepcopy(readings[1])
            changed[field] = "changed proof"
            self.assertNotEqual(first, MODULE._fingerprint(self.context, self.context.paths, changed))

    def test_failed_final_lint_restores_only_own_plan_bytes_and_does_not_commit(self):
        before = (self.root / PLAN).read_bytes()
        head = self.context.git("rev-parse", "HEAD").stdout
        self.context.fail_final_lint = True
        with self.assertRaisesRegex(Blocked, "Статус восстановлен"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(before, (self.root / PLAN).read_bytes())
        self.assertEqual(head, self.context.git("rev-parse", "HEAD").stdout)
        self.assertEqual(before.decode(), self.context.git("show", f":{PLAN}").stdout)
        self.assertEqual((self.root / TARGET).read_text(), "reviewed delivery\n")
        self.assertFalse(any(call[:2] == ("git", "reset") for call in self.context.calls))

    def test_setter_partial_failure_restores_written_status_before_final_stage(self):
        before = (self.root / PLAN).read_bytes()
        self.context.fail_setter = True
        with self.assertRaisesRegex(Blocked, "setter failure"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(before, (self.root / PLAN).read_bytes())
        stages = [call for call in self.context.calls if call[:2] == ("planveyor_plan_bundle", "--stage")]
        self.assertEqual(len(stages), 1)
        self.assertEqual(before.decode(), self.context.git("show", f":{PLAN}").stdout)

    def test_status_rollback_stages_only_literal_plan_path(self):
        literal = "docs/plans/261003_0100_fixture[a].md"
        foreign = "docs/plans/261003_0100_fixturea.md"
        (self.root / PLAN).rename(self.root / literal)
        (self.root / foreign).write_text("foreign baseline\n")
        self.context.plan_ref = literal
        self.context.paths = [literal, REVIEW, TARGET]
        self.context.git("add", "--all")
        self.context.git("commit", "-m", "literal path baseline")
        (self.root / foreign).write_text("foreign unstaged work\n")
        (self.root / TARGET).write_text("reviewed delivery again\n")
        original = (self.root / literal).read_bytes()
        self.context.fail_final_lint = True
        with self.assertRaisesRegex(Blocked, "Статус восстановлен"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual((self.root / literal).read_bytes(), original)
        self.assertNotIn(foreign, self.context.git("diff", "--cached", "--name-only").stdout.splitlines())
        self.assertEqual(self.context.git("show", f"HEAD:{foreign}").stdout, "foreign baseline\n")
        self.assertEqual((self.root / foreign).read_text(), "foreign unstaged work\n")

    def test_worktree_drift_during_preflight_blocks_pathspec_commit(self):
        self.context.drift_during_final_preflight = True
        head = self.context.git("rev-parse", "HEAD").stdout
        with self.assertRaisesRegex(Blocked, "изменились перед коммитом"):
            MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(head, self.context.git("rev-parse", "HEAD").stdout)
        self.assertIn("Architect arch review", (self.root / PLAN).read_text())
        self.assertEqual((self.root / TARGET).read_text(), "unreviewed bytes\n")

    def test_strict_preflight_false_fields_and_null_command_block_before_done(self):
        for field in ("git_writable", "commit_ready", "staged_exact"):
            self.context.preflight_override = {"semantic_ready": True, "bundle_ready": True,
                "git_writable": True, "staged_exact": True, "commit_ready": True,
                "closeout_state": "commit_ready", "safe_command": "ignored", field: False}
            with self.subTest(field=field), self.assertRaises(Blocked):
                MODULE.handle_close(self.context, self._args(True))
            self.assertIn("Architect arch review", (self.root / PLAN).read_text())
        self.context.preflight_override["safe_command"] = None
        with self.assertRaises(Blocked):
            MODULE.handle_close(self.context, self._args(True))

    def test_ready_does_not_run_stack_commands_and_blocked_noop_is_not_ready(self):
        self.context.set_status(PLAN, "Done")
        self.context.git("add", "--", PLAN)
        self.context.git("commit", "-m", "fixture done")
        self.context.docs_payload = {"schema": "docs_closeout_payload.v1", "schema_state": "ok",
            "plan_ref": PLAN, "state": "blocked", "final_docs_commit": "no_op", "reason_code": "missing_capture"}
        result = MODULE.handle_ready(self.context, SimpleNamespace())
        self.assertEqual(result["state"], "pending")
        self.assertFalse(any(call[0] in {"make", "planveyor_plan_lint", "planveyor_manager_init"} for call in self.context.calls))

    def test_done_with_canonical_pending_semantic_delta_can_be_committed(self):
        self.context.set_status(PLAN, "Done")
        self.context.docs_payload = {"schema": "docs_closeout_payload.v1", "schema_state": "ok",
            "plan_ref": PLAN, "state": "blocked", "reason_code": "semantic_closeout_has_unstaged_delta",
            "semantic_closeout_kind": "staged_empty", "bundle_ok": True, "final_docs_diff_paths": [],
            "current_plan_owned_docs_delta_paths": []}
        preview = MODULE.handle_close(self.context, self._args())
        self.assertEqual(preview["state"], "semantic_ready")
        result = MODULE.handle_close(self.context, self._args(True))
        self.assertEqual(result["state"], "semantic_committed")
        self.assertEqual(self.context.git("show", f"HEAD:{TARGET}").stdout, "reviewed delivery\n")

    def test_clean_arch_review_refuses_before_stage_or_status_effects(self):
        self.context.git("add", "--", TARGET)
        self.context.git("commit", "-m", "already committed Arch fixture")
        before = self._state()
        for explicit_commit in (False, True):
            self.context.calls.clear()
            with self.assertRaisesRegex(Blocked, "Переход Done без semantic delta") as rejected:
                MODULE.handle_close(self.context, self._args(explicit_commit))
            self.assertIn("planveyor sibling architect", str(rejected.exception))
            self.assertEqual(before, self._state())
            self.assertFalse(any(call[0] == "set_status" or call[:2] == ("planveyor_plan_bundle", "--stage")
                                 or call[0] == "planveyor_plan_closeout_preflight" for call in self.context.calls))


class ExistingCaptureIntegrationTests(unittest.TestCase):
    def test_docs_preview_exact_commit_and_immediate_cold_readback_use_existing_receipt(self):
        # Reuse the existing capture fixture and actual receipt/tree/CAS writers.
        from test_planveyor_plan_bundle import PlanBundleCommitReadyTests, CAPTURE_PLAN_REL
        fixture = PlanBundleCommitReadyTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixture._init_repo(root)
            docs, owned = fixture._capture_docs_payload(root)
            cycle = str(docs["followups_capture_cycle_id"])
            context = FixtureContext(root)
            context.plan_ref = CAPTURE_PLAN_REL
            context.paths = [CAPTURE_PLAN_REL]
            docs.update({"state": "completed", "bundle_ok": True, "bundle_errors": [],
                "process_improvement_capture_state": "clean_noop",
                "followups_reconciliation": {"state": "clean_noop"}})
            context.docs_payload = docs
            canonical_call = context.call
            seen = []

            def call(command, *args, input_text=None, check=True):
                seen.append((command, args))
                payload = json.loads(input_text) if input_text else None
                if command == "planveyor_plan_bundle" and args[0] == "--stage":
                    output = MODULE.followups_capture.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
                elif command == "planveyor_plan_closeout_preflight":
                    output = MODULE.followups_capture.commit_preflight(root, CAPTURE_PLAN_REL, payload)
                elif command == "planveyor_plan_bundle" and args[0] == "--commit-exact":
                    self.assertEqual(payload["schema_version"], "followups_commit_preflight.v1")
                    output = MODULE.followups_capture.commit_exact(root, CAPTURE_PLAN_REL, payload, message_auto=True)
                    # Cold proof uses the canonical reader against the committed objects.
                    readback = MODULE.followups_capture.read_capture(root, CAPTURE_PLAN_REL, cycle)
                    self.assertIn(readback["state"], {"materialized", "clean_noop"})
                    context.docs_payload = {**docs, "final_docs_commit": "landed", "final_docs_diff_paths": [],
                                            "current_plan_owned_docs_delta_paths": []}
                else:
                    return canonical_call(command, *args, input_text=input_text, check=check)
                return subprocess.CompletedProcess(args, 0, json.dumps(output), "")

            context.call = call
            before_head = context.git("rev-parse", "HEAD").stdout
            preview = MODULE.handle_close(context, SimpleNamespace(commit=False, cycle=None, message=None))
            self.assertEqual(preview["state"], "docs_ready")
            self.assertEqual(context.git("diff", "--cached", "--name-only").stdout, "")
            self.assertEqual(before_head, context.git("rev-parse", "HEAD").stdout)
            result = MODULE.handle_close(context, SimpleNamespace(commit=True, cycle=None, message=None))
            self.assertEqual(result["state"], "completed")
            self.assertEqual(context.git("show", f"HEAD:{owned}").stdout, (root / owned).read_text())
            self.assertEqual([item[0] for item in seen],
                             ["planveyor_plan_bundle", "planveyor_plan_closeout_preflight", "planveyor_plan_bundle"])
            docs_reads = [call for call in context.calls if call[0] == "planveyor_docs_closeout"]
            self.assertEqual(len(docs_reads), 3)
            self.assertTrue(all("--followups-capture-cycle-id" in call and cycle in call for call in docs_reads))


class PublicCloseoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_sibling_runbook import PublicSiblingTests
        cls.transport = PublicSiblingTests
        cls.failed = False
        cls.transport.setUpClass()

    @classmethod
    def tearDownClass(cls):
        if cls.failed:
            # Keep the same target/runtime and receipts for a narrow diagnosis;
            # never copy or reuse a receipt in another disposable checkout.
            cls.transport.temporary._finalizer.detach()
            print(f"Preserved failed disposable fixture: {cls.transport.root}", file=sys.stderr)
            return
        cls.transport.tearDownClass()

    def tearDown(self):
        result = self._outcome.result
        if any(test is self for test, _trace in result.errors + result.failures):
            type(self).failed = True

    def facade(self, *args, cwd=None, input_text=None, check=True):
        # A close invocation deliberately repeats the existing cold gates;
        # its complete attested route can exceed the smaller fixture timeout.
        public = self.transport
        completed = subprocess.run([str(public.runtime / "bin/planveyor"), *args],
            cwd=cwd or public.outside, env=public.env, text=True, input=input_text,
            capture_output=True, timeout=600, check=False)
        if check and completed.returncode:
            self.fail(f"{args}: {completed.returncode}\n{completed.stdout}\n{completed.stderr}")
        return completed

    def _accepted_fixture(self, target, status="Architect arch review"):
        from test_plan_lint import PlanLintReviewRouteDeterminismTests
        from test_planveyor_plan_bundle import PLAN_REL, REVIEW_REL, DRAFT_REL, PRIMARY_TARGET_REL
        from test_review_artifact_lint import ReviewArtifactLintTests
        with tempfile.TemporaryDirectory() as directory:
            scaffold = Path(directory).resolve()
            review_fixture = ReviewArtifactLintTests()
            review = review_fixture._single_commit_dual_lane_fixture(target=f"PLAN={PLAN_REL}")
            review += "\n## Архитектурное ревью\nВердикт: принято.\nОбоснование: fixture scope.\n"
            PlanLintReviewRouteDeterminismTests()._write_fixture(
                scaffold, plan_stem=Path(PLAN_REL).stem, plan_status=status,
                target_paths=[PRIMARY_TARGET_REL], review_artifact_lines=[f"- Code review (primary): `{REVIEW_REL}`"],
                review_artifact_payloads={REVIEW_REL: review}, complete=True,
                changes_block=f"- Scripts/tools:\n  - `{PRIMARY_TARGET_REL}`",
            )
            with (scaffold / PLAN_REL).open("a", encoding="utf-8") as handle:
                handle.write("\n## Evidence\n- reviewer_code_risk lane-run artifact:\n  ```json\n" +
                    json.dumps({"lane_id": "reviewer_code_risk", "target_snapshot": f"PLAN={PLAN_REL}",
                                "lane_status": "complete"}) + "\n  ```\n")
            (scaffold / PRIMARY_TARGET_REL).parent.mkdir(parents=True, exist_ok=True)
            (scaffold / PRIMARY_TARGET_REL).write_text("echo reviewed-fixture\n")
            for relative in (PLAN_REL, DRAFT_REL, REVIEW_REL, PRIMARY_TARGET_REL):
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(scaffold / relative, destination)
        return PLAN_REL

    def test_attested_facade_preview_and_semantic_commit_use_real_gates(self):
        public = self.transport
        target = public.root / "close-semantic"
        shutil.copytree(public.seed, target)
        PLAN_REL = self._accepted_fixture(target)
        self.facade("sibling", "plan", PLAN_REL, cwd=target)
        # The human path must read actual selected sibling context, not runtime.
        preview = self.facade("sibling", "close", cwd=target)
        self.assertIn("План принят", preview.stdout)
        self.assertEqual(subprocess.run(["git", "-C", str(target), "diff", "--cached", "--name-only"],
                                        capture_output=True, text=True).stdout, "")
        self.assertIn("Architect arch review", (target / PLAN_REL).read_text())
        committed = self.facade("sibling", "close", "--commit", cwd=target)
        self.assertIn("План закоммичен", committed.stdout)
        self.assertIn("planveyor sibling run", committed.stdout)
        shown = subprocess.run(["git", "-C", str(target), "show", f"HEAD:{PLAN_REL}"],
                               capture_output=True, text=True, check=True).stdout
        self.assertIn("**Status:** Done", shown)
        self.assertFalse((target / ".fixture_init_calls").exists())
        ready = self.facade("sibling", "ready", cwd=target)
        self.assertIn("Closeout ещё не завершён", ready.stdout)
        self._attested_docs_tail(target, PLAN_REL)

    def test_attested_canonical_verdict_preview_and_fresh_done_admission(self):
        public = self.transport
        target = public.root / "close-canonical-admission"
        shutil.copytree(public.seed, target)
        plan = self._accepted_fixture(target)
        self.facade("sibling", "plan", plan, cwd=target)
        head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout
        preview = self.facade("sibling", "close", cwd=target)
        self.assertIn("План принят", preview.stdout)
        self.assertEqual(subprocess.run(["git", "-C", str(target), "diff", "--cached", "--name-only"],
                                        capture_output=True, text=True, check=True).stdout, "")
        self.assertIn("Architect arch review", (target / plan).read_text())
        self.facade("--project", str(target), "planveyor_plan_bundle", "--stage", plan)
        self.facade("--project", str(target), "sibling", "--internal", "set-done", plan)
        self.assertIn("**Status:** Done", (target / plan).read_text())
        self.assertEqual(head, subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                                             capture_output=True, text=True, check=True).stdout)
        self.assertFalse((target / ".fixture_init_calls").exists())

    def test_attested_docs_closeout_and_ready_use_actual_facade(self):
        public = self.transport
        target = public.root / "close-docs"
        shutil.copytree(public.seed, target)
        plan = self._accepted_fixture(target, "Done")
        subprocess.run(["git", "-C", str(target), "add", "--all"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "Disposable accepted terminal fixture"],
                       check=True, capture_output=True)
        self.facade("sibling", "plan", plan, cwd=target)
        ready = self.facade("sibling", "ready", cwd=target)
        self.assertIn("Closeout ещё не завершён", ready.stdout)
        self._attested_docs_tail(target, plan)
        ready = self.facade("sibling", "ready", cwd=target)
        self.assertIn("Consumer contract и выбранный план закрыты", ready.stdout)

    def _attested_docs_tail(self, target, plan_ref):
        # The disposable capture simulates the existing Manager role output;
        # receipt generation uses the real, just-committed accepted plan and
        # canonical docs classifier rather than a synthetic semantic identity.
        capture = MODULE.followups_capture
        admission = json.loads(self.facade("--project", str(target), "planveyor_docs_closeout", plan_ref, "--json").stdout)
        self.assertEqual(admission["semantic_closeout_kind"], "already_materialized")
        begun = capture.begin_cycle(target, plan_ref, admission)
        cycle = str(begun["capture_cycle_id"])

        def text(role, cycle):
            if role == "Coder":
                return ("## Process improvements\n### Suggestion 1\n"
                    "- symptom: disposable receipt needs one owned PI delta\n"
                    "- process_gap: verify existing human docs transport\n"
                    "- suggested_fix: exercise stage and immutable commit\n"
                    "- owner: Architect\n- promotion_class: helper_change\n"
                    "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                    f"- source_ref: {plan_ref}\n")
            return "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"

        for role in capture.REQUIRED_ROLES:
            collected = self.facade("--project", str(target), "planveyor_runtime_py", "process_improvements_collect.py",
                "--role", role, "--source-ref", plan_ref,
                "--followups-capture-cycle-id", cycle, "--input", "-", "--json", input_text=text(role, cycle))
            self.assertIn(json.loads(collected.stdout)["state"], {"collected", "no_process_improvements"})
        capture.checkpoint_general_pi(target, plan_ref, cycle)
        for role in capture.REQUIRED_ROLES:
            capture.prepare_role(target, plan_ref, cycle, role)
            capture.finalize_role(target, plan_ref, cycle, role, b"NO FOLLOWUPS\nSummary: none\n")
        preview = self.facade("sibling", "close", cwd=target)
        self.assertIn("Документы готовы", preview.stdout)
        self.assertIn("Planveyor-Plan: " + plan_ref, preview.stdout)
        self.assertEqual(subprocess.run(["git", "-C", str(target), "diff", "--cached", "--name-only"],
                                        capture_output=True, text=True).stdout, "")
        committed = self.facade("sibling", "close", "--commit", cwd=target)
        self.assertIn("План и документы закрыты", committed.stdout)
        cold = self.facade("--project", str(target), "planveyor_docs_closeout", plan_ref,
                             "--followups-capture-cycle-id", cycle, "--json")
        payload = json.loads(cold.stdout)
        self.assertEqual(payload["state"], "completed")
        self.assertIn(payload["final_docs_commit"], {"no_op", "landed"})


if __name__ == "__main__":
    unittest.main()

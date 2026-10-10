"""Disposable public-facade and canonical Owner-answer regression tests."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import consumer_contract
import plan_status_oracle
import sibling_runbook as sibling


ROOT = Path(__file__).resolve().parent.parent


def run(argv, *, cwd=None, env=None, input_text=None, check=True):
    completed = subprocess.run(argv, cwd=cwd, env=env, text=True, input=input_text,
                               capture_output=True, timeout=120, check=False)
    if check and completed.returncode:
        raise AssertionError(f"{argv}: {completed.returncode}\n{completed.stdout}\n{completed.stderr}")
    return completed


def git(root, *args):
    return run(["git", "-C", os.fspath(root), "-c", "user.name=Fixture Owner",
                "-c", "user.email=fixture@example.invalid", *args]).stdout.strip()


class AnswerContext(sibling.Context):
    def require_project(self):
        pass

    def before_effect(self):
        pass

    def plan(self, reference=None):
        reference = self.literal_plan(reference or "docs/plans/261003_1200_answer.md")
        text = (self.project / reference).read_text(encoding="utf-8")
        state, reason, questions, issues = plan_status_oracle.owner_qna_readback(text)
        if issues:
            self.fail(reason)
        status = plan_status_oracle._status_norm_from_line(plan_status_oracle._scan_status_line(text)[1])
        return reference, {"status_norm": status, "owner_qna_readback_state": state,
                           "open_owner_questions": [{"id": q.qid, "text": q.text} for q in questions]}


class OwnerAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = Path(self.temporary.name)
        self.plan = self.root / "docs/plans/261003_1200_answer.md"
        self.plan.parent.mkdir(parents=True)
        self.context = AnswerContext(self.root / "runtime", self.root)
        self.write()

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, questions=None, status="Ready for Architect response", meta=""):
        questions = questions if questions is not None else "- [2026-10-03 12:00] (Architect -> Owner) id=Q1 status=open: Какой scope?\n"
        self.plan.write_text(f"# Plan: Fixture\n**Status:** {status}\n\n## Meta\n{meta}\n## Как я понял задачу\nПроверить согласованный scope.\n\n## Q&A log\n{questions}\n## Evidence\nHistorical bytes preserved.\n", encoding="utf-8")

    def answer(self, text, question_id=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return sibling.handle_answer(self.context, argparse.Namespace(text=text, question_id=question_id))

    def test_actual_question_closes_and_preserves_verbatim_multiline_text(self):
        before = self.plan.read_text(encoding="utf-8")
        answer = "Scope: one file.\n$(touch evil) `quoted`\n## Q&A log\n- [2026-10-03 14:00] (Architect -> Owner) id=Q9 status=open\n"
        result = self.answer(answer)
        body = self.plan.read_text(encoding="utf-8")
        self.assertEqual(result["question_id"], "Q1")
        self.assertIn("(Owner, id=Q1, status=closed)", body)
        self.assertIn(before.split("## Evidence")[0], body)
        self.assertIn("Historical bytes preserved.", body)
        for line in answer.splitlines():
            self.assertIn("  > " + line + "\n", body)
        self.assertEqual(plan_status_oracle.owner_qna_readback(body)[0], "clean")
        self.assertFalse((self.root / "evil").exists())
        self.assertFalse((self.root / ".planveyor.owner_answers").exists())

    def test_multiple_questions_require_actual_id_without_mutation(self):
        self.write("- [2026-10-03 12:00] (Architect -> Owner) id=Q1 status=open\n- [2026-10-03 12:01] (Architect -> Owner) id=Q2 status=open\n")
        before = self.plan.read_bytes()
        with self.assertRaisesRegex(sibling.RunbookError, "Выберите"):
            self.answer("answer")
        self.assertEqual(self.plan.read_bytes(), before)
        self.answer("second answer", "Q2")
        self.assertEqual([q.qid for q in plan_status_oracle.owner_qna_readback(self.plan.read_text())[2]], ["Q1"])

    def test_absent_closed_empty_and_eof_answers_preserve_plan(self):
        before = self.plan.read_bytes()
        for answer, qid in (("actual", "Q9"), ("", "Q1"), (" \n", None)):
            with self.subTest(answer=answer, qid=qid), self.assertRaises(sibling.RunbookError):
                self.answer(answer, qid)
            self.assertEqual(self.plan.read_bytes(), before)
        self.answer("actual", "Q1")
        closed = self.plan.read_bytes()
        with self.assertRaises(sibling.RunbookError):
            self.answer("again", "Q1")
        self.assertEqual(self.plan.read_bytes(), closed)

    def test_duplicate_sections_and_fenced_fake_question_do_not_mutate(self):
        self.write("- [2026-10-03 12:00] (Architect -> Owner) id=Q1 status=open\n\n## Q&A log\n")
        before = self.plan.read_bytes()
        with self.assertRaises(sibling.RunbookError):
            self.answer("actual")
        self.assertEqual(self.plan.read_bytes(), before)
        self.write("```text\n- [2026-10-03 12:00] (Architect -> Owner) id=Q8 status=open\n```\n")
        before = self.plan.read_bytes()
        with self.assertRaises(sibling.RunbookError):
            self.answer("actual", "Q8")
        self.assertEqual(self.plan.read_bytes(), before)

    def test_initial_answer_preserves_pending_payload(self):
        self.write(status="Architect initial draft")
        payload = self.root / ".planveyor.owner_answers"
        payload.write_text("TO=coder\nPLAN_PATH=other.md\n---\nExisting decision.\n")
        before = self.plan.read_bytes()
        with self.assertRaisesRegex(sibling.RunbookError, "payload"):
            self.answer("new decision")
        self.assertEqual(payload.read_text(), "TO=coder\nPLAN_PATH=other.md\n---\nExisting decision.\n")
        self.assertEqual(self.plan.read_bytes(), before)

    def test_initial_native_confirmation_does_not_invent_qid_or_status(self):
        self.write(questions="", status="Architect initial draft")
        before = self.plan.read_bytes()
        answer = "OK: confirm moving plan to **Status:** Architect draft"
        result = self.answer(answer)
        self.assertIsNone(result["question_id"])
        self.assertEqual(self.plan.read_bytes(), before)
        self.assertIn(answer, (self.root / ".planveyor.owner_answers").read_text())

    def test_machine_authority_question_only_delivers_native_payload(self):
        self.write(meta='```json\n{"plan_meta":{"machine_authority_decision":{"confirmation":{"question_ref":"Q1"}}}}\n```')
        before = self.plan.read_bytes()
        self.answer("Owner actual decision")
        self.assertEqual(self.plan.read_bytes(), before)
        self.assertEqual(plan_status_oracle.owner_qna_readback(self.plan.read_text())[0], "open")
        self.assertIn("Owner actual decision", (self.root / ".planveyor.owner_answers").read_text())

    def test_drift_during_input_refuses_without_overwriting_new_bytes(self):
        original = self.context.before_effect
        def drift():
            original()
            with self.plan.open("a") as handle:
                handle.write("Concurrent evidence.\n")
        self.context.before_effect = drift
        with self.assertRaisesRegex(sibling.RunbookError, "изменился"):
            self.answer("actual")
        self.assertIn("Concurrent evidence.", self.plan.read_text())
        self.assertEqual(plan_status_oracle.owner_qna_readback(self.plan.read_text())[0], "open")

    def test_literal_selector_refuses_missing_template_escape_and_symlink(self):
        (self.plan.parent / "link.md").symlink_to(self.plan)
        for reference in ("docs/plans/missing.md", "docs/plans/_template.md", "docs/plans/../plans/261003_1200_answer.md", "docs/plans/link.md", "/outside.md"):
            with self.subTest(reference=reference), self.assertRaises(sibling.RunbookError):
                self.context.literal_plan(reference)

    def test_init_identity_reads_global_config_and_ignores_repo_local_author(self):
        home = self.root / "fixture-home"
        home.mkdir()
        (home / ".gitconfig").write_text("[user]\n name = Real Global Owner\n email = real-global@example.invalid\n")
        git(self.root, "init", "--quiet")
        git(self.root, "config", "user.name", "Unrelated Local Owner")
        git(self.root, "config", "user.email", "local-only@example.invalid")
        with mock.patch.dict(os.environ, {"HOME": os.fspath(home)}):
            self.assertEqual(sibling.init_identity(self.context, None, None),
                             ("Real Global Owner", "real-global@example.invalid"))

    def test_ready_accepts_explicit_existing_cycle_selector(self):
        args = sibling.parser().parse_args(["--runtime-root", os.fspath(self.root / "runtime"),
                                            "--project-root", os.fspath(self.root), "ready", "--cycle",
                                            "11111111-1111-4111-8111-111111111111"])
        self.assertEqual(args.cycle, "11111111-1111-4111-8111-111111111111")

    def test_actual_authority_error_has_reason_code_and_no_answer_writes(self):
        from contract_authority_snapshot import parse_context_envelope
        # Use the real authority parser and exception, rather than a generic
        # RuntimeError or a fabricated CLI diagnostic.
        self.context.before_effect = lambda: parse_context_envelope("{}")
        original = self.plan.read_bytes()
        stderr = io.StringIO()
        with mock.patch.object(sibling, "Context", return_value=self.context), \
                mock.patch.object(sibling, "atomic_write") as writer, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            result = sibling.main(["--runtime-root", os.fspath(self.root / "runtime"),
                                   "--project-root", os.fspath(self.root),
                                   "answer", "Q1", "--text", "Actual Owner decision"])
        self.assertEqual(result, 3)
        self.assertIn("planveyor sibling: context_envelope_schema_invalid:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        writer.assert_not_called()
        self.assertEqual(self.plan.read_bytes(), original)
        self.assertFalse((self.root / ".planveyor.owner_answers").exists())


class PublicSiblingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sibling-public-", dir=Path(tempfile.gettempdir()).resolve())
        cls.root = Path(cls.temporary.name)
        cls.runtime = cls.root / "runtime"
        cls.outside = cls.root / "outside"
        cls.outside.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        cls.env.update(HOME=os.fspath(cls.home), PATH=os.fspath(Path(sys.executable).parent) + os.pathsep + cls.env.get("PATH", ""))
        run(["git", "clone", "--quiet", "--no-local", os.fspath(ROOT), os.fspath(cls.runtime)], env=cls.env)
        changed = git(ROOT, "diff", "--name-only", "--diff-filter=AM").splitlines()
        additions = ["scripts/sibling_runbook.py", "scripts/sibling_closeout.py"]
        additions += [os.fspath(path.relative_to(ROOT)) for path in (ROOT / "docs/contract_notices").glob("*human*sibling*.json")]
        for relative in dict.fromkeys(changed + additions):
            source = ROOT / relative
            if source.is_file():
                destination = cls.runtime / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        # Provider-free native receipts still pass the real retained bridge
        # checker. The fixture replaces only the two live Architect sinks.
        facade_path = cls.runtime / "scripts/planveyor.zsh"
        fixture_adapter = '''
_planveyor_codex_session_stats_script() { print -r -- "$PLANVEYOR_RUNTIME_ROOT/scripts/sibling_fixture_stats.py"; }
planveyor_arch_init() {
  _planveyor_py_any - "$PLANVEYOR_CTX_JSON" "$PLANVEYOR_CTX_ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[2])
sid = "11111111-1111-4111-8111-111111111111"
receipt = root / ".planveyor.init_runs/by_sid" / sid / "meta.json"
receipt.parent.mkdir(parents=True, exist_ok=True)
receipt.write_text(json.dumps({"outcome":"success","sid":sid,"session_key":"architect","authority_context":json.loads(sys.argv[1])}))
(root / ".planveyor.session.architect").write_text(sid + "\\n")
with (root / ".fixture_init_calls").open("a") as handle: handle.write("architect\\n")
PY
}
planveyor_arch_initial() { print initial >> "$PLANVEYOR_CTX_ROOT/.fixture_role_calls"; }
planveyor_arch() { print status-driven >> "$PLANVEYOR_CTX_ROOT/.fixture_role_calls"; }
'''
        if getattr(cls, "actual_native_policy_sink", False):
            # Keep actual bootstrap/resume producers and their real receipts;
            # replace only the live native boundary, recording argv and stdin.
            fixture_adapter = NATIVE_POLICY_FIXTURE_ADAPTER
            (cls.runtime / "scripts/sibling_fixture_native.py").write_text(NATIVE_POLICY_FIXTURE_PROGRAM)
        facade_path.write_text(facade_path.read_text().replace(
            "_planveyor_authority_finalize_loaded_source || return $?", fixture_adapter + "\n_planveyor_authority_finalize_loaded_source || return $?"))
        (cls.runtime / "scripts/sibling_fixture_stats.py").write_text("print('sid=fixture')\n")
        with (cls.runtime / "copier_template/.gitignore.jinja").open("a") as handle:
            handle.write("\n.fixture_init_calls\n.fixture_role_calls\n")
            if getattr(cls, "actual_native_policy_sink", False):
                handle.write(".fixture_native_calls\n")
        git(cls.runtime, "add", "--all")
        git(cls.runtime, "commit", "--quiet", "-m", "Disposable human sibling command fixture")
        cls.seed = cls.root / "seed"
        initialized = cls.facade("sibling", "init", os.fspath(cls.seed), "--author-name", "Actual Fixture Owner", "--author-email", "actual-fixture@example.invalid")
        if "Sibling создан" not in initialized.stdout:
            raise AssertionError(initialized.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def facade(cls, *args, cwd=None, input_text=None, check=True):
        return run([os.fspath(cls.runtime / "bin/planveyor"), *args], cwd=cwd or cls.outside,
                   env=cls.env, input_text=input_text, check=check)

    def target(self, name):
        target = self.root / name
        shutil.copytree(self.seed, target)
        return target

    def write_plan(self, target):
        reference = "docs/plans/261003_1200_public.md"
        (target / reference).write_text("# Plan: Public\n**Status:** Architect initial draft\n\n## Как я понял задачу\nBounded fixture task.\n\n## Q&A log\n- [2026-10-03 12:00] (Architect -> Owner) id=Q1 status=open: Actual question.\n", encoding="utf-8")
        return reference

    def test_init_from_non_git_cwd_commits_and_saves_actual_local_identity(self):
        target = self.seed
        self.assertEqual(git(target, "log", "-1", "--format=%an|%ae|%cn|%ce"),
                         "Actual Fixture Owner|actual-fixture@example.invalid|Actual Fixture Owner|actual-fixture@example.invalid")
        self.assertEqual(git(target, "config", "--local", "--get", "user.name"), "Actual Fixture Owner")
        self.assertEqual(git(target, "config", "--local", "--get", "user.email"), "actual-fixture@example.invalid")
        doctor = self.facade("--project", os.fspath(target), "planveyor_consumer_doctor")
        self.assertEqual(json.loads(doctor.stdout)["state"], "ok")
        self.assertEqual(git(target, "status", "--porcelain=v1"), "")

    def test_help_is_available_without_project_and_has_no_effects(self):
        before = git(self.seed, "status", "--porcelain=v1")
        for args in (("sibling", "--help"), ("sibling", "run", "--help"), ("sibling", "close", "--help"), ("help", "sibling")):
            with self.subTest(args=args):
                result = self.facade(*args)
                self.assertIn("usage:", result.stdout)
        self.assertEqual(git(self.seed, "status", "--porcelain=v1"), before)
        self.assertFalse((self.seed / ".planveyor.session.manager").exists())

    def test_plan_infers_project_from_nested_cwd_and_validates_before_pointer_write(self):
        target = self.target("plan-inference")
        reference = self.write_plan(target)
        nested = target / "docs/plans"
        result = self.facade("sibling", "plan", reference, cwd=nested)
        self.assertIn(reference, result.stdout)
        pointer = (target / ".planveyor.planpath").read_bytes()
        rejected = self.facade("sibling", "plan", "docs/plans/missing.md", cwd=nested, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((target / ".planveyor.planpath").read_bytes(), pointer)
        status = self.facade("sibling", "plan", cwd=nested)
        self.assertIn("Q1", status.stdout)

    def test_ambiguous_or_symlink_pointer_is_not_a_plan_selector(self):
        target = self.target("ambiguous-pointer")
        reference = self.write_plan(target)
        pointer = target / ".planveyor.planpath"
        pointer.write_text(reference + "\n" + reference + "\n")
        result = self.facade("sibling", "plan", cwd=target, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("неоднозначен", result.stderr)
        pointer.unlink()
        foreign = self.root / "foreign-pointer"
        foreign.write_text(reference + "\n")
        pointer.symlink_to(foreign)
        result = self.facade("sibling", "plan", cwd=target, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(foreign.read_text(), reference + "\n")

    def test_answer_through_attested_facade_serializes_actual_question(self):
        target = self.target("public-answer")
        reference = self.write_plan(target)
        self.facade("--project", os.fspath(target), "sibling", "plan", reference)
        result = self.facade("sibling", "answer", cwd=target, input_text="Actual Owner decision\n")
        self.assertIn("Ответ сохранён", result.stdout)
        state = plan_status_oracle.owner_qna_readback((target / reference).read_text())[0]
        self.assertEqual(state, "clean")
        self.assertIn("Actual Owner decision", (target / ".planveyor.owner_answers").read_text())

    def test_missing_identity_does_not_create_target_or_candidate(self):
        target = self.root / "no-identity"
        result = self.facade("sibling", "init", os.fspath(target), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identity", result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".no-identity-init-*")), [])

    def test_init_does_not_use_unrelated_repository_local_identity(self):
        elsewhere = self.root / "unrelated"
        elsewhere.mkdir()
        git(elsewhere, "init", "--quiet")
        git(elsewhere, "config", "user.name", "Unrelated Repo Owner")
        git(elsewhere, "config", "user.email", "unrelated@example.invalid")
        target = self.root / "wrong-identity"
        result = self.facade("sibling", "init", os.fspath(target), cwd=elsewhere, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_upgrade_inside_target_refuses_before_any_swap(self):
        target = self.target("upgrade-cwd")
        before = git(target, "rev-parse", "HEAD")
        result = self.facade("sibling", "upgrade", cwd=target / "docs", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Выйдите", result.stderr)
        self.assertEqual(git(target, "rev-parse", "HEAD"), before)
        self.assertEqual(list(self.root.glob(".upgrade-cwd-before-*")), [])

    def test_wrong_project_and_late_project_flag_do_not_start_roles(self):
        for arguments, cwd in ((("sibling", "run"), self.runtime), (("sibling", "run"), self.outside),
                                (("--project", os.fspath(self.seed), "sibling", "run", "--project", os.fspath(self.seed)), self.outside)):
            with self.subTest(arguments=arguments):
                result = self.facade(*arguments, cwd=cwd, check=False)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.seed / ".planveyor.session.manager").exists())

    def test_reserved_context_selectors_refuse_without_other_project_effects(self):
        target = self.target("reserved-context")
        reference = self.write_plan(target)
        other = self.target("context-other")
        for selector in ("--runtime-root", "--project-root", "--invocation-root"):
            result = self.facade("--project", os.fspath(target), "sibling", selector,
                                 os.fspath(other), "plan", reference, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reserved", result.stderr)
        self.assertFalse((target / ".planveyor.planpath").exists())
        self.assertFalse((other / ".planveyor.planpath").exists())

    def test_architect_wrong_status_refuses_before_native_init(self):
        target = self.target("wrong-role-status")
        reference = self.write_plan(target)
        path = target / reference
        path.write_text(path.read_text().replace("Architect initial draft", "Ready for Coder"))
        self.facade("--project", os.fspath(target), "sibling", "plan", reference)
        result = self.facade("sibling", "architect", cwd=target, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((target / ".fixture_init_calls").exists())
        self.assertFalse((target / ".planveyor.session.architect").exists())

    def test_native_receipt_missing_stale_and_invalid_use_canonical_checker(self):
        target = self.target("native-receipt")
        reference = self.write_plan(target)
        self.facade("--project", os.fspath(target), "sibling", "plan", reference)
        self.facade("sibling", "architect", cwd=target)
        self.facade("sibling", "architect", cwd=target)
        calls = target / ".fixture_init_calls"
        self.assertEqual(calls.read_text().splitlines(), ["architect"])
        receipt_path = target / ".planveyor.init_runs/by_sid/11111111-1111-4111-8111-111111111111/meta.json"
        # A valid same-root receipt becomes stale when the current contract's
        # entry HEAD/tree changes; no home migration or alternative model.
        git(target, "add", "--", reference)
        git(target, "commit", "--quiet", "-m", "Native receipt fixture plan")
        self.facade("sibling", "architect", cwd=target)
        self.assertEqual(calls.read_text().splitlines(), ["architect", "architect"])
        receipt = json.loads(receipt_path.read_text())
        receipt["session_key"] = "coder"
        receipt_path.write_text(json.dumps(receipt))
        before = calls.read_bytes()
        rejected = self.facade("sibling", "architect", cwd=target, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("bind", rejected.stderr)
        self.assertEqual(calls.read_bytes(), before)

    def test_literal_help_answer_is_recorded_as_actual_text(self):
        target = self.target("help-text")
        reference = self.write_plan(target)
        self.facade("--project", os.fspath(target), "sibling", "plan", reference)
        result = self.facade("sibling", "answer", "Q1", "--text", "help", cwd=target)
        self.assertIn("Ответ сохранён", result.stdout)
        self.assertIn("  > help\n", (target / reference).read_text())

    def test_upgrade_from_outside_preserves_local_sections_and_selects_returned_plan(self):
        target = self.target("outside-upgrade")
        relative = "docs/playbooks/review_staged_or_commit.md"
        local = target / relative
        heading = consumer_contract.LOCAL_HEADINGS[0] + "\n"
        old = local.read_text()
        start = old.index(heading) + len(heading)
        end = old.find("\n## ", start)
        end = len(old) if end < 0 else end
        preserved = "Fixture stack rule: preserve the actual local bytes.\n"
        local.write_text(old[:start] + preserved + old[end:])
        git(target, "add", "--", relative)
        git(target, "commit", "--quiet", "-m", "Fixture local stack rule")
        notice = self.runtime / "docs/contract_notices/fixture-human-update.json"
        notice.write_text(json.dumps({"summary":"Fixture runtime update", "contract_changes":[],
                                     "engine_changes":["Fixture source increment"], "sibling_actions":["Review adaptation"],
                                     "checks":["Consumer doctor"]}))
        git(self.runtime, "add", "--", os.fspath(notice.relative_to(self.runtime)))
        git(self.runtime, "commit", "--quiet", "-m", "Disposable source update")
        try:
            result = self.facade("--project", os.fspath(target), "sibling", "upgrade")
            self.assertIn("адаптация ещё открыта", result.stdout)
            self.assertIn(preserved, (target / relative).read_text())
            pointer = self.facade("--project", os.fspath(target), "planveyor_planpath").stdout.strip()
            self.assertIn("contract_upgrade_", pointer)
            self.assertTrue((target / pointer).is_file())
            self.assertEqual(plan_status_oracle._status_norm_from_line(plan_status_oracle._scan_status_line((target / pointer).read_text())[1]), "architect initial draft")
            self.assertEqual(len(list(self.root.glob(".outside-upgrade-before-*"))), 1)
        finally:
            # Other tests continue using the originally delivered runtime pin.
            git(self.runtime, "reset", "--hard", "HEAD~1")


NATIVE_POLICY_FIXTURE_ADAPTER = '''
_planveyor_codex_session_stats_script() { print -r -- "$PLANVEYOR_RUNTIME_ROOT/scripts/sibling_fixture_stats.py"; }
_planveyor_codex() { _planveyor_py_any "$PLANVEYOR_RUNTIME_ROOT/scripts/sibling_fixture_native.py" "$@"; }
'''

NATIVE_POLICY_FIXTURE_PROGRAM = '''import json, pathlib, re, sys
argv = sys.argv[1:]
stdin = sys.stdin.read() if argv and argv[-1] == "-" else ""
payload = stdin if argv and argv[-1] == "-" else argv[-1]
header = payload.split("[ALWAYS START]", 1)[0]
role = re.search(r"^ROLE=(Architect|Manager)$", header, re.MULTILINE).group(1)
with (pathlib.Path.cwd() / ".fixture_native_calls").open("a") as stream:
    stream.write(json.dumps({"argv": argv, "stdin": stdin, "payload": payload, "role": role}) + "\\n")
sid = {"Architect": "11111111-1111-4111-8111-111111111111", "Manager": "22222222-2222-4222-8222-222222222222"}[role]
print("session id: " + sid)
'''


class NativeSiblingCommitPolicyTests(unittest.TestCase):
    """Exercise real init/resume producers through the existing public fixture."""
    actual_native_policy_sink = True
    setUpClass = PublicSiblingTests.__dict__["setUpClass"]
    tearDownClass = PublicSiblingTests.__dict__["tearDownClass"]
    facade = PublicSiblingTests.__dict__["facade"]
    target = PublicSiblingTests.target
    write_plan = PublicSiblingTests.write_plan

    def events(self, target):
        path = target / ".fixture_native_calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def selected(self, name, *, status="Architect initial draft"):
        target = self.target(name)
        reference = self.write_plan(target)
        path = target / reference
        body = path.read_text().replace("Architect initial draft", status)
        if status == "Blocked":
            # Exercise real Manager admission with an explicit allowed mode.
            body += "\n```json\n" + json.dumps({"plan_meta": {"cluster": "process", "required_manager_mode": "manager-collab"}}) + "\n```\n"
        path.write_text(body)
        self.facade("--project", os.fspath(target), "sibling", "plan", reference)
        return target, reference

    def assert_policy(self, event, expected):
        header = event["payload"].split("[ALWAYS START]", 1)[0]
        self.assertEqual([line for line in header.splitlines() if line.startswith("COMMIT_POLICY=")],
                         ["COMMIT_POLICY=" + expected])

    def test_actual_architect_cold_init_and_reused_resume_get_current_human_policy(self):
        target, reference = self.selected("policy-architect")
        self.facade("sibling", "architect", cwd=target)
        self.facade("sibling", "architect", cwd=target)
        plan = target / reference
        plan.write_text(plan.read_text().replace("Architect initial draft", "Architect arch review"))
        self.facade("sibling", "architect", cwd=target)
        events = self.events(target)
        self.assertEqual(len(events), 4, events)
        self.assertTrue(all(event["role"] == "Architect" for event in events))
        self.assertNotIn("resume", events[0]["argv"])
        for event in events:
            self.assert_policy(event, "human_explicit")
        for event in events[1:]:
            self.assertIn("resume", event["argv"])
            self.assertIn("PLAN_PATH=" + reference, event["payload"])
            self.assertEqual(event["argv"][-1], "-")
        for event in events[1:3]:
            self.assertRegex(event["payload"], r"(?m)^PRE_STATUS_LINE=\d+:\*\*Status:\*\* Architect initial draft$")
        self.assertRegex(events[-1]["payload"], r"(?m)^PRE_STATUS_LINE=\d+:\*\*Status:\*\* Architect arch review$")
        self.assertIn("[E_ARCH_REVIEW]", events[-1]["payload"])
        receipt = target / ".planveyor.init_runs/by_sid/11111111-1111-4111-8111-111111111111/meta.json"
        self.assertEqual(json.loads(receipt.read_text())["session_key"], "architect")

    def test_actual_manager_bootstrap_resume_and_explicit_cycle_keep_current_policy(self):
        target, reference = self.selected("policy-manager", status="Blocked")
        cycle = "33333333-3333-4333-8333-333333333333"
        self.facade("sibling", "run", cwd=target)
        self.facade("sibling", "run", "--followups-capture-cycle-id", cycle, cwd=target)
        events = self.events(target)
        self.assertEqual(len(events), 3, events)
        self.assertTrue(all(event["role"] == "Manager" for event in events))
        self.assertNotIn("resume", events[0]["argv"])
        for event in events:
            self.assert_policy(event, "human_explicit")
        for event in events[1:]:
            self.assertIn("resume", event["argv"])
            self.assertIn("PLAN_PATH=" + reference, event["payload"])
            self.assertEqual(event["payload"].rstrip().splitlines()[-1], "MANAGER_CMD=run " + reference)
        self.assertIn("FOLLOWUPS_CAPTURE_CYCLE_ID=" + cycle, events[-1]["payload"])
        self.assertNotIn("FOLLOWUPS_CAPTURE_CYCLE_ID=", events[1]["payload"])

    def test_direct_native_after_human_call_ignores_ambient_selector_and_history(self):
        target, _ = self.selected("policy-direct")
        self.facade("sibling", "architect", cwd=target)
        first = self.events(target)
        self.assertEqual(len(first), 2)
        for event in first:
            self.assert_policy(event, "human_explicit")
        direct_env = dict(self.env, PLANVEYOR_SIBLING_COMMIT_POLICY="human_explicit")
        result = run([os.fspath(self.runtime / "bin/planveyor"), "--project", os.fspath(target), "planveyor_arch"], cwd=target, env=direct_env)
        self.assertEqual(result.returncode, 0)
        events = self.events(target)
        self.assertEqual(len(events), 3)
        self.assert_policy(events[-1], "native_existing")
        self.assertIn("resume", events[-1]["argv"])
        self.assertEqual(git(target, "diff", "--cached", "--name-only"), "")

    def test_direct_manager_resume_after_human_run_uses_fresh_native_policy(self):
        target, reference = self.selected("policy-direct-manager-resume", status="Blocked")
        self.facade("sibling", "run", cwd=target)
        first = self.events(target)
        self.assertEqual(len(first), 2, first)
        for event in first:
            self.assert_policy(event, "human_explicit")
        direct_env = dict(self.env, PLANVEYOR_SIBLING_COMMIT_POLICY="human_explicit")
        run([os.fspath(self.runtime / "bin/planveyor"), "--project", os.fspath(target), "planveyor_manager_collab_cmd", "run", reference],
            cwd=target, env=direct_env)
        events = self.events(target)
        self.assertEqual(len(events), 3, events)
        self.assert_policy(events[-1], "native_existing")
        self.assertIn("resume", events[-1]["argv"])
        self.assertEqual(events[-1]["argv"][events[-1]["argv"].index("resume") + 1],
                         first[-1]["argv"][first[-1]["argv"].index("resume") + 1])
        self.assertIn("PLAN_PATH=" + reference, events[-1]["payload"])
        self.assertEqual(events[-1]["payload"].rstrip().splitlines()[-1], "MANAGER_CMD=run " + reference)
        self.assertFalse((target / ".planveyor.planqueue.json").exists())

    def test_ambient_selector_does_not_supply_direct_manager_bootstrap_authority(self):
        for index, value in enumerate(("human_explicit", "", "unknown")):
            with self.subTest(value=value):
                # Each cold bootstrap owns a fresh target and init receipt.
                target, _ = self.selected("policy-direct-manager-" + str(index), status="Blocked")
                direct_env = dict(self.env, PLANVEYOR_SIBLING_COMMIT_POLICY=value)
                run([os.fspath(self.runtime / "bin/planveyor"), "--project", os.fspath(target), "planveyor_manager_init"], cwd=target, env=direct_env)
                self.assert_policy(self.events(target)[-1], "native_existing")

    def test_missing_mutable_and_invalid_sibling_selectors_refuse_before_child_or_answers(self):
        original = "    local -r +x PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit || return 3\n"
        variants = {
            "missing": "",
            "mutable": "    local +x PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit\n",
            "invalid": "    local -r +x PLANVEYOR_SIBLING_COMMIT_POLICY=invalid || return 3\n",
        }
        self.assertEqual(git(self.runtime, "status", "--porcelain=v1"), "")
        for name, replacement in variants.items():
            with self.subTest(name=name):
                runtime = self.root / ("policy-invalid-runtime-" + name)
                shutil.copytree(self.runtime, runtime)
                source = runtime / "scripts/planveyor.zsh"
                body = source.read_text()
                self.assertEqual(body.count(original), 1)
                source.write_text(body.replace(original, replacement, 1))
                git(runtime, "add", "--", "scripts/planveyor.zsh")
                git(runtime, "commit", "--quiet", "-m", "Disposable invalid scope fixture")
                target = self.root / ("policy-invalid-target-" + name)
                command = [os.fspath(runtime / "bin/planveyor")]
                run(command + ["sibling", "init", os.fspath(target), "--author-name", "Fixture Owner",
                               "--author-email", "fixture@example.invalid"], cwd=self.outside, env=self.env)
                reference = self.write_plan(target)
                run(command + ["--project", os.fspath(target), "sibling", "plan", reference], cwd=self.outside, env=self.env)
                answers = target / ".planveyor.owner_answers"
                answers.write_text("TO=architect\nPLAN_PATH=" + reference + "\n---\nActual pending decision.\n")
                before = answers.read_bytes(), (target / reference).read_bytes(), git(target, "rev-parse", "HEAD"), (target / ".git/index").read_bytes()
                result = run(command + ["sibling", "architect"], cwd=target, env=self.env, check=False)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("invalid invocation commit policy", result.stderr)
                self.assertEqual((answers.read_bytes(), (target / reference).read_bytes(), git(target, "rev-parse", "HEAD"), (target / ".git/index").read_bytes()), before)
                self.assertEqual(self.events(target), [])
                self.assertFalse((target / ".planveyor.session.architect").exists())


    def test_role_prompt_body_invalid_sibling_frame_returns_3_before_prompt_file_and_header(self):
        from test_contract_authority_support import shell_loader_literal

        target, reference = self.selected("policy-prompt-backstop")
        answers = target / ".planveyor.owner_answers"
        answers.write_text("TO=architect\nPLAN_PATH=" + reference + "\n---\nActual pending decision.\n")

        def inventory():
            return {
                os.fspath(path.relative_to(target)): (
                    path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns
                )
                for path in target.rglob("*") if path.is_file()
            }

        before = inventory()
        environment = dict(self.env, PLANVEYOR_RUNTIME_ROOT=os.fspath(self.runtime))
        environment.pop("PLANVEYOR_SIBLING_COMMIT_POLICY", None)
        prefix = shell_loader_literal(self.runtime) + r'''
planveyor_source_runtime "$1" || exit $?
typeset -r policy_effects="$2"
functions -c _planveyor_normalize_role_id _fixture_policy_normalize_original || exit $?
functions -c _planveyor_prompt_file_for_role_phase _fixture_policy_prompt_original || exit $?
_planveyor_normalize_role_id() {
  print -r -- normalize >> "$policy_effects"
  _fixture_policy_normalize_original "$@"
}
_planveyor_prompt_file_for_role_phase() {
  print -r -- prompt-file >> "$policy_effects"
  _fixture_policy_prompt_original "$@"
}
'''
        variants = {
            "missing": "",
            "mutable": "local +x PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit;",
            "invalid": "local -r +x PLANVEYOR_SIBLING_COMMIT_POLICY=invalid;",
        }
        for name, declaration in variants.items():
            with self.subTest(name=name):
                effects = self.root / ("policy-prompt-effects-" + name)
                command = prefix + "planveyor_sibling() { " + declaration + (
                    " _planveyor_role_prompt_body architect init; }; planveyor_sibling"
                )
                result = run(["/bin/zsh", "-fc", command, "policy-backstop",
                              os.fspath(self.runtime / "scripts/planveyor.zsh"), os.fspath(effects)],
                             cwd=target, env=environment, check=False)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn("invalid invocation commit policy", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(effects.exists())
                self.assertEqual(self.events(target), [])
                self.assertEqual(inventory(), before)
                self.assertFalse((target / ".planveyor.session.architect").exists())

        for name, call, policy in (
            ("valid-human", "planveyor_sibling() { local -r +x PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit; "
             "_planveyor_role_prompt_body architect init; }; planveyor_sibling", "human_explicit"),
            ("ambient-native", "export PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit; "
             "_planveyor_role_prompt_body architect init", "native_existing"),
        ):
            with self.subTest(name=name):
                effects = self.root / ("policy-prompt-effects-" + name)
                result = run(["/bin/zsh", "-fc", prefix + call, "policy-backstop",
                              os.fspath(self.runtime / "scripts/planveyor.zsh"), os.fspath(effects)],
                             cwd=target, env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines()[0], "COMMIT_POLICY=" + policy)
                self.assertIn("PLANVEYOR_RUNTIME_ROOT=" + os.fspath(self.runtime), result.stdout)
                self.assertIn("[ALWAYS START]", result.stdout)
                self.assertIn("normalize", effects.read_text().splitlines())
                self.assertIn("prompt-file", effects.read_text().splitlines())
                self.assertEqual(self.events(target), [])
                self.assertEqual(inventory(), before)


if __name__ == "__main__":
    unittest.main()

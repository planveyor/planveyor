#!/usr/bin/env python3
"""Human commands that present the existing Planveyor sibling workflow."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import consumer_contract
import plan_status_oracle
from contract_authority_snapshot import ContractAuthorityError


class RunbookError(RuntimeError):
    pass


class Context:
    def __init__(self, runtime: Path, project: Path, invocation: Path | None = None):
        self.runtime = runtime
        self.project = project
        self.invocation = invocation or project
        self.facade = runtime / "bin/planveyor"

    def fail(self, message: str):
        raise RunbookError(message)

    def call(self, command: str, *arguments: str, capture: bool = True,
             input_text: str | None = None, check: bool = True,
             project: Path | None = None) -> subprocess.CompletedProcess[str]:
        # Every short-lived facade child gets a fresh attested runtime and a
        # literal project. The original upgrade caller must remain outside it.
        done = subprocess.run(
            [os.fspath(self.facade), "--project", os.fspath(project or self.project), command, *arguments],
            cwd=self.runtime, text=True, capture_output=capture, input=input_text,
            check=False,
        )
        if check and done.returncode:
            self.fail((done.stderr or done.stdout or f"Команда {command} завершилась с кодом {done.returncode}.").strip())
        return done

    def json_call(self, command: str, *arguments: str, **options) -> dict:
        done = self.call(command, *arguments, **options)
        try:
            value = json.loads(done.stdout)
        except (ValueError, TypeError):
            self.fail(f"Команда {command} не вернула корректный readback.")
        if not isinstance(value, dict):
            self.fail(f"Команда {command} вернула неоднозначный readback.")
        return value

    def git(self, *arguments: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        done = subprocess.run(["git", "-C", os.fspath(root or self.project), *arguments],
                              text=True, capture_output=True, env=env, check=False)
        if done.returncode:
            self.fail(done.stderr.strip() or "Git не смог прочитать выбранный checkout.")
        return done

    def require_project(self) -> None:
        if self.project == self.runtime:
            self.fail("Войдите в sibling checkout или задайте --project.")
        try:
            consumer_contract.canonical_external(os.fspath(self.project), self.runtime, must_exist=True)
            consumer_contract.ensure_git_root(self.project)
            consumer_contract.marker_answers(self.project, self.runtime)
        except consumer_contract.ContractError as exc:
            self.fail(str(exc))

    def literal_plan(self, reference: str) -> str:
        if not reference or any(character in reference for character in "\x00\r\n"):
            self.fail("Укажите один существующий plan в docs/plans.")
        path = Path(reference)
        if path.is_absolute():
            try:
                reference = os.fspath(path.relative_to(self.project))
            except ValueError:
                self.fail("Plan находится за пределами выбранного sibling.")
        parts = reference.split("/")
        if (parts[:2] != ["docs", "plans"] or any(part in {"", ".", ".."} for part in parts)
                or not reference.endswith(".md") or parts[-1].startswith("_")):
            self.fail("Выберите literal plan docs/plans/NAME.md; шаблон и обход пути недопустимы.")
        selected, _, error = consumer_contract.selected_path(self.project, reference)
        if error or selected is None:
            self.fail("Plan отсутствует, недоступен или содержит symlink.")
        return reference

    def plan(self, reference: str | None = None) -> tuple[str, dict]:
        self.require_project()
        if reference is None:
            pointer, metadata, error = consumer_contract.selected_path(self.project, ".planveyor.planpath")
            if error or pointer is None or metadata is None:
                self.fail("Текущий plan не выбран или pointer повреждён. Выполните planveyor sibling plan docs/plans/NAME.md.")
            body, error = consumer_contract.read_selected_file(pointer, metadata)
            if error or body is None:
                self.fail("Не удалось прочитать current plan pointer.")
            try:
                selected = [line for line in body.decode("utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
            except UnicodeDecodeError:
                self.fail("Current plan pointer не является UTF-8.")
            if len(selected) != 1:
                self.fail("Current plan pointer неоднозначен; выберите один plan явно.")
            done = self.call("planveyor_planpath", check=False)
            if done.returncode:
                self.fail("Текущий plan не выбран. Выполните planveyor sibling plan docs/plans/NAME.md.")
            reference = done.stdout.strip()
            if reference != selected[0]:
                self.fail("Current plan pointer изменился при чтении; повторите команду.")
        reference = self.literal_plan(reference)
        oracle = self.json_call("planveyor_plan_status_oracle", "--json", "--current-state", reference)
        if not isinstance(oracle.get("status_norm"), str) or not oracle["status_norm"]:
            self.fail("Oracle не подтверждает единственный status выбранного plan.")
        if oracle.get("owner_qna_readback_state") == "blocked":
            self.fail("Canonical Q&A повреждён: " + str(oracle.get("owner_qna_readback_reason", "blocked")))
        return reference, oracle

    def before_effect(self) -> None:
        from contract_authority_context import context_for_reader, validate_before_effect
        validate_before_effect(context_for_reader(self.project))

    def set_status(self, plan: str, status: str) -> None:
        if status != "Done":
            self.fail("Удобная команда не изменяет этот status.")
        self.call("sibling", "--internal", "set-done", self.literal_plan(plan))

    def run_native_session(self, role: str, plan: str, arguments: list[str]):
        if role != "manager" or arguments[:2] != ["run", plan]:
            self.fail("Недопустимый native Manager вызов.")
        return self.call("sibling", "run", *arguments[2:], capture=False)


def show_plan(reference: str, oracle: dict, context: Context | None = None) -> dict:
    print(f"План: {reference}\nСтатус: {oracle['status_norm']}")
    if context is not None and oracle["status_norm"] in {"done", "superseded"}:
        from sibling_closeout import _correction_outcome, _cycle, _docs
        outcome = _correction_outcome(reference, _docs(context, reference, _cycle(context, reference, None)))
        if outcome is not None:
            print(f"general_pi_format_correction_state={outcome['general_pi_format_correction_state']}")
            print(outcome["message"])
            return {"plan": reference, "oracle": oracle, "next": None, **outcome}
    questions = oracle.get("open_owner_questions", [])
    for question in questions:
        print(f"{question['id']}: {question['text']}")
    if questions:
        next_step = "planveyor sibling answer"
    elif oracle.get("route_guard_triggered"):
        next_step = str(oracle.get("route_guard_reason", "Oracle route guard blocked"))
    elif oracle["status_norm"] == "architect initial draft":
        next_step = "planveyor sibling architect"
    elif oracle["status_norm"] in {"done", "superseded", "architect arch review"}:
        next_step = "planveyor sibling close"
    else:
        next_step = "planveyor sibling run"
    print(f"Следующий шаг: {next_step}")
    return {"plan": reference, "oracle": oracle, "next": next_step}


def init_identity(context: Context, name: str | None, email: str | None) -> tuple[str, str]:
    if (name is None) != (email is None):
        context.fail("Задайте --author-name и --author-email вместе.")
    if name is None:
        def effective(key: str) -> str:
            env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            for scope in ("--global", "--system"):
                done = subprocess.run(["git", "config", scope, "--get", key],
                                      text=True, capture_output=True, env=env, check=False)
                if done.returncode not in {0, 1}:
                    context.fail("Git не смог прочитать identity; исправьте config или задайте имя и email.")
                if done.returncode == 0:
                    return done.stdout.rstrip("\n")
            return ""
        name, email = effective("user.name"), effective("user.email")
        if not name or not email:
            if not sys.stdin.isatty():
                context.fail("Git identity не настроена. Задайте --author-name и --author-email.")
            try:
                name = input("Имя для коммитов sibling: ")
                email = input("Email для коммитов sibling: ")
            except EOFError:
                context.fail("Identity не введена; sibling не создан.")
    try:
        identity = consumer_contract.init_identity(name, email)
    except consumer_contract.ContractError as exc:
        context.fail(str(exc))
    if identity == (consumer_contract.INIT_AUTHOR_NAME, consumer_contract.INIT_AUTHOR_EMAIL):
        context.fail("Укажите свою Git identity вместо служебной identity initializer.")
    return identity


def handle_init(context: Context, args) -> dict:
    name, email = init_identity(context, args.author_name, args.author_email)
    target = Path(args.target)
    if not target.is_absolute():
        target = context.invocation / target
    try:
        target = consumer_contract.canonical_external(os.fspath(target), context.runtime, must_exist=False)
    except consumer_contract.ContractError as exc:
        context.fail(str(exc))
    commit = context.git("rev-parse", "--verify", "HEAD^{commit}", root=context.runtime).stdout.strip()
    if context.git("status", "--porcelain=v1", "--untracked-files=all", root=context.runtime).stdout:
        context.fail("Выбранный runtime содержит незакоммиченные изменения; используйте clean runtime.")
    print(f"Git identity: {name} <{email}>")
    result = context.json_call("planveyor_consumer_init", os.fspath(target), "--source-commit", commit,
                               "--author-name", name, "--author-email", email, "--save-identity",
                               project=context.runtime)
    context.json_call("planveyor_consumer_doctor", project=target)
    print(f"Sibling создан: {target}\nОткройте его в рабочем чате и поручите $planveyor-plan-draft создать и выбрать план адаптации.")
    return result


def atomic_write(path: Path, body: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".planveyor-answer-", dir=path.parent)
    try:
        if path.exists():
            os.fchmod(descriptor, path.stat().st_mode & 0o777)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def owner_payload(context: Context, reference: str, body: str) -> Path:
    payload = context.project / ".planveyor.owner_answers"
    if payload.exists() or payload.is_symlink():
        context.fail("Уже есть ожидающий Owner payload. Завершите соответствующий ход роли; существующие ответы сохранены.")
    return payload


def handle_answer(context: Context, args) -> dict:
    reference, oracle = context.plan()
    path = context.project / reference
    original = path.read_bytes()
    text = original.decode("utf-8")
    state, _, questions, issues = plan_status_oracle.owner_qna_readback(text)
    if issues or state == "blocked":
        context.fail("Canonical Q&A повреждён; ответ не сохранён.")
    from plan_lint import _semantic_masked_markdown_lines
    masked = _semantic_masked_markdown_lines(text.splitlines())
    if any(masked[question.line_no - 1] for question in questions):
        context.fail("Owner вопрос находится в fenced example; canonical ответ не сохранён.")
    actual = {question.qid: question for question in questions}
    question_id = args.question_id.upper() if args.question_id else None
    if question_id and question_id not in actual:
        context.fail("Такого открытого Owner вопроса нет; ответ не сохранён.")
    if question_id is None and len(actual) > 1:
        for question in questions:
            print(f"{question.qid}: {question.text}")
        context.fail("Выберите фактический вопрос: planveyor sibling answer QID.")
    if question_id is None and len(actual) == 1:
        question_id = next(iter(actual))
    if question_id:
        print(actual[question_id].text)
    elif oracle["status_norm"] == "architect initial draft":
        sections = plan_status_oracle._machine_authority_top_level_heading_indices(text.splitlines())
        lines = text.splitlines()
        summaries = [index for index in sections if lines[index] == "## Как я понял задачу"]
        if len(summaries) != 1:
            context.fail("Открытого вопроса нет и текущий итог Architect не найден. Запустите sibling architect.")
        start = summaries[0] + 1
        end = next((index for index in sections if index >= start), len(lines))
        summary = "\n".join(lines[start:end]).strip()
        if not summary:
            context.fail("Architect ещё не записал итог задачи. Запустите sibling architect.")
        print("Текущий итог Architect:\n" + summary + "\nВведите своё решение для следующего хода Architect.")
    else:
        context.fail("Открытых Owner вопросов нет.")
    if args.text is None:
        if sys.stdin.isatty():
            print("Введите ответ; закончите Ctrl-D:", file=sys.stderr)
        answer = sys.stdin.read()
    else:
        answer = args.text
    if not answer.strip() or "\x00" in answer:
        context.fail("Пустой ответ/EOF; plan не изменён.")
    # Authority decisions stay Architect-owned. Deliver the actual human text
    # without writing confirmation/digest fields or closing their reserved QID.
    meta = plan_status_oracle.strict_plan_meta_json(text).plan_meta or {}
    decision = meta.get("machine_authority_decision")
    confirmation = decision.get("confirmation", {}) if isinstance(decision, dict) else {}
    authority_question = isinstance(confirmation, dict) and confirmation.get("question_ref") == question_id
    use_payload = question_id is None or authority_question or oracle["status_norm"] == "architect initial draft"
    payload = owner_payload(context, reference, answer) if use_payload else None
    updated = original
    if question_id and not authority_question:
        lines = text.splitlines(keepends=True)
        indices = plan_status_oracle._machine_authority_top_level_heading_indices(text.splitlines())
        starts = [index for index in indices if plan_status_oracle.OWNER_QNA_SECTION_HEADING_RE.fullmatch(lines[index].rstrip("\r\n"))]
        if len(starts) != 1:
            context.fail("Canonical Q&A section неоднозначен.")
        end = next((index for index in indices if index > starts[0]), len(lines))
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
        entry = f"\n- [{timestamp}] (Owner, id={question_id}, status=closed)\n"
        entry += "".join(f"  > {line}\n" for line in answer.splitlines())
        lines.insert(end, entry + "\n")
        updated = "".join(lines).encode("utf-8")
        after_state, _, after_questions, after_issues = plan_status_oracle.owner_qna_readback(updated.decode("utf-8"))
        if after_state == "blocked" or after_issues or any(question.qid == question_id for question in after_questions):
            context.fail("Ответ не прошёл canonical Q&A validation; plan не изменён.")
    context.plan(reference)
    context.before_effect()
    if path.read_bytes() != original:
        context.fail("Plan изменился во время ввода; повторите answer для текущего вопроса.")
    try:
        if updated != original:
            atomic_write(path, updated)
        if payload is not None:
            # Exclusive creation preserves any concurrently delivered payload.
            with payload.open("x", encoding="utf-8") as handle:
                os.chmod(payload, 0o600)
                handle.write(f"TO=architect\nPLAN_PATH={reference}\n---\n{answer}\n")
        _, after = context.plan(reference)
    except Exception:
        if updated != original and path.read_bytes() == updated:
            atomic_write(path, original)
        raise
    print("Ответ сохранён. Следующий шаг: planveyor sibling " + ("architect" if use_payload else "run"))
    return {"plan": reference, "question_id": question_id, "owner_qna_readback_state": after.get("owner_qna_readback_state"), "native_payload": use_payload}


def handle_upgrade(context: Context, args) -> dict:
    context.require_project()
    if context.invocation == context.project or context.project in context.invocation.parents:
        context.fail("Выйдите из sibling перед upgrade и вызовите planveyor --project PATH sibling upgrade; затем откройте его заново.")
    if context.git("status", "--porcelain=v1", "--untracked-files=all", root=context.runtime).stdout:
        context.fail("Выбранный runtime содержит незакоммиченные изменения; используйте clean runtime.")
    commit = context.git("rev-parse", "--verify", "HEAD^{commit}", root=context.runtime).stdout.strip()
    print("Обновление использует выбранный runtime; existing upgrade сохранит backup и создаст план адаптации.")
    arguments = ["--source-commit", commit]
    if args.accept_candidate:
        arguments.append("--accept-candidate")
    result = context.json_call("planveyor_contract_upgrade", *arguments)
    if result.get("state") != "updated_pending_adaptation" or not isinstance(result.get("plan"), str):
        context.fail("Upgrade не подтвердил adaptation plan.")
    reference, oracle = context.plan(result["plan"])
    context.call("planveyor_plan_set", reference)
    print(f"Backup: {result.get('backup')}\nКонтракт обновлён; адаптация ещё открыта.")
    show_plan(reference, oracle)
    return result


def session_check(context: Context, role: str, sid: str) -> str:
    from contract_authority_bridge import BridgeError, _receipt_validate
    from contract_authority_snapshot import parse_context_envelope
    compact = os.environ.get("_PLANVEYOR_AUTHORITY_CONTEXT_V1", "")
    expected = parse_context_envelope(compact)
    args = argparse.Namespace(project_root=os.fspath(context.project), session_key=role,
                              sid=sid, mode=expected["state"], context=compact)
    try:
        _receipt_validate(args)
    except BridgeError as exc:
        if exc.code == "receipt_missing":
            return "init"
        if exc.code != "receipt_authority_mismatch":
            context.fail(str(exc))
        receipt = context.project / ".planveyor.init_runs/by_sid" / sid / "meta.json"
        authority = json.loads(receipt.read_text(encoding="utf-8"))["authority_context"]
        previous = parse_context_envelope(json.dumps(authority))
        if (previous.get("project_root") != expected.get("project_root")
                or previous.get("runtime_pin", {}).get("runtime_root") != expected.get("runtime_pin", {}).get("runtime_root")):
            context.fail("Receipt принадлежит другому project/runtime; сессия не заменена.")
        return "init"
    return "ready"


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="planveyor sibling", description="Обычный цикл sibling: init → plan → architect/answer → run → close → ready.")
    cli.add_argument("--runtime-root", required=True, help=argparse.SUPPRESS)
    cli.add_argument("--project-root", required=True, help=argparse.SUPPRESS)
    cli.add_argument("--invocation-root", help=argparse.SUPPRESS)
    actions = cli.add_subparsers(dest="action", required=True)
    create = actions.add_parser("init", help="создать sibling с вашей Git identity")
    create.add_argument("target")
    create.add_argument("--author-name")
    create.add_argument("--author-email")
    select = actions.add_parser("plan", help="выбрать или показать текущий plan")
    select.add_argument("plan", nargs="?")
    actions.add_parser("architect", help="обсудить текущий plan с Architect")
    answer = actions.add_parser("answer", help="сохранить фактический Owner ответ")
    answer.add_argument("question_id", nargs="?")
    answer.add_argument("--text", help="ваш ответ; без параметра читается stdin")
    run = actions.add_parser("run", help="продолжить normal Manager для текущего plan")
    run.add_argument("--followups-capture-cycle-id", dest="cycle", help="явный existing cycle при восстановлении")
    close = actions.add_parser("close", help="показать точный набор или явно коммитить его")
    close.add_argument("--commit", action="store_true")
    close.add_argument("--message")
    close.add_argument("--cycle", help="existing capture cycle при неоднозначном readback")
    ready = actions.add_parser("ready", help="прочитать реальную готовность текущего sibling")
    ready.add_argument("--cycle", help="existing capture cycle при неоднозначном readback")
    upgrade = actions.add_parser("upgrade", help="обновить из выбранного runtime")
    upgrade.add_argument("--accept-candidate", action="store_true")
    return cli


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    cli = parser()
    # The shell's finite adapter invokes only these read-only preparations.
    internal = None
    if "--internal" in arguments:
        index = arguments.index("--internal")
        internal = arguments[index + 1:]
        arguments = arguments[:index] + ["plan"]
    args = cli.parse_args(arguments)
    context = Context(Path(args.runtime_root), Path(args.project_root),
                      Path(args.invocation_root) if args.invocation_root else None)
    try:
        if internal is not None:
            if not internal:
                context.fail("Недопустимый внутренний adapter.")
            if internal[0] == "session-check" and len(internal) == 3 and internal[1] in {"architect", "manager"}:
                print(session_check(context, internal[1], internal[2]))
                return 0
            if internal[0] == "admit-done" and len(internal) == 2:
                from sibling_closeout import _strict, validate_done_admission
                reference, oracle = context.plan(internal[1])
                if oracle["status_norm"] != "architect arch review":
                    context.fail("Переход Done требует текущий Arch review.")
                validate_done_admission(context, reference, oracle)
                preflight = _strict(context, reference)
                if preflight.get("closeout_state") != "commit_ready":
                    context.fail("Строгий preflight не разрешает переход Done.")
                return 0
            context.fail("Недопустимый внутренний adapter.")
        if args.action == "init":
            handle_init(context, args)
        elif args.action == "plan":
            reference, oracle = context.plan(args.plan)
            if args.plan is not None:
                context.call("planveyor_plan_set", reference)
            show_plan(reference, oracle, context)
        elif args.action == "answer":
            handle_answer(context, args)
        elif args.action == "upgrade":
            handle_upgrade(context, args)
        elif args.action in {"architect", "run"}:
            # Executed by the shell adapter after this validation-only entry.
            reference, oracle = context.plan()
            if args.action == "architect" and oracle["status_norm"] not in {
                "architect initial draft", "architect draft", "ready for architect response",
                "architect response", "ready for arch review", "architect arch review",
            }:
                context.fail("Текущий status не принадлежит Architect; используйте planveyor sibling run.")
            print(reference if args.action == "run" else oracle["status_norm"])
        else:
            from sibling_closeout import handle_close, handle_ready
            result = handle_close(context, args) if args.action == "close" else handle_ready(context, args)
            if result is not None:
                if result.get("general_pi_format_correction_state"):
                    print("general_pi_format_correction_state=" + result["general_pi_format_correction_state"])
                if result.get("message"):
                    print(result["message"])
                for reference in result.get("paths", []):
                    print(f"  {reference}")
                if result.get("commit_message"):
                    print("Сообщение коммита: " + result["commit_message"])
        return 0
    except ContractAuthorityError as exc:
        print(f"planveyor sibling: {exc.reason_code}: {exc}", file=sys.stderr)
        return 3
    except (RunbookError, consumer_contract.ContractError, OSError, ValueError) as exc:
        print(f"planveyor sibling: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

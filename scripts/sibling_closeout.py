"""Human sibling closeout adapters; canonical helpers remain the authority."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import followups_capture
import plan_lint


def _git(context: Any, *args: str) -> subprocess.CompletedProcess[str]:
    return context.git(*args)


def _paths(context: Any, value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        context.fail("Helper не вернул точный список путей.")
    for item in value:
        path = PurePosixPath(item)
        if (not item or path.is_absolute() or "\x00" in item
                or any(part in {"", ".", ".."} for part in item.split("/"))):
            context.fail("Helper вернул небезопасный путь в bundle.")
    if len(value) != len(set(value)):
        context.fail("Helper вернул повторяющиеся пути.")
    return value


def _bundle(context: Any, plan: str, *, require_green: bool = True,
            allow_docs_stage: bool = False) -> tuple[dict, dict]:
    payload = context.json_call("planveyor_plan_bundle", "--closeout-json", plan)
    roots = payload.get("repo_roots")
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], dict):
        context.fail("Закрытие требует одного однозначного Git root; верните scope Architect.")
    root = roots[0]
    if root.get("repo_root") != str(context.project):
        context.fail("Bundle относится к другому Git root; закрытие остановлено.")
    _paths(context, root.get("bundle_paths"))
    extras = _paths(context, root.get("staged_extra_paths"))
    if extras and not allow_docs_stage:
        context.fail("В index есть файлы вне выбранного bundle. Сохраните их отдельно перед close.")
    if require_green and payload.get("bundle_ok") is not True:
        reasons = payload.get("errors") or root.get("path_problems") or payload.get("closeout_kind")
        context.fail(f"Canonical bundle заблокирован: {reasons}. Следующий шаг: planveyor sibling run.")
    return payload, root


def _arch_acceptance(context: Any, plan: str) -> dict[str, str]:
    lines = (context.project / plan).read_text(encoding="utf-8").splitlines()
    refs = plan_lint.extract_live_review_artifact_refs(lines)
    if len(refs) != 1:
        context.fail("Нужен единственный review artifact с архитектурной приёмкой. Следующий шаг: planveyor sibling architect.")
    review_ref = refs[0][1]
    _paths(context, [review_ref])
    review = context.project / review_ref
    for component in [review, *review.parents]:
        if component == context.project:
            break
        if component.is_symlink():
            context.fail("Review artifact не может проходить через symlink.")
    rows = review.read_text(encoding="utf-8").splitlines()
    masked = plan_lint._semantic_masked_markdown_lines(rows)
    sections = [(start, end) for start, title, end in plan_lint._semantic_h2_sections(rows, masked)
                if title.casefold() in {"## архитектурное ревью", "## arch review"}]
    if len(sections) != 1:
        context.fail("Нужна одна секция «Архитектурное ревью» в review artifact. Следующий шаг: planveyor sibling architect.")
    start, end = sections[0]
    body = [row.strip() for index, row in enumerate(rows[start + 1:end], start + 1)
            if not masked[index] and row.strip()]
    first = body[0] if body else ""
    # This human admission has one canonical positive verdict. Explanations
    # belong below it; neither affirmative prefixes nor free prose are proof.
    if first.casefold() != "вердикт: принято.":
        context.fail(f"Первый вердикт Architect не даёт однозначной приёмки. Получено: {first!r}. "
                     "Ожидается первая строка «Вердикт: принято.», обоснование ниже. "
                     "Следующий шаг: planveyor sibling architect; статус не изменён.")
    return {"review": review_ref, "verdict": first}


def validate_done_admission(context: Any, plan: str, oracle: dict) -> dict:
    """Read-only gate, also reused by the finite existing-setter adapter."""
    status = oracle.get("status_norm")
    if status not in {"architect arch review", "done"}:
        context.fail("План ещё не принят Architect. Следующий шаг: planveyor sibling run.")
    if oracle.get("route_guard_triggered") is not False:
        context.fail(f"Oracle блокирует переход: {oracle.get('route_guard_reason') or 'route guard'}.")
    if (oracle.get("owner_qna_readback_state") != "clean" or oracle.get("owner_qna_issues")
            or oracle.get("open_owner_questions")):
        context.fail("Остались реальные вопросы Owner. Следующий шаг: planveyor sibling answer.")
    if oracle.get("review_readback_state") != "ok":
        context.fail(f"Текущее ревью не принято: {oracle.get('review_readback_reason') or 'missing review'}. Запустите sibling run.")
    _arch_acceptance(context, plan)
    payload, _root = _bundle(context, plan)
    if status == "architect arch review" and payload.get("closeout_kind") == "already_materialized":
        context.fail("Bundle уже materialized, но статус ещё Arch review. "
                     "Переход Done без semantic delta здесь не поддержан. "
                     "Следующий шаг: planveyor sibling architect для разбора перехода.")
    result = context.call("planveyor_plan_lint", "--as-status", "Done", plan, check=False)
    if result.returncode:
        context.fail("Переход в Done не прошёл canonical lint:\n" + (result.stdout or result.stderr).strip())
    return payload


def _strict(context: Any, plan: str) -> dict:
    result = context.json_call("planveyor_plan_closeout_preflight", "--json", plan)
    if (result.get("closeout_state") == "already_materialized"
            and result.get("semantic_ready") is True and result.get("bundle_ready") is True):
        return result
    if not (result.get("closeout_state") == "commit_ready"
            and all(result.get(key) is True for key in
                    ("semantic_ready", "bundle_ready", "staged_exact", "git_writable", "commit_ready"))
            and isinstance(result.get("safe_command"), str) and result["safe_command"].strip()):
        context.fail(f"Коммит заблокирован canonical preflight: {result.get('closeout_state', 'invalid payload')}.")
    # safe_command is an admission signal only; it is never parsed or executed.
    return result


def _fingerprint(context: Any, paths: list[str], oracle: dict) -> str:
    digest = hashlib.sha256()
    for root, relatives in ((context.project, paths + ["docs/_meta/planveyor_contract_authority.v1.json", ".copier-answers.yml"]),):
        for relative in sorted(set(relatives)):
            path = root / relative
            digest.update(relative.encode("utf-8") + b"\0")
            try:
                info = path.lstat()
            except FileNotFoundError:
                digest.update(b"missing\0")
                continue
            if not stat.S_ISREG(info.st_mode):
                context.fail("Bundle изменился или содержит непроверенный тип файла; повторите close.")
            digest.update(str(info.st_mode).encode("ascii") + b"\0" + path.read_bytes())
    for args in (("rev-parse", "HEAD"), ("--literal-pathspecs", "ls-files", "--stage", "-z", "--", *paths)):
        digest.update(_git(context, *args).stdout.encode("utf-8"))
    runtime = context.git("rev-parse", "HEAD", root=context.runtime)
    digest.update(runtime.stdout.encode("ascii"))
    # Oracle's documented diagnostic run UUID is fresh for every invocation
    # (plan_status_oracle.oracle_result), including --json --current-state.
    # Preserve every other field, including plan_hash/mtime and current_state.
    oracle_evidence = {key: value for key, value in oracle.items() if key != "oracle_run_id"}
    digest.update(json.dumps(oracle_evidence, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def _message(context: Any, plan: str, override: str | None) -> str:
    if override is not None:
        if not override.strip() or "\x00" in override:
            context.fail("Сообщение коммита должно быть непустым и не содержать NUL.")
        return override
    rows = (context.project / plan).read_text(encoding="utf-8").splitlines()
    title = next((row[2:].strip() for row in rows if row.startswith("# ")), Path(plan).stem)
    return f"plan: {title}\n\nPlanveyor-Plan: {plan}"


def _cycle(context: Any, plan: str, explicit: str | None) -> str | None:
    if explicit:
        if not followups_capture.UUID4_RE.fullmatch(explicit):
            context.fail("Capture cycle должен быть canonical UUIDv4.")
        return explicit
    family = context.project / ".tmp/followups_capture" / followups_capture.plan_stem(plan)
    if not family.exists() and not family.is_symlink():
        return None
    candidates = []
    try:
        with followups_capture.CaptureHost(context.project, plan) as host:
            for name in sorted(os.listdir(host.family_fd)):
                if not followups_capture.UUID4_RE.fullmatch(name):
                    continue
                fd, identity = followups_capture._open_cycle(host, name)
                try:
                    receipt, _raw, _identity = followups_capture._read_receipt(fd, plan, name)
                    if (receipt["cycle_directory_identity"] != identity
                            or receipt["transaction_host_identity"] != host.transaction_host_identity()):
                        context.fail("Capture receipt изменил host identity; закрытие остановлено.")
                    try:
                        followups_capture._current_plan_identity(context.project, receipt)
                    except followups_capture.CaptureError as exc:
                        if exc.reason_code == "followup_capture_plan_identity_mismatch":
                            continue
                        raise
                    candidates.append(name)
                finally:
                    os.close(fd)
    except followups_capture.CaptureError as exc:
        context.fail(f"Capture proof невалиден: {exc.reason_code}. Запустите sibling run для разбора.")
    if len(candidates) > 1:
        context.fail("Несколько валидных capture cycles этого плана; выберите --cycle из диагностики: " + ", ".join(candidates))
    return candidates[0] if candidates else None


def _docs(context: Any, plan: str, cycle: str | None) -> dict:
    args = [plan]
    if cycle:
        args += ["--followups-capture-cycle-id", cycle]
    payload = context.json_call("planveyor_docs_closeout", *args, "--json")
    if (payload.get("schema") != "docs_closeout_payload.v1" or payload.get("schema_state") != "ok"
            or payload.get("schema_errors") or payload.get("plan_ref") != plan):
        context.fail("Docs-closeout не вернул валидное доказательство выбранного плана.")
    if cycle and payload.get("followups_capture_cycle_id") != cycle:
        context.fail("Docs-closeout вернул другой capture cycle.")
    return payload


def _completed(payload: dict) -> bool:
    return (payload.get("state") == "completed" and payload.get("bundle_ok") is True
            and not payload.get("bundle_errors") and payload.get("final_docs_commit") in {"no_op", "landed"}
            and payload.get("process_improvement_capture_state") in {"clean_noop", "materialized", "already_tracked"}
            and payload.get("followups_reconciliation", {}).get("state") in {"clean_noop", "external_clean_noop", "external_clean"}
            and not payload.get("blocked_docs_delta_paths") and not payload.get("protected_docs_delta_paths"))


def _result(state: str, plan: str, message: str, **details: Any) -> dict:
    return {"state": state, "plan": plan, "message": message, **details}


def handle_close(context: Any, args: Any) -> dict:
    plan, oracle = context.plan()
    terminal = None
    semantic_pending = False
    if oracle["status_norm"] == "done":
        terminal_bundle, terminal_root = _bundle(context, plan, require_green=False, allow_docs_stage=True)
        cycle = _cycle(context, plan, getattr(args, "cycle", None))
        docs = _docs(context, plan, cycle)
        terminal = (terminal_root, cycle, docs)
        # A legacy/provisional Done still needs its semantic commit. The
        # canonical docs classifier distinguishes it from a receipt-owned tail.
        semantic_pending = (cycle is None and docs.get("state") == "blocked"
            and docs.get("reason_code") in {"semantic_closeout_commit_pending", "semantic_closeout_has_unstaged_delta"}
            and docs.get("semantic_closeout_kind") == terminal_bundle.get("closeout_kind")
            and docs.get("bundle_ok") is True and not docs.get("current_plan_owned_docs_delta_paths")
            and not docs.get("final_docs_diff_paths"))
    if oracle["status_norm"] != "done" or semantic_pending:
        bundle = validate_done_admission(context, plan, oracle)
        root = bundle["repo_roots"][0]
        paths = _paths(context, root["bundle_paths"])
        message = _message(context, plan, getattr(args, "message", None))
        if not args.commit:
            return _result("semantic_ready", plan, "План принят. Следующий шаг: planveyor sibling close --commit.",
                           paths=paths, commit_message=message, next_command="planveyor sibling close --commit")
        head = _git(context, "rev-parse", "HEAD").stdout.strip()
        before = (context.project / plan).read_bytes()
        provisional: bytes | None = None
        try:
            result = context.call("planveyor_plan_bundle", "--stage", plan, check=False)
            if result.returncode:
                context.fail("Exact stage остановлен; выбранные paths могли остаться staged: " + (result.stderr or result.stdout).strip())
            _strict(context, plan)
            if oracle["status_norm"] != "done":
                rows = before.decode("utf-8").splitlines()
                status_rows = plan_lint.extract_status_lines(rows)
                if len(status_rows) != 1:
                    context.fail("Status изменился перед переходом в Done.")
                line_number = status_rows[0][0]
                prefix = re.match(r"^(\s*(?:>\s*)?\*\*Status:\*\*\s*)", rows[line_number - 1])
                if prefix is None:
                    context.fail("Status изменился перед переходом в Done.")
                rows[line_number - 1] = prefix.group(1) + "Done  "
                provisional = ("\n".join(rows) + "\n").encode("utf-8")
                context.set_status(plan, "Done")
                if (context.project / plan).read_bytes() != provisional:
                    context.fail("Plan изменился во время status setter; закрытие остановлено.")
                result = context.call("planveyor_plan_lint", plan, check=False)
                if result.returncode:
                    context.fail("Final Done lint не прошёл: " + (result.stdout or result.stderr).strip())
                result = context.call("planveyor_plan_bundle", "--stage", plan, check=False)
                if result.returncode:
                    context.fail("Final exact stage не выполнен: " + (result.stderr or result.stdout).strip())
            fresh = context.json_call("planveyor_plan_status_oracle", "--json", "--current-state", plan)
            current, current_root = _bundle(context, plan)
            if current_root["bundle_paths"] != paths:
                context.fail("Bundle scope изменился; повторите close.")
            observed = _fingerprint(context, paths, fresh)
            preflight = _strict(context, plan)
            if preflight["closeout_state"] != "already_materialized":
                staged = _paths(context, current_root.get("staged_bundle_paths"))
                if not staged or current.get("closeout_kind") != "commit_ready":
                    context.fail("Свежий bundle не подтверждает точный staged delta.")
                checked, checked_root = _bundle(context, plan)
                final_oracle = context.json_call("planveyor_plan_status_oracle", "--json", "--current-state", plan)
                if checked != current or _fingerprint(context, paths, final_oracle) != observed:
                    context.fail("HEAD, index, worktree или review изменились перед коммитом. Повторите close.")
                if checked_root.get("staged_bundle_paths") != staged:
                    context.fail("Staged path set изменился перед коммитом.")
                context.before_effect()
                _git(context, "--literal-pathspecs", "commit", "-m", message, "--", *staged)
            landed = _git(context, "rev-parse", "HEAD").stdout.strip()
            readback, _readback_root = _bundle(context, plan)
            if readback.get("closeout_kind") != "already_materialized":
                context.fail("Коммит выполнен, но fresh semantic readback не чистый. Повторите close для диагностики.")
        except Exception as exc:
            # Restore only the bytes we wrote, only before any commit landed.
            if (provisional is not None and _git(context, "rev-parse", "HEAD").stdout.strip() == head
                    and (context.project / plan).read_bytes() == provisional):
                (context.project / plan).write_bytes(before)
                _git(context, "--literal-pathspecs", "add", "--", plan)
                context.fail(f"{exc}\nСтатус восстановлен; выбранный plan staged с исходными bytes. Остальные staged paths сохранены.")
            raise
        return _result("semantic_committed", plan, "План закоммичен. Следующий шаг: planveyor sibling run для документов.",
                       commit=landed, commit_message=message, paths=paths, next_command="planveyor sibling run")

    # Receipt-owned terminal docs never enter the ordinary Git commit route.
    assert terminal is not None
    terminal_root, cycle, docs = terminal
    if getattr(args, "message", None) is not None:
        context.fail("Docs closeout использует штатное автоматическое сообщение; уберите --message.")
    allowed_docs = _paths(context, docs.get("final_docs_diff_paths", []))
    if set(terminal_root["staged_extra_paths"]) - set(allowed_docs):
        context.fail("В index есть файлы вне выбранного semantic/docs bundle; закрытие остановлено.")
    if _completed(docs):
        return _result("completed", plan, "План и документы закрыты. Можно начать следующую задачу.", closeout=docs)
    if docs.get("state") != "completed" or docs.get("final_docs_commit") != "required":
        return _result("docs_pending", plan, f"Документы ещё не закрыты: {docs.get('reason_code')}. Следующий шаг: planveyor sibling run.",
                       closeout=docs, next_command="planveyor sibling run")
    doc_paths = _paths(context, docs.get("final_docs_diff_paths"))
    if not cycle or not doc_paths or docs.get("blocked_docs_delta_paths") or docs.get("protected_docs_delta_paths"):
        context.fail("Нет однозначного receipt-owned docs bundle; следующий шаг: planveyor sibling run.")
    if not args.commit:
        return _result("docs_ready", plan, "Документы готовы. Следующий шаг: planveyor sibling close --commit.",
                       paths=doc_paths, commit_message=followups_capture._resolve_commit_message(plan, None, message_auto=True).decode("utf-8"),
                       closeout=docs, next_command="planveyor sibling close --commit")
    raw = json.dumps(docs, ensure_ascii=False)
    staged = context.call("planveyor_plan_bundle", "--stage", "--docs-closeout-json", "-", plan, input_text=raw, check=False)
    if staged.returncode:
        context.fail("Docs exact stage остановлен; receipt-owned paths могли остаться staged: " + (staged.stderr or staged.stdout).strip())
    preflight_result = context.call("planveyor_plan_closeout_preflight", "--docs-closeout-json", "-", "--json", plan, input_text=raw, check=False)
    try:
        preflight = json.loads(preflight_result.stdout)
    except (ValueError, TypeError):
        context.fail("Docs preflight не вернул JSON; коммит не выполнен.")
    if (preflight_result.returncode or not isinstance(preflight, dict)
            or preflight.get("schema_version") != "followups_commit_preflight.v1"
            or preflight.get("state") != "ready" or preflight.get("plan_ref") != plan
            or preflight.get("capture_cycle_id") != cycle):
        context.fail("Docs preflight заблокирован; коммит не выполнен.")
    committed = context.call("planveyor_plan_bundle", "--commit-exact", "--preflight-json", "-", "--message-auto", plan,
                             input_text=json.dumps(preflight, ensure_ascii=False), check=False)
    if committed.returncode:
        context.fail("Docs commit-exact остановлен: " + (committed.stderr or committed.stdout).strip())
    cold = _docs(context, plan, cycle)
    if not _completed(cold):
        context.fail(f"Docs commit выполнен, но cold closeout не завершён: {cold.get('reason_code')}. Повторите close.")
    return _result("completed", plan, "План и документы закрыты. Можно начать следующую задачу.", closeout=cold)


def handle_ready(context: Any, args: Any) -> dict:
    doctor = context.json_call("planveyor_consumer_doctor")
    plan, oracle = context.plan()
    if doctor.get("state") != "ok":
        return _result("blocked", plan, "Consumer contract требует разбора; готовность не подтверждена.", contract=doctor)
    if oracle.get("status_norm") != "done" or oracle.get("route_guard_triggered") is not False or oracle.get("queue_closeout_ready") is not True:
        return _result("pending", plan, "Выбранный план ещё не закрыт. Следующий шаг: planveyor sibling run.",
                       oracle=oracle, next_command="planveyor sibling run")
    cycle = _cycle(context, plan, getattr(args, "cycle", None))
    docs = _docs(context, plan, cycle)
    if not _completed(docs):
        return _result("pending", plan, f"Closeout ещё не завершён: {docs.get('reason_code')}. Выполните planveyor sibling close.",
                       closeout=docs, next_command="planveyor sibling close")
    return _result("ready", plan, "Consumer contract и выбранный план закрыты. Готовность отдельного release или SQL не проверялась.",
                   contract=doctor, oracle=oracle, closeout=docs)

#!/usr/bin/env python3
"""Check public Planveyor lifecycle and packet-contract owners."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
TICK = chr(96)
DOLLAR = "$"


def code(value: str) -> str:
    return f"{TICK}{value}{TICK}"


MANAGER_PROMPT = "docs/tools/prompts/manager_collab_merge_pipeline.md"
DOC_LINT_PLAYBOOK = "docs/playbooks/doc_lint.md"
DOCS_HYGIENE_PLAYBOOK = "docs/playbooks/post_merge_docs_hygiene.md"
ARCHITECT_DOCS_FINALIZE = "docs/tools/prompts/architect_docs_finalize_general.md"
PLANVEYOR_ZSH = "scripts/planveyor.zsh"
ROLLOUT_PACKET = "scripts/rollout_packet.py"
PACKETIZATION_GATE = "scripts/post_merge_packetization_gate.py"
READY_TO_PUSH_CLOSEOUT = "scripts/post_merge_ready_to_push_closeout.py"
OPERATIONAL_RECEIPT = "scripts/post_merge_operational_receipt.py"
DOCS_FINALIZE_ZSH = "scripts/planveyor/docs_finalize.zsh"

EXACT_BUNDLE = (
    MANAGER_PROMPT,
    DOC_LINT_PLAYBOOK,
    DOCS_HYGIENE_PLAYBOOK,
    ARCHITECT_DOCS_FINALIZE,
    PLANVEYOR_ZSH,
    ROLLOUT_PACKET,
    PACKETIZATION_GATE,
    READY_TO_PUSH_CLOSEOUT,
    OPERATIONAL_RECEIPT,
    DOCS_FINALIZE_ZSH,
)

INVARIANT_IDS = (
    "no_default_django_baseline",
    "tooling_merge_step_set",
    "doc_lint_gate",
    "docs_hygiene_suggest_autorun",
    "ready_to_push_auto_closeout",
    "no_progress_updates",
    "docs_finalize_merge_receipt",
    "packetization_range_identity",
    "packetization_target_applicability",
)

BUNDLE_FILE_INVARIANT = "bundle_file"

MERGE_STEPS = (
    "step:review_range",
    "step:merge_notes",
    "step:plan_harvest",
    "step:canon_sweep",
    "step:packetization_gate",
    "step:docs_finalize",
    "step:doc_lint",
    "step:post_merge_audit",
    "step:docs_hygiene_archive",
    "step:docs_hygiene_suggest",
    "step:ready_to_push",
)


@dataclass(frozen=True)
class Finding:
    invariant_id: str
    rel_path: str
    message: str

    def render(self) -> str:
        return f"ERROR {self.invariant_id} {self.rel_path}: {self.message}"


def _read_bundle(root: Path) -> tuple[dict[str, str], list[Finding]]:
    texts: dict[str, str] = {}
    findings: list[Finding] = []
    for rel_path in EXACT_BUNDLE:
        file_path = root / rel_path
        if not file_path.is_file():
            findings.append(Finding(BUNDLE_FILE_INVARIANT, rel_path, "missing required bundle file"))
            continue
        texts[rel_path] = file_path.read_text(encoding="utf-8")
    return texts, findings


def _add_missing(
    texts: dict[str, str],
    invariant_id: str,
    rel_path: str,
    snippets: tuple[str, ...],
    findings: list[Finding],
) -> None:
    text = texts.get(rel_path)
    if text is None:
        return
    missing = tuple(snippet for snippet in snippets if snippet not in text)
    if missing:
        findings.append(
            Finding(
                invariant_id,
                rel_path,
                "missing required snippet(s): " + ", ".join(repr(item) for item in missing),
            )
        )


def _add_ordered(
    texts: dict[str, str],
    invariant_id: str,
    rel_path: str,
    snippets: tuple[str, ...],
    findings: list[Finding],
) -> None:
    text = texts.get(rel_path)
    if text is None:
        return
    positions = tuple(text.find(snippet) for snippet in snippets)
    if any(position < 0 for position in positions):
        _add_missing(texts, invariant_id, rel_path, snippets, findings)
    elif positions != tuple(sorted(positions)):
        findings.append(Finding(invariant_id, rel_path, "required lifecycle sequence is out of order"))


def _shell_function_body(text: str, name: str) -> str | None:
    start = re.search(rf"(?m)^{re.escape(name)}\s*\(\)\s*\{{", text)
    if start is None:
        return None
    remainder = text[start.end() :]
    next_function = re.search(r"(?m)^[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", remainder)
    return remainder[: next_function.start()] if next_function else remainder


def _recovery_body_keeps_range_only_contract(body: str) -> bool:
    """Check the finite supported recovery-body form for range-only input.

    This deliberately does not execute shell text or infer arbitrary shell
    reachability. It recognizes the public recovery dispatch plus the supported
    parser/guard form, and rejects a source-plan control gate before that
    dispatch. Comments are excluded so documented optional syntax is not
    mistaken for a prerequisite.
    """

    dispatch = re.search(
        r'(?m)^[ \t]*(?!#)_planveyor_py_any "\$helper" --content-profile-id "\$content_profile_id" --repo-root "\$root" --recover "\$@"\s*$',
        body,
    )
    if dispatch is None:
        return False
    executable_prefix = "\n".join(
        line for line in body[: dispatch.start()].splitlines() if not line.lstrip().startswith("#")
    )
    source_plan_guard = re.compile(
        r"(?mx)"
        r"^[ \t]*(?:(?:if|elif)[ \t]+)?"
        r"!?[ \t]*"
        r"(?:"
        r"\(\([^\n]*\b[A-Za-z_]*source_plan[A-Za-z0-9_]*\b[^\n]*\)\)"
        r"|\[\[[^\n]*(?:\b[A-Za-z_]*source_plan[A-Za-z0-9_]*\b|--source-plan)[^\n]*\]\]"
        r")"
        r"[ \t]*(?:\|\||;?[ \t]*then\b|&&[ \t]*(?:return|exit)\b)"
    )
    return source_plan_guard.search(executable_prefix) is None


def _has_legacy_source_artifacts_range_identity(text: str) -> bool:
    return re.search(
        r"exact\s+full-OID\s+range\s+identity\s*\(\s*`?source_range`?\s*,\s*"
        r"`?source_revision`?\s*,\s*sorted\s+`?source_artifacts`?\s*\)",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _manager_step_slice(text: str, step: str) -> str | None:
    start = re.search(rf"(?m)^[ \t]*-\s+{re.escape(code(step))}:\s*$", text)
    if start is None:
        return None
    remainder = text[start.end() :]
    next_step = re.search(r"(?m)^[ \t]*-\s+`step:[^`]+`:\s*$", remainder)
    return remainder[: next_step.start()] if next_step else remainder


def _add_function_dispatch(
    texts: dict[str, str],
    invariant_id: str,
    *,
    name: str,
    required_fragments: tuple[str, ...],
    executable_pattern: str,
    findings: list[Finding],
) -> None:
    text = texts.get(PLANVEYOR_ZSH)
    if text is None:
        return
    body = _shell_function_body(text, name)
    if body is None:
        findings.append(Finding(invariant_id, PLANVEYOR_ZSH, f"missing public function {name}"))
        return
    missing = tuple(fragment for fragment in required_fragments if fragment not in body)
    if missing:
        findings.append(
            Finding(
                invariant_id,
                PLANVEYOR_ZSH,
                f"{name} missing required body fragment(s): " + ", ".join(repr(item) for item in missing),
            )
        )
        return
    if re.search(executable_pattern, body, flags=re.MULTILINE) is None:
        findings.append(
            Finding(
                invariant_id,
                PLANVEYOR_ZSH,
                f"{name} lacks the required executable helper dispatch",
            )
        )


def _check_no_default_baseline(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "no_default_django_baseline",
        MANAGER_PROMPT,
        (
            "Generic merge baseline не предполагает Django, " + code("manage.py") + ", migrations, ledger, browser/UI harness или другой product stack.",
            "Target-defined gate запускается только когда tracker-linked canon/plan literal-но объявляет его contract, preconditions и success criterion;",
            "Target может добавить declared gate, но он не становится shared default.",
            "Он не является shared default и не materialize-ится при отсутствии declared contract.",
        ),
        findings,
    )


def _check_merge_steps(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(texts, "tooling_merge_step_set", MANAGER_PROMPT, MERGE_STEPS, findings)
    _add_missing(
        texts,
        "tooling_merge_step_set",
        MANAGER_PROMPT,
        (
            "Базовый порядок generic merge closeout: "
            + code("review_range")
            + " → "
            + code("merge_notes")
            + " → "
            + code("plan_harvest")
            + " → "
            + code("canon_sweep")
            + " → "
            + code("packetization_gate")
            + " → "
            + code("docs_finalize")
            + " → "
            + code("doc_lint")
            + " → "
            + code("post_merge_audit")
            + " → hygiene/readiness.",
        ),
        findings,
    )


def _check_doc_lint(texts: dict[str, str], findings: list[Finding]) -> None:
    lint_args_ref = DOLLAR + "{lint_args[@]}"
    _add_missing(
        texts,
        "doc_lint_gate",
        DOC_LINT_PLAYBOOK,
        (
            "Обычный gate: " + code("make doc-lint"),
            "Canonical closeout gate: " + code("planveyor_doc_lint"),
            "Strict explicit bundle",
        ),
        findings,
    )
    _add_missing(texts, "doc_lint_gate", MANAGER_PROMPT, ("- " + code("make doc-lint"),), findings)
    _add_function_dispatch(
        texts,
        "doc_lint_gate",
        name="planveyor_doc_lint",
        required_fragments=(
            'lint_script="$(_planveyor_script doc_lint.py)"',
            "--check-code-refs --code-refs-scope repo",
            'env PYTHONDONTWRITEBYTECODE=1 "$pybin" -B "$lint_script" "' + lint_args_ref + '"',
        ),
        executable_pattern=(
            r'^[ \t]*(?!#)env PYTHONDONTWRITEBYTECODE=1 "\$pybin" -B "\$lint_script" "'
            + re.escape(lint_args_ref)
            + r'"\s*$'
        ),
        findings=findings,
    )


def _check_docs_hygiene(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "docs_hygiene_suggest_autorun",
        MANAGER_PROMPT,
        (
            "planveyor_post_merge_docs_hygiene_suggest_gate",
            "stdout markers " + code("[planveyor] Range:") + " + " + code("[planveyor] Suggested (Owner) command:"),
            "no traceback, no tracked git status change before tracker tick",
            "не тикать " + code("step:ready_to_push"),
        ),
        findings,
    )
    _add_missing(
        texts,
        "docs_hygiene_suggest_autorun",
        DOCS_HYGIENE_PLAYBOOK,
        (
            "docs_hygiene_suggest_summary",
            "report_only=true",
            "deletion_executed=false",
        ),
        findings,
    )
    _add_function_dispatch(
        texts,
        "docs_hygiene_suggest_autorun",
        name="planveyor_post_merge_docs_hygiene_suggest_gate",
        required_fragments=(
            'planveyor_docs_hygiene_suggest --range "$range" >"$stdout_path" 2>"$stderr_path"',
            "rg -q '^\\[planveyor\\] Range:'",
            "rg -q '^\\[planveyor\\] Suggested \\(Owner\\) command:'",
            "rg -q 'Traceback'",
            '[[ "$before_status" != "$after_status" ]]',
            "planveyor_merge_tracker_tick step:docs_hygiene_suggest",
            "suggested git rm was not executed",
        ),
        executable_pattern=r'^[ \t]*(?!#)planveyor_docs_hygiene_suggest --range "\$range" >"\$stdout_path" 2>"\$stderr_path"\s*$',
        findings=findings,
    )
    _add_missing(
        texts,
        "docs_hygiene_suggest_autorun",
        OPERATIONAL_RECEIPT,
        (
            'DOCS_HYGIENE_SUGGEST_GATE_COMMAND = "planveyor_post_merge_docs_hygiene_suggest_gate"',
            '"report_only": True',
            '"deletion_executed": False',
            '"ready_to_push_ticked_by_suggest_gate": False',
        ),
        findings,
    )


def _check_ready_to_push(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "ready_to_push_auto_closeout",
        MANAGER_PROMPT,
        (
            "planveyor_post_merge_ready_to_push_closeout",
            "terminal_ready_to_push_proof",
            "rolls that tick back if receipt staging or commit fails",
            "stage all report-accepted paths and rerun",
            "never runs " + code("git push"),
        ),
        findings,
    )
    _add_function_dispatch(
        texts,
        "ready_to_push_auto_closeout",
        name="planveyor_post_merge_ready_to_push_closeout",
        required_fragments=(
            'helper="$(_planveyor_script post_merge_ready_to_push_closeout.py)"',
            '_planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --root "$root" "$@"',
        ),
        executable_pattern=r'^[ \t]*(?!#)_planveyor_py_any "\$helper" --content-profile-id "\$content_profile_id" --root "\$root" "\$@"\s*$',
        findings=findings,
    )
    _add_missing(
        texts,
        "ready_to_push_auto_closeout",
        READY_TO_PUSH_CLOSEOUT,
        (
            'DIRTY_ACCEPTED_RECOVERY = "stage all report-accepted paths and rerun"',
            'TERMINAL_PROOF_STATE = "terminal_ready_to_push_proof"',
            '"staging_diagnostics"',
            '"pending_owner_gate": "git push"',
            "_restore_tracker_text(",
            '_run_git(root, "commit", "-m", subject)',
        ),
        findings,
    )


def _check_no_progress(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "no_progress_updates",
        ARCHITECT_DOCS_FINALIZE,
        (
            code("NO FOLLOWUPS") + ", " + code("NO PROGRESS UPDATES") + ", chat-only prose, skeleton-only текст и placeholder values здесь не являются proof и запрещены.",
            "exact standalone " + code("NO PROCESS IMPROVEMENTS — why: <reason_code>"),
            "в ответе явно напиши " + code("NO PROGRESS UPDATES"),
        ),
        findings,
    )
    _add_missing(
        texts,
        "no_progress_updates",
        MANAGER_PROMPT,
        (
            code("NO FOLLOWUPS") + ", " + code("NO PROGRESS UPDATES") + ", chat-only и skeleton-only output не доказывают этот step.",
        ),
        findings,
    )


def _check_docs_finalize(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_ordered(
        texts,
        "docs_finalize_merge_receipt",
        MANAGER_PROMPT,
        (
            "DOCS_FINALIZE_RECEIPT_PATH=docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md",
            "planveyor_post_merge_receipt_skeleton docs_finalize_receipt",
            "planveyor_arch_docs_general --receipt-path",
            "docs_finalize_receipt_path=$DOCS_FINALIZE_RECEIPT_PATH",
            "planveyor_post_merge_docs_finalize_tick --role Architect",
        ),
        findings,
    )
    _add_missing(
        texts,
        "docs_finalize_merge_receipt",
        ARCHITECT_DOCS_FINALIZE,
        (
            code("**Role:** Architect"),
            code("**Schema version:** review.v1"),
            code("docs_finalize_receipt_path=<DOCS_FINALIZE_RECEIPT_PATH>"),
            code("## Process improvements"),
            "ровно одну",
        ),
        findings,
    )
    _add_missing(
        texts,
        "docs_finalize_merge_receipt",
        DOCS_FINALIZE_ZSH,
        (
            "planveyor_arch_docs_general() {",
            "--receipt-path",
            "DOCS_FINALIZE_RECEIPT_PATH=" + DOLLAR + "{receipt_path}",
            'local expected_readback="docs_finalize_receipt_path=' + DOLLAR + '{receipt_path}"',
            "readback_count != 1 || exact_readback_count != 1",
        ),
        findings,
    )
    _add_function_dispatch(
        texts,
        "docs_finalize_merge_receipt",
        name="planveyor_post_merge_docs_finalize_tick",
        required_fragments=(
            '[[ "$role" == "Architect" ]]',
            "planveyor_post_merge_receipt_preflight docs_finalize",
            "planveyor_merge_tracker_tick step:docs_finalize",
        ),
        executable_pattern=r'^[ \t]*(?!#)planveyor_post_merge_receipt_preflight docs_finalize --role "\$role" --range "\$range" --path "\$receipt_path" \|\| return \$\?\s*$',
        findings=findings,
    )
    manager_text = texts.get(MANAGER_PROMPT)
    if manager_text is not None:
        step_text = _manager_step_slice(manager_text, "step:docs_finalize")
        if step_text is None:
            findings.append(
                Finding(
                    "docs_finalize_merge_receipt",
                    MANAGER_PROMPT,
                    "missing bounded step:docs_finalize Manager section",
                )
            )
        else:
            required = (
                "Запусти только Architect general: " + code("planveyor_arch_docs_general --receipt-path \"$DOCS_FINALIZE_RECEIPT_PATH\"") + ".",
                "Не запускай " + code("planveyor_arch_followups") + " или другой role lane как proof этого tracker step.",
            )
            missing = tuple(fragment for fragment in required if fragment not in step_text)
            if missing:
                findings.append(
                    Finding(
                        "docs_finalize_merge_receipt",
                        MANAGER_PROMPT,
                        "docs-finalize lane policy missing required snippet(s): "
                        + ", ".join(repr(item) for item in missing),
                    )
                )
            step_without_followups_policy = step_text.replace(required[1], "", 1)
            forbidden_lane = None
            for line in step_without_followups_policy.splitlines():
                for lane in re.findall(r"\b(planveyor_arch_[A-Za-z0-9_]+)\b", line):
                    if lane == "planveyor_arch_docs_general":
                        continue
                    forbidden_lane = lane
                    break
                if forbidden_lane is not None:
                    break
            if forbidden_lane is not None:
                findings.append(
                    Finding(
                        "docs_finalize_merge_receipt",
                        MANAGER_PROMPT,
                        f"docs-finalize section launches non-general Architect lane {forbidden_lane}",
                    )
                )


def _check_packetization_range_identity(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "packetization_range_identity",
        MANAGER_PROMPT,
        (
            "Packetization authority is exact full-OID range identity (" + code("source_range") + ", " + code("source_revision") + "), not a plan header.",
            "Run-level " + code("--source-plan") + " is optional provenance;",
            "neither can choose artifacts, close coverage or yield terminal green.",
            code("source_artifacts") + " — единственный source coverage carrier;",
            "mode=" + code("receipt-reuse-only"),
            "planveyor_rollout_packet_create <target_repo> <topic_slug> [--source-plan",
        ),
        findings,
    )
    _add_function_dispatch(
        texts,
        "packetization_range_identity",
        name="planveyor_post_merge_packetization_gate_recover",
        required_fragments=(
            "# Bounded source-local recovery: --range is mandatory; --source-plan is optional provenance.",
            "planveyor_post_merge_packetization_gate_recover --range BASE..HEAD [--source-plan docs/plans/<provenance-plan>.md]",
            "--range|--source-plan)",
            '[[ "$arg" == "--range" ]] && have_range=1',
            "(( have_range )) || {",
            '_planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" --recover "$@"',
        ),
        executable_pattern=r'^[ \t]*(?!#)_planveyor_py_any "\$helper" --content-profile-id "\$content_profile_id" --repo-root "\$root" --recover "\$@"\s*$',
        findings=findings,
    )
    facade_text = texts.get(PLANVEYOR_ZSH)
    if facade_text is not None:
        body = _shell_function_body(facade_text, "planveyor_post_merge_packetization_gate_recover")
        if body is not None and re.search(
            r'(?m)^[ \t]*(?!#)\[\[ "\$arg" == "--range" \]\] && have_range=1\s*$',
            body,
        ) is None:
            findings.append(
                Finding(
                    "packetization_range_identity",
                    PLANVEYOR_ZSH,
                    "recovery facade does not keep --source-plan independent of required --range",
                )
            )
        if body is not None and not _recovery_body_keeps_range_only_contract(body):
            findings.append(
                Finding(
                    "packetization_range_identity",
                    PLANVEYOR_ZSH,
                    "recovery facade adds a source-plan conditional to the supported range-only contract",
                )
            )
    manager_text = texts.get(MANAGER_PROMPT)
    if manager_text is not None:
        packetization_step = _manager_step_slice(manager_text, "step:packetization_gate")
        if packetization_step is not None and _has_legacy_source_artifacts_range_identity(packetization_step):
            findings.append(
                Finding(
                    "packetization_range_identity",
                    MANAGER_PROMPT,
                    "report-context source_artifacts must not be added to exact range identity",
                )
            )
    _add_missing(
        texts,
        "packetization_range_identity",
        PACKETIZATION_GATE,
        (
            'help="Run bounded current-packet recovery for the exact --range; --source-plan is optional provenance."',
            'base = _resolve_commit_oid(repo_root, base_ref, label="BASE")',
            'raise ValueError(f"BASE ' + TICK + "{base}" + TICK + ' must be an ancestor of HEAD ' + TICK + "{head}" + TICK + '{suffix}")',
            'source_plan = "N/A (why=report-only range identity has no single source plan)"',
            'delivery_mode = "receipt-reuse-only"',
        ),
        findings,
    )
    _add_missing(
        texts,
        "packetization_range_identity",
        ROLLOUT_PACKET,
        (
            "CURRENT_DELIVERY_META_KEYS = (",
            '"source_range",',
            '"source_revision",',
            '"source_artifacts",',
            '"target_writable_carriers",',
            "packet_meta.source_range must be a full-OID BASE..HEAD string",
        ),
        findings,
    )


def _check_packetization_target_applicability(texts: dict[str, str], findings: list[Finding]) -> None:
    _add_missing(
        texts,
        "packetization_target_applicability",
        MANAGER_PROMPT,
        (
            "packetization_report_required",
            "target_packet_required",
            "target_source_artifacts",
            "target_writable_carriers",
            code("source_only") + " nonblocking, unknown/malformed/ambiguous applicability fail-closed.",
            "Нельзя применять global sibling union или fixed two-target fanout.",
            "Manager не читает/не пишет sibling repo.",
        ),
        findings,
    )
    _add_missing(
        texts,
        "packetization_target_applicability",
        PACKETIZATION_GATE,
        (
            "EXPLICIT_TARGET_APPLICABILITY",
            "Tests may inject a fixture entry, but production",
            "code never falls back to an inferred sibling obligation.",
            '"target_source_artifacts": list(self.target_source_artifacts)',
            '"target_writable_carriers": list(self.target_writable_carriers)',
            'target_kind="source_only"',
            "unknown target mapping",
            "target-local scope must name one consumer repo",
        ),
        findings,
    )


def check_planveyor_profile_contract(root: Path) -> list[Finding]:
    texts, findings = _read_bundle(root)
    _check_no_default_baseline(texts, findings)
    _check_merge_steps(texts, findings)
    _check_doc_lint(texts, findings)
    _check_docs_hygiene(texts, findings)
    _check_ready_to_push(texts, findings)
    _check_no_progress(texts, findings)
    _check_docs_finalize(texts, findings)
    _check_packetization_range_identity(texts, findings)
    _check_packetization_target_applicability(texts, findings)
    return sorted(findings, key=lambda item: (item.invariant_id, item.rel_path, item.message))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check public Planveyor lifecycle and packet-contract owners.")
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repository root containing the public Planveyor lifecycle bundle.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    findings = check_planveyor_profile_contract(Path(args.root).resolve())
    if findings:
        for finding in findings:
            print(finding.render())
        return 1
    print(f"planveyor-profile-contract: OK files={len(EXACT_BUNDLE)} invariants={len(INVARIANT_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

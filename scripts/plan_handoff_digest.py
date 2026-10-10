#!/usr/bin/env python3
"""Emit a derived Planner/Coder handoff digest from existing truth hosts.

The digest is intentionally read-only and non-authoritative. It summarizes
the plan, linked code draft, oracle readback, exact-bundle preflight and
declared review artifact without replacing any of those carriers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import contract_authority_children
from contract_authority_context import context_for_reader, context_to_json

if TYPE_CHECKING:
    from contract_authority_context import ContractContext


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SCHEMA = "handoff_digest.v1"

STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<status>.+?)\s*$", re.MULTILINE)
CODE_DRAFT_RE = re.compile(r"docs/code_drafts/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
REVIEW_ARTIFACT_RE = re.compile(r"docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)
REVIEW_REQUIRED_STATUS_NORMS = {"ready for arch review", "done", "superseded"}
OK_HOST_STATES = {"ok", "not_required"}
STATE_SEVERITY = ("red_or_inconsistent", "ambiguous", "missing", "unsupported")
NON_BLOCKING_ROUTE_GUARDS = {"", "none", "not_applicable"}
BLOCKING_ORACLE_STATES = {
    "blocker_state": {"blocked"},
    "terminal_ready_state": {"blocked"},
    "owner_qna_readback_state": {"blocked"},
}


@dataclass
class HostResult:
    host: str
    state: str
    reason: str
    path: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": self.state,
            "reason": self.reason,
        }
        if self.path:
            payload["path"] = self.path
        if self.fields:
            payload["fields"] = self.fields
        return payload


OracleRunner = Callable[[Path, Path], HostResult]
BundleRunner = Callable[[Path, Path], HostResult]


def _runtime_root() -> Path:
    """Return the Planveyor runtime that owns this helper."""

    return SCRIPT_DIR.parent.resolve()


def _runtime_launcher() -> Path:
    """Return the sealed child launcher for the owning runtime."""

    return _runtime_root() / "bin" / "planveyor"


def _repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_plan_path(plan_path: str | Path, repo_root: Path) -> Path:
    path = Path(plan_path)
    if path.is_absolute():
        return path
    return repo_root / path


def _unique_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _section_text(text: str, heading: str) -> str:
    wanted = heading.strip().lower()
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip().lower() == wanted:
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _parse_single_status(text: str) -> tuple[str | None, str | None]:
    matches = [match.group("status").strip() for match in STATUS_RE.finditer(text)]
    if not matches:
        return None, "missing"
    if len(set(matches)) > 1:
        return None, "ambiguous"
    return matches[0], None


def _status_norm(status: str | None) -> str:
    return " ".join((status or "").strip().lower().split())


def _extract_json_payload_with_key(text: str, key: str) -> dict[str, Any] | None:
    for match in JSON_FENCE_RE.finditer(text):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get(key), dict):
            return payload
    return None


def _read_plan_host(plan_path: Path, repo_root: Path) -> tuple[HostResult, str | None, str]:
    rel_path = _repo_rel(plan_path, repo_root)
    if not plan_path.exists():
        return (
            HostResult("plan", "missing", "PLAN_PATH does not exist", rel_path),
            None,
            "",
        )
    text = plan_path.read_text(encoding="utf-8")
    status, status_issue = _parse_single_status(text)
    if status_issue == "missing":
        return HostResult("plan", "missing", "single header **Status:** line is missing", rel_path), None, text
    if status_issue == "ambiguous":
        return HostResult("plan", "ambiguous", "multiple conflicting **Status:** lines found", rel_path), None, text
    assert status is not None
    return (
        HostResult(
            "plan",
            "ok",
            "single header status read",
            rel_path,
            {"status": status, "status_norm": _status_norm(status)},
        ),
        status,
        text,
    )


def _read_code_draft_host(plan_text: str, plan_path: Path, repo_root: Path) -> HostResult:
    refs = _unique_preserve_order(CODE_DRAFT_RE.findall(plan_text))
    if not refs:
        return HostResult("code_draft", "missing", "no docs/code_drafts reference found in plan")
    if len(refs) > 1:
        return HostResult("code_draft", "ambiguous", "multiple code draft references found", fields={"refs": refs})

    draft_rel = refs[0]
    draft_path = repo_root / draft_rel
    if not draft_path.exists():
        return HostResult("code_draft", "missing", "linked code draft does not exist", draft_rel)

    draft_text = draft_path.read_text(encoding="utf-8")
    payload = _extract_json_payload_with_key(draft_text, "code_draft_meta")
    if payload is None:
        return HostResult("code_draft", "missing", "code_draft_meta JSON carrier is missing", draft_rel)

    meta = payload["code_draft_meta"]
    targets = meta.get("targets")
    if not isinstance(targets, list) or not targets:
        return HostResult("code_draft", "missing", "code_draft_meta.targets is missing or empty", draft_rel)

    target_paths: list[str] = []
    invalid_targets: list[object] = []
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("path"), str) or not target["path"].strip():
            invalid_targets.append(target)
        else:
            target_paths.append(target["path"].strip())
    if invalid_targets:
        return HostResult(
            "code_draft",
            "ambiguous",
            "code_draft_meta.targets contains invalid entries",
            draft_rel,
            {"invalid_targets": invalid_targets},
        )
    if len(set(target_paths)) != len(target_paths):
        return HostResult(
            "code_draft",
            "ambiguous",
            "code_draft_meta.targets contains duplicate paths",
            draft_rel,
            {"targets": target_paths},
        )

    plan_rel = _repo_rel(plan_path, repo_root)
    meta_plan = meta.get("plan")
    if meta_plan != plan_rel:
        return HostResult(
            "code_draft",
            "red_or_inconsistent",
            "code_draft_meta.plan does not match PLAN_PATH",
            draft_rel,
            {"expected_plan": plan_rel, "actual_plan": meta_plan},
        )

    missing_targets = [target for target in target_paths if not (repo_root / target).exists()]
    if missing_targets:
        return HostResult(
            "code_draft",
            "missing",
            "one or more code_draft_meta.targets paths are missing",
            draft_rel,
            {"missing_targets": missing_targets, "targets": target_paths},
        )

    return HostResult(
        "code_draft",
        "ok",
        "code_draft_meta target inventory read",
        draft_rel,
        {"targets": target_paths},
    )


def _read_review_host(plan_text: str, status: str | None, repo_root: Path) -> HostResult:
    refs = _unique_preserve_order(REVIEW_ARTIFACT_RE.findall(_section_text(plan_text, "Review artifacts")))
    required = _status_norm(status) in REVIEW_REQUIRED_STATUS_NORMS
    if not refs:
        state = "missing" if required else "not_required"
        return HostResult("review_artifact", state, "no declared review artifact reference found")
    if len(refs) > 1:
        return HostResult("review_artifact", "ambiguous", "multiple review artifact references found", fields={"refs": refs})

    review_rel = refs[0]
    review_path = repo_root / review_rel
    if not review_path.exists():
        state = "missing" if required else "not_required"
        reason = "declared review artifact is not materialized"
        if not required:
            reason += " and is not required for current handoff status"
        return HostResult("review_artifact", state, reason, review_rel, {"required": required})

    review_text = review_path.read_text(encoding="utf-8")
    review_status, status_issue = _parse_single_status(review_text)
    if status_issue == "missing":
        return HostResult("review_artifact", "missing", "review artifact status is missing", review_rel)
    if status_issue == "ambiguous":
        return HostResult("review_artifact", "ambiguous", "review artifact has multiple conflicting statuses", review_rel)
    assert review_status is not None
    status_norm = _status_norm(review_status)
    if "blocker" in status_norm or "❌" in review_status:
        return HostResult(
            "review_artifact",
            "red_or_inconsistent",
            "review artifact is red/blocking",
            review_rel,
            {"status": review_status, "status_norm": status_norm},
        )
    if "ok" not in status_norm and "✅" not in review_status:
        return HostResult(
            "review_artifact",
            "ambiguous",
            "review artifact status is not a recognized green verdict",
            review_rel,
            {"status": review_status, "status_norm": status_norm},
        )
    return HostResult(
        "review_artifact",
        "ok",
        "review artifact is green",
        review_rel,
        {"status": review_status, "status_norm": status_norm},
    )


def default_oracle_runner(
    plan_path: Path,
    repo_root: Path,
    *,
    context: ContractContext | None = None,
) -> HostResult:
    authority_context = context_for_reader(repo_root, context) if context is not None else None
    if authority_context is not None and authority_context.state == "engaged":
        assert authority_context.runtime_pin is not None
        oracle_path = authority_context.runtime_pin.runtime_root / "scripts" / "plan_status_oracle.py"
    else:
        launcher = _runtime_launcher()
        if not launcher.is_file() or not os.access(launcher, os.X_OK):
            return HostResult("status_oracle", "unsupported", "bin/planveyor is missing or not executable")
        oracle_path = None
    if oracle_path is not None and not oracle_path.exists():
        return HostResult("status_oracle", "unsupported", "scripts/plan_status_oracle.py is missing")
    plan_arg = _repo_rel(plan_path, repo_root)
    try:
        command = (
            contract_authority_children.python_entry_argv(
                authority_context,
                oracle_path,
                ("--current-state", plan_arg),
                python_executable=sys.executable,
            )
            if authority_context is not None and authority_context.state == "engaged"
            else [
                str(launcher),
                "--project",
                str(repo_root.resolve()),
                "planveyor_plan_status_oracle",
                "--json",
                plan_arg,
            ]
        )
    except contract_authority_children.AuthorityChildLaunchError as exc:
        return HostResult("status_oracle", "red_or_inconsistent", "authority child launch was rejected", fields={"reason": str(exc)})
    run_kwargs: dict[str, Any] = {
        "cwd": repo_root,
        "text": True,
        "capture_output": True,
        "check": False,
    }
    if authority_context is not None and authority_context.state == "engaged":
        child_env = os.environ.copy()
        child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(authority_context)
        run_kwargs["env"] = child_env
    result = subprocess.run(command, **run_kwargs)
    if result.returncode != 0:
        return HostResult(
            "status_oracle",
            "red_or_inconsistent",
            "plan_status_oracle.py returned non-zero",
            fields={"returncode": result.returncode, "stderr": result.stderr.strip()},
        )
    if authority_context is not None and authority_context.state == "engaged":
        # The authority child keeps the historical --current-state protocol.
        fields: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
    else:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return HostResult(
                "status_oracle",
                "red_or_inconsistent",
                "planveyor_plan_status_oracle returned invalid JSON",
                fields={"reason": str(exc)},
            )
        if not isinstance(payload, dict):
            return HostResult(
                "status_oracle",
                "red_or_inconsistent",
                "planveyor_plan_status_oracle returned a non-object JSON payload",
            )
        fields = {
            key: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
            for key, value in payload.items()
        }
    review_state = fields.get("review_readback_state", "").strip()
    review_state_norm = review_state.lower()
    if (
        review_state in {"current_red", "needs_reviewer_rerun", "live_blocker"}
        or "red" in review_state_norm
        or "blocker" in review_state_norm
    ):
        return HostResult("status_oracle", "red_or_inconsistent", "oracle review readback is red", fields=fields)
    if "ambiguous" in review_state:
        return HostResult("status_oracle", "ambiguous", "oracle review readback is ambiguous", fields=fields)
    for field_name, blocking_values in BLOCKING_ORACLE_STATES.items():
        if fields.get(field_name, "").strip().lower() in blocking_values:
            return HostResult(
                "status_oracle",
                "red_or_inconsistent",
                f"oracle {field_name} is blocking",
                fields=fields,
            )
    route_guard_kind = fields.get("route_guard_kind", "").strip()
    if route_guard_kind.lower() not in NON_BLOCKING_ROUTE_GUARDS:
        return HostResult(
            "status_oracle",
            "red_or_inconsistent",
            "oracle route_guard_kind is blocking",
            fields=fields,
        )
    if fields.get("promoted_from_state") not in {"", "not_applicable", "valid"}:
        return HostResult("status_oracle", "red_or_inconsistent", "oracle promoted_from_state is not valid", fields=fields)
    return HostResult("status_oracle", "ok", "plan_status_oracle.py current-state read", fields=fields)


def default_bundle_runner(
    plan_path: Path,
    repo_root: Path,
    *,
    context: ContractContext | None = None,
) -> HostResult:
    authority_context = context_for_reader(repo_root, context) if context is not None else None
    if authority_context is not None and authority_context.state == "engaged":
        assert authority_context.runtime_pin is not None
        planveyor_script = authority_context.runtime_pin.runtime_root / "scripts" / "planveyor.zsh"
    else:
        launcher = _runtime_launcher()
        if not launcher.is_file() or not os.access(launcher, os.X_OK):
            return HostResult("bundle_preflight", "unsupported", "bin/planveyor is missing or not executable")
        planveyor_script = None
    if planveyor_script is not None and not planveyor_script.exists():
        return HostResult("bundle_preflight", "unsupported", "scripts/planveyor.zsh is missing")
    plan_arg = shlex.quote(_repo_rel(plan_path, repo_root))
    try:
        command = (
            contract_authority_children.shell_command(
                authority_context,
                f"planveyor_plan_bundle --preflight {plan_arg}",
            )
            if authority_context is not None and authority_context.state == "engaged"
            else [
                str(launcher),
                "--project",
                str(repo_root.resolve()),
                "planveyor_plan_bundle",
                "--preflight",
                _repo_rel(plan_path, repo_root),
            ]
        )
    except contract_authority_children.AuthorityChildLaunchError as exc:
        return HostResult("bundle_preflight", "red_or_inconsistent", "authority child launch was rejected", fields={"reason": str(exc)})
    run_kwargs: dict[str, Any] = {
        "cwd": repo_root,
        "text": True,
        "capture_output": True,
        "check": False,
    }
    if authority_context is not None and authority_context.state == "engaged":
        child_env = os.environ.copy()
        child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(authority_context)
        run_kwargs["env"] = child_env
    result = subprocess.run(command, **run_kwargs)
    fields = {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if result.returncode == 0:
        return HostResult("bundle_preflight", "ok", "planveyor_plan_bundle --preflight passed", fields=fields)
    combined = f"{result.stdout}\n{result.stderr}".lower()
    state = "missing" if "missing" in combined or "not found" in combined else "red_or_inconsistent"
    return HostResult("bundle_preflight", state, "planveyor_plan_bundle --preflight failed", fields=fields)


def _overall_state(hosts: dict[str, HostResult]) -> str:
    for state in STATE_SEVERITY:
        if any(host.state == state for host in hosts.values()):
            return state
    return "ok"


def build_digest(
    plan_path: str | Path,
    *,
    repo_root: Path = REPO_ROOT,
    oracle_runner: OracleRunner = default_oracle_runner,
    bundle_runner: BundleRunner = default_bundle_runner,
    context: ContractContext | None = None,
) -> dict[str, Any]:
    authority_context = context_for_reader(repo_root, context)
    repo_root = authority_context.project_root
    resolved_plan = _resolve_plan_path(plan_path, repo_root)
    plan_host, status, plan_text = _read_plan_host(resolved_plan, repo_root)
    hosts: dict[str, HostResult] = {"plan": plan_host}

    if plan_text:
        hosts["code_draft"] = _read_code_draft_host(plan_text, resolved_plan, repo_root)
        hosts["review_artifact"] = _read_review_host(plan_text, status, repo_root)
    else:
        hosts["code_draft"] = HostResult("code_draft", "missing", "plan text unavailable")
        hosts["review_artifact"] = HostResult("review_artifact", "missing", "plan text unavailable")

    hosts["status_oracle"] = (
        default_oracle_runner(resolved_plan, repo_root, context=authority_context)
        if oracle_runner is default_oracle_runner
        else oracle_runner(resolved_plan, repo_root)
    )
    hosts["bundle_preflight"] = (
        default_bundle_runner(resolved_plan, repo_root, context=authority_context)
        if bundle_runner is default_bundle_runner
        else bundle_runner(resolved_plan, repo_root)
    )

    oracle_fields = hosts["status_oracle"].fields
    if hosts["plan"].state == "ok" and oracle_fields.get("status_value"):
        plan_status = hosts["plan"].fields.get("status")
        if plan_status != oracle_fields.get("status_value"):
            hosts["status_oracle"] = HostResult(
                "status_oracle",
                "red_or_inconsistent",
                "oracle status_value does not match plan header status",
                fields=oracle_fields,
            )

    state = _overall_state(hosts)
    blockers = [
        {
            "host": host.host,
            "state": host.state,
            "reason": host.reason,
            **({"path": host.path} if host.path else {}),
        }
        for host in hosts.values()
        if host.state not in OK_HOST_STATES
    ]
    code_draft_targets = hosts["code_draft"].fields.get("targets", [])

    return {
        "schema": SCHEMA,
        "state": state,
        "authority": "derived_read_only",
        "non_authoritative_for": [
            "manager_routing",
            "plan_status",
            "target_inventory",
            "review_verdict",
            "exact_bundle",
        ],
        "plan_path": _repo_rel(resolved_plan, repo_root),
        "summary": {
            "status": hosts["plan"].fields.get("status", ""),
            "status_norm": hosts["plan"].fields.get("status_norm", ""),
            "code_draft_targets": code_draft_targets,
            "review_artifact": hosts["review_artifact"].path,
            "oracle_status_norm": oracle_fields.get("status_norm", ""),
            "bundle_preflight_state": hosts["bundle_preflight"].state,
        },
        "truth_hosts": {name: host.to_json() for name, host in hosts.items()},
        "blockers": blockers,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"schema={payload['schema']}",
        f"state={payload['state']}",
        f"authority={payload['authority']}",
        f"plan_path={payload['plan_path']}",
    ]
    summary = payload.get("summary", {})
    lines.extend(
        [
            f"status={summary.get('status', '')}",
            f"status_norm={summary.get('status_norm', '')}",
            f"bundle_preflight_state={summary.get('bundle_preflight_state', '')}",
            f"review_artifact={summary.get('review_artifact', '') or 'N/A'}",
        ]
    )
    targets = summary.get("code_draft_targets") or []
    lines.append("code_draft_targets=" + ",".join(targets))
    if payload.get("blockers"):
        lines.append("blockers:")
        for blocker in payload["blockers"]:
            path = f" path={blocker['path']}" if blocker.get("path") else ""
            lines.append(
                f"- host={blocker['host']} state={blocker['state']}{path} reason={blocker['reason']}"
            )
    else:
        lines.append("blockers=none")
    lines.append("non_authoritative_for=" + ",".join(payload["non_authoritative_for"]))
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_path", help="repo-relative or absolute docs/plans/*.md path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_digest(args.plan_path)
    if args.format == "json":
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(payload))
    return 0 if payload["state"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

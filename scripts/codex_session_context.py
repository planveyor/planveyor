#!/usr/bin/env python3
"""Collect repo-backed provenance/session context for plan-like artifacts.

Normalized envelope guidance for this family:
- source family: `session_context.provenance`
- schema_version: `session_context_provenance.v1`
- ts: literal `captured_at`
- trace_id: literal `thread_id` when available, otherwise explicit `N/A (why=...)`
- event_id/span_id: derived downstream from section kind + `captured_at`; this helper does
  not claim runtime-span semantics on its own
- parent_span_id: `N/A (why=provenance helper exposes thread lineage, not span lineage)`
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



def _authority_module() -> Any:
    """Import the sibling authority parser without consulting a target package."""

    expected = Path(__file__).resolve().with_name("contract_authority_context.py")
    loaded = [
        sys.modules[name]
        for name in ("contract_authority_context", "scripts.contract_authority_context")
        if name in sys.modules
    ]
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str) or Path(origin).resolve(strict=True) != expected:
            raise ImportError("authority module has an unsafe origin")
    if len({id(module) for module in loaded}) > 1:
        raise ImportError("authority module aliases are split")
    if loaded:
        return loaded[0]
    script_dir = str(expected.parent)
    while script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    return importlib.import_module("contract_authority_context")

REPO_ROOT = Path(__file__).resolve().parent.parent
ENVELOPE_SCHEMA_VERSION = "session_context_provenance.v1"
ENVELOPE_EVENT_TYPE = "session_context.provenance"

PLAN_SECTION = "## Plan provenance / session context"
CODE_DRAFT_SECTION = "## Provenance / session context"
PACKET_SECTION = "## Source provenance"

VALID_RELATIONS = {
    "created-here",
    "continued-here",
    "imported-from-packet",
    "manual-backfill",
}
VALID_CAPTURED_FROM = {
    "env",
    "wrapper-session-file",
    "session-stats",
    "packet-import",
    "manual-owner",
}
VALID_LAUNCH_SURFACES = {
    "codex-desktop",
    "codex-cli",
    "manager-collab",
    "manager-custom-pipeline",
}
VALID_SECTIONS = {"plan", "code-draft", "packet"}
VALID_FORMATS = {"markdown", "json", "kv"}
ROLE_TO_SESSION_KEY = {
    "architect": "architect",
    "planner": "planner",
    "coder": "coder",
    "reviewer": "reviewer",
    "manager": "manager",
}


@dataclass(frozen=True)
class ProvenanceContext:
    relation: str
    thread_id: str
    parent_thread_id: str
    session_sid: str
    launch_surface: str
    captured_from: str
    captured_at: str
    authority_context: dict[str, object] | None = None


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_last_non_comment_line(path: Path) -> str:
    if not path.exists():
        return ""
    value = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value = line
    return value


def _read_kv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _normalize_session_key(raw: str) -> str:
    value = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return ROLE_TO_SESSION_KEY.get(value, value)


def _session_key_from_env() -> str:
    return _normalize_session_key(os.environ.get("ROLE", ""))


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _section_exists(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(
        header in text
        for header in (
            PLAN_SECTION,
            CODE_DRAFT_SECTION,
            PACKET_SECTION,
        )
    )


def _n_a(reason: str) -> str:
    return f"N/A (why={reason})"


def _unknown(reason: str) -> str:
    return f"unknown (why={reason})"


def _map_launch_surface(run_receipt: dict[str, str], stats_kv: dict[str, str]) -> str:
    pipeline_mode = run_receipt.get("pipeline_mode", "")
    launch_surface = run_receipt.get("launch_surface", "")
    originator = stats_kv.get("originator", "")
    source = stats_kv.get("source", "")

    if pipeline_mode == "manager_custom_pipeline":
        return "manager-custom-pipeline"
    if pipeline_mode == "collab" or launch_surface == "collab_subagent":
        return "manager-collab"
    if launch_surface == "codex_desktop":
        return "codex-desktop"
    if launch_surface in {"codex_cli", "codex_exec"}:
        return "codex-cli"
    if originator == "codex_desktop":
        return "codex-desktop"
    if originator in {"codex_cli", "codex_exec"} or source == "exec":
        return "codex-cli"
    return _unknown("no env, wrapper receipt, or session stats origin identified the launch surface")


def _query_session_stats(
    root: Path,
    sid: str,
    *,
    stats_script: str,
) -> dict[str, str]:
    if not sid or not Path(stats_script).exists():
        return {}
    result = subprocess.run(
        [
            sys.executable,
            stats_script,
            "--sid",
            sid,
            "--search-all",
            "--mode",
            "quick",
            "--format",
            "kv",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    parsed: dict[str, str] = {}
    for raw in result.stdout.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _resolve_stats_script(root: Path, raw: str) -> str:
    if raw.strip():
        return str(Path(raw).expanduser())
    tooling_script = REPO_ROOT / "scripts" / "codex_session_stats.py"
    if tooling_script.exists():
        return str(tooling_script)
    repo_script = root / "scripts" / "codex_session_stats.py"
    return str(repo_script)


def _infer_relation(args: argparse.Namespace, plan_path: Path | None) -> str:
    if args.relation:
        return args.relation
    if args.packet_path:
        return "imported-from-packet"
    if args.manual_backfill:
        return "manual-backfill"
    if plan_path is not None and _section_exists(plan_path):
        return "continued-here"
    return "created-here"


def _infer_captured_from(
    args: argparse.Namespace,
    *,
    thread_from_env: bool,
    used_wrapper_file: bool,
    used_session_stats: bool,
) -> str:
    if args.captured_from:
        return args.captured_from
    if args.packet_path:
        return "packet-import"
    if args.manual_backfill:
        return "manual-owner"
    if thread_from_env:
        return "env"
    if used_wrapper_file:
        return "wrapper-session-file"
    if used_session_stats:
        return "session-stats"
    return "manual-owner"


def collect_context(args: argparse.Namespace) -> ProvenanceContext:
    root = Path(args.root).expanduser().resolve()
    session_key = _normalize_session_key(args.session_key or _session_key_from_env())
    plan_path = Path(args.plan_path).expanduser().resolve() if args.plan_path else None
    run_receipt_path = (
        Path(args.run_receipt_path).expanduser().resolve()
        if args.run_receipt_path
        else Path(os.environ["RUN_RECEIPT_PATH"]).expanduser().resolve()
        if os.environ.get("RUN_RECEIPT_PATH")
        else None
    )

    thread_from_env = False
    used_wrapper_file = False
    used_session_stats = False

    session_sid = (args.session_sid or "").strip()
    if not session_sid and session_key:
        session_path = root / f".planveyor.session.{session_key}"
        session_sid = _read_last_non_comment_line(session_path)
        used_wrapper_file = bool(session_sid)

    run_receipt = _read_kv_file(run_receipt_path) if run_receipt_path is not None else {}
    used_wrapper_file = used_wrapper_file or bool(run_receipt)
    authority_context = None
    if "authority_context" in run_receipt:
        # Preserve the receipt's entry observation. A later Coder commit must
        # not cause passive provenance collection to replace that observation.
        authority = _authority_module()
        ContractAuthorityError = authority.ContractAuthorityError
        parse_context_envelope = authority.parse_context_envelope

        authority_context = parse_context_envelope(run_receipt["authority_context"])
        if authority_context["project_root"] != str(root):
            raise ContractAuthorityError("receipt_authority_root_mismatch", "receipt authority belongs to a different root")

    thread_id = (args.thread_id or "").strip()
    if not thread_id:
        thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
        thread_from_env = bool(thread_id)
    if not thread_id:
        thread_id = run_receipt.get("thread_id", "").strip()

    parent_thread_id = (args.parent_thread_id or "").strip()
    if not parent_thread_id:
        parent_thread_id = os.environ.get("CODEX_PARENT_THREAD_ID", "").strip()
    if not parent_thread_id:
        parent_thread_id = run_receipt.get("parent_thread_id", "").strip()

    stats_kv: dict[str, str] = {}
    stats_script = _resolve_stats_script(root, args.stats_script)
    if session_sid:
        stats_kv = _query_session_stats(root, session_sid, stats_script=stats_script)
        used_session_stats = bool(stats_kv)
    if not parent_thread_id:
        parent_thread_id = stats_kv.get("parent_thread_id", "").strip()

    launch_surface = (args.launch_surface or "").strip()
    if not launch_surface:
        launch_surface = _map_launch_surface(run_receipt, stats_kv)

    relation = _infer_relation(args, plan_path)
    captured_from = _infer_captured_from(
        args,
        thread_from_env=thread_from_env,
        used_wrapper_file=used_wrapper_file,
        used_session_stats=used_session_stats,
    )
    captured_at = args.captured_at or _now_utc_iso()

    if not thread_id:
        thread_id = _n_a("CODEX_THREAD_ID and wrapper receipts did not expose a live thread id")
    if not parent_thread_id:
        parent_thread_id = _n_a("not exposed by env, wrapper receipts, or session stats")
    if not session_sid:
        if session_key:
            session_sid = _n_a(f".planveyor.session.{session_key} is missing or empty")
        else:
            session_sid = _n_a("session key was not provided and ROLE env is empty")

    return ProvenanceContext(
        relation=relation,
        thread_id=thread_id,
        parent_thread_id=parent_thread_id,
        session_sid=session_sid,
        launch_surface=launch_surface,
        captured_from=captured_from,
        captured_at=captured_at,
        authority_context=authority_context,
    )


def render_markdown(context: ProvenanceContext, *, section: str) -> str:
    if section == "plan":
        lines = [
            PLAN_SECTION,
            f"- Relation: `{context.relation}`",
            f"- Thread ID: `{context.thread_id}`",
            f"- Parent thread ID: `{context.parent_thread_id}`",
            f"- Session SID: `{context.session_sid}`",
            f"- Launch surface: `{context.launch_surface}`",
            f"- Captured from: `{context.captured_from}`",
            f"- Captured at: `{context.captured_at}`",
        ]
    elif section == "code-draft":
        lines = [
            CODE_DRAFT_SECTION,
            "- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`",
            f"- Relation: `{context.relation}`",
            f"- Thread ID: `{context.thread_id}`",
            f"- Parent thread ID: `{context.parent_thread_id}`",
            f"- Session SID: `{context.session_sid}`",
            f"- Launch surface: `{context.launch_surface}`",
            f"- Captured from: `{context.captured_from}`",
            f"- Captured at: `{context.captured_at}`",
        ]
    else:
        lines = [
            PACKET_SECTION,
            f"- Relation: `{context.relation}`",
            f"- Thread ID: `{context.thread_id}`",
            f"- Session SID: `{context.session_sid}`",
            f"- Launch surface: `{context.launch_surface}`",
            f"- Captured from: `{context.captured_from}`",
            f"- Captured at: `{context.captured_at}`",
            "- Target import expectation: `target repo records source packet path/id, one local outcome, and local plan path/no-plan reason before queue_after_import can matter`",
        ]
    if context.authority_context is not None:
        lines.append(f"- Contract authority generation: `{context.authority_context['generation_sha256']}`")
    return "\n".join(lines) + "\n"


def render_kv(context: ProvenanceContext) -> str:
    # Keep the emitted keys aligned with the normalized envelope vocabulary via
    # naming, but do not pretend this helper is a full runtime event source.
    payload = asdict(context)
    order = (
        "relation",
        "thread_id",
        "parent_thread_id",
        "session_sid",
        "launch_surface",
        "captured_from",
        "captured_at",
    )
    lines = [f"{key}={payload[key]}" for key in order]
    if context.authority_context is not None:
        lines.append("authority_context=" + json.dumps(context.authority_context, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect canonical plan/code-draft/packet provenance/session context "
            f"(normalized source family {ENVELOPE_EVENT_TYPE} / {ENVELOPE_SCHEMA_VERSION})."
        )
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root that owns .planveyor.* state files.")
    parser.add_argument("--plan-path", default="", help="Optional plan/code-draft/packet path for relation inference.")
    parser.add_argument("--session-key", default="", help="Role/session key for reading .planveyor.session.<key>.")
    parser.add_argument("--run-receipt-path", default="", help="Optional .planveyor.run_receipt.* path.")
    parser.add_argument("--stats-script", default="", help="Optional path to scripts/codex_session_stats.py.")
    parser.add_argument("--relation", choices=sorted(VALID_RELATIONS), default="", help="Explicit relation override.")
    parser.add_argument("--thread-id", default="", help="Explicit thread id override.")
    parser.add_argument("--parent-thread-id", default="", help="Explicit parent thread id override.")
    parser.add_argument("--session-sid", default="", help="Explicit session sid override.")
    parser.add_argument("--launch-surface", choices=sorted(VALID_LAUNCH_SURFACES), default="", help="Explicit launch-surface override.")
    parser.add_argument("--captured-from", choices=sorted(VALID_CAPTURED_FROM), default="", help="Explicit captured-from override.")
    parser.add_argument("--captured-at", default="", help="Explicit captured-at timestamp override.")
    parser.add_argument("--packet-path", default="", help="Optional packet path; implies imported-from-packet relation unless overridden.")
    parser.add_argument("--manual-backfill", action="store_true", help="Mark this provenance as manual-backfill unless --relation overrides it.")
    parser.add_argument("--section", choices=sorted(VALID_SECTIONS), default="plan", help="Markdown section type to render.")
    parser.add_argument("--format", choices=sorted(VALID_FORMATS), default="markdown", help="Output format.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    ContractAuthorityError = _authority_module().ContractAuthorityError

    try:
        context = collect_context(args)
    except ContractAuthorityError as exc:
        print(f"ERROR: {exc.reason_code}: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        payload = asdict(context)
        if context.authority_context is None:
            payload.pop("authority_context")
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    elif args.format == "kv":
        sys.stdout.write(render_kv(context))
    else:
        sys.stdout.write(render_markdown(context, section=args.section))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

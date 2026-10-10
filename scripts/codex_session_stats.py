#!/usr/bin/env python3
"""Inspect rollout-backed Codex session stats.

Normalized envelope guidance for this fallback family:
- source family: `session_stats.snapshot`
- schema_version: `session_stats_snapshot.v1`
- ts: literal `last_utc` (fallback `created_utc`)
- trace_id: literal `sid`
- event_id/span_id: derived downstream from `sid` + `last_utc`; this helper is a
  truthful fallback snapshot, not a full runtime span carrier
- parent_span_id: `N/A (why=session stats expose parent_thread_id only as thread lineage hint)`
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ENVELOPE_SCHEMA_VERSION = "session_stats_snapshot.v1"
ENVELOPE_EVENT_TYPE = "session_stats.snapshot"


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _default_codex_home() -> Path:
    selected = os.environ.get("PLANVEYOR_CODEX_HOME") or os.environ.get("CODEX_HOME")
    return Path(selected) if selected else Path.home() / ".codex"


def _parse_iso(ts: str) -> datetime | None:
    ts = ts.strip()
    if not ts:
        return None
    # `datetime.fromisoformat` expects offset like +00:00, not "Z".
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone().strftime("%d.%m.%Y %H:%M:%S %z")


def _worktree_id_from_path(path: Path) -> str:
    # Home layout is consumer-owned; recognize only a generic worktree segment.
    return _worktree_id_from_cwd(str(path))


def _worktree_id_from_cwd(cwd: str) -> str:
    if not cwd:
        return ""
    try:
        parts = list(Path(cwd).parts)
    except Exception:
        return ""
    for i in range(len(parts) - 1):
        part = parts[i]
        if part == "worktrees" or part.endswith(".worktrees"):
            return parts[i + 1]
    return ""


def _read_last_line(path: Path) -> str:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return ""
        # Read backwards until we find a newline.
        chunk_size = 4096
        buf = b""
        pos = size
        while pos > 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            buf = f.read(read_size) + buf
            if b"\n" in buf:
                break
        # Split and take the last non-empty line.
        lines = buf.splitlines()
        for line in reversed(lines):
            if line.strip():
                try:
                    return line.decode("utf-8", errors="replace")
                except Exception:
                    return ""
        return ""


def _iter_json_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


def _find_rollout_file(codex_home: Path, sid: str) -> Path | None:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.exists():
        return None

    # Most common naming pattern.
    candidates: list[Path] = list(sessions_dir.rglob(f"rollout-*-{sid}.jsonl"))
    if not candidates:
        # Fallback: older/variant file names.
        candidates = list(sessions_dir.rglob(f"*{sid}*.jsonl"))
    if not candidates:
        return None
    # Pick the newest file by mtime.
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _candidate_homes(primary: Path, search_all: bool) -> list[Path]:
    homes: list[Path] = []

    def add(p: Path) -> None:
        try:
            p = p.expanduser().resolve()
        except Exception:
            p = p.expanduser()
        if p not in homes:
            homes.append(p)

    add(primary)
    if not search_all:
        return homes

    add(Path.home() / ".codex")
    return homes


@dataclass
class SessionStats:
    sid: str
    codex_home: str = ""
    codex_home_worktree: str = ""
    worktree: str = ""
    rollout_path: str = ""
    rollout_size_bytes: int = 0
    line_count: int = 0

    created_utc: str = ""
    created_local: str = ""
    last_utc: str = ""
    last_local: str = ""

    cwd: str = ""
    cli_version: str = ""
    originator: str = ""
    source: str = ""
    agent_nickname: str = ""
    agent_role: str = ""
    parent_thread_id: str = ""
    model: str = ""
    effort: str = ""
    approval_policy: str = ""
    collab_model: str = ""
    collab_effort: str = ""
    model_first: str = ""
    effort_first: str = ""
    approval_policy_first: str = ""
    collab_model_first: str = ""
    collab_effort_first: str = ""
    model_last: str = ""
    effort_last: str = ""
    approval_policy_last: str = ""
    collab_model_last: str = ""
    collab_effort_last: str = ""
    model_chain: str = ""
    effort_chain: str = ""
    approval_policy_chain: str = ""
    collab_model_chain: str = ""
    collab_effort_chain: str = ""

    compactions: int = 0
    turn_aborted: int = 0
    user_messages: int = 0
    agent_messages: int = 0
    agent_reasoning: int = 0

    last_user_text: str = ""
    last_agent_text: str = ""

    token_total: int = 0
    token_input: int = 0
    token_cached_input: int = 0
    token_output: int = 0
    token_reasoning: int = 0
    model_context_window: int = 0


def _build_stats(sid: str, rollout: Path, codex_home: Path, *, mode: str) -> SessionStats:
    stats = SessionStats(sid=sid)
    stats.codex_home = str(codex_home)
    stats.codex_home_worktree = _worktree_id_from_path(codex_home)
    stats.rollout_path = str(rollout)
    try:
        stats.rollout_size_bytes = rollout.stat().st_size
    except Exception:
        stats.rollout_size_bytes = 0

    # Quick timestamps (read last line without scanning the whole file).
    last_line = _read_last_line(rollout)
    last_dt = None
    if last_line:
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict):
                last_dt = _parse_iso(str(obj.get("timestamp") or ""))
        except Exception:
            last_dt = None

    # Read session_meta from the beginning (first N JSON lines).
    created_dt = None
    cwd = ""
    cli_version = ""
    originator = ""
    source = ""
    agent_nickname = ""
    agent_role = ""
    parent_thread_id = ""
    model = ""
    effort = ""
    approval_policy = ""
    collab_model = ""
    collab_effort = ""
    got_meta = False
    got_turn_context = False
    meta_lines = 0
    with rollout.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            meta_lines += 1
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            event_type = obj.get("type")
            if event_type == "session_meta" and not got_meta:
                payload = obj.get("payload") or {}
                if isinstance(payload, dict):
                    created_dt = _parse_iso(str(payload.get("timestamp") or ""))
                    cwd = str(payload.get("cwd") or "")
                    cli_version = str(payload.get("cli_version") or "")
                    originator = str(payload.get("originator") or "")
                    source_raw = payload.get("source")
                    agent_nickname = str(payload.get("agent_nickname") or "")
                    agent_role = str(payload.get("agent_role") or "")
                    if isinstance(source_raw, str):
                        source = source_raw
                    elif source_raw is not None:
                        try:
                            source = json.dumps(source_raw, ensure_ascii=False, sort_keys=True)
                        except Exception:
                            source = str(source_raw)
                    if isinstance(source_raw, dict):
                        subagent = source_raw.get("subagent")
                        if isinstance(subagent, dict):
                            thread_spawn = subagent.get("thread_spawn")
                            if isinstance(thread_spawn, dict):
                                parent_thread_id = str(thread_spawn.get("parent_thread_id") or "")
                got_meta = True
            elif event_type == "turn_context" and not got_turn_context:
                payload = obj.get("payload") or {}
                if isinstance(payload, dict):
                    model = str(payload.get("model") or "")
                    effort = str(payload.get("effort") or "")
                    approval_policy = str(payload.get("approval_policy") or "")
                    collab = payload.get("collaboration_mode")
                    if isinstance(collab, dict):
                        settings = collab.get("settings")
                        if isinstance(settings, dict):
                            collab_model = str(settings.get("model") or "")
                            collab_effort = str(settings.get("reasoning_effort") or "")
                got_turn_context = True
            if (got_meta and got_turn_context) or meta_lines >= 400:
                break

    stats.cwd = cwd
    stats.worktree = stats.codex_home_worktree or _worktree_id_from_cwd(stats.cwd) or "default"
    stats.cli_version = cli_version
    stats.originator = originator
    stats.source = source
    stats.agent_nickname = agent_nickname
    stats.agent_role = agent_role
    stats.parent_thread_id = parent_thread_id
    stats.model = model
    stats.effort = effort
    stats.approval_policy = approval_policy
    stats.collab_model = collab_model
    stats.collab_effort = collab_effort
    stats.model_first = model
    stats.effort_first = effort
    stats.approval_policy_first = approval_policy
    stats.collab_model_first = collab_model
    stats.collab_effort_first = collab_effort
    stats.model_last = model
    stats.effort_last = effort
    stats.approval_policy_last = approval_policy
    stats.collab_model_last = collab_model
    stats.collab_effort_last = collab_effort
    stats.model_chain = model
    stats.effort_chain = effort
    stats.approval_policy_chain = approval_policy
    stats.collab_model_chain = collab_model
    stats.collab_effort_chain = collab_effort

    stats.created_utc = created_dt.isoformat().replace("+00:00", "Z") if created_dt else ""
    stats.created_local = _format_dt(created_dt)
    stats.last_utc = last_dt.isoformat().replace("+00:00", "Z") if last_dt else ""
    stats.last_local = _format_dt(last_dt)

    if mode == "quick":
        return stats

    # Full scan (reliable counters + last token totals).
    last_token_info: dict[str, Any] | None = None
    last_token_ctx_window: int = 0

    model_timeline: list[str] = []
    effort_timeline: list[str] = []
    approval_timeline: list[str] = []
    collab_model_timeline: list[str] = []
    collab_effort_timeline: list[str] = []

    for obj in _iter_json_lines(rollout):
        stats.line_count += 1

        ts = obj.get("timestamp")
        if isinstance(ts, str) and not _is_blank(ts):
            last_dt = _parse_iso(ts) or last_dt

        if obj.get("type") == "turn_context":
            payload = obj.get("payload") or {}
            if isinstance(payload, dict):
                m = str(payload.get("model") or "")
                if m and (not model_timeline or model_timeline[-1] != m):
                    model_timeline.append(m)
                e = str(payload.get("effort") or "")
                if e and (not effort_timeline or effort_timeline[-1] != e):
                    effort_timeline.append(e)
                a = str(payload.get("approval_policy") or "")
                if a and (not approval_timeline or approval_timeline[-1] != a):
                    approval_timeline.append(a)

                collab = payload.get("collaboration_mode")
                if isinstance(collab, dict):
                    settings = collab.get("settings")
                    if isinstance(settings, dict):
                        cm = str(settings.get("model") or "")
                        if cm and (not collab_model_timeline or collab_model_timeline[-1] != cm):
                            collab_model_timeline.append(cm)
                        ce = str(settings.get("reasoning_effort") or "")
                        if ce and (not collab_effort_timeline or collab_effort_timeline[-1] != ce):
                            collab_effort_timeline.append(ce)

        if obj.get("type") != "event_msg":
            continue

        payload = obj.get("payload") or {}
        if not isinstance(payload, dict):
            continue

        ptype = payload.get("type")
        if ptype == "context_compacted":
            stats.compactions += 1
        elif ptype == "turn_aborted":
            stats.turn_aborted += 1
        elif ptype == "user_message":
            stats.user_messages += 1
            msg = payload.get("message") or payload.get("text") or payload.get("content") or ""
            if isinstance(msg, list):
                parts: list[str] = []
                for item in msg:
                    if isinstance(item, dict):
                        for key in ("text", "input_text", "output_text"):
                            v = item.get(key)
                            if isinstance(v, str) and v.strip():
                                parts.append(v)
                msg = " ".join(parts)
            if isinstance(msg, str):
                stats.last_user_text = msg
        elif ptype == "agent_message":
            stats.agent_messages += 1
            msg = payload.get("message") or payload.get("text") or payload.get("content") or ""
            if isinstance(msg, list):
                parts = []
                for item in msg:
                    if isinstance(item, dict):
                        for key in ("text", "input_text", "output_text"):
                            v = item.get(key)
                            if isinstance(v, str) and v.strip():
                                parts.append(v)
                msg = " ".join(parts)
            if isinstance(msg, str):
                stats.last_agent_text = msg
        elif ptype == "agent_reasoning":
            stats.agent_reasoning += 1
        elif ptype == "token_count":
            info = payload.get("info")
            if isinstance(info, dict):
                total = info.get("total_token_usage")
                if isinstance(total, dict):
                    last_token_info = total
                ctx = info.get("model_context_window")
                if isinstance(ctx, int):
                    last_token_ctx_window = ctx

    # If we didn't count lines above (because file was empty), line_count is 0.
    # For consistency, fall back to a cheap wc if needed.
    if stats.line_count == 0:
        try:
            stats.line_count = sum(1 for _ in rollout.open("rb"))
        except Exception:
            stats.line_count = 0

    # Last seen from full scan is more robust than last line parsing.
    stats.last_utc = last_dt.isoformat().replace("+00:00", "Z") if last_dt else stats.last_utc
    stats.last_local = _format_dt(last_dt) if last_dt else stats.last_local

    if last_token_info:
        stats.token_input = int(last_token_info.get("input_tokens") or 0)
        stats.token_cached_input = int(last_token_info.get("cached_input_tokens") or 0)
        stats.token_output = int(last_token_info.get("output_tokens") or 0)
        stats.token_reasoning = int(last_token_info.get("reasoning_output_tokens") or 0)
        stats.token_total = int(last_token_info.get("total_tokens") or 0)
        stats.model_context_window = int(last_token_ctx_window or 0)

    # Prefer the most recent turn_context data (session settings may change across resumes).
    if model_timeline:
        stats.model_first = model_timeline[0]
        stats.model_last = model_timeline[-1]
        stats.model_chain = " -> ".join(model_timeline)
        stats.model = stats.model_last
    if effort_timeline:
        stats.effort_first = effort_timeline[0]
        stats.effort_last = effort_timeline[-1]
        stats.effort_chain = " -> ".join(effort_timeline)
        stats.effort = stats.effort_last
    if approval_timeline:
        stats.approval_policy_first = approval_timeline[0]
        stats.approval_policy_last = approval_timeline[-1]
        stats.approval_policy_chain = " -> ".join(approval_timeline)
        stats.approval_policy = stats.approval_policy_last
    if collab_model_timeline:
        stats.collab_model_first = collab_model_timeline[0]
        stats.collab_model_last = collab_model_timeline[-1]
        stats.collab_model_chain = " -> ".join(collab_model_timeline)
        stats.collab_model = stats.collab_model_last
    if collab_effort_timeline:
        stats.collab_effort_first = collab_effort_timeline[0]
        stats.collab_effort_last = collab_effort_timeline[-1]
        stats.collab_effort_chain = " -> ".join(collab_effort_timeline)
        stats.collab_effort = stats.collab_effort_last

    return stats


def _emit(stats: SessionStats, fmt: str) -> None:
    # The helper stays a fallback snapshot family. Downstream derivation may map
    # it into the normalized envelope, but these outputs must not overclaim live
    # runtime span semantics.
    if fmt == "json":
        print(json.dumps(stats.__dict__, ensure_ascii=False, sort_keys=True))
        return
    # kv
    for k, v in stats.__dict__.items():
        print(f"{k}={v}")


def _extract_sid_from_rollout_path(path: Path) -> str:
    # rollout-YYYY-MM-DDTHH-MM-SS-<sid>.jsonl
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", str(path))
    return m.group(0) if m else ""


@dataclass
class RolloutCandidate:
    sid: str
    codex_home: Path
    rollout: Path
    last_dt: datetime


def _rollout_last_dt(rollout: Path) -> datetime:
    # Prefer last JSON timestamp; fall back to file mtime.
    last_line = _read_last_line(rollout)
    if last_line:
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict):
                dt = _parse_iso(str(obj.get("timestamp") or ""))
                if dt is not None:
                    return dt
        except Exception:
            pass
    try:
        return datetime.fromtimestamp(rollout.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _iter_rollout_candidates(homes: list[Path]) -> Iterable[RolloutCandidate]:
    for home in homes:
        sessions_dir = home / "sessions"
        if not sessions_dir.exists():
            continue
        for rollout in sessions_dir.rglob("rollout-*.jsonl"):
            sid = _extract_sid_from_rollout_path(rollout)
            if not sid:
                continue
            yield RolloutCandidate(sid=sid, codex_home=home, rollout=rollout, last_dt=_rollout_last_dt(rollout))


def _rollout_cwd(rollout: Path) -> str:
    # Cheaply extract session cwd from session_meta (first N JSON lines).
    meta_lines = 0
    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                meta_lines += 1
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "session_meta":
                    if meta_lines >= 200:
                        break
                    continue
                payload = obj.get("payload") or {}
                if isinstance(payload, dict):
                    return str(payload.get("cwd") or "")
                return ""
    except Exception:
        return ""
    return ""


def _emit_table(rows: list[SessionStats]) -> None:
    # Keep it shell-friendly.
    headers = [
        "sid",
        "worktree",
        "line_count",
        "created_local",
        "last_local",
        "compactions",
        "user_messages",
        "agent_messages",
    ]
    print("\t".join(headers))
    for s in rows:
        vals = [
            s.sid,
            s.worktree,
            str(s.line_count),
            s.created_local,
            s.last_local,
            str(s.compactions),
            str(s.user_messages),
            str(s.agent_messages),
        ]
        print("\t".join(vals))


def _shorten(text: str, limit: int = 220) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _emit_tail(rows: list[SessionStats]) -> None:
    print("")
    print("last_messages:")
    for s in rows:
        header = f"{s.sid} [{s.worktree}]"
        print(header)
        if s.last_user_text:
            print(f"  user: {_shorten(s.last_user_text)}")
        else:
            print("  user: (none)")
        if s.last_agent_text:
            print(f"  agent: {_shorten(s.last_agent_text)}")
        else:
            print("  agent: (none)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.description = (
        "Inspect rollout-backed Codex session stats "
        f"(normalized source family {ENVELOPE_EVENT_TYPE} / {ENVELOPE_SCHEMA_VERSION})."
    )
    ap.add_argument("--sid", default="", help="Codex session id (UUID)")
    ap.add_argument("--codex-home", default="", help="Select a home (default: PLANVEYOR_CODEX_HOME, CODEX_HOME, or ~/.codex)")
    ap.add_argument("--search-all", action="store_true", help="Also search the ordinary ~/.codex home")
    ap.add_argument("--mode", choices=["quick", "full"], default="full")
    ap.add_argument("--format", choices=["kv", "json"], default="kv")
    ap.add_argument("--list", action="store_true", help="List recent sessions as a TSV table (ignores --sid)")
    ap.add_argument("--limit", type=int, default=10, help="Limit for --list (default: 10)")
    ap.add_argument("--days", type=int, default=0, help="For --list: show only sessions active in last N days")
    ap.add_argument("--tail", action="store_true", help="For --list: print last user/agent messages under the table")
    ap.add_argument(
        "--cwd-prefix",
        action="append",
        default=[],
        help="For --list: include only sessions whose cwd starts with prefix (can be repeated)",
    )
    ap.add_argument("--only-worktrees", action="store_true", help="For --list: show only sessions with non-default worktree")
    ap.add_argument(
        "--null-sessions",
        action="store_true",
        help="For --list: show only sessions with 0 user + 0 agent messages (default excludes them)",
    )
    args = ap.parse_args(argv)

    codex_home = Path(args.codex_home).expanduser() if args.codex_home else _default_codex_home()
    homes = _candidate_homes(codex_home, args.search_all)

    if args.list:
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=args.days) if args.days and args.days > 0 else None

        candidates = list(_iter_rollout_candidates(homes))
        if cutoff is not None:
            candidates = [c for c in candidates if c.last_dt >= cutoff]

        # IMPORTANT: apply cwd-prefix filtering BEFORE limit. Otherwise `--search-all` can
        # accidentally "crowd out" relevant sessions from other CODEX_HOME roots.
        if args.cwd_prefix:
            prefixes = [p for p in args.cwd_prefix if p]
            if prefixes:
                filtered: list[RolloutCandidate] = []
                for c in candidates:
                    cwd = _rollout_cwd(c.rollout)
                    if cwd and any(cwd.startswith(p) for p in prefixes):
                        filtered.append(c)
                candidates = filtered

        # Sort by last activity.
        candidates.sort(key=lambda c: c.last_dt, reverse=True)

        # IMPORTANT: apply limit AFTER filters that depend on scanning rollouts.
        # Otherwise "null" sessions (no user/agent messages) or non-worktree sessions
        # can crowd out older relevant sessions from the top-N window.
        rows: list[SessionStats] = []
        for c in candidates:
            s = _build_stats(c.sid, c.rollout, c.codex_home, mode=args.mode)
            if args.only_worktrees and (not s.worktree or s.worktree == "default"):
                continue
            if args.null_sessions:
                if (s.user_messages + s.agent_messages) != 0:
                    continue
            else:
                if (s.user_messages + s.agent_messages) == 0:
                    continue
            rows.append(s)
            if args.limit and args.limit > 0 and len(rows) >= args.limit:
                break
        _emit_table(rows)
        # Never emit last-message tail for empty sessions; it's noise and often misleading.
        if args.tail and not args.null_sessions:
            _emit_tail(rows)
        return 0

    sid = args.sid.strip()
    if not sid:
        print("Missing --sid (or pass --list)", file=sys.stderr)
        return 2

    found_home: Path | None = None
    found_rollout: Path | None = None
    for home in homes:
        rollout = _find_rollout_file(home, sid)
        if rollout:
            found_home = home
            found_rollout = rollout
            break

    if not found_home or not found_rollout:
        print(f"Session not found: sid={sid} (searched {len(homes)} CODEX_HOME candidates)", file=sys.stderr)
        return 1

    stats = _build_stats(sid, found_rollout, found_home, mode=args.mode)
    _emit(stats, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Extract repo-native normalized trace events into JSONL and optional SQLite.

The extractor keeps raw receipts/logs as truth sources:
- `.planveyor.run_receipt.*`
- `.planveyor.role_runs/*.json`
- `.planveyor.collab.agent.<role>.log`
- live review artifacts under `docs/code_reviews`, `docs/doc_reviews`, `docs/reviews`

The canonical derived stream is JSONL. SQLite, when requested, is rebuilt from that
JSONL only and must not become a second raw-carrier parser path.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

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

UTC = timezone.utc
# Legacy writers used Moscow time, including stamps with no zone label.
LEGACY_MSK = timezone(timedelta(hours=3))
RUN_RECEIPT_PREFIX = ".planveyor.run_receipt."
ROLE_RUN_RECEIPT_GLOB = ".planveyor.role_runs/*.json"
COLLAB_LOG_PREFIX = ".planveyor.collab.agent."
DEFAULT_JSONL_REL = ".tmp/planveyor_trace_events.jsonl"
DEFAULT_SQLITE_REL = ".tmp/planveyor_trace_index.sqlite"
HEADER_FIELD_RE = re.compile(r"^\*\*(?P<label>[^*]+?):\*\*\s*(?P<value>.+?)\s*$")
PLAN_PATH_RE = re.compile(r"docs/plans/[A-Za-z0-9_./-]+\.md")
BLOCKER_ID_RE = re.compile(r"^\s*###\s+(?P<blocker>B\d+)\)")
SPACE_RE = re.compile(r"\s+")
NON_ID_RE = re.compile(r"[^a-z0-9._-]+")


def _n_a(reason: str) -> str:
    return f"N/A (why={reason})"


def _collapse_space(value: str) -> str:
    return SPACE_RE.sub(" ", value.strip())


def _slug(value: str) -> str:
    normalized = NON_ID_RE.sub("_", value.strip().lower())
    normalized = normalized.strip("._")
    return normalized or "unknown"


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _normalize_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _with_zone(parsed: datetime) -> datetime:
    """Keep unmarked historical stamps at +03:00; new stamps carry an offset."""

    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=LEGACY_MSK)


def _parse_timestamp(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if not value:
        return "", ""

    value = value.replace("(Europe/Moscow)", "").strip()

    candidates: list[datetime] = []
    iso_candidate = value
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        candidates.append(_with_zone(parsed))
    except ValueError:
        pass

    formats = (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M %z",
        "%d.%m.%Y %H:%M:%S %z",
        "%d.%m.%Y %H:%M %z",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M:%S MSK",
        "%d.%m.%Y %H:%M MSK",
        "%Y-%m-%d %H:%M:%S MSK",
        "%Y-%m-%d %H:%M MSK",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        candidates.append(_with_zone(parsed))
        break

    if not candidates:
        return value, value
    normalized = _normalize_iso(candidates[0])
    return normalized, normalized


def _read_kv_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    docs_root = root / "docs"
    for rel_dir in ("code_reviews", "doc_reviews", "reviews"):
        target_dir = docs_root / rel_dir
        if not target_dir.exists():
            continue
        for path in sorted(target_dir.glob("*.md")):
            name = path.name
            if name.startswith("_template") or name == "README.md":
                continue
            yield path


def _review_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = HEADER_FIELD_RE.match(line.strip())
        if not match:
            continue
        label = _collapse_space(match.group("label")).lower()
        fields[label] = _collapse_space(match.group("value"))
    return fields


def _review_title(lines: list[str]) -> str:
    for raw in lines:
        line = raw.strip()
        if line.startswith("# "):
            return _collapse_space(line[2:])
    return ""


def _review_blockers(lines: list[str]) -> list[str]:
    blockers: list[str] = []
    for raw in lines:
        match = BLOCKER_ID_RE.match(raw)
        if match:
            blockers.append(match.group("blocker"))
    return blockers


def _looks_like_live_review_artifact(lines: list[str], fields: dict[str, str]) -> bool:
    return bool(lines and "date" in fields and "status" in fields)


def _is_range_review(path: Path, title: str, fields: dict[str, str]) -> bool:
    title_lower = title.lower()
    return (
        "merge-range" in title_lower
        or "reviewer_range_" in path.name
        or "range" in fields
        or "range=" in fields.get("target", "").lower()
    )


def _review_event_type(path: Path, title: str, fields: dict[str, str]) -> str:
    parts = set(path.parts)
    if "code_reviews" in parts:
        return "review.code.merge_range" if _is_range_review(path, title, fields) else "review.code.single_commit"
    if "doc_reviews" in parts:
        return "review.doc.merge_range" if _is_range_review(path, title, fields) else "review.doc.single_commit"

    name = path.name.lower()
    title_lower = title.lower()
    if "post_merge_audit" in name or "post-merge audit" in title_lower:
        return "review.post_merge_audit"
    if "plan_harvest" in name or "plan harvest" in title_lower:
        return "review.plan_harvest"
    if "merge_notes" in name or "merge notes" in title_lower:
        return "review.merge_notes"
    if title_lower.startswith("review:"):
        suffix = title_lower.split("review:", 1)[1].strip()
        return f"review.{_slug(suffix).replace('.', '_')}"
    return "review.artifact"


def _review_trace_id(
    *,
    rel_path: str,
    text: str,
    result_artifact_lookup: dict[str, str],
    plan_trace_lookup: dict[str, list[str]],
) -> tuple[str, str]:
    matched = result_artifact_lookup.get(rel_path, "").strip()
    if matched:
        return matched, "result_artifact"

    plan_paths = sorted(set(PLAN_PATH_RE.findall(text)))
    for plan_path in plan_paths:
        traces = [candidate for candidate in plan_trace_lookup.get(plan_path, []) if candidate]
        unique = sorted(set(traces))
        if len(unique) == 1:
            return unique[0], f"plan_path:{plan_path}"

    return _n_a("review artifact did not expose a literal trace id and no unique run receipt match was available"), "none"


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str, int]:
    ts = str(event.get("ts") or "")
    source_path = str(event.get("source_path") or "")
    payload = event.get("payload") or {}
    line_no = int(payload.get("line_no") or 0)
    return (ts, source_path, line_no)


def _validated_receipt_authority(payload: dict[str, Any], *, expected_root: Path | None = None) -> dict[str, Any]:
    """Validate embedded evidence without reading current contract/runtime bytes."""
    if "authority_context" not in payload:
        return payload
    authority = _authority_module()
    ContractAuthorityError = authority.ContractAuthorityError
    parse_context_envelope = authority.parse_context_envelope

    raw = payload["authority_context"]
    envelope = parse_context_envelope(raw if isinstance(raw, str) else json.dumps(raw))
    if expected_root is not None and envelope["project_root"] != str(expected_root.resolve()):
        raise ContractAuthorityError("receipt_authority_root_mismatch", "receipt authority belongs to a different root")
    return {**payload, "authority_context": envelope}


def _run_receipt_event(path: Path, root: Path) -> dict[str, Any]:
    payload = _read_kv_file(path)
    receipt_key = path.name[len(RUN_RECEIPT_PREFIX) :]
    ts_raw = payload.get("ts") or payload.get("finished_at") or payload.get("started_at") or ""
    ts, _ = _parse_timestamp(ts_raw)
    started_at = payload.get("started_at") or ts or path.name
    trace_id = payload.get("thread_id") or _n_a("run receipt did not expose thread_id")
    parent_thread_id = payload.get("parent_thread_id") or ""
    receipt_schema = payload.get("schema_version") or "runtime_receipt.v1"
    event_type = payload.get("event_type") or f"run_receipt.{receipt_key}"
    token = _slug(started_at)
    event_id = f"evt.run_receipt.{_slug(receipt_key)}.{token}"
    span_id = f"span.run_receipt.{_slug(receipt_key)}.{token}"
    rel_path = _repo_relative(path, root)
    clean_payload = _validated_receipt_authority(dict(payload), expected_root=root)
    clean_payload["receipt_key"] = receipt_key
    clean_payload["source_parent_thread_id"] = parent_thread_id or _n_a("run receipt did not expose parent_thread_id")
    return {
        "schema_version": receipt_schema,
        "event_type": event_type,
        "ts": ts or ts_raw,
        "event_id": event_id,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": _n_a("run receipt family keeps parent_thread_id as thread lineage only"),
        "source_family": "run_receipt",
        "source_path": rel_path,
        "source_root": str(root),
        "payload": clean_payload,
    }


def _role_run_receipt_event(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("schema_version") != "role_execution_receipt.v1":
        return None

    run_id = str(payload.get("run_id") or path.stem)
    session_key = str(payload.get("session_key") or "unknown")
    ts_raw = str(payload.get("receipt_written_at") or payload.get("finished_at") or payload.get("started_at") or "")
    ts, _ = _parse_timestamp(ts_raw)
    event_id = f"evt.role_execution.{_slug(run_id)}"
    rel_path = _repo_relative(path, root)
    clean_payload = _validated_receipt_authority(dict(payload), expected_root=root)
    clean_payload["source_receipt_path"] = rel_path
    return {
        "schema_version": "role_execution_receipt.v1",
        "event_type": f"role_execution.{_slug(session_key)}",
        "ts": ts or ts_raw,
        "event_id": event_id,
        "trace_id": run_id,
        "span_id": f"span.role_execution.{_slug(run_id)}",
        "parent_span_id": _n_a("role execution receipt does not expose parent span lineage"),
        "source_family": "role_execution_receipt",
        "source_path": rel_path,
        "source_root": str(root),
        "payload": clean_payload,
    }


def _collab_log_events(path: Path, root: Path) -> list[dict[str, Any]]:
    role = path.name[len(COLLAB_LOG_PREFIX) : -len(".log")]
    rel_path = _repo_relative(path, root)
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split("\t")
        if len(parts) < 2:
            continue
        raw_ts = parts[0].strip()
        sid = parts[1].strip()
        event_name = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else "UNCONFIRMED"
        note = parts[3].strip() if len(parts) >= 4 else ""
        ts, _ = _parse_timestamp(raw_ts)
        token = _slug(f"{role}:{ts or raw_ts}:{event_name}:{sid}")
        events.append(
            {
                "schema_version": "collab_agent_log.v1",
                "event_type": f"collab_agent.{event_name}",
                "ts": ts or raw_ts,
                "event_id": f"evt.collab_agent.{token}",
                "trace_id": sid or _n_a("collab log row did not expose a session id"),
                "span_id": f"span.collab_agent.{token}",
                "parent_span_id": _n_a("collab log keeps lineage hints only in the note column"),
                "source_family": "collab_agent_log",
                "source_path": rel_path,
                "source_root": str(root),
                "payload": {
                    "role": role,
                    "sid": sid or _n_a("collab log row did not expose a session id"),
                    "event": event_name,
                    "note": note or "",
                    "line_no": idx,
                    "raw_ts": raw_ts,
                    "raw_columns": len(parts),
                },
            }
        )
    return events


def _review_artifact_event(
    path: Path,
    root: Path,
    *,
    result_artifact_lookup: dict[str, str],
    plan_trace_lookup: dict[str, list[str]],
) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    fields = _review_fields(lines)
    if not _looks_like_live_review_artifact(lines, fields):
        return None

    title = _review_title(lines)
    rel_path = _repo_relative(path, root)
    event_type = _review_event_type(path, title, fields)
    ts_raw = fields.get("date", "")
    ts, _ = _parse_timestamp(ts_raw)
    trace_id, trace_match = _review_trace_id(
        rel_path=rel_path,
        text=text,
        result_artifact_lookup=result_artifact_lookup,
        plan_trace_lookup=plan_trace_lookup,
    )
    basename = path.stem
    event_id = f"evt.review.{_slug(basename)}.{_slug(ts or ts_raw or basename)}"
    span_id = f"span.review.{_slug(rel_path)}"
    return {
        "schema_version": "review_receipt.v1",
        "event_type": event_type,
        "ts": ts or ts_raw,
        "event_id": event_id,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": _n_a("review artifact header does not expose parent span lineage"),
        "source_family": "review_receipt",
        "source_path": rel_path,
        "source_root": str(root),
        "payload": {
            "title": title,
            "status": fields.get("status", ""),
            "target": fields.get("target", ""),
            "spec": fields.get("spec", ""),
            "topic": fields.get("topic", ""),
            "plan_paths": sorted(set(PLAN_PATH_RE.findall(text))),
            "blocker_ids": _review_blockers(lines),
            "trace_match": trace_match,
        },
    }


def extract_root(root: Path) -> list[dict[str, Any]]:
    result_artifact_lookup: dict[str, str] = {}
    plan_trace_lookup: dict[str, list[str]] = {}
    events: list[dict[str, Any]] = []

    for path in sorted(root.glob(f"{RUN_RECEIPT_PREFIX}*")):
        event = _run_receipt_event(path, root)
        events.append(event)
        trace_id = str(event["trace_id"])
        payload = event["payload"]
        result_artifact = str(payload.get("result_artifact") or "")
        plan_path = str(payload.get("plan_path") or "")
        if trace_id and not trace_id.startswith("N/A (why="):
            if result_artifact and result_artifact != "stdout receipt":
                result_artifact_lookup[result_artifact] = trace_id
            if plan_path:
                plan_trace_lookup.setdefault(plan_path, []).append(trace_id)

    for path in sorted(root.glob(ROLE_RUN_RECEIPT_GLOB)):
        event = _role_run_receipt_event(path, root)
        if event is None:
            continue
        events.append(event)
        trace_id = str(event["trace_id"])
        payload = event["payload"]
        result_artifact = str(payload.get("result_artifact") or "")
        plan_path = str(payload.get("target_plan") or "")
        if trace_id and not trace_id.startswith("N/A (why="):
            if result_artifact and result_artifact != "stdout receipt":
                result_artifact_lookup[result_artifact] = trace_id
            if plan_path:
                plan_trace_lookup.setdefault(plan_path, []).append(trace_id)

    for path in sorted(root.glob(f"{COLLAB_LOG_PREFIX}*.log")):
        events.extend(_collab_log_events(path, root))

    for path in _iter_markdown_files(root):
        event = _review_artifact_event(
            path,
            root,
            result_artifact_lookup=result_artifact_lookup,
            plan_trace_lookup=plan_trace_lookup,
        )
        if event is not None:
            events.append(event)

    events.sort(key=_event_sort_key)
    return events


def extract_roots(roots: list[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for root in roots:
        events.extend(extract_root(root))
    events.sort(key=_event_sort_key)
    return events


def _write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def build_sqlite_index(jsonl_path: Path, sqlite_path: Path) -> int:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()
    conn = sqlite3.connect(sqlite_path.as_posix())
    try:
        conn.executescript(
            """
            CREATE TABLE events (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                parent_span_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                source_family TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_root TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX idx_events_ts ON events(ts);
            CREATE INDEX idx_events_trace ON events(trace_id);
            CREATE INDEX idx_events_type ON events(event_type);
            CREATE INDEX idx_events_event_id ON events(event_id);
            """
        )
        inserted = 0
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                event = json.loads(line)
                conn.execute(
                    """
                    INSERT INTO events (
                        event_id, ts, event_type, trace_id, span_id, parent_span_id,
                        schema_version, source_family, source_path, source_root, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(event.get("event_id") or ""),
                        str(event.get("ts") or ""),
                        str(event.get("event_type") or ""),
                        str(event.get("trace_id") or ""),
                        str(event.get("span_id") or ""),
                        str(event.get("parent_span_id") or ""),
                        str(event.get("schema_version") or ""),
                        str(event.get("source_family") or ""),
                        str(event.get("source_path") or ""),
                        str(event.get("source_root") or ""),
                        json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True),
                    ),
                )
                inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def _resolve_roots(raw_roots: list[str]) -> list[Path]:
    if not raw_roots:
        return [Path.cwd().resolve()]
    resolved: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_roots:
        path = Path(raw).expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        resolved.append(path)
    return resolved


def _default_output_path(roots: list[Path], rel_path: str) -> Path:
    return (roots[0] / rel_path).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract normalized repo-native trace events from persisted receipts/logs "
            "into canonical JSONL and optional SQLite."
        )
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Repository root to scan. Repeatable; defaults to the current working directory.",
    )
    parser.add_argument(
        "--jsonl-out",
        default="",
        help=f"Output JSONL path (default: first root/{DEFAULT_JSONL_REL}).",
    )
    parser.add_argument(
        "--sqlite-out",
        default="",
        help=f"Optional SQLite output path (default when --with-sqlite: first root/{DEFAULT_SQLITE_REL}).",
    )
    parser.add_argument(
        "--with-sqlite",
        action="store_true",
        help="Also rebuild the default SQLite index from the emitted JSONL.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    roots = _resolve_roots(args.root)
    for root in roots:
        if not root.exists():
            parser.error(f"Missing root: {root}")

    jsonl_out = Path(args.jsonl_out).expanduser().resolve() if args.jsonl_out else _default_output_path(roots, DEFAULT_JSONL_REL)
    sqlite_requested = args.with_sqlite or bool(args.sqlite_out)
    sqlite_out = (
        Path(args.sqlite_out).expanduser().resolve()
        if args.sqlite_out
        else _default_output_path(roots, DEFAULT_SQLITE_REL)
        if sqlite_requested
        else None
    )

    ContractAuthorityError = _authority_module().ContractAuthorityError

    try:
        events = extract_roots(roots)
    except ContractAuthorityError as exc:
        print(f"ERROR: {exc.reason_code}: {exc}", file=sys.stderr)
        return 2
    _write_jsonl(jsonl_out, events)

    sqlite_rows = 0
    if sqlite_out is not None:
        sqlite_rows = build_sqlite_index(jsonl_out, sqlite_out)

    summary = {
        "roots": [str(root) for root in roots],
        "event_count": len(events),
        "jsonl_out": str(jsonl_out),
        "sqlite_out": str(sqlite_out) if sqlite_out is not None else None,
        "sqlite_rows": sqlite_rows,
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

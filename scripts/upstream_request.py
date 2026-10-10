#!/usr/bin/env python3
"""Source-local helper for target-originated upstream request packets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import process_improvements_collect


# The checkout this helper runs from is the source repository.  An omitted
# --tooling-root must not let a sibling satisfy the source-local guard with ".".
SOURCE_ROOT = Path(__file__).resolve().parent.parent
REQUEST_DIR = Path("docs") / "upstream_packets"
PROCESS_DIR = Path("docs") / "process_improvements"
OWNING_REPO = "planveyor"
OWNING_REPO_NORMALIZED = "planveyor"
REQUEST_STATUSES = ("open", "imported", "decided", "superseded", "cancelled")
HEADER_FIELD_RE = re.compile(r"^\s*\*\*(?P<field>[^*]+):\*\*\s*(?P<value>.+?)\s*$", re.MULTILINE)
CONTEXT_LINK_RE = re.compile(r"^\s*-\s*(?P<field>[^:]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)
CONTEXT_LINKS_HEADING_RE = re.compile(r"^\s*\*\*Context links \(source of truth\):\*\*\s*$", re.MULTILINE)
META_JSON_RE = re.compile(r"## Meta \(machine-readable JSON\)\s*```json\s*(?P<body>\{.*?\})\s*```", re.DOTALL)
REQUEST_FIELD_RE = re.compile(r"^\s*-\s*(?P<field>symptom|process_gap|suggested_fix)\s*:\s*(?P<value>.*?)\s*$")
REQUEST_SECTION_RE = re.compile(r"^\s*##\s+Request\s*$", re.MULTILINE)
H2_RE = re.compile(r"^\s*##\s+", re.MULTILINE)


class PacketError(ValueError):
    """Raised when a request packet is malformed or violates ownership rules."""


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _normalize_repo_id(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        raise PacketError("repo id must be non-empty")
    return text


def _normalize_pointer(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("`").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "null" or lowered.startswith("n/a"):
        return None
    return text


def _ensure_source_local(repo_root: Path, tooling_root: Path) -> None:
    if repo_root.resolve() != tooling_root.resolve():
        raise PacketError(
            "upstream request helpers are source-local only; run them from the planveyor repo, "
            "not from a sibling repo"
        )


def _resolve_request_path(repo_root: Path, packet_path: str) -> Path:
    candidate = Path(packet_path)
    if candidate.is_absolute():
        raise PacketError(f"request path must be repo-relative under {REQUEST_DIR.as_posix()}/")
    if candidate.suffix != ".md":
        raise PacketError(f"request path must end with .md under {REQUEST_DIR.as_posix()}/")

    resolved = (repo_root / candidate).resolve()
    expected_root = (repo_root / REQUEST_DIR).resolve()
    try:
        resolved.relative_to(expected_root)
    except ValueError as exc:
        raise PacketError(f"request path must stay under {REQUEST_DIR.as_posix()}/") from exc
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _read_headers(text: str) -> dict[str, str]:
    return {match.group("field").strip(): match.group("value").strip() for match in HEADER_FIELD_RE.finditer(text)}


def _context_links_block_bounds(text: str) -> tuple[int, int]:
    match = CONTEXT_LINKS_HEADING_RE.search(text)
    if not match:
        raise PacketError("request packet must contain **Context links (source of truth):**")

    start = match.end()
    block_end = start
    seen_context_line = False
    for chunk in text[match.end() :].splitlines(keepends=True):
        line_start = block_end
        line_end = line_start + len(chunk)
        line = chunk.rstrip("\r\n")
        if not line.strip():
            if seen_context_line:
                block_end = line_start
                break
            block_end = line_end
            continue
        if not line.lstrip().startswith("- "):
            block_end = line_start
            break
        seen_context_line = True
        block_end = line_end
    return start, block_end


def _read_context_links(text: str) -> dict[str, str]:
    start, end = _context_links_block_bounds(text)
    context_block = text[start:end]
    links: dict[str, str] = {}
    for match in CONTEXT_LINK_RE.finditer(context_block):
        field = match.group("field").strip()
        if field in links:
            raise PacketError(f"request context links must contain at most one `{field}` line")
        links[field] = match.group("value").strip()
    return links


def _read_meta(text: str) -> dict[str, Any]:
    match = META_JSON_RE.search(text)
    if not match:
        raise PacketError("request packet must contain one machine-readable JSON meta block")
    payload = json.loads(match.group("body"))
    if not isinstance(payload, dict):
        raise PacketError("request packet meta must be a JSON object")
    request_meta = payload.get("upstream_request_meta")
    if not isinstance(request_meta, dict):
        raise PacketError("request packet meta must contain upstream_request_meta object")
    return payload


def _section_body(text: str, heading_re: re.Pattern[str]) -> str:
    match = heading_re.search(text)
    if not match:
        raise PacketError("request packet must contain ## Request section")
    start = match.end()
    next_h2 = H2_RE.search(text, pos=start)
    end = next_h2.start() if next_h2 else len(text)
    return text[start:end].strip()


def _read_request_fields(text: str) -> dict[str, str]:
    body = _section_body(text, REQUEST_SECTION_RE)
    fields: dict[str, str] = {}
    for raw_line in body.splitlines():
        match = REQUEST_FIELD_RE.match(raw_line)
        if match:
            fields[match.group("field")] = match.group("value").strip()
    missing = [field for field in ("symptom", "process_gap", "suggested_fix") if not fields.get(field)]
    if missing:
        raise PacketError(f"request packet is missing required request field(s): {', '.join(missing)}")
    return fields


def _parse_request(packet_path: Path) -> dict[str, Any]:
    text = packet_path.read_text(encoding="utf-8")
    headers = _read_headers(text)
    meta = _read_meta(text)
    request_meta = meta["upstream_request_meta"]
    request_fields = _read_request_fields(text)

    return {
        "text": text,
        "headers": headers,
        "context_links": _read_context_links(text),
        "meta": meta,
        "request_meta": request_meta,
        "request_fields": request_fields,
    }


def _value_from(packet: dict[str, Any], meta_key: str, header_key: str) -> str | None:
    meta_value = _normalize_pointer(packet["request_meta"].get(meta_key))
    if meta_value:
        return meta_value
    header_value = _normalize_pointer(packet["headers"].get(header_key))
    if header_value:
        return header_value
    return _normalize_pointer(packet["context_links"].get(header_key))


def _status(packet: dict[str, Any]) -> str:
    status = _value_from(packet, "status", "Status")
    return str(status or "unknown").strip().lower()


def _validate_request(packet: dict[str, Any]) -> None:
    request_meta = packet["request_meta"]
    headers = packet["headers"]
    context_links = packet["context_links"]
    for field in (
        "id",
        "origin_repo",
        "owning_repo",
        "origin_plan",
        "trigger_ref",
        "status",
        "source_import_plan",
        "source_decision_ref",
        "source_execution_ref",
    ):
        if field not in request_meta:
            raise PacketError(f"upstream_request_meta missing required field: {field}")

    def require_single_header(header_key: str) -> None:
        header_re = re.compile(rf"^\s*\*\*{re.escape(header_key)}:\*\*\s*.+?$", flags=re.MULTILINE)
        count = len(header_re.findall(str(packet["text"])))
        if count != 1:
            raise PacketError(f"request header must contain exactly one **{header_key}:** field")

    require_single_header("Origin repo")
    require_single_header("Owning repo")
    require_single_header("Status")

    def require_carrier_meta_match(
        *,
        header_key: str,
        meta_key: str,
        normalizer: Any = lambda value: str(value).strip(),
        carrier: dict[str, str] | None = None,
        carrier_name: str = "header",
        required: bool = False,
        strict: bool = False,
    ) -> None:
        carrier = carrier if carrier is not None else headers
        raw_header_value = carrier.get(header_key)
        header_value = _normalize_pointer(raw_header_value)
        meta_value = _normalize_pointer(request_meta.get(meta_key))
        if required and (raw_header_value is None or not str(raw_header_value).strip()):
            raise PacketError(f"{carrier_name} {header_key} is required")
        if strict:
            normalized_header = None if header_value is None else normalizer(header_value)
            normalized_meta = None if meta_value is None else normalizer(meta_value)
            if normalized_header != normalized_meta:
                raise PacketError(
                    f"{carrier_name} {header_key} `{raw_header_value}` disagrees with upstream_request_meta.{meta_key} `{request_meta.get(meta_key)}`"
                )
            return
        if header_value and meta_value and normalizer(header_value) != normalizer(meta_value):
            raise PacketError(
                f"{carrier_name} {header_key} `{header_value}` disagrees with upstream_request_meta.{meta_key} `{meta_value}`"
            )

    require_carrier_meta_match(header_key="Origin repo", meta_key="origin_repo", normalizer=_normalize_repo_id)
    require_carrier_meta_match(header_key="Owning repo", meta_key="owning_repo", normalizer=_normalize_repo_id)
    require_carrier_meta_match(
        header_key="Status",
        meta_key="status",
        normalizer=lambda value: str(value).strip().lower(),
    )
    require_carrier_meta_match(
        header_key="Origin plan",
        meta_key="origin_plan",
        carrier=context_links,
        carrier_name="context link",
        required=True,
        strict=True,
    )
    require_carrier_meta_match(
        header_key="Trigger ref",
        meta_key="trigger_ref",
        carrier=context_links,
        carrier_name="context link",
        required=True,
        strict=True,
    )
    require_carrier_meta_match(
        header_key="Source import plan",
        meta_key="source_import_plan",
        carrier=context_links,
        carrier_name="context link",
        required=True,
        strict=True,
    )
    require_carrier_meta_match(
        header_key="Source decision ref",
        meta_key="source_decision_ref",
        carrier=context_links,
        carrier_name="context link",
        required=True,
        strict=True,
    )
    require_carrier_meta_match(
        header_key="Source execution ref",
        meta_key="source_execution_ref",
        carrier=context_links,
        carrier_name="context link",
        required=True,
        strict=True,
    )

    owning_repo = _normalize_repo_id(_value_from(packet, "owning_repo", "Owning repo"))
    if owning_repo != OWNING_REPO_NORMALIZED:
        raise PacketError(f"request owning_repo must be `{OWNING_REPO}`; found `{owning_repo}`")

    origin_repo = _normalize_repo_id(_value_from(packet, "origin_repo", "Origin repo"))
    if origin_repo == OWNING_REPO_NORMALIZED:
        raise PacketError("origin_repo must be a target repo, not planveyor")

    status = _status(packet)
    if status not in REQUEST_STATUSES:
        raise PacketError(f"unknown upstream request status `{status}`")


def _request_summary(packet_path: Path, repo_root: Path) -> dict[str, Any]:
    packet = _parse_request(packet_path)
    _validate_request(packet)
    request_meta = packet["request_meta"]
    request_fields = packet["request_fields"]
    return {
        "path": _repo_relative(packet_path, repo_root),
        "absolute_path": str(packet_path.resolve()),
        "id": str(request_meta.get("id") or packet_path.stem),
        "origin_repo": _normalize_repo_id(_value_from(packet, "origin_repo", "Origin repo")),
        "owning_repo": OWNING_REPO,
        "origin_plan": str(_value_from(packet, "origin_plan", "Origin plan") or ""),
        "trigger_ref": str(_value_from(packet, "trigger_ref", "Trigger ref") or ""),
        "status": _status(packet),
        "source_import_plan": _normalize_pointer(request_meta.get("source_import_plan")),
        "source_decision_ref": _normalize_pointer(request_meta.get("source_decision_ref")),
        "source_execution_ref": _normalize_pointer(request_meta.get("source_execution_ref")),
        "requested_source_canon_path": _normalize_pointer(request_meta.get("requested_source_canon_path")),
        "symptom": request_fields["symptom"],
        "process_gap": request_fields["process_gap"],
        "suggested_fix": request_fields["suggested_fix"],
    }


def _request_query_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_path": summary["path"],
        "id": summary["id"],
        "origin_repo": summary["origin_repo"],
        "status": summary["status"],
        "origin_plan": summary["origin_plan"],
        "trigger_ref": summary["trigger_ref"],
        "source_import_plan": summary["source_import_plan"],
        "source_decision_ref": summary["source_decision_ref"],
        "source_execution_ref": summary["source_execution_ref"],
    }


def _lint_finding(*, file: str, code: str, message: str) -> dict[str, str]:
    return {
        "file": file,
        "code": code,
        "message": message,
    }


def _default_lint_paths(repo_root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    request_root = repo_root / REQUEST_DIR
    if not request_root.is_dir():
        return [], [
            _lint_finding(
                file=REQUEST_DIR.as_posix(),
                code="missing_directory",
                message=f"request directory does not exist: {REQUEST_DIR.as_posix()}",
            )
        ]
    return [
        packet_path
        for packet_path in sorted(request_root.glob("*.md"))
        if packet_path.name != "_template.md"
    ], []


def _explicit_lint_paths(repo_root: Path, raw_paths: list[str]) -> tuple[list[Path], list[dict[str, str]]]:
    request_root = (repo_root / REQUEST_DIR).resolve()
    paths: list[Path] = []
    findings: list[dict[str, str]] = []
    seen: set[Path] = set()

    def add_packet(path: Path) -> None:
        resolved = path.resolve()
        if resolved.name == "_template.md" or resolved in seen:
            return
        seen.add(resolved)
        paths.append(resolved)

    for raw_path in raw_paths:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            findings.append(
                _lint_finding(
                    file=raw_path,
                    code="invalid_path",
                    message=f"lint path must be repo-relative under {REQUEST_DIR.as_posix()}/",
                )
            )
            continue

        resolved = (repo_root / candidate).resolve()
        try:
            resolved.relative_to(request_root)
        except ValueError:
            findings.append(
                _lint_finding(
                    file=raw_path,
                    code="invalid_path",
                    message=f"lint path must stay under {REQUEST_DIR.as_posix()}/",
                )
            )
            continue

        if not resolved.exists():
            findings.append(
                _lint_finding(
                    file=candidate.as_posix(),
                    code="missing",
                    message=f"request path does not exist: {candidate.as_posix()}",
                )
            )
            continue

        if resolved.is_dir():
            for packet_path in sorted(resolved.glob("*.md")):
                add_packet(packet_path)
            continue

        if not resolved.is_file() or resolved.suffix != ".md":
            findings.append(
                _lint_finding(
                    file=candidate.as_posix(),
                    code="invalid_path",
                    message=f"lint path must be a .md file or directory under {REQUEST_DIR.as_posix()}/",
                )
            )
            continue

        add_packet(resolved)

    return paths, findings


def _lint_scope(repo_root: Path, raw_paths: list[str]) -> tuple[list[Path], list[dict[str, str]]]:
    if raw_paths:
        return _explicit_lint_paths(repo_root, raw_paths)
    return _default_lint_paths(repo_root)


def _lint_packet(packet_path: Path, repo_root: Path) -> tuple[dict[str, str], dict[str, str] | None]:
    file_ref = _repo_relative(packet_path, repo_root)
    try:
        packet = _parse_request(packet_path)
        _validate_request(packet)
    except FileNotFoundError as exc:
        return {"file": file_ref, "status": "error"}, _lint_finding(
            file=file_ref,
            code="missing",
            message=str(exc),
        )
    except json.JSONDecodeError as exc:
        return {"file": file_ref, "status": "error"}, _lint_finding(
            file=file_ref,
            code="invalid_json",
            message=str(exc),
        )
    except PacketError as exc:
        return {"file": file_ref, "status": "error"}, _lint_finding(
            file=file_ref,
            code="invalid_packet",
            message=str(exc),
        )
    return {"file": file_ref, "status": "ok"}, None


def _replace_status_header(text: str, status: str) -> str:
    status_header_re = re.compile(r"^(\s*)\*\*Status:\*\*\s*.+?$", flags=re.MULTILINE)
    if len(status_header_re.findall(text)) != 1:
        raise PacketError("request header must contain exactly one **Status:** field")
    next_text, count = status_header_re.subn(rf"\1**Status:** {status}", text, count=1)
    if count != 1:
        raise PacketError("request header must contain exactly one **Status:** field")
    return next_text


def _replace_context_line(text: str, label: str, value: str) -> str:
    start, end = _context_links_block_bounds(text)
    context_block = text[start:end]
    next_block, count = re.subn(
        rf"^(\s*)- {re.escape(label)}: .*$",
        rf"\1- {label}: `{value}`",
        context_block,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise PacketError(f"request context links must contain one `{label}` line")
    return f"{text[:start]}{next_block}{text[end:]}"


def _replace_meta_json(text: str, meta: dict[str, Any]) -> str:
    rendered = json.dumps(meta, indent=2, ensure_ascii=False)
    replacement = f"## Meta (machine-readable JSON)\n```json\n{rendered}\n```"
    next_text, count = META_JSON_RE.subn(replacement, text, count=1)
    if count != 1:
        raise PacketError("request packet must contain one machine-readable JSON meta block")
    return next_text


def _append_import_receipt(text: str, *, imported_at: str, import_ref: str) -> str:
    receipt = f"- [{imported_at}] source import: source_import_plan=`{import_ref}`; approval=`not decided`."
    stripped = text.rstrip()
    if re.search(r"^## Source Import Receipts\s*$", stripped, flags=re.MULTILINE):
        return f"{stripped}\n{receipt}\n"
    return f"{stripped}\n\n## Source Import Receipts\n{receipt}\n"


def _append_ack_receipt(
    text: str,
    *,
    acknowledged_at: str,
    source_decision_ref: str | None,
    source_execution_ref: str | None,
) -> str:
    fields = []
    if source_decision_ref:
        fields.append(f"source_decision_ref=`{source_decision_ref}`")
    if source_execution_ref:
        fields.append(f"source_execution_ref=`{source_execution_ref}`")
    receipt = f"- [{acknowledged_at}] source ack: {'; '.join(fields)}."
    stripped = text.rstrip()
    if re.search(r"^## Source Ack Receipts\s*$", stripped, flags=re.MULTILINE):
        return f"{stripped}\n{receipt}\n"
    return f"{stripped}\n\n## Source Ack Receipts\n{receipt}\n"


def _preflight_import_render(packet: dict[str, Any]) -> None:
    meta = dict(packet["meta"])
    request_meta = dict(packet["request_meta"])
    request_meta["status"] = "imported"
    request_meta["source_import_plan"] = "__preflight_import_ref__"
    request_meta["source_imported_at"] = "2000-01-01T00:00:00"
    meta["upstream_request_meta"] = request_meta

    next_text = _replace_status_header(str(packet["text"]), "imported")
    next_text = _replace_context_line(next_text, "Source import plan", "__preflight_import_ref__")
    _replace_meta_json(next_text, meta)


def _render_imported_request(packet: dict[str, Any], *, import_ref: str, now: datetime) -> str:
    if _status(packet) != "open":
        raise PacketError(f"request status must be open before import; found `{_status(packet)}`")

    meta = dict(packet["meta"])
    request_meta = dict(packet["request_meta"])
    request_meta["status"] = "imported"
    request_meta["source_import_plan"] = import_ref
    request_meta["source_imported_at"] = now.astimezone().isoformat(timespec="seconds")
    meta["upstream_request_meta"] = request_meta

    next_text = _replace_status_header(str(packet["text"]), "imported")
    next_text = _replace_context_line(next_text, "Source import plan", import_ref)
    next_text = _replace_meta_json(next_text, meta)
    return _append_import_receipt(next_text, imported_at=now.astimezone().strftime("%Y-%m-%d %H:%M %z"), import_ref=import_ref)


def _render_acknowledged_request(
    packet: dict[str, Any],
    *,
    source_decision_ref: str | None,
    source_execution_ref: str | None,
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    status = _status(packet)
    if status not in {"imported", "decided"}:
        raise PacketError(f"request status must be imported or decided before ack; found `{status}`")

    normalized_decision = _normalize_pointer(source_decision_ref)
    normalized_execution = _normalize_pointer(source_execution_ref)
    if source_decision_ref is not None and normalized_decision is None:
        raise PacketError("source_decision_ref must be a non-empty pointer")
    if source_execution_ref is not None and normalized_execution is None:
        raise PacketError("source_execution_ref must be a non-empty pointer")
    if normalized_decision is None and normalized_execution is None:
        raise PacketError("ack requires --source-decision-ref, --source-execution-ref, or both")

    current_decision = _normalize_pointer(packet["request_meta"].get("source_decision_ref"))
    current_execution = _normalize_pointer(packet["request_meta"].get("source_execution_ref"))
    effective_decision = normalized_decision if normalized_decision is not None else current_decision
    effective_execution = normalized_execution if normalized_execution is not None else current_execution
    if normalized_execution is not None and effective_decision is None:
        raise PacketError("source_execution_ref requires source_decision_ref to be set first")

    meta = dict(packet["meta"])
    request_meta = dict(packet["request_meta"])
    request_meta["status"] = "decided"
    request_meta["source_decision_ref"] = effective_decision
    request_meta["source_execution_ref"] = effective_execution
    request_meta["source_acknowledged_at"] = now.astimezone().isoformat(timespec="seconds")
    meta["upstream_request_meta"] = request_meta

    next_text = _replace_status_header(str(packet["text"]), "decided")
    if normalized_decision is not None:
        next_text = _replace_context_line(next_text, "Source decision ref", normalized_decision)
    if normalized_execution is not None:
        next_text = _replace_context_line(next_text, "Source execution ref", normalized_execution)
    next_text = _replace_meta_json(next_text, meta)
    next_text = _append_ack_receipt(
        next_text,
        acknowledged_at=now.astimezone().strftime("%Y-%m-%d %H:%M %z"),
        source_decision_ref=normalized_decision,
        source_execution_ref=normalized_execution,
    )
    return next_text, request_meta


def _process_improvement_text(summary: dict[str, Any], *, owner: str, promotion_class: str) -> str:
    return "\n".join(
        [
            "## Process improvements",
            "### Suggestion 1",
            f"- symptom: {summary['symptom']}",
            f"- process_gap: {summary['process_gap']}",
            f"- suggested_fix: {summary['suggested_fix']}",
            f"- owner: {owner}",
            f"- promotion_class: {promotion_class}",
            f"- trigger_ref: {summary['trigger_ref']}",
            f"- source_ref: {summary['path']}",
            "",
        ]
    )


def _import_ref_from_collect_payload(payload: dict[str, Any]) -> str:
    created = payload.get("created")
    if isinstance(created, list) and created:
        row = created[0]
        return f"{row['file']}#{row['entry_id']}"

    duplicates = payload.get("duplicates")
    if isinstance(duplicates, list) and duplicates:
        row = duplicates[0]
        return f"{row['file']}#{row['entry_id']}"

    backlog_files = payload.get("backlog_files")
    if isinstance(backlog_files, list) and backlog_files:
        return str(backlog_files[0])
    raise PacketError("process-improvement import did not create or find a backlog row")


def _normalize_status_filters(raw_statuses: list[str] | None) -> set[str]:
    statuses = {status.strip().lower() for status in (raw_statuses or ["open"]) if status.strip()}
    unknown = sorted(status for status in statuses if status != "all" and status not in REQUEST_STATUSES)
    if unknown:
        raise PacketError(f"unknown upstream request status filter: {', '.join(unknown)}")
    return statuses or {"open"}


def _load_request_corpus(repo_root: Path) -> list[dict[str, Any]]:
    request_root = repo_root / REQUEST_DIR
    if not request_root.is_dir():
        raise FileNotFoundError(request_root)

    summaries: list[dict[str, Any]] = []
    for packet_path in sorted(request_root.glob("*.md")):
        if packet_path.name == "_template.md":
            continue
        summaries.append(_request_summary(packet_path, repo_root))
    return summaries


def cmd_show(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    try:
        _ensure_source_local(repo_root, tooling_root)
        packet_path = _resolve_request_path(repo_root, args.packet_path)
        packet = _parse_request(packet_path)
        _validate_request(packet)
    except (FileNotFoundError, PacketError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    if args.raw:
        print(packet["text"], end="" if str(packet["text"]).endswith("\n") else "\n")
        return 0

    summary = _request_summary(packet_path, repo_root)
    print(f"Upstream request: {summary['path']}")
    print(f"Request id: {summary['id']}")
    print(f"Origin repo: {summary['origin_repo']}")
    print(f"Owning repo: {summary['owning_repo']}")
    print(f"Origin plan: {summary['origin_plan']}")
    print(f"Trigger ref: {summary['trigger_ref']}")
    print(f"Status: {summary['status']}")
    print(f"Source import plan: {summary['source_import_plan'] or 'N/A'}")
    print(f"Source decision ref: {summary['source_decision_ref'] or 'N/A'}")
    print(f"Source execution ref: {summary['source_execution_ref'] or 'N/A'}")
    print(f"Symptom: {summary['symptom']}")
    print(f"Process gap: {summary['process_gap']}")
    print(f"Suggested fix: {summary['suggested_fix']}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    now = datetime.now()
    try:
        _ensure_source_local(repo_root, tooling_root)
        packet_path = _resolve_request_path(repo_root, args.packet)
        packet = _parse_request(packet_path)
        _validate_request(packet)
        summary = _request_summary(packet_path, repo_root)
        if summary["status"] != "open":
            raise PacketError(f"request status must be open before import; found `{summary['status']}`")
        _preflight_import_render(packet)
        improvement_text = _process_improvement_text(
            summary,
            owner=args.owner,
            promotion_class=args.promotion_class,
        )
        if args.dry_run:
            print("Mode: dry-run (no file written)")
            print(improvement_text, end="")
            return 0

        payload = process_improvements_collect.collect_process_improvements(
            project_root=repo_root,
            role=args.role,
            source_ref=summary["path"],
            text=improvement_text,
        )
        import_ref = _import_ref_from_collect_payload(payload)

        created = payload.get("created")
        if isinstance(created, list) and created:
            first = created[0]
            process_improvements_collect.update_backlog_entry(
                project_root=repo_root,
                backlog_path=repo_root / str(first["file"]),
                entry_id=str(first["entry_id"]),
                triage_note="auto-imported from upstream request packet",
            )

        next_text = _render_imported_request(packet, import_ref=import_ref, now=now)
    except (FileNotFoundError, PacketError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))
    except process_improvements_collect.authority_context.ContractAuthorityError as exc:
        # The collector refuses writes outside the invoking authority context;
        # report that refusal instead of letting it escape as a crash.
        return _fail(f"{exc.reason_code}: {exc}")

    packet_path.write_text(next_text, encoding="utf-8")
    print(f"Upstream request: {_repo_relative(packet_path, repo_root)}")
    print(f"Status: imported")
    print(f"Source import plan: {import_ref}")
    print("Result: source-local process-improvement row recorded; source decision remains pending")
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    now = datetime.now()
    try:
        _ensure_source_local(repo_root, tooling_root)
        packet_path = _resolve_request_path(repo_root, args.packet)
        packet = _parse_request(packet_path)
        _validate_request(packet)
        next_text, request_meta = _render_acknowledged_request(
            packet,
            source_decision_ref=args.source_decision_ref,
            source_execution_ref=args.source_execution_ref,
            now=now,
        )
        if args.dry_run:
            print(next_text, end="" if next_text.endswith("\n") else "\n")
            return 0
    except (FileNotFoundError, PacketError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    packet_path.write_text(next_text, encoding="utf-8")
    print(f"Upstream request: {_repo_relative(packet_path, repo_root)}")
    print("Status: decided")
    print(f"Source decision ref: {request_meta.get('source_decision_ref') or 'N/A'}")
    print(f"Source execution ref: {request_meta.get('source_execution_ref') or 'N/A'}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    try:
        _ensure_source_local(repo_root, tooling_root)
        statuses = _normalize_status_filters(args.status)
        summaries = _load_request_corpus(repo_root)
    except (FileNotFoundError, PacketError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    include_all = "all" in statuses
    origin_filter = _normalize_repo_id(args.origin_repo) if args.origin_repo else None
    rows = [
        _request_query_row(summary)
        for summary in summaries
        if (include_all or str(summary["status"]).lower() in statuses)
        and (origin_filter is None or summary["origin_repo"] == origin_filter)
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "repo_root": str(repo_root),
                    "statuses": sorted(statuses),
                    "origin_repo": origin_filter,
                    "count": len(rows),
                    "requests": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    status_label = "all" if include_all else "|".join(sorted(statuses))
    print("Upstream request query")
    print(f"Repo root: {repo_root}")
    print(f"Status filter: {status_label}")
    if origin_filter:
        print(f"Origin repo filter: {origin_filter}")
    print(f"Matching requests: {len(rows)}")
    for idx, row in enumerate(rows, 1):
        print(
            "{idx:02d}. {path} id={id} origin={origin} status={status}".format(
                idx=idx,
                path=row["request_path"],
                id=row["id"],
                origin=row["origin_repo"],
                status=row["status"],
            )
        )
        print(f"    source_import_plan={row['source_import_plan'] or 'N/A'}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    try:
        _ensure_source_local(repo_root, tooling_root)
    except PacketError as exc:
        return _fail(str(exc))

    packet_paths, findings = _lint_scope(repo_root, args.paths)
    files: list[dict[str, str]] = []
    for packet_path in packet_paths:
        file_entry, finding = _lint_packet(packet_path, repo_root)
        files.append(file_entry)
        if finding is not None:
            findings.append(finding)

    if args.json:
        print(
            json.dumps(
                {
                    "repo_root": str(repo_root),
                    "files": files,
                    "findings": findings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1 if findings else 0

    print(f"upstream-request-lint: {'FAIL' if findings else 'OK'}")
    print(f"files checked: {len(files)}")
    print(f"findings: {len(findings)}")
    for finding in findings:
        print(f"- {finding['file']}: {finding['code']}: {finding['message']}")
    return 1 if findings else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Source-local upstream request helper surfaces.")
    parser.add_argument("--repo-root", default=".", help="Repo root for source-local operations.")
    parser.add_argument(
        "--tooling-root",
        default=str(SOURCE_ROOT),
        help="Expected planveyor root (default: the checkout that contains this helper).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Show a source-local upstream request packet.")
    show_parser.add_argument("packet_path", help="Repo-relative path under docs/upstream_packets/.")
    show_parser.add_argument("--raw", action="store_true", help="Print raw packet content.")
    show_parser.set_defaults(func=cmd_show)

    import_parser = subparsers.add_parser("import", help="Import an open upstream request into source-local process improvements.")
    import_parser.add_argument("--packet", required=True, help="Repo-relative path under docs/upstream_packets/.")
    import_parser.add_argument("--role", default="Coder", help="Role recorded on the process-improvement row.")
    import_parser.add_argument("--owner", default="Architect", help="Owner for the imported process-improvement row.")
    import_parser.add_argument("--promotion-class", default="canon_update", help="Process-improvement promotion_class.")
    import_parser.add_argument("--dry-run", action="store_true", help="Print the structured row without writing files.")
    import_parser.set_defaults(func=cmd_import)

    ack_parser = subparsers.add_parser("ack", help="Acknowledge source-side decision/execution refs on a packet.")
    ack_parser.add_argument("--packet", required=True, help="Repo-relative path under docs/upstream_packets/.")
    ack_parser.add_argument("--source-decision-ref", help="Repo-backed source decision pointer to record.")
    ack_parser.add_argument("--source-execution-ref", help="Repo-backed source execution pointer to record.")
    ack_parser.add_argument("--dry-run", action="store_true", help="Render the updated packet without writing it.")
    ack_parser.set_defaults(func=cmd_ack)

    query_parser = subparsers.add_parser("query", help="List source-local upstream requests by explicit fields.")
    query_parser.add_argument(
        "--status",
        action="append",
        choices=(*REQUEST_STATUSES, "all"),
        help="Request status to include. Defaults to open; pass more than once for multiple statuses.",
    )
    query_parser.add_argument("--origin-repo", help="Filter by origin repo id.")
    query_parser.add_argument("--json", action="store_true", help="Print machine-readable query JSON.")
    query_parser.set_defaults(func=cmd_query)

    lint_parser = subparsers.add_parser("lint", help="Read-only lint for upstream request packets.")
    lint_parser.add_argument(
        "paths",
        nargs="*",
        metavar="PACKET_OR_DIR",
        help="Repo-relative packet file or directory under docs/upstream_packets/. Defaults to the live corpus.",
    )
    lint_parser.add_argument("--json", action="store_true", help="Print machine-readable lint JSON.")
    lint_parser.set_defaults(func=cmd_lint)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

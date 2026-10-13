#!/usr/bin/env python3
"""
Batch-read documents for retrieval pipelines.

Note: paths are resolved relative to the current working directory (repo root),
because this tool is executed from other repos via shell wrappers.

Inputs:
- glob/path args
- `@filelist` (one entry per line)
- `-` (stdin file list)

In a target with i18n/pairs.json, glob matches skip Russian copies `*.ru.md`;
an explicit path to a copy is still read.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from docs_context_registry import contexts_for_path, format_contexts_inline
# The same rule keeps Russian copies out of the derived index.
from docs_index_build import translation_copy_suffixes


REPO_ROOT = Path.cwd().resolve()
DOCS_ROOT = (REPO_ROOT / "docs").resolve()

DEFAULT_MAX_BYTES = 200_000
DEFAULT_MAX_BYTES_PER_DOC = 40_000
DEFAULT_MAX_FILES = 30
DEFAULT_READ_LOG = ".tmp/planveyor_docs_retrieve_reads.jsonl"
READ_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_READ_LOG"
LOG_DISABLE_VALUES = {"0", "off", "false", "no", "disable", "disabled"}

USAGE_ERROR = 2
RUNTIME_ERROR = 1


class UsageError(RuntimeError):
    """CLI usage/arguments error."""


class RuntimeDataError(RuntimeError):
    """Runtime/data/path error."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse integration
        raise UsageError(message)


def _scan_wants_json(argv: list[str]) -> bool:
    for i, arg in enumerate(argv):
        if arg == "--format" and i + 1 < len(argv) and argv[i + 1].strip().lower() == "json":
            return True
        if arg.startswith("--format=") and arg.split("=", 1)[1].strip().lower() == "json":
            return True
    return False


def _json_dump(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_read_event_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"read-{stamp}-{uuid.uuid4().hex[:8]}"


def _resolve_read_log_path(args: argparse.Namespace) -> Path | None:
    if bool(getattr(args, "no_read_log", False)):
        return None

    arg_value = str(getattr(args, "read_log", "") or "").strip()
    if arg_value:
        return Path(arg_value)

    env_value = os.environ.get(READ_LOG_ENV_VAR)
    if env_value is not None:
        env_value = env_value.strip()
        if env_value.lower() in LOG_DISABLE_VALUES:
            return None
        if env_value:
            return Path(env_value)

    return Path(DEFAULT_READ_LOG)


def _materialize_log_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _append_jsonl(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
    except OSError:
        return


def _file_log_rows(docs_out: list[dict]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for doc in docs_out:
        truncated = doc.get("truncated") or {}
        rows.append(
            {
                "path": str(doc.get("path") or ""),
                "returned_lines": int(doc.get("lines") or 0),
                "returned_bytes": int(doc.get("bytes") or 0),
                "truncated": bool(truncated.get("per_doc") or truncated.get("total"))
                if isinstance(truncated, dict)
                else False,
            }
        )
    return rows


def _emit_batch_read_event(
    log_path: Path | None,
    *,
    status: str,
    inputs_count: int,
    files: list[dict[str, object]],
    emitted_files: int,
    skipped_inputs_count: int,
    tail_dropped_files_count: int,
    skipped_total_cap_count: int,
    total_bytes: int,
    error_code: str | None = None,
) -> str:
    event_id = _new_read_event_id()
    payload: dict[str, object] = {
        "event_id": event_id,
        "event_type": "docs_multi_get.read",
        "ts": _utc_ts(),
        "tool": "docs_multi_get",
        "cwd": Path.cwd().as_posix(),
        "repo": Path.cwd().name,
        "status": status,
        "inputs_count": int(inputs_count),
        "files": files,
        "emitted_files": int(emitted_files),
        "skipped_inputs_count": int(skipped_inputs_count),
        "tail_dropped_files_count": int(tail_dropped_files_count),
        "skipped_total_cap_count": int(skipped_total_cap_count),
        "total_bytes": int(total_bytes),
    }
    if error_code:
        payload["error_code"] = error_code
    _append_jsonl(log_path, payload)
    return event_id


def _emit_json_error(*, code: str, message: str, meta: dict | None = None) -> None:
    _json_dump(
        {
            "ok": False,
            "files": [],
            "meta": meta or {},
            "error": {"code": code, "message": message},
        }
    )


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def _build_parser() -> _Parser:
    parser = _Parser(description="Batch-read docs files with safety caps.")
    parser.add_argument(
        "inputs",
        nargs="*",
        help="glob/path entries, @filelist, or '-' for stdin (i18n registry opts globs out of *.ru.md copies)",
    )
    parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Max total output bytes (default: {DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--max-bytes-per-doc",
        type=int,
        default=DEFAULT_MAX_BYTES_PER_DOC,
        help=f"Max bytes per doc before total cap (default: {DEFAULT_MAX_BYTES_PER_DOC})",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=f"Max number of files to process (default: {DEFAULT_MAX_FILES})",
    )
    parser.add_argument("--allow-non-docs", action="store_true", help="Allow paths outside docs/**")
    parser.add_argument("--no-context", action="store_true", help="Disable path-prefix context hints in output")
    parser.add_argument(
        "--read-log",
        default="",
        help=(
            f"Read/open telemetry JSONL path. Default: {DEFAULT_READ_LOG}; "
            f"override via {READ_LOG_ENV_VAR}=PATH"
        ),
    )
    parser.add_argument("--no-read-log", action="store_true", help="Disable read/open telemetry for this invocation")
    return parser


def _read_filelist_lines(raw: str) -> list[str]:
    out: list[str] = []
    for line in raw.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        out.append(entry)
    return out


def _looks_like_glob(entry: str) -> bool:
    return any(ch in entry for ch in ("*", "?", "["))


def _resolve_path(raw_path: str, *, allow_non_docs: bool) -> tuple[Path, str]:
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    else:
        p = p.resolve()

    if not allow_non_docs:
        try:
            p.relative_to(DOCS_ROOT)
        except ValueError as e:
            raise RuntimeDataError(f"forbidden_path:{raw_path}") from e

    if not p.exists():
        raise RuntimeDataError(f"not_found:{raw_path}")
    if not p.is_file():
        raise RuntimeDataError(f"not_file:{raw_path}")

    try:
        rel_path = p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel_path = p.as_posix()
    return p, rel_path


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _truncate_bytes(data: bytes, *, max_bytes: int) -> tuple[bytes, bool]:
    if len(data) <= max_bytes:
        return data, False
    return data[:max_bytes], True


def _parse_reason(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        return "runtime_error", raw
    reason, detail = raw.split(":", 1)
    return reason, detail


def _run(argv: list[str], *, parser: _Parser) -> int:
    wants_json = _scan_wants_json(argv)
    try:
        args = parser.parse_args(argv)
        wants_json = wants_json or (str(args.format) == "json")
    except UsageError as e:
        if wants_json:
            _emit_json_error(code="usage_error", message=str(e))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
            print(parser.format_usage().strip(), file=sys.stderr)
        return USAGE_ERROR

    read_log_path = _materialize_log_path(_resolve_read_log_path(args))

    if int(args.max_bytes) < 1 or int(args.max_bytes_per_doc) < 1 or int(args.max_files) < 1:
        msg = "--max-bytes, --max-bytes-per-doc, --max-files must be >= 1"
        _emit_batch_read_event(
            read_log_path,
            status="usage_error",
            inputs_count=len(args.inputs),
            files=[],
            emitted_files=0,
            skipped_inputs_count=0,
            tail_dropped_files_count=0,
            skipped_total_cap_count=0,
            total_bytes=0,
            error_code="invalid_caps",
        )
        if wants_json:
            _emit_json_error(code="usage_error", message=msg)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR

    raw_inputs = list(args.inputs)
    if not raw_inputs:
        if sys.stdin.isatty():
            msg = "no inputs provided (pass paths/globs/@filelist or pipe stdin)"
            if wants_json:
                _emit_json_error(code="usage_error", message=msg)
            else:
                print(f"ERROR: {msg}", file=sys.stderr)
            return USAGE_ERROR
        raw_inputs = ["-"]

    skipped_inputs: list[dict[str, str]] = []
    expanded_entries: list[str] = []
    stdin_consumed = False

    for token in raw_inputs:
        if token == "-":
            if stdin_consumed:
                skipped_inputs.append({"input": "-", "reason": "stdin_already_consumed"})
                continue
            if sys.stdin.isatty():
                msg = "stdin is empty/tty for '-' input"
                if wants_json:
                    _emit_json_error(code="usage_error", message=msg)
                else:
                    print(f"ERROR: {msg}", file=sys.stderr)
                return USAGE_ERROR
            stdin_raw = sys.stdin.read()
            stdin_entries = _read_filelist_lines(stdin_raw)
            if not stdin_entries:
                msg = "stdin list is empty"
                if wants_json:
                    _emit_json_error(code="usage_error", message=msg)
                else:
                    print(f"ERROR: {msg}", file=sys.stderr)
                return USAGE_ERROR
            expanded_entries.extend(stdin_entries)
            stdin_consumed = True
            continue

        if token.startswith("@"):
            list_path = token[1:]
            try:
                list_text = Path(list_path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped_inputs.append({"input": token, "reason": "filelist_not_found"})
                continue
            file_entries = _read_filelist_lines(list_text)
            if not file_entries:
                skipped_inputs.append({"input": token, "reason": "filelist_empty"})
                continue
            expanded_entries.extend(file_entries)
            continue

        expanded_entries.append(token)

    resolved_paths: list[tuple[Path, str]] = []
    seen_rel: set[str] = set()
    copy_suffixes = translation_copy_suffixes(REPO_ROOT)
    for entry in expanded_entries:
        candidates: list[str]
        from_glob = _looks_like_glob(entry)
        if from_glob:
            # Keep deterministic order.
            candidates = sorted(glob.glob(entry, recursive=True))
            if not candidates:
                skipped_inputs.append({"input": entry, "reason": "no_match"})
                continue
        else:
            candidates = [entry]

        for candidate in candidates:
            try:
                abs_path, rel_path = _resolve_path(candidate, allow_non_docs=bool(args.allow_non_docs))
            except RuntimeDataError as e:
                reason, detail = _parse_reason(str(e))
                skipped_inputs.append({"input": detail, "reason": reason})
                continue
            if rel_path in seen_rel:
                continue
            if from_glob and rel_path.endswith(copy_suffixes):
                # A pattern must not return both versions of a document.
                skipped_inputs.append({"input": rel_path, "reason": "translation_copy"})
                continue
            seen_rel.add(rel_path)
            resolved_paths.append((abs_path, rel_path))

    if not resolved_paths:
        msg = "no readable files after input expansion"
        if wants_json:
            _emit_json_error(code="runtime_error", message=msg, meta={"skipped_inputs": skipped_inputs})
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
            for item in skipped_inputs:
                _warn(f"skip input={item['input']} reason={item['reason']}")
        _emit_batch_read_event(
            read_log_path,
            status="error",
            inputs_count=len(raw_inputs),
            files=[],
            emitted_files=0,
            skipped_inputs_count=len(skipped_inputs),
            tail_dropped_files_count=0,
            skipped_total_cap_count=0,
            total_bytes=0,
            error_code="no_readable_files",
        )
        return RUNTIME_ERROR

    tail_dropped_files: list[str] = []
    if len(resolved_paths) > int(args.max_files):
        tail_dropped_files = [rel for _, rel in resolved_paths[int(args.max_files) :]]
        resolved_paths = resolved_paths[: int(args.max_files)]

    docs_out: list[dict] = []
    skipped_total_cap: list[str] = []
    total_bytes = 0
    total_cap_reached = False

    for abs_path, rel_path in resolved_paths:
        try:
            raw_text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped_inputs.append({"input": rel_path, "reason": "read_error"})
            continue

        data = raw_text.encode("utf-8")
        data, per_doc_truncated = _truncate_bytes(data, max_bytes=int(args.max_bytes_per_doc))

        remaining = int(args.max_bytes) - total_bytes
        if remaining <= 0:
            skipped_total_cap.append(rel_path)
            total_cap_reached = True
            continue

        data, total_truncated = _truncate_bytes(data, max_bytes=remaining)
        if total_truncated:
            total_cap_reached = True

        content = data.decode("utf-8", errors="ignore")
        emitted_bytes = len(content.encode("utf-8"))
        total_bytes += emitted_bytes

        docs_out.append(
            {
                "path": rel_path,
                "contexts": [] if bool(args.no_context) else contexts_for_path(rel_path),
                "content": content,
                "bytes": emitted_bytes,
                "lines": _count_lines(content),
                "truncated": {
                    "per_doc": bool(per_doc_truncated),
                    "total": bool(total_truncated),
                },
            }
        )

    if not docs_out:
        msg = "no readable files emitted (caps/read errors)"
        meta = {
            "skipped_inputs": skipped_inputs,
            "tail_dropped_files": tail_dropped_files,
            "skipped_total_cap": skipped_total_cap,
        }
        if wants_json:
            _emit_json_error(code="runtime_error", message=msg, meta=meta)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
            for item in skipped_inputs:
                _warn(f"skip input={item['input']} reason={item['reason']}")
        _emit_batch_read_event(
            read_log_path,
            status="error",
            inputs_count=len(raw_inputs),
            files=[],
            emitted_files=0,
            skipped_inputs_count=len(skipped_inputs),
            tail_dropped_files_count=len(tail_dropped_files),
            skipped_total_cap_count=len(skipped_total_cap),
            total_bytes=total_bytes,
            error_code="no_emitted_files",
        )
        return RUNTIME_ERROR

    meta = {
        "max_bytes": int(args.max_bytes),
        "max_bytes_per_doc": int(args.max_bytes_per_doc),
        "max_files": int(args.max_files),
        "resolved_files": len(resolved_paths),
        "emitted_files": len(docs_out),
        "total_bytes": total_bytes,
        "tail_dropped_files": tail_dropped_files,
        "skipped_total_cap": skipped_total_cap,
        "skipped_inputs": skipped_inputs,
        "total_cap_reached": total_cap_reached,
    }
    read_event_id = _emit_batch_read_event(
        read_log_path,
        status="ok",
        inputs_count=len(raw_inputs),
        files=_file_log_rows(docs_out),
        emitted_files=len(docs_out),
        skipped_inputs_count=len(skipped_inputs),
        tail_dropped_files_count=len(tail_dropped_files),
        skipped_total_cap_count=len(skipped_total_cap),
        total_bytes=total_bytes,
    )

    if str(args.format) == "json":
        _json_dump(
            {
                "ok": True,
                "files": docs_out,
                "meta": {**meta, "read_event_id": read_event_id},
            }
        )
        return 0

    print(
        "docs_multi_get "
        f"(event_id={read_event_id}, files={len(docs_out)}, total_bytes={total_bytes}/{int(args.max_bytes)}, "
        f"max_bytes_per_doc={int(args.max_bytes_per_doc)}, max_files={int(args.max_files)})"
    )
    if tail_dropped_files:
        print(f"- tail_dropped_files={len(tail_dropped_files)}")
    if skipped_total_cap:
        print(f"- skipped_total_cap={len(skipped_total_cap)}")
    if skipped_inputs:
        print(f"- skipped_inputs={len(skipped_inputs)}")
    print()

    for doc in docs_out:
        path = str(doc["path"])
        content = str(doc["content"])
        trunc = doc["truncated"]
        print(f"### `{path}`")
        print(
            f"- bytes={int(doc['bytes'])}, lines={int(doc['lines'])}, "
            f"truncated_per_doc={'yes' if trunc['per_doc'] else 'no'}, "
            f"truncated_total={'yes' if trunc['total'] else 'no'}"
        )
        print(f"- Context: {format_contexts_inline(doc.get('contexts', []))}")
        print("```text")
        if content:
            sys.stdout.write(content)
            if not content.endswith("\n"):
                sys.stdout.write("\n")
        print("```")
        print()

    if tail_dropped_files:
        _warn(
            f"max-files cap reached: dropped {len(tail_dropped_files)} files "
            "(increase --max-files to include them)"
        )
    if skipped_total_cap:
        _warn(
            f"total bytes cap reached: skipped {len(skipped_total_cap)} files "
            "(increase --max-bytes to include them)"
        )
    if skipped_inputs:
        for item in skipped_inputs:
            _warn(f"skip input={item['input']} reason={item['reason']}")

    return 0


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        return _run(argv, parser=parser)
    except BrokenPipeError:  # pragma: no cover - shell pipeline behavior
        return 0
    except Exception as e:  # pragma: no cover - defensive top-level hardening
        wants_json = _scan_wants_json(argv)
        msg = f"unexpected error: {type(e).__name__}: {e}"
        if wants_json:
            try:
                _emit_json_error(code="runtime_error", message=msg)
            except Exception:
                print(f"ERROR: {msg}", file=sys.stderr)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

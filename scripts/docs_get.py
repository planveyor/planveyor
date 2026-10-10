#!/usr/bin/env python3
"""
Read a single document for retrieval pipelines.

Note: paths are resolved relative to the current working directory (repo root),
because this tool is executed from other repos via shell wrappers.

Input:
- `<path>`
- `<path:line>` (jump hint from docs_retrieve)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from docs_context_registry import contexts_for_path, format_contexts_inline


REPO_ROOT = Path.cwd().resolve()
DOCS_ROOT = (REPO_ROOT / "docs").resolve()

DEFAULT_MAX_BYTES = 40_000
DEFAULT_MAX_LINES = 400
DEFAULT_WINDOW_LINES = 81  # ~ +/-40 around line
DEFAULT_FROM_LINE_LINES = 80
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


def _emit_read_event(
    log_path: Path | None,
    *,
    status: str,
    path: str | None,
    mode: str,
    from_line: int | None,
    to_line: int | None,
    returned_lines: int,
    returned_bytes: int,
    truncated: bool,
    output_format: str,
    error_code: str | None = None,
) -> str:
    event_id = _new_read_event_id()
    payload: dict[str, object] = {
        "event_id": event_id,
        "event_type": "docs_get.read",
        "ts": _utc_ts(),
        "tool": "docs_get",
        "cwd": Path.cwd().as_posix(),
        "repo": Path.cwd().name,
        "status": status,
        "path": path or "",
        "mode": mode,
        "from_line": from_line,
        "to_line": to_line,
        "returned_lines": int(returned_lines),
        "returned_bytes": int(returned_bytes),
        "truncated": bool(truncated),
        "format": output_format,
    }
    if error_code:
        payload["error_code"] = error_code
    _append_jsonl(log_path, payload)
    return event_id


def _emit_json_error(*, code: str, message: str, path: str | None = None) -> None:
    _json_dump(
        {
            "ok": False,
            "path": path,
            "content": "",
            "error": {"code": code, "message": message},
        }
    )


def _build_parser() -> _Parser:
    parser = _Parser(description="Read a single docs file (full or around line) with safety caps.")
    parser.add_argument("target", help="Path or jump hint path:line")
    parser.add_argument("--from-line", type=int, default=None, help="Start line (1-based)")
    parser.add_argument("--lines", type=int, default=None, help="Number of lines to read")
    parser.add_argument("--full", action="store_true", help="Read full file (still capped by max-lines/max-bytes)")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Max output size in bytes (default: {DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Max output lines (default: {DEFAULT_MAX_LINES})",
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
    parser.add_argument("--format", choices=["text", "md", "json"], default="text", help="Output format")
    return parser


def _parse_target(target: str) -> tuple[str, int | None]:
    if ":" not in target:
        return target, None
    path_part, maybe_line = target.rsplit(":", 1)
    if path_part and maybe_line.isdigit():
        return path_part, int(maybe_line)
    return target, None


def _resolve_path(raw_path: str, *, allow_non_docs: bool) -> tuple[Path, str]:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    else:
        path = path.resolve()

    if not allow_non_docs:
        try:
            path.relative_to(DOCS_ROOT)
        except ValueError as e:
            raise RuntimeDataError(f"forbidden path outside docs/**: {raw_path}") from e

    if not path.exists():
        raise RuntimeDataError(f"file not found: {raw_path}")
    if not path.is_file():
        raise RuntimeDataError(f"not a file: {raw_path}")

    try:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel_path = path.as_posix()
    return path, rel_path


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _truncate_bytes(text: str, *, max_bytes: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text, False
    cut = data[:max_bytes]
    return cut.decode("utf-8", errors="ignore"), True


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

    if args.full and (args.from_line is not None or args.lines is not None):
        msg = "--full cannot be combined with --from-line/--lines"
        _emit_read_event(
            read_log_path,
            status="usage_error",
            path=str(args.target),
            mode="unknown",
            from_line=args.from_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="invalid_args",
        )
        if wants_json:
            _emit_json_error(code="usage_error", message=msg, path=str(args.target))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR
    if args.from_line is not None and int(args.from_line) < 1:
        msg = "--from-line must be >= 1"
        _emit_read_event(
            read_log_path,
            status="usage_error",
            path=str(args.target),
            mode="unknown",
            from_line=args.from_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="invalid_from_line",
        )
        if wants_json:
            _emit_json_error(code="usage_error", message=msg, path=str(args.target))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR
    if args.lines is not None and int(args.lines) < 1:
        msg = "--lines must be >= 1"
        _emit_read_event(
            read_log_path,
            status="usage_error",
            path=str(args.target),
            mode="unknown",
            from_line=args.from_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="invalid_lines",
        )
        if wants_json:
            _emit_json_error(code="usage_error", message=msg, path=str(args.target))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR
    if int(args.max_bytes) < 1 or int(args.max_lines) < 1:
        msg = "--max-bytes and --max-lines must be >= 1"
        _emit_read_event(
            read_log_path,
            status="usage_error",
            path=str(args.target),
            mode="unknown",
            from_line=args.from_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="invalid_caps",
        )
        if wants_json:
            _emit_json_error(code="usage_error", message=msg, path=str(args.target))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR

    raw_path, jump_line = _parse_target(str(args.target))
    try:
        abs_path, rel_path = _resolve_path(raw_path, allow_non_docs=bool(args.allow_non_docs))
    except RuntimeDataError as e:
        _emit_read_event(
            read_log_path,
            status="error",
            path=raw_path,
            mode="unknown",
            from_line=args.from_line or jump_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="runtime_error",
        )
        if wants_json:
            _emit_json_error(code="runtime_error", message=str(e), path=str(args.target))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        full_text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        msg = f"failed to read file: {e}"
        _emit_read_event(
            read_log_path,
            status="error",
            path=rel_path,
            mode="unknown",
            from_line=args.from_line or jump_line,
            to_line=None,
            returned_lines=0,
            returned_bytes=0,
            truncated=False,
            output_format=str(args.format),
            error_code="read_error",
        )
        if wants_json:
            _emit_json_error(code="runtime_error", message=msg, path=rel_path)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return RUNTIME_ERROR

    file_lines = full_text.splitlines(keepends=True)
    mode = "full"
    start_line = 1
    selected_lines: list[str]

    if args.full:
        selected_lines = file_lines
    else:
        if args.from_line is not None:
            mode = "from_line"
            start_line = int(args.from_line)
            requested_lines = int(args.lines) if args.lines is not None else DEFAULT_FROM_LINE_LINES
        elif jump_line is not None:
            mode = "around"
            requested_lines = int(args.lines) if args.lines is not None else DEFAULT_WINDOW_LINES
            start_line = max(1, int(jump_line) - (requested_lines // 2))
        else:
            msg = "for non-full mode provide path:line or --from-line"
            _emit_read_event(
                read_log_path,
                status="usage_error",
                path=rel_path,
                mode="unknown",
                from_line=None,
                to_line=None,
                returned_lines=0,
                returned_bytes=0,
                truncated=False,
                output_format=str(args.format),
                error_code="missing_line_selector",
            )
            if wants_json:
                _emit_json_error(code="usage_error", message=msg, path=str(args.target))
            else:
                print(f"ERROR: {msg}", file=sys.stderr)
            return USAGE_ERROR

        selected_lines = file_lines[start_line - 1 : start_line - 1 + requested_lines]

    selected_text = "".join(selected_lines)
    selected_lines_before_caps = _count_lines(selected_text)
    selected_bytes_before_caps = len(selected_text.encode("utf-8"))

    by_lines = False
    if selected_lines_before_caps > int(args.max_lines):
        by_lines = True
        selected_lines = selected_lines[: int(args.max_lines)]
        selected_text = "".join(selected_lines)

    selected_text, by_bytes = _truncate_bytes(selected_text, max_bytes=int(args.max_bytes))

    returned_lines = _count_lines(selected_text)
    returned_bytes = len(selected_text.encode("utf-8"))
    to_line = (start_line + returned_lines - 1) if returned_lines > 0 else (start_line - 1)
    truncated = bool(by_lines or by_bytes)
    contexts = [] if bool(args.no_context) else contexts_for_path(rel_path)
    context_inline = format_contexts_inline(contexts)
    read_event_id = _emit_read_event(
        read_log_path,
        status="ok",
        path=rel_path,
        mode=mode,
        from_line=start_line,
        to_line=to_line,
        returned_lines=returned_lines,
        returned_bytes=returned_bytes,
        truncated=truncated,
        output_format=str(args.format),
    )

    if str(args.format) == "json":
        _json_dump(
            {
                "ok": True,
                "path": rel_path,
                "contexts": contexts,
                "mode": mode,
                "from_line": start_line,
                "to_line": to_line,
                "line_hint": jump_line,
                "content": selected_text,
                "truncated": {
                    "yes": truncated,
                    "by_lines": bool(by_lines),
                    "by_bytes": bool(by_bytes),
                    "selected_lines_before_caps": selected_lines_before_caps,
                    "selected_bytes_before_caps": selected_bytes_before_caps,
                    "returned_lines": returned_lines,
                    "returned_bytes": returned_bytes,
                    "max_lines": int(args.max_lines),
                    "max_bytes": int(args.max_bytes),
                },
                "meta": {
                    "allow_non_docs": bool(args.allow_non_docs),
                    "read_event_id": read_event_id,
                },
            }
        )
        return 0

    if str(args.format) == "md":
        print(f"### `{rel_path}`")
        print(
            f"- mode={mode}, from_line={start_line}, to_line={to_line}, "
            f"returned_lines={returned_lines}, returned_bytes={returned_bytes}, "
            f"truncated={'yes' if truncated else 'no'}, event_id={read_event_id}"
        )
        print(f"- Context: {context_inline}")
        print(f"- caps (max_lines={int(args.max_lines)}, max_bytes={int(args.max_bytes)})")
        print("```text")
        if selected_text:
            sys.stdout.write(selected_text)
            if not selected_text.endswith("\n"):
                sys.stdout.write("\n")
        print("```")
        if truncated:
            print(
                "TRUNCATED: "
                f"by_lines={'yes' if by_lines else 'no'}, "
                f"by_bytes={'yes' if by_bytes else 'no'}, "
                f"selected_lines_before_caps={selected_lines_before_caps}, "
                f"selected_bytes_before_caps={selected_bytes_before_caps}",
                file=sys.stderr,
            )
        return 0

    print(
        "docs_get "
        f"(event_id={read_event_id}, path={rel_path}, mode={mode}, from_line={start_line}, to_line={to_line}, "
        f"returned_lines={returned_lines}, returned_bytes={returned_bytes}, truncated={'yes' if truncated else 'no'})"
    )
    print(f"Context: {context_inline}")
    print(f"caps (max_lines={int(args.max_lines)}, max_bytes={int(args.max_bytes)})")
    print("----- BEGIN CONTENT -----")
    if selected_text:
        sys.stdout.write(selected_text)
        if not selected_text.endswith("\n"):
            sys.stdout.write("\n")
    print("----- END CONTENT -----")
    if truncated:
        print(
            "TRUNCATED: "
            f"by_lines={'yes' if by_lines else 'no'}, "
            f"by_bytes={'yes' if by_bytes else 'no'}, "
            f"selected_lines_before_caps={selected_lines_before_caps}, "
            f"selected_bytes_before_caps={selected_bytes_before_caps}",
            file=sys.stderr,
        )
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

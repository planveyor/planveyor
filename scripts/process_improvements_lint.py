#!/usr/bin/env python3
"""Validate process-improvement backlog files."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import process_improvements_collect as common

from process_improvements_collect import PROCESS_IMPROVEMENTS_DIR, parse_backlog_file


BACKLOG_GLOB = "*__process_improvements_backlog.md"


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_no: int | None
    code: str
    message: str

    def render(self) -> str:
        if self.line_no is None:
            return f"{self.rel_path}: {self.code}: {self.message}"
        return f"{self.rel_path}:{self.line_no}: {self.code}: {self.message}"


def resolve_project_root(raw: str | None) -> Path:
    root = Path(raw).expanduser() if raw else Path.cwd()
    return root.resolve()


def _resolve_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def _rel_path(project_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def iter_default_backlog_paths(project_root: Path) -> list[Path]:
    root = project_root / PROCESS_IMPROVEMENTS_DIR
    if not root.exists():
        return []
    return sorted(path.resolve() for path in root.glob(BACKLOG_GLOB) if path.is_file())


def expand_lint_target(project_root: Path, raw_path: str) -> list[Path]:
    resolved = _resolve_path(project_root, raw_path)
    if not resolved.exists():
        return [resolved]
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        if resolved == project_root:
            return iter_default_backlog_paths(project_root)
        return sorted(path.resolve() for path in resolved.glob(BACKLOG_GLOB) if path.is_file())
    return [resolved]


def select_backlog_paths(project_root: Path, raw_paths: Iterable[str] | None = None) -> list[Path]:
    if not raw_paths:
        return iter_default_backlog_paths(project_root)
    selected: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths:
        for path in expand_lint_target(project_root, raw_path):
            if path in seen:
                continue
            seen.add(path)
            selected.append(path)
    return selected


def lint_backlog_paths(paths: Iterable[Path], project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        rel_path = _rel_path(project_root, path)
        if not path.exists():
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="missing_path",
                    message="Process-improvement lint target does not exist.",
                )
            )
            continue
        if not path.is_file():
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="unsupported_path",
                    message="Process-improvement lint target must be a file or directory.",
                )
            )
            continue
        try:
            parse_backlog_file(path, project_root)
        except ValueError as exc:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="parse_error",
                    message=str(exc),
                )
            )
    return findings


def carrier_readback_for_paths(paths: Iterable[Path], project_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            backlog = parse_backlog_file(path, project_root)
        except ValueError:
            continue
        rel_path = _rel_path(project_root, path)
        line_numbers = common.backlog_entry_line_numbers(path)
        for entry in backlog.entries:
            issues = common.triage_carrier_issues(entry)
            if not issues:
                continue
            rows.append(
                {
                    "file": rel_path,
                    "line": line_numbers.get(entry.entry_id),
                    "entry_id": entry.entry_id,
                    "status": entry.status,
                    "missing_fields": [issue.field for issue in issues],
                    "codes": [issue.code for issue in issues],
                    "messages": [issue.message for issue in issues],
                }
            )
    return rows


def carrier_findings_for_readback(rows: Iterable[dict[str, object]]) -> list[Finding]:
    findings: list[Finding] = []
    for row in rows:
        fields = ", ".join(str(field) for field in row["missing_fields"])
        findings.append(
            Finding(
                rel_path=str(row["file"]),
                line_no=row["line"] if isinstance(row["line"], int) else None,
                code="missing_triage_carrier",
                message=f"{row['entry_id']} missing triage carrier field(s): {fields}",
            )
        )
    return findings


def render_findings_text(findings: Iterable[Finding]) -> str:
    rendered = [finding.render() for finding in findings]
    if not rendered:
        return "process-improvements-lint: OK"
    return "\n".join([*rendered, f"process-improvements-lint: FAIL ({len(rendered)} findings)"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="process_improvements_lint",
        description="Validate primary `docs/process_improvements/*__process_improvements_backlog.md` files.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional backlog files or directories to lint (relative to `--project-root`).",
    )
    parser.add_argument(
        "--project-root",
        default="",
        help="Repo root that owns `docs/process_improvements/*` (default: cwd).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--require-triage-carrier",
        action="store_true",
        help="Turn staged triage-carrier readback issues into hard lint findings.",
    )
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root or None)
    paths = select_backlog_paths(project_root, args.paths or None)
    findings = lint_backlog_paths(paths, project_root)
    carrier_rows = carrier_readback_for_paths(paths, project_root)
    if args.require_triage_carrier:
        findings.extend(carrier_findings_for_readback(carrier_rows))

    if args.format == "json":
        payload = {
            "project_root": str(project_root),
            "files": [_rel_path(project_root, path) for path in paths],
            "findings": [
                {
                    "file": finding.rel_path,
                    "line": finding.line_no,
                    "code": finding.code,
                    "message": finding.message,
                }
                for finding in findings
            ],
            "carrier_readback": {
                "mode": "hard" if args.require_triage_carrier else "staged",
                "rows": carrier_rows,
                "count": len(carrier_rows),
            },
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(render_findings_text(findings) + "\n")

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())

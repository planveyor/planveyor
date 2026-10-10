#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_gate_policy


STEP_LINE_RE = re.compile(
    r"^(?P<prefix>\s*[-*]\s*\[)(?P<mark>[ xX])(?P<suffix>\]\s+)(?P<key>step:[^\s#]+)(?P<rest>.*)$"
)
HEADER_RE = re.compile(r"^(?P<key>[A-Z_]+)=(?P<value>.*)$")


@dataclass(frozen=True)
class StepLine:
    index: int
    key: str
    checked: bool


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_snapshot(path: Path) -> tuple[bytes, list[str]]:
    raw = path.read_bytes()
    return raw, raw.decode("utf-8").splitlines()


def _parse_steps(lines: list[str]) -> list[StepLine]:
    out: list[StepLine] = []
    for i, line in enumerate(lines):
        m = STEP_LINE_RE.match(line)
        if not m:
            continue
        key = m.group("key").strip()
        mark = m.group("mark")
        out.append(StepLine(index=i, key=key, checked=(mark.lower() == "x")))
    return out


def _parse_header(lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        match = HEADER_RE.match(line.strip())
        if match:
            header[match.group("key")] = match.group("value").strip()
    return header


def _read_range_value(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    return None


def _tracker_header_expectations(tracker_path: Path) -> dict[str, str]:
    root = tracker_path.resolve().parent
    base = _read_range_value(root / ".planveyor.range.base")
    head = _read_range_value(root / ".planveyor.range.head")
    merge = _read_range_value(root / ".planveyor.range.merge")
    expected: dict[str, str] = {}
    if base:
        expected["BASE"] = base
    if head:
        expected["HEAD"] = head
    if merge:
        expected["MERGE_SHA"] = merge
    if base and head:
        expected["RANGE"] = f"{base}..{head}"
        expected["RANGE_ID"] = f"range_{base[:7]}_{head[:7]}"
    return expected


def _tracker_header_errors(tracker_path: Path, header: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for key, expected in _tracker_header_expectations(tracker_path).items():
        actual = header.get(key)
        if actual is None:
            errors.append({"field": key, "expected": expected, "actual": "(missing)"})
        elif actual != expected:
            errors.append({"field": key, "expected": expected, "actual": actual})
    return errors


def _next_step_key(lines: list[str]) -> str | None:
    for step in _parse_steps(lines):
        if not step.checked:
            return step.key
    return None


def _tick_step(lines: list[str], key: str) -> tuple[list[str], bool]:
    key = key.strip()
    if not key:
        raise ValueError("empty step key")

    out = list(lines)
    for step in _parse_steps(lines):
        if step.key != key:
            continue
        if step.checked:
            return out, False
        line = out[step.index]
        m = STEP_LINE_RE.match(line)
        if not m:
            return out, False
        out[step.index] = f"{m.group('prefix')}x{m.group('suffix')}{m.group('key')}{m.group('rest')}"
        return out, True
    return out, False


def _emit(payload: dict[str, object], fmt: str, *, default_plain: str) -> int:
    if fmt == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 0 if "error" not in payload else 2
    if fmt == "kv":
        for k, v in payload.items():
            sys.stdout.write(f"{k}={v}\n")
        return 0 if "error" not in payload else 2
    sys.stdout.write(default_plain + "\n")
    return 0 if "error" not in payload else 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Deterministic helper for .planveyor.merge_tracker.md")
    parser.add_argument(
        "--tracker",
        default=".planveyor.merge_tracker.md",
        help="Path to merge tracker file (default: .planveyor.merge_tracker.md)",
    )
    parser.add_argument(
        "--format",
        default="plain",
        choices=("plain", "kv", "json"),
        help="Output format (default: plain)",
    )

    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("next", help="Print next unchecked step key (step:...) or empty if done")
    p_tick = sub.add_parser("tick", help="Mark a step as checked (step:...)")
    p_tick.add_argument("key", help="Step key to tick (e.g. step:review_range)")

    ns = parser.parse_args(argv)
    cmd = ns.cmd or "next"
    tracker_path = Path(ns.tracker)
    msg: dict[str, object]

    # Engaged policy validation deliberately happens before existence checks,
    # header expectations, routing, or tick writes.  The validator returns
    # ``None`` for legacy roots, preserving this module's legacy grammar and
    # topology behavior (including the historical [A-Z_]+ header parser).
    try:
        binding = merge_gate_policy.validate_tracker_for_path(tracker_path)
    except (merge_gate_policy.MergeGatePolicyError, merge_gate_policy.authority.ContractAuthorityError) as exc:
        msg = {
            "error": getattr(exc, "reason_code", "merge_policy_invalid"),
            "tracker": str(tracker_path),
        }
        return _emit(msg, ns.format, default_plain=f"ERROR merge policy: {exc}")

    effective_tracker = tracker_path if binding is None else binding.tracker_path
    if not effective_tracker.exists():
        msg = {"error": "missing_tracker", "tracker": str(tracker_path)}
        return _emit(msg, ns.format, default_plain=f"ERROR missing tracker: {tracker_path}")

    tracker_snapshot, lines = _read_snapshot(effective_tracker)
    header = _parse_header(lines)
    header_errors = _tracker_header_errors(effective_tracker, header)
    if header_errors:
        detail = "; ".join(
            f"{item['field']}: tracker={item['actual']} saved={item['expected']}"
            for item in header_errors
        )
        msg = {
            "error": "tracker_header_inconsistent",
            "tracker": str(tracker_path),
            "header_errors": header_errors,
        }
        return _emit(msg, ns.format, default_plain=f"ERROR tracker header inconsistent: {detail}")

    if cmd == "next":
        steps = _parse_steps(lines)
        if not steps:
            msg = {
                "error": "no_steps_found",
                "tracker": str(tracker_path),
                "next_step": "",
                "done": 0,
            }
            return _emit(msg, ns.format, default_plain="")

        key = _next_step_key(lines)
        msg = {"next_step": (key or ""), "done": int(key is None), "tracker": str(tracker_path)}
        return _emit(msg, ns.format, default_plain=(key or ""))

    if cmd == "tick":
        steps = _parse_steps(lines)
        if not steps:
            msg = {
                "error": "no_steps_found",
                "tracker": str(tracker_path),
                "key": ns.key,
                "changed": 0,
            }
            return _emit(msg, ns.format, default_plain="changed=0")

        new_lines, changed = _tick_step(lines, ns.key)
        if changed:
            if binding is not None:
                try:
                    fresh_binding = merge_gate_policy.validate_tracker_for_path(tracker_path)
                except (merge_gate_policy.MergeGatePolicyError, merge_gate_policy.authority.ContractAuthorityError) as exc:
                    msg = {
                        "error": getattr(exc, "reason_code", "merge_policy_invalid"),
                        "tracker": str(tracker_path),
                    }
                    return _emit(msg, ns.format, default_plain=f"ERROR merge policy: {exc}")
                if (
                    fresh_binding is None
                    or fresh_binding.tracker_path != binding.tracker_path
                    or fresh_binding.context.project_root != binding.context.project_root
                    or fresh_binding.context.generation_sha256 != binding.context.generation_sha256
                    or fresh_binding.policy.raw_sha256 != binding.policy.raw_sha256
                ):
                    msg = {"error": "engaged_tracker_binding_changed", "tracker": str(tracker_path)}
                    return _emit(msg, ns.format, default_plain="ERROR engaged tracker binding changed")
                try:
                    fresh_snapshot, _fresh_lines = _read_snapshot(fresh_binding.tracker_path)
                except OSError as exc:
                    msg = {"error": "engaged_tracker_read_failed", "tracker": str(tracker_path)}
                    return _emit(msg, ns.format, default_plain=f"ERROR tracker read failed: {exc}")
                if fresh_snapshot != tracker_snapshot:
                    msg = {"error": "engaged_tracker_changed_before_tick", "tracker": str(tracker_path)}
                    return _emit(msg, ns.format, default_plain="ERROR engaged tracker changed before tick")
            _write_lines(effective_tracker, new_lines)
        if not changed and ns.key.strip() and all(step.key != ns.key.strip() for step in steps):
            msg = {"error": "step_not_found", "changed": 0, "key": ns.key, "tracker": str(tracker_path)}
        else:
            msg = {"changed": int(changed), "key": ns.key, "tracker": str(tracker_path)}
        return _emit(msg, ns.format, default_plain=("changed=1" if changed else "changed=0"))

    msg = {"error": "unknown_cmd", "cmd": cmd}
    return _emit(msg, ns.format, default_plain=f"ERROR unknown cmd: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

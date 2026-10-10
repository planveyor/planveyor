#!/usr/bin/env python3
"""Read-only CLI projection for the semantic review observation V1 contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import plan_lint


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read semantic review observation materialization/validation from PLAN_PATH."
    )
    parser.add_argument("--plan", required=True, help="Repository-relative or absolute PLAN_PATH.")
    parser.add_argument("--format", required=True, choices=("json", "text"), help="Readback format.")
    return parser.parse_args(argv)


def render_text(report: dict[str, object]) -> str:
    lines = [
        f"semantic_review_observation: {report['state']}",
        f"reason_code: {report['reason_code']}",
    ]
    chain = report.get("validated_chain")
    if isinstance(chain, list):
        lines.append("validated_chain: " + (", ".join(str(value) for value in chain) if chain else "<empty>"))
    materialization = report.get("materialization")
    if materialization is not None:
        lines.append("materialization: available (copy materialization.observation exactly)")
    errors = report.get("errors")
    if isinstance(errors, list):
        for error in errors:
            if not isinstance(error, dict):
                continue
            location = error.get("path") or "<plan>"
            line_no = error.get("line")
            location_text = f"{location}:{line_no}" if isinstance(line_no, int) else str(location)
            lines.append(f"error[{error.get('code', 'unknown')}]: {location_text}: {error.get('message', '')}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = plan_lint.build_semantic_review_observation_report(Path(args.plan))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(render_text(report))
    return 1 if report["state"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

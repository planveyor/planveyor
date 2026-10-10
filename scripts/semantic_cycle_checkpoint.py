#!/usr/bin/env python3
"""Read-only semantic-cycle checkpoint projection for one plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import plan_lint


NONZERO_STATES = frozenset({"blocked", "required", "producer_blocked"})


def format_text(report: dict[str, object]) -> str:
    """Keep text output compact while preserving JSON's route-relevant parity."""

    trigger = report.get("trigger")
    resolution = report.get("resolution")
    trigger_id = trigger.get("observation_id", "") if isinstance(trigger, dict) else ""
    trigger_kind = trigger.get("trigger_kind", "") if isinstance(trigger, dict) else ""
    allowed_next_status = resolution.get("allowed_next_status", "") if isinstance(resolution, dict) else ""
    errors = report.get("errors")
    error_codes = (
        ",".join(str(item.get("code", "")) for item in errors if isinstance(item, dict))
        if isinstance(errors, list)
        else ""
    )
    return "\n".join(
        (
            f"schema_version={report.get('schema_version', '')}",
            f"state={report.get('state', '')}",
            f"reason_code={report.get('reason_code', '')}",
            f"trigger_observation_id={trigger_id}",
            f"trigger_kind={trigger_kind}",
            f"authority_decision_id={report.get('authority_decision_id', '')}",
            f"authority_carrier_sha256={report.get('authority_carrier_sha256', '')}",
            f"grammar_contour_id={report.get('grammar_contour_id', '')}",
            f"allowed_next_status={allowed_next_status}",
            f"error_codes={error_codes}",
        )
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="semantic_cycle_checkpoint",
        description="Read one plan's fail-closed semantic-cycle checkpoint state.",
    )
    parser.add_argument("--plan", required=True, type=Path, help="PLAN_PATH to inspect read-only.")
    parser.add_argument("--format", choices=("json", "text"), default="json", help="Output representation.")
    args = parser.parse_args(argv)

    report = plan_lint.build_semantic_cycle_checkpoint_report(args.plan)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(report), end="")
    return 2 if report.get("state") in NONZERO_STATES else 0


if __name__ == "__main__":
    raise SystemExit(main())

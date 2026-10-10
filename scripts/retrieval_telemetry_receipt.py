#!/usr/bin/env python3
"""Shared lint helpers for bounded docs retrieval telemetry receipts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence


RETRIEVAL_TELEMETRY_RECEIPT_TITLE = "retrieval telemetry receipt"
TRIGGER_TOKENS = (
    "planveyor_docs_lookup",
    "planveyor_docs_retrieve",
    "docs_retrieve.py",
    "docs_retrieve (",
)
DECISION_EVIDENCE_MARKERS = (
    "decision evidence",
    "source selection",
    "source-selection",
    "file selection",
    "selected files",
    "lookup evidence",
    "cited evidence",
    "used ",
    "evidence",
)
ALLOWED_NO_OP_REASONS = frozenset(
    {
        "not_used_for_decision",
        "retrieval_only_file_discovery",
        "instrumented_read_unavailable",
        "external_source_read",
        "already_evaluated_in_prior_receipt",
    }
)
ALLOWED_OUTCOMES = frozenset({"used", "partial", "miss", "noise", "not_evaluated"})
ALLOWED_READ_LOG_STATUSES = frozenset({"present", "missing", "disabled"})
REQUIRED_RECEIPT_FIELDS = (
    "query_event_id",
    "used_for_decision",
    "read_open",
    "read_log_status",
    "read_event_id",
    "outcome",
    "outcome_reason",
    "cited/opened_files",
)

H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
SPACE_RE = re.compile(r"\s+")
FIELD_RE = re.compile(r"^\s*(?:[-*]\s*)?`?(?P<key>[A-Za-z0-9_/ -]+)`?\s*(?::|=)\s*(?P<value>.+?)\s*$")
NA_WHY_RE = re.compile(r"\bn\s*/\s*a\s*\(\s*why\s*=\s*(?P<reason>[A-Za-z0-9_]+)[^)]*\)", re.IGNORECASE)


@dataclass(frozen=True)
class ReceiptFinding:
    line_no: int
    code: str
    message: str


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.lower()).strip()


def normalize_field_key(value: str) -> str:
    normalized = value.replace("`", "").strip().lower()
    normalized = normalized.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    normalized = re.sub(r"\s+", "_", normalized)
    return normalized


def heading_locations(lines: Sequence[str]) -> dict[str, int]:
    locations: dict[str, int] = {}
    for line_no, line in enumerate(lines, start=1):
        match = H2_RE.match(line)
        if not match:
            continue
        locations.setdefault(normalize_text(match.group("title")), line_no)
    return locations


def section_lines(lines: Sequence[str], section_title: str) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    current_h2: str | None = None
    for line_no, line in enumerate(lines, start=1):
        match = H2_RE.match(line)
        if match:
            current_h2 = normalize_text(match.group("title"))
            continue
        if current_h2 == section_title:
            collected.append((line_no, line))
    return collected


def _field_values(lines: Sequence[tuple[int, str]]) -> dict[str, tuple[int, str]]:
    values: dict[str, tuple[int, str]] = {}
    for line_no, line in lines:
        match = FIELD_RE.match(line)
        if not match:
            continue
        key = normalize_field_key(match.group("key"))
        value = match.group("value").strip().strip("`").strip()
        values.setdefault(key, (line_no, value))
    if "query_event_id" not in values and "query_event_ids" in values:
        values["query_event_id"] = values["query_event_ids"]
    return values


def _extract_no_op_reason(value: str) -> str | None:
    clean = value.strip().strip("`").strip()
    if clean in ALLOWED_NO_OP_REASONS:
        return clean
    match = NA_WHY_RE.search(clean)
    if match:
        return match.group("reason")
    if "why=" in clean:
        tail = clean.split("why=", 1)[1]
        reason = re.split(r"[^A-Za-z0-9_]", tail, 1)[0]
        return reason or None
    return None


def _line_with_trigger(lines: Sequence[str], trigger_tokens: Sequence[str]) -> int:
    for line_no, line in enumerate(lines, start=1):
        lower = line.lower()
        if any(token.lower() in lower for token in trigger_tokens):
            return line_no
    return 1


def _line_with_decision_evidence_trigger(lines: Sequence[str], trigger_tokens: Sequence[str]) -> int | None:
    retrieval_tokens = tuple(
        token.lower()
        for token in trigger_tokens
        if normalize_text(token) != RETRIEVAL_TELEMETRY_RECEIPT_TITLE
    )
    for line_no, line in enumerate(lines, start=1):
        lower = line.lower()
        if "planveyor_docs_lookup" in lower:
            return line_no
        if any(token in lower for token in retrieval_tokens) and any(
            marker in lower for marker in DECISION_EVIDENCE_MARKERS
        ):
            return line_no
    return None


def needs_retrieval_telemetry_receipt(
    lines: Sequence[str],
    trigger_tokens: Sequence[str] = TRIGGER_TOKENS,
    *,
    decision_evidence_only: bool = False,
) -> bool:
    if decision_evidence_only:
        headings = heading_locations(lines)
        return (
            RETRIEVAL_TELEMETRY_RECEIPT_TITLE in headings
            or _line_with_decision_evidence_trigger(lines, trigger_tokens) is not None
        )
    text = "\n".join(lines).lower()
    return any(token.lower() in text for token in trigger_tokens)


def _value_is_empty_or_placeholder(value: str) -> bool:
    stripped = value.strip().strip("`").strip()
    if not stripped:
        return True
    return stripped.lower() in {"n/a", "na", "none", "null", "tbd", "todo", "unknown"}


def _no_op_reason_state(fields: dict[str, tuple[int, str]]) -> tuple[bool, ReceiptFinding | None]:
    if "no_op_reason" not in fields:
        return False, None
    line_no, value = fields["no_op_reason"]
    clean = value.strip().strip("`").strip()
    if _value_is_empty_or_placeholder(clean) or clean.lower().startswith("n/a"):
        return False, None
    reason = _extract_no_op_reason(value)
    if reason in ALLOWED_NO_OP_REASONS:
        return True, None
    return False, ReceiptFinding(
        line_no=line_no,
        code="invalid_retrieval_telemetry_receipt",
        message=(
            "`no_op_reason` must use one allowed enum: "
            + ", ".join(sorted(ALLOWED_NO_OP_REASONS))
            + "."
        ),
    )


def _decision_flag(
    fields: dict[str, tuple[int, str]],
    *,
    receipt_line: int,
) -> tuple[bool | None, ReceiptFinding | None]:
    if "used_for_decision" not in fields:
        return None, ReceiptFinding(
            line_no=receipt_line,
            code="invalid_retrieval_telemetry_receipt",
            message="Retrieval telemetry receipt must include `used_for_decision=true|false`.",
        )
    line_no, value = fields["used_for_decision"]
    normalized = value.strip().strip("`").lower()
    if normalized == "true":
        return True, None
    if normalized == "false":
        return False, None
    return None, ReceiptFinding(
        line_no=line_no,
        code="invalid_retrieval_telemetry_receipt",
        message="`used_for_decision` must be `true` or `false`.",
    )


def _field_no_op_reason(fields: dict[str, tuple[int, str]], field: str) -> tuple[int, str | None]:
    if field not in fields:
        return 0, None
    line_no, value = fields[field]
    return line_no, _extract_no_op_reason(value)


def _validate_receipt_fields(
    fields: dict[str, tuple[int, str]],
    receipt_line: int,
    *,
    lines: Sequence[str],
    trigger_tokens: Sequence[str],
) -> list[ReceiptFinding]:
    findings: list[ReceiptFinding] = []

    no_op_valid, no_op_finding = _no_op_reason_state(fields)
    if no_op_finding is not None:
        findings.append(no_op_finding)
    elif no_op_valid:
        used_for_decision, decision_finding = _decision_flag(fields, receipt_line=receipt_line)
        if decision_finding is not None:
            findings.append(decision_finding)
        elif used_for_decision is not False:
            line_no = fields.get("used_for_decision", (receipt_line, ""))[0]
            findings.append(
                ReceiptFinding(
                    line_no=line_no,
                    code="invalid_retrieval_telemetry_receipt",
                    message="Retrieval telemetry no-op receipt must set `used_for_decision=false`.",
                )
            )
        return findings

    missing = [field for field in REQUIRED_RECEIPT_FIELDS if field not in fields]
    if missing:
        findings.append(
            ReceiptFinding(
                line_no=receipt_line,
                code="invalid_retrieval_telemetry_receipt",
                message="Retrieval telemetry receipt is missing fields: " + ", ".join(missing) + ".",
            )
        )
        return findings

    used_for_decision, decision_finding = _decision_flag(fields, receipt_line=receipt_line)
    if decision_finding is not None:
        findings.append(decision_finding)

    decision_line = _line_with_decision_evidence_trigger(lines, trigger_tokens)
    if used_for_decision is False and decision_line is not None:
        findings.append(
            ReceiptFinding(
                line_no=decision_line,
                code="invalid_retrieval_telemetry_receipt",
                message="Retrieval decision evidence cannot set `used_for_decision=false`.",
            )
        )

    no_op_line, no_op_reason = _field_no_op_reason(fields, "no_op_reason")
    accepted_line, accepted_reason = _field_no_op_reason(fields, "accepted_no_op_reason")
    if used_for_decision is False and no_op_reason != "not_used_for_decision" and accepted_reason != "not_used_for_decision":
        findings.append(
            ReceiptFinding(
                line_no=no_op_line or accepted_line or fields["used_for_decision"][0],
                code="invalid_retrieval_telemetry_receipt",
                message=(
                    "`used_for_decision=false` requires `no_op_reason=not_used_for_decision` "
                    "or `accepted_no_op_reason=not_used_for_decision`."
                ),
            )
        )
    if used_for_decision is True and (no_op_reason == "not_used_for_decision" or accepted_reason == "not_used_for_decision"):
        findings.append(
            ReceiptFinding(
                line_no=no_op_line or accepted_line or fields["used_for_decision"][0],
                code="invalid_retrieval_telemetry_receipt",
                message="`not_used_for_decision` no-op reason is invalid when `used_for_decision=true`.",
            )
        )

    query_line, query_value = fields["query_event_id"]
    if _value_is_empty_or_placeholder(query_value):
        findings.append(
            ReceiptFinding(
                line_no=query_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`query_event_id` must be a concrete event id, `latest`, or a copied event-id list.",
            )
        )

    read_open_line, read_open_value = fields["read_open"]
    read_open_norm = read_open_value.strip().strip("`").lower()
    if not (
        read_open_norm in {"ok", "missing"}
        or (_extract_no_op_reason(read_open_value) in ALLOWED_NO_OP_REASONS)
    ):
        findings.append(
            ReceiptFinding(
                line_no=read_open_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`read_open` must be `ok`, `missing`, or `N/A (why=<allowed no-op reason>)`.",
            )
        )

    read_log_line, read_log_value = fields["read_log_status"]
    read_log_norm = read_log_value.strip().strip("`").lower()
    if not (
        read_log_norm in ALLOWED_READ_LOG_STATUSES
        or (_extract_no_op_reason(read_log_value) in ALLOWED_NO_OP_REASONS)
    ):
        findings.append(
            ReceiptFinding(
                line_no=read_log_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`read_log_status` must be `present`, `missing`, `disabled`, or `N/A (why=<allowed no-op reason>)`.",
            )
        )

    read_event_line, read_event_value = fields["read_event_id"]
    if (
        read_open_norm == "ok"
        and _value_is_empty_or_placeholder(read_event_value)
        and _extract_no_op_reason(read_event_value) not in ALLOWED_NO_OP_REASONS
    ):
        findings.append(
            ReceiptFinding(
                line_no=read_event_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`read_event_id` must be concrete when `read_open=ok`.",
            )
        )

    outcome_line, outcome_value = fields["outcome"]
    outcome_norm = outcome_value.strip().strip("`").lower()
    if outcome_norm not in ALLOWED_OUTCOMES:
        findings.append(
            ReceiptFinding(
                line_no=outcome_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`outcome` must be one of: " + ", ".join(sorted(ALLOWED_OUTCOMES)) + ".",
            )
        )

    reason_line, reason_value = fields["outcome_reason"]
    if _value_is_empty_or_placeholder(reason_value):
        findings.append(
            ReceiptFinding(
                line_no=reason_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`outcome_reason` must be a short concrete reason.",
            )
        )

    files_line, files_value = fields["cited/opened_files"]
    if read_open_norm == "ok" and _value_is_empty_or_placeholder(files_value):
        findings.append(
            ReceiptFinding(
                line_no=files_line,
                code="invalid_retrieval_telemetry_receipt",
                message="`cited/opened files` must name paths when `read_open=ok`.",
            )
        )

    return findings


def lint_retrieval_telemetry_receipt(
    lines: Sequence[str],
    *,
    trigger_tokens: Sequence[str] = TRIGGER_TOKENS,
    decision_evidence_only: bool = False,
) -> list[ReceiptFinding]:
    if not needs_retrieval_telemetry_receipt(
        lines,
        trigger_tokens=trigger_tokens,
        decision_evidence_only=decision_evidence_only,
    ):
        return []

    headings = heading_locations(lines)
    receipt_line = headings.get(RETRIEVAL_TELEMETRY_RECEIPT_TITLE)
    if receipt_line is None:
        line_no = _line_with_trigger(lines, trigger_tokens)
        if decision_evidence_only:
            line_no = _line_with_decision_evidence_trigger(lines, trigger_tokens) or line_no
        return [
            ReceiptFinding(
                line_no=line_no,
                code="missing_retrieval_telemetry_receipt",
                message="Retrieval-backed artifact must include `## Retrieval telemetry receipt` or a bounded no-op receipt.",
            )
        ]

    fields = _field_values(section_lines(lines, RETRIEVAL_TELEMETRY_RECEIPT_TITLE))
    return _validate_receipt_fields(fields, receipt_line, lines=lines, trigger_tokens=trigger_tokens)

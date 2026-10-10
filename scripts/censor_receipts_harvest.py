#!/usr/bin/env python3
"""Harvest structured CENSOR receipts from plan/review markdown."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Iterable


REQUIRED_LABELS = (
    "Artifacts opened",
    "Review verdict seen",
    "Blocker IDs considered",
    "Role-owned finding",
    "Reconciliation",
    "Final censor verdict",
)

CENSOR_EVIDENCE_REQUIRED_FIELDS = (
    "Second opinion",
    "Addendum",
    "Context reconciliation",
    "Fixes",
)

CENSOR_EVIDENCE_NO_FINDINGS_FIELDS = (
    "Counterfactuals considered",
)

CENSOR_EVIDENCE_FIELD_ALIASES = {
    "Second opinion": ("Second opinion",),
    "Addendum": ("Addendum", "Addendum (new angle)"),
    "Context reconciliation": ("Context reconciliation",),
    "Fixes": ("Fixes",),
    "Counterfactuals considered": ("Counterfactuals considered",),
}

CENSOR_EVIDENCE_ALIAS_TO_FIELD = {
    alias: field
    for field, aliases in CENSOR_EVIDENCE_FIELD_ALIASES.items()
    for alias in aliases
}
MACHINE_READBACK_ALIAS_TO_FIELD = {
    label.lower(): label for label in REQUIRED_LABELS
}
MACHINE_READBACK_ALIAS_TO_FIELD.update(
    {
        alias.lower(): field
        for field, aliases in CENSOR_EVIDENCE_FIELD_ALIASES.items()
        for alias in aliases
    }
)
MACHINE_READBACK_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<label>"
    + "|".join(
        re.escape(label)
        for label in sorted(MACHINE_READBACK_ALIAS_TO_FIELD, key=len, reverse=True)
    )
    + r")\s*:",
    re.IGNORECASE,
)
CENSOR_EVIDENCE_LABEL_RE = re.compile(
    r"(?P<label>"
    + "|".join(
        re.escape(label)
        for label in sorted(CENSOR_EVIDENCE_ALIAS_TO_FIELD, key=len, reverse=True)
    )
    + r")\s*:"
)

DEADLOCK_LABELS = (
    "Loop signal",
    "Root cause class",
    "Why previous rerun did not break the loop",
    "Extraordinary action",
)

ROLE_QUALITY_CATEGORIES = (
    "helped",
    "missed live blocker",
    "receipt missing",
    "noise/no-op",
    "UNCONFIRMED",
)

ALL_LABELS = REQUIRED_LABELS + DEADLOCK_LABELS
LABEL_RE = re.compile(r"(?P<label>" + "|".join(re.escape(label) for label in ALL_LABELS) + r")\s*:")
SUPPORTED_CENSOR_ROLES = ("Architect", "Planner", "Coder", "Reviewer")
SUPPORTED_CENSOR_ROLE_BY_NORM = {role.lower(): role for role in SUPPORTED_CENSOR_ROLES}
CENSOR_TAG_RE = re.compile(
    r"^\s*-\s*(?:\[[^\]\n]+\]\s*)?"
    r"(?P<tag>\([^()\n]*\bCENSOR\b[^()\n]*\))"
)
CENSOR_ROLE_RE = re.compile(r"\((?P<role>[^()]+?)\s+CENSOR\)")
CENSOR_ROLE_HINT_RE = re.compile(r"\((?P<role>[^()\s]+)[^()]*?\bCENSOR\b")
CENSOR_CURRENT_FIELD_LABEL_RE = re.compile(
    r"\bcurrent\s*=",
    re.IGNORECASE,
)
CENSOR_CURRENT_FIELD_RE = re.compile(
    r"(?:^|[.;]\s+)current=true(?=$|[.;](?:\s|$))"
)
CENSOR_DISPATCH_ID_LABEL_PATTERN = (
    r"Censor(?:\s+|[-_]+)dispatch(?:\s+|[-_]+)id\s*:\s*"
)
CENSOR_DISPATCH_ID_FIELD_LABEL_RE = re.compile(
    CENSOR_DISPATCH_ID_LABEL_PATTERN,
    re.IGNORECASE,
)
CENSOR_DISPATCH_ID_BROAD_FIELD_RE = re.compile(
    CENSOR_DISPATCH_ID_LABEL_PATTERN
    + r"(?P<value>.*?)(?=$|[.;,](?:\s|$))",
    re.IGNORECASE,
)
CENSOR_DISPATCH_ID_RE = re.compile(
    r"(?:^|[.;]\s+)Censor dispatch id:\s*"
    r"(?P<value>[A-Za-z0-9_:-]+(?:\.[A-Za-z0-9_:-]+)*)(?=$|[.;](?:\s|$))"
)
CENSOR_HANDOFF_STATUS_RE = re.compile(
    r"^(?:OK|FAIL):\s*(?P<value>.+?)\s+validated(?=$|[.;](?:\s|$))",
)
CENSOR_HANDOFF_STATUS_BROAD_RE = re.compile(
    r"\b(?:OK|FAIL):\s*.+?\s+validated(?=$|[.;,](?:\s|$))",
    re.IGNORECASE,
)
CENSOR_OBSERVATIONS_BOUNDARY_RE = re.compile(r"\bObservations\s*:", re.IGNORECASE)
ROLE_TAG_RE = re.compile(
    r"^\s*-\s*(?:\[[^\]\n]+\]\s*)?"
    r"\((?P<role>Architect|Planner|Coder|Reviewer)"
    r"(?:\)|[ \t]+(?P<suffix>[^()\n]*\S)[ \t]*\))"
)
ROLE_ASSESSMENT_HEADING_RE = re.compile(r"^#{3,6}\s+R\d+\)\s*(?P<title>.+?)\s*$")
ROLE_ASSESSMENT_SECTION_RE = re.compile(r"^#{2,6}\s+Role assessment \(censor receipts", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+")

TRAILING_FIELD_MARKERS = (
    " Counterfactuals considered:",
    " Fixes:",
    " Censor hint:",
    " Gates:",
    " Context reconciliation:",
    " Addendum (new angle):",
)
SKIP_HINT_BODY_RE = re.compile(r"censor hint:\s*skip\s*\((?P<body>[^)]*)\)", re.IGNORECASE)
SAFE_HANDOFF_ONLY_CONTRACT_RE = re.compile(
    r"\bprevious\s+(?P<role>[a-z]+)-owned\s+contract\s+unchanged\b",
    re.IGNORECASE,
)
SEMANTIC_CHANGE_TOKEN_RE = re.compile(r"\bchanged\b", re.IGNORECASE)
SEMANTIC_CHANGE_SURFACE_TOKENS = (
    "implementation",
    "code",
    "target",
    "targets",
    "test",
    "tests",
    "scope",
)


@dataclass(frozen=True)
class MarkdownInput:
    kind: str
    display_path: str
    path: Path
    text: str | None


@dataclass(frozen=True)
class ReceiptCandidate:
    source: str
    path: str
    line: int
    role: str
    text: str


@dataclass(frozen=True)
class CensorEvidenceEvent:
    kind: str
    line: int
    role: str
    text: str


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def read_markdown(kind: str, raw_path: str) -> tuple[MarkdownInput, list[str]]:
    path = resolve_path(raw_path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = None
        warnings = [f"{kind} not found: {raw_path}"]
    except OSError as exc:
        text = None
        warnings = [f"{kind} unreadable: {raw_path}: {exc}"]
    else:
        warnings = []
    return MarkdownInput(kind=kind, display_path=raw_path, path=path, text=text), warnings


def _clean_value(raw_value: str) -> str:
    value = " ".join(raw_value.strip().split())
    for marker in TRAILING_FIELD_MARKERS:
        marker_index = value.find(marker)
        if marker_index >= 0:
            value = value[:marker_index].strip()
    return value.strip(" \t.;")


def parse_label_fields(text: str) -> dict[str, str]:
    matches = list(LABEL_RE.finditer(text))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group("label")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields[label] = _clean_value(text[match.end() : end])
    return fields


def parse_censor_evidence_fields(text: str) -> dict[str, str]:
    matches = list(CENSOR_EVIDENCE_LABEL_RE.finditer(text))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = CENSOR_EVIDENCE_ALIAS_TO_FIELD[match.group("label")]
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields[label] = _clean_value(text[match.end() : end])
    return fields


def _duplicate_machine_readback_label_reasons(text: str) -> list[str]:
    counts: dict[str, int] = {}
    for match in MACHINE_READBACK_LABEL_RE.finditer(text):
        field = MACHINE_READBACK_ALIAS_TO_FIELD[match.group("label").lower()]
        counts[field] = counts.get(field, 0) + 1
    return [
        f"duplicate_machine_readback_label:{field}"
        for field in (*CENSOR_EVIDENCE_REQUIRED_FIELDS, *CENSOR_EVIDENCE_NO_FINDINGS_FIELDS, *REQUIRED_LABELS)
        if counts.get(field, 0) > 1
    ]


def _normalize_selector(value: str | None) -> str:
    return " ".join((value or "").strip().strip("`").lower().split())


def _censor_receipt_preamble(text: str) -> str:
    match = CENSOR_OBSERVATIONS_BOUNDARY_RE.search(text)
    return text[: match.start()] if match is not None else text


def _censor_observations_boundary_invalid_reason(text: str) -> str | None:
    matches = list(CENSOR_OBSERVATIONS_BOUNDARY_RE.finditer(text))
    if not matches:
        return "missing_observations_boundary"
    if len(matches) > 1:
        return "duplicate_observations_boundaries"
    if matches[0].group(0) != "Observations:":
        return "malformed_observations_boundary"
    return None


def _has_censor_current_marker(text: str) -> bool:
    preamble = _censor_receipt_preamble(text)
    labels = list(CENSOR_CURRENT_FIELD_LABEL_RE.finditer(preamble))
    valid_fields = list(CENSOR_CURRENT_FIELD_RE.finditer(preamble))
    return len(labels) == 1 and len(valid_fields) == 1


def _has_legacy_censor_current_marker(text: str) -> bool:
    return "current=true" in _normalize_selector(text)


def _censor_current_field_invalid_reason(text: str) -> str:
    preamble = _censor_receipt_preamble(text)
    labels = list(CENSOR_CURRENT_FIELD_LABEL_RE.finditer(preamble))
    valid_fields = list(CENSOR_CURRENT_FIELD_RE.finditer(preamble))
    if len(labels) > 1:
        return "duplicate_or_conflicting_current_fields"
    if len(labels) == 1 and len(valid_fields) != 1:
        return "invalid_current_field"
    return "dispatch_receipt_missing_current_marker"


def _extract_censor_dispatch_ids(text: str) -> list[str]:
    return [
        match.group("value")
        for match in CENSOR_DISPATCH_ID_RE.finditer(_censor_receipt_preamble(text))
    ]


def _extract_broad_censor_dispatch_values(text: str) -> list[str]:
    return [
        match.group("value").strip().strip("`")
        for match in CENSOR_DISPATCH_ID_BROAD_FIELD_RE.finditer(
            _censor_receipt_preamble(text)
        )
    ]


def _censor_dispatch_id_field_count(text: str) -> int:
    return len(CENSOR_DISPATCH_ID_FIELD_LABEL_RE.findall(_censor_receipt_preamble(text)))


def _extract_censor_dispatch_id(text: str) -> str | None:
    values = _extract_censor_dispatch_ids(text)
    return values[0] if len(values) == 1 else None


def _extract_censor_handoff_status(text: str) -> str | None:
    preamble = _censor_receipt_preamble(text)
    tag_match = CENSOR_TAG_RE.search(preamble)
    if tag_match is None:
        return None
    handoff_text = preamble[tag_match.end() :].lstrip()
    exact_matches = list(CENSOR_HANDOFF_STATUS_RE.finditer(handoff_text))
    broad_matches = list(CENSOR_HANDOFF_STATUS_BROAD_RE.finditer(handoff_text))
    if len(exact_matches) != 1 or len(broad_matches) != 1:
        return None
    return exact_matches[0].group("value")


def _extract_censor_role(text: str) -> str:
    tag_match = CENSOR_TAG_RE.search(text)
    tag = tag_match.group("tag") if tag_match else text
    match = CENSOR_ROLE_RE.search(tag)
    if match:
        role = match.group("role").strip()
        return SUPPORTED_CENSOR_ROLE_BY_NORM.get(role.lower(), role)
    hint = CENSOR_ROLE_HINT_RE.search(tag)
    if hint:
        role = hint.group("role").strip()
        return SUPPORTED_CENSOR_ROLE_BY_NORM.get(role.lower(), role)
    return "Unknown"


def _censor_role_tag_invalid_reasons(text: str) -> list[str]:
    tag_match = CENSOR_TAG_RE.search(text)
    if tag_match is None:
        return []
    role_match = CENSOR_ROLE_RE.search(tag_match.group("tag"))
    if role_match is None:
        return ["malformed_censor_role_tag"]
    role = role_match.group("role").strip()
    if role.lower() not in SUPPORTED_CENSOR_ROLE_BY_NORM:
        return [f"unsupported_censor_role_tag:{role}"]
    return []


def _extract_regular_role(text: str) -> str:
    match = ROLE_TAG_RE.search(text)
    if match:
        return match.group("role").strip()
    return "Unknown"


def _extract_role_from_assessment_title(title: str) -> str:
    if "/" in title:
        return title.rsplit("/", 1)[-1].strip() or "Unknown"
    tokens = [token.strip() for token in re.split(r"[-:|]", title) if token.strip()]
    return tokens[-1] if tokens else "Unknown"


def _iter_receipt_scan_lines(markdown: MarkdownInput) -> Iterable[tuple[int, str]]:
    if markdown.text is None:
        return
    lines = markdown.text.splitlines()
    if markdown.kind != "plan":
        for line_number, line in enumerate(lines, start=1):
            yield line_number, line
        return

    in_evidence = False
    for line_number, line in enumerate(lines, start=1):
        if re.match(r"^##\s+Evidence\b", line):
            in_evidence = True
            yield line_number, line
            continue
        if in_evidence and re.match(r"^##\s+", line):
            in_evidence = False
        if in_evidence:
            yield line_number, line


def _line_candidates(markdown: MarkdownInput) -> Iterable[ReceiptCandidate]:
    if markdown.text is None:
        return
    for line_number, line in _iter_receipt_scan_lines(markdown):
        if CENSOR_TAG_RE.search(line) is None:
            continue
        yield ReceiptCandidate(
            source=markdown.kind,
            path=markdown.display_path,
            line=line_number,
            role=_extract_censor_role(line),
            text=line,
        )


def _role_assessment_candidates(markdown: MarkdownInput) -> Iterable[ReceiptCandidate]:
    if markdown.text is None:
        return
    lines = markdown.text.splitlines()
    in_section = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if ROLE_ASSESSMENT_SECTION_RE.match(line):
            in_section = True
            index += 1
            continue
        if in_section and line.startswith("## ") and not ROLE_ASSESSMENT_SECTION_RE.match(line):
            in_section = False
        if not in_section:
            index += 1
            continue
        heading = ROLE_ASSESSMENT_HEADING_RE.match(line)
        if not heading:
            index += 1
            continue
        block_start = index
        index += 1
        block_lines = [line]
        while index < len(lines) and not HEADING_RE.match(lines[index]):
            block_lines.append(lines[index])
            index += 1
        block = "\n".join(block_lines)
        if parse_label_fields(block):
            yield ReceiptCandidate(
                source=markdown.kind,
                path=markdown.display_path,
                line=block_start + 1,
                role=_extract_role_from_assessment_title(heading.group("title")),
                text=block,
            )
        continue
    return


def _iter_censor_evidence_events(markdown: MarkdownInput) -> Iterable[CensorEvidenceEvent]:
    if markdown.text is None:
        return
    for line_number, line in _iter_receipt_scan_lines(markdown):
        if CENSOR_TAG_RE.search(line):
            yield CensorEvidenceEvent(
                kind="receipt",
                line=line_number,
                role=_extract_censor_role(line),
                text=line,
            )
            continue
        if "Censor hint: skip" in line:
            yield CensorEvidenceEvent(
                kind="skip_hint",
                line=line_number,
                role=_extract_regular_role(line),
                text=line,
            )
            continue
        yield CensorEvidenceEvent(
            kind="context",
            line=line_number,
            role=_extract_regular_role(line),
            text=line,
        )


def _event_matches(
    event: CensorEvidenceEvent,
    role: str | None,
    handoff_status: str | None,
    *,
    strict_receipt_status: bool = False,
) -> bool:
    if role and _normalize_selector(event.role) != _normalize_selector(role):
        return False
    status_norm = _normalize_selector(handoff_status)
    if status_norm:
        if strict_receipt_status and event.kind == "receipt":
            if _normalize_selector(_extract_censor_handoff_status(event.text)) != status_norm:
                return False
        elif status_norm not in _normalize_selector(event.text):
            return False
    return True


def _base_censor_evidence_lint(
    state: str,
    reason_code: str,
    role: str | None,
    handoff_status: str | None,
    censor_dispatch_id: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "state": state,
        "reason_code": reason_code,
        "role": role or "",
        "handoff_status": handoff_status or "",
        "receipt_line": None,
        "missing_fields": [],
        "invalid_reasons": [],
        "selected_excerpt": "",
    }
    if censor_dispatch_id is not None:
        result["censor_dispatch_id"] = censor_dispatch_id
    return result


def _skip_hint_body(text: str) -> str:
    match = SKIP_HINT_BODY_RE.search(text)
    return match.group("body") if match else text


def _skip_hint_why_text(skip_hint_body: str) -> str:
    match = re.search(r"\bwhy\s*=\s*(?P<why>.*)$", skip_hint_body, flags=re.IGNORECASE)
    return match.group("why").strip() if match else ""


def _contract_role_token(role: str | None) -> str:
    return re.sub(r"[^a-z]", "", _normalize_selector(role))


def _has_handoff_only_alias(why_text: str) -> bool:
    return "handoff-only" in _lower(why_text)


def _has_evidence_status_alias(why_text: str) -> bool:
    why_lower = _lower(why_text)
    return bool(
        re.search(r"\bevidence/status(?:-only)?\b", why_lower)
        or re.search(r"\bstatus/evidence(?:-only)?\b", why_lower)
    )


def _has_same_role_unchanged_contract_proof(
    skip_hint_body: str,
    selected_role: str | None,
) -> bool:
    expected_role = _contract_role_token(selected_role)
    return bool(expected_role) and any(
        _contract_role_token(match.group("role")) == expected_role
        for match in SAFE_HANDOFF_ONLY_CONTRACT_RE.finditer(skip_hint_body)
    )


def _skip_hint_reason_says_semantic_delta(why_text: str) -> bool:
    if not SEMANTIC_CHANGE_TOKEN_RE.search(why_text):
        return False
    why_lower = _lower(why_text)
    return any(token in why_lower for token in SEMANTIC_CHANGE_SURFACE_TOKENS)


def _append_invalid_reason(invalid: list[str], reason: str) -> None:
    if reason not in invalid:
        invalid.append(reason)


def _skip_hint_invalid_reasons(
    skip_event: CensorEvidenceEvent,
    consecutive_skip_tail: list[CensorEvidenceEvent],
    selected_role: str | None,
) -> list[str]:
    text = _lower(skip_event.text)
    skip_hint_body = _skip_hint_body(skip_event.text)
    why_text = _skip_hint_why_text(skip_hint_body)
    handoff_only_alias_requested = _has_handoff_only_alias(why_text)
    evidence_status_alias_requested = _has_evidence_status_alias(why_text)
    same_role_unchanged_contract_proof = _has_same_role_unchanged_contract_proof(
        skip_hint_body,
        selected_role,
    )
    bounded_skip_alias = (
        handoff_only_alias_requested or evidence_status_alias_requested
    ) and same_role_unchanged_contract_proof
    invalid: list[str] = []
    if "why=" not in text:
        invalid.append("skip_hint_missing_why")
    if len(consecutive_skip_tail) > 2:
        invalid.append("skip_hint_anti_spam_limit_exceeded")
    if (
        (handoff_only_alias_requested or evidence_status_alias_requested)
        and not bounded_skip_alias
    ):
        _append_invalid_reason(invalid, "skip_hint_semantic_delta")
    if _skip_hint_reason_says_semantic_delta(why_text):
        _append_invalid_reason(invalid, "skip_hint_semantic_delta")

    unsafe_tokens = (
        "decisions",
        "scope",
        "solution",
        "acceptance",
        "target",
        "reviewer route",
        "test",
        "queue",
        "oracle",
        "semantic",
        "runtime",
        "code",
        "implementation",
    )
    safe_tokens = (
        "evidence-only",
        "status-only",
        "handoff wording",
        "docs-only audit wording",
    )
    if (
        any(token in text for token in unsafe_tokens)
        and not any(token in text for token in safe_tokens)
        and not bounded_skip_alias
    ):
        _append_invalid_reason(invalid, "skip_hint_semantic_delta")

    return invalid


def _consecutive_skip_tail(
    matching_events: list[CensorEvidenceEvent],
    latest_event: CensorEvidenceEvent,
) -> list[CensorEvidenceEvent]:
    tail: list[CensorEvidenceEvent] = []
    for event in reversed([event for event in matching_events if event.line <= latest_event.line]):
        if event.kind != "skip_hint":
            break
        tail.append(event)
    return list(reversed(tail))


def _later_matching_context_events(
    matching_events: list[CensorEvidenceEvent],
    selected_receipt: CensorEvidenceEvent,
) -> list[CensorEvidenceEvent]:
    return [
        event
        for event in matching_events
        if event.line > selected_receipt.line and event.kind == "context"
    ]


def _receipt_field_diagnostics(text: str) -> tuple[list[str], list[str]]:
    receipt_fields = parse_label_fields(text)
    fields = parse_censor_evidence_fields(text)
    missing_fields = [field for field in REQUIRED_LABELS if not receipt_fields.get(field)]
    missing_fields.extend(
        field for field in CENSOR_EVIDENCE_REQUIRED_FIELDS if not fields.get(field)
    )
    invalid_reasons = _censor_role_tag_invalid_reasons(text)
    invalid_reasons.extend(_duplicate_machine_readback_label_reasons(text))
    second_opinion = _lower(fields.get("Second opinion"))
    if "no findings" in second_opinion and not fields.get("Counterfactuals considered"):
        missing_fields.extend(CENSOR_EVIDENCE_NO_FINDINGS_FIELDS)
        invalid_reasons.append("no_findings_missing_counterfactuals")
    return missing_fields, invalid_reasons


def _receipt_fields_are_complete(text: str) -> bool:
    missing_fields, invalid_reasons = _receipt_field_diagnostics(text)
    return not missing_fields and not invalid_reasons


def _unresolved_matching_context_events(
    matching_events: list[CensorEvidenceEvent],
    selected_skip: CensorEvidenceEvent,
) -> list[CensorEvidenceEvent]:
    prior_events = [event for event in matching_events if event.line <= selected_skip.line]
    complete_receipts = [
        event
        for event in prior_events
        if event.kind == "receipt"
        and _receipt_fields_are_complete(event.text)
    ]
    if complete_receipts:
        boundary_line = complete_receipts[-1].line
    else:
        skip_events = [event for event in prior_events if event.kind == "skip_hint"]
        boundary_line = skip_events[0].line
    return [
        event
        for event in matching_events
        if event.line > boundary_line and event.kind == "context"
    ]


def build_censor_evidence_lint(
    plan_input: MarkdownInput,
    role: str | None = None,
    handoff_status: str | None = None,
    censor_dispatch_id: str | None = None,
) -> dict[str, object]:
    if not role or not handoff_status:
        return _base_censor_evidence_lint(
            "not_applicable",
            "missing_selector",
            role,
            handoff_status,
            censor_dispatch_id,
        )
    if plan_input.text is None:
        return _base_censor_evidence_lint(
            "incomplete",
            "plan_unreadable",
            role,
            handoff_status,
            censor_dispatch_id,
        )

    all_events = list(_iter_censor_evidence_events(plan_input))
    strict_receipt_status = censor_dispatch_id is not None
    selector_dispatch_receipts: list[CensorEvidenceEvent] = []
    if censor_dispatch_id is not None:
        selector_dispatch_receipts = [
            event
            for event in all_events
            if event.kind == "receipt"
            and censor_dispatch_id in _extract_broad_censor_dispatch_values(event.text)
        ]
        malformed_selector_receipts = [
            event
            for event in selector_dispatch_receipts
            if _censor_dispatch_id_field_count(event.text) != 1
            or len(_extract_censor_dispatch_ids(event.text)) != 1
            or _extract_censor_dispatch_ids(event.text)[0] != censor_dispatch_id
        ]
        if malformed_selector_receipts or len(selector_dispatch_receipts) > 1:
            selected_receipt = max(
                malformed_selector_receipts or selector_dispatch_receipts,
                key=lambda event: event.line,
            )
            result = _base_censor_evidence_lint(
                "incomplete",
                "ambiguous_censor_dispatch_id",
                role,
                handoff_status,
                censor_dispatch_id,
            )
            result.update(
                {
                    "receipt_line": selected_receipt.line,
                    "actual_censor_dispatch_id": "|".join(
                        _extract_broad_censor_dispatch_values(selected_receipt.text)
                    ),
                    "invalid_reasons": [
                        "duplicate_or_conflicting_censor_dispatch_id_fields"
                        if malformed_selector_receipts
                        else "duplicate_censor_dispatch_id_receipts"
                    ],
                    "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
                }
            )
            return result

    matching_timeline = [
        event
        for event in all_events
        if _event_matches(
            event,
            role,
            handoff_status,
            strict_receipt_status=strict_receipt_status,
        )
    ]
    matching_events = [
        event
        for event in matching_timeline
        if event.kind in {"receipt", "skip_hint"}
        and _event_matches(
            event,
            role,
            handoff_status,
            strict_receipt_status=strict_receipt_status,
        )
    ]
    if not matching_events:
        if censor_dispatch_id is not None and selector_dispatch_receipts:
            selected_receipt = selector_dispatch_receipts[0]
            result = _base_censor_evidence_lint(
                "incomplete",
                "missing_or_mismatched_censor_dispatch_id",
                role,
                handoff_status,
                censor_dispatch_id,
            )
            result.update(
                {
                    "receipt_line": selected_receipt.line,
                    "actual_censor_dispatch_id": censor_dispatch_id,
                    "invalid_reasons": ["dispatch_receipt_role_or_handoff_status_mismatch"],
                    "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
                }
            )
            return result
        return _base_censor_evidence_lint(
            "incomplete",
            "missing_current_receipt",
            role,
            handoff_status,
            censor_dispatch_id,
        )

    latest_event = max(matching_events, key=lambda event: event.line)
    if latest_event.kind == "skip_hint":
        if censor_dispatch_id is not None:
            result = _base_censor_evidence_lint(
                "incomplete",
                "missing_or_mismatched_censor_dispatch_id",
                role,
                handoff_status,
                censor_dispatch_id,
            )
            result.update(
                {
                    "receipt_line": latest_event.line,
                    "invalid_reasons": ["dispatch_selector_disallows_skip_hint"],
                    "selected_excerpt": " ".join(latest_event.text.split())[:500],
                }
            )
            return result
        consecutive_skip_tail = _consecutive_skip_tail(matching_timeline, latest_event)
        invalid_reasons = _skip_hint_invalid_reasons(
            latest_event,
            consecutive_skip_tail,
            role,
        )
        later_context_events = _unresolved_matching_context_events(
            matching_timeline,
            latest_event,
        )
        if later_context_events:
            _append_invalid_reason(
                invalid_reasons,
                "stale_current_receipt_after_later_matching_event",
            )
        result = _base_censor_evidence_lint(
            "incomplete" if invalid_reasons else "skipped_by_valid_hint",
            "invalid_skip_hint" if invalid_reasons else "valid_skip_hint",
            role,
            handoff_status,
            censor_dispatch_id,
        )
        result.update(
            {
                "receipt_line": latest_event.line,
                "invalid_reasons": invalid_reasons,
                "selected_excerpt": " ".join(
                    (
                        later_context_events[-1]
                        if later_context_events
                        else latest_event
                    ).text.split()
                )[:500],
            }
        )
        return result

    receipt_events = [event for event in matching_events if event.kind == "receipt"]
    if censor_dispatch_id is not None:
        dispatch_receipts = [
            event for event in receipt_events
            if censor_dispatch_id in _extract_censor_dispatch_ids(event.text)
        ]
        if dispatch_receipts:
            selected_receipt = dispatch_receipts[0]
        else:
            current_marked = [
                event for event in receipt_events if _has_censor_current_marker(event.text)
            ]
            selected_receipt = max(current_marked or receipt_events, key=lambda event: event.line)
            actual_dispatch_ids = _extract_censor_dispatch_ids(selected_receipt.text)
            dispatch_field_count = _censor_dispatch_id_field_count(selected_receipt.text)
            result = _base_censor_evidence_lint(
                "incomplete",
                "missing_or_mismatched_censor_dispatch_id",
                role,
                handoff_status,
                censor_dispatch_id,
            )
            result.update(
                {
                    "receipt_line": selected_receipt.line,
                    "actual_censor_dispatch_id": "|".join(actual_dispatch_ids),
                    "invalid_reasons": [
                        "invalid_censor_dispatch_id_field"
                        if dispatch_field_count and not actual_dispatch_ids
                        else (
                            "mismatched_censor_dispatch_id"
                            if actual_dispatch_ids
                            else "missing_censor_dispatch_id"
                        )
                    ],
                    "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
                }
            )
            return result
    else:
        selected_receipt = None

    if (
        censor_dispatch_id is not None
        and selected_receipt is not None
        and _censor_observations_boundary_invalid_reason(selected_receipt.text) is not None
    ):
        result = _base_censor_evidence_lint(
            "incomplete",
            "missing_or_invalid_fields",
            role,
            handoff_status,
            censor_dispatch_id,
        )
        result.update(
            {
                "receipt_line": selected_receipt.line,
                "actual_censor_dispatch_id": _extract_censor_dispatch_id(selected_receipt.text) or "",
                "invalid_reasons": [
                    _censor_observations_boundary_invalid_reason(selected_receipt.text)
                ],
                "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
            }
        )
        return result

    if (
        censor_dispatch_id is not None
        and selected_receipt is not None
        and not _has_censor_current_marker(selected_receipt.text)
    ):
        result = _base_censor_evidence_lint(
            "incomplete",
            "missing_or_mismatched_censor_dispatch_id",
            role,
            handoff_status,
            censor_dispatch_id,
        )
        result.update(
            {
                "receipt_line": selected_receipt.line,
                "actual_censor_dispatch_id": _extract_censor_dispatch_id(selected_receipt.text) or "",
                "invalid_reasons": [_censor_current_field_invalid_reason(selected_receipt.text)],
                "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
            }
        )
        return result

    current_marker = (
        _has_censor_current_marker
        if censor_dispatch_id is not None
        else _has_legacy_censor_current_marker
    )
    current_marked = [event for event in receipt_events if current_marker(event.text)]
    latest_receipt = max(receipt_events, key=lambda event: event.line)
    if selected_receipt is None:
        if current_marked:
            latest_current = max(current_marked, key=lambda event: event.line)
            selected_receipt = (
                latest_receipt if latest_receipt.line > latest_current.line else latest_current
            )
        elif len(receipt_events) == 1:
            selected_receipt = receipt_events[0]
        else:
            result = _base_censor_evidence_lint(
                "incomplete",
                "ambiguous_current_receipt",
                role,
                handoff_status,
            )
            result["invalid_reasons"] = [
                "multiple_same_role_status_receipts_without_current_selector"
            ]
            return result

    if censor_dispatch_id is not None:
        later_receipts = [
            event for event in receipt_events if event.line > selected_receipt.line
        ]
        if later_receipts:
            latest_later_receipt = max(later_receipts, key=lambda event: event.line)
            result = _base_censor_evidence_lint(
                "incomplete",
                "stale_censor_dispatch_id",
                role,
                handoff_status,
                censor_dispatch_id,
            )
            result.update(
                {
                    "receipt_line": selected_receipt.line,
                    "actual_censor_dispatch_id": _extract_censor_dispatch_id(selected_receipt.text) or "",
                    "invalid_reasons": ["later_same_role_status_receipt_supersedes_dispatch"],
                    "selected_excerpt": " ".join(latest_later_receipt.text.split())[:500],
                }
            )
            return result

    later_context_events = _later_matching_context_events(matching_timeline, selected_receipt)
    if later_context_events:
        result = _base_censor_evidence_lint(
            "incomplete",
            "missing_current_receipt",
            role,
            handoff_status,
            censor_dispatch_id,
        )
        result.update(
            {
                "receipt_line": selected_receipt.line,
                "invalid_reasons": ["stale_current_receipt_after_later_matching_event"],
                "selected_excerpt": " ".join(later_context_events[-1].text.split())[:500],
            }
        )
        return result

    missing_fields, invalid_reasons = _receipt_field_diagnostics(selected_receipt.text)

    result = _base_censor_evidence_lint(
        "incomplete" if missing_fields or invalid_reasons else "complete",
        "missing_or_invalid_fields" if missing_fields or invalid_reasons else "complete_current_receipt",
        role,
        handoff_status,
        censor_dispatch_id,
    )
    result.update(
        {
            "receipt_line": selected_receipt.line,
            "missing_fields": missing_fields,
            "invalid_reasons": invalid_reasons,
            "selected_excerpt": " ".join(selected_receipt.text.split())[:500],
        }
    )
    return result


def iter_receipt_candidates(markdown_inputs: Iterable[MarkdownInput]) -> Iterable[ReceiptCandidate]:
    seen: set[tuple[str, int, str]] = set()
    for markdown in markdown_inputs:
        for candidate in _line_candidates(markdown):
            key = (candidate.path, candidate.line, candidate.text)
            if key not in seen:
                seen.add(key)
                yield candidate
        for candidate in _role_assessment_candidates(markdown):
            key = (candidate.path, candidate.line, candidate.text)
            if key not in seen:
                seen.add(key)
                yield candidate


def _receipt_status(fields: dict[str, str]) -> tuple[str, list[str]]:
    missing = [label for label in REQUIRED_LABELS if not fields.get(label)]
    if not fields:
        return "missing", list(REQUIRED_LABELS)
    if missing:
        return "partial", missing
    return "complete", []


def _lower(value: str | None) -> str:
    return (value or "").lower()


def _noneish(value: str | None) -> bool:
    lowered = _lower(value).strip("` ")
    if not lowered:
        return True
    noneish_tokens = (
        "none",
        "no findings",
        "no finding",
        "n/a",
        "not applicable",
        "receipt missing",
    )
    return any(token in lowered for token in noneish_tokens)


def _historical_or_no_live(fields: dict[str, str]) -> bool:
    blob = _lower(" ".join(fields.get(label, "") for label in REQUIRED_LABELS))
    return any(
        token in blob
        for token in (
            "historical anchor only",
            "stale",
            "no live review artifact",
            "no live blocker",
            "review artifact not materialized",
        )
    )


def _live_blocker_signal(fields: dict[str, str]) -> bool:
    review = _lower(fields.get("Review verdict seen"))
    blockers = _lower(fields.get("Blocker IDs considered"))
    reconciliation = _lower(fields.get("Reconciliation"))
    if _historical_or_no_live(fields):
        return False
    return any(
        token in " ".join((review, blockers, reconciliation))
        for token in (
            "s1 blocker",
            "current blocker",
            "live blocker",
            "blocker=yes",
            "#b",
            " b1",
            " b2",
            " b3",
            " b4",
            " b5",
        )
    )


def _current_blocker_ref_signal(fields: dict[str, str]) -> bool:
    review = _lower(fields.get("Review verdict seen"))
    blockers = _lower(fields.get("Blocker IDs considered"))
    blob = " ".join((review, blockers))
    return any(
        token in blob
        for token in (
            "s1 blocker",
            "❌ s1 blocker",
            "current blocker",
            "blocker=yes",
            "#b",
            " b1",
            " b2",
            " b3",
            " b4",
            " b5",
        )
    )


def _exact_current_negative_signal(fields: dict[str, str]) -> bool:
    if _historical_or_no_live(fields):
        return False
    reconciliation = _lower(fields.get("Reconciliation"))
    return (
        "live blocker belongs here" in reconciliation
        and _current_blocker_ref_signal(fields)
    )


def classify_receipt(status: str, fields: dict[str, str]) -> tuple[str, str, str | None]:
    if status != "complete":
        return "receipt missing", f"{status} CENSOR receipt", "missing required CENSOR receipt labels"

    role_owned = fields.get("Role-owned finding", "")
    reconciliation = _lower(fields.get("Reconciliation"))
    final_verdict = _lower(fields.get("Final censor verdict"))
    live_blocker = _live_blocker_signal(fields)
    exact_current_negative = _exact_current_negative_signal(fields)
    role_owned_none = _noneish(role_owned)

    if exact_current_negative and role_owned_none and ("ok" in final_verdict or "no findings" in final_verdict):
        return "missed live blocker", "exact current negative signal with no role-owned finding", None
    if live_blocker and (
        not role_owned_none
        or "found gap" in final_verdict
        or "fixed" in final_verdict
    ):
        return "helped", "live blocker or handoff gap was tied to a role-owned finding", None
    if _historical_or_no_live(fields):
        if role_owned_none:
            return "noise/no-op", "no live blocker and no role-owned finding", None
        return "helped", "role-owned finding was recorded without live blocker lineage", None
    if live_blocker and role_owned_none:
        return (
            "UNCONFIRMED",
            "live blocker wording without exact current negative signal",
            "classification needs human review for ambiguous live blocker wording",
        )
    if role_owned_none and ("ok" in final_verdict or "no findings" in final_verdict):
        return "noise/no-op", "complete receipt with no finding", None
    if not role_owned_none:
        return "helped", "role-owned finding was recorded", None
    return "UNCONFIRMED", "receipt could not be classified from exact labels", "classification needs human review"


def _is_malformed_current_range(receipt: dict[str, object]) -> bool:
    invalid_reasons = receipt.get("invalid_reasons", [])
    if isinstance(invalid_reasons, list) and invalid_reasons:
        return True
    if receipt["status"] == "complete":
        return False
    fields = receipt.get("fields", {})
    assert isinstance(fields, dict)
    blob = _lower(str(receipt.get("excerpt", "")) + " " + " ".join(str(value) for value in fields.values()))
    if "no live review artifact" in blob or "historical anchor only" in blob:
        return False
    return any(
        token in blob
        for token in (
            "current-range",
            "current range",
            "current blocker",
            "live blocker belongs here",
            "s1 blocker",
            "#b",
        )
    )


def build_payload(
    plan_path: str,
    review_artifacts: list[str],
    censor_role: str | None = None,
    handoff_status: str | None = None,
    censor_dispatch_id: str | None = None,
) -> tuple[dict[str, object], int]:
    markdown_inputs: list[MarkdownInput] = []
    warnings: list[str] = []
    plan_input, plan_warnings = read_markdown("plan", plan_path)
    markdown_inputs.append(plan_input)
    warnings.extend(plan_warnings)
    for artifact_path in review_artifacts:
        review_input, review_warnings = read_markdown("review_artifact", artifact_path)
        markdown_inputs.append(review_input)
        warnings.extend(review_warnings)

    receipts: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    unconfirmed_reasons: list[str] = []
    role_quality = {category: 0 for category in ROLE_QUALITY_CATEGORIES}

    for candidate in iter_receipt_candidates(markdown_inputs):
        fields = parse_label_fields(candidate.text)
        status, missing_labels = _receipt_status(fields)
        deadlock_fields = {label: fields[label] for label in DEADLOCK_LABELS if fields.get(label)}
        receipt: dict[str, object] = {
            "source": candidate.source,
            "path": candidate.path,
            "line": candidate.line,
            "role": candidate.role,
            "parse_status": status,
            "status": status,
            "fields": {label: fields[label] for label in REQUIRED_LABELS if label in fields},
            "deadlock_fields": deadlock_fields,
            "missing_labels": missing_labels,
            "invalid_reasons": _censor_role_tag_invalid_reasons(candidate.text),
            "excerpt": " ".join(candidate.text.split())[:500],
        }
        receipt_index = len(receipts)
        receipts.append(receipt)

        role_tag_invalid_reasons = receipt["invalid_reasons"]
        assert isinstance(role_tag_invalid_reasons, list)
        if role_tag_invalid_reasons:
            category = "UNCONFIRMED"
            reason = "unsupported or malformed CENSOR role tag"
            unconfirmed_reason = ", ".join(str(item) for item in role_tag_invalid_reasons)
            warnings.append(
                f"{candidate.path}:{candidate.line} invalid CENSOR role tag: {unconfirmed_reason}"
            )
        else:
            category, reason, unconfirmed_reason = classify_receipt(status, fields)
        role_quality[category] += 1
        finding = {
            "receipt_index": receipt_index,
            "source": candidate.source,
            "path": candidate.path,
            "line": candidate.line,
            "role": candidate.role,
            "category": category,
            "reason": reason,
            "blocker_ids": fields.get("Blocker IDs considered", ""),
            "review_verdict": fields.get("Review verdict seen", ""),
            "final_censor_verdict": fields.get("Final censor verdict", ""),
            "role_owned_finding": fields.get("Role-owned finding", ""),
        }
        findings.append(finding)
        if missing_labels:
            warnings.append(
                f"{candidate.path}:{candidate.line} {candidate.role} CENSOR receipt {status}; "
                f"missing: {', '.join(missing_labels)}"
            )
        if unconfirmed_reason:
            unconfirmed_reasons.append(f"{candidate.path}:{candidate.line}: {unconfirmed_reason}")

    if not receipts:
        role_quality["receipt missing"] += 1
        warnings.append("No CENSOR receipt candidates found in supplied markdown inputs.")
        unconfirmed_reasons.append("No structured CENSOR receipt labels were found.")
        findings.append(
            {
                "receipt_index": None,
                "source": "inputs",
                "path": plan_path,
                "line": 0,
                "role": "Unknown",
                "category": "receipt missing",
                "reason": "no CENSOR receipt candidates found",
                "blocker_ids": "",
                "review_verdict": "",
                "final_censor_verdict": "",
                "role_owned_finding": "",
            }
        )

    malformed_current_range = [receipt for receipt in receipts if _is_malformed_current_range(receipt)]
    if malformed_current_range:
        warnings.append(
            "Malformed current-range CENSOR receipts: "
            + ", ".join(f"{receipt['path']}:{receipt['line']}" for receipt in malformed_current_range)
        )

    summary = {
        "receipt_count": len(receipts),
        "complete_receipt_count": sum(1 for receipt in receipts if receipt["status"] == "complete"),
        "partial_receipt_count": sum(1 for receipt in receipts if receipt["status"] == "partial"),
        "missing_receipt_count": (
            sum(1 for receipt in receipts if receipt["status"] == "missing") + (1 if not receipts else 0)
        ),
        "finding_count": len(findings),
        "warning_count": len(warnings),
        "unconfirmed_count": len(unconfirmed_reasons),
        "malformed_current_range_count": len(malformed_current_range),
        "role_quality": role_quality,
    }

    payload: dict[str, object] = {
        "inputs": {
            "plan": plan_path,
            "review_artifacts": review_artifacts,
        },
        "censor_evidence_lint": build_censor_evidence_lint(
            plan_input,
            role=censor_role,
            handoff_status=handoff_status,
            censor_dispatch_id=censor_dispatch_id,
        ),
        "summary": summary,
        "receipts": receipts,
        "findings": findings,
        "warnings": warnings,
        "unconfirmed_reasons": unconfirmed_reasons,
    }
    return payload, 2 if malformed_current_range else 0


def format_text(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    role_quality = summary["role_quality"]
    assert isinstance(role_quality, dict)
    lines = [
        "censor-receipts-harvest:",
        f" receipts={summary['receipt_count']} complete={summary['complete_receipt_count']} "
        f"partial={summary['partial_receipt_count']} missing={summary['missing_receipt_count']}",
        " role_quality="
        + "; ".join(f"{category}={role_quality.get(category, 0)}" for category in ROLE_QUALITY_CATEGORIES),
    ]
    censor_lint = payload.get("censor_evidence_lint")
    if isinstance(censor_lint, dict):
        lines.append(
            " censor_evidence_lint="
            f"state={censor_lint.get('state')} reason_code={censor_lint.get('reason_code')} "
            f"role={censor_lint.get('role')} handoff_status={censor_lint.get('handoff_status')}"
        )
        lines.append(" current_handoff_gate=censor_evidence_lint.state (receipts[].status is parse_status only)")
    findings = payload["findings"]
    assert isinstance(findings, list)
    if findings:
        lines.append("findings:")
        for finding in findings:
            assert isinstance(finding, dict)
            receipt_ref = (
                "N/A"
                if finding.get("receipt_index") is None
                else f"{finding.get('path')}:{finding.get('line')}"
            )
            lines.append(
                f"- {receipt_ref} role={finding.get('role')} category={finding.get('category')} "
                f"reason={finding.get('reason')} review_verdict={finding.get('review_verdict')} "
                f"final_censor_verdict={finding.get('final_censor_verdict')}"
            )
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    if warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    unconfirmed = payload["unconfirmed_reasons"]
    assert isinstance(unconfirmed, list)
    if unconfirmed:
        lines.append("unconfirmed_reasons:")
        lines.extend(f"- {reason}" for reason in unconfirmed)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="censor_receipts_harvest",
        description="Extract structured CENSOR receipt labels and role-quality readback from markdown.",
    )
    parser.add_argument("--plan", required=True, help="Plan markdown path.")
    parser.add_argument(
        "--review-artifact",
        action="append",
        default=[],
        help="Review/audit markdown artifact path. Repeat for multiple artifacts.",
    )
    parser.add_argument(
        "--censor-role",
        help="Optional CENSOR role selector for the additive censor_evidence_lint readback.",
    )
    parser.add_argument(
        "--handoff-status",
        help="Optional post-handoff status selector for the additive censor_evidence_lint readback.",
    )
    parser.add_argument(
        "--censor-dispatch-id",
        help="Optional exact CENSOR dispatch provenance selector for censor_evidence_lint.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="text", help="Output format.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload, exit_code = build_payload(
        args.plan,
        list(args.review_artifact),
        censor_role=args.censor_role,
        handoff_status=args.handoff_status,
        censor_dispatch_id=args.censor_dispatch_id,
    )
    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(format_text(payload) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

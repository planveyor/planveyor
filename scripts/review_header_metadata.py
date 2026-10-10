#!/usr/bin/env python3
"""Extract canonical review metadata from the bounded post-H1 preamble."""

from __future__ import annotations

import re
from collections.abc import Sequence


HEADER_FIELD_RE = re.compile(r"^\*\*(?P<label>[^*\n]+?):\*\*\s*(?P<value>.*?)\s*$")


def normalize_label(value: str) -> str:
    return " ".join(value.casefold().split())


def extract_header_fields(lines: Sequence[str]) -> list[tuple[int, str, str, str]]:
    """Return line number, normalized label, value, and raw line for preamble fields."""

    fields: list[tuple[int, str, str, str]] = []
    saw_h1 = False
    for line_no, line in enumerate(lines, start=1):
        if not saw_h1:
            if not line.strip():
                continue
            if line.startswith("# "):
                saw_h1 = True
                continue
            break
        if not line.strip():
            continue
        match = HEADER_FIELD_RE.fullmatch(line)
        if match is None:
            break
        fields.append(
            (
                line_no,
                normalize_label(match.group("label")),
                match.group("value").strip(),
                line,
            )
        )
    return fields


def header_values(lines: Sequence[str], label: str) -> list[tuple[int, str]]:
    normalized = normalize_label(label)
    return [
        (line_no, value)
        for line_no, field_label, value, _raw_line in extract_header_fields(lines)
        if field_label == normalized
    ]


def singleton_header_value(lines: Sequence[str], label: str) -> tuple[str | None, int]:
    normalized = normalize_label(label)
    matches = [
        (line_no, value, raw_line)
        for line_no, field_label, value, raw_line in extract_header_fields(lines)
        if field_label == normalized
    ]
    if len(matches) == 1:
        line_no, value, raw_line = matches[0]
        raw_match = HEADER_FIELD_RE.fullmatch(raw_line)
        if raw_match is not None and raw_match.group("label").casefold() == normalized:
            return value, line_no
        return None, line_no
    if len(matches) > 1:
        return None, matches[1][0]
    return None, 1


def duplicate_singleton_fields(
    lines: Sequence[str],
    labels: Sequence[str],
) -> list[tuple[int, str]]:
    duplicates: list[tuple[int, str]] = []
    for label in labels:
        matches = header_values(lines, label)
        duplicates.extend((line_no, normalize_label(label)) for line_no, _value in matches[1:])
    return sorted(duplicates)

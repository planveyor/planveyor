#!/usr/bin/env python3
"""Shared dependency-light review artifact schema contract."""

from __future__ import annotations

import re


CURRENT_REVIEW_SCHEMA_VERSION = "review.v1"

CODE_DOC_REVIEW_DRAFT_STATUS = "Черновик"
CODE_DOC_REVIEW_OK_STATUS = "✅ OK"
CODE_DOC_REVIEW_BLOCKER_STATUS = "❌ S1 blocker(ы)"
MERGE_NOTES_DRAFT_STATUS = "Draft"
MERGE_NOTES_DONE_STATUS = "✅ Done"


def normalize_review_status(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.replace("`", "").casefold()).strip()


CODE_DOC_REVIEW_STATUS_NORMS = frozenset(
    normalize_review_status(status)
    for status in (
        CODE_DOC_REVIEW_DRAFT_STATUS,
        CODE_DOC_REVIEW_OK_STATUS,
        CODE_DOC_REVIEW_BLOCKER_STATUS,
    )
)
MERGE_NOTES_STATUS_NORMS = frozenset(
    normalize_review_status(status)
    for status in (
        MERGE_NOTES_DRAFT_STATUS,
        MERGE_NOTES_DONE_STATUS,
    )
)
CODE_DOC_REVIEW_FINAL_STATUS_NORMS = frozenset(
    normalize_review_status(status)
    for status in (
        CODE_DOC_REVIEW_OK_STATUS,
        CODE_DOC_REVIEW_BLOCKER_STATUS,
    )
)
CODE_DOC_REVIEW_OK_STATUS_NORM = normalize_review_status(CODE_DOC_REVIEW_OK_STATUS)
CODE_DOC_REVIEW_BLOCKER_STATUS_NORM = normalize_review_status(CODE_DOC_REVIEW_BLOCKER_STATUS)


def review_blocker_status_regex() -> str:
    return r"(?:❌\s*)?s1\s+blocker(?:\(ы\))?"

#!/usr/bin/env python3
"""Apply one typed V2 follow-ups ingress with a serial CAS boundary.

This module intentionally owns the only durable V2 row write.  Roles publish
read-only terminal declarations, generic harvesters freeze source-object
batches, and promotion submits one checked request; every profile calls this
boundary instead of editing a durable carrier itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:  # direct script execution keeps ``scripts`` itself on sys.path
    from scripts import followups_capture
    from scripts import followups_index_rebuild
    from scripts import followups_lint
except ModuleNotFoundError:
    import followups_capture
    import followups_index_rebuild
    import followups_lint


FROZEN_SCHEMA = "followups_capture_cycle.v2"
GENERIC_BATCH_SCHEMA = "followups_generic_batch.v2"
GENERIC_SOURCE_KIND = "generic_harvest"
GENERIC_PRODUCER_IDS = {"code_reviews_harvest"}
LOCK_REL_PATH = ".tmp/followups_apply.v2.lock"
_GENERIC_SOURCE_REF_RE = re.compile(r"^(?P<path>[^#]+)#(?P<anchor>L[1-9][0-9]*)$")


class ApplyError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class FrozenRow:
    followup_path: str
    payload: dict[str, object]
    digest: str
    owner: str
    expected_current_digest: str | None = None

    @property
    def tuple(self) -> tuple[str, str]:
        source_ref = self.payload.get("source_ref")
        item_id = self.payload.get("item_id")
        assert isinstance(source_ref, str) and isinstance(item_id, str)
        return source_ref, item_id


@dataclass(frozen=True)
class GenericSourceObject:
    source_path: str
    source_sha256: str
    anchors: tuple[str, ...]


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_followup_path(raw: object) -> str:
    if not isinstance(raw, str):
        raise ApplyError("frozen_row_path_invalid", "frozen row requires a string followup_path")
    try:
        path = followups_capture.validate_followup_relpath(raw)
    except followups_capture.CaptureError as exc:
        raise ApplyError("frozen_row_path_invalid", str(exc)) from exc
    if Path(path).name in followups_lint.FOLLOWUPS_IGNORE:
        raise ApplyError(
            "frozen_row_path_ignored",
            f"the sole writer must not materialize a V2 row in ignored carrier {path}",
        )
    return path


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApplyError("frozen_manifest_invalid", f"{field} must be a non-empty string")
    return value.strip()


def _tuple_key(source_ref: str, item_id: str) -> str:
    return f"{source_ref}\u0000{item_id}"


def _normalize_row_payload(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ApplyError("frozen_row_invalid", "frozen row payload must be an object")
    required = {
        "priority",
        "summary",
        "cluster",
        "to",
        "status",
        "plan",
        "why",
        "item_id",
        "source_ref",
        "disposition_kind",
        "disposition_ref",
        "disposition_commit_oid",
        "reason",
    }
    missing = sorted(required - set(raw))
    extra = sorted(
        set(raw)
        - required
        - {"tags", *followups_lint.V2_LEGACY_BRIDGE_FIELDS, *followups_lint.V2_PRESENTATION_FIELDS}
    )
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise ApplyError("frozen_row_shape_invalid", "frozen row schema mismatch: " + "; ".join(detail))
    payload = {key: raw.get(key) for key in required}
    for key in followups_lint.V2_LEGACY_BRIDGE_FIELDS:
        payload[key] = raw.get(key)
    for key in followups_lint.V2_PRESENTATION_FIELDS:
        if raw.get(key) is not None:
            if not isinstance(raw.get(key), str) or not str(raw[key]).strip():
                raise ApplyError("frozen_row_shape_invalid", f"frozen row {key} must be a non-empty string when supplied")
            payload[key] = str(raw[key]).strip()
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ApplyError("frozen_row_shape_invalid", "frozen row tags must be a string array")
    payload["tags"] = list(tags)
    rendered = followups_lint.render_v2_row(payload)
    parsed = followups_lint.parse_followup_item("docs/followups/_frozen.md", 1, rendered)
    if parsed is None or followups_lint.lint_v2_item(
        parsed,
        Path("."),
        validate_legacy_bridge_source=False,
        validate_disposition_source=False,
    ):
        raise ApplyError("frozen_row_semantic_invalid", "frozen V2 row fails the canonical V2 field matrix")
    source_ref = followups_lint.normalize_source_ref(parsed.source_ref)
    if source_ref is None or parsed.item_id is None:
        raise ApplyError("frozen_row_semantic_invalid", "frozen V2 row lacks a valid tuple")
    return followups_lint.v2_row_payload(parsed)


def load_frozen_manifest(value: Mapping[str, object]) -> tuple[dict[str, object], list[FrozenRow]]:
    if value.get("schema_version") != FROZEN_SCHEMA:
        raise ApplyError("frozen_manifest_schema_invalid", f"schema_version must be {FROZEN_SCHEMA!r}")
    generic_profile_fields = {
        "source_kind",
        "producer_id",
        "target_followup_path",
        "target_header",
        "source_objects",
    }
    mixed_profile_fields = sorted(generic_profile_fields & set(value))
    if mixed_profile_fields:
        raise ApplyError(
            "frozen_manifest_generic_profile_impersonation",
            "terminal frozen manifest must not carry generic producer fields: " + ", ".join(mixed_profile_fields),
        )
    declaration_roles = list(followups_capture.REQUIRED_ROLES)
    if value.get("declaration_roles") != declaration_roles:
        raise ApplyError(
            "frozen_manifest_declaration_roles_invalid",
            f"declaration_roles must exactly equal {declaration_roles!r}",
        )
    raw_plan_ref = _string(value.get("plan_ref"), field="plan_ref")
    try:
        plan_ref = followups_capture.normalize_plan_ref(raw_plan_ref)
    except followups_capture.CaptureError as exc:
        raise ApplyError("frozen_manifest_plan_ref_invalid", str(exc)) from exc
    _string(value.get("source_terminal_commit_oid"), field="source_terminal_commit_oid")
    _string(value.get("source_plan_blob_oid"), field="source_plan_blob_oid")
    baseline = value.get("baseline_followups_snapshot")
    if not isinstance(baseline, dict):
        raise ApplyError("frozen_manifest_baseline_invalid", "baseline_followups_snapshot must be an object")
    raw_expected = value.get("expected_owned_tuples")
    raw_owners = value.get("tuple_owners")
    raw_rows = value.get("proposed_rows")
    if not isinstance(raw_expected, list) or not isinstance(raw_owners, dict) or not isinstance(raw_rows, list):
        raise ApplyError("frozen_manifest_shape_invalid", "manifest requires expected_owned_tuples, tuple_owners and proposed_rows")
    expected: list[tuple[str, str]] = []
    for raw_tuple in raw_expected:
        if not isinstance(raw_tuple, dict):
            raise ApplyError("frozen_manifest_tuple_invalid", "expected tuple must be an object")
        source_ref = followups_lint.normalize_source_ref(raw_tuple.get("source_ref") if isinstance(raw_tuple.get("source_ref"), str) else None)
        item_id = raw_tuple.get("item_id")
        if source_ref is None or not isinstance(item_id, str) or not followups_lint.V2_ITEM_ID_RE.fullmatch(item_id):
            raise ApplyError("frozen_manifest_tuple_invalid", "expected tuple has invalid source_ref or item_id")
        expected.append((source_ref, item_id))
    if len(expected) != len(set(expected)) or expected != sorted(expected):
        raise ApplyError("frozen_manifest_tuple_invalid", "expected_owned_tuples must be sorted and unique")
    raw_expected_current = value.get("expected_current_row_digests", {})
    if not isinstance(raw_expected_current, dict):
        raise ApplyError(
            "frozen_manifest_current_digest_invalid",
            "expected_current_row_digests must be an object when supplied",
        )
    expected_tuple_keys = {_tuple_key(*entry) for entry in expected}
    if not set(raw_expected_current).issubset(expected_tuple_keys):
        raise ApplyError(
            "frozen_manifest_current_digest_invalid",
            "expected_current_row_digests may name only frozen expected tuples",
        )
    expected_zero_reason = value.get("expected_zero_reason")
    if expected:
        if expected_zero_reason is not None:
            raise ApplyError("frozen_manifest_zero_invalid", "expected_zero_reason is only allowed for an empty union")
    elif not isinstance(expected_zero_reason, str) or not expected_zero_reason.strip():
        raise ApplyError("frozen_manifest_zero_invalid", "empty union requires a non-empty expected_zero_reason")

    rows: list[FrozenRow] = []
    seen_rows: set[tuple[str, str]] = set()
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ApplyError("frozen_row_invalid", "proposed_rows entries must be objects")
        followup_path = _safe_followup_path(raw_row.get("followup_path"))
        payload = _normalize_row_payload(raw_row.get("payload"))
        digest = _string(raw_row.get("row_digest"), field="row_digest")
        actual_digest = _sha256(_canonical_json(payload))
        if digest != actual_digest:
            raise ApplyError("frozen_row_digest_mismatch", "frozen row digest does not match normalized payload")
        tuple_value = (str(payload["source_ref"]), str(payload["item_id"]))
        owner = raw_owners.get(_tuple_key(*tuple_value))
        if not isinstance(owner, str) or owner not in declaration_roles:
            raise ApplyError(
                "frozen_manifest_owner_invalid",
                "every frozen tuple owner must be one exact declaration role",
            )
        if tuple_value in seen_rows:
            raise ApplyError("frozen_manifest_overlap", "frozen proposed_rows contains a duplicate tuple")
        seen_rows.add(tuple_value)
        expected_current_digest = raw_expected_current.get(_tuple_key(*tuple_value))
        if expected_current_digest is not None:
            if not isinstance(expected_current_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_current_digest):
                raise ApplyError(
                    "frozen_manifest_current_digest_invalid",
                    "expected current row digest must be one 64-character lower-case SHA-256 value",
                )
        rows.append(FrozenRow(followup_path, payload, digest, owner, expected_current_digest))
    if set(expected) != seen_rows or len(rows) != len(expected):
        raise ApplyError("frozen_manifest_payload_mismatch", "proposed_rows must cover every expected tuple exactly once")
    if set(raw_owners) != {_tuple_key(*entry) for entry in expected}:
        raise ApplyError("frozen_manifest_owner_invalid", "tuple_owners must exactly match expected tuples")
    return dict(value), rows


def _generic_source_ref(raw: str) -> tuple[str, str]:
    match = _GENERIC_SOURCE_REF_RE.fullmatch(raw)
    if match is None:
        raise ApplyError(
            "generic_source_ref_invalid",
            "generic source_ref must be one safe repo-relative path with one #L<line> anchor",
        )
    try:
        source_path = followups_capture._normalize_repo_regular_relpath(match.group("path"))
    except followups_capture.CaptureError as exc:
        raise ApplyError("generic_source_path_invalid", str(exc)) from exc
    return source_path, match.group("anchor")


def load_generic_batch(
    value: Mapping[str, object],
) -> tuple[dict[str, object], list[FrozenRow], list[GenericSourceObject]]:
    """Validate a read-only generic-harvest ingress without writing a carrier."""

    if value.get("schema_version") != GENERIC_BATCH_SCHEMA:
        raise ApplyError("generic_batch_schema_invalid", f"schema_version must be {GENERIC_BATCH_SCHEMA!r}")
    if value.get("source_kind") != GENERIC_SOURCE_KIND:
        raise ApplyError("generic_batch_source_kind_invalid", "generic batch requires literal source_kind=generic_harvest")
    producer_id = value.get("producer_id")
    if producer_id not in GENERIC_PRODUCER_IDS:
        raise ApplyError("generic_batch_producer_invalid", "generic batch producer_id is not one declared harvester")
    forbidden_terminal_fields = {
        "plan_ref",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
        "declaration_roles",
        "tuple_owners",
    }
    present_terminal_fields = sorted(forbidden_terminal_fields & set(value))
    if present_terminal_fields:
        raise ApplyError(
            "generic_batch_terminal_profile_impersonation",
            "generic batch must not carry terminal declaration fields: " + ", ".join(present_terminal_fields),
        )
    allowed_fields = {
        "schema_version",
        "source_kind",
        "producer_id",
        "target_followup_path",
        "target_header",
        "baseline_followups_snapshot",
        "source_objects",
        "expected_owned_tuples",
        "expected_zero_reason",
        "proposed_rows",
    }
    unexpected_fields = sorted(set(value) - allowed_fields)
    if unexpected_fields:
        raise ApplyError(
            "generic_batch_shape_invalid",
            "generic batch has unsupported fields: " + ", ".join(unexpected_fields),
        )
    target_followup_path = _safe_followup_path(value.get("target_followup_path"))
    target_header = value.get("target_header")
    if target_header is None:
        target_header = _new_v2_file_text(target_followup_path)
    else:
        if not isinstance(target_header, str) or not target_header.endswith("\n"):
            raise ApplyError("generic_target_header_invalid", "generic target_header must be one newline-terminated string when supplied")
        header_parsed = followups_lint.parse_followup_text(target_header, target_followup_path, Path(target_followup_path))
        header_schema, header_findings = followups_lint.classify_followups_schema_version(header_parsed)
        if header_schema != "v2" or header_findings or header_parsed.items:
            raise ApplyError(
                "generic_target_header_invalid",
                "generic target_header must be an empty lint-compatible followups.v2 carrier header",
            )
    baseline = value.get("baseline_followups_snapshot")
    if not isinstance(baseline, dict):
        raise ApplyError("generic_batch_baseline_invalid", "generic batch requires a baseline followups snapshot object")
    raw_sources = value.get("source_objects")
    raw_expected = value.get("expected_owned_tuples")
    raw_rows = value.get("proposed_rows")
    if not isinstance(raw_sources, list) or not isinstance(raw_expected, list) or not isinstance(raw_rows, list):
        raise ApplyError("generic_batch_shape_invalid", "generic batch requires source_objects, expected_owned_tuples and proposed_rows arrays")

    source_objects: list[GenericSourceObject] = []
    source_anchor_pairs: set[tuple[str, str]] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict) or set(raw_source) != {"source_path", "source_sha256", "anchors"}:
            raise ApplyError("generic_source_object_invalid", "generic source object must contain only source_path, source_sha256 and anchors")
        raw_path = raw_source.get("source_path")
        raw_sha256 = raw_source.get("source_sha256")
        raw_anchors = raw_source.get("anchors")
        if not isinstance(raw_path, str):
            raise ApplyError("generic_source_object_invalid", "generic source_path must be a string")
        try:
            source_path = followups_capture._normalize_repo_regular_relpath(raw_path)
        except followups_capture.CaptureError as exc:
            raise ApplyError("generic_source_path_invalid", str(exc)) from exc
        if not isinstance(raw_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", raw_sha256):
            raise ApplyError("generic_source_hash_invalid", "generic source_sha256 must be one lower-case SHA-256 digest")
        if not isinstance(raw_anchors, list) or any(not isinstance(anchor, str) for anchor in raw_anchors):
            raise ApplyError("generic_source_anchor_invalid", "generic source anchors must be a string array")
        anchors = tuple(raw_anchors)
        if anchors != tuple(sorted(set(anchors))) or any(not re.fullmatch(r"L[1-9][0-9]*", anchor) for anchor in anchors):
            raise ApplyError("generic_source_anchor_invalid", "generic source anchors must be sorted unique L<line> values")
        for anchor in anchors:
            pair = (source_path, anchor)
            if pair in source_anchor_pairs:
                raise ApplyError("generic_source_anchor_duplicate", "one generic source anchor is declared more than once")
            source_anchor_pairs.add(pair)
        source_objects.append(GenericSourceObject(source_path, raw_sha256, anchors))
    if [source.source_path for source in source_objects] != sorted(source.source_path for source in source_objects):
        raise ApplyError("generic_source_object_invalid", "generic source_objects must be sorted by source_path")
    if len({source.source_path for source in source_objects}) != len(source_objects):
        raise ApplyError("generic_source_object_invalid", "generic source_objects must not repeat a source_path")

    expected: list[tuple[str, str]] = []
    for raw_tuple in raw_expected:
        if not isinstance(raw_tuple, dict) or set(raw_tuple) != {"source_ref", "item_id"}:
            raise ApplyError("generic_batch_tuple_invalid", "generic expected tuple must contain source_ref and item_id")
        source_ref = followups_lint.normalize_source_ref(raw_tuple.get("source_ref") if isinstance(raw_tuple.get("source_ref"), str) else None)
        item_id = raw_tuple.get("item_id")
        if source_ref is None or not isinstance(item_id, str) or not followups_lint.V2_ITEM_ID_RE.fullmatch(item_id):
            raise ApplyError("generic_batch_tuple_invalid", "generic expected tuple has invalid source_ref or item_id")
        expected.append((source_ref, item_id))
    if expected != sorted(set(expected)):
        raise ApplyError("generic_batch_tuple_invalid", "generic expected_owned_tuples must be sorted and unique")
    expected_zero_reason = value.get("expected_zero_reason")
    if expected:
        if expected_zero_reason is not None:
            raise ApplyError("generic_batch_zero_invalid", "generic expected_zero_reason is only allowed for an empty batch")
    elif not isinstance(expected_zero_reason, str) or not expected_zero_reason.strip():
        raise ApplyError("generic_batch_zero_invalid", "empty generic batch requires a non-empty expected_zero_reason")

    rows: list[FrozenRow] = []
    seen_rows: set[tuple[str, str]] = set()
    used_source_anchors: set[tuple[str, str]] = set()
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict) or set(raw_row) != {
            "followup_path",
            "payload",
            "row_digest",
            "expected_current_row_digest",
        }:
            raise ApplyError(
                "generic_row_invalid",
                "generic proposed row must contain followup_path, payload, row_digest and expected_current_row_digest",
            )
        followup_path = _safe_followup_path(raw_row.get("followup_path"))
        if followup_path != target_followup_path:
            raise ApplyError("generic_target_path_mismatch", "every generic row must use the declared target_followup_path")
        payload = _normalize_row_payload(raw_row.get("payload"))
        digest = _string(raw_row.get("row_digest"), field="row_digest")
        if digest != _sha256(_canonical_json(payload)):
            raise ApplyError("generic_row_digest_mismatch", "generic row digest does not match normalized payload")
        expected_current_digest = raw_row.get("expected_current_row_digest")
        if expected_current_digest is not None and (
            not isinstance(expected_current_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_current_digest)
        ):
            raise ApplyError("generic_current_digest_invalid", "generic expected_current_row_digest must be null or one lower-case SHA-256 digest")
        tuple_value = (str(payload["source_ref"]), str(payload["item_id"]))
        if tuple_value in seen_rows:
            raise ApplyError("generic_batch_overlap", "generic proposed_rows contains a duplicate tuple")
        seen_rows.add(tuple_value)
        source_path, anchor = _generic_source_ref(tuple_value[0])
        if (source_path, anchor) not in source_anchor_pairs:
            raise ApplyError("generic_source_ref_uncovered", "generic row source_ref is not owned by one frozen source object anchor")
        used_source_anchors.add((source_path, anchor))
        rows.append(FrozenRow(followup_path, payload, digest, str(producer_id), expected_current_digest))
    if set(expected) != seen_rows or len(rows) != len(expected):
        raise ApplyError("generic_batch_payload_mismatch", "generic proposed_rows must cover every expected tuple exactly once")
    if expected and not source_objects:
        raise ApplyError("generic_source_object_invalid", "a non-empty generic batch requires frozen source objects")
    if [row.tuple for row in rows] != sorted(row.tuple for row in rows):
        raise ApplyError("generic_batch_row_order_invalid", "generic proposed_rows must be sorted by source_ref and item_id")
    if used_source_anchors != source_anchor_pairs:
        raise ApplyError("generic_source_anchor_uncovered", "generic source object anchors must exactly match the proposed source_ref anchors")
    frozen = dict(value)
    frozen["target_header"] = target_header
    return frozen, rows, source_objects


def _snapshot_equals(expected: Mapping[str, object], actual: Mapping[str, object]) -> bool:
    return _canonical_json(expected) == _canonical_json(actual)


def _new_v2_file_text(path: str) -> str:
    stem = Path(path).stem
    return (
        f"# Follow-ups backlog — {stem}\n\n"
        "**Date:** N/A (why=serial V2 writer stores row authority, not a second timestamp truth)\n"
        "**Source:** external-only follow-ups authority V2\n"
        "**Status:** Draft\n"
        "**Schema version:** followups.v2\n\n"
        "## Follow-ups (backlog)\n"
    )


def _current_authoritative_v2_carriers(
    current_snapshot: Mapping[str, Mapping[str, object]],
    current_bytes: Mapping[str, bytes],
    root: Path,
) -> dict[str, followups_lint.FollowupFile]:
    """Admit only a complete blocker-free V2 carrier inventory."""

    inventory = followups_lint._inventory_followups_snapshot(root, current_snapshot, current_bytes)
    if inventory.blockers:
        codes = ", ".join(sorted({finding.code for finding in inventory.blockers}))
        raise ApplyError(
            "v2_integrity_blocker",
            f"complete follow-ups snapshot is not lint-green: V2 integrity blocker ({codes})",
        )
    return dict(inventory.valid_v2)


def _global_tuple_owners(
    carriers: Mapping[str, followups_lint.FollowupFile],
) -> dict[tuple[str, str], set[str]]:
    owners: dict[tuple[str, str], set[str]] = {}
    for rel_path, parsed in carriers.items():
        for item in parsed.items:
            source_ref = followups_lint.normalize_source_ref(item.source_ref)
            if source_ref is None or item.item_id is None:
                continue
            owners.setdefault((source_ref, item.item_id), set()).add(rel_path)
    return owners


def _render_global_v2_candidates(
    current_snapshot: Mapping[str, Mapping[str, object]],
    current_bytes: Mapping[str, bytes],
    rows: list[FrozenRow],
    root: Path,
    *,
    generic: bool = False,
    new_file_texts: Mapping[str, str] | None = None,
) -> tuple[dict[str, bytes], bool]:
    """Render and lint the complete resulting authoritative V2 carrier set.

    The caller performs this again after acquiring the serial lock.  Legacy V1
    carriers remain outside this V2-only authority check by design.
    """

    current_v2 = _current_authoritative_v2_carriers(current_snapshot, current_bytes, root)
    current_owners = _global_tuple_owners(current_v2)
    for row in rows:
        foreign_owners = sorted(current_owners.get(row.tuple, set()) - {row.followup_path})
        if foreign_owners:
            raise ApplyError(
                "global_tuple_owner_conflict",
                (
                    f"proposed V2 tuple {row.tuple!r} is already owned by another authoritative carrier: "
                    + ", ".join(foreign_owners)
                ),
            )

    by_path: dict[str, list[FrozenRow]] = {}
    for row in rows:
        by_path.setdefault(row.followup_path, []).append(row)
    rendered: dict[str, bytes] = {}
    for rel_path, path_rows in sorted(by_path.items()):
        rendered[rel_path] = _append_rows(
            current_bytes.get(rel_path, b""),
            rel_path,
            path_rows,
            root,
            generic=generic,
            new_file_text=(new_file_texts or {}).get(rel_path),
        )

    candidate_bytes = dict(current_bytes)
    candidate_snapshot = dict(current_snapshot)
    for rel_path, data in rendered.items():
        candidate_bytes[rel_path] = data
        candidate_snapshot[rel_path] = {
            "sha256": _sha256(data),
            "file_type": "regular",
            "st_size": len(data),
        }
    candidate_inventory = followups_lint._inventory_followups_snapshot(root, candidate_snapshot, candidate_bytes)
    if candidate_inventory.blockers:
        codes = ", ".join(sorted({finding.code for finding in candidate_inventory.blockers}))
        raise ApplyError(
            "v2_integrity_blocker",
            f"complete resulting V2 carrier set is not lint-green: V2 integrity blocker ({codes})",
        )
    candidates = dict(candidate_inventory.valid_v2)
    findings = followups_lint.lint_followup_files(
        [candidates[path] for path in sorted(candidates)],
        root,
    )
    if findings:
        codes = ", ".join(sorted({finding.code for finding in findings}))
        raise ApplyError(
            "global_v2_candidate_not_lint_green",
            f"complete resulting authoritative V2 carrier set is not lint-green ({codes})",
        )
    idempotent = bool(rows) and all(
        rendered[path] == current_bytes.get(path, b"") for path in rendered
    )
    return rendered, idempotent


def _append_rows(
    base: bytes,
    rel_path: str,
    rows: list[FrozenRow],
    root: Path,
    *,
    generic: bool = False,
    new_file_text: str | None = None,
) -> bytes:
    if base:
        try:
            text = base.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApplyError("current_file_not_utf8", f"{rel_path} is not UTF-8") from exc
    else:
        text = new_file_text if new_file_text is not None else _new_v2_file_text(rel_path)
    if not any(followups_lint.FOLLOWUPS_H2_RE.match(line) for line in text.splitlines()):
        raise ApplyError("current_file_schema_invalid", f"{rel_path} is missing its canonical ## Follow-ups section")
    parsed = followups_lint.parse_followup_text(text, rel_path, root / rel_path)
    schema, schema_findings = followups_lint.classify_followups_schema_version(parsed)
    if schema != "v2" or schema_findings:
        raise ApplyError("current_file_schema_invalid", f"{rel_path} must be a lint-green followups.v2 carrier")
    current_findings = followups_lint.lint_followup_files([parsed], root)
    if current_findings:
        codes = ", ".join(sorted({finding.code for finding in current_findings}))
        raise ApplyError(
            "current_file_not_lint_green",
            f"{rel_path} must be a lint-green followups.v2 carrier before the sole writer can apply a row ({codes})",
        )
    existing_by_tuple: dict[tuple[str, str], followups_lint.FollowupItem] = {}
    for item in parsed.items:
        source_ref = followups_lint.normalize_source_ref(item.source_ref)
        if source_ref is not None and item.item_id is not None:
            tuple_value = (source_ref, item.item_id)
            if tuple_value in existing_by_tuple:
                raise ApplyError("current_tuple_duplicate", f"current V2 carrier repeats tuple: {tuple_value!r}")
            existing_by_tuple[tuple_value] = item
    extra_lines: list[str] = []
    replacements: dict[int, str] = {}
    for row in rows:
        current = existing_by_tuple.get(row.tuple)
        if current is not None:
            current_digest = followups_lint.v2_row_digest(current)
            if current_digest != row.digest:
                if generic and row.expected_current_digest is None:
                    raise ApplyError(
                        "generic_unexpected_existing_tuple",
                        f"generic batch expected a new tuple but found one in the carrier: {row.tuple!r}",
                    )
                if row.expected_current_digest != current_digest:
                    raise ApplyError(
                        "generic_current_tuple_drift" if generic else "current_tuple_payload_drift",
                        (
                            f"generic existing V2 tuple differs from its frozen CAS digest: {row.tuple!r}"
                            if generic
                            else f"existing V2 tuple payload differs from frozen CAS digest: {row.tuple!r}"
                        ),
                    )
                replacements[current.line_no] = followups_lint.render_v2_row(row.payload)
            continue
        if row.expected_current_digest is not None:
            raise ApplyError(
                "generic_current_tuple_missing" if generic else "current_tuple_missing",
                (
                    f"generic frozen CAS transition expected an existing V2 tuple: {row.tuple!r}"
                    if generic
                    else f"frozen CAS transition expected an existing V2 tuple: {row.tuple!r}"
                ),
            )
        extra_lines.append(followups_lint.render_v2_row(row.payload))
    if replacements:
        lines = text.splitlines()
        for line_no, replacement in replacements.items():
            lines[line_no - 1] = replacement
        text = "\n".join(lines) + "\n"
    if not extra_lines:
        candidate_text = text
    else:
        if not text.endswith("\n"):
            text += "\n"
        if not text.endswith("\n\n"):
            text += "\n"
        candidate_text = text + "\n".join(extra_lines) + "\n"
    candidate = followups_lint.parse_followup_text(candidate_text, rel_path, root / rel_path)
    candidate_findings = followups_lint.lint_followup_files([candidate], root)
    if candidate_findings:
        codes = ", ".join(sorted({finding.code for finding in candidate_findings}))
        raise ApplyError(
            "rendered_row_not_lint_green",
            f"frozen row would leave {rel_path} outside the V2 lint-green contract ({codes})",
        )
    return candidate_text.encode("utf-8")


def _acquire_lock(root: Path) -> int:
    path = root / LOCK_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ApplyError("serial_writer_busy", "another followups V2 apply operation holds the serial writer lock") from exc


def _raw_followups_source_bytes(all_bytes: Mapping[str, bytes]) -> dict[str, bytes]:
    """Return the sorted authoritative source map, never including generated files."""

    return {
        path: all_bytes[path]
        for path in sorted(all_bytes)
        if Path(path).name not in followups_lint.FOLLOWUPS_IGNORE
    }


def _index_lifecycle_enabled(frozen: Mapping[str, object]) -> bool:
    baseline = frozen.get("baseline_followups_snapshot")
    return isinstance(baseline, Mapping) and followups_capture.FOLLOWUPS_INDEX_PATH in baseline


def _render_terminal_index_candidate(
    root: Path,
    all_bytes: Mapping[str, bytes],
) -> followups_index_rebuild.BoundIndexRender:
    index_path = followups_capture.FOLLOWUPS_INDEX_PATH
    index_before = all_bytes.get(index_path)
    if not isinstance(index_before, bytes):
        raise ApplyError("followups_index_before_missing", "terminal index lifecycle requires a bound regular index before-image")
    source_bytes = _raw_followups_source_bytes(all_bytes)
    try:
        manifest = followups_index_rebuild.authoritative_followups_manifest(source_bytes)
        lifecycle = followups_index_rebuild.promoted_plan_lifecycle_manifest(
            root,
            source_bytes,
            manifest,
        )
        return followups_index_rebuild.render_bound_index(
            root,
            source_bytes,
            manifest,
            index_before,
            promoted_plan_lifecycle=lifecycle,
            stamp=followups_index_rebuild.generated_summary_stamp(index_before),
        )
    except followups_index_rebuild.BoundIndexInputError as exc:
        raise ApplyError("followups_index_bound_input_invalid", str(exc)) from exc


def _assert_terminal_index_lifecycle_current(
    root: Path,
    candidate_bytes: Mapping[str, bytes],
    expected_render: followups_index_rebuild.BoundIndexRender,
) -> None:
    """Fail closed when a promoted lifecycle input drifts during publication.

    The existing serial lock coordinates terminal apply writers, but promoted
    target plans are external lifecycle inputs.  Rebinding after every
    replacement and after receipt publication makes the final successful
    point linearizable; a changed target instead enters the existing rollback
    boundary and cannot leave a current receipt behind.
    """

    observed_render = _render_terminal_index_candidate(root, candidate_bytes)
    if (
        observed_render.authoritative_followups_manifest_sha256
        != expected_render.authoritative_followups_manifest_sha256
    ):
        raise ApplyError(
            "followups_index_lifecycle_drift",
            "promoted-plan lifecycle changed during terminal index publication",
        )


def _index_refresh_receipt(
    *,
    binding: Mapping[str, object],
    rendered: followups_index_rebuild.BoundIndexRender,
    before_bytes: Mapping[str, bytes],
    candidate_bytes: Mapping[str, bytes],
) -> dict[str, object]:
    index_path = followups_capture.FOLLOWUPS_INDEX_PATH
    before_index = before_bytes.get(index_path)
    after_index = candidate_bytes.get(index_path)
    if not isinstance(before_index, bytes) or not isinstance(after_index, bytes):
        raise ApplyError("followups_index_before_missing", "index refresh receipt requires before and after index bytes")
    changed_paths = [
        path
        for path in sorted(candidate_bytes)
        if candidate_bytes[path] != before_bytes.get(path, b"")
    ]
    state = "updated" if changed_paths else "clean_noop"
    return {
        "authoritative_followups_manifest_sha256": rendered.authoritative_followups_manifest_sha256,
        "capture_cycle_id": binding["capture_cycle_id"],
        "changed_paths": changed_paths,
        "index_after_sha256": _sha256(after_index),
        "index_before_sha256": _sha256(before_index),
        "owner_id": followups_capture.FOLLOWUPS_INDEX_REFRESH_OWNER_ID,
        "rendered_summary_sha256": rendered.rendered_summary_sha256,
        "state": state,
    }


def _safe_current_bytes(path: Path) -> bytes | None:
    """Read one rollback candidate without following a foreign replacement."""

    try:
        st = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ApplyError("followups_rollback_path_unreadable", f"cannot stat rollback path {path}: {exc}") from exc
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        return None
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ApplyError("followups_rollback_path_unreadable", f"cannot read rollback path {path}: {exc}") from exc
    try:
        after = path.lstat()
    except OSError as exc:
        raise ApplyError("followups_rollback_path_unreadable", f"cannot re-stat rollback path {path}: {exc}") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or after.st_size != len(data)
        or after.st_dev != st.st_dev
        or after.st_ino != st.st_ino
    ):
        return None
    return data


def _restore_terminal_before_image(path: Path, *, original: bytes | None, expected_after: bytes) -> bool:
    """Restore only if the file still contains this transaction's own after-image."""

    current = _safe_current_bytes(path)
    if current != expected_after:
        return False
    if original is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True
    _atomic_write(path, original)
    return True


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _snapshot_changed_paths(before: Mapping[str, object], after: Mapping[str, object]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _terminal_index_result_payload(
    *,
    frozen: Mapping[str, object],
    rows: list[FrozenRow],
    observed_bytes: Mapping[str, bytes],
    candidate_bytes: Mapping[str, bytes],
    refresh_receipt: Mapping[str, object] | None,
    is_idempotent: bool,
    state: str,
) -> dict[str, object]:
    result_rows = [
        {
            "proof_host": f"{row.followup_path}#{row.payload['item_id']}",
            "followup_path": row.followup_path,
            "source_ref": row.payload["source_ref"],
            "item_id": row.payload["item_id"],
            "tuple_owner": row.owner,
            "declared_row_digest": row.digest,
            "applied_row_digest": row.digest,
            "file_before_sha256": _sha256(observed_bytes[row.followup_path]) if row.followup_path in observed_bytes else None,
            "file_after_sha256": _sha256(candidate_bytes[row.followup_path]),
            "source_terminal_commit_oid": frozen["source_terminal_commit_oid"],
            "source_plan_blob_oid": frozen["source_plan_blob_oid"],
        }
        for row in rows
    ]
    payload: dict[str, object] = {
        "schema_version": "followups_apply_result.v2",
        "state": "idempotent" if is_idempotent else state,
        "expected_owned_tuples": frozen["expected_owned_tuples"],
        "expected_zero_reason": frozen.get("expected_zero_reason"),
        "rows": result_rows,
        "changed_paths": [
            path for path in sorted(candidate_bytes) if candidate_bytes[path] != observed_bytes.get(path, b"")
        ],
    }
    if refresh_receipt is not None:
        payload["followups_index_refresh_receipt"] = dict(refresh_receipt)
    return payload


def _expected_existing_index_receipt(
    *,
    frozen: Mapping[str, object],
    binding: Mapping[str, object],
    current_snapshot: Mapping[str, object],
    current_bytes: Mapping[str, bytes],
    rendered: followups_index_rebuild.BoundIndexRender,
) -> dict[str, object]:
    baseline = frozen["baseline_followups_snapshot"]
    assert isinstance(baseline, Mapping)
    index_path = followups_capture.FOLLOWUPS_INDEX_PATH
    baseline_index = baseline.get(index_path)
    current_index = current_bytes.get(index_path)
    if (
        not isinstance(baseline_index, Mapping)
        or not isinstance(baseline_index.get("sha256"), str)
        or not isinstance(current_index, bytes)
    ):
        raise ApplyError("followups_index_binding_invalid", "index lifecycle binding lacks exact before/after objects")
    changed_paths = _snapshot_changed_paths(baseline, current_snapshot)
    return {
        "authoritative_followups_manifest_sha256": rendered.authoritative_followups_manifest_sha256,
        "capture_cycle_id": binding["capture_cycle_id"],
        "changed_paths": changed_paths,
        "index_after_sha256": _sha256(current_index),
        "index_before_sha256": baseline_index["sha256"],
        "owner_id": followups_capture.FOLLOWUPS_INDEX_REFRESH_OWNER_ID,
        "rendered_summary_sha256": rendered.rendered_summary_sha256,
        "state": "updated" if changed_paths else "clean_noop",
    }


def _apply_terminal_index_refresh_rows(
    root: Path,
    frozen: dict[str, object],
    rows: list[FrozenRow],
    *,
    mutate: bool,
) -> dict[str, object]:
    """Apply the index-bearing terminal branch under the existing serial lock."""

    baseline = frozen["baseline_followups_snapshot"]
    assert isinstance(baseline, dict)
    current_snapshot, current_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
    rendered, raw_idempotent = _render_global_v2_candidates(current_snapshot, current_bytes, rows, root)
    candidate_bytes = dict(current_bytes)
    candidate_bytes.update(rendered)
    index_render = _render_terminal_index_candidate(root, candidate_bytes)
    candidate_bytes[followups_capture.FOLLOWUPS_INDEX_PATH] = index_render.index_bytes
    candidate_idempotent = (raw_idempotent or not rows) and all(
        candidate_bytes[path] == current_bytes.get(path, b"") for path in candidate_bytes
    )
    if not mutate:
        return _terminal_index_result_payload(
            frozen=frozen,
            rows=rows,
            observed_bytes=current_bytes,
            candidate_bytes=candidate_bytes,
            refresh_receipt=None,
            is_idempotent=candidate_idempotent,
            state="preflight",
        )

    lock_fd = _acquire_lock(root)
    lock_path = root / LOCK_REL_PATH
    replaced: list[str] = []
    before_images: dict[str, bytes | None] = {}
    refresh_receipt: dict[str, object] | None = None
    receipt_publish_attempted = False
    try:
        try:
            binding = followups_capture.find_followups_index_refresh_binding(root, frozen)
        except followups_capture.CaptureError as exc:
            raise ApplyError(exc.reason_code, str(exc)) from exc
        now_snapshot, now_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
        locked_rendered, locked_raw_idempotent = _render_global_v2_candidates(now_snapshot, now_bytes, rows, root)
        locked_candidate = dict(now_bytes)
        locked_candidate.update(locked_rendered)
        locked_index_render = _render_terminal_index_candidate(root, locked_candidate)
        locked_candidate[followups_capture.FOLLOWUPS_INDEX_PATH] = locked_index_render.index_bytes
        _assert_terminal_index_lifecycle_current(root, locked_candidate, locked_index_render)
        locked_idempotent = (locked_raw_idempotent or not rows) and all(
            locked_candidate[path] == now_bytes.get(path, b"") for path in locked_candidate
        )
        try:
            existing_receipt, _existing_object = followups_capture.read_followups_index_refresh_receipt(
                root,
                plan_ref=str(frozen["plan_ref"]),
                capture_cycle_id=str(binding["capture_cycle_id"]),
            )
        except followups_capture.CaptureError as exc:
            if exc.reason_code != "followups_index_refresh_receipt_missing":
                raise ApplyError(exc.reason_code, str(exc)) from exc
            existing_receipt = None

        if existing_receipt is not None:
            if not locked_idempotent:
                raise ApplyError(
                    "followups_index_postwrite_drift",
                    "existing index refresh receipt does not match the current raw/index candidate",
                )
            expected_receipt = _expected_existing_index_receipt(
                frozen=frozen,
                binding=binding,
                current_snapshot=now_snapshot,
                current_bytes=now_bytes,
                rendered=locked_index_render,
            )
            if existing_receipt != expected_receipt:
                raise ApplyError(
                    "followups_index_refresh_receipt_drift",
                    "existing index refresh receipt differs from the current canonical proof",
                )
            return _terminal_index_result_payload(
                frozen=frozen,
                rows=rows,
                observed_bytes=now_bytes,
                candidate_bytes=locked_candidate,
                refresh_receipt=existing_receipt,
                is_idempotent=True,
                state="applied",
            )

        if now_snapshot != baseline:
            raise ApplyError(
                "followups_index_prewrite_drift",
                "raw follow-ups or generated index changed before the first terminal index refresh",
            )
        refresh_receipt = _index_refresh_receipt(
            binding=binding,
            rendered=locked_index_render,
            before_bytes=now_bytes,
            candidate_bytes=locked_candidate,
        )
        before_images = {path: now_bytes.get(path) for path in locked_candidate}
        changed_paths = list(refresh_receipt["changed_paths"])
        for rel_path in changed_paths:
            target = root / rel_path
            if _safe_current_bytes(target) != before_images[rel_path]:
                raise ApplyError("followups_index_prewrite_drift", f"candidate before-image drifted: {rel_path}")
            _atomic_write(target, locked_candidate[rel_path])
            replaced.append(rel_path)
            _assert_terminal_index_lifecycle_current(root, locked_candidate, locked_index_render)
        try:
            receipt_publish_attempted = True
            published_receipt, _receipt_object, _created = followups_capture.publish_followups_index_refresh_receipt(
                root,
                plan_ref=str(frozen["plan_ref"]),
                capture_cycle_id=str(binding["capture_cycle_id"]),
                receipt=refresh_receipt,
            )
        except followups_capture.CaptureError as exc:
            raise ApplyError(exc.reason_code, str(exc)) from exc
        _assert_terminal_index_lifecycle_current(root, locked_candidate, locked_index_render)
        return _terminal_index_result_payload(
            frozen=frozen,
            rows=rows,
            observed_bytes=now_bytes,
            candidate_bytes=locked_candidate,
            refresh_receipt=published_receipt,
            is_idempotent=not changed_paths,
            state="applied",
        )
    except Exception as exc:
        rollback_conflicts: list[str] = []
        receipt_rollback_conflict = False
        if refresh_receipt is not None and receipt_publish_attempted:
            # ``publish_*`` uses an exclusive leaf, but a failure can occur
            # after that leaf became visible (for example while syncing it).
            # Remove only our exact payload before restoring the raw/index
            # images; a foreign or malformed replacement is a fail-closed
            # rollback conflict rather than something this writer may erase.
            try:
                removed_receipt = followups_capture.remove_followups_index_refresh_receipt_if_exact(
                    root,
                    plan_ref=str(frozen["plan_ref"]),
                    capture_cycle_id=str(refresh_receipt["capture_cycle_id"]),
                    receipt=refresh_receipt,
                )
            except followups_capture.CaptureError:
                receipt_rollback_conflict = True
            else:
                if not removed_receipt:
                    try:
                        followups_capture.read_followups_index_refresh_receipt(
                            root,
                            plan_ref=str(frozen["plan_ref"]),
                            capture_cycle_id=str(refresh_receipt["capture_cycle_id"]),
                        )
                    except followups_capture.CaptureError as receipt_error:
                        if receipt_error.reason_code != "followups_index_refresh_receipt_missing":
                            receipt_rollback_conflict = True
                    else:
                        receipt_rollback_conflict = True
        for rel_path in reversed(replaced):
            try:
                restored = _restore_terminal_before_image(
                    root / rel_path,
                    original=before_images[rel_path],
                    expected_after=locked_candidate[rel_path],
                )
            except ApplyError:
                restored = False
            if not restored:
                rollback_conflicts.append(rel_path)
        if rollback_conflicts:
            raise ApplyError(
                "followups_index_rollback_cas_lost",
                "rollback refused to overwrite a foreign candidate replacement: " + ", ".join(sorted(rollback_conflicts)),
            ) from exc
        if receipt_rollback_conflict:
            raise ApplyError(
                "followups_index_receipt_rollback_cas_lost",
                "rollback refused to remove a foreign or malformed index refresh receipt",
            ) from exc
        raise
    finally:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _apply_terminal_frozen_rows(project_root: Path, manifest: Mapping[str, object], *, mutate: bool) -> dict[str, object]:
    """CAS-validate and, when requested, apply all frozen V2 row payloads.

    The function validates every file and row before writing any file.  A write
    error restores already replaced files from in-memory before-images.
    """

    root = project_root.resolve()
    frozen, rows = load_frozen_manifest(manifest)
    plan_ref = str(frozen["plan_ref"])
    if any(row.tuple[0] != plan_ref and not row.tuple[0].startswith(plan_ref + "#") for row in rows):
        raise ApplyError(
            "frozen_manifest_source_ref_mismatch",
            "frozen rows must be source-bound to the exact terminal plan path or one of its anchors",
        )
    try:
        followups_capture._v2_source_identity(
            root,
            plan_ref,
            str(frozen["source_terminal_commit_oid"]),
            str(frozen["source_plan_blob_oid"]),
        )
    except followups_capture.CaptureError as exc:
        raise ApplyError(exc.reason_code, str(exc)) from exc
    if _index_lifecycle_enabled(frozen):
        return _apply_terminal_index_refresh_rows(root, frozen, rows, mutate=mutate)
    baseline = frozen["baseline_followups_snapshot"]
    assert isinstance(baseline, dict)
    current_snapshot, current_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
    rendered, idempotent = _render_global_v2_candidates(current_snapshot, current_bytes, rows, root)
    baseline_matches = _snapshot_equals(baseline, current_snapshot)
    if not idempotent and not baseline_matches:
        raise ApplyError("baseline_snapshot_drift", "followups object map changed after Manager froze the declaration union")

    def result_payload(
        observed_bytes: Mapping[str, bytes],
        candidate_bytes: Mapping[str, bytes],
        *,
        is_idempotent: bool,
        state: str,
    ) -> dict[str, object]:
        result_rows = [
            {
                "proof_host": f"{row.followup_path}#{row.payload['item_id']}",
                "followup_path": row.followup_path,
                "source_ref": row.payload["source_ref"],
                "item_id": row.payload["item_id"],
                "tuple_owner": row.owner,
                "declared_row_digest": row.digest,
                "applied_row_digest": row.digest,
                "file_before_sha256": _sha256(observed_bytes[row.followup_path]) if row.followup_path in observed_bytes else None,
                "file_after_sha256": _sha256(candidate_bytes[row.followup_path]),
                "source_terminal_commit_oid": frozen["source_terminal_commit_oid"],
                "source_plan_blob_oid": frozen["source_plan_blob_oid"],
            }
            for row in rows
        ]
        return {
            "schema_version": "followups_apply_result.v2",
            "state": "idempotent" if is_idempotent else state,
            "expected_owned_tuples": frozen["expected_owned_tuples"],
            "expected_zero_reason": frozen.get("expected_zero_reason"),
            "rows": result_rows,
            "changed_paths": [
                path for path in sorted(candidate_bytes) if candidate_bytes[path] != observed_bytes.get(path, b"")
            ],
        }

    if not mutate:
        return result_payload(current_bytes, rendered, is_idempotent=idempotent, state="preflight")

    lock_fd = _acquire_lock(root)
    lock_path = root / LOCK_REL_PATH
    replaced: list[str] = []
    try:
        # Re-read all current carriers under the same lock, then construct and
        # lint the complete resulting V2 set before the first replacement.
        now_snapshot, now_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
        locked_rendered, locked_idempotent = _render_global_v2_candidates(now_snapshot, now_bytes, rows, root)
        locked_baseline_matches = _snapshot_equals(baseline, now_snapshot)
        if not locked_idempotent and not locked_baseline_matches:
            raise ApplyError("baseline_snapshot_drift", "followups object map changed before serial writer acquired its lock")
        if locked_idempotent:
            return result_payload(now_bytes, locked_rendered, is_idempotent=True, state="applied")
        before_images = {rel_path: now_bytes.get(rel_path) for rel_path in locked_rendered}
        for rel_path in sorted(locked_rendered):
            if locked_rendered[rel_path] == before_images.get(rel_path, b""):
                continue
            _atomic_write(root / rel_path, locked_rendered[rel_path])
            replaced.append(rel_path)
    except Exception:
        for rel_path in reversed(replaced):
            original = before_images[rel_path]
            target = root / rel_path
            if original is None:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            else:
                _atomic_write(target, original)
        raise
    finally:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
    return result_payload(now_bytes, locked_rendered, is_idempotent=False, state="applied")


def _verify_generic_source_objects(root: Path, source_objects: list[GenericSourceObject]) -> None:
    for source in source_objects:
        try:
            _object, data = followups_capture.read_repo_regular_path(root, source.source_path)
        except followups_capture.CaptureError as exc:
            raise ApplyError("generic_source_object_unreadable", str(exc)) from exc
        if _sha256(data) != source.source_sha256:
            raise ApplyError(
                "generic_source_hash_drift",
                f"generic source object changed after discovery: {source.source_path}",
            )
        try:
            line_count = len(data.decode("utf-8").splitlines())
        except UnicodeDecodeError as exc:
            raise ApplyError("generic_source_not_utf8", f"generic source object is not UTF-8: {source.source_path}") from exc
        for anchor in source.anchors:
            if int(anchor[1:]) > line_count:
                raise ApplyError(
                    "generic_source_anchor_drift",
                    f"generic source anchor no longer exists: {source.source_path}#{anchor}",
                )


def _apply_generic_batch(project_root: Path, manifest: Mapping[str, object], *, mutate: bool) -> dict[str, object]:
    """Validate and serially apply one producer-frozen generic batch."""

    root = project_root.resolve()
    frozen, rows, source_objects = load_generic_batch(manifest)
    _verify_generic_source_objects(root, source_objects)
    current_snapshot, current_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
    target_followup_path = str(frozen["target_followup_path"])
    rendered, idempotent = _render_global_v2_candidates(
        current_snapshot,
        current_bytes,
        rows,
        root,
        generic=True,
        new_file_texts={target_followup_path: str(frozen["target_header"])},
    )
    baseline = frozen["baseline_followups_snapshot"]
    assert isinstance(baseline, dict)
    baseline_matches = _snapshot_equals(baseline, current_snapshot)
    if not idempotent and not baseline_matches:
        raise ApplyError(
            "generic_baseline_snapshot_drift",
            "followups object map changed after the generic producer discovery pass",
        )
    def result_payload(
        observed_bytes: Mapping[str, bytes],
        candidate_bytes: Mapping[str, bytes],
        *,
        is_idempotent: bool,
        state: str,
    ) -> dict[str, object]:
        result_rows = [
            {
                "proof_host": f"{row.followup_path}#{row.payload['item_id']}",
                "followup_path": row.followup_path,
                "source_ref": row.payload["source_ref"],
                "item_id": row.payload["item_id"],
                "tuple_owner": row.owner,
                "declared_row_digest": row.digest,
                "applied_row_digest": row.digest,
                "expected_current_row_digest": row.expected_current_digest,
                "file_before_sha256": _sha256(observed_bytes[row.followup_path]) if row.followup_path in observed_bytes else None,
                "file_after_sha256": _sha256(candidate_bytes[row.followup_path]),
            }
            for row in rows
        ]
        return {
            "schema_version": "followups_apply_result.v2",
            "state": "idempotent" if is_idempotent else state,
            "source_kind": GENERIC_SOURCE_KIND,
            "producer_id": frozen["producer_id"],
            "target_followup_path": target_followup_path,
            "source_objects": [
                {"source_path": source.source_path, "source_sha256": source.source_sha256, "anchors": list(source.anchors)}
                for source in source_objects
            ],
            "expected_owned_tuples": frozen["expected_owned_tuples"],
            "expected_zero_reason": frozen.get("expected_zero_reason"),
            "rows": result_rows,
            "changed_paths": [
                path for path in sorted(candidate_bytes) if candidate_bytes[path] != observed_bytes.get(path, b"")
            ],
        }

    if not mutate:
        return result_payload(current_bytes, rendered, is_idempotent=idempotent, state="preflight")

    lock_fd = _acquire_lock(root)
    lock_path = root / LOCK_REL_PATH
    replaced: list[str] = []
    try:
        now_snapshot, now_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
        locked_rendered, locked_idempotent = _render_global_v2_candidates(
            now_snapshot,
            now_bytes,
            rows,
            root,
            generic=True,
            new_file_texts={target_followup_path: str(frozen["target_header"])},
        )
        locked_baseline_matches = _snapshot_equals(baseline, now_snapshot)
        if not locked_idempotent and not locked_baseline_matches:
            raise ApplyError(
                "generic_baseline_snapshot_drift",
                "followups object map changed before the sole serial writer acquired its lock",
            )
        _verify_generic_source_objects(root, source_objects)
        if locked_idempotent:
            return result_payload(now_bytes, locked_rendered, is_idempotent=True, state="applied")
        before_images = {rel_path: now_bytes.get(rel_path) for rel_path in locked_rendered}
        for rel_path in sorted(locked_rendered):
            if locked_rendered[rel_path] == before_images.get(rel_path, b""):
                continue
            _atomic_write(root / rel_path, locked_rendered[rel_path])
            replaced.append(rel_path)
    except Exception:
        for rel_path in reversed(replaced):
            original = before_images[rel_path]
            target = root / rel_path
            if original is None:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            else:
                _atomic_write(target, original)
        raise
    finally:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
    return result_payload(now_bytes, locked_rendered, is_idempotent=False, state="applied")


def apply_frozen_rows(project_root: Path, manifest: Mapping[str, object], *, mutate: bool) -> dict[str, object]:
    """Apply exactly one typed terminal or generic frozen ingress request."""

    schema_version = manifest.get("schema_version")
    if schema_version == FROZEN_SCHEMA:
        return _apply_terminal_frozen_rows(project_root, manifest, mutate=mutate)
    if schema_version == GENERIC_BATCH_SCHEMA:
        return _apply_generic_batch(project_root, manifest, mutate=mutate)
    raise ApplyError(
        "frozen_manifest_schema_invalid",
        f"schema_version must be {FROZEN_SCHEMA!r} or {GENERIC_BATCH_SCHEMA!r}",
    )


def _read_manifest(path: str) -> dict[str, object]:
    raw = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplyError("frozen_manifest_json_invalid", f"cannot decode frozen manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise ApplyError("frozen_manifest_json_invalid", "frozen manifest root must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply only typed frozen V2 follow-up rows with serial CAS validation.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--frozen-manifest", required=True, help="JSON manifest path or '-' for stdin")
    parser.add_argument("--apply", action="store_true", help="Write after a successful full preflight; otherwise print read-only preflight")
    args = parser.parse_args(argv)
    try:
        payload = apply_frozen_rows(Path(args.project_root), _read_manifest(args.frozen_manifest), mutate=args.apply)
    except ApplyError as exc:
        print(json.dumps({"schema_version": "followups_apply_result.v2", "state": "blocked", "reason_code": exc.reason_code, "message": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

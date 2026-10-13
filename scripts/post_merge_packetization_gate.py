#!/usr/bin/env python3
"""Post-merge rollout-packet coverage gate for shared canon changes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rollout_packet import (
    CURRENT_CONSUMER_REPO,
    _current_delivery_stable_identity,
    _load_source_corpus,
    _normalize_current_delivery_path_list,
    _normalize_repo_id,
    _packet_ack_reason,
    _packet_header_status,
    _packet_meta_status,
    _packet_summary,
    _packet_target_repo,
    _packet_target_adoption_state,
    _render_current_delivery_restamp,
    _resolve_current_delivery_packet_path,
    _validate_current_delivery_packet,
    _validate_current_delivery_restamp_input,
    _current_delivery_section_paths,
    parse_packet_text,
)
from process_improvements_collect import BacklogEntry, parse_backlog_text, triage_carrier_issues
from shared_docs_mirror_drift import (
    GENERIC_MIRROR_POLICY,
    MirrorPolicy,
    MirrorPolicyError,
    declared_mirror_target_applicability,
    load_shared_docs_mirror_policy,
)


PACKET_DIR = Path("docs") / "rollout_packets"
REPORT_DIR = Path("docs") / "reviews"
PACKETIZATION_GATE_SCHEMA_VERSION = "packetization_gate.v1"
PACKETIZATION_GATE_STEP = "step:packetization_gate"
PACKETIZATION_GATE_RECEIPT_KIND = "packetization_gate"
PACKETIZATION_GATE_RECEIPT_NAME = "packetization_gate"
# Kept as a compatibility vocabulary for existing receipt readers.  New
# applicability failures use the row-level ``blocking`` bit; consumers must not
# infer a green result from this historical, incomplete list.
BLOCKING_COVERAGES = {"missing-packet", "unknown_target_mapping", "legacy-create-drafts-refused"}
COVERING_PACKET_STATUSES = {"open", "imported"}
MATCHABLE_PACKET_STATUSES = {"open", "imported", "superseded"}
REPORT_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.+?)\s*$", re.MULTILINE)
RECOVERY_COMMAND = (
    'planveyor_post_merge_packetization_gate_recover --range "$(planveyor_range_base)..$(planveyor_range_head)" '
    "[--source-plan docs/plans/<provenance-plan>.md] --packet docs/rollout_packets/<packet>.md"
)
LEGACY_CREATE_DRAFTS_RECIPE = (
    "planveyor_rollout_packet_create <target_repo> <topic_slug> "
    "[--source-plan <provenance-plan>] --target-kind <target-kind>; "
    "complete source artifacts and target writable carriers; "
    "planveyor_post_merge_packetization_gate_recover --range <BASE>..<HEAD> "
    "[--source-plan <provenance-plan>] --packet docs/rollout_packets/<packet>.md"
)
REPORT_FILENAME_MARKER = "_packetization_gate_range_"
TARGET_LOCAL_SCOPE = "target-local"
SOURCE_ONLY_ROOTS = {
    "docs/tools/owner_runbook_codex.md": "owner runbook is planveyor operator guidance",
    # The Russian copy is the same operator guidance and keeps the original's
    # classification; it is listed by exact path, not by a `.ru.md` rule.
    "docs/tools/owner_runbook_codex.ru.md": "owner runbook is planveyor operator guidance",
}
SHARED_PREFIXES = (
    "docs/roles/",
    "docs/tools/prompts/",
    "docs/playbooks/",
    "docs/adr/",
    "docs/process_improvements/",
    "docs/guides/",
)
PI_BACKLOG_SUFFIX = "__process_improvements_backlog.md"

# This is deliberately a checked-in, narrow table rather than a broad prefix
# default.  It is empty until an owner can name a target repo, kind and exact
# target-side carrier set.  Tests may inject a fixture entry, but production
# code never falls back to an inferred sibling obligation.
EXPLICIT_TARGET_APPLICABILITY: dict[str, tuple[tuple[str, str, tuple[str, ...], str], ...]] = {}

# ``execution_kind`` is the existing PI authority for the packet action kind.
# It is intentionally finite: a new kind must update this table rather than
# silently becoming a guessed rollout packet.
PI_EXECUTION_KIND_TO_TARGET_KIND = {
    "plan": "plan_adoption",
    "helper": "checker_rollout",
    "canon_doc": "consumer_only",
    "rollout_packet": "plan_adoption",
}


@dataclass(frozen=True)
class Classification:
    targets: tuple[str, ...]
    source_only_reason: str | None = None
    unknown_target_mapping: bool = False
    ignored_reason: str | None = None


@dataclass(frozen=True)
class TargetApplicability:
    """One exact target delivery obligation within a range."""

    target_repo: str
    target_kind: str
    target_source_artifacts: tuple[str, ...]
    target_writable_carriers: tuple[str, ...]
    record_authorities: tuple[str, ...]

    @property
    def authority(self) -> str:
        """Stable summary; rows retain each individual record authority."""

        return "; ".join(self.record_authorities)

    @property
    def key(self) -> tuple[str, str]:
        """A delivery partition is defined only by its target repo and kind."""

        return (self.target_repo, self.target_kind)

    def to_json(self) -> dict[str, object]:
        return {
            "target_repo": self.target_repo,
            "target_kind": self.target_kind,
            "target_source_artifacts": list(self.target_source_artifacts),
            "target_writable_carriers": list(self.target_writable_carriers),
            "authority": self.authority,
        }


@dataclass(frozen=True)
class ApplicabilityRecord:
    changed_file: str
    target_repo: str | None = None
    target_kind: str | None = None
    target_writable_carriers: tuple[str, ...] = ()
    authority: str = ""
    source_only_reason: str | None = None
    blocking_reason: str | None = None
    ignored_reason: str | None = None


@dataclass(frozen=True)
class TargetApplicabilityResult:
    """Public normalized, side-effect-free result consumed by all gate readers."""

    changed_files: tuple[str, ...]
    report_context_paths: tuple[str, ...]
    records: tuple[ApplicabilityRecord, ...]
    partitions: tuple[TargetApplicability, ...]

    @property
    def packetization_report_required(self) -> bool:
        return bool(self.report_context_paths)

    @property
    def target_packet_required(self) -> bool:
        return bool(self.partitions)

    @property
    def blocking_records(self) -> tuple[ApplicabilityRecord, ...]:
        return tuple(record for record in self.records if record.blocking_reason)

    def partition_for(
        self,
        *,
        target_repo: str,
        target_kind: str,
    ) -> TargetApplicability | None:
        normalized_repo = normalize_repo_id(target_repo)
        matches = [
            partition
            for partition in self.partitions
            if normalize_repo_id(partition.target_repo) == normalized_repo
            and partition.target_kind == target_kind
        ]
        return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True)
class RecoveryLineage:
    base: str
    head: str
    range_ref: str
    source_plan: str | None
    changed_files: tuple[str, ...]
    source_artifacts: tuple[str, ...]
    applicability: TargetApplicabilityResult


def normalize_repo_id(value: str) -> str:
    repo_id = value.strip().lower().replace("_", "-")
    repo_id = re.sub(r"-+", "-", repo_id).strip("-")
    return repo_id


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_changed_path(value: str) -> str | None:
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    parts = raw.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)


def _source_only_record(path: str, reason: str, *, authority: str) -> ApplicabilityRecord:
    return ApplicabilityRecord(
        changed_file=path,
        target_repo=CURRENT_CONSUMER_REPO,
        target_kind="source_only",
        authority=authority,
        source_only_reason=reason,
    )


def _blocking_record(path: str, reason: str, *, authority: str) -> ApplicabilityRecord:
    return ApplicabilityRecord(
        changed_file=path,
        target_repo="unknown",
        target_kind="unknown",
        authority=authority,
        blocking_reason=reason,
    )


def _target_record(
    path: str,
    *,
    target_repo: str,
    target_kind: str,
    target_writable_carriers: tuple[str, ...] | list[str],
    authority: str,
) -> ApplicabilityRecord:
    raw_carriers = tuple(str(item) for item in target_writable_carriers)
    if not raw_carriers:
        return _blocking_record(path, "target applicability has no writable carriers", authority=authority)
    if (
        raw_carriers != tuple(sorted(set(raw_carriers)))
        or any(_normalize_changed_path(item) != item for item in raw_carriers)
    ):
        return _blocking_record(
            path,
            "target applicability writable carriers must be literal normalized sorted unique paths",
            authority=authority,
        )
    return ApplicabilityRecord(
        changed_file=path,
        target_repo=normalize_repo_id(target_repo),
        target_kind=target_kind,
        target_writable_carriers=raw_carriers,
        authority=authority,
    )


def _is_process_improvement_backlog(path: str) -> bool:
    return (
        path.startswith("docs/process_improvements/")
        and path.endswith(PI_BACKLOG_SUFFIX)
        and Path(path).name != "_template_process_improvements_backlog.md"
    )


def _build_target_applicability_result(
    changed_files: list[str] | tuple[str, ...],
    *,
    pi_records_by_path: dict[str, tuple[ApplicabilityRecord, ...]] | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> TargetApplicabilityResult:
    """Build one normalized result from checked-in applicability inputs only.

    The function is intentionally pure: callers provide the already-resolved PI
    range delta, and no live mirror checkout, report, packet, or target repo is
    consulted.  It is the one policy implementation used by the gate and its
    terminal consumers.
    """

    records: list[ApplicabilityRecord] = []
    report_context_paths: set[str] = set()
    pi_records_by_path = pi_records_by_path or {}
    normalized_changed_files: list[str] = []

    for raw_path in sorted(set(changed_files)):
        path = _normalize_changed_path(raw_path)
        if path is None:
            records.append(
                _blocking_record(
                    str(raw_path),
                    "changed path is not a normalized repo-relative pathname",
                    authority="packetization path normalization",
                )
            )
            report_context_paths.add(str(raw_path))
            continue
        normalized_changed_files.append(path)

        if _is_process_improvement_backlog(path):
            pi_records = pi_records_by_path.get(path)
            if pi_records is None:
                pi_records = (
                    _blocking_record(
                        path,
                        "process-improvement applicability requires an exact BASE-to-HEAD snapshot delta",
                        authority="process_improvements_collect parser",
                    ),
                )
            records.extend(pi_records)
            if pi_records:
                report_context_paths.add(path)
            continue

        mirror = declared_mirror_target_applicability(path, policy=mirror_policy)
        if mirror is not None:
            records.append(
                _target_record(
                    path,
                    target_repo=str(mirror["target_repo"]),
                    target_kind=str(mirror["target_kind"]),
                    target_writable_carriers=tuple(str(item) for item in mirror["target_writable_carriers"]),
                    authority=f"declared mirror policy; {mirror['authority']}",
                )
            )
            report_context_paths.add(path)
            continue

        if path in SOURCE_ONLY_ROOTS:
            records.append(
                _source_only_record(
                    path,
                    SOURCE_ONLY_ROOTS[path],
                    authority="checked-in source-only root policy",
                )
            )
            report_context_paths.add(path)
            continue

        if path.startswith("docs/tools/prompts/profiles/"):
            records.append(
                _blocking_record(
                    path,
                    "unknown target mapping: retired profile carrier has no public source or consumer mapping",
                    authority="public corpus boundary",
                )
            )
            report_context_paths.add(path)
            continue

        explicit_rules = EXPLICIT_TARGET_APPLICABILITY.get(path)
        if explicit_rules is not None:
            if not explicit_rules:
                records.append(
                    _blocking_record(
                        path,
                        "explicit target applicability is empty",
                        authority="checked-in explicit mapping table",
                    )
                )
            else:
                for target_repo, target_kind, carriers, authority in explicit_rules:
                    records.append(
                        _target_record(
                            path,
                            target_repo=target_repo,
                            target_kind=target_kind,
                            target_writable_carriers=carriers,
                            authority=authority,
                        )
                    )
            report_context_paths.add(path)
            continue

        if any(path.startswith(prefix) for prefix in SHARED_PREFIXES):
            records.append(
                _source_only_record(
                    path,
                    "tooling-owned canon has no explicit target mapping",
                    authority="checked-in source ownership policy",
                )
            )
            report_context_paths.add(path)
            continue

        # Unlisted paths are outside the packetization canon rather than a
        # guessed target obligation.
        records.append(ApplicabilityRecord(changed_file=path, ignored_reason="not a shared canon carrier"))

    records = sorted(
        set(records),
        key=lambda record: (
            record.changed_file,
            record.target_repo or "",
            record.target_kind or "",
            record.target_writable_carriers,
            record.authority,
            record.source_only_reason or "",
            record.blocking_reason or "",
            record.ignored_reason or "",
        ),
    )
    grouped: dict[tuple[str, str], dict[str, set[str]]] = {}
    for record in records:
        if not record.target_repo or not record.target_kind or record.source_only_reason or record.blocking_reason:
            continue
        key = (record.target_repo, record.target_kind)
        aggregate = grouped.setdefault(
            key,
            {"source_artifacts": set(), "writable_carriers": set(), "record_authorities": set()},
        )
        aggregate["source_artifacts"].add(record.changed_file)
        aggregate["writable_carriers"].update(record.target_writable_carriers)
        if record.authority:
            aggregate["record_authorities"].add(record.authority)
    partitions = tuple(
        TargetApplicability(
            target_repo=target_repo,
            target_kind=target_kind,
            target_source_artifacts=tuple(sorted(aggregate["source_artifacts"])),
            target_writable_carriers=tuple(sorted(aggregate["writable_carriers"])),
            record_authorities=tuple(sorted(aggregate["record_authorities"])),
        )
        for (target_repo, target_kind), aggregate in sorted(grouped.items())
    )
    return TargetApplicabilityResult(
        changed_files=tuple(sorted(set(normalized_changed_files))),
        report_context_paths=tuple(sorted(report_context_paths)),
        records=tuple(records),
        partitions=partitions,
    )


def classify_changed_file(
    path: str,
    *,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> Classification:
    """Compatibility projection of the one normalized applicability result.

    Older read-only callers only need the coarse target list.  Keeping this
    projection thin prevents them from preserving a second broad-prefix policy
    beside :func:`resolve_target_applicability`.
    """

    result = _build_target_applicability_result([path], mirror_policy=mirror_policy)
    records = tuple(record for record in result.records if not record.ignored_reason)
    if not records:
        return Classification((), ignored_reason="not a shared canon carrier")
    if any(record.blocking_reason for record in records):
        return Classification((), unknown_target_mapping=True)
    targets = tuple(sorted({record.target_repo for record in records if record.target_repo and not record.source_only_reason}))
    if targets:
        return Classification(targets)
    source_only = next((record.source_only_reason for record in records if record.source_only_reason), None)
    return Classification((CURRENT_CONSUMER_REPO,), source_only_reason=source_only or "source-only applicability")


def shared_packetization_paths(
    paths: list[str],
    *,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> list[str]:
    """Compatibility list derived from the normalized applicability projection."""

    out: list[str] = []
    for path in paths:
        classification = classify_changed_file(path, mirror_policy=mirror_policy)
        if classification.ignored_reason or classification.source_only_reason:
            continue
        if classification.unknown_target_mapping or classification.targets:
            out.append(path)
    return sorted(out)


def _git_snapshot_text(repo_root: Path, ref: str, path: str) -> str | None:
    """Read one exact Git snapshot; a missing path is an expected empty side."""

    rc, _, _ = run_git(repo_root, "cat-file", "-e", f"{ref}:{path}")
    if rc != 0:
        return None
    rc, stdout, stderr = run_git(repo_root, "show", f"{ref}:{path}")
    if rc != 0:
        detail = stderr.strip() or stdout.strip() or "git show failed"
        raise ValueError(f"could not read process-improvement snapshot {ref}:{path}: {detail}")
    return stdout


def _entry_target_signature(record: ApplicabilityRecord) -> tuple[str, str, tuple[str, ...]] | None:
    if record.target_repo and record.target_kind and not record.source_only_reason and not record.blocking_reason:
        return (record.target_repo, record.target_kind, record.target_writable_carriers)
    return None


_PI_TRANSITION_REFERENCE_FIELD_RE = re.compile(
    r"\bpacketization_(?:withdrawal|replacement)_(?:ref|authority)=",
    re.IGNORECASE,
)
_PI_TRANSITION_REFERENCE_RE = re.compile(
    r"\bpacketization_(?:withdrawal|replacement)_ref=(?P<packet_path>[^;\s]+)",
    re.IGNORECASE,
)


def _is_direct_rollout_packet_ref(value: str) -> bool:
    """Accept only a normalized literal source-side packet path."""

    if not value or value != value.strip() or "\\" in value:
        return False
    candidate = Path(value)
    return (
        not candidate.is_absolute()
        and candidate.as_posix() == value
        and candidate.parts == ("docs", "rollout_packets", candidate.name)
        and candidate.name != "_template.md"
        and candidate.suffix == ".md"
    )


def _single_pi_transition_reference(note: str) -> str | None:
    """Return one canonical withdrawal/replacement packet ref, or fail closed.

    The transition marker is an authority binding, not a free-form reason.  A
    duplicate, an unsupported ``*_authority`` spelling, an empty value or a
    non-packet path is ambiguous/malformed and must not authorize a target
    removal.
    """

    fields = list(_PI_TRANSITION_REFERENCE_FIELD_RE.finditer(note))
    references = list(_PI_TRANSITION_REFERENCE_RE.finditer(note))
    if len(fields) != 1 or len(references) != 1:
        return None
    packet_path = references[0].group("packet_path")
    return packet_path if _is_direct_rollout_packet_ref(packet_path) else None


def _base_transition_packet_paths(base_entry: BacklogEntry) -> tuple[str, ...]:
    """Return literal unique packet paths selected by one BASE PI row."""

    if base_entry.delivery_refs == "null":
        return ()
    packet_paths = tuple(base_entry.delivery_refs.split("; "))
    if not packet_paths or len(set(packet_paths)) != len(packet_paths):
        return ()
    if any(not _is_direct_rollout_packet_ref(packet_path) for packet_path in packet_paths):
        return ()
    return packet_paths


def _head_packet_authorizes_pi_transition(
    repo_root: Path,
    *,
    head: str,
    path: str,
    base_entry: BacklogEntry,
    old_signature: tuple[str, str, tuple[str, ...]],
) -> bool:
    """Validate one BASE-row packet reference against immutable HEAD bytes.

    The BASE entry's literal ``delivery_refs`` is the entry-level binding.  A
    cancelled or superseded packet at that same path is an existing
    source-side authority host only when its HEAD bytes prove the exact old
    target identity and explicitly record a withdrawal/replacement reason.
    No worktree packet can authorize a removal.
    """

    packet_paths = _base_transition_packet_paths(base_entry)
    if not packet_paths:
        return False
    target_repo, target_kind, target_writable_carriers = old_signature
    for packet_path in packet_paths:
        text = _git_snapshot_text(repo_root, head, packet_path)
        if text is None:
            continue
        try:
            packet = parse_packet_text(text)
            headers = packet.get("header_values")
            packet_meta = packet.get("packet_meta")
            if not isinstance(headers, dict) or not isinstance(packet_meta, dict):
                continue
            if any(len(headers.get(field, [])) != 1 for field in ("Source repo", "Status", "Target repo", "Target kind")):
                continue
            if headers["Source repo"][0] != CURRENT_CONSUMER_REPO or packet_meta.get("source_repo") != CURRENT_CONSUMER_REPO:
                continue
            header_status = _packet_header_status(packet)
            meta_status = _packet_meta_status(packet)
            if header_status not in {"cancelled", "superseded"} or meta_status != header_status:
                continue
            acknowledgement = packet_meta.get("source_acknowledgement")
            if not isinstance(acknowledgement, dict) or str(acknowledgement.get("status") or "").strip().lower() != header_status:
                continue
            reason = _packet_ack_reason(packet)
            if reason is None or _single_pi_transition_reference(reason) != packet_path:
                continue
            if _normalize_repo_id(str(headers["Target repo"][0])) != target_repo:
                continue
            if _packet_target_repo(packet) != target_repo or _normalize_repo_id(str(packet_meta.get("target_repo") or "")) != target_repo:
                continue
            if str(headers["Target kind"][0]).strip() != target_kind or str(packet_meta.get("target_kind") or "").strip() != target_kind:
                continue
            source_artifacts = _normalize_current_delivery_path_list(
                packet_meta.get("source_artifacts"), field="source_artifacts"
            )
            target_carriers = _normalize_current_delivery_path_list(
                packet_meta.get("target_writable_carriers"), field="target_writable_carriers"
            )
            if path not in source_artifacts or tuple(target_carriers) != target_writable_carriers:
                continue
            if _current_delivery_section_paths(
                str(packet.get("text") or ""), heading="Source artifacts", field="source_artifacts"
            ) != source_artifacts:
                continue
            if _current_delivery_section_paths(
                str(packet.get("text") or ""), heading="Target writable carriers", field="target_writable_carriers"
            ) != target_carriers:
                continue
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return False


def _pi_transition_authorized(
    entry: BacklogEntry | None,
    *,
    repo_root: Path,
    head: str,
    path: str,
    base_entry: BacklogEntry,
    old_signature: tuple[str, str, tuple[str, ...]],
) -> bool:
    """Check an in-row ref or an exact HEAD packet authority for a transition."""

    if entry is not None and _single_pi_transition_reference(entry.triage_note) in _base_transition_packet_paths(base_entry):
        return True
    return _head_packet_authorizes_pi_transition(
        repo_root,
        head=head,
        path=path,
        base_entry=base_entry,
        old_signature=old_signature,
    )


def _pi_entry_applicability(path: str, entry: BacklogEntry) -> ApplicabilityRecord:
    target_fields = (
        entry.target_canon_path,
        entry.target_repo_scope,
        entry.delivery_mode,
        entry.execution_kind,
        entry.execution_ref,
    )
    fully_null = all(value == "null" for value in target_fields)
    authority = f"process-improvements {path}#{entry.entry_id}"

    if entry.status == "open" and entry.priority == "P?" and fully_null:
        return _source_only_record(path, f"PI {entry.entry_id} is a fully-null open source-only row", authority=authority)
    if entry.status == "rejected":
        if fully_null:
            return _source_only_record(path, f"PI {entry.entry_id} is a rejected source-only row", authority=authority)
        return _blocking_record(path, f"PI {entry.entry_id} rejected row retains target-bearing fields", authority=authority)
    if entry.status == "unconfirmed":
        return _blocking_record(path, f"PI {entry.entry_id} is unconfirmed", authority=authority)
    if entry.status == "deferred":
        if "packetization_outcome=source_only" in entry.triage_note.lower() and entry.target_repo_scope == CURRENT_CONSUMER_REPO:
            return _source_only_record(path, f"PI {entry.entry_id} deferred source-only outcome", authority=authority)
        return _blocking_record(
            path,
            f"PI {entry.entry_id} deferred row lacks an explicit packetization outcome",
            authority=authority,
        )
    if entry.target_repo_scope == CURRENT_CONSUMER_REPO and entry.delivery_mode == "source_only":
        return _source_only_record(path, f"PI {entry.entry_id} has current-repo source-only delivery", authority=authority)
    if entry.target_repo_scope == "multi_repo" or entry.delivery_mode == "umbrella_mixed":
        return _blocking_record(path, f"PI {entry.entry_id} has ambiguous multi-repo applicability", authority=authority)
    if entry.delivery_mode not in {"source_plus_rollout", "packet_only"}:
        return _blocking_record(path, f"PI {entry.entry_id} has unsupported delivery mode for target packetization", authority=authority)
    target_repo = normalize_repo_id(entry.target_repo_scope)
    if target_repo == TARGET_LOCAL_SCOPE:
        return _blocking_record(
            path,
            f"PI {entry.entry_id} target-local scope must name one consumer repo",
            authority=authority,
        )
    if target_repo in {"", "null", "multi-repo"}:
        return _blocking_record(path, f"PI {entry.entry_id} lacks one literal target repo", authority=authority)
    issues = triage_carrier_issues(entry)
    if issues:
        detail = ", ".join(f"{issue.field}:{issue.code}" for issue in issues)
        return _blocking_record(path, f"PI {entry.entry_id} has incomplete carrier fields ({detail})", authority=authority)
    target_kind = PI_EXECUTION_KIND_TO_TARGET_KIND.get(entry.execution_kind)
    if target_kind is None:
        return _blocking_record(
            path,
            f"PI {entry.entry_id} execution_kind {entry.execution_kind!r} has no checked-in target-kind mapping",
            authority=authority,
        )
    carrier = _normalize_changed_path(entry.target_canon_path)
    if carrier is None:
        return _blocking_record(path, f"PI {entry.entry_id} target_canon_path is invalid", authority=authority)
    return _target_record(
        path,
        target_repo=target_repo,
        target_kind=target_kind,
        target_writable_carriers=(carrier,),
        authority=authority,
    )


def _snapshot_backlog_entries(
    repo_root: Path,
    *,
    ref: str,
    path: str,
) -> dict[str, BacklogEntry]:
    text = _git_snapshot_text(repo_root, ref, path)
    if text is None:
        return {}
    parsed = parse_backlog_text(text, path=repo_root / path, project_root=repo_root)
    entries: dict[str, BacklogEntry] = {}
    for entry in parsed.entries:
        if entry.entry_id in entries:
            raise ValueError(f"duplicate process-improvement entry id in {path}@{ref}: {entry.entry_id}")
        entries[entry.entry_id] = entry
    return entries


def _process_improvement_records_for_range(
    repo_root: Path,
    *,
    base: str,
    head: str,
    changed_files: list[str],
) -> dict[str, tuple[ApplicabilityRecord, ...]]:
    result: dict[str, tuple[ApplicabilityRecord, ...]] = {}
    for path in sorted(path for path in changed_files if _is_process_improvement_backlog(path)):
        try:
            base_entries = _snapshot_backlog_entries(repo_root, ref=base, path=path)
            head_entries = _snapshot_backlog_entries(repo_root, ref=head, path=path)
        except (OSError, ValueError) as exc:
            result[path] = (
                _blocking_record(
                    path,
                    f"could not normalize exact process-improvement snapshots: {exc}",
                    authority="process_improvements_collect parser",
                ),
            )
            continue

        records: list[ApplicabilityRecord] = []
        for entry_id in sorted(set(base_entries) | set(head_entries)):
            base_entry = base_entries.get(entry_id)
            head_entry = head_entries.get(entry_id)
            if base_entry == head_entry:
                continue
            base_record = _pi_entry_applicability(path, base_entry) if base_entry else None
            head_record = _pi_entry_applicability(path, head_entry) if head_entry else None
            base_signature = _entry_target_signature(base_record) if base_record else None
            head_signature = _entry_target_signature(head_record) if head_record else None
            if base_signature is not None and base_signature != head_signature and not _pi_transition_authorized(
                head_entry,
                repo_root=repo_root,
                head=head,
                path=path,
                base_entry=base_entry,
                old_signature=base_signature,
            ):
                records.append(
                    _blocking_record(
                        path,
                        f"PI {entry_id} removes or changes target/kind/carriers without packetization withdrawal/replacement authority",
                        authority=f"process-improvements {path}#{entry_id}",
                    )
                )
            if head_record is not None:
                records.append(head_record)
        if not records:
            records.append(
                _source_only_record(
                    path,
                    "PI snapshot changed without a row-level delivery obligation",
                    authority="process_improvements_collect parser",
                )
            )
        result[path] = tuple(records)
    return result


def resolve_target_applicability(
    repo_root: Path,
    *,
    changed_files: list[str] | tuple[str, ...],
    base: str | None = None,
    head: str | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> TargetApplicabilityResult:
    """Resolve the public normal form for an exact range or a test seam.

    No target checkout is read.  PI snapshot data is only read from explicit
    Git objects when both full range endpoints are supplied.
    """

    normalized_paths = [path for path in changed_files if _normalize_changed_path(path) is not None]
    pi_records: dict[str, tuple[ApplicabilityRecord, ...]] = {}
    if base is not None and head is not None:
        pi_records = _process_improvement_records_for_range(
            repo_root,
            base=base,
            head=head,
            changed_files=normalized_paths,
        )
    return _build_target_applicability_result(
        changed_files,
        pi_records_by_path=pi_records,
        mirror_policy=mirror_policy,
    )


def run_git(repo_root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def read_range(repo_root: Path) -> str:
    def read_one(path: Path) -> str:
        if not path.is_file():
            raise ValueError(f"missing {repo_rel(path, repo_root)}")
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        raise ValueError(f"empty {repo_rel(path, repo_root)}")

    base = read_one(repo_root / ".planveyor.range.base")
    head = read_one(repo_root / ".planveyor.range.head")
    return f"{base}..{head}"


def changed_files_for_range(repo_root: Path, range_ref: str) -> list[str]:
    rc, stdout, stderr = run_git(repo_root, "diff", "--name-only", range_ref)
    if rc != 0:
        detail = stderr.strip() or stdout.strip() or f"git diff failed for {range_ref}"
        raise RuntimeError(detail)
    return sorted(line.strip() for line in stdout.splitlines() if line.strip())


def _normalize_source_plan_path(value: str) -> str:
    raw = value.strip()
    if not raw or raw != value or "\\" in raw:
        raise ValueError("--source-plan must be a normalized repo-relative docs/plans/*.md path")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.as_posix() != raw or candidate.parts != ("docs", "plans", candidate.name):
        raise ValueError("--source-plan must be a repo-relative docs/plans/*.md path")
    if candidate.suffix != ".md":
        raise ValueError("--source-plan must be a repo-relative docs/plans/*.md path")
    return candidate.as_posix()


def _resolve_commit_oid(repo_root: Path, ref: str, *, label: str) -> str:
    rc, stdout, stderr = run_git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if rc != 0:
        detail = stderr.strip() or stdout.strip() or "not a commit"
        raise ValueError(f"{label} range ref `{ref}` must resolve to a commit: {detail}")
    oid = stdout.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", oid):
        raise ValueError(f"{label} range ref `{ref}` did not resolve to a full commit OID")
    return oid.lower()


def resolve_recovery_lineage(
    repo_root: Path,
    *,
    range_ref: str,
    source_plan: str | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> RecoveryLineage:
    """Resolve the exact range identity before recovery can touch packet bytes or the index."""

    base_ref, separator, head_ref = range_ref.partition("..")
    if not separator or not base_ref or not head_ref or ".." in head_ref:
        raise ValueError("--range must use exactly BASE..HEAD")
    normalized_source_plan = _normalize_source_plan_path(source_plan) if source_plan is not None else None
    base = _resolve_commit_oid(repo_root, base_ref, label="BASE")
    head = _resolve_commit_oid(repo_root, head_ref, label="HEAD")
    rc, stdout, stderr = run_git(repo_root, "merge-base", "--is-ancestor", base, head)
    if rc != 0:
        detail = stderr.strip() or stdout.strip()
        suffix = f": {detail}" if detail else ""
        raise ValueError(f"BASE `{base}` must be an ancestor of HEAD `{head}`{suffix}")
    resolved_range = f"{base}..{head}"
    changed_files = changed_files_for_range(repo_root, resolved_range)
    applicability = resolve_target_applicability(
        repo_root,
        changed_files=changed_files,
        base=base,
        head=head,
        mirror_policy=mirror_policy,
    )
    # The legacy top-level field remains a range-level report context.  It is
    # never used as a per-packet coverage expectation.
    source_artifacts = applicability.report_context_paths
    return RecoveryLineage(
        base=base,
        head=head,
        range_ref=resolved_range,
        source_plan=normalized_source_plan,
        changed_files=tuple(changed_files),
        source_artifacts=source_artifacts,
        applicability=applicability,
    )


def packet_text(summary: dict[str, Any]) -> str:
    absolute_path = Path(str(summary.get("absolute_path") or ""))
    if not absolute_path.is_file():
        return ""
    return absolute_path.read_text(encoding="utf-8")


def markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def normalize_path_token(value: str) -> str:
    token = value.strip().strip("`'\"")
    token = token.rstrip(".,;:)")
    token = token.replace("\\", "/")
    if not token or token.lower().startswith("n/a"):
        return ""
    return token


def section_path_tokens(section: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"`([^`]+)`", section):
        for part in re.split(r"\s+", raw):
            token = normalize_path_token(part)
            if "/" in token:
                tokens.add(token)
    for raw in re.findall(r"(?:^|[\s(:])((?:/[\w.@+-]+)+|(?:[\w.@+-]+/)+[\w.@+-]+)", section, flags=re.MULTILINE):
        token = normalize_path_token(raw)
        if "/" in token:
            tokens.add(token)
    return tokens


def path_token_matches_changed_file(token: str, changed_file: str) -> bool:
    normalized_token = normalize_path_token(token)
    normalized_changed = normalize_path_token(changed_file)
    if not normalized_token or not normalized_changed:
        return False
    return normalized_token == normalized_changed or normalized_token.endswith(f"/{normalized_changed}")


def packet_target_writable_carriers(summary: dict[str, Any]) -> set[str]:
    raw = summary.get("target_writable_carriers")
    if isinstance(raw, list):
        return {normalize_path_token(str(item)) for item in raw if normalize_path_token(str(item))}
    return section_path_tokens(markdown_section(packet_text(summary), "Target writable carriers"))


def packet_targets_changed_file(summary: dict[str, Any], changed_file: str) -> bool:
    return any(path_token_matches_changed_file(token, changed_file) for token in packet_target_writable_carriers(summary))


def packet_source_artifacts(summary: dict[str, Any]) -> set[str]:
    """Return declared source artifacts only; target carriers are never source coverage."""

    raw = summary.get("source_artifacts")
    if not isinstance(raw, list):
        return set()
    return {normalize_path_token(str(item)) for item in raw if normalize_path_token(str(item))}


def _literal_packet_path_list(value: object) -> tuple[str, ...] | None:
    """Return only a canonical packet path list; never normalize it into a match.

    Packetization admission is an equality contract.  Turning a packet list
    into a set would let duplicate, reordered, whitespace-padded or extra
    target intent pass a partition check.
    """

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    paths = tuple(value)
    if not paths or paths != tuple(sorted(set(paths))):
        return None
    if any(_normalize_changed_path(path) != path for path in paths):
        return None
    return paths


def packet_sources_changed_file(summary: dict[str, Any], changed_file: str) -> bool:
    normalized_changed = normalize_path_token(changed_file)
    return bool(normalized_changed and normalized_changed in packet_source_artifacts(summary))


def packet_matches_envelope(
    summary: dict[str, Any],
    *,
    target_repo: str,
    target_kind: str | None = None,
) -> bool:
    if str(summary.get("source_repo") or "") != CURRENT_CONSUMER_REPO:
        return False
    packet_target_repo = normalize_repo_id(str(summary.get("target_repo") or ""))
    requested_target_repo = normalize_repo_id(target_repo)
    if packet_target_repo != requested_target_repo:
        return False
    if target_kind is not None and str(summary.get("target_kind") or "") != target_kind:
        return False
    return str(summary.get("status") or "").lower() in MATCHABLE_PACKET_STATUSES


def packet_matches_changed_file(
    summary: dict[str, Any],
    *,
    changed_file: str,
    target_repo: str,
    target_kind: str | None = None,
    source_range: str | None = None,
    source_revision: str | None = None,
    source_artifacts: list[str] | None = None,
    target_writable_carriers: list[str] | None = None,
    eligible_packet_paths: set[str] | None = None,
) -> bool:
    if not packet_matches_envelope(summary, target_repo=target_repo, target_kind=target_kind):
        return False
    if eligible_packet_paths is not None and str(summary.get("path") or "") not in eligible_packet_paths:
        return False
    # Older open packets can still be a deliberate placeholder before a
    # current-range restamp.  Once either value is literal, however, it is
    # target intent and must not be reused for another range/revision.
    declared_range = str(summary.get("source_range") or "").strip()
    if source_range is not None and declared_range and not declared_range.lower().startswith("n/a"):
        if declared_range.lower() != source_range.lower():
            return False
    declared_revision = str(summary.get("source_revision") or "").strip()
    if source_revision is not None and declared_revision and not declared_revision.lower().startswith("n/a"):
        if declared_revision.lower() != source_revision.lower():
            return False
    declared_source_artifacts: tuple[str, ...] | None = None
    if source_artifacts is not None:
        declared_source_artifacts = _literal_packet_path_list(summary.get("source_artifacts"))
        if declared_source_artifacts != tuple(source_artifacts):
            return False
    if target_writable_carriers is not None:
        declared_carriers = _literal_packet_path_list(summary.get("target_writable_carriers"))
        if declared_carriers != tuple(target_writable_carriers):
            return False
    if declared_source_artifacts is not None:
        return changed_file in declared_source_artifacts
    return packet_sources_changed_file(summary, changed_file)


def best_packet_for_changed_file(
    summaries: list[dict[str, Any]],
    *,
    changed_file: str,
    target_repo: str,
    target_kind: str | None = None,
    source_range: str | None = None,
    source_revision: str | None = None,
    source_artifacts: list[str] | None = None,
    target_writable_carriers: list[str] | None = None,
    eligible_packet_paths: set[str] | None = None,
) -> dict[str, Any] | None:
    candidates = [
        summary
        for summary in summaries
        if packet_matches_envelope(summary, target_repo=target_repo, target_kind=target_kind)
    ]
    if not candidates:
        return None
    matches = [
        summary
        for summary in candidates
        if packet_matches_changed_file(
            summary,
            changed_file=changed_file,
            target_repo=target_repo,
            target_kind=target_kind,
            source_range=source_range,
            source_revision=source_revision,
            source_artifacts=source_artifacts,
            target_writable_carriers=target_writable_carriers,
            eligible_packet_paths=eligible_packet_paths,
        )
    ]
    covering = [summary for summary in matches if str(summary.get("status") or "").lower() in COVERING_PACKET_STATUSES]
    return sorted(covering or matches, key=lambda item: str(item.get("path") or ""))[-1] if (covering or matches) else None


def build_rows(
    changed_files: list[str],
    summaries: list[dict[str, Any]],
    *,
    applicability: TargetApplicabilityResult | None = None,
    source_range: str | None = None,
    source_revision: str | None = None,
    eligible_packet_paths: set[str] | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> list[dict[str, Any]]:
    normalized = applicability or _build_target_applicability_result(
        changed_files,
        mirror_policy=mirror_policy,
    )
    rows: list[dict[str, Any]] = []
    for record in normalized.records:
        changed_file = record.changed_file
        if record.ignored_reason:
            continue
        if record.source_only_reason:
            rows.append(
                {
                    "changed_file": changed_file,
                    "target_repo": record.target_repo or "source-only",
                    "target_kind": record.target_kind or "source_only",
                    "target_source_artifacts": [],
                    "target_writable_carriers": [],
                    "authority": record.authority,
                    "packet_path": "N/A",
                    "packet_status": "N/A",
                    "target_adoption_state": "N/A",
                    "coverage": "source_only",
                    "blocking": False,
                    "action": record.source_only_reason,
                }
            )
            continue
        if record.blocking_reason:
            coverage = (
                "unknown_target_mapping"
                if "unknown" in record.blocking_reason.lower()
                else "invalid_applicability"
            )
            rows.append(
                {
                    "changed_file": changed_file,
                    "target_repo": record.target_repo or "unknown",
                    "target_kind": record.target_kind or "unknown",
                    "target_source_artifacts": [],
                    "target_writable_carriers": [],
                    "authority": record.authority,
                    "packet_path": "N/A",
                    "packet_status": "unknown",
                    "target_adoption_state": "N/A",
                    "coverage": coverage,
                    "blocking": True,
                    "action": record.blocking_reason,
                }
            )
            continue
        if not record.target_repo or not record.target_kind:
            rows.append(
                {
                    "changed_file": changed_file,
                    "target_repo": record.target_repo or "unknown",
                    "target_kind": record.target_kind or "unknown",
                    "target_source_artifacts": [],
                    "target_writable_carriers": [],
                    "authority": record.authority or "packetization normalizer",
                    "packet_path": "N/A",
                    "packet_status": "unknown",
                    "target_adoption_state": "N/A",
                    "coverage": "invalid_applicability",
                    "blocking": True,
                    "action": "target applicability record is incomplete",
                }
            )
            continue
        partition = normalized.partition_for(
            target_repo=record.target_repo,
            target_kind=record.target_kind,
        )
        if partition is None:
            rows.append(
                {
                    "changed_file": changed_file,
                    "target_repo": record.target_repo,
                    "target_kind": record.target_kind,
                    "target_source_artifacts": [],
                    "target_writable_carriers": list(record.target_writable_carriers),
                    "authority": record.authority,
                    "packet_path": "N/A",
                    "packet_status": "unknown",
                    "target_adoption_state": "N/A",
                    "coverage": "invalid_applicability",
                    "blocking": True,
                    "action": "normalized target partition is missing",
                }
            )
            continue
        expected_artifacts = list(partition.target_source_artifacts)
        expected_carriers = list(partition.target_writable_carriers)
        packet = best_packet_for_changed_file(
            summaries,
            changed_file=changed_file,
            target_repo=partition.target_repo,
            target_kind=partition.target_kind,
            source_range=source_range,
            source_revision=source_revision,
            source_artifacts=expected_artifacts,
            target_writable_carriers=expected_carriers,
            eligible_packet_paths=eligible_packet_paths,
        )
        is_covered = bool(
            packet
            and str(packet.get("status") or "").lower() in COVERING_PACKET_STATUSES
            and packet_matches_changed_file(
                packet,
                changed_file=changed_file,
                target_repo=partition.target_repo,
                target_kind=partition.target_kind,
                source_range=source_range,
                source_revision=source_revision,
                source_artifacts=expected_artifacts,
                target_writable_carriers=expected_carriers,
                eligible_packet_paths=eligible_packet_paths,
            )
        )
        rows.append(
            {
                "changed_file": changed_file,
                "target_repo": partition.target_repo,
                "target_kind": partition.target_kind,
                "target_source_artifacts": expected_artifacts,
                "target_writable_carriers": expected_carriers,
                "authority": record.authority,
                "packet_path": str(packet.get("path") or "N/A") if packet else "N/A",
                "packet_status": str(packet.get("status") or "missing") if packet else "missing",
                "target_adoption_state": _packet_target_adoption_state(packet) if packet else "N/A",
                "coverage": "covered" if is_covered else "missing-packet",
                "blocking": not is_covered,
                "action": "none" if is_covered else "create exact partition packet or fail close",
            }
        )
    return rows


def _format_packet_findings(findings: list[dict[str, object]]) -> str:
    messages = [str(finding.get("message") or "invalid packet") for finding in findings]
    return "; ".join(messages) or "invalid packet"


def _admit_recovery_packets(
    repo_root: Path,
    raw_packet_paths: list[str],
    *,
    applicability: TargetApplicabilityResult,
) -> list[tuple[str, Path, dict[str, object], TargetApplicability]]:
    admitted: list[tuple[str, Path, dict[str, object], TargetApplicability]] = []
    seen_paths: set[Path] = set()
    for raw_path in raw_packet_paths:
        packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
        if packet_path in seen_paths:
            raise ValueError(f"duplicate canonical packet input: {raw_path}")
        seen_paths.add(packet_path)
        _, findings = _validate_current_delivery_restamp_input(packet_path, repo_root)
        errors = [finding for finding in findings if finding.get("severity") == "error"]
        if errors:
            raise ValueError(f"packet `{raw_path}` is not admissible for recovery: {_format_packet_findings(errors)}")
        stable_identity = _current_delivery_stable_identity(packet_path, repo_root)
        target_repo = str(stable_identity.get("target_repo") or "")
        target_kind = str(stable_identity.get("target_kind") or "")
        raw_carriers = stable_identity.get("target_writable_carriers")
        if not isinstance(raw_carriers, list):
            raise ValueError(f"packet `{raw_path}` has no stable target_writable_carriers")
        partition = applicability.partition_for(
            target_repo=target_repo,
            target_kind=target_kind,
        )
        if partition is None:
            raise ValueError(
                f"packet `{raw_path}` has no matching current target partition "
                f"for {target_repo or 'missing'}:{target_kind or 'missing'}"
            )
        if tuple(str(item) for item in raw_carriers) != partition.target_writable_carriers:
            raise ValueError(
                f"packet `{raw_path}` target_writable_carriers do not equal the current "
                f"{partition.target_repo}:{partition.target_kind} partition"
            )
        admitted.append((raw_path, packet_path, stable_identity, partition))
    return admitted


def _stage_packets(repo_root: Path, raw_packet_paths: list[str]) -> None:
    if not raw_packet_paths:
        return
    canonical_paths: list[str] = []
    for raw_path in raw_packet_paths:
        packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
        canonical_paths.append(repo_rel(packet_path, repo_root))
    rc, stdout, stderr = run_git(repo_root, "add", "--", *canonical_paths)
    if rc != 0:
        detail = stderr.strip() or stdout.strip() or "git add failed"
        raise RuntimeError(f"could not stage admitted recovery packets: {detail}")


def restamp_recovery_packets(
    repo_root: Path,
    *,
    lineage: RecoveryLineage,
    raw_packet_paths: list[str],
    stage_packets: bool,
) -> list[str]:
    """Restamp only admitted open packets after all lineage/path guards have passed."""

    admitted = _admit_recovery_packets(
        repo_root,
        raw_packet_paths,
        applicability=lineage.applicability,
    )
    rendered_packets: list[tuple[str, Path, dict[str, object], TargetApplicability, str]] = []
    for raw_path, admitted_path, stable_identity, partition in admitted:
        packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
        if packet_path != admitted_path:
            raise ValueError(f"packet path changed during recovery admission: {raw_path}")
        summary = _packet_summary(packet_path, repo_root)
        packet_source_plan = str(summary.get("source_plan") or "")
        rendered = _render_current_delivery_restamp(
            packet_path,
            repo_root,
            source_plan=packet_source_plan,
            source_range=lineage.range_ref,
            source_revision=lineage.head,
            source_artifacts=list(partition.target_source_artifacts),
            expected_target_repo=partition.target_repo,
            expected_target_kind=partition.target_kind,
            expected_target_writable_carriers=list(partition.target_writable_carriers),
        )
        rendered_packets.append((raw_path, admitted_path, stable_identity, partition, rendered))

    for raw_path, admitted_path, stable_identity, _, rendered in rendered_packets:
        packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
        if packet_path != admitted_path:
            raise ValueError(f"packet path changed during recovery write: {raw_path}")
        packet_path.write_text(rendered, encoding="utf-8")
        if _current_delivery_stable_identity(packet_path, repo_root) != stable_identity:
            raise RuntimeError(f"recovery attempted to change stable packet identity: {raw_path}")

    if stage_packets:
        # Every path was admitted and rendered before the only index mutation.
        _stage_packets(repo_root, [raw_path for raw_path, _, _, _ in admitted])

    accepted_paths: list[str] = []
    for raw_path, admitted_path, _, partition in admitted:
        packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
        if packet_path != admitted_path:
            raise ValueError(f"packet path changed before current-delivery readback: {raw_path}")
        _, findings = _validate_current_delivery_packet(
            packet_path,
            repo_root,
            source_range=lineage.range_ref,
            source_revision=lineage.head,
            source_artifacts=list(partition.target_source_artifacts),
            expected_target_repo=partition.target_repo,
            expected_target_kind=partition.target_kind,
            expected_target_writable_carriers=list(partition.target_writable_carriers),
            require_tracked=True,
        )
        if not any(finding.get("severity") == "error" for finding in findings):
            accepted_paths.append(repo_rel(packet_path, repo_root))
    if len(accepted_paths) != len(admitted):
        raise RuntimeError("admitted recovery packet failed current-delivery readback")
    return sorted(set(accepted_paths))


def current_delivery_packet_paths(
    repo_root: Path,
    *,
    lineage: RecoveryLineage,
) -> set[str]:
    """Reopen current packets from disk; this stays read-only in receipt-reuse mode."""

    packet_root = repo_root / PACKET_DIR
    if not packet_root.is_dir() or packet_root.is_symlink():
        return set()
    paths: set[str] = set()
    for candidate in sorted(packet_root.glob("*.md")):
        if candidate.name == "_template.md":
            continue
        raw_path = (PACKET_DIR / candidate.name).as_posix()
        try:
            packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
            stable_identity = _current_delivery_stable_identity(packet_path, repo_root)
            raw_carriers = stable_identity.get("target_writable_carriers")
            if not isinstance(raw_carriers, list):
                continue
            partition = lineage.applicability.partition_for(
                target_repo=str(stable_identity.get("target_repo") or ""),
                target_kind=str(stable_identity.get("target_kind") or ""),
            )
            if partition is None:
                continue
            _, findings = _validate_current_delivery_packet(
                packet_path,
                repo_root,
                source_range=lineage.range_ref,
                source_revision=lineage.head,
                source_artifacts=list(partition.target_source_artifacts),
                expected_target_repo=partition.target_repo,
                expected_target_kind=partition.target_kind,
                expected_target_writable_carriers=list(partition.target_writable_carriers),
                require_tracked=True,
            )
        except (OSError, ValueError):
            continue
        if not any(finding.get("severity") == "error" for finding in findings):
            paths.add(repo_rel(packet_path, repo_root))
    return paths


def table_value(value: object) -> str:
    text = str(value)
    return text.replace("|", "\\|")


def render_report(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    report_status = "Done" if not payload["blocking_count"] else "Blocked"
    lines = [
        "# Packetization gate report",
        "",
        f"**Status:** {report_status}",
        f"**Schema version:** `{payload['schema_version']}`",
        f"**Range:** `{payload['range']}`",
        f"**Blocking rows:** {payload['blocking_count']}",
        "",
        "## Summary",
        f"- Delivery mode: `{payload['delivery_mode']}`",
        f"- Changed shared canon files: {len(payload['changed_shared_canon_files'])}",
        f"- Packetization report required: `{str(bool(payload['packetization_report_required'])).lower()}`",
        f"- Target packet required: `{str(bool(payload['target_packet_required'])).lower()}`",
        f"- Target partitions: {len(payload['target_partitions'])}",
        f"- Ignored changed files: {payload['ignored_changed_files_count']}",
        f"- Accepted packets: {len(payload['report_accepted_packet_paths'])}",
        f"- Recovery command: `{payload['recovery_command']}`",
        f"- Superseded previous reports: {len(payload.get('superseded_reports', []))}",
        "",
        "## Matrix",
        "| changed_file | target_repo | target_kind | target_source_artifacts | target_writable_carriers | coverage | blocking | packet_path | packet_status | target_adoption_state | action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    table_value(row[key])
                    for key in (
                        "changed_file",
                        "target_repo",
                        "target_kind",
                        "target_source_artifacts",
                        "target_writable_carriers",
                        "coverage",
                        "blocking",
                        "packet_path",
                        "packet_status",
                        "target_adoption_state",
                        "action",
                    )
                )
                + " |"
            )
    else:
        lines.append("| N/A | N/A | N/A | [] | [] | none | false | N/A | N/A | N/A | no shared canon changes |")
    lines.extend(
        [
            "",
            "## Machine-readable JSON",
            "```json",
            json.dumps({"packetization_gate": payload}, indent=2, ensure_ascii=False, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def default_report_path(repo_root: Path, *, range_ref: str, now: datetime) -> Path:
    base, head = range_ref.split("..", 1)
    return repo_root / REPORT_DIR / f"{now:%y%m%d_%H%M}_packetization_gate_range_{base[:7]}_{head[:7]}.md"


def collision_safe_default_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    if REPORT_FILENAME_MARKER not in path.name:
        raise RuntimeError(f"default packetization report path has unexpected name: {path}")
    prefix, rest = path.name.split(REPORT_FILENAME_MARKER, 1)
    for index in range(2, 1000):
        candidate = path.with_name(f"{prefix}_{index:02d}{REPORT_FILENAME_MARKER}{rest}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find unused packetization report path near {path}")


def same_range_report_paths(repo_root: Path, *, range_ref: str, exclude: Path | None = None) -> list[Path]:
    base, head = range_ref.split("..", 1)
    report_dir = repo_root / REPORT_DIR
    pattern = f"*_packetization_gate_range_{base[:7]}_{head[:7]}.md"
    excluded = exclude.resolve() if exclude else None
    paths: list[Path] = []
    for path in sorted(report_dir.glob(pattern)):
        if not path.is_file():
            continue
        if excluded and path.resolve() == excluded:
            continue
        paths.append(path)
    return paths


def report_status_value(report_path: Path) -> str:
    text = report_path.read_text(encoding="utf-8")
    match = REPORT_STATUS_RE.search(text)
    return (match.group("value") if match else "").strip()


def is_superseded_report(report_path: Path) -> bool:
    return report_status_value(report_path).lower().startswith("superseded")


def canonical_default_report_path(repo_root: Path, *, range_ref: str, now: datetime) -> Path:
    existing = same_range_report_paths(repo_root, range_ref=range_ref)
    active = [path for path in existing if not is_superseded_report(path)]
    if len(active) > 1:
        rel_paths = ", ".join(repo_rel(path, repo_root) for path in active)
        raise RuntimeError(
            "ambiguous same-range packetization reports; pass --out for explicit repair/archive path "
            f"or resolve duplicates first: {rel_paths}"
        )
    if active:
        return active[0]
    if existing:
        rel_paths = ", ".join(repo_rel(path, repo_root) for path in existing)
        raise RuntimeError(
            "same-range packetization reports are all superseded; pass --out for explicit repair/archive path "
            f"or resolve the stale reports first: {rel_paths}"
        )
    return default_report_path(repo_root, range_ref=range_ref, now=now)


def replace_markdown_section(text: str, heading: str, replacement_body: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    section = f"## {heading}\n{replacement_body.rstrip()}\n"
    if not match:
        return text.rstrip() + "\n\n" + section
    next_heading = re.search(r"^##\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[: match.start()] + section + text[end:].lstrip("\n")


def mark_report_superseded(
    report_path: Path,
    *,
    repo_root: Path,
    superseded_by: str,
    range_ref: str,
    now: datetime,
) -> bool:
    text = report_path.read_text(encoding="utf-8")
    if REPORT_STATUS_RE.search(text):
        text = REPORT_STATUS_RE.sub("**Status:** Superseded", text, count=1)
    else:
        text = text.rstrip() + "\n\n**Status:** Superseded\n"
    rel_path = repo_rel(report_path, repo_root)
    section_body = "\n".join(
        [
            f"- Superseded by: `{superseded_by}`",
            f"- Range: `{range_ref}`",
            f"- Superseded at: `{now.astimezone():%Y-%m-%d %H:%M %z}`",
        ]
    )
    text = replace_markdown_section(text, "Supersession", section_body)
    report_path.write_text(text, encoding="utf-8")
    return rel_path != superseded_by


def supersede_same_range_reports(
    repo_root: Path,
    *,
    range_ref: str,
    out_path: Path,
    now: datetime,
) -> list[str]:
    superseded_by = repo_rel(out_path, repo_root)
    superseded: list[str] = []
    for report_path in same_range_report_paths(repo_root, range_ref=range_ref, exclude=out_path):
        if mark_report_superseded(
            report_path,
            repo_root=repo_root,
            superseded_by=superseded_by,
            range_ref=range_ref,
            now=now,
        ):
            superseded.append(repo_rel(report_path, repo_root))
    return superseded


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%y%m%d_%H%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported --now value: {value}")


def build_payload(
    repo_root: Path,
    *,
    range_ref: str,
    changed_files: list[str],
    create_drafts: bool,
    now: datetime,
    lineage: RecoveryLineage | None = None,
    accepted_packet_paths: set[str] | None = None,
    delivery_mode: str = "report-only",
    source_revision: str | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, Any]:
    if lineage:
        summaries = []
        for raw_path in sorted(accepted_packet_paths or set()):
            packet_path = _resolve_current_delivery_packet_path(repo_root, raw_path)
            summaries.append(_packet_summary(packet_path, repo_root))
    else:
        try:
            summaries = _load_source_corpus(repo_root)
        except FileNotFoundError:
            summaries = []

    if lineage is not None:
        applicability = lineage.applicability
    else:
        base, separator, head = range_ref.partition("..")
        applicability = resolve_target_applicability(
            repo_root,
            changed_files=changed_files,
            base=base if separator and base else None,
            head=head if separator and head else None,
            mirror_policy=mirror_policy,
        )
    source_artifacts = list(applicability.report_context_paths)
    if lineage:
        rows = build_rows(
            changed_files,
            summaries,
            applicability=applicability,
            source_range=lineage.range_ref,
            source_revision=lineage.head,
            eligible_packet_paths=accepted_packet_paths or set(),
            mirror_policy=mirror_policy,
        )
        source_plan = lineage.source_plan or "N/A (why=range identity has no single source plan)"
        source_revision = lineage.head
    else:
        rows = build_rows(
            changed_files,
            summaries,
            applicability=applicability,
            source_range=range_ref,
            source_revision=source_revision,
            mirror_policy=mirror_policy,
        )
        source_plan = "N/A (why=report-only range identity has no single source plan)"
        source_revision = source_revision or range_ref.partition("..")[2]

    if create_drafts:
        rows.append(
            {
                "changed_file": "N/A",
                "target_repo": "source-local",
                "target_kind": "legacy",
                "target_source_artifacts": [],
                "target_writable_carriers": [],
                "authority": "legacy compatibility",
                "packet_path": "N/A",
                "packet_status": "N/A",
                "target_adoption_state": "N/A",
                "coverage": "legacy-create-drafts-refused",
                "blocking": True,
                "action": LEGACY_CREATE_DRAFTS_RECIPE,
            }
        )

    blocking_rows = [row for row in rows if bool(row.get("blocking"))]
    coverage_counts = {coverage: 0 for coverage in sorted(BLOCKING_COVERAGES | {"source_only"})}
    for row in rows:
        coverage = str(row.get("coverage") or "")
        if coverage:
            coverage_counts[coverage] = coverage_counts.get(coverage, 0) + 1
    changed_shared = list(applicability.report_context_paths)
    accepted_paths = sorted(accepted_packet_paths or set())
    return {
        "schema_version": PACKETIZATION_GATE_SCHEMA_VERSION,
        "step": PACKETIZATION_GATE_STEP,
        "receipt_kind": PACKETIZATION_GATE_RECEIPT_KIND,
        "receipt_name": PACKETIZATION_GATE_RECEIPT_NAME,
        "range": range_ref,
        "source_plan": source_plan,
        "source_range": range_ref,
        "source_revision": source_revision,
        "source_artifacts": source_artifacts,
        "packetization_report_required": applicability.packetization_report_required,
        "target_packet_required": applicability.target_packet_required,
        "target_partitions": [partition.to_json() for partition in applicability.partitions],
        "delivery_mode": "legacy-create-drafts-refused" if create_drafts else delivery_mode,
        "changed_files_count": len(changed_files),
        "changed_shared_canon_files": sorted(set(changed_shared)),
        "ignored_changed_files_count": len(changed_files) - len({str(row["changed_file"]) for row in rows if str(row["changed_file"]) in changed_files}),
        "created_packets": [],
        "draft_packets_created_count": 0,
        "draft_packets_created_paths": [],
        "draft_packets_reused_paths": accepted_paths,
        "report_accepted_packet_paths": accepted_paths,
        "superseded_reports": [],
        "superseded_packetization_reports": [],
        "recovery_command": LEGACY_CREATE_DRAFTS_RECIPE if create_drafts else RECOVERY_COMMAND,
        "rows": rows,
        "blocking_count": len(blocking_rows),
        "blocking_rows_count": len(blocking_rows),
        "blocking_coverages": sorted({row["coverage"] for row in blocking_rows}),
        "blocking_coverage_counts": dict(sorted(coverage_counts.items())),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate the post-merge packetization gate report.")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--range", dest="range_ref", default=None, help="Git range BASE..HEAD")
    parser.add_argument("--out", default=None, help="Report output path (default: docs/reviews/*_packetization_gate_range_*.md)")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Run bounded current-packet recovery for the exact --range; --source-plan is optional provenance.",
    )
    parser.add_argument("--source-plan", default=None, help="Optional repo-relative provenance plan under docs/plans/*.md")
    parser.add_argument("--packet", action="append", default=[], help="Explicit current open packet path (repeatable)")
    parser.add_argument("--stage-packets", action="store_true", help="Stage only accepted explicit --packet paths")
    parser.add_argument(
        "--create-drafts",
        "--apply",
        action="store_true",
        help="Legacy compatibility route: writes no packets and emits the explicit create/complete/recover recipe",
    )
    parser.add_argument("--format", choices=("plain", "json"), default="plain", help="Output format")
    parser.add_argument("--json", action="store_true", help="Compatibility alias for --format json")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved content profile; target-local remains consumer-owned and has no inferred mirror policy.",
    )
    parser.add_argument("--changed-file", action="append", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--now", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    try:
        mirror_policy = load_shared_docs_mirror_policy(content_profile_id=args.content_profile_id)
        now = parse_now(args.now)
        recovery_requested = bool(args.recover or args.source_plan or args.packet or args.stage_packets)
        if args.create_drafts and recovery_requested:
            raise ValueError("--create-drafts cannot be combined with current recovery inputs")
        if args.stage_packets and not args.packet:
            raise ValueError("--stage-packets requires at least one explicit --packet")
        if recovery_requested and not args.range_ref:
            raise ValueError("current recovery requires --range BASE..HEAD")

        requested_range = args.range_ref or read_range(repo_root)
        if ".." not in requested_range:
            raise ValueError("--range must use BASE..HEAD")
        lineage: RecoveryLineage | None = None
        report_source_revision: str | None = None
        if recovery_requested:
            if args.changed_file:
                raise ValueError("--changed-file is not accepted in current recovery; source artifacts come from the resolved range")
            lineage = resolve_recovery_lineage(
                repo_root,
                range_ref=requested_range,
                source_plan=args.source_plan,
                mirror_policy=mirror_policy,
            )
            range_ref = lineage.range_ref
            changed_files = list(lineage.changed_files)
            report_source_revision = lineage.head
        else:
            if args.changed_file:
                # Hidden test seam: injected classifications intentionally need no Git fixture.
                range_ref = requested_range
                changed_files = sorted(args.changed_file)
                report_source_revision = range_ref.partition("..")[2]
            else:
                report_lineage = resolve_recovery_lineage(
                    repo_root,
                    range_ref=requested_range,
                    mirror_policy=mirror_policy,
                )
                range_ref = report_lineage.range_ref
                changed_files = list(report_lineage.changed_files)
                report_source_revision = report_lineage.head

        # Resolve the canonical report before a recovery can write packet bytes or stage paths.
        out_path = Path(args.out) if args.out else canonical_default_report_path(
            repo_root, range_ref=range_ref, now=now
        )
        if not out_path.is_absolute():
            out_path = repo_root / out_path
        if args.out and out_path.exists():
            raise ValueError("explicit --out must name a fresh report path; existing same-range evidence is immutable")

        accepted_packet_paths: set[str] = set()
        delivery_mode = "report-only"
        if lineage:
            if args.packet:
                restamp_recovery_packets(
                    repo_root,
                    lineage=lineage,
                    raw_packet_paths=list(args.packet),
                    stage_packets=bool(args.stage_packets),
                )
                delivery_mode = "discovery-or-seed"
            else:
                delivery_mode = "receipt-reuse-only"
            accepted_packet_paths = current_delivery_packet_paths(repo_root, lineage=lineage)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = build_payload(
            repo_root,
            range_ref=range_ref,
            changed_files=changed_files,
            create_drafts=args.create_drafts,
            now=now,
            lineage=lineage,
            accepted_packet_paths=accepted_packet_paths,
            delivery_mode=delivery_mode,
            source_revision=report_source_revision,
            mirror_policy=mirror_policy,
        )
        payload["report_path"] = repo_rel(out_path, repo_root)
        # A fresh explicit report is P0 regression evidence and must leave the
        # blocked incident byte-for-byte intact.  Canonical default recovery
        # retains the historical single-active-report behavior.
        payload["superseded_reports"] = (
            []
            if args.out
            else supersede_same_range_reports(
                repo_root,
                range_ref=range_ref,
                out_path=out_path,
                now=now,
            )
        )
        payload["superseded_packetization_reports"] = payload["superseded_reports"]
        out_path.write_text(render_report(payload), encoding="utf-8")
    except (MirrorPolicyError, RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json or args.format == "json":
        sys.stdout.write(json.dumps({"packetization_gate": payload}, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        print(f"Saved: {payload['report_path']}")
        print(f"Blocking rows: {payload['blocking_count']}")
        print(f"Accepted packets: {len(payload['report_accepted_packet_paths'])}")
        if payload["blocking_count"]:
            print(f"Recovery command: {payload['recovery_command']}")
    return 2 if payload["blocking_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

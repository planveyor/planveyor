#!/usr/bin/env python3
"""Source-owned review-range scaffold engine.

This module is deliberately the only generator route for both legacy and
engaged review-range scaffolds.  A Planveyor marker supplies only the finite
declared inputs recorded below; it never chooses an executable, a root, a
template, a publisher, or an output location.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any, Final, Mapping, Sequence


ENGINE_SCHEMA_VERSION: Final[str] = "review_range_scaffold_engine.v1"
ENGINE_VERSION: Final[str] = "review-range-source-route.v2"
# API 5 is deliberately provisional.  Parent integration must rebind it to
# the actual predecessor after the independently serialized API-4 route.
REVIEW_RANGE_RUNTIME_API_VERSION: Final[int] = 5
SEMANTIC_SURFACE_SHA256: Final[str] = (
    "f41cf5cbc089f4614d4106e48366eabe4bcbb388e02d6fbcf981c59aa57bc5de"
)

# The table is source code, not a target registry.  Every target-facing read
# or render attachment below is finite and has an exact literal locator.
PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1: Final[Mapping[str, Any]] = {
    "schema_version": "planveyor.review_range_scaffold.semantic_surface_inventory.v1",
    "sha256": SEMANTIC_SURFACE_SHA256,
    "selectors": {
        "corpus_rule": "planveyor.v1",
        "visual_rule": "planveyor.v1",
        "render_profile": "planveyor.review_only.v1",
    },
    "inputs": {
        "policy_json": {
            "path": "docs/_meta/review_range_policy.v1.json",
            "reader": "strict_duplicate_key_safe_json",
            "outputs": (
                "plan:Scope",
                "plan:Reviewability preflight receipt",
                "plan:Visual Acceptance (browser, UI tasks)",
                "plan:Verification rerun / exec handoff",
            ),
        },
        "plan_template": {"path": "docs/plans/_template.md", "reader": "declared_text"},
        "code_draft_template": {"path": "docs/code_drafts/_template.md", "reader": "declared_text"},
        "reviewer_role_reference": {"path": "docs/roles/reviewer.md", "reader": "declared_identity"},
        "review_scoping_playbook": {"path": "docs/playbooks/review_scoping_plan.md", "reader": "declared_text"},
        "review_merge_playbook": {"path": "docs/playbooks/review_merge_range.md", "reader": "declared_text"},
        "plan_vocabulary_reference": {
            "path": "docs/_meta/plan_vocab.json",
            "reader": "captured_row_only",
        },
        "smoke_visual": {"path": "docs/smoke_visual.md", "reader": "visual_helper_declared_text"},
        "testing_runbook": {"path": "docs/testing_runbook.md", "reader": "visual_helper_declared_text"},
    },
    "render_destinations": frozenset(
        {
            "plan:Scope",
            "plan:Reviewability preflight receipt",
            "plan:Visual Acceptance (browser, UI tasks)",
            "plan:Verification rerun / exec handoff",
            "plan:Review-range semantic provenance",
            "draft:Review-range semantic provenance",
            "visual_support_carrier",
        }
    ),
    "legacy_rules": frozenset(
        {
            "legacy_profile_aware_generated_prose",
            "range_and_artifact_core",
            "visual_contract_parser_and_renderer",
            "provenance_rerun_and_lifecycle",
            "fixed_dependent_test_map",
            "review_only_mechanical_commands",
        }
    ),
}

_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "corpus_rule", "visual_rule", "render_profile", "section_prose"}
)
_POLICY_PROSE_KEYS: Final[Mapping[str, str]] = {
    "review_scope_note": "Scope",
    "reviewability_note": "Reviewability preflight receipt",
    "runtime_lane_note": "Visual Acceptance (browser, UI tasks)",
    "verification_handoff_note": "Verification rerun / exec handoff",
}
_HEX40_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_CONSUMER_REPOSITORY_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_KNOWN_CONTENT_PROFILES = frozenset({"default", "planveyor", "target-local"})
_ROOT_REVIEW_REFERENCE_IDS = (
    "reviewer_role",
    "review_scoping_playbook",
    "review_merge_range_playbook",
)


class EngineError(RuntimeError):
    """Stable internal failure with no success payload."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}{': ' + detail if detail else ''}")
        self.code = code


@dataclass(frozen=True)
class ReviewRangeSourcePolicy:
    """Explicit root-local references used by legacy source callers."""

    references: tuple[tuple[str, str], ...]

    def reference_for(self, reference_id: str) -> str:
        values = dict(self.references)
        try:
            return values[reference_id]
        except KeyError as exc:
            raise EngineError("invalid_review_range_source_policy", reference_id) from exc


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _strict_json(data: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EngineError("duplicate_policy_key", f"{label}:{key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise EngineError("invalid_policy_json", f"{label}:{value}")

    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except EngineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EngineError("invalid_policy_json", label) from exc
    if type(value) is not dict:
        raise EngineError("invalid_policy_json", f"{label}:not_object")
    return value


ROOT_GENERIC_REVIEW_REFERENCE_POLICY = ReviewRangeSourcePolicy(
    (
        ("reviewer_role", "docs/roles/reviewer.md"),
        ("review_scoping_playbook", "docs/playbooks/review_scoping_plan.md"),
        ("review_merge_range_playbook", "docs/playbooks/review_merge_range.md"),
    )
)


def _legacy_root_review_references(*, content_profile_id: str) -> ReviewRangeSourcePolicy:
    """Return public root references without inferring a consumer profile tree."""

    profile = content_profile_id.strip()
    if profile not in _KNOWN_CONTENT_PROFILES:
        raise EngineError("invalid_content_profile_id", content_profile_id)
    if profile == "target-local":
        raise EngineError("target_local_requires_declared_context")
    return ROOT_GENERIC_REVIEW_REFERENCE_POLICY


def _safe_relative(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or ".." in candidate.parts
        or "." in candidate.parts
        or "\\" in value
    ):
        raise EngineError("unsafe_output_path", value)
    return candidate.as_posix()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise EngineError("git_operation_failed", result.stderr.strip() or " ".join(args))
    return result.stdout.strip()


def _resolve_commit(root: Path, value: str, *, label: str) -> str:
    resolved = _git(root, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{value}^{{commit}}").lower()
    if _HEX40_RE.fullmatch(resolved) is None:
        raise EngineError("invalid_commitish", label)
    return resolved


def _range_stats(root: Path, base: str, head: str) -> dict[str, Any]:
    range_ref = f"{base}..{head}"
    total = int(_git(root, "rev-list", "--count", range_ref) or "0")
    first_parent = int(_git(root, "rev-list", "--first-parent", "--count", range_ref) or "0")
    paths = [line for line in _git(root, "diff", "--name-only", range_ref).splitlines() if line.strip()]
    shortstat = _git(root, "diff", "--shortstat", range_ref) or "0 files changed, 0 insertions(+), 0 deletions(-)"

    def number(pattern: str) -> int:
        found = re.search(pattern, shortstat)
        return int(found.group(1)) if found else 0

    return {
        "range": range_ref,
        "base": base,
        "head": head,
        "base_short": base[:7],
        "head_short": head[:7],
        "range_id": f"range_{base[:7]}_{head[:7]}",
        "total_commits": total,
        "first_parent_commits": first_parent,
        "changed_files": len(paths),
        "diffstat_summary": shortstat,
        "diffstat": {
            "files_changed": number(r"(\d+)\s+files?\s+changed"),
            "insertions": number(r"(\d+)\s+insertions?\(\+\)"),
            "deletions": number(r"(\d+)\s+deletions?\(-\)"),
        },
        "labels": {
            "total_commits": "total commits",
            "first_parent_commits": "first-parent commits",
            "changed_files": "changed files",
            "diffstat_summary": "diffstat summary",
        },
    }


def _range_paths(root: Path, base: str, head: str, exclude_docs: str) -> list[str]:
    paths = [line for line in _git(root, "diff", "--name-only", f"{base}..{head}").splitlines() if line.strip()]
    if exclude_docs == "1":
        paths = [path for path in paths if not path.startswith("docs/")]
    return paths or ["docs/plans/_template.md"]


def _host_family(paths: Sequence[str]) -> str:
    return "doc_reviews" if paths and all(path.startswith("docs/") for path in paths) else "code_reviews"


def _review_artifact(plan_ref: str, host_family: str) -> str:
    prefix = "docs/doc_reviews" if host_family == "doc_reviews" else "docs/code_reviews"
    return f"{prefix}/{Path(plan_ref).stem}.md"


def _new_plan_ref(root: Path, base: str, head: str, *, timestamp: str | None) -> str:
    from datetime import datetime
    if timestamp is not None and re.fullmatch(r"[0-9]{6}_[0-9]{4}", timestamp) is None:
        raise EngineError("invalid_scaffold_timestamp")
    if timestamp is None:
        clock = subprocess.run(
            ["date", "+%y%m%d_%H%M"],
            text=True,
            capture_output=True,
            check=False,
        )
        timestamp = clock.stdout.strip()
    if re.fullmatch(r"[0-9]{6}_[0-9]{4}", timestamp) is None:
        timestamp = datetime.now().strftime("%y%m%d_%H%M")
    stem = f"{timestamp}_reviewer_range_{base[:7]}_{head[:7]}"
    candidate = f"docs/plans/{stem}.md"
    suffix = 2
    while (root / candidate).exists():
        candidate = f"docs/plans/{stem}_{suffix}.md"
        suffix += 1
    return candidate


def _rerun_carrier(root: Path) -> dict[str, Any]:
    mode = os.environ.get("PLANVEYOR_REVIEW_RERUN_MODE", "").strip().lower()
    baseline = os.environ.get("PLANVEYOR_REVIEW_BASELINE_ARTIFACT", "").strip()
    prior_raw = os.environ.get("PLANVEYOR_REVIEW_PRIOR_ARTIFACTS", "").strip()
    if not any((mode, baseline, prior_raw)):
        return {"active": False, "mode": None, "baseline_artifact": None, "prior_artifacts": []}
    if mode not in {"incremental", "full"}:
        raise EngineError(
            "invalid_rerun_carrier",
            "ERROR: PLANVEYOR_REVIEW_RERUN_MODE must be `incremental` or `full` when explicit rerun carrier is used.",
        )

    def verified_path(value: str, label: str) -> str:
        pure = PurePosixPath(value)
        if (
            not value
            or pure.is_absolute()
            or ".." in pure.parts
            or not value.startswith("docs/")
            or pure.suffix != ".md"
        ):
            raise EngineError(
                "invalid_rerun_carrier",
                f"ERROR: {label} must be a repo-relative `docs/*.md` path, got: {value or '<empty>'}",
            )
        if not (root / value).exists():
            raise EngineError("invalid_rerun_carrier", f"ERROR: {label} does not exist: {value}")
        return value

    if baseline:
        baseline = verified_path(baseline, "PLANVEYOR_REVIEW_BASELINE_ARTIFACT")
    if mode == "incremental" and not baseline:
        raise EngineError(
            "invalid_rerun_carrier",
            "ERROR: PLANVEYOR_REVIEW_BASELINE_ARTIFACT is required when PLANVEYOR_REVIEW_RERUN_MODE=incremental.",
        )
    prior: list[str] = []
    if prior_raw:
        for raw in prior_raw.split("|"):
            value = raw.strip()
            if not value:
                raise EngineError(
                    "invalid_rerun_carrier",
                    "ERROR: PLANVEYOR_REVIEW_PRIOR_ARTIFACTS must be a `|`-delimited list without empty items.",
                )
            value = verified_path(value, "PLANVEYOR_REVIEW_PRIOR_ARTIFACTS item")
            if value not in prior:
                prior.append(value)
    if mode == "full" and not baseline and not prior:
        raise EngineError(
            "invalid_rerun_carrier",
            "ERROR: explicit rerun carrier is incomplete: `full` rerun needs PLANVEYOR_REVIEW_BASELINE_ARTIFACT or PLANVEYOR_REVIEW_PRIOR_ARTIFACTS.",
        )
    return {
        "active": True,
        "mode": mode,
        "baseline_artifact": baseline or None,
        "prior_artifacts": prior or ([baseline] if baseline else []),
    }


def _existing_plan(
    root: Path,
    *,
    base: str,
    head: str,
    exclude_docs: str,
    profile_id: str,
    host_family: str,
    rerun: Mapping[str, Any],
    reviewer_role_ref: str,
    review_scoping_playbook_ref: str,
    review_merge_playbook_ref: str,
) -> str | None:
    expected_rerun = {
        "active": bool(rerun.get("active")),
        "mode": rerun.get("mode"),
        "baseline_artifact": rerun.get("baseline_artifact"),
        "prior_artifacts": rerun.get("prior_artifacts") or [],
    }

    def first_backticked_value(line: str) -> str | None:
        match = re.search(r"`([^`]+)`", line)
        return match.group(1) if match else None

    def all_backticked_values(line: str) -> list[str]:
        return re.findall(r"`([^`]+)`", line)

    def parse_review_target(text: str) -> tuple[str, str, str] | None:
        match = re.search(
            r"- Review target: `RANGE=(?P<base>[0-9a-f]+)\.\.(?P<head>[0-9a-f]+) \(EXCLUDE_DOCS=(?P<exclude>[01])\)`",
            text,
        )
        if match is None:
            return None
        return match.group("base"), match.group("head"), match.group("exclude")

    def parse_review_host_family(text: str) -> str | None:
        section = re.search(r"(?ms)^## Review artifacts\n(?P<body>.*?)(?=^## |\Z)", text)
        if section is None:
            return None
        match = re.search(r"docs/(code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md", section.group("body"))
        return match.group(1) if match else None

    def parse_repo_profile(text: str) -> str:
        match = re.search(r"^- Repo profile: `([^`]+)`", text, re.MULTILINE)
        if match is None:
            return "" if profile_id == "planveyor" else profile_id
        return match.group(1)

    def has_expected_default_context_sources(text: str) -> bool:
        markers = list(re.finditer(r"(?m)^\*\*Context links \(source of truth\):\*\*$", text))
        if len(markers) != 1:
            return False
        after_context = text[markers[0].end() :]
        meta = re.search(r"(?m)^## Meta\b", after_context)
        if meta is None:
            return False
        context_lines = after_context[: meta.start()].splitlines()
        context_body = "\n".join(context_lines)
        expected_literals = (
            f"`{reviewer_role_ref}`",
            f"`{review_scoping_playbook_ref}`",
            f"`{review_merge_playbook_ref}`",
        )
        if any(context_body.count(literal) != 1 for literal in expected_literals):
            return False
        reviewer_lines = [line for line in context_lines if re.match(r"^\s*-\s*Reviewer role\b", line)]
        if reviewer_lines != [f"- Reviewer role: `{reviewer_role_ref}`"]:
            return False
        shared_lines = [line for line in context_lines if re.match(r"^\s*-\s*Shared playbooks\b", line)]
        if shared_lines != ["- Shared playbooks:"]:
            return False
        shared_index = context_lines.index("- Shared playbooks:")
        nested: list[str] = []
        for line in context_lines[shared_index + 1 :]:
            if re.match(r"^-\s", line):
                break
            if not line.strip():
                continue
            if re.match(r"^\s+-", line):
                nested.append(line)
                continue
            return False
        return nested == [
            f"  - `{review_scoping_playbook_ref}`",
            f"  - `{review_merge_playbook_ref}`",
        ]

    def parse_rerun_tuple(text: str) -> dict[str, object] | None:
        prior_line = re.search(r"^- Prior review / rerun artifacts: .*$", text, re.MULTILINE)
        mode_line = re.search(r"^- Rerun mode: .*$", text, re.MULTILINE)
        baseline_line = re.search(r"^- Baseline artifact: .*$", text, re.MULTILINE)
        if not (prior_line and mode_line and baseline_line):
            return None
        mode = first_backticked_value(mode_line.group(0)) or ""
        baseline_value = first_backticked_value(baseline_line.group(0)) or ""
        prior_values = all_backticked_values(prior_line.group(0))
        if mode == "N/A (first pass)":
            return {"active": False, "mode": None, "baseline_artifact": None, "prior_artifacts": []}
        if mode not in {"incremental", "full"}:
            return None
        if baseline_value in {"N/A (first pass)", "N/A (full rerun; explicit prior artifacts only)"}:
            baseline_value = ""
        if prior_values == ["N/A (first pass)"]:
            prior_values = []
        return {
            "active": True,
            "mode": mode,
            "baseline_artifact": baseline_value or None,
            "prior_artifacts": prior_values,
        }

    for path in sorted((root / "docs" / "plans").glob(f"*_reviewer_range_{base[:7]}_{head[:7]}*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if profile_id in {"default", "planveyor"} and not has_expected_default_context_sources(text):
            continue
        parsed_target = parse_review_target(text)
        if parsed_target != (base, head, exclude_docs):
            if not re.search(r'"schema_version"\s*:\s*"review_visual_lane_contract_ref\.v1"', text):
                continue
        if parse_review_host_family(text) != host_family:
            continue
        if parse_repo_profile(text) != profile_id:
            continue
        if parse_rerun_tuple(text) != expected_rerun:
            continue
        return path.relative_to(root).as_posix()
    return None


def _replace_or_upsert(text: str, heading: str, body: str, *, before: str | None = None) -> str:
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if before:
        before_pattern = re.compile(rf"(?m)^## {re.escape(before)}\n")
        if before_pattern.search(text):
            return before_pattern.sub(replacement + f"## {before}\n", text, count=1)
    return text.rstrip() + "\n\n" + replacement


def _append_policy_note(text: str, heading: str, note: str) -> str:
    pattern = re.compile(rf"(?ms)^(## {re.escape(heading)}\n)(.*?)(?=^## |\Z)")
    match = pattern.search(text)
    if match is None:
        raise EngineError("unlisted_review_range_semantic_render", f"plan:{heading}")
    body = match.group(2).rstrip()
    return text[: match.start()] + match.group(1) + body + "\n\n" + note.strip() + "\n\n" + text[match.end() :]


def _section_body(text: str, heading: str) -> str | None:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n\n?(.*?)(?=^## |\Z)", text)
    return None if match is None else match.group(1).strip()


def _section_next_heading(text: str, heading: str) -> str | None:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", text)
    if match is None:
        return None
    next_match = re.match(r"^## (?P<heading>.+?)\n", text[match.end() :])
    return None if next_match is None else str(next_match.group("heading"))


def _preserve_reused_metadata(rendered: str, existing: str, *, sections: Sequence[str]) -> str:
    """Keep creation facts stable when a selected tuple is rendered again."""

    source_date = re.search(r"(?m)^\*\*Date:\*\*.*$", existing)
    if source_date is not None:
        rendered = re.sub(r"(?m)^\*\*Date:\*\*.*$", source_date.group(0), rendered, count=1)
    for heading in sections:
        body = _section_body(existing, heading)
        if body is not None:
            rendered = _replace_or_upsert(rendered, heading, body)
    return rendered


def _restore_section_placement(text: str, *, heading: str, next_heading: str | None) -> str:
    """Keep a reusable generated section beside the same successor heading."""

    if next_heading is None or next_heading == heading:
        return text
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    section = pattern.search(text)
    if section is None:
        return text
    stripped = text[: section.start()] + text[section.end() :]
    anchor = re.search(rf"(?m)^## {re.escape(next_heading)}\n", stripped)
    if anchor is None:
        return text
    replacement = section.group(0).rstrip() + "\n\n"
    return stripped[: anchor.start()] + replacement + stripped[anchor.start() :]


def _run_renderer(source: str, args: Sequence[str], *, root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-", *args],
        input=source,
        text=True,
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise EngineError("renderer_failed", result.stderr.strip() or "review-range renderer exited nonzero")


def _context_for_request(root: Path):
    import contract_authority_context as authority

    expected = os.environ.get(authority.EXPECTED_CONTEXT_ENV, "")
    if expected:
        context = authority.validate_inherited_context(expected, root)
    else:
        context = authority.resolve_top_level_context(root)
    if context.project_root.resolve() != root.resolve():
        raise EngineError("context_project_root_mismatch")
    return context, authority


def _parse_policy(data: bytes) -> Mapping[str, Any]:
    policy = _strict_json(data, label="review_range_policy.v1")
    if set(policy) != _POLICY_KEYS or policy.get("schema_version") != "review_range_policy.v1":
        raise EngineError("invalid_policy_json", "field_set_or_schema")
    selectors = PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["selectors"]
    for name, expected in selectors.items():
        if policy.get(name) != expected:
            raise EngineError("invalid_policy_selector", name)
    prose = policy.get("section_prose")
    if type(prose) is not dict or set(prose) != set(_POLICY_PROSE_KEYS):
        raise EngineError("invalid_policy_json", "section_prose")
    if any(type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 8192 for value in prose.values()):
        raise EngineError("invalid_policy_json", "section_prose_value")
    return policy


def _local_input_row(input_id: str, spec: Mapping[str, Any]) -> dict[str, str]:
    return {
        "id": input_id,
        "reader": str(spec["reader"]),
        "contract_relative_path": str(spec["path"]),
        "content_source": "current_local_worktree",
    }


def _matching_engaged_consumer_identity(context: Any) -> bool:
    """Require an already-verified non-default marker/consumer identity pair."""

    marker = context.marker
    identity = context.behavior_identity
    return (
        marker is not None
        and type(identity) is str
        and identity != "default"
        and _CONSUMER_REPOSITORY_ID_RE.fullmatch(identity) is not None
        and marker.repository_id == identity
    )


def _engaged_inputs(context: Any, authority: Any) -> tuple[Mapping[str, Any], dict[str, str], list[dict[str, str]]]:
    if not _matching_engaged_consumer_identity(context):
        raise EngineError("repository_identity_mismatch")
    if context.runtime_pin is None or context.runtime_pin.runtime_api_version != REVIEW_RANGE_RUNTIME_API_VERSION:
        raise EngineError("review_range_runtime_api_mismatch")
    api_range = context.marker.required_runtime_api
    if api_range.minimum != REVIEW_RANGE_RUNTIME_API_VERSION or api_range.maximum != REVIEW_RANGE_RUNTIME_API_VERSION:
        raise EngineError("review_range_marker_api_mismatch")

    inputs = PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["inputs"]
    rows: list[dict[str, str]] = []

    policy_spec = inputs["policy_json"]
    policy = _parse_policy(
        authority.read_declared_bytes(context, str(policy_spec["path"]), purpose="review-range policy")
    )
    rows.append(_local_input_row("policy_json", policy_spec))

    plan_spec = inputs["plan_template"]
    plan_template = authority.read_declared_text(context, str(plan_spec["path"]), purpose="review-range plan template")
    rows.append(_local_input_row("plan_template", plan_spec))

    draft_spec = inputs["code_draft_template"]
    draft_template = authority.read_declared_text(context, str(draft_spec["path"]), purpose="review-range code-draft template")
    rows.append(_local_input_row("code_draft_template", draft_spec))

    reviewer_spec = inputs["reviewer_role_reference"]
    authority.require_declared_read(context, str(reviewer_spec["path"]), purpose="review-range reviewer reference")
    rows.append(_local_input_row("reviewer_role_reference", reviewer_spec))

    scoping_spec = inputs["review_scoping_playbook"]
    authority.read_declared_text(context, str(scoping_spec["path"]), purpose="review-range scoping playbook")
    rows.append(_local_input_row("review_scoping_playbook", scoping_spec))

    merge_spec = inputs["review_merge_playbook"]
    authority.read_declared_text(context, str(merge_spec["path"]), purpose="review-range merge playbook")
    rows.append(_local_input_row("review_merge_playbook", merge_spec))

    for input_id in ("plan_vocabulary_reference", "smoke_visual", "testing_runbook"):
        spec = inputs[input_id]
        authority.require_declared_read(context, str(spec["path"]), purpose=f"review-range {input_id}")
        rows.append(_local_input_row(input_id, spec))

    return policy, {"plan": plan_template, "draft": draft_template}, rows


def _legacy_templates() -> dict[str, str]:
    source_root = _source_root()
    paths = {
        "plan": source_root / "docs" / "plans" / "_template.md",
        "draft": source_root / "docs" / "code_drafts" / "_template.md",
    }
    try:
        return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    except OSError as exc:
        raise EngineError("missing_shared_template") from exc


def _semantic_receipt(
    *,
    context: Any,
    state: str,
    input_rows: Sequence[Mapping[str, str]],
    policy: Mapping[str, Any] | None,
    plan_ref: str,
    draft_ref: str,
    materialization: Mapping[str, Any],
) -> Mapping[str, Any]:
    runtime_pin: Mapping[str, Any]
    if context.runtime_pin is None:
        runtime_pin = {"state": "legacy_unpinned"}
    else:
        runtime_pin = {
            "runtime_api_version": context.runtime_pin.runtime_api_version,
            "runtime_root": str(context.runtime_pin.runtime_root),
            "sha256": context.runtime_pin.pin_sha256,
        }
    visual: Mapping[str, Any]
    if materialization.get("mode") == "external":
        visual = {
            "kind": "external_ref",
            "ref": str(materialization["support_ref"]),
            "sha256": str(materialization["support_sha256"]),
        }
    else:
        visual = {
            "kind": "inline_digest",
            "sha256": hashlib.sha256(str(materialization["markdown"]).encode("utf-8")).hexdigest(),
        }
    # ``legacy_rules`` is intentionally a set for membership semantics in the
    # frozen surface.  Its receipt projection must nevertheless be byte-stable
    # across interpreter hash seeds so repeat/reuse does not churn a plan.
    selected = sorted(str(rule) for rule in PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["legacy_rules"])
    if policy is not None:
        # The declared selectors have a meaningful fixed precedence, but two
        # selectors may name the same rule.  A receipt records rule IDs, not
        # selector occurrences, so preserve first occurrence while deduping.
        selected = list(dict.fromkeys(str(policy[name]) for name in ("corpus_rule", "visual_rule", "render_profile")))
    return {
        "schema_version": "review_range_semantic_provenance.v2",
        "source_engine_version": ENGINE_VERSION,
        "source_runtime_pin": runtime_pin,
        "context_state": state,
        "behavior_identity": context.behavior_identity,
        "marker_repository_id_or_not_applicable": (
            context.marker.repository_id if context.marker is not None else "not_applicable"
        ),
        "context_generation": context.generation_sha256,
        "semantic_surface_sha256": SEMANTIC_SURFACE_SHA256,
        "selected_rule_ids": selected,
        "inputs": list(input_rows),
        "outputs": [
            {"artifact": "plan", "section_or_path": plan_ref, "rule_ids": selected},
            {"artifact": "draft", "section_or_path": draft_ref, "rule_ids": selected},
        ],
        "visual_contract_ref_or_inline_digest": visual,
    }


def _render_and_publish(
    *,
    root: Path,
    context: Any,
    authority: Any,
    base: str,
    head: str,
    exclude_docs: str,
    force_new: str,
    timestamp: str | None,
    content_profile_id: str,
) -> str:
    state = context.state
    if state == "engaged" and exclude_docs not in {"0", "1"}:
        raise EngineError("invalid_engaged_exclude_docs")
    if force_new not in {"0", "1"}:
        raise EngineError("invalid_force_new")

    profile_id = context.behavior_identity if state == "engaged" else content_profile_id
    policy: Mapping[str, Any] | None = None
    input_rows: list[dict[str, str]] = []
    if state == "engaged":
        policy, templates, input_rows = _engaged_inputs(context, authority)
        reviewer_ref = "docs/roles/reviewer.md"
        scoping_ref = "docs/playbooks/review_scoping_plan.md"
        merge_ref = "docs/playbooks/review_merge_range.md"
    else:
        templates = _legacy_templates()
        root_references = _legacy_root_review_references(
            content_profile_id=content_profile_id,
        )
        reviewer_ref = root_references.reference_for("reviewer_role")
        scoping_ref = root_references.reference_for("review_scoping_playbook")
        merge_ref = root_references.reference_for("review_merge_range_playbook")

    # Everything above is read-only admission.  Do not make a temporary path,
    # publisher lock, or stdout payload before the complete finite surface has
    # accepted the request and current captured generation.
    range_stats = _range_stats(root, base, head)
    bundle_paths = _range_paths(root, base, head, exclude_docs)
    family = _host_family(bundle_paths)
    rerun = _rerun_carrier(root)
    plan_ref = None if force_new == "1" else _existing_plan(
        root,
        base=base,
        head=head,
        exclude_docs=exclude_docs,
        profile_id=profile_id,
        host_family=family,
        rerun=rerun,
        reviewer_role_ref=reviewer_ref,
        review_scoping_playbook_ref=scoping_ref,
        review_merge_playbook_ref=merge_ref,
    )
    plan_ref = plan_ref or _new_plan_ref(root, base, head, timestamp=timestamp)
    plan_ref = _safe_relative(plan_ref)
    draft_ref = _safe_relative(f"docs/code_drafts/{Path(plan_ref).stem}__code_draft.md")
    artifact_ref = _review_artifact(plan_ref, family)
    plan_path = root / plan_ref
    draft_path = root / draft_ref
    plan_existed = "1" if plan_path.is_file() else "0"
    draft_existed = draft_path.is_file()
    try:
        plan_source_text = plan_path.read_text(encoding="utf-8") if plan_existed == "1" else templates["plan"]
        draft_source_text = draft_path.read_text(encoding="utf-8") if draft_existed else templates["draft"]
        draft_visual_next_heading = (
            _section_next_heading(draft_source_text, "Review visual lane contract")
            if draft_existed
            else None
        )
    except OSError as exc:
        raise EngineError("artifact_source_read_failed") from exc

    import review_visual_lane_contract as visual
    changed_entries = visual.git_changed_entries(root, base, head)
    visual_payload = visual.discover_review_visual_lane(
        project_root=root,
        profile_id=profile_id,
        content_profile_id=content_profile_id,
        changed_entries=changed_entries,
        exclude_docs=exclude_docs == "1",
        review_basename=Path(artifact_ref).stem,
        plan_ref=plan_ref,
        context=context,
    )
    materialization = visual.prepare_materialized_contract(
        visual_payload,
        base=base,
        head=head,
        exclude_docs=exclude_docs,
        plan_ref=plan_ref,
        review_artifact_ref=artifact_ref,
    )
    if "visual_support_carrier" not in PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["render_destinations"]:
        raise EngineError("unlisted_review_range_semantic_render", "visual_support_carrier")

    # Recheck selector/runtime before staging; previously read bodies are not sealed.
    authority.validate_before_effect(context)
    with tempfile.TemporaryDirectory(prefix="planveyor-review-range-engine-") as temporary:
        temporary_root = Path(temporary)
        plan_source = temporary_root / "plan-template.md"
        draft_source = temporary_root / "draft-template.md"
        plan_stage = temporary_root / "plan-stage.md"
        draft_stage = temporary_root / "draft-stage.md"
        plan_source.write_text(plan_source_text, encoding="utf-8")
        draft_source.write_text(draft_source_text, encoding="utf-8")
        machine_authority_na = {
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        from plan_status_oracle import machine_authority_decision_sha256
        machine_authority_na["carrier_sha256"] = machine_authority_decision_sha256(
            {"schema_version": "machine_authority_decision.v1", **machine_authority_na}
        )
        materialization_json = json.dumps(materialization, ensure_ascii=False, separators=(",", ":"))
        _run_renderer(
            PLAN_RENDERER_SOURCE,
            (
                plan_ref, base, head, exclude_docs, profile_id, content_profile_id, artifact_ref,
                json.dumps(rerun, ensure_ascii=False, separators=(",", ":")), plan_existed,
                json.dumps(range_stats, ensure_ascii=False, separators=(",", ":")), materialization_json,
                str(plan_source), str(plan_stage), reviewer_ref, scoping_ref, merge_ref,
            ),
            root=root,
        )
        _run_renderer(
            DRAFT_RENDERER_SOURCE,
            (
                draft_ref, plan_ref, base, head, exclude_docs, profile_id, artifact_ref,
                json.dumps(rerun, ensure_ascii=False, separators=(",", ":")),
                json.dumps(range_stats, ensure_ascii=False, separators=(",", ":")), materialization_json,
                json.dumps(machine_authority_na, ensure_ascii=False, separators=(",", ":")),
                str(plan_stage), str(draft_source), str(draft_stage),
            ),
            root=root,
        )
        plan_text = plan_stage.read_text(encoding="utf-8")
        draft_text = draft_stage.read_text(encoding="utf-8")
        if plan_existed == "1":
            plan_text = _preserve_reused_metadata(
                plan_text,
                plan_source_text,
                sections=("Plan provenance / session context",),
            )
        if draft_existed:
            draft_text = _preserve_reused_metadata(
                draft_text,
                draft_source_text,
                sections=("Provenance / session context",),
            )
        if policy is not None:
            prose = policy["section_prose"]
            for key, heading in _POLICY_PROSE_KEYS.items():
                destination = f"plan:{heading}"
                if destination not in PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["render_destinations"]:
                    raise EngineError("unlisted_review_range_semantic_render", destination)
                plan_text = _append_policy_note(plan_text, heading, str(prose[key]))
        receipt = _semantic_receipt(
            context=context,
            state=state,
            input_rows=input_rows,
            policy=policy,
            plan_ref=plan_ref,
            draft_ref=draft_ref,
            materialization=materialization,
        )
        receipt_block = "```json\n" + json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n```"
        plan_text = _replace_or_upsert(
            plan_text, "Review-range semantic provenance", receipt_block,
            before="Visual Acceptance (browser, UI tasks)",
        )
        draft_text = _replace_or_upsert(
            draft_text, "Review-range semantic provenance", receipt_block,
            before="Targeted changes (by file)",
        )
        draft_text = _restore_section_placement(
            draft_text,
            heading="Review visual lane contract",
            next_heading=draft_visual_next_heading,
        )
        try:
            visual.publish_generated_scaffold(
                project_root=root,
                plan_ref=plan_ref,
                plan_text=plan_text,
                draft_ref=draft_ref,
                draft_text=draft_text,
                materialization=materialization,
                inject_failure_after=os.environ.get("PLANVEYOR_REVIEW_VISUAL_LANE_PUBLISH_FAIL_AFTER"),
                context=context,
            )
        except visual.PublicationError as exc:
            raise EngineError("publication_failed", str(exc)) from exc
    return plan_ref


def run(
    *,
    root_text: str,
    base_input: str,
    head_input: str,
    exclude_docs: str,
    force_new: str,
    timestamp: str | None = None,
    content_profile_id: str = "default",
) -> str:
    root = Path(root_text).resolve()
    if not root.is_dir():
        raise EngineError("invalid_project_root")
    context, authority = _context_for_request(root)
    effective_content_profile_id = content_profile_id.strip()
    if effective_content_profile_id not in _KNOWN_CONTENT_PROFILES:
        raise EngineError("invalid_content_profile_id", content_profile_id)
    if context.state != "engaged":
        _legacy_root_review_references(content_profile_id=effective_content_profile_id)
    base = _resolve_commit(root, base_input, label="BASE")
    head = _resolve_commit(root, head_input, label="HEAD")
    return _render_and_publish(
        root=root,
        context=context,
        authority=authority,
        base=base,
        head=head,
        exclude_docs=exclude_docs,
        force_new=force_new,
        timestamp=timestamp,
        content_profile_id=effective_content_profile_id,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--exclude-docs", required=True)
    parser.add_argument("--force-new", required=True)
    parser.add_argument("--timestamp")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=sorted(_KNOWN_CONTENT_PROFILES),
        help="Resolved content profile; default and planveyor use root-local sources.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan_ref = run(
            root_text=args.root,
            base_input=args.base,
            head_input=args.head,
            exclude_docs=args.exclude_docs,
            force_new=args.force_new,
            timestamp=args.timestamp,
            content_profile_id=args.content_profile_id,
        )
    except EngineError as exc:
        print(f"review-range-scaffold-engine: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - boundary avoids partial stdout.
        print(f"review-range-scaffold-engine: unexpected failure: {exc}", file=sys.stderr)
        return 2
    print(plan_ref)
    return 0


# The two frozen, source-owned renderer bodies are mechanically moved below.
# They retain the proven section transforms while this module owns admission,
# target reads, provenance, visual publication, and public path-only ABI.
PLAN_RENDERER_SOURCE = r'''from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
import time

plan_path, base, head, exclude_docs, profile_id, content_profile_id, review_artifact, rerun_carrier_json, plan_existed, range_stats_json, visual_lane_materialization_json, plan_source_path, plan_output_path, reviewer_role_ref, review_scoping_playbook_ref, review_merge_playbook_ref = sys.argv[1:17]
rerun_carrier = json.loads(rerun_carrier_json)
range_stats = json.loads(range_stats_json)
visual_lane_materialization = json.loads(visual_lane_materialization_json)
visual_lane_contract = visual_lane_materialization["contract"]
visual_lane_contract_markdown = str(visual_lane_materialization["markdown"])
rerun_active = bool(rerun_carrier.get("active"))
rerun_mode = rerun_carrier.get("mode")
baseline_artifact = rerun_carrier.get("baseline_artifact")
prior_artifacts = rerun_carrier.get("prior_artifacts") or []

ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
title = f"# Plan: Reviewer — merge-range {base[:7]}..{head[:7]} (review-only)"
plan_stem = Path(plan_path).stem
draft = f"docs/code_drafts/{plan_stem}__code_draft.md"
range_stats_command = f"zsh -lc 'source scripts/planveyor.zsh && planveyor_merge_range_stats_json {base} {head}'"
range_stats_inline = (
    f"`{range_stats_command}` -> "
    f"`total_commits={range_stats['total_commits']}`, "
    f"`first_parent_commits={range_stats['first_parent_commits']}`, "
    f"`changed_files={range_stats['changed_files']}`, "
    f"`diffstat_summary={range_stats['diffstat_summary']}`"
)


def _read_last_non_comment_line(path: Path) -> str:
    if not path.exists():
        return ""
    value = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value = line
    return value


def _read_kv_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _n_a(reason: str) -> str:
    return f"N/A (why={reason})"


def _unknown(reason: str) -> str:
    return f"unknown (why={reason})"


def _normalize_session_key(raw: str) -> str:
    return raw.strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_helper_script() -> Path | None:
    candidates: list[Path] = []
    tooling_root = os.environ.get("PLANVEYOR_ROOT", "").strip()
    if tooling_root:
        candidates.append(Path(tooling_root).expanduser() / "scripts" / "codex_session_context.py")
    candidates.append(Path.cwd() / "scripts" / "codex_session_context.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _map_launch_surface(run_receipt: dict[str, str]) -> str:
    pipeline_mode = run_receipt.get("pipeline_mode", "")
    launch_surface = run_receipt.get("launch_surface", "")
    if pipeline_mode == "manager_custom_pipeline":
        return "manager-custom-pipeline"
    if pipeline_mode == "collab" or launch_surface == "collab_subagent":
        return "manager-collab"
    if launch_surface == "codex_desktop":
        return "codex-desktop"
    if launch_surface in {"codex_cli", "codex_exec"}:
        return "codex-cli"
    return _unknown("no env, wrapper receipt, or session stats origin identified the launch surface")


def _collect_provenance_context(*, relation: str) -> dict[str, str]:
    helper_script = _resolve_helper_script()
    session_key = _normalize_session_key(os.environ.get("ROLE", ""))
    authority_context = sys.modules.get("contract_authority_context")
    child_context = authority_context.context_for_reader(Path.cwd()) if authority_context is not None else None
    engaged_child = child_context is not None and child_context.state == "engaged"
    if engaged_child:
        helper_script = child_context.runtime_pin.runtime_root / "scripts" / "codex_session_context.py"
    if helper_script is not None:
        cmd = [
            sys.executable,
            str(helper_script),
            "--root",
            str(Path.cwd()),
            "--plan-path",
            plan_path,
            "--relation",
            relation,
            "--format",
            "json",
        ]
        if session_key:
            cmd.extend(["--session-key", session_key])
        child_env = os.environ.copy()
        if engaged_child:
            from contract_authority_children import python_entry_argv

            cmd = python_entry_argv(child_context, helper_script, cmd[2:])
            child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = authority_context.context_to_json(child_context)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=child_env,
        )
        if engaged_child and result.returncode != 0:
            print(result.stderr.strip() or "Authority provenance child failed", file=sys.stderr)
            raise SystemExit(result.returncode or 2)
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                return {
                    "relation": str(payload.get("relation", relation)),
                    "thread_id": str(payload.get("thread_id", _n_a("helper returned no thread id"))),
                    "parent_thread_id": str(payload.get("parent_thread_id", _n_a("helper returned no parent thread id"))),
                    "session_sid": str(payload.get("session_sid", _n_a("helper returned no session sid"))),
                    "launch_surface": str(payload.get("launch_surface", _unknown("helper returned no launch-surface value"))),
                    "captured_from": str(payload.get("captured_from", "manual-owner")),
                    "captured_at": str(payload.get("captured_at", datetime.utcnow().replace(microsecond=0).isoformat() + "Z")),
                }

    run_receipt_path = (
        Path(os.environ["RUN_RECEIPT_PATH"]).expanduser().resolve()
        if os.environ.get("RUN_RECEIPT_PATH")
        else None
    )
    run_receipt = _read_kv_file(run_receipt_path)
    thread_id = os.environ.get("CODEX_THREAD_ID", "").strip() or run_receipt.get("thread_id", "").strip()
    parent_thread_id = os.environ.get("CODEX_PARENT_THREAD_ID", "").strip() or run_receipt.get("parent_thread_id", "").strip()
    session_sid = ""
    if session_key:
        session_sid = _read_last_non_comment_line(Path.cwd() / f".planveyor.session.{session_key}")
    captured_from = "manual-owner"
    if thread_id:
        captured_from = "env"
    elif session_sid or run_receipt:
        captured_from = "wrapper-session-file"

    return {
        "relation": relation,
        "thread_id": thread_id or _n_a("CODEX_THREAD_ID and wrapper receipts did not expose a live thread id"),
        "parent_thread_id": parent_thread_id or _n_a("not exposed by env, wrapper receipts, or session stats"),
        "session_sid": session_sid or _n_a("session key was not provided or .planveyor.session.<role> is missing"),
        "launch_surface": _map_launch_surface(run_receipt),
        "captured_from": captured_from,
        "captured_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }


def _render_plan_provenance(context: dict[str, str]) -> str:
    return "\n".join(
        [
            f"- Relation: `{context['relation']}`",
            f"- Thread ID: `{context['thread_id']}`",
            f"- Parent thread ID: `{context['parent_thread_id']}`",
            f"- Session SID: `{context['session_sid']}`",
            f"- Launch surface: `{context['launch_surface']}`",
            f"- Captured from: `{context['captured_from']}`",
            f"- Captured at: `{context['captured_at']}`",
        ]
    )


def git_changed_paths(range_base: str, range_head: str, *, exclude_docs_flag: bool) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{range_base}..{range_head}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if exclude_docs_flag:
        paths = [path for path in paths if not path.startswith("docs/")]
    return paths


def git_changed_path_statuses(range_base: str, range_head: str, *, exclude_docs_flag: bool) -> list[dict[str, object]]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-status", "-M", f"{range_base}..{range_head}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    entries: list[dict[str, object]] = []
    for raw_line in proc.stdout.splitlines():
        parts = [part for part in raw_line.split("\t") if part]
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        if exclude_docs_flag and path.startswith("docs/"):
            continue
        entries.append({"status": status, "path": path, "deleted": status.startswith("D")})
    return entries


def _stable_paths(paths: list[str]) -> list[str]:
    return sorted(dict.fromkeys(path for path in paths if path.strip()))


def _format_path_list(paths: list[str]) -> str:
    return ", ".join(f"`{path}`" for path in _stable_paths(paths))


def _is_doc_path(path: str) -> bool:
    return path.startswith("docs/") or Path(path).suffix.lower() in {".md", ".mdx", ".rst"}


def _is_process_doc_path(path: str) -> bool:
    return path.startswith(
        (
            "docs/plans/",
            "docs/code_drafts/",
            "docs/code_reviews/",
            "docs/doc_reviews/",
            "docs/followups/",
            "docs/playbooks/",
            "docs/tools/",
            "docs/roles/",
            "docs/process_improvements/",
        )
    )


def _is_tooling_or_process_path(path: str) -> bool:
    return path.startswith(("scripts/", ".github/")) or _is_process_doc_path(path)


def _is_sync_doc_target(path: str) -> bool:
    if not _is_doc_path(path):
        return False
    return not path.startswith(("docs/code_drafts/", "docs/code_reviews/", "docs/doc_reviews/"))


SHARED_HELPER_DEPENDENT_INVENTORY: dict[str, tuple[str, ...]] = {
    "scripts/planveyor/role_runtime.zsh": (
        "scripts/test_planveyor_init_capture.py",
        "scripts/test_planveyor_trace_extractor.py",
        "scripts/test_planveyor_bare_entrypoints.py",
        "scripts/test_planveyor_router_merge_boundary.py",
    ),
}


def render_shared_helper_dependent_inventory(target_paths: list[str]) -> str:
    fragments: list[str] = []
    target_set = set(target_paths)
    for target_path in sorted(target_set.intersection(SHARED_HELPER_DEPENDENT_INVENTORY)):
        dependent_paths = ", ".join(
            f"`{dependent_path}`"
            for dependent_path in SHARED_HELPER_DEPENDENT_INVENTORY[target_path]
        )
        fragments.append(
            f"required mapped run-to-confirm inventory for `{target_path}` = {dependent_paths}"
        )
    if not fragments:
        return ""
    return "; " + "; ".join(fragments)


def render_documentation_impact(
    target_paths: list[str],
    deleted_paths: list[str],
    *,
    plan_path: str,
    draft_path: str,
    review_artifact: str,
    range_base: str,
    range_head: str,
    exclude_docs: str,
) -> str:
    live_targets = _stable_paths(target_paths)
    sync_doc_targets = [path for path in live_targets if _is_sync_doc_target(path)]
    if sync_doc_targets:
        sync_doc_line = _format_path_list(sync_doc_targets)
    elif live_targets and all(_is_tooling_or_process_path(path) for path in live_targets):
        sync_doc_line = "`N/A (why=process/tooling-only reviewed range; no product documentation target inferred from exact target metadata)`"
    else:
        sync_doc_line = "`N/A (why=no documentation target in exact reviewed target metadata)`"
    deleted_line = _format_path_list(deleted_paths) if deleted_paths else "`N/A (why=no tracked deleted paths in exact target metadata)`"
    live_targets_line = _format_path_list(live_targets) if live_targets else "`N/A (why=no live targets in exact target metadata)`"
    generated_carriers = _format_path_list([plan_path, draft_path, review_artifact])
    return f"""- Source docs used: exact reviewed target metadata from `RANGE={range_base}..{range_head}` / generated `code_draft_meta.targets`; no prose-only docs-impact inference.
- Exact target metadata: live `code_draft_meta.targets` = {live_targets_line}; deleted `code_draft_meta.deleted_paths` = {deleted_line}
- Synchronous doc/registry targets: {sync_doc_line}
- Generated docs targets / derived carriers: {generated_carriers}
- Post-merge canon updates: `N/A (why=review-only scaffold reports target-derived docs impact; Reviewer/Architect triage owns canon promotion decisions)`
- Deferred documentation follow-ups: `N/A (why=review-only scaffold does not create docs follow-ups during init; Reviewer/Architect triage owns follow-up routing)`
- Provenance refs: `code_draft_meta.targets` source = exact live filtered carrier list for `RANGE={range_base}..{range_head}` with `EXCLUDE_DOCS={exclude_docs}`; `code_draft_meta.deleted_paths` = {deleted_line}; review artifact = `{review_artifact}`"""


def looks_runtime_ui(path: str) -> bool:
    if path.startswith("docs/"):
        return False
    parts = Path(path).parts
    if "templates" in parts or "static" in parts:
        return True
    suffix = Path(path).suffix.lower()
    return suffix in {".html", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx"}


def replace_section(text: str, heading: str, body: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    return text


def upsert_section(text: str, heading: str, body: str, *, before_heading: str | None = None) -> str:
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if before_heading:
        before_pattern = re.compile(rf"(?m)^## {re.escape(before_heading)}\n")
        if before_pattern.search(text):
            return before_pattern.sub(replacement + f"## {before_heading}\n", text, count=1)
    return text.rstrip() + "\n\n" + replacement


def render_visual_lane_contract(payload: dict[str, object]) -> str:
    del payload
    return visual_lane_contract_markdown


def scrub_ordinary_plan_meta(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_json = False
    json_buf: list[str] = []

    def rewrite_json_block(block: str) -> str:
        try:
            parsed = json.loads(block)
        except Exception:
            return block
        meta = parsed.get("plan_meta")
        if not isinstance(meta, dict):
            return block
        if meta.get("wave_family") is None and meta.get("phase_overlay") is None:
            for key in ("promoted_from", "queue_activation", "scope_expansion"):
                if meta.get(key) is None:
                    meta.pop(key, None)
        meta["machine_authority_decision"] = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        parsed["plan_meta"] = meta
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    for line in lines:
        if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
            in_json = True
            json_buf = []
            out.append(line)
            continue
        if in_json and re.match(r"^\s*```\s*$", line):
            out.append(rewrite_json_block("\n".join(json_buf)))
            out.append(line)
            in_json = False
            json_buf = []
            continue
        if in_json:
            json_buf.append(line)
            continue
        out.append(line)
    if in_json:
        out.extend(json_buf)
    return "\n".join(out) + "\n"


exclude_docs_flag = exclude_docs == "1"
changed_paths = git_changed_paths(base, head, exclude_docs_flag=exclude_docs_flag)
changed_entries = git_changed_path_statuses(base, head, exclude_docs_flag=exclude_docs_flag)
live_target_paths = [str(entry["path"]) for entry in changed_entries if not bool(entry["deleted"])]
deleted_target_paths = [str(entry["path"]) for entry in changed_entries if bool(entry["deleted"])]
if not live_target_paths and changed_paths:
    live_target_paths = changed_paths
target_paths_for_docs_impact = live_target_paths or [plan_path]
has_runtime_ui = any(looks_runtime_ui(path) for path in changed_paths)
has_non_doc_paths = any(not path.startswith("docs/") for path in changed_paths)
docs_only = bool(changed_paths) and not has_non_doc_paths
contract_visual_lane = visual_lane_contract.get("availability_state") == "available"
visual_lane_needs_repair = (
    has_runtime_ui
    and visual_lane_contract.get("availability_state") in {"missing", "malformed", "ambiguous"}
)
source_refs_display = ""
if contract_visual_lane:
    source_refs_display = ", ".join(f"`{ref}`" for ref in visual_lane_contract["source_refs"])
    modes_display = ", ".join(f"`{mode}`" for mode in visual_lane_contract["mandatory_modes"])
    visual_summary = (
        "machine-backed runtime-UI visual lane with independent mechanical comparator and complete-index "
        f"human review for modes {modes_display} (sources: {source_refs_display})"
    )
else:
    if visual_lane_needs_repair:
        visual_summary = (
            "technical visual-lane gap requiring Architect triage: "
            f"`availability_state={visual_lane_contract.get('availability_state')}`; "
            f"reason=`{visual_lane_contract.get('reason')}`"
        )
    elif has_runtime_ui:
        visual_summary = (
            "`N/A (why=no declared applicable visual carrier for the current legacy range; "
            "the shared scaffold must not invent browser defaults)`"
        )
    elif docs_only:
        visual_summary = "`N/A (why: docs-only range; runtime UI gate is not implied by changed paths)`"
    else:
        visual_summary = "`N/A (why: no runtime UI paths detected in the current range)`"

if contract_visual_lane:
    visual_gate_summary = (
        "materializes separate exact comparator and human-perceptual commands, complete-index inspection, "
        "mandatory modes and current-review durable asset root"
    )
    hook_proof_lane = "materialized from the single validated `review_visual_lane_contract.v1` payload"
    runtime_proof_lane = (
        "run the exact comparator command and each exact human command in `## Review visual lane contract`, "
        "inspect every indexed PNG, then cite per-mode current-review-owned durable assets"
    )
else:
    if visual_lane_needs_repair:
        visual_gate_summary = "materializes a non-available technical gap that blocks Reviewer-ready use and routes to Architect"
        hook_proof_lane = "materialized as an explicit technical gap instead of naked `N/A`"
        runtime_proof_lane = "blocked pending Architect repair of the repo-backed visual lane contract"
    else:
        visual_gate_summary = (
            "stays explicit `N/A (why)` because the current diff/profile does not support "
            "a truthful declared visual proof lane"
        )
        hook_proof_lane = "left explicit as `N/A (why)` instead of fake browser defaults"
        runtime_proof_lane = "`N/A (why: no truthful declared visual proof lane was auto-enabled for this range/profile)`"

range_diff_command = f"git diff -U3 {base}..{head}"
if exclude_docs == "1":
    range_diff_command = f"{range_diff_command} -- . ':(exclude)docs'"
review_target_literal = f"RANGE={base}..{head} (EXCLUDE_DOCS={exclude_docs})"
review_spec_literal = plan_path

if rerun_active:
    prior_artifacts_display = ", ".join(f"`{artifact}`" for artifact in prior_artifacts)
    prior_review_context_line = f"- Prior review / rerun artifacts: {prior_artifacts_display}"
    rerun_mode_line = f"- Rerun mode: `{rerun_mode}`"
    if baseline_artifact:
        baseline_artifact_line = f"- Baseline artifact: `{baseline_artifact}`"
    else:
        baseline_artifact_line = "- Baseline artifact: `N/A (full rerun; explicit prior artifacts only)`"
    rerun_scope_line = (
        f"- Rerun scope: `current blocker-fix pass for RANGE={base}..{head}; "
        "exact trusted unaffected surfaces / reused evidence belong in the review artifact`"
    )
    rerun_problem_line = (
        "4. Текущий pass уже является blocker-fix rerun, поэтому scaffold обязан materialize-ить "
        "`Prior review / rerun artifacts`, `Rerun mode` и `Baseline artifact` из explicit current-flow "
        "carrier вместо ложного `first pass`."
    )
    rerun_solution_line = (
        "5. Если rerun carrier уже передан на init surface, scaffold materialize-ит ту же lineage "
        "в generated plan и generated code draft без hidden git-history inference."
    )
    rerun_changes_block = f"""{rerun_mode_line}
{baseline_artifact_line}
{rerun_scope_line}"""
else:
    prior_review_context_line = "- Prior review / rerun artifacts: `N/A (first pass)`"
    rerun_mode_line = "- Rerun mode: `N/A (first pass)`"
    baseline_artifact_line = "- Baseline artifact: `N/A (first pass)`"
    rerun_scope_line = ""
    rerun_problem_line = ""
    rerun_solution_line = ""
    rerun_changes_block = f"""{rerun_mode_line}
{baseline_artifact_line}"""

provenance_relation = "continued-here" if plan_existed == "1" else "created-here"
plan_provenance = _render_plan_provenance(_collect_provenance_context(relation=provenance_relation))
documentation_impact = render_documentation_impact(
    target_paths_for_docs_impact,
    deleted_target_paths,
    plan_path=plan_path,
    draft_path=draft,
    review_artifact=review_artifact,
    range_base=base,
    range_head=head,
    exclude_docs=exclude_docs,
)
shared_helper_dependent_inventory_note = render_shared_helper_dependent_inventory(live_target_paths)
retrieval_telemetry_receipt = "- used_for_decision: `false`\n- no_op_reason: `not_used_for_decision`"

context_links = f"""**Context links (source of truth):**
- Reviewer role: `{reviewer_role_ref}`
- Shared playbooks:
  - `{review_scoping_playbook_ref}`
  - `{review_merge_playbook_ref}`
- Wrapper/materializer: `scripts/planveyor.zsh`
- Expected review artifact: `{review_artifact}`
- Review artifact machine carriers:
  - `**Target:** {review_target_literal}`
  - `**Spec:** {review_spec_literal}`
- Code draft(s): `{draft}`
{prior_review_context_line}
"""

problem = f"""1. Выполнить review-only merge-range review для `RANGE={base}..{head}` и зафиксировать verdict в `{review_artifact}`.
2. Не тратить первый reviewer pass на ручную materialization почти template-only scaffold: этот plan уже должен честно materialize-ить `Problem / Solution / Scope / Tests / Commands / Review artifacts`.
3. Держать visual/runtime lane truth-based: {visual_summary}.
4. Держать range stats helper-backed: {range_stats_inline}.
{rerun_problem_line}"""

understanding = f"""Нужно проверить merge-range `RANGE={base}..{head}` как отдельный review-only flow и записать результат в `{review_artifact}`.
Этот plan не является местом для product/runtime fixes: любые найденные blockers уходят в отдельный dev-plan после Architect triage.
Generated scaffold уже должен дать Reviewer рабочий контракт: target/spec carriers, scope, commands, stats и честную visual/runtime lane без template placeholders.
Owner-решений на старте не требуется; route идёт через Reviewer intake и затем Architect triage."""

solution = f"""1. Пройти merge-range review как bounded review-only flow: mechanical checks, diff inspection и review artifact без product-code правок внутри этого plan.
2. Держать source-of-truth явно в паре `Review target` + `Review artifacts`, а в итоговом review artifact materialize-ить machine carriers `**Target:** {review_target_literal}` и `**Spec:** {review_spec_literal}`, чтобы helpers не восстанавливали range/spec contract по памяти.
3. Держать source-of-truth для статистики диапазона в `planveyor_merge_range_stats_json`: artifacts копируют labels `total_commits`, `first_parent_commits`, `changed_files`, `diffstat_summary`, а не пересчитывают counts в prose.
4. Если range действительно затрагивает runtime UI, materialize-ить truthful lane только из accepted declared `review_visual_lane_contract.v1`; без такого carrier оставлять explicit `N/A (why)`.
5. Любые реальные продуктовые фиксы, canon rewrites или repo-profile-specific runtime lanes выносить в отдельный follow-up dev-plan / profile override, а не маскировать внутри review-only scaffold.
{rerun_solution_line}"""

decisions = f"""❌ Оставлять generated review-only plan почти template-only и добивать `Problem / Scope / Commands / Review artifacts` вручную на первом reviewer pass
✅ Materialize-ить bounded review contract сразу из `RANGE={base}..{head}` и shared reviewer flow
Компромиссы: scaffold остаётся generic, но перестаёт быть пустой болванкой.

❌ Включать visual/browser lane по basename, profile name или generic login/path defaults, когда accepted declared carrier отсутствует
✅ Активировать visual lane только из accepted declared `review_visual_lane_contract.v1`; во всех остальных случаях оставлять explicit `N/A (why)`
Компромиссы: shared scaffold не угадывает runtime proof, зато не публикует выдуманные команды или credentials.

❌ Смешивать review-only scaffold и будущие продуктовые фиксы в одном артефакте
✅ Держать этот plan strictly review-only: verdict/evidence здесь, любые fixes — отдельным dev-plan
Компромиссы: больше явных follow-up решений после triage, но меньше process drift.

### UI playbooks (micro-block; required for UI tasks)
- Playbooks: `N/A (why=review-only merge-range scaffold; exact dev-plan micro-block, если нужен, lives in affected implementation plans)`
- Playbook fields: `N/A (why=review-only merge-range scaffold does not invent implementation-specific UI playbook fields)`"""

scope = f"""- Review-only inspection диапазона `RANGE={base}..{head}`.
- Mechanical checks, diff inspection и materialized review artifact path `{review_artifact}`.
- Helper-backed range stats readback: {range_stats_inline}.
- Truthful visual/runtime lane only when the current diff/profile actually supports it."""

out_of_scope = """- Любые product/runtime fixes внутри этого plan.
- Тихий canon rewrite или repo-profile-specific override “по пути”, если он не materialize-ится отдельным bounded follow-up.
- Fake browser/login defaults там, где shared scaffold не может честно назвать proof lane."""

followups = """- Если review найдёт S1/S2, архитектурный triage заводит отдельный dev-plan; этот review-only plan не превращается в fix plan."""

close_out_routing = f"""- Roadmap/queue sync: `N/A (review-only range scaffold does not update a separate roadmap/queue at init time)`
- Follow-up sync: if `{review_artifact}` lands with S1/S2, Architect triage creates a separate dev-plan; otherwise the current review-only flow closes as-is
- Next bounded slice: Architect triage of `{review_artifact}`
- Terminal outcome: no (this scaffold still hands off through Reviewer -> Architect triage before terminal closeout)"""

business_decomposition_framing = "`N/A (why=review-only range scaffold; not business decomposition)`"

child_plan_map = """| Queue order | Plan | Purpose | Input | Output | Consumer | Depends on | Dependency type | Acceptance/proof lane | Independent-stop reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `N/A` | `N/A (why=not a decomposition wave)` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` |"""

decomposition_quality_gate = """- Solvability: `N/A (why=not a decomposition wave)`
- Completeness: `N/A (why=not a decomposition wave)`
- Non-redundancy: `N/A (why=not a decomposition wave)`
- Mutable surface / runtime isolation: `N/A (why=not a decomposition wave)`
- Recomposition / integration owner: `N/A (why=not a decomposition wave)`"""

mechanism_coverage = "- `N/A (why=review-only range scaffold; not a decomposition umbrella)`"

risks = f"""- Если changed paths не дают accepted declared visual carrier, scaffold обязан сохранить это как explicit `N/A (why)`, а не подменять guess-логикой.
- Исторический review artifact сам по себе не считается live proof lane: rerun context и reused evidence materialize-ятся только когда они действительно есть для `RANGE={base}..{head}`."""

changes = f"""- Review target: `{review_target_literal}`
- Review artifact machine carriers (must be copied literally into `{review_artifact}` before final status):
  - `**Target:** {review_target_literal}`
  - `**Spec:** {review_spec_literal}`
- Range stats (helper-backed): {range_stats_inline}
{rerun_changes_block}
- Data/schema (migrations if used): `N/A (why=review-only scaffold does not prescribe product-layer edits)`
- Logic/modules: `N/A (why=review-only scaffold does not prescribe product-layer edits)`
- Interfaces (API/CLI/UI): `N/A (why=review-only scaffold does not prescribe product-layer edits)`
- Config (keys/defaults): `N/A (why=review-only scaffold does not prescribe product-layer edits)`
- Docs/registry:
  - Expected review artifact: `{review_artifact}`
  - Visual/default lane: {visual_summary}"""

rollout_packet_handoff = """- Role: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`
- Packet path: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`
- Target repo: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`
- Suggested target plan slug: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`
- Queue after import: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`"""

small_slice_classifier = """- Requested profile: `N/A (why=this scaffold does not request reduced same-session conveyor classification)`
- Expected bundle family: `N/A (why=this scaffold does not request reduced same-session conveyor classification)`
- Helper validation: `N/A (why=this scaffold does not request reduced same-session conveyor classification)`
- Drift behavior: `N/A (why=this scaffold does not request reduced same-session conveyor classification)`"""

execution_queue = "- `N/A (why=this review-only range scaffold does not materialize a queue carrier)`"
queue_close_out = "- `N/A (why=this review-only range scaffold does not materialize a queue carrier)`"

reviewability_primary_lane = (
    f"`mechanical review entrypoint`: `python3 ${{PLANVEYOR_ROOT:-$HOME/planveyor}}/scripts/plan_lint.py {plan_path}`, "
    f"`{range_stats_command}`, `git log --oneline --first-parent --merges {base}..{head}`, `git diff --check {base}..{head}`, "
    f"`rg -n \"^<<<<<<< |^======= |^>>>>>>> \" .`, `{range_diff_command}`"
)

if contract_visual_lane:
    reviewability_proof_path_class = "`generated review-only scaffold + structural diff inspection + machine-backed two-claim visual lane`"
    reviewability_non_primary_lane = (
        "`mechanical comparator + human perceptual lane`: exact commands and outputs are materialized in "
        "`## Review visual lane contract`"
    )
    reviewability_helper_support = (
        f"`{visual_lane_contract['comparator_command']}` plus per-mode commands from "
        f"`human_commands_by_mode`; source files = {source_refs_display}"
    )
    reviewability_seed_discovery = (
        "run exact materialized commands; inspect every PNG linked by each `human_index_paths_by_mode` value "
        "before recording `design_verdict`"
    )
    reviewability_dependent_inventory = (
        f"generated plan `{plan_path}`, generated code draft `{draft}`, review artifact `{review_artifact}`, "
        f"and source carriers {source_refs_display}{shared_helper_dependent_inventory_note}"
    )
else:
    reviewability_proof_path_class = "`generated review-only scaffold + structural diff inspection`"
    reviewability_non_primary_lane = (
        "`N/A (why=no truthful declared visual contextual lane auto-enabled for this range/profile)`"
    )
    reviewability_helper_support = (
        "`N/A (why=no helper family required)`; support files = `scripts/planveyor.zsh`, "
        f"`{review_merge_playbook_ref}`"
    )
    reviewability_seed_discovery = (
        "`N/A (why=no declared runtime lane auto-enabled for this range/profile)`"
    )
    reviewability_dependent_inventory = (
        f"generated plan `{plan_path}`, generated code draft `{draft}`, and review artifact `{review_artifact}`"
        f"{shared_helper_dependent_inventory_note}"
    )

reviewability_reroute_rule = (
    f"if review mechanics fail or the materialized contextual lane cannot be justified from repo-backed sources, "
    f"record the gap in `{review_artifact}` and route to a bounded follow-up dev-plan instead of inventing fallback login/path defaults"
)

reviewability_receipt = f"""- `proof-path class`: {reviewability_proof_path_class}
- `mandatory primary lane`: {reviewability_primary_lane}
- `mandatory non-primary carrier / contextual lane`: {reviewability_non_primary_lane}
- `exact helper path + support files`: {reviewability_helper_support}
- `dependent tests / dependent docs / known consumer paths`: {reviewability_dependent_inventory}
- `preconditions / seed-discovery`: {reviewability_seed_discovery}
- `reroute rule`: {reviewability_reroute_rule}
- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`"""

acceptance = f"""### Review-only contract checklist
- [ ] `Review target` и expected review artifact path fixed literally in the plan (`RANGE={base}..{head}`, `{review_artifact}`)
- [ ] Final review artifact materializes machine carriers `**Target:** {review_target_literal}` and `**Spec:** {review_spec_literal}` before `**Status:**`
- [ ] `## Problem` / `## Solution` / `## Scope` / `## Tests` / `## Commands` materialized enough for Reviewer intake; no template-only placeholders on the critical path
- [ ] Этот plan остаётся `review-only`: product/code fixes route to a separate dev-plan instead of this artifact
- [ ] `## Visual Acceptance` truthfully {visual_gate_summary}
- [ ] `## Commands` stay bounded to merge-range review mechanics and do not assume hidden repo-local helper state

### UI contract checklist
- [ ] `N/A (why=review-only range scaffold; implementation-specific checklist remains in affected dev plans)`"""

if contract_visual_lane:
    human_command_lines = "\n".join(
        f"- `{mode}`: `{visual_lane_contract['human_commands_by_mode'][mode]}` -> "
        f"index `{visual_lane_contract['human_index_paths_by_mode'][mode]}`"
        for mode in visual_lane_contract["mandatory_modes"]
    )
    modes_literal = " + ".join(visual_lane_contract["mandatory_modes"])
    visual_acceptance = f"""### Visual gate (S1)
- Comparator and human-perceptual proof are independent mandatory claims; either red/missing claim is **S1 Blocker**.
- Baseline update/generation is not acceptance (`baseline_update_allowed=false`).

### Visual env (обязательно для UI-задач)
- Modes to test: `{modes_literal}`
- Visual evidence: `{visual_lane_contract['durable_review_asset_root']}...`

### How to run (Reviewer)
- Comparator: `{visual_lane_contract['comparator_command']}`
{human_command_lines}
- Open every PNG from every materialized Markdown index before recording `design_verdict=no_findings|findings`.

### Visual checks (screenshots required for UI tasks)
- `comparator_claim=mechanical` must pass independently.
- `capture_status=complete` proves capture completeness only; complete-index inspection plus `design_verdict` proves perception.
- Copy/cite at least one non-empty regular non-symlink asset per mandatory mode under `{visual_lane_contract['durable_review_asset_root']}`.
- `.tmp/**`, historical and other-review assets are contextual only and cannot close the current review.

### Visual regression scenarios (docs/smoke_visual.md)
- Source scenarios: {source_refs_display}
- Run only the literal commands from `## Review visual lane contract`; do not replace comparator acceptance with baseline generation.

### Perf checks (optional; recommended for perf tasks)
- `N/A (why: enable only if the range or linked plan artifacts make perf claims)`"""
else:
    visual_acceptance = visual_summary

tests = f"""### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)
- `Invariant #1: review-only range scaffold starts truthful for RANGE={base}..{head}`
  - `Risky touchpoints/surfaces:` generated plan `{plan_path}`, generated code draft `{draft}`, expected review artifact `{review_artifact}`
  - `Hook/test proof:` inspect the generated contract after `planveyor_review_range_init()` and confirm that `Problem / Scope / Commands / Review artifacts` are filled and that the visual lane is {hook_proof_lane}
  - `Runtime/browser proof:` {runtime_proof_lane}
  - `Alternate surfaces / bypass paths:` docs-only/non-UI/backend range vs legacy runtime-UI range without a declared carrier vs accepted engaged target-local reader lane

### Что написать / поправить
- Review artifact only: findings/plan gaps/evidence in `{review_artifact}`
- If the scaffold still leaves profile-specific runtime ambiguity, record it explicitly in the review artifact instead of inventing a fake lane

### Что прогнать
- `python3 ${{PLANVEYOR_ROOT:-$HOME/planveyor}}/scripts/plan_lint.py {plan_path}`
- `{range_stats_command}`
- `git log --oneline --first-parent --merges {base}..{head}`
- `git diff --check {base}..{head}`
- `rg -n "^<<<<<<< |^======= |^>>>>>>> " .`
- `{range_diff_command}`"""

commands = f"""```bash
PYBIN="${{PYBIN:-python3}}"
python3 ${{PLANVEYOR_ROOT:-$HOME/planveyor}}/scripts/plan_lint.py {plan_path}
{range_stats_command}
git log --oneline --first-parent --merges {base}..{head}
git diff --check {base}..{head}
rg -n "^<<<<<<< |^======= |^>>>>>>> " .
{range_diff_command}
```"""

review_artifact_label = "Code review (primary)"
if review_artifact.startswith("docs/doc_reviews/"):
    review_artifact_label = "Doc review (docs-only)"
review_artifacts = f"- {review_artifact_label}: `{review_artifact}`"
verification_handoff = f"""- Mode: N/A (why: this scaffold itself is the reviewer entrypoint; rerun scope is already fixed by `Review target: RANGE={base}..{head}`)
- Repo profile: `{profile_id}`
- Context source: `Review target + {review_artifact}`; review artifact carriers must be `**Target:** {review_target_literal}` and `**Spec:** {review_spec_literal}`
- Prompt: `N/A`
- Command: `N/A`
- Expected artifact: `{review_artifact}`"""

text = Path(plan_source_path).read_text(encoding="utf-8")

replacements = {
    r"^# Plan: .*": title,
    r"^\*\*Date:\*\*.*": f"**Date:** {ts}",
    r"^\*\*Stage:\*\*.*": "**Stage:** Stage 1",
    r"^\*\*Priority:\*\*.*": "**Priority:** P1",
    r"^\*\*Plan type:\*\*.*": "**Plan type:** review-only",
    r"^\*\*Status:\*\*.*": "**Status:** Reviewer intake",
    r"^[ \t]*- Code draft\(s\):.*": f"- Code draft(s): `{draft}`",
}

lines = text.splitlines()
out: list[str] = []
for line in lines:
    new_line = line
    for pat, rep in replacements.items():
        if re.match(pat, new_line):
            new_line = rep
            break
    if '"cluster": "UNCONFIRMED"' in new_line:
        new_line = '    "cluster": "process",'
    if '"tags": []' in new_line:
        new_line = '    "tags": ["review", "merge-range"],'
    out.append(new_line)
text = "\n".join(out) + "\n"
text = scrub_ordinary_plan_meta(text)
text = re.sub(
    r"(?ms)^\*\*Context links \(source of truth\):\*\*.*?(?=^## Meta\b)",
    context_links.rstrip() + "\n\n",
    text,
    count=1,
)
text = replace_section(text, "Problem", problem)
text = replace_section(text, "Как я понял задачу", understanding)
text = replace_section(text, "Solution (high level)", solution)
text = replace_section(text, "Decisions (final)", decisions)
text = replace_section(text, "Scope", scope)
text = replace_section(text, "Out of scope", out_of_scope)
text = replace_section(text, "Follow-ups (deferred)", followups)
text = replace_section(text, "Plan provenance / session context", plan_provenance)
text = replace_section(text, "Documentation impact / provenance", documentation_impact)
text = upsert_section(text, "Retrieval telemetry receipt", retrieval_telemetry_receipt, before_heading="Problem")
text = replace_section(text, "Rollout packet handoff", rollout_packet_handoff)
text = replace_section(text, "Small-slice conveyor classifier", small_slice_classifier)
text = replace_section(text, "Close-out routing", close_out_routing)
text = replace_section(text, "Business decomposition framing", business_decomposition_framing)
text = replace_section(text, "Child plan map", child_plan_map)
text = replace_section(text, "Decomposition quality gate", decomposition_quality_gate)
text = replace_section(text, "Execution queue", execution_queue)
text = replace_section(text, "Queue close-out", queue_close_out)
text = replace_section(text, "Mechanism coverage", mechanism_coverage)
text = replace_section(text, "Risks / Open questions (summary)", risks)
text = replace_section(text, "Reviewability preflight receipt", reviewability_receipt)
text = replace_section(text, "Changes (by area)", changes)
text = replace_section(text, "Acceptance criteria / DoD", acceptance)
text = upsert_section(
    text,
    "Review visual lane contract",
    render_visual_lane_contract(visual_lane_contract),
    before_heading="Visual Acceptance (browser, UI tasks)",
)
text = replace_section(text, "Visual Acceptance (browser, UI tasks)", visual_acceptance)
text = replace_section(text, "Tests", tests)
text = replace_section(text, "Commands", commands)
text = replace_section(text, "Verification rerun / exec handoff", verification_handoff)
text = replace_section(text, "Review artifacts", review_artifacts)

Path(plan_output_path).write_text(text, encoding="utf-8")'''
DRAFT_RENDERER_SOURCE = r'''from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime

draft_path, plan_path, base, head, exclude_docs, profile_id, review_artifact, rerun_carrier_json, range_stats_json, visual_lane_materialization_json, machine_authority_na_ref_json, plan_source_path, draft_source_path, draft_output_path = sys.argv[1:15]
rerun_carrier = json.loads(rerun_carrier_json)
range_stats = json.loads(range_stats_json)
visual_lane_materialization = json.loads(visual_lane_materialization_json)
visual_lane_contract = visual_lane_materialization["contract"]
visual_lane_contract_markdown = str(visual_lane_materialization["markdown"])
rerun_active = bool(rerun_carrier.get("active"))
rerun_mode = rerun_carrier.get("mode")
baseline_artifact = rerun_carrier.get("baseline_artifact")
prior_artifacts = rerun_carrier.get("prior_artifacts") or []

ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")

title = f"# Code draft: Reviewer — merge-range {base[:7]}..{head[:7]} (review-only)"


def git_changed_paths(range_base: str, range_head: str, *, exclude_docs_flag: bool) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{range_base}..{range_head}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    paths = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if exclude_docs_flag:
        paths = [path for path in paths if not path.startswith("docs/")]
    return paths


def git_changed_path_statuses(range_base: str, range_head: str, *, exclude_docs_flag: bool) -> list[dict[str, object]]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-status", "-M", f"{range_base}..{range_head}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    entries: list[dict[str, object]] = []
    for raw_line in proc.stdout.splitlines():
        parts = [part for part in raw_line.split("\t") if part]
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        if exclude_docs_flag and path.startswith("docs/"):
            continue
        entries.append(
            {
                "status": status,
                "path": path,
                "deleted": status.startswith("D"),
            }
        )
    return entries


def infer_target_kind(path: str) -> str:
    if path.startswith("docs/") or Path(path).suffix.lower() == ".md":
        return "doc"
    if path.startswith("templates/"):
        return "template"
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "py"
    if suffix in {".sh", ".zsh"}:
        return "sh"
    if suffix == ".html":
        return "template"
    if suffix in {".css", ".scss"}:
        return "css"
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return "js"
    return "file"


def _stable_paths(paths: list[str]) -> list[str]:
    return sorted(dict.fromkeys(path for path in paths if path.strip()))


def _format_path_list(paths: list[str]) -> str:
    return ", ".join(f"`{path}`" for path in _stable_paths(paths))


def _is_doc_path(path: str) -> bool:
    return path.startswith("docs/") or Path(path).suffix.lower() in {".md", ".mdx", ".rst"}


def _is_process_doc_path(path: str) -> bool:
    return path.startswith(
        (
            "docs/plans/",
            "docs/code_drafts/",
            "docs/code_reviews/",
            "docs/doc_reviews/",
            "docs/followups/",
            "docs/playbooks/",
            "docs/tools/",
            "docs/roles/",
            "docs/process_improvements/",
        )
    )


def _is_tooling_or_process_path(path: str) -> bool:
    return path.startswith(("scripts/", ".github/")) or _is_process_doc_path(path)


def _is_sync_doc_target(path: str) -> bool:
    if not _is_doc_path(path):
        return False
    return not path.startswith(("docs/code_drafts/", "docs/code_reviews/", "docs/doc_reviews/"))


def render_documentation_impact(
    target_paths: list[str],
    deleted_paths: list[str],
    *,
    plan_path: str,
    draft_path: str,
    review_artifact: str,
    range_base: str,
    range_head: str,
    exclude_docs: str,
) -> str:
    live_targets = _stable_paths(target_paths)
    sync_doc_targets = [path for path in live_targets if _is_sync_doc_target(path)]
    if sync_doc_targets:
        sync_doc_line = _format_path_list(sync_doc_targets)
    elif live_targets and all(_is_tooling_or_process_path(path) for path in live_targets):
        sync_doc_line = "`N/A (why=process/tooling-only reviewed range; no product documentation target inferred from exact target metadata)`"
    else:
        sync_doc_line = "`N/A (why=no documentation target in exact reviewed target metadata)`"
    deleted_line = _format_path_list(deleted_paths) if deleted_paths else "`N/A (why=no tracked deleted paths in exact target metadata)`"
    live_targets_line = _format_path_list(live_targets) if live_targets else "`N/A (why=no live targets in exact target metadata)`"
    generated_carriers = _format_path_list([plan_path, draft_path, review_artifact])
    return f"""- Source docs used: exact reviewed target metadata from `RANGE={range_base}..{range_head}` / generated `code_draft_meta.targets`; no prose-only docs-impact inference.
- Exact target metadata: live `code_draft_meta.targets` = {live_targets_line}; deleted `code_draft_meta.deleted_paths` = {deleted_line}
- Synchronous doc/registry targets: {sync_doc_line}
- Generated docs targets / derived carriers: {generated_carriers}
- Post-merge canon updates: `N/A (why=review-only scaffold reports target-derived docs impact; Reviewer/Architect triage owns canon promotion decisions)`
- Deferred documentation follow-ups: `N/A (why=review-only scaffold does not create docs follow-ups during init; Reviewer/Architect triage owns follow-up routing)`
- Provenance refs: `code_draft_meta.targets` source = exact live filtered carrier list for `RANGE={range_base}..{range_head}` with `EXCLUDE_DOCS={exclude_docs}`; `code_draft_meta.deleted_paths` = {deleted_line}; review artifact = `{review_artifact}`"""


def replace_section(text: str, heading: str, body: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    return text


def upsert_section(text: str, heading: str, body: str, *, before_heading: str | None = None) -> str:
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if before_heading:
        before_pattern = re.compile(rf"(?m)^## {re.escape(before_heading)}\n")
        if before_pattern.search(text):
            return before_pattern.sub(replacement + f"## {before_heading}\n", text, count=1)
    return text.rstrip() + "\n\n" + replacement


def remove_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)")
    return pattern.sub("", text, count=1)


def extract_section_body(text: str, heading: str) -> str | None:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\n\n?(.*?)(?=^## |\Z)")
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def render_visual_lane_contract(payload: dict[str, object]) -> str:
    del payload
    return visual_lane_contract_markdown


exclude_docs_flag = exclude_docs == "1"
changed_entries = git_changed_path_statuses(base, head, exclude_docs_flag=exclude_docs_flag)
changed_paths = [str(entry["path"]) for entry in changed_entries]
live_target_paths = [str(entry["path"]) for entry in changed_entries if not bool(entry["deleted"])]
deleted_target_paths = [str(entry["path"]) for entry in changed_entries if bool(entry["deleted"])]
target_paths = live_target_paths or [plan_path]
documentation_impact = render_documentation_impact(
    target_paths,
    deleted_target_paths,
    plan_path=plan_path,
    draft_path=draft_path,
    review_artifact=review_artifact,
    range_base=base,
    range_head=head,
    exclude_docs=exclude_docs,
)

range_stats_command = f"zsh -lc 'source scripts/planveyor.zsh && planveyor_merge_range_stats_json {base} {head}'"
range_stats_inline = (
    f"`{range_stats_command}` -> "
    f"`total_commits={range_stats['total_commits']}`, "
    f"`first_parent_commits={range_stats['first_parent_commits']}`, "
    f"`changed_files={range_stats['changed_files']}`, "
    f"`diffstat_summary={range_stats['diffstat_summary']}`"
)
review_target_literal = f"RANGE={base}..{head} (EXCLUDE_DOCS={exclude_docs})"
review_spec_literal = plan_path

purpose = f"""Держать generated review-only scaffold буквально привязанным к реальному range contract `RANGE={base}..{head}`: plan сверху, expected review artifact `{review_artifact}` снизу, helper-backed stats `{range_stats_command}` как единый count/stat source. Итоговый review artifact обязан materialize-ить `**Target:** {review_target_literal}` и `**Spec:** {review_spec_literal}` как machine carriers; это не production patch spec и не скрытый dev handoff."""

targeted_changes = f"""- Review target: `{review_target_literal}`
- `code_draft_meta.targets`: mirror the live filtered carrier list for `RANGE={base}..{head}` ({len(live_target_paths)} path(s)); tracked deletions live in `code_draft_meta.deleted_paths` ({len(deleted_target_paths)} path(s)) so the live review route `{review_artifact}` agrees with docs-only vs non-doc classification.
- `range stats`: consume {range_stats_inline} so generated scaffold fields do not hand-count `total_commits` / `first_parent_commits` independently.
- `{plan_path}`: materialize literal `Review target`, `Problem / Scope / Tests / Commands`, truthful visual/default lane, and concrete `## Review artifacts`.
- `{review_artifact}`: keep the expected review path concrete from the start, and materialize `**Target:** {review_target_literal}` + `**Spec:** {review_spec_literal}` before `**Status:**`, so Reviewer/Architect/helpers do not reconstruct it from memory or heuristics."""

review_lane_type = "docs review" if review_artifact.startswith("docs/doc_reviews/") else "code review"
review_route = f"""- `Primary artifact`: `{review_artifact}`
- `Lane type`: `{review_lane_type}`"""

patch_sketch = f"""1. Materialize the review-only contract directly from `RANGE={base}..{head}` and the current repo profile instead of leaving template placeholders.
2. Enable a visual lane only when an accepted declared `review_visual_lane_contract.v1` justifies it; otherwise keep explicit `N/A (why)`.
3. Keep the review artifact exact: `**Target:** {review_target_literal}` and `**Spec:** {review_spec_literal}` are mandatory machine carriers for this generated path; do not use the manual no-origin escape hatch here.
4. Keep the bundle exact: `code_draft_meta.targets` = live filtered carrier list from the reviewed range, `code_draft_meta.deleted_paths` = tracked deleted carrier list; `PLAN_PATH`, the code draft, and `{review_artifact}` are bundled separately."""

critical_invariants = f"""- `Invariant:` generated artifact stays `review-only`
  - `Trap:` переписать scaffold так, будто это новый dev-plan с product-fix scope
  - `Bypass path:` separate follow-up dev-plan after Architect triage
- `Invariant:` visual/default lane stays truthful
  - `Trap:` подставить browser/login defaults там, где accepted declared carrier отсутствует
  - `Bypass path:` explicit `N/A (why)` or declared consumer contract
- `Invariant:` generated review artifact uses plan-backed machine carriers
  - `Trap:` заменить `**Spec:** {review_spec_literal}` на prose-only origin, filename inference, queue state, or manual no-origin escape hatch
  - `Bypass path:` fix generated scaffold/materializer or route a bounded process follow-up; do not hand-patch after closeout"""

assumptions_risks = f"""- Assumption: an accepted declared visual contract is sufficient to name visual proof for `RANGE={base}..{head}`.
- Risk: if runtime proof has no declared carrier, the generated scaffold must keep that ambiguity explicit instead of fabricating a browser lane."""

notes_for_coder = f"""- Для review-only merge-range draft `code_draft_meta.targets` must mirror the live filtered carrier list of `RANGE={base}..{head}`, while tracked deletions must live in `code_draft_meta.deleted_paths`.
- Итоговый generated review artifact must include top-level `**Target:** {review_target_literal}` and `**Spec:** {review_spec_literal}` before `**Status:**`; generated init paths do not use the manual no-origin Spec escape hatch.
- Если generated plan всё ещё оставляет template-only placeholders на critical path, исправляй scaffold/materializer, а не конкретный one-off plan руками.
- Если consumer needs a richer runtime lane, поднимай это через declared consumer contract, а не как silent shared fallback.
- Final exact bundle for this generated artifact = filtered range carriers from `code_draft_meta.targets` + current plan path + expected review artifact path."""

plan_text = Path(plan_source_path).read_text(encoding="utf-8")
plan_provenance = extract_section_body(plan_text, "Plan provenance / session context")
fallback_provenance_captured_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
if plan_provenance is None:
    draft_provenance = """- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`
- Relation: `created-here`
- Thread ID: `N/A (why=generated plan did not materialize provenance before draft sync)`
- Parent thread ID: `N/A (why=generated plan did not materialize provenance before draft sync)`
- Session SID: `N/A (why=generated plan did not materialize provenance before draft sync)`
- Launch surface: `unknown (why=generated plan did not materialize provenance before draft sync)`
- Captured from: `manual-owner`
- Captured at: `__FALLBACK_CAPTURED_AT__`""".replace("__FALLBACK_CAPTURED_AT__", fallback_provenance_captured_at)
else:
    draft_provenance = (
        "- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`\n"
        + plan_provenance
    )
reviewability_receipt = extract_section_body(plan_text, "Reviewability preflight receipt")
if reviewability_receipt is None:
    reviewability_receipt = (
        "- `proof-path class`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `mandatory primary lane`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `mandatory non-primary carrier / contextual lane`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `exact helper path + support files`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `dependent tests / dependent docs / known consumer paths`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `preconditions / seed-discovery`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `reroute rule`: `N/A (why=generated plan did not materialize the receipt)`\n"
        "- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`"
    )

if rerun_active:
    prior_artifacts_display = ", ".join(f"`{artifact}`" for artifact in prior_artifacts)
    if baseline_artifact:
        baseline_artifact_line = f"- Baseline artifact: `{baseline_artifact}`"
    else:
        baseline_artifact_line = "- Baseline artifact: `N/A (full rerun; explicit prior artifacts only)`"
    current_flow_rerun_lineage = f"""- Prior review / rerun artifacts: {prior_artifacts_display}
- Rerun mode: `{rerun_mode}`
{baseline_artifact_line}
- Carrier source: explicit env (`PLANVEYOR_REVIEW_RERUN_MODE`, `PLANVEYOR_REVIEW_BASELINE_ARTIFACT`, `PLANVEYOR_REVIEW_PRIOR_ARTIFACTS`); no git-history inference."""

text = Path(draft_source_path).read_text(encoding="utf-8").splitlines()
out: list[str] = []
skip_placeholder_target = False

replacements = {
    r"^# Code draft: .*": title,
    r"^\*\*Date:\*\*.*": f"**Date:** {ts}",
    r"^\*\*Cluster:\*\*.*": "**Cluster:** process",
    r"^\*\*Related plan:\*\*.*": f"**Related plan:** `{plan_path}`",
    r"^\*\*Author role:\*\*.*": "**Author role:** Reviewer",
}

for line in text:
    new_line = line
    for pat, rep in replacements.items():
        if re.match(pat, new_line):
            new_line = rep
            break
    if '"cluster": "UNCONFIRMED"' in new_line:
        new_line = '    "cluster": "process",'
    if '"plan": "docs/plans/YYMMDD_HHMM_topic.md"' in new_line:
        new_line = f'    "plan": "{plan_path}",'
    if '"targets": [' in new_line:
        out.append(new_line)
        for index, target_path in enumerate(target_paths):
            comma = "," if index < len(target_paths) - 1 else ""
            out.extend(
                [
                    "      {",
                    f'        "path": "{target_path}",',
                    f'        "kind": "{infer_target_kind(target_path)}"',
                    f"      }}{comma}",
                ]
            )
        skip_placeholder_target = True
        continue
    if skip_placeholder_target:
        if new_line.strip() in {"]", "],"}:
            skip_placeholder_target = False
            out.append(new_line)
        continue
    if '"path": "UNCONFIRMED"' in new_line or '"kind": "py|template|css|js|doc"' in new_line:
        continue
    out.append(new_line)

draft_text = "\n".join(out) + "\n"
meta_payload = {
    "code_draft_meta": {
        "plan": plan_path,
        "cluster": "process",
        "targets": [
            {"path": target_path, "kind": infer_target_kind(target_path)}
            for target_path in target_paths
        ],
        "deleted_paths": [
            {"path": target_path, "kind": infer_target_kind(target_path)}
            for target_path in deleted_target_paths
        ],
        "machine_authority_decision_ref": json.loads(machine_authority_na_ref_json),
    }
}
draft_text = re.sub(
    r"(?ms)(^## Meta \(machine-readable JSON\)\n```json\n).*?(\n```)",
    lambda match: match.group(1) + json.dumps(meta_payload, ensure_ascii=False, indent=2) + match.group(2),
    draft_text,
    count=1,
)
draft_text = replace_section(draft_text, "Provenance / session context", draft_provenance)
draft_text = replace_section(draft_text, "Purpose", purpose)
draft_text = upsert_section(
    draft_text,
    "Documentation impact / provenance",
    documentation_impact,
    before_heading="Reviewability preflight receipt",
)
draft_text = replace_section(draft_text, "Reviewability preflight receipt", reviewability_receipt)
draft_text = upsert_section(
    draft_text,
    "Review visual lane contract",
    render_visual_lane_contract(visual_lane_contract),
    before_heading="Targeted changes (by file)",
)
draft_text = replace_section(draft_text, "Targeted changes (by file)", targeted_changes)
draft_text = replace_section(draft_text, "Review route", review_route)
draft_text = replace_section(draft_text, "Patch sketch (keep it small)", patch_sketch)
draft_text = replace_section(draft_text, "Critical invariants / traps / bypass paths", critical_invariants)
draft_text = replace_section(draft_text, "Assumptions / risks", assumptions_risks)
draft_text = replace_section(draft_text, "Notes for Coder", notes_for_coder)
if rerun_active:
    draft_text = upsert_section(
        draft_text,
        "Current-flow rerun lineage",
        current_flow_rerun_lineage,
        before_heading="Patch sketch (keep it small)",
    )
else:
    draft_text = remove_section(draft_text, "Current-flow rerun lineage")

Path(draft_output_path).write_text(draft_text, encoding="utf-8")'''


if __name__ == "__main__":
    raise SystemExit(main())

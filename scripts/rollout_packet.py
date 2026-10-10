from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


TARGET_KINDS = ("plan_adoption", "mirror_sync", "checker_rollout", "consumer_only")
ACK_STATUSES = ("imported", "superseded", "cancelled")
PACKET_STATUSES = ("open", *ACK_STATUSES)
CURRENT_CONSUMER_REPO = 'current-consumer'
PACKET_DIR = Path("docs") / "rollout_packets"
TARGET_PLAN_DIR = Path("docs") / "plans"
HEADER_FIELD_RE = re.compile(r"^\s*\*\*(?P<field>[^*]+):\*\*\s*(?P<value>.+?)\s*$", re.MULTILINE)
CONTEXT_LINK_RE = re.compile(r"^\s*-\s*(?P<field>[^:\r\n]+):\s*(?P<value>[^\r\n]+)\s*$", re.MULTILINE)
CONTEXT_LINKS_HEADING_RE = re.compile(r"^\s*\*\*Context links \(source of truth\):\*\*\s*$", re.MULTILINE)
META_JSON_RE = re.compile(r"## Meta \(machine-readable JSON\)\s*```json\s*(?P<body>\{.*?\})\s*```", re.DOTALL)
H2_RE = re.compile(r"^\s*##\s+(?P<heading>.+?)\s*$", re.MULTILINE)
REQUIRED_PACKET_HEADERS = ("Date", "Source repo", "Target repo", "Target kind", "Status")
REQUIRED_PACKET_META_KEYS = (
    "id",
    "source_repo",
    "source_plan",
    "target_repo",
    "target_kind",
    "status",
    "depends_on_packets",
    "queue_after_import",
    "suggested_target_plan_slug",
    "target_import_receipt",
    "target_local_plan",
)
CURRENT_DELIVERY_META_KEYS = (
    "source_range",
    "source_revision",
    "source_artifacts",
    "target_writable_carriers",
)
CURRENT_DELIVERY_ALLOWED_STATUSES = ("open", "imported")
FULL_GIT_OID_RE = re.compile(r"^[0-9a-f]{40,64}$", re.IGNORECASE)
CANONICAL_REPO_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
REQUIRED_PACKET_H2_SECTIONS = (
    "Meta (machine-readable JSON)",
    "Source provenance",
    "Why target repo action exists",
    "Source artifacts",
    "Target writable carriers",
    "Import recipe",
    "Stop conditions / not-in-scope",
    "Adoption completion signal",
    "Source-side acknowledgement",
)
CARRIER_BEGIN = b"<!-- planveyor:rollout_packet_carrier.v1:begin"
CARRIER_END = b"planveyor:rollout_packet_carrier.v1:end -->"
CARRIER_SCHEMA_VERSION = "rollout_packet_outcomes.v1"
CARRIER_TOP_LEVEL_KEYS = ("rollout_packet_import", "rollout_packet_outcomes")
CARRIER_IMPORT_KEYS = (
    "source_repo",
    "source_root",
    "target_repo",
    "imported_at",
    "target_import_receipt",
    "target_local_plan",
    "queue_result",
    "packet_count",
    "excluded_packet_count",
    "packet_rows",
)
CARRIER_OUTCOMES_KEYS = ("schema_version", "items")
CARRIER_ITEM_KEYS = (
    "packet_id",
    "packet_path",
    "target_import_receipt",
    "target_local_plan",
    "decision_state",
    "outcome",
)
CANONICAL_TARGET_OUTCOMES = (
    "imported",
    "adopted",
    "already-handled",
    "pointer-preserved",
    "parked",
    "no-op",
    "superseded",
    "forward-adopted",
    "cancelled",
    "rejected",
)
TARGET_OUTCOME_ALIASES = {
    "already handled": "already-handled",
    "pointer preserved": "pointer-preserved",
    "no op": "no-op",
    "noop": "no-op",
    "forward adopted": "forward-adopted",
    "canceled": "cancelled",
}


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _is_git_worktree(repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _packet_git_state(packet_path: Path, repo_root: Path) -> str:
    if not _is_git_worktree(repo_root):
        return "unknown"

    rel_path = _repo_relative(packet_path, repo_root)
    try:
        tracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", rel_path],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return "unknown"
    if tracked.returncode == 0:
        return "tracked"
    return "untracked"


def _source_readiness_from_git_state(git_state: str) -> str:
    if git_state == "tracked":
        return "tracked-source-packet"
    if git_state == "untracked":
        return "draft-untracked-source-packet"
    return "unknown-git-state"


def _ensure_source_local(repo_root: Path, tooling_root: Path) -> None:
    if repo_root.resolve() != tooling_root.resolve():
        raise SystemExit(
            _fail(
                "rollout packet helpers are source-local only; run them from the planveyor repo, "
                "not from a sibling repo"
            )
        )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        raise ValueError("expected a non-empty lowercase slug")
    return slug


def _normalize_repo_id(value: str) -> str:
    repo_id = value.strip().lower().replace("_", "-")
    repo_id = re.sub(r"-+", "-", repo_id).strip("-")
    if not repo_id:
        raise ValueError("expected a non-empty repo id")
    return repo_id


def _require_current_consumer_source(value: object, *, field: str) -> str:
    if value != CURRENT_CONSUMER_REPO:
        literal = json.dumps(value, ensure_ascii=False, sort_keys=True)
        raise ValueError(
            f"{field} must literally equal `{CURRENT_CONSUMER_REPO}`; found `{literal}`"
        )
    return CURRENT_CONSUMER_REPO


def _humanize_topic(slug: str) -> str:
    text = slug.replace("_", " ").replace("-", " ").strip()
    return text.title() if text else slug


def _read_active_plan(repo_root: Path) -> str | None:
    plan_file = repo_root / ".planveyor.planpath"
    if not plan_file.is_file():
        return None
    lines = [line.strip() for line in plan_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[-1] if lines else None


def _load_template(repo_root: Path) -> str:
    template_path = repo_root / PACKET_DIR / "_template.md"
    if not template_path.is_file():
        raise FileNotFoundError(template_path)
    return template_path.read_text(encoding="utf-8")


def _read_packet_headers(packet_path: Path) -> dict[str, str]:
    text = packet_path.read_text(encoding="utf-8")
    headers: dict[str, str] = {}
    for match in HEADER_FIELD_RE.finditer(text):
        headers[match.group("field").strip()] = match.group("value").strip()
    return headers


def _render_packet(args: argparse.Namespace, repo_root: Path) -> tuple[Path, str]:
    target_repo = _normalize_repo_id(args.target_repo)
    if not CANONICAL_REPO_ID_RE.fullmatch(target_repo):
        raise ValueError("target repo must normalize to a lowercase hyphenated repo id")
    target_slug = _slugify(target_repo)
    topic_slug = _slugify(args.topic_slug)
    source_plan = args.source_plan or _read_active_plan(repo_root)
    if not source_plan:
        raise ValueError("source plan is required; pass --source-plan or set .planveyor.planpath first")

    timestamp = datetime.now()
    packet_id = f"{timestamp:%y%m%d_%H%M}_{target_slug}_{topic_slug}"
    output_path = repo_root / PACKET_DIR / f"{packet_id}.md"
    queue_after_import = args.queue_after_import == "yes"

    content = _load_template(repo_root)
    replacements = {
        "<TOPIC>": _humanize_topic(topic_slug),
        "YYYY-MM-DD HH:MM": timestamp.astimezone().strftime("%Y-%m-%d %H:%M %z"),
        "<target-repo>": target_repo,
        "plan_adoption | mirror_sync | checker_rollout | consumer_only": args.target_kind,
        "open | imported | superseded | cancelled": "open",
        "docs/plans/<YYMMDD_HHMM>_<topic>.md": source_plan,
        "- Related source docs/code drafts: `docs/code_drafts/...` / `docs/reviews/...` / `N/A`": "- Related source docs/code drafts: `N/A`",
        (
            "- Target import receipt: same path as target local plan by default "
            "(`docs/plans/...`) или `N/A (why=not imported yet)`"
        ): (
            "- Target import receipt: `N/A (why=not imported yet; "
            "default target_import_receipt == target_local_plan after target import)`"
        ),
        (
            "- Target local plan: same path as target import receipt by default "
            "(`docs/plans/...`) или `N/A (why=not imported yet)`"
        ): (
            "- Target local plan: `N/A (why=not imported yet; "
            "target repo has not materialized the adoption plan/import receipt)`"
        ),
        "<topic_slug>": topic_slug,
        '"id": "YYMMDD_HHMM_target_topic"': f'"id": "{packet_id}"',
        '"source_plan": "docs/plans/<YYMMDD_HHMM>_<topic>.md"': f'"source_plan": "{source_plan}"',
        '"target_kind": "plan_adoption"': f'"target_kind": "{args.target_kind}"',
        '"status": "open"': '"status": "open"',
        '"queue_after_import": true': f'"queue_after_import": {json.dumps(queue_after_import)}',
        '"suggested_target_plan_slug": "<topic_slug>"': f'"suggested_target_plan_slug": "{topic_slug}"',
    }
    for needle, replacement in replacements.items():
        content = content.replace(needle, replacement)

    expected_source_header = f"**Source repo:** {CURRENT_CONSUMER_REPO}"
    expected_source_meta = f'"source_repo": "{CURRENT_CONSUMER_REPO}"'
    if content.count(expected_source_header) != 1 or content.count(expected_source_meta) != 1:
        raise ValueError(
            f"rollout packet template must serialize source_repo as `{CURRENT_CONSUMER_REPO}`"
        )

    return output_path, content


def _resolve_packet_path(repo_root: Path, packet_path: str) -> Path:
    candidate = Path(packet_path)
    if candidate.is_absolute():
        raise ValueError(f"packet path must be repo-relative under {PACKET_DIR.as_posix()}/")

    resolved = (repo_root / candidate).resolve()
    expected_root = (repo_root / PACKET_DIR).resolve()
    try:
        resolved.relative_to(expected_root)
    except ValueError as exc:
        raise ValueError(f"packet path must stay under {PACKET_DIR.as_posix()}/") from exc
    if resolved.suffix != ".md":
        raise ValueError(f"packet path must end with .md under {PACKET_DIR.as_posix()}/")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _normalize_current_delivery_path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} entries must be strings")
    raw = value.strip()
    if not raw or raw.lower().startswith("n/a") or "<" in raw or ">" in raw:
        raise ValueError(f"{field} entries must be non-placeholder repo-relative paths")
    if raw != value or "\\" in raw:
        raise ValueError(f"{field} entries must use normalized repo-relative paths")
    candidate = Path(raw)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError(f"{field} entries must stay repo-relative")
    normalized = candidate.as_posix()
    if normalized != raw or normalized.startswith("../"):
        raise ValueError(f"{field} entries must use normalized repo-relative paths")
    return normalized


def _normalize_current_delivery_path_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"packet_meta.{field} must be a list")
    paths = [_normalize_current_delivery_path(item, field=field) for item in value]
    if not paths:
        raise ValueError(f"packet_meta.{field} must not be empty")
    if paths != sorted(paths):
        raise ValueError(f"packet_meta.{field} must be sorted")
    if len(paths) != len(set(paths)):
        raise ValueError(f"packet_meta.{field} must not contain duplicates")
    return paths


def _markdown_h2_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"missing required H2 section: {heading}")
    next_heading = re.search(r"^##\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def _current_delivery_section_paths(text: str, *, heading: str, field: str) -> list[str]:
    section = _markdown_h2_section(text, heading)
    paths: list[str] = []
    for raw_line in section.splitlines():
        if not raw_line.strip():
            continue
        match = re.fullmatch(r"\s*-\s+`(?P<path>[^`]+)`\s*", raw_line)
        if not match:
            raise ValueError(f"{heading} must contain only '- `repo/relative/path`' entries")
        paths.append(_normalize_current_delivery_path(match.group("path"), field=field))
    if not paths:
        raise ValueError(f"{heading} must not be empty")
    if paths != sorted(paths):
        raise ValueError(f"{heading} entries must be sorted")
    if len(paths) != len(set(paths)):
        raise ValueError(f"{heading} entries must not contain duplicates")
    return paths


def _validate_current_source_plan(value: object) -> str:
    normalized = _normalize_current_delivery_path(value, field="source_plan")
    candidate = Path(normalized)
    if len(candidate.parts) != 3 or candidate.parts[:2] != ("docs", "plans") or candidate.suffix != ".md":
        raise ValueError("packet_meta.source_plan must be a repo-relative docs/plans/*.md path")
    return normalized


def _validate_current_source_range(value: object) -> tuple[str, str, str]:
    if not isinstance(value, str):
        raise ValueError("packet_meta.source_range must be a full-OID BASE..HEAD string")
    base, separator, head = value.partition("..")
    if not separator or not base or not head or ".." in head:
        raise ValueError("packet_meta.source_range must be a full-OID BASE..HEAD string")
    if not FULL_GIT_OID_RE.fullmatch(base) or not FULL_GIT_OID_RE.fullmatch(head):
        raise ValueError("packet_meta.source_range must contain full commit OIDs")
    return f"{base.lower()}..{head.lower()}", base.lower(), head.lower()


def _validate_current_source_revision(value: object, *, source_range_head: str) -> str:
    if not isinstance(value, str) or not FULL_GIT_OID_RE.fullmatch(value):
        raise ValueError("packet_meta.source_revision must be a full commit OID")
    revision = value.lower()
    if revision != source_range_head:
        raise ValueError("packet_meta.source_revision must equal source_range HEAD")
    return revision


def _resolve_current_delivery_packet_path(repo_root: Path, packet_path: str) -> Path:
    """Resolve one recovery packet through its lexical, symlink-free source path."""

    raw = str(packet_path)
    if not raw or raw != raw.strip() or "\\" in raw:
        raise ValueError(f"packet path must be a normalized repo-relative {PACKET_DIR.as_posix()}/*.md path")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.as_posix() != raw:
        raise ValueError(f"packet path must be a normalized repo-relative {PACKET_DIR.as_posix()}/*.md path")
    if candidate.parts != ("docs", "rollout_packets", candidate.name):
        raise ValueError(f"packet path must be directly under {PACKET_DIR.as_posix()}/")
    if candidate.name == "_template.md" or candidate.suffix != ".md":
        raise ValueError(f"packet path must name a non-template .md file under {PACKET_DIR.as_posix()}/")

    lexical_parts = (repo_root / "docs", repo_root / PACKET_DIR, repo_root / candidate)
    for component in lexical_parts:
        try:
            component_stat = component.lstat()
        except FileNotFoundError as exc:
            raise FileNotFoundError(component) from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise ValueError(f"packet path must not traverse a symlink: {component}")
    if not stat.S_ISREG((repo_root / candidate).lstat().st_mode):
        raise ValueError(f"packet path must name a regular file: {candidate.as_posix()}")

    resolved = (repo_root / candidate).resolve(strict=True)
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"packet path must stay under {PACKET_DIR.as_posix()}/") from exc
    return resolved


def _validate_target_plan_path(target_plan: str) -> str:
    candidate = Path(target_plan)
    if candidate.is_absolute():
        raise ValueError(f"target plan path must be repo-relative under {TARGET_PLAN_DIR.as_posix()}/")
    if candidate.suffix != ".md":
        raise ValueError(f"target plan path must end with .md under {TARGET_PLAN_DIR.as_posix()}/")

    normalized = candidate.as_posix()
    parts = candidate.parts
    if not parts or ".." in parts or normalized.startswith("../"):
        raise ValueError(f"target plan path must stay under {TARGET_PLAN_DIR.as_posix()}/")
    if len(parts) < 3 or parts[0] != "docs" or parts[1] != "plans":
        raise ValueError(f"target plan path must stay under {TARGET_PLAN_DIR.as_posix()}/")
    return normalized


def _normalize_direct_target_plan_ref(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{field} must stay under {TARGET_PLAN_DIR.as_posix()}/ and be a direct repo-relative "
            f"{TARGET_PLAN_DIR.as_posix()}/*.md path"
        )
    raw = value
    if not raw or raw != raw.strip() or "\\" in raw:
        raise ValueError(
            f"{field} must stay under {TARGET_PLAN_DIR.as_posix()}/ and be a direct repo-relative "
            f"{TARGET_PLAN_DIR.as_posix()}/*.md path"
        )
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.as_posix() != raw:
        raise ValueError(
            f"{field} must stay under {TARGET_PLAN_DIR.as_posix()}/ and be a direct repo-relative "
            f"{TARGET_PLAN_DIR.as_posix()}/*.md path"
        )
    if candidate.parts != ("docs", "plans", candidate.name) or candidate.name == "_template.md" or candidate.suffix != ".md":
        raise ValueError(
            f"{field} must stay under {TARGET_PLAN_DIR.as_posix()}/ and be a direct repo-relative "
            f"{TARGET_PLAN_DIR.as_posix()}/*.md path"
        )
    return raw


def _is_direct_target_plan_ref(value: str | None) -> bool:
    if not value:
        return False
    try:
        _normalize_direct_target_plan_ref(value, field="target plan path")
    except ValueError:
        return False
    return True


def _resolve_direct_target_plan_path(repo_root: Path, target_plan: str) -> tuple[Path, str]:
    plan_rel = _normalize_direct_target_plan_ref(target_plan, field="target plan path")
    docs_dir = repo_root / "docs"
    plans_dir = repo_root / TARGET_PLAN_DIR
    plan_path = repo_root / plan_rel
    for component, label in ((docs_dir, "docs"), (plans_dir, TARGET_PLAN_DIR.as_posix()), (plan_path, plan_rel)):
        try:
            component_stat = component.lstat()
        except FileNotFoundError as exc:
            raise FileNotFoundError(component) from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise ValueError(f"target plan path must not traverse a symlink: {label}")
    if not stat.S_ISDIR(docs_dir.lstat().st_mode) or not stat.S_ISDIR(plans_dir.lstat().st_mode):
        raise ValueError(f"target plan path must stay under {TARGET_PLAN_DIR.as_posix()}/")
    if not stat.S_ISREG(plan_path.lstat().st_mode):
        raise ValueError(f"target plan path must name an existing regular file: {plan_rel}")
    resolved = plan_path.resolve(strict=True)
    try:
        resolved.relative_to(plans_dir.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"target plan path must stay under {TARGET_PLAN_DIR.as_posix()}/") from exc
    return resolved, plan_rel


def parse_packet_text(text: str) -> dict[str, object]:
    """Parse one packet from immutable bytes without touching the filesystem.

    Consumers that validate a packet stored in an exact Git object must not
    accidentally substitute the live worktree bytes.  Keep the parser shared
    with the normal path-based reader so the packet grammar has one source of
    truth.
    """

    header_values = _read_packet_header_values(text)
    headers = {field: values[-1] for field, values in header_values.items() if values}
    meta_match = META_JSON_RE.search(text)
    meta = {}
    if meta_match:
        meta = json.loads(meta_match.group("body"))
        if not isinstance(meta, dict):
            meta = {}
    packet_meta = meta.get("packet_meta", {})
    if not isinstance(packet_meta, dict):
        packet_meta = {}

    return {
        "text": text,
        "meta": meta,
        "headers": headers,
        "header_values": header_values,
        "packet_meta": packet_meta,
    }


def _parse_packet(packet_path: Path) -> dict[str, object]:
    return parse_packet_text(packet_path.read_text(encoding="utf-8"))


def _read_packet_header_values(text: str) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for match in HEADER_FIELD_RE.finditer(text):
        field = match.group("field").strip()
        headers.setdefault(field, []).append(match.group("value").strip())
    return headers


def _context_links_block_bounds(text: str) -> tuple[int, int]:
    match = CONTEXT_LINKS_HEADING_RE.search(text)
    if not match:
        raise ValueError("packet must contain **Context links (source of truth):**")

    start = match.end()
    block_end = start
    seen_context_line = False
    for chunk in text[match.end() :].splitlines(keepends=True):
        line_start = block_end
        line_end = line_start + len(chunk)
        line = chunk.rstrip("\r\n")
        if not line.strip():
            if seen_context_line:
                block_end = line_start
                break
            block_end = line_end
            continue
        if not line.lstrip().startswith("- "):
            block_end = line_start
            break
        seen_context_line = True
        block_end = line_end
    return start, block_end


def _read_context_link_values(text: str) -> dict[str, list[str]]:
    start, end = _context_links_block_bounds(text)
    context_block = text[start:end]
    links: dict[str, list[str]] = {}
    for match in CONTEXT_LINK_RE.finditer(context_block):
        field = match.group("field").strip()
        links.setdefault(field, []).append(match.group("value").strip())
    return links


def _lint_finding(path: str, severity: str, code: str, message: str) -> dict[str, object]:
    return {
        "path": path,
        "severity": severity,
        "code": code,
        "message": message,
    }


def _normalized_pointer_equal(left: object, right: object) -> bool:
    return _normalize_pointer(left) == _normalize_pointer(right)


def _normalized_repo_equal(left: object, right: object) -> bool:
    try:
        return _normalize_repo_id(str(left or "")) == _normalize_repo_id(str(right or ""))
    except ValueError:
        return False


def _lint_scope(repo_root: Path, *, all_packets: bool, raw_paths: list[str]) -> tuple[list[Path], list[dict[str, object]]]:
    if all_packets and raw_paths:
        return [], [
            _lint_finding(
                PACKET_DIR.as_posix(),
                "error",
                "invalid_scope",
                "lint accepts either --all or explicit packet/dir args, not both",
            )
        ]
    if all_packets:
        packet_root = repo_root / PACKET_DIR
        if not packet_root.is_dir():
            return [], [
                _lint_finding(
                    PACKET_DIR.as_posix(),
                    "error",
                    "missing_directory",
                    f"packet directory does not exist: {PACKET_DIR.as_posix()}",
                )
            ]
        return [
            packet_path
            for packet_path in sorted(packet_root.glob("*.md"))
            if packet_path.name != "_template.md"
        ], []
    if not raw_paths:
        return [], [
            _lint_finding(
                PACKET_DIR.as_posix(),
                "error",
                "missing_scope",
                "lint requires --all or at least one packet/dir path",
            )
        ]

    packet_root = (repo_root / PACKET_DIR).resolve()
    paths: list[Path] = []
    findings: list[dict[str, object]] = []
    seen: set[Path] = set()

    def add_packet(path: Path) -> None:
        resolved = path.resolve()
        if resolved.name == "_template.md" or resolved in seen:
            return
        seen.add(resolved)
        paths.append(resolved)

    for raw_path in raw_paths:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            findings.append(
                _lint_finding(
                    raw_path,
                    "error",
                    "invalid_path",
                    f"lint path must be repo-relative under {PACKET_DIR.as_posix()}/",
                )
            )
            continue

        resolved = (repo_root / candidate).resolve()
        try:
            resolved.relative_to(packet_root)
        except ValueError:
            findings.append(
                _lint_finding(
                    raw_path,
                    "error",
                    "invalid_path",
                    f"lint path must stay under {PACKET_DIR.as_posix()}/",
                )
            )
            continue
        if not resolved.exists():
            findings.append(
                _lint_finding(
                    candidate.as_posix(),
                    "error",
                    "missing",
                    f"packet path does not exist: {candidate.as_posix()}",
                )
            )
            continue
        if resolved.is_dir():
            for packet_path in sorted(resolved.glob("*.md")):
                add_packet(packet_path)
            continue
        if not resolved.is_file() or resolved.suffix != ".md":
            findings.append(
                _lint_finding(
                    candidate.as_posix(),
                    "error",
                    "invalid_path",
                    f"lint path must be a .md file or directory under {PACKET_DIR.as_posix()}/",
                )
            )
            continue
        add_packet(resolved)
    return paths, findings


def _lint_packet(packet_path: Path, repo_root: Path, *, strict_sections: bool) -> tuple[dict[str, object], list[dict[str, object]]]:
    file_ref = _repo_relative(packet_path, repo_root)
    findings: list[dict[str, object]] = []
    text = packet_path.read_text(encoding="utf-8")

    try:
        packet = _parse_packet(packet_path)
    except json.JSONDecodeError as exc:
        return {"path": file_ref, "status": "error"}, [
            _lint_finding(file_ref, "error", "invalid_json", f"malformed packet JSON: {exc}")
        ]

    header_values = _read_packet_header_values(text)
    headers = packet["headers"] if isinstance(packet.get("headers"), dict) else {}
    for header in REQUIRED_PACKET_HEADERS:
        count = len(header_values.get(header, []))
        if count == 0:
            findings.append(_lint_finding(file_ref, "error", "missing_header", f"missing required header: {header}"))
        elif count > 1:
            findings.append(_lint_finding(file_ref, "error", "duplicate_header", f"duplicate required header: {header}"))

    meta_matches = list(META_JSON_RE.finditer(text))
    packet_meta: object = None
    if not meta_matches:
        findings.append(_lint_finding(file_ref, "error", "missing_meta_block", "missing machine-readable JSON meta block"))
    elif len(meta_matches) > 1:
        findings.append(_lint_finding(file_ref, "error", "duplicate_meta_block", "packet must contain one JSON meta block"))
    else:
        try:
            meta_payload = json.loads(meta_matches[0].group("body"))
        except json.JSONDecodeError as exc:
            findings.append(_lint_finding(file_ref, "error", "invalid_json", f"malformed packet JSON: {exc}"))
            meta_payload = {}
        if not isinstance(meta_payload, dict):
            findings.append(_lint_finding(file_ref, "error", "invalid_meta", "packet meta must be a JSON object"))
        else:
            packet_meta = meta_payload.get("packet_meta")
            if not isinstance(packet_meta, dict):
                findings.append(
                    _lint_finding(file_ref, "error", "invalid_packet_meta", "packet meta must contain packet_meta object")
                )

    meta = packet_meta if isinstance(packet_meta, dict) else {}
    for key in REQUIRED_PACKET_META_KEYS:
        if key not in meta:
            findings.append(_lint_finding(file_ref, "error", "missing_meta_key", f"packet_meta missing required key: {key}"))

    for carrier, raw_value in (
        ("header Source repo", headers.get("Source repo")),
        ("packet_meta.source_repo", meta.get("source_repo")),
    ):
        if raw_value != CURRENT_CONSUMER_REPO:
            literal = json.dumps(raw_value, ensure_ascii=False, sort_keys=True)
            findings.append(
                _lint_finding(
                    file_ref,
                    "error",
                    "invalid_source_repo",
                    f"{carrier} must literally equal `{CURRENT_CONSUMER_REPO}`; found `{literal}`",
                )
            )

    header_target_kind = str(headers.get("Target kind") or "").strip()
    meta_target_kind = str(meta.get("target_kind") or "").strip()
    for carrier, value in (("header Target kind", header_target_kind), ("packet_meta.target_kind", meta_target_kind)):
        if value and value not in TARGET_KINDS:
            findings.append(
                _lint_finding(file_ref, "error", "bad_target_kind", f"{carrier} `{value}` is not one of: {', '.join(TARGET_KINDS)}")
            )

    header_status = str(headers.get("Status") or "").strip().lower()
    meta_status = str(meta.get("status") or "").strip().lower()
    for carrier, value in (("header Status", header_status), ("packet_meta.status", meta_status)):
        if value and value not in PACKET_STATUSES:
            findings.append(
                _lint_finding(file_ref, "error", "bad_status", f"{carrier} `{value}` is not one of: {', '.join(PACKET_STATUSES)}")
            )

    for carrier, present, raw_value in (
        ("header Target repo", "Target repo" in headers, headers.get("Target repo")),
        ("packet_meta.target_repo", "target_repo" in meta, meta.get("target_repo")),
    ):
        if not present:
            continue
        is_canonical = False
        if isinstance(raw_value, str):
            try:
                normalized_value = _normalize_repo_id(raw_value)
            except ValueError:
                normalized_value = None
            is_canonical = (
                normalized_value is not None
                and raw_value == normalized_value
                and CANONICAL_REPO_ID_RE.fullmatch(raw_value) is not None
            )
        if not is_canonical:
            literal = json.dumps(raw_value, ensure_ascii=False, sort_keys=True)
            findings.append(
                _lint_finding(
                    file_ref,
                    "error",
                    "noncanonical_target_repo",
                    f"{carrier} `{literal}` must use its canonical repo id form",
                )
            )

    consistency_checks = (
        ("source_repo", "Source repo", _normalized_repo_equal),
        ("target_repo", "Target repo", _normalized_repo_equal),
        ("target_kind", "Target kind", lambda left, right: str(left or "").strip() == str(right or "").strip()),
        (
            "status",
            "Status",
            lambda left, right: str(left or "").strip().lower() == str(right or "").strip().lower(),
        ),
    )
    for meta_key, header_key, normalizer in consistency_checks:
        header_value = headers.get(header_key)
        meta_value = meta.get(meta_key)
        if header_value is not None and meta_value is not None and not normalizer(header_value, meta_value):
            findings.append(
                _lint_finding(
                    file_ref,
                    "error",
                    "header_meta_mismatch",
                    f"header {header_key} `{header_value}` disagrees with packet_meta.{meta_key} `{meta_value}`",
                )
            )

    try:
        context_values = _read_context_link_values(text)
    except ValueError as exc:
        context_values = {}
        findings.append(_lint_finding(file_ref, "error", "missing_context_links", str(exc)))

    context_checks = (
        ("source_plan", "Source plan"),
        ("target_import_receipt", "Target import receipt"),
        ("target_local_plan", "Target local plan"),
    )
    for meta_key, context_key in context_checks:
        values = context_values.get(context_key, [])
        if not values:
            findings.append(_lint_finding(file_ref, "error", "missing_context", f"missing context link: {context_key}"))
            continue
        if len(values) > 1:
            findings.append(_lint_finding(file_ref, "error", "duplicate_context", f"duplicate context link: {context_key}"))
            continue
        context_value = values[0]
        meta_value = meta.get(meta_key)
        if meta_key in meta and not _normalized_pointer_equal(context_value, meta_value):
            findings.append(
                _lint_finding(
                    file_ref,
                    "error",
                    "context_meta_mismatch",
                    f"context {context_key} `{context_value}` disagrees with packet_meta.{meta_key} `{meta_value}`",
                )
            )

    h2_sections = [match.group("heading").strip() for match in H2_RE.finditer(text)]
    missing_section_severity = "error" if strict_sections else "warning"
    for section in REQUIRED_PACKET_H2_SECTIONS:
        count = h2_sections.count(section)
        if count == 0:
            findings.append(
                _lint_finding(
                    file_ref,
                    missing_section_severity,
                    "missing_section",
                    f"missing required H2 section: {section}",
                )
            )
        elif count > 1:
            findings.append(
                _lint_finding(file_ref, "error", "duplicate_section", f"duplicate required H2 section: {section}")
            )

    required_sections = set(REQUIRED_PACKET_H2_SECTIONS)
    for section in h2_sections:
        if section not in required_sections:
            findings.append(_lint_finding(file_ref, "warning", "extra_section", f"unknown H2 section: {section}"))

    status = "error" if any(finding["severity"] == "error" for finding in findings) else "ok"
    return {"path": file_ref, "status": status}, findings


def _current_delivery_finding(packet_path: Path, repo_root: Path, message: str) -> dict[str, object]:
    return _lint_finding(
        _repo_relative(packet_path, repo_root),
        "error",
        "invalid_current_delivery",
        message,
    )


def _current_delivery_target_semantics(
    packet: dict[str, object],
    *,
    packet_path: Path,
    repo_root: Path,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    findings: list[dict[str, object]] = []
    meta = packet.get("packet_meta")
    if not isinstance(meta, dict):
        return None, [_current_delivery_finding(packet_path, repo_root, "packet_meta must be an object")]

    if meta.get("source_repo") != CURRENT_CONSUMER_REPO:
        findings.append(
            _current_delivery_finding(
                packet_path,
                repo_root,
                f"packet_meta.source_repo must literally equal `{CURRENT_CONSUMER_REPO}`",
            )
        )

    def require_repo(field: str) -> None:
        try:
            _normalize_repo_id(str(meta.get(field) or ""))
        except ValueError:
            findings.append(
                _current_delivery_finding(packet_path, repo_root, f"packet_meta.{field} must be a non-placeholder repo id")
            )

    require_repo("target_repo")
    packet_id = str(meta.get("id") or "").strip()
    if not packet_id or packet_id.lower().startswith("n/a"):
        findings.append(_current_delivery_finding(packet_path, repo_root, "packet_meta.id must be non-placeholder"))
    target_kind = str(meta.get("target_kind") or "").strip()
    if target_kind not in TARGET_KINDS:
        findings.append(
            _current_delivery_finding(
                packet_path,
                repo_root,
                f"packet_meta.target_kind must be one of: {', '.join(TARGET_KINDS)}",
            )
        )

    target_carriers: list[str] | None = None
    try:
        target_carriers = _normalize_current_delivery_path_list(
            meta.get("target_writable_carriers"), field="target_writable_carriers"
        )
        section_carriers = _current_delivery_section_paths(
            str(packet.get("text") or ""),
            heading="Target writable carriers",
            field="target_writable_carriers",
        )
        if section_carriers != target_carriers:
            findings.append(
                _current_delivery_finding(
                    packet_path,
                    repo_root,
                    "Target writable carriers must exactly match packet_meta.target_writable_carriers",
                )
            )
    except ValueError as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))

    if findings or target_carriers is None:
        return None, findings
    return {
        "id": packet_id,
        "source_repo": CURRENT_CONSUMER_REPO,
        "target_repo": _normalize_repo_id(str(meta.get("target_repo") or "")),
        "target_kind": target_kind,
        "target_writable_carriers": target_carriers,
    }, findings


def _validate_current_delivery_restamp_input(
    packet_path: Path,
    repo_root: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Validate the immutable part of an explicit open recovery packet before a restamp."""

    packet_result, findings = _lint_packet(packet_path, repo_root, strict_sections=True)
    if any(finding.get("severity") == "error" for finding in findings):
        return packet_result, findings
    try:
        packet = _parse_packet(packet_path)
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, f"could not parse packet: {exc}"))
        return packet_result, findings

    status = _packet_status(packet)
    if status != "open":
        findings.append(
            _current_delivery_finding(
                packet_path,
                repo_root,
                f"explicit recovery may restamp only open packets; found `{status or 'missing'}`",
            )
        )
    _, target_findings = _current_delivery_target_semantics(packet, packet_path=packet_path, repo_root=repo_root)
    findings.extend(target_findings)
    packet_result["status"] = "error" if any(finding.get("severity") == "error" for finding in findings) else "ok"
    return packet_result, findings


def _current_delivery_stable_identity(packet_path: Path, repo_root: Path) -> dict[str, object]:
    packet = _parse_packet(packet_path)
    stable, findings = _current_delivery_target_semantics(packet, packet_path=packet_path, repo_root=repo_root)
    if findings or stable is None:
        message = "; ".join(str(finding.get("message") or "invalid target semantics") for finding in findings)
        raise ValueError(message or "invalid target semantics")
    return {
        "path": _repo_relative(packet_path, repo_root),
        **stable,
    }


def _validate_current_delivery_packet(
    packet_path: Path,
    repo_root: Path,
    *,
    source_plan: str | None = None,
    source_range: str | None = None,
    source_revision: str | None = None,
    source_artifacts: list[str] | None = None,
    expected_target_repo: str | None = None,
    expected_target_kind: str | None = None,
    expected_target_writable_carriers: list[str] | None = None,
    require_tracked: bool = True,
    allowed_statuses: tuple[str, ...] = CURRENT_DELIVERY_ALLOWED_STATUSES,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Strictly validate a current packet that may appear in a recovery receipt."""

    packet_result, findings = _lint_packet(packet_path, repo_root, strict_sections=True)
    if any(finding.get("severity") == "error" for finding in findings):
        return packet_result, findings
    try:
        packet = _parse_packet(packet_path)
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, f"could not parse packet: {exc}"))
        return packet_result, findings

    meta = packet.get("packet_meta")
    if not isinstance(meta, dict):
        findings.append(_current_delivery_finding(packet_path, repo_root, "packet_meta must be an object"))
        return packet_result, findings

    for key in CURRENT_DELIVERY_META_KEYS:
        if key not in meta:
            findings.append(_current_delivery_finding(packet_path, repo_root, f"packet_meta missing current field: {key}"))

    stable, target_findings = _current_delivery_target_semantics(packet, packet_path=packet_path, repo_root=repo_root)
    findings.extend(target_findings)
    current_source_plan = ""
    current_source_range = ""
    current_source_revision = ""
    current_source_artifacts: list[str] | None = None
    try:
        current_source_plan = _validate_current_source_plan(meta.get("source_plan"))
    except ValueError as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))
    try:
        current_source_range, _, range_head = _validate_current_source_range(meta.get("source_range"))
    except ValueError as exc:
        range_head = ""
        findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))
    try:
        current_source_revision = _validate_current_source_revision(
            meta.get("source_revision"), source_range_head=range_head
        )
    except ValueError as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))
    try:
        current_source_artifacts = _normalize_current_delivery_path_list(
            meta.get("source_artifacts"), field="source_artifacts"
        )
        section_artifacts = _current_delivery_section_paths(
            str(packet.get("text") or ""),
            heading="Source artifacts",
            field="source_artifacts",
        )
        if section_artifacts != current_source_artifacts:
            findings.append(
                _current_delivery_finding(
                    packet_path,
                    repo_root,
                    "Source artifacts must exactly match packet_meta.source_artifacts",
                )
            )
    except ValueError as exc:
        findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))

    status = _packet_status(packet)
    if status not in allowed_statuses:
        findings.append(
            _current_delivery_finding(
                packet_path,
                repo_root,
                f"current delivery status must be one of: {', '.join(allowed_statuses)}; found `{status or 'missing'}`",
            )
        )
    if source_plan is not None:
        try:
            expected_source_plan = _validate_current_source_plan(source_plan)
        except ValueError as exc:
            findings.append(_current_delivery_finding(packet_path, repo_root, f"expected source plan invalid: {exc}"))
        else:
            if current_source_plan != expected_source_plan:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        f"packet_meta.source_plan `{current_source_plan or 'missing'}` does not match `{expected_source_plan}`",
                    )
                )
    if source_range is not None:
        try:
            expected_source_range, _, _ = _validate_current_source_range(source_range)
        except ValueError as exc:
            findings.append(_current_delivery_finding(packet_path, repo_root, f"expected source range invalid: {exc}"))
        else:
            if current_source_range != expected_source_range:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        f"packet_meta.source_range `{current_source_range or 'missing'}` does not match `{expected_source_range}`",
                    )
                )
    if source_revision is not None:
        expected_revision = str(source_revision).lower()
        if not FULL_GIT_OID_RE.fullmatch(expected_revision):
            findings.append(_current_delivery_finding(packet_path, repo_root, "expected source revision must be a full commit OID"))
        elif current_source_revision != expected_revision:
            findings.append(
                _current_delivery_finding(
                    packet_path,
                    repo_root,
                    f"packet_meta.source_revision `{current_source_revision or 'missing'}` does not match `{expected_revision}`",
                )
            )
    if source_artifacts is not None:
        try:
            expected_artifacts = _normalize_current_delivery_path_list(source_artifacts, field="source_artifacts")
        except ValueError as exc:
            findings.append(_current_delivery_finding(packet_path, repo_root, f"expected source artifacts invalid: {exc}"))
        else:
            if current_source_artifacts != expected_artifacts:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        "packet_meta.source_artifacts does not match the resolved range artifact set",
                    )
                )

    if stable is not None and expected_target_repo is not None:
        try:
            normalized_expected_repo = _normalize_repo_id(expected_target_repo)
        except ValueError as exc:
            findings.append(_current_delivery_finding(packet_path, repo_root, f"expected target repo invalid: {exc}"))
        else:
            if str(meta.get("target_repo") or "") != expected_target_repo:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        "packet_meta.target_repo must literally equal the resolved target partition",
                    )
                )
            elif stable["target_repo"] != normalized_expected_repo:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        "packet_meta.target_repo does not match the resolved target partition",
                    )
                )
    if stable is not None and expected_target_kind is not None and stable["target_kind"] != expected_target_kind:
        findings.append(
            _current_delivery_finding(
                packet_path,
                repo_root,
                "packet_meta.target_kind does not match the resolved target partition",
            )
        )
    if stable is not None and expected_target_writable_carriers is not None:
        try:
            expected_carriers = _normalize_current_delivery_path_list(
                expected_target_writable_carriers,
                field="expected target_writable_carriers",
            )
        except ValueError as exc:
            findings.append(_current_delivery_finding(packet_path, repo_root, str(exc)))
        else:
            if stable["target_writable_carriers"] != expected_carriers:
                findings.append(
                    _current_delivery_finding(
                        packet_path,
                        repo_root,
                        "packet_meta.target_writable_carriers does not match the resolved target partition",
                    )
                )

    if require_tracked and _packet_git_state(packet_path, repo_root) != "tracked":
        findings.append(_current_delivery_finding(packet_path, repo_root, "current delivery packet must be tracked or staged"))

    packet_result["status"] = "error" if any(finding.get("severity") == "error" for finding in findings) else "ok"
    if stable is not None:
        packet_result["stable_identity"] = stable
        packet_result["packet_meta_target_repo"] = meta.get("target_repo")
    return packet_result, findings


def _replace_context_link_value(text: str, *, label: str, value: str) -> str:
    replacement = f"- {label}: `{value}`"
    next_text, count = re.subn(
        rf"^(\s*)- {re.escape(label)}: .*$",
        rf"\1{replacement}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(f"packet must contain exactly one context link: {label}")
    return next_text


def _replace_current_delivery_section_paths(text: str, *, heading: str, paths: list[str]) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"packet must contain exactly one H2 section: {heading}")
    match = matches[0]
    next_heading = re.search(r"^##\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    body = "\n".join(f"- `{path}`" for path in paths)
    replacement = f"## {heading}\n{body}\n"
    return text[: match.start()] + replacement + text[end:].lstrip("\n")


def _render_current_delivery_restamp(
    packet_path: Path,
    repo_root: Path,
    *,
    source_plan: str,
    source_range: str,
    source_revision: str,
    source_artifacts: list[str],
    expected_target_repo: str | None = None,
    expected_target_kind: str | None = None,
    expected_target_writable_carriers: list[str] | None = None,
) -> str:
    """Return a bounded source-delivery restamp without changing target semantics."""

    _, findings = _validate_current_delivery_restamp_input(packet_path, repo_root)
    errors = [finding for finding in findings if finding.get("severity") == "error"]
    if errors:
        message = "; ".join(str(finding.get("message") or "invalid packet") for finding in errors)
        raise ValueError(message)

    stable_identity = _current_delivery_stable_identity(packet_path, repo_root)
    if expected_target_repo is not None and stable_identity["target_repo"] != _normalize_repo_id(expected_target_repo):
        raise ValueError("packet target_repo does not match the resolved target partition")
    if expected_target_kind is not None and stable_identity["target_kind"] != expected_target_kind:
        raise ValueError("packet target_kind does not match the resolved target partition")
    if expected_target_writable_carriers is not None:
        expected_carriers = _normalize_current_delivery_path_list(
            expected_target_writable_carriers,
            field="expected target_writable_carriers",
        )
        if stable_identity["target_writable_carriers"] != expected_carriers:
            raise ValueError("packet target_writable_carriers do not match the resolved target partition")

    normalized_plan = _validate_current_source_plan(source_plan)
    normalized_range, _, range_head = _validate_current_source_range(source_range)
    normalized_revision = _validate_current_source_revision(source_revision, source_range_head=range_head)
    normalized_artifacts = _normalize_current_delivery_path_list(source_artifacts, field="source_artifacts")
    packet = _parse_packet(packet_path)
    meta = packet.get("meta")
    packet_meta = packet.get("packet_meta")
    if not isinstance(meta, dict) or not isinstance(packet_meta, dict):
        raise ValueError("packet meta must contain a packet_meta object")

    updated_meta = dict(meta)
    updated_packet_meta = dict(packet_meta)
    updated_packet_meta.update(
        {
            "source_plan": normalized_plan,
            "source_range": normalized_range,
            "source_revision": normalized_revision,
            "source_artifacts": normalized_artifacts,
        }
    )
    updated_meta["packet_meta"] = updated_packet_meta
    next_text = _replace_context_link_value(str(packet.get("text") or ""), label="Source plan", value=normalized_plan)
    next_text = _replace_current_delivery_section_paths(
        next_text,
        heading="Source artifacts",
        paths=normalized_artifacts,
    )
    return _replace_meta_json(next_text, updated_meta)


def _replace_status_header(text: str, status: str) -> str:
    status_header_re = re.compile(r"^(\s*)\*\*Status:\*\*\s*.+?$", flags=re.MULTILINE)
    if len(status_header_re.findall(text)) != 1:
        raise ValueError("packet header must contain exactly one **Status:** field")
    next_text, count = re.subn(
        status_header_re,
        rf"\1**Status:** {status}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError("packet header must contain exactly one **Status:** field")
    return next_text


def _replace_target_context_line(text: str, label: str, value: str | None, status: str) -> str:
    if value is None:
        replacement = f"- {label}: `N/A (why=source-side ack status {status} has no target-local receipt)`"
    else:
        replacement = f"- {label}: `{value}`"
    next_text, count = re.subn(
        rf"^(\s*)- {re.escape(label)}: .*$",
        rf"\1{replacement}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return next_text if count else text


def _replace_meta_json(text: str, meta: dict[str, object]) -> str:
    rendered = json.dumps(meta, indent=2, ensure_ascii=False)
    replacement = f"## Meta (machine-readable JSON)\n```json\n{rendered}\n```"
    next_text, count = META_JSON_RE.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError("packet must contain one machine-readable JSON meta block")
    return next_text


def _append_ack_receipt(
    text: str,
    *,
    acknowledged_at: str,
    status: str,
    reason: str | None,
    target_plan: str | None,
) -> str:
    target_value = target_plan or "N/A"
    reason_value = reason or "N/A (why=imported uses target-local plan/import receipt)"
    receipt = (
        f"- [{acknowledged_at}] source-side acknowledgement: status=`{status}`; "
        f"target_import_receipt=`{target_value}`; target_local_plan=`{target_value}`; reason=`{reason_value}`."
    )
    stripped = text.rstrip()
    if re.search(r"^## Source-side acknowledgement\s*$", stripped, flags=re.MULTILINE):
        stripped = re.sub(
            r"^- `N/A \(why=packet is still open; source-side ack is written by planveyor_rollout_packet_ack\)`\n?",
            "",
            stripped,
            count=1,
            flags=re.MULTILINE,
        )
        return f"{stripped}\n{receipt}\n"
    return f"{stripped}\n\n## Source-side acknowledgement\n{receipt}\n"


def _render_ack_packet(
    packet: dict[str, object],
    *,
    status: str,
    target_plan: str | None,
    reason: str | None,
    now: datetime,
) -> str:
    current_status = _packet_status(packet)
    if current_status != "open":
        raise ValueError(f"packet status must be open before ack; found `{current_status}`")

    text = str(packet["text"])
    meta = packet["meta"]
    packet_meta = packet["packet_meta"]
    if not isinstance(meta, dict) or not isinstance(packet_meta, dict):
        raise ValueError("packet meta must contain a packet_meta object")

    updated_meta = dict(meta)
    updated_packet_meta = dict(packet_meta)
    updated_packet_meta["status"] = status
    updated_packet_meta["target_import_receipt"] = target_plan
    updated_packet_meta["target_local_plan"] = target_plan
    updated_packet_meta["source_acknowledgement"] = {
        "status": status,
        "target_import_receipt": target_plan,
        "target_local_plan": target_plan,
        "reason": reason,
        "acknowledged_at": now.astimezone().isoformat(timespec="seconds"),
    }
    updated_meta["packet_meta"] = updated_packet_meta

    next_text = _replace_status_header(text, status)
    next_text = _replace_target_context_line(next_text, "Target import receipt", target_plan, status)
    next_text = _replace_target_context_line(next_text, "Target local plan", target_plan, status)
    next_text = _replace_meta_json(next_text, updated_meta)
    return _append_ack_receipt(
        next_text,
        acknowledged_at=now.astimezone().strftime("%Y-%m-%d %H:%M %z"),
        status=status,
        reason=reason,
        target_plan=target_plan,
    )


def _target_repo_from_root(repo_root: Path) -> str:
    return _normalize_repo_id(repo_root.resolve().name)


def _packet_status(packet: dict[str, object]) -> str:
    meta = packet["packet_meta"]
    headers = packet["headers"]
    if isinstance(meta, dict) and meta.get("status"):
        return str(meta.get("status")).strip().lower()
    if isinstance(headers, dict) and headers.get("Status"):
        return str(headers.get("Status")).strip().lower()
    return "unknown"


def _packet_header_status(packet: dict[str, object]) -> str:
    headers = packet["headers"]
    if isinstance(headers, dict) and headers.get("Status"):
        return str(headers.get("Status")).strip().lower()
    return ""


def _packet_meta_status(packet: dict[str, object]) -> str:
    meta = packet["packet_meta"]
    if isinstance(meta, dict) and meta.get("status"):
        return str(meta.get("status")).strip().lower()
    return ""


def _packet_target_repo(packet: dict[str, object]) -> str:
    meta = packet["packet_meta"]
    headers = packet["headers"]
    target = ""
    if isinstance(meta, dict) and meta.get("target_repo"):
        target = str(meta.get("target_repo"))
    elif isinstance(headers, dict) and headers.get("Target repo"):
        target = str(headers.get("Target repo"))
    return _normalize_repo_id(target)


def _packet_ack_reason(packet: dict[str, object]) -> str | None:
    meta = packet["packet_meta"]
    if isinstance(meta, dict):
        acknowledgement = meta.get("source_acknowledgement")
        if isinstance(acknowledgement, dict) and acknowledgement.get("reason"):
            return str(acknowledgement.get("reason")).strip() or None

    text = str(packet.get("text") or "")
    match = re.search(r"source-side acknowledgement: .*?reason=`(?P<reason>[^`]+)`", text)
    if match:
        reason = match.group("reason").strip()
        if reason and not reason.startswith("N/A"):
            return reason
    return None


def _normalize_pointer(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("`").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "null" or lowered.startswith("n/a"):
        return None
    return text


def _context_pointer(packet: dict[str, object], label: str) -> str | None:
    text = str(packet.get("text") or "")
    match = re.search(rf"^\s*- {re.escape(label)}:\s*(?P<value>.+?)\s*$", text, flags=re.MULTILINE)
    if not match:
        return None
    return _normalize_pointer(match.group("value"))


def _ack_matches_current_packet(
    packet: dict[str, object],
    *,
    status: str,
    target_plan: str | None,
    reason: str | None,
) -> bool:
    if _packet_status(packet) != status or _packet_header_status(packet) != status:
        return False

    meta = packet["packet_meta"]
    if not isinstance(meta, dict):
        return False

    normalized_target = _normalize_pointer(target_plan)
    if _normalize_pointer(meta.get("target_import_receipt")) != normalized_target:
        return False
    if _normalize_pointer(meta.get("target_local_plan")) != normalized_target:
        return False
    if _context_pointer(packet, "Target import receipt") != normalized_target:
        return False
    if _context_pointer(packet, "Target local plan") != normalized_target:
        return False

    requested_reason = reason.strip() if reason else None
    acknowledgement = meta.get("source_acknowledgement")
    if not isinstance(acknowledgement, dict):
        return False
    if str(acknowledgement.get("status") or "").strip().lower() != status:
        return False
    if _normalize_pointer(acknowledgement.get("target_import_receipt")) != normalized_target:
        return False
    if _normalize_pointer(acknowledgement.get("target_local_plan")) != normalized_target:
        return False
    if status in {"superseded", "cancelled"} or requested_reason:
        return _packet_ack_reason(packet) == requested_reason
    if _packet_ack_reason(packet) != requested_reason:
        return False
    return True


def _is_target_plan_ref(value: str | None) -> bool:
    if not value:
        return False
    try:
        _validate_target_plan_path(value)
    except ValueError:
        return False
    return True


def _has_target_plan_pointer(*values: object) -> bool:
    return any(_is_target_plan_ref(_normalize_pointer(value)) for value in values)


def _has_target_plan_pair(target_import_receipt: object, target_local_plan: object) -> bool:
    return _is_target_plan_ref(_normalize_pointer(target_import_receipt)) and _is_target_plan_ref(
        _normalize_pointer(target_local_plan)
    )


def _target_outcome_cancelled(outcome: str | None) -> bool:
    if not outcome:
        return False
    return any(token in outcome.lower() for token in ("cancelled", "canceled", "rejected", "superseded"))


def _target_outcome_pointer_preserved(outcome: str | None) -> bool:
    if not outcome:
        return False
    lowered = outcome.lower()
    return any(
        token in lowered
        for token in (
            "already-handled",
            "already handled",
            "pointer-preserved",
            "pointer preserved",
            "no-op",
            "noop",
        )
    )


def _target_outcome_parked(outcome: str | None) -> bool:
    return bool(outcome and "parked" in outcome.lower())


def _target_outcome_adopted(outcome: str | None) -> bool:
    if not outcome:
        return False
    lowered = outcome.lower()
    return "imported" in lowered or "adopted" in lowered


def _packet_target_adoption_state(summary: dict[str, object]) -> str:
    status = str(summary.get("status") or "").strip().lower()
    has_target_plan_pair = _has_target_plan_pair(
        summary.get("target_import_receipt"),
        summary.get("target_local_plan"),
    )

    if status in {"cancelled", "superseded"}:
        return "cancelled"
    if status == "imported":
        return "awaiting-target-outcome" if has_target_plan_pair else "awaiting-target-import"
    if status == "open":
        if has_target_plan_pair:
            return "adoption-plan-created"
        if str(summary.get("git_state") or "").strip().lower() == "untracked":
            return "draft-created"
        return "awaiting-target-import"
    return "awaiting-target-import"


def _target_readback_adoption_state(
    summary: dict[str, object],
    *,
    bucket: str,
    source_plan_readiness: str,
    target_local_plan: object,
    target_import_receipt: object,
    target_outcome: object,
) -> str:
    status = str(summary.get("status") or "").strip().lower()
    outcome = _normalize_pointer(target_outcome)
    has_target_plan = _has_target_plan_pointer(target_local_plan, target_import_receipt)

    if bucket == "unproven_target_outcome":
        return "awaiting-target-outcome"
    if bucket == "needs_explicit_target_receipt" and status == "imported":
        return "awaiting-target-outcome"
    if _target_outcome_cancelled(outcome):
        return "cancelled"
    if _target_outcome_parked(outcome):
        return "parked"
    if _target_outcome_pointer_preserved(outcome):
        return "pointer-preserved"
    if source_plan_readiness in {"pending-current-source-plan", "pending-source"}:
        return "adoption-plan-created" if has_target_plan or outcome else "awaiting-target-import"
    if has_target_plan and _target_outcome_adopted(outcome):
        return "adopted"
    if has_target_plan or outcome:
        return "adoption-plan-created"
    return _packet_target_adoption_state(summary)


def _packet_summary(packet_path: Path, tooling_root: Path) -> dict[str, object]:
    packet = _parse_packet(packet_path)
    meta = packet["packet_meta"]
    headers = packet["headers"]
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(headers, dict):
        headers = {}

    _require_current_consumer_source(meta.get("source_repo"), field="packet_meta.source_repo")
    _require_current_consumer_source(headers.get("Source repo"), field="header Source repo")

    target_repo = _packet_target_repo(packet)
    status = _packet_status(packet)
    git_state = _packet_git_state(packet_path, tooling_root)
    target_import_receipt = _normalize_pointer(meta.get("target_import_receipt"))
    target_local_plan = _normalize_pointer(meta.get("target_local_plan"))
    summary = {
        "path": _repo_relative(packet_path, tooling_root),
        "absolute_path": str(packet_path.resolve()),
        "id": str(meta.get("id") or packet_path.stem),
        "source_repo": CURRENT_CONSUMER_REPO,
        "source_plan": str(meta.get("source_plan") or "N/A"),
        "source_range": str(meta.get("source_range") or ""),
        "source_revision": str(meta.get("source_revision") or ""),
        "source_artifacts": meta.get("source_artifacts"),
        "target_repo": target_repo,
        "target_kind": str(meta.get("target_kind") or headers.get("Target kind") or "N/A"),
        "target_writable_carriers": meta.get("target_writable_carriers"),
        "status": status,
        "git_state": git_state,
        "source_readiness": _source_readiness_from_git_state(git_state),
        "header_status": _packet_header_status(packet),
        "meta_status": _packet_meta_status(packet),
        "date": str(headers.get("Date") or ""),
        "queue_after_import": bool(meta.get("queue_after_import", False)),
        "suggested_target_plan_slug": str(meta.get("suggested_target_plan_slug") or packet_path.stem),
        "target_import_receipt": target_import_receipt,
        "target_local_plan": target_local_plan,
        "context_target_import_receipt": _context_pointer(packet, "Target import receipt"),
        "context_target_local_plan": _context_pointer(packet, "Target local plan"),
        "reason": _packet_ack_reason(packet),
    }
    summary["target_adoption_state"] = _packet_target_adoption_state(summary)
    return summary


def _status_filter(raw_statuses: list[str] | None) -> set[str]:
    statuses = {status.strip().lower() for status in (raw_statuses or ["open"]) if status.strip()}
    return statuses or {"open"}


def _query_status_filter(raw_statuses: list[str] | None) -> set[str]:
    statuses = {status.strip().lower() for status in (raw_statuses or []) if status.strip()}
    unknown = sorted(status for status in statuses if status != "all" and status not in PACKET_STATUSES)
    if unknown:
        raise ValueError(f"unknown packet status filter: {', '.join(unknown)}")
    return statuses or {"all"}


def _load_source_corpus(repo_root: Path) -> list[dict[str, object]]:
    packet_root = repo_root / PACKET_DIR
    if not packet_root.is_dir():
        raise FileNotFoundError(packet_root)

    summaries: list[dict[str, object]] = []
    for packet_path in sorted(packet_root.glob("*.md")):
        if packet_path.name == "_template.md":
            continue
        try:
            summaries.append(_packet_summary(packet_path, repo_root))
        except json.JSONDecodeError as exc:
            packet_rel = _repo_relative(packet_path, repo_root)
            raise ValueError(f"{packet_rel}: malformed packet JSON: {exc}") from exc
    return summaries


def _packet_query_row(summary: dict[str, object]) -> dict[str, object]:
    return {
        "packet_path": summary["path"],
        "id": summary["id"],
        "target_repo": summary["target_repo"],
        "status": summary["status"],
        "target_adoption_state": _packet_target_adoption_state(summary),
        "git_state": summary["git_state"],
        "source_readiness": summary["source_readiness"],
        "source_plan": summary["source_plan"],
        "queue_after_import": summary["queue_after_import"],
        "target_import_receipt": summary["target_import_receipt"],
        "target_local_plan": summary["target_local_plan"],
        "reason": summary["reason"],
    }


def _parse_packet_datetime(summary: dict[str, object]) -> tuple[datetime | None, str | None]:
    raw_date = str(summary.get("date") or "").strip()
    if raw_date:
        try:
            explicit_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M %z")
            return explicit_date.astimezone().replace(tzinfo=None), None
        except ValueError:
            pass
        compact_date = re.sub(r"\s+[A-Z]{2,5}$", "", raw_date)
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(compact_date, fmt), None
            except ValueError:
                pass

    packet_id = str(summary.get("id") or "")
    match = re.match(r"(?P<stamp>\d{6}_\d{4})", packet_id)
    if match:
        try:
            return datetime.strptime(match.group("stamp"), "%y%m%d_%H%M"), None
        except ValueError:
            pass

    return None, "packet date is not parseable from **Date:** header or packet id timestamp"


def _reconcile_row(summary: dict[str, object], bucket: str, message: str) -> dict[str, object]:
    return {
        "bucket": bucket,
        "packet_path": summary["path"],
        "id": summary["id"],
        "status": summary["status"],
        "target_adoption_state": _packet_target_adoption_state(summary),
        "git_state": summary["git_state"],
        "source_readiness": summary["source_readiness"],
        "target_repo": summary["target_repo"],
        "target_import_receipt": summary["target_import_receipt"],
        "target_local_plan": summary["target_local_plan"],
        "reason": summary["reason"],
        "message": message,
    }


def _reconcile_rows(
    summaries: list[dict[str, object]], *, older_than_days: int, now: datetime
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    stale_cutoff = now - timedelta(days=older_than_days)

    for summary in summaries:
        status = str(summary["status"]).lower()
        meta_status = str(summary.get("meta_status") or "").lower()
        header_status = str(summary.get("header_status") or "").lower()
        if meta_status and header_status and meta_status != header_status:
            rows.append(
                _reconcile_row(
                    summary,
                    "status_mismatch",
                    f"header status `{header_status}` disagrees with packet_meta.status `{meta_status}`",
                )
            )

        if status == "open":
            packet_datetime, warning = _parse_packet_datetime(summary)
            if warning:
                rows.append(_reconcile_row(summary, "date_warning", warning))
            elif packet_datetime and packet_datetime < stale_cutoff:
                rows.append(
                    _reconcile_row(
                        summary,
                        "stale_open",
                        f"status is open and packet date is older than {older_than_days} day(s)",
                    )
                )

        target_import_receipt = _normalize_pointer(summary.get("target_import_receipt"))
        target_local_plan = _normalize_pointer(summary.get("target_local_plan"))
        context_import_receipt = _normalize_pointer(summary.get("context_target_import_receipt"))
        context_local_plan = _normalize_pointer(summary.get("context_target_local_plan"))
        if status == "imported":
            if not (_is_target_plan_ref(target_import_receipt) and _is_target_plan_ref(target_local_plan)):
                rows.append(
                    _reconcile_row(
                        summary,
                        "imported_without_target_path",
                        "imported packet must have target_import_receipt and target_local_plan under docs/plans/",
                    )
                )
            if (
                target_import_receipt != target_local_plan
                or context_import_receipt != target_import_receipt
                or context_local_plan != target_local_plan
            ):
                rows.append(
                    _reconcile_row(
                        summary,
                        "missing_pointers",
                        "header/context pointer fields and packet_meta target pointer fields are missing or disagree",
                    )
                )

        if status in {"superseded", "cancelled"} and not _normalize_pointer(summary.get("reason")):
            rows.append(
                _reconcile_row(
                    summary,
                    "terminal_without_reason",
                    f"{status} packet must carry an explicit acknowledgement reason",
                )
            )

    return rows


def _split_target_inbox(
    summaries: list[dict[str, object]], *, include_untracked: bool
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if include_untracked:
        return summaries, []

    included: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for summary in summaries:
        if summary.get("git_state") == "untracked":
            excluded_summary = dict(summary)
            excluded_summary["excluded_reason"] = (
                "untracked source packet hidden by default; pass --include-untracked to include draft packets"
            )
            excluded.append(excluded_summary)
        else:
            included.append(summary)
    return included, excluded


def _load_target_inbox(tooling_root: Path, target_repo: str, statuses: set[str]) -> list[dict[str, object]]:
    packet_root = tooling_root / PACKET_DIR
    if not packet_root.is_dir():
        raise FileNotFoundError(packet_root)

    normalized_target = _normalize_repo_id(target_repo)
    include_all_statuses = "all" in statuses
    summaries: list[dict[str, object]] = []
    for packet_path in sorted(packet_root.glob("*.md")):
        if packet_path.name == "_template.md":
            continue
        try:
            summary = _packet_summary(packet_path, tooling_root)
        except json.JSONDecodeError as exc:
            headers = _read_packet_headers(packet_path)
            packet_target = headers.get("Target repo")
            if packet_target and _normalize_repo_id(packet_target) != normalized_target:
                continue
            packet_rel = _repo_relative(packet_path, tooling_root)
            raise ValueError(f"{packet_rel}: malformed packet JSON: {exc}") from exc
        if str(summary["target_repo"]) != normalized_target:
            continue
        if not include_all_statuses and str(summary["status"]).lower() not in statuses:
            continue
        summaries.append(summary)
    return summaries


def _read_plan_status(repo_root: Path, plan_ref: object) -> str:
    raw_ref = _normalize_pointer(plan_ref)
    if not raw_ref:
        return "missing"
    candidate = Path(raw_ref)
    if candidate.is_absolute():
        return "invalid"
    plan_path = repo_root / candidate
    if not plan_path.is_file():
        return "missing"
    text = plan_path.read_text(encoding="utf-8")
    statuses = [match.group("value").strip() for match in HEADER_FIELD_RE.finditer(text) if match.group("field").strip() == "Status"]
    if len(statuses) != 1:
        return "invalid"
    return statuses[0]


def _source_plan_readiness(summary: dict[str, object], repo_root: Path, active_plan: str | None) -> tuple[str, str]:
    source_plan = str(summary.get("source_plan") or "")
    status = _read_plan_status(repo_root, source_plan)
    if status.strip().lower() == "done":
        return status, "target-ready/readback-needed"
    if active_plan and source_plan == active_plan:
        return status, "pending-current-source-plan"
    return status, "pending-source"


def _target_outcome_bucket(outcome: str) -> str:
    lowered = outcome.lower()
    if any(token in lowered for token in ("cancelled", "canceled", "rejected", "superseded")):
        return "cancelled/superseded candidate"
    if "parked" in lowered:
        return "parked candidate"
    if any(
        token in lowered
        for token in (
            "already-handled",
            "already handled",
            "pointer-preserved",
            "pointer preserved",
            "no-op",
            "noop",
        )
    ):
        return "pointer-preserved candidate"
    return "candidate_imported"


def _canonical_target_outcome(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("outcome must be one canonical value or documented alias")
    normalized = value.strip().lower()
    if normalized in CANONICAL_TARGET_OUTCOMES:
        return normalized
    alias = TARGET_OUTCOME_ALIASES.get(normalized)
    if alias:
        return alias
    raise ValueError("outcome must be one canonical value or documented alias")


def _require_exact_keys(value: object, *, field: str, expected: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{field} must have exactly the documented keys")
    return value


def _reject_duplicate_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key `{key}`")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant `{value}` is not allowed")


def _carrier_payload_span(raw: bytes) -> tuple[int, int] | None:
    offset = 0
    begin_lines: list[tuple[int, int]] = []
    end_lines: list[tuple[int, int]] = []
    for line in raw.splitlines(keepends=True):
        end = offset + len(line)
        content = line.rstrip(b"\r\n")
        if content == CARRIER_BEGIN:
            begin_lines.append((offset, end))
        if content == CARRIER_END:
            end_lines.append((offset, end))
        offset = end
    if not begin_lines and not end_lines:
        return None
    if len(begin_lines) != 1 or len(end_lines) != 1:
        raise ValueError("structured carrier requires exactly one begin and one end sentinel")
    begin_start, payload_start = begin_lines[0]
    payload_end, _end_line = end_lines[0]
    if begin_start >= payload_end:
        raise ValueError("structured carrier sentinels must be ordered and non-nesting")
    if not raw[payload_start:payload_end].strip():
        raise ValueError("structured carrier payload must contain one JSON object")
    return payload_start, payload_end


def _normalize_carrier_packet_path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a direct repo-relative {PACKET_DIR.as_posix()}/*.md path")
    raw = value
    if not raw or raw != raw.strip() or "\\" in raw:
        raise ValueError(f"{field} must be a direct repo-relative {PACKET_DIR.as_posix()}/*.md path")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.as_posix() != raw:
        raise ValueError(f"{field} must be a direct repo-relative {PACKET_DIR.as_posix()}/*.md path")
    if candidate.parts != ("docs", "rollout_packets", candidate.name) or candidate.name == "_template.md" or candidate.suffix != ".md":
        raise ValueError(f"{field} must be a direct repo-relative {PACKET_DIR.as_posix()}/*.md path")
    return raw


def _validate_structured_carrier_payload(
    payload: object,
    *,
    plan_rel: str,
    expected_target_repo: str,
) -> dict[str, object]:
    carrier = _require_exact_keys(payload, field="structured carrier", expected=CARRIER_TOP_LEVEL_KEYS)
    import_record = _require_exact_keys(
        carrier["rollout_packet_import"], field="rollout_packet_import", expected=CARRIER_IMPORT_KEYS
    )
    outcomes_record = _require_exact_keys(
        carrier["rollout_packet_outcomes"],
        field="rollout_packet_outcomes",
        expected=CARRIER_OUTCOMES_KEYS,
    )

    for field in ("source_repo", "source_root", "imported_at", "queue_result", "packet_rows"):
        value = import_record[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"rollout_packet_import.{field} must be a non-empty string")
    _require_current_consumer_source(import_record["source_repo"], field="rollout_packet_import.source_repo")
    target_repo = import_record["target_repo"]
    if not isinstance(target_repo, str) or _normalize_repo_id(target_repo) != target_repo:
        raise ValueError("rollout_packet_import.target_repo must be a normalized repo id")
    if target_repo != expected_target_repo:
        raise ValueError("rollout_packet_import.target_repo does not match the current target repo")
    receipt = _normalize_direct_target_plan_ref(
        import_record["target_import_receipt"], field="rollout_packet_import.target_import_receipt"
    )
    local_plan = _normalize_direct_target_plan_ref(
        import_record["target_local_plan"], field="rollout_packet_import.target_local_plan"
    )
    if receipt != local_plan or receipt != plan_rel:
        raise ValueError("rollout_packet_import pointer pair must equal the current target plan")
    for field in ("packet_count", "excluded_packet_count"):
        value = import_record[field]
        if type(value) is not int or value < 0:
            raise ValueError(f"rollout_packet_import.{field} must be a non-negative integer")
    if outcomes_record["schema_version"] != CARRIER_SCHEMA_VERSION:
        raise ValueError("rollout_packet_outcomes.schema_version is invalid")
    items = outcomes_record["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("rollout_packet_outcomes.items must be a non-empty list")
    if import_record["packet_count"] != len(items):
        raise ValueError("rollout_packet_import.packet_count must equal rollout_packet_outcomes.items length")

    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        record = _require_exact_keys(item, field=f"rollout_packet_outcomes.items[{index}]", expected=CARRIER_ITEM_KEYS)
        packet_id = record["packet_id"]
        if not isinstance(packet_id, str) or not packet_id or packet_id != packet_id.strip():
            raise ValueError(f"rollout_packet_outcomes.items[{index}].packet_id must be a non-empty exact string")
        packet_path = _normalize_carrier_packet_path(
            record["packet_path"], field=f"rollout_packet_outcomes.items[{index}].packet_path"
        )
        item_receipt = _normalize_direct_target_plan_ref(
            record["target_import_receipt"],
            field=f"rollout_packet_outcomes.items[{index}].target_import_receipt",
        )
        item_plan = _normalize_direct_target_plan_ref(
            record["target_local_plan"],
            field=f"rollout_packet_outcomes.items[{index}].target_local_plan",
        )
        if item_receipt != item_plan or item_receipt != plan_rel:
            raise ValueError(f"rollout_packet_outcomes.items[{index}] pointer pair must equal the current target plan")
        decision_state = record["decision_state"]
        outcome = record["outcome"]
        if decision_state == "pending":
            if outcome is not None:
                raise ValueError(f"rollout_packet_outcomes.items[{index}] pending state requires outcome=null")
        elif decision_state == "recorded":
            if not isinstance(outcome, str) or outcome not in CANONICAL_TARGET_OUTCOMES:
                raise ValueError(f"rollout_packet_outcomes.items[{index}] recorded state requires a canonical outcome")
        else:
            raise ValueError(f"rollout_packet_outcomes.items[{index}].decision_state must be pending or recorded")
        identity = (packet_id, packet_path)
        if identity in identities:
            raise ValueError("rollout_packet_outcomes.items must not contain duplicate packet identities")
        identities.add(identity)
    return carrier


def _read_structured_carrier(
    raw: bytes,
    *,
    plan_rel: str,
    expected_target_repo: str,
) -> dict[str, object] | None:
    span = _carrier_payload_span(raw)
    if span is None:
        return None
    payload_start, payload_end = span
    try:
        decoded = raw[payload_start:payload_end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("structured carrier payload must be valid UTF-8") from exc
    try:
        payload = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_object,
            parse_constant=_reject_non_finite_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"structured carrier JSON is invalid: {exc}") from exc
    carrier = _validate_structured_carrier_payload(
        payload,
        plan_rel=plan_rel,
        expected_target_repo=expected_target_repo,
    )
    return {
        "plan_rel": plan_rel,
        "payload": carrier,
        "payload_start": payload_start,
        "payload_end": payload_end,
    }


def _build_target_carrier_index(target_root: Path, *, target_repo: str) -> dict[str, object]:
    index: dict[str, object] = {"carriers": [], "invalid_labels": []}
    docs_dir = target_root / "docs"
    plans_dir = target_root / TARGET_PLAN_DIR
    if not docs_dir.exists() and not plans_dir.exists():
        return index
    try:
        docs_stat = docs_dir.lstat()
        plans_stat = plans_dir.lstat()
    except FileNotFoundError:
        return index
    if (
        stat.S_ISLNK(docs_stat.st_mode)
        or stat.S_ISLNK(plans_stat.st_mode)
        or not stat.S_ISDIR(docs_stat.st_mode)
        or not stat.S_ISDIR(plans_stat.st_mode)
    ):
        index["invalid_labels"] = ["docs/plans + invalid-direct-directory"]
        return index

    carriers: list[dict[str, object]] = []
    invalid_labels: list[str] = []
    try:
        plan_paths = sorted((path for path in plans_dir.iterdir() if path.suffix == ".md"), key=lambda path: path.name)
    except OSError as exc:
        index["invalid_labels"] = [f"docs/plans + unreadable:{exc.__class__.__name__}"]
        return index
    for plan_path in plan_paths:
        plan_rel = (TARGET_PLAN_DIR / plan_path.name).as_posix()
        try:
            plan_stat = plan_path.lstat()
            if stat.S_ISLNK(plan_stat.st_mode) or not stat.S_ISREG(plan_stat.st_mode):
                raise ValueError("target plan is not a direct regular non-symlink file")
            raw = plan_path.read_bytes()
            carrier = _read_structured_carrier(raw, plan_rel=plan_rel, expected_target_repo=target_repo)
        except (OSError, ValueError) as exc:
            invalid_labels.append(f"{plan_rel} + invalid:{exc}")
            continue
        if carrier is not None:
            carriers.append(carrier)
    index["carriers"] = carriers
    index["invalid_labels"] = sorted(invalid_labels)
    return index


def _source_target_pointer_pair(summary: dict[str, object]) -> str | None:
    receipt = _normalize_pointer(summary.get("target_import_receipt"))
    local_plan = _normalize_pointer(summary.get("target_local_plan"))
    if receipt == local_plan and _is_direct_target_plan_ref(receipt):
        return receipt
    return None


def _target_pointer_observation(summary: dict[str, object]) -> str:
    receipt = _normalize_pointer(summary.get("target_import_receipt")) or "null"
    local_plan = _normalize_pointer(summary.get("target_local_plan")) or "null"
    return f"target_import_receipt=`{receipt}` target_local_plan=`{local_plan}`"


def _unproven_target_outcome_evidence(
    summary: dict[str, object], *, message: str
) -> dict[str, object]:
    source_pair = _source_target_pointer_pair(summary)
    return {
        "bucket": "unproven_target_outcome",
        "target_local_plan": source_pair,
        "target_import_receipt": source_pair,
        "target_outcome": None,
        "message": message,
    }


def _carrier_item_label(carrier: dict[str, object], item: dict[str, object]) -> str:
    state = str(item["decision_state"])
    outcome = item["outcome"]
    value = str(outcome) if outcome is not None else "null"
    return f"{carrier['plan_rel']} + {state}:{value}"


def _target_plan_evidence_for_packet(
    carrier_index: dict[str, object], summary: dict[str, object]
) -> dict[str, object] | None:
    invalid_labels = carrier_index["invalid_labels"]
    if isinstance(invalid_labels, list) and invalid_labels:
        return _unproven_target_outcome_evidence(
            summary,
            message=f"target readback structured carrier validation failed; carriers: {', '.join(invalid_labels)}",
        )

    carriers = carrier_index["carriers"]
    if not isinstance(carriers, list) or not carriers:
        return None
    packet_id = str(summary.get("id") or "")
    packet_path = str(summary.get("path") or "")
    matches: list[tuple[dict[str, object], dict[str, object]]] = []
    for carrier in carriers:
        if not isinstance(carrier, dict):
            continue
        payload = carrier.get("payload")
        if not isinstance(payload, dict):
            continue
        outcomes = payload.get("rollout_packet_outcomes")
        if not isinstance(outcomes, dict):
            continue
        items = outcomes.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("packet_id") == packet_id and item.get("packet_path") == packet_path:
                matches.append((carrier, item))
    if not matches:
        labels = sorted(str(carrier.get("plan_rel") or "unknown") for carrier in carriers if isinstance(carrier, dict))
        return _unproven_target_outcome_evidence(
            summary,
            message=f"target readback found structured carriers but no exact packet item; carriers: {', '.join(labels)}",
        )

    labels = sorted(_carrier_item_label(carrier, item) for carrier, item in matches)
    if len(matches) != 1:
        return _unproven_target_outcome_evidence(
            summary,
            message=(
                "target readback needs exactly one valid matching recorded item; "
                f"carriers: {', '.join(labels)}"
            ),
        )
    carrier, item = matches[0]
    plan_rel = str(carrier["plan_rel"])
    if item["decision_state"] != "recorded":
        return _unproven_target_outcome_evidence(
            summary,
            message=f"target readback matching item is pending; carriers: {', '.join(labels)}",
        )
    source_pair = _source_target_pointer_pair(summary)
    if source_pair != plan_rel:
        return _unproven_target_outcome_evidence(
            summary,
            message=(
                "target readback carrier is incompatible with the source default pointer pair; "
                f"carriers: {', '.join(labels)}; expected target_import_receipt == target_local_plan == "
                f"`{plan_rel}`, observed {_target_pointer_observation(summary)}"
            ),
        )
    outcome = str(item["outcome"])
    return {
        "bucket": _target_outcome_bucket(outcome),
        "target_local_plan": plan_rel,
        "target_import_receipt": plan_rel,
        "target_outcome": outcome,
        "message": f"target plan records structured rollout packet outcome `{outcome}`",
    }


def _target_reconcile_row(
    summary: dict[str, object],
    *,
    bucket: str,
    message: str,
    source_plan_status: str,
    source_plan_readiness: str,
    target_local_plan: str | None = None,
    target_import_receipt: str | None = None,
    target_outcome: str | None = None,
) -> dict[str, object]:
    return {
        "bucket": bucket,
        "packet_path": summary["path"],
        "id": summary["id"],
        "status": summary["status"],
        "target_adoption_state": _target_readback_adoption_state(
            summary,
            bucket=bucket,
            source_plan_readiness=source_plan_readiness,
            target_local_plan=target_local_plan,
            target_import_receipt=target_import_receipt,
            target_outcome=target_outcome,
        ),
        "git_state": summary["git_state"],
        "source_readiness": summary["source_readiness"],
        "source_plan": summary["source_plan"],
        "source_plan_status": source_plan_status,
        "source_plan_readiness": source_plan_readiness,
        "target_repo": summary["target_repo"],
        "target_import_receipt": target_import_receipt,
        "target_local_plan": target_local_plan,
        "target_outcome": target_outcome,
        "reason": summary["reason"],
        "message": message,
    }


def _target_reconcile_rows(
    summaries: list[dict[str, object]],
    *,
    repo_root: Path,
    target_root: Path,
    target_repo: str,
) -> list[dict[str, object]]:
    normalized_target = _normalize_repo_id(target_repo)
    active_plan = _read_active_plan(repo_root)
    carrier_index = _build_target_carrier_index(target_root, target_repo=normalized_target)
    rows: list[dict[str, object]] = []
    for summary in summaries:
        if str(summary.get("target_repo")) != normalized_target:
            continue
        status = str(summary.get("status")).lower()
        if status not in {"open", "imported"}:
            continue

        source_plan_status, source_plan_readiness = _source_plan_readiness(summary, repo_root, active_plan)
        evidence = _target_plan_evidence_for_packet(carrier_index, summary)
        evidence_plan = _normalize_pointer(evidence.get("target_local_plan")) if evidence else None
        evidence_receipt = _normalize_pointer(evidence.get("target_import_receipt")) if evidence else None
        evidence_outcome = _normalize_pointer(evidence.get("target_outcome")) if evidence else None

        if status == "imported":
            if evidence:
                rows.append(
                    _target_reconcile_row(
                        summary,
                        bucket=str(evidence["bucket"]),
                        message=str(evidence["message"]),
                        source_plan_status=source_plan_status,
                        source_plan_readiness=source_plan_readiness,
                        target_local_plan=evidence_plan,
                        target_import_receipt=evidence_receipt,
                        target_outcome=evidence_outcome,
                    )
                )
                continue

            target_plan = _normalize_pointer(summary.get("target_local_plan")) or _normalize_pointer(
                summary.get("target_import_receipt")
            )
            rows.append(
                _target_reconcile_row(
                    summary,
                    bucket="needs_explicit_target_receipt",
                    message=(
                        "source packet is acked as imported, but target-local terminal outcome is not "
                        "visible from target readback"
                    ),
                    source_plan_status=source_plan_status,
                    source_plan_readiness=source_plan_readiness,
                    target_local_plan=target_plan,
                    target_import_receipt=target_plan,
                )
            )
            continue

        if source_plan_readiness == "pending-current-source-plan":
            message = "packet points at the active source plan, so target import waits for this plan to close"
            if evidence_plan:
                message += "; target-local receipt is report-only until source closes"
            rows.append(
                _target_reconcile_row(
                    summary,
                    bucket="pending-current-source-plan",
                    message=message,
                    source_plan_status=source_plan_status,
                    source_plan_readiness=source_plan_readiness,
                    target_local_plan=evidence_plan,
                    target_import_receipt=evidence_receipt,
                    target_outcome=evidence_outcome,
                )
            )
            continue

        if source_plan_readiness == "pending-source":
            message = "source plan is not terminal, so target queueing must wait or record pending-source locally"
            if evidence_plan:
                message += "; target-local receipt is report-only until source closes"
            rows.append(
                _target_reconcile_row(
                    summary,
                    bucket="pending-source",
                    message=message,
                    source_plan_status=source_plan_status,
                    source_plan_readiness=source_plan_readiness,
                    target_local_plan=evidence_plan,
                    target_import_receipt=evidence_receipt,
                    target_outcome=evidence_outcome,
                )
            )
            continue

        if evidence:
            rows.append(
                _target_reconcile_row(
                    summary,
                    bucket=str(evidence["bucket"]),
                    message=str(evidence["message"]),
                    source_plan_status=source_plan_status,
                    source_plan_readiness=source_plan_readiness,
                    target_local_plan=evidence_plan,
                    target_import_receipt=evidence_receipt,
                    target_outcome=evidence_outcome,
                )
            )
            continue

        if source_plan_readiness == "target-ready/readback-needed":
            rows.append(
                _target_reconcile_row(
                    summary,
                    bucket="needs_explicit_target_receipt",
                    message="source plan is Done, but target-local import receipt/outcome is not recorded",
                    source_plan_status=source_plan_status,
                    source_plan_readiness=source_plan_readiness,
                )
            )
    return rows


def _ensure_target_local_adoption(repo_root: Path, tooling_root: Path, target_repo: str) -> None:
    if repo_root.resolve() == tooling_root.resolve():
        raise ValueError("adoption-plan must run from the target repo, not from the planveyor source repo")

    current_repo = _target_repo_from_root(repo_root)
    if current_repo != target_repo:
        raise ValueError(
            f"adoption-plan target mismatch: current repo id `{current_repo}` does not match target repo `{target_repo}`"
        )


def _default_target_plan_path(now: datetime) -> Path:
    return Path("docs") / "plans" / f"{now:%y%m%d_%H%M}_process_rollout_packet_inbox_adoption.md"


def _resolve_target_plan_output(repo_root: Path, out: str | None, now: datetime) -> Path:
    raw = out if out is not None else _default_target_plan_path(now).as_posix()
    plan_rel = _normalize_direct_target_plan_ref(raw, field="target plan output")
    return repo_root / plan_rel


def _render_packet_list_for_plan(summaries: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for summary in summaries:
        lines.append(
            "- `{path}` - id=`{id}`, kind=`{kind}`, source_plan=`{source_plan}`, queue_after_import=`{queue}`".format(
                path=summary["absolute_path"],
                id=summary["id"],
                kind=summary["target_kind"],
                source_plan=summary["source_plan"],
                queue=str(summary["queue_after_import"]).lower(),
            )
        )
    return "\n".join(lines)


def _render_excluded_packet_list_for_plan(summaries: list[dict[str, object]]) -> str:
    if not summaries:
        return "- `N/A (why=no untracked source packets were excluded by helper default)`"
    lines: list[str] = []
    for summary in summaries:
        lines.append(
            "- `{path}` - id=`{id}`, git_state=`{git_state}`, reason=`{reason}`".format(
                path=summary["absolute_path"],
                id=summary["id"],
                git_state=summary["git_state"],
                reason=summary.get("excluded_reason", "excluded by helper default"),
            )
        )
    return "\n".join(lines)


def _render_import_receipt_for_plan(
    *,
    target_repo: str,
    tooling_root: Path,
    plan_rel: str,
    summaries: list[dict[str, object]],
    excluded_summaries: list[dict[str, object]],
    now: datetime,
) -> str:
    items = [
        {
            "packet_id": str(summary["id"]),
            "packet_path": str(summary["path"]),
            "target_import_receipt": plan_rel,
            "target_local_plan": plan_rel,
            "decision_state": "pending",
            "outcome": None,
        }
        for summary in summaries
    ]
    items.sort(key=lambda item: (str(item["packet_path"]), str(item["packet_id"])))
    identities = [(str(item["packet_id"]), str(item["packet_path"])) for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError("generated rollout packet carrier cannot contain duplicate packet identities")
    payload = {
        "rollout_packet_import": {
            "source_repo": CURRENT_CONSUMER_REPO,
            "source_root": str(tooling_root.resolve()),
            "target_repo": target_repo,
            "imported_at": now.astimezone().isoformat(timespec="seconds"),
            "target_import_receipt": plan_rel,
            "target_local_plan": plan_rel,
            "queue_result": "not_queued_yet",
            "packet_count": len(summaries),
            "excluded_packet_count": len(excluded_summaries),
            "packet_rows": "see ## Imported rollout packets",
        },
        "rollout_packet_outcomes": {
            "schema_version": CARRIER_SCHEMA_VERSION,
            "items": items,
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _render_adoption_plan(
    *,
    target_repo: str,
    tooling_root: Path,
    target_plan_path: Path,
    repo_root: Path,
    summaries: list[dict[str, object]],
    excluded_summaries: list[dict[str, object]],
    now: datetime,
) -> str:
    plan_rel = _repo_relative(target_plan_path, repo_root)
    import_receipt_json = _render_import_receipt_for_plan(
        target_repo=target_repo,
        tooling_root=tooling_root,
        plan_rel=plan_rel,
        summaries=summaries,
        excluded_summaries=excluded_summaries,
        now=now,
    )
    packet_list = _render_packet_list_for_plan(summaries)
    excluded_packet_list = _render_excluded_packet_list_for_plan(excluded_summaries)
    packet_context = "\n".join(f"  - `{summary['absolute_path']}`" for summary in summaries)
    packet_count = len(summaries)
    doc_review_path = f"docs/doc_reviews/{target_plan_path.stem}.md"
    return f"""# Plan: Process - rollout packet inbox adoption

**Date:** {now.astimezone():%Y-%m-%d %H:%M %z}
**Stage:** Stage 1
**Priority:** P1
**Plan type:** dev
**Status:** Architect initial draft
**Schema version:** plan.v2

**Handoff statuses (кто ставит):**
- `Ready for Planner` - Architect
- `Ready for Coder` - Planner
- `Ready for Review` - Coder
- `Ready for Arch review` - Reviewer
- `Done` - Architect

**Context links (source of truth):**
- Source tooling root: `{tooling_root.resolve()}`
- Imported source rollout packets:
{packet_context}
- Target import receipt / local adoption plan: `{plan_rel}`
- Code draft(s): `N/A (why=target-local import receipt plan generated from packet inbox; Planner may materialize a code draft if local implementation widens)`

## Meta (machine-readable JSON; required for new plans)
```json
{{
  "plan_meta": {{
    "cluster": "process",
    "required_manager_mode": "either",
    "tags": [
      "rollout-packet",
      "packet-inbox",
      "target-import",
      "local-adoption",
      "{target_repo}"
    ],
    "phase_overlay": null,
    "phase_state": null,
    "parent": null,
    "next_plans": [],
    "depends_on": [],
    "queue_activation": {{
      "state": "owner_approved",
      "source_ref": "target-local rollout packet adoption generated by planveyor_rollout_packet_adoption_plan",
      "reason": "Target operator materialized this adoption plan/import receipt from the source packet inbox; queue admission remains target-local."
    }},
    "canon_updates": []
  }}
}}
```

## Plan provenance / session context
- Relation: `imported-from-packet`
- Thread ID: `N/A (why=generated target-local packet inbox plan)`
- Parent thread ID: `N/A (why=generated target-local packet inbox plan)`
- Session SID: `N/A (why=generated target-local packet inbox plan)`
- Launch surface: `rollout-packet-inbox`
- Captured from: `wrapper-helper`
- Captured at: `{now.astimezone().isoformat(timespec="seconds")}`

## Documentation impact / provenance
- Source docs used: imported source rollout packets listed in `## Imported rollout packets`; `planveyor` helper `{tooling_root.resolve()}/scripts/rollout_packet.py`.
- Synchronous doc/registry targets: `N/A (why=generated target-local import receipt; concrete local docs/code targets are decided by target Planner)`
- Post-merge canon updates: `N/A (why=target-local adoption outcomes are recorded in this plan or child local plans)`
- Deferred documentation follow-ups: target-local child docs/plans if Planner splits imported packets.
- Provenance refs: helper-generated import from {packet_count} source rollout packet(s) for `{target_repo}`.

## Problem
1. Source repo `{CURRENT_CONSUMER_REPO}` has {packet_count} open rollout packet(s) for `{target_repo}`.
2. Packet files are handoff artifacts only; they are not executable queue items.
3. Target repo needs one local adoption plan that is also the import receipt before Manager/queue can process the work without hidden cross-repo ownership.

## Solution (high level)
- Treat this plan as the target-local import receipt and local adoption plan for the packet inbox.
- The helper-owned sentinel carrier in this plan starts every imported packet at `pending` with `outcome=null`; target roles use the checked-in `planveyor_rollout_packet_outcome_set` command to record one canonical decision.
- Only target-local plans may enter the target repo queue.

### Как я понял задачу
- Owner wants target repos to discover pending source packets from `planveyor` instead of relying on manual memory.
- This plan is generated inside the target repo and therefore may own target-local follow-up planning.
- Source packet files remain read-only context; this plan's exact structured carrier is the only target-decision authority, while prose and legacy fenced JSON are no-authority history.

## Decisions (final)
- ❌ Queue `docs/rollout_packets/*.md` directly -> ✅ queue this target-local adoption plan or its child local plans.
- ❌ Write target repo files from `planveyor` source context -> ✅ run packet inbox harvest from the target repo.
- ❌ Create a second target receipt file beside the adoption plan -> ✅ use this target-local adoption plan as the import receipt by default.
- ❌ Treat `queue_after_import`, prose or a fenced import copy as source authority -> ✅ target repo records a canonical outcome through the checked-in writer.

### UI playbooks (micro-block; required for UI tasks)
- Playbooks: `N/A (why=process/helper import plan; no UI surface)`
- Playbook fields: `N/A (why=process/helper import plan; no UI surface)`

## Scope
- Imported rollout packets:
{packet_list}
- Excluded rollout packets:
{excluded_packet_list}
- Target-local import decisions for each packet.
- Target-local adoption plan or child-plan creation if a packet requires implementation.

## Out of scope
- Editing `planveyor` source packets from this target-local plan.
- Writing files in sibling repositories.
- Treating source packet paths as queue items.
- Changing branch protection or external required-check settings without target-owner confirmation.

## Follow-ups (deferred)
- Target-local child plans for any imported packet that is too large for this single adoption plan.

## Rollout packet handoff
- Role: `target-import`
- Packet path: `N/A (why=multiple source packet paths are listed in Imported rollout packets)`
- Target repo: `{target_repo}`
- Suggested target plan slug: `N/A (why=this is already the target-local adoption plan)`
- Queue after import: `N/A (why=queue decision stays target-local after this receipt)`

## Close-out routing
- Roadmap/queue sync: target repo queues this plan or generated child plans only after `planveyor_rollout_packet_outcome_set` records target-local decisions.
- Follow-up sync: each packet outcome is recorded through the exact sentinel carrier as imported, parked, superseded, or cancelled.
- Next bounded slice: Planner reviews the packet list and decides whether to split into child local plans.
- Terminal outcome: yes

## Execution queue
- `N/A (why=single target-local import plan; packet list is not a plan queue)`

## Queue close-out
- `N/A (why=queue state is target-local and starts only if owner/manager queues this plan)`

## Mechanism coverage
- `Mechanism:` `target packet inbox -> target-local adoption plan`
  - `Usage:` target repo discovers source packets and materializes a local executable planning carrier.
  - `State:` `used`
  - `Promoted child impact:` no source-side queueing or sibling writes are required.

## Constraints / Assumptions
- Source packets remain read-only context.
- Target repo owns all local plan, code, docs, tests, and queue decisions.
- Packet statuses in source may remain `open` until a later source-side acknowledgement updates them.
- Only the exact sentinel carrier's `rollout_packet_outcomes.v1` item can record a terminal per-packet decision; prose and legacy standalone fenced JSON are not authority.

## Risks / Open questions (summary)
- If this plan imports too many unrelated packets, Planner should split into child local plans before implementation.
- If a packet is stale or already superseded locally, record a cancelled/superseded canonical outcome through `planveyor_rollout_packet_outcome_set` instead of implementing it.
- If source packet wording is insufficient, route back to `planveyor` with a concrete packet-quality follow-up.

## Reviewability preflight receipt
- `proof-path class`: `target-local packet inbox import receipt`
- `mandatory primary lane`: `<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py {plan_rel}`
- `mandatory non-primary carrier / contextual lane`: `planveyor_rollout_packet_inbox --target-repo {target_repo}`
- `exact helper path + support files`: `{tooling_root.resolve()}/scripts/rollout_packet.py`, `{tooling_root.resolve()}/docs/rollout_packets/*.md`, and this target-local plan
- `dependent tests / dependent docs / known consumer paths`: target-local queue/Manager flow, imported source packets, and any child local plans produced from this import
- `preconditions / seed-discovery`: `planveyor_rollout_packet_inbox --target-repo {target_repo}` returned {packet_count} matching packet(s)
- `reroute rule`: if work requires source packet rewrites, stop and route that fix to `planveyor`; if work requires target code/docs, keep it target-local
- `receipt-reuse-only`: `target_import_receipt == target_local_plan == {plan_rel}` for this generated target-local carrier unless a future packet-specific override says otherwise
- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`

## Changes (by area)
- Data/schema (migrations if used):
  - `N/A (process/docs import plan until Planner scopes concrete packet work)`
- Logic/modules:
  - `N/A (process/docs import plan until Planner scopes concrete packet work)`
- Interfaces (API/CLI/UI):
  - `N/A (process/docs import plan until Planner scopes concrete packet work)`
- Config (keys/defaults):
  - `N/A (process/docs import plan until Planner scopes concrete packet work)`
- Docs/registry:
  - `{plan_rel}`

## Acceptance criteria / DoD

### Backend/Domain contract checklist (required if touching data/logic/interfaces)
- [ ] `N/A (why=process/docs import plan until packet work is scoped)`

### General DoD checklist (recommended)
- [ ] Every imported packet has one machine-owned target-local outcome item: pending/null until `planveyor_rollout_packet_outcome_set` records a canonical value
- [ ] Queue contains only target-local plan paths, never source packet paths
- [ ] Any implementation packet is either handled in this plan or split into a child target-local plan
- [ ] Source packet quality gaps are routed back to `planveyor` instead of patched from the target repo

### UI contract checklist (required if touching UI)
- [ ] `N/A (why=process/docs import plan until packet work is scoped)`

### Visual regression scenarios (docs/smoke_visual.md)
- `N/A (why=process/docs import plan until packet work is scoped)`

## Tests
- `planveyor_rollout_packet_inbox --target-repo {target_repo}`
- `<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py {plan_rel}`

## Commands
```bash
planveyor_rollout_packet_inbox --target-repo {target_repo}
<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py {plan_rel}
```

## Verification rerun / exec handoff
- Mode: fresh-exec
- Context source: source rollout packet inbox from `{tooling_root.resolve()}/docs/rollout_packets`
- Prompt: `Review the imported rollout packet inbox for {target_repo}, use planveyor_rollout_packet_outcome_set for each target decision, and split implementation into child local plans when needed. Do not queue source packet files directly.`
- Command: `planveyor_rollout_packet_inbox --target-repo {target_repo} && <consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py {plan_rel}`
- Expected artifact: target-local import receipt and adoption plan

## Evidence (chronological, append-only)
- [{now.astimezone():%Y-%m-%d %H:%M %z}] (Helper) Generated target-local adoption plan/import receipt from {packet_count} open rollout packet(s) for `{target_repo}`; `rollout_packet_import.target_import_receipt` and `rollout_packet_import.target_local_plan` both point to `{plan_rel}`.
- [{now.astimezone():%Y-%m-%d %H:%M %z}] (Helper) Carrier note: `rollout_packet_outcomes.v1` starts every packet at pending/null; target roles must use `planveyor_rollout_packet_outcome_set` before source structured readback can become terminal.

## Imported rollout packets
### Imported packet rows
{packet_list}

### Excluded packet rows
{excluded_packet_list}

## Rollout packet outcome carrier
<!-- planveyor:rollout_packet_carrier.v1:begin
{import_receipt_json}
planveyor:rollout_packet_carrier.v1:end -->

## Review artifacts
- Doc review (docs-only): `{doc_review_path}`

## Q&A log (chronological, append-only)

### Architect Q&A
- [{now.astimezone():%Y-%m-%d %H:%M %z}] NO QUESTIONS: packet inbox was discovered from source repo and materialized as this target-local plan.
"""


def cmd_create(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    try:
        output_path, content = _render_packet(args, repo_root)
    except (FileNotFoundError, ValueError) as exc:
        return _fail(str(exc))

    print(f"Packet path: {_repo_relative(output_path, repo_root)}")
    if args.dry_run:
        print("Mode: dry-run (no file written)")
        print("---")
        print(content, end="" if content.endswith("\n") else "\n")
        return 0

    if output_path.exists():
        return _fail(f"packet already exists: {_repo_relative(output_path, repo_root)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print("Result: written")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    try:
        packet_path = _resolve_packet_path(repo_root, args.packet_path)
        packet = _parse_packet(packet_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    if args.raw:
        print(packet["text"], end="" if str(packet["text"]).endswith("\n") else "\n")
        return 0

    headers = packet["headers"]
    meta = packet["packet_meta"]
    print(f"Packet path: {_repo_relative(packet_path, repo_root)}")
    print(f"Packet id: {meta.get('id', 'N/A')}")
    print(f"Source repo: {headers.get('Source repo', meta.get('source_repo', 'N/A'))}")
    print(f"Source plan: {meta.get('source_plan', 'N/A')}")
    print(f"Target repo: {headers.get('Target repo', meta.get('target_repo', 'N/A'))}")
    print(f"Target kind: {headers.get('Target kind', meta.get('target_kind', 'N/A'))}")
    print(f"Status: {headers.get('Status', meta.get('status', 'N/A'))}")
    print(f"Queue after import: {meta.get('queue_after_import', 'N/A')}")
    print(f"Suggested target plan slug: {meta.get('suggested_target_plan_slug', 'N/A')}")
    print(f"Target import receipt: {meta.get('target_import_receipt', 'N/A')}")
    print(f"Target local plan: {meta.get('target_local_plan', 'N/A')}")
    return 0


def _print_target_plan_seed(packet_path_repo_relative: str, packet_meta: dict[str, object]) -> None:
    target_slug = packet_meta.get("suggested_target_plan_slug", "topic_slug")
    print("")
    print("Suggested target-local plan seed (text only):")
    print(f"- Filename slug: {target_slug}")
    print("- Context links:")
    print(f"  - Source rollout packet: `{packet_path_repo_relative}`")
    print("  - Target import receipt: same path as target local adoption plan by default")
    print("  - Target local plan: `docs/plans/...`")
    print("- Generate the plan with planveyor_rollout_packet_adoption_plan, then use planveyor_rollout_packet_outcome_set for the target decision.")
    print("- Queue after import stays target-local and explicit; this text seed is not outcome authority.")


def cmd_import_instructions(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    try:
        packet_path = _resolve_packet_path(repo_root, args.packet_path)
        packet = _parse_packet(packet_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    meta = packet["packet_meta"]
    packet_path_repo_relative = _repo_relative(packet_path, repo_root)
    print(f"Source packet: {packet_path_repo_relative}")
    print(f"Packet id: {meta.get('id', 'N/A')}")
    print(f"Target repo: {meta.get('target_repo', 'N/A')}")
    print(f"Suggested target plan slug: {meta.get('suggested_target_plan_slug', 'N/A')}")
    print("")
    print("Target-local import instructions:")
    print("1. Open this packet in the target repo context.")
    print(
        "2. Materialize one target-local adoption plan as the import receipt with planveyor_rollout_packet_adoption_plan."
    )
    print(
        "3. Record one target decision only with planveyor_rollout_packet_outcome_set --target-plan ... --packet-id ... "
        "--packet-path ... --outcome ...."
    )
    print("4. Use the generated adoption plan path as both target_import_receipt and target_local_plan; prose and legacy fenced JSON are not authority.")
    print("5. Queue only the target-local plan after import if the target repo explicitly wants it.")
    print("")
    print("Stop conditions:")
    print("- Do not write, stage, or commit sibling-repo files from the source repo.")
    print("- Do not invoke target-local queue commands from the source repo.")
    print("- If target-local automation is needed, reroute it to the target repo or a target-side follow-up.")

    if args.print_target_plan_seed:
        _print_target_plan_seed(packet_path_repo_relative, meta)
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    target_repo = _normalize_repo_id(args.target_repo or _target_repo_from_root(repo_root))
    statuses = _status_filter(args.status)

    try:
        all_summaries = _load_target_inbox(tooling_root, target_repo, statuses)
        summaries, excluded_summaries = _split_target_inbox(
            all_summaries, include_untracked=bool(args.include_untracked)
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    if args.json:
        print(
            json.dumps(
                {
                    "target_repo": target_repo,
                    "repo_root": str(repo_root),
                    "tooling_root": str(tooling_root),
                    "statuses": sorted(statuses),
                    "count": len(summaries),
                    "excluded_count": len(excluded_summaries),
                    "packets": summaries,
                    "excluded_packets": excluded_summaries,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    status_label = "all" if "all" in statuses else "|".join(sorted(statuses))
    print(f"Rollout packet inbox for target repo: {target_repo}")
    print(f"Target repo root: {repo_root}")
    print(f"Source tooling root: {tooling_root}")
    print(f"Status filter: {status_label}")
    print(f"Matching packets: {len(summaries)}")
    print(f"Excluded untracked packets: {len(excluded_summaries)}")
    for idx, summary in enumerate(summaries, 1):
        print(
            (
                "{idx:02d}. {path} id={id} kind={kind} status={status} "
                "target_adoption_state={state} git_state={git_state} queue_after_import={queue}"
            ).format(
                idx=idx,
                path=summary["path"],
                id=summary["id"],
                kind=summary["target_kind"],
                status=summary["status"],
                state=summary["target_adoption_state"],
                git_state=summary["git_state"],
                queue=str(summary["queue_after_import"]).lower(),
            )
        )
        print(f"    source_plan={summary['source_plan']}")
    for idx, summary in enumerate(excluded_summaries, 1):
        print(
            "excluded {idx:02d}. {path} id={id} git_state={git_state} reason={reason}".format(
                idx=idx,
                path=summary["path"],
                id=summary["id"],
                git_state=summary["git_state"],
                reason=summary.get("excluded_reason", "excluded"),
            )
        )
    return 0


def cmd_adoption_plan(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    target_repo = _normalize_repo_id(args.target_repo or _target_repo_from_root(repo_root))
    statuses = _status_filter(args.status)
    now = datetime.now()

    try:
        _ensure_target_local_adoption(repo_root, tooling_root, target_repo)
        all_summaries = _load_target_inbox(tooling_root, target_repo, statuses)
        summaries, excluded_summaries = _split_target_inbox(
            all_summaries, include_untracked=bool(args.include_untracked)
        )
        output_path = _resolve_target_plan_output(repo_root, args.out, now)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    if not summaries:
        print(f"No matching rollout packets for target repo: {target_repo}")
        if excluded_summaries:
            print(f"Excluded untracked packets: {len(excluded_summaries)}")
        return 0
    if output_path.exists():
        return _fail(f"target plan already exists: {_repo_relative(output_path, repo_root)}")

    content = _render_adoption_plan(
        target_repo=target_repo,
        tooling_root=tooling_root,
        target_plan_path=output_path,
        repo_root=repo_root,
        summaries=summaries,
        excluded_summaries=excluded_summaries,
        now=now,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    rel_output = _repo_relative(output_path, repo_root)
    print(f"Target local plan: {rel_output}")
    print(f"Imported packets: {len(summaries)}")
    print(f"Excluded untracked packets: {len(excluded_summaries)}")
    lint_command = f"<consumer-selected-python> -B <planveyor-runtime-root>/scripts/plan_lint.py {rel_output}"
    print(f"Validation: run `{lint_command}` from the target repo.")
    print("Queue hint: after validation exits 0, choose the actual Manager mode:")
    print(f"- native: `planveyor_q_set {rel_output} --for-manager-mode manager-collab`")
    print(f"- custom: `planveyor_q_set {rel_output} --for-manager-mode manager-custom-pipeline`")
    return 0


def _atomic_replace_carrier_payload(
    plan_path: Path,
    *,
    raw: bytes,
    payload_start: int,
    payload_end: int,
    payload: dict[str, object],
) -> None:
    original_payload = raw[payload_start:payload_end]
    if original_payload.endswith(b"\r\n"):
        line_ending = b"\r\n"
    elif original_payload.endswith(b"\n"):
        line_ending = b"\n"
    else:
        raise ValueError("structured carrier payload must end before a standalone end sentinel")
    rendered = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + line_ending
    replacement = raw[:payload_start] + rendered + raw[payload_end:]
    mode = stat.S_IMODE(plan_path.stat().st_mode)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{plan_path.name}.", suffix=".tmp", dir=plan_path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, plan_path)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def cmd_outcome_set(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    current_target_repo = _target_repo_from_root(repo_root)

    try:
        _ensure_target_local_adoption(repo_root, tooling_root, current_target_repo)
        plan_path, plan_rel = _resolve_direct_target_plan_path(repo_root, args.target_plan)
        raw = plan_path.read_bytes()
        carrier = _read_structured_carrier(
            raw,
            plan_rel=plan_rel,
            expected_target_repo=current_target_repo,
        )
        if carrier is None:
            raise ValueError("target plan has no structured rollout packet carrier")
        payload = carrier["payload"]
        if not isinstance(payload, dict):
            raise ValueError("structured carrier payload is invalid")
        outcomes_record = payload["rollout_packet_outcomes"]
        if not isinstance(outcomes_record, dict):
            raise ValueError("structured carrier outcomes object is invalid")
        items = outcomes_record["items"]
        if not isinstance(items, list):
            raise ValueError("structured carrier items are invalid")
        matches = [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("packet_id") == args.packet_id
            and item.get("packet_path") == args.packet_path
        ]
        if len(matches) != 1:
            raise ValueError("outcome-set requires exactly one matching packet id/path item")
        item = matches[0]
        canonical_outcome = _canonical_target_outcome(args.outcome)
        decision_state = item.get("decision_state")
        if decision_state == "recorded":
            if item.get("outcome") == canonical_outcome:
                print(f"Target plan: {plan_rel}")
                print(f"Packet id: {args.packet_id}")
                print(f"Packet path: {args.packet_path}")
                print(f"Outcome: {canonical_outcome}")
                print("Result: target outcome already recorded")
                return 0
            raise ValueError("outcome-set rejects a different second outcome for an already recorded packet")
        if decision_state != "pending" or item.get("outcome") is not None:
            raise ValueError("outcome-set requires one pending/null packet item")
        item["decision_state"] = "recorded"
        item["outcome"] = canonical_outcome
        _atomic_replace_carrier_payload(
            plan_path,
            raw=raw,
            payload_start=int(carrier["payload_start"]),
            payload_end=int(carrier["payload_end"]),
            payload=payload,
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    print(f"Target plan: {plan_rel}")
    print(f"Packet id: {args.packet_id}")
    print(f"Packet path: {args.packet_path}")
    print(f"Outcome: {canonical_outcome}")
    print("Result: target outcome recorded")
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    status = str(args.status).strip().lower()
    target_plan = None
    reason = str(args.reason).strip() if args.reason else None

    try:
        if status not in ACK_STATUSES:
            raise ValueError(f"unknown ack status `{args.status}`; expected one of: {', '.join(ACK_STATUSES)}")
        if status == "imported" and not args.target_plan:
            raise ValueError("imported ack requires --target-plan under docs/plans/")
        if status in {"superseded", "cancelled"} and not reason:
            raise ValueError(f"{status} ack requires --reason")
        if args.target_plan:
            target_plan = _validate_target_plan_path(args.target_plan)

        packet_path = _resolve_packet_path(repo_root, args.packet)
        packet = _parse_packet(packet_path)
        if _packet_status(packet) != "open" and _ack_matches_current_packet(
            packet,
            status=status,
            target_plan=target_plan,
            reason=reason,
        ):
            print(f"Source packet: {_repo_relative(packet_path, repo_root)}")
            print(f"Status: {status}")
            if target_plan:
                print(f"Target import receipt: {target_plan}")
                print(f"Target local plan: {target_plan}")
            if reason:
                print(f"Reason: {reason}")
            print("Result: source-side acknowledgement already recorded")
            return 0
        content = _render_ack_packet(
            packet,
            status=status,
            target_plan=target_plan,
            reason=reason,
            now=datetime.now(),
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    packet_path.write_text(content, encoding="utf-8")
    print(f"Source packet: {_repo_relative(packet_path, repo_root)}")
    print(f"Status: {status}")
    if target_plan:
        print(f"Target import receipt: {target_plan}")
        print(f"Target local plan: {target_plan}")
    if reason:
        print(f"Reason: {reason}")
    print("Result: source-side acknowledgement written")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    try:
        statuses = _query_status_filter(args.status)
        include_all_statuses = "all" in statuses
        summaries = _load_source_corpus(repo_root)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    rows = [
        _packet_query_row(summary)
        for summary in summaries
        if include_all_statuses or str(summary["status"]).lower() in statuses
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "repo_root": str(repo_root),
                    "statuses": sorted(statuses),
                    "count": len(rows),
                    "packets": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    status_label = "all" if include_all_statuses else "|".join(sorted(statuses))
    print("Rollout packet query")
    print(f"Source repo root: {repo_root}")
    print(f"Status filter: {status_label}")
    print(f"Matching packets: {len(rows)}")
    for idx, row in enumerate(rows, 1):
        print(
            "{idx:02d}. {path} id={id} target={target_repo} status={status} queue_after_import={queue}".format(
                idx=idx,
                path=row["packet_path"],
                id=row["id"],
                target_repo=row["target_repo"],
                status=row["status"],
                queue=str(row["queue_after_import"]).lower(),
            )
        )
        print(f"    target_adoption_state={row['target_adoption_state']}")
        print(f"    source_plan={row['source_plan']}")
        print(
            "    target_import_receipt={receipt} target_local_plan={plan}".format(
                receipt=row["target_import_receipt"] or "N/A",
                plan=row["target_local_plan"] or "N/A",
            )
        )
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    if not args.report:
        return _fail("reconcile currently supports --report only")
    if args.older_than_days < 0:
        return _fail("--older-than-days must be zero or greater")

    try:
        summaries = _load_source_corpus(repo_root)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _fail(str(exc))

    if bool(args.target_root) != bool(args.target_repo):
        return _fail("--target-root and --target-repo must be passed together for target readback reports")

    if args.target_root and args.target_repo:
        target_root = Path(args.target_root).resolve()
        target_repo = _normalize_repo_id(args.target_repo)
        rows = _target_reconcile_rows(
            summaries,
            repo_root=repo_root,
            target_root=target_root,
            target_repo=target_repo,
        )
        report_mode = "target-readback"
    else:
        target_root = None
        target_repo = None
        rows = _reconcile_rows(summaries, older_than_days=args.older_than_days, now=datetime.now())
        report_mode = "source-reconcile"
    bucket_counts: dict[str, int] = {}
    for row in rows:
        bucket = str(row["bucket"])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    if args.json:
        print(
            json.dumps(
                {
                    "repo_root": str(repo_root),
                    "mode": report_mode,
                    "older_than_days": args.older_than_days,
                    "target_root": str(target_root) if target_root else None,
                    "target_repo": target_repo,
                    "count": len(rows),
                    "buckets": bucket_counts,
                    "rows": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print("Rollout packet reconcile report")
    print(f"Source repo root: {repo_root}")
    print(f"Mode: {report_mode}")
    print(f"Older than days: {args.older_than_days}")
    if target_root and target_repo:
        print(f"Target repo root: {target_root}")
        print(f"Target repo: {target_repo}")
    print(f"Rows: {len(rows)}")
    if bucket_counts:
        print("Buckets:")
        for bucket in sorted(bucket_counts):
            print(f"  - {bucket}: {bucket_counts[bucket]}")
    for idx, row in enumerate(rows, 1):
        print(
            "{idx:02d}. bucket={bucket} packet={path} status={status} target={target_repo}".format(
                idx=idx,
                bucket=row["bucket"],
                path=row["packet_path"],
                status=row["status"],
                target_repo=row["target_repo"],
            )
        )
        print(f"    target_adoption_state={row['target_adoption_state']}")
        print(
            "    target_import_receipt={receipt} target_local_plan={plan} target_outcome={outcome}".format(
                receipt=row["target_import_receipt"] or "N/A",
                plan=row["target_local_plan"] or "N/A",
                outcome=row["target_outcome"] or "N/A",
            )
        )
        print(f"    message={row['message']}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    tooling_root = Path(args.tooling_root).resolve()
    _ensure_source_local(repo_root, tooling_root)

    packet_paths, findings = _lint_scope(repo_root, all_packets=bool(args.all), raw_paths=args.paths)
    files: list[dict[str, object]] = []
    strict_sections = not bool(args.all)
    for packet_path in packet_paths:
        try:
            file_entry, packet_findings = _lint_packet(packet_path, repo_root, strict_sections=strict_sections)
        except FileNotFoundError as exc:
            file_ref = _repo_relative(packet_path, repo_root)
            file_entry = {"path": file_ref, "status": "error"}
            packet_findings = [_lint_finding(file_ref, "error", "missing", str(exc))]
        files.append(file_entry)
        findings.extend(packet_findings)

    ok = not any(finding.get("severity") == "error" for finding in findings)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "repo_root": str(repo_root),
                    "files_checked": len(files),
                    "files": files,
                    "findings": findings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if ok else 1

    print(f"rollout-packet-lint: {'OK' if ok else 'FAIL'}")
    print(f"files checked: {len(files)}")
    print(f"findings: {len(findings)}")
    for finding in findings:
        print(
            "- {severity} {path}: {code}: {message}".format(
                severity=finding["severity"],
                path=finding["path"],
                code=finding["code"],
                message=finding["message"],
            )
        )
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rollout packet helper surfaces.")
    parser.add_argument("--repo-root", required=True, help="Current repo root where the helper operates.")
    parser.add_argument("--tooling-root", required=True, help="Canonical planveyor root for source-local guard.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a source-local rollout packet skeleton.")
    create_parser.add_argument("target_repo", help="Target repo id (for example: planveyor).")
    create_parser.add_argument("topic_slug", help="Packet topic slug.")
    create_parser.add_argument("--source-plan", help="Repo-relative source plan path. Defaults to .planveyor.planpath.")
    create_parser.add_argument(
        "--target-kind",
        default="plan_adoption",
        choices=TARGET_KINDS,
        help="Target repo action kind.",
    )
    create_parser.add_argument(
        "--queue-after-import",
        default="yes",
        choices=("yes", "no"),
        help="Packet-specific hint only; target repo decides after import.",
    )
    create_parser.add_argument("--dry-run", action="store_true", help="Print the packet instead of writing it.")
    create_parser.set_defaults(func=cmd_create)

    show_parser = subparsers.add_parser("show", help="Show a source-local rollout packet.")
    show_parser.add_argument("packet_path", help="Repo-relative packet path under docs/rollout_packets/.")
    show_parser.add_argument("--raw", action="store_true", help="Print raw packet content.")
    show_parser.set_defaults(func=cmd_show)

    import_parser = subparsers.add_parser(
        "import-instructions", help="Render target-local import instructions from an existing packet."
    )
    import_parser.add_argument("packet_path", help="Repo-relative packet path under docs/rollout_packets/.")
    import_parser.add_argument(
        "--print-target-plan-seed",
        action="store_true",
        help="Print a text-only target-local plan seed snippet.",
    )
    import_parser.set_defaults(func=cmd_import_instructions)

    inbox_parser = subparsers.add_parser(
        "inbox", help="List source packets addressed to the current target repo."
    )
    inbox_parser.add_argument("--target-repo", help="Target repo id. Defaults to current repo directory name.")
    inbox_parser.add_argument(
        "--status",
        action="append",
        help="Packet status to include. Defaults to open; pass --status all for every status.",
    )
    inbox_parser.add_argument("--json", action="store_true", help="Print machine-readable inbox JSON.")
    inbox_parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked source packet files in target-facing inbox output.",
    )
    inbox_parser.set_defaults(func=cmd_inbox)

    adoption_parser = subparsers.add_parser(
        "adoption-plan", help="Create a target-local adoption plan from matching source packets."
    )
    adoption_parser.add_argument("--target-repo", help="Target repo id. Defaults to current repo directory name.")
    adoption_parser.add_argument(
        "--status",
        action="append",
        help="Packet status to include. Defaults to open; pass --status all for every status.",
    )
    adoption_parser.add_argument("--out", help="Repo-relative output path under docs/plans/.")
    adoption_parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked source packet files in generated target-local adoption plan.",
    )
    adoption_parser.set_defaults(func=cmd_adoption_plan)

    outcome_set_parser = subparsers.add_parser(
        "outcome-set", help="Record one target-local rollout packet outcome in a structured carrier."
    )
    outcome_set_parser.add_argument(
        "--target-plan",
        required=True,
        help="Existing direct repo-relative target plan path under docs/plans/.",
    )
    outcome_set_parser.add_argument("--packet-id", required=True, help="Exact source rollout packet id.")
    outcome_set_parser.add_argument(
        "--packet-path", required=True, help="Exact source packet path under docs/rollout_packets/."
    )
    outcome_set_parser.add_argument("--outcome", required=True, help="Canonical outcome or documented alias.")
    outcome_set_parser.set_defaults(func=cmd_outcome_set)

    ack_parser = subparsers.add_parser("ack", help="Acknowledge a source-local rollout packet status transition.")
    ack_parser.add_argument("--packet", required=True, help="Repo-relative packet path under docs/rollout_packets/.")
    ack_parser.add_argument("--status", required=True, help="Ack status: imported, superseded, or cancelled.")
    ack_parser.add_argument(
        "--target-plan",
        help="Repo-relative target-local adoption plan/import receipt path under docs/plans/.",
    )
    ack_parser.add_argument("--reason", help="Required for superseded or cancelled acknowledgements.")
    ack_parser.set_defaults(func=cmd_ack)

    query_parser = subparsers.add_parser("query", help="List source-local rollout packets by explicit fields.")
    query_parser.add_argument(
        "--status",
        action="append",
        help="Packet status to include. Defaults to all; pass more than once for multiple statuses.",
    )
    query_parser.add_argument("--json", action="store_true", help="Print machine-readable query JSON.")
    query_parser.set_defaults(func=cmd_query)

    reconcile_parser = subparsers.add_parser(
        "reconcile", help="Report stale or inconsistent source-local rollout packets."
    )
    reconcile_parser.add_argument("--report", action="store_true", help="Print read-only reconcile report.")
    reconcile_parser.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="Age threshold for stale_open packets. Defaults to 7.",
    )
    reconcile_parser.add_argument(
        "--target-root",
        help="Read-only target repo root for report-only target receipt/readback classification.",
    )
    reconcile_parser.add_argument(
        "--target-repo",
        help="Target repo id for report-only target receipt/readback classification.",
    )
    reconcile_parser.add_argument("--json", action="store_true", help="Print machine-readable report JSON.")
    reconcile_parser.set_defaults(func=cmd_reconcile)

    lint_parser = subparsers.add_parser("lint", help="Read-only grammar lint for source-local rollout packets.")
    lint_parser.add_argument(
        "paths",
        nargs="*",
        metavar="PACKET_OR_DIR",
        help="Repo-relative packet file or directory under docs/rollout_packets/.",
    )
    lint_parser.add_argument("--all", action="store_true", help="Lint the checked-in source packet corpus.")
    lint_parser.add_argument("--json", action="store_true", help="Print machine-readable lint JSON.")
    lint_parser.set_defaults(func=cmd_lint)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

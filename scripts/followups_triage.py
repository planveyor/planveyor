#!/usr/bin/env python3
"""Post-harvest follow-ups triage/import into cluster master backlogs.

Flow:
1) Collect inbox followups files from a git range (or scan all inbox files).
2) Parse follow-up items from inbox files.
3) Route items by `cluster` to master backlogs using `docs/followups/index.md`.
4) Best-effort dedup in master files:
   - exact duplicate => merge `sources=[...]`
   - likely duplicate => report only
   - distinct => append new item to master
5) In apply mode, mark fully imported inbox files with `**Imported into:** ...`.

This tool is deterministic and idempotent for repeated `--apply` runs
on the same range/input set.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull


def _authority_module() -> Any:
    """Import the sibling authority parser without consulting a target package."""

    expected = Path(__file__).resolve().with_name("contract_authority_context.py")
    loaded = [
        sys.modules[name]
        for name in ("contract_authority_context", "scripts.contract_authority_context")
        if name in sys.modules
    ]
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str) or Path(origin).resolve(strict=True) != expected:
            raise ImportError("authority module has an unsafe origin")
    if len({id(module) for module in loaded}) > 1:
        raise ImportError("authority module aliases are split")
    if loaded:
        return loaded[0]
    script_dir = str(expected.parent)
    while script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    return importlib.import_module("contract_authority_context")

_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import (
        ContractAuthorityError,
        ContractContext,
        context_for_reader,
        read_declared_text,
        validate_before_effect,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    read_declared_text = _authority.read_declared_text
    validate_before_effect = _authority.validate_before_effect
import followups_capture
import followups_lint


# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
FOLLOWUPS_DIR = REPO_ROOT / "docs" / "followups"
FOLLOWUPS_INDEX = FOLLOWUPS_DIR / "index.md"
FOLLOWUPS_TEMPLATE = FOLLOWUPS_DIR / "_template_followups_backlog.md"

DEFAULT_CLUSTER = "process"
CLUSTER_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

ITEM_RE = re.compile(r"^\s*-\s*(?P<prio>P[0-9?])\s+\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$")
STATUS_RE = re.compile(r"^\s*\*\*Status:\*\*\s*(?P<value>.+?)\s*$")
SECTION_H2_RE = re.compile(r"^\s*##\s+")
HEADER_RE = re.compile(r"^\s*#\s+")

INDEX_ROW_FILE_RE = re.compile(r"`(?P<path>docs/followups/[^`]+\.md)`")
INDEX_ROW_CLUSTERS_RE = re.compile(r"clusters\s*=\s*(?P<clusters>[A-Za-z0-9_, -]+)")

SOURCE_FILE_IGNORE = {"README.md", "index.md", "_template_followups_backlog.md"}


@dataclass(frozen=True)
class FollowupItem:
    source_path: str
    source_line: int
    priority: str
    body: str
    summary: str
    cluster_raw: str | None
    cluster_norm: str | None
    authority_source_ref: str | None
    is_v2: bool = False
    item_id: str | None = None

    @property
    def source_ref(self) -> str:
        return f"{self.source_path}:{self.source_line}"

    @property
    def source_key(self) -> str:
        # Keep exact provenance (path + line) for traceability.
        return self.source_ref


@dataclass(frozen=True)
class MasterItem:
    line_index: int
    body: str
    summary: str
    cluster_norm: str | None
    authority_source_ref: str | None


@dataclass(frozen=True)
class Action:
    kind: str
    source_ref: str
    source_file: str
    master_path: str
    summary: str
    note: str = ""


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _read_text(path: Path) -> str:
    absolute = path.absolute()
    try:
        rel_path = absolute.relative_to(REPO_ROOT.absolute()).as_posix()
    except ValueError:
        return path.read_text(encoding="utf-8", errors="replace")
    if rel_path.startswith("docs/followups/") and len(Path(rel_path).parts) == 3:
        from followups_capture import read_followup_path

        _object, data = read_followup_path(REPO_ROOT.absolute(), rel_path)
        return data.decode("utf-8", errors="strict")
    return path.read_text(encoding="utf-8", errors="replace")


def _before_write(path: Path, context: ContractContext | None) -> ContractContext:
    ctx = context_for_reader(REPO_ROOT, context)
    if not path.resolve().is_relative_to(ctx.project_root):
        raise ContractAuthorityError("triage_output_root_mismatch", "triage output is outside the captured project")
    validate_before_effect(ctx)
    return ctx


def _write_text(path: Path, text: str, context: ContractContext | None = None) -> None:
    _before_write(path, context)
    path.write_text(text, encoding="utf-8")


def _cluster_vocabulary(context: ContractContext) -> tuple[frozenset[str] | None, dict[str, str]]:
    if context.state == "legacy":
        return None, {}
    try:
        clusters = json.loads(read_declared_text(context, "docs/_meta/plan_vocab.json"))["clusters"]
        canonical = clusters["canonical"]
        aliases = clusters.get("deprecated_aliases", {})
        if (not isinstance(canonical, list) or not canonical
                or any(not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", value) for value in canonical)
                or len(set(canonical)) != len(canonical) or not isinstance(aliases, dict)):
            raise ValueError("invalid cluster vocabulary")
        for alias, target in aliases.items():
            if (not isinstance(alias, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", alias)
                    or alias in canonical or not isinstance(target, str) or target not in canonical):
                raise ValueError("invalid cluster alias")
        return frozenset(canonical), aliases
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractAuthorityError("triage_vocabulary_invalid", "target cluster vocabulary is malformed") from exc


def _split_tokens(body: str) -> tuple[str, list[str]]:
    if " — " in body:
        parts = [p.strip() for p in body.split(" — ")]
    elif " - " in body:
        parts = [p.strip() for p in body.split(" - ")]
    else:
        parts = [body.strip()]
    summary = parts[0] if parts else body.strip()
    tokens = parts[1:] if len(parts) > 1 else []
    return summary, tokens


def _join_tokens(summary: str, tokens: list[str]) -> str:
    if not tokens:
        return summary.strip()
    return " — ".join([summary.strip(), *[t.strip() for t in tokens if t.strip()]])


def _token_key(token: str) -> str | None:
    t = token.strip()
    if not t:
        return None
    if t.lower().startswith("why:"):
        return "why"
    if "=" in t:
        key = t.split("=", 1)[0].strip().lower()
        if re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            return key
    return None


def _normalize_scalar(value: str) -> str:
    v = value.strip().strip("`").strip().strip("'").strip('"').strip()
    return v


def _extract_field(body: str, key: str) -> str | None:
    _, tokens = _split_tokens(body)
    want = key.lower()
    for token in tokens:
        tkey = _token_key(token)
        if tkey != want:
            continue
        if want == "why":
            return token.split(":", 1)[1].strip() if ":" in token else ""
        if "=" in token:
            return token.split("=", 1)[1].strip()
    return None


def _upsert_field(body: str, key: str, value: str) -> str:
    summary, tokens = _split_tokens(body)
    want = key.lower()
    repl = f"{want}={value}" if want != "why" else f"why: {value}"
    for i, token in enumerate(tokens):
        if _token_key(token) == want:
            tokens[i] = repl
            return _join_tokens(summary, tokens)
    tokens.append(repl)
    return _join_tokens(summary, tokens)


def _parse_sources(value: str | None) -> list[str]:
    if value is None:
        return []
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    out: list[str] = []
    for part in raw.split(","):
        v = _normalize_scalar(part)
        if v:
            out.append(v)
    return out


def _format_sources(values: Iterable[str]) -> str:
    uniq = sorted({v.strip() for v in values if v and v.strip()})
    inner = ", ".join(f'"{v}"' for v in uniq)
    return f"[{inner}]"


def _merge_source(body: str, source_ref: str) -> str:
    current = _parse_sources(_extract_field(body, "sources"))
    if source_ref in current:
        return body
    current.append(source_ref)
    return _upsert_field(body, "sources", _format_sources(current))


def _merge_sources(body: str, extra_sources: Iterable[str]) -> str:
    merged = set(_parse_sources(_extract_field(body, "sources")))
    for src in extra_sources:
        if not src:
            continue
        v = src.strip()
        if v:
            merged.add(v)
    return _upsert_field(body, "sources", _format_sources(merged))


def _normalize_cluster(value: str | None) -> str | None:
    if not value:
        return None
    v = _normalize_scalar(value).lower().replace(" ", "")
    return v or None


def _legacy_cluster_or_default(value: str | None) -> tuple[str, bool]:
    if value and CLUSTER_SLUG_RE.fullmatch(value):
        return value, False
    return DEFAULT_CLUSTER, True


def _legacy_routed_cluster(value: str | None, routing: dict[str, str]) -> tuple[str, bool]:
    cluster, used_fallback = _legacy_cluster_or_default(value)
    if not used_fallback and cluster != DEFAULT_CLUSTER and cluster not in routing:
        return DEFAULT_CLUSTER, True
    return cluster, used_fallback


def _normalize_summary(summary: str) -> str:
    text = summary.lower()
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _summary_tokens(summary: str) -> set[str]:
    parts = re.findall(r"[0-9a-zа-яё]+", summary.lower())
    return {p for p in parts if len(p) > 2}


def _similarity(a: str, b: str) -> float:
    ta = _summary_tokens(a)
    tb = _summary_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    denom = max(len(ta), len(tb))
    return inter / float(denom)


def _parse_item_body(body: str) -> tuple[str, str | None]:
    summary, _ = _split_tokens(body)
    cluster_raw = _extract_field(body, "cluster")
    return summary, cluster_raw


def _parse_followup_items(path: Path) -> tuple[list[FollowupItem], int]:
    lines = _read_text(path).splitlines()
    is_v2 = any(line.strip().lower() == "**schema version:** followups.v2" for line in lines[:80])
    items: list[FollowupItem] = []
    unparsed_bullets = 0
    in_followups = False
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.lower().startswith("## follow-ups"):
            in_followups = True
            continue
        if in_followups and SECTION_H2_RE.match(line):
            break
        if not in_followups:
            continue
        m = ITEM_RE.match(line)
        if not m:
            if line.startswith("- "):
                unparsed_bullets += 1
            continue
        body = m.group("body").strip()
        summary, cluster_raw = _parse_item_body(body)
        items.append(
            FollowupItem(
                source_path=path.relative_to(REPO_ROOT).as_posix(),
                source_line=idx,
                priority=m.group("prio"),
                body=body,
                summary=summary,
                cluster_raw=cluster_raw,
                cluster_norm=_normalize_cluster(cluster_raw),
                authority_source_ref=(
                    _normalize_scalar(_extract_field(body, "source_ref"))
                    if _extract_field(body, "source_ref")
                    else None
                ),
                is_v2=is_v2,
                item_id=(
                    _normalize_scalar(_extract_field(body, "item_id"))
                    if _extract_field(body, "item_id")
                    else None
                ),
            )
        )
    return items, unparsed_bullets


def _parse_master_items(lines: list[str]) -> list[MasterItem]:
    out: list[MasterItem] = []
    in_followups = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("## follow-ups"):
            in_followups = True
            continue
        if in_followups and SECTION_H2_RE.match(line):
            break
        if not in_followups:
            continue
        m = ITEM_RE.match(line)
        if not m:
            continue
        body = m.group("body").strip()
        summary, cluster_raw = _parse_item_body(body)
        out.append(
            MasterItem(
                line_index=idx,
                body=body,
                summary=summary,
                cluster_norm=_normalize_cluster(cluster_raw),
                authority_source_ref=(
                    _normalize_scalar(_extract_field(body, "source_ref"))
                    if _extract_field(body, "source_ref")
                    else None
                ),
            )
        )
    return out


def _collect_inbox_files(git_range: str) -> list[Path]:
    out = _run_git(["diff", "--name-only", git_range, "--", "docs/followups"])
    files: set[Path] = set()
    for raw in out.splitlines():
        rel = raw.strip()
        if not rel.endswith(".md"):
            continue
        p = Path(rel)
        if p.name in SOURCE_FILE_IGNORE:
            continue
        if p.name.endswith("_master.md"):
            continue
        abs_path = REPO_ROOT / rel
        if abs_path.exists():
            files.add(abs_path)
    return sorted(files)


def _is_fully_imported_inbox(path: Path) -> bool:
    """Return True when file is already safe-to-delete per policy.

    Keep it intentionally conservative: require both markers.
    """
    head = _read_text(path).splitlines()[:80]
    has_done = any(line.strip() == "**Status:** ✅ Done" for line in head)
    has_imported = any(
        line.strip().startswith("**Imported into:**") and _parse_imported_refs(line)
        for line in head
    )
    return has_done and has_imported


def _collect_inbox_files_all() -> list[Path]:
    files: list[Path] = []
    for abs_path in sorted(FOLLOWUPS_DIR.glob("*.md")):
        if abs_path.name in SOURCE_FILE_IGNORE:
            continue
        if abs_path.name.endswith("_master.md"):
            continue
        # Skip already fully imported inbox files to avoid churn.
        if _is_fully_imported_inbox(abs_path):
            continue
        files.append(abs_path)
    return files


def _collect_inbox_files_explicit(raw_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        if not raw or not raw.strip():
            raise ValueError("empty --file path")
        path = Path(raw.strip())
        abs_path = path if path.is_absolute() else REPO_ROOT / path
        # Keep the lexical direct-child pathname. Resolving here would turn an
        # in-tree symlink into a trusted regular-file alias before the shared
        # no-follow reader gets a chance to reject it.
        abs_path = abs_path.absolute()
        try:
            rel_path = abs_path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise ValueError(f"--file must stay inside repo root: {raw}") from exc
        if rel_path.parts[:2] != ("docs", "followups"):
            raise ValueError(f"--file must point into docs/followups: {raw}")
        try:
            followups_capture.validate_followup_relpath(rel_path.as_posix())
        except followups_capture.CaptureError as exc:
            raise ValueError(f"--file must be a direct followups carrier: {raw}") from exc
        if abs_path.name in SOURCE_FILE_IGNORE or abs_path.name.endswith("_master.md"):
            raise ValueError(f"--file must be an inbox followups file, not {rel_path.as_posix()}")
        if abs_path.suffix != ".md":
            raise ValueError(f"--file must be markdown: {raw}")
        if not os.path.lexists(abs_path):
            raise ValueError(f"--file does not exist: {rel_path.as_posix()}")
        if abs_path not in seen:
            files.append(abs_path)
            seen.add(abs_path)
    return files


def _load_cluster_routing(
    index_path: Path, *, canonical: frozenset[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> dict[str, str]:
    if not index_path.exists():
        return {}
    routing: dict[str, str] = {}
    for line in _read_text(index_path).splitlines():
        if not line.strip().startswith("|"):
            continue
        m_file = INDEX_ROW_FILE_RE.search(line)
        m_clusters = INDEX_ROW_CLUSTERS_RE.search(line)
        if not m_file or not m_clusters:
            continue
        rel = m_file.group("path").strip()
        raw_clusters = m_clusters.group("clusters")
        for part in raw_clusters.split(","):
            cluster = _normalize_cluster(part)
            if canonical is not None:
                cluster = (aliases or {}).get(cluster or "", cluster)
                if cluster not in canonical:
                    raise ContractAuthorityError("triage_route_unknown", "routing key is absent from target vocabulary")
                relative = Path(rel)
                if (relative.parts[:2] != ("docs", "followups") or len(relative.parts) != 3
                        or ".." in relative.parts or not (REPO_ROOT / relative).resolve().is_relative_to(REPO_ROOT)):
                    raise ContractAuthorityError("triage_route_path_invalid", "routing destination must be a project followups file")
                if cluster in routing and routing[cluster] != rel:
                    raise ContractAuthorityError("triage_route_ambiguous", "cluster has conflicting routing destinations")
            if not cluster:
                continue
            routing.setdefault(cluster, rel)
    return routing


def _new_master_relpath(cluster: str) -> str:
    ts = datetime.now().strftime("%y%m%d_%H%M")
    safe_cluster = re.sub(r"[^a-z0-9_]+", "_", cluster.lower())
    return f"docs/followups/{ts}_{safe_cluster}_followups_master.md"


def _render_master_template(cluster: str) -> str:
    now = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M %z")
    cluster_title = cluster.capitalize()
    return (
        f"# Follow-ups backlog — {cluster_title} (master)\n\n"
        f"**Date:** {now}  \n"
        "**Source:** triage/import  \n"
        "**Status:** Draft  \n\n"
        "Зачем этот файл: хранить единый backlog по кластеру и снижать дубли из range/memory inbox.\n\n"
        "## Context / inputs (optional)\n"
        f"- Routing key: `cluster={cluster}`\n"
        "- Created by: `scripts/followups_triage.py`\n\n"
        "## Follow-ups (backlog)\n"
        "Формат:\n"
        "`P? [ ] <summary> — cluster=<...> — tags=<...> — to=<...> — status=<open|promoted|handled|UNCONFIRMED> — plan=<...|null> — why: ...`\n\n"
        "## Notes\n"
        "- Auto-created cluster master backlog.\n"
    )


def _append_index_row(index_path: Path, relpath: str, cluster: str, context: ContractContext | None = None) -> bool:
    text = _read_text(index_path) if index_path.exists() else ""
    needle = f"`{relpath}`"
    if needle in text:
        return False
    row = f"| `{relpath}` | {cluster.capitalize()} | master backlog (auto-created by followups triage); clusters={cluster} |"
    if text and not text.endswith("\n"):
        text += "\n"
    text += row + "\n"
    _write_text(index_path, text, context)
    return True


def _ensure_master_file(path: Path, cluster: str, context: ContractContext | None = None) -> None:
    if path.exists():
        return
    ctx = _before_write(path, context)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(path, _render_master_template(cluster), ctx)


def _find_exact_duplicate(master_items: list[MasterItem], item: FollowupItem, cluster: str) -> MasterItem | None:
    n_item = _normalize_summary(item.summary)
    for existing in master_items:
        if existing.cluster_norm != cluster:
            continue
        if _normalize_summary(existing.summary) == n_item:
            return existing
    return None


def _find_possible_duplicate(master_items: list[MasterItem], item: FollowupItem, cluster: str) -> tuple[MasterItem | None, float]:
    best_item: MasterItem | None = None
    best_score = 0.0
    for existing in master_items:
        if existing.cluster_norm != cluster:
            continue
        score = _similarity(existing.summary, item.summary)
        if score > best_score:
            best_score = score
            best_item = existing
    if best_score >= 0.75:
        return best_item, best_score
    return None, 0.0


def _append_to_followups_section(lines: list[str], item_line: str) -> list[str]:
    out = list(lines)
    start_idx = -1
    for i, line in enumerate(out):
        if line.strip().lower().startswith("## follow-ups"):
            start_idx = i
            break
    if start_idx < 0:
        if out and out[-1].strip():
            out.append("")
        out.append("## Follow-ups (backlog)")
        out.append(item_line)
        out.append("")
        return out

    insert_at = len(out)
    for i in range(start_idx + 1, len(out)):
        if SECTION_H2_RE.match(out[i]):
            insert_at = i
            break
    out.insert(insert_at, item_line)
    return out


def _prepare_new_body(
    item: FollowupItem, target_cluster: str, *, canonical: frozenset[str] | None = None,
    legacy_fallback: bool = False,
) -> tuple[str, bool]:
    body = item.body
    used_fallback = legacy_fallback
    if canonical is not None and target_cluster not in canonical:
        raise ContractAuthorityError("triage_cluster_unknown", "source cluster is absent from target vocabulary")
    body = _upsert_field(body, "cluster", target_cluster)
    status = _extract_field(body, "status")
    if used_fallback:
        body = _upsert_field(body, "status", "UNCONFIRMED")
    elif not status:
        body = _upsert_field(body, "status", "open")
    body = _merge_source(body, item.source_key)
    return body, used_fallback


def _merge_sources_in_master_line(line: str, extra_sources: Iterable[str]) -> tuple[str, bool]:
    m = ITEM_RE.match(line)
    if not m:
        return line, False
    old_body = m.group("body").strip()
    new_body = _merge_sources(old_body, extra_sources)
    if new_body == old_body:
        return line, False
    new_line = f"- {m.group('prio')} [{m.group('mark')}] {new_body}"
    return new_line, True


def _parse_imported_refs(line: str) -> list[str]:
    tail = line.split(":", 1)[1] if ":" in line else line
    tail = tail.strip()
    normalized_tail = tail.strip("`").strip()
    if normalized_tail.upper().startswith("N/A"):
        return []

    refs = re.findall(r"`(docs/followups/[^`]+\.md)`", tail)
    out = [r.strip() for r in refs if r.strip()]
    if out:
        return out
    # Fallback for legacy non-backtick formatting.
    vals = []
    for part in tail.split(","):
        v = _normalize_scalar(part)
        if v.upper().startswith("N/A"):
            continue
        if not v.startswith("docs/followups/") or not v.endswith(".md"):
            continue
        vals.append(v)
    return vals


def _mark_inbox_imported(path: Path, imported_into: list[str], context: ContractContext | None = None) -> bool:
    if not path.exists():
        return False
    lines = _read_text(path).splitlines()
    changed = False

    status_idx = -1
    for i, line in enumerate(lines):
        if STATUS_RE.match(line):
            status_idx = i
            break
    if status_idx >= 0 and lines[status_idx].strip() != "**Status:** ✅ Done":
        lines[status_idx] = "**Status:** ✅ Done"
        changed = True
    if status_idx < 0:
        # Legacy inbox files might miss the Status header.
        # Insert it in the metadata block so "Done + Imported into" skip rule works.
        insert_status_at = 1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("**Date:**"):
                insert_status_at = i + 1
            if stripped.startswith("**Source:**"):
                insert_status_at = i + 1
                break
        lines.insert(insert_status_at, "**Status:** ✅ Done")
        status_idx = insert_status_at
        changed = True

    imported_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("**Imported into:**"):
            imported_idx = i
            break

    merged_refs = sorted(set(imported_into))
    if imported_idx >= 0:
        existing = _parse_imported_refs(lines[imported_idx])
        merged_refs = sorted(set(existing) | set(merged_refs))
        new_line = "**Imported into:** " + ", ".join(f"`{r}`" for r in merged_refs)
        if lines[imported_idx] != new_line:
            lines[imported_idx] = new_line
            changed = True
    else:
        new_line = "**Imported into:** " + ", ".join(f"`{r}`" for r in merged_refs)
        insert_at = status_idx + 1 if status_idx >= 0 else 1
        lines.insert(insert_at, new_line)
        changed = True

    if changed:
        _write_text(path, "\n".join(lines).rstrip() + "\n", context)
    return changed


def _render_report(
    *,
    mode: str,
    git_range: str,
    inbox_files: list[Path],
    items_count: int,
    created_masters: list[str],
    created_index_rows: list[str],
    actions: list[Action],
    unresolved_by_file: dict[str, int],
    parse_issues_by_file: dict[str, int],
    imported_targets: dict[str, set[str]],
    applied_files: list[str],
) -> str:
    counts = defaultdict(int)
    for a in actions:
        counts[a.kind] += 1

    lines: list[str] = []
    lines.append(f"followups_triage mode={mode}")
    lines.append(f"range={git_range}")
    lines.append(f"inbox_files={len(inbox_files)} items={items_count}")
    lines.append("")
    lines.append("action_counts:")
    for key in ("append_new", "merge_source", "possible_duplicate", "route_fallback", "v2_declaration_required"):
        lines.append(f"- {key}: {counts.get(key, 0)}")

    if created_masters:
        lines.append("")
        lines.append("created_master_backlogs:")
        for p in sorted(created_masters):
            lines.append(f"- {p}")

    if created_index_rows:
        lines.append("")
        lines.append("index_rows_added:")
        for p in sorted(created_index_rows):
            lines.append(f"- {p}")

    if actions:
        lines.append("")
        lines.append("actions:")
        for a in actions:
            note = f" ({a.note})" if a.note else ""
            lines.append(f"- {a.kind}: {a.source_ref} -> {a.master_path}{note} :: {a.summary}")

    lines.append("")
    lines.append("inbox_import_status:")
    if not inbox_files:
        lines.append("- (none)")
    for src in sorted({p.relative_to(REPO_ROOT).as_posix() for p in inbox_files}):
        unresolved = unresolved_by_file.get(src, 0)
        parse_issues = parse_issues_by_file.get(src, 0)
        imported = sorted(imported_targets.get(src, set()))
        if unresolved > 0 or parse_issues > 0:
            reasons: list[str] = []
            if unresolved > 0:
                reasons.append(f"possible_duplicates={unresolved}")
            if parse_issues > 0:
                reasons.append(f"unparsed_bullets={parse_issues}")
            lines.append(f"- {src}: pending ({'; '.join(reasons)}; keep inbox file for manual triage)")
        elif imported:
            lines.append(f"- {src}: imported -> {', '.join(imported)}")
        else:
            lines.append(f"- {src}: no actionable items parsed")

    if mode == "apply":
        lines.append("")
        lines.append("applied_file_changes:")
        if applied_files:
            for p in sorted(set(applied_files)):
                lines.append(f"- {p}")
        else:
            lines.append("- none (idempotent/no-op)")

    return "\n".join(lines) + "\n"


def _require_legacy_apply_inventory():
    """Keep legacy triage writes outside every explicit V2 integrity blocker."""

    try:
        snapshot, file_bytes = followups_capture.snapshot_followups(REPO_ROOT, include_bytes=True)
    except followups_capture.CaptureError as exc:
        raise RuntimeError(f"follow-ups snapshot is unsafe: {exc}") from exc
    inventory = followups_lint._inventory_followups_snapshot(REPO_ROOT, snapshot, file_bytes)
    if inventory.blockers:
        codes = ", ".join(sorted({finding.code for finding in inventory.blockers}))
        raise RuntimeError(f"follow-ups V2 integrity blocker: {codes}")
    return inventory


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Triage/import followups into cluster master backlogs.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--range", dest="git_range", help="Git range BASE..HEAD")
    src.add_argument("--all", action="store_true", help="Scan all inbox followups in docs/followups (skip imported)")
    src.add_argument("--file", dest="file_paths", action="append", help="Explicit post-harvest inbox file to import; can be repeated")
    parser.add_argument("--db", default=".tmp/planveyor_docs_index.sqlite", help="Optional retrieval DB path (reserved)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print report only (default mode)")
    mode.add_argument("--apply", action="store_true", help="Apply changes to docs/followups/*")
    return parser


def main(
    argv: list[str], *, project_root: Path | None = None, context: ContractContext | None = None,
) -> int:
    # Preserve the legacy helpers' module paths only for this invocation.  A
    # subsequent imported call captures its own explicit root or current cwd.
    global REPO_ROOT, FOLLOWUPS_DIR, FOLLOWUPS_INDEX, FOLLOWUPS_TEMPLATE
    previous = REPO_ROOT, FOLLOWUPS_DIR, FOLLOWUPS_INDEX, FOLLOWUPS_TEMPLATE
    try:
        requested_root = project_root or (context.project_root if isinstance(context, ContractContext) else Path.cwd())
        ctx = context_for_reader(requested_root, context)
        REPO_ROOT = ctx.project_root
        FOLLOWUPS_DIR = REPO_ROOT / "docs" / "followups"
        FOLLOWUPS_INDEX = FOLLOWUPS_DIR / "index.md"
        FOLLOWUPS_TEMPLATE = FOLLOWUPS_DIR / "_template_followups_backlog.md"
        return _main(argv, ctx)
    except ContractAuthorityError as exc:
        print(f"ERROR: {exc.reason_code}: {exc}", file=sys.stderr)
        return 2
    finally:
        REPO_ROOT, FOLLOWUPS_DIR, FOLLOWUPS_INDEX, FOLLOWUPS_TEMPLATE = previous


def _main(argv: list[str], context: ContractContext) -> int:
    args = _build_arg_parser().parse_args(argv)
    canonical, aliases = _cluster_vocabulary(context)
    engaged = context.state == "engaged"
    mode = "apply" if args.apply else "dry-run"
    if args.all:
        git_range = "ALL"
        inbox_files = _collect_inbox_files_all()
    elif args.file_paths:
        git_range = "FILES"
        try:
            inbox_files = _collect_inbox_files_explicit(args.file_paths)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        git_range = (args.git_range or "").strip()
        if ".." not in git_range:
            print(f"ERROR: invalid range: {git_range}", file=sys.stderr)
            return 2
        inbox_files = _collect_inbox_files(git_range)
    inventory = None
    if mode == "apply":
        try:
            inventory = _require_legacy_apply_inventory()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    all_items: list[FollowupItem] = []
    parse_issues_by_file: dict[str, int] = defaultdict(int)
    for path in inbox_files:
        parsed_items, parse_issues = _parse_followup_items(path)
        all_items.extend(parsed_items)
        if parse_issues > 0:
            rel_path = path.relative_to(REPO_ROOT).as_posix()
            parse_issues_by_file[rel_path] += parse_issues

    routing = _load_cluster_routing(FOLLOWUPS_INDEX, canonical=canonical if engaged else None, aliases=aliases)
    if engaged:
        # Validate the entire requested batch before the first write.  In this
        # mode neither a missing cluster nor a missing route creates a fallback.
        from dataclasses import replace

        normalized_items = []
        for item in all_items:
            cluster = aliases.get(item.cluster_norm or "", item.cluster_norm)
            if cluster not in canonical:
                raise ContractAuthorityError("triage_cluster_unknown", "source cluster is absent from target vocabulary")
            if cluster not in routing:
                raise ContractAuthorityError("triage_route_missing", "source cluster has no target route")
            normalized_items.append(replace(item, cluster_norm=cluster))
        all_items = normalized_items
    if mode == "apply":
        assert inventory is not None
        # Direct legacy mutation is compatibility-only.  Resolve every
        # selected legacy item before any master/index/source write so a later
        # V2 destination cannot leave an earlier legacy item partially
        # imported.  V2 inbox rows remain read-only declaration candidates.
        try:
            for item in all_items:
                if item.is_v2:
                    continue
                if item.source_path not in inventory.legacy_v1:
                    raise RuntimeError(
                        f"legacy_triage_source_not_legacy_v1: {item.source_path}"
                    )
                target_cluster = item.cluster_norm or ""
                if not engaged:
                    target_cluster, _ = _legacy_routed_cluster(item.cluster_norm, routing)
                master_rel = routing.get(target_cluster)
                if master_rel in inventory.valid_v2:
                    raise RuntimeError(
                        "legacy_triage_v2_destination_requires_apply: "
                        f"{item.source_path} -> {master_rel}"
                    )
                if not master_rel or master_rel not in inventory.legacy_v1:
                    raise RuntimeError(
                        "legacy_triage_destination_not_legacy_v1: "
                        f"{item.source_path} -> {master_rel or target_cluster}"
                    )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    created_masters: list[str] = []
    created_index_rows: list[str] = []
    actions: list[Action] = []
    unresolved_by_file: dict[str, int] = defaultdict(int)
    imported_targets: dict[str, set[str]] = defaultdict(set)
    applied_files: list[str] = []

    masters_cache: dict[str, list[str]] = {}
    masters_original: dict[str, str] = {}

    def load_master_lines(rel_path: str, fallback_cluster: str) -> list[str]:
        if rel_path in masters_cache:
            return masters_cache[rel_path]
        abs_path = REPO_ROOT / rel_path
        if abs_path.exists():
            text = _read_text(abs_path)
            masters_original[rel_path] = text
            lines = text.splitlines()
        else:
            masters_original[rel_path] = ""
            lines = _render_master_template(fallback_cluster).splitlines()
        masters_cache[rel_path] = lines
        return lines

    for item in all_items:
        if item.is_v2:
            # A V2 row is already a source-bound request candidate.  Triage is
            # not allowed to copy it into another durable carrier or alter its
            # fields; Manager must freeze declarations and call the one writer.
            unresolved_by_file[item.source_path] += 1
            actions.append(
                Action(
                    kind="v2_declaration_required",
                    source_ref=item.source_ref,
                    source_file=item.source_path,
                    master_path="(followups_apply.v2 required)",
                    summary=item.summary,
                    note=(
                        f"source_ref={item.authority_source_ref or 'missing'};"
                        f"item_id={item.item_id or 'missing'}"
                    ),
                )
            )
            continue
        target_cluster = item.cluster_norm or ""
        used_legacy_fallback = False
        if not engaged:
            target_cluster, used_legacy_fallback = _legacy_routed_cluster(item.cluster_norm, routing)
            if used_legacy_fallback:
                actions.append(
                    Action(
                        kind="route_fallback",
                        source_ref=item.source_ref,
                        source_file=item.source_path,
                        master_path="(pending route)",
                        summary=item.summary,
                        note="cluster fallback to process",
                    )
                )

        master_rel = routing.get(target_cluster)
        if not master_rel:
            master_rel = _new_master_relpath(target_cluster)
            routing[target_cluster] = master_rel
            created_masters.append(master_rel)
            if mode == "apply":
                _ensure_master_file(REPO_ROOT / master_rel, target_cluster, context)
                if _append_index_row(FOLLOWUPS_INDEX, master_rel, target_cluster, context):
                    created_index_rows.append(master_rel)
                    applied_files.append(FOLLOWUPS_INDEX.relative_to(REPO_ROOT).as_posix())
                applied_files.append(master_rel)

        master_lines = load_master_lines(master_rel, target_cluster)
        master_items = _parse_master_items(master_lines)

        same_authority = [
            candidate
            for candidate in master_items
            if item.authority_source_ref
            and candidate.authority_source_ref == item.authority_source_ref
        ]
        if same_authority and not any(
            _normalize_summary(candidate.summary) == _normalize_summary(item.summary)
            and candidate.cluster_norm == target_cluster
            for candidate in same_authority
        ):
            unresolved_by_file[item.source_path] += 1
            actions.append(
                Action(
                    kind="ambiguous_source_ref",
                    source_ref=item.source_ref,
                    source_file=item.source_path,
                    master_path=master_rel,
                    summary=item.summary,
                    note=f"authority_source_ref={item.authority_source_ref}",
                )
            )
            continue

        exact = _find_exact_duplicate(master_items, item, target_cluster)
        if exact is not None:
            if exact.authority_source_ref != item.authority_source_ref:
                unresolved_by_file[item.source_path] += 1
                actions.append(
                    Action(
                        kind="ambiguous_source_ref",
                        source_ref=item.source_ref,
                        source_file=item.source_path,
                        master_path=master_rel,
                        summary=item.summary,
                        note=(
                            f"incoming={item.authority_source_ref or 'missing'};"
                            f"existing={exact.authority_source_ref or 'missing'}"
                        ),
                    )
                )
                continue
            extra_sources = set(_parse_sources(_extract_field(item.body, "sources")))
            extra_sources.add(item.source_key)
            new_line, changed = _merge_sources_in_master_line(master_lines[exact.line_index], extra_sources)
            if changed:
                master_lines[exact.line_index] = new_line
            actions.append(
                Action(
                    kind="merge_source",
                    source_ref=item.source_ref,
                    source_file=item.source_path,
                    master_path=master_rel,
                    summary=item.summary,
                )
            )
            imported_targets[item.source_path].add(master_rel)
            continue

        likely, score = _find_possible_duplicate(master_items, item, target_cluster)
        if likely is not None:
            unresolved_by_file[item.source_path] += 1
            actions.append(
                Action(
                    kind="possible_duplicate",
                    source_ref=item.source_ref,
                    source_file=item.source_path,
                    master_path=master_rel,
                    summary=item.summary,
                    note=f"score={score:.2f}",
                )
            )
            continue

        prepared_body, used_fallback = _prepare_new_body(
            item,
            target_cluster,
            canonical=canonical if engaged else None,
            legacy_fallback=used_legacy_fallback,
        )
        new_line = f"- {item.priority} [ ] {prepared_body}"
        masters_cache[master_rel] = _append_to_followups_section(master_lines, new_line)
        actions.append(
            Action(
                kind="append_new",
                source_ref=item.source_ref,
                source_file=item.source_path,
                master_path=master_rel,
                summary=item.summary,
                note=("fallback_cluster" if used_fallback else ""),
            )
        )
        imported_targets[item.source_path].add(master_rel)

    if mode == "apply":
        for rel_path, lines in masters_cache.items():
            abs_path = REPO_ROOT / rel_path
            new_text = "\n".join(lines).rstrip() + "\n"
            old_text = masters_original.get(rel_path, "")
            if new_text != old_text:
                _before_write(abs_path, context)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                _write_text(abs_path, new_text, context)
                applied_files.append(rel_path)

        for src, masters in sorted(imported_targets.items()):
            if unresolved_by_file.get(src, 0) > 0 or parse_issues_by_file.get(src, 0) > 0:
                continue
            src_path = REPO_ROOT / src
            if not src_path.exists():
                continue
            if _mark_inbox_imported(src_path, sorted(masters), context):
                applied_files.append(src)

    report = _render_report(
        mode=mode,
        git_range=git_range,
        inbox_files=inbox_files,
        items_count=len(all_items),
        created_masters=created_masters,
        created_index_rows=created_index_rows,
        actions=actions,
        unresolved_by_file=unresolved_by_file,
        parse_issues_by_file=parse_issues_by_file,
        imported_targets=imported_targets,
        applied_files=applied_files,
    )
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

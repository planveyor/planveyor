#!/usr/bin/env python3
"""Harvest follow-ups from docs/code_reviews/*_line_by_line.md into a follow-ups inbox file.

Goal:
- One-shot import of actionable items from "line-by-line" code reviews into follow-ups masters.
- Avoid duplicates by best-effort matching against the declared `**Follow-ups backlog:**` file.
- Keep provenance via `sources=[...]` pointing to code review line numbers.

Flow:
1) Parse each code review doc for Risk/Nit/Follow-up items (Blocker is skipped by default).
2) Read the referenced follow-ups backlog file:
   - from working tree if exists,
   - else from `git show HEAD:<path>` (useful for already-deleted legacy inbox/backlog files).
3) For each extracted item:
   - Try to map it to an existing follow-up line in the backlog/master (label match, then similarity).
   - If mapped: re-emit the canonical follow-up line, adding `sources=[<review_path:line>]`.
   - If not mapped: generate a new follow-up line with neutral `cluster=process` and provenance.
4) Write a single inbox file under docs/followups/*.md (parseable by followups triage/import).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

try:
    from scripts import followups_apply, followups_capture, followups_lint
except ModuleNotFoundError:
    import followups_apply
    import followups_capture
    import followups_lint


# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
DEFAULT_GLOB = "docs/code_reviews/*_line_by_line.md"

DEFAULT_CLUSTER = "process"
CLUSTER_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

ITEM_RE = re.compile(r"^\s*-\s*(?P<prio>P[0-9?])\s+\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$")
SECTION_H2_RE = re.compile(r"^\s*##\s+")
FOLLOWUPS_BACKLOG_RE = re.compile(r"^\s*\*\*Follow-ups backlog:\*\*\s+`(?P<path>docs/followups/[^`]+?\.md)`")

# Review item heading formats:
#   1) **Title**
#   1) **Title**  (extra spaces ok)
REVIEW_ITEM_RE = re.compile(r"^\s*(?P<num>[0-9]+)\)\s+\*\*(?P<title>.+?)\*\*\s*$")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_scalar(value: str) -> str:
    v = value.strip().strip("`").strip().strip("'").strip('"').strip()
    v = v.replace("\u00a0", " ")
    return v


def _run_git_show(relpath: str) -> str:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git show HEAD:{relpath} failed")
    return proc.stdout


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


def _merge_sources(body: str, extra_sources: Iterable[str]) -> str:
    merged = set(_parse_sources(_extract_field(body, "sources")))
    for src in extra_sources:
        v = (src or "").strip()
        if v:
            merged.add(v)
    return _upsert_field(body, "sources", _format_sources(merged))


def _normalize_cluster(value: str | None) -> str | None:
    if not value:
        return None
    v = _normalize_scalar(value).lower().replace(" ", "")
    return v or None


def _is_cluster_slug(value: str | None) -> bool:
    return bool(value and CLUSTER_SLUG_RE.fullmatch(value))


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


@dataclass(frozen=True)
class ReviewItem:
    review_path: str
    section: str  # risk|nit|followup
    num: int
    title: str
    line_no: int

    @property
    def label(self) -> str:
        return f"{self.section}#{self.num}"

    @property
    def source_ref(self) -> str:
        return f"{self.review_path}#L{self.line_no}"


@dataclass(frozen=True)
class FollowupLine:
    priority: str
    body: str
    summary: str
    cluster_norm: str | None

    def key(self) -> tuple[str, str]:
        return (self.cluster_norm or "", _normalize_summary(self.summary))

    def harvest_key(self) -> tuple[str, str, str]:
        return (*self.key(), _extract_field(self.body, "source_intent") or "")


def _parse_review_items(
    review_path: Path,
    source_text: str,
    *,
    include_blockers: bool,
) -> tuple[str | None, list[ReviewItem]]:
    rel = review_path.relative_to(REPO_ROOT).as_posix()
    lines = source_text.splitlines()

    backlog_rel: str | None = None
    for line in lines[:60]:
        m = FOLLOWUPS_BACKLOG_RE.match(line.strip())
        if m:
            backlog_rel = m.group("path").strip()
            break

    items: list[ReviewItem] = []
    section: str | None = None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip().lower()
            if title.startswith("risk"):
                section = "risk"
            elif title.startswith("nit"):
                section = "nit"
            elif title.startswith("follow-up"):
                section = "followup"
            elif title.startswith("blocker"):
                section = "blocker" if include_blockers else None
            else:
                section = None
            continue

        if not section:
            continue
        m = REVIEW_ITEM_RE.match(line)
        if not m:
            continue
        num = int(m.group("num"))
        title = m.group("title").strip()
        items.append(
            ReviewItem(
                review_path=rel,
                section=section,
                num=num,
                title=title,
                line_no=i,
            )
        )
    return backlog_rel, items


def _parse_followup_lines(text: str) -> list[FollowupLine]:
    lines = text.splitlines()
    out: list[FollowupLine] = []
    in_followups = False
    for line in lines:
        if line.strip().lower().startswith("## follow-ups"):
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
        summary, _ = _split_tokens(body)
        cluster_raw = _extract_field(body, "cluster")
        out.append(
            FollowupLine(
                priority=m.group("prio"),
                body=body,
                summary=summary,
                cluster_norm=_normalize_cluster(cluster_raw),
            )
        )
    return out


WHY_LABEL_RE = re.compile(r"\b(?P<section>Risk|Nit|Follow-up|Blocker)\s*#\s*(?P<num>[0-9]+)\b", re.IGNORECASE)


def _label_from_why(body: str) -> str | None:
    why = _extract_field(body, "why") or ""
    m = WHY_LABEL_RE.search(why)
    if not m:
        return None
    sec = m.group("section").strip().lower().replace("-", "")
    num = int(m.group("num"))
    if sec == "followup":
        sec = "followup"
    if sec not in {"risk", "nit", "followup", "blocker"}:
        return None
    return f"{sec}#{num}"


def _new_row_cluster() -> str:
    return DEFAULT_CLUSTER


def _priority_for(item: ReviewItem) -> str:
    if item.section == "nit":
        return "P3"
    if item.section == "blocker":
        return "P1"
    # risk / followup
    return "P2"


def _format_list(values: list[str]) -> str:
    inner = ", ".join(f'"{v}"' for v in values if v)
    return f"[{inner}]"


def _format_lossless_token(value: str) -> str:
    return quote(value.strip(), safe="")


def _canonical_summary(item: ReviewItem) -> str:
    # Generic normalization only: the engine keeps no product-specific title
    # rewrites. Row keys also fold case and punctuation via _normalize_summary.
    return item.title.strip()


def _make_new_followup_line(item: ReviewItem, cluster: str) -> FollowupLine:
    tags = ["code_review", Path(item.review_path).stem, item.section, f"{item.section}_{item.num}"]
    why = f"from `{item.review_path}` {item.section.capitalize()} #{item.num}"
    summary = _canonical_summary(item)
    if summary != item.title.strip():
        why = f"{why}; original: {item.title.strip()}"
    body = (
        f"{summary}"
        f" — source_intent={_format_lossless_token(item.title)}"
        f" — canon_summary={_format_lossless_token(summary)}"
        f" — cluster={cluster}"
        f" — tags={_format_list(tags)}"
        f" — to=Owner"
        f" — status=open"
        f" — plan=null"
        f" — item_id=review-{hashlib.sha256(item.source_ref.encode('utf-8')).hexdigest()[:16]}"
        f" — source_ref={item.source_ref}"
        f" — disposition_kind=null"
        f" — disposition_ref=null"
        f" — disposition_commit_oid=null"
        f" — reason=null"
        f" — why: {why}"
        f" — sources={_format_sources([item.source_ref])}"
    )
    summary, _ = _split_tokens(body)
    return FollowupLine(priority=_priority_for(item), body=body, summary=summary, cluster_norm=_normalize_cluster(cluster))


def _v2ize_existing_body(body: str, item: ReviewItem, cluster: str) -> str:
    """Keep legacy context tokens but emit one valid typed V2 request row."""

    body = _upsert_field(body, "cluster", cluster)
    body = _upsert_field(body, "to", _extract_field(body, "to") or "Owner")
    body = _upsert_field(body, "status", "open")
    body = _upsert_field(body, "plan", "null")
    body = _upsert_field(body, "item_id", "review-" + hashlib.sha256(item.source_ref.encode("utf-8")).hexdigest()[:16])
    body = _upsert_field(body, "source_ref", item.source_ref)
    body = _upsert_field(body, "disposition_kind", "null")
    body = _upsert_field(body, "disposition_ref", "null")
    body = _upsert_field(body, "disposition_commit_oid", "null")
    body = _upsert_field(body, "reason", "null")
    body = _upsert_field(body, "why", _extract_field(body, "why") or f"from `{item.review_path}`")
    return body


def _best_backlog_match(item: ReviewItem, candidates: list[FollowupLine]) -> tuple[FollowupLine | None, float]:
    best: FollowupLine | None = None
    best_score = 0.0
    for cand in candidates:
        score = _similarity(cand.summary, item.title)
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def _default_out_path() -> Path:
    ts = datetime.now().strftime("%y%m%d_%H%M")
    return REPO_ROOT / "docs" / "followups" / f"{ts}_followups_code_reviews_line_by_line_inbox.md"


def _out_relpath(out_path: Path) -> str:
    try:
        rel_path = out_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("--out must be a repo-local docs/followups/*.md path") from exc
    if not rel_path.startswith("docs/followups/") or not rel_path.endswith(".md"):
        raise ValueError("--out must be a repo-local docs/followups/*.md path")
    return rel_path


def _current_row_digests(out_rel: str) -> dict[tuple[str, str], str]:
    target = REPO_ROOT / out_rel
    if not target.exists():
        return {}
    parsed = followups_lint.parse_followup_file(target, REPO_ROOT)
    schema, schema_findings = followups_lint.classify_followups_schema_version(parsed)
    findings = followups_lint.lint_followup_files([parsed], REPO_ROOT)
    if schema != "v2" or schema_findings or findings:
        raise ValueError("existing --out carrier must already be a lint-green followups.v2 file")
    digests: dict[tuple[str, str], str] = {}
    for item in parsed.items:
        source_ref = followups_lint.normalize_source_ref(item.source_ref)
        if source_ref is None or item.item_id is None:
            continue
        key = (source_ref, item.item_id)
        if key in digests:
            raise ValueError("existing --out carrier repeats a V2 tuple")
        digests[key] = followups_lint.v2_row_digest(item)
    return digests


def _target_header(source_paths: list[str]) -> str:
    now = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M %z")
    lines = [
        "# Follow-ups backlog — code reviews line-by-line harvest (inbox)",
        "",
        f"**Date:** {now}  ",
        "**Source:** code_reviews line-by-line harvest  ",
        "**Status:** Draft  ",
        "**Schema version:** followups.v2  ",
        "",
        "Зачем этот файл: one-shot перенос Risk/Nit/Follow-up из `docs/code_reviews/*_line_by_line.md` в master backlog’и `docs/followups/*_master.md`.",
        "После импорта inbox становится cleanup-receipt candidate; удаление допустимо только после `cleanup-receipt decision=delete-ready`.",
        "",
        "## Context / inputs (optional)",
        *[f"- Source: `{source_path}`" for source_path in source_paths],
        "",
        "## Follow-ups (backlog)",
    ]
    return "\n".join(lines) + "\n"


def _generic_batch(
    out_rel: str,
    payloads: list[dict[str, object]],
    source_snapshots: dict[str, bytes],
) -> dict[str, object]:
    baseline, _ = followups_capture.snapshot_followups(REPO_ROOT, include_bytes=True)
    current_digests = _current_row_digests(out_rel)
    source_anchors: dict[str, set[str]] = {source_path: set() for source_path in source_snapshots}
    proposed_rows: list[dict[str, object]] = []
    for payload in sorted(payloads, key=lambda value: (str(value["source_ref"]), str(value["item_id"]))):
        source_ref = str(payload["source_ref"])
        source_path, separator, anchor = source_ref.partition("#")
        if separator != "#" or not re.fullmatch(r"L[1-9][0-9]*", anchor):
            raise ValueError(f"generated review source_ref is not an exact line anchor: {source_ref}")
        if source_path not in source_anchors:
            raise ValueError(f"generated review source_ref is outside frozen source snapshots: {source_ref}")
        source_anchors[source_path].add(anchor)
        key = (source_ref, str(payload["item_id"]))
        proposed_rows.append(
            {
                "followup_path": out_rel,
                "payload": payload,
                "row_digest": followups_lint.v2_row_digest(payload),
                "expected_current_row_digest": current_digests.get(key),
            }
        )
    source_objects = []
    for source_path, anchors in sorted(source_anchors.items()):
        data = source_snapshots[source_path]
        source_objects.append(
            {
                "source_path": source_path,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "anchors": sorted(anchors),
            }
        )
    return {
        "schema_version": "followups_generic_batch.v2",
        "source_kind": "generic_harvest",
        "producer_id": "code_reviews_harvest",
        "target_followup_path": out_rel,
        "target_header": _target_header(list(source_snapshots)),
        "baseline_followups_snapshot": baseline,
        "source_objects": source_objects,
        "expected_owned_tuples": [
            {"source_ref": str(row["payload"]["source_ref"]), "item_id": str(row["payload"]["item_id"])}
            for row in proposed_rows
        ],
        "expected_zero_reason": None if proposed_rows else "no actionable code-review items found",
        "proposed_rows": proposed_rows,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harvest follow-ups from code review line-by-line docs into a follow-ups inbox file.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--all", action="store_true", help="Scan default pattern docs/code_reviews/*_line_by_line.md")
    src.add_argument("--src", action="append", default=[], help="Path to one review file (repeatable)")
    parser.add_argument("--out", default="", help="Output path (default: docs/followups/<ts>_followups_code_reviews_line_by_line_inbox.md)")
    parser.add_argument("--include-blockers", action="store_true", help="Include Blocker section items (default: skipped)")
    parser.add_argument("--match-threshold", type=float, default=0.30, help="Similarity threshold for matching existing backlog items")
    parser.add_argument("--dry-run", action="store_true", help="Print the frozen generic proposal without materializing a carrier.")
    return parser


def main(argv: list[str]) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.all:
        sources = sorted(REPO_ROOT.glob(DEFAULT_GLOB))
    else:
        sources = [REPO_ROOT / p for p in args.src]

    missing = [p.as_posix() for p in sources if not p.exists()]
    if missing:
        print("ERROR: missing sources:", file=sys.stderr)
        for p in missing:
            print(f"- {p}", file=sys.stderr)
        return 2

    out_path = Path(args.out).expanduser() if args.out.strip() else _default_out_path()
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    try:
        rel_out = _out_relpath(out_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    all_items_out: dict[tuple[str, str, str], FollowupLine] = {}
    mapped = 0
    created = 0
    skipped = 0

    try:
        source_snapshots: dict[str, bytes] = {}
        for review_path in sources:
            source_path = review_path.relative_to(REPO_ROOT).as_posix()
            _source_object, source_bytes = followups_capture.read_repo_regular_path(REPO_ROOT, source_path)
            source_snapshots[source_path] = source_bytes
        for review_path in sources:
            rel_review = review_path.relative_to(REPO_ROOT).as_posix()
            backlog_rel, review_items = _parse_review_items(
                review_path,
                source_snapshots[rel_review].decode("utf-8", errors="replace"),
                include_blockers=args.include_blockers,
            )
            if not backlog_rel:
                # Without a declared backlog, we still can generate new followups.
                backlog_rel = ""
            backlog_lines: list[FollowupLine] = []
            if backlog_rel:
                abs_backlog = REPO_ROOT / backlog_rel
                try:
                    backlog_text = _read_text(abs_backlog) if abs_backlog.exists() else _run_git_show(backlog_rel)
                    backlog_lines = _parse_followup_lines(backlog_text)
                except Exception as e:
                    print(f"WARNING: cannot read backlog {backlog_rel}: {e}", file=sys.stderr)
                    backlog_lines = []

            backlog_by_label: dict[str, FollowupLine] = {}
            for f in backlog_lines:
                lab = _label_from_why(f.body)
                if lab:
                    backlog_by_label.setdefault(lab, f)

            for item in review_items:
                cluster_guess = _new_row_cluster()

                # Prefer explicit label mapping (Risk/Nit/Follow-up #N) via `why:`.
                cand = backlog_by_label.get(item.label)
                score = 1.0 if cand else 0.0
                if not cand and backlog_lines:
                    same_cluster = [c for c in backlog_lines if (c.cluster_norm or "") == cluster_guess]
                    pool = same_cluster if same_cluster else backlog_lines
                    cand, score = _best_backlog_match(item, pool)
                    if score < float(args.match_threshold):
                        cand = None

                if cand:
                    # Re-emit canonical line, but add provenance to sources.
                    body = _merge_sources(cand.body, [item.source_ref])
                    body = _upsert_field(body, "source_intent", _format_lossless_token(item.title))
                    body = _upsert_field(body, "canon_summary", _format_lossless_token(cand.summary))
                    cluster = _normalize_cluster(_extract_field(body, "cluster"))
                    if not _is_cluster_slug(cluster):
                        # Preserve the canonical summary/body, but fix routing key.
                        body = _upsert_field(body, "cluster", cluster_guess)
                        cluster = cluster_guess
                    body = _v2ize_existing_body(body, item, cluster or cluster_guess)
                    summary, _ = _split_tokens(body)
                    out = FollowupLine(priority=cand.priority, body=body, summary=summary, cluster_norm=_normalize_cluster(cluster))
                    key = out.harvest_key()
                    if key in all_items_out:
                        all_items_out[key] = FollowupLine(
                            priority=all_items_out[key].priority,
                            body=_merge_sources(all_items_out[key].body, _parse_sources(_extract_field(out.body, "sources"))),
                            summary=all_items_out[key].summary,
                            cluster_norm=all_items_out[key].cluster_norm,
                        )
                        skipped += 1
                    else:
                        all_items_out[key] = out
                        mapped += 1
                    continue

                out = _make_new_followup_line(item, cluster=cluster_guess)
                key = out.harvest_key()
                if key in all_items_out:
                    all_items_out[key] = FollowupLine(
                        priority=all_items_out[key].priority,
                        body=_merge_sources(all_items_out[key].body, _parse_sources(_extract_field(out.body, "sources"))),
                        summary=all_items_out[key].summary,
                        cluster_norm=all_items_out[key].cluster_norm,
                    )
                    skipped += 1
                else:
                    all_items_out[key] = out
                    created += 1
        payloads: list[dict[str, object]] = []
        for _, item in sorted(all_items_out.items(), key=lambda kv: (kv[1].cluster_norm or "", _normalize_summary(kv[1].summary))):
            parsed = followups_lint.parse_followup_item(rel_out, 1, f"- {item.priority} [ ] {item.body}")
            if parsed is None:
                raise ValueError("generated review row could not be parsed as followups.v2")
            findings = followups_lint.lint_v2_item(parsed, REPO_ROOT)
            if findings:
                raise ValueError(
                    "generated review row fails followups.v2: "
                    + ", ".join(sorted({finding.code for finding in findings}))
                )
            payloads.append(followups_lint.v2_row_payload(parsed))
        batch = _generic_batch(
            rel_out,
            payloads,
            source_snapshots,
        )
        result = followups_apply.apply_frozen_rows(REPO_ROOT, batch, mutate=not args.dry_run)
    except (ValueError, followups_apply.ApplyError, followups_capture.CaptureError, OSError) as exc:
        print(f"ERROR: generic code-review harvest blocked: {exc}", file=sys.stderr)
        return 2

    print(f"harvested_reviews={len(sources)} items_out={len(all_items_out)} mapped={mapped} created={created} deduped={skipped}")
    print(f"out={rel_out}")
    if args.dry_run:
        print(json.dumps({"batch": batch, "apply": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

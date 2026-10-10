#!/usr/bin/env python3
"""Suggest temp-doc cleanup candidates for post-merge docs hygiene.

Given a git range BASE..HEAD, prints:
- cleanup-eligible terminal plans in range (`Done` + `Superseded`).
- Related temp artifacts (code/doc reviews + review assets) referenced by those plans.
- A conservative `git rm -r ...` suggestion (Owner still decides).

This is intentionally lightweight and deterministic (no markdown parser).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from typing import Iterable, Mapping, Sequence


# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
DOCS_ROOT = REPO_ROOT / "docs"
PLANS_ROOT = DOCS_ROOT / "plans"
FOLLOWUPS_ROOT = DOCS_ROOT / "followups"

DEFAULT_GIT_DIRS = [
    "docs/plans",
    "docs/followups",
    "docs/code_drafts",
    "docs/code_reviews",
    "docs/doc_reviews",
    "docs/snapshots",
    "docs/reviews",
]

TEMP_DOC_PREFIXES = (
    "docs/plans/",
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/code_drafts/",
    "docs/followups/",
)

CANON_REF_SCAN_EXCLUDES = (
    "docs/plans/",
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/code_drafts/",
    "docs/followups/",
    "docs/continuity/",
)

MERGE_PIPELINE_REVIEW_MARKERS = (
    "merge_notes_range_",
    "plan_harvest_range_",
    "post_merge_audit_range_",
)

MERGE_PIPELINE_SNAPSHOT_MARKERS = (
    "merge_workflow_checkpoint",
)

MERGE_PIPELINE_SNAPSHOT_RANGE_RE = re.compile(
    r".*_range_[0-9a-f]{7,}_[0-9a-f]{7,}_canon_sweep\.md$",
    re.IGNORECASE,
)

# Allow old plan headers that used Markdown blockquotes (`> **Status:** ...`).
STATUS_LINE_RE = re.compile(r"^\s*(?:>\s*)?\*\*Status:\*\*\s*(?P<status>.+?)\s*$")
TERMINAL_STATUS_RE = re.compile(r"\b(?:done|superseded)\b", re.IGNORECASE)
DONE_ONLY_RE = re.compile(r"\bdone\b", re.IGNORECASE)

DOC_REF_RE = re.compile(
    r"\bdocs/(?:plans|code_reviews|doc_reviews|code_drafts|followups|snapshots)/[A-Za-z0-9_./-]+\b"
)

# In code_reviews we often reference assets relatively: `assets/<dir>/<file>.png`
ASSET_REL_RE = re.compile(r"\bassets/[A-Za-z0-9_./-]+\b")


@dataclass(frozen=True)
class RefCheck:
    ok: bool
    blocking_plans: tuple[str, ...]
    terminal_plans: tuple[str, ...]
    all_plans: tuple[str, ...]
    reason: str


def _run_git(args: Sequence[str]) -> str:
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
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _extract_status_value(text: str) -> str | None:
    for line in text.splitlines():
        m = STATUS_LINE_RE.match(line)
        if m:
            return m.group("status").strip()
    return None


def _is_terminal_status(status: str | None) -> bool:
    if not status:
        return False
    return bool(TERMINAL_STATUS_RE.search(status))


def _is_done_only_status(status: str | None) -> bool:
    if not status:
        return False
    return bool(DONE_ONLY_RE.search(status))


def _iter_plan_files() -> Iterable[Path]:
    if not PLANS_ROOT.exists():
        return
    for p in sorted(PLANS_ROOT.glob("*.md")):
        if p.name in {"README.md", "_template.md"}:
            continue
        yield p


def _iter_followup_files() -> Iterable[Path]:
    if not FOLLOWUPS_ROOT.exists():
        return
    for p in sorted(FOLLOWUPS_ROOT.glob("*.md")):
        yield p


def _extract_doc_refs(text: str) -> set[str]:
    return {m.group(0) for m in DOC_REF_RE.finditer(text)}


def _extract_review_asset_dirs(code_review_path: Path) -> set[str]:
    """Return asset directories referenced by a code review file.

    Example in review text: `assets/260123_xxx/foo.png` -> docs/code_reviews/assets/260123_xxx/
    """
    text = _read_text(code_review_path)

    refs: set[str] = set()

    # Full refs (rare): docs/code_reviews/assets/...
    for ref in _extract_doc_refs(text):
        if ref.startswith("docs/code_reviews/assets/"):
            refs.add(ref)

    # Relative refs (common): assets/<dir>/...
    for m in ASSET_REL_RE.finditer(text):
        rel = m.group(0)
        refs.add(f"docs/code_reviews/{rel}")

    # Normalize to directories under docs/code_reviews/assets/<dir>
    dirs: set[str] = set()
    for ref in refs:
        if not ref.startswith("docs/code_reviews/assets/"):
            continue
        # docs/code_reviews/assets/<dir>/...
        parts = ref.split("/")
        if len(parts) >= 4:
            dirs.add("/".join(parts[:4]))
    return dirs


def _git_touched_docs(range_ref: str, dirs: Sequence[str]) -> list[str]:
    out = _run_git(["diff", "--name-only", range_ref, "--", *dirs])
    files = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.search(r"\.(md|png|jpe?g|webp)$", line, flags=re.IGNORECASE):
            continue
        files.append(line)
    return sorted(set(files))


def _build_plan_status_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for plan in _iter_plan_files():
        status = _extract_status_value(_read_text(plan)) or "UNCONFIRMED"
        index[_rel(plan)] = status
    return index


def _build_plan_ref_index(plan_status: Mapping[str, str]) -> dict[str, set[str]]:
    """plan -> doc refs (only for known docs/... references)."""
    plan_refs: dict[str, set[str]] = {}
    for plan_rel in sorted(plan_status.keys()):
        plan_path = REPO_ROOT / plan_rel
        if not plan_path.exists():
            continue
        plan_refs[plan_rel] = _extract_doc_refs(_read_text(plan_path))
    return plan_refs


def _invert_ref_index(plan_refs: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """ref -> set(plans). Only for temp doc refs we may consider deleting."""
    ref_to_plans: dict[str, set[str]] = {}
    for plan, refs in plan_refs.items():
        for ref in refs:
            if not ref.startswith(TEMP_DOC_PREFIXES):
                continue
            ref_to_plans.setdefault(ref, set()).add(plan)
    return ref_to_plans


def _ref_safe_to_delete(
    ref: str,
    *,
    ref_to_plans: Mapping[str, set[str]],
    plan_status: Mapping[str, str],
    terminal_plans_override: set[str],
) -> RefCheck:
    """A ref is safe if no non-terminal plan (outside override) references it."""
    blocking: list[str] = []
    terminal_refs: list[str] = []
    all_refs = sorted(ref_to_plans.get(ref, set()))
    for plan in all_refs:
        if plan in terminal_plans_override:
            terminal_refs.append(plan)
            continue
        if _is_terminal_status(plan_status.get(plan)):
            terminal_refs.append(plan)
            continue
        if not _is_terminal_status(plan_status.get(plan)):  # keep explicit for readability
            blocking.append(plan)

    if blocking:
        reason = "referenced by non-terminal plan(s)"
        ok = False
    elif all_refs:
        reason = "referenced only by terminal plan(s)"
        ok = True
    else:
        reason = "no plan references (orphan/touched artifact)"
        ok = True

    return RefCheck(
        ok=ok,
        blocking_plans=tuple(blocking),
        terminal_plans=tuple(terminal_refs),
        all_plans=tuple(all_refs),
        reason=reason,
    )


def _canon_reference_hits(candidates: Sequence[str]) -> dict[str, list[str]]:
    """Return mapping: candidate -> list of canon md files that reference it.

    "Canon" here means any docs/*.md outside known temp roots.
    """
    canon_files: list[Path] = []
    for p in DOCS_ROOT.rglob("*.md"):
        rel = _rel(p)
        if rel.startswith(CANON_REF_SCAN_EXCLUDES):
            continue
        if rel.startswith("docs/reviews/"):
            name = Path(rel).name
            if any(marker in name for marker in MERGE_PIPELINE_REVIEW_MARKERS):
                continue
        if rel.startswith("docs/snapshots/"):
            name = Path(rel).name
            if any(marker in name for marker in MERGE_PIPELINE_SNAPSHOT_MARKERS):
                continue
            if MERGE_PIPELINE_SNAPSHOT_RANGE_RE.match(name):
                continue
        canon_files.append(p)

    hits: dict[str, list[str]] = {c: [] for c in candidates}
    for p in canon_files:
        text = _read_text(p)
        rel = _rel(p)
        for c in candidates:
            if c in text:
                hits[c].append(rel)

    return {k: v for k, v in hits.items() if v}


def _missing_ref_placeholder(ref: str) -> str:
    return f"<missing-artifact:{Path(ref).name}>"


def _fix_missing_refs_in_plan(plan_rel: str, refs: Sequence[str], *, apply: bool) -> tuple[int, bool]:
    plan_path = REPO_ROOT / plan_rel
    if not plan_path.exists():
        return (0, False)
    text = _read_text(plan_path)
    original = text
    replaced = 0
    for ref in sorted(set(refs)):
        count = text.count(ref)
        if count <= 0:
            continue
        text = text.replace(ref, _missing_ref_placeholder(ref))
        replaced += count
    changed = text != original
    if apply and changed:
        plan_path.write_text(text, encoding="utf-8")
    return (replaced, changed)


def _compute_state(
    *,
    touched: Sequence[str],
    include_snapshots: bool,
    include_followups: bool,
) -> dict[str, object]:
    plan_status = _build_plan_status_index()
    plan_refs = _build_plan_ref_index(plan_status)
    ref_to_plans = _invert_ref_index(plan_refs)

    touched_plans = [p for p in touched if p.startswith("docs/plans/")]
    terminal_plans = [p for p in touched_plans if _is_terminal_status(plan_status.get(p))]

    # Candidate refs from terminal plans (`Done` + `Superseded`) (and optionally snapshots).
    referenced_from_done: set[str] = set()
    for plan in terminal_plans:
        for ref in plan_refs.get(plan, set()):
            if ref.startswith(
                (
                    "docs/code_reviews/",
                    "docs/doc_reviews/",
                    "docs/code_drafts/",
                )
            ):
                if ref.endswith(".md") and not ref.startswith("docs/code_reviews/assets"):
                    referenced_from_done.add(ref)
            if include_snapshots and ref.startswith("docs/snapshots/"):
                if ref.endswith(".md"):
                    referenced_from_done.add(ref)

    def _is_template_or_readme(rel_path: str) -> bool:
        name = Path(rel_path).name
        return name == "README.md" or name.startswith("_template")

    touched_temp_artifacts = {
        p
        for p in touched
        if p.startswith(("docs/code_reviews/", "docs/doc_reviews/", "docs/code_drafts/"))
        and not p.startswith("docs/code_reviews/assets/")
        and p.endswith(".md")
        and not _is_template_or_readme(p)
    }
    candidate_refs = {r for r in (referenced_from_done | touched_temp_artifacts) if r.endswith(".md")}

    safe_refs: list[str] = []
    blocked_refs: list[tuple[str, RefCheck]] = []
    for ref in sorted(candidate_refs):
        check = _ref_safe_to_delete(
            ref,
            ref_to_plans=ref_to_plans,
            plan_status=plan_status,
            terminal_plans_override=set(terminal_plans),
        )
        if check.ok:
            safe_refs.append(ref)
        else:
            blocked_refs.append((ref, check))

    safe_present = [r for r in safe_refs if (REPO_ROOT / r).exists()]
    safe_missing = [r for r in safe_refs if not (REPO_ROOT / r).exists()]
    blocked_present = [(r, c) for (r, c) in blocked_refs if (REPO_ROOT / r).exists()]
    blocked_missing = [(r, c) for (r, c) in blocked_refs if not (REPO_ROOT / r).exists()]

    # Followups (optional)
    touched_followups = [p for p in touched if p.startswith("docs/followups/") and p.endswith(".md")]
    done_followups: list[str] = []
    blocked_followups: list[tuple[str, tuple[str, ...]]] = []
    for f in touched_followups:
        fp = REPO_ROOT / f
        if not fp.exists():
            continue
        status = _extract_status_value(_read_text(fp))
        if not _is_done_only_status(status):
            continue
        refs = _extract_doc_refs(_read_text(fp))
        plan_refs_only = sorted(r for r in refs if r.startswith("docs/plans/"))
        blocking: list[str] = []
        for pr in plan_refs_only:
            if pr in terminal_plans:
                continue
            if not _is_terminal_status(plan_status.get(pr)):
                blocking.append(pr)
        if blocking:
            blocked_followups.append((f, tuple(blocking)))
        else:
            done_followups.append(f)

    # Build suggested deletion set (files only; asset dirs are derived from rm_items).
    delete_files = [p for p in terminal_plans if (REPO_ROOT / p).exists()]
    delete_files += [r for r in safe_refs if (REPO_ROOT / r).exists()]

    rm_candidates: list[str] = sorted(set(delete_files))
    if include_followups:
        rm_candidates += sorted(set(done_followups))
    rm_candidates = [p for p in rm_candidates if (REPO_ROOT / p).exists()]

    canon_hits = _canon_reference_hits(sorted(set(rm_candidates)))
    blocked_by_canon = set(canon_hits.keys())
    rm_items = [p for p in rm_candidates if p not in blocked_by_canon]

    asset_dirs: set[str] = set()
    for ref in rm_items:
        if not ref.startswith("docs/code_reviews/") or ref.startswith("docs/code_reviews/assets/"):
            continue
        review_path = REPO_ROOT / ref
        asset_dirs |= _extract_review_asset_dirs(review_path)
    delete_dirs = sorted({d for d in asset_dirs if (REPO_ROOT / d).exists()})

    return {
        "plan_status": plan_status,
        "ref_to_plans": ref_to_plans,
        "terminal_plans": terminal_plans,
        "safe_present": safe_present,
        "safe_missing": safe_missing,
        "blocked_present": blocked_present,
        "blocked_missing": blocked_missing,
        "done_followups": done_followups,
        "blocked_followups": blocked_followups,
        "canon_hits": canon_hits,
        "blocked_by_canon": blocked_by_canon,
        "rm_items": rm_items,
        "delete_dirs": delete_dirs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Suggest git-rm candidates for post-merge docs hygiene (plans/reviews/assets)."
    )
    parser.add_argument("--range", required=True, help="Git range, e.g. BASE..HEAD")
    parser.add_argument(
        "--include-followups",
        action="store_true",
        help="Include Done followups in the suggested git rm command (default: list separately).",
    )
    parser.add_argument(
        "--include-snapshots",
        action="store_true",
        help="Include docs/snapshots/* referenced by terminal plans (default: never delete snapshots).",
    )
    parser.add_argument(
        "--dirs",
        nargs="*",
        default=DEFAULT_GIT_DIRS,
        help="Docs roots to scan in git diff (advanced).",
    )
    parser.add_argument(
        "--fix-missing-blocks",
        choices=["dry-run", "apply"],
        help=(
            "Auto-fix blocked missing refs in non-terminal plans: replace missing docs/... refs with placeholders "
            "(`dry-run` only reports; `apply` writes changes)."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show low-signal diagnostic sections (e.g., safe artifacts already missing on disk).",
    )
    args = parser.parse_args()

    range_ref: str = args.range.strip()
    touched = _git_touched_docs(range_ref, args.dirs)

    state = _compute_state(
        touched=touched,
        include_snapshots=bool(args.include_snapshots),
        include_followups=bool(args.include_followups),
    )

    print(f"[planveyor] Range: {range_ref}")
    print("")

    plan_status = state["plan_status"]  # type: ignore[assignment]
    terminal_plans = state["terminal_plans"]  # type: ignore[assignment]

    if args.fix_missing_blocks:
        mode = str(args.fix_missing_blocks)
        apply_fix = mode == "apply"
        blocked_missing = state["blocked_missing"]  # type: ignore[assignment]
        plan_to_missing_refs: dict[str, set[str]] = defaultdict(set)
        for ref, check in blocked_missing:
            for plan in check.blocking_plans:
                plan_to_missing_refs[plan].add(ref)

        print(f"[planveyor] Missing-block fixer (--fix-missing-blocks={mode}):")
        if not plan_to_missing_refs:
            print("  - no blocked+missing refs found")
        else:
            changed_any = False
            for plan in sorted(plan_to_missing_refs.keys()):
                refs = sorted(plan_to_missing_refs[plan])
                replaced, changed = _fix_missing_refs_in_plan(plan, refs, apply=apply_fix)
                changed_any = changed_any or changed
                status = plan_status.get(plan, "UNCONFIRMED")
                action = "updated" if (apply_fix and changed) else "would-update" if changed else "no-op"
                print(f"  - {plan} ({status})")
                print(f"      action: {action}; replaced occurrences: {replaced}; missing refs: {len(refs)}")
                for ref in refs:
                    print(f"      ref: {ref}")
            if apply_fix and changed_any:
                state = _compute_state(
                    touched=touched,
                    include_snapshots=bool(args.include_snapshots),
                    include_followups=bool(args.include_followups),
                )
                plan_status = state["plan_status"]  # type: ignore[assignment]
                terminal_plans = state["terminal_plans"]  # type: ignore[assignment]
        print("")

    if not terminal_plans:
        print("[planveyor] Terminal plans in range (`Done` + `Superseded`): none")
    else:
        print(f"[planveyor] Terminal plans in range (`Done` + `Superseded`) ({len(terminal_plans)}):")
        for p in terminal_plans:
            print(f"  - {p}")
    print("")
    ref_to_plans = state["ref_to_plans"]  # type: ignore[assignment]
    safe_present = state["safe_present"]  # type: ignore[assignment]
    safe_missing = state["safe_missing"]  # type: ignore[assignment]
    blocked_present = state["blocked_present"]  # type: ignore[assignment]
    blocked_missing = state["blocked_missing"]  # type: ignore[assignment]
    done_followups = state["done_followups"]  # type: ignore[assignment]
    blocked_followups = state["blocked_followups"]  # type: ignore[assignment]
    canon_hits = state["canon_hits"]  # type: ignore[assignment]
    blocked_by_canon = state["blocked_by_canon"]  # type: ignore[assignment]
    rm_items = state["rm_items"]  # type: ignore[assignment]
    delete_dirs = state["delete_dirs"]  # type: ignore[assignment]

    if safe_present:
        print(f"[planveyor] Review/code drafts safe to delete ({len(safe_present)}):")
        for r in safe_present:
            check = _ref_safe_to_delete(
                r,
                ref_to_plans=ref_to_plans,
                plan_status=plan_status,
                terminal_plans_override=set(terminal_plans),
            )
            print(f"  - {r}")
            print(f"      reason: {check.reason}")
            if check.terminal_plans:
                plans_joined = ", ".join(check.terminal_plans)
                print(f"      refs in terminal plans: {plans_joined}")
        print("")

    if safe_missing and args.verbose:
        print(f"[planveyor] Review/code drafts already missing on disk ({len(safe_missing)}):")
        for r in safe_missing:
            check = _ref_safe_to_delete(
                r,
                ref_to_plans=ref_to_plans,
                plan_status=plan_status,
                terminal_plans_override=set(terminal_plans),
            )
            print(f"  - {r}")
            print(f"      reason: {check.reason}")
            if check.terminal_plans:
                plans_joined = ", ".join(check.terminal_plans)
                print(f"      refs in terminal plans: {plans_joined}")
        print("  action: no `git rm` needed (files are already absent on disk).")
        print("")

    if blocked_present:
        print(f"[planveyor] Review/code drafts NOT safe to delete ({len(blocked_present)}):")
        for ref, check in blocked_present:
            print(f"  - {ref}")
            print(f"      reason: {check.reason}")
            for plan in check.blocking_plans:
                print(f"      referenced by non-terminal plan: {plan} ({plan_status.get(plan, 'UNCONFIRMED')})")
        print("")

    if blocked_missing:
        print(f"[planveyor] Review/code drafts blocked BUT missing on disk ({len(blocked_missing)}):")
        for ref, check in blocked_missing:
            print(f"  - {ref}")
            print(f"      reason: {check.reason}")
            for plan in check.blocking_plans:
                print(f"      referenced by non-terminal plan: {plan} ({plan_status.get(plan, 'UNCONFIRMED')})")
        print("")
        print("[planveyor] Suggested remediation for blocked+missing:")
        for ref, check in blocked_missing:
            plan_args = " ".join(shlex.quote(p) for p in check.blocking_plans)
            print(f"  - stale link check for {ref}:")
            print(f"      rg -n --fixed-strings {shlex.quote(ref)} {plan_args}")
            print("      action A: update/remove stale refs in listed non-terminal plans")
            print(f"      action B: restore artifact if still required: git log --oneline -- {shlex.quote(ref)}")
        print("")

    if done_followups:
        print(f"[planveyor] Followups (Done) candidates ({len(done_followups)}):")
        for f in done_followups:
            print(f"  - {f}")
        print("")

    if blocked_followups:
        print(f"[planveyor] Followups (Done) blocked ({len(blocked_followups)}):")
        for f, blocking in blocked_followups:
            print(f"  - {f}")
            for pr in blocking:
                print(f"      references non-terminal plan: {pr} ({plan_status.get(pr, 'UNCONFIRMED')})")
        print("")

    if canon_hits:
        print("[planveyor] ⚠️  Blocked by canon references (excluded from Suggested (Owner) command):")
        for target, refs in sorted(canon_hits.items()):
            print(f"  - {target}")
            for r in refs:
                print(f"      referenced by: {r}")
        print("")

    done_plan_rm_items = [p for p in rm_items if p.startswith("docs/plans/")]
    if terminal_plans:
        print("[planveyor] Terminal plan decision map:")
        for plan in terminal_plans:
            if plan in done_plan_rm_items:
                print(f"  - {plan}")
                print("      decision: included in Suggested (Owner) command")
                print("      reason: terminal status (`Done`/`Superseded`) + no canon references")
                continue
            if plan in blocked_by_canon:
                refs = canon_hits.get(plan, [])
                print(f"  - {plan}")
                print("      decision: excluded from Suggested (Owner) command")
                print(f"      reason: canon references ({len(refs)})")
                continue
            if not (REPO_ROOT / plan).exists():
                print(f"  - {plan}")
                print("      decision: excluded from Suggested (Owner) command")
                print("      reason: missing on disk")
                continue
            print(f"  - {plan}")
            print("      decision: excluded from Suggested (Owner) command")
            print("      reason: filtered out by safety rules (check refs/status)")
        print("")

    if rm_items or delete_dirs or terminal_plans:
        print("[planveyor] REQUIRED before any git rm: archive temp docs into the central SQLite archive:")
        print(
            f"  python3 scripts/docs_hygiene_archive.py --range {shlex.quote(range_ref)} --apply"
        )
        print("")

    print("[planveyor] Suggested (Owner) command:")
    if not rm_items and not delete_dirs:
        print("  # nothing to remove (or nothing detected as safe)")
        return 0

    print("  git rm -r \\")
    for p in rm_items:
        print(f"    {p} \\")
    for d in delete_dirs:
        print(f"    {d} \\")
    print("  # (copy, then remove trailing backslash on the last line)")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

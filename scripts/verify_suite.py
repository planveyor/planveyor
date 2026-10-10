#!/usr/bin/env python3
"""Verify-suite: registry-driven integrity checks with summary report + interpretation.

The suite is a thin orchestrator over a registry of independent check
``ModuleBase`` subclasses. Each module produces a list of :class:`Result`
records and a free-form ``interpret`` note that classifies responsibility
(portability vs foreign track vs expected). The orchestrator renders a plain
table or a single JSON object and exits 2 when any check fails (the repo
convention for gate scripts, see ``merge_bundle_report.py``).

The first module is :class:`PortabilityModule`, which keeps generic
portability checks independent while allowing a caller to explicitly select
any plan and archive inputs that are present in the repository. Future modules
(reviewer_range, ai_gate, ...) register themselves and inherit the
orchestration without touching it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from portability_substitution import (
    GENERIC_PORTABILITY_RULES,
    PortabilityPolicyError,
    PortabilityRules,
    load_portability_rules,
)

# Keep the suite usable as a standalone legacy portability check.  The
# authority modules are loaded only when a parent explicitly supplies this
# child assertion; the literal is the reviewed wire name from
# contract_authority_context.EXPECTED_CONTEXT_ENV.
_AUTHORITY_CONTEXT_ENV = "_PLANVEYOR_AUTHORITY_CONTEXT_V1"


# --------------------------------------------------------------------------- #
# Result + module registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Result:
    """One check outcome. ``status`` is normalized to pass|warn|fail."""

    name: str
    status: str
    metric: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"pass", "warn", "fail"}:
            raise ValueError(f"Result.status must be pass|warn|fail, got {self.status!r}")


class ModuleBase:
    """Base class for a verification module.

    Subclasses set ``name`` and implement :meth:`run` and :meth:`interpret`.
    Each ``run`` call must be self-contained: a failing check returns a
    ``fail`` Result rather than raising, so the orchestrator can collect all
    results from all modules in one pass.
    """

    name: str = ""

    def run(self, repo_root: Path) -> list[Result]:  # pragma: no cover - abstract
        raise NotImplementedError

    def interpret(self, results: list[Result]) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


_REGISTRY: list[type[ModuleBase]] = []


def register(cls: type[ModuleBase]) -> type[ModuleBase]:
    """Decorator that adds a module class to the run registry."""
    _REGISTRY.append(cls)
    return cls


def _resolve_pybin(repo_root: Path) -> str:
    """Use this process's already selected Python, never a project-supplied path."""
    del repo_root
    return sys.executable


# --------------------------------------------------------------------------- #
# Portability module
# --------------------------------------------------------------------------- #
# Substrings that identify portability-related test modules by filename.
# Discovery-by-pattern (not a hardcoded list) keeps the check robust to the
# fact that the test-module set differs between worktrees (e.g. WT1 carries
# test_pybin / test_portability_substitution which WT3 does not).
_PORTABILITY_TEST_PATTERNS = (
    "test_runtime_portability",
    "test_post_merge_operational_receipt",
    "test_oss_release_scan",
    "test_docs_archive_restore",
    "test_docs_archive_snapshot",
    "test_portability_substitution",
    "test_docs_archive_normalize",
    "test_pybin",
)

def _has_resolved_user_home_path(text: str, user_home_re: re.Pattern[str]) -> bool:
    """Return whether text contains a generic user-home path with a child segment.

    ``PERSONAL_PATH_RE`` recognizes a generic concrete user-home root while
    excluding the scanner's ellipsis-style placeholder. A bare home token can be
    prose that discusses the syntax; a following slash begins a resolved path.
    This stays independent of any particular local username.
    """
    for match in user_home_re.finditer(text):
        remainder = text[match.end():]
        if remainder.startswith(("/", "\\")):
            return True
    return False

_HOMEBREW_PY = "/" + "opt/homebrew/bin/python3"
# This verifier owns its narrowly scoped local policy. It is intentionally
# independent from scanner input and does not suppress scanner findings.
_HOMEBREW_GATE_ALLOWLIST = frozenset(
    {
        "docs/tools/dotfiles/zsh/zshrc",
    }
)
# A table-collapse lesson is exceptional only when this verifier names it.
# The current tree has no such lesson, so the policy begins empty rather than
# importing an unrelated scanner-wide path inventory.
_CORRUPTION_LESSON_ALLOWLIST: frozenset[str] = frozenset()

# Local corruption probes are composed from public syntax fragments so this verifier
# can inspect other files without reporting its own implementation constants.
#
# The double-substitution marker matches the FULL re-substituted corruption
# form (a complete ${PLANVEYOR_ROOT:-$HOME/planveyor} immediately
# followed by ANOTHER complete one) — NOT the truncated prefix
# ".../${PLANVEYOR_ROOT", which would false-positive on a legitimate
# path joining two portable roots back-to-back.
_PORTABLE_FULL = "${" + "PLANVEYOR_ROOT:-$HOME/planveyor}"
_DOUBLE_SUB_MARKER = _PORTABLE_FULL + "/" + _PORTABLE_FULL
_TABLE_COLLAPSE_MARKER = "| " + "python3 | " + "python3 |"


@register
class PortabilityModule(ModuleBase):
    """Portability workstream integrity checks.

    ``--scope all`` complements the live keep-set baseline, so both current
    and historical text receive scanner coverage. Plan and archive checks are
    applicable only when the caller explicitly selects their inputs.
    """

    name = "portability"

    def __init__(
        self,
        *,
        portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
        portability_plans: tuple[str, ...] = (),
        archive_snapshot: str | None = None,
        full: bool = False,
    ) -> None:
        self._portability_rules = portability_rules
        self._portability_plans = portability_plans
        self._archive_snapshot = archive_snapshot
        self._full = full

    def _archive_snapshot_dir(self, repo_root: Path) -> Path | None:
        if self._archive_snapshot is None:
            return None
        return repo_root / self._archive_snapshot

    def _unselected_applicability_note(self) -> str:
        missing: list[str] = []
        if not self._portability_plans:
            missing.append("plan inputs")
        if self._archive_snapshot is None:
            missing.append("archive snapshot")
        if not missing:
            return ""
        return "\n  >> Not selected: " + "; ".join(missing) + "; no verification claim is made for omitted inputs."

    # -- individual checks -------------------------------------------------- #
    def check_test_scripts(self, repo_root: Path) -> Result:
        # Call the unittest discovery directly via the resolved interpreter
        # (same flags as the Makefile test-scripts target) rather than shelling
        # out to ``make``. Reuse this process's trusted interpreter so the
        # child cannot select a different executable during verification.
        pybin = _resolve_pybin(repo_root)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [pybin, "-B", "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-v"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        combined = proc.stdout + proc.stderr
        sys.stderr.write(combined)
        ran_match = re.search(r"^Ran (\d+) tests?", combined, re.MULTILINE)
        ran = ran_match.group(1) if ran_match else "?"
        fail_lines = re.findall(r"^(?:FAIL|ERROR):.*$", combined, re.MULTILINE)
        status = "pass" if (proc.returncode == 0 and not fail_lines) else "fail"
        metric = f"Ran {ran} tests, {len(fail_lines)} FAIL/ERROR" if fail_lines else f"Ran {ran} tests, 0 fail"
        detail = "\n".join(fail_lines[:5]) if fail_lines else ""
        return Result("test-scripts (unittest discover)", status, metric, detail)

    def check_oss_scan_keepset(self, repo_root: Path) -> Result:
        """Source-repo safety baseline: keep-set (live tracked files) has 0 blockers.

        A scanner input/configuration error is a failed gate, never an implicit
        zero-finding result.
        """
        pybin = _resolve_pybin(repo_root)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [pybin, "-B", "scripts/oss_release_scan.py", "--scope", "keep-set", "--format", "text", "--fail-on", "blocker"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
            env=env,
        )
        if proc.returncode == 2:
            return Result(
                "oss-scan keep-set (live-repo baseline)",
                "fail",
                "scanner input error",
                "scanner configuration failed",
            )
        match = re.search(r"blockers=(\d+)", proc.stdout)
        blockers = int(match.group(1)) if match else -1
        status = "pass" if (proc.returncode == 0 and blockers == 0) else "fail"
        return Result("oss-scan keep-set (live-repo baseline)", status, f"blockers={blockers}")

    def check_oss_scan_scope_all_personal_path(self, repo_root: Path) -> Result:
        """personal_path blockers under --scope all must be zero."""
        try:
            import oss_release_scan as scan_mod
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("oss-scan --scope all personal_path", "fail", "", f"import error: {exc}")
        try:
            findings = scan_mod.scan(repo_root, scope="all")
        except scan_mod.ScanInputError:
            return Result("oss-scan --scope all personal_path", "fail", "scanner input error", "scanner configuration failed")
        blockers = [f for f in findings if f.category == "personal_path" and f.severity == "blocker"]
        status = "pass" if not blockers else "fail"
        detail = "\n".join(f"{f.path}:{f.line} {f.token}" for f in blockers[:8])
        return Result("oss-scan --scope all personal_path", status, f"{len(blockers)} blockers", detail)

    def check_oss_scan_public_copy_personal_path(self, repo_root: Path) -> Result:
        """Resolved personal-path blockers under public-copy scope must be zero."""
        try:
            import oss_release_scan as scan_mod
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("oss-scan --scope public-copy personal_path", "fail", "", f"import error: {exc}")
        try:
            findings = scan_mod.scan(repo_root, scope="public-copy")
        except scan_mod.ScanInputError:
            return Result("oss-scan --scope public-copy personal_path", "fail", "scanner input error", "scanner configuration failed")
        blockers = [f for f in findings if f.category == "personal_path" and f.severity == "blocker"]
        status = "pass" if not blockers else "fail"
        detail = "\n".join(f"{f.path}:{f.line} {f.token}" for f in blockers[:8])
        return Result("oss-scan --scope public-copy personal_path", status, f"{len(blockers)} blockers", detail)

    def check_homebrew_outside_meta(self, repo_root: Path) -> Result:
        """Report /opt/homebrew/bin/python3 outside this verifier's local policy."""
        allowed = set(_HOMEBREW_GATE_ALLOWLIST)
        outside: list[tuple[str, int]] = []
        for path in _iter_text_files(repo_root, ("docs",)):
            rel = path.relative_to(repo_root).as_posix()
            if rel in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            count = text.count(_HOMEBREW_PY)
            if count:
                outside.append((rel, count))
        status = "pass" if not outside else "fail"
        detail = "\n".join(f"{p}: {c}" for p, c in outside[:8])
        return Result("homebrew python3 outside local allowlist", status, f"{sum(c for _, c in outside)} across {len(outside)} files", detail)

    def check_plan_lint_portability_plans(self, repo_root: Path) -> Result:
        if not self._portability_plans:
            return Result("plan_lint selected plans", "fail", "0 plans selected", "no portability plans selected")
        pybin = _resolve_pybin(repo_root)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        authority_context = None
        if _AUTHORITY_CONTEXT_ENV in os.environ:
            # An inherited assertion is an authority effect: validate it
            # before selecting a child command. Any malformed or stale
            # assertion raises here and is reported by the module boundary;
            # it must never fall back to the raw portability launch.
            import contract_authority_children
            from contract_authority_context import context_for_reader, context_to_json

            authority_context = context_for_reader(repo_root)
        fails: list[str] = []
        for plan in self._portability_plans:
            child_env = env
            if authority_context is None or authority_context.state == "legacy":
                # Preserve the legacy command and environment exactly when
                # no assertion was supplied, or when a supplied assertion
                # was itself verified as legacy above.
                command = [pybin, "-B", "scripts/plan_lint.py", plan]
            else:
                runtime_pin = authority_context.runtime_pin
                if runtime_pin is None:
                    raise RuntimeError("engaged authority context has no runtime pin")
                command = contract_authority_children.python_entry_argv(
                    authority_context,
                    runtime_pin.runtime_root / "scripts" / "plan_lint.py",
                    [plan],
                    python_executable=pybin,
                )
                child_env = dict(env)
                child_env[_AUTHORITY_CONTEXT_ENV] = context_to_json(authority_context)
            proc = subprocess.run(
                command,
                cwd=str(repo_root),
                text=True,
                capture_output=True,
                timeout=300,
                check=False,
                env=child_env,
            )
            if proc.returncode != 0:
                fails.append(plan)
        status = "pass" if not fails else "fail"
        detail = "\n".join(fails)
        count = len(self._portability_plans)
        return Result("plan_lint selected plans", status, f"{count - len(fails)}/{count} exit=0", detail)

    def check_corruption_artifacts(self, repo_root: Path) -> Result:
        """Sweep substitution damage with a verifier-local lesson policy."""
        allowed = set(_CORRUPTION_LESSON_ALLOWLIST)
        double_sub: list[str] = []
        real_collapses: list[str] = []
        lesson_collapses = 0
        for path in _iter_text_files(repo_root, ("scripts", "docs")):
            rel = path.relative_to(repo_root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if _DOUBLE_SUB_MARKER in text:
                double_sub.append(rel)
            if _TABLE_COLLAPSE_MARKER in text:
                if rel in allowed:
                    lesson_collapses += 1
                else:
                    real_collapses.append(rel)
        bad = double_sub + real_collapses
        status = "pass" if not bad else "fail"
        parts = [f"double-substitution={len(double_sub)}", f"real table-collapse={len(real_collapses)}"]
        if lesson_collapses:
            parts.append(f"local-lesson backticks={lesson_collapses} (allowlisted, ok)")
        detail = "\n".join(bad[:8])
        return Result("corruption artifacts", status, ", ".join(parts), detail)

    def check_portability_test_modules(self, repo_root: Path) -> Result:
        """Each portability-related test module runs green.

        Modules are discovered by filename pattern (see _PORTABILITY_TEST_PATTERNS),
        so the check adapts to the worktree's actual test set rather than
        asserting a fixed roster.
        """
        pybin = _resolve_pybin(repo_root)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        candidates = [
            repo_root / "scripts" / f"{name}.py"
            for name in _PORTABILITY_TEST_PATTERNS
            if (repo_root / "scripts" / f"{name}.py").exists()
        ]
        if not candidates:
            return Result("portability test modules", "fail", "0 modules discovered")
        fails: list[str] = []
        total = 0
        for mod_path in candidates:
            proc = subprocess.run(
                [pybin, "-m", "unittest", f"scripts.{mod_path.stem}"],
                cwd=str(repo_root),
                text=True,
                capture_output=True,
                timeout=300,
                check=False,
                env=env,
            )
            ran = re.search(r"^Ran (\d+) tests?", proc.stdout + proc.stderr, re.MULTILINE)
            if ran:
                total += int(ran.group(1))
            if proc.returncode != 0 or "FAILED" in (proc.stdout + proc.stderr):
                fails.append(mod_path.stem)
        status = "pass" if not fails else "fail"
        detail = "\n".join(fails)
        return Result("portability test modules", status, f"{len(candidates) - len(fails)}/{len(candidates)} modules OK ({total} tests)", detail)

    def check_manifest_validity(self, repo_root: Path) -> Result:
        snap_dir = self._archive_snapshot_dir(repo_root)
        if snap_dir is None:
            return Result("manifest validity", "fail", "", "archive snapshot not selected")
        manifest = snap_dir / "manifest.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            return Result("manifest validity", "fail", "", f"parse error: {exc}")
        db_path = data.get("source_db", {}).get("db_path", "")
        docs_count = data.get("source_db", {}).get("docs_count", "?")
        # Portable = no generic absolute user-home path. Both an env-substituted
        # form (${PLANVEYOR_ROOT}/...) and a repo-relative path (.tmp/...) are
        # portable; a concrete user-home path is not.
        try:
            import oss_release_scan as scan_mod
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("manifest validity", "fail", "", f"scanner import error: {exc}")
        personal_path = bool(scan_mod.PERSONAL_PATH_RE.search(db_path)) if db_path else False
        portable = bool(db_path) and not personal_path
        status = "pass" if portable else "fail"
        metric = f"db_path portable={portable}, docs_count={docs_count}"
        return Result("manifest validity", status, metric)

    def check_manifest_self_consistency(self, repo_root: Path) -> Result:
        """Manifest must be internally consistent AND match the JSONL artifact.

        Verifies (fail-closed on every committed archive contract):
        * artifact.path is a present, RELATIVE basename (no absolute/missing
          path silently defaulted to a conventional file).
        * artifact.{size_bytes,sha256,record_count} match the real JSONL on disk.
        * a selected storage_matrix[git_text_export] row exists and mirrors size.
        * artifact.record_count == source_db.docs_count.
        * sum(source_db.kind_counts) == source_db.docs_count (a hand-edit of one
          count field without the other is a contradiction).
        * source_db.kind_counts matches the ACTUAL per-kind distribution in the
          JSONL (a redistribution with the same sum is still drift).
        * WHEN the .tmp sqlite exists: source_db.content_bytes
          (sum(length(CAST(content AS BLOB))), docs_archive.py:449), db_sha256
          (sha256 of the file, docs_archive.py:85, 1 MiB streaming), and
          db_size_bytes (stat().st_size) all match. Drift in these three fields
          is reported as WARN when it is the only issue because the DB is ignored
          local state, not a committed archive artifact. These three are
          DB-DESCRIBING metrics (computed over the RAW DB), NOT derivable from
          the shipped JSONL (which is portabilized, changing byte length). The DB
          is gitignored (.gitignore) and ABSENT on fresh clones/CI; absence is
          the normal verify-time state -> these three are SKIPPED silently
          (metadata about a non-shipped file is never a false-red), never failed.
          db_path is a display field the producer portabilizes
          (docs_archive.py:464), so it is resolved in BOTH forms — repo-relative
          ``.tmp/...`` AND the producer's default env-substituted
          ``${PLANVEYOR_ROOT:-$HOME/planveyor}/.tmp/...`` (expanded to
          repo_root) — otherwise a producer-regenerated manifest would silently
          skip these checks. db_path PORTABILITY is NOT checked here — that is
          owned by check_manifest_validity (do not duplicate).
        """
        snap_dir = self._archive_snapshot_dir(repo_root)
        if snap_dir is None:
            return Result("manifest self-consistency", "fail", "", "archive snapshot not selected")
        manifest = snap_dir / "manifest.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            return Result("manifest self-consistency", "fail", "", f"parse error: {exc}")
        art = data.get("artifact", {}) or {}
        declared_path = art.get("path")

        committed_issues: list[str] = []
        local_db_issues: list[str] = []
        # artifact.path contract: present + relative basename (producer writes a
        # bare filename). Missing or absolute path is a drift, never a silent default.
        if not declared_path or not isinstance(declared_path, str):
            committed_issues.append("artifact.path missing (cannot resolve artifact)")
            artifact_name = "archived_docs.jsonl"
        elif os.path.isabs(declared_path) or "/" in declared_path:
            committed_issues.append(f"artifact.path={declared_path!r} must be a relative basename, not absolute/nested")
            artifact_name = "archived_docs.jsonl"
        else:
            artifact_name = declared_path

        artifact = snap_dir / artifact_name
        if not artifact.exists():
            committed_issues.append(f"artifact missing: {artifact_name}")
            actual_size = actual_sha = None
            actual_records = 0
        else:
            actual_bytes = artifact.read_bytes()
            actual_size = len(actual_bytes)
            actual_sha = hashlib.sha256(actual_bytes).hexdigest()
            actual_records = sum(1 for ln in actual_bytes.decode("utf-8", "replace").splitlines() if ln.strip())
            if art.get("size_bytes") != actual_size:
                committed_issues.append(f"artifact.size_bytes={art.get('size_bytes')} vs actual {actual_size}")
            if art.get("sha256") != actual_sha:
                committed_issues.append(f"artifact.sha256={art.get('sha256','')[:12]}... vs actual {actual_sha[:12]}...")
            if art.get("record_count") != actual_records:
                committed_issues.append(f"artifact.record_count={art.get('record_count')} vs actual {actual_records}")

        # storage_matrix: a selected git_text_export row MUST exist and mirror size.
        selected_text_row = next(
            (
                row
                for row in (data.get("storage_matrix", []) or [])
                if row.get("backend") == "git_text_export" and row.get("selected")
            ),
            None,
        )
        if selected_text_row is None:
            committed_issues.append("storage_matrix: no selected git_text_export row")
        elif actual_size is not None and selected_text_row.get("size_bytes") != actual_size:
            committed_issues.append(
                f"storage_matrix[git_text_export].size_bytes={selected_text_row.get('size_bytes')} vs actual {actual_size}"
            )

        source_db = data.get("source_db", {}) or {}
        # Producer contract (docs_archive.py:458-476 -> manifest.source_db via
        # :523) ALWAYS emits docs_count, kind_counts, content_bytes -- the very
        # fields this check cross-checks for value drift. A MISSING key
        # short-circuits the `if X is not None` gates below to no-issue (a
        # false-green), so absence is itself a contract violation = drift.
        # Assert presence with `is None` (not falsiness): docs_count=0 /
        # content_bytes=0 / kind_counts={} are legitimate empty-archive values.
        for _req_key in ("docs_count", "content_bytes"):
            if source_db.get(_req_key) is None:
                committed_issues.append(f"source_db.{_req_key} missing (producer contract)")
        if source_db.get("kind_counts") is None:
            committed_issues.append("source_db.kind_counts missing (producer contract)")
        docs_count = source_db.get("docs_count")
        if docs_count is not None and docs_count != actual_records:
            committed_issues.append(f"source_db.docs_count={docs_count} vs artifact records {actual_records}")
        # kind_counts must match the ACTUAL per-kind distribution in the JSONL,
        # not merely sum to docs_count — a redistribution (same sum, different
        # per-kind values) would otherwise pass, leaving a lineage hole.
        kind_counts = source_db.get("kind_counts")
        if isinstance(kind_counts, dict) and actual_records:
            actual_kind_counts: dict[str, int] = {}
            for ln in actual_bytes.decode("utf-8", "replace").splitlines():  # type: ignore[union-attr]
                if not ln.strip():
                    continue
                try:
                    rec = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                # Mirror the producer's serialization (docs_archive writes
                # "kind": str(kind), where kind is TEXT NOT NULL): absent key or
                # explicit null both normalize to "" so a malformed null kind
                # counts consistently rather than colliding with a literal
                # "None" kind value.
                raw_kind = rec.get("kind", "") if isinstance(rec, dict) else ""
                k = "" if raw_kind is None else str(raw_kind)
                actual_kind_counts[k] = actual_kind_counts.get(k, 0) + 1
            if actual_kind_counts != dict(kind_counts):
                committed_issues.append(
                    f"source_db.kind_counts={kind_counts} vs actual per-kind {actual_kind_counts}"
                )
        elif isinstance(kind_counts, dict) and docs_count is not None:
            # No artifact to compare against (file missing) — still catch a
            # self-contradiction: kind_counts must sum to docs_count.
            if sum(kind_counts.values()) != docs_count:
                committed_issues.append(
                    f"source_db.sum(kind_counts)={sum(kind_counts.values())} != docs_count={docs_count}"
                )

        # source_db.content_bytes / db_sha256 / db_size_bytes are all
        # DB-DESCRIBING metrics: the producer computes them over the RAW .tmp
        # sqlite (content_bytes = sum(length(CAST(content AS BLOB))) at
        # docs_archive.py:449; db_sha256 = sha256(file); db_size_bytes =
        # stat().st_size). They are NOT derivable from the shipped JSONL: the
        # JSONL is PORTABILIZED (export runs content through portabilize_text,
        # which changes byte length when it rewrites local paths), whereas these
        # metrics describe the raw DB. So a JSONL cross-check would false-red
        # whenever portabilize changes length (it does for any local-path-bearing
        # record). Instead, like db_sha256/db_size_bytes, content_bytes is
        # verified against the DB when present and SKIPPED when the DB is absent.
        # When present but stale/corrupt, the DB branch is a warning-only
        # remediation lane unless committed manifest/JSONL issues are also
        # present. db_path portability stays owned by check_manifest_validity.
        #
        # db_path is a DISPLAY field the producer portabilizes (docs_archive.py:464),
        # so it can be EITHER a repo-relative ".tmp/..." OR the producer's default
        # env-substituted "${PLANVEYOR_ROOT:-$HOME/planveyor}/.tmp/...".
        # The env-substituted form is the PRODUCER DEFAULT for a portable
        # environment-root db_path; if we only resolved the relative form, every
        # producer-regenerated manifest would silently skip these checks (a
        # permanent false-green). Resolve BOTH forms to repo_root (the canonical
        # expansion of ${PLANVEYOR_ROOT} at verify time is the repo under
        # test) so the present DB is actually checked. A personal absolute
        # path is left unresolved (it is a validity failure owned by
        # check_manifest_validity, and resolving it would embed machine state).
        declared_db_path = source_db.get("db_path")
        db_candidate: Path | None = None
        if isinstance(declared_db_path, str) and declared_db_path:
            if declared_db_path.startswith(_PORTABLE_FULL + "/"):
                # Producer default: strip the portable tooling-root prefix,
                # resolve the remainder under repo_root.
                db_candidate = repo_root / declared_db_path[len(_PORTABLE_FULL) + 1:]
            elif not os.path.isabs(declared_db_path):
                # Repo-relative form (e.g. ".tmp/planveyor_docs_archive.sqlite").
                db_candidate = repo_root / declared_db_path
        if db_candidate is not None and db_candidate.exists():
            try:
                db_display = str(db_candidate.relative_to(repo_root))
            except ValueError:
                db_display = str(db_candidate)
            actual_db_size = db_candidate.stat().st_size
            if source_db.get("db_size_bytes") != actual_db_size:
                local_db_issues.append(
                    f"source_db.db_size_bytes={source_db.get('db_size_bytes')} vs actual {actual_db_size}"
                )
            # content_bytes: recompute from the RAW DB (sum of UTF-8 byte length
            # of the content column), mirroring the producer's SQL
            # sum(length(CAST(content AS BLOB))) (docs_archive.py:449). NULL
            # content contributes 0 (SQLite sum skips NULL).
            actual_content_bytes = 0
            try:
                import sqlite3 as _sqlite3

                _db_conn = _sqlite3.connect(str(db_candidate))
                try:
                    _row = _db_conn.execute(
                        "SELECT coalesce(sum(length(CAST(content AS BLOB))),0) FROM archived_docs"
                    ).fetchone()
                finally:
                    _db_conn.close()
                actual_content_bytes = int(_row[0]) if _row else 0
            except Exception as exc:  # pragma: no cover - corrupt/unreadable DB
                local_db_issues.append(f"content_bytes recompute failed: {exc}")
            else:
                if source_db.get("content_bytes") != actual_content_bytes:
                    local_db_issues.append(
                        f"source_db.content_bytes={source_db.get('content_bytes')} vs actual {actual_content_bytes}"
                    )
            db_hasher = hashlib.sha256()
            with db_candidate.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    db_hasher.update(chunk)
            actual_db_sha = db_hasher.hexdigest()
            if source_db.get("db_sha256") != actual_db_sha:
                local_db_issues.append(
                    f"source_db.db_sha256={str(source_db.get('db_sha256', ''))[:12]}... vs actual {actual_db_sha[:12]}..."
                )

        status = "fail" if committed_issues else "warn" if local_db_issues else "pass"
        total_issues = len(committed_issues) + len(local_db_issues)
        if total_issues:
            metric = (
                f"{total_issues} field drift(s): "
                f"committed={len(committed_issues)}, ignored_db={len(local_db_issues)}"
            )
        else:
            metric = "0 field drift(s)"
        detail_parts = list(committed_issues)
        if local_db_issues:
            detail_parts.append(
                "ignored local archive DB drift: "
                f"{db_display}; remediation: delete the ignored local DB or regenerate it "
                "from committed archive snapshot state, then rerun verify; do not commit .tmp state"
            )
            detail_parts.extend(local_db_issues)
        return Result("manifest self-consistency", status, metric, "\n".join(detail_parts))

    def check_archive_db_label_portability(self, repo_root: Path) -> Result:
        """Archived records' extra_json.db must not carry personal paths.

        Fail-closed on every shape: malformed JSONL, malformed extra_json, AND
        a valid-but-non-object extra_json (e.g. ``[]``, ``42``, ``"str"``) are
        all reported as leaks — a non-object cannot be inspected for a ``db``
        key, so it cannot be trusted as clean. Detection is generic (any
        a concrete user-home root per the scanner's PERSONAL_PATH_RE). The dump is
        located via manifest.artifact.path; absence is a FAIL (the gate checks
        nothing if the dump is missing), not a silent warn-green.
        """
        try:
            import oss_release_scan as scan_mod
            users_re = scan_mod.PERSONAL_PATH_RE
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("archive db_label portability", "fail", "", f"scanner import error: {exc}")
        snap_dir = self._archive_snapshot_dir(repo_root)
        if snap_dir is None:
            return Result("archive db_label portability", "fail", "", "archive snapshot not selected")
        manifest = _load_archive_manifest(snap_dir)
        if manifest is None:
            return Result("archive db_label portability", "fail", "", "manifest missing")
        artifact_name = _manifest_artifact_path(manifest)
        dump = snap_dir / artifact_name
        if not dump.exists():
            return Result("archive db_label portability", "fail", "", f"archive dump absent: {artifact_name}")
        total = 0
        leaking: list[str] = []
        for ln in dump.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.strip():
                continue
            total += 1
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                leaking.append(f"<malformed JSONL record #{total}>")
                continue
            if not isinstance(rec, dict) or "extra_json" not in rec:
                leaking.append(f"<record #{total} missing extra_json>")
                continue
            extra = rec.get("extra_json", "")
            try:
                meta = json.loads(extra) if extra else {}
            except json.JSONDecodeError:
                leaking.append(f"<record #{total} malformed extra_json>")
                continue
            if not isinstance(meta, dict):
                # Valid JSON but not an object (e.g. [], 42, "str"): cannot
                # carry/inspect a db key, so it cannot be trusted as clean.
                leaking.append(f"<record #{total} non-object extra_json ({type(meta).__name__})>")
                continue
            db_label = str(meta.get("db", ""))
            hit = bool(users_re.search(db_label))
            if hit:
                leaking.append(db_label)
        status = "pass" if not leaking else "fail"
        detail = leaking[0] if leaking else ""
        metric = f"{total - len(leaking)}/{total} records clean"
        return Result("archive db_label portability", status, metric, detail)

    def check_archive_content_portability(self, repo_root: Path) -> Result:
        r"""Archived records' content must obey generic portability rules.

        The producer portabilizes content before sha256, so every record must
        remain unchanged under the selected ``PortabilityRules``. The gate also
        rejects every resolved generic user-home path even when a selected rule
        leaves it idempotent. A bare user-home token can be prose, while the
        scanner placeholder form is syntax rather than a resolved path.
        Fail-closed on malformed JSONL.
        """
        try:
            import portability_substitution as ps
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("archive content portability", "fail", "", f"import error: {exc}")
        try:
            import oss_release_scan as scan_mod
            users_re = scan_mod.PERSONAL_PATH_RE
        except Exception as exc:  # pragma: no cover - import path failure
            return Result("archive content portability", "fail", "", f"scanner import error: {exc}")
        snap_dir = self._archive_snapshot_dir(repo_root)
        if snap_dir is None:
            return Result("archive content portability", "fail", "", "archive snapshot not selected")
        manifest = _load_archive_manifest(snap_dir)
        if manifest is None:
            return Result("archive content portability", "fail", "", "manifest missing")
        artifact_name = _manifest_artifact_path(manifest)
        dump = snap_dir / artifact_name
        if not dump.exists():
            return Result("archive content portability", "fail", "", f"archive dump absent: {artifact_name}")
        total = 0
        leaking: list[str] = []
        for ln in dump.read_text(encoding="utf-8", errors="replace").splitlines():
            if not ln.strip():
                continue
            total += 1
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                leaking.append(f"<malformed JSONL record #{total}>")
                continue
            if not isinstance(rec, dict) or "content" not in rec:
                leaking.append(f"<record #{total} missing content>")
                continue
            content = str(rec.get("content", ""))
            # A selected normalizer can still declare a value nonportable. The
            # scanner-derived check independently rejects every resolved
            # user-home path without an identity-specific exception.
            non_idempotent = content != ps.portabilize_text(
                content,
                rules=self._portability_rules,
            )
            resolved_user_home_path = _has_resolved_user_home_path(content, users_re)
            if non_idempotent or resolved_user_home_path:
                snippet = content[:80].replace("\n", " ")
                if non_idempotent:
                    tag = "non-idempotent"
                else:
                    tag = "resolved-user-home-path"
                leaking.append(f"<record #{total}> {tag} {snippet!r}")
        status = "pass" if not leaking else "fail"
        detail = leaking[0] if leaking else ""
        metric = f"{total - len(leaking)}/{total} records portability-clean"
        return Result("archive content portability", status, metric, detail)

    def check_plans_status(self, repo_root: Path) -> Result:
        """Every explicitly selected plan must carry a completed status."""
        if not self._portability_plans:
            return Result("selected plans status", "fail", "0 plans selected", "no portability plans selected")
        issues: list[str] = []
        for plan in self._portability_plans:
            try:
                text = (repo_root / plan).read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(f"{plan}: unreadable: {exc}")
                continue
            status_match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", text, re.MULTILINE)
            status_val = status_match.group(1) if status_match else "<missing>"
            # Match "Done" as a status prefix (tolerant of "Done (parked)"), but
            # reject "Not Done" / "Undone" — mirrors merge_bundle_report's
            # norm.startswith("done") idiom.
            if not status_val.strip().lower().startswith("done"):
                issues.append(f"{Path(plan).name}: Status={status_val}")
        status = "pass" if not issues else "fail"
        count = len(self._portability_plans)
        return Result("selected plans status", status, f"{count} plan(s), Done", "\n".join(issues))

    # -- orchestration ------------------------------------------------------ #
    def run(self, repo_root: Path) -> list[Result]:
        checks = []
        if self._full:
            checks.append(self.check_test_scripts)
        checks.extend(
            [
                self.check_oss_scan_keepset,
                self.check_oss_scan_scope_all_personal_path,
                self.check_homebrew_outside_meta,
            ]
        )
        if self._portability_plans:
            checks.append(self.check_plan_lint_portability_plans)
        checks.extend(
            [
                self.check_corruption_artifacts,
                self.check_oss_scan_public_copy_personal_path,
            ]
        )
        if self._archive_snapshot is not None:
            checks.extend(
                [
                    self.check_manifest_validity,
                    self.check_manifest_self_consistency,
                    self.check_archive_db_label_portability,
                    self.check_archive_content_portability,
                ]
            )
        if self._portability_plans:
            checks.append(self.check_plans_status)
        results: list[Result] = []
        for check in checks:
            try:
                results.append(check(repo_root))
            except Exception as exc:  # one check failing must not abort the suite
                results.append(Result(check.__name__.removeprefix("check_"), "fail", "", f"exception: {exc!r}"))
        return results

    def interpret(self, results: list[Result]) -> str:
        fails = [r for r in results if r.status == "fail"]
        warns = [r for r in results if r.status == "warn"]
        applicability_note = self._unselected_applicability_note()
        if not fails and not warns:
            return "All applicable portability gates pass." + applicability_note
        if not fails:
            lines = [f"{len(warns)} portability warning(s); VERDICT remains GREEN:"]
            for r in warns:
                lines.append(f"  - {r.name}: {r.metric}")
                if r.detail:
                    lines.append(f"      {r.detail.splitlines()[0]}")
            return "\n".join(lines) + applicability_note
        lines = [f"{len(fails)} portability check(s) failed:"]
        for r in fails:
            lines.append(f"  - {r.name}: {r.metric}")
            if r.detail:
                lines.append(f"      {r.detail.splitlines()[0]}")
        pp = next((r for r in results if "personal_path" in r.name and r.status == "fail"), None)
        if pp:
            lines.append(
                "  >> portable-path verification VIOLATED: personal_path residuals require a substitution "
                "re-sweep (this is the portability workstream's responsibility)."
            )
        return "\n".join(lines) + applicability_note


# --------------------------------------------------------------------------- #
# Manifest / artifact helpers
# --------------------------------------------------------------------------- #
def _load_archive_manifest(snapshot_dir: Path) -> dict | None:
    """Load an explicitly selected archive snapshot manifest, if present."""
    manifest = snapshot_dir / "manifest.json"
    if not manifest.exists():
        return None
    return json.loads(manifest.read_text(encoding="utf-8"))


def _manifest_artifact_path(manifest: dict) -> str:
    """Resolve the declared artifact path from the manifest (relative basename).

    The producer always writes a relative basename (docs_path.name). An absolute
    or missing path is a contract violation surfaced by check_manifest_self_consistency;
    this helper returns the declared relative path when valid, else the conventional
    default so downstream checks still point at a concrete file.
    """
    declared = (manifest.get("artifact", {}) or {}).get("path")
    if isinstance(declared, str) and declared and not os.path.isabs(declared) and "/" not in declared:
        return declared
    return "archived_docs.jsonl"


# --------------------------------------------------------------------------- #
# File iteration helper
# --------------------------------------------------------------------------- #
def _extract_section(text: str, heading: str) -> str:
    """Return the body of a ``## <heading>`` section up to the next ``## `` heading.

    Kept as a generic section parser for callers that need to scope marker
    searches away from append-only evidence or log prose.
    """
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    return m.group(1) if m else ""


def _iter_text_files(repo_root: Path, subdirs: tuple[str, ...]) -> Iterable[Path]:
    """Yield readable text files under each subdir, skipping build artifacts.

    The verifier's own source (and its test) are excluded because they carry
    marker literals that the corruption checks look for — exactly like
    oss_release_scan.py carries its own sample tokens.
    """
    skip_dirs = {"__pycache__", ".git", ".tmp"}
    self_exclude = {("scripts", "verify_suite.py"), ("scripts", "test_verify_suite.py")}
    for sub in subdirs:
        base = repo_root / sub
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(repo_root).parts
            if any(part in skip_dirs for part in parts):
                continue
            if parts in self_exclude or parts[-2:] in self_exclude:
                continue
            if path.suffix.lower() in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".db", ".gz", ".7z"}:
                continue
            yield path


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _render_plain(modules_out: list[dict]) -> str:
    lines: list[str] = []
    total_checks = sum(len(m["results"]) for m in modules_out)
    lines.append(f"== verify-suite: {len(modules_out)} module(s), {total_checks} check(s) ==")
    for m in modules_out:
        for r in m["results"]:
            dots = "." * max(2, 38 - len(r["name"]))
            tag = r["status"].upper()
            metric = f"  ({r['metric']})" if r["metric"] else ""
            lines.append(f"[{m['name']}] {r['name']} {dots} {tag}{metric}")
        lines.append("---")
    any_fail = any(r["status"] == "fail" for m in modules_out for r in m["results"])
    verdict = "RED" if any_fail else "GREEN"
    lines.append(f"VERDICT: {verdict}")
    for m in modules_out:
        if m["interpretation"]:
            lines.append(f"INTERPRETATION [{m['name']}]:")
            for ln in m["interpretation"].splitlines():
                lines.append(f"  {ln}")
    return "\n".join(lines)


def _render_json(modules_out: list[dict]) -> str:
    any_fail = any(r["status"] == "fail" for m in modules_out for r in m["results"])
    payload = {
        "verdict": "RED" if any_fail else "GREEN",
        "modules": modules_out,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _load_modules(
    selected: list[str],
    *,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
    portability_plans: tuple[str, ...] = (),
    archive_snapshot: str | None = None,
    full: bool = False,
) -> list[ModuleBase]:
    available = {cls.name: cls for cls in _REGISTRY}
    instances: list[ModuleBase] = []

    def instantiate(cls: type[ModuleBase]) -> ModuleBase:
        if cls is PortabilityModule:
            return PortabilityModule(
                portability_rules=portability_rules,
                portability_plans=portability_plans,
                archive_snapshot=archive_snapshot,
                full=full,
            )
        return cls()

    if selected:
        for name in selected:
            if name not in available:
                # Gate-script convention (matches merge_bundle_report): usage
                # errors exit 2, not argparse's default 1.
                print(
                    f"error: unknown module {name!r}; available: {sorted(available)}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            instances.append(instantiate(available[name]))
    else:
        instances = [instantiate(cls) for cls in _REGISTRY]
    return instances


def _repo_relative_input_path(value: str) -> str:
    """Normalize a CLI applicability input without allowing repo escape."""
    raw = value.strip()
    candidate = Path(raw)
    if not raw or candidate == Path(".") or candidate.is_absolute() or ".." in candidate.parts:
        raise argparse.ArgumentTypeError("must be a nonempty repo-relative path without '..'")
    return candidate.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_suite.py",
        description="Registry-driven integrity checks with summary report + interpretation.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--format", choices=("plain", "json"), default="plain", help="Output format")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved public content profile; all use generic portability rules.",
    )
    parser.add_argument(
        "--portability-plan",
        action="append",
        default=[],
        type=_repo_relative_input_path,
        metavar="REPO_RELATIVE_PATH",
        help="Plan explicitly included in portability verification (repeatable).",
    )
    parser.add_argument(
        "--archive-snapshot",
        type=_repo_relative_input_path,
        metavar="REPO_RELATIVE_DIR",
        help="Archive snapshot directory explicitly included in portability verification.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full",
        action="store_true",
        help="Add one canonical unittest discovery to the aggregate verification route.",
    )
    mode.add_argument(
        "--module",
        action="append",
        default=[],
        help="Module to run (repeatable). Default: all registered modules.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"error: repo-root is not a directory: {repo_root}", file=sys.stderr)
        return 2

    try:
        portability_rules = load_portability_rules(content_profile_id=args.content_profile_id)
    except PortabilityPolicyError as e:
        print(f"error: portability policy invalid: {e}", file=sys.stderr)
        return 2

    modules = _load_modules(
        args.module,
        portability_rules=portability_rules,
        portability_plans=tuple(args.portability_plan),
        archive_snapshot=args.archive_snapshot,
        full=args.full,
    )
    modules_out: list[dict] = []
    for mod in modules:
        results = mod.run(repo_root)
        modules_out.append(
            {
                "name": mod.name,
                "results": [asdict(r) for r in results],
                "interpretation": mod.interpret(results),
            }
        )

    if args.format == "json":
        sys.stdout.write(_render_json(modules_out) + "\n")
    else:
        sys.stdout.write(_render_plain(modules_out) + "\n")

    return 2 if any(r["status"] == "fail" for m in modules_out for r in m["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

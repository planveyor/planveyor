import hashlib
import fnmatch
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import consumer_contract
import oss_release_scan as scan_mod


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "copier_template"
LAUNCH_GUIDE = TEMPLATE_ROOT / "docs" / "README.md.jinja"
LOCAL_HEADINGS = (
    "## Локальные правила стека",
    "## Разрешённое локальное переопределение процесса",
)
COMMON_LOCAL_GUIDE = "## Как заполнять локальные секции sibling"
ENGINE_GOLDEN_PATH = '"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"'
ENGINE_GOLDEN_PATH_PREFIX = '"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md'
ENGINE_LIFECYCLE_PATH = '"$PLANVEYOR_RUNTIME_ROOT/docs/guides/lifecycle-and-packets.md"'

READY_FILES = {
    "Architect / development": "docs/tools/prompts/architect_status_driven.md",
    "Planner / development": "docs/tools/prompts/planner_status_driven.md",
    "Coder / development": "docs/tools/prompts/coder_status_driven.md",
    "Coder / migration gate": "docs/tools/prompts/coder_migrations_gate.md",
    "Reviewer / role": "docs/tools/prompts/reviewer_status_driven.md",
    "Reviewer / staged or commit review": "docs/playbooks/review_staged_or_commit.md",
    "Reviewer / merge-range review": "docs/playbooks/review_merge_range.md",
    "Post-merge / audit": "docs/playbooks/post_merge_audit.md",
}

# SHA-256 of the bytes from the first local heading to the end of each carrier file.
# Upgrade compares these bytes in every sibling before and after Copier; any change
# here (placeholder, heading or trailing text) blocks the upgrade of every sibling.
LOCAL_SECTION_TAIL_SHA256 = {
    "docs/tools/prompts/architect_status_driven.md": "d5952d867e00de28470d02f93bb4fe0fbf80b0a890ae6c43e6106d5c248bbe9f",
    "docs/tools/prompts/planner_status_driven.md": "cc6258f7ca01660b532dfefa572477b13b5ef0ee8e6e78a8fe7795660b0b7b07",
    "docs/tools/prompts/coder_status_driven.md": "060cb3730a026e076f9e3ac1ad599e2a24d1a9b67d8f2a4005a8a8f94c83273b",
    "docs/tools/prompts/coder_migrations_gate.md": "2f916188594040153d76f34f166f167851ce0189b7e737c6057e207c3cbcbaa9",
    "docs/tools/prompts/reviewer_status_driven.md": "2f916188594040153d76f34f166f167851ce0189b7e737c6057e207c3cbcbaa9",
    "docs/playbooks/review_staged_or_commit.md": "867e19cd7285ae26683a4f8320acea7c55349d5a50f8dcf5a586bd1e3267154d",
    "docs/playbooks/review_merge_range.md": "2f916188594040153d76f34f166f167851ce0189b7e737c6057e207c3cbcbaa9",
    "docs/playbooks/post_merge_audit.md": "2f916188594040153d76f34f166f167851ce0189b7e737c6057e207c3cbcbaa9",
}

# Sections 2-10 of the accepted pre-change brief; only purpose/readiness in
# section 1 belongs to the ordinary Owner-task guidance change.
STACK_BRIEF_REMAINDER_SHA256 = "ed952d551357246a3536479e6c9c25d97d3f1697d95efbeed33cc8b20e157c9d"

# Phase prompts that must send the role to the carrier of that phase (a playbook, or
# the role prompt the phase does not load), so the sibling-owned local sections of
# the carrier reach the role run.
PHASE_PLAYBOOK_POINTERS = {
    "docs/tools/prompts/reviewer_status_driven.md": (
        "docs/playbooks/review_staged_or_commit.md",
        "docs/playbooks/review_merge_range.md",
    ),
    "docs/tools/prompts/architect_post_merge_audit.md": ("docs/playbooks/post_merge_audit.md",),
    # planveyor_arch_initial sends only the draft discussion prompt.
    "docs/tools/prompts/architect_draft_discussion.md": ("docs/tools/prompts/architect_status_driven.md",),
}

# A direct engine call from a delivered document fails in a sibling: it has no scripts/ or bin/.
ENGINE_CALL_RE = re.compile(
    r"(?:\bpython3?|\$\{?PYBIN\}?\"?|\bbash|\bzsh)\s+(?:-B\s+)?(?:\./)?scripts/[\w./-]+"
    r"|(?<![\w/$])\./bin/planveyor\b"
)
# Markers that scope a section or line to the Planveyor checkout itself.
SELF_PLANVEYOR_MARKERS = ("Self-Planveyor", "physical Planveyor root", "Planveyor source root")
# bin/planveyor runs every command in its own child process and defines nothing in
# the caller's shell, so a code line that starts with a bare engine function fails
# in a sibling with `command not found`. Prompt prefixes `$ ` and `! ` count as indent.
CODE_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
BARE_ENGINE_FUNCTION_RE = re.compile(r"^[ \t]*(?:\$[ \t]+|![ \t]*)?(planveyor_[A-Za-z0-9_]+)")
# Engine helpers whose --root defaults to the engine checkout when run directly.
ROOT_DEFAULTING_ENGINE_HELPERS = ("scripts/codex_session_context.py",)

# A concrete docs/<file> mention in a delivered document must resolve inside the sibling.
DOC_PATH_MENTION_RE = re.compile(r"(?<![\w/$.{-])docs/[A-Za-z0-9_./*?\[\]-]*[A-Za-z0-9_/*?\]]")
MARKDOWN_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
DOC_PATH_PLACEHOLDER_TOKENS = ("YYYYMMDD", "YYMMDD", "HHMM", "NNN", "...")
# Files the sibling itself owns or generates; delivered docs name them only as
# optional target-local canon or as helper output, never as engine documents.
SIBLING_OWNED_DOC_PATHS = frozenset(
    {
        # Optional target-local canon, used only when the sibling has it or declares it.
        "docs/api.md",
        "docs/arch.md",
        "docs/registry.md",
        "docs/roadmap.md",
        "docs/schema.md",
        "docs/tests.md",
        "docs/code_reviews/README.md",
        "docs/doc_reviews/README.md",
        # Created by the sibling's stack adaptation plan from docs/_template_stack_brief.md.
        "docs/stack_brief.md",
        # Generated inside the sibling by its own helper runs.
        "docs/followups/index.md",
        "docs/process_improvements/promotion_surface.md",
        "docs/_meta/archive_snapshots/current/archived_docs.jsonl",
        "docs/_meta/archive_snapshots/current/manifest.json",
    }
)

# Supported target namespaces come from existing output/override contracts.
# This permits their directory/pattern references, never an arbitrary concrete file.
SIBLING_DOC_NAMESPACE_CONTRACTS = {
    "docs/analysis_packs": ("docs/playbooks/analysis_wave.md", "docs/analysis_packs/<plan_stem>.md"),
    "docs/code_reviews/assets": ("docs/code_reviews/_template_merge_range.md", "Store in: `docs/code_reviews/assets/"),
    "docs/doc_reviews/assets": ("docs/doc_reviews/_template_merge_range.md", "docs/doc_reviews/assets/<REVIEW_BASENAME>/"),
    "docs/code_reviews/profiles": ("docs/playbooks/review_merge_range.md", "docs/code_reviews/profiles/<repo_profile>/"),
    "docs/doc_reviews/profiles": ("docs/playbooks/review_docs_staged_or_commit.md", "docs/doc_reviews/profiles/<repo_profile>/"),
    "docs/reviews/profiles": ("docs/playbooks/post_merge_plan_harvest.md", "docs/reviews/profiles/<repo_profile>/"),
    "docs/snapshots": ("docs/playbooks/snapshot.md", "Сохрани этот snapshot в файл: `docs/snapshots/"),
    "docs/contract_notices": ("docs/playbooks/docs_architecture.md", "docs/contract_notices/<change-id>.json"),
}

# Public model wording policy is independent of the external private dictionary.
# MinIO and the exact default lane model spelling stay allowed.
PUBLIC_MODEL_FINGERPRINT_RE = re.compile(r"\b(?:GLM|Grok|(?<!GPT-6\.1 )Sol|Astra)\b")

# Directories whose delivered copy must hold exactly the same tracked file set as docs/<dir>.
MIRRORED_TEMPLATE_DIRECTORIES = (
    "docs/_meta",
    "docs/adr",
    "docs/playbooks",
    "docs/roles",
    "docs/tools/prompts",
    "docs/tools/prompts/zcode",
    ".agents/skills/planveyor-plan-draft",
    ".agents/skills/planveyor-plan-draft/agents",
    ".agents/skills/planveyor-plan-queue",
    ".agents/skills/planveyor-plan-queue/agents",
)
# Directories that deliver only selected files. The engine keeps its own work
# artifacts here (plans, reviews, packets, backlogs), but every tracked
# `_template*` file of the engine directory must be delivered.
PARTIAL_TEMPLATE_DIRECTORIES = (
    "docs",
    "docs/code_drafts",
    "docs/code_reviews",
    "docs/doc_reviews",
    "docs/followups",
    "docs/plans",
    "docs/process_improvements",
    "docs/reviews",
    "docs/rollout_packets",
    "docs/upstream_packets",
)
TEMPLATE_RENDERED_ONLY = frozenset({".gitignore"})
# Copier excludes these by default; macOS Finder may leave them in either tree.
COPIER_EXCLUDED_NAMES = frozenset({".DS_Store"})


def _delivered_fingerprint_offenders(root: Path, template_root: Path) -> list[str]:
    rules = scan_mod.load_marker_rules(root)
    offenders = []
    for path in sorted(template_root.rglob("*")):
        if not path.is_file() or path.name in COPIER_EXCLUDED_NAMES:
            continue
        relative = path.relative_to(template_root).as_posix()
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in PUBLIC_MODEL_FINGERPRINT_RE.finditer(line):
                offenders.append(f"{scan_mod.safe_path(relative, rules)}:{line_no}: {match.group(0)}")
        for finding in scan_mod.marker_findings(text, relative, "public-copy", rules):
            offenders.append(f"{finding.path}:{finding.line}: {finding.category}: {finding.token}")
    return offenders


# Codex loads repository skills from .agents/skills; the engine keeps their
# sources under skills/, so those template copies map to a different prefix.
TEMPLATE_SOURCE_PREFIXES = ((".agents/skills/", "skills/"),)


def _engine_source(relative: str) -> str:
    for template_prefix, engine_prefix in TEMPLATE_SOURCE_PREFIXES:
        if relative.startswith(template_prefix):
            return engine_prefix + relative[len(template_prefix):]
    return relative


def _tracked_names(directory: str) -> set[str]:
    """Names of tracked files directly inside a repository directory.

    Untracked work files (a scratch plan, an editor backup) must not decide
    which files a sibling receives, so the file sets come from the Git index.
    """
    listed = subprocess.run(
        ("git", "ls-files", "-z", "--", directory),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    prefix = directory.rstrip("/") + "/"
    return {
        entry[len(prefix):]
        for entry in listed.stdout.split("\0")
        if entry.startswith(prefix) and "/" not in entry[len(prefix):]
    }

ENGINE_GOLDEN_REFERENCE_FILES = (
    "docs/tools/prompts/planner_status_driven.md",
    "docs/tools/prompts/reviewer_status_driven.md",
    "docs/tools/prompts/architect_post_merge_audit.md",
    "docs/tools/prompts/architect_plan_harvest.md",
    "docs/playbooks/decomposition_wave.md",
    "docs/playbooks/post_merge_plan_harvest.md",
    "docs/playbooks/post_merge_audit.md",
    "docs/playbooks/doc_gardening.md",
)


class SiblingContractDocsTest(unittest.TestCase):
    def test_review_scope_callers_keep_phase_specific_gate_contract(self) -> None:
        reviewer_paths = (
            "docs/roles/reviewer.md", "docs/tools/prompts/reviewer_status_driven.md",
            "docs/playbooks/review_staged_or_commit.md", "docs/playbooks/review_docs_staged_or_commit.md",
            "docs/code_reviews/README.md", "docs/doc_reviews/README.md",
        )
        planner_paths = (
            "docs/roles/planner.md", "docs/tools/prompts/planner_status_driven.md",
            "docs/roles/architect.md", "docs/tools/prompts/architect_status_driven.md",
            "docs/plans/README.md", "docs/plans/_template.md", "docs/code_drafts/_template.md",
            "skills/planveyor-plan-draft/SKILL.md",
        )
        for rel in (*reviewer_paths, *planner_paths):
            with self.subTest(path=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("planveyor_plan_bundle --scope-check", text)
                self.assertIn("--check", text)
                self.assertRegex(text, r"(?i)strict|строг")
                self.assertRegex(text, r"(?i)inventory|integrity")
                if rel in planner_paths:
                    self.assertIn("--preflight", text)
                    self.assertIn("materialized", text)
                    self.assertRegex(text, r"(?i)semantic lint")
                    self.assertRegex(text, r"(?i)handoff digest")
                copier = TEMPLATE_ROOT / rel
                if rel.startswith("skills/"):
                    copier = TEMPLATE_ROOT / ".agents" / rel
                if copier.is_file():
                    self.assertEqual(copier.read_bytes(), (ROOT / rel).read_bytes())
        for rel in ("docs/playbooks/review_staged_or_commit.md", "docs/playbooks/review_docs_staged_or_commit.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            process = text.split("## Процесс", 1)[1]
            scope = process.index("--scope-check")
            self.assertLess(scope, process.index("--check", scope))
        guidance = (ROOT / "scripts/plan_lint.py").read_text(encoding="utf-8")
        self.assertIn("first executable handoff", guidance)
        self.assertIn("Genuine refinement", guidance)
        self.assertNotIn("Run `source scripts/planveyor.zsh && planveyor_plan_bundle --preflight", guidance)
        architect = (ROOT / "docs/tools/prompts/architect_status_driven.md").read_text(encoding="utf-8")
        self.assertIn("--as-status Done", architect)
        self.assertIn("closeout_pending", architect)

    def test_sibling_tui_template_and_f12_keep_mode_and_row_contract(self) -> None:
        import followups_index_rebuild

        template = (TEMPLATE_ROOT / "AGENTS.md.jinja").read_text(encoding="utf-8")
        for marker in ("planveyor sibling tui", "COMMIT_POLICY=native_existing",
                       "planveyor sibling architect", "planveyor sibling run",
                       "COMMIT_POLICY=human_explicit", "close --commit", "preview/preflight",
                       "simulated Done lint", "final ordinary lint", "rollback", "owning non-Done",
                       "узкое разрешение", "полного запроса", "blanket grants", "sandbox",
                       "docs `no_op`", "fresh canonical readback", "push/publication"):
            self.assertIn(marker, template)
        release = (ROOT / "docs/release_backlog.md").read_text(encoding="utf-8")
        f12 = release.split("### F12\n", 1)[1].split("### F13\n", 1)[0]
        for marker in ("sibling tui", "native_existing", "sibling run", "human_explicit",
                       "git_writable=false", "preflight", "no_op", "rollback",
                       "F12 остаётся open", "без blanket grants", "F13/rebinding"):
            self.assertIn(marker, f12)
        backlog = (ROOT / "docs/followups/release_backlog.md").read_text(encoding="utf-8")
        rows = [line for line in backlog.splitlines() if "item_id=role-sandbox-commit —" in line]
        self.assertEqual(len(rows), 1)
        prefix, why = rows[0].split(" — why: ", 1)
        self.assertEqual(prefix, "- P2 [ ] Commit from the role sandbox — cluster=workflow — tags=sandbox,git,roles,post-release — to=architect — status=open — plan=null — item_id=role-sandbox-commit — source_ref=docs/release_backlog.md#f12 — disposition_kind=null — disposition_ref=null — disposition_commit_oid=null — reason=null")
        for marker in ("human_explicit", "native_existing", "preview", "preflight", "rollback",
                       "git_writable=false", "docs no_op", "F12", "F13/rebinding"):
            self.assertIn(marker, why)
        # The real derived consumer ignores explanation-only changes. Preserve
        # all typed/summary rendering inputs and compare its generated bytes.
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            carrier = project / "docs/followups/release_backlog.md"
            carrier.parent.mkdir(parents=True)
            carrier.write_text(backlog, encoding="utf-8")
            before = followups_index_rebuild.collect_rows(project)
            before_render = followups_index_rebuild.render_summary(before, stamp="fixture")
            carrier.write_text(backlog.replace(rows[0], prefix + " — why: Alternate factual explanation."), encoding="utf-8")
            after = followups_index_rebuild.collect_rows(project)
            self.assertEqual(before, after)
            self.assertEqual(before_render, followups_index_rebuild.render_summary(after, stamp="fixture"))
        self.assertIn("human_explicit", (ROOT / "docs/guides/launch-and-role-modes.md").read_text())

    def _assert_ordinary_owner_task(self, text: str, carrier: str) -> None:
        guidance = " ".join(text.replace("`", "").split()).lower()
        for marker in (
            "прямое поручение owner",
            "ordinary",
            "bounded discovery",
            "source_ref#item_id",
            "status=open",
            "plan=null",
            "disposition_kind=null",
            "disposition_ref=null",
            "disposition_commit_oid=null",
            "unchanged",
            "automatic backlink запрещён",
            "если совпадений нет",
            "активного плана",
            "architect/owner triage",
            "prepare/finalize/backlink не являются его предусловиями",
            "promotion writer",
            "exact proof",
        ):
            self.assertIn(marker, guidance, carrier)
        self.assertRegex(guidance, r"без искусственной row|не создавай искусственную row", carrier)
        for obsolete in (
            "не создавайте новый plan",
            "вместо второго плана",
            "штатное продвижение, а не второй план",
            "--prepare-v2",
            "--finalize-v2",
        ):
            self.assertNotIn(obsolete, guidance, carrier)

    def _assert_ordinary_owner_task_en(self, text: str, carrier: str) -> None:
        guidance = " ".join(text.replace("`", "").split()).lower()
        for marker in (
            "direct owner assignment",
            "ordinary",
            "bounded discovery",
            "source_ref#item_id",
            "status=open",
            "plan=null",
            "disposition_kind=null",
            "disposition_ref=null",
            "disposition_commit_oid=null",
            "unchanged",
            "automatic backlink is forbidden",
            "if there is no match",
            "already active plan",
            "architect/owner triage",
            "prepare/finalize/backlink are not its preconditions",
            "promotion writer",
            "exact proof",
        ):
            self.assertIn(marker, guidance, carrier)
        self.assertRegex(guidance, r"without an artificial row|do not create an artificial row", carrier)
        for obsolete in (
            "do not create a new plan",
            "instead of a second plan",
            "standard promotion, not a second plan",
            "--prepare-v2",
            "--finalize-v2",
        ):
            self.assertNotIn(obsolete, guidance, carrier)

    def test_stack_brief_adaptation_requires_purpose_and_readiness_only(self) -> None:
        for base in (ROOT, TEMPLATE_ROOT):
            with self.subTest(base=base):
                content = (base / "docs/_template_stack_brief.md").read_bytes()
                section_one = content.split(b"## 1.", 1)[1].split(b"## 2.", 1)[0].decode("utf-8")
                self.assertIn("Назначение и готовность стека", section_one)
                self.assertIn("отдельным прямым поручением Owner", section_one)
                self.assertIn("zero findings допустимы", section_one)
                self.assertNotRegex(section_one, r"первая полезная задача|первая бизнес|Northwind|tSQLt")
                remainder = content[content.index(b"## 2."):]
                self.assertEqual(STACK_BRIEF_REMAINDER_SHA256, hashlib.sha256(remainder).hexdigest())

    def test_ordinary_owner_task_preserves_matching_rows_and_handles_no_match_or_conflict(self) -> None:
        sources = (
            "skills/planveyor-plan-draft/SKILL.md",
            "docs/tools/prompts/architect_draft_discussion.md",
            "docs/tools/prompts/architect_status_driven.md",
            "docs/tools/prompts/planner_status_driven.md",
            *(f"docs/tools/prompts/{role}_docs_finalize_followups.md"
              for role in ("architect", "planner", "coder", "reviewer")),
        )
        for relative in sources:
            delivered = relative.replace("skills/", ".agents/skills/", 1) if relative.startswith("skills/") else relative
            for path in (ROOT / relative, TEMPLATE_ROOT / delivered):
                with self.subTest(path=path):
                    self._assert_ordinary_owner_task(path.read_text(encoding="utf-8"), str(path))
        for role in ("architect", "planner", "coder", "reviewer"):
            text = (ROOT / f"docs/tools/prompts/{role}_docs_finalize_followups.md").read_text(encoding="utf-8")
            self.assertIn("zero findings и честный no-op допустимы", text)
            self.assertIn("NO FOLLOWUPS", text)
            self.assertIn("scripts/followups_apply.py", text)
            self.assertIn("byte-immutable", text)

        backlog = (ROOT / "docs/followups/_template_followups_backlog.md").read_text(encoding="utf-8")
        self.assertIn("Ordinary plan не является row promotion", backlog)
        self.assertIn("не разрешает automatic backlink", backlog)
        self.assertIn("без ручной правки backlog", backlog)
        self.assertIn("только штатный promotion writer с exact proof", backlog)
        self.assertIn("`status=open` требует literal `plan=null`", backlog)
        self.assertNotIn("и ставим ссылку на него в этом backlog", backlog)

    def test_done_guidance_respects_existing_native_and_human_writers(self) -> None:
        groups = (
            "docs/plans/README.md",
            "docs/tools/prompts/manager_router.md",
            "docs/tools/prompts/coder_status_driven.md",
            "docs/tools/prompts/planner_status_driven.md",
        )
        for relative in groups:
            for base in (ROOT, TEMPLATE_ROOT):
                with self.subTest(path=base / relative):
                    text = (base / relative).read_text(encoding="utf-8")
                    for marker in ("native_existing", "human_explicit", "sibling close --commit", "accepted", "preview"):
                        self.assertIn(marker, text)
                    self.assertNotIn("Done = только Architect", text)
                    self.assertNotIn("только Architect ставит `Done`", text)
                    if relative.endswith(("coder_status_driven.md", "planner_status_driven.md")):
                        self.assertIn("`**Status:** Done` ты никогда не ставишь", text)
                        prohibition = next(line for line in text.splitlines() if "`**Status:** Done` ты никогда не ставишь" in line)
                        self.assertIn("не получает Done writer", prohibition)
        closeout = (ROOT / groups[0]).read_text(encoding="utf-8").split("## Post-review exact-bundle closeout", 1)[1]
        self.assertIn("не stage-ит, не записывает provisional `Done` и не коммитит", closeout)
        self.assertIn("ниже относятся только к `native_existing`", closeout)
        self.assertIn("failed terminal transition cleanup", closeout)
        self.assertIn("отдельный post-commit `Done`/второй commit запрещён", closeout)
        manager = (ROOT / groups[1]).read_text(encoding="utf-8")
        self.assertIn("current oracle и accepted review/closeout proof", manager)
        self.assertIn("raw Done сам по себе не доказывает authorized human close", manager)

    def test_owner_task_notice_is_exact_documentation_contract(self) -> None:
        relative = "scripts/test_data/owner_task_after_adaptation_notice.v1.json"
        notice = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        self.assertEqual(
            {"summary", "contract_changes", "engine_changes", "sibling_actions", "checks"},
            set(notice),
            "schema-valid notice must also remove every path-tracking stub key",
        )
        self.assertEqual(notice, consumer_contract.validate_notice(notice, relative))
        self.assertEqual([], notice["engine_changes"])
        for field in ("contract_changes", "sibling_actions", "checks"):
            self.assertTrue(notice[field], field)
        self.assertIn("source_ref#item_id", " ".join(notice["contract_changes"]))
        self.assertIn("human_explicit", " ".join(notice["contract_changes"]))

    @staticmethod
    def _copier_environment() -> dict[str, str]:
        environment = os.environ.copy()
        trusted_python = Path(environment.get("PYBIN", sys.executable)).resolve()
        environment["PYBIN"] = os.fspath(trusted_python)
        environment["PATH"] = os.fspath(trusted_python.parent) + os.pathsep + environment.get("PATH", "")
        return environment

    def _working_source_snapshot(self, parent: Path, environment: dict[str, str]) -> Path:
        source = parent / "source"
        clone = subprocess.run(
            ("git", "clone", "--quiet", os.fspath(ROOT), os.fspath(source)),
            cwd=parent,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(0, clone.returncode, clone.stderr or clone.stdout)
        current_diff = subprocess.run(
            ("git", "diff", "--binary", "HEAD"),
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(0, current_diff.returncode, current_diff.stderr or current_diff.stdout)
        if current_diff.stdout:
            applied = subprocess.run(
                ("git", "apply", "--whitespace=nowarn", "-"),
                cwd=source,
                env=environment,
                input=current_diff.stdout,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            self.assertEqual(0, applied.returncode, applied.stderr or applied.stdout)
            staged = subprocess.run(
                ("git", "add", "--all"),
                cwd=source,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            self.assertEqual(0, staged.returncode, staged.stderr or staged.stdout)
            committed = subprocess.run(
                (
                    "git",
                    "-c",
                    "user.name=Planveyor Sibling Docs Test",
                    "-c",
                    "user.email=planveyor-sibling-docs@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "Render current sibling docs fixture",
                ),
                cwd=source,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            self.assertEqual(0, committed.returncode, committed.stderr or committed.stdout)
        return source

    def _render_fresh_sibling(self, parent: Path) -> Path:
        environment = self._copier_environment()
        copier = shutil.which("copier", path=environment["PATH"])
        self.assertIsNotNone(copier, "trusted environment must provide Copier")
        source = self._working_source_snapshot(parent, environment)
        sibling = parent / "fresh-sibling"
        result = subprocess.run(
            (
                str(copier),
                "copy",
                "--trust",
                "--defaults",
                "--data",
                "repository_id=fresh-sibling",
                os.fspath(source),
                os.fspath(sibling),
            ),
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return sibling

    def test_template_copies_match_their_docs_sources_byte_for_byte(self) -> None:
        copies: dict[str, Path] = {}
        for path in sorted(TEMPLATE_ROOT.rglob("*")):
            if not path.is_file() or path.name.endswith(".jinja") or path.name in COPIER_EXCLUDED_NAMES:
                continue
            relative = path.relative_to(TEMPLATE_ROOT).as_posix()
            if relative in TEMPLATE_RENDERED_ONLY:
                continue
            copies[relative] = path
        self.assertTrue(copies, "copier_template must deliver plain copies of docs/")

        mismatched = []
        for relative, copy in copies.items():
            source = ROOT / _engine_source(relative)
            self.assertTrue(source.is_file(), f"{relative}: template copy has no engine source")
            if copy.read_bytes() != source.read_bytes():
                mismatched.append(relative)
        self.assertEqual(
            [],
            mismatched,
            "copier_template copies must equal their engine source byte for byte; edit both places together",
        )

        copied_directories = {Path(relative).parent.as_posix() for relative in copies}
        self.assertEqual(
            copied_directories,
            {*MIRRORED_TEMPLATE_DIRECTORIES, *PARTIAL_TEMPLATE_DIRECTORIES},
            "classify every copied directory as mirrored or partial",
        )
        for directory in (*MIRRORED_TEMPLATE_DIRECTORIES, *PARTIAL_TEMPLATE_DIRECTORIES):
            template_names = {
                name
                for name in _tracked_names(f"copier_template/{directory}")
                if not name.endswith(".jinja") and name not in COPIER_EXCLUDED_NAMES
            }
            source_names = _tracked_names(_engine_source(directory)) - COPIER_EXCLUDED_NAMES
            if directory in MIRRORED_TEMPLATE_DIRECTORIES:
                self.assertEqual(
                    source_names,
                    template_names,
                    f"{directory}: docs/ and copier_template/ must hold the same tracked file set",
                )
            else:
                missing = sorted(name for name in source_names - template_names if name.startswith("_template"))
                self.assertEqual(
                    [],
                    missing,
                    f"{directory}: deliver every engine _template* file to copier_template/",
                )

    def test_gitignore_hides_local_state_and_keeps_contract_files_visible(self) -> None:
        ignored = (
            ".env.local",
            ".planveyor.planpath",
            ".planveyor.init_runs/by_sid/receipt.json",
            ".tmp/runtime-output.txt",
            "build/output.txt",
            "dist/package.txt",
            "__pycache__/module.pyc",
            ".pytest_cache/state",
            "node_modules/package/index.js",
            ".DS_Store",
            "docs/.DS_Store",
        )
        visible = (
            ".copier-answers.yml",
            "docs/_meta/planveyor_contract_authority.v1.json",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_text(
                (TEMPLATE_ROOT / ".gitignore").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            for relative in (*ignored, *visible):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n", encoding="utf-8")
            for relative in ignored:
                result = subprocess.run(
                    ("git", "check-ignore", "-q", "--", relative),
                    cwd=root,
                    check=False,
                )
                self.assertEqual(0, result.returncode, relative)
            for relative in visible:
                result = subprocess.run(
                    ("git", "check-ignore", "-q", "--", relative),
                    cwd=root,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode, relative)

    def test_ready_files_hold_local_context_and_common_rules_stay_outside(self) -> None:
        for phase, relative in READY_FILES.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            common_index = text.index(COMMON_LOCAL_GUIDE)
            first_local_index = text.index(LOCAL_HEADINGS[0])
            final_local_index = text.index(LOCAL_HEADINGS[1])
            final_local_end = next(
                (index for index in range(final_local_index + 1, len(text)) if text.startswith("## ", index)),
                len(text),
            )
            self.assertLess(common_index, first_local_index, phase)
            self.assertEqual(1, text.count(LOCAL_HEADINGS[0]), phase)
            self.assertEqual(1, text.count(LOCAL_HEADINGS[1]), phase)
            self.assertIn("N/A (why=", text, phase)
            self.assertEqual(len(text), final_local_end, phase)

        architect = (ROOT / READY_FILES["Architect / development"]).read_text(encoding="utf-8")
        planner = (ROOT / READY_FILES["Planner / development"]).read_text(encoding="utf-8")
        coder = (ROOT / READY_FILES["Coder / development"]).read_text(encoding="utf-8")
        self.assertIn("Ограничения, термины и условия применимости", architect)
        self.assertIn(
            "При фактической безусловной приёмке первая строка должна быть ровно "
            "`Вердикт: принято.`, а обоснование пиши со следующих строк; при blockers "
            "или условной приёмке положительную "
            "формулу не используй. Не выдавай положительное решение автоматически.",
            architect[:architect.index(LOCAL_HEADINGS[0])],
        )
        self.assertIn("Команды, данные и preconditions", planner)
        self.assertIn("Подготовка, build/test/smoke commands", coder)

    def test_launch_guide_has_normal_human_sibling_recipe_and_matrix(self) -> None:
        text = LAUNCH_GUIDE.read_text(encoding="utf-8")
        self._assert_ordinary_owner_task(text, "template README")
        self.assertIn("zero findings допустимы", text)
        for command in ("plan", "architect", "answer", "run", "close", "ready"):
            self.assertIn(f"planveyor sibling {command}", text)
        for marker in (
            "Copier 9.18.2",
            "Python 3.12",
            "planveyor sibling close --commit",
            "sibling upgrade --accept-candidate",
            "Architect initial draft",
            "updated_pending_adaptation",
            "physical Planveyor root",
            "planveyor --project \"$PWD\" planveyor_help",
            '"$PLANVEYOR_RUNTIME_ROOT/docs/guides/stack-sibling.md"',
            "custom pipeline",
            "права 0600",
            "каталоги местами",
            "backup",
            "Команды / критерии в локальных секциях",
            "| Доставка |",
        ):
            self.assertIn(marker, text)
        for obsolete_step in (
            "export SOURCE_COMMIT",
            "config user.useConfigOnly true",
            "Planveyor Initializer <planveyor-init@example.invalid>",
            "planveyor_manager_custom_pipeline_cmd run",
        ):
            self.assertNotIn(obsolete_step, text)
        for phase, relative in READY_FILES.items():
            self.assertIn(phase, text)
            self.assertIn(f"`{relative}`", text)

    def test_public_human_runbook_keeps_explicit_commits_and_both_exchange_scenarios(self) -> None:
        guide = ROOT / "docs/guides/stack-sibling.md"
        texts = {
            "en": guide.read_text(encoding="utf-8"),
            "ru": guide.with_name("stack-sibling.ru.md").read_text(encoding="utf-8"),
        }
        self._assert_ordinary_owner_task(texts["ru"], "public runbook, Russian copy")
        self.assertIn("zero findings допустимы", texts["ru"])
        self.assertIn("Теоретическая readiness не доказывает живой проход", texts["ru"])
        self.assertIn("trace всех вызовов, inputs, stdout/stderr, exit codes", texts["ru"])
        self._assert_ordinary_owner_task_en(texts["en"], "public runbook")
        self.assertIn("zero findings are allowed", texts["en"])
        self.assertIn("Theoretical readiness does not prove a live pass", texts["en"])
        self.assertIn("trace of all calls, inputs, stdout/stderr, exit codes", texts["en"])
        for language, text in texts.items():
            with self.subTest(language=language):
                for command in ("init", "plan", "architect", "answer", "run", "close", "ready"):
                    self.assertIn(f"planveyor sibling {command}", text)
                self.assertIn("planveyor --project ~/my-stack sibling upgrade", text)
                self.assertIn("planveyor sibling close --commit", text)
                self.assertIn("planveyor-mssql", text)
                self.assertIn("provenance", text)
                self.assertIn("gh issue create --body-file", text)
                self.assertIn("Source-only ACK", text)
                self.assertIn("../playbooks/analysis_wave.md", text)
                self.assertIn("../playbooks/decomposition_wave.md", text)
                self.assertNotRegex(
                    text,
                    r"(?m)^\s*(?:setopt\b|python(?:3)?\s|git\s[^\n]*(?:commit|rev-parse)|.*git add -A)",
                )
                for operator_detail in ("~/sibling.env", "~/.zshenv", "--source-commit", "hashlib", "status=closed"):
                    self.assertNotIn(operator_detail, text)

    def test_fresh_sibling_delivers_required_paths_and_explicit_engine_references(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor-sibling-docs-") as temporary:
            sibling = self._render_fresh_sibling(Path(temporary))
            self.assertFalse((sibling / "docs/guides").exists())
            for relative in ("docs/README.md", "docs/roles/index.md", *READY_FILES.values()):
                self.assertTrue((sibling / relative).is_file(), relative)

            # Init delivers templates and plan skills only; the stack adaptation plan
            # creates the plan and the brief instance later inside the sibling.
            for relative in (
                "docs/_template_stack_brief.md",
                ".agents/skills/planveyor-plan-draft/SKILL.md",
                ".agents/skills/planveyor-plan-draft/agents/openai.yaml",
                ".agents/skills/planveyor-plan-queue/SKILL.md",
                ".agents/skills/planveyor-plan-queue/agents/openai.yaml",
            ):
                self.assertEqual(
                    (ROOT / _engine_source(relative)).read_bytes(),
                    (sibling / relative).read_bytes(),
                    relative,
                )
            self.assertFalse((sibling / "docs/stack_brief.md").exists())
            self.assertEqual(
                ["README.md", "_template.md"],
                sorted(path.name for path in (sibling / "docs/plans").iterdir()),
            )

            launch_guide = (sibling / "docs/README.md").read_text(encoding="utf-8")
            self._assert_ordinary_owner_task(launch_guide, "rendered fresh sibling README")
            self.assertIn('planveyor --project "$PWD" planveyor_help', launch_guide)
            self.assertIn("planveyor sibling architect", launch_guide)
            self.assertIn("planveyor sibling close --commit", launch_guide)
            self.assertIn('"$PLANVEYOR_RUNTIME_ROOT/docs/guides/stack-sibling.md"', launch_guide)
            self.assertIn("| Доставка |", launch_guide)

            role_index = (sibling / "docs/roles/index.md").read_text(encoding="utf-8")
            self.assertIn("`docs/README.md`", role_index)
            self.assertIn(ENGINE_LIFECYCLE_PATH, role_index)
            self.assertIn(ENGINE_GOLDEN_PATH, role_index)
            self.assertNotIn("`docs/guides/launch-and-role-modes.md`", role_index)
            self.assertNotIn("`docs/guides/lifecycle-and-packets.md`", role_index)

            self.assertTrue((ROOT / "docs/guides/golden_paths.md").is_file())
            for relative in ENGINE_GOLDEN_REFERENCE_FILES:
                text = (sibling / relative).read_text(encoding="utf-8")
                self.assertIn(ENGINE_GOLDEN_PATH_PREFIX, text, relative)
                self.assertNotRegex(
                    text,
                    r"(?<!\$PLANVEYOR_RUNTIME_ROOT/)docs/guides/golden_paths\.md",
                    relative,
                )

    def test_local_section_tails_stay_byte_stable_for_sibling_upgrade(self) -> None:
        self.assertEqual(set(READY_FILES.values()), set(LOCAL_SECTION_TAIL_SHA256))
        heading = LOCAL_HEADINGS[0].encode("utf-8")
        for relative, expected in LOCAL_SECTION_TAIL_SHA256.items():
            for path in (ROOT / relative, TEMPLATE_ROOT / relative):
                lines = path.read_bytes().splitlines(keepends=True)
                starts = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == heading]
                self.assertEqual(1, len(starts), f"{path}: exactly one {LOCAL_HEADINGS[0]!r} heading")
                actual = hashlib.sha256(b"".join(lines[starts[0]:])).hexdigest()
                self.assertEqual(
                    expected,
                    actual,
                    f"{path}: bytes from {LOCAL_HEADINGS[0]!r} to end of file changed. "
                    "This breaks planveyor_contract_upgrade for EVERY sibling, including untouched ones: "
                    "upgrade requires local sections to stay byte-identical before and after Copier. "
                    "Revert the change, or make it deliberately with a contract notice and explicit "
                    "sibling adaptation, then update LOCAL_SECTION_TAIL_SHA256.",
                )

    def test_phase_prompts_apply_local_sections_of_their_playbooks(self) -> None:
        for prompt, playbooks in PHASE_PLAYBOOK_POINTERS.items():
            text = (ROOT / prompt).read_text(encoding="utf-8")
            local_start = text.find("\n" + LOCAL_HEADINGS[0] + "\n")
            common = text if local_start < 0 else text[:local_start]
            for playbook in playbooks:
                self.assertIn(playbook, READY_FILES.values(), playbook)
                self.assertTrue(
                    f"`{playbook}`" in common,
                    f"{prompt} must point at the sibling copy of {playbook} outside local sections",
                )
            for heading in LOCAL_HEADINGS:
                section = heading.removeprefix("## ")
                self.assertTrue(
                    f"`{section}`" in common,
                    f"{prompt} must tell the role to apply the playbook section {section!r}",
                )

    def test_planner_common_rules_precede_its_trailing_local_body(self) -> None:
        text = (ROOT / READY_FILES["Planner / development"]).read_text(encoding="utf-8")
        first_local_index = text.index(LOCAL_HEADINGS[0])
        final_local_index = text.index(LOCAL_HEADINGS[1])
        final_local_end = next(
            (index for index in range(final_local_index + 1, len(text)) if text.startswith("## ", index)),
            len(text),
        )
        self.assertEqual(len(text), final_local_end)
        for marker in (
            COMMON_LOCAL_GUIDE,
            "Для любого Golden Path-dependent handoff",
            "planveyor_plan_bundle --preflight",
        ):
            self.assertLess(text.index(marker), first_local_index, marker)
            self.assertNotIn(marker, text[first_local_index:], marker)

    @staticmethod
    def _delivered_markdown() -> list[tuple[str, str]]:
        documents = []
        for path in sorted(TEMPLATE_ROOT.rglob("*")):
            if not path.is_file() or path.name in COPIER_EXCLUDED_NAMES:
                continue
            relative = path.relative_to(TEMPLATE_ROOT).as_posix()
            if relative.endswith(".md.jinja"):
                relative = relative.removesuffix(".jinja")
            elif not relative.endswith(".md"):
                continue
            documents.append((relative, path.read_text(encoding="utf-8")))
        return documents

    def test_delivered_docs_call_the_engine_only_through_the_facade(self) -> None:
        offenders = []
        for relative, text in self._delivered_markdown():
            section: list[str] = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if line.startswith("#"):
                    section = []
                section.append(line)
                match = ENGINE_CALL_RE.search(line)
                if match is None:
                    continue
                scope = "\n".join(section)
                if any(marker in scope for marker in SELF_PLANVEYOR_MARKERS):
                    continue
                offenders.append(f"{relative}:{line_no}: {match.group(0)}")
        if offenders:
            self.fail(
                "delivered docs must call the engine as "
                '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <command>, '
                "or mark the section as Self-Planveyor:\n" + "\n".join(offenders)
            )

    def test_delivered_code_blocks_do_not_start_with_bare_engine_functions(self) -> None:
        offenders = []
        for relative, text in self._delivered_markdown():
            section: list[str] = []
            fence = ""
            continued = False
            for line_no, line in enumerate(text.splitlines(), start=1):
                if line.startswith("#"):
                    section = []
                section.append(line)
                fence_match = CODE_FENCE_RE.match(line)
                if fence_match is not None:
                    fence_token, info = fence_match.groups()
                    if not fence:
                        fence, continued = fence_token, False
                        continue
                    if fence_token[0] == fence[0] and len(fence_token) >= len(fence) and not info.strip():
                        fence = ""
                        continue
                if not fence:
                    continue
                # A line after a trailing backslash continues the facade call above it.
                starts_command = not continued
                continued = line.rstrip().endswith("\\")
                match = BARE_ENGINE_FUNCTION_RE.match(line) if starts_command else None
                if match is None:
                    continue
                if any(marker in "\n".join(section) for marker in SELF_PLANVEYOR_MARKERS):
                    continue
                offenders.append(f"{relative}:{line_no}: {match.group(1)}")
        if offenders:
            self.fail(
                "delivered code blocks must run engine functions as "
                '"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <command>: the facade '
                "defines nothing in the caller's shell. Otherwise mark the section as Self-Planveyor:\n"
                + "\n".join(offenders)
            )

    @staticmethod
    def _delivered_paths() -> set[str]:
        paths = {".copier-answers.yml"}
        for path in TEMPLATE_ROOT.rglob("*"):
            if path.is_file() and path.name not in COPIER_EXCLUDED_NAMES:
                paths.add(path.relative_to(TEMPLATE_ROOT).as_posix().removesuffix(".jinja"))
        return paths

    @staticmethod
    def _doc_reference_available(mention: str, delivered: set[str]) -> bool:
        files = delivered | SIBLING_OWNED_DOC_PATHS
        directories = {
            parent.as_posix()
            for path in files
            for parent in Path(path).parents
            if parent.as_posix() != "."
        } | SIBLING_DOC_NAMESPACE_CONTRACTS.keys()
        if mention.endswith("/"):
            directory = mention.rstrip("/")
            if any(token in directory for token in "*?["):
                return any(fnmatch.fnmatchcase(path, directory) for path in directories)
            return directory in directories
        if mention in files or mention in directories:
            return True
        # Generated names/patterns must have a supported literal prefix. Existing
        # directories permit names under them; absent prefixes do not become canon.
        dynamic = [mention.find(token) for token in (*DOC_PATH_PLACEHOLDER_TOKENS, "*", "?", "[", ".*") if token in mention]
        if not dynamic:
            return False
        prefix = mention[:min(dynamic)]
        if prefix.endswith("/"):
            return prefix.rstrip("/") in directories
        return bool(prefix) and any(path.startswith(prefix) for path in files | directories)

    def test_supported_target_namespaces_have_existing_contract_carriers(self) -> None:
        for namespace, (carrier, declaration) in SIBLING_DOC_NAMESPACE_CONTRACTS.items():
            with self.subTest(namespace=namespace):
                self.assertIn(declaration, (TEMPLATE_ROOT / carrier).read_text(encoding="utf-8"))

    def test_delivery_guard_rejects_absent_directory_glob_and_extensionless_paths(self) -> None:
        references = (
            "docs/arch/", "docs/arch/*", "docs/arch/YYMMDD_HHMM_decision.md",
            "docs/continuity/", "docs/continuity/*", "docs/todo_stage_*",
            "docs/todo_stage_1", "docs/unknown/extensionless", "docs/api.md/",
            "docs/arch.md/", "docs/analysis_packs/undeclared_file.md",
        )
        for reference in references:
            with self.subTest(reference=reference):
                if reference not in ("docs/api.md/", "docs/arch.md/"):
                    self.assertFalse((TEMPLATE_ROOT / reference.rstrip("/*")).exists())
                with mock.patch.object(self, "_delivered_markdown", return_value=[("docs/roles/architect.md", f"See {reference}")]):
                    with self.assertRaises(AssertionError) as rejected:
                        self.test_delivered_docs_reference_only_delivered_or_explicit_engine_paths()
                    self.assertIn(reference.rstrip("/"), str(rejected.exception))

    def test_delivery_guard_keeps_delivered_patterns_optional_canon_and_engine_paths(self) -> None:
        text = "\n".join((
            "`docs/adr/` `docs/adr/*` `docs/plans/YYMMDD_HHMM_plan.md`",
            "`docs/api.md` `docs/arch.md` `docs/schema.md`",
            '"$PLANVEYOR_RUNTIME_ROOT/docs/guides/planning_contour_continuity.md"',
            "[ADR](../adr/)",
            "docs/analysis_packs/ docs/code_reviews/assets/* docs/contract_notices/",
        ))
        with mock.patch.object(self, "_delivered_markdown", return_value=[("docs/roles/architect.md", text)]):
            self.test_delivered_docs_reference_only_delivered_or_explicit_engine_paths()
        self.assertTrue(self._doc_reference_available("docs/extensionless", {"docs/extensionless"}))

    def test_delivered_docs_reference_only_delivered_or_explicit_engine_paths(self) -> None:
        delivered = self._delivered_paths()
        delivered_directories = {parent.as_posix() for path in delivered for parent in Path(path).parents}
        offenders = []
        for relative, text in self._delivered_markdown():
            section: list[str] = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if line.startswith("#"):
                    section = []
                section.append(line)
                if any(marker in "\n".join(section) for marker in SELF_PLANVEYOR_MARKERS):
                    continue
                for match in MARKDOWN_LINK_RE.finditer(line):
                    target = match.group(1).split("#", 1)[0]
                    if not target or target.startswith(("$", "/", "<")) or ":" in target:
                        continue
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
                    if resolved not in delivered and resolved not in delivered_directories:
                        offenders.append(f"{relative}:{line_no}: link {target}")
                for match in DOC_PATH_MENTION_RE.finditer(line):
                    mention = match.group(0)
                    if self._doc_reference_available(mention, delivered):
                        continue
                    offenders.append(f"{relative}:{line_no}: {mention}")
        if offenders:
            self.fail(
                "delivered docs must reference files present in the sibling; point at engine files as "
                '"$PLANVEYOR_RUNTIME_ROOT/<path>", describe them in text, or drop historical references:\n'
                + "\n".join(offenders)
            )

    def test_delivered_docs_do_not_offer_root_defaulting_helpers_directly(self) -> None:
        # Run directly from a sibling, these helpers default --root to the engine
        # checkout and read the engine's session files; the facade routes bind
        # the project root instead.
        offenders = []
        for relative, text in self._delivered_markdown():
            section: list[str] = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if line.startswith("#"):
                    section = []
                section.append(line)
                if not any(helper in line for helper in ROOT_DEFAULTING_ENGINE_HELPERS):
                    continue
                if any(marker in "\n".join(section) for marker in SELF_PLANVEYOR_MARKERS):
                    continue
                offenders.append(f"{relative}:{line_no}")
        if offenders:
            self.fail(
                "delivered docs must use planveyor_plan_provenance_stamp/context through the facade, "
                "or mark the section as Self-Planveyor:\n" + "\n".join(offenders)
            )

    def test_delivered_files_carry_no_private_fingerprints(self) -> None:
        offenders = _delivered_fingerprint_offenders(ROOT, TEMPLATE_ROOT)
        if offenders:
            self.fail("delivered files must use neutral wording:\n" + "\n".join(offenders))

    def _fingerprint_fixture(self) -> tuple[Path, Path, dict[str, str]]:
        temporary = tempfile.TemporaryDirectory(prefix="delivered_fingerprint_")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "project"
        template = root / "copier_template"
        template.mkdir(parents=True)
        env = dict(os.environ)
        env.pop(scan_mod.MARKER_ENV, None)
        return root, template, env

    def test_public_model_fingerprint_policy_and_exceptions_without_dictionary(self) -> None:
        root, template, env = self._fingerprint_fixture()
        (template / "positive.txt").write_text("GLM\nGrok\nSol\nAstra\nGPT-6.1X Sol\ngpt-6.1 Sol\n", encoding="utf-8")
        (template / "negative.txt").write_text("GPT-6.1 Sol\nMinIO\nxGLMy Grokish Solace Astral\nglm grok sol astra\n", encoding="utf-8")
        (template / ".DS_Store").write_text("GLM\n", encoding="utf-8")
        with mock.patch.dict(os.environ, env, clear=True):
            offenders = _delivered_fingerprint_offenders(root, template)
        self.assertEqual(offenders, [f"positive.txt:{line}: {term}" for line, term in enumerate(("GLM", "Grok", "Sol", "Astra", "Sol", "Sol"), 1)])

    def test_private_fingerprint_common_matcher_uses_synthetic_external_dictionary(self) -> None:
        root, template, env = self._fingerprint_fixture()
        marker = root.parent / "synthetic-markers.txt"
        env[scan_mod.MARKER_ENV] = str(marker)
        (template / "positive.txt").write_text('safe\nａｃｍｅ_private\n("acme_" +\n "private")\ndef example():\n    return ("acme_") + "private"\nawait ("acme_" + "private")\n', encoding="utf-8")
        (template / "negative.txt").write_text("acmeXprivate\nacme\u200e_private\nreturn make('acme_') + 'private'\nawait ('acme_') + 'private'\nawait 'acme_' + 'private'\n", encoding="utf-8")
        for dictionary in ("acme_private\n", "re:(?=acme_private)\n"):
            marker.write_text(dictionary, encoding="utf-8")
            with self.subTest(dictionary=dictionary), mock.patch.dict(os.environ, env, clear=True), mock.patch.object(scan_mod, "marker_findings", wraps=scan_mod.marker_findings) as common:
                offenders = _delivered_fingerprint_offenders(root, template)
            self.assertEqual(common.call_count, 2)
            self.assertTrue(all(call.args[3] and call.args[3][0].category == "private_marker" for call in common.call_args_list))
            self.assertEqual(offenders, [f"positive.txt:{line}: private_marker: <masked>" for line in (2, 3, 6, 7)])
            self.assertNotIn("acme", "\n".join(offenders))

    def test_private_fingerprint_dictionary_unset_and_invalid_input(self) -> None:
        root, template, env = self._fingerprint_fixture()
        (template / "sample.txt").write_text("GLM\nacme_private\n", encoding="utf-8")
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(scan_mod, "marker_findings", wraps=scan_mod.marker_findings) as common:
            self.assertEqual(_delivered_fingerprint_offenders(root, template), ["sample.txt:1: GLM"])
        self.assertEqual(common.call_count, 1)
        self.assertEqual(common.call_args.args[3], ())
        external = root.parent / "synthetic-markers.txt"
        external.write_text("acme_private\n", encoding="utf-8")
        inside = root / "inside-markers.txt"
        inside.write_text("acme_private\n", encoding="utf-8")
        link = root.parent / "marker-link.txt"
        link.symlink_to(external)
        for marker in (root.parent / "missing.txt", inside, link):
            with self.subTest(marker=marker), mock.patch.dict(os.environ, {**env, scan_mod.MARKER_ENV: str(marker)}, clear=True):
                with self.assertRaisesRegex(scan_mod.ScanInputError, "^scanner input is invalid$"):
                    _delivered_fingerprint_offenders(root, template)

    def test_transmitted_instructions_use_external_facade_and_delivered_guide(self) -> None:
        for relative, text in self._delivered_markdown():
            self.assertNotIn("docs/tools/owner_runbook_codex.md", text, relative)

        required_facade_files = (
            "docs/roles/planner.md",
            "docs/tools/prompts/planner_status_driven.md",
            "docs/plans/_template.md",
            "docs/plans/README.md",
            "docs/playbooks/post_merge_plan_harvest.md",
            "docs/tools/prompts/architect_post_merge_audit.md",
            "docs/playbooks/doc_lint.md",
            "docs/tools/prompts/manager_collab_merge_pipeline.md",
            "docs/tools/prompts/manager_collab_pipeline.md",
            "docs/tools/prompts/manager_custom_pipeline.md",
            "docs/tools/prompts/planveyor_decomposition.md",
        )
        for relative in required_facade_files:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project', text, relative)

        doc_lint = (ROOT / "docs/playbooks/doc_lint.md").read_text(encoding="utf-8")
        self.assertIn("### Self-Planveyor", doc_lint)
        self.assertIn("Обычный gate: `make doc-lint`", doc_lint)
        self.assertIn("### Sibling", doc_lint)

        decomposition = (ROOT / "docs/tools/prompts/planveyor_decomposition.md").read_text(encoding="utf-8")
        self.assertIn("Public entrypoint: ./bin/planveyor из physical Planveyor root.", decomposition)
        self.assertIn("Public entrypoint: `\"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor\" --project \"$PWD\"`.", decomposition)

        merge_pipeline = (ROOT / "docs/tools/prompts/manager_collab_merge_pipeline.md").read_text(encoding="utf-8")
        self.assertIn("- `make doc-lint` — только в physical self-Planveyor root.", merge_pipeline)
        self.assertIn('sibling запускает `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.', merge_pipeline)

        self_only_commands = (
            "docs/playbooks/docs_canon_sweep.md",
            "docs/playbooks/post_merge_audit.md",
            "docs/playbooks/post_merge_plan_harvest.md",
            "docs/tools/prompts/manager_collab_pipeline.md",
        )
        for relative in self_only_commands:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("Self-Planveyor", text, relative)
            self.assertIn('"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project', text, relative)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import re
import unittest

from test_planveyor_profile_extraction import PUBLIC_ROOT_CONTENT


ROOT = Path(__file__).resolve().parent.parent

class SharedCorpusContractTests(unittest.TestCase):
    def test_generic_reviews_preserve_supplied_spec_and_diff_transport(self) -> None:
        for name in ("review_staged_or_commit.md", "review_docs_staged_or_commit.md"):
            with self.subTest(playbook=name):
                text = (ROOT / "docs/playbooks" / name).read_text(encoding="utf-8")
                for marker in ("<<SPEC_TEXT>>", "<<END_SPEC_TEXT>>", "<<DIFF>>", "<<END_DIFF>>"):
                    self.assertEqual(text.count(marker), 1, f"{name}: {marker}")
                self.assertLess(text.index("<<SPEC_TEXT>>"), text.index("<<END_SPEC_TEXT>>"))
                self.assertLess(text.index("<<DIFF>>"), text.index("<<END_DIFF>>"))

    def test_generic_visual_review_keeps_materialized_proof_requirements(self) -> None:
        text = (ROOT / "docs/playbooks/post_merge_visual_review.md").read_text(encoding="utf-8")
        for field in (
            "Runtime UI visual evidence state", "Comparator command", "Comparator claim: mechanical",
            "Comparator result", "Capture status", "Complete index inspected", "Design verdict",
            "Finding dispositions", "Human index", "Durable asset", "Source scenarios:",
            "Post-merge visual sanity", "Proves:", "scenario -> mode -> asset -> verdict",
        ):
            self.assertIn(field, text)
        for requirement in ("Mechanical comparator", "human visual inspection", "baseline-update",
                            "non-empty regular non-symlink", "docs/code_reviews/assets/<REVIEW_BASENAME>/"):
            self.assertIn(requirement, text)

    def test_shared_role_and_prompt_fallbacks_are_declared_public_content(self) -> None:
        sources = [path for path in PUBLIC_ROOT_CONTENT
                   if path.startswith(("docs/roles/", "docs/tools/prompts/"))]
        self.assertEqual(len(sources), 39)
        self.assertEqual(len(sources), len(set(sources)))
        for relative in sources:
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text(encoding="utf-8").strip())

    def test_shared_playbooks_use_declared_inputs_without_weakening_process_gates(self) -> None:
        # Keep this repair scoped to the three shared playbooks. The Planveyor
        # profile and specialized legacy helpers intentionally retain their
        # product vocabulary; the existing role/prompt sweep is independent.
        contracts = {
            "worktrees_topic_split.md": {
                "forbidden": (
                    r"\btg_msg\b", r"\bDepo\b", r"slots-workplace",
                    r"\.\./planveyor\.worktrees/", r"planveyor_plan_list depo",
                    r"git worktree add[^\n]*\bmain\b",
                    r'planveyor_plan_list_status "architect initial draft" deploy',
                ),
                "required": (
                    "<worktree-dir>", "<branch-name>", "<base-ref>", "<topic>",
                    "EXAMPLE", "source of truth", "pointer", ".planveyor.planpath",
                    "Темы, каталог worktree, ветка, base ref и keywords берутся из выбранного project/plan",
                    "planveyor_plan_list", "planveyor_plan_list_status", "planveyor_plan_set",
                    "docs/followups/*",
                ),
            },
            "role_prompt_invariant_map.md": {
                "forbidden": (r"они\s+идут\s+через\s+Postgres\s+profile",),
                "required": (
                    "runtime tests/smokes", "объявленные выбранными repo/profile/plan",
                    "harness и backend", "contract admission", "required harness",
                    "gap для штатного reroute", "не ложный pass или `N/A`",
                    "bypass required check не доказывает результат без явно принятого contract admission",
                ),
            },
            "followups_topic_consolidation.md": {
                "forbidden": (
                    r"docs/todo_stage_", r"\bSlots\b", r"\bslot_status\b",
                    r"\bCalendar\b", r"\bCAL-1\b", r"\bHDR-1\b",
                    r"reviewer_calendar_merge_range",
                ),
                "required": (
                    "SOURCE_DOC", "Owner/intake/plan явно объявляет существующий",
                    "exact heading title",
                    "link-only", "1:1", "src=", "plain index prose", "source_ref",
                    "Source of truth по деталям = `SOURCE_DOC`",
                    "не копируй source text; не меняй source или backlinks без explicit Owner permission",
                    "does not select or run an extractor/checker", "declared source contract",
                    "grammar только если его объявляет selected source contract; иначе открой "
                    "`SOURCE_DOC` и перечисли exact heading titles вручную",
                    "planveyor_followups_query cleanup-receipt", "decision=delete-ready",
                    "### 4.5) Обнови backlinks", "удаление делает Owner",
                ),
            },
        }
        for name, contract in contracts.items():
            with self.subTest(playbook=name):
                text = (ROOT / "docs/playbooks" / name).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                for pattern in contract["forbidden"]:
                    self.assertIsNone(re.search(pattern, text), f"{name}: legacy default {pattern}")
                for anchor in contract["required"]:
                    self.assertIn(anchor, normalized, f"{name}: lost shared contract {anchor}")


if __name__ == "__main__":
    unittest.main()

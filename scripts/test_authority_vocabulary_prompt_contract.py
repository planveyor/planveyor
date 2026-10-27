"""Focused regression for the authority-vocabulary prompt contract."""

from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AuthorityVocabularyPromptContractTest(unittest.TestCase):
    WRONG_OWNER_CLAIM = "`plan_meta.canon_updates` владеет exact writable bundle"
    FALSE_PROMOTION_CLAIM = "`Owner` prose/candidate materialize-ят accepted route"
    FALSE_ENFORCEMENT_CLAIM = (
        "plan/prompt/test/review/receipt являются runtime enforcement"
    )

    def read_text(self, relative_path: str) -> str:
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def authority_texts(self) -> dict[str, str]:
        return {
            "architecture": self.read_text("docs/playbooks/docs_architecture.md"),
            "analysis": self.read_text("docs/playbooks/analysis_wave.md"),
            "invariant_map": self.read_text(
                "docs/playbooks/role_prompt_invariant_map.md"
            ),
            "architect_draft": self.read_text(
                "docs/tools/prompts/architect_draft_discussion.md"
            ),
            "architect_status": self.read_text(
                "docs/tools/prompts/architect_status_driven.md"
            ),
            "planner": self.read_text("docs/tools/prompts/planner_status_driven.md"),
            "reviewer": self.read_text("docs/tools/prompts/reviewer_status_driven.md"),
        }

    def assert_false_authority_claims_absent(
        self, architect_status: str, reviewer_prompt: str
    ) -> None:
        self.assertNotIn(self.WRONG_OWNER_CLAIM, architect_status)
        self.assertNotIn(self.FALSE_PROMOTION_CLAIM, architect_status)
        self.assertNotIn(self.FALSE_ENFORCEMENT_CLAIM, reviewer_prompt)


    def test_shared_root_authority_anchors_and_role_placement(self) -> None:
        texts = self.authority_texts()
        normalized_texts = {
            file_name: " ".join(text.split()) for file_name, text in texts.items()
        }
        anchors = {
            "architecture": (
                "## Слои",
                "Markdown source",
                "Control-plane metadata",
                "Derived artifact",
                "Runtime bundle",
                "Markdown остаётся source of truth для narrative и ownership.",
                "## Ownership и delivery",
                "У каждого shared carrier есть один source owner.",
                "Source change не копируется вручную в consumer.",
                "Нельзя использовать mirror или stale copy как новый source",
            ),
            "analysis": (
                "### Authority mapping",
                "но не владеет ею и не вводит второй route/status enum",
                "`analysis_pack.route_recommendation` = `analysis candidate`",
                "literal `## Promoted route artifact`",
            ),
            "invariant_map": (
                "Authority boundary: у нормы ровно один `canonical writable owner`",
                "duplicate writable truth, false promotion или owner mismatch",
                "только named enforcement mechanism может fail-close либо менять state",
            ),
            "architect_draft": (
                "0.5) Authority pre-write check",
                "`decision lifecycle` state, `canonical writable owner` и downstream carrier",
                "candidate не materialize-ят accepted route",
            ),
            "architect_status": (
                "Authority pre-scope check",
                "`decision lifecycle` state, `canonical writable owner` и downstream carrier",
                "`Owner` prose/candidate не materialize-ят accepted route",
                "`route_recommendation` не является accepted route truth: accepted route появляется только после `Architect arch review` через promoted route artifact/status/linkage",
            ),
            "planner": (
                "Authority normalization before `Ready for Coder`",
                "executable carriers, enforcement mechanisms, proof carriers и read-only consumers",
                "Только `code_draft_meta.targets` владеет exact writable bundle",
            ),
            "reviewer": (
                "Authority catch rule",
                "duplicate writable truth, false promotion и owner mismatch",
                "plan/prompt/test/review/receipt не являются runtime enforcement",
            ),
        }
        for file_name, expected_anchors in anchors.items():
            with self.subTest(file=file_name):
                for anchor in expected_anchors:
                    self.assertIn(anchor, normalized_texts[file_name])

        self.assertLess(
            texts["architecture"].index("## Слои"),
            texts["architecture"].index("## Ownership и delivery"),
        )
        self.assertLess(
            texts["architect_draft"].index("0.5) Authority pre-write check"),
            texts["architect_draft"].index("1) В plan добавь/обнови вводные:"),
        )
        self.assertLess(
            texts["architect_status"].index("Authority pre-scope check"),
            texts["architect_status"].index("- Если задача является `analysis_wave`"),
        )
        self.assertLess(
            texts["planner"].index("Authority normalization before `Ready for Coder`"),
            texts["planner"].index("- Первый executable handoff перед `Ready for Coder` требует strict `planveyor_plan_bundle --preflight <PLAN_PATH>`"),
        )
        self.assertLess(
            texts["reviewer"].index("Authority catch rule"),
            texts["reviewer"].index("- Dual-lane execution contract"),
        )

        self.assert_false_authority_claims_absent(
            texts["architect_status"], texts["reviewer"]
        )


    def test_wrong_owner_mutant_is_rejected_independently(self) -> None:
        texts = self.authority_texts()
        wrong_owner = f"{texts['architect_status']}\n{self.WRONG_OWNER_CLAIM}.\n"

        with self.assertRaisesRegex(AssertionError, "plan_meta\\.canon_updates"):
            self.assert_false_authority_claims_absent(wrong_owner, texts["reviewer"])

    def test_false_promotion_mutant_is_rejected_independently(self) -> None:
        texts = self.authority_texts()
        false_promotion = texts["architect_status"].replace(
            "`Owner` prose/candidate не materialize-ят accepted route",
            self.FALSE_PROMOTION_CLAIM,
            1,
        )
        self.assertNotEqual(false_promotion, texts["architect_status"])

        with self.assertRaisesRegex(AssertionError, "Owner"):
            self.assert_false_authority_claims_absent(false_promotion, texts["reviewer"])

    def test_false_enforcement_mutant_is_rejected_independently(self) -> None:
        texts = self.authority_texts()
        false_enforcement = texts["reviewer"].replace(
            "plan/prompt/test/review/receipt не являются runtime enforcement",
            self.FALSE_ENFORCEMENT_CLAIM,
            1,
        )
        self.assertNotEqual(false_enforcement, texts["reviewer"])

        with self.assertRaisesRegex(AssertionError, "runtime enforcement"):
            self.assert_false_authority_claims_absent(
                texts["architect_status"], false_enforcement
            )


    def test_machine_authority_writer_reader_and_derived_ref_contract_is_explicit(self) -> None:
        anchors = {
            "docs/plans/_template.md": (
                "Machine-authority admission: до downstream handoff",
                "ровно один `plan_meta.machine_authority_decision`",
                "Prose, Evidence, Q&A, target count и code draft не заменяют decision;",
            ),
            "docs/code_drafts/_template.md": (
                "Machine-authority derived binding",
                "contains only",
                "Planner copies no\n> semantic decision core",
            ),
            "docs/plans/README.md": (
                "## Machine-authority admission",
                "top-level `## Meta` JSON\nfence",
                "code examples, target count и prose не заменяют authority.",
                "Terminal consumers use the\ngeneric oracle `route_guard_*`",
            ),
            "docs/playbooks/docs_architecture.md": (
                "Markdown остаётся source of truth для narrative и ownership.",
                "JSON допустим только\nкогда его читает конкретный deterministic consumer.",
                "Generated index или runtime\nbundle не становится authorable substitute для source.",
            ),
            "docs/playbooks/role_prompt_invariant_map.md": (
                "Machine-authority admission is a narrower instance",
                "Planner owns only the tagged code-draft ref",
                "never parse the\n  semantic core or prose",
            ),
            "docs/roles/architect.md": (
                "Architect до `Ready for Planner`",
                "Evidence/Q&A/review prose не являются fallback",
            ),
            "docs/roles/planner.md": (
                "Planner читает только validated",
                "Не копируй/не исправляй semantic\n    core",
            ),
            "docs/tools/prompts/architect_draft_discussion.md": (
                "Обязательность определяется статусом/назначением, не датой/именем;",
                "не поручай Planner заполнить semantic core",
            ),
            "docs/tools/prompts/architect_status_driven.md": (
                "Дата/имя плана не включают и не отключают проверки",
                "CENSOR/readback не становятся writer",
            ),
            "docs/tools/prompts/planner_status_driven.md": (
                'Machine-authority admission: read `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_status_oracle.py',
                "Planner never writes/parses the\n  semantic core",
            ),
        }
        for relative_path, required in anchors.items():
            with self.subTest(path=relative_path):
                text = self.read_text(relative_path)
                for marker in required:
                    self.assertIn(marker, text)

        for relative_path in (
            "docs/plans/_template.md",
            "docs/tools/prompts/architect_draft_discussion.md",
            "docs/tools/prompts/architect_status_driven.md",
        ):
            with self.subTest(path=relative_path, removed="post-cutover"):
                self.assertNotIn("post-cutover", self.read_text(relative_path))

    def test_bounded_grammar_checkpoint_v2_preserves_writer_reader_split(self) -> None:
        anchors = {
            "docs/code_drafts/_template.md": (
                "bounded_grammar",
                "four-key `admission_baseline`",
                "never a current/subject authority",
            ),
            "docs/plans/README.md": (
                "### Bounded-grammar checkpoint V2",
                "Architect — единственный semantic writer",
                "V2 `stop`",
                "Manager/Planner/CENSOR never write",
            ),
            "docs/plans/_template.md": (
                "semantic_cycle_checkpoint_resolution.v2",
                "не является default template",
                "new family never resets",
            ),
            "docs/playbooks/review_route_and_receipt_canon.md": (
                "bounded_grammar` subject V2",
                "one-per-contour",
                "not V2 carrier",
            ),
            "docs/playbooks/role_prompt_invariant_map.md": (
                "checkpoint V2 semantic writer остаётся",
                "sole selector",
                "silent V1/V2 fallback",
            ),
            "docs/roles/architect.md": (
                "bounded_grammar` subject Architect likewise",
                "V2 `stop` forbidden",
                "exact-backlink non-terminal structured successor",
            ),
            "docs/roles/planner.md": (
                "checkpoint-V2 implementation",
                "four-key immutable `code_draft_meta.admission_baseline`",
                "does not write V2 resolution",
            ),
            "docs/tools/prompts/architect_status_driven.md": (
                "Bounded-grammar V2 is a separate subject-only branch",
                "never V2 `stop`",
                "CENSOR/readback never becomes a",
            ),
            "docs/tools/prompts/planner_status_driven.md": (
                "declared checkpoint-V2 implementation only",
                "fixed commit is an ancestor of captured `HEAD`",
                "does not write V2 Evidence",
            ),
        }
        for relative_path, required in anchors.items():
            with self.subTest(path=relative_path):
                text = self.read_text(relative_path)
                for marker in required:
                    self.assertIn(marker, text)

    def test_current_review_proof_reader_is_canonical_and_consumers_are_derived(self) -> None:
        documents = {
            "reviewer_prompt": "docs/tools/prompts/reviewer_status_driven.md",
            "reviewer_role": "docs/roles/reviewer.md",
            "review_canon": "docs/playbooks/review_route_and_receipt_canon.md",
            "exact_bundle_adr": "docs/adr/004-exact-bundle-truth-and-closeout.md",
        }
        for name, relative_path in documents.items():
            with self.subTest(document=name):
                text = self.read_text(relative_path)
                self.assertIn("preflight_current_review_proof", text)
                self.assertIn("BUNDLE=current bundle_sha256=<64 lowercase hex>", text)
                self.assertIn("review_target_snapshot.v2", text)
                self.assertIn("immutable", text)
                self.assertIn("fresh", text)
                self.assertIn("blocked", text)

        canon_text = self.read_text(documents["review_canon"])
        self.assertIn("Terminal immutable history остаётся read-compatible", canon_text)
        self.assertIn("не запускают второй current-proof parser", canon_text)
        adr_text = self.read_text(documents["exact_bundle_adr"])
        self.assertIn("read-only projectors", adr_text)
        self.assertIn("header-only green", adr_text)


if __name__ == "__main__":
    unittest.main()

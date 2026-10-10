#!/usr/bin/env python3
"""Focused isolated-repository checks for contract_authority_matrix_check.py."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "contract_authority_matrix_check.py"
RULES_PATH = "docs/tools/authority_matrix/rules.json"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", os.fspath(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return completed.stdout.decode("utf-8").strip()


def commit(root: Path, message: str) -> tuple[str, str]:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    current = git(root, "rev-parse", "HEAD")
    return current, git(root, "rev-parse", f"{current}^{{tree}}")


def write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def snapshot(root: Path) -> dict[str, tuple[str, int, str | None]]:
    result: dict[str, tuple[str, int, str | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat_result = path.lstat()
        if path.is_symlink():
            result[relative] = ("symlink", stat_result.st_mode, os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", stat_result.st_mode, hashlib.sha256(path.read_bytes()).hexdigest())
        elif path.is_dir():
            result[relative] = ("dir", stat_result.st_mode, None)
    return result


class ContractAuthorityMatrixCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.target = self.base / "target"
        self.source.mkdir()
        self.target.mkdir()
        for root in (self.source, self.target):
            git(root, "init", "-q")
            git(root, "config", "user.email", 'matrix' + '@' + 'example' + '.' + 'invalid')
            git(root, "config", "user.name", "Matrix Test")
        self._write_source_fixture()
        self._write_target_fixture()
        self.source_commit, self.source_tree = commit(self.source, "source fixture")
        self.target_commit, self.target_tree = commit(self.target, "target fixture")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _rules(self) -> dict[str, Any]:
        target_identity = {
            "consumer_anchor": "target-surface:review:docs/reviews/_template.md",
            "logical_referenced_surface": "target-surface:docs/reviews/_template.md",
            "target_disposition_scope": "target-path:docs/reviews/_template.md",
        }
        return {
            "schema_version": "planveyor.contract_authority_matrix.rules.v1",
            "rule_set_id": "fixture-static-authority-v1",
            "source_selectors": [
                {
                    "id": "required",
                    "kind": "ast_tuple",
                    "source_path": "scripts/contract_authority_context.py",
                    "binding": "REQUIRED_ENGAGED_PATHS",
                    "consumer_anchor_prefix": "source:context:required",
                    "logical_surface_prefix": "source-path:",
                    "target_scope_prefix": "target-path:",
                },
                {
                    "id": "phase",
                    "kind": "role_phase_map",
                    "source_path": "scripts/planveyor.zsh",
                    "case_marker": "case \"${role_id}:${phase_id}\" in",
                    "consumer_anchor_prefix": "source:planveyor:phase",
                    "logical_surface_prefix": "source-prompt:",
                    "target_scope_prefix": "target-path:",
                    "source_prompt_prefix": "docs/tools/prompts/",
                    "target_prompt_prefix": "docs/tools/prompts/",
                },
                {
                    "id": "profiles",
                    "kind": "profile_file_tree",
                    "source_prefix": "docs/tools/prompts/profiles/planveyor",
                    "target_prefix": "docs/tools/prompts",
                    "consumer_anchor_prefix": "source:profile",
                    "logical_surface_prefix": "source-profile:",
                    "target_scope_prefix": "target-path:",
                    "require_nonempty": True,
                },
                {
                    "id": "builder-vocab",
                    "kind": "direct_literal_reference_hits",
                    "repository": "source",
                    "paths": ["src/builder.py"],
                    "literal": "VOCAB_TOKEN",
                    "consumer_anchor_prefix": "source:builder:vocab",
                    "logical_referenced_surface": "vocab:plan",
                    "target_disposition_scope": "source-runtime:builder-vocab",
                    "require_hit": True,
                },
                {
                    "id": "lint-vocab",
                    "kind": "direct_literal_reference_hits",
                    "repository": "source",
                    "paths": ["src/linter.py"],
                    "literal": "VOCAB_TOKEN",
                    "consumer_anchor_prefix": "source:linter:vocab",
                    "logical_referenced_surface": "vocab:plan",
                    "target_disposition_scope": "source-runtime:linter-vocab",
                    "require_hit": True,
                },
            ],
            "target_surface_selectors": [
                {
                    "id": "review",
                    "kind": "target_surface_tree",
                    "prefixes": ["docs/reviews"],
                    "consumer_anchor_prefix": "target-surface:review",
                    "logical_surface_prefix": "target-surface:",
                    "target_scope_prefix": "target-path:",
                    "require_nonempty": True,
                }
            ],
            "manual_research_anchors": [
                {
                    "id": "generated-behavior",
                    "consumer_anchor": "manual:generated:behavior",
                    "logical_referenced_surface": "generated:behavior",
                    "target_disposition_scope": "research:generated:behavior",
                    "source_proof_path": "scripts/planveyor.zsh",
                    "description": "A behavior frontier is explicit even when lexical selectors are empty.",
                    "decision": {
                        "decision_state": "unresolved_research",
                        "research_obligation": "Classify generated behavior with separate evidence.",
                        "implementation_evidence": {"state": "not_applicable", "obligations": []},
                    },
                },
                {
                    "id": "manager-zcode",
                    "consumer_anchor": "manual:manager:zcode-reachability",
                    "logical_referenced_surface": "manager:zcode",
                    "target_disposition_scope": "research:manager:zcode",
                    "source_proof_path": "scripts/planveyor.zsh",
                    "description": "Profile absence never makes ZCode reachability n/a.",
                    "decision": {
                        "decision_state": "unresolved_research",
                        "research_obligation": "Find a pinned consumer route before classifying reachability.",
                        "implementation_evidence": {"state": "not_applicable", "obligations": []},
                    },
                },
            ],
            "decisions": [
                {
                    "identity": target_identity,
                    "decision_state": "pending_owner",
                    "question": "Classify the bounded target review template.",
                    "implementation_evidence": {"state": "not_applicable", "obligations": []},
                }
            ],
            "n_a_reasons": [{"code": "scoped-proven-n-a", "description": "Pinned source evidence establishes the bounded non-applicability."}],
        }

    def _write_source_fixture(self) -> None:
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*(f'{name}' for name in _PROMPTS), 'AGENTS.md')\n",
        )
        write(
            self.source,
            "scripts/planveyor.zsh",
            "role_id=planner\nphase_id=init\ncase \"${role_id}:${phase_id}\" in\n  planner:init) echo \"planner_init.md\" ;;\n  manager:init|manager:merge) echo \"manager_init.md\" ;;\n  *) return 1 ;;\n  esac\n",
        )
        write(self.source, "docs/tools/prompts/planner_init.md", "planner source\n")
        write(self.source, "docs/tools/prompts/manager_init.md", "manager source\n")
        write(self.source, "docs/tools/prompts/profiles/planveyor/planner_init.md", "profile body\n")
        write(self.source, "AGENTS.md", "fixture agents\n")
        write(self.source, "src/builder.py", "VALUE = 'VOCAB_TOKEN'\n")
        write(self.source, "src/linter.py", "VALUE = 'VOCAB_TOKEN'\n")
        write(self.source, RULES_PATH, json.dumps(self._rules(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def _write_target_fixture(self) -> None:
        write(self.target, "docs/tools/prompts/planner_init.md", "planner target\n")
        write(self.target, "docs/tools/prompts/manager_init.md", "manager target\n")
        write(self.target, "AGENTS.md", "target agents\n")
        write(self.target, "docs/reviews/_template.md", "review template\n")

    def _command(self, command: str, *, source_commit: str | None = None, source_tree: str | None = None, target_commit: str | None = None, target_tree: str | None = None, extra: list[str] | None = None) -> list[str]:
        values = [
            sys.executable,
            "-B",
            os.fspath(SCRIPT),
            command,
            "--source-root",
            os.fspath(self.source),
            "--source-commit",
            source_commit or self.source_commit,
            "--source-tree",
            source_tree or self.source_tree,
            "--target-root",
            os.fspath(self.target),
            "--target-commit",
            target_commit or self.target_commit,
            "--target-tree",
            target_tree or self.target_tree,
            "--rules-repo-path",
            RULES_PATH,
        ]
        if extra:
            values.extend(extra)
        return values

    def _run(self, command: str, *, env: dict[str, str] | None = None, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(self._command(command, **kwargs), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)

    def _emit(self, **kwargs: Any) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
        result = self._run("emit", **kwargs)
        return result, json.loads(result.stdout)

    def _update_source_rules(self, mutator: Any) -> tuple[str, str]:
        rules = self._rules()
        mutator(rules)
        write(self.source, RULES_PATH, json.dumps(rules, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return commit(self.source, "update rules")

    def _write_inventory(self, value: dict[str, Any], name: str) -> Path:
        path = self.base / name
        path.write_bytes(canonical(value))
        return path

    def _assert_canonical_failure(self, result: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
        self.assertEqual(result.returncode, 2, result.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"Traceback", result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(result.stdout, canonical(document))
        self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")
        return document

    def test_emit_verify_deterministic_and_no_source_or_target_write(self) -> None:
        before_source = snapshot(self.source)
        before_target = snapshot(self.target)
        first, first_document = self._emit()
        second, second_document = self._emit()
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(second.returncode, 0, second.stderr.decode())
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first_document, second_document)
        self.assertEqual(first_document["outcomes"], {"inventory_integrity": "passed", "enumerated_decision_completeness": "blocked", "semantic_closure": "not_claimed"})
        self.assertEqual(snapshot(self.source), before_source)
        self.assertEqual(snapshot(self.target), before_target)
        inventory = self._write_inventory(first_document, "inventory.json")
        checked = self._run("verify", extra=["--inventory", os.fspath(inventory)])
        self.assertEqual(checked.returncode, 0, checked.stderr.decode())
        self.assertEqual(json.loads(checked.stdout)["outcomes"], first_document["outcomes"])
        self.assertEqual(snapshot(self.source), before_source)
        self.assertEqual(snapshot(self.target), before_target)

    def test_explicit_completeness_flag_returns_three_only_for_valid_blocked_inventory(self) -> None:
        result, document = self._emit(extra=["--require-enumerated-decision-completeness"])
        self.assertEqual(result.returncode, 3)
        self.assertEqual(document["outcomes"]["inventory_integrity"], "passed")
        self.assertEqual(document["outcomes"]["enumerated_decision_completeness"], "blocked")

    def test_pin_tree_and_absolute_root_fail_as_integrity_before_completeness(self) -> None:
        result, document = self._emit(source_tree="0" * 40, extra=["--require-enumerated-decision-completeness"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")
        command = self._command("emit")
        command[command.index("--source-root") + 1] = "relative-source"
        relative = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(relative.returncode, 2)
        self.assertEqual(json.loads(relative.stdout)["outcomes"]["inventory_integrity"], "failed")

    def test_surrogate_json_and_malformed_tree_paths_return_canonical_failure(self) -> None:
        def write_rules(rules: dict[str, Any]) -> tuple[str, str]:
            write(self.source, RULES_PATH, json.dumps(rules, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
            return commit(self.source, "malformed JSON fixture")

        bad_rule_mutations = (
            lambda rules: rules["manual_research_anchors"][0].__setitem__("description", "\ud800"),
            lambda rules: rules.__setitem__("\ud800", "unknown"),
            lambda rules: rules["source_selectors"][0].__setitem__("consumer_anchor_prefix", "\ud800"),
        )
        for mutation in bad_rule_mutations:
            with self.subTest(mutation=mutation):
                rules = self._rules()
                mutation(rules)
                source_commit, source_tree = write_rules(rules)
                self._assert_canonical_failure(self._run("emit", source_commit=source_commit, source_tree=source_tree))

        newline_path = self.target / "docs" / "reviews" / "bad\nname.md"
        newline_path.write_text("fixture\n", encoding="utf-8")
        newline_commit, newline_tree = commit(self.target, "newline tree fixture")
        self._assert_canonical_failure(self._run("emit", target_commit=newline_commit, target_tree=newline_tree))

        def git_input(arguments: list[str], data: bytes | None = None) -> bytes:
            return subprocess.check_output(["git", "-C", os.fspath(self.target), *arguments], input=data)

        def replace_tree_entry(ref: str, filename: bytes, mode: bytes, kind: bytes, oid: str) -> str:
            records = [record for record in git_input(["ls-tree", "-z", ref]).split(b"\0") if record]
            records = [record for record in records if record.split(b"\t", 1)[1] != filename]
            records.append(mode + b" " + kind + b" " + oid.encode("ascii") + b"\t" + filename)
            return git_input(["mktree", "-z"], b"\0".join(records) + b"\0").decode("ascii").strip()

        blob_oid = git_input(["hash-object", "-w", "--stdin"], b"fixture\n").decode("ascii").strip()
        review_tree = replace_tree_entry(self.target_commit + ":docs/reviews", b"bad\xffname.md", b"100644", b"blob", blob_oid)
        docs_tree = replace_tree_entry(self.target_commit + ":docs", b"reviews", b"040000", b"tree", review_tree)
        invalid_tree = replace_tree_entry(self.target_commit, b"docs", b"040000", b"tree", docs_tree)
        invalid_commit = git_input(["commit-tree", invalid_tree, "-p", self.target_commit, "-m", "invalid UTF-8 tree fixture"]).decode("ascii").strip()
        self._assert_canonical_failure(self._run("emit", target_commit=invalid_commit, target_tree=invalid_tree))

        emitted, candidate = self._emit()
        self.assertEqual(emitted.returncode, 0)
        candidate["rows"][0]["description"] = "\ud800"
        inventory = self.base / "surrogate-inventory.json"
        inventory.write_text(json.dumps(candidate, ensure_ascii=True), encoding="utf-8")
        self._assert_canonical_failure(self._run("verify", extra=["--inventory", os.fspath(inventory)]))

    def test_manual_selector_ids_are_unique_and_cannot_collide_with_declared_ids(self) -> None:
        emitted, document = self._emit()
        self.assertEqual(emitted.returncode, 0)
        inventory = self._write_inventory(document, "valid-inventory.json")

        def duplicate_manual(rules: dict[str, Any]) -> None:
            duplicate = json.loads(json.dumps(rules["manual_research_anchors"][0]))
            duplicate["consumer_anchor"] = "manual:generated:other"
            rules["manual_research_anchors"].append(duplicate)

        duplicate_commit, duplicate_tree = self._update_source_rules(duplicate_manual)
        self._assert_canonical_failure(self._run("emit", source_commit=duplicate_commit, source_tree=duplicate_tree))
        self._assert_canonical_failure(self._run("verify", source_commit=duplicate_commit, source_tree=duplicate_tree, extra=["--inventory", os.fspath(inventory)]))

        def collision(rules: dict[str, Any]) -> None:
            rules["source_selectors"][0]["id"] = "manual:generated-behavior"

        collision_commit, collision_tree = self._update_source_rules(collision)
        self._assert_canonical_failure(self._run("emit", source_commit=collision_commit, source_tree=collision_tree))
        self._assert_canonical_failure(self._run("verify", source_commit=collision_commit, source_tree=collision_tree, extra=["--inventory", os.fspath(inventory)]))

    def test_inherited_git_routing_cannot_change_result(self) -> None:
        baseline, _ = self._emit()
        poisoned = dict(os.environ)
        poisoned.update(
            {
                "GIT_DIR": "/definitely/not/a/git-dir",
                "GIT_OBJECT_DIRECTORY": "/definitely/not/an/object-dir",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/definitely/not/an/alternate-dir",
                "GIT_CONFIG_GLOBAL": "/definitely/not/a/config",
                "GIT_CEILING_DIRECTORIES": "/",
            }
        )
        rerun, _ = self._emit(env=poisoned)
        self.assertEqual(rerun.returncode, 0, rerun.stderr.decode())
        self.assertEqual(rerun.stdout, baseline.stdout)

    def test_verify_rejects_tampered_dropped_duplicate_and_extra_rows(self) -> None:
        emitted, document = self._emit()
        self.assertEqual(emitted.returncode, 0)
        variants: list[dict[str, Any]] = []
        tampered = json.loads(json.dumps(document))
        tampered["rows"][0]["object_evidence"]["consumer"]["object"]["sha256"] = "0" * 64
        variants.append(tampered)
        dropped = json.loads(json.dumps(document))
        dropped["rows"].pop()
        variants.append(dropped)
        duplicate = json.loads(json.dumps(document))
        duplicate["rows"].append(json.loads(json.dumps(duplicate["rows"][0])))
        variants.append(duplicate)
        extra = json.loads(json.dumps(document))
        extra_row = json.loads(json.dumps(extra["rows"][0]))
        extra_row["identity"]["consumer_anchor"] += ":extra"
        extra["rows"].append(extra_row)
        variants.append(extra)
        boolean_index = json.loads(json.dumps(document))
        ast_row = next(item for item in boolean_index["rows"] if item["selector"]["kind"] == "ast_tuple")
        ast_row["object_evidence"]["consumer"]["anchor"]["index"] = False
        variants.append(boolean_index)
        float_count = json.loads(json.dumps(document))
        float_count["expected_edges"]["count"] = float(float_count["expected_edges"]["count"])
        variants.append(float_count)
        boolean_line = json.loads(json.dumps(document))
        literal_row = next(item for item in boolean_line["rows"] if item["selector"]["kind"] == "direct_literal_reference_hits")
        literal_row["object_evidence"]["consumer"]["anchor"]["line"] = True
        variants.append(boolean_line)
        for index, variant in enumerate(variants):
            checked = self._run("verify", extra=["--inventory", os.fspath(self._write_inventory(variant, f"bad-{index}.json"))])
            self.assertEqual(checked.returncode, 2, checked.stdout.decode())
            self.assertEqual(json.loads(checked.stdout)["outcomes"]["inventory_integrity"], "failed")

    def test_new_literal_and_new_target_surface_entry_change_expected_set(self) -> None:
        emitted, document = self._emit()
        self.assertEqual(emitted.returncode, 0)
        inventory = self._write_inventory(document, "old.json")
        write(self.source, "src/builder.py", "VALUE = 'VOCAB_TOKEN'\nOTHER = 'VOCAB_TOKEN'\n")
        new_source_commit, new_source_tree = commit(self.source, "new literal")
        literal_check = self._run("verify", source_commit=new_source_commit, source_tree=new_source_tree, extra=["--inventory", os.fspath(inventory)])
        self.assertEqual(literal_check.returncode, 2)
        write(self.target, "docs/reviews/new.md", "new target entry\n")
        new_target_commit, new_target_tree = commit(self.target, "new target")
        target_check = self._run("verify", source_commit=new_source_commit, source_tree=new_source_tree, target_commit=new_target_commit, target_tree=new_target_tree, extra=["--inventory", os.fspath(inventory)])
        self.assertEqual(target_check.returncode, 2)

    def test_target_surface_prefixes_require_each_declared_prefix_and_dedupe_overlap(self) -> None:
        emitted, document = self._emit()
        self.assertEqual(emitted.returncode, 0)
        inventory = self._write_inventory(document, "prior-valid-target-surface-inventory.json")

        def missing_one_required_prefix(rules: dict[str, Any]) -> None:
            selector = rules["target_surface_selectors"][0]
            selector["prefixes"] = ["docs/reviews", "docs/declared-but-absent"]

        missing_commit, missing_tree = self._update_source_rules(missing_one_required_prefix)
        for command, extra in (("emit", None), ("verify", ["--inventory", os.fspath(inventory)])):
            with self.subTest(command=command):
                result = self._run(command, source_commit=missing_commit, source_tree=missing_tree, extra=extra)
                failure = self._assert_canonical_failure(result)
                self.assertIn("review", failure["error"]["message"])
                self.assertIn("docs/declared-but-absent", failure["error"]["message"])

        def overlap(rules: dict[str, Any]) -> None:
            selector = rules["target_surface_selectors"][0]
            selector["prefixes"] = ["docs/reviews", "docs/reviews/_template.md"]

        overlap_commit, overlap_tree = self._update_source_rules(overlap)
        overlapped, overlap_document = self._emit(source_commit=overlap_commit, source_tree=overlap_tree)
        self.assertEqual(overlapped.returncode, 0, overlapped.stdout.decode())
        overlap_rows = [row for row in overlap_document["rows"] if row["selector"]["id"] == "review"]
        self.assertEqual([row["object_evidence"]["target_surface"]["path"] for row in overlap_rows], ["docs/reviews/_template.md"])
        overlap_inventory = self._write_inventory(overlap_document, "overlap-target-surface-inventory.json")
        checked = self._run("verify", source_commit=overlap_commit, source_tree=overlap_tree, extra=["--inventory", os.fspath(overlap_inventory)])
        self.assertEqual(checked.returncode, 0, checked.stdout.decode())

        def optional_missing_prefix(rules: dict[str, Any]) -> None:
            selector = rules["target_surface_selectors"][0]
            selector["prefixes"] = ["docs/reviews/_template.md", "docs/optional-absent"]
            selector["require_nonempty"] = False

        optional_commit, optional_tree = self._update_source_rules(optional_missing_prefix)
        optional, optional_document = self._emit(source_commit=optional_commit, source_tree=optional_tree)
        self.assertEqual(optional.returncode, 0, optional.stdout.decode())
        optional_rows = [row for row in optional_document["rows"] if row["selector"]["id"] == "review"]
        self.assertEqual([row["object_evidence"]["target_surface"]["path"] for row in optional_rows], ["docs/reviews/_template.md"])

    def test_help_is_canonical_usage_failure(self) -> None:
        for scope in ([], ["emit"], ["verify"]):
            for option in ("-h", "--help"):
                with self.subTest(scope=scope, option=option):
                    result = subprocess.run(
                        [sys.executable, "-B", os.fspath(SCRIPT), *scope, option],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    failure = self._assert_canonical_failure(result)
                    self.assertEqual(result.stderr, b"")
                    self.assertTrue(failure["error"]["message"])

    def test_planned_extraction_requires_typed_evidence_but_unfulfilled_does_not_change_state(self) -> None:
        identity = {
            "consumer_anchor": "source:context:required:0",
            "logical_referenced_surface": "source-path:docs/tools/prompts/planner_init.md",
            "target_disposition_scope": "target-path:docs/tools/prompts/planner_init.md",
        }

        def missing(rules: dict[str, Any]) -> None:
            rules["decisions"].append(
                {
                    "identity": identity,
                    "decision_state": "decided",
                    "disposition": {"kind": "planned_extraction"},
                    "decision_evidence": [{"path": "scripts/contract_authority_context.py"}],
                }
            )

        bad_commit, bad_tree = self._update_source_rules(missing)
        invalid, invalid_document = self._emit(source_commit=bad_commit, source_tree=bad_tree)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid_document["outcomes"]["inventory_integrity"], "failed")

    def test_proven_n_a_requires_declared_reason_and_pinned_source_literal(self) -> None:
        identity = {
            "consumer_anchor": "source:context:required:0",
            "logical_referenced_surface": "source-path:docs/tools/prompts/planner_init.md",
            "target_disposition_scope": "target-path:docs/tools/prompts/planner_init.md",
        }

        def invalid_na(rules: dict[str, Any]) -> None:
            rules["decisions"].append(
                {
                    "identity": identity,
                    "decision_state": "decided",
                    "disposition": {"kind": "not_applicable"},
                    "decision_evidence": [{"path": "scripts/contract_authority_context.py"}],
                    "n_a": {"reason_code": "not-declared", "source_proof": {"path": "scripts/contract_authority_context.py", "literal": "REQUIRED_ENGAGED_PATHS", "line": 2}},
                    "implementation_evidence": {"state": "not_applicable", "obligations": []},
                }
            )

        commit_id, tree_id = self._update_source_rules(invalid_na)
        invalid, document = self._emit(source_commit=commit_id, source_tree=tree_id)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")

    def test_proven_n_a_with_declared_pinned_literal_is_a_decided_row(self) -> None:
        identity = {
            "consumer_anchor": "source:context:required:0",
            "logical_referenced_surface": "source-path:docs/tools/prompts/planner_init.md",
            "target_disposition_scope": "target-path:docs/tools/prompts/planner_init.md",
        }

        def valid_na(rules: dict[str, Any]) -> None:
            rules["decisions"].append(
                {
                    "identity": identity,
                    "decision_state": "decided",
                    "disposition": {"kind": "not_applicable"},
                    "decision_evidence": [{"path": "scripts/contract_authority_context.py"}],
                    "n_a": {"reason_code": "scoped-proven-n-a", "source_proof": {"path": "scripts/contract_authority_context.py", "literal": "REQUIRED_ENGAGED_PATHS", "line": 2}},
                    "implementation_evidence": {"state": "not_applicable", "obligations": []},
                }
            )

        commit_id, tree_id = self._update_source_rules(valid_na)
        emitted, document = self._emit(source_commit=commit_id, source_tree=tree_id)
        self.assertEqual(emitted.returncode, 0, emitted.stdout.decode())
        row = next(item for item in document["rows"] if item["identity"] == identity)
        self.assertEqual(row["decision_state"], "decided")
        self.assertEqual(row["n_a"]["reason_code"], "scoped-proven-n-a")

    def test_fstring_conversion_and_unrecognized_phase_clause_fail_closed(self) -> None:
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*(f'{name!r}' for name in _PROMPTS),)\n",
        )
        conversion_commit, conversion_tree = commit(self.source, "fstring conversion")
        converted, conversion_document = self._emit(source_commit=conversion_commit, source_tree=conversion_tree)
        self.assertEqual(converted.returncode, 2)
        self.assertEqual(conversion_document["outcomes"]["inventory_integrity"], "failed")
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS, 'AGENTS.md')\n",
        )
        write(
            self.source,
            "scripts/planveyor.zsh",
            "role_id=planner\nphase_id=init\ncase \"${role_id}:${phase_id}\" in\n  planner:init) filename=planner_init.md; echo \"$filename\" ;;\n  *) return 1 ;;\n  esac\n",
        )
        phase_commit, phase_tree = commit(self.source, "unrecognized phase clause")
        malformed, malformed_document = self._emit(source_commit=phase_commit, source_tree=phase_tree)
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(malformed_document["outcomes"]["inventory_integrity"], "failed")

    def test_ast_binding_audit_rejects_augassign_and_mutation_prone_list_dependency(self) -> None:
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\n_PROMPTS += ('docs/tools/prompts/manager_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS, 'AGENTS.md')\n",
        )
        aug_commit, aug_tree = commit(self.source, "augassign")
        augmented, augmented_document = self._emit(source_commit=aug_commit, source_tree=aug_tree)
        self.assertEqual(augmented.returncode, 2)
        self.assertEqual(augmented_document["outcomes"]["inventory_integrity"], "failed")
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ['docs/tools/prompts/planner_init.md']\n_PROMPTS.append('docs/tools/prompts/manager_init.md')\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS, 'AGENTS.md')\n",
        )
        list_commit, list_tree = commit(self.source, "list append")
        listed, listed_document = self._emit(source_commit=list_commit, source_tree=list_tree)
        self.assertEqual(listed.returncode, 2)
        self.assertEqual(listed_document["outcomes"]["inventory_integrity"], "failed")
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nif True:\n    _PROMPTS = ('docs/tools/prompts/manager_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS, 'AGENTS.md')\n",
        )
        rebound_commit, rebound_tree = commit(self.source, "nested rebinding")
        rebound, rebound_document = self._emit(source_commit=rebound_commit, source_tree=rebound_tree)
        self.assertEqual(rebound.returncode, 2)
        self.assertEqual(rebound_document["outcomes"]["inventory_integrity"], "failed")

    def test_ast_context_grammar_rejects_implicit_expansion_and_nonassignment_binders(self) -> None:
        bad_sources = {
            "bare-name": "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (_PROMPTS,)\n",
            "bare-generator": "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = ((f'{name}' for name in _PROMPTS),)\n",
            "scalar-star": "name = 'not-a-tuple'\nREQUIRED_ENGAGED_PATHS = (*name,)\n",
            "tuple-call": "_PROMPTS = tuple(('docs/tools/prompts/planner_init.md',))\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS,)\n",
            "filtered-generator": "_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*(f'{name}' for name in _PROMPTS if name),)\n",
            "import-binder": "import fake as _PROMPTS\n_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS,)\n",
            "wildcard-import": "from fake import *\n_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS,)\n",
            "function-binder": "def _PROMPTS():\n    return ()\n_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS,)\n",
            "match-mapping-binder": "match {}:\n    case {**_PROMPTS}:\n        pass\n_PROMPTS = ('docs/tools/prompts/planner_init.md',)\nREQUIRED_ENGAGED_PATHS = (*_PROMPTS,)\n",
        }
        for label, source_text in bad_sources.items():
            with self.subTest(label=label):
                write(self.source, "scripts/contract_authority_context.py", source_text)
                source_commit, source_tree = commit(self.source, f"AST grammar {label}")
                invalid, document = self._emit(source_commit=source_commit, source_tree=source_tree)
                self.assertEqual(invalid.returncode, 2, invalid.stdout.decode())
                self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")

    def test_ast_context_grammar_accepts_partitioned_literal_starred_union(self) -> None:
        write(
            self.source,
            "scripts/contract_authority_context.py",
            "_TARGET = ('docs/tools/prompts/planner_init.md',)\n"
            "_PRIVATE = ('docs/tools/prompts/manager_init.md',)\n"
            "_PROMPT_FILENAMES = (*_TARGET, *_PRIVATE)\n"
            "REQUIRED_ENGAGED_PATHS = (*(f'{name}' for name in _TARGET), 'AGENTS.md')\n",
        )
        rules = self._rules()
        rules["source_selectors"][0]["binding"] = "_PROMPT_FILENAMES"
        write(self.source, RULES_PATH, json.dumps(rules, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        source_commit, source_tree = commit(self.source, "partitioned literal prompt union")
        emitted, document = self._emit(source_commit=source_commit, source_tree=source_tree)
        self.assertEqual(emitted.returncode, 0, emitted.stdout.decode())
        values = [
            row["provenance"]["value"]
            for row in document["rows"]
            if row["selector"]["id"] == "required"
        ]
        self.assertEqual(
            values,
            ["docs/tools/prompts/planner_init.md", "docs/tools/prompts/manager_init.md"],
        )

    def test_phase_filename_grammar_and_duplicate_marker_fail_closed(self) -> None:
        write(
            self.source,
            "scripts/planveyor.zsh",
            "role_id=planner\nphase_id=init\ncase \"${role_id}:${phase_id}\" in\n  planner:init) echo \"$phase_id.md\" ;;\n  *) return 1 ;;\n  esac\n",
        )
        grammar_commit, grammar_tree = commit(self.source, "phase filename grammar")
        grammar, grammar_document = self._emit(source_commit=grammar_commit, source_tree=grammar_tree)
        self.assertEqual(grammar.returncode, 2)
        self.assertEqual(grammar_document["outcomes"]["inventory_integrity"], "failed")
        write(
            self.source,
            "scripts/planveyor.zsh",
            "# case \"${role_id}:${phase_id}\" in\nrole_id=planner\nphase_id=init\ncase \"${role_id}:${phase_id}\" in\n  planner:init) echo \"planner_init.md\" ;;\n  *) return 1 ;;\n  esac\n",
        )
        duplicate_commit, duplicate_tree = commit(self.source, "duplicate phase marker")
        duplicate, duplicate_document = self._emit(source_commit=duplicate_commit, source_tree=duplicate_tree)
        self.assertEqual(duplicate.returncode, 2)
        self.assertEqual(duplicate_document["outcomes"]["inventory_integrity"], "failed")

    def test_present_implementation_evidence_is_not_an_attestation_in_v1(self) -> None:
        first_identity = {
            "consumer_anchor": "source:context:required:0",
            "logical_referenced_surface": "source-path:docs/tools/prompts/planner_init.md",
            "target_disposition_scope": "target-path:docs/tools/prompts/planner_init.md",
        }
        second_identity = {
            "consumer_anchor": "source:context:required:1",
            "logical_referenced_surface": "source-path:AGENTS.md",
            "target_disposition_scope": "target-path:AGENTS.md",
        }

        def present_planned(rules: dict[str, Any]) -> None:
            rules["decisions"].append(
                {
                    "identity": first_identity,
                    "decision_state": "decided",
                    "disposition": {"kind": "planned_extraction"},
                    "decision_evidence": [{"path": "scripts/contract_authority_context.py"}],
                    "implementation_evidence": {"state": "present", "obligations": []},
                }
            )

        planned_commit, planned_tree = self._update_source_rules(present_planned)
        planned, planned_document = self._emit(source_commit=planned_commit, source_tree=planned_tree)
        self.assertEqual(planned.returncode, 2)
        self.assertEqual(planned_document["outcomes"]["inventory_integrity"], "failed")

        def present_copy(rules: dict[str, Any]) -> None:
            rules["decisions"].append(
                {
                    "identity": second_identity,
                    "decision_state": "decided",
                    "disposition": {"kind": "copy_to_target"},
                    "decision_evidence": [{"path": "scripts/contract_authority_context.py"}],
                    "implementation_evidence": {"state": "present", "obligations": []},
                }
            )

        copy_commit, copy_tree = self._update_source_rules(present_copy)
        copied, copied_document = self._emit(source_commit=copy_commit, source_tree=copy_tree)
        self.assertEqual(copied.returncode, 2)
        self.assertEqual(copied_document["outcomes"]["inventory_integrity"], "failed")

    def test_declared_target_surface_rejects_gitlink_entry(self) -> None:
        git(self.target, "update-index", "--add", "--cacheinfo", f"160000,{self.target_commit},docs/reviews/foreign")
        git(self.target, "commit", "-qm", "gitlink target surface")
        target_commit = git(self.target, "rev-parse", "HEAD")
        target_tree = git(self.target, "rev-parse", f"{target_commit}^{{tree}}")
        emitted, document = self._emit(target_commit=target_commit, target_tree=target_tree)
        self.assertEqual(emitted.returncode, 2)
        self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")

    def test_profile_tree_and_target_surface_reject_symlink_entries(self) -> None:
        profile = self.source / "docs" / "tools" / "prompts" / "profiles" / "planveyor" / "planner_init.md"
        profile.unlink()
        os.symlink("planner_init.md", profile)
        source_commit, source_tree = commit(self.source, "profile symlink")
        invalid_profile, profile_document = self._emit(source_commit=source_commit, source_tree=source_tree)
        self.assertEqual(invalid_profile.returncode, 2)
        self.assertEqual(profile_document["outcomes"]["inventory_integrity"], "failed")

        review = self.target / "docs" / "reviews" / "_template.md"
        review.unlink()
        os.symlink("linked-template.md", review)
        target_commit, target_tree = commit(self.target, "review symlink")
        invalid_target, target_document = self._emit(target_commit=target_commit, target_tree=target_tree)
        self.assertEqual(invalid_target.returncode, 2)
        self.assertEqual(target_document["outcomes"]["inventory_integrity"], "failed")

    def test_present_source_and_target_surfaces_reject_symlink_facts(self) -> None:
        source_prompt = self.source / "docs" / "tools" / "prompts" / "planner_init.md"
        source_prompt.unlink()
        os.symlink("manager_init.md", source_prompt)
        source_commit, source_tree = commit(self.source, "source prompt symlink")
        invalid_source, source_document = self._emit(source_commit=source_commit, source_tree=source_tree)
        self.assertEqual(invalid_source.returncode, 2)
        self.assertEqual(source_document["outcomes"]["inventory_integrity"], "failed")

        target_prompt = self.target / "docs" / "tools" / "prompts" / "planner_init.md"
        target_prompt.unlink()
        os.symlink("manager_init.md", target_prompt)
        target_commit, target_tree = commit(self.target, "target prompt symlink")
        invalid_target, target_document = self._emit(target_commit=target_commit, target_tree=target_tree)
        self.assertEqual(invalid_target.returncode, 2)
        self.assertEqual(target_document["outcomes"]["inventory_integrity"], "failed")

    def test_builder_and_linter_are_distinct_edges_and_zcode_is_research(self) -> None:
        emitted, document = self._emit()
        self.assertEqual(emitted.returncode, 0)
        identities = [row["identity"] for row in document["rows"]]
        builder = [item for item in identities if item["consumer_anchor"].startswith("source:builder:vocab:")]
        linter = [item for item in identities if item["consumer_anchor"].startswith("source:linter:vocab:")]
        self.assertTrue(builder)
        self.assertTrue(linter)
        self.assertNotEqual(builder[0], linter[0])
        zcode = next(row for row in document["rows"] if row["identity"]["consumer_anchor"] == "manual:manager:zcode-reachability")
        self.assertEqual(zcode["decision_state"], "unresolved_research")
        self.assertNotIn("n_a", zcode)

    def test_nonregular_text_source_and_raw_path_alias_fail_closed(self) -> None:
        (self.source / "src" / "builder.py").unlink()
        os.symlink("linter.py", self.source / "src" / "builder.py")
        source_commit, source_tree = commit(self.source, "symlink literal source")
        invalid, document = self._emit(source_commit=source_commit, source_tree=source_tree)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(document["outcomes"]["inventory_integrity"], "failed")
        command = self._command("emit")
        command[command.index("--rules-repo-path") + 1] = "docs//tools/authority_matrix/rules.json"
        aliased = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(aliased.returncode, 2)

    def test_module_is_stdlib_only_and_has_no_output_argument(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.partition(".")[0])
        stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
        self.assertTrue(imports <= stdlib, imports - stdlib)
        self.assertNotIn("--out", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

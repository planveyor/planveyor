#!/usr/bin/env python3
"""Regression coverage for authority context across anchored child commands."""

from __future__ import annotations

import json
import textwrap
import unittest

from scripts import contract_authority_context as source_authority
from scripts.authority_bootstrap_test_support import run_python_stdin
from scripts.test_contract_authority_support import AuthorityFixture


_NESTED_MANIFEST_HARNESS = textwrap.dedent(
    """\
    import json
    from pathlib import Path
    import subprocess
    import sys

    import build_role_bundles as bundles
    import contract_authority_context as authority

    root = Path.cwd()
    mode = sys.argv[1]
    outer = authority.resolve_top_level_context(root)
    outer_envelope = authority.context_to_json(outer)
    actual_run = subprocess.run
    advanced = False
    child_envelope = None
    anchored = False

    def commit_paths(paths, message):
        actual_run(
            [
                "git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
                "-C", str(root), "add", "--", *paths,
            ],
            check=True,
        )
        actual_run(
            [
                "git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
                "-C", str(root), "commit", "--quiet", "-m", message,
            ],
            check=True,
        )

    def advance_generation():
        selector_path = root / authority._snapshot.MARKER_PATH
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        selector["required_runtime_api"] = {"minimum": 4, "maximum": 5}
        selector_path.write_text(json.dumps(selector, ensure_ascii=False, sort_keys=True) + "\\n", encoding="utf-8")

    def advance_unrelated():
        path = root / "unrelated" / "child-context.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unrelated target evolution\\n", encoding="utf-8")
        commit_paths(["unrelated/child-context.txt"], "unrelated child-context evolution")

    def intercept(command, *args, **kwargs):
        global advanced, child_envelope, anchored
        if not advanced and isinstance(command, list) and command[:2] == ["/bin/zsh", "-dfc"]:
            advanced = True
            child_envelope = kwargs.get("env", {}).get("_PLANVEYOR_AUTHORITY_CONTEXT_V1")
            anchored = "planveyor_source_runtime" in command[2]
            if mode == "generation":
                advance_generation()
            else:
                advance_unrelated()
        return actual_run(command, *args, **kwargs)

    bundles.subprocess.run = intercept
    error = None
    resolved = None
    try:
        profile, content_profile, manifest = bundles._load_prompt_manifest(
            root,
            outer.runtime_pin.runtime_root,
            ["architect"],
            context=outer,
        )
        resolved = {
            "profile": profile,
            "content_profile": content_profile,
            "roles": sorted(manifest),
        }
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        bundles.subprocess.run = actual_run

    fresh = authority.resolve_top_level_context(root)
    print(json.dumps({
        "advanced": advanced,
        "anchored": anchored,
        "child_envelope_matches_outer": child_envelope == outer_envelope,
        "outer_generation": outer.generation_sha256,
        "fresh_generation": fresh.generation_sha256,
        "generations_differ": outer.generation_sha256 != fresh.generation_sha256,
        "resolved": resolved,
        "error": error,
    }, sort_keys=True))
    """
)


class AuthorityChildContextTests(unittest.TestCase):
    def _run_manifest_child(self, mode: str) -> dict[str, object]:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(source_authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            result = run_python_stdin(
                fixture,
                _NESTED_MANIFEST_HARNESS,
                mode,
                timeout=120,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_anchored_child_rejects_a_valid_new_selector_generation(self) -> None:
        payload = self._run_manifest_child("generation")

        self.assertTrue(payload["advanced"])
        self.assertTrue(payload["anchored"])
        self.assertTrue(payload["child_envelope_matches_outer"])
        self.assertTrue(payload["generations_differ"])
        self.assertIsNone(payload["resolved"])
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertEqual(error["type"], "BuildError")
        self.assertIn("context_expectation_mismatch", error["message"])

    def test_anchored_child_accepts_unrelated_target_evolution(self) -> None:
        payload = self._run_manifest_child("unrelated")

        self.assertTrue(payload["advanced"])
        self.assertTrue(payload["anchored"])
        self.assertTrue(payload["child_envelope_matches_outer"])
        self.assertFalse(payload["generations_differ"])
        self.assertEqual(
            payload["resolved"],
            {"profile": "default", "content_profile": "target-local", "roles": ["architect"]},
        )
        self.assertIsNone(payload["error"])


if __name__ == "__main__":
    unittest.main()

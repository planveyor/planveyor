"""Complete mechanical admission rejects every omitted required carrier."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_authority_context as authority
from authority_bootstrap_test_support import run_python_stdin
from test_contract_authority_support import AuthorityFixture, SOURCE_ROOT, commit_all, tree_snapshot, write


class AuthorityAdmissionTests(unittest.TestCase):
    @staticmethod
    def _resolve_fixture_context(fixture: AuthorityFixture):
        return run_python_stdin(
            fixture,
            "import json\n"
            "import contract_authority_context as authority\n"
            "authority.ENGAGED_ADMISSION_COMPLETE = True\n"
            "try:\n"
            "    context = authority.resolve_top_level_context()\n"
            "except authority.ContractAuthorityError as error:\n"
            "    payload = {'reason_code': error.reason_code, 'message': str(error)}\n"
            "else:\n"
            "    payload = {'state': context.state, 'declared_rows': len(context.declared_rows)}\n"
            "print(json.dumps(payload, sort_keys=True))\n",
            cwd=fixture.target_root,
            environment=fixture.environment(),
        )

    def test_required_prompt_and_ui_paths_match_the_actual_finite_resolvers(self) -> None:
        source = (SOURCE_ROOT / "scripts/planveyor.zsh").read_text()
        start = source.index("_planveyor_prompt_filename_for_role_phase() {")
        end = source.index("\n}\n", start)
        cases = re.findall(r'^\s*([^\n)]+)\)\s+echo\s+"([a-z_]+\.md)"\s+;;$', source[start:end], re.MULTILINE)
        filenames = {filename for _selectors, filename in cases}
        self.assertTrue(filenames)
        self.assertEqual(set(authority._PROMPT_FILENAMES), filenames)
        self.assertEqual(sum(len(selectors.split("|")) for selectors, _filename in cases), 35)
        self.assertEqual(len(filenames), 34)
        case_map = {
            selector: filename
            for selectors, filename in cases
            for selector in selectors.split("|")
        }
        self.assertEqual(len(case_map), 35)
        self.assertEqual(case_map["manager:merge_pipeline"], "manager_collab_merge_pipeline.md")
        self.assertEqual(case_map["manager:collab_merge_pipeline"], "manager_collab_merge_pipeline.md")
        self.assertEqual(len(authority._TARGET_LOCAL_PROMPT_FILENAMES), 34)
        self.assertEqual(authority._PROMPT_FILENAMES, authority._TARGET_LOCAL_PROMPT_FILENAMES)
        self.assertEqual(len(authority._PROMPT_FILENAMES), 34)
        required_prompt_paths = {
            path for path in authority.REQUIRED_ENGAGED_PATHS if path.startswith("docs/tools/prompts/")
        }
        self.assertEqual(
            required_prompt_paths,
            {f"docs/tools/prompts/{name}" for name in authority._TARGET_LOCAL_PROMPT_FILENAMES},
        )
        self.assertFalse(any("/profiles/" in path for path in authority.REQUIRED_ENGAGED_PATHS))
        self.assertEqual(len(authority.REQUIRED_ENGAGED_PATHS), 59)
        self.assertEqual(authority.REQUIRED_ENGAGED_PATHS, authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
        self.assertFalse(any("dev_ui_" in path for path in authority.REQUIRED_ENGAGED_PATHS))

    def test_physical_v1_marker_blocks_without_queue_or_lock_effects(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate((authority.REQUIRED_ENGAGED_PATHS[0],))
            before = tree_snapshot(fixture.target_root)
            rejected = self._resolve_fixture_context(fixture)
            self.assertEqual(rejected.returncode, 0, rejected.stderr)
            payload = json.loads(rejected.stdout)
            self.assertEqual(payload["reason_code"], "unsupported_live_marker_schema")
            self.assertFalse((fixture.target_root / ".planveyor.planqueue.json").exists())
            self.assertFalse((fixture.target_root / ".planveyor.planqueue.lock").exists())
            self.assertEqual(tree_snapshot(fixture.target_root), before)

    def test_api_one_marker_rejects_an_otherwise_complete_target_with_api_two_pin(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            marker_path = "docs/_meta/planveyor_contract_authority.v1.json"
            marker = json.loads((fixture.target_root / marker_path).read_text(encoding="utf-8"))
            marker["required_runtime_api"] = {"minimum": 1, "maximum": 1}
            write(fixture.target_root, marker_path, json.dumps(marker, sort_keys=True) + "\n")
            rejected = self._resolve_fixture_context(fixture)

        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["reason_code"], "runtime_api_incompatible")


if __name__ == "__main__":
    unittest.main()

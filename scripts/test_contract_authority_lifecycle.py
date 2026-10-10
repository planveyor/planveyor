#!/usr/bin/env python3
"""Focused real-repository coverage for Package B lifecycle readers.

The cases execute the copied candidate runtime from a disposable Git checkout.
They explicitly enable admission inside that child interpreter and do not
change the reviewed source constant in the parent checkout.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_context
from authority_bootstrap_test_support import run_python_stdin
from test_contract_authority_support import AuthorityFixture


class ContractAuthorityLifecycleTests(unittest.TestCase):
    def _run_candidate(self, fixture: AuthorityFixture, body: str) -> subprocess.CompletedProcess[str]:
        return run_python_stdin(
            fixture,
            body,
            cwd=fixture.target_root,
            environment=fixture.environment(),
            timeout=45,
        )

    @staticmethod
    def _admission_prelude() -> str:
        return (
            "import contract_authority_context as authority\n"
            "authority.ENGAGED_ADMISSION_COMPLETE = True\n"
        )

    def test_engaged_default_template_scopes_read_target_rows(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            result = self._run_candidate(
                fixture,
                self._admission_prelude()
                + "import contextlib\n"
                + "import io\n"
                + "import json\n"
                + "import plan_harvest_lint\n"
                + "import post_merge_audit_lint\n"
                + "import review_artifact_lint\n"
                + "context = authority.resolve_top_level_context()\n"
                + "payload = {\n"
                + "  'review': [str(item.path) for item in review_artifact_lint.load_review_artifacts(context.project_root, context=context)],\n"
                + "  'audit': [str(item.path) for item in post_merge_audit_lint.load_audit_artifacts(context.project_root, context=context)],\n"
                + "  'harvest': [str(item.path) for item in plan_harvest_lint.load_harvest_artifacts(context.project_root, context=context)],\n"
                + "}\n"
                + "cli_paths = {}\n"
                + "def capture_default_scope(loader, name):\n"
                + "    def wrapped(project_root, raw_paths=None, *, context=None):\n"
                + "        artifacts = loader(project_root, raw_paths, context=context)\n"
                + "        cli_paths[name] = [str(item.path) for item in artifacts]\n"
                + "        return []\n"
                + "    return wrapped\n"
                + "review_artifact_lint.load_review_artifacts = capture_default_scope(review_artifact_lint.load_review_artifacts, 'review')\n"
                + "post_merge_audit_lint.load_audit_artifacts = capture_default_scope(post_merge_audit_lint.load_audit_artifacts, 'audit')\n"
                + "plan_harvest_lint.load_harvest_artifacts = capture_default_scope(plan_harvest_lint.load_harvest_artifacts, 'harvest')\n"
                + "with contextlib.redirect_stdout(io.StringIO()):\n"
                + "    cli_codes = [review_artifact_lint.main([]), post_merge_audit_lint.main([]), plan_harvest_lint.main([])]\n"
                + "payload['cli'] = {'codes': cli_codes, 'paths': cli_paths}\n"
                + "print(json.dumps(payload, sort_keys=True))\n",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            {key: len(payload[key]) for key in ("audit", "harvest", "review")},
            {"audit": 1, "harvest": 1, "review": 5},
        )
        self.assertEqual(payload["cli"]["codes"], [0, 0, 0])
        self.assertEqual(
            {key: len(value) for key, value in payload["cli"]["paths"].items()},
            {"audit": 1, "harvest": 1, "review": 5},
        )
        paths = [
            Path(item)
            for values in (
                payload["audit"],
                payload["harvest"],
                payload["review"],
                *payload["cli"]["paths"].values(),
            )
            for item in values
        ]
        self.assertTrue(all(path.is_relative_to(fixture.target_root) for path in paths))
        self.assertTrue(all(not path.is_relative_to(fixture.runtime_root) for path in paths))

    def test_plan_lint_scopes_target_vocabulary_root_per_context(self) -> None:
        with AuthorityFixture() as first, AuthorityFixture() as second:
            first.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            second_vocab = json.loads((SCRIPT_DIR.parent / "docs/_meta/plan_vocab.json").read_text(encoding="utf-8"))
            second_vocab["clusters"] = {
                "canonical": ["second-fixture-cluster"],
                "deprecated_aliases": {},
            }
            second.activate_planveyor(
                source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
                overrides={"docs/_meta/plan_vocab.json": json.dumps(second_vocab, sort_keys=True)},
            )
            result = self._run_candidate(
                first,
                self._admission_prelude()
                + "import json\n"
                + "from pathlib import Path\n"
                + "import plan_lint\n"
                + f"first_root = Path({str(first.target_root)!r})\n"
                + f"second_root = Path({str(second.target_root)!r})\n"
                + "first_context = authority.resolve_top_level_context(first_root)\n"
                + "second_context = authority.resolve_top_level_context(second_root)\n"
                + "baseline = {\n"
                + "  'root': str(plan_lint.REPO_ROOT),\n"
                + "  'vocab': str(plan_lint.PLAN_VOCAB_PATH),\n"
                + "  'clusters': sorted(plan_lint.ALLOWED_CLUSTERS),\n"
                + "}\n"
                + "with plan_lint._scoped_plan_lint_context(first_root, context=first_context, require_vocab=True):\n"
                + "    first_vocab = str(plan_lint.PLAN_VOCAB_PATH)\n"
                + "    first_clusters = sorted(plan_lint.ALLOWED_CLUSTERS)\n"
                + "with plan_lint._scoped_plan_lint_context(second_root, context=second_context, require_vocab=True):\n"
                + "    second_vocab = str(plan_lint.PLAN_VOCAB_PATH)\n"
                + "    second_clusters = sorted(plan_lint.ALLOWED_CLUSTERS)\n"
                + "import os\n"
                + "os.environ['PLANVEYOR_PROJECT_ROOT'] = str(second_root)\n"
                + "engaged_root = str(plan_lint.repo_root_for_plan_path(first_root / 'docs/plans/example.md', context=first_context))\n"
                + "print(json.dumps({\n"
                + "  'first_vocab': first_vocab, 'second_vocab': second_vocab,\n"
                + "  'first_clusters': first_clusters, 'second_clusters': second_clusters,\n"
                + "  'engaged_root': engaged_root,\n"
                + "  'restored': {\n"
                + "    'root': str(plan_lint.REPO_ROOT),\n"
                + "    'vocab': str(plan_lint.PLAN_VOCAB_PATH),\n"
                + "    'clusters': sorted(plan_lint.ALLOWED_CLUSTERS),\n"
                + "  }, 'baseline': baseline,\n"
                + "}, sort_keys=True))\n",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["first_vocab"].startswith(str(first.target_root)))
        self.assertTrue(payload["second_vocab"].startswith(str(second.target_root)))
        self.assertNotEqual(payload["first_vocab"], payload["second_vocab"])
        self.assertNotEqual(payload["first_clusters"], payload["second_clusters"])
        self.assertEqual(payload["second_clusters"], ["second-fixture-cluster"])
        self.assertEqual(payload["engaged_root"], str(first.target_root))
        self.assertEqual(payload["restored"], payload["baseline"])

    def test_engaged_queue_rejects_missing_vocabulary_before_lock_creation(self) -> None:
        required_without_vocab = tuple(
            path
            for path in source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS
            if path != "docs/_meta/plan_vocab.json"
        )
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(required_without_vocab)
            result = self._run_candidate(
                fixture,
                self._admission_prelude()
                + "import plan_queue\n"
                + "show_code = plan_queue.main(['show', '--json'])\n"
                + "history_code = plan_queue.main(['history', '--json'])\n"
                + "print(show_code, history_code)\n",
            )
            lock_exists = (fixture.target_root / ".planveyor.planqueue.lock").exists()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1 1")
        self.assertEqual(result.stderr.count("declared_read_missing"), 2)
        self.assertFalse(lock_exists)

    def test_engaged_invalid_vocabulary_blocks_queue_mutators_before_writes(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(
                source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
                overrides={"docs/_meta/plan_vocab.json": "{not-valid-json\n"},
            )
            result = self._run_candidate(
                fixture,
                self._admission_prelude()
                + "import plan_queue\n"
                + "context = authority.resolve_top_level_context()\n"
                + "paths = plan_queue.queue_paths(context.project_root, context=context)\n"
                + "for action in (\n"
                + "    lambda: plan_queue.append_log(paths, 'fixture'),\n"
                + "    lambda: plan_queue.save_state(paths, {'version': 1}),\n"
                + "):\n"
                + "    try:\n"
                + "        action()\n"
                + "    except plan_queue.QueueError as error:\n"
                + "        print(str(error))\n"
                + "    else:\n"
                + "        raise SystemExit('queue mutator accepted invalid vocabulary')\n",
            )
            queue_files = [
                fixture.target_root / name
                for name in (".planveyor.planqueue.lock", ".planveyor.planqueue.log", ".planveyor.planqueue.json")
            ]

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["contract_authority_invalid_plan_vocab"] * 2)
        self.assertTrue(all(not path.exists() for path in queue_files))

    def test_engaged_oracle_invalid_vocabulary_does_not_use_legacy_empty_fallback(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(
                source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
                overrides={"docs/_meta/plan_vocab.json": "{not-valid-json\n"},
            )
            result = self._run_candidate(
                fixture,
                self._admission_prelude()
                + "import plan_status_oracle\n"
                + "context = authority.resolve_top_level_context()\n"
                + "try:\n"
                + "    plan_status_oracle._planning_contour_vocab(context.project_root, context=context)\n"
                + "except ValueError as error:\n"
                + "    print(type(error).__name__)\n"
                + "else:\n"
                + "    raise SystemExit('oracle accepted invalid vocabulary fallback')\n",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "JSONDecodeError")

    def test_engaged_visual_lane_rejects_wrong_behavior_profile_before_na(self) -> None:
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            result = self._run_candidate(
                fixture,
                self._admission_prelude()
                + "import review_visual_lane_contract as lane\n"
                + "context = authority.resolve_top_level_context()\n"
                + "try:\n"
                + "    lane.discover_review_visual_lane(\n"
                + "        project_root=context.project_root, profile_id='default',\n"
                + "        changed_entries=[], exclude_docs=True, review_basename='review',\n"
                + "        plan_ref='docs/plans/example.md', context=context,\n"
                + "    )\n"
                + "except authority.ContractAuthorityError as error:\n"
                + "    print(error.reason_code)\n"
                + "else:\n"
                + "    raise SystemExit('wrong profile was accepted')\n",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "behavior_identity_mismatch")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for the committed portability substitution module.

The substitution rules (owner-local path prefixes → portable forms) previously
lived only in a gitignored `.tmp/portability_substitution.py` scratch script and
in the inline `COMMAND_PORTABILITY_SUBSTITUTIONS` table of
`post_merge_operational_receipt.py`. This module provides the first committed,
tested source of truth for the canonical substitution contract documented in
`docs/playbooks/portability_substitution_rules.md`.

These tests enforce: per-family coverage, prefix-collision safety (longest-prefix
first, primary `sample` last with trailing boundary), short-form miniforge
handling, version-pinned-receipt carve-out, and idempotency.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import portability_substitution as ps


# Synthetic owner-home path used only by these explicitly selected fixture rules.
_OWNER = "/" + "Users/" + "fixture-user"
_FIXTURE_RULES = ps.PortabilityRules(
    literal_rules=(
        (_OWNER + "/sample_tools", "${SOURCE_ROOT:-$HOME/sample_tools}"),
        (_OWNER + "/sample.worktrees", "${CONSUMER_WORKTREES_ROOT:-$HOME/sample.worktrees}"),
        (_OWNER + "/peer-one", "${PEER_ONE_ROOT:-$HOME/peer-one}"),
        (_OWNER + "/peer-two", "${PEER_TWO_ROOT:-$HOME/peer-two}"),
        (_OWNER + "/peer-three", "${PEER_THREE_ROOT:-$HOME/peer-three}"),
        (_OWNER + "/sample_front", "${CONSUMER_FRONT_ROOT:-$HOME/sample_front}"),
        *((_OWNER + "/" + item, "$HOME/" + item)
          for item in (".provider-state", ".codex", "Downloads", "Documents", "Library", ".local")),
    ), miniforge_replacement="python3", homebrew_source="/opt/homebrew/bin/python",
    homebrew_replacement="python3", primary_product_source=_OWNER + "/sample",
    primary_product_replacement="${CONSUMER_PRODUCT_ROOT:-$HOME/sample}",
    preserve_version_pinned_receipt=True,
)


def _selected_portabilize(text: str, *, is_version_pinned: bool = False) -> str:
    return ps.portabilize_text(text, rules=_FIXTURE_RULES, is_version_pinned=is_version_pinned)


class MiniforgeSubstitutionTests(unittest.TestCase):
    """The dominant contamination family: owner-local miniforge3 python interpreter."""

    def test_long_form_envs_sample_interpreter_replaced_by_python3(self) -> None:
        text = f"Run `{_OWNER}/miniforge3/envs/sample/bin/python -B scripts/foo.py`."
        self.assertEqual(
            _selected_portabilize(text),
            "Run `python3 -B scripts/foo.py`.",
        )

    def test_short_form_miniforge_bin_python_replaced(self) -> None:
        # The reference impl in post_merge_operational_receipt.py only matches the
        # /envs/<env>/bin/python long form; the corpus sweep was patched (ffff6666)
        # to also cover the short form. The committed module must cover both.
        text = f"exec {_OWNER}/miniforge3/bin/python -m pip check"
        self.assertEqual(
            _selected_portabilize(text),
            "exec python3 -m pip check",
        )

    def test_miniforge_python3_minor_version_variant_collapses_to_python3(self) -> None:
        # Canonical contract (playbook line 20): always bare ``python3``; the
        # minor version belongs to the PATH bootstrap resolver, not the text.
        text = f"{_OWNER}/miniforge3/envs/sample/bin/python3.12 --version"
        self.assertEqual(_selected_portabilize(text), "python3 --version")

    def test_miniforge_python3_plain_variant_replaced(self) -> None:
        text = f"{_OWNER}/miniforge3/envs/sample/bin/python3 --version"
        self.assertEqual(_selected_portabilize(text), "python3 --version")

    def test_miniforge_in_shell_parameter_assignment_replaced(self) -> None:
        # ${VAR:-default} shell form: the default is the owner-local interpreter.
        interp = _OWNER + "/miniforge3/envs/sample/bin/python"
        text = "PYBIN=${PYBIN:-" + interp + "} make test"
        self.assertEqual(
            _selected_portabilize(text),
            "PYBIN=${PYBIN:-python3} make test",
        )


class RepoPrefixSubstitutionTests(unittest.TestCase):
    """Owner-local repo-root path families → ${CONSUMER_*:-$HOME/...} env-var forms."""

    def test_sample_tools_root(self) -> None:
        text = f"source {_OWNER}/sample_tools/scripts/sample.zsh"
        self.assertIn("${SOURCE_ROOT:-$HOME/sample_tools}", _selected_portabilize(text))
        self.assertNotIn(_OWNER, _selected_portabilize(text))

    def test_peer_one_root(self) -> None:
        text = f"cd {_OWNER}/peer-one && make install"
        self.assertIn("${PEER_ONE_ROOT:-$HOME/peer-one}", _selected_portabilize(text))
        self.assertNotIn(_OWNER, _selected_portabilize(text))

    def test_peer_two_root(self) -> None:
        text = f"open {_OWNER}/peer-two/README.md"
        self.assertIn("${PEER_TWO_ROOT:-$HOME/peer-two}", _selected_portabilize(text))

    def test_peer_three_root(self) -> None:
        """An explicitly selected peer rule also handles nested workspaces."""
        text = f"workspace {_OWNER}/peer-three/workspace"
        self.assertIn("${PEER_THREE_ROOT:-$HOME/peer-three}", _selected_portabilize(text))
        self.assertNotIn(_OWNER, _selected_portabilize(text))

    def test_sample_front_root(self) -> None:
        text = f"npm --prefix {_OWNER}/sample_front install"
        self.assertIn("${CONSUMER_FRONT_ROOT:-$HOME/sample_front}", _selected_portabilize(text))

    def test_sample_worktrees_root(self) -> None:
        text = f"git -C {_OWNER}/sample.worktrees/main status"
        self.assertIn("${CONSUMER_WORKTREES_ROOT:-$HOME/sample.worktrees}", _selected_portabilize(text))

    def test_primary_sample_root(self) -> None:
        text = f"scripts live under {_OWNER}/sample/scripts/"
        out = _selected_portabilize(text)
        self.assertIn("${CONSUMER_PRODUCT_ROOT:-$HOME/sample}", out)
        self.assertNotIn(_OWNER, out)


class PrefixCollisionTests(unittest.TestCase):
    """Critical invariant: primary ``sample`` must not shadow longer siblings.

    The owner-home + ``/sample`` path is a literal prefix of ``sample_tools``,
    ``sample_front``, and ``sample.worktrees``. The substitution MUST apply the
    longer siblings first and the bare ``sample`` last (with a trailing-boundary
    guard), so that a ``sample_tools`` reference does not get mangled into a
    primary-sample substitution.
    """

    def test_sample_tools_not_collapsed_into_primary_sample(self) -> None:
        text = f"{_OWNER}/sample_tools/scripts/foo.py"
        out = _selected_portabilize(text)
        # Must produce the tooling-root form, NOT the primary sample form.
        self.assertIn("${SOURCE_ROOT:-$HOME/sample_tools}", out)
        self.assertNotIn("${CONSUMER_PRODUCT_ROOT:-$HOME/sample}/_tooling", out)
        self.assertNotIn("${CONSUMER_PRODUCT_ROOT:-$HOME/sample_tools", out)

    def test_primary_sample_does_not_match_sample_tools_via_boundary(self) -> None:
        # The primary-sample rule must NOT match when the next char is `_`.
        text = f"path={_OWNER}/sample_tools"
        out = _selected_portabilize(text)
        self.assertIn("${SOURCE_ROOT:-$HOME/sample_tools}", out)

    def test_primary_sample_does_not_match_sample_dot_worktrees(self) -> None:
        text = f"root={_OWNER}/sample.worktrees/x"
        out = _selected_portabilize(text)
        self.assertIn("${CONSUMER_WORKTREES_ROOT:-$HOME/sample.worktrees}", out)

    def test_multiple_primary_sample_occurrences_on_one_line_all_replaced(self) -> None:
        # Regression: a greedy rest-capture in the primary-sample regex caused only
        # the FIRST occurrence on a line to substitute, leaving the rest dirty.
        # Multiple occurrences must all be replaced (re.sub is global by default
        # once the regex matches only the prefix, not a greedy tail).
        text = (
            f"{_OWNER}/sample/docs/a.md {_OWNER}/sample/docs/b.md {_OWNER}/sample end"
        )
        out = _selected_portabilize(text)
        self.assertEqual(out.count("${CONSUMER_PRODUCT_ROOT:-$HOME/sample}"), 3)
        self.assertNotIn(_OWNER, out)

    def test_multiple_families_in_one_line_all_replaced(self) -> None:
        text = (
            f"{_OWNER}/miniforge3/envs/sample/bin/python "
            f"{_OWNER}/sample_tools/x.py "
            f"{_OWNER}/sample/y.py"
        )
        out = _selected_portabilize(text)
        self.assertNotIn(_OWNER, out)
        self.assertIn("python3", out)
        self.assertIn("${SOURCE_ROOT:-$HOME/sample_tools}", out)
        self.assertIn("${CONSUMER_PRODUCT_ROOT:-$HOME/sample}", out)


class UserLocalStateSubstitutionTests(unittest.TestCase):
    """User-local runtime state → $HOME/... forms."""

    def test_ai_profiles(self) -> None:
        text = f"CODEX_HOME={_OWNER}/.provider-state/foo"
        self.assertIn("$HOME/.provider-state/foo", _selected_portabilize(text))

    def test_codex_dir(self) -> None:
        text = f"config at {_OWNER}/.codex/config.toml"
        self.assertIn("$HOME/.codex/config.toml", _selected_portabilize(text))

    def test_downloads_documents_library_local(self) -> None:
        for sub in ("Downloads", "Documents", "Library", ".local"):
            with self.subTest(sub=sub):
                text = f"file://{_OWNER}/{sub}/thing"
                self.assertIn(f"$HOME/{sub}/thing", _selected_portabilize(text))


class HomebrewInterpreterTests(unittest.TestCase):
    """/opt/homebrew/bin/python3 → python3."""

    def test_homebrew_python_replaced(self) -> None:
        text = "/opt/homebrew/bin/python3 -m pip install -r requirements-dev.lock"
        self.assertEqual(
            _selected_portabilize(text),
            "python3 -m pip install -r requirements-dev.lock",
        )


class VersionPinnedReceiptTests(unittest.TestCase):
    """Carve-out: receipts with `pip install --dry-run` + Python version keep the
    historical miniforge interpreter, because substituting `python3` would
    contradict the recorded exit-0 / version evidence.
    """

    def test_version_pinned_record_skips_miniforge_substitution(self) -> None:
        text = (
            f"{_OWNER}/miniforge3/envs/sample/bin/python -m pip install --dry-run "
            f"-r requirements-dev.lock  # exit 0, Python 3.12, tomli ignored"
        )
        out = _selected_portabilize(text, is_version_pinned=True)
        # The miniforge interpreter MUST be preserved verbatim on a version-pinned line.
        self.assertIn(f"{_OWNER}/miniforge3/envs/sample/bin/python", out)
        self.assertNotIn("python3 -m pip install --dry-run", out)

    def test_non_pinned_record_still_substitutes(self) -> None:
        text = f"{_OWNER}/miniforge3/envs/sample/bin/python scripts/foo.py"
        out = _selected_portabilize(text, is_version_pinned=False)
        self.assertNotIn(_OWNER, out)
        self.assertIn("python3", out)

    def test_version_pinned_detection_helper(self) -> None:
        # The module exposes a detector so the sweep driver can classify records.
        pinned = (
            f"{_OWNER}/miniforge3/envs/sample/bin/python -m pip install --dry-run "
            f"-r x.lock  # Python 3.12"
        )
        plain = f"{_OWNER}/miniforge3/envs/sample/bin/python scripts/foo.py"
        self.assertTrue(ps.is_version_pinned_record(pinned))
        self.assertFalse(ps.is_version_pinned_record(plain))

    def test_version_pinned_detector_requires_all_three_conditions(self) -> None:
        # Robustness: each of the three co-located markers is independently
        # required. Any 2-of-3 must NOT classify as version-pinned (else a plain
        # miniforge command near a dry-run/version mention would be wrongly kept).
        interp = _OWNER + "/miniforge3/envs/sample/bin/python"
        # miniforge + dry-run, NO Python version
        self.assertFalse(ps.is_version_pinned_record(interp + " -m pip install --dry-run -r x.lock"))
        # miniforge + Python version, NO dry-run
        self.assertFalse(ps.is_version_pinned_record(interp + " scripts/foo.py  # Python 3.12"))
        # dry-run + Python version, NO miniforge interpreter
        self.assertFalse(ps.is_version_pinned_record("python3 -m pip install --dry-run  # Python 3.12"))


class IdempotencyTests(unittest.TestCase):
    """Re-running the sweep on already-clean content is a no-op."""

    def test_clean_text_is_unchanged(self) -> None:
        clean = "Run `python3 -B scripts/foo.py` under ${SOURCE_ROOT:-$HOME/sample_tools}."
        self.assertEqual(_selected_portabilize(clean), clean)

    def test_double_application_is_idempotent(self) -> None:
        dirty = (
            f"{_OWNER}/miniforge3/envs/sample/bin/python "
            f"{_OWNER}/sample_tools/x.py"
        )
        once = _selected_portabilize(dirty)
        twice = _selected_portabilize(once)
        self.assertEqual(once, twice)
        self.assertNotIn(_OWNER, twice)

    def test_clean_record_with_no_owner_paths_is_identity(self) -> None:
        text = "# A plan with no owner-local paths at all.\nJust portable text.\n"
        self.assertEqual(_selected_portabilize(text), text)


class ContentProfilePolicyTests(unittest.TestCase):
    def test_generic_rules_do_not_apply_owner_specific_replacements(self) -> None:
        text = f"{_OWNER}/sample_tools/scripts/sample.zsh {_OWNER}/miniforge3/bin/python"
        rendered = ps.portabilize_text(text)
        self.assertIn(f"{_OWNER}/sample_tools/scripts/sample.zsh", rendered)
        self.assertIn("python3", rendered)
        self.assertNotIn("${SOURCE_ROOT:-$HOME/sample_tools}", rendered)
        other_user = "/" + "Users/another-fixture/miniforge3/envs/sample/bin/python"
        self.assertEqual(ps.portabilize_text(other_user), "python3")

    def test_public_profiles_do_not_load_implicit_private_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for profile in ("default", "planveyor", "target-local"):
                self.assertEqual(ps.load_portability_rules(content_profile_id=profile,
                    policy_root=Path(tmpdir)), ps.GENERIC_PORTABILITY_RULES)

    def test_unknown_profile_fails_without_fallback(self) -> None:
        with self.assertRaises(ps.PortabilityPolicyError):
            ps.load_portability_rules(content_profile_id="unknown-consumer")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression coverage for the isolated Copier consumer lifecycle."""
from __future__ import annotations

import contextlib
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent
sys.path.insert(0, os.fspath(SCRIPTS))

import consumer_contract as contract


MANAGED = "docs/playbook.md"
REMOVED = "docs/obsolete.md"
LOCAL_HEADING = contract.LOCAL_HEADINGS[0]


def _physical_tempdir() -> str:
    """Return the platform temp directory with symlinks resolved.

    Init refuses sibling paths that pass through a symlink (macOS /tmp and
    /var are links into /private), so fixtures need the physical path.
    """
    return str(Path(tempfile.gettempdir()).resolve())


def _env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def run(argv: list[str], *, cwd: Path | None = None, input_text: str | None = None,
        check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=_env() if env is None else env,
        text=True,
        input=input_text,
        capture_output=True,
        stdin=subprocess.DEVNULL if input_text is None else None,
        check=False,
        timeout=60,
    )
    if check and completed.returncode:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(argv)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def git(root: Path, *args: str, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "git",
            "-C",
            os.fspath(root),
            "-c",
            "user.name=Consumer Contract Test",
            "-c",
            "user.email=consumer-contract-test@example.invalid",
            *args,
        ],
        input_text=input_text,
        check=check,
    )


def write(path: Path, body: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def file_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    snapshot: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        snapshot[path.relative_to(root).as_posix()] = (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.st_mtime_ns,
        )
    return snapshot


def repo_state(root: Path) -> dict[str, object]:
    index = Path(
        git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").stdout.strip()
    )
    index_stat = index.stat()
    return {
        "head": git(root, "rev-parse", "HEAD").stdout.strip(),
        "branch": git(root, "branch", "--show-current").stdout.strip(),
        "status": git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout,
        "index": (hashlib.sha256(index.read_bytes()).hexdigest(), index_stat.st_mtime_ns),
        "files": file_snapshot(root),
    }


def commit_identity(root: Path) -> tuple[str, str, str, str]:
    env = _env()
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    rendered = run(
        [
            "git",
            "-C",
            os.fspath(root),
            "-c",
            "mailmap.file=/dev/null",
            "-c",
            "mailmap.blob=",
            "show",
            "-s",
            "--format=%an%x00%ae%x00%cn%x00%ce",
            "HEAD",
        ],
        env=env,
    ).stdout.rstrip("\n")
    fields = rendered.split("\0")
    if len(fields) != 4:
        raise AssertionError(f"unexpected Git identity field count: {len(fields)}")
    return fields[0], fields[1], fields[2], fields[3]


class ConsumerFixture:
    """A tiny Git source with three Copier revisions and an initialized sibling."""

    def __init__(self, *, deleted_body: str | None = None) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="consumer-contract-", dir=_physical_tempdir())
        self.root = Path(self._temporary.name)
        self.runtime = self.root / "runtime"
        self.cases = self.root / "cases"
        self.runtime.mkdir()
        self.cases.mkdir()
        self._write_runtime_a()
        if deleted_body is not None:
            write(self.runtime / "copier_template" / REMOVED, deleted_body)
        git(self.runtime, "init", "-b", "main")
        self._commit("fixture A")
        self.a = git(self.runtime, "rev-parse", "HEAD").stdout.strip()

        write(
            self.runtime / "copier_template" / MANAGED.replace(".md", ".md.jinja"),
            self._playbook("B"),
        )
        if deleted_body is not None:
            (self.runtime / "copier_template" / REMOVED).unlink()
        self._commit("fixture B")
        self.b = git(self.runtime, "rev-parse", "HEAD").stdout.strip()

        old_template = self.runtime / "copier_template" / MANAGED.replace(".md", ".md.jinja")
        renamed_template = self.runtime / "copier_template" / "docs" / "renamed_playbook.md.jinja"
        old_template.rename(renamed_template)
        self._commit("fixture C renames a managed path")
        self.c = git(self.runtime, "rev-parse", "HEAD").stdout.strip()

        self.seed = self.cases / "seed"
        result = contract.init(self.runtime, self.seed, self.a)
        if result["state"] != "ok":
            raise AssertionError(f"fixture init failed: {result}")

    @staticmethod
    def _plan_template() -> str:
        return """# Plan: <TOPIC>

**Date:** YYYY-MM-DD HH:MM
**Stage:** UNCONFIRMED (Stage 1/2/3)
**Priority:** UNCONFIRMED (P0/P1/P2)
**Status:** Architect initial draft | Ready for Coder

```json
{"plan_meta": {"cluster": "UNCONFIRMED"}}
```

## Как я понял задачу

## Problem

## Solution (high level)

## Scope

## Tests

## Commands

## Evidence (chronological, append-only)
"""

    @staticmethod
    def _playbook(version: str) -> str:
        return (
            "# Managed playbook\n"
            f"shared={version}\n"
            f"{LOCAL_HEADING}\n"
            "N/A (why=fixture source placeholder)\n"
            "## End\n"
        )

    def _write_runtime_a(self) -> None:
        write(
            self.runtime / "copier.yml",
            """_answers_file: .copier-answers.yml
_subdirectory: copier_template
_templates_suffix: .jinja

repository_id:
  type: str
""",
        )
        write(
            self.runtime / "copier_template" / "{{ _copier_conf.answers_file }}.jinja",
            "{{ _copier_answers | to_nice_yaml }}\n",
        )
        write(
            self.runtime / "copier_template" / "docs" / "_meta" / "planveyor_contract_authority.v1.json.jinja",
            """{
  "schema_version": 3,
  "repository_id": "{{ repository_id }}",
  "authority_mode": "target-local",
  "contract_root": ".",
  "required_runtime_api": {"minimum": 5, "maximum": 5},
  "source_commit": "{{ _copier_conf.vcs_ref_hash }}"
}
""",
        )
        write(
            self.runtime / "copier_template" / "docs" / "plans" / "_template.md.jinja",
            self._plan_template(),
        )
        write(
            self.runtime / "copier_template" / MANAGED.replace(".md", ".md.jinja"),
            self._playbook("A"),
        )
        write(
            self.runtime / "bin" / "planveyor",
            """#!/bin/sh
if [ "${PLANVEYOR_TEST_LINT_FAIL:-}" = "1" ]; then
  echo "forced fixture lint failure" >&2
  exit 13
fi
exit 0
""",
            executable=True,
        )

    def _commit(self, message: str) -> None:
        git(self.runtime, "add", "--all")
        git(self.runtime, "commit", "--quiet", "-m", message)

    def clone_seed(self, name: str) -> Path:
        target = self.cases / name
        shutil.copytree(self.seed, target, symlinks=True)
        return target

    def commit_target(self, target: Path, message: str) -> None:
        git(target, "add", "--all")
        git(target, "commit", "--quiet", "-m", message)

    def candidate(self, target: Path, selected: str) -> Path:
        return target.parent / f".{target.name}-upgrade-{selected[:12]}"

    def backup(self, target: Path, selected: str) -> Path:
        return target.parent / f".{target.name}-before-{selected[:12]}"

    def unrelated_commit(self) -> str:
        tree = git(self.runtime, "mktree", input_text="").stdout.strip()
        return git(self.runtime, "commit-tree", tree, input_text="unrelated fixture\n").stdout.strip()

    def close(self) -> None:
        shutil.rmtree(contract.copier_cache_home(self.runtime), ignore_errors=True)
        self._temporary.cleanup()


class ConsumerContractDiagnosticsTests(unittest.TestCase):
    def test_bootstrap_hint_points_to_the_activated_environment(self) -> None:
        hint = contract.bootstrap_hint(Path("/runtime root"))
        self.assertIn("Activate the Planveyor environment", hint)
        self.assertIn("Python 3.12", hint)
        self.assertIn(f"Copier {contract.COPIER_VERSION}", hint)
        self.assertIn("PyYAML", hint)
        self.assertIn("'/runtime root/requirements-dev.lock'", hint)
        self.assertIn(sys.executable, hint)
        self.assertNotIn("pip", hint)
        self.assertNotIn("install -r", hint)

    def test_symlinked_target_error_names_the_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-target-path-") as tmpdir:
            root = Path(tmpdir).resolve()
            physical = root / "physical"
            physical.mkdir()
            alias = root / "alias"
            alias.symlink_to(physical, target_is_directory=True)
            requested = alias / "sibling"
            with self.assertRaises(contract.ContractError) as rejected:
                contract.canonical_external(os.fspath(requested), REPO_ROOT, must_exist=False)
            message = str(rejected.exception)
            self.assertIn("canonical physical path without symlinks", message)
            self.assertIn(f"{requested} resolves to {physical / 'sibling'}", message)
            self.assertIn("/private/tmp/...", message)

            self.assertEqual(
                contract.canonical_external(os.fspath(physical / "sibling"), REPO_ROOT, must_exist=False),
                physical / "sibling",
            )
        with self.assertRaisesRegex(contract.ContractError, "outside the Planveyor runtime"):
            contract.canonical_external(os.fspath(REPO_ROOT / "nested-sibling"), REPO_ROOT, must_exist=False)

    def test_main_init_reports_the_fallback_author_on_stderr(self) -> None:
        note = (
            f"note: init commit author is {contract.INIT_AUTHOR_NAME} <{contract.INIT_AUTHOR_EMAIL}>; "
            "pass --author-name and --author-email together to sign it with your own identity."
        )
        with tempfile.TemporaryDirectory(prefix="consumer-init-note-") as tmpdir:
            target = Path(tmpdir).resolve() / "sibling"
            base = ["--runtime-root", os.fspath(REPO_ROOT), "init", os.fspath(target), "--source-commit", "a" * 40]
            cases = (
                ("fallback", [], [note]),
                ("explicit", ["--author-name", "Fixture Owner", "--author-email", "owner@example.invalid"], []),
            )
            for label, flags, expected in cases:
                with self.subTest(label):
                    output = io.StringIO()
                    errors = io.StringIO()
                    with mock.patch.object(contract, "init", return_value={"state": "ok"}) as init_call:
                        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                            returncode = contract.main([*base, *flags])
                    self.assertEqual(returncode, 0, errors.getvalue())
                    init_call.assert_called_once()
                    self.assertEqual(json.loads(output.getvalue()), {"state": "ok"})
                    self.assertEqual(errors.getvalue().splitlines(), expected)

    def test_copier_cache_is_separate_for_each_runtime_root(self) -> None:
        first = contract.process_env(Path("/runtime/first"), copier=True)["XDG_CACHE_HOME"]
        repeated = contract.process_env(Path("/runtime/first"), copier=True)["XDG_CACHE_HOME"]
        second = contract.process_env(Path("/runtime/second"), copier=True)["XDG_CACHE_HOME"]

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, second)
        for cache in (first, second):
            self.assertEqual(Path(cache).parent, Path(tempfile.gettempdir()))
            self.assertRegex(Path(cache).name, r"\Aplanveyor-copier-cache-[0-9a-f]{12}\Z")
        self.assertEqual(Path(first), contract.copier_cache_home(Path("/runtime/first")))


class ConsumerContractInitIdentityTests(unittest.TestCase):
    OWNER_NAME = "fixture-owner"
    OWNER_EMAIL = "fixture-owner+tag@example.invalid"

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = ConsumerFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def assert_identity(self, target: Path, name: str, email: str) -> None:
        self.assertEqual(commit_identity(target), (name, email, name, email))
        config = (target / ".git" / "config").read_text(encoding="utf-8")
        self.assertNotIn("[user]", config)
        self.assertNotIn("[author]", config)
        self.assertNotIn("[committer]", config)

    def test_explicit_saved_identity_is_local_and_survives_atomic_init_publish(self) -> None:
        target = self.fixture.cases / "saved-human-identity"
        result = contract.init(self.fixture.runtime, target, self.fixture.a,
                               author_name=self.OWNER_NAME, author_email=self.OWNER_EMAIL,
                               save_identity=True)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(commit_identity(target), (self.OWNER_NAME, self.OWNER_EMAIL, self.OWNER_NAME, self.OWNER_EMAIL))
        for key, expected in (("user.name", self.OWNER_NAME), ("user.email", self.OWNER_EMAIL)):
            actual = contract.git(target, "config", "--local", "--get", key).stdout.strip()
            self.assertEqual(actual, expected)
        self.assertEqual(contract.git(target, "status", "--porcelain=v1").stdout, "")

    def test_saved_identity_cannot_use_default_placeholder_before_candidate_effects(self) -> None:
        target = self.fixture.cases / "saved-placeholder-refused"
        with self.assertRaisesRegex(contract.ContractError, "explicit author"):
            contract.init(self.fixture.runtime, target, self.fixture.a, save_identity=True)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(f".{target.name}-init-*")), [])

    def test_direct_api_default_owner_and_current_git_allowed_identity(self) -> None:
        fixture = self.fixture
        owner_target = fixture.cases / "owner-identity"
        self.assertEqual(
            contract.init(
                fixture.runtime,
                owner_target,
                fixture.a,
                author_name=self.OWNER_NAME,
                author_email=self.OWNER_EMAIL,
            )["state"],
            "ok",
        )
        self.assert_identity(owner_target, self.OWNER_NAME, self.OWNER_EMAIL)
        self.assertEqual(
            contract.doctor(owner_target, fixture.runtime, exact_runtime=False, expected=fixture.a)["state"],
            "ok",
        )

        fallback_target = fixture.cases / "fallback-identity"
        self.assertEqual(contract.init(fixture.runtime, fallback_target, fixture.a)["state"], "ok")
        self.assert_identity(fallback_target, contract.INIT_AUTHOR_NAME, contract.INIT_AUTHOR_EMAIL)

        allowed_target = fixture.cases / "git255-allowed-identity"
        allowed_name = '.Жанна "Q" O\'Connor\\team'
        allowed_email = ".identity@example.invalid"
        self.assertEqual(
            contract.init(
                fixture.runtime,
                allowed_target,
                fixture.a,
                author_name=allowed_name,
                author_email=allowed_email,
            )["state"],
            "ok",
        )
        self.assert_identity(allowed_target, allowed_name, allowed_email)

    def test_invalid_identity_fails_before_dependencies_or_candidate(self) -> None:
        fixture = self.fixture
        self.invalid_counter = 0
        valid_name = "Valid Name"
        valid_email = "valid@example.invalid"

        def reject(author_name: object | None, author_email: object | None) -> None:
            self.invalid_counter += 1
            target = fixture.cases / f"invalid-identity-{self.invalid_counter}"
            with mock.patch.object(
                contract,
                "require_consumer_dependencies",
                side_effect=AssertionError("dependency check must not run for invalid identity"),
            ) as dependency_check:
                with self.assertRaises(contract.ContractError) as rejected:
                    contract.init(  # type: ignore[arg-type]
                        fixture.runtime,
                        target,
                        fixture.a,
                        author_name=author_name,
                        author_email=author_email,
                    )
            dependency_check.assert_not_called()
            self.assertFalse(target.exists())
            self.assertFalse(list(target.parent.glob(f".{target.name}-init-*")))
            self.assertNotIn("do-not-echo", str(rejected.exception))

        with self.subTest("missing-author-email"):
            reject(valid_name, None)
        with self.subTest("missing-author-name"):
            reject(None, valid_email)

        invalid_values: tuple[object, ...] = (
            "",
            " ",
            "\x01",
            "\x7f",
            "\x85",
            "line\u2028separator",
            "line\u2029separator",
            "\ud800",
            " do-not-echo",
            "do-not-echo ",
            "<do-not-echo",
            "do-not-echo>",
            7,
            True,
            {},
            [],
        )
        for field in ("author_name", "author_email"):
            for value in invalid_values:
                with self.subTest(field=field, value=repr(value)):
                    reject(value if field == "author_name" else valid_name,
                           value if field == "author_email" else valid_email)

        with self.subTest("email-whitespace"):
            reject(valid_name, "valid name@example.invalid")

        for field in ("author_name", "author_email"):
            baseline = valid_name if field == "author_name" else valid_email
            other = valid_email if field == "author_name" else valid_name
            for edge in contract.INIT_IDENTITY_EDGE_CHARACTERS:
                for value in (edge + baseline, baseline + edge):
                    with self.subTest(field=field, edge=repr(edge), value=repr(value)):
                        reject(value if field == "author_name" else other,
                               value if field == "author_email" else other)

    def test_external_identity_sentinels_cannot_change_direct_api_or_main(self) -> None:
        fixture = self.fixture
        source_before = repo_state(fixture.runtime)
        with tempfile.TemporaryDirectory(prefix="consumer-identity-sentinel-", dir=_physical_tempdir()) as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            xdg = root / "xdg"
            global_config = root / "sentinel.gitconfig"
            config_body = (
                "[author]\n"
                "\tname = Sentinel Author\n"
                "\temail = sentinel-author@example.invalid\n"
                "[committer]\n"
                "\tname = Sentinel Committer\n"
                "\temail = sentinel-committer@example.invalid\n"
            )
            home.mkdir()
            (xdg / "git").mkdir(parents=True)
            (home / ".gitconfig").write_text(config_body, encoding="utf-8")
            (xdg / "git" / "config").write_text(config_body, encoding="utf-8")
            global_config.write_text(config_body, encoding="utf-8")
            sentinel_paths = (home / ".gitconfig", xdg / "git" / "config", global_config)
            sentinel_before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in sentinel_paths]

            unsafe_env = _env()
            unsafe_env.update(
                HOME=os.fspath(home),
                XDG_CONFIG_HOME=os.fspath(xdg),
                GIT_CONFIG_GLOBAL=os.fspath(global_config),
                GIT_CONFIG_NOSYSTEM="1",
            )
            ordinary = root / "ordinary-git-control"
            run(["git", "init", "--quiet", "-b", "main", os.fspath(ordinary)], env=unsafe_env)
            write(ordinary / "tracked.txt", "ordinary control\n")
            run(["git", "-C", os.fspath(ordinary), "add", "tracked.txt"], env=unsafe_env)
            run(["git", "-C", os.fspath(ordinary), "commit", "--quiet", "-m", "ordinary control"], env=unsafe_env)
            self.assertEqual(
                commit_identity(ordinary),
                (
                    "Sentinel Author",
                    "sentinel-author@example.invalid",
                    "Sentinel Committer",
                    "sentinel-committer@example.invalid",
                ),
            )

            external = {
                "HOME": os.fspath(home),
                "XDG_CONFIG_HOME": os.fspath(xdg),
                "GIT_CONFIG_GLOBAL": os.fspath(global_config),
                "GIT_AUTHOR_NAME": "Environment Author",
                "GIT_AUTHOR_EMAIL": "environment-author@example.invalid",
                "GIT_COMMITTER_NAME": "Environment Committer",
                "GIT_COMMITTER_EMAIL": "environment-committer@example.invalid",
                "GIT_CONFIG_PARAMETERS": "'user.name=Parameter Sentinel'",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "author.name",
                "GIT_CONFIG_VALUE_0": "Count Sentinel",
                "EMAIL": "email-sentinel@example.invalid",
            }
            with mock.patch.dict(os.environ, external, clear=False):
                clean_env = contract.process_env(fixture.runtime)
                self.assertEqual(clean_env["GIT_CONFIG_GLOBAL"], os.devnull)
                self.assertEqual(clean_env["GIT_CONFIG_NOSYSTEM"], "1")
                for key in external:
                    if key.startswith("GIT_") and key not in {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"}:
                        self.assertNotIn(key, clean_env)

                selected_target = fixture.cases / "sentinel-selected"
                self.assertEqual(
                    contract.init(
                        fixture.runtime,
                        selected_target,
                        fixture.a,
                        author_name=self.OWNER_NAME,
                        author_email=self.OWNER_EMAIL,
                    )["state"],
                    "ok",
                )

                fallback_target = fixture.cases / "sentinel-main-fallback"
                output = io.StringIO()
                errors = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    returncode = contract.main(
                        [
                            "--runtime-root",
                            os.fspath(fixture.runtime),
                            "init",
                            os.fspath(fallback_target),
                            "--source-commit",
                            fixture.a,
                        ]
                    )
                self.assertEqual(returncode, 0, errors.getvalue())
                self.assertEqual(json.loads(output.getvalue())["state"], "ok")
                self.assertIn(
                    f"note: init commit author is {contract.INIT_AUTHOR_NAME} <{contract.INIT_AUTHOR_EMAIL}>",
                    errors.getvalue(),
                )

            self.assert_identity(selected_target, self.OWNER_NAME, self.OWNER_EMAIL)
            self.assert_identity(fallback_target, contract.INIT_AUTHOR_NAME, contract.INIT_AUTHOR_EMAIL)
            self.assertEqual(repo_state(fixture.runtime), source_before)
            self.assertEqual(
                [(path.read_bytes(), path.stat().st_mtime_ns) for path in sentinel_paths],
                sentinel_before,
            )

    def test_dirty_target_with_valid_identity_is_preserved_without_candidate(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("dirty-identity-target")
        (target / MANAGED).write_text("dirty tracked file\n", encoding="utf-8")
        write(target / "untracked.txt", "dirty untracked file\n")
        before = repo_state(target)
        with self.assertRaisesRegex(contract.ContractError, "existing nonempty target is preserved"):
            contract.init(
                fixture.runtime,
                target,
                fixture.a,
                author_name=self.OWNER_NAME,
                author_email=self.OWNER_EMAIL,
            )
        self.assertEqual(repo_state(target), before)
        self.assertFalse(list(target.parent.glob(f".{target.name}-init-*")))


class ConsumerContractNoticeTests(unittest.TestCase):
    @staticmethod
    def valid_notice(**extra: object) -> dict[str, object]:
        notice: dict[str, object] = {
            "summary": "Проверено извещение контракта.",
            "contract_changes": ["docs/playbooks/docs_architecture.md"],
            "engine_changes": ["scripts/consumer_contract.py"],
            "sibling_actions": ["Проверить локальный план адаптации."],
            "checks": ["Запустить consumer doctor."],
        }
        notice.update(extra)
        return notice

    @staticmethod
    def commit_notice(fixture: ConsumerFixture, relative: str, body: str, message: str) -> str:
        write(fixture.runtime / relative, body)
        fixture._commit(message)
        return git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()

    def test_validate_notice_requires_five_clean_fields_and_every_array_item(self) -> None:
        valid = self.valid_notice(
            summary="Русский summary без переноса",
            contract_changes=["docs/playbooks/docs_architecture.md"],
            engine_changes=[],
            sibling_actions=[],
            checks=[],
        )
        self.assertEqual(contract.validate_notice(valid, "fixture"), valid)

        for field in contract.NOTICE_FIELDS:
            missing = dict(valid)
            del missing[field]
            with self.subTest(missing=field):
                with self.assertRaisesRegex(contract.ContractError, "invalid notice schema: fixture"):
                    contract.validate_notice(missing, "fixture")

        for field in contract.NOTICE_FIELDS:
            wrong_type = dict(valid)
            wrong_type[field] = [] if field == "summary" else "not an array"
            with self.subTest(wrong_type=field):
                with self.assertRaisesRegex(contract.ContractError, "invalid notice schema: fixture"):
                    contract.validate_notice(wrong_type, "fixture")

        for invalid in ("", " \t", "first\nsecond", "control\x01", "control\x7f", "line\u2028break", "line\u2029break", "\ud800", 7, True, None, [], {}):
            malformed = self.valid_notice(summary=invalid)
            with self.subTest(summary=repr(invalid)):
                with self.assertRaisesRegex(contract.ContractError, "invalid notice schema: fixture"):
                    contract.validate_notice(malformed, "fixture")

        invalid_items: tuple[object, ...] = (7, True, None, {}, [], ["nested"], "", " \t", "first\nsecond", "control\x01", "control\x7f", "line\u2028break", "line\u2029break", "\ud800")
        for field in contract.NOTICE_FIELDS[1:]:
            for invalid in invalid_items:
                malformed = self.valid_notice(**{field: [invalid]})
                with self.subTest(field=field, item=repr(invalid)):
                    with self.assertRaisesRegex(contract.ContractError, "invalid notice schema: fixture"):
                        contract.validate_notice(malformed, "fixture")

    def test_current_notice_history_and_strict_notice_are_valid(self) -> None:
        base = git(REPO_ROOT, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        current = git(REPO_ROOT, "rev-parse", "HEAD").stdout.strip()
        history = contract.notices(REPO_ROOT, base, current)
        for notice in history:
            self.assertEqual(
                contract.validate_notice(notice, f"{notice['path']}@{notice['commit']}"),
                notice,
            )

        for notice_path in sorted((REPO_ROOT / "docs" / "contract_notices").glob("*.json")):
            current_notice = json.loads(notice_path.read_text(encoding="utf-8"))
            self.assertEqual(
                contract.validate_notice(current_notice, os.fspath(notice_path)),
                current_notice,
            )

    def test_notice_history_reads_only_the_selected_synthetic_range(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-notice-range-") as tmpdir:
            source = Path(tmpdir).resolve() / "source"
            run(["git", "init", "--quiet", "-b", "main", os.fspath(source)])

            def commit(message: str) -> str:
                git(source, "add", "--all")
                git(source, "commit", "--quiet", "--allow-empty", "-m", message)
                return git(source, "rev-parse", "HEAD").stdout.strip()

            empty = commit("empty tree")
            self.assertEqual(git(source, "ls-tree", "-r", "--name-only", empty).stdout, "")
            notice_path = "docs/contract_notices/synthetic-change.json"
            notice = self.valid_notice()
            write(source / notice_path, json.dumps(notice, ensure_ascii=False) + "\n")
            write(source / "docs/contract_notices/README.md", "Format notes are not a notice.\n")
            added = commit("add synthetic notice")

            history = contract.notices(source, empty, added)
            self.assertEqual(history, [{**notice, "commit": added, "path": notice_path}])

            write(source / "unrelated.txt", "unrelated change\n")
            later = commit("unrelated change")
            # A notice already contained in the sibling's old source commit is not shown again.
            self.assertEqual(contract.notices(source, added, later), [])
            self.assertEqual(len(contract.notices(source, empty, later)), 1)

    @staticmethod
    def notice_source(root: Path) -> Path:
        source = root.resolve() / "source"
        run(["git", "init", "--quiet", "-b", "main", os.fspath(source)])
        return source

    @staticmethod
    def commit_all(source: Path, message: str) -> str:
        git(source, "add", "--all")
        git(source, "commit", "--quiet", "--allow-empty", "-m", message)
        return git(source, "rev-parse", "HEAD").stdout.strip()

    def test_merging_an_older_branch_does_not_repeat_a_delivered_notice(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-notice-older-branch-") as tmpdir:
            source = self.notice_source(Path(tmpdir))
            write(source / "README.md", "base\n")
            base = self.commit_all(source, "base")
            git(source, "checkout", "--quiet", "-b", "candidate")
            write(source / "candidate.txt", "candidate\n")
            candidate = self.commit_all(source, "candidate forks before the notice")
            git(source, "checkout", "--quiet", "main")
            notice_path = "docs/contract_notices/main-notice.json"
            notice = self.valid_notice(summary="Извещение на main после ответвления кандидата.")
            write(source / notice_path, json.dumps(notice, ensure_ascii=False) + "\n")
            delivered = self.commit_all(source, "add the notice on main")
            git(source, "merge", "--quiet", "--no-ff", "--no-edit", "-m", "merge the candidate", "candidate")
            merged = git(source, "rev-parse", "HEAD").stdout.strip()

            # The old source commit already delivered the notice; the merged branch lacks it.
            self.assertEqual(contract.notices(source, delivered, merged), [])
            # From before the notice, on main or on the candidate, it arrives once with its main commit.
            expected = [{**notice, "commit": delivered, "path": notice_path}]
            self.assertEqual(contract.notices(source, base, merged), expected)
            self.assertEqual(contract.notices(source, candidate, merged), expected)

    def test_notice_from_a_merged_branch_arrives_once_with_the_merge(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-notice-merged-branch-") as tmpdir:
            source = self.notice_source(Path(tmpdir))
            write(source / "README.md", "base\n")
            base = self.commit_all(source, "base")
            git(source, "checkout", "--quiet", "-b", "candidate")
            notice_path = "docs/contract_notices/candidate-notice.json"
            notice = self.valid_notice(summary="Извещение пришло из ветки кандидата.")
            write(source / notice_path, json.dumps(notice, ensure_ascii=False) + "\n")
            added = self.commit_all(source, "add the notice on the candidate")
            git(source, "checkout", "--quiet", "main")
            write(source / "main.txt", "main\n")
            main_change = self.commit_all(source, "main change")
            git(source, "merge", "--quiet", "--no-ff", "--no-edit", "-m", "merge the candidate", "candidate")
            merged = git(source, "rev-parse", "HEAD").stdout.strip()

            # The first-parent line receives the notice with the merge, once.
            expected = [{**notice, "commit": merged, "path": notice_path}]
            self.assertEqual(contract.notices(source, base, merged), expected)
            self.assertEqual(contract.notices(source, main_change, merged), expected)
            # A sibling already upgraded to the candidate commit has the notice.
            self.assertEqual(contract.notices(source, added, merged), [])

    def test_edited_notice_arrives_once_with_its_latest_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-notice-edited-") as tmpdir:
            source = self.notice_source(Path(tmpdir))
            write(source / "README.md", "base\n")
            base = self.commit_all(source, "base")
            notice_path = "docs/contract_notices/edited-notice.json"
            first = self.valid_notice(summary="Первая редакция извещения.")
            write(source / notice_path, json.dumps(first, ensure_ascii=False) + "\n")
            added = self.commit_all(source, "add the notice")
            second = self.valid_notice(summary="Вторая редакция извещения.")
            write(source / notice_path, json.dumps(second, ensure_ascii=False) + "\n")
            edited = self.commit_all(source, "edit the notice")

            expected = [{**second, "commit": edited, "path": notice_path}]
            self.assertEqual(contract.notices(source, base, edited), expected)
            # A sibling that already received the first text gets the edited notice again.
            self.assertEqual(contract.notices(source, added, edited), expected)

    def test_notice_kept_by_a_merge_off_the_first_parent_line_is_delivered(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-notice-kept-by-merge-") as tmpdir:
            source = self.notice_source(Path(tmpdir))
            notice_path = "docs/contract_notices/kept-notice.json"
            notice = self.valid_notice(summary="Извещение осталось на линии первых родителей.")
            write(source / notice_path, json.dumps(notice, ensure_ascii=False) + "\n")
            self.commit_all(source, "base with the notice")
            git(source, "checkout", "--quiet", "-b", "line")
            write(source / "line.txt", "line\n")
            self.commit_all(source, "line change")
            git(source, "checkout", "--quiet", "main")
            (source / notice_path).unlink()
            old = self.commit_all(source, "delete the notice on main")
            git(source, "checkout", "--quiet", "line")
            # The old commit becomes a second parent; the merge keeps the line tree and the notice.
            git(source, "merge", "--quiet", "--no-edit", "-s", "ours", "-m", "merge main keeping the line", "main")
            merged = git(source, "rev-parse", "HEAD").stdout.strip()

            self.assertEqual(
                contract.notices(source, old, merged),
                [{**notice, "commit": merged, "path": notice_path}],
            )

    def test_notices_fail_closed_on_malformed_name_status(self) -> None:
        malformed = subprocess.CompletedProcess(["git"], 0, "a" * 40 + "\0\nAA\0", "")
        with mock.patch.object(contract, "git", return_value=malformed):
            with self.assertRaisesRegex(contract.ContractError, "cannot parse notice history entry"):
                contract.notices(REPO_ROOT, "a" * 40, "b" * 40)

    def test_notices_keep_valid_deleted_history_and_refuse_corrupt_history(self) -> None:
        fixture = ConsumerFixture()
        try:
            baseline = fixture.c
            valid_path = "docs/contract_notices/valid-then-deleted.json"
            added = self.commit_notice(
                fixture,
                valid_path,
                json.dumps(self.valid_notice(commit="forged", path="forged", context="kept"), ensure_ascii=False) + "\n",
                "add valid notice",
            )
            (fixture.runtime / valid_path).unlink()
            fixture._commit("delete valid notice")
            deleted = git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()

            notices = contract.notices(fixture.runtime, baseline, deleted)
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0]["commit"], added)
            self.assertEqual(notices[0]["path"], valid_path)
            self.assertEqual(notices[0]["context"], "kept")

            special_paths = (
                "docs/contract_notices/русский\twith\nnewline.json",
                "docs/contract_notices/ещё\ttwo.json",
            )
            for special_path in special_paths:
                write(fixture.runtime / special_path, json.dumps(self.valid_notice(), ensure_ascii=False) + "\n")
            fixture._commit("add special filename notices")
            special = git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()
            special_notices = contract.notices(fixture.runtime, deleted, special)
            self.assertEqual({notice["path"] for notice in special_notices}, set(special_paths))

            fixed_path = "docs/contract_notices/corrupt-then-fixed.json"
            corrupt = self.commit_notice(fixture, fixed_path, "{not-json\n", "add corrupt notice")
            fixed = self.commit_notice(
                fixture,
                fixed_path,
                json.dumps(self.valid_notice(), ensure_ascii=False) + "\n",
                "repair corrupt notice",
            )
            with self.assertRaises(contract.ContractError) as repaired:
                contract.notices(fixture.runtime, special, fixed)
            self.assertIn(f"{fixed_path}@{corrupt}", str(repaired.exception))

            deleted_path = "docs/contract_notices/corrupt-then-deleted.json"
            corrupt_deleted = self.commit_notice(fixture, deleted_path, "{not-json\n", "add corrupt deleted notice")
            (fixture.runtime / deleted_path).unlink()
            fixture._commit("delete corrupt notice")
            deleted_corrupt = git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()
            with self.assertRaises(contract.ContractError) as removed:
                contract.notices(fixture.runtime, fixed, deleted_corrupt)
            self.assertIn(f"{deleted_path}@{corrupt_deleted}", str(removed.exception))
        finally:
            fixture.close()

    def test_notices_read_merge_resolution_notices(self) -> None:
        fixture = ConsumerFixture()
        try:
            git(fixture.runtime, "checkout", "--quiet", "-b", "merge-base", fixture.b)
            base = git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()
            git(fixture.runtime, "checkout", "--quiet", "-b", "merge-left")
            write(fixture.runtime / "left.txt", "left\n")
            fixture._commit("left parent")
            git(fixture.runtime, "checkout", "--quiet", "-b", "merge-right", base)
            write(fixture.runtime / "right.txt", "right\n")
            fixture._commit("right parent")
            git(fixture.runtime, "merge", "--no-ff", "--no-commit", "merge-left")
            merge_path = "docs/contract_notices/merge-resolution.json"
            write(fixture.runtime / merge_path, "{not-json\n")
            fixture._commit("merge resolution adds corrupt notice")
            merged = git(fixture.runtime, "rev-parse", "HEAD").stdout.strip()

            with self.assertRaises(contract.ContractError) as rejected:
                contract.notices(fixture.runtime, base, merged)
            self.assertIn(f"{merge_path}@{merged}", str(rejected.exception))
        finally:
            fixture.close()

    def test_unreadable_non_deleted_notice_refuses_upgrade_before_candidate_or_backup(self) -> None:
        fixture = ConsumerFixture()
        try:
            git(fixture.runtime, "checkout", "--quiet", "-b", "unreadable-upgrade", fixture.b)
            target = fixture.clone_seed("unreadable-notice")
            notice_path = "docs/contract_notices/unreadable-upgrade.json"
            selected = self.commit_notice(
                fixture,
                notice_path,
                json.dumps(self.valid_notice(), ensure_ascii=False) + "\n",
                "add unreadable upgrade notice",
            )
            source_before = repo_state(fixture.runtime)
            target_before = repo_state(target)
            original_git = contract.git

            def unreadable_blob(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
                if root == fixture.runtime and arguments == ("show", f"{selected}:{notice_path}") and not check:
                    return subprocess.CompletedProcess(["git"], 1, "", "fixture unreadable notice")
                return original_git(root, *arguments, check=check)

            with mock.patch.object(contract, "git", side_effect=unreadable_blob):
                with self.assertRaises(contract.ContractError) as rejected:
                    contract.upgrade(fixture.runtime, target, selected)
            self.assertIn(f"cannot read notice in source history: {notice_path}@{selected}", str(rejected.exception))
            self.assertEqual(repo_state(fixture.runtime), source_before)
            self.assertEqual(repo_state(target), target_before)
            self.assertFalse(fixture.candidate(target, selected).exists())
            self.assertFalse(fixture.backup(target, selected).exists())
        finally:
            fixture.close()


class ConsumerContractGitInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = ConsumerFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    @staticmethod
    def ignore(target: Path, pattern: str) -> None:
        exclude = Path(
            git(target, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip()
        )
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(pattern + "\n")

    def test_inventory_parser_and_actual_nul_paths(self) -> None:
        names = ("русский\twith\nnewline.txt", "ещё\ttwo.txt")
        payload = b"".join(name.encode("utf-8") + b"\0" for name in names)
        self.assertEqual(contract.git_inventory_records(b""), [])
        self.assertEqual(contract.git_inventory_records(payload), list(names))
        for malformed in (b"\0", b"first\0\0", b"first", b"\xff\0"):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(contract.ContractError, "cannot parse Git inventory"):
                    contract.git_inventory_records(malformed)

        target = self.fixture.clone_seed("inventory-special-names")
        marker = "<<<<<<< ours\n=======\n>>>>>>> theirs\n"
        for name in names:
            write(target / name, marker)
        problems = contract.bad_merge_state(target)
        self.assertEqual({f"conflict markers: {name}" for name in names}, set(problems))

    def test_ignored_cache_is_not_selected_but_selected_paths_still_block(self) -> None:
        marker = "<<<<<<< ours\n=======\n>>>>>>> theirs\n"
        ignored = self.fixture.clone_seed("ignored-cache-doctor")
        self.ignore(ignored, ".tmp/")
        ignored_marker = ignored / ".tmp" / "cache" / "marker.txt"
        ignored_reject = ignored / ".tmp" / "cache" / "marker.rej"
        write(ignored_marker, marker)
        write(ignored_reject, "synthetic ignored reject\n")
        for path in (ignored_marker, ignored_reject):
            self.assertEqual(git(ignored, "check-ignore", "-q", os.fspath(path.relative_to(ignored)), check=False).returncode, 0)
        before = repo_state(ignored)
        diagnosed = contract.doctor(ignored, self.fixture.runtime, exact_runtime=False, expected=self.fixture.a)
        self.assertEqual(diagnosed["state"], "ok")
        self.assertEqual(repo_state(ignored), before)

        selected = self.fixture.clone_seed("selected-inventory")
        self.ignore(selected, ".tmp/")
        tracked = ".tmp/tracked-marker.txt"
        untracked = "untracked-marker.txt"
        reject = "selected.rej"
        write(selected / tracked, marker)
        git(selected, "add", "--force", tracked)
        git(selected, "commit", "--quiet", "-m", "track ignored marker")
        self.assertEqual(git(selected, "check-ignore", "--no-index", "-q", tracked, check=False).returncode, 0)
        write(selected / untracked, marker)
        write(selected / reject, "selected reject\n")
        problems = contract.bad_merge_state(selected)
        self.assertIn(f"conflict markers: {tracked}", problems)
        self.assertIn(f"conflict markers: {untracked}", problems)
        self.assertIn(f"reject file: {reject}", problems)

    def test_managed_ignored_path_blocks_doctor_and_upgrade_before_copy(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("managed-ignored")
        self.ignore(target, MANAGED)
        marker = "<<<<<<< ours\n=======\n>>>>>>> theirs\n"
        write(target / MANAGED, marker)
        git(target, "rm", "--cached", MANAGED)
        git(target, "commit", "--quiet", "-m", "make managed path ignored")
        self.assertEqual(git(target, "check-ignore", "-q", MANAGED, check=False).returncode, 0)
        source_before = repo_state(fixture.runtime)
        target_before = repo_state(target)

        diagnosed = contract.doctor(target, fixture.runtime, exact_runtime=False, expected=fixture.a)
        self.assertEqual(diagnosed["state"], "blocked")
        self.assertIn(f"conflict markers: {MANAGED}", diagnosed["problems"])
        self.assertEqual(repo_state(target), target_before)

        with self.assertRaisesRegex(contract.ContractError, "sibling has uncommitted changes or conflict indicators"):
            contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertEqual(repo_state(fixture.runtime), source_before)
        self.assertEqual(repo_state(target), target_before)
        self.assertFalse(fixture.candidate(target, fixture.b).exists())
        self.assertFalse(fixture.backup(target, fixture.b).exists())

    def test_selected_symlink_read_failure_and_identity_change_block(self) -> None:
        fixture = self.fixture
        sentinel = fixture.root / "external-sentinel.txt"
        write(sentinel, "<<<<<<< outside\n=======\n>>>>>>> outside\n")
        linked = fixture.clone_seed("selected-symlink")
        link_name = "selected-link.txt"
        (linked / link_name).symlink_to(sentinel)
        git(linked, "add", link_name)
        git(linked, "commit", "--quiet", "-m", "track selected symlink")
        linked_before = repo_state(linked)
        self.assertEqual(contract.bad_merge_state(linked), [f"unsafe selected path: {link_name}"])
        self.assertEqual(repo_state(linked), linked_before)

        unreadable = fixture.clone_seed("selected-read-failure")
        unreadable_name = "read-failure.txt"
        write(unreadable / unreadable_name, "selected body\n")
        unreadable_before = repo_state(unreadable)
        original_read_selected_file = contract.read_selected_file

        def unreadable_selected_file(path: Path, expected: os.stat_result) -> tuple[bytes | None, str | None]:
            if path == unreadable / unreadable_name:
                return None, "cannot read selected path"
            return original_read_selected_file(path, expected)

        with mock.patch.object(contract, "read_selected_file", side_effect=unreadable_selected_file):
            self.assertEqual(
                contract.bad_merge_state(unreadable),
                [f"cannot read selected path: {unreadable_name}"],
            )
        self.assertEqual(repo_state(unreadable), unreadable_before)

        changed = fixture.clone_seed("selected-identity-change")
        changed_name = "identity-change.txt"
        write(changed / changed_name, "selected body\n")
        changed_before = repo_state(changed)
        original_read_selected_file = contract.read_selected_file

        def changed_selected_file(path: Path, expected: os.stat_result) -> tuple[bytes | None, str | None]:
            if path == changed / changed_name:
                return None, "selected path changed during inspection"
            return original_read_selected_file(path, expected)

        with mock.patch.object(contract, "read_selected_file", side_effect=changed_selected_file):
            self.assertEqual(
                contract.bad_merge_state(changed),
                [f"selected path changed during inspection: {changed_name}"],
            )
        self.assertEqual(repo_state(changed), changed_before)

    def test_managed_ignored_candidate_blocks_acceptance_without_swap(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("managed-ignored-accept")
        candidate = fixture.candidate(target, fixture.b)
        shutil.copytree(target, candidate, symlinks=True)
        self.ignore(candidate, MANAGED)
        write(candidate / MANAGED, "<<<<<<< candidate\n=======\n>>>>>>> candidate\n")
        git(candidate, "rm", "--cached", MANAGED)
        git(candidate, "commit", "--quiet", "-m", "make candidate managed path ignored")
        self.assertEqual(git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout, "")
        source_before = repo_state(fixture.runtime)
        target_before = repo_state(target)
        candidate_before = repo_state(candidate)

        blocked = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)
        self.assertEqual(blocked["state"], "blocked")
        self.assertIn(f"conflict markers: {MANAGED}", blocked["problems"])
        self.assertEqual(repo_state(fixture.runtime), source_before)
        self.assertEqual(repo_state(target), target_before)
        self.assertEqual(repo_state(candidate), candidate_before)
        self.assertFalse(fixture.backup(target, fixture.b).exists())


class ConsumerContractDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = ConsumerFixture(deleted_body="# Obsolete shared playbook\n")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_real_copier_unchanged_deletion_review_commit_and_accept(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("unchanged-deletion")
        before = repo_state(target)
        blocked = contract.upgrade(fixture.runtime, target, fixture.b)
        candidate = fixture.candidate(target, fixture.b)
        self.assertEqual(blocked["state"], "blocked")
        self.assertIn(f"cannot inspect selected path: {REMOVED}", blocked["problems"])
        self.assertFalse(contract.path_occupied(candidate / REMOVED))
        self.assertEqual(git(candidate, "ls-files", "--error-unmatch", REMOVED).returncode, 0)
        self.assertIn(f"D\t{REMOVED}\n", git(candidate, "diff", "--name-status").stdout)
        self.assertEqual(repo_state(target), before)
        self.assertFalse(fixture.backup(target, fixture.b).exists())
        self.assertEqual(list((candidate / "docs/plans").glob("*_contract_upgrade_*.md")), [])

        fixture.commit_target(candidate, "review unchanged managed deletion")
        self.assertEqual(git(candidate, "status", "--porcelain=v1").stdout, "")
        accepted = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)
        self.assertEqual(accepted["state"], "updated_pending_adaptation")
        self.assertFalse(contract.path_occupied(target / REMOVED))
        self.assertFalse(candidate.exists())
        self.assertEqual(repo_state(fixture.backup(target, fixture.b)), before)
        self.assertIn(REMOVED, accepted["contract_changes"])
        self.assertIn("**Status:** Architect initial draft", Path(str(accepted["plan"])).read_text())
        self.assertEqual(contract.marker_answers(target, fixture.runtime)[0].source_commit, fixture.b)
        self.assertEqual(contract.doctor(target, fixture.runtime, exact_runtime=False, expected=fixture.b)["state"], "ok")

    def test_unsafe_original_deletions_refuse_before_copy_and_acceptance(self) -> None:
        fixture = self.fixture
        variants = ("bytes", "mode", "missing", "directory", "symlink", "broken-symlink", *contract.LOCAL_HEADINGS)
        for index, variant in enumerate(variants):
            for accept in (False, True):
                with self.subTest(variant=variant, accept=accept):
                    target = fixture.clone_seed(f"unsafe-deletion-{index}-{accept}")
                    removed = target / REMOVED
                    if variant == "bytes":
                        removed.write_bytes(removed.read_bytes() + b"consumer edit\n")
                    elif variant == "mode":
                        removed.chmod(0o600)
                    elif variant == "missing":
                        removed.unlink()
                    elif variant == "directory":
                        removed.unlink()
                        write(removed / "retained.txt", "consumer directory\n")
                    elif variant in {"symlink", "broken-symlink"}:
                        removed.unlink()
                        removed.symlink_to("playbook.md" if variant == "symlink" else "missing-file.md")
                    else:
                        removed.write_text(removed.read_text() + f"{variant}\nconsumer local rule\n")
                    if git(target, "status", "--porcelain=v1").stdout:
                        fixture.commit_target(target, "commit unsafe original deletion fixture")
                    before = repo_state(target)
                    before_metadata = removed.lstat() if contract.path_occupied(removed) else None
                    before_link = os.readlink(removed) if removed.is_symlink() else None
                    candidate = fixture.candidate(target, fixture.b)
                    if accept:
                        shutil.copytree(target, candidate, symlinks=True)
                        write(candidate / "review.md", "reviewed candidate\n")
                        fixture.commit_target(candidate, "review candidate before original admission")
                        candidate_before = repo_state(candidate)
                    with mock.patch.object(contract.shutil, "copytree", side_effect=AssertionError("candidate copy must not run")):
                        with mock.patch.object(contract, "command", wraps=contract.command) as commands:
                            with self.assertRaisesRegex(contract.ContractError, f"managed path cannot be removed before Copier: {REMOVED}"):
                                contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=accept)
                    self.assertFalse(any(call.args[0][1:2] == ["update"] for call in commands.call_args_list))
                    self.assertEqual(repo_state(target), before)
                    self.assertEqual(removed.lstat() if contract.path_occupied(removed) else None, before_metadata)
                    self.assertEqual(os.readlink(removed) if removed.is_symlink() else None, before_link)
                    self.assertFalse(fixture.backup(target, fixture.b).exists())
                    if accept:
                        self.assertEqual(repo_state(candidate), candidate_before)
                    else:
                        self.assertFalse(candidate.exists())

    def test_unchanged_default_local_deletions_refuse_from_old_render(self) -> None:
        for index, heading in enumerate(contract.LOCAL_HEADINGS):
            with self.subTest(heading=heading):
                fixture = ConsumerFixture(deleted_body=f"# Obsolete shared playbook\n{heading}\nN/A (why=default local section)\n")
                self.addCleanup(fixture.close)
                for accept in (False, True):
                    target = fixture.clone_seed(f"default-local-deletion-{index}-{accept}")
                    candidate = fixture.candidate(target, fixture.b)
                    if accept:
                        shutil.copytree(target, candidate, symlinks=True)
                    before = repo_state(target)
                    with mock.patch.object(contract.shutil, "copytree", side_effect=AssertionError("candidate copy must not run")):
                        with self.assertRaisesRegex(contract.ContractError, f"managed path cannot be removed before Copier: {REMOVED}: protected local section"):
                            contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=accept)
                    self.assertEqual(repo_state(target), before)
                    self.assertFalse(fixture.backup(target, fixture.b).exists())
                    self.assertEqual(candidate.exists(), accept)

    def test_removed_and_added_inventory_keeps_original_rename_refusal(self) -> None:
        fixture = self.fixture
        for accept in (False, True):
            with self.subTest(accept=accept):
                target = fixture.clone_seed(f"unchanged-rename-{accept}")
                candidate = fixture.candidate(target, fixture.c)
                if accept:
                    shutil.copytree(target, candidate, symlinks=True)
                before = repo_state(target)
                with mock.patch.object(contract.shutil, "copytree", side_effect=AssertionError("candidate copy must not run")):
                    with self.assertRaisesRegex(contract.ContractError, "managed paths disappear or rename before Copier"):
                        contract.upgrade(fixture.runtime, target, fixture.c, accept_candidate=accept)
                self.assertEqual(repo_state(target), before)
                self.assertFalse(fixture.backup(target, fixture.c).exists())
                self.assertEqual(candidate.exists(), accept)

    def test_retained_removed_paths_block_after_copier_and_on_acceptance(self) -> None:
        fixture = self.fixture
        for variant in ("file", "directory", "broken-symlink"):
            with self.subTest(variant=variant):
                target = fixture.clone_seed(f"retained-deletion-{variant}")
                candidate = fixture.candidate(target, fixture.b)
                before = repo_state(target)
                original_command = contract.command

                def retain_removed(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                    if argv[1:2] != ["update"]:
                        return original_command(argv, **kwargs)
                    removed = candidate / REMOVED
                    if variant != "file":
                        removed.unlink()
                        if variant == "directory":
                            write(removed / "retained.txt", "retained directory\n")
                        else:
                            removed.symlink_to("missing-file.md")
                    marker_path = candidate / contract.MARKER
                    marker = json.loads(marker_path.read_text())
                    marker["source_commit"] = fixture.b
                    marker_path.write_text(json.dumps(marker))
                    answers_path = candidate / contract.ANSWERS
                    answers = contract.yaml.safe_load(answers_path.read_text())
                    answers["_commit"] = fixture.b
                    answers_path.write_text(contract.yaml.safe_dump(answers))
                    return subprocess.CompletedProcess(argv, 0, "", "")

                with mock.patch.object(contract, "command", side_effect=retain_removed):
                    with mock.patch.object(contract, "doctor", side_effect=AssertionError("retained paths must block before doctor")):
                        blocked = contract.upgrade(fixture.runtime, target, fixture.b)
                self.assertIn(f"removed managed path still exists: {REMOVED}", blocked["problems"])
                self.assertEqual(repo_state(target), before)
                fixture.commit_target(candidate, "review candidate retaining removed path")
                candidate_before = repo_state(candidate)
                with mock.patch.object(contract, "doctor", side_effect=AssertionError("retained paths must block before doctor")):
                    blocked = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)
                self.assertEqual(blocked["state"], "blocked")
                self.assertIn(f"removed managed path still exists: {REMOVED}", blocked["problems"])
                self.assertEqual(repo_state(target), before)
                self.assertEqual(repo_state(candidate), candidate_before)
                self.assertFalse(fixture.backup(target, fixture.b).exists())


class ConsumerContractLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = ConsumerFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_compatible_upgrade_preserves_local_section_and_swaps_only_after_checks(self) -> None:
        fixture = self.fixture
        target = fixture.cases / "compatible-upgrade"
        self.assertEqual(contract.init(fixture.runtime, target, fixture.a)["state"], "ok")
        local_body = f"{LOCAL_HEADING}\nlocal=kept-byte-for-byte\n"
        managed = target / MANAGED
        managed.write_text(
            "# Managed playbook\nshared=A\n" + local_body + "## End\n",
            encoding="utf-8",
        )
        fixture.commit_target(target, "add a compatible local section")

        before_doctor = repo_state(target)
        self.assertEqual(
            contract.doctor(target, fixture.runtime, exact_runtime=False, expected=fixture.a)["state"],
            "ok",
        )
        self.assertEqual(repo_state(target), before_doctor, "doctor must be read-only before upgrade")

        original_bytes = managed.read_bytes()
        before_swap = repo_state(target)
        candidate = fixture.candidate(target, fixture.b)
        backup = fixture.backup(target, fixture.b)
        observed_swap: list[bool] = []
        original_rename = Path.rename

        def observe_original_before_swap(path: Path, destination: str | Path) -> Path:
            if path == target and Path(destination) == backup:
                self.assertEqual(repo_state(target), before_swap)
                self.assertEqual((target / MANAGED).read_bytes(), original_bytes)
                observed_swap.append(True)
            return original_rename(path, destination)

        with mock.patch.object(Path, "rename", new=observe_original_before_swap):
            upgraded = contract.upgrade(fixture.runtime, target, fixture.b)

        self.assertEqual(upgraded["state"], "updated_pending_adaptation")
        self.assertEqual(observed_swap, [True], "the original must remain untouched until directory swap")
        self.assertFalse(candidate.exists())
        self.assertEqual((backup / MANAGED).read_bytes(), original_bytes)
        self.assertEqual(
            contract.local_sections(target, {MANAGED})[MANAGED][LOCAL_HEADING],
            local_body.encode("utf-8"),
        )
        self.assertIn("shared=B", (target / MANAGED).read_text(encoding="utf-8"))
        self.assertTrue(Path(str(upgraded["plan"])).is_file())
        self.assertEqual(Path(str(upgraded["backup"])), backup)

        after_doctor = repo_state(target)
        self.assertEqual(
            contract.doctor(target, fixture.runtime, exact_runtime=False, expected=fixture.b)["state"],
            "ok",
        )
        self.assertEqual(repo_state(target), after_doctor, "doctor must be read-only after upgrade")

    def test_copier_mirror_cache_belongs_to_the_fixture_runtime(self) -> None:
        cache = contract.copier_cache_home(self.fixture.runtime)
        self.assertTrue((cache / "copier").is_dir(), "fixture init must fill the Copier cache of its own runtime")

    def test_init_root_follows_umask_and_upgrade_keeps_the_root_mode(self) -> None:
        fixture = self.fixture
        target = fixture.cases / "root-mode"
        probe = fixture.cases / "root-mode-plain-mkdir"
        previous_umask = os.umask(0o027)
        try:
            probe.mkdir()
            self.assertEqual(contract.init(fixture.runtime, target, fixture.a)["state"], "ok")
        finally:
            os.umask(previous_umask)
        plain_mode = probe.stat().st_mode & 0o777
        self.assertEqual(plain_mode, 0o750)
        self.assertEqual(target.stat().st_mode & 0o777, plain_mode, "sibling root must not stay 0700 from mkdtemp")

        upgraded = contract.upgrade(fixture.runtime, target, fixture.b)

        self.assertEqual(upgraded["state"], "updated_pending_adaptation")
        backup = fixture.backup(target, fixture.b)
        self.assertEqual(backup.stat().st_mode & 0o777, plain_mode, "backup keeps the original root mode")
        self.assertEqual(target.stat().st_mode & 0o777, plain_mode, "upgrade keeps the original root mode")

    def test_raw_local_section_bytes_preserve_crlf_and_acceptance_refuses_newline_only_change(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("raw-crlf-local-section")
        local_crlf = f"{LOCAL_HEADING}\r\nlocal=kept-byte-for-byte\r\n".encode("utf-8")
        local_lf = f"{LOCAL_HEADING}\nlocal=kept-byte-for-byte\n".encode("utf-8")
        prefix = b"# Managed playbook\nshared=A\n"
        suffix = b"## End\n"
        (target / MANAGED).write_bytes(prefix + local_crlf + suffix)
        fixture.commit_target(target, "add CRLF local section")

        candidate = fixture.candidate(target, fixture.b)
        shutil.copytree(target, candidate, symlinks=True)
        (candidate / MANAGED).write_bytes(prefix + local_lf + suffix)
        fixture.commit_target(candidate, "change only local newlines")
        before = repo_state(target)

        blocked = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)

        self.assertEqual(blocked["state"], "blocked")
        self.assertIn(
            f"local text changed or disappeared: {MANAGED} / {LOCAL_HEADING}",
            blocked["problems"],
        )
        self.assertEqual(
            contract.local_sections(target, {MANAGED})[MANAGED][LOCAL_HEADING],
            local_crlf,
        )
        self.assertEqual(repo_state(target), before)
        self.assertFalse(fixture.backup(target, fixture.b).exists())

    def test_acceptance_preserves_unchanged_crlf_local_section(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("accept-unchanged-crlf-local-section")
        local_crlf = f"{LOCAL_HEADING}\r\nlocal=kept-byte-for-byte\r\n".encode("utf-8")
        original = target / MANAGED
        original.write_bytes(b"# Managed playbook\nshared=A\n" + local_crlf + b"## End\n")
        fixture.commit_target(target, "add CRLF local section")
        original_bytes = original.read_bytes()
        before = repo_state(target)

        candidate = fixture.candidate(target, fixture.b)
        shutil.copytree(target, candidate, symlinks=True)
        (candidate / MANAGED).write_bytes(b"# Managed playbook\nshared=B\n" + local_crlf + b"## End\n")
        marker_path = candidate / contract.MARKER
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["source_commit"] = fixture.b
        marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        answers_path = candidate / contract.ANSWERS
        answers = contract.yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        self.assertIsInstance(answers, dict)
        answers["_commit"] = fixture.b
        answers_path.write_text(contract.yaml.safe_dump(answers, sort_keys=False), encoding="utf-8")
        fixture.commit_target(candidate, "review CRLF-preserving candidate")

        accepted = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)

        backup = fixture.backup(target, fixture.b)
        self.assertEqual(accepted["state"], "updated_pending_adaptation")
        self.assertEqual((backup / MANAGED).read_bytes(), original_bytes)
        self.assertEqual(
            contract.local_sections(target, {MANAGED})[MANAGED][LOCAL_HEADING],
            local_crlf,
        )
        self.assertTrue(Path(str(accepted["plan"])).is_file())
        self.assertIn("Finish active sibling role and shell sessions", accepted["warnings"][0])
        self.assertFalse(candidate.exists())
        self.assertNotEqual(repo_state(target), before)

    def test_non_utf8_local_sections_refuse_upgrade_and_acceptance_without_swapping(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("non-utf8-target")
        (target / MANAGED).write_bytes(
            b"# Managed playbook\nshared=A\n" + LOCAL_HEADING.encode("utf-8") + b"\nlocal=\xff\n## End\n"
        )
        fixture.commit_target(target, "make managed local section non-UTF-8")
        target_before = repo_state(target)
        with self.assertRaisesRegex(contract.ContractError, "managed local section is not valid UTF-8"):
            contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertEqual(repo_state(target), target_before)
        self.assertFalse(fixture.candidate(target, fixture.b).exists())

        accepted_target = fixture.clone_seed("non-utf8-candidate")
        (accepted_target / MANAGED).write_text(
            "# Managed playbook\nshared=A\n## End\n",
            encoding="utf-8",
        )
        fixture.commit_target(accepted_target, "remove the old local heading from a valid target")
        candidate = fixture.candidate(accepted_target, fixture.b)
        shutil.copytree(accepted_target, candidate, symlinks=True)
        (candidate / MANAGED).write_bytes(b"# Managed playbook\nshared=A\nlocal=\xff\n## End\n")
        fixture.commit_target(candidate, "make candidate protected path non-UTF-8")
        accepted_before = repo_state(accepted_target)
        with self.assertRaisesRegex(contract.ContractError, "managed local section is not valid UTF-8"):
            contract.upgrade(fixture.runtime, accepted_target, fixture.b, accept_candidate=True)
        self.assertEqual(repo_state(accepted_target), accepted_before)
        self.assertFalse(fixture.backup(accepted_target, fixture.b).exists())

    def test_unreadable_protected_local_sections_fail_closed_on_upgrade_and_acceptance(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("unreadable-local-target")
        binary = target / "docs" / "unmanaged-binary.bin"
        binary.write_bytes(b"\xff\x00\xfe")
        self.assertEqual(contract.local_sections(target, {"docs/unmanaged-binary.bin"}), {})

        oversized_local = (
            b"# Managed playbook\nshared=A\n"
            + LOCAL_HEADING.encode("utf-8")
            + b"\n"
            + b"x" * 2_000_001
            + b"\n## End\n"
        )
        (target / MANAGED).write_bytes(oversized_local)
        fixture.commit_target(target, "add an unreadable protected local section fixture")
        target_before = repo_state(target)

        original_read_bytes = Path.read_bytes

        def unreadable(path: Path) -> bytes:
            if path == target / MANAGED:
                raise OSError("fixture unreadable managed file")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", new=unreadable):
            with self.assertRaisesRegex(contract.ContractError, "cannot read protected local section"):
                contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertEqual(repo_state(target), target_before)
        self.assertFalse(fixture.candidate(target, fixture.b).exists())

        accepted_target = fixture.clone_seed("unreadable-local-candidate")
        candidate = fixture.candidate(accepted_target, fixture.b)
        shutil.copytree(accepted_target, candidate, symlinks=True)
        (candidate / MANAGED).write_bytes(oversized_local)
        fixture.commit_target(candidate, "add an unreadable candidate local section fixture")
        accepted_before = repo_state(accepted_target)

        def unreadable_candidate(path: Path) -> bytes:
            if path == candidate / MANAGED:
                raise OSError("fixture unreadable candidate file")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", new=unreadable_candidate):
            with self.assertRaisesRegex(contract.ContractError, "cannot read protected local section"):
                contract.upgrade(fixture.runtime, accepted_target, fixture.b, accept_candidate=True)
        self.assertEqual(repo_state(accepted_target), accepted_before)
        self.assertFalse(fixture.backup(accepted_target, fixture.b).exists())

    def test_acceptance_refuses_uncommitted_candidate_and_preserves_original(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("accept-uncommitted-candidate")
        candidate = fixture.candidate(target, fixture.b)
        shutil.copytree(target, candidate, symlinks=True)
        write(candidate / "review-notes.md", "candidate must be committed\n")
        before = repo_state(target)

        with self.assertRaisesRegex(contract.ContractError, "candidate must be reviewed and committed"):
            contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)

        self.assertEqual(repo_state(target), before)
        self.assertFalse(fixture.backup(target, fixture.b).exists())

    def test_acceptance_refuses_lost_local_text_and_preserves_original(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("accept-lost-local-text")
        local_body = f"{LOCAL_HEADING}\nlocal=must-survive-acceptance\n"
        original = target / MANAGED
        original.write_text("# Managed playbook\nshared=A\n" + local_body + "## End\n", encoding="utf-8")
        fixture.commit_target(target, "add protected local text")
        candidate = fixture.candidate(target, fixture.b)
        shutil.copytree(target, candidate, symlinks=True)
        (candidate / MANAGED).write_text("# Managed playbook\nshared=B\n## End\n", encoding="utf-8")
        fixture.commit_target(candidate, "remove protected local text")
        before = repo_state(target)
        original_bytes = original.read_bytes()

        blocked = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)

        self.assertEqual(blocked["state"], "blocked")
        self.assertIn(
            f"local text changed or disappeared: {MANAGED} / {LOCAL_HEADING}",
            blocked["problems"],
        )
        self.assertEqual(repo_state(target), before)
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertTrue(candidate.is_dir())
        self.assertFalse(fixture.backup(target, fixture.b).exists())

    def test_existing_adaptation_plan_is_not_overwritten_during_acceptance(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("existing-adaptation-plan")
        local_body = f"{LOCAL_HEADING}\nlocal=kept-byte-for-byte\n"
        (target / MANAGED).write_text(
            "# Managed playbook\nshared=consumer-edit\n" + local_body + "## End\n",
            encoding="utf-8",
        )
        fixture.commit_target(target, "make Copier conflict for adaptation plan")
        blocked = contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertEqual(blocked["state"], "blocked")
        candidate = fixture.candidate(target, fixture.b)
        self.assertTrue(candidate.is_dir())
        (candidate / MANAGED).write_text(
            "# Managed playbook\nshared=B\n" + local_body + "## End\n",
            encoding="utf-8",
        )
        fixed_now = datetime(2026, 9, 26, 12, 34)
        plan = candidate / "docs" / "plans" / (
            f"{fixed_now:%y%m%d_%H%M}_contract_upgrade_{fixture.a[:7]}_{fixture.b[:7]}.md"
        )
        write(plan, "existing adaptation plan must survive\n")
        fixture.commit_target(candidate, "resolve conflict with existing adaptation plan")
        plan_bytes = plan.read_bytes()
        before = repo_state(target)

        class FixedDateTime:
            @classmethod
            def now(cls) -> datetime:
                return fixed_now

        with mock.patch.object(contract, "datetime", FixedDateTime):
            with self.assertRaisesRegex(contract.ContractError, "adaptation plan already exists"):
                contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)

        self.assertEqual(repo_state(target), before)
        self.assertEqual(plan.read_bytes(), plan_bytes)
        self.assertTrue(candidate.is_dir())
        self.assertFalse(fixture.backup(target, fixture.b).exists())

    def test_full_init_doctor_conflict_accept_and_rename_refusal(self) -> None:
        fixture = self.fixture
        target = fixture.cases / "lifecycle"
        initialized = contract.init(fixture.runtime, target, fixture.a)
        self.assertEqual(initialized["state"], "ok")

        before_doctor = repo_state(target)
        diagnosed = contract.doctor(target, fixture.runtime, exact_runtime=False, expected=fixture.a)
        self.assertEqual(diagnosed["state"], "ok")
        self.assertEqual(repo_state(target), before_doctor, "doctor must be read-only")

        original = target / MANAGED
        local_body = f"{LOCAL_HEADING}\nlocal=kept-byte-for-byte\n"
        original.write_text(
            "# Managed playbook\nshared=consumer-edit\n" + local_body + "## End\n",
            encoding="utf-8",
        )
        fixture.commit_target(target, "consumer edit that conflicts with B")
        original_bytes = original.read_bytes()
        before_conflict = repo_state(target)

        blocked = contract.upgrade(fixture.runtime, target, fixture.b)
        candidate = fixture.candidate(target, fixture.b)
        self.assertEqual(blocked["state"], "blocked")
        self.assertTrue(candidate.is_dir())
        self.assertTrue(any("conflict markers" in item for item in blocked["problems"]))
        self.assertEqual(repo_state(target), before_conflict, "a conflict must not change the original sibling")
        self.assertEqual((target / MANAGED).read_bytes(), original_bytes)

        (candidate / MANAGED).write_text(
            "# Managed playbook\nshared=B\n" + local_body + "## End\n",
            encoding="utf-8",
        )
        fixture.commit_target(candidate, "resolve generated Copier conflict")
        accepted = contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)
        backup = fixture.backup(target, fixture.b)
        self.assertEqual(accepted["state"], "updated_pending_adaptation")
        self.assertEqual((backup / MANAGED).read_bytes(), original_bytes)
        self.assertEqual(
            contract.local_sections(target, {MANAGED})[MANAGED][LOCAL_HEADING],
            local_body.encode("utf-8"),
        )
        self.assertIn("Finish active sibling role and shell sessions", accepted["warnings"][0])
        self.assertIn(os.fspath(backup), accepted["warnings"][1])

        fixture.commit_target(target, "commit adaptation plan before next upgrade")
        before_rename = repo_state(target)
        with self.assertRaisesRegex(contract.ContractError, "managed paths disappear or rename before Copier"):
            contract.upgrade(fixture.runtime, target, fixture.c)
        self.assertEqual(repo_state(target), before_rename)
        self.assertFalse(fixture.candidate(target, fixture.c).exists())

    def test_linked_and_external_metadata_refuse_before_candidate_copy(self) -> None:
        fixture = self.fixture
        main = fixture.root / "linked-main"
        main.mkdir()
        git(main, "init", "-b", "main")
        write(main / "tracked.txt", "original\n")
        git(main, "add", "tracked.txt")
        git(main, "commit", "--quiet", "-m", "linked fixture")
        linked = fixture.root / "linked-consumer"
        git(main, "worktree", "add", "-b", "linked-consumer", os.fspath(linked))
        linked_before = repo_state(linked)
        try:
            with self.assertRaisesRegex(contract.ContractError, "linked-worktree or external Git metadata"):
                contract.upgrade(fixture.runtime, linked, fixture.b)
            self.assertEqual(repo_state(linked), linked_before)
            self.assertFalse(fixture.candidate(linked, fixture.b).exists())
        finally:
            git(main, "worktree", "remove", "--force", os.fspath(linked))

        external = fixture.root / "external-control"
        target = fixture.root / "external-consumer"
        run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--separate-git-dir",
                os.fspath(external),
                os.fspath(fixture.seed),
                os.fspath(target),
            ]
        )
        self.assertTrue((target / ".git").is_file())
        external_before = repo_state(target)
        with self.assertRaisesRegex(contract.ContractError, "linked-worktree or external Git metadata"):
            contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertEqual(repo_state(target), external_before)
        self.assertFalse(fixture.candidate(target, fixture.b).exists())

    def test_shared_object_metadata_refuses_before_candidate_copy_or_acceptance(self) -> None:
        fixture = self.fixture

        objects_target = fixture.clone_seed("objects-symlink")
        objects = objects_target / ".git" / "objects"
        shared_objects = fixture.root / "shared-object-store"
        objects.rename(shared_objects)
        objects.symlink_to(shared_objects, target_is_directory=True)
        objects_before = repo_state(objects_target)
        with self.assertRaisesRegex(contract.ContractError, "external Git metadata symlink"):
            contract.upgrade(fixture.runtime, objects_target, fixture.b)
        self.assertEqual(repo_state(objects_target), objects_before)
        self.assertFalse(fixture.candidate(objects_target, fixture.b).exists())

        alternates_target = fixture.root / "reference-consumer"
        run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--reference",
                os.fspath(fixture.seed),
                os.fspath(fixture.seed),
                os.fspath(alternates_target),
            ]
        )
        alternates = alternates_target / ".git" / "objects" / "info" / "alternates"
        self.assertTrue(alternates.is_file())
        self.assertTrue(alternates.read_bytes())
        alternates_before = repo_state(alternates_target)
        with self.assertRaisesRegex(contract.ContractError, "external Git object alternates"):
            contract.upgrade(fixture.runtime, alternates_target, fixture.b)
        self.assertEqual(repo_state(alternates_target), alternates_before)
        self.assertFalse(fixture.candidate(alternates_target, fixture.b).exists())

        nested_target = fixture.clone_seed("nested-metadata-symlink")
        external_ref = fixture.root / "external-ref"
        external_ref.write_text(git(nested_target, "rev-parse", "HEAD").stdout, encoding="utf-8")
        (nested_target / ".git" / "refs" / "heads" / "shared").symlink_to(external_ref)
        nested_before = repo_state(nested_target)
        with self.assertRaisesRegex(contract.ContractError, "external Git metadata symlink"):
            contract.upgrade(fixture.runtime, nested_target, fixture.b)
        self.assertEqual(repo_state(nested_target), nested_before)
        self.assertFalse(fixture.candidate(nested_target, fixture.b).exists())

        accept_target = fixture.clone_seed("accept-shared-objects")
        candidate = fixture.candidate(accept_target, fixture.b)
        shutil.copytree(accept_target, candidate, symlinks=True)
        candidate_objects = candidate / ".git" / "objects"
        candidate_shared_objects = fixture.root / "candidate-shared-object-store"
        candidate_objects.rename(candidate_shared_objects)
        candidate_objects.symlink_to(candidate_shared_objects, target_is_directory=True)
        accept_before = repo_state(accept_target)
        with self.assertRaisesRegex(contract.ContractError, "external Git metadata symlink"):
            contract.upgrade(fixture.runtime, accept_target, fixture.b, accept_candidate=True)
        self.assertEqual(repo_state(accept_target), accept_before)
        self.assertFalse(fixture.backup(accept_target, fixture.b).exists())

    def test_a_runtime_worktree_remains_a_valid_read_only_source(self) -> None:
        fixture = self.fixture
        runtime_worktree = fixture.root / "runtime-worktree"
        self.addCleanup(shutil.rmtree, contract.copier_cache_home(runtime_worktree), True)
        git(fixture.runtime, "worktree", "add", "--detach", os.fspath(runtime_worktree), fixture.b)
        target = fixture.cases / "runtime-worktree-source"
        try:
            result = contract.init(runtime_worktree, target, fixture.a)
            self.assertEqual(result["state"], "ok")
            self.assertEqual(
                contract.doctor(target, runtime_worktree, exact_runtime=False, expected=fixture.a)["state"],
                "ok",
            )
        finally:
            git(fixture.runtime, "worktree", "remove", "--force", os.fspath(runtime_worktree))

    def test_dependency_diagnostics_and_bootstrap_declarations(self) -> None:
        fixture = self.fixture
        missing_yaml_target = fixture.cases / "missing-yaml"
        with mock.patch.object(contract, "yaml", None):
            with self.assertRaisesRegex(contract.ContractError, "Missing PyYAML.*Activate the Planveyor environment"):
                contract.init(fixture.runtime, missing_yaml_target, fixture.a)
        self.assertFalse(missing_yaml_target.exists())

        missing_copier_target = fixture.cases / "missing-copier"
        with mock.patch.object(contract.shutil, "which", return_value=None):
            with self.assertRaisesRegex(contract.ContractError, "Missing Copier 9\\.18\\.2.*Activate the Planveyor environment"):
                contract.init(fixture.runtime, missing_copier_target, fixture.a)
        self.assertFalse(missing_copier_target.exists())

        wrong_copier = subprocess.CompletedProcess(
            ["/trusted/copier", "--version"], 0, "copier 9.18.1\n", ""
        )
        with mock.patch.object(contract.shutil, "which", return_value="/trusted/copier"):
            with mock.patch.object(contract, "command", return_value=wrong_copier):
                with self.assertRaisesRegex(contract.ContractError, "Copier 9\\.18\\.2.*9\\.18\\.1.*Activate the Planveyor environment"):
                    contract.copier_executable(fixture.runtime)

        lock = (REPO_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
        self.assertIn("copier==9.18.2", lock)
        self.assertIn("PyYAML==6.0.3", lock)
        bootstrap = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn(".planveyor.pybin", bootstrap)
        self.assertNotIn(".planveyor.pybin", (SCRIPTS / "consumer_contract.py").read_text(encoding="utf-8"))

    def test_preflight_refusals_leave_the_sibling_and_candidate_unchanged(self) -> None:
        fixture = self.fixture

        same = fixture.clone_seed("same-version")
        same_before = repo_state(same)
        with self.assertRaisesRegex(contract.ContractError, "already uses the selected source commit"):
            contract.upgrade(fixture.runtime, same, fixture.a)
        self.assertEqual(repo_state(same), same_before)
        self.assertFalse(fixture.candidate(same, fixture.a).exists())

        unrelated = fixture.clone_seed("non-descendant")
        unrelated_before = repo_state(unrelated)
        unrelated_commit = fixture.unrelated_commit()
        with self.assertRaisesRegex(contract.ContractError, "not a descendant"):
            contract.upgrade(fixture.runtime, unrelated, unrelated_commit)
        self.assertEqual(repo_state(unrelated), unrelated_before)
        self.assertFalse(fixture.candidate(unrelated, unrelated_commit).exists())

        dirty = fixture.clone_seed("dirty")
        write(dirty / "dirty.txt", "do not touch\n")
        dirty_before = repo_state(dirty)
        with self.assertRaisesRegex(contract.ContractError, "uncommitted changes"):
            contract.upgrade(fixture.runtime, dirty, fixture.b)
        self.assertEqual(repo_state(dirty), dirty_before)
        self.assertFalse(fixture.candidate(dirty, fixture.b).exists())

        missing = fixture.clone_seed("missing-managed")
        (missing / MANAGED).unlink()
        fixture.commit_target(missing, "remove a managed path")
        missing_before = repo_state(missing)
        with self.assertRaisesRegex(contract.ContractError, "missing managed paths before Copier"):
            contract.upgrade(fixture.runtime, missing, fixture.b)
        self.assertEqual(repo_state(missing), missing_before)
        self.assertFalse(fixture.candidate(missing, fixture.b).exists())

        duplicate = fixture.clone_seed("duplicate-section")
        with (duplicate / MANAGED).open("a", encoding="utf-8") as handle:
            handle.write(f"{LOCAL_HEADING}\nduplicate\n")
        fixture.commit_target(duplicate, "add duplicate local heading")
        duplicate_before = repo_state(duplicate)
        with self.assertRaisesRegex(contract.ContractError, "duplicate local section"):
            contract.upgrade(fixture.runtime, duplicate, fixture.b)
        self.assertEqual(repo_state(duplicate), duplicate_before)
        self.assertFalse(fixture.candidate(duplicate, fixture.b).exists())

    def test_occupied_candidate_and_backup_are_rejected_before_copying(self) -> None:
        fixture = self.fixture
        candidate_target = fixture.clone_seed("occupied-candidate")
        candidate = fixture.candidate(candidate_target, fixture.b)
        candidate.mkdir()
        candidate_before = repo_state(candidate_target)
        with self.assertRaisesRegex(contract.ContractError, "candidate path already exists"):
            contract.upgrade(fixture.runtime, candidate_target, fixture.b)
        self.assertEqual(repo_state(candidate_target), candidate_before)

        backup_target = fixture.clone_seed("occupied-backup")
        backup = fixture.backup(backup_target, fixture.b)
        backup.mkdir()
        backup_before = repo_state(backup_target)
        with self.assertRaisesRegex(contract.ContractError, "backup path already exists"):
            contract.upgrade(fixture.runtime, backup_target, fixture.b)
        self.assertEqual(repo_state(backup_target), backup_before)
        self.assertFalse(fixture.candidate(backup_target, fixture.b).exists())

    def test_copier_and_lint_failures_retain_only_a_candidate(self) -> None:
        fixture = self.fixture
        copier_target = fixture.clone_seed("copier-failure")
        copier_before = repo_state(copier_target)
        original_command = contract.command

        def fail_update(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if Path(argv[0]).name == "copier" and len(argv) > 1 and argv[1] == "update":
                return subprocess.CompletedProcess(argv, 17, "", "forced Copier failure")
            return original_command(argv, **kwargs)

        with mock.patch.object(contract, "command", side_effect=fail_update):
            blocked = contract.upgrade(fixture.runtime, copier_target, fixture.b)
        self.assertEqual(blocked["state"], "blocked")
        self.assertTrue(any("Copier exited 17" in item for item in blocked["problems"]))
        self.assertEqual(repo_state(copier_target), copier_before)
        self.assertTrue(fixture.candidate(copier_target, fixture.b).is_dir())

        lint_target = fixture.clone_seed("lint-failure")
        lint_before = repo_state(lint_target)
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            with mock.patch.dict(os.environ, {"PLANVEYOR_TEST_LINT_FAIL": "1"}):
                with self.assertRaisesRegex(contract.ContractError, "generated adaptation plan failed lint"):
                    contract.upgrade(fixture.runtime, lint_target, fixture.b)
        self.assertIn("candidate retained", diagnostics.getvalue())
        self.assertEqual(repo_state(lint_target), lint_before)
        self.assertTrue(fixture.candidate(lint_target, fixture.b).is_dir())

    def test_rollback_restores_the_original_sibling_when_candidate_rename_fails(self) -> None:
        fixture = self.fixture
        target = fixture.clone_seed("rollback-rename")
        candidate = fixture.candidate(target, fixture.b)
        backup = fixture.backup(target, fixture.b)
        before = repo_state(target)
        original_rename = Path.rename

        def fail_candidate_rename(path: Path, destination: str | Path) -> Path:
            if path == candidate and Path(destination) == target:
                raise OSError("forced candidate rename failure")
            return original_rename(path, destination)

        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            with mock.patch.object(Path, "rename", new=fail_candidate_rename):
                with self.assertRaisesRegex(contract.ContractError, "original sibling restored from backup"):
                    contract.upgrade(fixture.runtime, target, fixture.b)
        self.assertIn("candidate retained", diagnostics.getvalue())
        self.assertEqual(repo_state(target), before)
        self.assertFalse(backup.exists())
        self.assertTrue(candidate.is_dir())

    def test_invalid_candidate_acceptance_refuses_without_swapping_directories(self) -> None:
        fixture = self.fixture
        missing = fixture.clone_seed("accept-missing")
        missing_before = repo_state(missing)
        with self.assertRaisesRegex(contract.ContractError, "candidate to accept does not exist"):
            contract.upgrade(fixture.runtime, missing, fixture.b, accept_candidate=True)
        self.assertEqual(repo_state(missing), missing_before)

        target = fixture.clone_seed("accept-unrelated")
        candidate = fixture.candidate(target, fixture.b)
        candidate.mkdir()
        git(candidate, "init", "-b", "main")
        write(candidate / "unrelated.txt", "unrelated candidate\n")
        git(candidate, "add", "unrelated.txt")
        git(candidate, "commit", "--quiet", "-m", "unrelated candidate")
        before = repo_state(target)
        with self.assertRaisesRegex(contract.ContractError, "does not descend from the original sibling"):
            contract.upgrade(fixture.runtime, target, fixture.b, accept_candidate=True)
        self.assertEqual(repo_state(target), before)


class ConsumerContractSourceRefTests(unittest.TestCase):
    def test_commit_outside_branches_and_tags_is_refused_before_copier(self) -> None:
        fixture = ConsumerFixture()
        self.addCleanup(fixture.close)
        runtime = fixture.runtime
        # The seed init already created the Copier mirror; its refresh fetches refs, not a detached HEAD.
        git(runtime, "checkout", "--quiet", "--detach", fixture.b)
        write(runtime / "copier_template" / MANAGED.replace(".md", ".md.jinja"), fixture._playbook("D"))
        fixture._commit("fixture D reachable only from a detached HEAD")
        detached = git(runtime, "rev-parse", "HEAD").stdout.strip()
        refusal = f"source commit {detached} is not on any branch or tag of the Planveyor runtime"

        target = fixture.clone_seed("detached-source")
        init_target = fixture.cases / "detached-init"
        target_before = repo_state(target)
        with mock.patch.object(contract, "copier_copy", side_effect=AssertionError("Copier must not run")):
            for accept_candidate in (False, True):
                with self.assertRaisesRegex(contract.ContractError, refusal):
                    contract.upgrade(runtime, target, detached, accept_candidate=accept_candidate)
            with self.assertRaisesRegex(contract.ContractError, refusal):
                contract.init(runtime, init_target, detached)
        self.assertEqual(repo_state(target), target_before)
        self.assertFalse(fixture.candidate(target, detached).exists())
        self.assertFalse(fixture.backup(target, detached).exists())
        self.assertFalse(init_target.exists())
        self.assertEqual([], list(fixture.cases.glob(f".{init_target.name}-init-*")))

        git(runtime, "branch", "detached-release", detached)
        self.assertEqual(contract.upgrade(runtime, target, detached)["state"], "updated_pending_adaptation")
        self.assertEqual(contract.init(runtime, init_target, detached)["state"], "ok")

        # Doctor renders the saved commit as well, so a branch or tag must keep containing it.
        git(runtime, "branch", "--delete", "--force", "detached-release")
        with self.assertRaisesRegex(contract.ContractError, refusal):
            contract.doctor(init_target, runtime)
        git(runtime, "tag", "detached-release", detached)
        self.assertEqual(contract.doctor(init_target, runtime)["state"], "ok")


class ConsumerContractFacadeTests(unittest.TestCase):
    """Exercise the public child facade, not only consumer_contract Python APIs."""

    def facade(self, runtime: Path, cwd: Path, *arguments: str,
               check: bool = True) -> subprocess.CompletedProcess[str]:
        env = _env()
        trusted_python = Path(env.get("PYBIN", sys.executable)).resolve()
        env["PYBIN"] = os.fspath(trusted_python)
        env["PATH"] = os.fspath(trusted_python.parent) + os.pathsep + env.get("PATH", "")
        return run([os.fspath(runtime / "bin" / "planveyor"), *arguments], cwd=cwd, check=check, env=env)

    def install_raw_local_bodies(self, target: Path) -> tuple[str, dict[str, bytes]]:
        relative = "docs/playbooks/review_staged_or_commit.md"
        local = target / relative
        body = local.read_bytes()
        raw_bodies: dict[str, bytes] = {}
        for index, heading in enumerate(contract.LOCAL_HEADINGS, start=1):
            heading_bytes = (heading + "\n").encode("utf-8")
            start = body.index(heading_bytes)
            end = body.find(b"## ", start + len(heading_bytes))
            if end == -1:
                end = len(body)
            raw_body = (heading + f"\r\nlocal=facade-{index}-kept-byte-for-byte\r\n").encode("utf-8")
            body = body[:start] + raw_body + body[end:]
            raw_bodies[heading] = raw_body
        local.write_bytes(body)
        return relative, raw_bodies

    def test_public_facade_init_doctor_and_compatible_upgrade(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-facade-") as tmpdir:
            root = Path(tmpdir).resolve()
            runtime = root / "runtime"
            self.addCleanup(shutil.rmtree, contract.copier_cache_home(runtime), True)
            elsewhere = root / "elsewhere"
            target = root / "facade-sibling"
            elsewhere.mkdir()
            run(["git", "clone", "--quiet", "--no-hardlinks", os.fspath(REPO_ROOT), os.fspath(runtime)])
            git(runtime, "remote", "remove", "origin")
            # Keep the source commit on a branch even when REPO_ROOT is a detached checkout (pull-request CI).
            git(runtime, "checkout", "--quiet", "-B", "main")
            shutil.copyfile(REPO_ROOT / "scripts" / "consumer_contract.py", runtime / "scripts" / "consumer_contract.py")
            git(runtime, "add", "scripts/consumer_contract.py")
            git(runtime, "commit", "--quiet", "--allow-empty", "-m", "facade fixture strict notice reader")
            source_a = git(runtime, "rev-parse", "HEAD").stdout.strip()

            initialized = self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(target),
                "--source-commit",
                source_a,
            )
            init_payload = json.loads(initialized.stdout)
            self.assertEqual(init_payload["state"], "ok")
            self.assertEqual(init_payload["target"], os.fspath(target))
            self.assertEqual(
                json.loads((target / contract.MARKER).read_text(encoding="utf-8"))["source_commit"],
                source_a,
            )
            self.assertEqual(
                set(
                    git(
                        target,
                        "ls-files",
                        "--error-unmatch",
                        contract.ANSWERS,
                        contract.MARKER,
                    ).stdout.splitlines()
                ),
                {os.fspath(contract.ANSWERS), os.fspath(contract.MARKER)},
            )
            # Init delivers the stack brief template and the plan skill, never the brief or a plan.
            template_brief = Path("docs") / "_template_stack_brief.md"
            draft_skill = Path(".agents") / "skills" / "planveyor-plan-draft" / "SKILL.md"
            for relative in (template_brief, draft_skill):
                self.assertEqual(
                    (target / relative).read_bytes(),
                    (runtime / "copier_template" / relative).read_bytes(),
                    relative,
                )
            self.assertFalse((target / "docs" / "stack_brief.md").exists())
            self.assertEqual(
                ["README.md", "_template.md"],
                sorted(path.name for path in (target / "docs" / "plans").iterdir()),
            )

            ignore = Path(
                git(target, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip()
            )
            with ignore.open("a", encoding="utf-8") as handle:
                handle.write(".tmp/\n")
            ignored_marker = target / ".tmp" / "cache" / "marker.txt"
            ignored_reject = target / ".tmp" / "cache" / "marker.rej"
            write(ignored_marker, "<<<<<<< ours\n=======\n>>>>>>> theirs\n")
            write(ignored_reject, "synthetic ignored reject\n")
            for path in (ignored_marker, ignored_reject):
                self.assertEqual(
                    git(target, "check-ignore", "-q", os.fspath(path.relative_to(target)), check=False).returncode,
                    0,
                )

            write(target / ".env.local", "local fixture state\n")
            write(target / ".planveyor.runtime-state.json", "local runtime state\n")
            local_relative, raw_local_bodies = self.install_raw_local_bodies(target)
            brief_text = "# Анкета стека\n\nsibling-owned brief\n"
            sibling_plan_relative = Path("docs") / "plans" / "260929_1200_stack_adaptation.md"
            sibling_plan_text = "# sibling-owned adaptation plan\n"
            write(target / "docs" / "stack_brief.md", brief_text)
            write(target / sibling_plan_relative, sibling_plan_text)
            git(target, "add", local_relative, "docs/stack_brief.md", os.fspath(sibling_plan_relative))
            git(target, "commit", "--quiet", "-m", "preserve raw local facade body")
            self.assertEqual(git(target, "status", "--porcelain=v1", "--untracked-files=all").stdout, "")
            before_doctor = repo_state(target)
            diagnosed = self.facade(
                runtime,
                elsewhere,
                "--project",
                os.fspath(target),
                "planveyor_consumer_doctor",
            )
            doctor_payload = json.loads(diagnosed.stdout)
            self.assertEqual(doctor_payload["state"], "ok")
            self.assertEqual(doctor_payload["target"], os.fspath(target))
            self.assertEqual(repo_state(target), before_doctor, "facade doctor must be read-only")

            revision_marker = "<!-- consumer facade fixture revision B -->\n"
            with (runtime / "copier_template" / "docs" / "README.md.jinja").open("a", encoding="utf-8") as handle:
                handle.write(revision_marker)
            for relative in (template_brief, draft_skill):
                with (runtime / "copier_template" / relative).open("a", encoding="utf-8") as handle:
                    handle.write(revision_marker)
            notice_relative = "docs/contract_notices/2026-09-26-facade-valid.json"
            write(
                runtime / notice_relative,
                json.dumps(
                    {
                        "summary": "Facade fixture проверяет strict notice reader.",
                        "contract_changes": ["docs/README.md"],
                        "engine_changes": ["scripts/consumer_contract.py"],
                        "sibling_actions": ["Проверить локальный план адаптации."],
                        "checks": ["Запустить consumer doctor."],
                    },
                    ensure_ascii=False,
                ) + "\n",
            )
            git(
                runtime,
                "add",
                "copier_template/docs/README.md.jinja",
                os.fspath(Path("copier_template") / template_brief),
                os.fspath(Path("copier_template") / draft_skill),
                notice_relative,
            )
            git(runtime, "commit", "--quiet", "-m", "facade fixture B")
            source_b = git(runtime, "rev-parse", "HEAD").stdout.strip()
            before_upgrade = repo_state(target)
            upgraded = self.facade(
                runtime,
                elsewhere,
                "--project",
                os.fspath(target),
                "planveyor_contract_upgrade",
                "--source-commit",
                source_b,
            )
            upgrade_payload = json.loads(upgraded.stdout)
            candidate = target.parent / f".{target.name}-upgrade-{source_b[:12]}"
            backup = target.parent / f".{target.name}-before-{source_b[:12]}"
            self.assertEqual(upgrade_payload["state"], "updated_pending_adaptation")
            self.assertEqual(upgrade_payload["target"], os.fspath(target))
            self.assertEqual(upgrade_payload["backup"], os.fspath(backup))
            self.assertIn("Finish active sibling role and shell sessions", upgraded.stderr)
            self.assertEqual(repo_state(backup), before_upgrade)
            self.assertFalse(candidate.exists())
            self.assertIn(revision_marker, (target / "docs" / "README.md").read_text(encoding="utf-8"))
            # Upgrade refreshes managed templates and skills and leaves sibling-owned files alone.
            for relative in (template_brief, draft_skill):
                self.assertTrue((target / relative).read_text(encoding="utf-8").endswith(revision_marker), relative)
            self.assertEqual((target / "docs" / "stack_brief.md").read_text(encoding="utf-8"), brief_text)
            self.assertEqual((target / sibling_plan_relative).read_text(encoding="utf-8"), sibling_plan_text)
            self.assertEqual(
                contract.local_sections(target, {local_relative})[local_relative],
                raw_local_bodies,
            )
            self.assertEqual(
                contract.local_sections(backup, {local_relative})[local_relative],
                raw_local_bodies,
            )
            self.assertEqual((target / ".env.local").read_text(encoding="utf-8"), "local fixture state\n")
            self.assertEqual(
                (target / ".planveyor.runtime-state.json").read_text(encoding="utf-8"),
                "local runtime state\n",
            )
            status = git(target, "status", "--porcelain=v1", "--untracked-files=all").stdout
            self.assertNotIn(".env.local", status)
            self.assertNotIn(".planveyor.runtime-state.json", status)
            plan = Path(str(upgrade_payload["plan"]))
            self.assertTrue(plan.is_file())
            plan_text = plan.read_text(encoding="utf-8")
            self.assertIn(source_a, plan_text)
            self.assertIn(source_b, plan_text)
            self.assertIn(notice_relative, plan_text)
            selected_notice = next(item for item in upgrade_payload["notices"] if item["path"] == notice_relative)
            self.assertEqual(selected_notice["commit"], source_b)

            after_upgrade_doctor = repo_state(target)
            checked = self.facade(
                runtime,
                elsewhere,
                "--project",
                os.fspath(target),
                "planveyor_consumer_doctor",
            )
            self.assertEqual(json.loads(checked.stdout)["state"], "ok")
            self.assertEqual(repo_state(target), after_upgrade_doctor, "facade doctor must remain read-only")

    def test_public_facade_malformed_notice_refuses_before_any_sibling_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-facade-invalid-") as tmpdir:
            root = Path(tmpdir).resolve()
            runtime = root / "runtime"
            self.addCleanup(shutil.rmtree, contract.copier_cache_home(runtime), True)
            elsewhere = root / "elsewhere"
            target = root / "facade-invalid-notice"
            elsewhere.mkdir()
            run(["git", "clone", "--quiet", "--no-hardlinks", os.fspath(REPO_ROOT), os.fspath(runtime)])
            git(runtime, "remote", "remove", "origin")
            # Keep the source commit on a branch even when REPO_ROOT is a detached checkout (pull-request CI).
            git(runtime, "checkout", "--quiet", "-B", "main")
            shutil.copyfile(REPO_ROOT / "scripts" / "consumer_contract.py", runtime / "scripts" / "consumer_contract.py")
            git(runtime, "add", "scripts/consumer_contract.py")
            git(runtime, "commit", "--quiet", "--allow-empty", "-m", "facade fixture strict notice reader")
            source_a = git(runtime, "rev-parse", "HEAD").stdout.strip()

            self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(target),
                "--source-commit",
                source_a,
            )
            local_relative, raw_local_bodies = self.install_raw_local_bodies(target)
            git(target, "add", local_relative)
            git(target, "commit", "--quiet", "-m", "preserve raw local malformed-notice body")

            notice_relative = "docs/contract_notices/2026-09-26-facade-malformed.json"
            write(runtime / notice_relative, "{not-json\n")
            git(runtime, "add", notice_relative)
            git(runtime, "commit", "--quiet", "-m", "facade malformed notice")
            source_b = git(runtime, "rev-parse", "HEAD").stdout.strip()
            source_before = repo_state(runtime)
            target_before = repo_state(target)

            rejected = self.facade(
                runtime,
                elsewhere,
                "--project",
                os.fspath(target),
                "planveyor_contract_upgrade",
                "--source-commit",
                source_b,
                check=False,
            )
            self.assertEqual(rejected.returncode, 3)
            blocked_lines = [line for line in rejected.stderr.splitlines() if line.strip().startswith("{")]
            self.assertTrue(blocked_lines)
            blocked = json.loads(blocked_lines[-1])
            self.assertEqual(blocked["state"], "blocked")
            self.assertIn(f"{notice_relative}@{source_b}", blocked["reason"])
            self.assertEqual(repo_state(runtime), source_before)
            self.assertEqual(repo_state(target), target_before)
            self.assertEqual(
                contract.local_sections(target, {local_relative})[local_relative],
                raw_local_bodies,
            )
            self.assertFalse((target.parent / f".{target.name}-upgrade-{source_b[:12]}").exists())
            self.assertFalse((target.parent / f".{target.name}-before-{source_b[:12]}").exists())


class ConsumerContractInitIdentityFacadeTests(unittest.TestCase):
    OWNER_NAME = "fixture-owner"
    OWNER_EMAIL = "fixture-owner+tag@example.invalid"

    def facade(self, runtime: Path, cwd: Path, *arguments: str,
               check: bool = True) -> subprocess.CompletedProcess[str]:
        env = _env()
        trusted_python = Path(env.get("PYBIN", sys.executable)).resolve()
        env["PYBIN"] = os.fspath(trusted_python)
        env["PATH"] = os.fspath(trusted_python.parent) + os.pathsep + env.get("PATH", "")
        return run([os.fspath(runtime / "bin" / "planveyor"), *arguments], cwd=cwd, check=check, env=env)

    def assert_identity(self, target: Path, name: str, email: str) -> None:
        self.assertEqual(commit_identity(target), (name, email, name, email))
        config = (target / ".git" / "config").read_text(encoding="utf-8")
        self.assertNotIn("[user]", config)
        self.assertNotIn("[author]", config)
        self.assertNotIn("[committer]", config)

    def test_public_facade_forwards_optional_identity_and_preserves_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="consumer-facade-identity-", dir=_physical_tempdir()) as tmpdir:
            root = Path(tmpdir).resolve()
            runtime = root / "runtime"
            self.addCleanup(shutil.rmtree, contract.copier_cache_home(runtime), True)
            elsewhere = root / "elsewhere"
            selected_target = root / "facade-selected"
            fallback_target = root / "facade-fallback"
            rejected_target = root / "facade-rejected"
            missing_value_target = root / "facade-missing-value"
            elsewhere.mkdir()
            run(["git", "clone", "--quiet", "--no-hardlinks", os.fspath(REPO_ROOT), os.fspath(runtime)])
            git(runtime, "remote", "remove", "origin")
            # Keep the source commit on a branch even when REPO_ROOT is a detached checkout (pull-request CI).
            git(runtime, "checkout", "--quiet", "-B", "main")
            shutil.copyfile(REPO_ROOT / "scripts" / "consumer_contract.py", runtime / "scripts" / "consumer_contract.py")
            git(runtime, "add", "scripts/consumer_contract.py")
            git(runtime, "commit", "--quiet", "--allow-empty", "-m", "facade fixture explicit init identity")
            source_commit = git(runtime, "rev-parse", "HEAD").stdout.strip()

            help_result = self.facade(runtime, elsewhere, "planveyor_consumer_init", "--help", check=False)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("--author-name", help_result.stdout)
            self.assertIn("--author-email", help_result.stdout)

            selected = self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(selected_target),
                "--source-commit",
                source_commit,
                "--author-name",
                self.OWNER_NAME,
                "--author-email",
                self.OWNER_EMAIL,
            )
            self.assertEqual(json.loads(selected.stdout)["state"], "ok")
            self.assertNotIn("note: init commit author", selected.stderr)
            self.assert_identity(selected_target, self.OWNER_NAME, self.OWNER_EMAIL)
            self.assertEqual(
                json.loads((selected_target / contract.MARKER).read_text(encoding="utf-8"))["source_commit"],
                source_commit,
            )
            selected_answers = contract.yaml.safe_load(
                (selected_target / contract.ANSWERS).read_text(encoding="utf-8")
            )
            self.assertIsInstance(selected_answers, dict)
            self.assertEqual(contract.resolve_answer_ref(runtime, selected_answers["_commit"]), source_commit)

            fallback = self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(fallback_target),
                "--source-commit",
                source_commit,
            )
            self.assertEqual(json.loads(fallback.stdout)["state"], "ok")
            self.assertIn(
                f"note: init commit author is {contract.INIT_AUTHOR_NAME} <{contract.INIT_AUTHOR_EMAIL}>; "
                "pass --author-name and --author-email together",
                fallback.stderr,
            )
            self.assert_identity(fallback_target, contract.INIT_AUTHOR_NAME, contract.INIT_AUTHOR_EMAIL)

            rejected = self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(rejected_target),
                "--source-commit",
                source_commit,
                "--author-name",
                "Facade Name",
                "--author-email",
                "not an email",
                check=False,
            )
            self.assertEqual(rejected.returncode, 3)
            blocked_lines = [line for line in rejected.stderr.splitlines() if line.strip().startswith("{")]
            self.assertTrue(blocked_lines)
            self.assertEqual(json.loads(blocked_lines[-1])["state"], "blocked")
            self.assertFalse(rejected_target.exists())
            self.assertFalse(list(rejected_target.parent.glob(f".{rejected_target.name}-init-*")))

            missing_value = self.facade(
                runtime,
                elsewhere,
                "planveyor_consumer_init",
                os.fspath(missing_value_target),
                "--source-commit",
                source_commit,
                "--author-name",
                check=False,
            )
            self.assertEqual(missing_value.returncode, 2)
            self.assertIn("argument --author-name: expected one argument", missing_value.stderr)
            self.assertFalse(missing_value_target.exists())


if __name__ == "__main__":
    unittest.main()

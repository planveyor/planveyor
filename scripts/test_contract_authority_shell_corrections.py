#!/usr/bin/env python3
"""Focused P1 regression coverage for Authority Package B shell corrections.

Every case runs a copied candidate runtime against a disposable Git target.
The only launch boundaries are shell-local or fixture-owned fake providers;
no real HOME, provider, Manager, or queue is used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_context
from test_contract_authority_support import AuthorityFixture, commit_all, git, write


class AuthorityBShellCorrectionTests(unittest.TestCase):
    """Exercise the P1 shell paths with fixture-local selector/runtime binding."""

    def _enable_isolated_admission(self, fixture: AuthorityFixture) -> None:
        """Enable admission only in the copied runtime when a base keeps it closed."""

        context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = context_path.read_text(encoding="utf-8")
        incomplete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False"
        complete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True"
        if incomplete in original:
            context_path.write_text(original.replace(incomplete, complete, 1), encoding="utf-8")
            fixture.runtime_commit = commit_all(fixture.runtime_root, "fixture engaged admission")
        else:
            self.assertIn(complete, original)

    def _run_shell(
        self,
        fixture: AuthorityFixture,
        command: str,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PYBIN"] = str(Path(sys.executable).resolve())
        if extra_env:
            environment.update(extra_env)
        facade = shlex.quote(str(fixture.runtime_root / "scripts" / "planveyor.zsh"))
        return subprocess.run(
            ["/bin/zsh", "-fc", fixture.shell_loader() + f"planveyor_source_runtime {facade} || exit $?; {command}"],
            cwd=fixture.target_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )

    @staticmethod
    def _sid(serial: int) -> str:
        return f"00000000-0000-4000-8000-{serial:012x}"

    @staticmethod
    def _receipt_path(fixture: AuthorityFixture, sid: str) -> Path:
        return fixture.target_root / ".planveyor.init_runs" / "by_sid" / sid / "meta.json"

    def _seed_bound_sid(
        self,
        fixture: AuthorityFixture,
        *,
        role: str,
        session_key: str,
        sid: str,
    ) -> dict[str, object]:
        """Use the real capture/finalize path without launching a provider."""

        role_q = shlex.quote(role)
        key_q = shlex.quote(session_key)
        sid_q = shlex.quote(sid)
        command = textwrap.dedent(
            f"""\
            authority_b_seed_receipt() {{
              emulate -L zsh
              local context="$(_planveyor_pre_dispatch authority_b_seed_receipt)" || return $?
              local state="$(_planveyor_authority_context_field "$context" state)" || return $?
              local root="$(_planveyor_authority_context_field "$context" project_root)" || return $?
              local generation="$(_planveyor_authority_context_field "$context" generation_sha256)" || return $?
              local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
              local -r PLANVEYOR_CTX_ROOT="$root"
              local -r PLANVEYOR_CTX_GENERATION="$generation"
              local -r PLANVEYOR_CTX_JSON="$context"
              local -r PLANVEYOR_CTX_STATE="$state"
              local capture_dir="$(_planveyor_init_run_capture_begin {role_q})" || return $?
              local out="Fake Codex session {sid_q}"
              _planveyor_save_session_key_from_output {key_q} "$out" 'runner=codex profile=test' || return $?
              _planveyor_init_run_capture_finalize "$capture_dir" {role_q} {key_q} codex test '' "$out" 0 "${{_PLANVEYOR_LAST_SAVED_SESSION_ID:-}}" '' '' '' '' '' '' '' 'runner=codex profile=test'
            }}
            authority_b_seed_receipt
            """
        )
        result = self._run_shell(fixture, command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt_path = self._receipt_path(fixture, sid)
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["sid"], sid)
        self.assertEqual(receipt["session_key"], session_key)
        self.assertEqual(receipt["authority_context"]["state"], "engaged")
        return receipt

    @staticmethod
    def _install_rollout(fixture: AuthorityFixture, *, sid: str, codex_home: Path) -> None:
        rollout = codex_home / "sessions" / "2026" / "09" / f"rollout-2026-09-08T00-00-00-{sid}.jsonl"
        rollout.parent.mkdir(parents=True, exist_ok=True)
        rollout.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "timestamp": "2026-09-08T00:00:00Z",
                        "cwd": str(fixture.target_root),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _shell_codex_seam() -> str:
        return textwrap.dedent(
            """\
            _planveyor_codex() {
              local pointer=absent
              [[ -e "${PLANVEYOR_TEST_POINTER_PATH:-}" ]] && pointer=present
              print -r -- "${pointer}:$*" >> "${PLANVEYOR_TEST_PROVIDER_LOG:?}"
              return "${PLANVEYOR_TEST_PROVIDER_RC:-0}"
            }
            """
        )

    def _fake_claude_environment(self, fixture: AuthorityFixture, log_path: Path) -> dict[str, str]:
        fake_bin = fixture.root / "fake-bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        provider = fake_bin / "claude"
        provider.write_text(
            "#!/bin/sh\n"
            "pointer=absent\n"
            "if [ -n \"${PLANVEYOR_TEST_POINTER_PATH:-}\" ] && [ -e \"$PLANVEYOR_TEST_POINTER_PATH\" ]; then pointer=present; fi\n"
            "printf '%s\\n' \"$pointer\" >> \"${PLANVEYOR_TEST_PROVIDER_LOG:?}\"\n"
            "exit \"${PLANVEYOR_TEST_PROVIDER_RC:-0}\"\n",
            encoding="utf-8",
        )
        provider.chmod(0o755)
        return {
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "PLANVEYOR_TEST_PROVIDER_LOG": str(log_path),
            "PLANVEYOR_TEST_PROVIDER_RC": "0",
            "PLANVEYOR_TEST_POINTER_PATH": str(fixture.target_root / ".planveyor.session.planner"),
        }

    def test_track_routes_reject_unbound_sid_and_resume_bound_sid(self) -> None:
        routes = (
            (
                "direct_track",
                "architect_process_roles",
                "_planveyor_arch_track_tui architect_process_roles docs/tools/prompts/architect_track_process_roles.md track_process_roles",
            ),
            ("roles_alias", "architect_process_roles", "planveyor_arch_roles_resume"),
            ("collab_alias", "architect_process_collab", "planveyor_arch_collab_resume"),
            ("innovations_alias", "architect_innovations", "planveyor_arch_inno_resume"),
        )

        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            provider_log = fixture.root / "track-provider.log"
            provider_env = {
                "PLANVEYOR_TEST_PROVIDER_LOG": str(provider_log),
                "PLANVEYOR_TEST_PROVIDER_RC": "0",
            }

            for serial, (name, session_key, route) in enumerate(routes, start=0xB101):
                with self.subTest(route=name, phase="unbound"):
                    sid = self._sid(serial)
                    pointer = fixture.target_root / f".planveyor.session.{session_key}"
                    write(pointer.parent, pointer.name, f"# unbound fixture pointer\n{sid}\n")
                    provider_log.unlink(missing_ok=True)
                    blocked = self._run_shell(
                        fixture,
                        self._shell_codex_seam() + "\n" + route,
                        extra_env={
                            **provider_env,
                            "PLANVEYOR_TEST_POINTER_PATH": str(pointer),
                        },
                    )
                    self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
                    self.assertFalse(provider_log.exists(), blocked.stdout + blocked.stderr)
                    self.assertEqual(pointer.read_text(encoding="utf-8").splitlines()[-1], sid)

                with self.subTest(route=name, phase="bound"):
                    bound_sid = self._sid(serial + 0x100)
                    receipt = self._seed_bound_sid(
                        fixture,
                        role="architect",
                        session_key=session_key,
                        sid=bound_sid,
                    )
                    provider_log.unlink(missing_ok=True)
                    resumed = self._run_shell(
                        fixture,
                        self._shell_codex_seam() + "\n" + route,
                        extra_env={
                            **provider_env,
                            "PLANVEYOR_TEST_POINTER_PATH": str(
                                fixture.target_root / f".planveyor.session.{session_key}"
                            ),
                        },
                    )
                    self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
                    self.assertEqual(provider_log.read_text(encoding="utf-8").count("resume"), 1)
                    self.assertEqual(receipt["sid"], bound_sid)

    def test_architect_special_starts_reject_unbound_sid_before_provider(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            base = git(fixture.target_root, "rev-parse", "HEAD")
            codex_home = fixture.root / "codex-home"
            provider_log = fixture.root / "special-provider.log"
            provider_env = {
                "PLANVEYOR_CODEX_HOME": str(codex_home),
                "PLANVEYOR_TEST_PROVIDER_LOG": str(provider_log),
                "PLANVEYOR_TEST_PROVIDER_RC": "0",
                "PLANVEYOR_TEST_POINTER_PATH": str(fixture.target_root / ".planveyor.session.architect"),
            }
            routes = (
                ("merge_notes", f"planveyor_arch_merge_notes_start {base} {base} docs/reviews/fixture_merge_notes.md"),
                ("plan_harvest", f"planveyor_arch_plan_harvest_start {base} {base} docs/reviews/fixture_plan_harvest.md"),
                ("post_merge_audit", f"planveyor_arch_post_merge_audit_start {base} {base} docs/reviews/fixture_post_merge_audit.md"),
                ("canon_sweep", f"planveyor_arch_canon_sweep_start {base} {base}"),
            )

            for serial, (name, route) in enumerate(routes, start=0xB201):
                with self.subTest(route=name, phase="unbound"):
                    sid = self._sid(serial)
                    pointer = fixture.target_root / ".planveyor.session.architect"
                    write(pointer.parent, pointer.name, f"# unbound fixture pointer\n{sid}\n")
                    self._install_rollout(fixture, sid=sid, codex_home=codex_home)
                    provider_log.unlink(missing_ok=True)
                    blocked = self._run_shell(
                        fixture,
                        self._shell_codex_seam() + "\n" + route,
                        extra_env=provider_env,
                    )
                    self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
                    self.assertFalse(provider_log.exists(), blocked.stdout + blocked.stderr)
                    self.assertEqual(pointer.read_text(encoding="utf-8").splitlines()[-1], sid)

                with self.subTest(route=name, phase="bound"):
                    bound_sid = self._sid(serial + 0x100)
                    receipt = self._seed_bound_sid(
                        fixture,
                        role="architect",
                        session_key="architect",
                        sid=bound_sid,
                    )
                    self._install_rollout(fixture, sid=bound_sid, codex_home=codex_home)
                    provider_log.unlink(missing_ok=True)
                    resumed = self._run_shell(
                        fixture,
                        self._shell_codex_seam() + "\n" + route,
                        extra_env=provider_env,
                    )
                    self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
                    self.assertEqual(provider_log.read_text(encoding="utf-8").count("resume"), 1)
                    self.assertEqual(receipt["sid"], bound_sid)

    @staticmethod
    def _legacy_architect_prompt_seam() -> str:
        # Isolate legacy session control flow from profile-content packaging.
        # Authority, provider, capture, SID lookup and publication stay real
        # unless the individual regression explicitly supplies a fault seam.
        return (
            '_planveyor_prompt_file_for_role_phase() { print -r -- "docs/tools/prompts/architect_${2}.md"; }\n'
            "_planveyor_role_prompt_body() { print -r -- 'fixture Architect prompt'; }\n"
        )

    def test_track_and_special_starts_reject_directory_pointer_before_provider(self) -> None:
        for engaged in (False, True):
            with self.subTest(engaged=engaged), AuthorityFixture(identity="planveyor") as fixture:
                if engaged:
                    self._enable_isolated_admission(fixture)
                    fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                base = git(fixture.target_root, "rev-parse", "HEAD")
                routes = (
                    ("architect_process_roles", "planveyor_arch_process_roles_tui"),
                    ("architect", f"planveyor_arch_merge_notes_start {base} {base} docs/reviews/notes.md"),
                    ("architect", f"planveyor_arch_plan_harvest_start {base} {base} docs/reviews/harvest.md"),
                    ("architect", f"planveyor_arch_post_merge_audit_start {base} {base} docs/reviews/audit.md"),
                    ("architect", f"planveyor_arch_canon_sweep_start {base} {base}"),
                )
                for index, (key, route) in enumerate(routes):
                    with self.subTest(route=route):
                        pointer = fixture.target_root / f".planveyor.session.{key}"
                        pointer.mkdir(exist_ok=True)
                        provider_log = fixture.root / f"directory-provider-{index}.log"
                        result = self._run_shell(
                            fixture,
                            self._shell_codex_seam()
                            + ("" if engaged else "\n" + self._legacy_architect_prompt_seam())
                            + "\n_planveyor_latest_codex_sid_for_cwd_prefix() { return 0; }\n"
                            + route,
                            extra_env={
                                "PLANVEYOR_TEST_PROVIDER_LOG": str(provider_log),
                                "PLANVEYOR_TEST_POINTER_PATH": str(pointer),
                            },
                        )
                        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("Invalid session pointer", result.stderr)
                        self.assertFalse(provider_log.exists(), result.stdout + result.stderr)
                        self.assertTrue(pointer.is_dir())
                        self.assertEqual(list(pointer.iterdir()), [])
                        self.assertFalse(pointer.with_name(pointer.name + ".log").exists())
                        self.assertNotIn("Saved:", result.stderr)

    def test_session_set_rejects_nonregular_destination_without_false_save(self) -> None:
        for kind in ("directory", "dangling_symlink", "regular_symlink", "fifo"):
            with self.subTest(kind=kind), AuthorityFixture(identity="planveyor") as fixture:
                pointer = fixture.target_root / ".planveyor.session.architect"
                referent = fixture.root / "pointer-referent"
                if kind == "directory":
                    pointer.mkdir()
                elif kind == "fifo":
                    os.mkfifo(pointer)
                else:
                    if kind == "regular_symlink":
                        referent.write_text("preserve referent\n", encoding="utf-8")
                    pointer.symlink_to(referent)
                before = pointer.lstat()
                result = self._run_shell(fixture, f"planveyor_session_set architect {self._sid(0xB250)}")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Invalid session pointer destination", result.stderr)
                self.assertEqual(pointer.lstat().st_ino, before.st_ino)
                self.assertEqual(pointer.lstat().st_mode, before.st_mode)
                if kind == "directory":
                    self.assertEqual(list(pointer.iterdir()), [])
                if kind == "regular_symlink":
                    self.assertEqual(referent.read_text(), "preserve referent\n")
                if kind == "dangling_symlink":
                    self.assertFalse(referent.exists())
                self.assertFalse(pointer.with_name(pointer.name + ".log").exists())
                self.assertFalse(list(pointer.parent.glob(pointer.name + ".tmp.*")))
                self.assertNotIn("Saved:", result.stderr)

    def test_session_set_replaces_exact_path_and_rejects_late_directory(self) -> None:
        for kind in ("absent", "regular", "late_directory"):
            with self.subTest(kind=kind), AuthorityFixture(identity="planveyor") as fixture:
                pointer = fixture.target_root / ".planveyor.session.architect"
                sid = self._sid(0xB251)
                if kind == "regular":
                    pointer.write_text("previous sid\n", encoding="utf-8")
                seam = ""
                if kind == "late_directory":
                    seam = textwrap.dedent(
                        """\
                        functions[_fixture_original_py_any]=$functions[_planveyor_py_any]
                        _planveyor_py_any() {
                          if [[ "$1" == -c && "$2" == *'os.replace('* ]]; then
                            mkdir -- "$4" || return $?
                          fi
                          _fixture_original_py_any "$@"
                        }
                        """
                    )
                result = self._run_shell(fixture, seam + f"planveyor_session_set architect {sid}")
                self.assertFalse(list(pointer.parent.glob(pointer.name + ".tmp.*")))
                log = pointer.with_name(pointer.name + ".log")
                if kind == "late_directory":
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(pointer.is_dir())
                    self.assertEqual(list(pointer.iterdir()), [])
                    self.assertFalse(log.exists())
                    self.assertIn("Failed to finalize session pointer", result.stderr)
                    self.assertNotIn("Saved:", result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(pointer.read_text().splitlines()[-1], sid)
                    self.assertEqual(log.read_text().splitlines()[0].split("\t")[1], sid)
                    self.assertEqual(result.stderr.count("Saved:"), 1)

    def test_legacy_track_missing_sid_preserves_provider_status(self) -> None:
        for capture_available in (False, True):
            for provider_rc in (0, 23):
                with self.subTest(capture=capture_available, provider_rc=provider_rc), AuthorityFixture(identity="planveyor") as fixture:
                    provider_log = fixture.root / "legacy-track-provider.log"
                    pointer = fixture.target_root / ".planveyor.session.architect_process_roles"
                    capture_override = "" if capture_available else "_planveyor_init_run_capture_begin() { return 0; }\n"
                    result = self._run_shell(
                        fixture,
                        self._shell_codex_seam()
                        + "\n" + self._legacy_architect_prompt_seam()
                        + "\n_planveyor_latest_codex_sid_for_cwd_prefix() { return 0; }\n"
                        + capture_override
                        + "planveyor_arch_process_roles_tui",
                        extra_env={
                            "PLANVEYOR_TEST_PROVIDER_LOG": str(provider_log),
                            "PLANVEYOR_TEST_PROVIDER_RC": str(provider_rc),
                            "PLANVEYOR_TEST_POINTER_PATH": str(pointer),
                        },
                    )
                    self.assertEqual(result.returncode, provider_rc, result.stdout + result.stderr)
                    self.assertEqual(len(provider_log.read_text().splitlines()), 1)
                    self.assertFalse(pointer.exists())
                    if provider_rc == 0:
                        self.assertIn("planveyor_session_set architect_process_roles", result.stderr)

    def test_fresh_two_argument_arch_track_rejects_unknown_prompt_before_role_start(self) -> None:
        """A legacy two-argument track call must not substitute a default phase."""

        with AuthorityFixture(identity="planveyor") as fixture:
            effects = fixture.root / "unexpected-role-start"
            unknown_prompt = "docs/tools/prompts/architect_track_unknown.md"
            pointer = fixture.target_root / ".planveyor.session.architect_process_roles"
            command = "\n".join(
                (
                    "_planveyor_role_prompt_body() {",
                    f"  print -r -- prompt-body >> {shlex.quote(str(effects))}",
                    "  print -r -- 'fixture Architect prompt'",
                    "}",
                    "_planveyor_init_run_capture_begin() {",
                    f"  print -r -- capture >> {shlex.quote(str(effects))}",
                    "  return 1",
                    "}",
                    "_planveyor_codex() {",
                    f"  print -r -- provider >> {shlex.quote(str(effects))}",
                    "  return 1",
                    "}",
                    "_planveyor_latest_codex_sid_for_cwd_prefix() { return 1; }",
                    "_planveyor_arch_track_tui architect_process_roles " + shlex.quote(unknown_prompt),
                )
            )

            result = self._run_shell(fixture, command)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ERROR: unsupported fresh Architect track prompt:", result.stderr)
            self.assertIn(str(fixture.runtime_root / unknown_prompt), result.stderr)
            self.assertFalse(effects.exists(), result.stdout + result.stderr)
            self.assertFalse(pointer.exists())
            self.assertFalse((fixture.target_root / ".planveyor.init_runs").exists())

    def test_fresh_track_receipt_lifecycle_cannot_report_success_after_failure(self) -> None:
        cases = (
            ("success", self._sid(0xB301), 0, None, 0),
            ("provider_failure", self._sid(0xB302), 23, None, 23),
            ("finalize_failure", self._sid(0xB303), 0, 47, 47),
            ("missing_sid", "", 0, None, 1),
        )

        for name, sid, provider_rc, finalize_rc, expected_rc in cases:
            with self.subTest(case=name), AuthorityFixture(identity="planveyor") as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                provider_log = fixture.root / "fresh-track-provider.log"
                counter = fixture.root / "sid-counter"
                pointer = fixture.target_root / ".planveyor.session.architect_process_roles"
                finalize_override = ""
                if finalize_rc is not None:
                    finalize_override = (
                        "_planveyor_init_run_capture_finalize() { "
                        f"return {finalize_rc}; "
                        "}\n"
                    )
                command = textwrap.dedent(
                    f"""\
                    print -r -- 0 > {shlex.quote(str(counter))}
                    _planveyor_latest_codex_sid_for_cwd_prefix() {{
                      local count="$(< {shlex.quote(str(counter))})"
                      count=$(( count + 1 ))
                      print -r -- "$count" > {shlex.quote(str(counter))}
                      if (( count >= 2 )) && [[ -n "${{PLANVEYOR_TEST_TRACK_SID:-}}" ]]; then
                        print -r -- "$PLANVEYOR_TEST_TRACK_SID"
                      fi
                    }}
                    {finalize_override}
                    {self._shell_codex_seam()}
                    planveyor_arch_process_roles_tui
                    """
                )
                result = self._run_shell(
                    fixture,
                    command,
                    extra_env={
                        "PLANVEYOR_TEST_PROVIDER_LOG": str(provider_log),
                        "PLANVEYOR_TEST_PROVIDER_RC": str(provider_rc),
                        "PLANVEYOR_TEST_POINTER_PATH": str(pointer),
                        "PLANVEYOR_TEST_TRACK_SID": sid,
                    },
                )
                self.assertEqual(result.returncode, expected_rc, result.stdout + result.stderr)
                self.assertTrue(provider_log.is_file())
                self.assertIn("absent", provider_log.read_text(encoding="utf-8"))

                if name == "success":
                    receipt = json.loads(self._receipt_path(fixture, sid).read_text(encoding="utf-8"))
                    self.assertEqual(receipt["outcome"], "success")
                    self.assertEqual(receipt["session_key"], "architect_process_roles")
                    self.assertEqual(pointer.read_text(encoding="utf-8").splitlines()[-1], sid)
                elif name == "provider_failure":
                    receipt = json.loads(self._receipt_path(fixture, sid).read_text(encoding="utf-8"))
                    self.assertEqual(receipt["outcome"], "failed")
                    self.assertFalse(pointer.exists())
                else:
                    self.assertFalse(pointer.exists())

    @staticmethod
    def _raw_case_route(kind: str) -> str:
        cases = {
            "planner_run": "planveyor_planner",
            "planner_censor": "planveyor_planner_censor",
            "reviewer_run": "planveyor_reviewer",
            "planner_resume": "planveyor_planner_resume",
            "reviewer_resume": "planveyor_reviewer_resume",
            "planner_init": "planveyor_planner_init",
            "reviewer_init": "planveyor_reviewer_init",
        }
        return cases[kind]

    @staticmethod
    def _raw_fast_seam() -> str:
        """Keep the launch routes intact while removing unrelated role work."""

        return textwrap.dedent(
            """\
            _planveyor_role_prompt_body() { print -r -- 'fixture prompt'; }
            planveyor_planpath() { print -r -- 'docs/plans/fixture.md'; }
            planveyor_session() { print -r -- '00000000-0000-4000-8000-00000000b4ff'; }
            _planveyor_session_authority_resume_validate() { return 0; }
            _planveyor_resolve_pybin_for_role() { print -r -- "${PYBIN:?}"; }
            planveyor_runner() { print -r -- claude; }
            _planveyor_profile_for_role_mode() { print -r -- fixture; }
            _planveyor_consume_owner_answers_for() { return 0; }
            _planveyor_peek_owner_answers_for() { return 0; }
            planveyor_status_line() { print -r -- '1:**Status:** Planner finalize'; }
            _planveyor_censor_handoff_status_for_role() { return 0; }
            _planveyor_model_identity_payload_args() { return 0; }
            _planveyor_model_identity_value() { return 0; }
            _planveyor_now_utc_iso() { print -r -- '2026-09-08T00:00:00Z'; }
            _planveyor_review_receipt_emit() { return 0; }
            _planveyor_py_any() { cat; }
            _planveyor_runner_selection_init_resolve() { print -r -- $'claude\\tfixture'; }
            _planveyor_prepare_role_bundle() { return 0; }
            _planveyor_uuid4() { print -r -- '00000000-0000-4000-8000-00000000b4ff'; }
            _planveyor_init_run_capture_begin() { print -r -- "${TMPDIR:-/tmp}/planveyor-fast-capture"; }
            _planveyor_init_run_capture_finalize() { return 0; }
            """
        )

    @staticmethod
    def _late_drift_seam(kind: str) -> str:
        update_selector = (
            "import json, pathlib, sys; "
            "path = pathlib.Path(sys.argv[1]); "
            "selector = json.loads(path.read_text()); "
            "selector['required_runtime_api'] = {'minimum': 4, 'maximum': 5}; "
            "path.write_text(json.dumps(selector, sort_keys=True) + '\\n')"
        )
        mutate = (
            f'command "${{PYBIN:?}}" -c {shlex.quote(update_selector)} "${{PLANVEYOR_TEST_MUTATE_PATH:?}}" || return $?\n'
            "PLANVEYOR_TEST_DRIFT_DONE=1\n"
        )
        if kind in {"planner_run", "planner_censor", "reviewer_run"}:
            return textwrap.dedent(
                f"""\
                planveyor_status_line() {{
                  if [[ -z "${{PLANVEYOR_TEST_DRIFT_DONE:-}}" ]]; then
                    {textwrap.indent(mutate.rstrip(), '    ')}
                  fi
                  print -r -- '1:**Status:** Planner finalize'
                }}
                """
            )
        if kind in {"planner_resume", "reviewer_resume"}:
            return textwrap.dedent(
                f"""\
                pushd() {{
                  if [[ -z "${{PLANVEYOR_TEST_DRIFT_DONE:-}}" ]]; then
                    {textwrap.indent(mutate.rstrip(), '    ')}
                  fi
                  builtin pushd "$@"
                }}
                """
            )
        if kind in {"planner_init", "reviewer_init"}:
            return textwrap.dedent(
                f"""\
                _planveyor_init_run_capture_begin() {{
                  if [[ -z "${{PLANVEYOR_TEST_DRIFT_DONE:-}}" ]]; then
                    {textwrap.indent(mutate.rstrip(), '    ')}
                  fi
                  print -r -- "${{TMPDIR:-/tmp}}/planveyor-fast-capture"
                }}
                """
            )
        raise AssertionError(f"unknown raw Claude case: {kind}")

    def test_all_raw_claude_sinks_revalidate_the_frozen_context(self) -> None:
        kinds = (
            "planner_run",
            "planner_censor",
            "reviewer_run",
            "planner_resume",
            "reviewer_resume",
            "planner_init",
            "reviewer_init",
        )

        for kind in kinds:
            with self.subTest(sink=kind, phase="positive"), AuthorityFixture(identity="planveyor") as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                route = self._raw_case_route(kind)
                provider_log = fixture.root / "raw-claude-positive.log"
                result = self._run_shell(
                    fixture,
                    self._raw_fast_seam() + "\n" + route,
                    extra_env=self._fake_claude_environment(fixture, provider_log),
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(provider_log.is_file(), result.stdout + result.stderr)
                self.assertEqual(len(provider_log.read_text(encoding="utf-8").splitlines()), 1)

            with self.subTest(sink=kind, phase="late_drift"), AuthorityFixture(identity="planveyor") as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                route = self._raw_case_route(kind)
                provider_log = fixture.root / "raw-claude-drift.log"
                mutated = fixture.target_root / source_context._snapshot.MARKER_PATH
                before = mutated.read_bytes()
                result = self._run_shell(
                    fixture,
                    self._raw_fast_seam() + "\n" + self._late_drift_seam(kind) + "\n" + route,
                    extra_env={
                        **self._fake_claude_environment(fixture, provider_log),
                        "PLANVEYOR_TEST_MUTATE_PATH": str(mutated),
                    },
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotEqual(mutated.read_bytes(), before)
                selector = json.loads(mutated.read_text(encoding="utf-8"))
                self.assertEqual(selector["required_runtime_api"], {"minimum": 4, "maximum": 5})
                self.assertFalse(provider_log.exists(), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

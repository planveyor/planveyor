#!/usr/bin/env python3
"""Disposable end-to-end coverage for Package B session authority binding.

The fixture runtime is a separate Git checkout.  Before the repository-wide
admission census flips the reviewed gate, a test may enable that copied runtime
only; production bytes and environment are never bypassed.  All provider calls
are handled by a local fake executable.
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
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_context
from authority_bootstrap_test_support import run_bootstrapped_bridge
from test_contract_authority_support import AuthorityFixture, commit_all, git, write


ARCHITECT_SID = "00000000-0000-4000-8000-00000000a701"
FAILED_SID = "00000000-0000-4000-8000-00000000a702"
MANAGER_SID = "00000000-0000-4000-8000-00000000a703"


class ContractAuthoritySessionTests(unittest.TestCase):
    def _enable_isolated_admission(self, fixture: AuthorityFixture) -> None:
        """Flip only the copied runtime's reviewed constant for this fixture."""

        context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = context_path.read_text(encoding="utf-8")
        incomplete_gate = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False"
        complete_gate = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True"
        if incomplete_gate in original:
            context_path.write_text(
                original.replace(incomplete_gate, complete_gate, 1),
                encoding="utf-8",
            )
        else:
            self.assertIn(complete_gate, original)
        policy = SCRIPT_DIR.parent / "docs" / "_meta" / "runner_selection_resolution.v1.json"
        write(
            fixture.runtime_root,
            "docs/_meta/runner_selection_resolution.v1.json",
            policy.read_bytes(),
        )
        fixture.runtime_commit = commit_all(fixture.runtime_root, "test-only engaged admission")

    @staticmethod
    def _install_fake_codex(fixture: AuthorityFixture) -> Path:
        bin_dir = fixture.root / "fake-bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        executable = bin_dir / "codex"
        executable.write_text(
            textwrap.dedent(
                '                #!/usr/bin/env python3\n                import json\n                import os\n                from pathlib import Path\n                import subprocess\n                import sys\n\n                root = Path.cwd()\n                log_path = Path(os.environ["PLANVEYOR_TEST_PROVIDER_LOG"])\n                log_path.parent.mkdir(parents=True, exist_ok=True)\n                log_path.write_text(json.dumps({\n                    "argv": sys.argv[1:],\n                    "pointer_exists_before_provider": (root / ".planveyor.session.architect").exists(),\n                }, sort_keys=True), encoding="utf-8")\n                sys.stdin.read()\n\n                if os.environ.get("PLANVEYOR_TEST_PROVIDER_MUTATE") == "1":\n                    changed = root / "unrelated-provider-change.txt"\n                    changed.write_text("provider changed an unrelated target file\\n", encoding="utf-8")\n                    subprocess.run(["git", "-C", str(root), "add", "--", changed.name], check=True)\n                    subprocess.run([\n                        "git", "-C", str(root),\n                        "-c", "user.name=Fixture provider",\n                        "-c", "user.email=' + 'fixture-provider' + '@' + 'example' + '.' + 'invalid' + '",\n                        "commit", "--quiet", "-m", "provider unrelated change",\n                    ], check=True)\n\n                print(f"Fake Codex session {os.environ[\'PLANVEYOR_TEST_PROVIDER_SID\']}")\n                raise SystemExit(int(os.environ.get("PLANVEYOR_TEST_PROVIDER_EXIT", "0")))\n                '
            ),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return bin_dir

    def _run_shell(
        self,
        fixture: AuthorityFixture,
        command: str,
        *,
        extra_env: dict[str, str] | None = None,
        loaded: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        if extra_env:
            environment.update(extra_env)
        runtime_facade = fixture.runtime_root / "scripts" / "planveyor.zsh"
        if loaded:
            prelude = (
                fixture.shell_loader()
                + f"\nplanveyor_source_runtime {shlex.quote(str(runtime_facade))} || exit $?"
                + "\n[[ \"${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}\" == pinned ]] || exit 96"
            )
        else:
            # Keep one legacy control: raw source is available, but cannot
            # make an attested runtime claim.
            prelude = f"source {shlex.quote(str(runtime_facade))} || exit $?"
        return subprocess.run(
            ["/bin/zsh", "-fc", f"{prelude}; {command}"],
            cwd=fixture.target_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _provider_environment(self, fixture: AuthorityFixture, *, sid: str, exit_code: int, mutate: bool) -> dict[str, str]:
        bin_dir = self._install_fake_codex(fixture)
        return {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "PYBIN": sys.executable,
            "PLANVEYOR_TEST_PROVIDER_LOG": str(fixture.root / "fake-provider.json"),
            "PLANVEYOR_TEST_PROVIDER_SID": sid,
            "PLANVEYOR_TEST_PROVIDER_EXIT": str(exit_code),
            "PLANVEYOR_TEST_PROVIDER_MUTATE": "1" if mutate else "0",
        }

    @staticmethod
    def _captured_init_command() -> str:
        """Exercise the provider-to-receipt ordering under one frozen parent."""

        return textwrap.dedent(
            """\
            planveyor_authority_test_init() {
              emulate -L zsh
              local _planveyor_ctx_json=""
              _planveyor_ctx_json="$(_planveyor_pre_dispatch planveyor_authority_test_init)" || return $?
              local _planveyor_ctx_state="$(_planveyor_authority_context_field "$_planveyor_ctx_json" state)" || return $?
              local _planveyor_ctx_root="$(_planveyor_authority_context_field "$_planveyor_ctx_json" project_root)" || return $?
              local _planveyor_ctx_generation="$(_planveyor_authority_context_field "$_planveyor_ctx_json" generation_sha256)" || return $?
              local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
              local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
              local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
              local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
              local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

              local capture_dir=""
              capture_dir="$(_planveyor_init_run_capture_begin architect)" || return $?
              local out=""
              out="$(printf 'ROLE=Architect\\n' | codex exec 2>&1)"
              local rc=$?
              printf '%s\\n' "$out"
              _planveyor_save_session_key_from_output architect "$out" "runner=codex profile=test" || return $?
              _planveyor_init_run_capture_finalize "$capture_dir" architect architect codex test "" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "" "" "" "" "" "" "" "runner=codex profile=test"
              local finalize_rc=$?
              if [[ "$rc" == "0" && "$finalize_rc" != "0" ]]; then
                return "$finalize_rc"
              fi
              return "$rc"
            }
            planveyor_authority_test_init
            """
        )

    @staticmethod
    def _manager_seed_command() -> str:
        """Write a Manager receipt under one frozen engaged invocation."""

        return textwrap.dedent(
            f"""\
            planveyor_authority_test_manager_seed() {{
              emulate -L zsh
              local _planveyor_ctx_json=""
              _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_authority_test_manager_seed)" || return $?
              local _planveyor_ctx_state="$(_planveyor_authority_context_field "$_planveyor_ctx_json" state)" || return $?
              local _planveyor_ctx_root="$(_planveyor_authority_context_field "$_planveyor_ctx_json" project_root)" || return $?
              local _planveyor_ctx_generation="$(_planveyor_authority_context_field "$_planveyor_ctx_json" generation_sha256)" || return $?
              local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
              local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
              local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
              local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
              local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

              local invocation_id="{MANAGER_SID}"
              local receipt_path=""
              receipt_path="$(_planveyor_manager_invocation_receipt_path "$invocation_id")" || return $?
              _planveyor_manager_invocation_receipt_seed \
                "$invocation_id" "$receipt_path" "$invocation_id" interactive "" \
                "2026-09-07T00:00:00Z" "$PLANVEYOR_CTX_JSON"
            }}
            planveyor_authority_test_manager_seed
            """
        )

    def _validate_receipt(
        self,
        fixture: AuthorityFixture,
        *,
        session_key: str,
        sid: str,
        context: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        return run_bootstrapped_bridge(
            fixture,
            "receipt-validate",
            "--project-root",
            str(fixture.target_root),
            "--session-key",
            session_key,
            "--sid",
            sid,
            "--mode",
            "engaged",
            "--context",
            json.dumps(context, sort_keys=True, separators=(",", ":")),
            cwd=fixture.target_root,
            environment=fixture.environment(),
            timeout=30,
        )

    def test_mocked_closed_admission_gate_rejects_marker(self) -> None:
        """A marker cannot engage when the admission gate is explicitly closed."""

        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            with (
                mock.patch.object(source_context, "ENGAGED_ADMISSION_COMPLETE", False),
                mock.patch.object(source_context, "_executing_runtime_root", return_value=fixture.runtime_root),
            ):
                with self.assertRaises(source_context.ContractAuthorityError) as raised:
                    source_context.resolve_top_level_context(
                        fixture.target_root,
                        runtime_root=fixture.runtime_root,
                    )
            self.assertEqual(raised.exception.reason_code, "engaged_admission_incomplete")

    def test_engaged_init_receipt_binds_sid_before_pointer_and_freezes_entry(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            entry_head = git(fixture.target_root, "rev-parse", "HEAD")
            provider_env = self._provider_environment(
                fixture,
                sid=ARCHITECT_SID,
                exit_code=0,
                mutate=True,
            )

            result = self._run_shell(fixture, self._captured_init_command(), extra_env=provider_env)
            self.assertEqual(result.returncode, 0, result.stderr)

            receipt_path = fixture.target_root / ".planveyor.init_runs" / "by_sid" / ARCHITECT_SID / "meta.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["outcome"], "success")
            self.assertEqual(receipt["sid"], ARCHITECT_SID)
            self.assertEqual(receipt["session_key"], "architect")
            authority = receipt["authority_context"]
            self.assertIsInstance(authority, dict)
            assert isinstance(authority, dict)
            self.assertEqual(authority["state"], "engaged")
            self.assertEqual(authority["schema_version"], "planveyor_contract_context.v3")
            self.assertEqual(authority["entry_observation_provenance"], "observed_local")
            self.assertEqual(authority["entry_observation"]["head"], entry_head)
            self.assertNotEqual(git(fixture.target_root, "rev-parse", "HEAD"), entry_head)

            provider_log = json.loads((fixture.root / "fake-provider.json").read_text(encoding="utf-8"))
            self.assertFalse(provider_log["pointer_exists_before_provider"])
            pointer = (fixture.target_root / ".planveyor.session.architect").read_text(encoding="utf-8")
            self.assertEqual(pointer.splitlines()[-1], ARCHITECT_SID)
            self.assertIn(f"authority_generation={authority['generation_sha256']}", pointer)
            self.assertIn(f"authority_context_sha256={authority['context_sha256']}", pointer)

            accepted = self._validate_receipt(
                fixture,
                session_key="architect",
                sid=ARCHITECT_SID,
                context=authority,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(json.loads(accepted.stdout)["receipt"], "matched")

            wrong_key = self._validate_receipt(
                fixture,
                session_key="coder",
                sid=ARCHITECT_SID,
                context=authority,
            )
            self.assertNotEqual(wrong_key.returncode, 0)
            self.assertIn("receipt_binding_mismatch", wrong_key.stderr)

    def test_failed_provider_receipt_cannot_bless_a_sid(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            provider_env = self._provider_environment(
                fixture,
                sid=FAILED_SID,
                exit_code=23,
                mutate=False,
            )

            failed = self._run_shell(fixture, self._captured_init_command(), extra_env=provider_env)
            self.assertEqual(failed.returncode, 23, failed.stderr)
            receipt_path = fixture.target_root / ".planveyor.init_runs" / "by_sid" / FAILED_SID / "meta.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["outcome"], "failed")
            self.assertEqual(receipt["authority_context"]["state"], "engaged")
            self.assertFalse((fixture.target_root / ".planveyor.session.architect").exists())

            setter = self._run_shell(
                fixture,
                f"planveyor_session_set architect {shlex.quote(FAILED_SID)}",
            )
            self.assertNotEqual(setter.returncode, 0)
            self.assertIn("Refusing to save an authority-unbound session id", setter.stderr)
            self.assertFalse((fixture.target_root / ".planveyor.session.architect").exists())

    def test_manager_seed_persists_frozen_engaged_authority_context(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)

            result = self._run_shell(fixture, self._manager_seed_command())
            self.assertEqual(result.returncode, 0, result.stderr)
            seed = json.loads(result.stdout)
            authority = seed["authority_context"]
            self.assertEqual(authority["state"], "engaged")
            self.assertEqual(seed["manager_sid"], MANAGER_SID)

            receipt_path = Path(seed["receipt_path"])
            stored = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["authority_context"], authority)
            self.assertEqual(stored["immutable_identity_sha256"], seed["immutable_identity_sha256"])

    def test_manager_receipt_validator_accepts_context_schema_provenance_matrix(self) -> None:
        """The embedded receipt validator admits v3 and fails closed on non-text fields."""

        def payload(
            schema: object,
            provenance: object | None = None,
            *,
            state: object = "engaged",
        ) -> dict[str, object]:
            result: dict[str, object] = {
                "schema_version": schema,
                "state": state,
                "project_root": "/fixture/project",
                "generation_sha256": "fixture-generation",
                "context_sha256": "fixture-context",
                "runtime_pin": {"pin_sha256": "fixture-runtime-pin"},
            }
            if provenance is not None:
                result["entry_observation_provenance"] = provenance
            return result

        missing_schema = payload("planveyor_contract_context.v1")
        missing_schema.pop("schema_version")
        cases: tuple[tuple[str, object, str], ...] = (
            ("validator-v1-accepted", payload("planveyor_contract_context.v1"), "accepted"),
            *(
                (
                    f"validator-{schema.rsplit('.', 1)[-1]}-{provenance}",
                    payload(schema, provenance),
                    "accepted",
                )
                for schema in ("planveyor_contract_context.v2", "planveyor_contract_context.v3")
                for provenance in ("observed_local", "inherited_supplied_unverified")
            ),
            ("validator-schema-missing", missing_schema, "rejected:125"),
            ("validator-schema-invalid-text", payload("planveyor_contract_context.v4"), "rejected:125"),
            ("validator-schema-list", payload([]), "rejected:125"),
            ("validator-schema-dict", payload({}), "rejected:125"),
            *(
                (
                    f"validator-{schema.rsplit('.', 1)[-1]}-legacy-state",
                    payload(schema, state="legacy"),
                    "rejected:125",
                )
                for schema in (
                    "planveyor_contract_context.v1",
                    "planveyor_contract_context.v2",
                    "planveyor_contract_context.v3",
                )
            ),
            *(
                (
                    f"validator-{schema.rsplit('.', 1)[-1]}-{kind}",
                    payload(schema, malformed) if kind != "provenance-missing" else payload(schema),
                    "rejected:125",
                )
                for schema in ("planveyor_contract_context.v2", "planveyor_contract_context.v3")
                for kind, malformed in (
                    ("provenance-missing", None),
                    ("provenance-invalid-text", "unsupported"),
                    ("provenance-list", []),
                    ("provenance-dict", {}),
                )
            ),
            ("validator-context-list", [], "rejected:125"),
            ("validator-context-text", "not-an-object", "rejected:125"),
        )
        self.assertEqual(len(cases), 22)
        validator_function_lines = [
            "planveyor_authority_test_receipt_validator_case() {",
            "  emulate -L zsh",
            "  local invocation_id=\"$1\" payload=\"$2\" receipt_path=\"\"",
            "  receipt_path=\"$(_planveyor_manager_invocation_receipt_path \"$invocation_id\")\" || return $?",
            "  if _planveyor_manager_invocation_receipt_mutate seed \"$receipt_path\" \"$invocation_id\" manager-sid interactive \"\" 2026-09-07T00:00:00Z \"$payload\" >/dev/null; then",
            "    print -r -- \"$invocation_id=accepted\"",
            "  else",
            "    print -r -- \"$invocation_id=rejected:$?\"",
            "  fi",
            "}",
        ]
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            # A production mutation deliberately revalidates its frozen authority
            # immediately before the effect. Keep each independent batch below
            # the shell's 60-second bound rather than extending that bound and
            # hiding aggregate runtime; every payload still gets its own mutation.
            for start in range(0, len(cases), 5):
                batch = cases[start : start + 5]
                command_lines = [
                    *validator_function_lines,
                    *(
                        "planveyor_authority_test_receipt_validator_case "
                        f"{shlex.quote(case_id)} {shlex.quote(json.dumps(context, sort_keys=True, separators=(',', ':')))}"
                        for case_id, context, _expected in batch
                    ),
                ]
                with self.subTest(batch_start=start):
                    result = self._run_shell(fixture, "\n".join(command_lines))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(
                        result.stdout.splitlines(),
                        [f"{case_id}={expected}" for case_id, _context, expected in batch],
                    )

    def test_engaged_child_uses_pinned_facade_not_target_shim(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            generated_child_source = (fixture.runtime_root / "scripts/planveyor/role_runtime.zsh").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                'f"_planveyor_runtime_api_guard 5 5 {shlex.quote(runtime_pin_sha256)} || exit $?",',
                generated_child_source,
            )
            hostile_marker = fixture.root / "hostile-target-shim-ran"
            write(
                fixture.target_root,
                "scripts/planveyor.zsh",
                "print -r -- hostile > ${PLANVEYOR_TEST_HOSTILE_MARKER:?}\nexit 91\n",
                executable=True,
            )
            wrapper_source = fixture.root / "child-wrapper.zsh"
            wrapper_result = fixture.root / "child-wrapper-ran"
            wrapper_source.write_text(
                textwrap.dedent(
                    f"""\
                    planveyor_authority_test_wrapper() {{
                      [[ -z "${{PLANVEYOR_CTX_SEAL-}}${{PLANVEYOR_CTX_ROOT-}}${{PLANVEYOR_CTX_GENERATION-}}${{PLANVEYOR_CTX_JSON-}}${{PLANVEYOR_CTX_STATE-}}" ]] || return 92
                      [[ -n "${{_PLANVEYOR_AUTHORITY_CONTEXT_V1-}}" ]] || return 93
                      print -r -- wrapped > {shlex.quote(str(wrapper_result))}
                    }}
                    """
                ),
                encoding="utf-8",
            )
            stdout_path = fixture.root / "child.stdout"
            stderr_path = fixture.root / "child.stderr"
            command = " ".join(
                (
                    "_planveyor_role_run_supervise",
                    shlex.quote(str(fixture.target_root)),
                    "planveyor_authority_test_wrapper",
                    shlex.quote(str(wrapper_source)),
                    shlex.quote(str(stdout_path)),
                    shlex.quote(str(stderr_path)),
                    "15",
                    "--",
                    "PLANVEYOR_CTX_SEAL=ambient-spoof",
                    "PLANVEYOR_CTX_ROOT=/ambient-spoof",
                    "PLANVEYOR_CTX_GENERATION=" + ("0" * 64),
                    "PLANVEYOR_CTX_JSON=ambient-spoof",
                    "PLANVEYOR_CTX_STATE=engaged",
                )
            )
            result = self._run_shell(
                fixture,
                command,
                extra_env={"PLANVEYOR_TEST_HOSTILE_MARKER": str(hostile_marker)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["exit_code"], 0)
            self.assertEqual(wrapper_result.read_text(encoding="utf-8").strip(), "wrapped")
            self.assertFalse(hostile_marker.exists())

    def test_public_resume_wrappers_preserve_child_status_and_cleanup(self) -> None:
        """Every direct resume surface returns its child status after ``popd``.

        This uses a clean, marker-free Git target with manually written legacy
        session pointers.  The sole runner seam prints the authority-denial
        result and returns its configured status; authority helpers and the
        external provider remain real, so an accidental provider call leaves
        the fixture's fake-provider log behind.
        """

        sid = "00000000-0000-4000-8000-00000000a704"
        session_keys = (
            "architect",
            "coder",
            "planner",
            "reviewer",
            "reviewer_code_risk",
            "reviewer_code_contracts",
            "manager",
        )
        resume_surfaces = (
            "planveyor_arch_resume",
            "planveyor_coder_resume",
            "planveyor_planner_resume",
            "planveyor_reviewer_resume",
            "planveyor_reviewer_code_risk_resume",
            "planveyor_reviewer_code_contracts_resume",
            "planveyor_manager_resume",
        )

        with AuthorityFixture(identity="planveyor") as fixture:
            for session_key in session_keys:
                write(
                    fixture.target_root,
                    f".planveyor.session.{session_key}",
                    f"# manual legacy session\n{sid}\n",
                )
            # The three reviewer variants share a private implementation.
            # Choose the neutral direct-Claude branch so no Codex session
            # model lookup obscures the public wrapper's child return status.
            write(fixture.target_root, ".planveyor.runner.reviewer", "claude\n")
            write(fixture.target_root, "nested/resume-caller/.keep", "fixture caller\n")
            commit_all(fixture.target_root, "manual legacy resume pointers")
            self.assertEqual(git(fixture.target_root, "status", "--porcelain"), "")

            provider_env = self._provider_environment(
                fixture,
                sid=sid,
                exit_code=0,
                mutate=False,
            )
            provider_log = Path(provider_env["PLANVEYOR_TEST_PROVIDER_LOG"])
            caller = fixture.target_root / "nested" / "resume-caller"
            surface_words = " ".join(resume_surfaces)
            command = textwrap.dedent(
                f"""\
                [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == unattested_legacy ]] || exit 70
                resume_context="$(_planveyor_authority_context_for_reader resume_return_matrix)" || exit $?
                [[ "$(_planveyor_authority_context_field "$resume_context" state)" == legacy ]] || exit 71

                # Deliberately intercept only the external child boundary.  The
                # public wrapper still captures context, reads the manual SID,
                # validates the legacy receipt rule, and owns its pushd/popd.
                _planveyor_codex() {{
                  print -u2 -r -- context_expectation_mismatch
                  return "${{PLANVEYOR_TEST_RESUME_RC:?}}"
                }}
                _planveyor_claude_direct_run() {{
                  print -u2 -r -- context_expectation_mismatch
                  return "${{PLANVEYOR_TEST_RESUME_RC:?}}"
                }}

                pushd {shlex.quote(str(caller))} >/dev/null || exit 72
                resume_probe() {{
                  local surface="$1"
                  local before_pwd="$PWD"
                  local before_dirs="$(dirs -p)"
                  "$surface"
                  local observed=$?
                  local after_dirs="$(dirs -p)"
                  [[ "$observed" == "$PLANVEYOR_TEST_RESUME_RC" ]] || {{
                    print -u2 -r -- "resume-rc-mismatch:$surface:$observed:$PLANVEYOR_TEST_RESUME_RC"
                    return 73
                  }}
                  [[ "$PWD" == "$before_pwd" && "$after_dirs" == "$before_dirs" ]] || {{
                    print -u2 -r -- "resume-cleanup-mismatch:$surface"
                    return 74
                  }}
                  print -r -- "resume-ok:$surface:$observed"
                }}
                for surface in {surface_words}; do
                  resume_probe "$surface" || exit $?
                done
                [[ ! -e "$PLANVEYOR_TEST_PROVIDER_LOG" ]] || {{
                  print -u2 -r -- provider-effect-observed
                  exit 75
                }}
                """
            )

            for child_rc in (2, 0):
                result = self._run_shell(
                    fixture,
                    command,
                    extra_env={**provider_env, "PLANVEYOR_TEST_RESUME_RC": str(child_rc)},
                    loaded=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.splitlines(),
                    [f"resume-ok:{surface}:{child_rc}" for surface in resume_surfaces],
                )
                self.assertEqual(
                    result.stderr.splitlines(),
                    ["context_expectation_mismatch"] * len(resume_surfaces),
                )
                self.assertFalse(provider_log.exists(), result.stderr)


class SessionIdExtractionTests(unittest.TestCase):
    """Run the facade's session-id parser alone in a clean zsh."""

    @staticmethod
    def _extract(text: str) -> subprocess.CompletedProcess[str]:
        source = (SCRIPT_DIR / "planveyor.zsh").read_text(encoding="utf-8")
        start = source.index("\n_planveyor_extract_session_id() {\n") + 1
        end = source.index("\n}\n", start) + 3
        return subprocess.run(
            ["/bin/zsh", "-fc", source[start:end] + '\n_planveyor_extract_session_id "$1"', "zsh", text],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_codex_banner_session_line_wins_over_an_earlier_path_uuid(self) -> None:
        path_uuid = "ae73d21f-d480-475b-bd4a-f18a6e2584c2"
        banner = (
            "OpenAI Codex v0.157.1\n"
            "--------\n"
            f"workdir: /private/tmp/agent/{path_uuid}/scratchpad/sibling\n"
            "model: gpt-test\n"
            f"session id: {ARCHITECT_SID}\n"
            "--------\n"
        )
        result = self._extract(banner)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(ARCHITECT_SID, result.stdout.strip())

    def test_output_without_banner_line_keeps_the_first_uuid(self) -> None:
        result = self._extract(f"resume with --resume {FAILED_SID}\nthen {MANAGER_SID}\n")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(FAILED_SID, result.stdout.strip())

    def test_output_without_uuid_reports_nothing(self) -> None:
        result = self._extract("no session here\n")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()

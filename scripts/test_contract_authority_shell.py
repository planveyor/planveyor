#!/usr/bin/env python3
"""Shell-process regressions for the contract-authority source boundary.

These cases run the copied candidate runtime from ``AuthorityFixture`` under
``/bin/zsh -f``.  They deliberately exercise source-time and pre-effect
behavior that a Python-only unit test cannot observe: readonly zsh state,
re-source ordering, and the bridge's import boundary.  Every repository,
HOME, provider, and poisoned module is disposable.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import py_compile
import shlex
import shutil
import stat
import subprocess
import sys
import textwrap
import time
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_context
from test_contract_authority_support import AuthorityFixture, commit_all, git, tree_snapshot, write


_DIRECT_AUTHORITY_CONSUMERS = (
    "scripts/build_role_bundles.py",
    "scripts/codex_session_context.py",
    "scripts/docs_closeout.py",
    "scripts/followups_promote.py",
    "scripts/followups_triage.py",
    "scripts/plan_harvest_lint.py",
    "scripts/plan_lint.py",
    "scripts/plan_queue.py",
    "scripts/plan_status_oracle.py",
    "scripts/post_merge_audit_lint.py",
    "scripts/post_merge_receipt_skeleton.py",
    "scripts/process_improvements_collect.py",
    "scripts/planveyor_trace_extractor.py",
    "scripts/review_artifact_lint.py",
    "scripts/review_visual_lane_contract.py",
    "scripts/role_outcome_receipt.py",
)

_PUBLIC_PI_CANDIDATE_PATHS = (
    "scripts/process_improvements_collect.py",
    "scripts/followups_capture.py",
    "scripts/test_contract_authority_writers.py",
    "scripts/test_process_improvements.py",
    "scripts/test_followups_capture.py",
    "scripts/test_contract_authority_shell.py",
    "scripts/test_manager_custom_pipeline_prompt_contract.py",
    "scripts/test_docs_closeout.py",
    "docs/tools/prompts/architect_docs_finalize_general.md",
    "docs/tools/prompts/coder_docs_finalize_general.md",
    "docs/tools/prompts/planner_docs_finalize_general.md",
    "docs/tools/prompts/reviewer_docs_finalize_general.md",
)


class ContractAuthorityShellIntegrationTests(unittest.TestCase):
    """Bounded source and bridge tests using only disposable checkouts."""

    def _shell_environment(
        self,
        fixture: AuthorityFixture,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        environment = fixture.environment()
        # The production bootstrap intentionally accepts only Python 3.10--3.12.
        # The test runner is invoked with that supported interpreter, so make its
        # sibling ``python``/``python3`` visible before a host Python 3.14.
        executable_dirs = [str(Path(sys.executable).resolve().parent)]
        for command in ("git", "rg"):
            binary = shutil.which(command)
            if binary is None:
                self.fail(f"test host is missing required public facade binary: {command}")
            executable_dirs.append(str(Path(binary).resolve().parent))
        environment["PATH"] = os.pathsep.join(
            (*dict.fromkeys(executable_dirs), environment.get("PATH", ""))
        )
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if extra:
            environment.update(extra)
        return environment

    def _run_zsh(
        self,
        fixture: AuthorityFixture,
        command: str,
        *,
        cwd: Path | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/zsh", "-f", "-c", fixture.shell_loader() + command],
            cwd=cwd or fixture.target_root,
            env=self._shell_environment(fixture, extra_environment),
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    @staticmethod
    def _facade_path(runtime_root: Path) -> str:
        return shlex.quote(str(runtime_root / "scripts" / "planveyor.zsh"))

    def _enable_isolated_admission(self, fixture: AuthorityFixture) -> None:
        """Enable admission only in this fixture runtime before it is sourced."""

        context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = context_path.read_text(encoding="utf-8")
        incomplete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False"
        complete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True"
        if incomplete in original:
            context_path.write_text(original.replace(incomplete, complete, 1), encoding="utf-8")
            fixture.runtime_commit = commit_all(fixture.runtime_root, "test-only engaged admission")
        else:
            self.assertIn(complete, original)

    @staticmethod
    def _dirty_runtime(fixture: AuthorityFixture) -> None:
        path = fixture.runtime_root / "scripts" / "plan_lint.py"
        path.write_bytes(path.read_bytes() + b"\n# disposable authority runtime drift\n")

    @staticmethod
    def _logging_interpreter(fixture: AuthorityFixture) -> tuple[Path, Path]:
        """Create a disposable Python shim that records and delegates calls."""

        wrapper = fixture.root / "interpreter-bin" / "python3"
        log = fixture.root / "interpreter-wrapper.log"
        actual_python = shlex.quote(str(Path(sys.executable).resolve()))
        write(
            fixture.root,
            "interpreter-bin/python3",
            "#!/bin/sh\n"
            "{ for arg do case \"$arg\" in *'\n'*) printf '%s ' '<caller-literal>';; "
            "*) printf '%s ' \"$arg\";; esac; done; printf '\\n'; } "
            ">> \"${AUTHORITY_TEST_INTERPRETER_LOG:?}\"\n"
            f"exec {actual_python} \"$@\"\n",
            executable=True,
        )
        return wrapper, log

    def _install_timestamp_valid_stale_context_cache(self, fixture: AuthorityFixture) -> Path:
        """Leave v1 source bytes behind a valid cache compiled from x1 bytes."""

        source = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = source.read_bytes()
        original_stat = source.stat()
        original_mode = stat.S_IMODE(original_stat.st_mode)
        original_git_row = git(
            fixture.runtime_root,
            "ls-files",
            "-s",
            "--",
            "scripts/contract_authority_context.py",
        )
        # ``context`` intentionally retains a compatibility alias after the
        # passive parser/schema moves to ``snapshot``.  Compile a same-size
        # stale cache whose old code substitutes a literal x1 value for that
        # alias.  Restoring the exact v1 source bytes, mode, mtime, and Git row
        # makes the cache timestamp-valid to an unprotected importer.
        before = b"CONTEXT_SCHEMA_VERSION: Final[str] = _snapshot.CONTEXT_SCHEMA_VERSION"
        replacement = b'CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.x1"'
        self.assertIn(before, original)
        self.assertLess(len(replacement), len(before))
        after = replacement + b" " * (len(before) - len(replacement))
        self.assertEqual(len(before), len(after))
        mutated = original.replace(before, after, 1)
        source.write_bytes(mutated)
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        # Do not let a B consumer's process-local pycache prefix change the
        # fixture compiler destination: this is the actual adjacent cache
        # CPython would use without the candidate's no-cache process policy.
        cache = source.parent / "__pycache__" / f"{source.stem}.{sys.implementation.cache_tag}.pyc"
        cache.parent.mkdir(exist_ok=True)
        py_compile.compile(
            str(source),
            cfile=str(cache),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        )
        source.write_bytes(original)
        source.chmod(original_mode)
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(source.stat().st_size, original_stat.st_size)
        self.assertEqual(source.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(stat.S_IMODE(source.stat().st_mode), original_mode)
        self.assertEqual(git(
            fixture.runtime_root,
            "ls-files",
            "-s",
            "--",
            "scripts/contract_authority_context.py",
        ), original_git_row)
        self.assertTrue(cache.is_file())
        return cache

    @staticmethod
    def _bound_context(action: str) -> str:
        """Run ``action`` under caller-local readonly authority values."""

        return textwrap.dedent(
            """\
            authority_shell_bound_context() {
              emulate -L zsh
              local _planveyor_ctx_json=""
              _planveyor_ctx_json="$(_planveyor_pre_dispatch authority_shell_bound_context)" || return $?
              local _planveyor_ctx_tuple=""
              _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
              local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
              IFS=$'\\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
              [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
              local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
              local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
              local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
              local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
              local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

            %s
            }
            authority_shell_bound_context
            """
            % textwrap.indent(action.strip(), "  ")
        )


    @staticmethod
    def _public_pi_clean_body(reason: str = "clean_run") -> str:
        return f"## Process improvements\nNO PROCESS IMPROVEMENTS — why: {reason}\n"

    @staticmethod
    def _public_pi_suggestion_body(plan_ref: str) -> str:
        return textwrap.dedent(
            f"""
            ## Process improvements
            ### Suggestion 1
            - symptom: public fixture needs a durable process-improvement record
            - process_gap: collector admission must bind the active capture cycle
            - suggested_fix: preserve the fixed PI write universe after exact admission
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/public_pi_fixture.md#C1
            - source_ref: {plan_ref}
            """
        )

    def _install_public_pi_semantic_sentinel(
        self,
        fixture: AuthorityFixture,
        *,
        argv: tuple[str, ...],
        expected_reason: str | None = None,
        expected_error: str | None = None,
    ) -> None:
        """Instrument only the copied allowlisted collector before fixture pinning."""

        if (expected_reason is None) == (expected_error is None):
            self.fail("semantic sentinel requires exactly one expected reason or error")
        collector_path = fixture.runtime_root / "scripts" / "process_improvements_collect.py"
        original = collector_path.read_text(encoding="utf-8")
        terminal = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
        self.assertEqual(original.count(terminal), 1)
        replacement = textwrap.dedent(
            f"""
            _TEST_PUBLIC_PI_SEMANTIC_ARGV = {argv!r}
            _TEST_PUBLIC_PI_SEMANTIC_REASON = {expected_reason!r}
            _TEST_PUBLIC_PI_SEMANTIC_ERROR = {expected_error!r}

            if __name__ == "__main__":
                original_argv = tuple(sys.argv[1:])
                if original_argv == _TEST_PUBLIC_PI_SEMANTIC_ARGV:
                    context = authority_context.context_for_reader(Path.cwd())
                    try:
                        main(list(original_argv), context=context)
                    except Exception as exc:
                        reason_code = getattr(exc, "reason_code", None)
                        if _TEST_PUBLIC_PI_SEMANTIC_REASON is not None:
                            if reason_code != _TEST_PUBLIC_PI_SEMANTIC_REASON:
                                raise
                        elif _TEST_PUBLIC_PI_SEMANTIC_ERROR not in str(exc):
                            raise
                        print(json.dumps(
                            {{
                                "context_state": context.state,
                                "reason_code": reason_code,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "runtime_commit": (
                                    context.runtime_pin.commit
                                    if context.runtime_pin is not None
                                    else None
                                ),
                            }},
                            sort_keys=True,
                        ))
                        raise SystemExit(2)
                    raise AssertionError("semantic collector sentinel unexpectedly succeeded")
                raise SystemExit(main())
            """
        )
        collector_path.write_text(original.replace(terminal, replacement, 1), encoding="utf-8")

    def _install_public_pi_failure_after_backlog_sentinel(
        self,
        fixture: AuthorityFixture,
        *,
        argv: tuple[str, ...],
    ) -> None:
        """Inject one semantic-only derived failure after the real backlog write."""

        collector_path = fixture.runtime_root / "scripts" / "process_improvements_collect.py"
        original = collector_path.read_text(encoding="utf-8")
        terminal = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
        self.assertEqual(original.count(terminal), 1)
        replacement = textwrap.dedent(
            f"""
            _TEST_PUBLIC_PI_FAILURE_ARGV = {argv!r}

            if __name__ == "__main__":
                original_argv = tuple(sys.argv[1:])
                if original_argv == _TEST_PUBLIC_PI_FAILURE_ARGV:
                    context = authority_context.context_for_reader(Path.cwd())
                    def _test_fail_after_backlog(*_args, **_kwargs):
                        raise OSError("test_public_pi_derived_failure_after_backlog")
                    _safe_pi_rebuild_derived_surfaces = _test_fail_after_backlog
                    try:
                        main(list(original_argv), context=context)
                    except OSError as exc:
                        print(json.dumps(
                            {{
                                "context_state": context.state,
                                "reason_code": "collector_error",
                                "runtime_commit": (
                                    context.runtime_pin.commit
                                    if context.runtime_pin is not None
                                    else None
                                ),
                                "error": str(exc),
                            }},
                            sort_keys=True,
                        ))
                        raise SystemExit(2)
                    raise AssertionError("failure sentinel unexpectedly succeeded")
                raise SystemExit(main())
            """
        )
        collector_path.write_text(original.replace(terminal, replacement, 1), encoding="utf-8")

    def _install_public_pi_recovery_failure_sentinel(
        self,
        fixture: AuthorityFixture,
        *,
        argv: tuple[str, ...],
        plan_ref: str,
        cycle_id: str,
    ) -> None:
        """Fail once after a real initial backlog write and once after recovery writes a surface."""

        collector_path = fixture.runtime_root / "scripts" / "process_improvements_collect.py"
        original = collector_path.read_text(encoding="utf-8")
        terminal = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
        self.assertEqual(original.count(terminal), 1)
        replacement = textwrap.dedent(
            f"""
            _TEST_PUBLIC_PI_RECOVERY_FAILURE_ARGV = {argv!r}
            _TEST_PUBLIC_PI_RECOVERY_FAILURE_PLAN_REF = {plan_ref!r}
            _TEST_PUBLIC_PI_RECOVERY_FAILURE_CYCLE_ID = {cycle_id!r}

            if __name__ == "__main__":
                original_argv = tuple(sys.argv[1:])
                if original_argv == _TEST_PUBLIC_PI_RECOVERY_FAILURE_ARGV:
                    context = authority_context.context_for_reader(Path.cwd())
                    receipt_path = Path(capture_receipt_rel_path(
                        _TEST_PUBLIC_PI_RECOVERY_FAILURE_PLAN_REF,
                        "Architect",
                        _TEST_PUBLIC_PI_RECOVERY_FAILURE_CYCLE_ID,
                    ))
                    if receipt_path.is_file():
                        _test_original_write = _safe_pi_write_text
                        _test_write_count = [0]
                        def _test_fail_after_one_recovery_write(*args, **kwargs):
                            result = _test_original_write(*args, **kwargs)
                            _test_write_count[0] += 1
                            if _test_write_count[0] == 1:
                                raise OSError("test_public_pi_recovery_derived_failure")
                            return result
                        _safe_pi_write_text = _test_fail_after_one_recovery_write
                    else:
                        def _test_fail_after_initial_backlog(*_args, **_kwargs):
                            raise OSError("test_public_pi_initial_derived_failure")
                        _safe_pi_rebuild_derived_surfaces = _test_fail_after_initial_backlog
                    try:
                        main(list(original_argv), context=context)
                    except OSError as exc:
                        print(json.dumps(
                            {{
                                "context_state": context.state,
                                "reason_code": "collector_error",
                                "runtime_commit": (
                                    context.runtime_pin.commit
                                    if context.runtime_pin is not None
                                    else None
                                ),
                                "error": str(exc),
                            }},
                            sort_keys=True,
                        ))
                        raise SystemExit(2)
                    raise AssertionError("recovery failure sentinel unexpectedly succeeded")
                raise SystemExit(main())
            """
        )
        collector_path.write_text(original.replace(terminal, replacement, 1), encoding="utf-8")

    def _install_public_pi_unobservable_postmap_sentinel(
        self,
        fixture: AuthorityFixture,
        *,
        argv: tuple[str, ...],
    ) -> None:
        """Turn the post-effect PI map unsafe after a real backlog write in the semantic half."""

        collector_path = fixture.runtime_root / "scripts" / "process_improvements_collect.py"
        original = collector_path.read_text(encoding="utf-8")
        terminal = 'if __name__ == "__main__":\n    raise SystemExit(main())\n'
        self.assertEqual(original.count(terminal), 1)
        replacement = textwrap.dedent(
            f"""
            _TEST_PUBLIC_PI_UNOBSERVABLE_POSTMAP_ARGV = {argv!r}

            if __name__ == "__main__":
                original_argv = tuple(sys.argv[1:])
                if original_argv == _TEST_PUBLIC_PI_UNOBSERVABLE_POSTMAP_ARGV:
                    context = authority_context.context_for_reader(Path.cwd())
                    def _test_make_postmap_unobservable(*_args, **_kwargs):
                        pi_root = Path.cwd() / "docs/process_improvements"
                        outside = Path.cwd() / "postmap-unobservable-outside"
                        outside.mkdir()
                        pi_root.rename(pi_root.with_name("process_improvements-before-unobservable"))
                        pi_root.symlink_to(outside, target_is_directory=True)
                        raise OSError("test_public_pi_postmap_unobservable")
                    _safe_pi_rebuild_derived_surfaces = _test_make_postmap_unobservable
                    try:
                        main(list(original_argv), context=context)
                    except OSError as exc:
                        print(json.dumps(
                            {{
                                "context_state": context.state,
                                "reason_code": "collector_error",
                                "runtime_commit": (
                                    context.runtime_pin.commit
                                    if context.runtime_pin is not None
                                    else None
                                ),
                                "error": str(exc),
                            }},
                            sort_keys=True,
                        ))
                        raise SystemExit(2)
                    raise AssertionError("post-map sentinel unexpectedly succeeded")
                raise SystemExit(main())
            """
        )
        collector_path.write_text(original.replace(terminal, replacement, 1), encoding="utf-8")

    def _prepare_public_pi_fixture(
        self,
        fixture: AuthorityFixture,
        *,
        semantic_sentinel: bool = False,
        semantic_argv: tuple[str, ...] | None = None,
        semantic_reason: str = "engaged_private_delivery_unsupported",
    ) -> tuple[str, str]:
        """Build one declared target and its active general-PI capture cycle."""

        plan_ref = "docs/plans/260927_0001_public_pi_fixture.md"
        source_entry = SCRIPT_DIR.parent / "bin" / "planveyor"
        self.assertTrue(source_entry.is_file())
        entry = fixture.runtime_root / "bin" / "planveyor"
        entry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_entry, entry)
        entry.chmod(0o755)
        # Bind every declared candidate byte before activation.  Semantic
        # tests may then make one explicit, committed collector-hook change.
        self._install_public_pi_candidate_runtime(fixture)
        if semantic_sentinel:
            self._install_public_pi_semantic_sentinel(
                fixture,
                argv=semantic_argv or (
                    "--role", "Architect", "--source-ref", plan_ref,
                    "--input", "-", "--json",
                ),
                expected_reason=semantic_reason,
            )
        fixture.runtime_commit = commit_all(
            fixture.runtime_root,
            "disposable public PI facade",
        )
        fixture.activate_planveyor(
            source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
        )
        marker = json.loads(
            (fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marker["source_commit"], fixture.runtime_commit)
        self.assertEqual(git(fixture.runtime_root, "rev-parse", "HEAD"), fixture.runtime_commit)
        write(
            fixture.target_root,
            plan_ref,
            "# Public PI fixture\n\n**Status:** Done\n**Schema version:** plan.v2\n",
        )
        commit_all(fixture.target_root, "disposable public PI plan")

        try:
            import docs_closeout
            import followups_capture
        except ModuleNotFoundError:
            from scripts import docs_closeout, followups_capture

        admission = docs_closeout.classify_followups_bootstrap_admission(
            fixture.target_root,
            plan_ref,
        )
        begun = followups_capture.begin_cycle(
            fixture.target_root,
            plan_ref,
            {
                "schema": "docs_closeout_payload.v1",
                "schema_state": "ok",
                "plan_ref": plan_ref,
                "semantic_status": "Done",
                "semantic_status_norm": "done",
                "semantic_closeout_kind": "already_materialized",
                "followups_bootstrap_admission": admission,
            },
        )
        return plan_ref, str(begun["capture_cycle_id"])

    def _rebind_public_pi_semantic_runtime(
        self,
        fixture: AuthorityFixture,
        *,
        argv: tuple[str, ...],
        message: str,
        expected_reason: str | None = None,
        expected_error: str | None = None,
    ) -> None:
        """Commit one terminal-only semantic hook and rebind its disposable pin."""

        self._install_public_pi_semantic_sentinel(
            fixture,
            argv=argv,
            expected_reason=expected_reason,
            expected_error=expected_error,
        )
        fixture.runtime_commit = commit_all(fixture.runtime_root, message)
        marker_path = fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["source_commit"] = fixture.runtime_commit
        write(
            fixture.target_root,
            "docs/_meta/planveyor_contract_authority.v1.json",
            json.dumps(marker, sort_keys=True) + "\n",
        )
        commit_all(fixture.target_root, f"rebind {message}")
        self.assertEqual(
            json.loads(marker_path.read_text(encoding="utf-8"))["source_commit"],
            fixture.runtime_commit,
        )

    @staticmethod
    def _public_pi_capture_projection(receipt: dict[str, object]) -> dict[str, object]:
        """Compare V2 outcome facts while excluding timestamped carrier bytes."""

        return {
            key: receipt.get(key)
            for key in (
                "capture_state",
                "reason_code",
                "input_sha256",
                "before_process_improvement_files",
                "after_process_improvement_files",
                "process_improvement_path_results",
                "created",
                "duplicates",
                "error",
            )
        }

    def _assert_public_pi_runtime_preserved(
        self,
        fixture: AuthorityFixture,
        *,
        expected_hashes: dict[str, str],
        source_hashes: dict[str, str],
        semantic_collector_hook: bool = False,
    ) -> None:
        """Check candidate bytes and the attested runtime pin, not mutable Git metadata."""

        current = self._public_pi_candidate_hashes(fixture.runtime_root)
        self.assertEqual(current, expected_hashes)
        self.assertEqual(git(fixture.runtime_root, "rev-parse", "HEAD"), fixture.runtime_commit)
        self.assertEqual(git(fixture.runtime_root, "status", "--short"), "")
        collector = "scripts/process_improvements_collect.py"
        if semantic_collector_hook:
            self.assertNotEqual(current[collector], source_hashes[collector])
            for relative, expected in source_hashes.items():
                if relative != collector:
                    self.assertEqual(current[relative], expected)
        else:
            self.assertEqual(current, source_hashes)

    def _run_public_pi_command(
        self,
        fixture: AuthorityFixture,
        *,
        label: str,
        arguments: list[str],
        input_text: str | None = None,
        trace: list[dict[str, object]] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one retained public command and retain a structured test trace."""

        command = [
            str(fixture.runtime_root / "bin" / "planveyor"),
            "--project",
            str(fixture.target_root),
            *arguments,
        ]
        result = subprocess.run(
            command,
            cwd=fixture.target_root,
            env=self._shell_environment(fixture),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if trace is not None:
            trace.append(
                {
                    "label": label,
                    "argv": command,
                    "actual_rc": result.returncode,
                    "stdin_sha256": (
                        hashlib.sha256(input_text.encode("utf-8")).hexdigest()
                        if input_text is not None
                        else None
                    ),
                    "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
                    "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
                }
            )
        return result

    def test_public_continuation_checkpoint_revalidates_fresh_bundle_and_replays_without_write(self) -> None:
        """Public helpers in an engaged disposable consumer; no provider run."""
        from unittest import mock
        from scripts.test_docs_closeout import DocsCloseoutContinuationAdmissionTests, MODULE
        with AuthorityFixture() as fixture:
            self._prepare_public_pi_fixture(fixture)
            helper = DocsCloseoutContinuationAdmissionTests()
            # The general collectors below run only through the public facade.
            with mock.patch.object(MODULE.followups_capture.process_improvements_collect,
                                   "collect_process_improvements", return_value={}):
                cycle = helper._fixture(fixture.target_root)
            for role in MODULE.followups_capture.REQUIRED_ROLES:
                result = self._run_public_pi_command(fixture, label=role, arguments=[
                    "planveyor_runtime_py", "process_improvements_collect.py", "--role", role,
                    "--source-ref", helper.plan_ref, "--followups-capture-cycle-id", cycle,
                    "--input", "-", "--json"],
                    input_text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n")
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            def read_payload():
                result = self._run_public_pi_command(fixture, label="docs", arguments=[
                    "planveyor_docs_closeout", helper.plan_ref, "--followups-capture-cycle-id", cycle, "--json"])
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["schema_state"], "ok", payload.get("schema_errors"))
                self.assertEqual(payload["state"], "blocked")
                self.assertEqual(payload["followups_continuation_admission"]["state"], "ready",
                                 payload["followups_continuation_admission"])
                return payload
            before = helper._objects(fixture.target_root)
            arguments = ["planveyor_runtime_py", "followups_capture.py", "checkpoint-general-pi",
                "--project-root", str(fixture.target_root), "--plan-ref", helper.plan_ref,
                "--capture-cycle-id", cycle, "--docs-closeout-json", "-"]
            result = self._run_public_pi_command(fixture, label="checkpoint", arguments=arguments,
                                                input_text=json.dumps(read_payload()))
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(json.loads(result.stdout)["reason_code"], "followup_capture_pi_general_checkpointed")
            after = helper._objects(fixture.target_root)
            receipt_path = helper._receipt_path(fixture.target_root, cycle).relative_to(fixture.target_root).as_posix()
            self.assertEqual([p for p in before if before[p] != after[p]], [receipt_path])
            result = self._run_public_pi_command(fixture, label="replay", arguments=arguments,
                                                input_text=json.dumps(read_payload()))
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(json.loads(result.stdout)["reason_code"], "followup_capture_pi_general_checkpoint_already_published")
            self.assertEqual(after, helper._objects(fixture.target_root))

    def _run_public_pi_collection(
        self,
        fixture: AuthorityFixture,
        *,
        plan_ref: str,
        role: str,
        body: str,
        cycle_id: str | None,
        trace: list[dict[str, object]] | None = None,
        label: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._run_public_pi_command(
            fixture,
            label=label or f"collector-{role}",
            arguments=self._public_pi_collection_arguments(
                plan_ref=plan_ref,
                role=role,
                cycle_id=cycle_id,
            ),
            input_text=body,
            trace=trace,
        )

    def _checkpoint_public_pi_after_architect(
        self,
        fixture: AuthorityFixture,
        *,
        plan_ref: str,
        cycle_id: str,
    ) -> None:
        """Finish the general chain with clean successors and publish its checkpoint."""

        for role in ("Coder", "Planner", "Reviewer"):
            collected = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role=role,
                body=self._public_pi_clean_body(),
                cycle_id=cycle_id,
            )
            self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
        published = self._run_public_pi_command(
            fixture,
            label="checkpoint-general-pi-after-recovery",
            arguments=[
                "planveyor_followups_capture",
                "checkpoint-general-pi",
                "--plan-ref",
                plan_ref,
                "--capture-cycle-id",
                cycle_id,
            ],
        )
        self.assertEqual(published.returncode, 0, published.stdout + published.stderr)
        self.assertEqual(
            json.loads(published.stdout)["reason_code"],
            "followup_capture_pi_general_checkpointed",
        )

    @staticmethod
    def _public_pi_collection_arguments(
        *,
        plan_ref: str,
        role: str,
        cycle_id: str | None,
    ) -> list[str]:
        arguments = [
            "planveyor_runtime_py",
            "process_improvements_collect.py",
            "--role",
            role,
            "--source-ref",
            plan_ref,
        ]
        if cycle_id is not None:
            arguments.extend(("--followups-capture-cycle-id", cycle_id))
        arguments.extend(("--input", "-", "--json"))
        return arguments

    def _run_public_pi_collection_open_stdin(
        self,
        fixture: AuthorityFixture,
        *,
        plan_ref: str,
        role: str,
        cycle_id: str | None,
    ) -> subprocess.CompletedProcess[str]:
        """Keep stdin open: a pre-admission failure must terminate anyway."""

        process, command = self._start_public_pi_collection_open_stdin(
            fixture,
            plan_ref=plan_ref,
            role=role,
            cycle_id=cycle_id,
        )
        return self._finish_public_pi_collection_open_stdin(process, command, body=None)

    def _start_public_pi_collection_open_stdin(
        self,
        fixture: AuthorityFixture,
        *,
        plan_ref: str,
        role: str,
        cycle_id: str | None,
    ) -> tuple[subprocess.Popen[str], list[str]]:
        command = [
            str(fixture.runtime_root / "bin" / "planveyor"),
            "--project",
            str(fixture.target_root),
            *self._public_pi_collection_arguments(
                plan_ref=plan_ref,
                role=role,
                cycle_id=cycle_id,
            ),
        ]
        process = subprocess.Popen(
            command,
            cwd=fixture.target_root,
            env=self._shell_environment(fixture),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdin is not None
        return process, command

    def _finish_public_pi_collection_open_stdin(
        self,
        process: subprocess.Popen[str],
        command: list[str],
        *,
        body: str | None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            if body is not None:
                assert process.stdin is not None
                try:
                    process.stdin.write(body)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            returncode = process.wait(timeout=15)
            assert process.stdout is not None
            assert process.stderr is not None
            stdout = process.stdout.read()
            stderr = process.stderr.read()
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
            self.fail("public collector consumed stdin before admission rejected")
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is None:
                    continue
                try:
                    stream.close()
                except BrokenPipeError:
                    pass
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    @staticmethod
    def _public_pi_candidate_hashes(root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for relative in _PUBLIC_PI_CANDIDATE_PATHS:
            path = root / relative
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise AssertionError(f"public PI candidate path must be a regular file: {relative}")
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def _install_public_pi_candidate_runtime(
        self,
        fixture: AuthorityFixture,
    ) -> dict[str, str]:
        """Bind the disposable runtime to the exact twelve candidate bytes."""

        source_root = SCRIPT_DIR.parent
        source_hashes = self._public_pi_candidate_hashes(source_root)
        for relative in _PUBLIC_PI_CANDIDATE_PATHS:
            source = source_root / relative
            destination = fixture.runtime_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            destination.chmod(stat.S_IMODE(source.lstat().st_mode))
        self.assertEqual(
            self._public_pi_candidate_hashes(fixture.runtime_root),
            source_hashes,
        )
        return source_hashes

    def _prepare_public_pi_composition_fixture(
        self,
        fixture: AuthorityFixture,
    ) -> dict[str, object]:
        """Create committed disposable inputs; public lifecycle phases start later."""

        plan_ref = "docs/plans/260927_0002_public_pi_composition.md"
        draft_ref = "docs/code_drafts/260927_0002_public_pi_composition__code_draft.md"
        review_ref = "docs/code_reviews/260927_0002_public_pi_composition.md"
        target_ref = "scripts/public_pi_composition_target.py"
        entry = fixture.runtime_root / "bin" / "planveyor"
        entry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT_DIR.parent / "bin" / "planveyor", entry)
        entry.chmod(0o755)
        source_root = SCRIPT_DIR.parent
        shutil.copy2(source_root / "copier.yml", fixture.runtime_root / "copier.yml")
        shutil.copytree(
            source_root / "copier_template",
            fixture.runtime_root / "copier_template",
            copy_function=shutil.copy2,
        )
        source_candidate_hashes = self._install_public_pi_candidate_runtime(fixture)
        fixture.runtime_commit = commit_all(fixture.runtime_root, "disposable public PI composition runtime")
        composition_target = fixture.root / "public-pi-composition-sibling"
        self.assertFalse(composition_target.exists())
        initialized = subprocess.run(
            [
                str(entry),
                "planveyor_consumer_init",
                str(composition_target),
                "--source-commit",
                fixture.runtime_commit,
            ],
            cwd=fixture.root,
            env=self._shell_environment(fixture),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        init_payload = json.loads(initialized.stdout)
        self.assertEqual(init_payload["state"], "ok")
        self.assertEqual(init_payload["target"], str(composition_target))
        fixture.target_root = composition_target
        marker = json.loads(
            (fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marker["source_commit"], fixture.runtime_commit)
        self.assertEqual(git(fixture.runtime_root, "rev-parse", "HEAD"), fixture.runtime_commit)
        self.assertEqual(
            self._public_pi_candidate_hashes(fixture.runtime_root),
            source_candidate_hashes,
        )

        try:
            import plan_status_oracle
        except ModuleNotFoundError:
            from scripts import plan_status_oracle

        decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        draft_meta = {
            "code_draft_meta": {
                "plan": plan_ref,
                "cluster": "process",
                "targets": [{"path": target_ref, "kind": "py"}],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": decision["reason_code"],
                    "carrier_sha256": plan_status_oracle.machine_authority_decision_sha256(decision),
                },
            }
        }
        tick = chr(96)
        fence = tick * 3
        write(fixture.target_root, target_ref, "# disposable target\n")
        write(fixture.target_root, "docs/followups/README.md", "# Follow-ups fixture\n")
        write(
            fixture.target_root,
            draft_ref,
            "# Code draft: public PI composition fixture\n\n"
            + fence + "json\n"
            + json.dumps(draft_meta, ensure_ascii=False, indent=2)
            + "\n" + fence + "\n",
        )
        plan_meta = {
            "plan_meta": {
                "cluster": "process",
                "tags": [],
                "phase_overlay": None,
                "phase_state": None,
                "parent": None,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": [],
                "machine_authority_decision": decision,
            }
        }
        # Keep the embedded machine JSON on one line so dedent sees the
        # Markdown indentation rather than JSON continuation lines.
        plan_meta_json = json.dumps(plan_meta, ensure_ascii=False, separators=(",", ":"))
        plan_text = textwrap.dedent(
                f"""\
                # Plan: public PI composition fixture

                **Date:** 2026-09-27 12:00 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Done
                **Schema version:** plan.v2

                **Handoff statuses (кто ставит):**
                - {tick}Ready for Planner{tick} — Architect
                - {tick}Ready for Coder{tick} — Planner
                - {tick}Ready for Review{tick} — Coder
                - {tick}Ready for Arch review{tick} — Reviewer
                - {tick}Done{tick} — Architect

                **Context links (source of truth):**
                - Code draft(s): {tick}{draft_ref}{tick}

                ## Meta (machine-readable JSON; required for new plans)
                {fence}json
                {plan_meta_json}
                {fence}

                ## Review artifacts
                - Code review (primary): {tick}{review_ref}{tick}

                ## Evidence (chronological, append-only)
                - [2026-09-27 12:00 MSK] (Reviewer) Disposable public-composition input.
                """
        )
        write(
            fixture.target_root,
            plan_ref,
            plan_text,
        )
        rendered_plan = (fixture.target_root / plan_ref).read_text(encoding="utf-8")
        self.assertTrue(rendered_plan.startswith("# Plan: public PI composition fixture\n"))
        self.assertEqual(
            [line for line in rendered_plan.splitlines() if line.startswith("## ")],
            [
                "## Meta (machine-readable JSON; required for new plans)",
                "## Review artifacts",
                "## Evidence (chronological, append-only)",
            ],
        )
        placeholder = "BUNDLE=current bundle_sha256=" + ("0" * 64)
        write(
            fixture.target_root,
            review_ref,
            "# Code review: public PI composition fixture\n\n"
            f"**Target:** {placeholder}\n**Status:** ✅ OK\n",
        )
        commit_all(fixture.target_root, "disposable public PI composition inputs")
        target_result = subprocess.run(
            [
                str(Path(sys.executable).resolve()),
                "-B",
                str(fixture.runtime_root / "scripts" / "review_target_snapshot.py"),
                plan_ref,
                "--current-bundle",
                "--project-root",
                str(fixture.target_root),
            ],
            cwd=fixture.target_root,
            env=self._shell_environment(fixture),
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(target_result.returncode, 0, target_result.stderr)
        strict_target = str(json.loads(target_result.stdout)["target"])
        self.assertRegex(strict_target, r"^BUNDLE=current bundle_sha256=[0-9a-f]{64}$")
        review_path = fixture.target_root / review_ref
        self.assertEqual(review_path.read_text(encoding="utf-8").count(placeholder), 1)
        review_path.write_text(
            review_path.read_text(encoding="utf-8").replace(placeholder, strict_target, 1),
            encoding="utf-8",
        )
        target_commit = commit_all(fixture.target_root, "disposable public PI composition review target")
        terminal_paths = (plan_ref, draft_ref, review_ref)
        return {
            "plan_ref": plan_ref,
            "terminal_paths": terminal_paths,
            "terminal_before": {
                path: (fixture.target_root / path).read_bytes()
                for path in terminal_paths
            },
            "target_commit": target_commit,
            "marker": marker,
            "candidate_source_sha256": source_candidate_hashes,
            "candidate_fixture_sha256": self._public_pi_candidate_hashes(fixture.runtime_root),
        }

    def _run_public_pi_composition(self, *, materialized: bool) -> None:
        """Future-gated full public composition, with a durable stdout trace."""

        trace: dict[str, object] = {
            "schema": "public_pi_composition_trace.v1",
            "fixture_inputs_not_live_roles_or_sql": True,
            "ordinary_source_commit": False,
            "source_b1": False,
            "family": "materialized_duplicate" if materialized else "clean_noop",
            "commands": [],
        }
        try:
            with AuthorityFixture() as fixture:
                setup = self._prepare_public_pi_composition_fixture(fixture)
                plan_ref = str(setup["plan_ref"])
                terminal_paths = tuple(setup["terminal_paths"])
                terminal_before = dict(setup["terminal_before"])
                marker = dict(setup["marker"])
                source_candidate_hashes = dict(setup["candidate_source_sha256"])
                fixture_candidate_hashes = dict(setup["candidate_fixture_sha256"])
                self.assertEqual(source_candidate_hashes, fixture_candidate_hashes)
                runtime_before = tree_snapshot(fixture.runtime_root)
                trace["fixture"] = {
                    "runtime_commit": fixture.runtime_commit,
                    "runtime_head": git(fixture.runtime_root, "rev-parse", "HEAD"),
                    "marker_source_commit": marker["source_commit"],
                    "target_initial_commit": setup["target_commit"],
                    "candidate_source_sha256": source_candidate_hashes,
                    "candidate_fixture_sha256": fixture_candidate_hashes,
                }
                command_trace = trace["commands"]
                self.assertIsInstance(command_trace, list)

                def public(
                    label: str,
                    arguments: list[str],
                    input_text: str | None = None,
                    *,
                    expect_json: bool = True,
                ) -> dict[str, object] | str:
                    result = self._run_public_pi_command(
                        fixture,
                        label=label,
                        arguments=arguments,
                        input_text=input_text,
                        trace=command_trace,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if expect_json:
                        return json.loads(result.stdout)
                    return result.stdout

                begin_closeout = public(
                    "begin-docs-closeout",
                    ["planveyor_docs_closeout", plan_ref, "--json"],
                )
                self.assertEqual(begin_closeout["schema"], "docs_closeout_payload.v1")
                begun = public(
                    "begin",
                    [
                        "planveyor_followups_capture", "begin", "--plan-ref", plan_ref,
                        "--docs-closeout-json", "-",
                    ],
                    json.dumps(begin_closeout, ensure_ascii=False) + "\n",
                )
                cycle_id = str(begun["capture_cycle_id"])
                bodies = {
                    "Architect": self._public_pi_clean_body(),
                    "Coder": self._public_pi_suggestion_body(plan_ref) if materialized else self._public_pi_clean_body(),
                    "Planner": self._public_pi_clean_body(),
                    "Reviewer": (
                        self._public_pi_suggestion_body(plan_ref)
                        if materialized
                        else self._public_pi_clean_body()
                    ),
                }
                captures: dict[str, dict[str, object]] = {}
                for role in ("Architect", "Coder", "Planner", "Reviewer"):
                    result = self._run_public_pi_collection(
                        fixture, plan_ref=plan_ref, role=role, body=bodies[role],
                        cycle_id=cycle_id, trace=command_trace,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    captures[role] = json.loads(result.stdout)
                if materialized:
                    self.assertEqual(captures["Coder"]["process_improvement_capture_state"], "materialized")
                    self.assertEqual(captures["Reviewer"]["process_improvement_capture_state"], "already_tracked")
                    self.assertTrue(captures["Reviewer"]["duplicates"])
                    self.assertEqual(
                        captures["Reviewer"]["before_process_improvement_files"],
                        captures["Coder"]["after_process_improvement_files"],
                    )
                    self.assertEqual(
                        captures["Reviewer"]["after_process_improvement_files"],
                        captures["Coder"]["after_process_improvement_files"],
                    )
                    duplicate = self._run_public_pi_collection(
                        fixture, plan_ref=plan_ref, role="Coder", body=bodies["Coder"],
                        cycle_id=cycle_id, trace=command_trace, label="collector-Coder-duplicate",
                    )
                    self.assertEqual(duplicate.returncode, 0, duplicate.stdout + duplicate.stderr)
                    duplicate_payload = json.loads(duplicate.stdout)
                    self.assertEqual(duplicate_payload["process_improvement_capture_replay"], "exact_leaf")
                    self.assertEqual(duplicate_payload["process_improvement_capture_state"], "materialized")
                else:
                    self.assertEqual(
                        [captures[role]["process_improvement_capture_state"] for role in captures],
                        ["clean_noop", "clean_noop", "clean_noop", "clean_noop"],
                    )

                for label in ("checkpoint-general-pi", "checkpoint-general-pi-replay"):
                    checkpoint = public(
                        label,
                        [
                            "planveyor_followups_capture", "checkpoint-general-pi",
                            "--plan-ref", plan_ref, "--capture-cycle-id", cycle_id,
                        ],
                    )
                    expected = (
                        "followup_capture_pi_general_checkpointed"
                        if label == "checkpoint-general-pi"
                        else "followup_capture_pi_general_checkpoint_already_published"
                    )
                    self.assertEqual(checkpoint["reason_code"], expected)

                row: dict[str, object] | None = None
                if materialized:
                    try:
                        import followups_lint
                    except ModuleNotFoundError:
                        from scripts import followups_lint
                    row_payload = {
                        "priority": "P1", "summary": "Public PI composition follow-up",
                        "cluster": "process", "to": "coder", "status": "open", "plan": None,
                        "why": "exercise the declared ordinary V2 public family",
                        "tags": ["public-pi-composition"], "item_id": "public-pi-composition-001",
                        "source_ref": plan_ref, "disposition_kind": None, "disposition_ref": None,
                        "disposition_commit_oid": None, "reason": None,
                    }
                    row = {
                        "followup_path": "docs/followups/process_followups_master.md",
                        "payload": row_payload,
                        "row_digest": followups_lint.v2_row_digest(row_payload),
                    }

                for role in ("Architect", "Coder", "Planner", "Reviewer"):
                    public(
                        f"prepare-{role}",
                        [
                            "planveyor_followups_capture", "prepare-role", "--plan-ref", plan_ref,
                            "--capture-cycle-id", cycle_id, "--role", role,
                        ],
                    )
                    rows = [row] if row is not None and role == "Coder" else []
                    compact = {
                        "role": role,
                        "proposed_rows": rows,
                        "role_no_items_reason": None if rows else f"{role} found no ordinary compact rows.",
                    }
                    public(
                        f"submit-{role}",
                        [
                            "planveyor_followups_capture", "submit-ordinary-v2", "--plan-ref", plan_ref,
                            "--capture-cycle-id", cycle_id, "--role", role, "--input", "-", "--write",
                        ],
                        json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n",
                    )
                    public(
                        f"bind-{role}",
                        [
                            "planveyor_followups_capture", "bind-ordinary-v2", "--plan-ref", plan_ref,
                            "--capture-cycle-id", cycle_id, "--role", role,
                            "--submission-current", "--write",
                        ],
                    )

                frozen = public(
                    "freeze-ordinary-v2",
                    [
                        "planveyor_followups_capture", "freeze-ordinary-v2", "--plan-ref", plan_ref,
                        "--capture-cycle-id", cycle_id, "--write",
                    ],
                )
                public(
                    "followups-apply",
                    [
                        "planveyor_followups_apply", "--frozen-manifest",
                        str(frozen["frozen_manifest_path"]), "--apply",
                    ],
                )
                closeout = public(
                    "capture-aware-docs-closeout",
                    [
                        "planveyor_docs_closeout", plan_ref,
                        "--followups-capture-cycle-id", cycle_id, "--json",
                    ],
                )
                self.assertEqual(closeout["schema"], "docs_closeout_payload.v1")

                if materialized:
                    self.assertEqual(closeout["final_docs_commit"], "required")
                    preflight = public(
                        "capture-aware-preflight",
                        [
                            "planveyor_plan_closeout_preflight", "--docs-closeout-json", "-",
                            "--json", plan_ref,
                        ],
                        json.dumps(closeout, ensure_ascii=False) + "\n",
                    )
                    commit = public(
                        "plan-bundle-commit-exact",
                        [
                            "planveyor_plan_bundle", "--commit-exact", "--preflight-json",
                            "-", "--message-auto", plan_ref,
                        ],
                        json.dumps(preflight, ensure_ascii=False) + "\n",
                    )
                    fresh = public(
                        "fresh-capture-aware-docs-closeout",
                        [
                            "planveyor_docs_closeout", plan_ref,
                            "--followups-capture-cycle-id", cycle_id, "--json",
                        ],
                    )
                    self.assertIn(fresh["final_docs_commit"], {"landed", "no_op"})
                    doc_lint = public("doc-lint", ["planveyor_doc_lint"], expect_json=False)
                    self.assertIsInstance(doc_lint, str)
                    self.assertIn("doc-lint: OK", doc_lint)
                    public(
                        "process-improvements-lint",
                        ["planveyor_runtime_py", "process_improvements_lint.py", "--format", "json"],
                    )
                    public("consumer-doctor", ["planveyor_consumer_doctor"])
                    trace["docs_commit"] = {"commit_result": commit, "fresh_closeout": fresh}
                else:
                    self.assertEqual(closeout["final_docs_commit"], "no_op")

                readback = public(
                    "capture-readback",
                    [
                        "planveyor_followups_capture", "read", "--plan-ref", plan_ref,
                        "--capture-cycle-id", cycle_id,
                    ],
                )
                terminal_after = {
                    path: (fixture.target_root / path).read_bytes()
                    for path in terminal_paths
                }
                self.assertEqual(terminal_after, terminal_before)
                self.assertEqual(tree_snapshot(fixture.runtime_root), runtime_before)
                self.assertEqual(
                    self._public_pi_candidate_hashes(SCRIPT_DIR.parent),
                    source_candidate_hashes,
                )
                self.assertEqual(
                    self._public_pi_candidate_hashes(fixture.runtime_root),
                    fixture_candidate_hashes,
                )
                pi_root = fixture.target_root / "docs/process_improvements"
                capture_root = fixture.target_root / ".tmp/followups_capture"
                trace["final"] = {
                    "target_head": git(fixture.target_root, "rev-parse", "HEAD"),
                    "target_status": git(fixture.target_root, "status", "--short"),
                    "terminal_preserved": True,
                    "terminal_sha256": {
                        path: hashlib.sha256(data).hexdigest()
                        for path, data in terminal_after.items()
                    },
                    "runtime_unchanged": True,
                    "candidate_source_fixture_equal": True,
                    "candidate_source_sha256": self._public_pi_candidate_hashes(SCRIPT_DIR.parent),
                    "candidate_fixture_sha256": self._public_pi_candidate_hashes(fixture.runtime_root),
                    "process_improvement_paths": {
                        path.relative_to(fixture.target_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(pi_root.rglob("*")) if path.is_file()
                    },
                    "capture_paths": {
                        path.relative_to(fixture.target_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(capture_root.rglob("*")) if path.is_file()
                    },
                    "capture_readback": readback,
                }
        finally:
            print(json.dumps(trace, ensure_ascii=False, sort_keys=True))

    def test_public_pi_composition_clean_noop(self) -> None:
        self._run_public_pi_composition(materialized=False)

    def test_public_pi_composition_materialized_duplicate(self) -> None:
        self._run_public_pi_composition(materialized=True)

    def test_public_pi_facade_runs_all_general_roles_and_v2_replay(self) -> None:
        with AuthorityFixture() as fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(fixture)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(fixture.runtime_root)
            bodies = {
                "Architect": self._public_pi_clean_body(),
                "Coder": self._public_pi_suggestion_body(plan_ref),
                "Planner": self._public_pi_clean_body(),
                "Reviewer": self._public_pi_suggestion_body(plan_ref),
            }
            payloads: dict[str, dict[str, object]] = {}
            for role in ("Architect", "Coder", "Planner", "Reviewer"):
                result = self._run_public_pi_collection(
                    fixture,
                    plan_ref=plan_ref,
                    role=role,
                    body=bodies[role],
                    cycle_id=cycle_id,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payloads[role] = json.loads(result.stdout)

            banners: set[str] = set()
            workflow_ref = "docs/tools/prompts/manager_collab_pipeline.md"
            self.assertTrue((fixture.target_root / workflow_ref).is_file())
            for name in ("index", "deferred", "promotion_surface"):
                surface = fixture.target_root / f"docs/process_improvements/{name}.md"
                text = surface.read_text(encoding="utf-8")
                banner_lines = [line for line in text.splitlines() if line.startswith("_DO NOT EDIT")]
                self.assertEqual(len(banner_lines), 1, surface)
                banner = banner_lines[0]
                banners.add(banner)
                self.assertIn("PI/docs-closeout workflow", banner)
                self.assertIn(f"`{workflow_ref}`", banner)
                self.assertIn("Standalone `--rebuild-derived` недоступен при engaged authority", banner)
                self.assertNotIn("regenerate via", banner)
                self.assertNotIn("scripts/process_improvements_collect.py", banner)
                self.assertNotIn("docs/process_improvements/README.md", banner)
                self.assertIn("_Auto-generated by `scripts/process_improvements_collect.py` on ", text)
            self.assertEqual(len(banners), 1)

            self.assertEqual(payloads["Architect"]["process_improvement_capture_state"], "clean_noop")
            self.assertEqual(payloads["Coder"]["process_improvement_capture_state"], "materialized")
            self.assertEqual(payloads["Planner"]["process_improvement_capture_state"], "clean_noop")
            self.assertEqual(payloads["Reviewer"]["process_improvement_capture_state"], "already_tracked")
            self.assertTrue(payloads["Reviewer"]["duplicates"])
            self.assertEqual(
                payloads["Reviewer"]["before_process_improvement_files"],
                payloads["Coder"]["after_process_improvement_files"],
            )
            self.assertEqual(
                payloads["Reviewer"]["after_process_improvement_files"],
                payloads["Coder"]["after_process_improvement_files"],
            )
            self.assertTrue(str(payloads["Coder"]["process_improvement_receipt_path"]).startswith(".tmp/"))

            replay = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Coder",
                body=bodies["Coder"],
                cycle_id=cycle_id,
            )
            self.assertEqual(replay.returncode, 0, replay.stderr)
            replay_payload = json.loads(replay.stdout)
            self.assertEqual(replay_payload["process_improvement_capture_replay"], "exact_leaf")
            self.assertEqual(replay_payload["process_improvement_capture_state"], "materialized")

            try:
                import followups_capture
            except ModuleNotFoundError:
                from scripts import followups_capture

            checkpoint = followups_capture.checkpoint_general_pi(
                fixture.target_root,
                plan_ref,
                cycle_id,
            )
            self.assertEqual(checkpoint["reason_code"], "followup_capture_pi_general_checkpointed")
            checkpoint_replay = followups_capture.checkpoint_general_pi(
                fixture.target_root,
                plan_ref,
                cycle_id,
            )
            self.assertEqual(
                checkpoint_replay["reason_code"],
                "followup_capture_pi_general_checkpoint_already_published",
            )
            self._assert_public_pi_runtime_preserved(
                fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

    def test_public_pi_missing_cycle_pairs_semantic_reason_and_preserves_fixture(self) -> None:
        with AuthorityFixture() as fixture:
            plan_ref, _cycle_id = self._prepare_public_pi_fixture(
                fixture,
                semantic_sentinel=True,
            )
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(fixture.runtime_root)
            target_before = tree_snapshot(fixture.target_root)
            body = "SENTINEL: collector must not consume this input\n"

            result = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=None,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["context_state"], "engaged")
            self.assertEqual(payload["runtime_commit"], fixture.runtime_commit)
            self.assertEqual(
                payload["reason_code"],
                "engaged_private_delivery_unsupported",
            )
            self.assertNotIn("internal_error", result.stdout + result.stderr)
            self._assert_public_pi_runtime_preserved(
                fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )
            self.assertEqual(tree_snapshot(fixture.target_root), target_before)

    def test_public_pi_pre_admission_negative_matrix_keeps_stdin_and_pi_map_unread(self) -> None:
        """Pair real facades with attested terminal semantics on one shared recipe."""

        body = b"SENTINEL: do not consume pre-admission stdin\n"
        for role, has_cycle, expected_reason in (
            ("Architect", False, "engaged_private_delivery_unsupported"),
            ("Manager", True, "followup_capture_pi_general_collection_role_invalid"),
            ("Owner", True, "followup_capture_pi_general_collection_role_invalid"),
        ):
            with self.subTest(role=role, has_cycle=has_cycle):
                public_recipe: dict[str, object]
                with AuthorityFixture() as public_fixture:
                    plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
                    source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
                    runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
                    self.assertEqual(runtime_hashes, source_hashes)
                    selected_cycle = cycle_id if has_cycle else None
                    public_argv = tuple(
                        self._public_pi_collection_arguments(
                            plan_ref=plan_ref, role=role, cycle_id=selected_cycle,
                        )[2:]
                    )
                    recipe_argv = tuple(
                        "<fresh-cycle>" if has_cycle and item == selected_cycle else item
                        for item in public_argv
                    )
                    public_recipe = {
                        "stdin_sha256": hashlib.sha256(body).hexdigest(),
                        "argv": recipe_argv,
                        "role": role,
                        "source_ref": plan_ref,
                        "cycle_state": "active" if has_cycle else "missing",
                        "pi_map": "unsafe_ancestor",
                        "expected_reason": expected_reason,
                    }
                    source_before = (SCRIPT_DIR / "process_improvements_collect.py").read_bytes()
                    self.assertEqual(
                        (public_fixture.runtime_root / "scripts/process_improvements_collect.py").read_bytes(),
                        source_before,
                    )
                    outside = public_fixture.root / "public-unsafe-pi-map"
                    outside.mkdir()
                    map_path = public_fixture.target_root / "docs/process_improvements"
                    map_path.rename(map_path.with_name("process_improvements-before-negative"))
                    map_path.symlink_to(outside, target_is_directory=True)
                    target_before = tree_snapshot(public_fixture.target_root)
                    result = self._run_public_pi_collection_open_stdin(
                        public_fixture,
                        plan_ref=plan_ref,
                        role=role,
                        cycle_id=selected_cycle,
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("internal_error", result.stdout + result.stderr)
                    self.assertEqual(tree_snapshot(public_fixture.target_root), target_before)
                    self.assertEqual(list(outside.iterdir()), [])
                    self._assert_public_pi_runtime_preserved(
                        public_fixture,
                        expected_hashes=runtime_hashes,
                        source_hashes=source_hashes,
                    )

                with AuthorityFixture() as semantic_fixture:
                    plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
                    selected_cycle = cycle_id if has_cycle else None
                    semantic_argv = tuple(
                        self._public_pi_collection_arguments(
                            plan_ref=plan_ref, role=role, cycle_id=selected_cycle,
                        )[2:]
                    )
                    # The two halves share every recipe field.  Their only
                    # deliberate fixture differences are root, hook runtime
                    # commit, and this fresh capture-cycle UUID.
                    self._install_public_pi_semantic_sentinel(
                        semantic_fixture,
                        argv=semantic_argv,
                        expected_reason=expected_reason,
                    )
                    semantic_fixture.runtime_commit = commit_all(
                        semantic_fixture.runtime_root,
                        "disposable public PI semantic terminal hook",
                    )
                    marker_path = semantic_fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    marker["source_commit"] = semantic_fixture.runtime_commit
                    write(
                        semantic_fixture.target_root,
                        "docs/_meta/planveyor_contract_authority.v1.json",
                        json.dumps(marker, sort_keys=True) + "\n",
                    )
                    commit_all(semantic_fixture.target_root, "rebind disposable semantic runtime")
                    source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
                    runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
                    recipe_argv = tuple(
                        "<fresh-cycle>" if has_cycle and item == selected_cycle else item
                        for item in semantic_argv
                    )
                    semantic_recipe = {
                        "stdin_sha256": hashlib.sha256(body).hexdigest(),
                        "argv": recipe_argv,
                        "role": role,
                        "source_ref": plan_ref,
                        "cycle_state": "active" if has_cycle else "missing",
                        "pi_map": "unsafe_ancestor",
                        "expected_reason": expected_reason,
                    }
                    self.assertEqual(semantic_recipe, public_recipe)
                    outside = semantic_fixture.root / "semantic-unsafe-pi-map"
                    outside.mkdir()
                    map_path = semantic_fixture.target_root / "docs/process_improvements"
                    map_path.rename(map_path.with_name("process_improvements-before-negative"))
                    map_path.symlink_to(outside, target_is_directory=True)
                    marker = json.loads(marker_path.read_text(encoding="utf-8"))
                    self.assertEqual(marker["source_commit"], semantic_fixture.runtime_commit)
                    target_before = tree_snapshot(semantic_fixture.target_root)
                    result = self._run_public_pi_collection_open_stdin(
                        semantic_fixture,
                        plan_ref=plan_ref,
                        role=role,
                        cycle_id=selected_cycle,
                    )
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["context_state"], "engaged")
                    self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
                    self.assertEqual(payload["reason_code"], expected_reason)
                    self._assert_public_pi_runtime_preserved(
                        semantic_fixture,
                        expected_hashes=runtime_hashes,
                        source_hashes=source_hashes,
                        semantic_collector_hook=True,
                    )
                    self.assertEqual(tree_snapshot(semantic_fixture.target_root), target_before)
                    self.assertEqual(list(outside.iterdir()), [])

    def test_public_pi_phase_drift_after_stdin_blocks_all_collector_effects(self) -> None:
        """A real active admission must be checked again after stdin before output."""

        expected_reason = "followup_capture_pi_general_collection_phase_closed"

        def block_cycle(fixture: AuthorityFixture, plan_ref: str, cycle_id: str) -> None:
            try:
                import followups_capture
            except ModuleNotFoundError:
                from scripts import followups_capture
            with followups_capture.CaptureHost(fixture.target_root, plan_ref, create=False) as host:
                cycle_fd, _cycle_identity = followups_capture._open_cycle(host, cycle_id)
                try:
                    receipt, raw, _receipt_identity = followups_capture._read_receipt(
                        cycle_fd, plan_ref, cycle_id
                    )
                    blocked = followups_capture._block_cycle(
                        host,
                        cycle_fd,
                        cycle_id,
                        receipt,
                        raw,
                        role="Architect",
                        reason_code="test_public_pi_phase_drift",
                        message="controlled phase drift after collector admission",
                        process_improvement_files={},
                        checkpoint_pi_failure=True,
                    )
                finally:
                    os.close(cycle_fd)
            self.assertEqual(blocked["state"], "blocked")
            self.assertEqual(blocked["reason_code"], "test_public_pi_phase_drift")

        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            try:
                import process_improvements_collect as collector
            except ModuleNotFoundError:
                from scripts import process_improvements_collect as collector
            collector_receipt = public_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            body = self._public_pi_suggestion_body(plan_ref)
            public_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            public_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active_then_blocked_after_stdin",
            }
            pi_root = public_fixture.target_root / "docs/process_improvements"
            pi_before = tree_snapshot(pi_root)
            process, command = self._start_public_pi_collection_open_stdin(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                cycle_id=cycle_id,
            )
            time.sleep(0.3)
            self.assertIsNone(process.poll(), "collector must still be waiting on its open stdin")
            block_cycle(public_fixture, plan_ref, cycle_id)
            result = self._finish_public_pi_collection_open_stdin(
                process,
                command,
                body=body,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("internal_error", result.stdout + result.stderr)
            self.assertEqual(tree_snapshot(pi_root), pi_before)
            self.assertFalse(collector_receipt.exists())
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            semantic_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._install_public_pi_semantic_sentinel(
                semantic_fixture,
                argv=semantic_argv,
                expected_reason=expected_reason,
            )
            semantic_fixture.runtime_commit = commit_all(
                semantic_fixture.runtime_root,
                "disposable public PI phase-drift terminal hook",
            )
            marker_path = semantic_fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_commit"] = semantic_fixture.runtime_commit
            write(
                semantic_fixture.target_root,
                "docs/_meta/planveyor_contract_authority.v1.json",
                json.dumps(marker, sort_keys=True) + "\n",
            )
            commit_all(semantic_fixture.target_root, "rebind disposable phase-drift runtime")
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            body = self._public_pi_suggestion_body(plan_ref)
            semantic_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in semantic_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active_then_blocked_after_stdin",
            }
            self.assertEqual(semantic_recipe, public_recipe)
            self.assertEqual(
                json.loads(marker_path.read_text(encoding="utf-8"))["source_commit"],
                semantic_fixture.runtime_commit,
            )
            pi_root = semantic_fixture.target_root / "docs/process_improvements"
            pi_before = tree_snapshot(pi_root)
            process, command = self._start_public_pi_collection_open_stdin(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                cycle_id=cycle_id,
            )
            time.sleep(0.3)
            self.assertIsNone(process.poll(), "collector must still be waiting on its open stdin")
            block_cycle(semantic_fixture, plan_ref, cycle_id)
            result = self._finish_public_pi_collection_open_stdin(
                process,
                command,
                body=body,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["context_state"], "engaged")
            self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
            self.assertEqual(payload["reason_code"], expected_reason)
            self.assertEqual(tree_snapshot(pi_root), pi_before)
            collector_receipt = semantic_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            self.assertFalse(collector_receipt.exists())

    def test_public_pi_checkpointed_replay_pairs_semantic_reason_before_stdin(self) -> None:
        """A stale post-checkpoint collector call rejects before reading stdin or the PI map."""

        expected_reason = "followup_capture_pi_general_collection_checkpoint_closed"

        def checkpoint(fixture: AuthorityFixture, plan_ref: str, cycle_id: str) -> None:
            for role in ("Architect", "Coder", "Planner", "Reviewer"):
                collected = self._run_public_pi_collection(
                    fixture,
                    plan_ref=plan_ref,
                    role=role,
                    body=self._public_pi_clean_body(),
                    cycle_id=cycle_id,
                )
                self.assertEqual(collected.returncode, 0, collected.stdout + collected.stderr)
            published = self._run_public_pi_command(
                fixture,
                label="checkpoint-general-pi-before-stale-replay",
                arguments=[
                    "planveyor_followups_capture",
                    "checkpoint-general-pi",
                    "--plan-ref",
                    plan_ref,
                    "--capture-cycle-id",
                    cycle_id,
                ],
            )
            self.assertEqual(published.returncode, 0, published.stdout + published.stderr)
            self.assertEqual(
                json.loads(published.stdout)["reason_code"],
                "followup_capture_pi_general_checkpointed",
            )

        body = b"SENTINEL: checkpointed collector must not consume stdin\n"
        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            checkpoint(public_fixture, plan_ref, cycle_id)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            public_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            public_recipe = {
                "stdin_sha256": hashlib.sha256(body).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "checkpointed",
                "pi_map": "unsafe_ancestor",
                "expected_reason": expected_reason,
            }
            outside = public_fixture.root / "checkpointed-public-unsafe-map"
            outside.mkdir()
            pi_root = public_fixture.target_root / "docs/process_improvements"
            pi_root.rename(pi_root.with_name("process_improvements-before-checkpointed-replay"))
            pi_root.symlink_to(outside, target_is_directory=True)
            target_before = tree_snapshot(public_fixture.target_root)
            result = self._run_public_pi_collection_open_stdin(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                cycle_id=cycle_id,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("internal_error", result.stdout + result.stderr)
            self.assertEqual(tree_snapshot(public_fixture.target_root), target_before)
            self.assertEqual(list(outside.iterdir()), [])
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            checkpoint(semantic_fixture, plan_ref, cycle_id)
            semantic_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._rebind_public_pi_semantic_runtime(
                semantic_fixture,
                argv=semantic_argv,
                expected_reason=expected_reason,
                message="disposable checkpointed PI semantic terminal hook",
            )
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            semantic_recipe = {
                "stdin_sha256": hashlib.sha256(body).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in semantic_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "checkpointed",
                "pi_map": "unsafe_ancestor",
                "expected_reason": expected_reason,
            }
            self.assertEqual(semantic_recipe, public_recipe)
            outside = semantic_fixture.root / "checkpointed-semantic-unsafe-map"
            outside.mkdir()
            pi_root = semantic_fixture.target_root / "docs/process_improvements"
            pi_root.rename(pi_root.with_name("process_improvements-before-checkpointed-replay"))
            pi_root.symlink_to(outside, target_is_directory=True)
            target_before = tree_snapshot(semantic_fixture.target_root)
            result = self._run_public_pi_collection_open_stdin(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                cycle_id=cycle_id,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["context_state"], "engaged")
            self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
            self.assertEqual(payload["reason_code"], expected_reason)
            self.assertEqual(tree_snapshot(semantic_fixture.target_root), target_before)
            self.assertEqual(list(outside.iterdir()), [])
            self._assert_public_pi_runtime_preserved(
                semantic_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_public_pi_post_admission_body_validation_pairs_semantic_error(self) -> None:
        """Malformed or foreign parsed bodies leave only their truthful blocked receipt."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        cases = (
            (
                "malformed_structured_body",
                lambda plan_ref: textwrap.dedent(
                    f"""\
                    ## Process improvements
                    ### Suggestion 1
                    - symptom: public fixture requires complete structured content
                    - process_gap: malformed role output must be rejected after admission
                    - owner: Architect
                    - promotion_class: helper_change
                    - trigger_ref: docs/code_reviews/public_pi_fixture.md#C2
                    - source_ref: {plan_ref}
                    """
                ),
                "Missing required field: suggested_fix",
            ),
            (
                "parsed_foreign_source",
                lambda plan_ref: self._public_pi_suggestion_body(plan_ref).replace(
                    f"- source_ref: {plan_ref}",
                    "- source_ref: docs/plans/260927_foreign_source.md",
                    1,
                ),
                "Structured \u0060source_ref\u0060 must match manager-fed/header source_ref",
            ),
        )

        for case_name, body_for, expected_error in cases:
            with self.subTest(case=case_name):
                public_recipe: dict[str, object]
                public_projection: dict[str, object]
                with AuthorityFixture() as public_fixture:
                    plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
                    body = body_for(plan_ref)
                    source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
                    runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
                    public_argv = tuple(
                        self._public_pi_collection_arguments(
                            plan_ref=plan_ref,
                            role="Architect",
                            cycle_id=cycle_id,
                        )[2:]
                    )
                    public_recipe = {
                        "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_argv),
                        "role": "Architect",
                        "source_ref": plan_ref,
                        "cycle_state": "active",
                        "validation": case_name,
                        "expected_error": expected_error,
                    }
                    pi_before = collector._safe_pi_object_map(public_fixture.target_root, plan_ref)
                    receipt_path = public_fixture.target_root / collector.capture_receipt_rel_path(
                        plan_ref, "Architect", cycle_id
                    )
                    result = self._run_public_pi_collection(
                        public_fixture,
                        plan_ref=plan_ref,
                        role="Architect",
                        body=body,
                        cycle_id=cycle_id,
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("internal_error", result.stdout + result.stderr)
                    self.assertEqual(
                        collector._safe_pi_object_map(public_fixture.target_root, plan_ref),
                        pi_before,
                    )
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    self.assertEqual(receipt["capture_state"], "blocked")
                    self.assertEqual(receipt["reason_code"], "collector_error")
                    self.assertIn(expected_error, str(receipt["error"]))
                    self.assertEqual(list(receipt_path.parent.glob("*.json")), [receipt_path])
                    public_projection = self._public_pi_capture_projection(receipt)
                    self._assert_public_pi_runtime_preserved(
                        public_fixture,
                        expected_hashes=runtime_hashes,
                        source_hashes=source_hashes,
                    )

                with AuthorityFixture() as semantic_fixture:
                    plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
                    body = body_for(plan_ref)
                    semantic_argv = tuple(
                        self._public_pi_collection_arguments(
                            plan_ref=plan_ref,
                            role="Architect",
                            cycle_id=cycle_id,
                        )[2:]
                    )
                    self._rebind_public_pi_semantic_runtime(
                        semantic_fixture,
                        argv=semantic_argv,
                        expected_error=expected_error,
                        message=f"disposable {case_name} PI semantic terminal hook",
                    )
                    source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
                    runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
                    semantic_recipe = {
                        "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in semantic_argv),
                        "role": "Architect",
                        "source_ref": plan_ref,
                        "cycle_state": "active",
                        "validation": case_name,
                        "expected_error": expected_error,
                    }
                    self.assertEqual(semantic_recipe, public_recipe)
                    pi_before = collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref)
                    receipt_path = semantic_fixture.target_root / collector.capture_receipt_rel_path(
                        plan_ref, "Architect", cycle_id
                    )
                    result = self._run_public_pi_collection(
                        semantic_fixture,
                        plan_ref=plan_ref,
                        role="Architect",
                        body=body,
                        cycle_id=cycle_id,
                    )
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["context_state"], "engaged")
                    self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
                    self.assertEqual(payload["error_type"], "ValueError")
                    self.assertIn(expected_error, payload["error"])
                    self.assertEqual(
                        collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref),
                        pi_before,
                    )
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    self.assertEqual(receipt["capture_state"], "blocked")
                    self.assertEqual(receipt["reason_code"], "collector_error")
                    self.assertIn(expected_error, str(receipt["error"]))
                    self.assertEqual(list(receipt_path.parent.glob("*.json")), [receipt_path])
                    self.assertEqual(
                        self._public_pi_capture_projection(receipt),
                        public_projection,
                    )
                    self._assert_public_pi_runtime_preserved(
                        semantic_fixture,
                        expected_hashes=runtime_hashes,
                        source_hashes=source_hashes,
                        semantic_collector_hook=True,
                    )

    def test_public_pi_differing_input_replay_pairs_semantic_error(self) -> None:
        """A byte-different V2 replay preserves the accepted receipt and PI map."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        accepted_body = self._public_pi_clean_body()
        changed_body = accepted_body + "\n"
        expected_error = "process-improvement v2 continuation receipt input digest conflicts before collection"
        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            accepted = self._run_public_pi_collection(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=accepted_body,
                cycle_id=cycle_id,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            receipt_path = public_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            accepted_receipt = receipt_path.read_bytes()
            pi_before = collector._safe_pi_object_map(public_fixture.target_root, plan_ref)
            public_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            public_recipe = {
                "accepted_stdin_sha256": hashlib.sha256(accepted_body.encode("utf-8")).hexdigest(),
                "stdin_sha256": hashlib.sha256(changed_body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active_with_accepted_v2_receipt",
                "expected_error": expected_error,
            }
            rejected = self._run_public_pi_collection(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=changed_body,
                cycle_id=cycle_id,
            )
            self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            self.assertIn("internal_error", rejected.stdout + rejected.stderr)
            self.assertEqual(receipt_path.read_bytes(), accepted_receipt)
            self.assertEqual(
                collector._safe_pi_object_map(public_fixture.target_root, plan_ref),
                pi_before,
            )
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            accepted = self._run_public_pi_collection(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=accepted_body,
                cycle_id=cycle_id,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            semantic_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._rebind_public_pi_semantic_runtime(
                semantic_fixture,
                argv=semantic_argv,
                expected_error=expected_error,
                message="disposable differing-input PI semantic terminal hook",
            )
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            receipt_path = semantic_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            accepted_receipt = receipt_path.read_bytes()
            pi_before = collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref)
            semantic_recipe = {
                "accepted_stdin_sha256": hashlib.sha256(accepted_body.encode("utf-8")).hexdigest(),
                "stdin_sha256": hashlib.sha256(changed_body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in semantic_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active_with_accepted_v2_receipt",
                "expected_error": expected_error,
            }
            self.assertEqual(semantic_recipe, public_recipe)
            rejected = self._run_public_pi_collection(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=changed_body,
                cycle_id=cycle_id,
            )
            self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
            payload = json.loads(rejected.stdout)
            self.assertEqual(payload["context_state"], "engaged")
            self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
            self.assertEqual(payload["error_type"], "ValueError")
            self.assertIn(expected_error, payload["error"])
            self.assertEqual(receipt_path.read_bytes(), accepted_receipt)
            self.assertEqual(
                collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref),
                pi_before,
            )
            self._assert_public_pi_runtime_preserved(
                semantic_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_public_pi_rebuild_derived_flag_pairs_semantic_private_rejection(self) -> None:
        """One representative private collector flag remains unavailable through the public facade."""

        expected_reason = "engaged_private_delivery_unsupported"
        arguments = ["planveyor_runtime_py", "process_improvements_collect.py", "--rebuild-derived", "--json"]
        semantic_argv = tuple(arguments[2:])
        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            public_recipe = {
                "stdin_sha256": None,
                "argv": semantic_argv,
                "role": None,
                "source_ref": None,
                "cycle_state": "active_but_unconsumed",
                "command_mode": "rebuild-derived",
                "expected_reason": expected_reason,
            }
            target_before = tree_snapshot(public_fixture.target_root)
            result = self._run_public_pi_command(
                public_fixture,
                label="collector-rebuild-derived-private-rejection",
                arguments=arguments,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("internal_error", result.stdout + result.stderr)
            self.assertEqual(tree_snapshot(public_fixture.target_root), target_before)
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            self._rebind_public_pi_semantic_runtime(
                semantic_fixture,
                argv=semantic_argv,
                expected_reason=expected_reason,
                message="disposable rebuild-derived PI semantic terminal hook",
            )
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            semantic_recipe = {
                "stdin_sha256": None,
                "argv": semantic_argv,
                "role": None,
                "source_ref": None,
                "cycle_state": "active_but_unconsumed",
                "command_mode": "rebuild-derived",
                "expected_reason": expected_reason,
            }
            self.assertEqual(semantic_recipe, public_recipe)
            target_before = tree_snapshot(semantic_fixture.target_root)
            result = self._run_public_pi_command(
                semantic_fixture,
                label="collector-rebuild-derived-semantic-private-rejection",
                arguments=arguments,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["context_state"], "engaged")
            self.assertEqual(payload["runtime_commit"], semantic_fixture.runtime_commit)
            self.assertEqual(payload["reason_code"], expected_reason)
            self.assertEqual(tree_snapshot(semantic_fixture.target_root), target_before)
            self._assert_public_pi_runtime_preserved(
                semantic_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_public_pi_blocked_recovery_requires_recorded_after_map_and_repairs_derived(self) -> None:
        """Recover one truthful blocked V2 record without a second carrier."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        with AuthorityFixture() as fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(fixture.runtime_root)
            first = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            receipt_path = fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            original = json.loads(receipt_path.read_text(encoding="utf-8"))
            original_before = original["before_process_improvement_files"]

            index_path = fixture.target_root / collector.INDEX_PATH
            index_path.write_text(collector.default_index_text(), encoding="utf-8")
            blocked_after = collector._safe_pi_object_map(fixture.target_root, plan_ref)
            blocked = dict(original)
            blocked.update(
                capture_state="blocked",
                reason_code="collector_error",
                error="controlled derived publication failure after backlog write",
                after_process_improvement_files=blocked_after,
                process_improvement_path_results=collector._capture_pi_path_results(
                    original_before, blocked_after
                ),
            )
            receipt_path.write_text(
                json.dumps(blocked, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            blocked_bytes = receipt_path.read_bytes()

            index_path.write_text(collector.default_index_text() + "\n", encoding="utf-8")
            mismatch = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertNotEqual(mismatch.returncode, 0, mismatch.stdout + mismatch.stderr)
            self.assertIn("internal_error", mismatch.stdout + mismatch.stderr)
            self.assertEqual(receipt_path.read_bytes(), blocked_bytes)

            index_path.write_text(collector.default_index_text(), encoding="utf-8")
            recovered = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            payload = json.loads(recovered.stdout)
            self.assertEqual(payload["process_improvement_capture_state"], "materialized")
            self.assertEqual(payload["before_process_improvement_files"], original_before)
            self.assertEqual(set(payload["derived_surfaces"]), {
                collector.INDEX_PATH.as_posix(),
                collector.DEFERRED_PATH.as_posix(),
                collector.PROMOTION_PATH.as_posix(),
            })
            replacement = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertNotEqual(receipt_path.read_bytes(), blocked_bytes)
            self.assertEqual(replacement["before_process_improvement_files"], original_before)
            self.assertEqual(
                replacement["after_process_improvement_files"],
                collector._safe_pi_object_map(fixture.target_root, plan_ref),
            )
            self.assertEqual(
                payload["process_improvement_path_results"],
                replacement["process_improvement_path_results"],
            )
            self.assertTrue(collector.check_derived_surfaces(fixture.target_root)["ok"])
            self.assertEqual(list(receipt_path.parent.glob("*.json")), [receipt_path])
            self._checkpoint_public_pi_after_architect(fixture, plan_ref=plan_ref, cycle_id=cycle_id)
            self._assert_public_pi_runtime_preserved(
                fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

    def test_public_pi_semantic_failure_after_backlog_recovers_exact_blocked_state(self) -> None:
        """A controlled post-backlog failure leaves a truthful recoverable V2 receipt."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        with AuthorityFixture() as fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            failure_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._install_public_pi_failure_after_backlog_sentinel(
                fixture,
                argv=failure_argv,
            )
            fixture.runtime_commit = commit_all(
                fixture.runtime_root,
                "disposable public PI post-backlog failure hook",
            )
            marker_path = fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_commit"] = fixture.runtime_commit
            write(
                fixture.target_root,
                "docs/_meta/planveyor_contract_authority.v1.json",
                json.dumps(marker, sort_keys=True) + "\n",
            )
            commit_all(fixture.target_root, "rebind disposable failure runtime")
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(fixture.runtime_root)

            failed = self._run_public_pi_collection(
                fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
            failed_payload = json.loads(failed.stdout)
            self.assertEqual(failed_payload["context_state"], "engaged")
            self.assertEqual(failed_payload["runtime_commit"], fixture.runtime_commit)
            self.assertEqual(failed_payload["reason_code"], "collector_error")
            self.assertIn("derived_failure_after_backlog", failed_payload["error"])

            receipt_path = fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            blocked = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["capture_state"], "blocked")
            self.assertEqual(blocked["reason_code"], "collector_error")
            self.assertTrue(blocked["after_process_improvement_files"])
            self.assertFalse((fixture.target_root / collector.INDEX_PATH).exists())
            self.assertEqual(
                blocked["after_process_improvement_files"],
                collector._safe_pi_object_map(fixture.target_root, plan_ref),
            )
            blocked_before = blocked["before_process_improvement_files"]
            blocked_bytes = receipt_path.read_bytes()

            changed_input = body + "\n"
            self.assertNotEqual(
                hashlib.sha256(changed_input.encode("utf-8")).hexdigest(),
                blocked["input_sha256"],
            )
            changed = self._run_public_pi_command(
                fixture,
                label="collector-Architect-partial-recovery-changed-input",
                arguments=[
                    *self._public_pi_collection_arguments(
                        plan_ref=plan_ref,
                        role="Architect",
                        cycle_id=cycle_id,
                    ),
                    "--format",
                    "json",
                ],
                input_text=changed_input,
            )
            self.assertNotEqual(changed.returncode, 0, changed.stdout + changed.stderr)
            self.assertIn("internal_error", changed.stdout + changed.stderr)
            self.assertEqual(receipt_path.read_bytes(), blocked_bytes)

            recovered = self._run_public_pi_command(
                fixture,
                label="collector-Architect-blocked-recovery",
                arguments=[
                    *self._public_pi_collection_arguments(
                        plan_ref=plan_ref,
                        role="Architect",
                        cycle_id=cycle_id,
                    ),
                    "--format",
                    "json",
                ],
                input_text=body,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            recovered_payload = json.loads(recovered.stdout)
            self.assertEqual(recovered_payload["process_improvement_capture_state"], "materialized")
            self.assertEqual(recovered_payload["before_process_improvement_files"], blocked_before)
            self.assertNotEqual(receipt_path.read_bytes(), blocked_bytes)
            continuation = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(continuation["before_process_improvement_files"], blocked_before)
            self.assertEqual(
                continuation["after_process_improvement_files"],
                collector._safe_pi_object_map(fixture.target_root, plan_ref),
            )
            self.assertEqual(
                recovered_payload["process_improvement_path_results"],
                continuation["process_improvement_path_results"],
            )
            self.assertTrue(collector.check_derived_surfaces(fixture.target_root)["ok"])
            self.assertEqual(list(receipt_path.parent.glob("*.json")), [receipt_path])
            self._checkpoint_public_pi_after_architect(fixture, plan_ref=plan_ref, cycle_id=cycle_id)
            self._assert_public_pi_runtime_preserved(
                fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_public_pi_partial_recovery_replaces_one_blocked_carrier_truthfully(self) -> None:
        """Same-input recovery updates the original blocked receipt after further partial output."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            public_args = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            public_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_args),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active",
                "fault": "post_backlog_and_post_first_derived_write",
            }
            public = self._run_public_pi_collection(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(public.returncode, 0, public.stdout + public.stderr)
            self.assertEqual(
                json.loads(public.stdout)["process_improvement_capture_state"], "materialized"
            )
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            failure_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._install_public_pi_recovery_failure_sentinel(
                semantic_fixture,
                argv=failure_argv,
                plan_ref=plan_ref,
                cycle_id=cycle_id,
            )
            semantic_fixture.runtime_commit = commit_all(
                semantic_fixture.runtime_root,
                "disposable public PI partial-recovery failure hook",
            )
            marker_path = semantic_fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_commit"] = semantic_fixture.runtime_commit
            write(
                semantic_fixture.target_root,
                "docs/_meta/planveyor_contract_authority.v1.json",
                json.dumps(marker, sort_keys=True) + "\n",
            )
            commit_all(semantic_fixture.target_root, "rebind disposable partial-recovery runtime")
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            semantic_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in failure_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active",
                "fault": "post_backlog_and_post_first_derived_write",
            }
            self.assertEqual(semantic_recipe, public_recipe)
            self.assertEqual(
                json.loads(marker_path.read_text(encoding="utf-8"))["source_commit"],
                semantic_fixture.runtime_commit,
            )

            first = self._run_public_pi_collection(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(first.returncode, 2, first.stdout + first.stderr)
            self.assertIn("initial_derived_failure", json.loads(first.stdout)["error"])
            receipt_path = semantic_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            first_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            first_bytes = receipt_path.read_bytes()
            first_before = first_receipt["before_process_improvement_files"]
            first_after = first_receipt["after_process_improvement_files"]
            self.assertNotEqual(first_before, first_after)

            changed = self._run_public_pi_command(
                semantic_fixture,
                label="collector-Architect-partial-carrier-changed-input",
                arguments=[
                    *self._public_pi_collection_arguments(
                        plan_ref=plan_ref,
                        role="Architect",
                        cycle_id=cycle_id,
                    ),
                    "--format",
                    "json",
                ],
                input_text=body + "\n",
            )
            self.assertNotEqual(changed.returncode, 0, changed.stdout + changed.stderr)
            self.assertIn("internal_error", changed.stdout + changed.stderr)
            self.assertEqual(receipt_path.read_bytes(), first_bytes)

            second = self._run_public_pi_collection(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
            self.assertIn("recovery_derived_failure", json.loads(second.stdout)["error"])
            second_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            second_bytes = receipt_path.read_bytes()
            self.assertNotEqual(second_bytes, first_bytes)
            self.assertEqual(second_receipt["before_process_improvement_files"], first_before)
            self.assertEqual(
                second_receipt["after_process_improvement_files"],
                collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref),
            )
            self.assertNotEqual(second_receipt["after_process_improvement_files"], first_after)
            self.assertFalse(collector.check_derived_surfaces(semantic_fixture.target_root)["ok"])

            recovered = self._run_public_pi_command(
                semantic_fixture,
                label="collector-Architect-partial-carrier-final-recovery",
                arguments=[
                    *self._public_pi_collection_arguments(
                        plan_ref=plan_ref,
                        role="Architect",
                        cycle_id=cycle_id,
                    ),
                    "--format",
                    "json",
                ],
                input_text=body,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            recovered_payload = json.loads(recovered.stdout)
            self.assertEqual(recovered_payload["process_improvement_capture_state"], "materialized")
            self.assertEqual(recovered_payload["before_process_improvement_files"], first_before)
            continuation = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(continuation["before_process_improvement_files"], first_before)
            self.assertEqual(
                continuation["after_process_improvement_files"],
                collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref),
            )
            self.assertEqual(
                recovered_payload["process_improvement_path_results"],
                continuation["process_improvement_path_results"],
            )
            self.assertTrue(collector.check_derived_surfaces(semantic_fixture.target_root)["ok"])
            self.assertEqual(list(receipt_path.parent.glob("*.json")), [receipt_path])
            self._assert_public_pi_runtime_preserved(
                semantic_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_public_pi_unobservable_postmap_skips_fabricated_blocked_receipt(self) -> None:
        """An engaged exception cannot publish a false empty after-map receipt."""

        try:
            import process_improvements_collect as collector
        except ModuleNotFoundError:
            from scripts import process_improvements_collect as collector

        public_recipe: dict[str, object]
        with AuthorityFixture() as public_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(public_fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(public_fixture.runtime_root)
            public_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            public_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in public_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active",
                "fault": "post_effect_unsafe_map",
            }
            public = self._run_public_pi_collection(
                public_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(public.returncode, 0, public.stdout + public.stderr)
            self.assertEqual(
                json.loads(public.stdout)["process_improvement_capture_state"], "materialized"
            )
            self._assert_public_pi_runtime_preserved(
                public_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
            )

        with AuthorityFixture() as semantic_fixture:
            plan_ref, cycle_id = self._prepare_public_pi_fixture(semantic_fixture)
            body = self._public_pi_suggestion_body(plan_ref)
            semantic_argv = tuple(
                self._public_pi_collection_arguments(
                    plan_ref=plan_ref,
                    role="Architect",
                    cycle_id=cycle_id,
                )[2:]
            )
            self._install_public_pi_unobservable_postmap_sentinel(
                semantic_fixture,
                argv=semantic_argv,
            )
            semantic_fixture.runtime_commit = commit_all(
                semantic_fixture.runtime_root,
                "disposable public PI unobservable-postmap hook",
            )
            marker_path = semantic_fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_commit"] = semantic_fixture.runtime_commit
            write(
                semantic_fixture.target_root,
                "docs/_meta/planveyor_contract_authority.v1.json",
                json.dumps(marker, sort_keys=True) + "\n",
            )
            commit_all(semantic_fixture.target_root, "rebind disposable unobservable-postmap runtime")
            source_hashes = self._public_pi_candidate_hashes(SCRIPT_DIR.parent)
            runtime_hashes = self._public_pi_candidate_hashes(semantic_fixture.runtime_root)
            semantic_recipe = {
                "stdin_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "argv": tuple("<fresh-cycle>" if item == cycle_id else item for item in semantic_argv),
                "role": "Architect",
                "source_ref": plan_ref,
                "cycle_state": "active",
                "fault": "post_effect_unsafe_map",
            }
            self.assertEqual(semantic_recipe, public_recipe)
            self.assertEqual(
                json.loads(marker_path.read_text(encoding="utf-8"))["source_commit"],
                semantic_fixture.runtime_commit,
            )

            failed = self._run_public_pi_collection(
                semantic_fixture,
                plan_ref=plan_ref,
                role="Architect",
                body=body,
                cycle_id=cycle_id,
            )
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
            failed_payload = json.loads(failed.stdout)
            self.assertEqual(failed_payload["reason_code"], "collector_error")
            self.assertIn("postmap_unobservable", failed_payload["error"])
            receipt_path = semantic_fixture.target_root / collector.capture_receipt_rel_path(
                plan_ref, "Architect", cycle_id
            )
            self.assertFalse(receipt_path.exists())
            pi_root = semantic_fixture.target_root / "docs/process_improvements"
            moved_root = pi_root.with_name("process_improvements-before-unobservable")
            outside = semantic_fixture.target_root / "postmap-unobservable-outside"
            self.assertTrue(pi_root.is_symlink())
            self.assertTrue(moved_root.is_dir())
            self.assertEqual(list(outside.iterdir()), [])
            with self.assertRaisesRegex(ValueError, "unsafe engaged process-improvement ancestor"):
                collector._safe_pi_object_map(semantic_fixture.target_root, plan_ref)
            self._assert_public_pi_runtime_preserved(
                semantic_fixture,
                expected_hashes=runtime_hashes,
                source_hashes=source_hashes,
                semantic_collector_hook=True,
            )

    def test_first_source_under_nounset_keeps_module_loading_and_source_state(self) -> None:
        for source_state in ("pinned", "unattested_legacy"):
            with self.subTest(source_state=source_state), AuthorityFixture() as fixture:
                if source_state == "unattested_legacy":
                    self._dirty_runtime(fixture)
                facade = self._facade_path(fixture.runtime_root)
                source_command = "planveyor_source_runtime" if source_state == "pinned" else "source"
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        setopt no_unset
                        {source_command} {facade} || exit $?
                        _planveyor_authority_source_state_internal || exit $?
                        whence -w planveyor_role_run >/dev/null || exit $?
                        print -r -- "FIRST_STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE}}"
                        {source_command} {facade} || exit $?
                        print -r -- "SECOND_STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE}}"
                        """
                    ),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.splitlines(),
                    [f"FIRST_STATE={source_state}", f"SECOND_STATE={source_state}"],
                )
                self.assertNotIn("parameter not set", result.stderr)
                self.assertNotIn("Missing planveyor module", result.stderr)

    def test_clean_first_source_pins_and_same_source_is_idempotent(self) -> None:
        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    print -r -- "FIRST_STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                    if [[ "$(typeset -p _PLANVEYOR_AUTHORITY_SOURCE_STATE)" == *" -x "* ]]; then
                      print -r -- EXPORTED_SOURCE_STATE
                    else
                      print -r -- UNEXPORTED_SOURCE_STATE
                    fi
                    planveyor_help() {{ print -r -- ORIGINAL_HELP_SURVIVED; }}
                    planveyor_source_runtime {facade} || exit $?
                    planveyor_help
                    print -r -- "SECOND_STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                    """
                ),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FIRST_STATE=pinned", result.stdout)
        self.assertIn("SECOND_STATE=pinned", result.stdout)
        self.assertIn("UNEXPORTED_SOURCE_STATE", result.stdout)
        self.assertIn("ORIGINAL_HELP_SURVIVED", result.stdout)
        self.assertNotIn("EXPORTED_SOURCE_STATE", result.stdout.splitlines())

    def test_different_root_and_changed_revision_fail_before_existing_function_overwrite(self) -> None:
        with AuthorityFixture() as fixture, AuthorityFixture() as other:
            first = self._facade_path(fixture.runtime_root)
            second = self._facade_path(other.runtime_root)
            root_result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {first} || exit $?
                    planveyor_help() {{ print -r -- ROOT_OLD_FUNCTION_SURVIVED; }}
                    if planveyor_source_runtime {second}; then
                      print -r -- ROOT_SWITCH_ACCEPTED
                    else
                      print -r -- ROOT_SWITCH_REJECTED
                    fi
                    planveyor_help
                    """
                ),
            )

        self.assertEqual(root_result.returncode, 0, root_result.stderr)
        self.assertIn("ROOT_SWITCH_REJECTED", root_result.stdout)
        self.assertIn("ROOT_OLD_FUNCTION_SURVIVED", root_result.stdout)
        self.assertNotIn("ROOT_SWITCH_ACCEPTED", root_result.stdout)
        self.assertIn("runtime_source_mismatch", root_result.stderr)

        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            runtime = shlex.quote(str(fixture.runtime_root))
            revision_result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    planveyor_help() {{ print -r -- REVISION_OLD_FUNCTION_SURVIVED; }}
                    print -r -- '# disposable source revision' >> {facade}
                    git -C {runtime} add -- scripts/planveyor.zsh || exit $?
                    git -C {runtime} commit --quiet -m disposable-source-revision || exit $?
                    if planveyor_source_runtime {facade}; then
                      print -r -- REVISION_SWITCH_ACCEPTED
                    else
                      print -r -- REVISION_SWITCH_REJECTED
                    fi
                    planveyor_help
                    """
                ),
            )

        self.assertEqual(revision_result.returncode, 0, revision_result.stderr)
        self.assertIn("REVISION_SWITCH_REJECTED", revision_result.stdout)
        self.assertIn("REVISION_OLD_FUNCTION_SURVIVED", revision_result.stdout)
        self.assertNotIn("REVISION_SWITCH_ACCEPTED", revision_result.stdout)
        self.assertIn("runtime_pin_mismatch", revision_result.stderr)

    def test_dirty_or_non_git_initial_source_stays_unattested_after_runtime_becomes_clean(self) -> None:
        with self.subTest(initial_runtime="dirty"):
            with AuthorityFixture() as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                self._dirty_runtime(fixture)
                facade = self._facade_path(fixture.runtime_root)
                runtime = shlex.quote(str(fixture.runtime_root))
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        set -e
                        source {facade} || exit $?
                        print -r -- "STATE_BEFORE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                        git -C {runtime} add -- scripts/plan_lint.py || exit $?
                        git -C {runtime} commit --quiet -m disposable-runtime-promotion || exit $?
                        print -r -- "STATE_AFTER=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                        if _planveyor_pre_dispatch authority_shell_test >/dev/null; then
                          print -r -- UNATTESTED_PROMOTED
                        else
                          print -r -- UNATTESTED_REJECTED
                        fi
                        """
                    ),
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("STATE_BEFORE=unattested_legacy", result.stdout)
            self.assertIn("STATE_AFTER=unattested_legacy", result.stdout)
            self.assertIn("UNATTESTED_REJECTED", result.stdout)
            self.assertNotIn("UNATTESTED_PROMOTED", result.stdout)
            self.assertIn("runtime_pin_unattested", result.stderr)

        with self.subTest(initial_runtime="non_git"):
            with AuthorityFixture() as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
                non_git_runtime = fixture.root / "non-git-runtime"
                shutil.copytree(
                    fixture.runtime_root,
                    non_git_runtime,
                    ignore=shutil.ignore_patterns(".git", "__pycache__"),
                )
                facade = self._facade_path(non_git_runtime)
                runtime = shlex.quote(str(non_git_runtime))
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        set -e
                        source {facade} || exit $?
                        print -r -- "STATE_BEFORE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                        git -C {runtime} init --quiet || exit $?
                        git -C {runtime} add --all || exit $?
                        git -C {runtime} commit --quiet -m disposable-runtime-promotion || exit $?
                        print -r -- "STATE_AFTER=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                        if _planveyor_pre_dispatch authority_shell_test >/dev/null; then
                          print -r -- UNATTESTED_PROMOTED
                        else
                          print -r -- UNATTESTED_REJECTED
                        fi
                        """
                    ),
                    extra_environment={"PLANVEYOR_ROOT": str(non_git_runtime)},
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("STATE_BEFORE=unattested_legacy", result.stdout)
            self.assertIn("STATE_AFTER=unattested_legacy", result.stdout)
            self.assertIn("UNATTESTED_REJECTED", result.stdout)
            self.assertNotIn("UNATTESTED_PROMOTED", result.stdout)
            self.assertIn("runtime_pin_unattested", result.stderr)

    def test_initially_unattested_legacy_shell_remains_usable_and_unpinned_after_clean_commit(self) -> None:
        with AuthorityFixture() as fixture:
            self._dirty_runtime(fixture)
            facade = self._facade_path(fixture.runtime_root)
            runtime = shlex.quote(str(fixture.runtime_root))
            bound_context = self._bound_context(
                "print -r -- \"LEGACY_CONTEXT=$PLANVEYOR_CTX_JSON\"\n"
                "_planveyor_authority_before_effect || return $?\n"
                "print -r -- UNATTESTED_LEGACY_EFFECT_SENTINEL"
            )
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    set -e
                    source {facade} || exit $?
                    print -r -- "STATE_BEFORE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                    git -C {runtime} add -- scripts/plan_lint.py || exit $?
                    git -C {runtime} commit --quiet -m disposable-legacy-runtime-cleanup || exit $?
                    print -r -- "STATE_AFTER=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                    {bound_context}
                    """
                ),
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATE_BEFORE=unattested_legacy", result.stdout)
        self.assertIn("STATE_AFTER=unattested_legacy", result.stdout)
        self.assertIn("UNATTESTED_LEGACY_EFFECT_SENTINEL", result.stdout)
        context_line = next(line for line in result.stdout.splitlines() if line.startswith("LEGACY_CONTEXT="))
        context = json.loads(context_line.removeprefix("LEGACY_CONTEXT="))
        self.assertEqual(context["state"], "legacy")
        self.assertIsNone(context["runtime_pin"])
        self.assertNotIn("runtime_pin_unattested", result.stderr)

    def test_api_guard_rejects_unsupported_api_for_pinned_and_unattested_sources(self) -> None:
        for state in ("pinned", "unattested_legacy"):
            with self.subTest(source_state=state), AuthorityFixture() as fixture:
                if state == "unattested_legacy":
                    self._dirty_runtime(fixture)
                facade = self._facade_path(fixture.runtime_root)
                source_command = "planveyor_source_runtime" if state == "pinned" else "source"
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        {source_command} {facade} || exit $?
                        print -r -- "SOURCE_STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}"
                        if _planveyor_runtime_api_guard 999; then
                          print -r -- API_GUARD_ACCEPTED
                        else
                          print -r -- API_GUARD_REJECTED
                        fi
                        """
                    ),
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"SOURCE_STATE={state}", result.stdout)
            self.assertIn("API_GUARD_REJECTED", result.stdout)
            self.assertNotIn("API_GUARD_ACCEPTED", result.stdout)
            if state == "pinned":
                self.assertIn("runtime_api_incompatible", result.stderr)
            else:
                self.assertIn("loaded runtime API is outside the requested range", result.stderr)

    def test_api_one_range_rejects_pinned_and_unattested_sources(self) -> None:
        for state in ("pinned", "unattested_legacy"):
            with self.subTest(source_state=state), AuthorityFixture() as fixture:
                if state == "unattested_legacy":
                    self._dirty_runtime(fixture)
                facade = self._facade_path(fixture.runtime_root)
                source_command = "planveyor_source_runtime" if state == "pinned" else "source"
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        {source_command} {facade} || exit $?
                        if _planveyor_runtime_api_guard 1 1; then
                          print -r -- API_ONE_RANGE_ACCEPTED
                        else
                          print -r -- API_ONE_RANGE_REJECTED
                        fi
                        """
                    ),
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("API_ONE_RANGE_REJECTED", result.stdout)
            self.assertNotIn("API_ONE_RANGE_ACCEPTED", result.stdout)
            if state == "pinned":
                self.assertIn("runtime_api_incompatible", result.stderr)
            else:
                self.assertIn("loaded runtime API is outside the requested range", result.stderr)

    def test_fake_and_exported_readonly_source_assertions_are_rejected(self) -> None:
        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            runtime = shlex.quote(str(fixture.runtime_root))
            cached_python = shlex.quote(str(Path(sys.executable).resolve()))
            # The fake pin summary is rejected before descriptor validation.
            cases = {
                "fake_readonly": textwrap.dedent(
                    f"""\
                    typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_STATE=pinned
                    typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_PATH={facade}
                    typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR='{{}}'
                    typeset -gr _PLANVEYOR_AUTHORITY_RUNTIME_ROOT={runtime}
                    typeset -gr _PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY='{{}}'
                    typeset -gr _PLANVEYOR_AUTHORITY_PYTHON_BIN={cached_python}
                    """
                ),
                "exported_readonly": textwrap.dedent(
                    f"""\
                    typeset -xgr _PLANVEYOR_AUTHORITY_SOURCE_STATE=pinned
                    typeset -xgr _PLANVEYOR_AUTHORITY_SOURCE_PATH={facade}
                    typeset -xgr _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR='{{}}'
                    typeset -xgr _PLANVEYOR_AUTHORITY_RUNTIME_ROOT={runtime}
                    typeset -xgr _PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY='{{}}'
                    typeset -xgr _PLANVEYOR_AUTHORITY_PYTHON_BIN={cached_python}
                    """
                ),
            }
            results: dict[str, subprocess.CompletedProcess[str]] = {}
            for name, preseed in cases.items():
                results[name] = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_help() {{ print -r -- {name}_OLD_FUNCTION_SURVIVED; }}
                        {preseed}
                        if planveyor_source_runtime {facade}; then
                          print -r -- {name}_ASSERTION_ACCEPTED
                        else
                          print -r -- {name}_ASSERTION_REJECTED
                        fi
                        planveyor_help
                        """
                    ),
                )

        for name, result in results.items():
            with self.subTest(assertion=name):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{name}_ASSERTION_REJECTED", result.stdout)
                self.assertIn(f"{name}_OLD_FUNCTION_SURVIVED", result.stdout)
                self.assertNotIn(f"{name}_ASSERTION_ACCEPTED", result.stdout)

        self.assertIn("runtime_pin_summary_invalid", results["fake_readonly"].stderr)
        self.assertIn("exported or mutable loaded source state", results["exported_readonly"].stderr)

    def test_source_state_requires_exact_global_readonly_scalar_variables(self) -> None:
        """Only bootstrap-owned global readonly scalars may describe a source."""

        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            positive = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_SOURCE_STATE}}" == scalar-readonly ]] || exit 81
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_SOURCE_PATH}}" == scalar-readonly ]] || exit 82
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR}}" == scalar-readonly ]] || exit 83
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_RUNTIME_ROOT}}" == scalar-readonly ]] || exit 84
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY}}" == scalar-readonly ]] || exit 85
                    [[ "${{(t)_PLANVEYOR_AUTHORITY_PYTHON_BIN}}" == scalar-readonly ]] || exit 86
                    _planveyor_authority_source_state_internal || exit 87
                    print -r -- SOURCE_GLOBAL_SCALAR_READONLY_ACCEPTED
                    """
                ),
            )

            cases = {
                "local_readonly": (
                    "local -r _PLANVEYOR_AUTHORITY_SOURCE_STATE=pinned",
                    "exported or mutable loaded source state is rejected",
                ),
                "mutable": (
                    'local _PLANVEYOR_AUTHORITY_SOURCE_PATH="$source_path"',
                    "loaded source state is incomplete",
                ),
                "exported": (
                    'local -xr _PLANVEYOR_AUTHORITY_PYTHON_BIN="$python_bin"',
                    "loaded interpreter state is invalid",
                ),
                "array": (
                    'local -ar _PLANVEYOR_AUTHORITY_RUNTIME_ROOT=("$runtime_root")',
                    "loaded source state is incomplete",
                ),
                "assoc": (
                    'local -Ar _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR=(value "$descriptor")',
                    "loaded source state is incomplete",
                ),
                "lowercase": (
                    "local -lr _PLANVEYOR_AUTHORITY_SOURCE_STATE=pinned",
                    "exported or mutable loaded source state is rejected",
                ),
                "unique": (
                    'local -aUr _PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY=("$pin_summary")',
                    "loaded runtime pin state is invalid",
                ),
                # The old textual declaration check accepted this mutable
                # scalar because its value merely contained the token -r.
                "forged_readonly_token": (
                    'local _PLANVEYOR_AUTHORITY_SOURCE_PATH="forged -r readonly-looking payload"',
                    "loaded source state is incomplete",
                ),
            }
            results: dict[str, subprocess.CompletedProcess[str]] = {}
            for name, (declaration, expected_error) in cases.items():
                results[name] = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_source_runtime {facade} || exit $?
                        planveyor_help() {{ print -r -- SOURCE_ORIGINAL_FUNCTION_SURVIVED; }}
                        source_attribute_case() {{
                          emulate -L zsh
                          local source_path="$_PLANVEYOR_AUTHORITY_SOURCE_PATH"
                          local descriptor="$_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR"
                          local runtime_root="$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT"
                          local python_bin="$_PLANVEYOR_AUTHORITY_PYTHON_BIN"
                          local pin_summary="$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY"
                          {declaration}
                          if planveyor_source_runtime {facade}; then
                            print -r -- SOURCE_RESOURCE_ACCEPTED
                          else
                            print -r -- SOURCE_RESOURCE_REJECTED
                          fi
                          planveyor_help
                          if _planveyor_authority_source_state_internal; then
                            print -r -- SOURCE_ATTRIBUTE_ACCEPTED
                          else
                            print -r -- SOURCE_ATTRIBUTE_REJECTED
                          fi
                          if _planveyor_authority_runtime_root_loaded >/dev/null; then
                            print -r -- SOURCE_FALLBACK_ACCEPTED
                          else
                            print -r -- SOURCE_FALLBACK_REJECTED
                          fi
                        }}
                        source_attribute_case
                        """
                    ),
                )
                self.assertIn(expected_error, results[name].stderr)

        self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
        self.assertIn("SOURCE_GLOBAL_SCALAR_READONLY_ACCEPTED", positive.stdout)
        for name, result in results.items():
            with self.subTest(source_declaration=name):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("SOURCE_RESOURCE_REJECTED", result.stdout)
                self.assertIn("SOURCE_ORIGINAL_FUNCTION_SURVIVED", result.stdout)
                self.assertIn("SOURCE_ATTRIBUTE_REJECTED", result.stdout)
                self.assertIn("SOURCE_FALLBACK_REJECTED", result.stdout)
                self.assertNotIn("SOURCE_RESOURCE_ACCEPTED", result.stdout)
                self.assertNotIn("SOURCE_ATTRIBUTE_ACCEPTED", result.stdout)
                self.assertNotIn("SOURCE_FALLBACK_ACCEPTED", result.stdout)

    def test_parent_context_requires_exact_caller_local_readonly_scalars(self) -> None:
        """A visible context tuple may be used only from its caller's locals."""

        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            seal_declarations = {
                "valid_local_readonly": 'local -r PLANVEYOR_CTX_SEAL="$seal"',
                "global_readonly": 'typeset -gr PLANVEYOR_CTX_SEAL="$seal"',
                "mutable": 'local PLANVEYOR_CTX_SEAL="$seal"',
                "exported": 'local -xr PLANVEYOR_CTX_SEAL="$seal"',
                "array": 'local -ar PLANVEYOR_CTX_SEAL=("$seal")',
                "assoc": 'local -Ar PLANVEYOR_CTX_SEAL=(value "$seal")',
                "lowercase": 'local -lr PLANVEYOR_CTX_SEAL="$seal"',
                "unique": 'local -aUr PLANVEYOR_CTX_SEAL=("$seal")',
            }
            results: dict[str, subprocess.CompletedProcess[str]] = {}
            for name, seal_declaration in seal_declarations.items():
                results[name] = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_source_runtime {facade} || exit $?
                        context_json="$(_planveyor_pre_dispatch native-attribute-context)" || exit $?
                        context_tuple="$(_planveyor_authority_context_bindings "$context_json")" || exit $?
                        IFS=$'\t' read -r state root generation remainder <<< "$context_tuple" || exit 88
                        [[ -z "${{remainder:-}}" ]] || exit 89
                        parent_attribute_case() {{
                          emulate -L zsh
                          local -r seal='planveyor-contract-context.v1'
                          local -r PLANVEYOR_CTX_ROOT="$root"
                          local -r PLANVEYOR_CTX_GENERATION="$generation"
                          local -r PLANVEYOR_CTX_JSON="$context_json"
                          local -r PLANVEYOR_CTX_STATE="$state"
                          {seal_declaration}
                          if _planveyor_authority_parent_context_json >/dev/null; then
                            print -r -- PARENT_ATTRIBUTE_ACCEPTED
                          else
                            print -r -- PARENT_ATTRIBUTE_REJECTED
                          fi
                          if _planveyor_pre_dispatch native-attribute-context >/dev/null; then
                            print -r -- PARENT_CONTEXT_FALLBACK_ACCEPTED
                          else
                            print -r -- PARENT_CONTEXT_FALLBACK_REJECTED
                          fi
                        }}
                        parent_attribute_case
                        """
                    ),
                )

        valid = results.pop("valid_local_readonly")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertIn("PARENT_ATTRIBUTE_ACCEPTED", valid.stdout)
        self.assertIn("PARENT_CONTEXT_FALLBACK_ACCEPTED", valid.stdout)
        self.assertNotIn("PARENT_ATTRIBUTE_REJECTED", valid.stdout)
        self.assertNotIn("PARENT_CONTEXT_FALLBACK_REJECTED", valid.stdout)
        for name, result in results.items():
            with self.subTest(context_declaration=name):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PARENT_ATTRIBUTE_REJECTED", result.stdout)
                self.assertIn("PARENT_CONTEXT_FALLBACK_REJECTED", result.stdout)
                self.assertNotIn("PARENT_ATTRIBUTE_ACCEPTED", result.stdout)
                self.assertNotIn("PARENT_CONTEXT_FALLBACK_ACCEPTED", result.stdout)

    def test_runtime_closure_and_runner_policy_drift_fail_before_effect_sentinel(self) -> None:
        drift_paths = (
            "scripts/plan_lint.py",
            "docs/_meta/runner_selection_resolution.v1.json",
        )
        for relative_path in drift_paths:
            with self.subTest(drift_path=relative_path), AuthorityFixture() as fixture:
                facade = self._facade_path(fixture.runtime_root)
                drift_path = shlex.quote(str(fixture.runtime_root / relative_path))
                bound_context = self._bound_context(
                    f"print -r -- '# disposable post-capture drift' >> {drift_path}\n"
                    "print -r -- DRIFT_APPLIED\n"
                    "_planveyor_authority_before_effect || return $?\n"
                    "print -r -- EFFECT_SENTINEL"
                )
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_source_runtime {facade} || exit $?
                        {bound_context}
                        """
                    ),
                )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("EFFECT_SENTINEL", result.stdout)
            self.assertIn("DRIFT_APPLIED", result.stdout)
            self.assertIn("runtime_pin_unattested", result.stderr)

    def test_target_mutation_after_declared_read_reaches_effect_with_current_content(self) -> None:
        """An allowed target body may evolve after capture and before an effect."""

        with AuthorityFixture() as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            facade = self._facade_path(fixture.runtime_root)
            target_template = shlex.quote(str(fixture.target_root / "docs" / "plans" / "_template.md"))
            bound_context = self._bound_context(
                "template=$(_planveyor_contract_read docs/plans/_template.md post-read-target) || return $?\n"
                "[[ -n \"$template\" ]] || return 81\n"
                "print -r -- TARGET_READ_COMPLETE\n"
                f"print -r -- '# disposable mutation after declared read' >> {target_template}\n"
                "current_template=$(_planveyor_contract_read docs/plans/_template.md post-mutation-target) || return $?\n"
                "[[ \"$current_template\" == *'# disposable mutation after declared read'* ]] || return 82\n"
                "print -r -- TARGET_CURRENT_READ_COMPLETE\n"
                "_planveyor_authority_before_effect || return $?\n"
                "print -r -- TARGET_POST_READ_EFFECT_SENTINEL"
            )
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    {bound_context}
                    """
                ),
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TARGET_READ_COMPLETE", result.stdout)
        self.assertIn("TARGET_CURRENT_READ_COMPLETE", result.stdout)
        self.assertIn("TARGET_POST_READ_EFFECT_SENTINEL", result.stdout)

    def test_engaged_context_rejects_an_unexported_foreign_runtime_root_before_effect(self) -> None:
        """The shell enforces its loaded runtime even when children cannot see it."""

        with AuthorityFixture() as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            foreign_root = fixture.root / "foreign-existing-runtime"
            foreign_root.mkdir()
            facade = self._facade_path(fixture.runtime_root)
            quoted_foreign_root = shlex.quote(str(foreign_root))
            bound_context = self._bound_context(
                "typeset +x PLANVEYOR_ROOT\n"
                f"typeset -g PLANVEYOR_ROOT={quoted_foreign_root}\n"
                "_planveyor_authority_before_effect || return $?\n"
                "print -r -- FOREIGN_RUNTIME_EFFECT_SENTINEL"
            )
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    {bound_context}
                    """
                ),
            )

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FOREIGN_RUNTIME_EFFECT_SENTINEL", result.stdout)
        self.assertIn("PLANVEYOR_ROOT differs from the loaded runtime", result.stderr)

    def test_stale_timestamp_valid_context_bytecode_cannot_change_shell_effect_context(self) -> None:
        with AuthorityFixture() as fixture:
            cache = self._install_timestamp_valid_stale_context_cache(fixture)
            bridge = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
            direct = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(bridge),
                    "context",
                    "--runtime-root",
                    str(fixture.runtime_root),
                ],
                cwd=fixture.target_root,
                env=self._shell_environment(fixture),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            facade = self._facade_path(fixture.runtime_root)
            bound_context = self._bound_context(
                "schema=$(_planveyor_authority_context_field \"$PLANVEYOR_CTX_JSON\" schema_version) || return $?\n"
                "[[ \"$schema\" == \"planveyor_contract_context.v3\" ]] || { print -r -- \"STALE_PYC_SCHEMA=$schema\"; return 89; }\n"
                "_planveyor_authority_before_effect || return $?\n"
                "print -r -- STALE_PYC_V3_EFFECT_SENTINEL"
            )
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    {bound_context}
                    """
                ),
            )
            cache_exists = cache.is_file()

        self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        direct_payload = json.loads(direct.stdout)
        self.assertEqual(direct_payload["schema_version"], "planveyor_contract_context.v3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(cache_exists)
        self.assertIn("STALE_PYC_V3_EFFECT_SENTINEL", result.stdout)
        self.assertNotIn("STALE_PYC_SCHEMA=planveyor_contract_context.x1", result.stdout)

    def test_stale_timestamp_valid_context_bytecode_cannot_change_direct_plan_lint_import(self) -> None:
        with AuthorityFixture() as fixture:
            cache = self._install_timestamp_valid_stale_context_cache(fixture)
            entrypoint = fixture.runtime_root / "scripts" / "plan_lint.py"
            harness = textwrap.dedent(
                """\
                import importlib.util
                from pathlib import Path
                import sys

                entrypoint = Path(sys.argv[1])
                spec = importlib.util.spec_from_file_location("fresh_plan_lint", entrypoint)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                print(module._authority.CONTEXT_SCHEMA_VERSION)
                """
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    "pycache_prefix=/dev/null",
                    "-c",
                    harness,
                    str(entrypoint),
                ],
                cwd=fixture.target_root,
                env=self._shell_environment(fixture),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            cache_exists = cache.is_file()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(cache_exists)
        self.assertEqual(result.stdout, "planveyor_contract_context.v3\n")

    def test_direct_authority_consumers_install_bytecode_policy_before_runtime_imports(self) -> None:
        """Keep the fixed direct-script boundary exhaustive without a registry."""

        self.assertEqual(len(_DIRECT_AUTHORITY_CONSUMERS), 16)
        self.assertEqual(len(set(_DIRECT_AUTHORITY_CONSUMERS)), len(_DIRECT_AUTHORITY_CONSUMERS))
        for relative_path in (*_DIRECT_AUTHORITY_CONSUMERS, "scripts/contract_authority_bridge.py"):
            with self.subTest(entrypoint=relative_path):
                source = (SCRIPT_DIR.parent / relative_path).read_text(encoding="utf-8")
                no_write = source.index("sys.dont_write_bytecode = True")
                cache_prefix = source.index("sys.pycache_prefix = os.devnull")
                self.assertLess(source.index("import os"), no_write)
                self.assertLess(source.index("import sys"), no_write)
                self.assertLess(no_write, cache_prefix)
                runtime_load_boundaries = tuple(
                    source.index(marker)
                    for marker in (
                        "sys.path.insert(",
                        "importlib.import_module(",
                        "importlib.util.spec_from_file_location(",
                    )
                    if marker in source
                )
                self.assertTrue(runtime_load_boundaries)
                self.assertLess(cache_prefix, min(runtime_load_boundaries))

    def test_cached_interpreter_reuses_absolute_binary_after_path_change(self) -> None:
        with AuthorityFixture() as fixture:
            interpreter, log = self._logging_interpreter(fixture)
            git_binary = shutil.which("git")
            self.assertIsNotNone(git_binary)
            git_only = fixture.root / "git-only"
            write(
                fixture.root,
                "git-only/git",
                "#!/bin/sh\n" + f"exec {shlex.quote(str(git_binary))} \"$@\"\n",
                executable=True,
            )
            facade = self._facade_path(fixture.runtime_root)
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    print -r -- "CACHED_INTERPRETER=${{_PLANVEYOR_AUTHORITY_PYTHON_BIN:-}}"
                    if [[ "$(typeset -p _PLANVEYOR_AUTHORITY_PYTHON_BIN)" == typeset\\ -r\\ * ]]; then
                      print -r -- CACHED_INTERPRETER_READONLY
                    fi
                    PATH={shlex.quote(str(git_only))}
                    if _planveyor_runtime_api_guard 5; then
                      print -r -- CACHED_INTERPRETER_GUARD_OK
                    else
                      print -r -- CACHED_INTERPRETER_GUARD_FAILED
                    fi
                    """
                ),
                extra_environment={
                    "PATH": os.pathsep.join((str(interpreter.parent), os.environ.get("PATH", ""))),
                    "AUTHORITY_TEST_INTERPRETER_LOG": str(log),
                },
            )
            wrapper_log = log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"CACHED_INTERPRETER={interpreter}", result.stdout)
        self.assertIn("CACHED_INTERPRETER_READONLY", result.stdout)
        self.assertIn("CACHED_INTERPRETER_GUARD_OK", result.stdout)
        self.assertNotIn("CACHED_INTERPRETER_GUARD_FAILED", result.stdout)
        version_probe = "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)"
        self.assertEqual(wrapper_log.count(version_probe), 1)
        self.assertNotIn("runtime-api-version", wrapper_log)
        self.assertIn("runtime-api", wrapper_log)
        bridge_calls = tuple(
            line
            for line in wrapper_log.splitlines()
            if "/scripts/contract_authority_bridge.py " in line
        )
        self.assertEqual(len(bridge_calls), 8)
        bridge_prefix = f"-I -B -c <caller-literal> {fixture.runtime_root}/scripts/contract_authority_bridge.py "
        self.assertTrue(all(line.startswith(bridge_prefix) for line in bridge_calls))
        self.assertTrue(all("pycache_prefix" not in line for line in bridge_calls))
        for command in (
            "shell-source",
            "source-buffer",
            "source-verify",
            "runtime-verify",
            "runtime-api",
        ):
            self.assertTrue(any(f" {command}" in line for line in bridge_calls), command)

    def test_preseeded_or_missing_interpreter_cache_rejects_before_bridge(self) -> None:
        with AuthorityFixture() as fixture:
            facade = self._facade_path(fixture.runtime_root)
            actual_python = shlex.quote(str(Path(sys.executable).resolve()))
            preseeds = {
                "readonly": f"typeset -gr _PLANVEYOR_AUTHORITY_PYTHON_BIN={actual_python}",
                "mutable": f"typeset -g _PLANVEYOR_AUTHORITY_PYTHON_BIN={actual_python}",
                "exported": f"typeset -xgr _PLANVEYOR_AUTHORITY_PYTHON_BIN={actual_python}",
            }
            preseed_results: dict[str, subprocess.CompletedProcess[str]] = {}
            for name, declaration in preseeds.items():
                preseed_results[name] = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_help() {{ print -r -- {name}_PRESEED_OLD_FUNCTION_SURVIVED; }}
                        {declaration}
                        if planveyor_source_runtime {facade}; then
                          print -r -- {name}_PRESEED_ACCEPTED
                        else
                          print -r -- {name}_PRESEED_REJECTED
                        fi
                        planveyor_help
                        """
                    ),
                )

        for name, result in preseed_results.items():
            with self.subTest(preseed=name):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{name}_PRESEED_REJECTED", result.stdout)
                self.assertIn(f"{name}_PRESEED_OLD_FUNCTION_SURVIVED", result.stdout)
                self.assertNotIn(f"{name}_PRESEED_ACCEPTED", result.stdout)
                self.assertIn("preseeded interpreter state is rejected", result.stderr)

        with AuthorityFixture() as fixture:
            interpreter, log = self._logging_interpreter(fixture)
            facade = self._facade_path(fixture.runtime_root)
            missing_interpreter = shlex.quote(str(interpreter.with_name("python3.missing")))
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    planveyor_help() {{ print -r -- MISSING_CACHE_OLD_FUNCTION_SURVIVED; }}
                    mv {shlex.quote(str(interpreter))} {missing_interpreter} || exit $?
                    if planveyor_source_runtime {facade}; then
                      print -r -- MISSING_CACHE_ACCEPTED
                    else
                      print -r -- MISSING_CACHE_REJECTED
                    fi
                    planveyor_help
                    """
                ),
                extra_environment={
                    "PATH": os.pathsep.join((str(interpreter.parent), os.environ.get("PATH", ""))),
                    "AUTHORITY_TEST_INTERPRETER_LOG": str(log),
                },
            )
            initial_wrapper_log = log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MISSING_CACHE_REJECTED", result.stdout)
        self.assertIn("MISSING_CACHE_OLD_FUNCTION_SURVIVED", result.stdout)
        self.assertNotIn("MISSING_CACHE_ACCEPTED", result.stdout)
        self.assertIn("loaded interpreter state is invalid", result.stderr)
        self.assertIn("shell-source", initial_wrapper_log)

    def test_context_capture_uses_one_bootstrap_runtime_verify(self) -> None:
        """The bridge's context command owns the post-load pin check once."""

        with AuthorityFixture() as fixture:
            interpreter, log = self._logging_interpreter(fixture)
            facade = self._facade_path(fixture.runtime_root)
            result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    context="$(_planveyor_pre_dispatch authority_context_capture_count)" || exit $?
                    [[ -n "${{context//[[:space:]]/}}" ]] || exit 90
                    print -r -- CONTEXT_CAPTURED
                    """
                ),
                extra_environment={
                    "PATH": os.pathsep.join((str(interpreter.parent), os.environ.get("PATH", ""))),
                    "AUTHORITY_TEST_INTERPRETER_LOG": str(log),
                },
            )
            bridge_calls = tuple(
                line
                for line in log.read_text(encoding="utf-8").splitlines()
                if "/scripts/contract_authority_bridge.py " in line
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONTEXT_CAPTURED", result.stdout)
        self.assertEqual(sum(" runtime-verify" in line for line in bridge_calls), 1)
        self.assertEqual(sum(" context --runtime-pin-summary" in line for line in bridge_calls), 1)

    def test_engaged_prompt_and_template_read_current_target_content(self) -> None:
        target_template = "TARGET_ONLY:docs/plans/_template.md\n"
        with AuthorityFixture() as fixture:
            self._enable_isolated_admission(fixture)
            fixture.activate_planveyor(
                source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
                overrides={"docs/plans/_template.md": target_template},
            )
            facade = self._facade_path(fixture.runtime_root)
            bound_context = self._bound_context(
                "prompt=$(_planveyor_contract_read docs/tools/prompts/coder_init.md target-prompt) || return $?\n"
                "template=$(_planveyor_contract_read docs/plans/_template.md target-template) || return $?\n"
                "[[ \"$prompt\" == *\"TARGET_ONLY:docs/tools/prompts/coder_init.md\"* ]] || return 71\n"
                "[[ \"$template\" == \"TARGET_ONLY:docs/plans/_template.md\" ]] || return 72\n"
                "print -r -- TARGET_SOURCE_SENTINEL"
            )
            target_result = self._run_zsh(
                fixture,
                textwrap.dedent(
                    f"""\
                    planveyor_source_runtime {facade} || exit $?
                    {bound_context}
                    """
                ),
            )

        self.assertEqual(target_result.returncode, 0, target_result.stderr)
        self.assertIn("TARGET_SOURCE_SENTINEL", target_result.stdout)

        current_cases = (
            (
                "changed_prompt",
                "docs/tools/prompts/coder_init.md",
                "CURRENT_TARGET_PROMPT\n",
                "docs/tools/prompts/coder_init.md",
            ),
            (
                "changed_template",
                "docs/plans/_template.md",
                "CURRENT_TARGET_TEMPLATE\n",
                "docs/plans/_template.md",
            ),
        )
        for name, relative_path, replacement, read_path in current_cases:
            with self.subTest(source_state=name), AuthorityFixture() as fixture:
                self._enable_isolated_admission(fixture)
                fixture.activate_planveyor(
                    source_context.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
                    overrides={"docs/plans/_template.md": target_template},
                )
                target_path = fixture.target_root / relative_path
                target_path.write_text(replacement, encoding="utf-8")
                facade = self._facade_path(fixture.runtime_root)
                # Command substitution removes the selected body's trailing
                # newline, while the reader itself preserves the target bytes.
                expected = shlex.quote(replacement.rstrip("\n"))
                sentinel = f"CURRENT_{name.upper()}_SOURCE_SENTINEL"
                action = (
                    f"body=$(_planveyor_contract_read {read_path} current-{name}) || return $?\n"
                    f'[[ "$body" == {expected} ]] || return 73\n'
                    "_planveyor_authority_before_effect || return $?\n"
                    f"print -r -- {sentinel}"
                )
                result = self._run_zsh(
                    fixture,
                    textwrap.dedent(
                        f"""\
                        planveyor_source_runtime {facade} || exit $?
                        {self._bound_context(action)}
                        """
                    ),
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(sentinel, result.stdout)

    def test_bridge_ignores_target_modules_and_rejects_preloaded_foreign_authority_aliases(self) -> None:
        target_init_exists = False
        target_authority_exists = False
        with AuthorityFixture() as fixture:
            target_init = write(
                fixture.target_root,
                "scripts/__init__.py",
                "raise SystemExit('TARGET_SCRIPTS_INIT_IMPORTED')\n",
            )
            target_authority = write(
                fixture.target_root,
                "scripts/contract_authority_context.py",
                "raise SystemExit('TARGET_AUTHORITY_MODULE_IMPORTED')\n",
            )
            foreign_root = fixture.root / "foreign-parent"
            write(foreign_root, "scripts/__init__.py", "ORIGIN = 'foreign-parent'\n")
            foreign_authority = write(foreign_root, "foreign_authority.py", "# foreign alias\n")
            bridge = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
            generic_parent_program = textwrap.dedent(
                """\
                import json
                from pathlib import Path
                import runpy
                import sys

                foreign_root = Path(sys.argv[1])
                bridge = sys.argv[2]
                runtime_root = sys.argv[3]
                sys.path.insert(0, str(foreign_root))
                import scripts
                assert Path(scripts.__file__).resolve() == foreign_root / 'scripts' / '__init__.py'
                sys.argv = [bridge, 'context', '--runtime-root', runtime_root]
                runpy.run_path(bridge, run_name='__main__')
                """
            )
            generic_parent = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    "pycache_prefix=/dev/null",
                    "-c",
                    generic_parent_program,
                    str(foreign_root),
                    str(bridge),
                    str(fixture.runtime_root),
                ],
                cwd=fixture.target_root,
                env=self._shell_environment(fixture),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            alias_program = textwrap.dedent(
                """\
                from pathlib import Path
                import runpy
                import sys
                import types

                bridge = sys.argv[1]
                foreign_authority = sys.argv[2]
                alias = types.ModuleType('contract_authority_context')
                alias.__file__ = foreign_authority
                sys.modules['contract_authority_context'] = alias
                sys.argv = [bridge, 'runtime-api-version']
                runpy.run_path(bridge, run_name='__main__')
                """
            )
            foreign_alias = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    "pycache_prefix=/dev/null",
                    "-c",
                    alias_program,
                    str(bridge),
                    str(foreign_authority),
                ],
                cwd=fixture.target_root,
                env=self._shell_environment(fixture),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            target_init_exists = target_init.is_file()
            target_authority_exists = target_authority.is_file()

        self.assertEqual(generic_parent.returncode, 0, generic_parent.stderr)
        payload = json.loads(generic_parent.stdout)
        self.assertEqual(payload["state"], "legacy")
        self.assertNotIn("TARGET_SCRIPTS_INIT_IMPORTED", generic_parent.stdout + generic_parent.stderr)
        self.assertNotIn("TARGET_AUTHORITY_MODULE_IMPORTED", generic_parent.stdout + generic_parent.stderr)
        self.assertTrue(target_init_exists)
        self.assertTrue(target_authority_exists)
        self.assertEqual(foreign_alias.returncode, 2)
        self.assertIn("authority_module_origin_mismatch", foreign_alias.stderr)


if __name__ == "__main__":
    unittest.main()

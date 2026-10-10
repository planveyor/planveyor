#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import plan_status_oracle as PLAN_STATUS_ORACLE

PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
FAKE_SID = "00000000-0000-4000-8000-000000000001"

# The facade observes and pins its actual sibling runtime before the router
# functions run.  Router fixtures therefore need a real, committed runtime
# root, rather than a copied facade that falls through to this test checkout.
# Keep test modules and test data out of that closure: only the source-time
# facade closure, its direct Manager helpers, and the docs consumed by these
# router paths are admitted.  A broad script copy makes every guarded reader
# rehash unrelated tools and can turn the queue subcases into timeouts.
FIXTURE_RUNTIME_SCRIPTS = (
    "scripts/planveyor.zsh",
    "scripts/planveyor/contract_authority.zsh",
    "scripts/planveyor/session_init.zsh",
    "scripts/planveyor/role_runtime.zsh",
    "scripts/planveyor/docs_finalize.zsh",
    "scripts/planveyor/home_runtime.zsh",
    "scripts/contract_authority_bootstrap.py",
    "scripts/contract_authority_shell_loader.zsh",
    "scripts/contract_authority_children.py",
    "scripts/contract_authority_bridge.py",
    "scripts/contract_authority_context.py",
    "scripts/contract_authority_runtime.py",
    "scripts/contract_authority_snapshot.py",
    "scripts/fs_object_identity.py",
    "scripts/codex_session_stats.py",
    "scripts/custom_pipeline_dirty_state.py",
    "scripts/plan_lint.py",
    "scripts/plan_queue.py",
    "scripts/plan_status_oracle.py",
    "scripts/retrieval_telemetry_receipt.py",
    "scripts/review_artifact_lint.py",
    "scripts/review_header_metadata.py",
    "scripts/review_schema_contract.py",
    "scripts/review_target_snapshot.py",
    "scripts/review_visual_lane_contract.py",
)
FIXTURE_RUNTIME_DOCUMENT_TREES = (
    "docs/tools/prompts",
)
FIXTURE_RUNTIME_DOCUMENTS = (
    "docs/_meta/plan_vocab.json",
    "docs/_meta/runner_selection_resolution.v1.json",
    "docs/roles/manager.md",
    "docs/playbooks/docs_architecture.md",
)


class RouterMergeBoundaryTests(unittest.TestCase):
    def test_codex_exec_surfaces_have_classified_current_contract(self) -> None:
        expected_never_by_path = {
            REPO_ROOT / "scripts" / "planveyor.zsh": 4,
            REPO_ROOT / "scripts" / "planveyor" / "session_init.zsh": 5,
            REPO_ROOT / "scripts" / "planveyor" / "role_runtime.zsh": 10,
            REPO_ROOT / "scripts" / "planveyor" / "docs_finalize.zsh": 9,
        }
        never_contract = re.compile(
            r"_planveyor_codex\s+exec\s+-c\s+'approval_policy=\"never\"'\s+"
            r"--sandbox\s+workspace-write(?=\s|$)"
        )
        on_request_contract = re.compile(
            r"_planveyor_codex\s+exec\s+-c\s+'approval_policy=\"on-request\"'\s+"
            r"-c\s+'sandbox_mode=\"workspace-write\"'(?=\s|$)"
        )
        wrapper_exec = re.compile(r"(?<![A-Za-z0-9_])_planveyor_codex\s+exec\b")
        direct_exec = re.compile(
            r"(?<![A-Za-z0-9_])(?:command\s+)?codex\s+exec\b"
        )

        def normalize_quoted_command_word(line: str) -> str:
            for token in ("_planveyor_codex", "codex"):
                line = re.sub(
                    rf"(?<![A-Za-z0-9_])([\"']){re.escape(token)}\1(?=\s+exec\b)",
                    token,
                    line,
                )
            return line

        def strip_comment(line: str) -> str:
            quote = ""
            escaped = False
            for index, char in enumerate(line):
                if escaped:
                    escaped = False
                    continue
                if char == "\\" and quote != "'":
                    escaped = True
                    continue
                if quote:
                    if char == quote:
                        quote = ""
                    continue
                if char in ("'", '"'):
                    quote = char
                    continue
                if char == "#" and (
                    index == 0
                    or line[index - 1].isspace()
                    or line[index - 1] in ";&|()<>"):
                    return line[:index]
            return line

        def logical_commands(runtime: str) -> list[str]:
            commands: list[str] = []
            pending = ""
            heredoc_end = ""
            heredoc_strip_tabs = False

            def heredoc_marker(command: str) -> tuple[str, bool] | None:
                quote = ""
                escaped = False
                arithmetic_depth = 0
                index = 0
                while index < len(command):
                    char = command[index]
                    if escaped:
                        escaped = False
                        index += 1
                        continue
                    if char == "\\" and quote != "'":
                        escaped = True
                        index += 1
                        continue
                    if quote:
                        if char == quote:
                            quote = ""
                        index += 1
                        continue
                    if char in ("'", '"'):
                        quote = char
                        index += 1
                        continue
                    if command.startswith("$((", index):
                        arithmetic_depth += 1
                        index += 3
                        continue
                    if command.startswith("((", index):
                        arithmetic_depth += 1
                        index += 2
                        continue
                    if arithmetic_depth:
                        if command.startswith("))", index):
                            arithmetic_depth -= 1
                            index += 2
                        else:
                            index += 1
                        continue
                    if command.startswith("<<<", index):
                        index += 3
                        continue
                    if not command.startswith("<<", index):
                        index += 1
                        continue

                    cursor = index + 2
                    strip_tabs = cursor < len(command) and command[cursor] == "-"
                    if strip_tabs:
                        cursor += 1
                    while cursor < len(command) and command[cursor] in " \t":
                        cursor += 1
                    if cursor >= len(command):
                        return None

                    delimiter_quote = command[cursor] if command[cursor] in ("'", '"') else ""
                    if delimiter_quote:
                        cursor += 1
                        end = command.find(delimiter_quote, cursor)
                        if end < 0:
                            return None
                        delimiter = command[cursor:end]
                    else:
                        match = re.match(r"[A-Za-z0-9_]+", command[cursor:])
                        if not match:
                            return None
                        delimiter = match.group(0)
                    return (delimiter, strip_tabs) if delimiter else None
                return None

            for raw_line in runtime.splitlines():
                if heredoc_end:
                    candidate = raw_line.lstrip("\t") if heredoc_strip_tabs else raw_line
                    if candidate.strip() == heredoc_end:
                        heredoc_end = ""
                        heredoc_strip_tabs = False
                    continue
                stripped = strip_comment(raw_line).rstrip()
                if not stripped and not pending:
                    continue
                if stripped.endswith("\\"):
                    pending += stripped[:-1] + " "
                    continue
                command = strip_comment(pending + stripped).strip()
                pending = ""
                if not command:
                    continue
                commands.append(re.sub(r"[ \t]+", " ", command))
                heredoc = heredoc_marker(command)
                if heredoc:
                    heredoc_end, heredoc_strip_tabs = heredoc
            if pending.strip():
                commands.append(re.sub(r"[ \t]+", " ", strip_comment(pending).strip()))
            return commands

        docs_finalize_path = "scripts/planveyor/docs_finalize.zsh"
        expected_docs_finalize_inventory = [
            (docs_finalize_path, "planveyor_arch_docs_general", "receipt-path", "architect", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_arch_docs_general", "default", "architect", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_arch_followups", "single", "architect", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_coder_docs_general", "single", "coder", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_coder_followups", "single", "coder", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_planner_docs_general", "single", "planner", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_planner_followups", "single", "planner", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_reviewer_docs_general", "single", "reviewer", "role/main", "never", "workspace-write"),
            (docs_finalize_path, "planveyor_reviewer_followups", "single", "reviewer", "role/main", "never", "workspace-write"),
        ]
        expected_role_by_function = {
            "planveyor_arch_docs_general": "architect",
            "planveyor_arch_followups": "architect",
            "planveyor_coder_docs_general": "coder",
            "planveyor_coder_followups": "coder",
            "planveyor_planner_docs_general": "planner",
            "planveyor_planner_followups": "planner",
            "planveyor_reviewer_docs_general": "reviewer",
            "planveyor_reviewer_followups": "reviewer",
        }

        def docs_finalize_inventory(runtime: str) -> tuple[list[tuple[str, str, str, str, str, str, str]], int]:
            target_functions = {row[1] for row in expected_docs_finalize_inventory}
            function_pattern = re.compile(
                r"(?ms)^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\(\) \{\n"
                r"(?P<body>.*?)(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{|\Z)"
            )
            regions: list[tuple[str, str, str]] = []
            for function_match in function_pattern.finditer(runtime):
                function_name = function_match.group("name")
                if function_name not in target_functions:
                    continue
                body = function_match.group("body")
                if function_name != "planveyor_arch_docs_general":
                    regions.append((function_name, "single", body))
                    continue

                branches = re.search(
                    r'(?ms)^  if \[\[ -n "\$receipt_path" \]\]; then\n'
                    r"(?P<receipt>.*?)^  else\n"
                    r"(?P<default>.*?)^  fi\n",
                    body,
                )
                self.assertIsNotNone(branches, function_name)
                assert branches is not None
                regions.extend(
                    (
                        (function_name, "receipt-path", branches.group("receipt")),
                        (function_name, "default", branches.group("default")),
                    )
                )

            rows: list[tuple[str, str, str, str, str, str, str]] = []
            role_pattern = re.compile(
                r'_planveyor_with_role_env\s+(?P<role>[a-z]+)\s+"\$pybin"\s+'
                r"_planveyor_codex\s+exec\b"
            )
            profile_args_marker = '"${codex_profile_args[@]}"'
            direct_profile_pattern = re.compile(r"(?:^|\s)(?:-p|--profile)(?:\s|=)")
            policy_pattern = re.compile(r'approval_policy="(?P<policy>[^"]+)"')
            sandbox_pattern = re.compile(r"--sandbox\s+(?P<sandbox>[A-Za-z0-9-]+)(?=\s|$)")
            for function_name, branch, region in regions:
                for line in logical_commands(region):
                    line = normalize_quoted_command_word(line)
                    if not wrapper_exec.search(line):
                        continue
                    self.assertIsNone(
                        direct_profile_pattern.search(line),
                        f"direct profile flag in {function_name}/{branch}: {line}",
                    )
                    matches = [
                        label
                        for label, contract in (
                            ("never", never_contract),
                            ("on-request", on_request_contract),
                        )
                        if contract.search(line)
                    ]
                    self.assertEqual(
                        len(matches),
                        1,
                        f"unclassified docs-finalize Codex exec in {function_name}/{branch}: {line}",
                    )
                    role = role_pattern.search(line)
                    profile = "role/main" if line.count(profile_args_marker) == 1 else "<invalid-profile-args>"
                    policy = policy_pattern.search(line)
                    sandbox = sandbox_pattern.search(line)
                    rows.append(
                        (
                            docs_finalize_path,
                            function_name,
                            branch,
                            role.group("role") if role else "<missing-role>",
                            profile,
                            policy.group("policy") if policy else "<missing-policy>",
                            sandbox.group("sandbox") if sandbox else "<missing-sandbox>",
                        )
                    )

            command_count = sum(
                len(list(wrapper_exec.finditer(normalize_quoted_command_word(line))))
                for line in logical_commands(runtime)
            )
            return rows, command_count

        def assert_docs_finalize_profile_contract(runtime: str) -> None:
            function_pattern = re.compile(
                r"(?ms)^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\(\) \{\n"
                r"(?P<body>.*?)(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{|\Z)"
            )
            bodies = {
                match.group("name"): match.group("body")
                for match in function_pattern.finditer(runtime)
                if match.group("name") in expected_role_by_function
            }
            self.assertEqual(set(bodies), set(expected_role_by_function))
            for function_name, role in expected_role_by_function.items():
                body = bodies[function_name]
                resolver = (
                    f'codex_profile="$(_planveyor_profile_for_role_mode {role} main)" '
                    "|| return $?"
                )
                declaration = "local -a codex_profile_args"
                initialization = "codex_profile_args=()"
                expansion = (
                    '[[ -n "${codex_profile//[[:space:]]/}" ]] && '
                    'codex_profile_args=(-p "$codex_profile")'
                )
                self.assertEqual(body.count(resolver), 1, function_name)
                self.assertEqual(body.count(declaration), 1, function_name)
                self.assertEqual(body.count(initialization), 1, function_name)
                self.assertEqual(body.count(expansion), 1, function_name)
                resolver_at = body.index(resolver)
                declaration_at = body.index(declaration, resolver_at)
                initialization_at = body.index(initialization, declaration_at)
                expansion_at = body.index(expansion, initialization_at)
                self.assertLess(resolver_at, declaration_at)
                self.assertLess(declaration_at, initialization_at)
                self.assertLess(initialization_at, expansion_at)
                invocations = list(
                    re.finditer(
                        r"_planveyor_with_role_env\s+"
                        + re.escape(role)
                        + r'\s+"\$pybin"\s+_planveyor_codex\s+exec\b',
                        body,
                    )
                )
                expected_invocation_count = (
                    2 if function_name == "planveyor_arch_docs_general" else 1
                )
                self.assertEqual(
                    len(invocations), expected_invocation_count, function_name
                )
                for invocation in invocations:
                    self.assertLess(expansion_at, invocation.start(), function_name)

        def assert_docs_finalize_inventory(runtime: str) -> None:
            assert_docs_finalize_profile_contract(runtime)
            rows, command_count = docs_finalize_inventory(runtime)
            self.assertEqual(command_count, len(expected_docs_finalize_inventory))
            self.assertEqual(len(rows), command_count)
            self.assertEqual(sorted(rows), sorted(expected_docs_finalize_inventory))

        docs_finalize_runtime = (
            REPO_ROOT / "scripts" / "planveyor" / "docs_finalize.zsh"
        ).read_text(encoding="utf-8")
        assert_docs_finalize_inventory(docs_finalize_runtime)

        equal_total_substitution = docs_finalize_runtime.replace(
            "planveyor_coder_followups() {",
            "planveyor_coder_docs_general() {",
            1,
        )
        substituted_rows, substituted_count = docs_finalize_inventory(equal_total_substitution)
        self.assertEqual(substituted_count, len(expected_docs_finalize_inventory))
        self.assertEqual(len(substituted_rows), len(expected_docs_finalize_inventory))
        self.assertNotEqual(
            sorted(substituted_rows),
            sorted(expected_docs_finalize_inventory),
        )
        with self.assertRaises(AssertionError):
            assert_docs_finalize_inventory(equal_total_substitution)

        duplicate_command = (
            '  _planveyor_with_role_env coder "$pybin" _planveyor_codex exec '
            "-c 'approval_policy=\"never\"' --sandbox workspace-write \"${codex_profile_args[@]}\" "
            'resume "${sid}" -\n'
        )
        duplicate_marker = (
            "  local rc=$?\n"
            "  popd >/dev/null || return 1\n"
            "  return $rc\n"
            "}\n\n"
            "planveyor_coder_followups() {"
        )
        negative_fixtures = {
            "unclassified": docs_finalize_runtime.replace(
                "--sandbox workspace-write",
                "--sandbox read-only",
                1,
            ),
            "duplicate": docs_finalize_runtime.replace(
                duplicate_marker,
                duplicate_command + duplicate_marker,
                1,
            ),
            "removed": docs_finalize_runtime.replace(
                "_planveyor_codex exec",
                "_planveyor_codex inspect",
                1,
            ),
            "policy_drift": docs_finalize_runtime.replace(
                "-c 'approval_policy=\"never\"' --sandbox workspace-write",
                "-c 'approval_policy=\"on-request\"' -c 'sandbox_mode=\"workspace-write\"'",
                1,
            ),
            "profile_args_drift": docs_finalize_runtime.replace(
                '"${codex_profile_args[@]}"',
                '"${retired_profile_args[@]}"',
                1,
            ),
            "profile_resolver_drift": docs_finalize_runtime.replace(
                "_planveyor_profile_for_role_mode architect main",
                "_planveyor_profile_for_role_mode reviewer main",
                1,
            ),
            "direct_profile_drift": docs_finalize_runtime.replace(
                '"${codex_profile_args[@]}"',
                '"${codex_profile_args[@]}" -p retired-profile',
                1,
            ),
            "profile_setup_after_exec": docs_finalize_runtime.replace(
                '  [[ -n "${codex_profile//[[:space:]]/}" ]] && '
                'codex_profile_args=(-p "$codex_profile")\n\n  pushd "$root"',
                '  pushd "$root"',
                1,
            ).replace(
                '          resume "${sid}" -)\n',
                '          resume "${sid}" -)\n'
                '  [[ -n "${codex_profile//[[:space:]]/}" ]] && '
                'codex_profile_args=(-p "$codex_profile")\n',
                1,
            ),
        }
        for fixture_name, mutated_runtime in negative_fixtures.items():
            with self.subTest(fixture=fixture_name):
                with self.assertRaises(AssertionError):
                    assert_docs_finalize_inventory(mutated_runtime)

        executable_after_comment = logical_commands(
            "# comment that ends with a continuation \\\n"
            "command codex exec -p test -\n"
        )
        self.assertIn("command codex exec -p test -", executable_after_comment)
        executable_after_quoted_marker = logical_commands(
            "print -r -- '<<TAG'\n"
            "command codex exec -p test -\n"
            "TAG\n"
        )
        self.assertIn("command codex exec -p test -", executable_after_quoted_marker)
        executable_after_here_string = logical_commands(
            "read -r value <<< \"$payload\"\n"
            "command codex exec -p test -\n"
        )
        self.assertIn("command codex exec -p test -", executable_after_here_string)
        executable_after_arithmetic_shift = logical_commands(
            "print -r -- $((1 << 2))\n"
            "command codex exec -p test -\n"
        )
        self.assertIn("command codex exec -p test -", executable_after_arithmetic_shift)
        executable_after_separator_comment = logical_commands(
            "print -r -- before;# comment containing <<MUTATION_TEXT\n"
            "command codex exec -p test -\n"
        )
        self.assertIn("command codex exec -p test -", executable_after_separator_comment)
        self.assertIsNotNone(
            direct_exec.search(normalize_quoted_command_word('"codex" exec -p test -'))
        )
        self.assertIsNotNone(
            wrapper_exec.search(
                normalize_quoted_command_word(
                    '"_planveyor_codex" exec -c \'approval_policy="never"\' '
                    "--sandbox workspace-write -"
                )
            )
        )

        classified: list[tuple[Path, str, str]] = []
        for path in sorted((REPO_ROOT / "scripts").rglob("*.zsh")):
            runtime = path.read_text(encoding="utf-8")
            for line in logical_commands(runtime):
                line = normalize_quoted_command_word(line)
                direct_match = direct_exec.search(line)
                self.assertIsNone(
                    direct_match,
                    f"direct Codex exec bypass in {path.relative_to(REPO_ROOT)}: {line}",
                )
                if not wrapper_exec.search(line):
                    continue
                self.assertNotIn("--full-auto", line)
                self.assertEqual(line.count("approval_policy="), 1, line)
                sandbox_selectors = len(re.findall(r"(?:--sandbox\b|sandbox_mode=)", line))
                self.assertEqual(sandbox_selectors, 1, line)
                matches = [
                    label
                    for label, contract in (
                        ("never", never_contract),
                        ("on-request", on_request_contract),
                    )
                    if contract.search(line)
                ]
                self.assertEqual(
                    len(matches),
                    1,
                    f"unclassified Codex exec in {path.relative_to(REPO_ROOT)}: {line.strip()}",
                )
                classified.append((path, line.strip(), matches[0]))

        never_by_path = {
            path: sum(1 for item_path, _, label in classified if item_path == path and label == "never")
            for path in expected_never_by_path
        }
        self.assertEqual(never_by_path, expected_never_by_path)
        self.assertEqual(sum(label == "never" for _, _, label in classified), 28)
        self.assertEqual(sum(label == "on-request" for _, _, label in classified), 5)
        self.assertEqual(len(classified), 33)

    def test_custom_manager_payload_builders_use_prompt_resolver(self) -> None:
        role_runtime = (REPO_ROOT / "scripts" / "planveyor" / "role_runtime.zsh").read_text(encoding="utf-8")
        supervisor = re.search(
            r"^_planveyor_manager_custom_pipeline_supervise\(\) \{.*?^}\s*"
            r"(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{|\Z)",
            role_runtime,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(supervisor)
        supervisor_body = supervisor.group(0)
        self.assertRegex(
            supervisor_body,
            r'prompt_body="\$\(_planveyor_role_prompt_body manager custom_pipeline\)" \|\| return \$\?',
        )
        self.assertIn("printf '%s\\n' \"$prompt_body\"", supervisor_body)
        self.assertNotIn(
            "_planveyor_prompt_file_for_role_phase manager custom_pipeline",
            supervisor_body,
        )
        self.assertNotIn('cat "$prompt_file"', supervisor_body)
        self.assertNotIn(
            'cat "$(_planveyor_prompts_root)/manager_custom_pipeline.md"',
            supervisor_body,
        )
        for fn_name in (
            "planveyor_manager_custom_pipeline",
            "planveyor_manager_custom_pipeline_tui",
            "planveyor_manager_custom_pipeline_cmd",
        ):
            with self.subTest(fn=fn_name):
                match = re.search(
                    rf"^{re.escape(fn_name)}\(\) \{{.*?^}}\s*(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{{|\Z)",
                    role_runtime,
                    flags=re.MULTILINE | re.DOTALL,
                )
                self.assertIsNotNone(match)
                body = match.group(0)
                self.assertTrue(
                    "_planveyor_manager_custom_pipeline_supervise" in body
                    or "_planveyor_manager_custom_pipeline_nonrun_cmd" in body
                )

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        fixture_home = root.parent / f".{root.name}-git-home"
        fixture_home.mkdir(exist_ok=True)
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith(("GIT_", "PLANVEYOR_", "ZCODE_", "CODEX_")):
                env.pop(key)
        env.update(
            HOME=str(fixture_home),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
            GIT_AUTHOR_NAME="Router fixture",
            GIT_AUTHOR_EMAIL='router-fixture' + '@' + 'example' + '.' + 'invalid',
            GIT_COMMITTER_NAME="Router fixture",
            GIT_COMMITTER_EMAIL='router-fixture' + '@' + 'example' + '.' + 'invalid',
            LC_ALL="C",
        )
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgSign=false",
                *args,
            ],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=20,
        )

    def _copy_runtime_fixture(self, root: Path) -> None:
        """Materialize the source/runtime closure used by router subprocesses."""

        for relative in FIXTURE_RUNTIME_SCRIPTS:
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        for relative in FIXTURE_RUNTIME_DOCUMENT_TREES:
            shutil.copytree(REPO_ROOT / relative, root / relative)
        for relative in FIXTURE_RUNTIME_DOCUMENTS:
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _install_fake_codex(self, root: Path) -> tuple[Path, Path]:
        bin_dir = root / "bin"
        log_dir = root / ".fake_codex"
        bin_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        codex_script = bin_dir / "codex"
        codex_script.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                from pathlib import Path
                import json
                import os
                import subprocess
                import sys

                log_dir = Path(os.environ["PLANVEYOR_FAKE_CODEX_DIR"])
                log_dir.mkdir(parents=True, exist_ok=True)
                counter_path = log_dir / "counter"
                try:
                    counter = int(counter_path.read_text(encoding="utf-8").strip())
                except FileNotFoundError:
                    counter = 0
                counter += 1
                counter_path.write_text(str(counter), encoding="utf-8")

                stdin_text = sys.stdin.read()
                stdin_path = ""
                if stdin_text:
                    stdin_path = str(log_dir / f"stdin-{counter}.txt")
                    Path(stdin_path).write_text(stdin_text, encoding="utf-8")

                entry = {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "stdin_path": stdin_path,
                    "manager_invocation_id": os.environ.get("MANAGER_INVOCATION_ID", ""),
                    "manager_invocation_receipt_path": os.environ.get(
                        "MANAGER_INVOCATION_RECEIPT_PATH", ""
                    ),
                }
                with (log_dir / "calls.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\\n")

                if os.environ.get("PLANVEYOR_FAKE_MANAGER_QUEUE_ACTION") == "closeout":
                    closeout = subprocess.run(
                        [
                            "/bin/zsh",
                            "-fc",
                            "source scripts/planveyor.zsh && "
                            "planveyor_q_closeout_json "
                            "--manager-mode manager-custom-pipeline >/dev/null",
                        ],
                        cwd=os.getcwd(),
                        env=os.environ.copy(),
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if closeout.returncode != 0:
                        sys.stderr.write(closeout.stderr)
                        raise SystemExit(closeout.returncode)

                manager_receipt = os.environ.get("MANAGER_INVOCATION_RECEIPT_PATH", "")
                if (
                    manager_receipt
                    and os.environ.get("PLANVEYOR_FAKE_MANAGER_SKIP_CHECKPOINT") != "1"
                ):
                    receipt_path = Path(manager_receipt)
                    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if (
                        payload.get("state") == "running"
                        and payload.get("stop_checkpoint_state") == "missing"
                    ):
                        payload["stop_checkpoint_state"] = "recorded"
                        payload["stop_reason_code"] = "terminal_status"
                        payload["stop_source_refs"] = [
                            f"{payload.get('active_plan') or 'queue'}#fake-manager"
                        ]
                        prepared = receipt_path.with_name(
                            f".{receipt_path.name}.fake-manager.tmp"
                        )
                        prepared.write_text(
                            json.dumps(payload, sort_keys=True) + "\\n",
                            encoding="utf-8",
                        )
                        prepared.chmod(0o600)
                        os.replace(prepared, receipt_path)

                print(f"Fake Codex session {os.environ.get('PLANVEYOR_FAKE_CODEX_SID', '')}")
                raise SystemExit(int(os.environ.get("PLANVEYOR_FAKE_MANAGER_EXIT", "0")))
                """
            ),
            encoding="utf-8",
        )
        codex_script.chmod(0o755)
        return bin_dir, log_dir

    def _prepare_repo(self, tmpdir: str, repo_name: str) -> tuple[Path, dict[str, str], Path]:
        root = Path(tmpdir) / repo_name
        root.mkdir(parents=True, exist_ok=True)
        self._copy_runtime_fixture(root)

        self._git(root, "init", "--quiet")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._git(root, "add", "--", "scripts", "docs")
        self._git(root, "commit", "--quiet", "-m", "fixture runtime baseline")

        bin_dir, log_dir = self._install_fake_codex(root)
        home_dir = root / ".home"
        codex_home = root / ".codex-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=True)
        child_tmp = (Path(tmpdir) / f"{repo_name}-child-tmp").resolve()
        child_tmp.mkdir(exist_ok=True)

        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PLANVEYOR_", "ZCODE_", "CODEX_", "GIT_"))
        }
        env.update(
            HOME=str(home_dir),
            CODEX_HOME=str(codex_home),
            PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
            PYBIN=sys.executable,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONNOUSERSITE="1",
            TMPDIR=str(child_tmp),
            TMPPREFIX=str(child_tmp / "zsh"),
            PLANVEYOR_ROOT=str(root),
            PLANVEYOR_FAKE_CODEX_DIR=str(log_dir),
            PLANVEYOR_FAKE_CODEX_SID=FAKE_SID,
            PLANVEYOR_FAKE_CODEX_BIN=str(bin_dir),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
        )
        return root, env, log_dir

    def _run(self, root: Path, env: dict[str, str], command: str) -> subprocess.CompletedProcess[str]:
        shell_command = (
            f'export PATH={shlex.quote(env["PLANVEYOR_FAKE_CODEX_BIN"])}:$PATH; '
            f"source scripts/planveyor.zsh && {command}"
        )
        argv = ["/bin/zsh", "-fc", shell_command]
        try:
            return subprocess.run(
                argv,
                cwd=root,
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=60,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(
                "\x1b[31mtest child timed out: "
                f"argv={argv!r}; cwd={root}; timeout={exc.timeout!r}; "
                f"stdout={exc.stdout!r}; stderr={exc.stderr!r}\x1b[0m"
            )

    def _codex_calls(self, log_dir: Path) -> list[dict[str, object]]:
        log_path = log_dir / "calls.jsonl"
        if not log_path.exists():
            return []
        return [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _seed_fake_codex_rollout(
        self,
        root: Path,
        env: dict[str, str],
        sid: str = FAKE_SID,
    ) -> None:
        rollout_dir = Path(env["CODEX_HOME"]) / "sessions" / "2026" / "08" / "27"
        rollout_dir.mkdir(parents=True, exist_ok=True)
        rollout = rollout_dir / f"rollout-test-{sid}.jsonl"
        rollout.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-27T10:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "id": sid,
                        "timestamp": "2026-08-27T10:00:00Z",
                        "cwd": str(root),
                        "cli_version": "0.149.1",
                        "originator": "codex_exec",
                        "source": "exec",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_run_timeout_is_fail_closed_with_context(self) -> None:
        root = Path("/tmp/planveyor-router-timeout")
        env = {"PLANVEYOR_FAKE_CODEX_BIN": "/tmp/planveyor-fake-bin"}
        expired = subprocess.TimeoutExpired(
            ["/bin/zsh", "-fc", "timeout-fixture"],
            60,
            output="fake stdout",
            stderr="fake stderr",
        )

        with mock.patch.object(subprocess, "run", side_effect=expired) as run:
            with self.assertRaisesRegex(AssertionError, "test child timed out") as raised:
                self._run(root, env, "timeout-fixture")

        message = str(raised.exception)
        self.assertIn("argv=", message)
        self.assertIn("cwd=/tmp/planveyor-router-timeout", message)
        self.assertIn("stdout='fake stdout'", message)
        self.assertIn("stderr='fake stderr'", message)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def _collab_agent_artifacts(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(
                root.glob(".planveyor.collab.agent.*"),
                key=lambda item: item.name,
            )
            if path.is_file()
        }

    def _seed_noncanonical_collab_agent_artifacts(self, root: Path) -> dict[str, bytes]:
        roles = (
            "architect",
            "planner",
            "coder",
            "reviewer_code_risk",
            "reviewer_code_contracts",
            "reviewer",
        )
        for role in roles:
            (root / f".planveyor.collab.agent.{role}").write_bytes(
                f"stale-{role}\n".encode("utf-8")
            )
            (root / f".planveyor.collab.agent.{role}.log").write_bytes(
                f"2000-01-01T00:00:00Z\tlogged-{role}\tsync\n".encode("utf-8")
            )
        return self._collab_agent_artifacts(root)

    def _role_runtime_function_body(self, name: str) -> str:
        role_runtime = (
            REPO_ROOT / "scripts" / "planveyor" / "role_runtime.zsh"
        ).read_text(encoding="utf-8")
        match = re.search(
            rf"^{re.escape(name)}\(\) \{{.*?^}}\s*"
            rf"(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{{|\Z)",
            role_runtime,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, name)
        return str(match.group(0))

    def _assert_absent_state(self, root: Path) -> None:
        for rel_path in (
            ".planveyor.planpath",
            ".planveyor.merge_tracker.md",
            ".planveyor.range.base",
            ".planveyor.range.head",
            ".planveyor.range.merge",
            ".planveyor.session.manager",
        ):
            self.assertFalse((root / rel_path).exists(), rel_path)

    def _write_custom_manager_plan(
        self,
        root: Path,
        plan_rel: str,
        *,
        status: str,
        next_plans: list[str] | None = None,
        execution_queue: list[str] | None = None,
        resume_parent: str = "none",
        required_manager_mode: str = "manager-custom-pipeline",
        depends_on: list[str] | None = None,
        machine_authority: bool = True,
    ) -> Path:
        plan = root / plan_rel
        plan.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "plan_meta": {
                "cluster": "process",
                "required_manager_mode": required_manager_mode,
                "next_plans": next_plans or [],
            }
        }
        if depends_on is not None:
            meta["plan_meta"]["depends_on"] = depends_on
        decision = {
            "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        if machine_authority:
            meta["plan_meta"]["machine_authority_decision"] = decision
        status_norm = " ".join(status.lower().split())
        needs_draft_ref = (
            machine_authority
            and status_norm in PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_REF_REQUIRED_STATUSES
        )
        draft_rel = f"docs/code_drafts/{plan.stem}__code_draft.md"
        context_line = (
            f"- Code draft(s): `{draft_rel}`"
            if needs_draft_ref
            else "- Code draft(s): N/A (why=isolated queue-lineage fixture has no implementation bundle)"
        )
        text = (
            f"# Plan: {plan.stem}\n\n"
            f"**Status:** {status}\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            f"{json.dumps(meta, sort_keys=True)}\n"
            "```\n\n"
            "**Context links (source of truth):**\n"
            f"{context_line}\n\n"
            "## Documentation impact / provenance\n"
            "- Source docs used: N/A (why=isolated queue-lineage fixture has no documentation source)\n"
            "- Synchronous doc/registry targets: N/A (why=isolated queue-lineage fixture changes no documentation target)\n"
            "- Post-merge canon updates: N/A (why=isolated queue-lineage fixture has no canon update)\n"
            "- Deferred documentation follow-ups: N/A (why=isolated queue-lineage fixture has no documentation follow-up)\n"
            "- Provenance refs: N/A (why=generated fixture is self-contained)\n\n"
            "## Как я понял задачу\n"
            "Изолированный fixture проверяет queue lineage без implementation bundle, fake code draft или изменения queue authority.\n\n"
            "## Rollout packet handoff\n"
            "- Role: N/A (why=isolated queue-lineage fixture has no rollout packet)\n"
            "- Packet path: N/A (why=isolated queue-lineage fixture has no rollout packet)\n"
            "- Target repo: N/A (why=isolated queue-lineage fixture has no rollout packet)\n"
            "- Suggested target plan slug: N/A (why=isolated queue-lineage fixture has no rollout packet)\n"
            "- Queue after import: N/A (why=isolated queue-lineage fixture has no rollout packet)\n\n"
            "## Close-out routing\n"
            "- Roadmap/queue sync: N/A (why=fixture verifies supplied queue lineage without a roadmap mutation)\n"
            "- Follow-up sync: N/A (why=isolated queue-lineage fixture has no follow-up mutation)\n"
            "- Next bounded slice: N/A (why=isolated queue-lineage fixture has no successor slice)\n"
            "- Terminal outcome: N/A (why=isolated queue-lineage fixture declares no terminal product outcome)\n\n"
            "## Verification rerun / exec handoff\n"
            "- Mode: N/A (why=isolated queue-lineage fixture has no rerun handoff)\n"
            "- Context source: N/A (why=isolated queue-lineage fixture is self-contained)\n"
            "- Prompt: N/A (why=isolated queue-lineage fixture is exercised by its test)\n"
            "- Command: N/A (why=isolated queue-lineage fixture is exercised by its test)\n"
            "- Expected artifact: N/A (why=isolated queue-lineage fixture has no implementation artifact)\n"
        )
        if execution_queue is not None:
            text += (
                "\n## Execution queue\n"
                f"- Resume parent: `{resume_parent}`\n"
                + "".join(f"- Plan: `{item}`\n" for item in execution_queue)
            )
        plan.write_text(text, encoding="utf-8")
        if needs_draft_ref:
            draft = root / draft_rel
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text(
                "# Code draft: router fixture\n\n"
                "```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": plan_rel,
                            "cluster": "process",
                            "targets": [{"path": "scripts/plan_queue.py", "kind": "py"}],
                            "machine_authority_decision_ref": {
                                "applicability": "not_applicable",
                                "reason_code": "no_machine_authority_change",
                                "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(
                                    decision
                                ),
                            },
                        }
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )
        return plan

    def test_custom_pipeline_preserves_native_collab_bytes(self) -> None:
        for name, command_kind, expected_rc, receipt_state, receipt_reason in (
            ("run", "run", 0, "completed", "manager_process_exited"),
            ("run_q", "run Q", 0, "completed", "manager_process_exited"),
            ("run_q_alias", "run_q", 0, "completed", "manager_process_exited"),
            ("status", "status", 0, None, None),
            ("plan_set", "plan_set", 0, None, None),
            ("nonzero_run", "run", 17, "blocked", "manager_process_failed"),
        ):
            with self.subTest(command=name), tempfile.TemporaryDirectory() as tmpdir:
                root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
                plan_rel = f"docs/plans/260802_1457_{name}.md"
                self._write_custom_manager_plan(
                    root,
                    plan_rel,
                    status="Architect initial draft",
                )
                session = self._run(
                    root,
                    env,
                    f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null",
                )
                self.assertEqual(session.returncode, 0, session.stderr)
                before = self._seed_noncanonical_collab_agent_artifacts(root)
                self.assertEqual(len(before), 12)

                queue_payload = json.dumps(
                    {
                        "exists": True,
                        "queue_empty": False,
                        "active_plan": plan_rel,
                        "resume_parent_plan": None,
                        "effective_plan": plan_rel,
                        "last_transition": {},
                    },
                    sort_keys=True,
                )
                if command_kind == "run":
                    command = f"planveyor_manager_custom_pipeline_cmd run {plan_rel}"
                elif command_kind in {"run Q", "run_q"}:
                    queue_stub = (
                        f"planveyor_q_next_json() {{ print -r -- {shlex.quote(queue_payload)}; }}; "
                        f"planveyor_q_show() {{ print -r -- {shlex.quote(queue_payload)}; }}; "
                    )
                    command = (
                        queue_stub
                        + "planveyor_manager_custom_pipeline_cmd "
                        + command_kind
                    )
                elif command_kind == "plan_set":
                    command = f"planveyor_manager_custom_pipeline_cmd plan_set {plan_rel}"
                else:
                    command = "planveyor_manager_custom_pipeline_cmd status"
                if name == "nonzero_run":
                    env["PLANVEYOR_FAKE_MANAGER_EXIT"] = "17"
                command += '; rc=$?; print -r -- "PWD_AFTER=$PWD" >&2; exit $rc'

                result = self._run(root, env, command)

                self.assertEqual(result.returncode, expected_rc, result.stderr)
                pwd_lines = [
                    line
                    for line in result.stderr.splitlines()
                    if line.startswith("PWD_AFTER=")
                ]
                self.assertEqual(len(pwd_lines), 1, result.stderr)
                self.assertEqual(
                    Path(pwd_lines[0].removeprefix("PWD_AFTER=")).resolve(),
                    root.resolve(),
                )
                self.assertEqual(self._collab_agent_artifacts(root), before)
                self.assertEqual(len(self._codex_calls(log_dir)), 1)
                if receipt_state is None:
                    self.assertFalse((root / ".planveyor.manager_runs").exists())
                    continue

                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["state"], receipt_state)
                self.assertEqual(receipt["reason_code"], receipt_reason)
                if command_kind in {"run Q", "run_q"}:
                    self.assertEqual(receipt["command"], "run_q")
                    self.assertEqual(receipt["queue_readback"]["active_plan"], plan_rel)
                    self.assertEqual(
                        Path(receipt["oracle_readback"]["plan_path"]).resolve(),
                        (root / plan_rel).resolve(),
                    )
                else:
                    self.assertEqual(receipt["command"], "run")
                    self.assertEqual(receipt["active_plan"], plan_rel)
                    self.assertEqual(receipt["final_plan"], plan_rel)

        for function_name in (
            "_planveyor_manager_custom_pipeline_supervise",
            "_planveyor_manager_custom_pipeline_nonrun_cmd",
        ):
            with self.subTest(function=function_name):
                self.assertEqual(
                    self._role_runtime_function_body(function_name).count(
                        "_planveyor_collab_agent_sync_all"
                    ),
                    0,
                )
        for function_name in (
            "planveyor_manager_collab",
            "planveyor_manager_collab_tui",
            "planveyor_manager_collab_cmd",
            "planveyor_merge_apply_collab_tui",
            "planveyor_merge_apply_collab_cmd",
        ):
            with self.subTest(function=function_name):
                self.assertEqual(
                    self._role_runtime_function_body(function_name).count(
                        "_planveyor_collab_agent_sync_all"
                    ),
                    1,
                )

    def test_neutral_consumer_manager_init_reaches_fake_codex_and_saves_sid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "neutral-consumer")
            self._assert_absent_state(root)

            result = self._run(
                root,
                env,
                'planveyor_manager_init && print -r -- "C03_ROUTER_TMP=$TMPDIR|$TMPPREFIX"',
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                f"C03_ROUTER_TMP={env['TMPDIR']}|{env['TMPPREFIX']}",
                result.stdout.splitlines(),
            )

            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            argv = [str(item) for item in calls[0]["argv"]]
            self.assertIn("exec", argv)
            self.assertNotIn("--full-auto", argv)
            self.assertIn('approval_policy="never"', argv)
            self.assertIn("--sandbox", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
            self.assertNotIn("-p", argv)  # neutral consumer uses its Codex default

            stdin_path = Path(str(calls[0]["stdin_path"]))
            self.assertTrue(stdin_path.exists())
            payload = stdin_path.read_text(encoding="utf-8")
            self.assertIn("ROLE=Manager", payload)

            session_file = root / ".planveyor.session.manager"
            self.assertTrue(session_file.exists())
            self.assertEqual(session_file.read_text(encoding="utf-8").splitlines()[-1], FAKE_SID)

    def test_regular_manager_resume_uses_current_headless_exec_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan_rel = "docs/plans/260827_1200_manager_resume.md"
            self._write_custom_manager_plan(
                root,
                plan_rel,
                status="Ready for Coder",
                required_manager_mode="manager-collab",
            )
            self._seed_fake_codex_rollout(root, env)

            result = self._run(
                root,
                env,
                f"planveyor_plan_set {shlex.quote(plan_rel)} >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            argv = [str(item) for item in calls[0]["argv"]]
            self.assertEqual(
                argv,
                [
                    "exec",
                    "-c",
                    'approval_policy="never"',
                    "--sandbox",
                    "workspace-write",
                    "resume",
                    FAKE_SID,
                    "-",
                ],
            )
            stdin_path = Path(str(calls[0]["stdin_path"]))
            self.assertIn("ROLE=Manager", stdin_path.read_text(encoding="utf-8"))

    def test_collab_tui_runtime_pin_guard_epilogue_preserves_manager_rc(self) -> None:
        """Exercise the wrapper epilogue; validator/drift semantics stay outside this stubbed seam."""
        for validator_fails, manager_exit in ((False, 0), (False, 23), (True, 0), (True, 23)):
            with self.subTest(
                validator_fails=validator_fails, manager_exit=manager_exit
            ), tempfile.TemporaryDirectory() as tmpdir:
                root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
                plan_rel = "docs/plans/260915_0000_runtime_pin_drift.md"
                self._write_custom_manager_plan(
                    root,
                    plan_rel,
                    status="Ready for Coder",
                    required_manager_mode="manager-collab",
                )
                self._seed_fake_codex_rollout(root, env)
                env["PLANVEYOR_FAKE_MANAGER_EXIT"] = str(manager_exit)
                temp_root = root / ".test-tmp"
                temp_root.mkdir()
                env["TMPDIR"] = str(temp_root)
                env["TMPPREFIX"] = str(temp_root / "zsh")
                posthooks = log_dir / "posthooks.log"
                marker = shlex.quote(str(posthooks))
                validator_log = log_dir / "validator.log"
                validator_marker = shlex.quote(str(validator_log))
                validator_exit = 1 if validator_fails else 0
                result = self._run(
                    root,
                    env,
                    "\n".join(
                        (
                            "_planveyor_codex() { \"$PYBIN\" \"$PLANVEYOR_FAKE_CODEX_BIN/codex\" \"$@\"; }",
                            f"planveyor_plan_set {shlex.quote(plan_rel)} >/dev/null || exit $?",
                            f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null || exit $?",
                            f"_planveyor_authority_validate_runtime_pin() {{ print -r -- validate >> {validator_marker}; return {validator_exit}; }}",
                            f"_planveyor_collab_agent_sync_all() {{ print -r -- sync >> {marker}; }}",
                            f"_planveyor_collab_snapshot_ids() {{ print -r -- snapshot >> {marker}; print -r -- '[]'; }}",
                            f"_planveyor_collab_log_transitions() {{ print -r -- transition >> {marker}; }}",
                            'print -r -- "TEST_CWD_BEFORE=${PWD}"',
                            'print -r -- "TEST_DIRSTACK_BEFORE=${#dirstack}"',
                            'print -r -- "C03_ROUTER_OVERRIDE_TMP=$TMPDIR|$TMPPREFIX"',
                            "planveyor_manager_collab_tui --no-alt-screen",
                            "exit_code=$?",
                            'print -r -- "TEST_CWD_AFTER=${PWD}"',
                            'print -r -- "TEST_DIRSTACK_AFTER=${#dirstack}"',
                            'exit "$exit_code"',
                        )
                    ),
                )

                self.assertEqual(result.returncode, manager_exit, result.stderr)
                self.assertIn(
                    f"C03_ROUTER_OVERRIDE_TMP={temp_root}|{temp_root / 'zsh'}",
                    result.stdout.splitlines(),
                )
                calls = self._codex_calls(log_dir)
                self.assertEqual(len(calls), 1, calls)
                argv = [str(item) for item in calls[0]["argv"]]
                self.assertEqual(argv[0], "resume", argv)
                self.assertIn("--no-alt-screen", argv)
                self.assertEqual(argv[argv.index("-s") + 1], "workspace-write")
                self.assertIn(FAKE_SID, argv)
                self.assertIn("ROLE=Manager", argv[-1])
                self.assertEqual(Path(str(calls[0]["cwd"])).resolve(), root.resolve())

                def output_values(prefix: str) -> list[str]:
                    return [
                        line.removeprefix(prefix)
                        for line in result.stdout.splitlines()
                        if line.startswith(prefix)
                    ]

                self.assertEqual(
                    output_values("TEST_CWD_BEFORE="),
                    [str(root.resolve())],
                    result.stdout,
                )
                self.assertEqual(
                    output_values("TEST_CWD_AFTER="),
                    output_values("TEST_CWD_BEFORE="),
                    result.stdout,
                )
                self.assertEqual(
                    output_values("TEST_DIRSTACK_AFTER="),
                    output_values("TEST_DIRSTACK_BEFORE="),
                    result.stdout,
                )
                self.assertEqual(
                    sorted(path.name for path in temp_root.glob("planveyor.collab.*")),
                    [],
                )
                events = posthooks.read_text(encoding="utf-8").splitlines()
                self.assertEqual(validator_log.read_text(encoding="utf-8").splitlines(), ["validate"])
                status_lines = result.stderr.splitlines()
                self.assertEqual(
                    len([line for line in status_lines if line.startswith("Plan status (pre):")]),
                    1,
                    result.stderr,
                )
                if validator_fails:
                    diagnostic = (
                        "planveyor: runtime_changed_after_resume; "
                        f"manager_rc={manager_exit}; posthooks=skipped"
                    )
                    self.assertEqual(
                        [
                            line
                            for line in result.stderr.splitlines()
                            if "runtime_changed_after_resume" in line
                        ],
                        [diagnostic],
                        result.stderr,
                    )
                    self.assertEqual(
                        len([line for line in status_lines if line.startswith("Plan status (post):")]),
                        0,
                        result.stderr,
                    )
                    self.assertEqual(events, ["snapshot"])
                else:
                    self.assertNotIn("runtime_changed_after_resume", result.stderr)
                    self.assertEqual(
                        len([line for line in status_lines if line.startswith("Plan status (post):")]),
                        1,
                        result.stderr,
                    )
                    self.assertEqual(
                        events,
                        ["snapshot", "sync", "snapshot", "transition"],
                    )

    def test_neutral_consumer_merge_review_control_lane_reaches_fake_codex_merge_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "neutral-consumer")
            self._assert_absent_state(root)

            result = self._run(root, env, "planveyor_merge_collab_cmd --range auto")

            self.assertEqual(result.returncode, 0, result.stderr)

            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 2, calls)
            init_argv = [str(item) for item in calls[0]["argv"]]
            self.assertNotIn("--full-auto", init_argv)
            self.assertIn('approval_policy="never"', init_argv)
            self.assertIn("--sandbox", init_argv)
            self.assertEqual(
                init_argv[init_argv.index("--sandbox") + 1],
                "workspace-write",
            )
            self.assertIn("resume", calls[1]["argv"])
            payload = str(calls[1]["argv"][-1])
            self.assertIn("ROLE=Manager", payload)
            self.assertIn("MERGE_MODE=1", payload)
            self.assertIn("MANAGER_CMD=merge_run --range auto", payload)

            session_file = root / ".planveyor.session.manager"
            self.assertTrue(session_file.exists())
            self.assertEqual(session_file.read_text(encoding="utf-8").splitlines()[-1], FAKE_SID)

    def test_default_repo_custom_pipeline_keeps_ordinary_planpath_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            self._assert_absent_state(root)

            result = self._run(root, env, "planveyor_manager_custom_pipeline")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No selected plan. Select an existing plan with:", result.stderr)
            self.assertIn("planveyor_plan_set <PLAN_PATH>", result.stderr)
            self.assertEqual(self._codex_calls(log_dir), [])

    def test_default_repo_custom_pipeline_tui_resume_uses_current_codex_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            self._assert_absent_state(root)
            plan = root / "docs" / "plans" / "260101_0000_custom_tui.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                textwrap.dedent(
                    """\
                    # Plan: custom TUI fake smoke

                    **Date:** 2026-01-01 00:00 MSK
                    **Plan type:** dev
                    **Status:** Architect initial draft

                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "required_manager_mode": "manager-custom-pipeline"
                      }
                    }
                    ```

                    ## Evidence
                    """
                ),
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_custom_tui.md >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_tui --no-alt-screen",
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            argv = [str(item) for item in calls[0]["argv"]]
            self.assertEqual(
                argv[:-1],
                ["resume", "--no-alt-screen", "-s", "workspace-write", FAKE_SID],
            )
            self.assertNotIn("--full-auto", argv)
            payload = argv[-1]
            self.assertIn("ROLE=Manager", payload)
            self.assertIn("PLAN_PATH=docs/plans/260101_0000_custom_tui.md", payload)
            self.assertIn("PRE_STATUS_LINE=", payload)

    def test_custom_pipeline_mode_mismatch_stops_before_sid_and_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan = root / "docs/plans/260712_1255_native_only.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: native only\n\n**Status:** Architect initial draft\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process","required_manager_mode":"manager-collab"}}\n'
                "```\n",
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260712_1255_native_only.md >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline",
            )

            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn("state=mismatch", result.stderr)
            self.assertIn("reason=required_mode_mismatch", result.stderr)
            self.assertIn("no automatic Manager switch was attempted", result.stderr)
            self.assertEqual(self._codex_calls(log_dir), [])
            receipts = list((root / ".planveyor.manager_runs").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(receipt["reason_code"], "manager_mode_rejected")
            self.assertEqual(receipt["compatibility_pointer_state"], "updated")

    def test_collab_explicit_run_path_precedes_stale_cached_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plans = root / "docs/plans"
            plans.mkdir(parents=True, exist_ok=True)
            cached_path = "docs/plans/260712_1255_cached_custom.md"
            explicit_path = "docs/plans/260712_1256_explicit_collab.md"
            (plans / "260712_1255_cached_custom.md").write_text(
                "# Plan: cached\n\n**Status:** Architect initial draft\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process","required_manager_mode":"manager-custom-pipeline"}}\n'
                "```\n",
                encoding="utf-8",
            )
            (plans / "260712_1256_explicit_collab.md").write_text(
                "# Plan: explicit\n\n**Status:** Blocked\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process","required_manager_mode":"manager-collab"}}\n'
                "```\n",
                encoding="utf-8",
            )
            queue_sentinel = root / ".queue-helper-called"
            queue_guards = (
                f"queue_sentinel={shlex.quote(str(queue_sentinel))}; "
                'planveyor_q_next_json() { print -r -- next > "$queue_sentinel"; return 97; }; '
                'planveyor_q_show() { print -r -- show > "$queue_sentinel"; return 97; }; '
                'planveyor_q_advance_json() { print -r -- advance > "$queue_sentinel"; return 97; }; '
                'planveyor_q_closeout_json() { print -r -- closeout > "$queue_sentinel"; return 97; }; '
                'planveyor_q_stop_json() { print -r -- stop > "$queue_sentinel"; return 97; }; '
                'planveyor_q_set() { print -r -- set > "$queue_sentinel"; return 97; }; '
            )

            result = self._run(
                root,
                env,
                f"planveyor_plan_set {cached_path} >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                f"cached_pointer=$(cat .planveyor.planpath) && {queue_guards}"
                f"planveyor_manager_collab_cmd run {explicit_path} && "
                'test "$(cat .planveyor.planpath)" = "$cached_pointer"',
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(queue_sentinel.exists())
            self.assertFalse((root / ".planveyor.planqueue.json").exists())
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            payload = str(calls[0]["argv"][-1])
            self.assertIn(f"PLAN_PATH={explicit_path}", payload)
            self.assertNotIn(f"PLAN_PATH={cached_path}", payload)
            self.assertRegex(payload, r"(?m)^PRE_STATUS_LINE=\d+:\*\*Status:\*\* Blocked$")
            self.assertEqual(payload.rstrip().splitlines()[-1], f"MANAGER_CMD=run {explicit_path}")

    def test_native_legacy_custom_mode_prose_cannot_override_missing_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan = root / "docs/plans/260711_0136_legacy_custom.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: legacy 0136 fixture\n\n**Status:** Ready for Planner\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process","tags":["manager-custom-pipeline"]}}\n'
                "```\n\n"
                "## Verification rerun / exec handoff\n"
                "- Mode: manager-custom-pipeline\n"
                "- Command: `planveyor_manager_custom_pipeline_cmd run`\n",
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260711_0136_legacy_custom.md >/dev/null && "
                "planveyor_manager_collab",
            )

            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn("state=unclassified_missing", result.stderr)
            self.assertIn("reason=required_mode_missing", result.stderr)
            self.assertFalse((root / ".planveyor.session.manager").exists())
            self.assertEqual(self._codex_calls(log_dir), [])

    def test_custom_explicit_run_path_works_without_cached_planpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan = root / "docs/plans/260712_1255_explicit_custom.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: explicit custom\n\n**Status:** Architect initial draft\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process","required_manager_mode":"manager-custom-pipeline"}}\n'
                "```\n",
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run docs/plans/260712_1255_explicit_custom.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".planveyor.planpath").exists())
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            self.assertIn(
                "PLAN_PATH=docs/plans/260712_1255_explicit_custom.md",
                str(calls[0]["argv"][-1]),
            )
            argv = [str(item) for item in calls[0]["argv"]]
            self.assertNotIn("--full-auto", argv)
            self.assertIn('approval_policy="on-request"', argv)
            self.assertIn('sandbox_mode="workspace-write"', argv)
            invocation_id = str(calls[0]["manager_invocation_id"])
            receipt_path = Path(str(calls[0]["manager_invocation_receipt_path"]))
            self.assertTrue(invocation_id)
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["invocation_id"], invocation_id)
            self.assertEqual(receipt["command"], "run")
            self.assertEqual(receipt["state"], "completed")
            self.assertEqual(receipt["reason_code"], "manager_process_exited")
            self.assertEqual(receipt["stop_checkpoint_state"], "recorded")
            self.assertEqual(receipt["compatibility_pointer_state"], "updated")

    def test_custom_manager_bootstrap_clock_failure_stays_prechild(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan_rel = "docs/plans/260712_1256_bootstrap_clock_failure.md"
            plan = root / plan_rel
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: bootstrap clock failure\n\n"
                "**Status:** Architect initial draft\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process",'
                '"required_manager_mode":"manager-custom-pipeline"}}\n'
                "```\n",
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "_planveyor_now_utc_iso() { return 1; } && "
                f"planveyor_manager_custom_pipeline_cmd run {plan_rel}",
            )

            self.assertEqual(result.returncode, 125, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["reason_code"], "receipt_seed_failed")
            self.assertEqual(self._codex_calls(log_dir), [])
            self.assertFalse((root / ".planveyor.manager_runs").exists())

    def test_custom_run_q_seeds_null_plan_before_queue_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan_rel = "docs/plans/260712_1257_queue_custom.md"
            self._write_custom_manager_plan(
                root,
                plan_rel,
                status="Ready for Coder",
            )

            result = self._run(
                root,
                env,
                f"planveyor_q_set {plan_rel} --for-manager-mode "
                "manager-custom-pipeline --json >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".planveyor.planpath").exists())
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            payload_text = str(calls[0]["argv"][-1])
            self.assertIn(f"PLAN_PATH={plan_rel}", payload_text)
            self.assertIn("MANAGER_QUEUE_DISCOVERY_JSON=", payload_text)
            receipt_path = Path(str(calls[0]["manager_invocation_receipt_path"]))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["command"], "run_q")
            self.assertIsNone(receipt["initial_plan"])
            self.assertEqual(receipt["active_plan"], plan_rel)
            self.assertEqual(receipt["final_plan"], plan_rel)
            self.assertEqual(receipt["queue_readback"]["active_plan"], plan_rel)
            self.assertEqual(receipt["state"], "completed")

    def test_custom_run_q_restamps_closeout_to_next_and_queue_complete(self) -> None:
        for transition in ("next_plan", "queue_complete"):
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as tmpdir:
                root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
                first_rel = f"docs/plans/260712_1257_{transition}_first.md"
                second_rel = f"docs/plans/260712_1257_{transition}_second.md"
                self._write_custom_manager_plan(root, first_rel, status="Done")
                plans = [first_rel]
                if transition == "next_plan":
                    self._write_custom_manager_plan(
                        root,
                        second_rel,
                        status="Ready for Coder",
                    )
                    plans.append(second_rel)
                env["PLANVEYOR_FAKE_MANAGER_QUEUE_ACTION"] = "closeout"

                result = self._run(
                    root,
                    env,
                    "planveyor_q_set "
                    + " ".join(shlex.quote(item) for item in plans)
                    + " --for-manager-mode manager-custom-pipeline --json >/dev/null && "
                    f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                    "planveyor_manager_custom_pipeline_cmd run Q",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                receipt_path = Path(
                    str(self._codex_calls(log_dir)[0]["manager_invocation_receipt_path"])
                )
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                transition_readback = receipt["queue_readback"]["last_transition"]
                self.assertEqual(transition_readback["finalized_plan"], first_rel)
                if transition == "next_plan":
                    self.assertEqual(receipt["active_plan"], second_rel)
                    self.assertEqual(receipt["final_plan"], second_rel)
                    self.assertEqual(receipt["queue_readback"]["active_plan"], second_rel)
                    self.assertEqual(receipt["queue_readback"]["effective_plan"], second_rel)
                    self.assertEqual(
                        receipt["closeout_state"]["status_line"],
                        "3:**Status:** Ready for Coder",
                    )
                else:
                    self.assertIsNone(receipt["active_plan"])
                    self.assertEqual(receipt["final_plan"], first_rel)
                    self.assertIsNone(receipt["queue_readback"]["effective_plan"])
                    self.assertTrue(receipt["queue_readback"]["queue_empty"])
                    self.assertTrue(transition_readback["queue_complete"])
                    self.assertEqual(
                        receipt["closeout_state"]["status_line"],
                        "3:**Status:** Done",
                    )
                self.assertEqual(receipt["state"], "completed")

    def test_custom_run_q_restamps_resume_parent_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            parent_rel = "docs/plans/260712_1257_resume_parent.md"
            child_rel = "docs/plans/260712_1257_resume_child.md"
            self._write_custom_manager_plan(root, child_rel, status="Done")
            self._write_custom_manager_plan(
                root,
                parent_rel,
                status="Ready for Coder",
                next_plans=[child_rel],
                execution_queue=[child_rel],
                resume_parent="run-parent-once",
            )
            env["PLANVEYOR_FAKE_MANAGER_QUEUE_ACTION"] = "closeout"

            result = self._run(
                root,
                env,
                f"planveyor_q_set --from-umbrella {parent_rel} "
                "--for-manager-mode manager-custom-pipeline --json >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_path = Path(
                str(self._codex_calls(log_dir)[0]["manager_invocation_receipt_path"])
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["active_plan"], parent_rel)
            self.assertEqual(receipt["final_plan"], parent_rel)
            self.assertIsNone(receipt["queue_readback"]["active_plan"])
            self.assertEqual(receipt["queue_readback"]["resume_parent_plan"], parent_rel)
            self.assertEqual(receipt["queue_readback"]["effective_plan"], parent_rel)
            self.assertEqual(
                receipt["queue_readback"]["last_transition"]["finalized_plan"],
                child_rel,
            )
            self.assertEqual(
                receipt["closeout_state"]["status_line"],
                "3:**Status:** Ready for Coder",
            )
            self.assertEqual(receipt["state"], "completed")

    def test_custom_run_q_accepts_advance_blocked_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            active_rel = "docs/plans/260712_1257_advance_blocked_active.md"
            prerequisite_rel = (
                "docs/plans/260712_1257_advance_blocked_collab_prerequisite.md"
            )
            dependent_rel = (
                "docs/plans/260712_1257_advance_blocked_custom_dependent.md"
            )
            self._write_custom_manager_plan(
                root,
                active_rel,
                status="Done",
                required_manager_mode="either",
            )
            self._write_custom_manager_plan(
                root,
                prerequisite_rel,
                status="Ready for Coder",
                required_manager_mode="manager-collab",
            )
            self._write_custom_manager_plan(
                root,
                dependent_rel,
                status="Ready for Coder",
                required_manager_mode="either",
                depends_on=[prerequisite_rel],
            )
            env["PLANVEYOR_FAKE_MANAGER_QUEUE_ACTION"] = "closeout"

            result = self._run(
                root,
                env,
                "planveyor_q_set "
                f"{active_rel} {prerequisite_rel} {dependent_rel} "
                "--for-manager-mode manager-collab --json >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_path = Path(
                str(self._codex_calls(log_dir)[0]["manager_invocation_receipt_path"])
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            blocker = (
                f"depends_on_skipped_incompatible: {dependent_rel} depends_on "
                f"{prerequisite_rel} state=skipped_manager_mode"
            )
            transition = receipt["queue_readback"]["last_transition"]
            self.assertEqual(receipt["state"], "completed")
            self.assertEqual(receipt["reason_code"], "manager_process_exited")
            self.assertIsNone(receipt["active_plan"])
            self.assertEqual(receipt["final_plan"], active_rel)
            self.assertFalse(receipt["queue_readback"]["queue_empty"])
            self.assertIsNone(receipt["queue_readback"]["effective_plan"])
            self.assertEqual(
                [item["state"] for item in receipt["queue_readback"]["items"]],
                ["done", "skipped_manager_mode", "pending"],
            )
            self.assertEqual(transition["kind"], "advance_blocked")
            self.assertEqual(transition["finalized_plan"], active_rel)
            self.assertFalse(transition["queue_complete"])
            self.assertIsNone(transition["next_plan"])
            self.assertIsNone(transition["resume_parent_plan"])
            self.assertEqual(transition["activation_blocker"], blocker)
            self.assertEqual(
                Path(receipt["oracle_readback"]["plan_path"]).resolve(),
                (root / active_rel).resolve(),
            )
            self.assertEqual(
                receipt["oracle_readback"]["status_line"],
                "3:**Status:** Done",
            )
            self.assertEqual(
                receipt["closeout_state"]["status_line"],
                "3:**Status:** Done",
            )

    def test_custom_run_q_advance_blocked_malformed_lineage_fails_closed(self) -> None:
        active_rel = "docs/plans/260712_1257_advance_blocked_malformed.md"
        dependent_rel = "docs/plans/260712_1257_advance_blocked_dependent.md"
        prerequisite_rel = "docs/plans/260712_1257_advance_blocked_prerequisite.md"
        blocker = (
            f"depends_on_skipped_incompatible: {dependent_rel} depends_on "
            f"{prerequisite_rel} state=skipped_manager_mode"
        )
        base_transition = {
            "kind": "advance_blocked",
            "finalized_plan": active_rel,
            "next_plan": None,
            "resume_parent_plan": None,
            "queue_complete": False,
            "activation_blocker": blocker,
        }
        variants = {
            "missing_blocker": {"activation_blocker": None},
            "blank_blocker": {"activation_blocker": ""},
            "wrong_blocker_type": {"activation_blocker": []},
            "wrong_blocker_shape": {
                "activation_blocker": "queue_dependency_blocked: pending"
            },
            "wrong_kind": {"kind": "advance"},
            "wrong_finalized_plan": {
                "finalized_plan": "docs/plans/foreign.md"
            },
            "queue_complete": {"queue_complete": True},
            "next_plan_present": {"next_plan": dependent_rel},
            "resume_parent_present": {"resume_parent_plan": dependent_rel},
        }
        for name, delta in variants.items():
            with self.subTest(variant=name), tempfile.TemporaryDirectory() as tmpdir:
                root, env, _ = self._prepare_repo(tmpdir, "default-repo")
                self._write_custom_manager_plan(root, active_rel, status="Done")
                transition = {**base_transition, **delta}
                malformed = json.dumps(
                    {
                        "exists": True,
                        "queue_empty": False,
                        "active_plan": None,
                        "resume_parent_plan": None,
                        "effective_plan": None,
                        "last_transition": transition,
                    },
                    sort_keys=True,
                )

                result = self._run(
                    root,
                    env,
                    f"planveyor_q_set {active_rel} "
                    "--for-manager-mode manager-custom-pipeline "
                    "--json >/dev/null && "
                    f"planveyor_session_set manager {FAKE_SID} runner=codex "
                    ">/dev/null && "
                    f"planveyor_q_show() {{ print -r -- {shlex.quote(malformed)}; }} && "
                    "planveyor_manager_custom_pipeline_cmd run Q",
                )

                self.assertEqual(result.returncode, 125, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["state"], "blocked")
                self.assertEqual(
                    receipt["reason_code"],
                    "terminal_readback_failed",
                )

    def test_custom_run_q_inconsistent_post_exit_lineage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, "default-repo")
            first_rel = "docs/plans/260712_1257_inconsistent_first.md"
            second_rel = "docs/plans/260712_1257_inconsistent_second.md"
            self._write_custom_manager_plan(root, first_rel, status="Done")
            self._write_custom_manager_plan(root, second_rel, status="Ready for Coder")
            env["PLANVEYOR_FAKE_MANAGER_QUEUE_ACTION"] = "closeout"
            inconsistent = json.dumps(
                {
                    "exists": True,
                    "queue_empty": False,
                    "active_plan": second_rel,
                    "resume_parent_plan": None,
                    "effective_plan": second_rel,
                    "last_transition": {
                        "finalized_plan": "docs/plans/foreign.md",
                        "next_plan": second_rel,
                        "resume_parent_plan": None,
                        "queue_complete": False,
                    },
                },
                sort_keys=True,
            )

            result = self._run(
                root,
                env,
                "planveyor_q_set "
                f"{first_rel} {second_rel} "
                "--for-manager-mode manager-custom-pipeline --json >/dev/null && "
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                f"planveyor_q_show() {{ print -r -- {shlex.quote(inconsistent)}; }} && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 125, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(receipt["reason_code"], "terminal_readback_failed")

    def test_custom_run_q_uninitialized_queue_keeps_null_plan_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")

            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".planveyor.planpath").exists())
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1, calls)
            payload_text = str(calls[0]["argv"][-1])
            payload_header = payload_text.split("[ALWAYS START]", 1)[0]
            self.assertNotIn("PLAN_PATH=", payload_header)
            receipt_path = Path(str(calls[0]["manager_invocation_receipt_path"]))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["command"], "run_q")
            self.assertIsNone(receipt["initial_plan"])
            self.assertIsNone(receipt["active_plan"])
            self.assertIsNone(receipt["final_plan"])
            self.assertFalse(receipt["queue_readback"]["exists"])
            self.assertTrue(receipt["queue_readback"]["queue_empty"])
            self.assertEqual(receipt["oracle_readback"]["state"], "not_applicable")
            self.assertEqual(receipt["state"], "completed")

    def test_custom_run_q_mode_rejection_terminalizes_seed_without_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan_rel = "docs/plans/260712_1258_queue_mode_rejected.md"
            plan = self._write_custom_manager_plan(
                root,
                plan_rel,
                status="Ready for Coder",
            )
            activated = self._run(
                root,
                env,
                f"planveyor_q_set {plan_rel} --for-manager-mode "
                "manager-custom-pipeline --json >/dev/null && "
                "planveyor_q_next_json --manager-mode manager-custom-pipeline >/dev/null",
            )
            self.assertEqual(activated.returncode, 0, activated.stderr)
            plan.write_text(
                plan.read_text(encoding="utf-8").replace(
                    "manager-custom-pipeline",
                    "manager-collab",
                ),
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd run Q",
            )

            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertEqual(self._codex_calls(log_dir), [])
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["command"], "run_q")
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(receipt["reason_code"], "manager_mode_rejected")
            self.assertEqual(
                receipt["queue_readback"]["closeout_kind"],
                "manager_mode_mismatch",
            )

    def test_custom_supervisor_revalidates_prompt_before_each_native_sink(self) -> None:
        fixture_scripts = FIXTURE_RUNTIME_SCRIPTS
        fixture_trees = FIXTURE_RUNTIME_DOCUMENT_TREES
        fixture_documents = FIXTURE_RUNTIME_DOCUMENTS

        def prepare(tmpdir: str) -> tuple[Path, dict[str, str], Path]:
            with mock.patch.object(
                sys.modules[__name__], "FIXTURE_RUNTIME_SCRIPTS", fixture_scripts
            ), mock.patch.object(
                sys.modules[__name__], "FIXTURE_RUNTIME_DOCUMENT_TREES", fixture_trees
            ), mock.patch.object(
                sys.modules[__name__], "FIXTURE_RUNTIME_DOCUMENTS", fixture_documents
            ):
                return self._prepare_repo(tmpdir, "default-repo")

        for surface in ("codex_exec", "codex_cli"):
            for mode in ("stable", "changed", "missing"):
                with self.subTest(surface=surface, mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                    root, env, log_dir = prepare(tmpdir)
                    plan_rel = f"docs/plans/260914_promptcheck_{surface}_{mode}.md"
                    self._write_custom_manager_plan(
                        root,
                        plan_rel,
                        status="Ready for Coder",
                    )
                    session = self._run(
                        root,
                        env,
                        f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null",
                    )
                    self.assertEqual(session.returncode, 0, session.stderr)
                    if surface == "codex_exec":
                        command = f"planveyor_manager_custom_pipeline_cmd run {plan_rel}"
                    else:
                        command = (
                            f"planveyor_plan_set {plan_rel} >/dev/null && "
                            "planveyor_manager_custom_pipeline_tui --no-alt-screen"
                        )

                    selected_prompt = root / "docs/tools/prompts/manager_custom_pipeline.md"
                    before_selected_prompt = selected_prompt.read_bytes()
                    binding_wrapper = textwrap.dedent(
                        f'''\
                        functions -c _planveyor_role_prompt_body _planveyor_promptcheck_real_prompt_body
                        _planveyor_role_prompt_body() {{
                          local rendered=""
                          rendered="$(_planveyor_promptcheck_real_prompt_body "$@")" || return $?
                          if [[ "$1" == manager && "$2" == custom_pipeline && ! -e "$PWD/.promptcheck-prepared-body" ]]; then
                            print -r -- "$rendered" > "$PWD/.promptcheck-prepared-body" || return 1
                            case {shlex.quote(mode)} in
                              changed) print -r -- '# changed selected prompt' > "$PWD/docs/tools/prompts/manager_custom_pipeline.md" || return 1 ;;
                              missing) rm -f -- "$PWD/docs/tools/prompts/manager_custom_pipeline.md" || return 1 ;;
                            esac
                            if [[ {shlex.quote(mode)} != stable ]]; then
                              : > "$PWD/.promptcheck-late-mutated" || return 1
                            fi
                          fi
                          print -r -- "$rendered"
                        }}
                        '''
                    )
                    result = self._run(
                        root,
                        env,
                        binding_wrapper
                        + command
                        + '; rc=$?; print -r -- "PWD_AFTER=$PWD" >&2; exit $rc',
                    )
                    pwd_lines = [
                        line
                        for line in result.stderr.splitlines()
                        if line.startswith("PWD_AFTER=")
                    ]
                    self.assertEqual(len(pwd_lines), 1, result.stderr)
                    self.assertEqual(
                        Path(pwd_lines[0].removeprefix("PWD_AFTER=")).resolve(),
                        root.resolve(),
                    )
                    calls = self._codex_calls(log_dir)
                    if mode == "stable":
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(len(calls), 1, calls)
                        prepared_body = (root / ".promptcheck-prepared-body").read_text(
                            encoding="utf-8"
                        ).removesuffix("\n")
                        # The retained fixture binds the same logical prompt body
                        # through two disposable consumer roots.  Provider forwarding
                        # preserves the body after shell command substitution removes
                        # its terminal newline; only fixture-specific absolute locator
                        # values may differ between the two render contexts.
                        def normalize_fixture_locators(body: str) -> str:
                            return re.sub(
                                r'"(?:physical_path|tooling_root)":"[^"]+"',
                                '"fixture_locator":"<fixture>"',
                                body,
                            )

                        self.assertIn(
                            normalize_fixture_locators(prepared_body),
                            normalize_fixture_locators(str(calls[0]["argv"][-1])),
                        )
                        continue

                    self.assertEqual(result.returncode, 125, result.stderr)
                    self.assertEqual(calls, [])
                    self.assertTrue((root / ".promptcheck-late-mutated").is_file())
                    if mode == "changed":
                        self.assertNotEqual(selected_prompt.read_bytes(), before_selected_prompt)
                    else:
                        self.assertFalse(selected_prompt.exists())
                    receipt = json.loads(result.stdout)
                    self.assertEqual(receipt["state"], "blocked")
                    self.assertEqual(
                        receipt["reason_code"], "prompt_body_binding_changed"
                    )
                    self.assertIsNone(receipt["manager_exit_code"])
                    self.assertEqual(receipt["stop_checkpoint_state"], "missing")
                    self.assertEqual(
                        receipt["compatibility_pointer_state"], "updated"
                    )


    def test_custom_manager_exit_and_checkpoint_failures_are_bounded(self) -> None:
        cases = (
            ("missing_checkpoint", "0", "1", 125, "blocked", "stop_checkpoint_missing"),
            ("failed_child", "17", "1", 17, "blocked", "manager_process_failed"),
            ("interrupted_child", "130", "0", 130, "interrupted", "manager_process_interrupted"),
        )
        for name, child_exit, skip_checkpoint, expected_rc, state, reason in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
                plan_rel = f"docs/plans/260712_1259_{name}.md"
                plan = root / plan_rel
                plan.parent.mkdir(parents=True, exist_ok=True)
                plan.write_text(
                    "# Plan: manager terminal fixture\n\n"
                    "**Status:** Architect initial draft\n\n"
                    "```json\n"
                    '{"plan_meta":{"cluster":"process",'
                    '"required_manager_mode":"manager-custom-pipeline"}}\n'
                    "```\n",
                    encoding="utf-8",
                )
                env["PLANVEYOR_FAKE_MANAGER_EXIT"] = child_exit
                env["PLANVEYOR_FAKE_MANAGER_SKIP_CHECKPOINT"] = skip_checkpoint

                result = self._run(
                    root,
                    env,
                    f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                    f"planveyor_manager_custom_pipeline_cmd run {plan_rel}",
                )

                self.assertEqual(result.returncode, expected_rc, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["state"], state)
                self.assertEqual(receipt["reason_code"], reason)
                self.assertEqual(
                    receipt["stop_checkpoint_state"],
                    "missing" if skip_checkpoint == "1" else "recorded",
                )
                self.assertEqual(len(self._codex_calls(log_dir)), 1)

    def test_custom_pointer_failure_blocks_exact_receipt_and_status_stays_outside_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, "default-repo")
            plan_rel = "docs/plans/260712_1258_pointer_failure.md"
            plan = root / plan_rel
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: pointer failure\n\n"
                "**Status:** Architect initial draft\n\n"
                "```json\n"
                '{"plan_meta":{"cluster":"process",'
                '"required_manager_mode":"manager-custom-pipeline"}}\n'
                "```\n",
                encoding="utf-8",
            )
            failing_sink = root / ".compatibility-receipt-sink"
            failing_sink.mkdir()
            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "_planveyor_run_receipt_path() { "
                "print -r -- \"$PWD/.compatibility-receipt-sink\"; } && "
                f"planveyor_manager_custom_pipeline_cmd run {plan_rel}",
            )

            self.assertEqual(result.returncode, 125, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["state"], "blocked")
            self.assertEqual(
                receipt["reason_code"],
                "compatibility_pointer_write_failed",
            )
            self.assertEqual(receipt["compatibility_pointer_state"], "write_failed")
            self.assertEqual(len(self._codex_calls(log_dir)), 1)
            self.assertTrue(failing_sink.is_dir())
            self.assertEqual(
                list(root.glob(f".{failing_sink.name}.tmp-*")),
                [],
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, "default-repo")
            result = self._run(
                root,
                env,
                f"planveyor_session_set manager {FAKE_SID} runner=codex >/dev/null && "
                "planveyor_manager_custom_pipeline_cmd status",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".planveyor.manager_runs").exists())


if __name__ == "__main__":
    unittest.main()

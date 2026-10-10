"""Static census for shell entrypoints that must capture contract authority.

This is deliberately an admission test, not a proof that shell control flow is
sound.  The runtime tests own disposable filesystem/provider sentinels.  Here
we make the static boundary reviewable: a retained or newly added public
surface either has the common-context prologue before any non-trivial command,
or remains a mechanically exact one-command delegate to a separately guarded
target.

The parser is intentionally small but does bind each function header to its
matching closing brace while ignoring comments, quoted text, and here-document
payloads.  A loose grep over a function body would let a late guard or a guard
mentioned in a here-document satisfy the check.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "scripts/test_data/contract_authority_surfaces.v1.json"

# Keep this generic so a private delegate target is bound to its real function
# body too.  Public-prefix filtering happens after parsing.
FUNCTION_HEADER = re.compile(
    r"(?m)^[ \t]*(?:function[ \t]+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"[ \t]*(?:\([ \t]*\))?[ \t]*\{"
)
OLD_PARENT_CONTEXT_TRUE = re.compile(
    r"_planveyor_authority_parent_context_json[^\n]*(?:\|\|[ \t]*true)"
)
FORBIDDEN_DELEGATE_SYNTAX = re.compile(
    r"(?:\$\(|`|[|;]|(?:^|\s)(?:source|eval|exec|if|case|for|while|until|function)(?:\s|$)|"
    r"(?:^|\s)\.(?:\s|$)|(?:^|\s)[A-Za-z_][A-Za-z0-9_]*=|<<|>>|[<>])"
)
FILE_TESTS = {"-e", "-a", "-b", "-c", "-d", "-f", "-g", "-h", "-k", "-L", "-O", "-p", "-r", "-s", "-S", "-u", "-w", "-x"}

# This exact argument-validation prefix only reads argv, updates function-local
# values/positionals, and emits Usage plus rc1 on malformed continuation input.
# It must precede authority capture so invalid grammar cannot reach live effects.
# Any prefix edit requires a fresh proof review; the capture and readonly caller
# bindings below it still pass the ordinary admission checks.
MANAGER_CONTINUATION_PREFIX_PAIR = (
    "scripts/planveyor/role_runtime.zsh", "planveyor_manager_collab_cmd"
)
MANAGER_CONTINUATION_PREFIX_SHA256 = "dc1573f3f327fd564fc447722086fe4463f54d05e11af2e3827e62e7737c9f85"


@dataclass(frozen=True)
class ShellFunction:
    """A source-backed shell function with byte offsets into its file."""

    source_path: str
    name: str
    source: str
    code_mask: str
    opening_brace: int
    closing_brace: int

    @property
    def body(self) -> str:
        return self.source[self.opening_brace + 1 : self.closing_brace]

    @property
    def masked_body(self) -> str:
        return self.code_mask[self.opening_brace + 1 : self.closing_brace]

    @property
    def line(self) -> int:
        return self.source.count("\n", 0, self.opening_brace) + 1

    def line_at_body_offset(self, offset: int) -> int:
        return self.source.count("\n", 0, self.opening_brace + 1 + offset) + 1


@dataclass(frozen=True)
class ParsedSources:
    by_pair: dict[tuple[str, str], ShellFunction]
    by_name: dict[str, tuple[ShellFunction, ...]]


def _blank_non_newlines(buffer: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if buffer[index] != "\n":
            buffer[index] = " "


def _quoted_end(source: str, start: int, quote: str) -> int:
    """Return the first offset after a shell quote, retaining newlines later."""

    index = start + 1
    while index < len(source):
        if quote != "'" and source[index] == "\\":
            index += 2
            continue
        if source[index] == quote:
            return index + 1
        index += 1
    return len(source)


def _heredoc_operator(source: str, start: int) -> tuple[int, str, bool] | None:
    """Parse a simple shell here-document operator at ``start``.

    Shell sources in this repository use named delimiters (usually ``PY``),
    optionally quoted or tab-stripping.  An unsupported/dynamic delimiter is
    left in code rather than guessed, so it cannot hide a brace from the
    parser.
    """

    if source.startswith("<<<", start):
        return None
    index = start + 2
    strip_tabs = False
    if index < len(source) and source[index] == "-":
        strip_tabs = True
        index += 1
    while index < len(source) and source[index] in " \t":
        index += 1
    if index >= len(source) or source[index] in "\r\n":
        return None
    if source[index] in "'\"":
        quote = source[index]
        end = _quoted_end(source, index, quote)
        if end == len(source) or end <= index + 1:
            return None
        return end, source[index + 1 : end - 1], strip_tabs
    if source[index] == "\\":
        index += 1
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", source[index:])
    if match is None:
        return None
    end = index + match.end()
    return end, match.group(0), strip_tabs


def _starts_shell_comment(source: str, index: int) -> bool:
    """Recognise a shell comment without mistaking ``${#name}`` for one."""

    if index == 0:
        return True
    return source[index - 1].isspace() or source[index - 1] in ";|&()"


def shell_code_mask(source: str, *, mask_quotes: bool = True) -> str:
    """Mask shell comments and here-doc payloads without moving text.

    ``mask_quotes=True`` makes it a structural parser mask for brace matching.
    ``False`` preserves quoted command syntax while still excluding comments
    and here-doc payloads from admission assertions.  Both results retain the
    source's offsets and newline layout.
    """

    masked = list(source)
    pending_heredocs: list[tuple[str, bool]] = []
    new_heredocs: list[tuple[str, bool]] = []
    index = 0
    line_start = True
    length = len(source)

    while index < length:
        if line_start and pending_heredocs:
            line_end = source.find("\n", index)
            if line_end < 0:
                line_end = length
            delimiter, strip_tabs = pending_heredocs[0]
            candidate = source[index:line_end]
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            _blank_non_newlines(masked, index, line_end)
            if candidate == delimiter:
                pending_heredocs.pop(0)
            index = line_end
            if index < length:
                index += 1
            line_start = True
            continue

        char = source[index]
        if char == "\n":
            if new_heredocs:
                pending_heredocs.extend(new_heredocs)
                new_heredocs.clear()
            line_start = True
            index += 1
            continue
        line_start = False
        if char == "#" and _starts_shell_comment(source, index):
            line_end = source.find("\n", index)
            if line_end < 0:
                line_end = length
            _blank_non_newlines(masked, index, line_end)
            index = line_end
            continue
        if char in "'\"`":
            end = _quoted_end(source, index, char)
            if mask_quotes:
                _blank_non_newlines(masked, index, end)
            index = end
            continue
        if char == "\\":
            # A quoted newline cannot start a comment or quote on this pass.
            index += 2
            continue
        if source.startswith("<<<", index):
            # Consume the complete here-string operator.  Advancing one byte
            # would revisit its second '<' as a false here-document opener.
            index += 3
            continue
        if source.startswith("<<", index):
            parsed = _heredoc_operator(source, index)
            if parsed is not None:
                end, delimiter, strip_tabs = parsed
                new_heredocs.append((delimiter, strip_tabs))
                index = end
                continue
        index += 1

    return "".join(masked)


def _matching_brace(code_mask: str, opening_brace: int) -> int:
    depth = 0
    for index in range(opening_brace, len(code_mask)):
        char = code_mask[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
    raise ValueError(f"unclosed shell function body at byte {opening_brace}")


def parse_shell_functions(source_path: str, source: str) -> dict[str, ShellFunction]:
    """Return top-level function definitions with their exact bounded bodies."""

    code_mask = shell_code_mask(source)
    functions: dict[str, ShellFunction] = {}
    consumed_through = 0
    for match in FUNCTION_HEADER.finditer(code_mask):
        if match.start() < consumed_through:
            # A real nested definition and a function-looking example inside a
            # body are both outside this entrypoint census.
            continue
        name = match.group("name")
        opening_brace = code_mask.rfind("{", match.start(), match.end())
        closing_brace = _matching_brace(code_mask, opening_brace)
        if name in functions:
            raise ValueError(f"duplicate function definition: {source_path}:{name}")
        functions[name] = ShellFunction(
            source_path=source_path,
            name=name,
            source=source,
            code_mask=code_mask,
            opening_brace=opening_brace,
            closing_brace=closing_brace,
        )
        consumed_through = closing_brace + 1
    return functions


def parse_sources(source_paths: list[str]) -> ParsedSources:
    by_pair: dict[tuple[str, str], ShellFunction] = {}
    mutable_by_name: dict[str, list[ShellFunction]] = {}
    for source_path in source_paths:
        source = (ROOT / source_path).read_text(encoding="utf-8")
        for name, function in parse_shell_functions(source_path, source).items():
            pair = (source_path, name)
            if pair in by_pair:
                raise ValueError(f"duplicate source pair: {source_path}:{name}")
            by_pair[pair] = function
            mutable_by_name.setdefault(name, []).append(function)
    return ParsedSources(by_pair=by_pair, by_name={name: tuple(items) for name, items in mutable_by_name.items()})


def _normalise_statement(value: str) -> str:
    return " ".join(value.strip().split())


def _pure_delegate_statement(function: ShellFunction) -> str:
    """Return the one executable statement, excluding prose and a terminator."""

    executable_lines = [
        line.strip()
        for line in function.body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    statement = _normalise_statement(" ".join(executable_lines))
    # `name() { target "$@"; }` has one command; the semicolon is the
    # function-body terminator, not a second statement.
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    return statement


def _safe_local_declaration(raw: str, code: str) -> bool:
    if not re.match(r"^(?:local|typeset)\b", code):
        return False
    if re.match(r"^(?:local|typeset)\b[^\n]*\s-[A-Za-z]*g", code):
        return False
    if re.search(r"(?:\$\(|`|<\(|>\(|<<|>>|[<>]|\|)", raw):
        return False
    # Local declarations can shape positional values before admission.  A
    # command substitution, redirect, pipeline, or global declaration remains
    # an observable boundary and is rejected above.
    return True


def _safe_test_expression(raw: str, code: str) -> bool:
    candidate = code.strip()
    if candidate.startswith("if "):
        candidate = candidate[3:].strip()
    elif candidate.startswith("elif "):
        candidate = candidate[5:].strip()
    candidate = re.sub(r";[ \t]*then[ \t]*$", "", candidate)
    candidate = re.sub(r"\|\|[ \t]*return(?:[ \t]+[0-9]+)?[ \t]*$", "", candidate)
    if not (candidate.startswith("[[") or candidate.startswith("((")):
        return False
    raw_without_early_return = re.sub(r"\|\|[ \t]*return(?:[ \t]+(?:\$\?|[0-9]+))?[ \t]*$", "", raw)
    if re.search(r"(?:\$\(|`|<\(|>\(|<<|>>|[<>]|\|)", raw_without_early_return):
        return False
    if any(token in raw.split() for token in FILE_TESTS):
        return False
    # A `[[ -n "${argument//...}" ]]` check only examines already-local
    # shell values.  It is allowed before capture; command substitutions and
    # filesystem predicates above remain first-effect anchors.
    return True


def _is_harmless_pre_guard_line(raw: str, code: str) -> bool:
    """Recognise the deliberately narrow, effect-free prologue vocabulary."""

    candidate = code.strip()
    if not candidate:
        return True
    if re.fullmatch(r"emulate[ \t]+-L[ \t]+zsh", candidate):
        return True
    if _safe_local_declaration(raw.strip(), candidate):
        return True
    if _safe_test_expression(raw.strip(), candidate):
        return True
    if candidate in {"then", "else", "fi", "do", "done", "esac", ";;", ";&", ";;&", ")"}:
        return True
    if re.fullmatch(r"[^;()]+\)[ \t]*;;", candidate):
        # An empty case arm only participates in positional/argument routing.
        return True
    if re.fullmatch(r"[^;()]+\)", candidate):
        return True
    if re.fullmatch(r"(?:return(?:[ \t]+[0-9]+)?|shift(?:[ \t]+[0-9]+)?|:|true|false)", candidate):
        return True
    if candidate.startswith("case ") and candidate.endswith(" in"):
        return not re.search(r"(?:\$\(|`|<\(|>\(|<<|>>|[<>]|\|)", raw)
    return False


def first_unsafe_pre_guard_line(function: ShellFunction, guard_start: int) -> tuple[int, str] | None:
    """Return the first non-trivial pre-capture source line, if any."""

    raw_prefix = function.body[:guard_start]
    if (
        (function.source_path, function.name) == MANAGER_CONTINUATION_PREFIX_PAIR
        and hashlib.sha256(raw_prefix.encode("utf-8")).hexdigest() == MANAGER_CONTINUATION_PREFIX_SHA256
    ):
        return None
    code_prefix = shell_code_mask(raw_prefix)
    raw_lines = raw_prefix.splitlines()
    code_lines = code_prefix.splitlines()
    for index, (raw, code) in enumerate(zip(raw_lines, code_lines)):
        if _is_harmless_pre_guard_line(raw, code):
            continue
        return function.line_at_body_offset(sum(len(item) + 1 for item in raw_lines[:index])), raw.strip()
    return None


def _guard_capture(
    function: ShellFunction,
    guard_api: str,
) -> re.Match[str] | None:
    name = re.escape(function.name)
    api = re.escape(guard_api)
    api_arguments = rf"[ \t]+(?:[\"']{name}[\"']|{name})(?=[ \t)])[^\n]*?\)"
    pattern = re.compile(
        rf"""(?mx)
        ^[ \t]*(?:local[ \t]+)?
        (?P<variable>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(?:[\"'])?
        \$\([ \t]*{api}{api_arguments}(?:[\"'])?
        [ \t]*\|\|[ \t]*return(?:[ \t]+(?:\$\?|[0-9]+))?[ \t]*(?:\#.*)?$
        """
    )
    # A here-document may contain an example prologue.  It cannot satisfy the
    # actual function's admission check.
    return pattern.search(shell_code_mask(function.body, mask_quotes=False))


def missing_readonly_context_locals(
    function: ShellFunction,
    guard: re.Match[str],
    required: list[str],
    *,
    require_same_capture_bindings: bool = False,
) -> list[str]:
    """Check that a successful capture becomes caller-owned readonly state."""

    tail = shell_code_mask(function.body[guard.end() :], mask_quotes=False)
    capture_variable = re.escape(guard.group("variable"))
    expected_values = {
        "PLANVEYOR_CTX_SEAL": r"(?:'planveyor-contract-context\.v1'|\"planveyor-contract-context\.v1\")",
        "PLANVEYOR_CTX_ROOT": r"[\"']?\$_planveyor_ctx_root[\"']?",
        "PLANVEYOR_CTX_GENERATION": r"[\"']?\$_planveyor_ctx_generation[\"']?",
        "PLANVEYOR_CTX_STATE": r"[\"']?\$_planveyor_ctx_state[\"']?",
        "PLANVEYOR_CTX_JSON": rf"[\"']?\${capture_variable}[\"']?",
    }
    missing: list[str] = []
    for local_name in required:
        base = rf"(?m)^[ \t]*local[ \t]+-[A-Za-z]*r[A-Za-z]*[ \t]+{re.escape(local_name)}="
        if re.search(base, tail) is None:
            missing.append(local_name)
            continue
        expected_value = expected_values.get(local_name) if require_same_capture_bindings else None
        if local_name == "PLANVEYOR_CTX_JSON":
            expected_value = expected_values[local_name]
        if expected_value is not None:
            bound = rf"(?m)^[ \t]*local[ \t]+-[A-Za-z]*r[A-Za-z]*[ \t]+{re.escape(local_name)}={expected_value}[ \t]*(?:\#.*)?$"
            if re.search(bound, tail) is None:
                missing.append(local_name)
    return missing


class ShellParserTests(unittest.TestCase):
    def test_parser_binds_a_function_body_across_heredoc_braces(self) -> None:
        source = """\
sample() {
  cat <<'PY'
}
looks_like_a_function() {
PY
  read -r selected <<< "$value"
  print -r -- done
}
after() { print -r -- after; }
"""
        functions = parse_shell_functions("fixture.zsh", source)
        self.assertEqual(set(functions), {"sample", "after"})
        self.assertIn("print -r -- done", functions["sample"].body)
        self.assertEqual(_normalise_statement(functions["after"].body), "print -r -- after;")

    def test_parser_ignores_braces_in_comments_and_quotes(self) -> None:
        source = """\
first() {
  # }
  local count=${#value}
  print -r -- "}"
}
second() { :; }
"""
        functions = parse_shell_functions("fixture.zsh", source)
        self.assertEqual(set(functions), {"first", "second"})

    def test_pre_guard_command_substitution_is_not_effect_free(self) -> None:
        source = """\
sample() {
  emulate -L zsh
  local root="$(_planveyor_root)"
  ctx="$(_planveyor_authority_context_for_reader sample)" || return $?
}
"""
        function = parse_shell_functions("fixture.zsh", source)["sample"]
        guard = _guard_capture(function, "_planveyor_authority_context_for_reader")
        self.assertIsNotNone(guard)
        unsafe = first_unsafe_pre_guard_line(function, guard.start())
        self.assertEqual(unsafe, (3, 'local root="$(_planveyor_root)"'))

    def test_guard_example_inside_a_heredoc_is_not_a_capture(self) -> None:
        source = """\
sample() {
  cat <<'EXAMPLE'
ctx="$(_planveyor_authority_context_for_reader sample)" || return $?
EXAMPLE
  print -r -- no-guard-ran
}
"""
        function = parse_shell_functions("fixture.zsh", source)["sample"]
        self.assertIsNone(_guard_capture(function, "_planveyor_authority_context_for_reader"))


class ContractAuthoritySurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.admission = cls.manifest["admission"]
        cls.public_by_file = cls.manifest["public_by_file"]
        cls.internal_sinks = cls.manifest["internal_sinks"]
        cls.approved_guard_api_exceptions = cls.manifest["approved_guard_api_exceptions"]
        cls.pure_delegates = cls.manifest["pure_delegates"]
        cls.reclassified_public = set(cls.admission["guarded_public_reclassifications"])
        cls.active_pure_delegates = {
            name: record for name, record in cls.pure_delegates.items() if name not in cls.reclassified_public
        }
        cls.sources = sorted(
            set(cls.public_by_file)
            | set(cls.internal_sinks.values())
            | {record["file"] for record in cls.approved_guard_api_exceptions.values()}
        )
        cls.parsed = parse_sources(cls.sources)

    def _public_pairs(self) -> set[tuple[str, str]]:
        return {(source_path, name) for source_path, names in self.public_by_file.items() for name in names}

    def _function_for_pair(self, source_path: str, name: str) -> ShellFunction:
        try:
            return self.parsed.by_pair[(source_path, name)]
        except KeyError as error:
            self.fail(f"{source_path}: missing bounded function definition for {name}")
            raise AssertionError from error

    def _assert_guarded(self, function: ShellFunction) -> None:
        guard = _guard_capture(function, self.admission["guard_api"])
        if guard is None:
            self.fail(
                f"{function.source_path}:{function.line}: {function.name}: missing literal "
                f"{self.admission['guard_api']} {function.name} capture with || return"
            )
        assert guard is not None
        old_parent = OLD_PARENT_CONTEXT_TRUE.search(shell_code_mask(function.body[: guard.start()], mask_quotes=False))
        if old_parent is not None:
            self.fail(
                f"{function.source_path}:{function.line_at_body_offset(old_parent.start())}: {function.name}: "
                "old parent-context `|| true` prologue is disallowed; capture the current reader context"
            )
        unsafe = first_unsafe_pre_guard_line(function, guard.start())
        if unsafe is not None:
            line, statement = unsafe
            self.fail(
                f"{function.source_path}:{line}: {function.name}: pre-capture statement is not an approved "
                f"effect-free declaration or argument check: {statement!r}"
            )
        missing = missing_readonly_context_locals(function, guard, self.admission["readonly_context_locals"])
        if missing:
            self.fail(
                f"{function.source_path}:{function.line_at_body_offset(guard.start())}: {function.name}: "
                f"capture must bind readonly caller context locals; missing {', '.join(missing)}"
            )

    def _assert_exact_pure_delegate(self, name: str, record: dict[str, str]) -> ShellFunction:
        function = self._function_for_pair(record["file"], name)
        actual = _pure_delegate_statement(function)
        expected = _normalise_statement(record["statement"])
        self.assertEqual(
            actual,
            expected,
            f"{function.source_path}:{function.line}: {name}: a pure delegate must retain its exact one-command proof",
        )
        self.assertFalse(
            FORBIDDEN_DELEGATE_SYNTAX.search(actual),
            f"{function.source_path}:{function.line}: {name}: pure delegate has assignment, redirection, pipeline, "
            "command substitution, source/eval/exec, or control flow",
        )
        first_command = actual.split(maxsplit=1)[0] if actual else ""
        self.assertEqual(
            first_command,
            record["target"],
            f"{function.source_path}:{function.line}: {name}: delegate target must remain the first command",
        )
        return function

    def test_manifest_is_a_closed_no_exemption_baseline(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertNotIn("baseline_commit", self.manifest)
        self.assertEqual(sum(len(names) for names in self.public_by_file.values()), 219)
        self.assertEqual(len(self._public_pairs()), 219)
        self.assertIn(("scripts/planveyor.zsh", "planveyor_sibling"), self._public_pairs())
        self.assertEqual(self.admission["baseline_internal_sink_count"], 40)
        self.assertEqual(
            len(self.internal_sinks),
            39,
            "the two retired UI sinks are no longer census-owned",
        )
        self.assertEqual(len(self.pure_delegates), 52)
        self.assertFalse(
            set(self.pure_delegates) - {name for _, name in self._public_pairs()},
            "a pure-delegate proof must belong to a retained public surface",
        )
        self.assertFalse(
            self.reclassified_public - set(self.pure_delegates),
            "a guarded reclassification must name a baseline pure-delegate proof",
        )
        self.assertNotIn("legacy_only", json.dumps(self.manifest, sort_keys=True))
        self.assertEqual(
            self.admission["guard_api"], "_planveyor_authority_context_for_reader",
            "public and ordinary internal owners use the common reader context capture",
        )
        self.assertEqual(
            self.approved_guard_api_exceptions,
            {},
            "no removed destination-owner exceptions remain",
        )
        self.assertFalse(
            set(self.approved_guard_api_exceptions) & {name for _, name in self._public_pairs()},
            "public entrypoints must retain their standard reader A prologue",
        )

    def test_every_baseline_name_file_pair_remains_defined(self) -> None:
        expected = self._public_pairs()
        missing = sorted(expected - set(self.parsed.by_pair))
        self.assertFalse(missing, f"baseline public name/file pair removed or moved: {missing}")

    def test_every_current_public_prefix_is_explicitly_classified(self) -> None:
        prefixes = tuple(self.admission["allowed_public_prefixes"])
        current = {pair for pair in self.parsed.by_pair if pair[1].startswith(prefixes)}
        expected = self._public_pairs()
        unexpected = sorted(current - expected)
        self.assertFalse(
            unexpected,
            "new public function has no admission classification; add its name/file to public_by_file and either "
            "make it guarded or provide an exact pure_delegates proof: " + repr(unexpected),
        )

    def test_every_nonalias_public_surface_and_named_internal_sink_is_guarded_before_effects(self) -> None:
        public_pairs = self._public_pairs()
        guarded_public = sorted(
            pair for pair in public_pairs
            if pair[1] not in self.active_pure_delegates
        )
        guarded_internal = {(source_path, name) for name, source_path in self.internal_sinks.items()}
        for source_path, name in [*guarded_public, *sorted(guarded_internal)]:
            with self.subTest(source_path=source_path, name=name):
                self._assert_guarded(self._function_for_pair(source_path, name))

    def test_manager_continuation_prefix_rejects_added_or_changed_effects(self) -> None:
        function = self._function_for_pair(*MANAGER_CONTINUATION_PREFIX_PAIR)
        guard = _guard_capture(function, self.admission["guard_api"])
        assert guard is not None
        prefix, tail = function.body[:guard.start()], function.body[guard.start():]
        mutations = {
            "before_prefix": '  touch session-sentinel\n' + prefix,
            "after_prefix": prefix + '  planveyor_plan_set docs/plans/sentinel.md\n',
            "in_scan_loop": prefix.replace(
                '  for continuation_arg in "$@"; do\n',
                '  for continuation_arg in "$@"; do\n    _planveyor_codex provider-sentinel\n',
            ),
            "in_refusal_branch": prefix.replace(
                '      echo "Usage:', '      touch queue-sentinel\n      echo "Usage:',
            ),
            "declaration_substitution": prefix.replace(
                'local continuation_cycle_id=""', 'local continuation_cycle_id="$(touch substitution-sentinel)"',
            ),
            "global_assignment": prefix.replace(
                '    continuation_cycle_id="$4"', '    typeset -g continuation_cycle_id="$4"',
            ),
        }
        for label, mutated_prefix in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(mutated_prefix, prefix)
                source = f"{function.name}() {{{mutated_prefix}{tail}}}"
                mutated = parse_shell_functions(function.source_path, source)[function.name]
                with self.assertRaisesRegex(AssertionError, "pre-capture statement"):
                    self._assert_guarded(mutated)

    def test_manager_continuation_prefix_does_not_exempt_capture_or_bindings(self) -> None:
        function = self._function_for_pair(*MANAGER_CONTINUATION_PREFIX_PAIR)
        mutations = {
            "missing_capture": function.body.replace(
                "_planveyor_authority_context_for_reader planveyor_manager_collab_cmd", "unapproved_reader_call",
            ),
            "missing_readonly_binding": function.body.replace(
                'local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"', 'local PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"',
            ),
        }
        for label, body in mutations.items():
            with self.subTest(mutation=label):
                source = f"{function.name}() {{{body}}}"
                mutated = parse_shell_functions(function.source_path, source)[function.name]
                with self.assertRaises(AssertionError):
                    self._assert_guarded(mutated)
        other_file = parse_shell_functions(
            "scripts/unapproved_surface.zsh", f"{function.name}() {{{function.body}}}"
        )[function.name]
        with self.assertRaisesRegex(AssertionError, "pre-capture statement"):
            self._assert_guarded(other_file)
        other_name = "unapproved_manager_reader"
        other_body = function.body.replace(
            f"{self.admission['guard_api']} {function.name}", f"{self.admission['guard_api']} {other_name}"
        )
        other_function = parse_shell_functions(
            function.source_path, f"{other_name}() {{{other_body}}}"
        )[other_name]
        with self.assertRaisesRegex(AssertionError, "pre-capture statement"):
            self._assert_guarded(other_function)


    def test_pure_delegates_remain_exact_and_resolve_to_a_guarded_terminal(self) -> None:
        terminals = {
            name
            for source_path, name in self._public_pairs()
            if name not in self.active_pure_delegates
        } | set(self.internal_sinks)

        def resolve(name: str, chain: tuple[str, ...] = ()) -> str:
            if name in chain:
                self.fail("pure delegate cycle: " + " -> ".join([*chain, name]))
            record = self.active_pure_delegates.get(name)
            if record is None:
                self.assertIn(name, terminals, f"delegate target {name!r} is neither guarded nor an exact delegate")
                functions = self.parsed.by_name.get(name, ())
                self.assertEqual(len(functions), 1, f"delegate target {name!r} must resolve to one bounded function")
                return name
            self._assert_exact_pure_delegate(name, record)
            return resolve(record["target"], (*chain, name))

        for name, record in sorted(self.active_pure_delegates.items()):
            with self.subTest(name=name):
                self._assert_exact_pure_delegate(name, record)
                resolve(record["target"], (name,))


if __name__ == "__main__":
    unittest.main()

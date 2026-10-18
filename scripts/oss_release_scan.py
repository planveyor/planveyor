#!/usr/bin/env python3
from __future__ import annotations

"""Read-only public safety scanner for tracked OSS release inputs."""

import argparse
import ast
from bisect import bisect_right
from dataclasses import asdict, dataclass
import json
import keyword
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata
from typing import Iterable, Sequence


SCOPES = ("keep-set", "public-copy", "evidence", "all")
FORMATS = ("text", "json")
FAIL_LEVELS = ("blocker", "warning", "never")
SEVERITY_RANK = {"warning": 1, "blocker": 2}
MARKER_ENV = "PLANVEYOR_OSS_SCAN_MARKERS"
MASKED_TOKEN = "<masked>"
SANCTIONED_SECURITY_CONTACT = "security" + "@" + "planveyor.dev"
SECURITY_CONTACT_PATHS = frozenset({"SECURITY.md", "SECURITY.ru.md"})

HISTORICAL_DIRS = {
    "docs/plans",
    "docs/code_drafts",
    "docs/code_reviews",
    "docs/doc_reviews",
    "docs/reviews",
    "docs/followups",
    "docs/snapshots",
    "docs/rollout_packets",
    "docs/upstream_packets",
    "docs/process_improvements",
    "docs/_meta/archive_snapshots",
}
EVIDENCE_DIRS = HISTORICAL_DIRS
ARCHIVE_CATEGORIES = frozenset(
    {
        "plans",
        "code_drafts",
        "code_reviews",
        "doc_reviews",
        "followups",
        "canon_notes",
    }
)

# Kept as a module API for portability verifiers. It matches concrete macOS,
# Unix, and Windows user-home roots while excluding the documented ellipsis form.
PERSONAL_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:/(?:Users|home)/(?!\.\.\.)(?:[A-Za-z0-9][A-Za-z0-9._-]*)|"
    r"[A-Za-z]:[\\/]+Users[\\/]+(?!\.\.\.)(?:[A-Za-z0-9][A-Za-z0-9._-]*))"
)
GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{8,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
SLACK_TOKEN_RE = re.compile(r"(?i)\bxox(?:[abpors]-[A-Za-z0-9-]{10,})\b")
EMAIL_RE = re.compile(r"(?i)\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}\b")
PHONE_RE = re.compile(
    r"(?:(?<![A-Za-z0-9])(?:\+\d{1,3}[ -]\d{2,4}[ -]\d{2,4}[ -]\d{2}[ -]\d{2}|"
    r"\+\d{1,3}[ -]\d{2,4}[ -]\d{2,4}[ -]\d{3,4}|\(\d{2,4}\)[ -]\d{2,4}[ -]\d{3,4})(?![A-Za-z0-9])|"
    r"(?<![A-Za-z0-9_-])(?:\d{1,3}[ -]\d{2,4}[ -]\d{2,4}[ -]\d{2}[ -]\d{2}|"
    r"\d{1,3}[ -]\d{2,4}[ -]\d{2,4}[ -]\d{3,4})(?![A-Za-z0-9_-]))"
)
IP_ADDRESS_RE = re.compile(r"\b(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})(?:\.(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}\b")
VERSION_CONTEXT_BEFORE_IP_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])version[ \t]+$")
INTERNAL_HOSTNAME_RE = re.compile(
    r"(?i)\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+(?:internal|corp|lan)\b"
)
URL_CREDENTIALS_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]*:[^\s/@]+@[^\s/]+")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])(?:(?:[A-Za-z_][A-Za-z0-9]*[_-]+))*"
    r"(?:api[_-]?(?:key|token)|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"private[_-]?key|secret|password|token)(?![A-Za-z0-9_-])\s*[:=]\s*[\"']?([A-Za-z0-9_./+=-]{12,})"
)
SECRET_TOKEN_RE = re.compile(
    r"(?:\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16})\b|"
    r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-]))"
)
THIRD_PARTY_DUMP_PATTERNS = (
    re.compile(r"third[- ]party.{0,40}prompt.{0,40}dump", re.I),
    re.compile(r"BEGIN THIRD[- ]PARTY PROMPT", re.I),
    re.compile(r"<!--\s*Source:\s*/[^>]+-->", re.I),
)
THIRD_PARTY_SOURCE_RE = re.compile(r"(?:^|/)docs/reviews/sources(?:/|$)", re.I)
LEGAL_ATTRIBUTION_RE = re.compile(r"(?i)^\s*(?:copyright(?:\s*\(?c\)?)?|license[ _-]?holder|licensor)\b")

GENERIC_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("personal_path", PERSONAL_PATH_RE),
    ("github_token", GITHUB_TOKEN_RE),
    ("private_key", PRIVATE_KEY_RE),
    ("bearer_token", BEARER_TOKEN_RE),
    ("bearer_token", JWT_RE),
    ("slack_token", SLACK_TOKEN_RE),
    ("email", EMAIL_RE),
    ("phone", PHONE_RE),
    ("ip_address", IP_ADDRESS_RE),
    ("internal_hostname", INTERNAL_HOSTNAME_RE),
    ("url_credentials", URL_CREDENTIALS_RE),
    ("secret_like", SECRET_ASSIGNMENT_RE),
    ("secret_like", SECRET_TOKEN_RE),
)


class ScanInputError(RuntimeError):
    """A fail-closed scanner input or configuration error."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    category: str
    severity: str
    token: str


@dataclass(frozen=True)
class MarkerRule:
    category: str
    pattern: re.Pattern[str]
    author_literal: str | None = None


ZERO_WIDTH_POINTS = frozenset("\u200b\u200c\u200d\u2060\ufeff")
ASCII_CASE_PAIR_RE = re.compile(r"\[([A-Za-z])([A-Za-z])\]")
STRING_OPEN_RE = re.compile(r'''(?i)([rubf]{0,2})("""|\x27\x27\x27|"|\x27)''')


@dataclass(frozen=True)
class _SourceView:
    text: str
    spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class _StringPart:
    kind: str
    start: int
    end: int
    view: _SourceView | None = None


def _canonical_literal(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value) if char not in ZERO_WIDTH_POINTS)


def _join_views(parts: Sequence[_SourceView]) -> _SourceView:
    return _SourceView("".join(part.text for part in parts), tuple(span for part in parts for span in part.spans))


def _canonical_view(view: _SourceView) -> _SourceView:
    # NFKD first exposes both compatibility expansions and combining marks.
    # Canonical ordering and NFC composition then retain every contributor.
    decomposed: list[tuple[str, tuple[int, int]]] = []
    marks: list[tuple[str, tuple[int, int]]] = []
    for char, span in zip(view.text, view.spans):
        for piece in unicodedata.normalize("NFKD", char):
            if unicodedata.combining(piece):
                marks.append((piece, span))
            else:
                decomposed.extend(sorted(marks, key=lambda item: unicodedata.combining(item[0])))
                marks = []
                decomposed.append((piece, span))
    decomposed.extend(sorted(marks, key=lambda item: unicodedata.combining(item[0])))
    composed: list[tuple[str, tuple[int, int]]] = []
    starter: int | None = None
    last_class = 0
    for char, span in decomposed:
        char_class = unicodedata.combining(char)
        if starter is not None and (last_class < char_class or last_class == 0):
            old, old_span = composed[starter]
            combined = unicodedata.normalize("NFC", old + char)
            if len(combined) == 1:
                composed[starter] = (combined, (min(old_span[0], span[0]), max(old_span[1], span[1])))
                continue
        if char_class == 0:
            starter = len(composed)
        composed.append((char, span))
        last_class = char_class
    if "".join(char for char, _ in composed) != unicodedata.normalize("NFKC", view.text):
        raise ScanInputError("scanner input is invalid")
    filtered = [(char, span) for char, span in composed if char not in ZERO_WIDTH_POINTS]
    text = "".join(char for char, _ in filtered)
    result: list[tuple[str, tuple[int, int]]] = []
    cursor = 0
    while cursor < len(text):
        pair = ASCII_CASE_PAIR_RE.match(text, cursor)
        if pair and pair[1] != pair[2] and pair[1].lower() == pair[2].lower():
            spans = [span for _, span in filtered[cursor : pair.end()]]
            result.append((pair[1].lower(), (min(start for start, _ in spans), max(end for _, end in spans))))
            cursor = pair.end()
        else:
            result.append(filtered[cursor])
            cursor += 1
    return _SourceView("".join(char for char, _ in result), tuple(span for _, span in result))


def _decode_string_token(text: str, start: int, end: int, prefix: str, quote: str) -> _SourceView | None:
    if prefix.lower() not in {"", "u", "r"}:
        return None
    body_start = start + len(prefix) + len(quote)
    body_end = end - len(quote)
    pieces: list[tuple[str, tuple[int, int]]] = []
    cursor = body_start
    simple = {"\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    while cursor < body_end:
        char = text[cursor]
        if char != "\\" or prefix.lower() == "r":
            end_char = cursor + 1
            if char == "\r":
                if text[end_char : end_char + 1] == "\n":
                    end_char += 1
                char = "\n"
            pieces.append((char, (cursor, end_char)))
            cursor = end_char
            continue
        begin = cursor
        cursor += 1
        if cursor >= body_end:
            return None
        code = text[cursor]
        cursor += 1
        if code in "\r\n":
            if code == "\r" and text[cursor : cursor + 1] == "\n":
                cursor += 1
            continue
        if code in simple:
            value = simple[code]
        elif code in "01234567":
            while cursor < min(begin + 4, body_end) and text[cursor] in "01234567":
                cursor += 1
            value = chr(int(text[begin + 1 : cursor], 8))
        elif code in "xuU":
            count = {"x": 2, "u": 4, "U": 8}[code]
            digits = text[cursor : cursor + count]
            if len(digits) != count or not re.fullmatch(r"[0-9a-fA-F]+", digits) or cursor + count > body_end:
                return None
            try:
                value = chr(int(digits, 16))
            except ValueError:
                return None
            cursor += count
        elif code == "N" and text[cursor : cursor + 1] == "{":
            close = text.find("}", cursor + 1, body_end)
            if close < 0:
                return None
            try:
                value = unicodedata.lookup(text[cursor + 1 : close])
            except KeyError:
                return None
            cursor = close + 1
        else:
            return None
        pieces.extend((piece, (begin, cursor)) for piece in value)
    try:
        # This is exactly one lexically recognized scalar token, never an expression.
        value = ast.literal_eval(text[start:end])
    except (SyntaxError, ValueError, UnicodeError):
        return None
    if not isinstance(value, str) or value != "".join(char for char, _ in pieces):
        return None
    return _SourceView(value, tuple(span for _, span in pieces))


def _string_parts(text: str) -> list[_StringPart]:
    parts: list[_StringPart] = []
    cursor = 0
    while cursor < len(text):
        start = cursor
        opener = STRING_OPEN_RE.match(text, cursor)
        if opener:
            prefix, quote = opener.groups()
            permitted = not (start and (text[start - 1].isalnum() or text[start - 1] == "_"))
            cursor = opener.end()
            closed = False
            while cursor < len(text):
                if text.startswith(quote, cursor):
                    cursor += len(quote)
                    closed = True
                    break
                if text[cursor] == "\\":
                    cursor += 3 if text[cursor + 1 : cursor + 3] == "\r\n" else 2
                elif len(quote) == 1 and text[cursor] in "\r\n":
                    break
                else:
                    cursor += 1
            cursor = min(cursor, len(text))
            view = _decode_string_token(text, start, cursor, prefix, quote) if permitted and closed else None
            parts.append(_StringPart("string" if view is not None else "boundary", start, cursor, view))
            continue
        char = text[cursor]
        if char == "\\" and text[cursor + 1 : cursor + 2] in {"\n", "\r"}:
            cursor += 2
            if text[cursor - 1] == "\r" and text[cursor : cursor + 1] == "\n":
                cursor += 1
            kind = "gap"
        elif char in "\r\n":
            cursor += 1
            kind = "newline"
        elif char.isspace():
            cursor += 1
            kind = "gap"
        elif char == "#":
            cursor = text.find("\n", cursor)
            if cursor < 0:
                cursor = len(text)
            kind = "boundary"
        elif char.isalnum() or char == "_":
            cursor += 1
            while cursor < len(text) and (text[cursor].isalnum() or text[cursor] == "_"):
                cursor += 1
            kind = "boundary"
        else:
            cursor += 1
            kind = {"(": "open", ")": "close", "+": "plus"}.get(char, "boundary")
        parts.append(_StringPart(kind, start, cursor))
    return parts


def _literal_views(text: str) -> list[_SourceView]:
    parts = _string_parts(text)
    pairs: dict[int, int] = {}
    stack: list[int] = []
    call_opens: set[int] = set()
    await_strings: set[int] = set()
    previous: _StringPart | None = None
    previous_is_keyword = False
    previous_is_await = False
    last_boundary = -1
    for index, part in enumerate(parts):
        if part.kind == "gap":
            continue
        if part.kind == "newline":
            if not stack:
                previous = None
                previous_is_keyword = False
                previous_is_await = False
            continue
        if part.kind == "string" and previous_is_await:
            await_strings.add(index)
        if part.kind == "open":
            # A callable operand is a dynamic boundary. Its constant arguments
            # remain inspectable, but its closing parenthesis cannot join an Add.
            if previous is not None and (
                previous.kind in {"string", "close"}
                or (previous.kind == "boundary" and not previous_is_keyword and (
                    text[previous.end - 1].isalnum()
                    or text[previous.end - 1] in "_]}\"'"
                ))
            ):
                call_opens.add(index)
            stack.append(index)
            if len(stack) > 128:
                raise ScanInputError("scanner input is invalid")
        elif part.kind == "close" and stack:
            pairs[stack.pop()] = index
        if part.kind == "boundary":
            last_boundary = index
        # Await consumes one primary, so its result cannot join an outer Add.
        # Its inner constants remain inspectable, as do ordinary call arguments.
        word = text[part.start : part.end] if part.kind == "boundary" else ""
        previous_is_await = word == "await" and (previous is None or text[previous.start : previous.end] != ".")
        previous_is_keyword = (
            keyword.iskeyword(word) and word not in {"False", "None", "True", "await"}
            and (previous is None or text[previous.start : previous.end] != ".")
        )
        previous = part
    incomplete_start = min((index for index in stack if index >= last_boundary), default=len(parts))
    # One range pass replaces searching every pair separately for every fragment.
    nesting_delta = [0] * (len(parts) + 1)
    for start, end in pairs.items():
        nesting_delta[start + 1] += 1
        nesting_delta[end] -= 1
    nested_at = []
    level = 0
    for delta in nesting_delta[:-1]:
        level += delta
        nested_at.append(level > 0)

    def skip(index: int, nested: bool) -> int:
        while index < len(parts) and (parts[index].kind == "gap" or (nested and parts[index].kind == "newline")):
            index += 1
        return index

    def atom(index: int, nested: bool, depth: int) -> tuple[_SourceView, int] | None:
        if depth > 128:
            raise ScanInputError("scanner input is invalid")
        index = skip(index, nested)
        if index >= len(parts):
            return None
        if parts[index].kind == "open":
            if index not in pairs or index in call_opens:
                return None
            parsed = expression(index + 1, True, depth + 1)
            if parsed is None:
                return None
            view, end = parsed
            end = skip(end, True)
            return (view, end + 1) if end == pairs[index] else None
        if parts[index].kind != "string":
            return None
        values = []
        while index < len(parts) and parts[index].kind == "string":
            values.append(parts[index].view)
            end = index + 1
            index = skip(end, nested)
        return _join_views(values), end

    failed_expressions: set[tuple[int, bool]] = set()

    def expression(index: int, nested: bool, depth: int) -> tuple[_SourceView, int] | None:
        index = skip(index, nested)
        if (index, nested) in failed_expressions:
            return None
        values = []
        suffix_starts: list[tuple[int, bool]] = []
        while True:
            parsed = atom(index, nested, depth)
            if parsed is None:
                # Every same-level constant suffix reaches this same boundary.
                # Inner group/argument starts remain independently inspectable.
                failed_expressions.update(suffix_starts)
                failed_expressions.add((index, nested))
                return None
            view, end = parsed
            if parts[index].kind == "string":
                suffix_starts.extend(
                    (candidate, nested) for candidate in range(index, end)
                    if parts[candidate].kind == "string"
                )
            else:
                suffix_starts.append((index, nested))
            values.append(view)
            next_index = skip(end, nested)
            if next_index >= len(parts) or parts[next_index].kind != "plus":
                return _join_views(values), end
            index = skip(next_index + 1, nested)

    views = []
    index = 0
    while index < len(parts):
        if parts[index].kind not in {"string", "open"} or index > incomplete_start:
            index += 1
            continue
        parsed = atom(index, nested_at[index], 0) if index in await_strings else expression(index, nested_at[index], 0)
        if parsed is None:
            index += 1
            continue
        view, index = parsed
        views.append(view)
    return views


def _marker_matches(text: str, rel: str, rules: Sequence[MarkerRule], source_kind: str) -> list[tuple[int, int, str]]:
    if source_kind not in {"content", "path", "metadata"}:
        raise ScanInputError("scanner input is invalid")
    if not rules:
        return []
    try:
        raw = _SourceView(text, tuple((index, index + 1) for index in range(len(text))))
        candidates = [raw, _canonical_view(raw)]
        if source_kind != "path":
            for view in _literal_views(text):
                candidates.extend((view, _canonical_view(view)))
        author_starts: list[int] = []
        author_lines: list[str] = []
        if any(rule.author_literal is not None for rule in rules):
            offset = 0
            for line in text.splitlines(keepends=True):
                author_starts.append(offset)
                author_lines.append((line.splitlines() or [""])[0])
                offset += len(line)
        found: set[tuple[int, int, str]] = set()
        raw_zero_origins: set[tuple[int, int]] = set()
        for view in candidates:
            offset = 0
            lines = [view.text] if source_kind == "path" else view.text.splitlines(keepends=True)
            for line in lines:
                logical_line = line if source_kind == "path" else (line.splitlines() or [""])[0]
                for rule in rules:
                    for match in rule.pattern.finditer(logical_line):
                        spans = view.spans[offset + match.start() : offset + match.end()]
                        if spans:
                            start = min(begin for begin, _ in spans)
                            end = max(finish for _, finish in spans)
                        else:
                            # Contextual zero-width regexes have a source boundary,
                            # even though no character contributes a nonempty span.
                            boundary = offset + match.start()
                            right = (
                                view.spans[boundary][0] if boundary < len(view.spans)
                                else view.spans[-1][1] if view.spans else 0
                            )
                            left = view.spans[boundary - 1][1] if boundary else right
                            if view is raw:
                                start = right
                                raw_zero_origins.add((id(rule), start))
                            elif (id(rule), left) in raw_zero_origins:
                                start = left
                            elif (id(rule), right) in raw_zero_origins:
                                start = right
                            elif left != right and (prefix_match := rule.pattern.match(
                                logical_line, match.start(), match.start()
                            )) is not None and prefix_match.end() == match.start():
                                # Prefix-supported matches stay after their left
                                # contributor across removed text or token gaps.
                                start = left
                            else:
                                start = right
                            end = start
                        if rule.author_literal is not None:
                            row = bisect_right(author_starts, start) - 1
                            raw_start, raw_line = author_starts[row], author_lines[row]
                            if end <= raw_start + len(raw_line) and _allowed_author_identity(
                                rule, rel, raw_line, start - raw_start, end - raw_start
                            ):
                                continue
                        found.add((start, end, rule.category))
                offset += len(line)
        return sorted(found)
    except ScanInputError:
        raise
    except Exception as exc:
        raise ScanInputError("scanner input is invalid") from exc


def marker_findings(text: str, rel: str, scope: str, rules: Sequence[MarkerRule], *, source_kind: str = "content") -> list[Finding]:
    """Match only externally supplied rules, retaining original physical origins."""
    starts = [0]
    offset = 0
    for line in text.splitlines(keepends=True):
        offset += len(line)
        # EOF is not an additional physical line for a zero-width match.
        if offset < len(text):
            starts.append(offset)
    return [
        _finding(rel, bisect_right(starts, start) if source_kind == "content" else 0, category, scope, rules)
        for start, _end, category in _marker_matches(text, rel, rules, source_kind)
    ]


def is_under(path: str, parents: Iterable[str]) -> bool:
    return any(path == parent or path.startswith(f"{parent}/") for parent in parents)


def scope_includes(rel: str, scope: str) -> bool:
    if scope == "keep-set":
        return not is_under(rel, HISTORICAL_DIRS)
    if scope == "evidence":
        return is_under(rel, EVIDENCE_DIRS)
    return True


def severity_for(category: str, scope: str) -> str:
    del scope
    return "warning" if category == "binary_file" else "blocker"


def _raise_input_error() -> None:
    raise ScanInputError("scanner input is invalid")


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _has_samefile_ancestor(path: Path, root: Path) -> bool:
    current = path
    while True:
        try:
            if current.samefile(root):
                return True
        except OSError as exc:
            raise ScanInputError("scanner input is invalid") from exc
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _clean_git_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
    ):
        env.pop(name, None)
    env["LC_ALL"] = "C"
    return env


def _run_git(args: Sequence[str]) -> bytes:
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,
            check=False,
            env=_clean_git_env(),
        )
    except OSError as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if proc.returncode != 0:
        _raise_input_error()
    return proc.stdout


def _decode_git_path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if not path or "\x00" in path:
        _raise_input_error()
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _raise_input_error()
    if pure.as_posix() != path:
        _raise_input_error()
    return path


def git_inventory(root: Path) -> list[str]:
    if not root.is_dir():
        _raise_input_error()
    root = root.resolve()
    top_raw = _run_git(["git", "-C", str(root), "rev-parse", "--show-toplevel"])
    try:
        top = Path(top_raw.decode("utf-8", errors="strict").strip()).resolve()
    except UnicodeDecodeError as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if top != root:
        _raise_input_error()
    raw = _run_git(["git", "-C", str(root), "ls-files", "-z"])
    if raw and not raw.endswith(b"\0"):
        _raise_input_error()
    items = raw[:-1].split(b"\0") if raw else []
    paths = [_decode_git_path(item) for item in items]
    if len(paths) != len(set(paths)):
        _raise_input_error()
    return sorted(paths)


def _require_regular_file(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if not stat.S_ISREG(mode):
        _raise_input_error()


def literal_pattern(value: str, *, short_name: bool = True) -> re.Pattern[str]:
    value = _canonical_literal(value)
    if not value or not value.strip():
        _raise_input_error()
    pieces = re.split(r"[-_. ]+", value)
    expression = r"[-_ .]?".join(re.escape(piece) for piece in pieces)
    if not expression:
        _raise_input_error()
    if short_name and re.fullmatch(r"\w{1,4}", value):
        expression = rf"(?<!\w){expression}(?!\w)"
    try:
        return re.compile(expression, re.I)
    except re.error as exc:  # pragma: no cover - escaped values cannot fail
        raise ScanInputError("scanner input is invalid") from exc


def author_pattern(value: str) -> re.Pattern[str]:
    value = _canonical_literal(value)
    if not value or not value.strip() or value != value.strip():
        _raise_input_error()
    try:
        return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(value)}(?:[0-9]+)?(?![A-Za-z0-9_])", re.I)
    except re.error as exc:  # pragma: no cover - escaped values cannot fail
        raise ScanInputError("scanner input is invalid") from exc


def load_marker_rules(root: Path) -> tuple[MarkerRule, ...]:
    if MARKER_ENV not in os.environ:
        return ()
    raw_value = os.environ[MARKER_ENV]
    marker_path = Path(raw_value)
    if not raw_value or not marker_path.is_absolute():
        _raise_input_error()
    try:
        mode = marker_path.lstat().st_mode
        if not stat.S_ISREG(mode):
            _raise_input_error()
        marker_path = marker_path.resolve(strict=True)
        root = root.resolve(strict=True)
        if _inside(marker_path, root) or _has_samefile_ancestor(marker_path, root):
            _raise_input_error()
        content = marker_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScanInputError("scanner input is invalid") from exc

    rules: list[MarkerRule] = []
    for original in content.splitlines():
        entry = original.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("path:"):
            payload = entry[len("path:") :]
            rules.append(MarkerRule("personal_path", literal_pattern(payload, short_name=False)))
            continue
        if entry.startswith("re:"):
            payload = entry[len("re:") :]
            if not payload:
                _raise_input_error()
            try:
                pattern = re.compile(payload, re.I)
            except re.error as exc:
                raise ScanInputError("scanner input is invalid") from exc
            if pattern.search("") is not None:
                _raise_input_error()
            rules.append(MarkerRule("private_marker", pattern))
            continue
        if entry.startswith("author:"):
            payload = entry[len("author:") :]
            rules.append(MarkerRule("owner_identity", author_pattern(payload), payload))
            continue
        rules.append(MarkerRule("private_marker", literal_pattern(entry)))
    if not rules:
        _raise_input_error()
    return tuple(rules)


def _safe_archive_path(value: object, category: object) -> str:
    if not isinstance(value, str) or not isinstance(category, str):
        _raise_input_error()
    if not value or "\0" in value or "\\" in value or "//" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _raise_input_error()
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value:
        _raise_input_error()
    if any(part in {"", ".", ".."} for part in pure.parts):
        _raise_input_error()
    parts = pure.parts
    if len(parts) != 4 or parts[:2] != ("docs", "evidence"):
        _raise_input_error()
    if parts[2] != category or category not in ARCHIVE_CATEGORIES:
        _raise_input_error()
    filename = parts[3]
    if filename.startswith(".") or not filename.endswith(".md"):
        _raise_input_error()
    return value


def _reject_duplicate_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _raise_input_error()
        result[key] = value
    return result


def _archive_manifest_paths(manifest: Path) -> dict[str, tuple[str, str]]:
    try:
        mode = manifest.lstat().st_mode
        if not stat.S_ISREG(mode):
            _raise_input_error()
        payload = json.loads(
            manifest.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "items"}:
        _raise_input_error()
    if payload.get("schema_version") != "oss-evidence-manifest.v1":
        _raise_input_error()
    items = payload.get("items")
    if not isinstance(items, list):
        _raise_input_error()
    if not items:
        _raise_input_error()
    entries: dict[str, tuple[str, str]] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "public_path",
            "category",
            "why_included",
            "sanitization_status",
        }:
            _raise_input_error()
        if not isinstance(item["why_included"], str) or not item["why_included"].strip():
            _raise_input_error()
        if not isinstance(item["sanitization_status"], str) or not item["sanitization_status"].strip():
            _raise_input_error()
        path = _safe_archive_path(item["public_path"], item["category"])
        if path in entries:
            _raise_input_error()
        entries[path] = (item["why_included"], item["sanitization_status"])
    return entries


def _walk_archive_regular_files(root: Path) -> set[str]:
    if not root.is_dir():
        _raise_input_error()
    found: set[str] = set()

    def visit(directory: Path, prefix: tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ScanInputError("scanner input is invalid") from exc
        for entry in entries:
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise ScanInputError("scanner input is invalid") from exc
            rel_parts = (*prefix, entry.name)
            if stat.S_ISDIR(mode):
                visit(Path(entry.path), rel_parts)
                continue
            if not stat.S_ISREG(mode):
                _raise_input_error()
            rel = PurePosixPath(*rel_parts).as_posix()
            found.add(rel)

    visit(root, ())
    return found


def archive_inventory(root: Path, manifest: Path, scope: str) -> tuple[list[str], dict[str, tuple[str, str]]]:
    if scope != "public-copy":
        _raise_input_error()
    entries = _archive_manifest_paths(manifest)
    expected = set(entries)
    observed = _walk_archive_regular_files(root)
    if observed != expected:
        _raise_input_error()
    return sorted(expected), entries


def _matches_for_path_redaction(rules: Sequence[MarkerRule]) -> tuple[re.Pattern[str], ...]:
    del rules
    return tuple(pattern for _, pattern in GENERIC_RULES) + THIRD_PARTY_DUMP_PATTERNS


def safe_path(rel: str, rules: Sequence[MarkerRule]) -> str:
    if _marker_matches(rel, rel, rules, "path"):
        return MASKED_TOKEN
    result = rel
    for pattern in _matches_for_path_redaction(rules):
        result = pattern.sub(MASKED_TOKEN, result)
    return result


def is_secret_assignment_value(value: str) -> bool:
    if len(value) < 12 or not any(char.isalpha() for char in value):
        return False
    has_digit = any(char.isdigit() for char in value)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) and not has_digit:
        return False
    return has_digit


def _allowed_version_context_ip(line: str, match: re.Match[str]) -> bool:
    return VERSION_CONTEXT_BEFORE_IP_RE.search(line[: match.start()]) is not None


def _allowed_security_contact(rel: str, line_no: int, category: str, value: str) -> bool:
    return category == "email" and rel in SECURITY_CONTACT_PATHS and line_no > 0 and value == SANCTIONED_SECURITY_CONTACT


def _allowed_author_identity(rule: MarkerRule, rel: str, line: str, start: int, end: int) -> bool:
    if rule.author_literal is None:
        return False
    value = line[start:end]
    left = line[start - 1 : start]
    right = line[end : end + 1]
    return (
        rel in {"LICENSE", "NOTICE"}
        and LEGAL_ATTRIBUTION_RE.search(line) is not None
        and value.casefold() == rule.author_literal.casefold()
        and not any(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-" for char in left + right)
    )


def _finding(rel: str, line: int, category: str, scope: str, rules: Sequence[MarkerRule]) -> Finding:
    return Finding(safe_path(rel, rules), line, category, severity_for(category, scope), MASKED_TOKEN)


def _line_findings(line: str, rel: str, line_no: int, scope: str, rules: Sequence[MarkerRule]) -> list[Finding]:
    findings: list[Finding] = []
    for category, pattern in GENERIC_RULES:
        for match in pattern.finditer(line):
            value = match.group(1) if pattern is SECRET_ASSIGNMENT_RE else match.group(0)
            if pattern is SECRET_ASSIGNMENT_RE and not is_secret_assignment_value(value):
                continue
            if pattern is IP_ADDRESS_RE and _allowed_version_context_ip(line, match):
                continue
            if category == "email" and value.lower().endswith("@example.invalid"):
                # Reserved, non-routable identity used by local generated commits.
                continue
            if _allowed_security_contact(rel, line_no, category, value):
                continue
            findings.append(_finding(rel, line_no, category, scope, rules))
    for pattern in THIRD_PARTY_DUMP_PATTERNS:
        for _match in pattern.finditer(line):
            findings.append(_finding(rel, line_no, "third_party_prompt_dump", scope, rules))
    return findings


def _path_findings(rel: str, scope: str, rules: Sequence[MarkerRule]) -> list[Finding]:
    findings = _line_findings(rel, rel, 0, scope, rules)
    findings.extend(marker_findings(rel, rel, scope, rules, source_kind="path"))
    if THIRD_PARTY_SOURCE_RE.search(rel):
        findings.append(_finding(rel, 0, "third_party_source_path", scope, rules))
    return findings


def _read_content(path: Path) -> str | None:
    _require_regular_file(path)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ScanInputError("scanner input is invalid") from exc
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


def _read_tracked_content(root: Path, rel: str, tracked: set[str], scope: str) -> str | None:
    path = root.joinpath(*PurePosixPath(rel).parts)
    if path.is_symlink():
        # Copier's source-only links reuse tracked contract bytes. All other
        # links remain invalid scanner inputs, and no link may escape the repo.
        if not rel.startswith("copier_template/"):
            _raise_input_error()
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ScanInputError("scanner input is invalid") from exc
        if not _inside(resolved, root):
            _raise_input_error()
        if resolved.is_dir():
            # A directory link has no content of its own. Its destination
            # bytes are covered by the ordinary scan only if each tracked
            # source file is included in this same scope.
            for child in resolved.rglob("*"):
                if child.is_symlink() or (not child.is_file() and not child.is_dir()):
                    _raise_input_error()
                if child.is_file():
                    source_rel = child.relative_to(root).as_posix()
                    if source_rel not in tracked or not scope_includes(source_rel, scope):
                        _raise_input_error()
            return ""
        if resolved.relative_to(root).as_posix() not in tracked:
            _raise_input_error()
        path = resolved
    return _read_content(path)


def scan(root: Path, scope: str, *, archive_manifest: Path | None = None) -> list[Finding]:
    if scope not in SCOPES:
        _raise_input_error()
    root = root.resolve()
    rules = load_marker_rules(root)
    if archive_manifest is None:
        paths = git_inventory(root)
        manifest_metadata: dict[str, tuple[str, str]] = {}
    else:
        paths, manifest_metadata = archive_inventory(root, archive_manifest, scope)
    tracked = set(paths)
    findings: list[Finding] = []
    for rel in paths:
        if not scope_includes(rel, scope):
            continue
        path = root.joinpath(*PurePosixPath(rel).parts)
        for value in manifest_metadata.get(rel, ()):
            for line in value.splitlines() or [value]:
                findings.extend(_line_findings(line, rel, 0, scope, rules))
            findings.extend(marker_findings(value, rel, scope, rules, source_kind="metadata"))
        findings.extend(_path_findings(rel, scope, rules))
        text = _read_tracked_content(root, rel, tracked, scope)
        if text is None:
            findings.append(_finding(rel, 0, "binary_file", scope, rules))
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            findings.extend(_line_findings(line, rel, line_no, scope, rules))
        findings.extend(marker_findings(text, rel, scope, rules))
    return findings


def exit_code(findings: Sequence[Finding], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[fail_on]
    return 1 if any(SEVERITY_RANK[finding.severity] >= threshold for finding in findings) else 0


def summary(findings: Sequence[Finding]) -> dict[str, int]:
    result = {"blocker": 0, "warning": 0}
    for finding in findings:
        result[finding.severity] += 1
    return result


def text_path(path: str) -> str:
    return "".join(
        {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(char, f"\\x{ord(char):02x}")
        if ord(char) < 32 or ord(char) == 127
        else char
        for char in path
    )


def print_text(findings: Sequence[Finding], *, scope: str, fail_on: str) -> None:
    counts = summary(findings)
    print(f"oss-release-scan scope={scope} root=. blockers={counts['blocker']} warnings={counts['warning']} fail_on={fail_on}")
    if not findings:
        print("OK: no findings")
        return
    for finding in findings:
        print(f"{text_path(finding.path)}:{finding.line}: {finding.severity}: {finding.category}: {finding.token}")


def print_json(findings: Sequence[Finding], *, scope: str, fail_on: str) -> None:
    payload = {
        "root": ".",
        "scope": scope,
        "fail_on": fail_on,
        "counts": summary(findings),
        "findings": [asdict(finding) for finding in findings],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Scan root. Defaults to current working directory.")
    parser.add_argument("--scope", choices=SCOPES, default="keep-set")
    parser.add_argument("--format", choices=FORMATS, default="text")
    parser.add_argument("--fail-on", choices=FAIL_LEVELS, default="blocker")
    parser.add_argument("--archive-manifest", help="Explicit oss-evidence-manifest.v1 input for a staged public archive.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        findings = scan(
            Path(args.root),
            args.scope,
            archive_manifest=Path(args.archive_manifest) if args.archive_manifest else None,
        )
    except ScanInputError:
        print("error: scanner input is invalid", file=sys.stderr)
        return 2
    if args.format == "json":
        print_json(findings, scope=args.scope, fail_on=args.fail_on)
    else:
        print_text(findings, scope=args.scope, fail_on=args.fail_on)
    return exit_code(findings, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())

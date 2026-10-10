#!/usr/bin/env python3
from __future__ import annotations

"""Read-only public safety scanner for tracked OSS release inputs."""

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Iterable, Sequence


SCOPES = ("keep-set", "public-copy", "evidence", "all")
FORMATS = ("text", "json")
FAIL_LEVELS = ("blocker", "warning", "never")
SEVERITY_RANK = {"warning": 1, "blocker": 2}
MARKER_ENV = "PLANVEYOR_OSS_SCAN_MARKERS"
MASKED_TOKEN = "<masked>"
SANCTIONED_SECURITY_CONTACT = "security" + "@" + "planveyor.dev"

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


def literal_pattern(value: str) -> re.Pattern[str]:
    if not value or not value.strip():
        _raise_input_error()
    pieces = re.split(r"[-_. ]+", value)
    expression = r"[-_ .]?".join(re.escape(piece) for piece in pieces)
    if not expression:
        _raise_input_error()
    try:
        return re.compile(expression, re.I)
    except re.error as exc:  # pragma: no cover - escaped values cannot fail
        raise ScanInputError("scanner input is invalid") from exc


def author_pattern(value: str) -> re.Pattern[str]:
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
            rules.append(MarkerRule("personal_path", literal_pattern(payload)))
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
    return tuple(pattern for _, pattern in GENERIC_RULES) + tuple(rule.pattern for rule in rules) + THIRD_PARTY_DUMP_PATTERNS


def safe_path(rel: str, rules: Sequence[MarkerRule]) -> str:
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
    return category == "email" and rel == "SECURITY.md" and line_no > 0 and value == SANCTIONED_SECURITY_CONTACT


def _allowed_author_identity(rule: MarkerRule, rel: str, line: str, match: re.Match[str]) -> bool:
    if rule.author_literal is None:
        return False
    value = match.group(0)
    left = line[match.start() - 1 : match.start()]
    right = line[match.end() : match.end() + 1]
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
    for rule in rules:
        for match in rule.pattern.finditer(line):
            if rule.category == "owner_identity" and _allowed_author_identity(rule, rel, line, match):
                continue
            findings.append(_finding(rel, line_no, rule.category, scope, rules))
    return findings


def _path_findings(rel: str, scope: str, rules: Sequence[MarkerRule]) -> list[Finding]:
    findings = _line_findings(rel, rel, 0, scope, rules)
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
        findings.extend(_path_findings(rel, scope, rules))
        text = _read_tracked_content(root, rel, tracked, scope)
        if text is None:
            findings.append(_finding(rel, 0, "binary_file", scope, rules))
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            findings.extend(_line_findings(line, rel, line_no, scope, rules))
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

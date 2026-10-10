"""Local, fail-closed SQL Server 2019 rehearsal commands.

Only ``main`` reads .env.local. Importing this module is safe for fake tests.
No subprocess command line or unredacted subprocess output is displayed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_SOURCE = ROOT / "sql/Northwind/Northwind.sql"
TEST_SOURCE = ROOT / "sql/tests/SqlHarnessSmoke.sql"
CONTENT_TEST_SOURCE = ROOT / "sql/tests/GetReorderCandidatesTests.sql"
TEST_RUNNER = ROOT / "sql/tests/run-tests.sql"
JUNIT = ROOT / "docs/code_reviews/assets/260928_0006_get_reorder_candidates/get_reorder_candidates.junit.xml"
TEST_NAME = "SqlHarnessSmoke.test_schema_present"
CONTENT_TEST_NAMES = (
    "GetReorderCandidatesTests.test_positive_shortage_and_units_on_order",
    "GetReorderCandidatesTests.test_equality_and_excess_excluded",
    "GetReorderCandidatesTests.test_discontinued_and_null_excluded",
    "GetReorderCandidatesTests.test_null_quantities_zero",
    "GetReorderCandidatesTests.test_empty_products",
    "GetReorderCandidatesTests.test_productid_order_rows",
    "GetReorderCandidatesTests.test_smallint_boundary_int_arithmetic",
)
TEST_NAMES = (TEST_NAME, *CONTENT_TEST_NAMES)
TEST_CLASSES = ("SqlHarnessSmoke", "GetReorderCandidatesTests")
CODE_DRAFT = ROOT / "docs/code_drafts/260928_0006_get_reorder_candidates__code_draft.md"
ENV_KEYS = ("SQLCMDSERVER", "SQLCMDUSER", "SQLCMDPASSWORD", "SQLCMDDBNAME")


class SqlHarnessError(Exception):
    """Safe, fixed-text error for the operator."""


@dataclass(frozen=True)
class CommandFailure(SqlHarnessError):
    category: str
    actual_rc: int

    def __str__(self) -> str:
        return f"{self.category}; actual_rc={self.actual_rc}"


@dataclass(frozen=True)
class Connection:
    server: str
    user: str
    password: str
    dev_database: str

    @property
    def values(self) -> tuple[str, ...]:
        return (self.server, self.user, self.password, self.dev_database)


def parse_env(data: str) -> Connection:
    """Accept a small dotenv subset, never source shell code."""
    found: dict[str, str] = {}
    for raw in data.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SqlHarnessError("invalid .env.local format")
        key, value = line.split("=", 1)
        if key not in ENV_KEYS or key in found:
            raise SqlHarnessError("invalid .env.local key")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value or "\x00" in value or "\n" in value:
            raise SqlHarnessError("missing or invalid .env.local value")
        found[key] = value
    if set(found) != set(ENV_KEYS):
        raise SqlHarnessError("missing .env.local input")
    if found["SQLCMDDBNAME"].casefold() in {
        "northwind", "master", "model", "msdb", "tempdb"
    }:
        raise SqlHarnessError("SQLCMDDBNAME must identify a designated dev database")
    return Connection(found["SQLCMDSERVER"], found["SQLCMDUSER"],
                      found["SQLCMDPASSWORD"], found["SQLCMDDBNAME"])


def load_connection(root: Path = ROOT) -> Connection:
    file = root / ".env.local"
    if file.is_symlink() or not file.is_file():
        raise SqlHarnessError("missing regular .env.local")
    if stat.S_IMODE(file.stat().st_mode) & 0o077:
        raise SqlHarnessError(".env.local permissions must be owner-only")
    return parse_env(file.read_text(encoding="utf-8"))


def redaction_tokens(values: tuple[str, ...]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if value:
            tokens.update((value, html.escape(value), urllib.parse.quote(value),
                           urllib.parse.quote_plus(value)))
    return {token for token in tokens if token}


def scrub(text: str, values: tuple[str, ...] = ()) -> str:
    safe = xml_safe(text)
    for token in sorted(redaction_tokens(values), key=len, reverse=True):
        safe = safe.replace(token, "[REDACTED]")
    # Tools sometimes echo a connection string with a value not identical to
    # the input spelling. Remove each property before any display or write.
    safe = re.sub(r"(?i)\b(password|pwd|user id|uid|server|data source|database)\s*=\s*[^;\s]+",
                  lambda m: m.group(1) + "=[REDACTED]", safe)
    return safe


def xml_safe(text: str) -> str:
    return "".join(c for c in text if c in "\t\n\r" or ord(c) >= 0x20)


def classify_failure(output: str, stage: str) -> str:
    lowered = output.casefold()
    if stage == "lint" and ("prs" in lowered or "parsing error" in lowered):
        return "parser_failure"
    if any(word in lowered for word in ("login failed", "authentication failed", "18456")):
        return "login_failure"
    if any(word in lowered for word in (
        "network-related", "could not open a connection", "connection refused",
        "server was not found", "timed out", "login timeout", "error: 40",
    )):
        return "connection_failure"
    if stage == "test":
        return "test_failure"
    return "tool_failure"


def local_environment(root: Path = ROOT) -> dict[str, str]:
    env = os.environ.copy()
    for key, relative in {
        "DOTNET_CLI_HOME": ".tmp/dotnet-home",
        "NUGET_PACKAGES": ".tmp/nuget/packages",
        "NUGET_HTTP_CACHE_PATH": ".tmp/nuget/http",
        "PIP_CACHE_DIR": ".tmp/pip-cache",
        "TMPDIR": ".tmp/sql-tmp",
    }.items():
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_command(argv: list[str], *, stage: str, env: dict[str, str],
                values: tuple[str, ...] = (), cwd: Path = ROOT,
                show_output: bool = False) -> str:
    """Capture both streams before release; never print argv or exception repr."""
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, text=True,
                                encoding="utf-8", errors="replace",
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False)
    except (OSError, ValueError):
        raise CommandFailure("tool_unavailable", 127) from None
    clean_out = scrub(result.stdout, values)
    clean_err = scrub(result.stderr, values)
    if show_output and clean_out:
        print(clean_out, end="" if clean_out.endswith("\n") else "\n")
    if show_output and clean_err:
        print(clean_err, end="" if clean_err.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode:
        raise CommandFailure(classify_failure(result.stdout + result.stderr, stage),
                             result.returncode)
    return clean_out


def sqlpackage(action: str, extra: list[str]) -> list[str]:
    return ["dotnet", "tool", "run", "sqlpackage", "--", f"/Action:{action}", *extra]


def extract_args(connection: Connection, destination: Path) -> list[str]:
    return sqlpackage("Extract", [
        f"/SourceServerName:{connection.server}", "/SourceDatabaseName:Northwind",
        f"/SourceUser:{connection.user}", f"/SourcePassword:{connection.password}",
        "/SourceEncryptConnection:True", "/SourceTrustServerCertificate:True",
        f"/TargetFile:{destination}", "/p:ExtractTarget=File",
        "/p:ExtractAllTableData=false",
        "/p:ExtractReferencedServerScopedElements=false",
    ])


def schema_code_mask(sql: str) -> str:
    """Hide comments and quoted text while retaining code and real separators."""
    masked = list(sql)
    line_comment = False
    block_depth = 0
    quote_end: str | None = None
    index = 0

    def hide(position: int) -> None:
        if sql[position] not in "\r\n":
            masked[position] = " "

    while index < len(sql):
        char = sql[index]
        if line_comment:
            if char in "\r\n":
                line_comment = False
            else:
                hide(index)
            index += 1
        elif block_depth:
            if sql.startswith("/*", index):
                hide(index)
                hide(index + 1)
                block_depth += 1
                index += 2
            elif sql.startswith("*/", index):
                hide(index)
                hide(index + 1)
                block_depth -= 1
                index += 2
            else:
                hide(index)
                index += 1
        elif quote_end:
            hide(index)
            if char == quote_end:
                if index + 1 < len(sql) and sql[index + 1] == quote_end:
                    hide(index + 1)
                    index += 2
                    continue
                quote_end = None
            index += 1
        elif sql.startswith("--", index):
            hide(index)
            hide(index + 1)
            line_comment = True
            index += 2
        elif sql.startswith("/*", index):
            hide(index)
            hide(index + 1)
            block_depth = 1
            index += 2
        elif char in "'\"[":
            hide(index)
            quote_end = "]" if char == "[" else char
            index += 1
        else:
            index += 1
    if block_depth or quote_end:
        raise SqlHarnessError("Extract contains unterminated comment or quoted text")
    return "".join(masked)


def omit_source_environment_security(raw: bytes, principal: str) -> bytes:
    """Omit only the two approved, complete source-environment GO batches."""
    error = "Northwind Extract: неожиданная security DDL"
    try:
        if not principal or any(ord(char) < 0x20 for char in principal):
            raise ValueError
        quoted = ("[" + principal.replace("]", "]]") + "]").encode("utf-8")
        leading_blank = rb"(?:[ \t]*\r?\n)*[ \t]*"
        trailing_blank = rb"[ \t]*(?:\r?\n[ \t]*)*\r?"
        user_form = re.compile(
            leading_blank + rb"CREATE[ \t]+USER[ \t]+" + re.escape(quoted) +
            rb"[ \t]+FOR[ \t]+LOGIN[ \t]+" + re.escape(quoted) +
            rb"[ \t]*;" + trailing_blank)
        role_form = re.compile(
            leading_blank + rb"ALTER[ \t]+ROLE[ \t]+\[db_datareader\]" +
            rb"[ \t]+ADD[ \t]+MEMBER[ \t]+" + re.escape(quoted) +
            rb"[ \t]*;" + trailing_blank)
        decoded = raw.decode("utf-8")
        masked_lines = schema_code_mask(decoded).split("\n")
        lines = raw.split(b"\n")
        if len(lines) != len(masked_lines):
            raise ValueError

        delimiters: list[int] = []
        for index, (line, code_line) in enumerate(zip(lines, masked_lines)):
            if re.fullmatch(r"[ \t]*GO[ \t]*\r?", code_line):
                if not re.fullmatch(rb"[ \t]*GO[ \t]*\r?", line):
                    raise ValueError
                delimiters.append(index)

        offsets = [0]
        for line in lines[:-1]:
            offsets.append(offsets[-1] + len(line) + 1)
        spans: list[tuple[int, int]] = []
        matches: list[str] = []
        start = 0
        for end in [*delimiters, len(lines)]:
            batch = b"\n".join(lines[start:end])
            kind = ("user" if end in delimiters and user_form.fullmatch(batch) else
                    "role" if end in delimiters and role_form.fullmatch(batch) else None)
            if kind is not None:
                matches.append(kind)
                spans.append((offsets[start], offsets[end] + len(lines[end]) +
                              (1 if end < len(lines) - 1 else 0)))
            else:
                code = "\n".join(masked_lines[start:end])
                if re.search(
                    r"\b(?:CREATE|ALTER|DROP)\s+(?:USER|ROLE|LOGIN|CREDENTIAL|SERVER"
                    r"|APPLICATION\s+ROLE|CERTIFICATE"
                    r"|(?:MASTER|ASYMMETRIC|SYMMETRIC)\s+KEY)\b"
                    r"|\b(?:GRANT|DENY|REVOKE|AUTHORIZATION|IMPERSONATE)\b"
                    r"|\bEXEC(?:UTE)?\s+AS\b"
                    r"|\b(?:sp_addrolemember|sp_droprolemember)\b", code, re.I
                ):
                    raise ValueError
                remaining = batch.decode("utf-8").casefold()
                if (principal.casefold() in remaining or
                        quoted.decode("utf-8").casefold() in remaining):
                    raise ValueError
            start = end + 1
        if matches != ["user", "role"]:
            raise ValueError
        kept: list[bytes] = []
        cursor = 0
        for first, last in spans:
            kept.append(raw[cursor:first])
            cursor = last
        kept.append(raw[cursor:])
        return b"".join(kept)
    except (UnicodeError, ValueError, SqlHarnessError, TypeError):
        raise SqlHarnessError(error) from None


def validate_schema(sql: str) -> None:
    if "PATH_TRACKING_STUB" in sql or not sql.strip():
        raise SqlHarnessError("Northwind schema Extract is not materialized")
    code = schema_code_mask(sql)
    products = re.finditer(
        r"\bCREATE\s+TABLE\s+(?:\[dbo\]|dbo)\.(?:\[Products\]|Products)(?=\s|\(|$)",
        sql, re.I)
    if not any(code[match.start():match.start() + 6].upper() == "CREATE"
               for match in products):
        raise SqlHarnessError("Northwind Products DDL missing from Extract")
    batches = re.split(r"(?im)^[ \t]*GO(?:[ \t]+\d+)?[ \t]*\r?$", code)
    module_start = re.compile(
        r"(?:CREATE(?:\s+OR\s+ALTER)?|ALTER)\s+(?:PROC(?:EDURE)?|FUNCTION|TRIGGER)\b",
        re.I)
    data_statement = re.compile(
        r"(?:\A|;|^)[ \t\r\n]*(?P<verb>INSERT\b|UPDATE\b|DELETE\b|MERGE\b|BULK\s+INSERT\b|SET\s+IDENTITY_INSERT\b)",
        re.I | re.M)
    server_statement = re.compile(r"\b(?:CREATE|ALTER)\s+(?:LOGIN|CREDENTIAL|SERVER)\b", re.I)
    for batch in batches:
        if module_start.match(batch.lstrip()):
            continue  # Module bodies may contain DML; the batch is schema DDL.
        if server_statement.search(batch):
            raise SqlHarnessError("Extract contains data or server-scoped statements")
        for match in data_statement.finditer(batch):
            # A line break between ON and DELETE/UPDATE is still a foreign-key
            # clause, not a standalone data statement.
            if (match.group("verb").upper() in {"DELETE", "UPDATE"} and
                    re.search(r"\bON\s*$", batch[:match.start()], re.I)):
                continue
            raise SqlHarnessError("Extract contains data or server-scoped statements")


def current_test_set(smoke_text: str, content_text: str,
                     runner_text: str) -> tuple[str, ...]:
    if "PATH_TRACKING_STUB" in smoke_text + content_text + runner_text:
        raise SqlHarnessError("test source is a path-tracking stub")
    declaration = re.compile(r"\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+",
                             re.I)
    named_declaration = re.compile(
        r"\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+"
        r"\[([^]]+)\]\.\[(test_[A-Za-z0-9_]+)\]", re.I)
    for source, class_name, expected_names in (
        (smoke_text, "SqlHarnessSmoke", (TEST_NAME,)),
        (content_text, "GetReorderCandidatesTests", CONTENT_TEST_NAMES),
    ):
        code = schema_code_mask(source)
        schemas = [match for match in re.finditer(r"\bCREATE\s+SCHEMA\s+\[([^]]+)\]",
                                                  source, re.I)
                   if code[match.start():match.start() + 6].upper() == "CREATE"]
        if len(schemas) != 1 or schemas[0].group(1) != class_name:
            raise SqlHarnessError("unexpected tSQLt class")
        count = sum(code[match.start():match.start() + 6].upper() == "CREATE"
                    for match in declaration.finditer(source))
        found = [f"{match.group(1)}.{match.group(2)}"
                 for match in named_declaration.finditer(source)
                 if code[match.start():match.start() + 6].upper() == "CREATE"]
        if count != len(expected_names) or set(found) != set(expected_names) or \
                len(found) != len(expected_names):
            raise SqlHarnessError("unexpected tSQLt test set")

    runner_code = schema_code_mask(runner_text)
    if re.search(r"\bRunAll\b", runner_text, re.I):
        raise SqlHarnessError("RunAll is forbidden")
    if re.search(r"(?m)^\s*(?::|!!)", runner_code):
        raise SqlHarnessError("runner contains a sqlcmd directive")
    call_pattern = re.compile(
        r"\bEXEC(?:UTE)?\s+((?:\[[A-Za-z0-9_]+\]|[A-Za-z0-9_]+)\."
        r"(?:\[[A-Za-z0-9_]+\]|[A-Za-z0-9_]+))", re.I)
    calls = [(match.start(), match.group(1).replace("[", "").replace("]", "").casefold())
             for match in call_pattern.finditer(runner_text)
             if runner_code[match.start():match.start() + 4].upper() == "EXEC"]
    expected_calls = ["tsqlt.run", "tsqlt.run", "tsqlt.faketable",
                      "dbo.getreordercandidates"]
    if (len(re.findall(r"\bEXEC(?:UTE)?\b", runner_code, re.I)) != 4 or
            [name for _position, name in calls] != expected_calls):
        raise SqlHarnessError("runner must call only two classes and direct order probe")
    run_args = re.findall(
        r"\bEXEC\s+(?:tSQLt\.Run|\[tSQLt\]\.\[Run\])\s+"
        r"@TestName\s*=\s*N?'([^']+)'", runner_text, re.I)
    if run_args != list(TEST_CLASSES):
        raise SqlHarnessError("runner must call only two classes and direct order probe")
    result_markers = [match.start() for match in re.finditer(r"PV_TEST_RESULT\|", runner_text)]
    begin_markers = [match.start() for match in re.finditer(r"PV_ORDER_BEGIN", runner_text)]
    end_markers = [match.start() for match in re.finditer(r"PV_ORDER_END", runner_text)]
    if (len(result_markers) != 2 or len(begin_markers) != 1 or
            len(end_markers) != 1 or not
            (calls[0][0] < result_markers[0] < calls[1][0] < result_markers[1]
             < calls[2][0] < begin_markers[0] < calls[3][0] < end_markers[0]) or
            runner_code.upper().count("BEGIN TRANSACTION") != 1 or
            runner_code.upper().count("ROLLBACK TRANSACTION") != 2):
        raise SqlHarnessError("runner result/order boundary is incomplete")
    return TEST_NAMES


def verify_test_files(directory: Path = TEST_SOURCE.parent) -> None:
    names = sorted(file.name for file in directory.glob("*.sql") if file.is_file())
    if names != ["GetReorderCandidatesTests.sql", "SqlHarnessSmoke.sql", "run-tests.sql"]:
        raise SqlHarnessError("unexpected SQL test source file")


def parse_test_results(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "PV_TEST_RESULT|" not in line:
            continue
        fields = line.strip().split("|")
        if len(fields) != 3 or fields[0] != "PV_TEST_RESULT" or fields[1] in result:
            raise SqlHarnessError("invalid or duplicate tSQLt result")
        result[fields[1]] = fields[2]
    if set(result) != set(TEST_NAMES):
        raise SqlHarnessError("tSQLt result does not match current test set")
    if any(value.casefold() != "success" for value in result.values()):
        raise SqlHarnessError("test_failure")
    return result


def existing_classes_are_safe(output: str, *, allow_unmarked: set[str] | None = None,
                              require_tests: bool = False) -> set[str]:
    """Return missing classes; reject foreign owners and any test collision."""
    allowed = allow_unmarked or set()
    classes: dict[str, str] = {}
    existing: dict[str, list[str]] = {name: [] for name in TEST_CLASSES}
    for line in output.splitlines():
        fields = line.strip().split("|")
        if fields[0] == "PV_CLASS":
            if (len(fields) != 3 or fields[1] not in TEST_CLASSES or
                    fields[1] in classes or fields[2] not in
                    {"missing", "marked", "unmarked"}):
                raise SqlHarnessError("dev test class state is ambiguous")
            classes[fields[1]] = fields[2]
        elif fields[0] == "PV_EXISTING_TEST":
            if len(fields) != 3 or fields[1] not in TEST_CLASSES:
                raise SqlHarnessError("dev test class contains an unexpected test")
            existing[fields[1]].append(fields[2])
    if set(classes) != set(TEST_CLASSES):
        raise SqlHarnessError("dev test class state is ambiguous")
    for name in TEST_CLASSES:
        state = classes[name]
        if state == "unmarked" and name not in allowed:
            raise SqlHarnessError("dev test class state is ambiguous")
        expected = {item.split(".", 1)[1] for item in TEST_NAMES
                    if item.startswith(name + ".")}
        found = existing[name]
        if (state == "missing" and found or
                (state != "missing" and (len(found) != len(expected) or
                                         set(found) != expected)) or
                (require_tests and state == "missing")):
            raise SqlHarnessError("dev test class contains an unexpected test")
    return {name for name, state in classes.items() if state == "missing"}


def parse_order_rows(output: str) -> tuple[int, ...]:
    lines = [line.strip() for line in output.splitlines()]
    begin = [index for index, line in enumerate(lines) if line == "PV_ORDER_BEGIN"]
    end = [index for index, line in enumerate(lines) if line == "PV_ORDER_END"]
    if len(begin) != 1 or len(end) != 1 or begin[0] >= end[0]:
        raise SqlHarnessError("direct order observer markers missing or duplicate")
    rows = []
    for line in lines[begin[0] + 1:end[0]]:
        if not line:
            continue
        fields = tuple(field.strip() for field in line.split("|"))
        if len(fields) != 3 or not fields[0].isdigit() or not fields[2].isdigit():
            raise SqlHarnessError("direct order observer output invalid")
        rows.append((int(fields[0]), fields[1], int(fields[2])))
    if rows != [(10, "Order10", 5), (20, "Order20", 5), (30, "Order30", 5)]:
        raise SqlHarnessError("direct order observer sequence mismatch")
    return tuple(row[0] for row in rows)


def junit_xml(names: tuple[str, ...] = TEST_NAMES, *, failure: str | None = None) -> str:
    suite = ET.Element("testsuite", name="Northwind.Tests", tests=str(len(names)),
                       failures="0" if failure is None else "1", errors="0")
    for index, name in enumerate(names):
        class_name, test_name = name.split(".", 1)
        case = ET.SubElement(suite, "testcase", classname=class_name, name=test_name)
        if failure is not None and index == 0:
            ET.SubElement(case, "failure", type=xml_safe(failure)).text = xml_safe(failure)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def junit_matches(xml: str, expected: tuple[str, ...] = TEST_NAMES) -> bool:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return False
    if (root.tag != "testsuite" or root.get("name") != "Northwind.Tests" or
            root.get("tests") != str(len(expected)) or
            root.get("failures") != "0" or root.get("errors") != "0"):
        return False
    cases = root.findall("testcase")
    actual = tuple(c.get("classname", "") + "." + c.get("name", "") for c in cases)
    return (len(root) == len(cases) and len(set(actual)) == len(expected) and
            set(actual) == set(expected) and
            all(len(c) == 0 for c in cases))


def reusable_proof(*, proof_bytes: dict[str, bytes], current_bytes: dict[str, bytes],
                   proof_commit: str, current_commit: str, actual_rc: int,
                   xml: str, tests: tuple[str, ...]) -> bool:
    """In-memory equality check only; no persisted fingerprint/receipt schema."""
    return (actual_rc == 0 and proof_commit == current_commit and
            bool(proof_bytes) and proof_bytes.keys() == current_bytes.keys() and
            all(proof_bytes[key] == current_bytes[key] for key in proof_bytes) and
            tests == TEST_NAMES and junit_matches(xml, tests))


def current_proof_bytes(draft: Path = CODE_DRAFT, root: Path = ROOT) -> dict[str, bytes]:
    """Read current executable/config targets from the native code draft."""
    match = re.search(r"## Meta \(machine-readable JSON\)\s*```json\s*(.*?)\s*```",
                      draft.read_text(encoding="utf-8"), re.S)
    if match is None:
        raise SqlHarnessError("code draft target carrier missing")
    try:
        targets = json.loads(match.group(1))["code_draft_meta"]["targets"]
        names = [item["path"] for item in targets if item["kind"] != "doc"]
    except (ValueError, KeyError, TypeError):
        raise SqlHarnessError("code draft target carrier invalid") from None
    if not names or len(names) != len(set(names)):
        raise SqlHarnessError("code draft executable targets ambiguous")
    result: dict[str, bytes] = {}
    for name in names:
        if name.startswith("/") or ".." in Path(name).parts:
            raise SqlHarnessError("code draft target path invalid")
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise SqlHarnessError("code draft executable target missing")
        result[name] = file.read_bytes()
    return result


def unique_file(directory: Path, name: str) -> Path:
    matches = [item for item in directory.rglob(name) if item.is_file() and not item.is_symlink()]
    if len(matches) != 1:
        raise SqlHarnessError(f"missing or ambiguous build artifact: {name}")
    return matches[0]


def publish_args(connection: Connection, dacpac: Path) -> list[str]:
    return sqlpackage("Publish", [
        f"/SourceFile:{dacpac}", f"/TargetServerName:{connection.server}",
        f"/TargetDatabaseName:{connection.dev_database}",
        f"/TargetUser:{connection.user}", f"/TargetPassword:{connection.password}",
        "/TargetEncryptConnection:True", "/TargetTrustServerCertificate:True",
        "/p:IncludeCompositeObjects=True",
        "/p:DropObjectsNotInSource=false",
        "/p:DropExtendedPropertiesNotInSource=false",
        "/p:BlockOnPossibleDataLoss=true",
        "/p:CreateNewDatabase=false",
    ])


def sqlcmd_args(connection: Connection, *extra: str) -> list[str]:
    return ["sqlcmd", "--encrypt-connection=mandatory", "-C", "-b", "-r1",
            "-S", connection.server, "-d", connection.dev_database,
            "-U", connection.user, *extra]


def setup() -> None:
    env = local_environment()
    version = run_command(["dotnet", "--version"], stage="setup", env=env)
    if version.strip() != "10.0.401":
        raise SqlHarnessError("required .NET SDK 10.0.401 is unavailable")
    run_command(["dotnet", "tool", "restore", "--tool-manifest",
                 ".config/dotnet-tools.json"], stage="setup", env=env)
    for project in ("sql/Northwind/Northwind.sqlproj", "sql/tests/Northwind.Tests.sqlproj"):
        run_command(["dotnet", "restore", project], stage="setup", env=env)
    venv = ROOT / ".tmp/sql-venv"
    run_command([sys.executable, "-m", "venv", str(venv)], stage="setup", env=env)
    run_command([str(venv / "bin/pip"), "install", "--disable-pip-version-check",
                 "--no-input", "sqlfluff==3.4.2"], stage="setup", env=env)


def db_extract() -> None:
    connection = load_connection()
    env = local_environment()
    staging = ROOT / ".tmp/sql-extract"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="Northwind-", suffix=".sql", dir=staging,
                                     delete=False) as handle:
        candidate = Path(handle.name)
    try:
        run_command(extract_args(connection, candidate), stage="extract", env=env,
                    values=connection.values)
        normalized = omit_source_environment_security(candidate.read_bytes(), connection.user)
        if schema_evidence_contains_secrets([normalized], connection):
            raise SqlHarnessError("Northwind Extract contains a local connection value")
        try:
            validate_schema(normalized.decode("utf-8-sig"))
        except UnicodeError:
            raise SqlHarnessError("Northwind Extract: неожиданная security DDL") from None
        candidate.write_bytes(normalized)
        os.replace(candidate, SQL_SOURCE)
    finally:
        candidate.unlink(missing_ok=True)


def db_build() -> None:
    validate_schema(SQL_SOURCE.read_text(encoding="utf-8-sig"))
    verify_test_files()
    current_test_set(TEST_SOURCE.read_text(encoding="utf-8"),
                     CONTENT_TEST_SOURCE.read_text(encoding="utf-8"),
                     TEST_RUNNER.read_text(encoding="utf-8"))
    env = local_environment()
    for project in ("sql/Northwind/Northwind.sqlproj", "sql/tests/Northwind.Tests.sqlproj"):
        run_command(["dotnet", "build", project, "--no-restore"],
                    stage="build", env=env, show_output=True)


def lint() -> None:
    validate_schema(SQL_SOURCE.read_text(encoding="utf-8-sig"))
    sqlfluff = ROOT / ".tmp/sql-venv/bin/sqlfluff"
    if not sqlfluff.is_file():
        raise SqlHarnessError("sqlfluff 3.4.2 local installation missing")
    env = local_environment()
    env["PIP_NO_INDEX"] = "1"
    version = run_command([str(sqlfluff), "--version"], stage="lint", env=env,
                          show_output=True)
    if not re.search(r"(?<!\d)3\.4\.2(?!\d)", version):
        raise SqlHarnessError("required SQLFluff 3.4.2 is unavailable")

    generated = "sql/Northwind/Northwind.sql"
    authored: list[str] = []
    for path in (ROOT / "sql").rglob("*"):
        relative = path.relative_to(ROOT)
        if path.suffix.lower() != ".sql" or {"bin", "obj"} & set(relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            raise SqlHarnessError("authored SQL source must be a regular file")
        name = relative.as_posix()
        if name != generated:
            authored.append(name)
    authored.sort()
    if not {"sql/Northwind/GetReorderCandidates.sql",
            "sql/tests/GetReorderCandidatesTests.sql",
            "sql/tests/SqlHarnessSmoke.sql", "sql/tests/run-tests.sql"}.issubset(authored):
        raise SqlHarnessError("authored SQL source inventory incomplete")

    def check_sqlfluff(argv: list[str], *, generated_lane: bool) -> None:
        try:
            result = subprocess.run(argv, cwd=ROOT, env=env, text=True,
                                    encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    check=False)
        except (OSError, ValueError):
            raise CommandFailure("tool_unavailable", 127) from None
        clean_out, clean_err = scrub(result.stdout), scrub(result.stderr)
        tool_diagnostic = bool(re.search(
            r"(?im)^\s*(?:user error|error|traceback)\b", clean_out + "\n" + clean_err))
        if generated_lane:
            # Human parse output contains the entire imported SQL tree. Release
            # only positions and diagnostic codes, never that tree or SQL text.
            diagnostics = re.findall(
                r"(?m)^\s*L:\s*(\d+)\s*\|\s*P:\s*(\d+)\s*\|\s*(PRS|LXR|TMP)\b",
                clean_out + "\n" + clean_err)
            violation_header = bool(re.search(
                r"(?im)^=+\s*(?:parsing|lexing|templating) violations\s*=+\s*$|"
                r"^WARNING:\s*(?:Parsing|Lexing|Templating) errors found",
                clean_out + "\n" + clean_err))
            for line, position, code in diagnostics:
                print(f"SQLFluff generated {code} at L:{line} P:{position}")
            if violation_header and not diagnostics:
                print("SQLFluff generated parser diagnostic without position")
            if tool_diagnostic:
                print("SQLFluff generated tool diagnostic")
            has_diagnostics = bool(diagnostics) or violation_header or tool_diagnostic
        else:
            has_diagnostics = bool(re.search(
                r"(?m)^== .* FAIL\s*$|^\s*L:\s*\d+\s*\|\s*P:\s*\d+\s*\|\s*(?:[A-Z]{2,3}\d{2}|PRS|LXR|TMP)\b",
                clean_out + "\n" + clean_err)) or tool_diagnostic
            if clean_out:
                print(clean_out, end="" if clean_out.endswith("\n") else "\n")
            if clean_err:
                print(clean_err, end="" if clean_err.endswith("\n") else "\n",
                      file=sys.stderr)
        if result.returncode:
            if not has_diagnostics:
                lane = "parse" if generated_lane else "lint"
                raise CommandFailure(f"sqlfluff_{lane}_missing_diagnostics",
                                     result.returncode)
            category = ("tool_failure" if result.returncode != 1 or tool_diagnostic else
                        "parser_failure" if generated_lane or re.search(
                            r"\b(?:PRS|LXR|TMP)\b", clean_out + clean_err) else
                        "lint_failure")
            raise CommandFailure(category, result.returncode)
        if has_diagnostics:
            raise SqlHarnessError("SQLFluff reported diagnostics with zero exit status")

    check_sqlfluff([str(sqlfluff), "parse", "--dialect", "tsql", "--templater",
                    "raw", generated], generated_lane=True)
    check_sqlfluff([str(sqlfluff), "lint", "--disable-progress-bar", "--dialect",
                    "tsql", "--templater", "raw", *authored], generated_lane=False)


def secret_variants(values: tuple[str, ...]) -> set[bytes]:
    return {token.encode("utf-8") for token in redaction_tokens(values)}


def assets_contain_secrets(blobs: list[bytes], values: tuple[str, ...]) -> bool:
    variants = secret_variants(values)
    return any(secret in blob for blob in blobs for secret in variants)


def schema_evidence_contains_secrets(blobs: list[bytes], connection: Connection) -> bool:
    """Check local values and the SQL bracket-escaped login identifier silently."""
    quoted_user = ("[" + connection.user.replace("]", "]]") + "]").encode("utf-8")
    return (assets_contain_secrets(blobs, connection.values) or
            any(quoted_user in blob for blob in blobs))


def check_secrets() -> None:
    connection = load_connection()
    if SQL_SOURCE.is_symlink() or not SQL_SOURCE.is_file():
        raise SqlHarnessError("Northwind schema source must be a regular file")
    if schema_evidence_contains_secrets([SQL_SOURCE.read_bytes()], connection):
        raise SqlHarnessError("Northwind schema source contains a local connection value")
    asset_directories = (
        ROOT / "docs/code_reviews/assets/260927_1913_sql_server_adaptation",
        JUNIT.parent,
    )
    if not any(assets.exists() for assets in asset_directories):
        print("check-secrets: no review assets yet")
        return
    for assets in asset_directories:
        if not assets.exists():
            continue
        if assets.is_symlink():
            raise SqlHarnessError("review assets path must not be a symlink")
        for file in assets.rglob("*"):
            if file.is_symlink():
                raise SqlHarnessError("review assets contain a symlink")
            if file.is_file() and schema_evidence_contains_secrets([file.read_bytes()], connection):
                raise SqlHarnessError("review asset contains a local connection value")
    print("check-secrets: review assets contain no local connection values")


def write_junit(xml: str) -> None:
    if JUNIT.is_symlink():
        raise SqlHarnessError("JUnit asset must not be a symlink")
    JUNIT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".xml",
                                     dir=JUNIT.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(xml)
    os.replace(temporary, JUNIT)


def failure_junit(category: str) -> str:
    suite = ET.Element("testsuite", name="Northwind.Tests", tests="0",
                       failures="0", errors="1")
    ET.SubElement(suite, "error", type=category).text = category
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def db_proof() -> None:
    connection = load_connection()
    verify_test_files()
    expected = current_test_set(TEST_SOURCE.read_text(encoding="utf-8"),
                                CONTENT_TEST_SOURCE.read_text(encoding="utf-8"),
                                TEST_RUNNER.read_text(encoding="utf-8"))
    validate_schema(SQL_SOURCE.read_text(encoding="utf-8-sig"))
    if shutil.which("sqlcmd") is None:
        raise SqlHarnessError("sqlcmd unavailable; no database publication attempted")
    before_bytes = current_proof_bytes()
    # Rebuild the current sources before any publication; cached dacpacs alone
    # are never sufficient evidence of current SQL bytes.
    db_build()
    lint()
    test_dacpac = unique_file(ROOT / "sql/tests/bin", "Northwind.Tests.dacpac")
    env = local_environment()
    sqlcmd_env = dict(env)
    sqlcmd_env["SQLCMDPASSWORD"] = connection.password
    commit = run_command(["git", "rev-parse", "HEAD"], stage="metadata", env=env,
                         values=connection.values).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SqlHarnessError("source commit readback unavailable")
    class_query = (
        "SELECT N'PV_CLASS|' + c.name + N'|' + CASE WHEN SCHEMA_ID(c.name) IS NULL "
        "THEN N'missing' WHEN EXISTS (SELECT 1 FROM sys.extended_properties e "
        "WHERE e.class=3 AND e.major_id=SCHEMA_ID(c.name) "
        "AND e.name=N'tSQLt.TestClass') THEN N'marked' ELSE N'unmarked' END "
        "FROM (VALUES (N'SqlHarnessSmoke'), (N'GetReorderCandidatesTests')) c(name); "
        "SELECT N'PV_EXISTING_TEST|' + s.name + N'|' + p.name FROM sys.procedures p "
        "JOIN sys.schemas s ON p.schema_id=s.schema_id "
        "WHERE s.name IN (N'SqlHarnessSmoke', N'GetReorderCandidatesTests');"
    )
    try:
        class_output = run_command(sqlcmd_args(connection, "-h", "-1", "-W", "-Q", class_query),
                                   stage="test", env=sqlcmd_env, values=connection.values)
        missing_classes = existing_classes_are_safe(class_output)
        # ProjectReference + PackageReference/DacpacName make one composite
        # test DACPAC containing Northwind, tSQLt and both authored classes.
        run_command(publish_args(connection, test_dacpac), stage="publish", env=env,
                    values=connection.values)
        after_publish = run_command(sqlcmd_args(connection, "-h", "-1", "-W", "-Q", class_query),
                                    stage="test", env=sqlcmd_env, values=connection.values)
        existing_classes_are_safe(after_publish, allow_unmarked=missing_classes,
                                  require_tests=True)
        # Mark only newly published classes, without recreating either schema.
        for class_name in sorted(missing_classes):
            marker_sql = (
                "EXEC sys.sp_addextendedproperty @name=N'tSQLt.TestClass', @value=1, "
                f"@level0type=N'SCHEMA', @level0name=N'{class_name}';"
            )
            run_command(sqlcmd_args(connection, "-Q", marker_sql),
                        stage="test", env=sqlcmd_env, values=connection.values)
        final_classes = run_command(sqlcmd_args(connection, "-h", "-1", "-W", "-Q", class_query),
                                    stage="test", env=sqlcmd_env, values=connection.values)
        existing_classes_are_safe(final_classes, require_tests=True)
        output = run_command(sqlcmd_args(connection, "-h", "-1", "-W", "-s", "|",
                                         "-i", str(TEST_RUNNER)),
                             stage="test", env=sqlcmd_env, values=connection.values)
        parse_test_results(output)
        parse_order_rows(output)
    except CommandFailure as exc:
        write_junit(failure_junit(exc.category))
        raise
    except SqlHarnessError:
        write_junit(failure_junit("test_failure"))
        raise
    xml = junit_xml(expected)
    write_junit(xml)
    after_commit = run_command(["git", "rev-parse", "HEAD"], stage="metadata", env=env,
                               values=connection.values).strip()
    if not reusable_proof(proof_bytes=before_bytes, current_bytes=current_proof_bytes(),
                          proof_commit=commit, current_commit=after_commit,
                          actual_rc=0, xml=JUNIT.read_text(encoding="utf-8"), tests=expected):
        write_junit(failure_junit("stale_proof"))
        raise SqlHarnessError("current source or JUnit readback changed during db-proof")
    print(f"db-proof: source_commit={commit}; current classes/results/order verified; actual_rc=0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local SQL rehearsal harness")
    parser.add_argument("action", choices=("setup", "db-extract", "db-build", "lint",
                                            "check-secrets", "db-proof"))
    arguments = parser.parse_args(argv)
    operations = {
        "setup": setup, "db-extract": db_extract, "db-build": db_build,
        "lint": lint, "check-secrets": check_secrets, "db-proof": db_proof,
    }
    try:
        operations[arguments.action]()
    except CommandFailure as exc:
        print(f"{arguments.action}: {exc}", file=sys.stderr)
        return 1
    except (SqlHarnessError, OSError, UnicodeError) as exc:
        # SqlHarnessError messages are fixed; raw OSError may include an argv
        # or a sensitive path, so never stringify it.
        message = str(exc) if isinstance(exc, SqlHarnessError) else "local input/output failure"
        print(f"{arguments.action}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

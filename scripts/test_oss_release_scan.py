#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "scripts" / "oss_release_scan.py"
if str(SCANNER.parent) not in sys.path:
    sys.path.insert(0, str(SCANNER.parent))
import oss_release_scan as scan_mod


_UNSET = object()


def secret_value() -> str:
    return "synthetic" + "A1B2C3D4E5F6G7"


def github_value() -> str:
    return "ghp_" + ("A" * 20)


def slack_value() -> str:
    return "xoxb-" + ("a" * 16)


def bearer_value() -> str:
    return "Bearer " + ("b" * 16)


def security_contact() -> str:
    return "security" + "@" + "planveyor.dev"


def generic_home() -> str:
    return "/" + "home" + "/" + "fixture-user"


def generic_windows_home() -> str:
    return "C:" + "\\" + "Users" + "\\" + "fixture-user"


def private_key_header() -> str:
    return "-----BEGIN " + "OPENSSH PRIVATE " + "KEY-----"


def credential_url() -> str:
    return "https" + "://" + "user" + ":" + "pass" + "@" + "host.invalid"


def google_api_key() -> str:
    return "AI" + "za" + ("A" * 35)


def non_http_credential_url(scheme: str) -> str:
    return scheme + "://" + "user" + ":" + "pass" + "@" + "localhost"


def empty_user_credential_url() -> str:
    return "redis" + "://" + ":" + "diagnostic" + "-" + "pass" + "@" + "host"


def dotted_quad(*parts: str) -> str:
    return ".".join(parts)


def phone_without_plus() -> str:
    return "1" + " 202" + "-555" + "-0147"


def legacy_parenthesized_phone() -> str:
    return "phone_" + "(" + "202" + ")" + " " + "555" + "-0147"


def scanner_gap_negative_values() -> tuple[str, str, str, str]:
    uuid = "00000000" + "-0000" + "-4000" + "-8000" + "-000000000001"
    date = "2026" + "-09" + "-19"
    version = "1" + ".202.555.0147"
    identifier = "build" + "-" + phone_without_plus()
    return uuid, date, version, identifier


def identity_bundle() -> str:
    email = "ops" + "@" + "private.invalid"
    phone = "+" + "1 202" + "-555" + "-0147"
    address = "10" + "." + "77" + "." + "88" + "." + "99"
    host = "build" + "." + "internal"
    return " ".join((email, phone, address, host))


class OssReleaseScanTests(unittest.TestCase):
    def make_repo(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="oss_scan_git_")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        proc = subprocess.run(["git", "init", "-q"], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return root

    def write(self, root: Path, rel: str, text: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_bytes(self, root: Path, rel: str, content: bytes) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def track(self, root: Path, *rels: str) -> None:
        proc = subprocess.run(["git", "add", "--", *rels], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def run_scan(
        self,
        root: Path,
        *args: str,
        marker: object = _UNSET,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.pop(scan_mod.MARKER_ENV, None)
        if marker is not _UNSET:
            env[scan_mod.MARKER_ENV] = str(marker)
        return subprocess.run(
            [sys.executable, "-B", str(SCANNER), "--root", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def json_scan(self, root: Path, *args: str, marker: object = _UNSET) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self.run_scan(root, "--format", "json", "--fail-on", "never", *args, marker=marker)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result, json.loads(result.stdout)

    def assert_input_error(self, result: subprocess.CompletedProcess[str], *forbidden: str) -> None:
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: scanner input is invalid\n")
        for value in forbidden:
            self.assertNotIn(value, result.stderr)

    def external_markers(self, root: Path, content: str) -> Path:
        markers = root.parent / f"{root.name}-external-markers.txt"
        markers.write_text(content, encoding="utf-8")
        return markers

    def manifest(self, parent: Path, items: list[dict[str, object]], *, schema: str = "oss-evidence-manifest.v1") -> Path:
        path = parent / "manifest.json"
        path.write_text(json.dumps({"schema_version": schema, "items": items}) + "\n", encoding="utf-8")
        return path

    def evidence_item(self, path: str = "docs/evidence/canon_notes/policy.md") -> dict[str, object]:
        return {
            "public_path": path,
            "category": "canon_notes",
            "why_included": "synthetic public evidence",
            "sanitization_status": "pending",
        }

    def test_non_git_and_nested_root_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_scan_non_git_") as temporary:
            non_git = Path(temporary)
            self.write(non_git, "README.md", "safe\n")
            self.assert_input_error(self.run_scan(non_git, "--format", "json"))
        root = self.make_repo()
        self.write(root, "nested/README.md", "safe\n")
        self.track(root, "nested/README.md")
        self.assert_input_error(self.run_scan(root / "nested", "--format", "json"))

    def test_direct_git_failure_is_typed(self) -> None:
        root = self.make_repo()
        self.write(root, "README.md", "safe\n")
        self.track(root, "README.md")
        with mock.patch.object(scan_mod, "_run_git", side_effect=scan_mod.ScanInputError("x")):
            with self.assertRaises(scan_mod.ScanInputError):
                scan_mod.scan(root, "public-copy")

    def test_unset_marker_env_is_generic_only(self) -> None:
        root = self.make_repo()
        self.write(root, "README.md", "acme-private marker\n" + identity_bundle() + "\n")
        self.track(root, "README.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy")
        categories = {item["category"] for item in payload["findings"]}
        self.assertNotIn("private_marker", categories)
        self.assertTrue({"email", "phone", "ip_address", "internal_hostname"} <= categories)

    def test_explicit_marker_dictionary_fail_closed_matrix(self) -> None:
        root = self.make_repo()
        self.write(root, "README.md", "safe\n")
        self.track(root, "README.md")
        outside = root.parent / f"{root.name}-outside"
        outside.mkdir()
        missing = outside / "missing.txt"
        directory = outside / "marker-directory"
        directory.mkdir()
        invalid_utf8 = outside / "invalid-utf8.txt"
        invalid_utf8.write_bytes(bytes((0xFF, 0xFE)))
        malformed = outside / "malformed.txt"
        malformed.write_text("re:(\n", encoding="utf-8")
        zero_width = outside / "zero-width.txt"
        zero_width.write_text("re:^\n", encoding="utf-8")
        valid = outside / "valid.txt"
        valid.write_text("acme_private\n", encoding="utf-8")
        empty = outside / "empty.txt"
        empty.write_text("", encoding="utf-8")
        comment_only = outside / "comment-only.txt"
        comment_only.write_text("# comment only\n  # another comment\n\n", encoding="utf-8")
        empty_path = outside / "empty-path.txt"
        empty_path.write_text("path:\n", encoding="utf-8")
        empty_author = outside / "empty-author.txt"
        empty_author.write_text("author: \n", encoding="utf-8")
        inside = root / "inside-markers.txt"
        inside.write_text("acme_private\n", encoding="utf-8")
        link = outside / "marker-link.txt"
        link.symlink_to(valid)
        values: list[object] = [
            "relative-markers.txt",
            str(missing),
            str(directory),
            str(invalid_utf8),
            str(malformed),
            str(zero_width),
            str(empty),
            str(comment_only),
            str(empty_path),
            str(empty_author),
            str(inside),
            str(link),
        ]
        for value in values:
            with self.subTest(marker=value):
                self.assert_input_error(self.run_scan(root, "--format", "json", marker=value), str(value))

    def test_marker_dictionary_rejects_case_alias_inside_root(self) -> None:
        root = self.make_repo()
        self.write(root, "README.md", "safe\n")
        self.track(root, "README.md")
        alias = root.with_name(root.name.upper())
        if not alias.exists() or not alias.samefile(root):
            self.skipTest("filesystem has no case-insensitive alias")
        marker = alias / "case-alias-markers.txt"
        marker.write_text("acme_private\n", encoding="utf-8")
        self.assert_input_error(self.run_scan(root, "--format", "json", marker=marker), str(marker))

    def test_prefixed_secret_assignment_names_are_detected(self) -> None:
        root = self.make_repo()
        value = "synthetic-example-A1B2C3D4E5F6G7"
        self.write(
            root,
            "README.md",
            "DATABASE_PASSWORD=" + value + "\nMY_SECRET=" + value + "\nSESSION_TOKEN=" + value
            + "\nSERVICE_API_KEY=" + value + "\nTOKEN_COUNT=" + value + "\nPASSWORD_POLICY=" + value + "\n",
        )
        self.track(root, "README.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy")
        findings = [item for item in payload["findings"] if item["category"] == "secret_like"]
        self.assertEqual({item["line"] for item in findings}, {1, 2, 3, 4})
        self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in findings))

    def test_marker_separator_folding_and_near_miss(self) -> None:
        root = self.make_repo()
        marker = self.external_markers(root, "# public synthetic dictionary\nacme_private\n")
        variants = "Acme-private acme.private acme private acmeprivate acmeXprivate\n"
        self.write(root, "README.md", variants)
        self.track(root, "README.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy", marker=marker)
        findings = [item for item in payload["findings"] if item["category"] == "private_marker"]
        self.assertEqual(len(findings), 4)
        self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in findings))

    def test_author_marker_context_suffix_and_home_path(self) -> None:
        root = self.make_repo()
        marker = self.external_markers(root, "author:acme_maintainer\n")
        home = "/" + "Users" + "/" + "fixture-user"
        self.write(root, "LICENSE", "Copyright 2026 acme_maintainer\n")
        self.write(root, "NOTICE", "Licensor acme_maintainer\n")
        self.write(root, "README.md", "acme_maintainer18\n")
        self.write(root, "docs/NOTICE", "Copyright 2026 acme_maintainer\n")
        self.write(root, "legal.md", "Narrative acme_maintainer\n")
        self.write(root, "licensed-path.md", "Copyright 2026 acme_maintainer " + home + "\n")
        self.track(root, "LICENSE", "NOTICE", "README.md", "docs/NOTICE", "legal.md", "licensed-path.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy", marker=marker)
        identities = [item for item in payload["findings"] if item["category"] == "owner_identity"]
        paths = {item["path"] for item in identities}
        self.assertEqual(paths, {"README.md", "docs/NOTICE", "legal.md", "licensed-path.md"})
        self.assertTrue(all(item["severity"] == "blocker" and item["token"] == scan_mod.MASKED_TOKEN for item in identities))
        personal = [item for item in payload["findings"] if item["category"] == "personal_path"]
        self.assertEqual({item["path"] for item in personal}, {"licensed-path.md"})

    def test_author_marker_legal_allowance_requires_an_exact_bare_identity(self) -> None:
        root = self.make_repo()
        marker = self.external_markers(root, "author:acme_maintainer\n")
        legal_lines = "\n".join((
            "Copyright 2026 acme_maintainer",
            "Copyright 2026 acme_maintainer7",
            "Copyright 2026 acme_maintainer-suffix",
            "Copyright 2026 acme_maintainer.suffix",
            "Copyright 2026 x-acme_maintainer",
            "Copyright 2026 x.acme_maintainer",
        )) + "\n"
        self.write(root, "LICENSE", legal_lines)
        self.write(root, "NOTICE", legal_lines)
        self.write(root, "docs/NOTICE", "Copyright 2026 acme_maintainer\n")
        self.track(root, "LICENSE", "NOTICE", "docs/NOTICE")
        _result, payload = self.json_scan(root, "--scope", "public-copy", marker=marker)
        identities = [item for item in payload["findings"] if item["category"] == "owner_identity"]
        expected = {(path, line) for path in ("LICENSE", "NOTICE") for line in range(2, 7)}
        expected.add(("docs/NOTICE", 1))
        self.assertEqual({(item["path"], item["line"]) for item in identities}, expected)
        self.assertTrue(all(item["severity"] == "blocker" and item["token"] == scan_mod.MASKED_TOKEN for item in identities))

    def test_tracked_deleted_file_fails_closed(self) -> None:
        root = self.make_repo()
        path = self.write(root, "gone.md", "safe\n")
        self.track(root, "gone.md")
        path.unlink()
        self.assert_input_error(self.run_scan(root, "--scope", "public-copy", "--format", "json"))

    def test_git_inventory_uses_tracked_nul_records_only(self) -> None:
        root = self.make_repo()
        tracked_token = secret_value()
        self.write(root, "tracked.md", "API_TOKEN=" + tracked_token + "\n")
        self.write(root, "untracked.md", "API_TOKEN=" + tracked_token + "\n")
        unusual = "docs/line\nbreak.md"
        escape_name = "docs/escape" + chr(27) + "name.md"
        self.write(root, unusual, "API_TOKEN=" + tracked_token + "\n")
        self.write(root, escape_name, "API_TOKEN=" + tracked_token + "\n")
        self.track(root, "tracked.md", unusual, escape_name)
        _result, payload = self.json_scan(root, "--scope", "public-copy")
        paths = {item["path"] for item in payload["findings"] if item["category"] == "secret_like"}
        self.assertIn("tracked.md", paths)
        self.assertIn(unusual, paths)
        self.assertIn(escape_name, paths)
        self.assertNotIn("untracked.md", paths)
        text_result = self.run_scan(root, "--scope", "public-copy", "--format", "text", "--fail-on", "never")
        self.assertIn("docs/line\\nbreak.md:1:", text_result.stdout)
        self.assertIn("docs/escape\\x1bname.md:1:", text_result.stdout)

    def test_generic_negative_controls_do_not_trigger_blockers(self) -> None:
        root = self.make_repo()
        uuid = "00000000" + "-0000" + "-4000" + "-8000" + "-000000000001"
        timestamp = "2026" + "-09" + "-19"
        package = "sample" + "@" + "1.2.3"
        self.write(root, "README.md", "trace=" + uuid + " date=" + timestamp + " token = helper_value package=" + package + "\n")
        self.track(root, "README.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy")
        self.assertEqual(payload["findings"], [])

    def test_binary_warning_line_zero_and_threshold(self) -> None:
        root = self.make_repo()
        self.write_bytes(root, "payload.dat", bytes((0xFF, 0x00, 0x80)))
        self.track(root, "payload.dat")
        never = self.run_scan(root, "--scope", "public-copy", "--format", "json", "--fail-on", "never")
        blocker = self.run_scan(root, "--scope", "public-copy", "--format", "json", "--fail-on", "blocker")
        warning = self.run_scan(root, "--scope", "public-copy", "--format", "json", "--fail-on", "warning")
        self.assertEqual(never.returncode, 0, never.stderr)
        self.assertEqual(blocker.returncode, 0, blocker.stderr)
        self.assertEqual(warning.returncode, 1, warning.stderr)
        payload = json.loads(never.stdout)
        self.assertEqual(payload["findings"], [{"path": "payload.dat", "line": 0, "category": "binary_file", "severity": "warning", "token": scan_mod.MASKED_TOKEN}])
        self.assertNotIn("ff", never.stdout.lower())

    def test_s0_generic_gap_detection_and_masking(self) -> None:
        root = self.make_repo()
        uuid, date, version, identifier = scanner_gap_negative_values()
        lines = [
            "01 " + google_api_key(),
            "02 " + non_http_credential_url("redis" + "+tls"),
            "03 " + non_http_credential_url("amqp"),
            "04 " + phone_without_plus(),
            "05 " + legacy_parenthesized_phone(),
            "06 date=" + date,
            "07 version=" + version,
            "08 trace=" + uuid,
            "09 identifier=" + identifier,
        ]
        self.write(root, "generic_gaps.txt", "\n".join(lines) + "\n")
        self.track(root, "generic_gaps.txt")
        result, payload = self.json_scan(root, "--scope", "public-copy")
        self.assertEqual(result.stderr, "")
        expected = {
            1: {"secret_like"},
            2: {"url_credentials"},
            3: {"url_credentials"},
            4: {"phone"},
            5: {"phone"},
        }
        observed = {
            line_no: {
                item["category"]
                for item in payload["findings"]
                if item["path"] == "generic_gaps.txt" and item["line"] == line_no and item["severity"] == "blocker"
            }
            for line_no in expected
        }
        self.assertEqual(observed, expected)
        negative_lines = {6, 7, 8, 9}
        negatives = [
            item
            for item in payload["findings"]
            if item["path"] == "generic_gaps.txt" and item["line"] in negative_lines
        ]
        self.assertEqual(negatives, [])
        self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in payload["findings"]))

    def test_empty_user_credentials_and_version_context(self) -> None:
        root = self.make_repo()
        version_quad = dotted_quad("1", "2", "3", "4")
        network_quad = dotted_quad("10", "27", "38", "49")
        lines = [
            "01 " + empty_user_credential_url(),
            "02 " + non_http_credential_url("redis"),
            "03 version " + version_quad,
            "04 " + version_quad,
            "05 server_ip=" + network_quad,
        ]
        self.write(root, "scanner_followups.txt", "\n".join(lines) + "\n")
        self.track(root, "scanner_followups.txt")

        result, payload = self.json_scan(root, "--scope", "public-copy")
        self.assertEqual(result.stderr, "")
        cli_findings = [item for item in payload["findings"] if item["path"] == "scanner_followups.txt"]

        direct_env = dict(os.environ)
        direct_env.pop(scan_mod.MARKER_ENV, None)
        with mock.patch.dict(os.environ, direct_env, clear=True):
            direct_findings = [
                finding
                for finding in scan_mod.scan(root, "public-copy")
                if finding.path == "scanner_followups.txt"
            ]

        expected = {
            1: {"url_credentials"},
            2: {"url_credentials"},
            3: set(),
            4: {"ip_address"},
            5: {"ip_address"},
        }
        cli_observed = {
            line_no: {item["category"] for item in cli_findings if item["line"] == line_no}
            for line_no in expected
        }
        direct_observed = {
            line_no: {finding.category for finding in direct_findings if finding.line == line_no}
            for line_no in expected
        }
        self.assertEqual(cli_observed, expected)
        self.assertEqual(direct_observed, expected)
        self.assertEqual(len(cli_findings), 4)
        self.assertEqual(len(direct_findings), 4)
        self.assertTrue(
            all(item["severity"] == "blocker" and item["token"] == scan_mod.MASKED_TOKEN for item in cli_findings)
        )
        self.assertTrue(
            all(finding.severity == "blocker" and finding.token == scan_mod.MASKED_TOKEN for finding in direct_findings)
        )

    def test_public_synthetic_eleven_record_category_map(self) -> None:
        root = self.make_repo()
        marker = self.external_markers(root, "acme_private\nauthor:acme_maintainer\n")
        lines = [
            "public synthetic scanner corpus",
            "01 acme-private",
            "02 acme_private",
            "03 " + generic_home() + " " + generic_windows_home(),
            "04 " + github_value(),
            "05 " + private_key_header(),
            "06 Authorization: " + bearer_value(),
            "07 " + slack_value(),
            "08 " + identity_bundle(),
            "09 acme_maintainer18",
            "10 " + credential_url(),
            "11 API_TOKEN=" + ("sk-" + "example" + ("a" * 16)),
        ]
        self.write(root, "synthetic_leaks.txt", "\n".join(lines) + "\n")
        self.track(root, "synthetic_leaks.txt")
        result, payload = self.json_scan(root, "--scope", "public-copy", marker=marker)
        self.assertEqual(result.stderr, "")
        expected = {
            2: {"private_marker"},
            3: {"private_marker"},
            4: {"personal_path"},
            5: {"github_token"},
            6: {"private_key"},
            7: {"bearer_token"},
            8: {"slack_token"},
            9: {"email", "phone", "ip_address", "internal_hostname"},
            10: {"owner_identity"},
            11: {"url_credentials"},
            12: {"secret_like"},
        }
        for line_no, categories in expected.items():
            observed = {
                item["category"]
                for item in payload["findings"]
                if item["path"] == "synthetic_leaks.txt" and item["line"] == line_no and item["severity"] == "blocker"
            }
            self.assertTrue(categories <= observed, (line_no, categories, observed))
        self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in payload["findings"]))

    def test_exact_security_contact_exception_has_no_broad_bypass(self) -> None:
        root = self.make_repo()
        self.write(root, "SECURITY.md", security_contact() + "\n")
        self.write(root, "SECURITY.ru.md", security_contact() + "\n")
        self.write(root, "README.md", security_contact() + "\n")
        self.write(root, "docs/SECURITY.ru.md", security_contact() + "\n")
        self.write(root, "docs/contact.md", "support" + "@" + "planveyor.dev\n")
        self.track(root, "SECURITY.md", "SECURITY.ru.md", "README.md", "docs/SECURITY.ru.md", "docs/contact.md")
        _result, payload = self.json_scan(root, "--scope", "public-copy")
        emails = [item for item in payload["findings"] if item["category"] == "email"]
        self.assertEqual({item["path"] for item in emails}, {"README.md", "docs/SECURITY.ru.md", "docs/contact.md"})

    def test_path_marker_is_masked_at_api_origin(self) -> None:
        root = self.make_repo()
        marker = self.external_markers(root, "acme_private\n")
        raw_marker = "acme_private"
        rel = "notes/" + raw_marker + ".md"
        self.write(root, rel, "safe\n")
        self.track(root, rel)
        env = dict(os.environ)
        env[scan_mod.MARKER_ENV] = str(marker)
        with mock.patch.dict(os.environ, env, clear=True):
            findings = scan_mod.scan(root, "public-copy")
        self.assertTrue(findings)
        self.assertTrue(all(raw_marker not in finding.path and finding.token == scan_mod.MASKED_TOKEN for finding in findings))
        result, payload = self.json_scan(root, "--scope", "public-copy", marker=marker)
        self.assertNotIn(raw_marker, result.stdout)
        self.assertTrue(all(raw_marker not in item["path"] for item in payload["findings"]))

    def test_tracked_symlink_fails_closed_without_following_target(self) -> None:
        root = self.make_repo()
        outside = root.parent / "outside-target.txt"
        outside.write_text("safe outside target\n", encoding="utf-8")
        (root / "linked.txt").symlink_to(outside)
        self.track(root, "linked.txt")
        self.assert_input_error(self.run_scan(root, "--scope", "public-copy", "--format", "json"))

    def test_copier_source_link_reads_only_tracked_in_repo_content(self) -> None:
        root = self.make_repo()
        source = self.write(root, "docs/playbooks/shared.md", "safe contract\n")
        link = root / "copier_template/docs/playbooks/shared.md"
        link.parent.mkdir(parents=True)
        link.symlink_to(source)
        self.track(root, "docs/playbooks/shared.md", "copier_template/docs/playbooks/shared.md")
        self.assertEqual(scan_mod.scan(root, "keep-set"), [])

        link.unlink()
        outside = root.parent / "outside-target.txt"
        outside.write_text("safe outside target\n", encoding="utf-8")
        link.symlink_to(outside)
        self.assert_input_error(self.run_scan(root, "--scope", "keep-set", "--format", "json"))

    def test_copier_directory_link_requires_tracked_regular_source_files(self) -> None:
        root = self.make_repo()
        self.write(root, "docs/playbooks/shared.md", "safe contract\n")
        link = root / "copier_template/docs/playbooks"
        link.parent.mkdir(parents=True)
        link.symlink_to(root / "docs/playbooks")
        self.track(root, "docs/playbooks/shared.md", "copier_template/docs/playbooks")
        self.assertEqual(scan_mod.scan(root, "keep-set"), [])

        self.write(root, "docs/playbooks/untracked.md", "not part of source inventory\n")
        self.assert_input_error(self.run_scan(root, "--scope", "keep-set", "--format", "json"))

    def test_copier_directory_link_cannot_hide_excluded_history(self) -> None:
        root = self.make_repo()
        self.write(root, "docs/plans/history.md", "owner path: " + generic_home() + "\n")
        link = root / "copier_template/docs/imported-history"
        link.parent.mkdir(parents=True)
        link.symlink_to(root / "docs/plans")
        self.track(root, "docs/plans/history.md", "copier_template/docs/imported-history")

        self.assert_input_error(self.run_scan(root, "--scope", "keep-set", "--format", "json"))
        findings = scan_mod.scan(root, "all")
        self.assertTrue(any(item.category == "personal_path" for item in findings))

    def test_reserved_initializer_email_is_not_a_personal_address(self) -> None:
        root = self.make_repo()
        self.write(root, "docs/identity.md", "Planveyor Initializer <planveyor-init@example.invalid>\n")
        self.track(root, "docs/identity.md")
        self.assertEqual(scan_mod.scan(root, "keep-set"), [])

    def test_scope_filters_apply_after_tracked_inventory(self) -> None:
        root = self.make_repo()
        token = secret_value()
        self.write(root, "docs/plans/old.md", "API_TOKEN=" + token + "\n")
        self.write(root, "docs/tools/live.md", "API_TOKEN=" + token + "\n")
        self.track(root, "docs/plans/old.md", "docs/tools/live.md")
        _keep_result, keep = self.json_scan(root, "--scope", "keep-set")
        _evidence_result, evidence = self.json_scan(root, "--scope", "evidence")
        self.assertEqual({item["path"] for item in keep["findings"]}, {"docs/tools/live.md"})
        self.assertEqual({item["path"] for item in evidence["findings"]}, {"docs/plans/old.md"})

    def test_renderers_and_api_mask_tokens(self) -> None:
        root = self.make_repo()
        token = secret_value()
        self.write(root, "leak.md", "API_TOKEN=" + token + "\n")
        self.track(root, "leak.md")
        text = self.run_scan(root, "--scope", "public-copy", "--format", "text", "--fail-on", "never")
        rendered, payload = self.json_scan(root, "--scope", "public-copy")
        direct_env = dict(os.environ)
        direct_env.pop(scan_mod.MARKER_ENV, None)
        with mock.patch.dict(os.environ, direct_env, clear=True):
            direct = scan_mod.scan(root, "public-copy")
        self.assertNotIn(token, text.stdout)
        self.assertNotIn(token, rendered.stdout)
        self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in payload["findings"]))
        self.assertTrue(all(finding.token == scan_mod.MASKED_TOKEN for finding in direct))

    def test_archive_manifest_exact_set_and_no_git_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_scan_archive_") as temporary:
            parent = Path(temporary)
            archive = parent / "staged"
            self.write(archive, "docs/evidence/canon_notes/policy.md", "safe public evidence\n")
            manifest = self.manifest(parent, [self.evidence_item()])
            result = self.run_scan(
                archive,
                "--archive-manifest",
                str(manifest),
                "--scope",
                "public-copy",
                "--format",
                "json",
                "--fail-on",
                "never",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout)["findings"], [])
            with mock.patch.object(scan_mod, "_run_git", side_effect=AssertionError("Git must not run")):
                self.assertEqual(scan_mod.scan(archive, "public-copy", archive_manifest=manifest), [])

    def test_archive_manifest_metadata_is_scanned_and_masked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_scan_archive_metadata_") as temporary:
            parent = Path(temporary)
            archive = parent / "staged"
            self.write(archive, "docs/evidence/canon_notes/policy.md", "safe public evidence\n")
            item = self.evidence_item()
            metadata_secret = "DATABASE" + "_PASSWORD=" + "synthetic-example-A1B2C3D4E5F6G7"
            item["why_included"] = metadata_secret
            item["sanitization_status"] = "acme_private"
            manifest = self.manifest(parent, [item])
            marker = self.external_markers(archive, "acme_private\n")
            result, payload = self.json_scan(
                archive,
                "--archive-manifest",
                str(manifest),
                "--scope",
                "public-copy",
                marker=marker,
            )
            findings = [item for item in payload["findings"] if item["line"] == 0]
            self.assertEqual({item["category"] for item in findings}, {"private_marker", "secret_like"})
            self.assertTrue(all(item["token"] == scan_mod.MASKED_TOKEN for item in findings))
            self.assertNotIn("acme_private", result.stdout + result.stderr)
            self.assertNotIn(metadata_secret, result.stdout + result.stderr)

    def test_archive_manifest_rejects_unsafe_or_nonexact_sets(self) -> None:
        cases = ("wrong-schema", "empty", "duplicate", "traversal", "missing", "extra", "symlink", "wrong-scope")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="oss_scan_archive_bad_") as temporary:
                parent = Path(temporary)
                archive = parent / "staged"
                target = self.write(archive, "docs/evidence/canon_notes/policy.md", "safe\n")
                items = [self.evidence_item()]
                schema = "oss-evidence-manifest.v1"
                if case == "wrong-schema":
                    schema = "other.v1"
                if case == "empty":
                    items = []
                if case == "duplicate":
                    items = [self.evidence_item(), self.evidence_item()]
                if case == "traversal":
                    items = [self.evidence_item("docs/evidence/canon_notes/../policy.md")]
                if case == "missing":
                    target.unlink()
                if case == "extra":
                    self.write(archive, "docs/evidence/canon_notes/extra.md", "extra\n")
                if case == "symlink":
                    target.unlink()
                    target.symlink_to(parent / "outside.md")
                manifest = self.manifest(parent, items, schema=schema)
                scope = "keep-set" if case == "wrong-scope" else "public-copy"
                result = self.run_scan(
                    archive,
                    "--archive-manifest",
                    str(manifest),
                    "--scope",
                    scope,
                    "--format",
                    "json",
                )
                self.assert_input_error(result)

    def test_scanner_and_its_public_tests_are_generic_clean(self) -> None:
        root = self.make_repo()
        self.write(root, "scripts/oss_release_scan.py", SCANNER.read_text(encoding="utf-8"))
        self.write(root, "scripts/test_oss_release_scan.py", Path(__file__).read_text(encoding="utf-8"))
        self.track(root, "scripts/oss_release_scan.py", "scripts/test_oss_release_scan.py")
        result = self.run_scan(root, "--scope", "public-copy", "--format", "json", "--fail-on", "blocker")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["counts"], {"blocker": 0, "warning": 0})


if __name__ == "__main__":
    unittest.main()

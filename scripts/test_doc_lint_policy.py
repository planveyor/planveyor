"""Neutral source and explicit caller doc-reference policy contracts."""
from pathlib import Path
import json
import unittest
from unittest import mock
from scripts import doc_lint


class ProductRootPolicyTests(unittest.TestCase):
    def test_public_profiles_need_no_consumer_policy_file(self):
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected policy read")):
            for profile in ("default", "planveyor", "target-local"):
                self.assertEqual(doc_lint.load_product_root_policy(content_profile_id=profile,
                    policy_root=Path("/nonexistent-consumer")), doc_lint.GENERIC_PRODUCT_ROOT_POLICY)
                self.assertEqual(doc_lint.load_product_root_policy(content_profile_id=profile),
                                 doc_lint.GENERIC_PRODUCT_ROOT_POLICY)

    def test_explicit_policy_parser_preserves_strict_negative_cases(self):
        value = {"schema_version": "doc-lint-product-root-policy.v1",
                 "allowed_ref_prefixes": ["src/"], "root_filenames": ["README.md"]}
        policy = doc_lint._strict_product_policy(json.dumps(value).encode())
        self.assertEqual(policy.allowed_ref_prefixes, ("src/",))
        self.assertEqual(policy.root_filenames, ("README.md",))
        for mutation in ({"extra": True}, {"allowed_ref_prefixes": ["../outside/"]},
                         {"allowed_ref_prefixes": ["src/", "src/"]}, {"root_filenames": ["../secret"]},
                         {"schema_version": "unsupported"}, {"allowed_ref_prefixes": []}):
            with self.subTest(mutation=mutation), self.assertRaises(doc_lint.ProductRootPolicyError):
                doc_lint._strict_product_policy(json.dumps(dict(value, **mutation)).encode())
        for payload in (b'{"schema_version":"doc-lint-product-root-policy.v1","schema_version":"duplicate"}',
                        b'not-json', b'[]'):
            with self.assertRaises(doc_lint.ProductRootPolicyError):
                doc_lint._strict_product_policy(payload)

    def test_unknown_profile_never_falls_back(self):
        for profile in ("unknown-consumer", "", "../escape"):
            with self.assertRaises(doc_lint.ProductRootPolicyError):
                doc_lint.load_product_root_policy(content_profile_id=profile)


if __name__ == "__main__":
    unittest.main()

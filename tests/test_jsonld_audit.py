#!/usr/bin/env python3
"""Tests for jsonld_audit. Run: python3 tests/test_jsonld_audit.py

Standard library unittest only — no third-party packages. A local
test HTTP server is used for the URL tests, so no real network is
needed. No test imports yaml or any other third-party module.
"""

import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jsonld_audit import (  # noqa: E402
    audit, entities_of, fetch_url, parse_jsonld, parse_page, type_of)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "jsonld_audit.py"
EXAMPLES = ROOT / "examples"

GOOD_HTML = (EXAMPLES / "knife-guide.html").read_text()
BAD_HTML = (EXAMPLES / "bad-page.html").read_text()
GOOD_LLMS = (EXAMPLES / "good-llms.txt").read_text()
BAD_LLMS = (EXAMPLES / "bad-llms.txt").read_text()


def run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=stdin, capture_output=True, text=True)


def status_of(checks, name):
    for check in checks:
        if check.name == name:
            return check.status
    return None


def detail_of(checks, name):
    for check in checks:
        if check.name == name:
            return check.detail
    return None


class TestParsePage(unittest.TestCase):
    def test_title_og_and_jsonld_extracted(self):
        title, og, blocks = parse_page(GOOD_HTML)
        self.assertEqual(title, "How to sharpen a kitchen knife")
        self.assertEqual(og["og:title"], "How to sharpen a kitchen knife")
        self.assertEqual(og["og:type"], "article")
        self.assertEqual(len(blocks), 1)
        self.assertIn("HowTo", blocks[0])

    def test_page_without_jsonld(self):
        _, _, blocks = parse_page("<html><head><title>T</title></head></html>")
        self.assertEqual(blocks, [])

    def test_og_meta_name_attribute_also_works(self):
        title, og, _ = parse_page(
            '<meta name="og:title" content="Hello">')
        self.assertEqual(og["og:title"], "Hello")


class TestParseJsonld(unittest.TestCase):
    def test_valid_block_parses(self):
        parsed = parse_jsonld(['{"@context": "https://schema.org", '
                               '"@type": "Article", "headline": "Hi"}'])
        self.assertIsNone(parsed[0][1])
        self.assertEqual(parsed[0][0]["@type"], "Article")

    def test_broken_block_reports_error(self):
        parsed = parse_jsonld(["{ this is not json"])
        self.assertIsNone(parsed[0][0])
        self.assertIn("Expecting property name", parsed[0][1])

    def test_graph_entities_flattened(self):
        parsed = parse_jsonld(['{"@context": "https://schema.org", '
                               '"@graph": [{"@type": "WebPage"}, '
                               '{"@type": "Organization", "name": "X"}]}'])
        ents = entities_of(parsed[0][0])
        self.assertEqual([type_of(e) for e in ents],
                         [["WebPage"], ["Organization"]])

    def test_list_block_flattened(self):
        parsed = parse_jsonld(['[{"@type": "Article"}, {"@type": "FAQPage"}]'])
        self.assertEqual(len(entities_of(parsed[0][0])), 2)

    def test_type_as_list(self):
        self.assertEqual(type_of({"@type": ["Article", "BlogPosting"]}),
                         ["Article", "BlogPosting"])
        self.assertEqual(type_of({}), [])


class TestAuditGoodPage(unittest.TestCase):
    def setUp(self):
        self.checks = audit(GOOD_HTML, page_path="knife-guide.html",
                            llms_text=GOOD_LLMS, llms_detail="test llms")

    def test_all_pass(self):
        self.assertTrue(all(c.status == "PASS" for c in self.checks))
        self.assertEqual(len(self.checks), 17)

    def test_counts(self):
        self.assertEqual(status_of(self.checks, "llms-links"), "PASS")
        self.assertEqual(detail_of(self.checks, "llms-links"),
                         "3 link(s) in llms.txt")


class TestAuditBadPage(unittest.TestCase):
    def setUp(self):
        self.checks = audit(BAD_HTML, page_path="bad-page.html",
                            llms_text=BAD_LLMS, llms_detail="test llms")

    def test_broken_jsonld_fails(self):
        self.assertEqual(status_of(self.checks, "jsonld-valid"), "FAIL")
        self.assertIn("block 2", detail_of(self.checks, "jsonld-valid"))

    def test_missing_product_name_fails(self):
        self.assertEqual(status_of(self.checks, "jsonld-required-fields"),
                         "FAIL")
        self.assertIn("Product.name",
                      detail_of(self.checks, "jsonld-required-fields"))

    def test_missing_og_tags_fail(self):
        for name in ("og:description", "og:type", "og:url"):
            self.assertEqual(status_of(self.checks, name), "FAIL")

    def test_relative_og_image_fails(self):
        self.assertEqual(status_of(self.checks, "og-image-absolute"), "FAIL")

    def test_title_mismatch_warns_not_fails(self):
        self.assertEqual(status_of(self.checks, "og-title-matches"), "WARN")

    def test_bad_llms_fails_heading_and_links(self):
        self.assertEqual(status_of(self.checks, "llms-heading"), "FAIL")
        self.assertEqual(status_of(self.checks, "llms-links"), "FAIL")


class TestAuditEdgeCases(unittest.TestCase):
    def test_no_jsonld_skips_dependent_checks(self):
        checks = audit("<html><head><title>T</title></head></html>",
                       llms_text=GOOD_LLMS, llms_detail="test")
        self.assertEqual(status_of(checks, "jsonld-present"), "FAIL")
        for name in ("jsonld-valid", "jsonld-context", "jsonld-type",
                     "jsonld-known-type", "jsonld-required-fields"):
            self.assertEqual(status_of(checks, name), "SKIP")

    def test_no_llms_skips_dependent_checks(self):
        checks = audit(GOOD_HTML, page_path="knife-guide.html",
                       llms_text=None, llms_detail="no llms.txt found")
        self.assertEqual(status_of(checks, "llms-present"), "FAIL")
        for name in ("llms-heading", "llms-links", "llms-mentions-page"):
            self.assertEqual(status_of(checks, name), "SKIP")

    def test_unknown_type_warns_not_fails(self):
        html = ('<script type="application/ld+json">'
                '{"@context": "https://schema.org", "@type": "SpaceShip", '
                '"name": "X"}</script>')
        checks = audit(html, llms_text=GOOD_LLMS, llms_detail="test")
        self.assertEqual(status_of(checks, "jsonld-known-type"), "WARN")
        self.assertEqual(status_of(checks, "jsonld-required-fields"), "PASS")

    def test_missing_context_fails(self):
        html = ('<script type="application/ld+json">'
                '{"@type": "Article", "headline": "Hi"}</script>')
        checks = audit(html, llms_text=GOOD_LLMS, llms_detail="test")
        self.assertEqual(status_of(checks, "jsonld-context"), "FAIL")

    def test_entity_without_type_fails(self):
        html = ('<script type="application/ld+json">'
                '{"@context": "https://schema.org", "name": "X"}</script>')
        checks = audit(html, llms_text=GOOD_LLMS, llms_detail="test")
        self.assertEqual(status_of(checks, "jsonld-type"), "FAIL")


class TestCli(unittest.TestCase):
    def test_good_page_exit_0(self):
        result = run_cli(str(EXAMPLES / "knife-guide.html"),
                         "--llms", str(EXAMPLES / "good-llms.txt"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("17 passed, 0 failed, 0 warned, 0 skipped",
                      result.stdout)

    def test_bad_page_exit_1(self):
        result = run_cli(str(EXAMPLES / "bad-page.html"),
                         "--llms", str(EXAMPLES / "bad-llms.txt"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("8 failed", result.stdout)

    def test_missing_file_exit_2(self):
        result = run_cli("nope.html")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such file", result.stderr)

    def test_stdin_input(self):
        result = run_cli("-", "--llms", str(EXAMPLES / "good-llms.txt"),
                         stdin=GOOD_HTML)
        self.assertEqual(result.returncode, 0)
        self.assertIn("16 passed", result.stdout)
        self.assertIn("1 skipped", result.stdout)

    def test_json_format_parses(self):
        result = run_cli(str(EXAMPLES / "knife-guide.html"),
                         "--llms", str(EXAMPLES / "good-llms.txt"),
                         "--format", "json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["summary"]["PASS"], 17)
        self.assertEqual(data["checks"][0]["name"], "jsonld-present")

    def test_no_llms_found_fails(self):
        result = run_cli(str(EXAMPLES / "bad-page.html"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("llms-present", result.stdout)
        self.assertIn("FAIL", result.stdout)

    def test_example_audit_file_matches_real_run(self):
        # Same relative paths as the committed sample-audit.txt.
        result = subprocess.run(
            [sys.executable, str(CLI), "examples/knife-guide.html",
             "--llms", "examples/good-llms.txt"],
            capture_output=True, text=True, cwd=str(ROOT))
        saved = (EXAMPLES / "sample-audit.txt").read_text()
        self.assertEqual(result.stdout, saved)


class TestUrlMode(unittest.TestCase):
    """URL fetching against a local server — no real network."""

    @classmethod
    def setUpClass(cls):
        # A temp site folder with a page and an llms.txt at its root,
        # so the URL mode's automatic llms.txt lookup can be tested.
        cls.tmp = tempfile.TemporaryDirectory()
        site = Path(cls.tmp.name)
        (site / "knife-guide.html").write_text(GOOD_HTML)
        (site / "llms.txt").write_text(GOOD_LLMS)
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler,
            directory=str(site))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                     handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_url_page_and_llms_auto_lookup(self):
        # No --llms flag: the tool must fetch /llms.txt from the site
        # root by itself.
        base = "http://127.0.0.1:%d" % self.port
        result = run_cli(base + "/knife-guide.html")
        self.assertEqual(result.returncode, 0)
        self.assertIn("17 passed", result.stdout)
        self.assertIn("llms-present", result.stdout)

    def test_unreachable_url_exit_2(self):
        result = run_cli("http://127.0.0.1:1/nope.html")
        self.assertEqual(result.returncode, 2)
        self.assertIn("fetch failed", result.stderr)

    def test_fetch_url_reads_page(self):
        text = fetch_url("http://127.0.0.1:%d/knife-guide.html" % self.port)
        self.assertIn("HowTo", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Audit one page's JSON-LD, Open Graph, and llms.txt.

Run: python3 src/jsonld_audit.py <page> [--llms <path-or-url>]
     python3 src/jsonld_audit.py <page> --format json

<page> is a local HTML file, a URL, or "-" for HTML on standard input.
The audit is one page only: it reads the page, pulls out its JSON-LD
<script> blocks and Open Graph meta tags, and reads the site's
llms.txt if it can find it. Each check reports PASS, FAIL, WARN, or
SKIP — a check that did not run is SKIP, never PASS.

Python standard library only. Nothing is sent anywhere except the
single page fetch when you give a URL (and its llms.txt fetch).
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

VERSION = "1.0.0"
MAX_BYTES = 1_000_000
FETCH_TIMEOUT = 10

# Schema.org types this tool knows the usual fields for. A type not
# in this list is not wrong — it is reported as WARN, not FAIL.
KNOWN_TYPES = {
    "Article", "BlogPosting", "NewsArticle", "WebPage", "WebSite",
    "Organization", "Person", "Product", "FAQPage", "BreadcrumbList",
    "Recipe", "Event", "LocalBusiness", "VideoObject", "ImageObject",
    "HowTo", "Review", "Offer", "Place", "ItemList",
}

# Fields that usually have to be there for each known type. A missing
# field is a FAIL — the block claims a type but leaves out the part
# search engines and readers need most.
REQUIRED_FIELDS = {
    "Article": ["headline"],
    "BlogPosting": ["headline"],
    "NewsArticle": ["headline"],
    "WebPage": ["name", "url"],
    "WebSite": ["name", "url"],
    "Organization": ["name"],
    "Person": ["name"],
    "Product": ["name"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "Recipe": ["name"],
    "Event": ["name", "startDate"],
    "LocalBusiness": ["name"],
    "VideoObject": ["name"],
    "ImageObject": ["url"],
    "HowTo": ["name"],
    "Review": ["name"],
    "Offer": ["price"],
    "Place": ["name"],
    "ItemList": ["itemListElement"],
}

OG_CHECKS = ["og:title", "og:description", "og:type", "og:url", "og:image"]


class Check:
    """One audit result: name, status, and what was actually seen."""

    def __init__(self, name, status, detail):
        self.name = name
        self.status = status  # PASS, FAIL, WARN, or SKIP
        self.detail = detail

    def as_dict(self):
        return {"name": self.name, "status": self.status,
                "detail": self.detail}


class PageParser(HTMLParser):
    """Pull the title, Open Graph tags, and JSON-LD blocks out of HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.og = {}
        self.jsonld_blocks = []
        self._in_jsonld = False
        self._jsonld_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            prop = attrs.get("property", "") or attrs.get("name", "")
            if prop.startswith("og:") and "content" in attrs:
                self.og.setdefault(prop, attrs["content"])
        elif tag == "script":
            if attrs.get("type", "").strip().lower() == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_text = ""

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld_blocks.append(self._jsonld_text)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld:
            self._jsonld_text += data


def parse_page(html):
    """Return (title, og dict, list of raw JSON-LD block strings)."""
    parser = PageParser()
    parser.feed(html)
    return parser.title.strip(), parser.og, parser.jsonld_blocks


def parse_jsonld(blocks):
    """Parse each raw block. Returns [(parsed or None, error or None)]."""
    out = []
    for block in blocks:
        try:
            out.append((json.loads(block), None))
        except json.JSONDecodeError as exc:
            out.append((None, str(exc)))
    return out


def entities_of(parsed):
    """Flatten one parsed JSON-LD value into its typed entities.

    A block can be one object, a list of objects, or an object with an
    @graph list. Each entry in the list is one entity.
    """
    if isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
        return parsed["@graph"]
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []


def type_of(entity):
    """The @type of an entity, as a list of type names."""
    if not isinstance(entity, dict):
        return []
    raw = entity.get("@type")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, str)]
    return []


def fetch_url(url):
    """Fetch one URL as text. Raises ValueError with the reason."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "jsonld-audit-cli/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError("fetch failed: %s returned HTTP %d"
                         % (url, exc.code))
    except urllib.error.URLError as exc:
        raise ValueError("fetch failed: %s (%s)" % (url, exc.reason))
    except TimeoutError:
        raise ValueError("fetch failed: %s timed out" % url)
    if len(data) > MAX_BYTES:
        raise ValueError("fetch failed: %s is over 1 MB" % url)
    return data.decode("utf-8", errors="replace")


def read_llms(source, page_url, page_path):
    """Find and read llms.txt. Returns (text or None, detail string).

    --llms wins. Otherwise, for a URL page, fetch origin/llms.txt;
    for a local file, read the llms.txt next to the page file.
    A page read from stdin has no site, so nothing is looked up.
    """
    if source:
        if source.startswith(("http://", "https://")):
            try:
                return fetch_url(source), "read from %s" % source
            except ValueError as exc:
                return None, str(exc)
        path = Path(source)
        if not path.is_file():
            return None, "no such file: %s" % source
        return path.read_text(encoding="utf-8", errors="replace"), \
            "read from %s" % source
    if page_url:
        origin = "%s://%s" % (urllib.parse.urlparse(page_url).scheme,
                              urllib.parse.urlparse(page_url).netloc)
        url = origin + "/llms.txt"
        try:
            return fetch_url(url), "read from %s" % url
        except ValueError as exc:
            return None, str(exc)
    if page_path:
        sibling = Path(page_path).resolve().parent / "llms.txt"
        if sibling.is_file():
            return sibling.read_text(encoding="utf-8", errors="replace"), \
                "read from %s" % sibling
        return None, "no llms.txt next to %s" % page_path
    return None, "stdin page has no site to look up llms.txt in"


def audit(html, page_url=None, page_path=None, llms_text=None,
          llms_detail=""):
    """Run every check on one page. Returns a list of Check objects."""
    title, og, blocks = parse_page(html)
    parsed = parse_jsonld(blocks)
    good = [obj for obj, err in parsed if err is None]
    entities = []
    for obj in good:
        entities.extend(entities_of(obj))
    checks = []

    # --- JSON-LD ---
    if blocks:
        checks.append(Check("jsonld-present", "PASS",
                            "%d JSON-LD block(s) found" % len(blocks)))
    else:
        checks.append(Check("jsonld-present", "FAIL",
                            "no <script type=\"application/ld+json\"> block"))
    if not blocks:
        for name in ("jsonld-valid", "jsonld-context", "jsonld-type",
                     "jsonld-known-type", "jsonld-required-fields"):
            checks.append(Check(name, "SKIP", "no JSON-LD block to check"))
    else:
        bad = [(i + 1, err) for i, (_, err) in enumerate(parsed)
               if err is not None]
        if bad:
            detail = "; ".join("block %d: %s" % (i, e) for i, e in bad)
            checks.append(Check("jsonld-valid", "FAIL", detail))
        else:
            checks.append(Check("jsonld-valid", "PASS",
                                "%d block(s) parse as JSON" % len(blocks)))
        if good:
            no_context = sum(1 for obj in good
                             if not isinstance(obj, dict)
                             or "schema.org" not in str(obj.get("@context", "")))
            if no_context:
                checks.append(Check("jsonld-context", "FAIL",
                                    "%d block(s) without a schema.org @context"
                                    % no_context))
            else:
                checks.append(Check("jsonld-context", "PASS",
                                    "every block has a schema.org @context"))
            no_type = sum(1 for ent in entities if not type_of(ent))
            if not entities:
                checks.append(Check("jsonld-type", "FAIL",
                                    "no typed entity found in the JSON-LD"))
            elif no_type:
                checks.append(Check("jsonld-type", "FAIL",
                                    "%d entit(ies) without @type" % no_type))
            else:
                checks.append(Check("jsonld-type", "PASS",
                                    "every entity has @type"))
            unknown = sorted({t for ent in entities for t in type_of(ent)
                              if t not in KNOWN_TYPES})
            if unknown:
                checks.append(Check("jsonld-known-type", "WARN",
                                    "unknown type(s): %s"
                                    % ", ".join(unknown)))
            else:
                types = sorted({t for ent in entities for t in type_of(ent)})
                checks.append(Check("jsonld-known-type", "PASS",
                                    "type(s): %s" % ", ".join(types)
                                    if types else "no entities"))
            missing = []
            for ent in entities:
                for t in type_of(ent):
                    for field in REQUIRED_FIELDS.get(t, []):
                        if not isinstance(ent, dict) or field not in ent \
                                or ent[field] in ("", None):
                            missing.append("%s.%s" % (t, field))
            if missing:
                checks.append(Check("jsonld-required-fields", "FAIL",
                                    "missing: %s" % ", ".join(sorted(set(missing)))))
            else:
                checks.append(Check("jsonld-required-fields", "PASS",
                                    "usual fields are present"))
        else:
            for name in ("jsonld-context", "jsonld-type",
                         "jsonld-known-type", "jsonld-required-fields"):
                checks.append(Check(name, "SKIP",
                                    "no block parsed as JSON"))

    # --- Open Graph ---
    for prop in OG_CHECKS:
        value = og.get(prop, "")
        if value.strip():
            checks.append(Check(prop, "PASS", "%s" % value.strip()[:80]))
        else:
            checks.append(Check(prop, "FAIL", "%s tag missing or empty"
                            % prop))
    image = og.get("og:image", "").strip()
    if not image:
        checks.append(Check("og-image-absolute", "SKIP",
                            "no og:image to check"))
    elif image.startswith(("http://", "https://")):
        checks.append(Check("og-image-absolute", "PASS",
                            "og:image is an absolute URL"))
    else:
        checks.append(Check("og-image-absolute", "FAIL",
                            "og:image is not an absolute URL: %s" % image))
    og_title = og.get("og:title", "").strip()
    if not og_title or not title:
        checks.append(Check("og-title-matches", "SKIP",
                            "og:title or <title> missing"))
    elif og_title == title:
        checks.append(Check("og-title-matches", "PASS",
                            "og:title matches <title>"))
    else:
        checks.append(Check("og-title-matches", "WARN",
                            "og:title %r differs from <title> %r"
                            % (og_title, title)))

    # --- llms.txt ---
    if llms_text is None:
        checks.append(Check("llms-present", "FAIL", llms_detail))
        for name in ("llms-heading", "llms-links", "llms-mentions-page"):
            checks.append(Check(name, "SKIP", "no llms.txt to check"))
    else:
        checks.append(Check("llms-present", "PASS", llms_detail))
        if re.search(r"^#{1,6}\s+\S", llms_text, re.MULTILINE):
            checks.append(Check("llms-heading", "PASS",
                                "llms.txt has a Markdown heading"))
        else:
            checks.append(Check("llms-heading", "FAIL",
                                "llms.txt has no Markdown heading"))
        md_links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", llms_text)
        rest = re.sub(r"\[[^\]]+\]\([^)]+\)", "", llms_text)
        bare_links = re.findall(r"https?://\S+", rest)
        links = md_links + bare_links
        if links:
            checks.append(Check("llms-links", "PASS",
                                "%d link(s) in llms.txt" % len(links)))
        else:
            checks.append(Check("llms-links", "FAIL",
                                "llms.txt has no links"))
        needle = None
        if page_url:
            needle = urllib.parse.urlparse(page_url).path.strip("/")
        elif page_path:
            needle = Path(page_path).name
        if not needle:
            checks.append(Check("llms-mentions-page", "SKIP",
                                "no page URL or file name to look for"))
        elif needle in llms_text:
            checks.append(Check("llms-mentions-page", "PASS",
                                "llms.txt mentions this page"))
        else:
            checks.append(Check("llms-mentions-page", "WARN",
                                "llms.txt does not mention this page"))

    return checks


def summarize(checks):
    """Count checks by status."""
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
    for check in checks:
        counts[check.status] += 1
    return counts


def render_text(source, checks):
    """The plain-text report."""
    counts = summarize(checks)
    lines = ["JSON-LD + Open Graph + llms.txt audit",
             "Page: %s" % source, ""]
    for check in checks:
        lines.append("%-5s %-22s %s"
                     % (check.status, check.name, check.detail))
    lines.append("")
    lines.append("%d passed, %d failed, %d warned, %d skipped"
                 % (counts["PASS"], counts["FAIL"], counts["WARN"],
                    counts["SKIP"]))
    return "\n".join(lines) + "\n"


def render_json(source, checks):
    """The JSON report."""
    counts = summarize(checks)
    return json.dumps({"source": source,
                       "checks": [c.as_dict() for c in checks],
                       "summary": counts}, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jsonld_audit",
        description="Audit one page's JSON-LD, Open Graph, and llms.txt.")
    parser.add_argument("source",
                        help="HTML file, URL, or - for HTML on stdin")
    parser.add_argument("--llms", default=None,
                        help="llms.txt file or URL (otherwise looked up "
                             "next to the page, or at the site root)")
    parser.add_argument("--format", choices=["text", "json"],
                        default="text", help="report format")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)

    page_url = None
    page_path = None
    if args.source == "-":
        html = sys.stdin.read()
    elif args.source.startswith(("http://", "https://")):
        page_url = args.source
        try:
            html = fetch_url(args.source)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
    else:
        page_path = args.source
        path = Path(args.source)
        if not path.is_file():
            print("error: no such file: %s" % args.source, file=sys.stderr)
            return 2
        html = path.read_text(encoding="utf-8", errors="replace")

    llms_text, llms_detail = read_llms(args.llms, page_url, page_path)
    checks = audit(html, page_url=page_url, page_path=page_path,
                   llms_text=llms_text, llms_detail=llms_detail)

    if args.format == "json":
        sys.stdout.write(render_json(args.source, checks))
    else:
        sys.stdout.write(render_text(args.source, checks))
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())

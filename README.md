# jsonld-audit-cli

Audit one page's JSON-LD, Open Graph, and llms.txt.

[![CI](https://github.com/haiderstudio/jsonld-audit-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/jsonld-audit-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`jsonld-audit` reads one page and checks three things on it, one check
at a time:

- **JSON-LD** — is there a `<script type="application/ld+json">`
  block, does it parse as JSON, does it have a schema.org `@context`
  and an `@type`, is the type one the tool knows, and are the usual
  fields for that type there (a Product needs a name, an Article
  needs a headline, an FAQPage needs `mainEntity`).
- **Open Graph** — are `og:title`, `og:description`, `og:type`,
  `og:url`, and `og:image` there and not empty, is `og:image` an
  absolute URL, and does `og:title` match the page `<title>`.
- **llms.txt** — is there an `llms.txt`, does it have a Markdown
  heading and links, and does it mention this page.

Each check reports PASS, FAIL, WARN, or SKIP. A check that did not run
is SKIP, never PASS — for example, if the page has no JSON-LD at all,
the JSON-LD detail checks are SKIP, not PASS. The run exits 0 when
nothing failed and 1 when any check failed, so it works as a CI gate.

## What it does NOT do

- It does not crawl a site. One page per run.
- It does not check whether the JSON-LD claims are true — only that
  the block is there, parses, and has the fields its type usually
  needs. A Product named "Best product ever" passes; the tool cannot
  tell if the claim is true.
- It does not check the whole Schema.org spec, only the common types
  and fields listed in the code. An unknown type is WARN, not FAIL.
- It does not fix anything. It only reports.
- It does not rank your page, guess your search position, or claim
  anything about AI search results.

## Who it is for

Anyone who added JSON-LD, Open Graph tags, or an `llms.txt` to a page
and wants to know, before publishing, whether the basics are actually
there — and anyone who wants that check in CI so a broken block
cannot ship quietly.

## How this differs from similar tools

Full SEO suites check everything: houtini-ai/seo-audit is an MCP
server that pulls Google Search Console history and crawls a site;
MrRex168/agent-readiness-toolkit scores a whole website and API for
machine-readability; maxbuildog/skills is a broad pack of SEO/GEO
agent skills. RelayStack/astro-seo-toolkit generates `llms.txt`,
JSON-LD, and sitemaps for Astro sites — it writes files, it does not
audit one page. Google's Schema Markup Validator and Screaming Frog
are web tools / desktop apps for whole sites.

This tool does a narrower job: one page, three checks, from a local
file, standard input, or one URL, with Python 3 and one file — no
install, no account, no crawl.

## Install

Python standard library only — no packages to download. Clone the repo
and run it in place:

```sh
git clone https://github.com/haiderstudio/jsonld-audit-cli.git
cd jsonld-audit-cli
```

Python 3.9 or newer.

## Usage

```sh
python3 src/jsonld_audit.py <page> [--llms <path-or-url>] [--format json]
```

`<page>` is a local HTML file, a URL, or `-` for HTML on standard
input. Without `--llms`, the tool looks for `llms.txt` next to the
page file, or at the site root for a URL page.

Audit the good sample page:

```sh
python3 src/jsonld_audit.py examples/knife-guide.html --llms examples/good-llms.txt
```

Real output:

```text
JSON-LD + Open Graph + llms.txt audit
Page: examples/knife-guide.html

PASS  jsonld-present         1 JSON-LD block(s) found
PASS  jsonld-valid           1 block(s) parse as JSON
PASS  jsonld-context         every block has a schema.org @context
PASS  jsonld-type            every entity has @type
PASS  jsonld-known-type      type(s): HowTo
PASS  jsonld-required-fields usual fields are present
PASS  og:title               How to sharpen a kitchen knife
PASS  og:description         A short guide to sharpening a kitchen knife with a whetstone.
PASS  og:type                article
PASS  og:url                 https://example.com/knife-guide.html
PASS  og:image               https://example.com/images/knife.jpg
PASS  og-image-absolute      og:image is an absolute URL
PASS  og-title-matches       og:title matches <title>
PASS  llms-present           read from examples/good-llms.txt
PASS  llms-heading           llms.txt has a Markdown heading
PASS  llms-links             3 link(s) in llms.txt
PASS  llms-mentions-page     llms.txt mentions this page

17 passed, 0 failed, 0 warned, 0 skipped
```

Exit code 0. The same report as JSON, for scripts and CI:

```sh
python3 src/jsonld_audit.py examples/knife-guide.html --llms examples/good-llms.txt --format json
```

Real output (first lines):

```json
{
  "source": "examples/knife-guide.html",
  "checks": [
    {
      "name": "jsonld-present",
      "status": "PASS",
      "detail": "1 JSON-LD block(s) found"
    },
    {
      "name": "jsonld-valid",
      "status": "PASS",
      "detail": "1 block(s) parse as JSON"
    }
  ],
  "summary": {
    "PASS": 17,
    "FAIL": 0,
    "WARN": 0,
    "SKIP": 0
  }
}
```

## Examples

### 1. A bad page — 8 checks fail

```sh
python3 src/jsonld_audit.py examples/bad-page.html --llms examples/bad-llms.txt
```

Real output:

```text
JSON-LD + Open Graph + llms.txt audit
Page: examples/bad-page.html

PASS  jsonld-present         2 JSON-LD block(s) found
FAIL  jsonld-valid           block 2: Expecting property name enclosed in double quotes: line 2 column 3 (char 3)
PASS  jsonld-context         every block has a schema.org @context
PASS  jsonld-type            every entity has @type
PASS  jsonld-known-type      type(s): Product
FAIL  jsonld-required-fields missing: Product.name
PASS  og:title               A different title
FAIL  og:description         og:description tag missing or empty
FAIL  og:type                og:type tag missing or empty
FAIL  og:url                 og:url tag missing or empty
PASS  og:image               /images/missing.jpg
FAIL  og-image-absolute      og:image is not an absolute URL: /images/missing.jpg
WARN  og-title-matches       og:title 'A different title' differs from <title> 'Untitled page'
PASS  llms-present           read from examples/bad-llms.txt
FAIL  llms-heading           llms.txt has no Markdown heading
FAIL  llms-links             llms.txt has no links
WARN  llms-mentions-page     llms.txt does not mention this page

7 passed, 8 failed, 2 warned, 0 skipped
```

Exit code 1. The broken JSON-LD block, the Product with no name, the
missing Open Graph tags, and the empty `llms.txt` are each named on
their own line.

### 2. HTML on standard input

```sh
cat examples/knife-guide.html | python3 src/jsonld_audit.py - --llms examples/good-llms.txt
```

Real output (last lines):

```text
PASS  llms-links             3 link(s) in llms.txt
SKIP  llms-mentions-page     no page URL or file name to look for

16 passed, 0 failed, 0 warned, 1 skipped
```

A page read from stdin has no file name, so the "mentions this page"
check cannot run — it is SKIP, not PASS. Exit code 0.

### 3. A page with no JSON-LD at all

```sh
printf '<html><head><title>Plain</title></head><body><p>Hi.</p></body></html>' | python3 src/jsonld_audit.py - --llms examples/good-llms.txt
```

Real output (first lines):

```text
JSON-LD + Open Graph + llms.txt audit
Page: -

FAIL  jsonld-present         no <script type="application/ld+json"> block
SKIP  jsonld-valid           no JSON-LD block to check
SKIP  jsonld-context         no JSON-LD block to check
SKIP  jsonld-type            no JSON-LD block to check
SKIP  jsonld-known-type      no JSON-LD block to check
SKIP  jsonld-required-fields no JSON-LD block to check
```

The missing block is one FAIL; the five detail checks are SKIP, not
PASS. Exit code 1.

## How it is tested

```sh
python3 tests/test_jsonld_audit.py
```

31 tests, standard library `unittest` only — no third-party packages,
and no `yaml` import anywhere (a clean CI runner has no `yaml`).
They cover: title/Open Graph/JSON-LD extraction, valid and broken
JSON-LD, `@graph` and list blocks, missing `@context`/`@type`,
required fields per type, unknown types (WARN, not FAIL), Open Graph
checks, `llms.txt` checks, no-JSON-LD and no-llms.txt SKIP behaviour,
CLI exit codes (0 / 1 / 2), stdin input, `--format json`, and URL
fetching plus automatic `llms.txt` lookup against a local test
server — no real network is used. The committed
`examples/sample-audit.txt` is checked against a fresh run of the
same command.

The bundled examples are real runs, not made-up output:

```sh
sh examples/run-example.sh
```

It audits the good page (17 passed), the bad page (8 failed), checks
the JSON format parses, and diffs the saved sample audit against a
fresh run.

## Contributing

Small, focused improvements are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Built from scratch for this repo. The idea — auditing one page's
structured data — follows the same pattern as the Schema Markup
Validator and the tools named in "How this differs from similar
tools" above; no code was copied from any of them.

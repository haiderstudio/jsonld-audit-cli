#!/bin/sh
# Audit the two sample pages. Run from the repo root:
# sh examples/run-example.sh
# The good page passes every check; the bad page fails 8 checks.
set -e
cd "$(dirname "$0")/.."
echo "--- good page (expect 17 passed, exit 0) ---"
python3 src/jsonld_audit.py examples/knife-guide.html --llms examples/good-llms.txt
echo "--- bad page (expect 8 failed, exit 1) ---"
python3 src/jsonld_audit.py examples/bad-page.html --llms examples/bad-llms.txt || test $? -eq 1
echo "--- JSON format (expect it to parse) ---"
python3 src/jsonld_audit.py examples/knife-guide.html --llms examples/good-llms.txt --format json | python3 -m json.tool > /dev/null
echo "--- saved sample audit matches a fresh run ---"
python3 src/jsonld_audit.py examples/knife-guide.html --llms examples/good-llms.txt > /tmp/sample-audit-check.txt
diff examples/sample-audit.txt /tmp/sample-audit-check.txt

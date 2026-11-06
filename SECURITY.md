# Security Policy

This tool runs locally and collects no data. It reads one page — a file on
your machine, HTML on standard input, or one URL you give it — and, for a
URL page, the site's `llms.txt` at the site root. It sends nothing else
anywhere, needs no API key or secret, and writes nothing except the report
on standard output (or the file you name with `--format json`, which is
still only the report).

It never guesses: a check it could not run is SKIP, never PASS.

If you find a case where the tool reports PASS for a check it did not
actually run, or where it sends a request to a URL you did not give it,
please open an issue describing the exact commands and input. Do not
include any real secret in the report.

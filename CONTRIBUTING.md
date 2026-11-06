# Contributing

Small, focused improvements are welcome.

- Open an issue first for anything larger than a typo or a clearer example, so the scope can be agreed before work starts.
- Never weaken the honesty rules: a check that did not run must stay SKIP, never PASS, and a missing field must stay FAIL — and the rule must be covered by a test.
- Every claim in a proposed change must be verifiable: a command must be runnable, a feature must exist in code, a badge must be true.
- Run `python3 tests/test_jsonld_audit.py` before opening a pull request. It must pass.
- Do not add placeholder text, invented features, or copied content without attribution.
- Python standard library only — no new dependency without a reason in the issue.

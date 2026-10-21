# Contributing

Run `python -m unittest discover -s tests -v` and `python -m delivery_probe demo`.
Tests use synthetic fixtures and loopback HTTP servers; no API keys required.

For a bug report, include Python/OS version, a minimal synthetic fixture,
scenario, expected final state and a redacted report. Do not attach customer
payloads or credentials. Add a reproducing regression test with a fix.

Keep new scenarios deterministic, document their limits and preserve the
distinction between HTTP acceptance and side-effect correctness. Discuss major
scope additions in an issue first. No trademark or provider affiliation implied.

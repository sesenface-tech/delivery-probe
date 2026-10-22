# Delivery Probe

**Reproduce duplicate, delayed and out-of-order webhook deliveries, then check the receiver's final state.**

Early-stage open source, maintained by Serkan Esen. No runtime dependencies, cloud account, AI key, webhook tunnel or hardware. Python 3.10+. This is an independent project, not part of OwnerWing. No external adoption or production reliability is claimed.

## Try it in under a minute

From a checkout, with Python installed:

```sh
python -m delivery_probe demo
python -m unittest discover -s tests -v
```

On systems where the executable is named `python3`, use that instead. On Windows, `py -m delivery_probe demo` also works when Python Launcher is installed.

The demo starts eight isolated loopback test sessions on OS-assigned ports. A deliberately naive receiver accepts every request with HTTP 200 but fails duplicate and reorder assertions. A receiver with deduplication and a version guard passes the four fixtures. Demo exit 0 means these expected positive AND negative outcomes were observed; the intentionally failing controls are not a demo failure.

| Scenario | Naive receiver | Deduplication + version guard |
| --- | --- | --- |
| Normal | Verified | Verified |
| Duplicate first event | Fails final state, despite HTTP 200 | Verified |
| Delay second event | Verified | Verified |
| Reverse order | Fails final state, despite HTTP 200 | Verified |

Optional installation: `python -m pip install .` (build backend setuptools required). Then use `delivery-probe demo`. The checkout commands need no package installation or network access.

## Test your own local receiver

Use an isolated test database or a fresh fixture. The tool NEVER resets your application state.

```sh
python -m delivery_probe run examples/events.json \
  --url http://127.0.0.1:8080/webhook \
  --scenario duplicate \
  --state-url http://127.0.0.1:8080/state \
  --expect examples/expected.json
```

Your receiver must understand your event fixture. The whole event object is sent as JSON; the `id` value stays unchanged on redelivery. The bundled fields `version` and `payload` are example conventions, not a standard webhook schema. You can use different payload fields; every source event needs a unique printable ASCII `id`.

The optional state endpoint returns JSON such as `{"processed_unique":2,"version":2,"other":"ignored"}`. Expected object keys are checked recursively as a subset; arrays and scalars match exactly, including types. Define assertions that reflect YOUR real business side effects. Omit both state options to test transport alone: output is `delivered_unverified`, never a correctness claim. A weak state assertion cannot prove stronger properties.

- `normal`: original input order.
- `duplicate`: send first event twice consecutively, then remaining events.
- `delayed`: pause before the second event (`--delay 0.1` seconds by default).
- `reorder`: reverse the input order.
- `--wait 1`: wait before ONE final-state observation for asynchronous receivers. No polling or eventual-consistency guarantee.
- `--timeout 2`: per-request timeout. A timeout may follow a completed side effect; the tool does not retry automatically.
- `--allow-remote`: opt in to a non-loopback server you are authorized to test. No external services are contacted by the demo or test suite.

Sequential delivery only. The delayed scenario demonstrates a pause; it does not automatically determine whether a deadline or stale-state policy was violated. Concurrent races, arbitrary permutations, provider signatures, authentication headers, exact raw-byte replay, automatic provider retries and production certification are out of scope in v0.1.

## Reports and CI

```sh
python -m delivery_probe demo > demo-report.json
```

JSON contains scenario, delivery status codes, elapsed time, and state assertion outcome. It deliberately omits event IDs, request URLs, payloads, headers and receiver state bodies. Do not put secrets in fixture files you commit. Endpoint paths and fixture data still reach the target by design. Timing values vary between runs.

Exit codes: **0** deliveries accepted and optional assertions matched (or demo controls behaved as expected); **1** transport/state assertion failure; **2** invalid input/configuration. Always inspect `verification.kind` when interpreting exit 0. The included GitHub Actions workflow is a template until it actually runs on GitHub.

## Scope of evidence

The in-memory demo receiver illustrates deduplication/version guards, not durable storage or a correct financial transaction design. It does not test crash recovery, concurrent requests, atomicity or retention. Adapt your state endpoint to count real side effects. Passing a fixture is evidence for that fixture only.

## Related tools

Existing projects include [webhook-replay](https://pypi.org/project/webhook-replay/), [Unhook](https://unhook.sh/), and [HookChaos](https://github.com/umutkeskin1001-cell/HookChaos). Delivery Probe makes no uniqueness claim: its small scope is dependency-free scripted scenarios, optional receiver-state assertions and an isolated positive/negative demo. No code was copied from these projects.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md), and the [MIT license](LICENSE).

## Generated regression-test integration

[Webhook Regression Kit](https://github.com/sesenface-tech/webhook-regression-kit)
turns local event fixtures and explicit expected state into a Python unittest.
Run the committed, reviewed example with:

```sh
python -m examples.regression.demo
```

It verifies that the generated duplicate test fails on a deliberately naive
receiver and passes on a guarded receiver, using actual loopback HTTP and fresh
state. See [the example](examples/regression/README.md). This is self-integration
using synthetic fixtures, not evidence of independent users or production usage.

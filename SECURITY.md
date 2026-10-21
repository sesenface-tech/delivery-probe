# Security and data handling

v0.1 is an early-stage local development tool, not a hosted service. Only test
receivers you own or are authorized to exercise. Use synthetic data and isolated
test state: delivering a webhook can trigger real side effects.

Loopback targets are the default. Remote URLs require explicit opt-in. Redirects
and environment proxies are disabled. URL credentials/query strings/fragments
are rejected; arbitrary auth headers and provider signing are not implemented.
Input manifests are limited to 1 MiB by the CLI, 100 events, 64 KiB per event;
responses are limited to 64 KiB. Delays/waits are limited to 5s, timeouts to 10s.

Reports omit payloads, IDs, URLs and state response bodies. This is data
minimization, not a general-purpose secret scanner. Never commit real payloads.
The state endpoint must not expose production data. The bundled demo binds only
127.0.0.1 and uses ephemeral in-memory state.

Do not post exploit details or credentials in public issues. If no private
reporting channel is available, open an issue asking the maintainer to establish
one, without disclosing the vulnerability itself. Use synthetic reproduction
steps when a private channel is established. There is no paid support,
response-time guarantee or completed external audit.

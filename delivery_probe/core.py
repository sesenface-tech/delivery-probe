"""Delivery scheduling and optional receiver-state assertions.

No provider signatures, automatic retries, redirects, or implicit success oracle.
"""

import http.client
import ipaddress
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 65536
SCENARIOS = ("normal", "duplicate", "delayed", "reorder")


def validate_url(url, allow_remote=False):
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("An http(s) URL with a hostname is required")
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError("URL credentials, query strings and fragments are not supported")
    if port == 0:
        raise ValueError("Invalid port")
    try:
        local = ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        local = parts.hostname.lower() == "localhost"
    if not local and not allow_remote:
        raise ValueError("Only loopback targets are allowed; use --allow-remote for an authorized test server")
    return url


def bounded_number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def encode_json(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def validate_events(events):
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise ValueError("Manifest must be an array containing 1..100 events")
    ids = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Each event must be an object")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128 or not all(32 <= ord(c) <= 126 for c in event_id):
            raise ValueError("Event id must contain 1..128 printable ASCII characters")
        if event_id in ids:
            raise ValueError("Source event IDs must be unique; use the duplicate scenario")
        ids.add(event_id)
        if len(encode_json(event)) > MAX_BYTES:
            raise ValueError("An event exceeds 64 KiB")
    return events


def plan(events, scenario, delay=0.1):
    validate_events(events)
    bounded_number(delay, 0, 5, "delay")
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    if scenario in ("duplicate", "delayed", "reorder") and len(events) < 2:
        raise ValueError("Fault scenarios require at least two source events")
    ordered = list(reversed(events)) if scenario == "reorder" else list(events)
    if scenario == "duplicate":
        ordered.insert(1, events[0])
    # Sequential schedule: delay occurs before the second delivery, not inside HTTP.
    return [(delay if scenario == "delayed" and i == 1 else 0, event) for i, event in enumerate(ordered)]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, method="GET", payload=None, timeout=2):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = encode_json(payload)
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    # Explicitly ignore environment proxy settings, including for local targets.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                return response.status, None, "response_too_large"
            return response.status, body, None
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        return code, None, "http_error"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        return None, None, "transport_error"


def matches_subset(actual, expected):
    """Objects are recursive subsets; arrays/scalars must match exactly, with types."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and matches_subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(matches_subset(a, e) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def run(events, target, scenario="normal", delay=0.1, timeout=2,
        state_url=None, expected=None, allow_remote=False, wait=0):
    validate_url(target, allow_remote)
    if (state_url is None) != (expected is None):
        raise ValueError("State URL and expected state must be provided together")
    if state_url is not None:
        validate_url(state_url, allow_remote)
        if not isinstance(expected, dict) or not expected:
            raise ValueError("Expected state must be a non-empty JSON object")
        encode_json(expected)
    bounded_number(timeout, 0.05, 10, "timeout")
    bounded_number(wait, 0, 5, "wait")
    deliveries = []
    for pause, event in plan(events, scenario, delay):
        if pause:
            time.sleep(pause)
        start = time.monotonic()
        status, _, error = request_json(target, "POST", event, timeout)
        # Do not put payloads, IDs, endpoints, headers or receiver bodies into reports.
        deliveries.append({"index": len(deliveries), "status": status,
                           "error": error, "elapsed_ms": round((time.monotonic() - start) * 1000, 2)})
    accepted = all(d["status"] is not None and 200 <= d["status"] < 300 and not d["error"] for d in deliveries)
    verification = {"kind": "delivery_only", "state_matches": None, "error": None}
    if state_url is not None:
        if wait:
            time.sleep(wait)
        status, body, error = request_json(state_url, timeout=timeout)
        if error or status is None or not 200 <= status < 300:
            verification = {"kind": "receiver_state", "state_matches": False, "error": error or "state_http_error"}
        else:
            try:
                actual = json.loads(body)
                match = matches_subset(actual, expected)
                verification = {"kind": "receiver_state", "state_matches": match, "error": None}
            except (ValueError, UnicodeError):
                verification = {"kind": "receiver_state", "state_matches": False, "error": "invalid_state_json"}
    ok = accepted and verification["state_matches"] is not False
    return {"schema_version": 1, "scenario": scenario, "delivery_count": len(deliveries),
            "http_accepted": accepted, "verification": verification,
            "outcome": "failed" if not ok else ("verified" if state_url else "delivered_unverified"),
            "deliveries": deliveries}

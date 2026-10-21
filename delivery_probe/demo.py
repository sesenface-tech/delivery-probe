"""Isolated localhost receivers demonstrate what HTTP 200 cannot prove."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from .core import MAX_BYTES, SCENARIOS, encode_json, run

EVENTS = [{"id": "example-created", "version": 1, "payload": {"state": "created"}},
          {"id": "example-updated", "version": 2, "payload": {"state": "updated"}}]


@contextmanager
def receiver(robust=True):
    state = {"processed_unique": 0, "version": 0}
    seen = set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data):
            body = encode_json(data)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.respond(200, state) if self.path == "/state" else self.respond(404, {})

        def do_POST(self):
            if self.path != "/webhook":
                self.respond(404, {})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BYTES:
                    raise ValueError()
                event = json.loads(self.rfile.read(length))
                event_id, version = event["id"], event["version"]
                if not isinstance(event_id, str) or type(version) is not int:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                self.respond(400, {})
                return
            if not robust or event_id not in seen:
                state["processed_unique"] += 1
                if not robust or version > state["version"]:
                    state["version"] = version
                seen.add(event_id)
            self.respond(200, {"accepted": True})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def demo():
    results = []
    expected = {"processed_unique": 2, "version": 2}
    for robust in (False, True):
        for scenario in SCENARIOS:
            with receiver(robust) as base:
                report = run(EVENTS, base + "/webhook", scenario, delay=0.05,
                             state_url=base + "/state", expected=expected)
                report["receiver"] = "deduplicating_version_guard" if robust else "naive"
                results.append(report)
    # The negative controls must fail even though every delivery returns HTTP 200.
    expected_outcomes = ["verified", "failed", "verified", "failed"] + ["verified"] * 4
    passed = [r["outcome"] for r in results] == expected_outcomes
    return {"demo_assertions_passed": passed, "note": "Synthetic fixtures; in-memory receivers; no production certification", "runs": results}

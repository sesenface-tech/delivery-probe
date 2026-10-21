import contextlib
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from delivery_probe.cli import main
from delivery_probe.core import matches_subset, plan, request_json, run, validate_events, validate_url
from delivery_probe.demo import EVENTS, demo, receiver


class ProbeTests(unittest.TestCase):
    def test_schedules(self):
        self.assertEqual([e['id'] for _, e in plan(EVENTS, 'duplicate')], ['example-created', 'example-created', 'example-updated'])
        self.assertEqual([e['version'] for _, e in plan(EVENTS, 'reorder')], [2, 1])
        self.assertEqual([p for p, _ in plan(EVENTS, 'delayed', .2)], [0, .2])
        self.assertEqual([e for _, e in plan(EVENTS, 'normal')], EVENTS)

    def test_invalid_events(self):
        for events in ([], {}, [1], [{'id': 'bad\nheader'}], [{'id': 'x'}, {'id': 'x'}], [{'id': 'x', 'value': float('nan')}], [{'id': 'x', 'value': 'a' * 65536}]):
            with self.subTest(events=str(events)[:30]), self.assertRaises(ValueError):
                validate_events(events)

    def test_invalid_plans(self):
        for scenario, delay in [('unknown', .1), ('normal', float('nan')), ('delayed', -1), ('delayed', 6)]:
            with self.assertRaises(ValueError):
                plan(EVENTS, scenario, delay)
        for scenario in ('duplicate', 'delayed', 'reorder'):
            with self.assertRaises(ValueError):
                plan(EVENTS[:1], scenario)

    def test_subset_is_typed_and_recursive(self):
        self.assertTrue(matches_subset({'a': {'x': 2, 'y': 3}, 'b': 0}, {'a': {'x': 2}}))
        self.assertFalse(matches_subset({'a': True}, {'a': 1}))
        self.assertFalse(matches_subset({'a': 1.0}, {'a': 1}))
        self.assertFalse(matches_subset({'a': [1, 2]}, {'a': [1]}))
        self.assertFalse(matches_subset({}, {'a': None}))

    def test_url_boundaries(self):
        for url in ('http://127.0.0.1:123/a', 'http://localhost:80', 'http://[::1]/'):
            self.assertEqual(validate_url(url), url)
        for url in ('http://example.com/', 'http://127.0.0.1.evil.test/', 'file:///etc/passwd', 'http://u:p@localhost/', 'http://localhost/?token=x', 'http://localhost/#secret', 'http://localhost:0/', 'http://localhost:bad/'):
            with self.assertRaises(ValueError):
                validate_url(url)
        self.assertEqual(validate_url('https://example.com/', True), 'https://example.com/')

    def test_oracle_validation_before_any_delivery(self):
        for kwargs in ({'state_url': 'http://localhost/state'}, {'expected': {'x': 1}}, {'state_url': 'http://localhost/state', 'expected': {}}, {'timeout': float('inf')}, {'wait': -1}):
            with patch('delivery_probe.core.request_json') as network:
                with self.assertRaises(ValueError):
                    run(EVENTS, 'http://localhost/webhook', **kwargs)
                network.assert_not_called()

    def test_demo_detects_bugs_and_accepts_robust_receiver(self):
        result = demo()
        self.assertTrue(result['demo_assertions_passed'])
        self.assertEqual(len(result['runs']), 8)
        self.assertTrue(all(r['http_accepted'] for r in result['runs']))
        self.assertEqual([r['outcome'] for r in result['runs']], ['verified', 'failed', 'verified', 'failed'] + ['verified'] * 4)

    def test_no_oracle_does_not_claim_correctness(self):
        with receiver() as base:
            result = run(EVENTS, base + '/webhook')
        self.assertEqual(result['outcome'], 'delivered_unverified')
        self.assertIsNone(result['verification']['state_matches'])

    def test_wait_and_delay_are_applied(self):
        with patch('delivery_probe.core.request_json', return_value=(200, b'{"x":1}', None)), patch('delivery_probe.core.time.sleep') as sleep:
            run(EVENTS, 'http://localhost/webhook', 'delayed', delay=.2, state_url='http://localhost/state', expected={'x': 1}, wait=.3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [.2, .3])

    def test_network_failure_and_bad_status(self):
        for response in [(None, None, 'transport_error'), (500, None, 'http_error'), (302, None, 'http_error')]:
            with patch('delivery_probe.core.request_json', return_value=response):
                self.assertEqual(run(EVENTS, 'http://localhost/webhook')['outcome'], 'failed')

    def test_bad_state_and_missing_state(self):
        for body in (b'not json', b'\xff', b'{}'):
            with patch('delivery_probe.core.request_json', side_effect=[(200, b'', None)] * 2 + [(200, body, None)]):
                result = run(EVENTS, 'http://localhost/webhook', state_url='http://localhost/state', expected={'version': 2})
                self.assertEqual(result['outcome'], 'failed')

    def test_reports_do_not_echo_secrets(self):
        secret = 'synthetic-private-value'
        events = [{'id': secret, 'payload': {'secret': secret}}]
        with patch('delivery_probe.core.request_json', return_value=(200, secret.encode(), None)):
            result = run(events, 'http://localhost/private-path')
        serialized = json.dumps(result)
        self.assertNotIn(secret, serialized)
        self.assertNotIn('private-path', serialized)

    def test_redirects_and_large_responses(self):
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                hits.append(self.path)
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/should-not-be-called')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'a' * 65537)

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(request_json(base + '/redirect')[0], 302)
            self.assertEqual(request_json(base + '/large')[2], 'response_too_large')
            self.assertEqual(hits, ['/redirect', '/large'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cli_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.json'
            path.write_text(json.dumps(EVENTS))
            expected = Path(directory) / 'expected.json'
            expected.write_text('{"processed_unique":2,"version":2}')
            for robust, code in ((True, 0), (False, 1)):
                with receiver(robust) as base, contextlib.redirect_stdout(io.StringIO()) as output:
                    actual = main(['run', str(path), '--url', base + '/webhook', '--scenario', 'duplicate', '--state-url', base + '/state', '--expect', str(expected)])
                    self.assertEqual(actual, code)
                    self.assertIn('outcome', json.loads(output.getvalue()))
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(['run', str(path), '--url', 'http://bad.test/private']), 2)
                self.assertNotIn('bad.test', output.getvalue())


if __name__ == '__main__':
    unittest.main()

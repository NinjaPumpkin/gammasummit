"""Unit tests: UW PHX client rate law (card E2.2).

No network, no real clock: transport/sleep/clock are injected. The hard rule
under test — rate limits are NEVER hit: pacing at <=50% of documented limits,
daily cap, cooldown + exponential backoff on any rate signal, auth fallback,
bounded retries on transient upstream failure.
"""
from __future__ import annotations

import json
import unittest

from backend.core.errors import IngestError, RateLimitError, UpstreamError
from backend.ingest.uw_client import PhxClient

OK_CHAINS = json.dumps(
    {"data": [{"expires": "2026-10-09", "oi": 1, "number_of_strikes": 2}]}
).encode()
OK_BODY = json.dumps({"data": [{"x": 1}]}).encode()


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": dict(headers)})
        item = self.responses.pop(0) if self.responses else (200, OK_BODY, {})
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self, start=100.0):
        self.now = start
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def make_client(responses, **kwargs):
    transport = FakeTransport(responses)
    fake = FakeClock()
    defaults = dict(
        base_url="https://phx.test",
        auth_token=None,
        pace_s=0.55,
        daily_cap=100,
        transport=transport,
        sleep=fake.sleep,
        clock=fake.clock,
    )
    defaults.update(kwargs)
    return PhxClient(**defaults), transport, fake


class RateLawTest(unittest.TestCase):
    def test_browser_headers_always_sent(self):
        client, transport, _ = make_client([(200, OK_BODY, {})])
        client.get_json("/api/x")
        headers = transport.calls[0]["headers"]
        self.assertIn("uw-sh", headers)
        self.assertIn("User-Agent", headers)
        self.assertEqual(headers["Referer"], "https://unusualwhales.com/")
        self.assertNotIn("Authorization", headers)

    def test_pacing_gaps_calls(self):
        client, transport, fake = make_client([(200, OK_BODY, {}), (200, OK_BODY, {})])
        client.get_json("/api/a")
        client.get_json("/api/b")
        self.assertEqual(len(transport.calls), 2)
        # second call waited out the min gap (first call's gap <= pace).
        self.assertTrue(any(s > 0.0 for s in fake.sleeps))
        self.assertGreaterEqual(round(fake.now - 100.0, 6), 0.5499)

    def test_pace_below_half_limit_rejected(self):
        with self.assertRaises(Exception):
            PhxClient("https://phx.test", pace_s=0.1)

    def test_daily_cap_blocks_further_calls(self):
        client, transport, _ = make_client(
            [(200, OK_BODY, {}), (200, OK_BODY, {}), (200, OK_BODY, {})], daily_cap=2
        )
        client.get_json("/api/a")
        client.get_json("/api/b")
        with self.assertRaises(RateLimitError) as ctx:
            client.get_json("/api/c")
        self.assertEqual(ctx.exception.detail, "daily_cap")
        self.assertGreater(ctx.exception.retry_after_s, 0)
        self.assertEqual(len(transport.calls), 2)  # never dialed

    def test_429_sets_cooldown_and_refuses_to_dial(self):
        client, transport, fake = make_client([(429, b"{}", {}), (200, OK_BODY, {})])
        with self.assertRaises(RateLimitError) as ctx:
            client.get_json("/api/a")
        cooldown = ctx.exception.retry_after_s
        self.assertGreaterEqual(cooldown, 30.0)
        self.assertEqual(client.paused_until, fake.now + cooldown)
        with self.assertRaises(RateLimitError):
            client.get_json("/api/a")
        self.assertEqual(len(transport.calls), 1)  # paused source never re-dialed

    def test_rate_cooldowns_grow_exponentially(self):
        client, transport, fake = make_client(
            [(429, b"{}", {}), (429, b"{}", {})], rate_cooldown_base_s=30.0
        )
        with self.assertRaises(RateLimitError) as first:
            client.get_json("/api/a")
        fake.now += first.exception.retry_after_s  # wait out the pause
        with self.assertRaises(RateLimitError) as second:
            client.get_json("/api/a")
        self.assertGreater(second.exception.retry_after_s, first.exception.retry_after_s)

    def test_403_unauthenticated_is_a_rate_signal(self):
        client, transport, _ = make_client([(403, b"{}", {})])
        with self.assertRaises(RateLimitError):
            client.get_json("/api/a")

    def test_auth_falls_back_unauthenticated_on_401(self):
        client, transport, _ = make_client(
            [(401, b"{}", {}), (200, OK_BODY, {})], auth_token="tok123"
        )
        payload = client.get_json("/api/a")
        self.assertEqual(payload, {"data": [{"x": 1}]})
        self.assertEqual(client.auth_fallbacks, 1)
        self.assertIn("Authorization", transport.calls[0]["headers"])
        self.assertNotIn("Authorization", transport.calls[1]["headers"])


class RetryTest(unittest.TestCase):
    def test_network_failures_retry_then_recover(self):
        client, transport, fake = make_client(
            [ConnectionError("boom"), ConnectionError("boom"), (200, OK_BODY, {})]
        )
        payload = client.get_json("/api/a")
        self.assertEqual(payload, {"data": [{"x": 1}]})
        self.assertEqual(client.retries, 2)
        self.assertTrue(fake.sleeps)  # backoff happened

    def test_network_failure_exhausts_to_upstream_error(self):
        client, transport, _ = make_client(
            [ConnectionError("boom")] * 4, max_attempts=4
        )
        with self.assertRaises(UpstreamError):
            client.get_json("/api/a")
        self.assertEqual(len(transport.calls), 4)

    def test_5xx_retries_then_upstream_error(self):
        client, transport, _ = make_client([(503, b"{}", {})] * 3, max_attempts=3)
        with self.assertRaises(UpstreamError) as ctx:
            client.get_json("/api/a")
        self.assertEqual(ctx.exception.status, 503)

    def test_4xx_is_not_retried(self):
        client, transport, _ = make_client([(404, b"{}", {}), (200, OK_BODY, {})])
        with self.assertRaises(UpstreamError) as ctx:
            client.get_json("/api/a")
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(len(transport.calls), 1)


class EndpointGuardTest(unittest.TestCase):
    def test_silent_empty_chains_is_upstream_error(self):
        client, _, _ = make_client([(200, b'{"data": []}', {})])
        with self.assertRaises(UpstreamError):
            client.chain_expiries("SPY")

    def test_flow_alerts_may_be_empty(self):
        body = json.dumps({"newer_than": "", "older_than": "", "alerts": []}).encode()
        client, _, _ = make_client([(200, body, {})])
        self.assertEqual(client.flow_alerts("SPY"), [])

    def test_price_requires_market_time(self):
        client, _, _ = make_client([(200, b'{"prev": "1"}', {})])
        with self.assertRaises(UpstreamError):
            client.price("SPY")

    def test_bad_ticker_rejected_before_dial(self):
        client, transport, _ = make_client([])
        with self.assertRaises(IngestError):
            client.chain_expiries("SPY; DROP TABLE x")
        self.assertEqual(len(transport.calls), 0)

    def test_chain_expiry_bad_date_rejected(self):
        client, transport, _ = make_client([])
        with self.assertRaises(IngestError):
            client.chain_expiry("SPY", "09/30/2026")
        self.assertEqual(len(transport.calls), 0)

    def test_stats_shape(self):
        client, _, _ = make_client([(200, OK_BODY, {})])
        client.get_json("/api/a")
        stats = client.stats()
        self.assertEqual(stats["source"], "phx")
        self.assertEqual(stats["calls"], 1)
        self.assertIn("rate_signals", stats)


if __name__ == "__main__":
    unittest.main()

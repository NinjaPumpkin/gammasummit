"""UW PHX fetch client (tree: ingest/uw_client.py) — card E2.2.

UW PHX (phx.unusualwhales.com) is the ONLY production data source. This client
is strictly read-only against upstream and encodes the rate law as a hard
rule — rate limits are NEVER hit:

  - pacing at <=50% of the documented limit (PHX: 4 req/s documented → the
    default 0.55s min gap ≈ 1.8 rps), plus a daily request cap
  - any rate signal (429, or 403 once unauthenticated) pauses the source with
    exponential cooldown (30s base, 900s cap) and raises `RateLimitError`
    carrying `retry_after_s` — the caller must respect the pause, no caller
    may hammer a paused source (get_json refuses to dial while paused)
  - transient upstream failures (network, 5xx) retry with exponential backoff
    + jitter, bounded attempts, then `UpstreamError`

PHX quirks encoded here (RE-verified 2026-09-30 / 2026-10-02):
  - browser headers (`uw-sh` + User-Agent + Referer) are MANDATORY — without
    them every endpoint returns HTTP 200 with an empty payload (silent empty),
    so endpoint helpers treat "empty where rows are structurally required" as
    an upstream failure
  - an auth token (GAMMASUMMIT_PHX_AUTH_TOKEN) is optional; on 401/403 the
    client transparently falls back to unauthenticated calls (slightly less
    accurate gamma upstream, still production-usable)

Transport, sleep and clock are injectable — unit tests never touch the
network. Python 3.10 floor (stdlib only; no env reads — config arrives via
constructor).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Optional

from backend.core.errors import ConfigError, IngestError, RateLimitError, UpstreamError

SOURCE = "phx"
DEFAULT_BASE_URL = "https://phx.unusualwhales.com"
# Public client marker baked into the UW web app (RE evidence) — not a secret.
UW_SH_HEADER = "bpzdbMf9zofibLbATL1O37"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
REFERER = "https://unusualwhales.com/"
DEFAULT_TIMEOUT_S = 60.0

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
EXPIRY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# transport(url, headers, timeout) -> (status, body_bytes, response_headers).
# Raises OSError-family exceptions on network failure (like urllib does).
Transport = Callable[[str, Mapping[str, str], float], tuple[int, bytes, Mapping[str, str]]]


def _default_transport(
    url: str, headers: Mapping[str, str], timeout: float
) -> tuple[int, bytes, Mapping[str, str]]:
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        # HTTP-level failures are responses, not transport failures.
        return exc.code, exc.read(), dict(exc.headers or {})


class PhxClient:
    """Paced, retrying, pause-respecting PHX GET client (read-only)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        auth_token: Optional[str] = None,
        *,
        pace_s: float = 0.55,
        daily_cap: int = 4000,
        max_attempts: int = 4,
        rate_cooldown_base_s: float = 30.0,
        rate_cooldown_cap_s: float = 900.0,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not base_url:
            raise ConfigError("PHX base url is empty")
        if pace_s < 0.5:
            # 4 req/s documented limit — the law caps pacing at 2 rps.
            raise ConfigError("ingest pace below 0.5s would exceed 50% of the PHX limit")
        if daily_cap < 1:
            raise ConfigError("ingest daily cap must be positive")
        self._base_url = base_url.rstrip("/")
        self._token = auth_token or ""
        self._pace_s = pace_s
        self._daily_cap = daily_cap
        self._max_attempts = max_attempts
        self._cooldown_base_s = rate_cooldown_base_s
        self._cooldown_cap_s = rate_cooldown_cap_s
        self._transport = transport or _default_transport
        self._sleep = sleep
        self._clock = clock

        self._last_call_at = 0.0
        self._paused_until = 0.0
        self._consecutive_rate_signals = 0
        self._unauth_fallback = False
        self._cap_day: Optional[dt.date] = None
        self._cap_used = 0

        self.calls = 0
        self.retries = 0
        self.auth_fallbacks = 0
        self.rate_signals = 0
        self.incidents: list[str] = []

    # ------------------------------------------------------------------ stats
    @property
    def calls_today(self) -> int:
        return self._cap_used

    @property
    def paused_until(self) -> float:
        return self._paused_until

    def stats(self) -> dict[str, Any]:
        return {
            "source": SOURCE,
            "calls": self.calls,
            "calls_today": self._cap_used,
            "daily_cap": self._daily_cap,
            "retries": self.retries,
            "auth_fallbacks": self.auth_fallbacks,
            "rate_signals": self.rate_signals,
            "paused_until": self._paused_until,
            "incidents": list(self.incidents),
        }

    def _incident(self, text: str) -> None:
        self.incidents.append(text)
        del self.incidents[:-50]

    # ------------------------------------------------------------- rate law
    def _tick_day(self) -> None:
        today = dt.datetime.now(tz=dt.timezone.utc).date()
        if today != self._cap_day:
            self._cap_day = today
            self._cap_used = 0

    def _seconds_to_utc_midnight(self) -> float:
        now = dt.datetime.now(tz=dt.timezone.utc)
        tomorrow = now.date() + dt.timedelta(days=1)
        midnight = dt.datetime.combine(tomorrow, dt.time(), tzinfo=dt.timezone.utc)
        return max(1.0, (midnight - now).total_seconds())

    def _respect_pause(self) -> None:
        now = self._clock()
        if now < self._paused_until:
            raise RateLimitError(
                "PHX source paused after a rate signal",
                retry_after_s=self._paused_until - now,
                source=SOURCE,
            )

    def _throttle(self) -> None:
        gap = self._pace_s - (self._clock() - self._last_call_at)
        if gap > 0:
            self._sleep(gap)

    def _rate_signal(self, detail: str) -> RateLimitError:
        self._consecutive_rate_signals += 1
        self.rate_signals += 1
        cooldown = min(
            self._cooldown_cap_s,
            self._cooldown_base_s * (2 ** (self._consecutive_rate_signals - 1)),
        )
        self._paused_until = self._clock() + cooldown
        self._incident(f"rate signal ({detail}); source paused {cooldown:.0f}s")
        return RateLimitError(
            f"PHX rate signal ({detail})",
            retry_after_s=cooldown,
            source=SOURCE,
            detail=detail,
        )

    # ------------------------------------------------------------------ fetch
    def _headers(self, authed: bool) -> dict[str, str]:
        h = {
            "uw-sh": UW_SH_HEADER,
            "User-Agent": BROWSER_UA,
            "Referer": REFERER,
            "Accept": "application/json",
        }
        if authed and self._token:
            h["Authorization"] = "Bearer " + self._token
        return h

    def get_json(self, path: str) -> Any:
        """GET one PHX path and parse JSON under the full rate law."""
        self._respect_pause()
        self._tick_day()
        if self._cap_used >= self._daily_cap:
            raise RateLimitError(
                "PHX daily request cap reached",
                retry_after_s=self._seconds_to_utc_midnight(),
                source=SOURCE,
                detail="daily_cap",
            )

        url = self._base_url + path
        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_attempts):
            authed = bool(self._token) and not self._unauth_fallback
            self._throttle()
            self._last_call_at = self._clock()
            self.calls += 1
            self._cap_used += 1
            try:
                status, body, _resp_headers = self._transport(
                    url, self._headers(authed), DEFAULT_TIMEOUT_S
                )
            except (OSError, TimeoutError) as exc:
                last_exc = exc
                self.retries += 1
                if attempt + 1 >= self._max_attempts:
                    self._incident(f"network failure on {path}: {exc!r}")
                    raise UpstreamError(
                        "PHX unreachable", source=SOURCE, detail=repr(exc)
                    ) from exc
                self._backoff(attempt)
                continue

            if status == 200:
                self._consecutive_rate_signals = 0
                try:
                    return json.loads(body.decode("utf-8"))
                except ValueError as exc:
                    raise UpstreamError(
                        "PHX returned invalid JSON", source=SOURCE, detail=repr(exc)
                    ) from exc

            if status in (401, 403) and authed:
                # Auth token rejected/rotated: fall back to unauthenticated
                # (RE-documented behavior) instead of burning retries.
                self.auth_fallbacks += 1
                self._unauth_fallback = True
                self._incident("auth rejected; falling back to unauthenticated")
                continue

            if status == 429 or (status == 403 and not authed):
                raise self._rate_signal(f"HTTP {status} on {path}")

            if 500 <= status < 600:
                last_exc = UpstreamError(
                    f"PHX HTTP {status}", source=SOURCE, status=status
                )
                self.retries += 1
                if attempt + 1 >= self._max_attempts:
                    self._incident(f"HTTP {status} on {path} after retries")
                    raise last_exc
                self._backoff(attempt)
                continue

            # Other 4xx: caller error — retrying cannot help.
            raise UpstreamError(
                f"PHX HTTP {status}", source=SOURCE, status=status, detail=path
            )

        raise UpstreamError("PHX call failed", source=SOURCE, detail=repr(last_exc))

    def _backoff(self, attempt: int) -> None:
        delay = min(8.0, 0.5 * (2 ** attempt)) * (0.5 + random.random())
        self._sleep(delay)

    # ------------------------------------------------------------ endpoints
    def _require_rows(self, payload: Any, path: str, key: str = "data") -> list[dict]:
        """Structurally-required rows must be non-empty: a 200 with an empty
        payload is PHX's documented missing-browser-header / auth failure mode."""
        rows = payload.get(key) if isinstance(payload, dict) else payload
        if not rows:
            raise UpstreamError(
                "PHX silent-empty response (browser headers/auth?)",
                source=SOURCE,
                detail=path,
            )
        return rows

    def chain_expiries(self, ticker: str, limit: int = 200) -> list[dict]:
        ticker = self._check_ticker(ticker)
        path = f"/api/chains_expiry/{ticker}?limit={limit}"
        return self._require_rows(self.get_json(path), path)

    def chain_expiry(self, ticker: str, expiry: str) -> dict:
        ticker = self._check_ticker(ticker)
        if not EXPIRY_RE.match(expiry or ""):
            raise IngestError(f"bad expiry: {expiry!r}", detail=SOURCE)
        path = f"/api/chains_expiry/{ticker}/{expiry}"
        payload = self.get_json(path)
        rows = self._require_rows(payload, path)
        price_data = payload.get("price_data") if isinstance(payload, dict) else {}
        return {"rows": rows, "price_data": price_data or {}}

    def price(self, ticker: str) -> dict:
        ticker = self._check_ticker(ticker)
        path = f"/api/ticker/{ticker}/price/v2"
        payload = self.get_json(path)
        if not isinstance(payload, dict) or not payload.get("market_time"):
            raise UpstreamError(
                "PHX silent-empty price payload", source=SOURCE, detail=path
            )
        return payload

    def flow_alerts(self, ticker: str, limit: int = 50) -> list[dict]:
        ticker = self._check_ticker(ticker)
        path = f"/api/flow/alerts?ticker_symbol={ticker}&limit={limit}"
        payload = self.get_json(path)
        rows = payload.get("alerts") if isinstance(payload, dict) else None
        return list(rows or [])  # empty is legitimate (no alerts fired)

    def dark_pool(self, limit: int = 50) -> list[dict]:
        path = f"/api/flow/dark-pool?limit={limit}"
        payload = self.get_json(path)
        rows = payload.get("trades") if isinstance(payload, dict) else None
        return list(rows or [])

    @staticmethod
    def _check_ticker(ticker: str) -> str:
        ticker = (ticker or "").strip().upper()
        if not TICKER_RE.match(ticker):
            raise IngestError(f"bad ticker: {ticker!r}", detail=SOURCE)
        return ticker

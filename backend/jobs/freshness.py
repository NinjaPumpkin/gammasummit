"""Freshness metric per table/tier (tree: jobs/freshness.py) — card E2.4.

Deep health = data freshness, not process liveness (docs/ops/operations.md
"Freshness = health"; SignalForge knowledge-transfer lesson: a vendor freeze
looked alive for days while row counts kept "working"). Every number here is
driven by PAYLOAD timestamps (the upstream tape time we stored), never by
`now()`-stamped bookkeeping rows — the E2.2 freshness-trust rule.

Checks mirror operations.md verbatim:

  t0_freshness     newest T0 payload ts > 15 min stale during market hours
  downsampler_lag  (T0 max ts - T1 max bucket) > 30 min
  retention_jobs   retention/export job misses its daily window (audit_log)

Per-table metrics (newest payload ts, age, row count) ride the same report so
the UI "Last updated" badge and the alert read one truth. The Uptime Kuma
wiring is a push beacon per check: `--push` posts up/down to each configured
push-monitor URL (`GAMMASUMMIT_KUMA_PUSH_*`, tokens are secrets — env only).
A missing push (job dead) is itself a Kuma alarm (heartbeat age).

`--as-of` is the documented clock hook (same pattern as export_cold): it
shifts "now" for threshold evaluation ONLY — no data is touched. It is how
the deliberate staleness test fires the alarm without faking rows.

CLI:
  python -m backend.jobs.freshness                  # report to stdout
  python -m backend.jobs.freshness --report out.json
  python -m backend.jobs.freshness --push           # + beacon Uptime Kuma
  python -m backend.jobs.freshness --as-of 2026-10-05T18:00:00Z  # staleness test
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional, Sequence
from zoneinfo import ZoneInfo

from backend.core.config import get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

# (table, tier, payload timestamp column). Table names are code constants
# (never user input) — same law as core.db.upsert_sql / jobs/retention.py.
TIER_TABLES: tuple[tuple[str, str, str], ...] = (
    ("gamma_snapshot", "T0", "ts"),
    ("spot_tick", "T0", "ts"),
    ("flow_print", "T0", "ts"),
    ("darkpool_print", "T0", "ts"),
    ("gamma_bucket_5m", "T1", "bucket"),
    ("expiry_rollup_hourly", "T2", "hour"),
    ("strike_eod", "T2", "day"),
    ("contract_daily_stats", "daily", "date"),
    ("underlying_daily_stats", "daily", "date"),
)

OK = "ok"
ALERT = "alert"

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dt.time(9, 30)
MARKET_CLOSE = dt.time(16, 0)


def market_open(now: dt.datetime) -> bool:
    """US regular session Mon-Fri 09:30-16:00 ET (the operations.md gate:
    the T0 staleness alert fires 'during market hours')."""
    local = now.astimezone(MARKET_TZ)
    return local.weekday() < 5 and MARKET_OPEN <= local.time() < MARKET_CLOSE


def _age_s(newest: Optional[dt.datetime], now: dt.datetime) -> Optional[float]:
    if newest is None:
        return None
    return (now - newest).total_seconds()


class FreshnessJob:
    """Computes the freshness metric + verdicts. Read-only against the DB."""

    def __init__(
        self,
        db: Database,
        *,
        now: Optional[Callable[[], dt.datetime]] = None,
        t0_stale_minutes: Optional[int] = None,
        downsampler_lag_minutes: Optional[int] = None,
        retention_late_hours: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self._db = db
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))
        self._t0_stale_s = 60.0 * (t0_stale_minutes if t0_stale_minutes is not None
                                   else settings.freshness_t0_stale_minutes)
        self._lag_s = 60.0 * (downsampler_lag_minutes if downsampler_lag_minutes is not None
                              else settings.freshness_downsampler_lag_minutes)
        self._retention_late_s = 3600.0 * (retention_late_hours if retention_late_hours is not None
                                           else settings.freshness_retention_late_hours)

    # ------------------------------------------------------------- metrics
    async def table_metrics(self, now: dt.datetime) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for table, tier, col in TIER_TABLES:
            row = await self._db.fetchrow(
                f"SELECT max({col}) AS newest, count(*) AS rows FROM {table}"  # noqa: S608
            )
            newest = row["newest"] if row is not None else None
            if isinstance(newest, dt.date) and not isinstance(newest, dt.datetime):
                newest = dt.datetime.combine(newest, dt.time(), tzinfo=dt.timezone.utc)
            out.append({
                "table": table,
                "tier": tier,
                "newest_payload_ts": newest.isoformat() if newest else None,
                "age_s": _age_s(newest, now),
                "rows": int(row["rows"]) if row is not None else 0,
            })
        return out

    async def t0_newest(self) -> Optional[dt.datetime]:
        newest: Optional[dt.datetime] = None
        for table, tier, col in TIER_TABLES:
            if tier != "T0":
                continue
            val = await self._db.fetchval(f"SELECT max({col}) FROM {table}")  # noqa: S608
            if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
                val = dt.datetime.combine(val, dt.time(), tzinfo=dt.timezone.utc)
            if val is not None and (newest is None or val > newest):
                newest = val
        return newest

    async def t1_newest(self) -> Optional[dt.datetime]:
        val = await self._db.fetchval("SELECT max(bucket) FROM gamma_bucket_5m")
        return val

    async def job_runs(self, since: dt.datetime) -> list[dict[str, Any]]:
        """Scheduled job runs from the shared audit ledger (one truth for
        freshness alarms and humans, scheduler.py docstring). The scheduler
        audits action='job.run' with the job name in `target` (its _audit)."""
        rows = await self._db.fetch(
            "SELECT target AS action, ts, detail FROM audit_log "
            "WHERE actor = 'jobs:scheduler' AND action = 'job.run' "
            "AND target IN ('retention_t0', 'export_cold') "
            "AND ts >= $1 ORDER BY ts DESC",
            since,
        )
        out = []
        for r in rows:
            detail = r["detail"]
            if isinstance(detail, str):
                try:
                    detail = json.loads(detail)
                except ValueError:
                    detail = {"raw": detail}
            out.append({"action": r["action"], "ts": r["ts"], "detail": detail})
        return out

    # -------------------------------------------------------------- checks
    async def run(self, *, as_of: Optional[dt.datetime] = None) -> dict[str, Any]:
        now = as_of or self._now()
        is_open = market_open(now)
        tables = await self.table_metrics(now)
        t0_newest = await self.t0_newest()
        t1_newest = await self.t1_newest()
        checks: list[dict[str, Any]] = []

        # 1. t0_freshness — "newest T0 timestamp > 15 min stale during market hours"
        age = _age_s(t0_newest, now)
        if age is None:
            # No T0 payloads at all. During market hours that IS staleness;
            # outside, an idle pipeline is the normal post-close state.
            verdict = ALERT if is_open else OK
            detail = "no T0 payload rows"
        elif age > self._t0_stale_s and is_open:
            verdict = ALERT
            detail = (f"newest T0 payload {age/60.0:.1f} min old "
                      f"(threshold {self._t0_stale_s/60.0:.0f} min, market open)")
        else:
            verdict = OK
            detail = (f"newest T0 payload {age/60.0:.1f} min old"
                      + ("" if is_open else " (market closed — check gated)"))
        checks.append({
            "id": "t0_freshness", "verdict": verdict,
            "value_s": age, "threshold_s": self._t0_stale_s, "detail": detail,
        })

        # 2. downsampler_lag — "(T0 max ts - T1 max ts) > 30 min"
        lag = None
        if t0_newest is not None and t1_newest is not None:
            lag = (t0_newest - t1_newest).total_seconds()
        if lag is None:
            verdict = OK
            detail = "no T0 payload rows — nothing to lag"
        elif lag > self._lag_s:
            verdict = ALERT
            detail = f"downsampler lag {lag/60.0:.1f} min (threshold {self._lag_s/60.0:.0f} min)"
        else:
            verdict = OK
            detail = f"downsampler lag {lag/60.0:.1f} min"
        checks.append({
            "id": "downsampler_lag", "verdict": verdict,
            "value_s": lag, "threshold_s": self._lag_s, "detail": detail,
        })

        # 3. retention_jobs — "retention/export job misses its daily window"
        runs = await self.job_runs(now - dt.timedelta(seconds=self._retention_late_s))
        ok_actions = {r["action"] for r in runs
                      if isinstance(r["detail"], dict) and "error" not in r["detail"]}
        missing = sorted({"retention_t0", "export_cold"} - ok_actions)
        if missing:
            verdict = ALERT
            detail = ("no successful scheduled run in the last "
                      f"{self._retention_late_s/3600.0:.0f}h for: " + ", ".join(missing))
        else:
            verdict = OK
            detail = "retention_t0 + export_cold ran within the daily window"
        checks.append({
            "id": "retention_jobs", "verdict": verdict,
            "value_s": None, "threshold_s": self._retention_late_s, "detail": detail,
        })

        overall = ALERT if any(c["verdict"] == ALERT for c in checks) else OK
        return {
            "generated_at": self._now().isoformat(),
            "as_of": now.isoformat(),
            "market_open": is_open,
            "tables": tables,
            "checks": checks,
            "overall": overall,
        }


# ---------------------------------------------------------------- Uptime Kuma
PUSH_URLS = {
    "overall": "kuma_push_overall",
    "t0_freshness": "kuma_push_t0_freshness",
    "downsampler_lag": "kuma_push_downsampler_lag",
    "retention_jobs": "kuma_push_retention_jobs",
}


def push_url_for(check_id: str, settings: Any) -> Optional[str]:
    attr = PUSH_URLS.get(check_id)
    return getattr(settings, attr, None) if attr else None


def push_beacon(url: str, *, up: bool, msg: str,
                timeout_s: float = 10.0) -> dict[str, Any]:
    """POST one verdict to an Uptime Kuma push monitor.

    Uptime Kuma push API: /api/push/<token>?status=up|down&msg=... — the
    monitor flips on receipt and its notification channel fires. Returns the
    parsed response (or the error) — never raises; a dead beacon must not
    take the freshness job down with it.
    """
    sep = "&" if "?" in url else "?"
    qs = urllib.parse.urlencode({"status": "up" if up else "down", "msg": msg[:200]})
    full = f"{url}{sep}{qs}"
    req = urllib.request.Request(
        full, method="GET", headers={"User-Agent": "gammasummit-freshness/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — operator-configured URL
            body = resp.read().decode("utf-8", "replace")
            return {"ok": True, "http_status": resp.status, "body": body[:200]}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "error": repr(exc)}


def push_all(report: dict[str, Any], settings: Any) -> dict[str, Any]:
    """Push every configured check verdict (+ overall) to its Kuma monitor."""
    verdicts = {"overall": report["overall"]}
    for check in report["checks"]:
        verdicts[check["id"]] = check["verdict"]
    results: dict[str, Any] = {}
    for check_id, verdict in verdicts.items():
        url = push_url_for(check_id, settings)
        if not url:
            continue
        msg = f"{check_id}: {verdict}"
        if check_id != "overall":
            detail = next((c["detail"] for c in report["checks"] if c["id"] == check_id), "")
            msg = f"{check_id}: {verdict} — {detail}"
        results[check_id] = push_beacon(url, up=(verdict == OK), msg=msg)
    return results


# --------------------------------------------------------------------- CLI
def _parse_ts(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Freshness metric per table/tier (E2.4)")
    ap.add_argument("--report", default="", help="write the report JSON here")
    ap.add_argument("--push", action="store_true",
                    help="beacon verdicts to Uptime Kuma push monitors")
    ap.add_argument("--as-of", default="",
                    help="clock hook: evaluate thresholds as of this instant")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    db = Database(settings.database_url)
    await db.connect()
    try:
        as_of = _parse_ts(args.as_of) if args.as_of else None
        report = await FreshnessJob(db).run(as_of=as_of)
        if args.push:
            report["push"] = push_all(report, settings)
        return report
    finally:
        await db.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    report = asyncio.run(_async_main(args))
    text = json.dumps(report, indent=1, default=str)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0 if report["overall"] == OK else 1


if __name__ == "__main__":
    sys.exit(main())

"""Ingest daemon / fleet scheduler (tree: ingest/fleet.py) — card E2.2.

Drives the UW PHX fetchers into T0: one capture cycle per live tickers
(top-200 live policy, docs/ops/data-tiering.md "Universe policy"), plus the
fetch→T0 handler for pgmq lazy-backfill gap messages. Read-only upstream,
batch-upsert downstream (idempotent), full rate law in ingest/uw_client.py.

Scheduler law: this process loop captures DATA only. It never schedules
rollups/retention (single-scheduler rule: pg_cron XOR backend timers — that
choice lands in E2.3 and is the only timer in the system).

Dependency law (master-architecture §9): ingest/jobs/api never import each
other's internals. The backfill-queue enqueue callback is INJECTED here and the
CLI entrypoints are the composition roots that wire ingest <-> jobs — module
code never crosses the boundary.

CLI (dry-run is the default — hard rule):
  python -m backend.ingest.fleet --dry-run --tickers SPY,QQQ      # plan only
  python -m backend.ingest.fleet --execute --once --tickers SPY   # one cycle
  python -m backend.ingest.fleet --execute --loop --interval 300  # daemon
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from typing import Any, Awaitable, Callable, Optional, Sequence

from backend.core.config import Settings, get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError, IngestError, RateLimitError, UpstreamError
from backend.core.logging import bind_payload_ts, configure_logging, get_logger
from backend.ingest import chain_writer, flow_writer, spot_writer
from backend.ingest.uw_client import PhxClient

log = get_logger(__name__)

DATASETS = ("gamma_chain", "spot", "flow", "dark_pool")

# enqueue_backfill(payload dict) -> awaitable queue msg id (wired to
# jobs.backfill at the composition root; None disables gap enqueueing).
EnqueueFn = Callable[[dict], Awaitable[Any]]


async def resolve_universe(db: Database, limit: int = 200) -> list[str]:
    """top-200 live policy: current-month ranking, falling back to the active
    catalog. The data law is ALL tickers — the tail is lazy-backfill, never
    silently dropped."""
    rows = await db.fetch(
        "SELECT ticker FROM top200_membership "
        "WHERE month = date_trunc('month', now())::date "
        "ORDER BY rank LIMIT $1",
        limit,
    )
    if rows:
        return [r["ticker"] for r in rows]
    rows = await db.fetch(
        "SELECT ticker FROM ticker_universe WHERE is_active ORDER BY ticker LIMIT $1",
        limit,
    )
    return [r["ticker"] for r in rows]


class Fleet:
    """Capture cycles + gap backfill handler over one PHX client and one DB."""

    def __init__(
        self,
        client: PhxClient,
        db: Database,
        *,
        max_expiries: int = 8,
        capture_flow: bool = True,
        capture_dark_pool: bool = True,
        enqueue_backfill: Optional[EnqueueFn] = None,
    ) -> None:
        self._client = client
        self._db = db
        self._max_expiries = max_expiries
        self._capture_flow = capture_flow
        self._capture_dark_pool = capture_dark_pool
        self._enqueue = enqueue_backfill

    # ------------------------------------------------------------- capture
    async def run_cycle(self, tickers: Sequence[str]) -> dict[str, Any]:
        """One capture pass. RateLimitError aborts the cycle mid-flight — a
        paused source is never hammered; remaining work goes to the gap queue."""
        started = time.time()
        report: dict[str, Any] = {
            "started_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "tickers_requested": list(tickers),
            "rows": {"gamma_snapshot": 0, "spot_tick": 0, "flow_print": 0, "darkpool_print": 0},
            "failures": [],
            "enqueued": [],
            "aborted": None,
        }
        done: list[str] = []
        try:
            if self._capture_dark_pool:
                await self._capture_dark_pool_once(report)
        except RateLimitError as exc:
            report["aborted"] = f"rate pause during dark-pool capture ({exc.retry_after_s:.0f}s)"

        for ticker in tickers:
            if report["aborted"]:
                report["failures"].append(
                    {"ticker": ticker, "dataset": "*", "error": "cycle_aborted"}
                )
                continue
            try:
                await self._capture_ticker(ticker, report)
                done.append(ticker)
            except RateLimitError as exc:
                report["aborted"] = f"rate pause on {ticker} ({exc.retry_after_s:.0f}s)"
                report["failures"].append(
                    {"ticker": ticker, "dataset": "*", "error": "rate_pause"}
                )
            except (UpstreamError, IngestError) as exc:
                report["failures"].append(
                    {
                        "ticker": ticker,
                        "dataset": "*",
                        "error": getattr(exc, "code", "ingest_error"),
                    }
                )
                log.warning("capture failed", extra={"ticker": ticker, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 — one bad ticker never kills the daemon
                report["failures"].append(
                    {"ticker": ticker, "dataset": "*", "error": type(exc).__name__}
                )
                log.error("capture crashed", extra={"ticker": ticker, "error": repr(exc)})

        await self._enqueue_gaps(report)
        report["tickers_completed"] = done
        report["finished_at"] = dt.datetime.now(tz=dt.timezone.utc).isoformat()
        report["duration_s"] = round(time.time() - started, 2)
        report["client"] = self._client.stats()
        return report

    async def _capture_dark_pool_once(self, report: dict[str, Any]) -> None:
        trades = self._client.dark_pool(limit=200)
        rows, dropped = flow_writer.map_darkpool_rows(trades)
        written = await flow_writer.write_darkpool_prints(self._db, rows)
        report["rows"]["darkpool_print"] += written
        if dropped:
            report.setdefault("dropped", {})["darkpool_print"] = (
                report.get("dropped", {}).get("darkpool_print", 0) + dropped
            )

    async def _capture_ticker(self, ticker: str, report: dict[str, Any]) -> None:
        # Freshness trust: one capture ts per ticker snapshot; the upstream
        # payload timestamp rides the logs (payload_ts) for staleness alarms.
        capture_ts = dt.datetime.now(tz=dt.timezone.utc)

        price_payload = self._client.price(ticker)
        payload_ts = spot_writer.latest_payload_ts(price_payload)
        bind_payload_ts(payload_ts.isoformat() if payload_ts else None)
        spot_rows = spot_writer.map_spot_rows(ticker, price_payload)
        report["rows"]["spot_tick"] += await spot_writer.write_spot_ticks(self._db, spot_rows)

        expiries = self._client.chain_expiries(ticker)
        selected = [
            str(e.get("expires") or "")[:10]
            for e in expiries[: self._max_expiries]
            if e.get("expires")
        ]
        chain_rows: list[dict[str, Any]] = []
        spot = None
        chain_payload_ts = None
        for expiry in selected:
            fetched = self._client.chain_expiry(ticker, expiry)
            contract_rows = fetched["rows"]
            spot = chain_writer.map_spot_from_chain(fetched.get("price_data") or {}) or spot
            chain_rows.extend(
                chain_writer.map_chain_rows(
                    ticker, contract_rows, ts=capture_ts, spot=spot
                )
            )
            stamp = chain_writer.latest_payload_ts(contract_rows)
            if stamp and (chain_payload_ts is None or stamp > chain_payload_ts):
                chain_payload_ts = stamp
        bind_payload_ts(chain_payload_ts.isoformat() if chain_payload_ts else None)
        report["rows"]["gamma_snapshot"] += await chain_writer.write_chain_snapshot(
            self._db, chain_rows
        )

        if self._capture_flow:
            alerts = self._client.flow_alerts(ticker)
            flow_rows, dropped = flow_writer.map_flow_rows(alerts)
            report["rows"]["flow_print"] += await flow_writer.write_flow_prints(
                self._db, flow_rows
            )
            if dropped:
                report.setdefault("dropped", {})["flow_print"] = (
                    report.get("dropped", {}).get("flow_print", 0) + dropped
                )
        log.info(
            "ticker captured",
            extra={"ticker": ticker, "rows": len(chain_rows), "expiries": len(selected)},
        )

    async def _enqueue_gaps(self, report: dict[str, Any]) -> None:
        """Failed ticker work becomes lazy-backfill queue messages (gap fills).
        Best-effort: a queue outage must not fail the capture path."""
        if not self._enqueue:
            return
        today = dt.datetime.now(tz=dt.timezone.utc).date().isoformat()
        seen: set[tuple[str, str]] = set()
        for failure in report["failures"]:
            ticker = failure.get("ticker")
            if not ticker or ticker == "*":
                continue
            for dataset in ("gamma_chain", "spot", "flow"):
                key = (ticker, dataset)
                if key in seen:
                    continue
                seen.add(key)
                payload = {
                    "ticker": ticker,
                    "dataset": dataset,
                    "date_from": today,
                    "date_to": today,
                    "reason": f"cycle_gap:{failure.get('error')}",
                    "requested_by": "fleet",
                    "queued_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
                }
                try:
                    msg_id = await self._enqueue(payload)
                    report["enqueued"].append({"msg_id": msg_id, **payload})
                except Exception as exc:  # noqa: BLE001 — queue is best-effort
                    log.warning("backfill enqueue failed", extra={"error": repr(exc)})

    # ------------------------------------------------- lazy-backfill handler
    async def run_gap(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one lazy-backfill message (fetch + T0 write).

        NOTE: PHX `chains_expiry` serves only the latest settled snapshot
        (`date=` is a no-op upstream, RE-verified) — a gamma_chain gap refetches
        CURRENT state, and `date_from`/`date_to` are recorded for the audit
        trail rather than sent upstream."""
        ticker = str(payload.get("ticker") or "").upper()
        dataset = str(payload.get("dataset") or "")
        if dataset not in DATASETS:
            raise IngestError(f"unknown backfill dataset: {dataset!r}")
        out: dict[str, Any] = {
            "ticker": ticker,
            "dataset": dataset,
            "date_from": payload.get("date_from"),
            "date_to": payload.get("date_to"),
            "rows": 0,
        }
        if dataset == "dark_pool":
            trades = self._client.dark_pool(limit=200)
            rows, _dropped = flow_writer.map_darkpool_rows(trades)
            rows = [r for r in rows if r["ticker"] == ticker]
            out["rows"] = await flow_writer.write_darkpool_prints(self._db, rows)
        elif dataset == "flow":
            alerts = self._client.flow_alerts(ticker)
            rows, _dropped = flow_writer.map_flow_rows(alerts)
            out["rows"] = await flow_writer.write_flow_prints(self._db, rows)
        elif dataset == "spot":
            payload_price = self._client.price(ticker)
            rows = spot_writer.map_spot_rows(ticker, payload_price)
            out["rows"] = await spot_writer.write_spot_ticks(self._db, rows)
        else:  # gamma_chain
            capture_ts = dt.datetime.now(tz=dt.timezone.utc)
            expiries = self._client.chain_expiries(ticker)
            selected = [
                str(e.get("expires") or "")[:10]
                for e in expiries[: self._max_expiries]
                if e.get("expires")
            ]
            rows: list[dict[str, Any]] = []
            spot = None
            for expiry in selected:
                fetched = self._client.chain_expiry(ticker, expiry)
                spot = chain_writer.map_spot_from_chain(fetched.get("price_data") or {}) or spot
                rows.extend(
                    chain_writer.map_chain_rows(
                        ticker, fetched["rows"], ts=capture_ts, spot=spot
                    )
                )
            out["rows"] = await chain_writer.write_chain_snapshot(self._db, rows)
        log.info("backfill gap filled", extra=out)
        return out


# ----------------------------------------------------------------- CLI
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="UW PHX ingest daemon (T0 capture)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan only (default)")
    mode.add_argument("--execute", action="store_true", help="fetch + write T0")
    ap.add_argument("--once", action="store_true", help="single cycle (default)")
    ap.add_argument("--loop", action="store_true", help="run cycles forever")
    ap.add_argument("--interval", type=float, default=300.0, help="seconds between cycles")
    ap.add_argument("--tickers", default="", help="comma list (default: universe policy)")
    ap.add_argument("--max-expiries", type=int, default=0, help="override per-ticker expiries")
    ap.add_argument("--no-flow", action="store_true", help="skip flow alerts capture")
    ap.add_argument("--no-dark-pool", action="store_true", help="skip dark-pool capture")
    ap.add_argument("--report", default="", help="write the cycle report JSON here")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    max_expiries = args.max_expiries or settings.ingest_max_expiries

    if not args.execute:
        if not tickers:
            db = Database(settings.database_url or "")
            await db.connect()
            tickers = await resolve_universe(db)
            await db.close()
        calls_per_ticker = 2 + max_expiries + (0 if args.no_flow else 1)
        plan = {
            "mode": "dry-run (no network, no writes)",
            "tickers": len(tickers),
            "max_expiries": max_expiries,
            "estimated_calls_per_cycle": len(tickers) * calls_per_ticker
            + (0 if args.no_dark_pool else 1),
            "daily_cap": settings.ingest_daily_cap,
            "pace_s": settings.ingest_pace_s,
            "rate_law": "<=50% of documented PHX 4 req/s; cooldown on any rate signal",
        }
        return plan

    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required for --execute")
    db = Database(
        settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout_s=settings.db_command_timeout_s,
    )
    await db.connect()
    try:
        if not tickers:
            tickers = await resolve_universe(db)
        client = PhxClient(
            settings.phx_url,
            settings.phx_auth_token,
            pace_s=settings.ingest_pace_s,
            daily_cap=settings.ingest_daily_cap,
        )

        # Composition root (dependency law): wire the pgmq gap queue lazily —
        # ingest module code never imports jobs module code.
        enqueue: Optional[EnqueueFn] = None
        try:
            from backend.jobs.backfill import enqueue as _enqueue  # noqa: PLC0415

            async def _enqueue_via_db(payload: dict) -> Any:
                return await _enqueue(db, payload)

            enqueue = _enqueue_via_db
        except Exception as exc:  # noqa: BLE001 — queue optional at runtime
            log.warning("backfill queue unavailable", extra={"error": repr(exc)})

        fleet = Fleet(
            client,
            db,
            max_expiries=max_expiries,
            capture_flow=not args.no_flow,
            capture_dark_pool=not args.no_dark_pool,
            enqueue_backfill=enqueue,
        )
        if args.loop:
            report: dict[str, Any] = {"cycles": []}
            while True:
                cycle = await fleet.run_cycle(tickers)
                report["cycles"].append(cycle)
                log.info("cycle done", extra={"rows": cycle["rows"]})
                await asyncio.sleep(args.interval)
        return await fleet.run_cycle(tickers)
    finally:
        await db.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    report = asyncio.run(_async_main(args, settings))
    text = json.dumps(report, indent=1, default=str)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

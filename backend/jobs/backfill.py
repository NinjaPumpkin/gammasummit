"""Lazy-backfill queue worker (tree: jobs/backfill.py) — card E2.2.

pgmq queue `backfill` (db/migrations/0005_pgmq_backfill_queue.sql): gap fills
for T0, triggered by the fleet scheduler (cycle failures) and later by the
API's /jobs/backfill endpoint. Transport only — consuming a message is worker
polling, never a scheduler (single-scheduler law).

Message contract (also documented in migration 0005):
  {"ticker": "SPY", "dataset": "gamma_chain|spot|flow|dark_pool",
   "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD",
   "reason": "...", "requested_by": "...", "queued_at": "<ISO ts>",
   "attempts": 0, "last_error": "..."}

Retry/dead-letter policy (poison-safe):
  - success            → pgmq.delete (ack)
  - handler failure    → re-enqueue with attempts+1 and an exponential `delay`
                         (30s base, 300s cap), old message deleted
  - attempts >= max    → dead-letter: pgmq.a_backfill (error context preserved
                         in the message body)
  - rate pause         → re-enqueued after the upstream `retry_after_s` and
                         does NOT consume an attempt (rate limits are never hit)
  - invalid payload    → immediate dead-letter

Dependency law: the fetch→T0 handler is INJECTED (built by ingest/fleet.py at
the composition root) — jobs module code never imports ingest internals.

CLI (dry-run default — hard rule):
  python -m backend.jobs.backfill --dry-run                 # queue stats
  python -m backend.jobs.backfill --execute --max 25        # consume up to 25
  python -m backend.jobs.backfill --execute --enqueue \
      --ticker SPY --dataset gamma_chain --reason gap_scan
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import math
import sys
from typing import Any, Awaitable, Callable, Optional, Sequence

from backend.core.config import get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError, RateLimitError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

QUEUE = "backfill"
# Owner of the message contract (mirrored in ingest/fleet.py DATASETS — the two
# modules never import each other; migration 0005 is the shared spec).
DATASETS = ("gamma_chain", "spot", "flow", "dark_pool")
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_VT_S = 120

# handler(payload) -> result dict (writes T0). Built by the composition root.
Handler = Callable[[dict], Awaitable[dict]]


def build_message(
    ticker: str,
    dataset: str,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    reason: str = "api_request",
    requested_by: str = "api",
) -> dict[str, Any]:
    today = dt.datetime.now(tz=dt.timezone.utc).date().isoformat()
    return {
        "ticker": (ticker or "").strip().upper(),
        "dataset": dataset,
        "date_from": date_from or today,
        "date_to": date_to or today,
        "reason": reason,
        "requested_by": requested_by,
        "queued_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "attempts": 0,
    }


def valid_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and bool(str(payload.get("ticker") or "").strip())
        and payload.get("dataset") in DATASETS
    )


async def enqueue(db: Database, payload: dict[str, Any]) -> int:
    """pgmq.send — the only producer entrypoint (fleet gaps + API trigger)."""
    return int(
        await db.fetchval(
            "SELECT pgmq.send($1::text, $2::jsonb)", QUEUE, json.dumps(payload, default=str)
        )
    )


async def queue_stats(db: Database) -> dict[str, Any]:
    depth = await db.fetchval(f"SELECT count(*) FROM pgmq.q_{QUEUE}")
    archived = await db.fetchval(f"SELECT count(*) FROM pgmq.a_{QUEUE}")
    oldest = await db.fetchval(
        f"SELECT min(enqueued_at) FROM pgmq.q_{QUEUE}"
    )
    return {
        "queue": QUEUE,
        "depth": int(depth or 0),
        "dead_lettered": int(archived or 0),
        "oldest_enqueued_at": oldest,
    }


class BackfillWorker:
    """Poll-consume loop over the pgmq queue with poison-safe retries."""

    def __init__(
        self,
        db: Database,
        handler: Handler,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        vt_s: int = DEFAULT_VT_S,
    ) -> None:
        if max_attempts < 1:
            raise ConfigError("backfill max_attempts must be >= 1")
        self._db = db
        self._handler = handler
        self._max_attempts = max_attempts
        self._vt_s = vt_s

    async def work_one(self) -> Optional[dict[str, Any]]:
        """Consume one message. Returns a step report, or None when idle."""
        rows = await self._db.fetch(
            "SELECT msg_id, read_ct, message FROM pgmq.read($1::text, $2::integer, 1, NULL)",
            QUEUE,
            self._vt_s,
        )
        if not rows:
            return None
        row = rows[0]
        msg_id = int(row["msg_id"])
        payload = row["message"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        if not valid_payload(payload):
            await self._db.fetchval(
                "SELECT pgmq.archive($1::text, $2::bigint)", QUEUE, msg_id
            )
            log.warning("backfill dead-lettered: invalid payload", extra={"msg_id": msg_id})
            return {"msg_id": msg_id, "outcome": "dead_lettered", "reason": "invalid_payload"}

        try:
            result = await self._handler(payload)
        except RateLimitError as exc:
            # Upstream pause: never burn an attempt, never hammer the source.
            return await self._requeue(
                msg_id,
                payload,
                delay_s=max(1, math.ceil(exc.retry_after_s)),
                error="rate_pause",
                consume_attempt=False,
            )
        except Exception as exc:  # noqa: BLE001 — poison isolation per message
            return await self._requeue(
                msg_id,
                payload,
                delay_s=min(300, 30 * (int(payload.get("attempts") or 0) + 1)),
                error=repr(exc),
                consume_attempt=True,
            )

        await self._db.fetchval("SELECT pgmq.delete($1::text, $2::bigint)", QUEUE, msg_id)
        return {"msg_id": msg_id, "outcome": "processed", "result": result}

    async def _requeue(
        self,
        msg_id: int,
        payload: dict[str, Any],
        *,
        delay_s: int,
        error: str,
        consume_attempt: bool,
    ) -> dict[str, Any]:
        attempts = int(payload.get("attempts") or 0) + (1 if consume_attempt else 0)
        updated = dict(payload)
        updated["attempts"] = attempts
        updated["last_error"] = error
        if consume_attempt and attempts >= self._max_attempts:
            # Dead-letter with full error context: park a copy in the archive.
            new_id = await enqueue(self._db, updated)
            await self._db.fetchval(
                "SELECT pgmq.delete($1::text, $2::bigint)", QUEUE, msg_id
            )
            await self._db.fetchval(
                "SELECT pgmq.archive($1::text, $2::bigint)", QUEUE, new_id
            )
            log.warning(
                "backfill dead-lettered: attempts exhausted",
                extra={"msg_id": msg_id, "attempts": attempts, "error": error},
            )
            return {"msg_id": msg_id, "outcome": "dead_lettered", "attempts": attempts}

        new_id = await self._db.fetchval(
            "SELECT pgmq.send($1::text, $2::jsonb, $3::integer)",
            QUEUE,
            json.dumps(updated, default=str),
            delay_s,
        )
        await self._db.fetchval("SELECT pgmq.delete($1::text, $2::bigint)", QUEUE, msg_id)
        return {
            "msg_id": msg_id,
            "outcome": "requeued",
            "new_msg_id": int(new_id),
            "attempts": attempts,
            "delay_s": delay_s,
            "error": error,
        }

    async def run(self, max_messages: Optional[int] = None) -> dict[str, Any]:
        report: dict[str, Any] = {
            "processed": 0,
            "requeued": 0,
            "dead_lettered": 0,
            "steps": [],
        }
        consumed = 0
        while max_messages is None or consumed < max_messages:
            step = await self.work_one()
            if step is None:
                break
            consumed += 1
            report["steps"].append(step)
            outcome = step.get("outcome")
            if outcome == "processed":
                report["processed"] += 1
            elif outcome == "requeued":
                report["requeued"] += 1
            elif outcome == "dead_lettered":
                report["dead_lettered"] += 1
        report["consumed"] = consumed
        return report


# ----------------------------------------------------------------- CLI
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="pgmq lazy-backfill queue worker")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="queue stats only (default)")
    mode.add_argument("--execute", action="store_true", help="consume / enqueue for real")
    ap.add_argument("--max", type=int, default=25, help="max messages per run")
    ap.add_argument("--enqueue", action="store_true", help="enqueue one gap message")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--dataset", default="", choices=["", *DATASETS])
    ap.add_argument("--date-from", default="")
    ap.add_argument("--date-to", default="")
    ap.add_argument("--reason", default="api_request")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    db = Database(settings.database_url)
    await db.connect()
    try:
        if not args.execute:
            return {
                "mode": "dry-run (no writes)",
                **(await queue_stats(db)),
                "max_attempts": settings.backfill_max_attempts,
            }
        if args.enqueue:
            if not args.ticker or not args.dataset:
                raise ConfigError("--enqueue needs --ticker and --dataset")
            payload = build_message(
                args.ticker,
                args.dataset,
                date_from=args.date_from or None,
                date_to=args.date_to or None,
                reason=args.reason,
                requested_by="cli",
            )
            msg_id = await enqueue(db, payload)
            return {"enqueued": payload, "msg_id": msg_id}

        # Composition root (dependency law): handler built from ingest's gap
        # pipeline; jobs code never imports ingest internals.
        from backend.ingest.fleet import Fleet  # noqa: PLC0415
        from backend.ingest.uw_client import PhxClient  # noqa: PLC0415

        client = PhxClient(
            settings.phx_url,
            settings.phx_auth_token,
            pace_s=settings.ingest_pace_s,
            daily_cap=settings.ingest_daily_cap,
        )
        fleet = Fleet(client, db, max_expiries=settings.ingest_max_expiries)
        worker = BackfillWorker(
            db, fleet.run_gap, max_attempts=settings.backfill_max_attempts
        )
        return await worker.run(max_messages=args.max)
    finally:
        await db.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    report = asyncio.run(_async_main(args))
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

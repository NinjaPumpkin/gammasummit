"""Gamma chain snapshot writer (tree: ingest/chain_writer.py) — card E2.2.

Maps PHX `/api/chains_expiry/{T}/{EXP}` contract rows (25 keys, RE-verified
shape 2026-10-02) onto `gamma_snapshot` rows: one strike cell per side split
(call_*/put_* columns — the within-expiry net_gex = call_gex − put_gex grain of
the value model). Batch-upsert via backend.core.db (conflict keys = table PK),
idempotent on retry.

Known upstream limits (documented, not guessed):
  - PHX chains serve the LATEST settled snapshot per expiry (`date=` param is
    a no-op upstream) — backfill of historical intraday chains is impossible
    from this source; the lazy-backfill queue only refetches current state.
  - per-contract bid/ask prices are not served (only bid_volume/ask_volume) —
    call_bid/call_ask/put_bid/put_ask stay NULL; never synthesized.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Optional, Sequence

from backend.core.db import Database
from backend.ingest.t0_writer import parse_ts, to_float, to_int, write_rows

SOURCE = "phx_chains_expiry"

_GREEKS = (
    ("iv", "iv"),
    ("delta", "delta"),
    ("gamma", "gamma"),
    ("vega", "vega"),
    ("theta", "theta"),
)


def map_chain_rows(
    ticker: str,
    contract_rows: Sequence[Mapping[str, Any]],
    *,
    ts: dt.datetime,
    spot: Optional[float],
    source: str = SOURCE,
) -> list[dict[str, Any]]:
    """Merge call/put contract rows into one gamma_snapshot row per
    (expiry, strike). `ts` is the capture time of the snapshot (one value per
    ticker snapshot, so writer retries stay idempotent)."""
    ticker = (ticker or "").strip().upper()
    cells: dict[tuple[str, float], dict[str, Any]] = {}
    for r in contract_rows:
        expiry = str(r.get("expires") or "")[:10]
        strike = to_float(r.get("strike"))
        opt_type = str(r.get("option_type") or "").lower()
        if not expiry or strike is None or not opt_type:
            continue
        side = "call" if opt_type.startswith("c") else "put"
        key = (expiry, strike)
        cell = cells.get(key)
        if cell is None:
            cell = {
                "ticker": ticker,
                "expiry": dt.date.fromisoformat(expiry),
                "strike": strike,
                "ts": ts,
                "spot": spot,
                "call_oi": None,
                "put_oi": None,
                "call_volume": None,
                "put_volume": None,
                "call_bid": None,  # not served per-contract upstream
                "call_ask": None,
                "put_bid": None,
                "put_ask": None,
                "call_iv": None,
                "put_iv": None,
                "call_delta": None,
                "put_delta": None,
                "call_gamma": None,
                "put_gamma": None,
                "call_vega": None,
                "put_vega": None,
                "call_theta": None,
                "put_theta": None,
                "source": source,
            }
            cells[key] = cell
        cell[f"{side}_oi"] = to_int(r.get("open_interest"))
        cell[f"{side}_volume"] = to_int(r.get("volume"))
        for upstream, greek in _GREEKS:
            cell[f"{side}_{greek}"] = to_float(r.get(upstream))
    return [cells[k] for k in sorted(cells)]


def map_spot_from_chain(price_data: Mapping[str, Any]) -> Optional[float]:
    """`price_data.price` is a string like "736.9" — coerce or give up."""
    return to_float(price_data.get("price")) if isinstance(price_data, Mapping) else None


def latest_payload_ts(contract_rows: Sequence[Mapping[str, Any]]) -> Optional[dt.datetime]:
    """Freshness trust (core/logging payload-ts law): the latest per-contract
    tape time is the payload timestamp of a chain snapshot."""
    stamps = [parse_ts(r.get("last_tape_time")) for r in contract_rows]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


async def write_chain_snapshot(db: Database, rows: Sequence[Mapping[str, Any]]) -> int:
    return await write_rows(db, "gamma_snapshot", rows)

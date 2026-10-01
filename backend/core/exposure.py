"""Clean-room cross-expiry exposure calculator (card E0.3).

Derived fresh from math + RE evidence (docs/build/skylit-value-model.md,
docs/build/cross-expiry-layer-spec.md). Zero code copied from any reference
trading system; zero external trading-system imports. Production inputs are
UW `gamma_data_v2` rows ONLY (columns listed in UW_COLUMNS).

Value model (spec §2):
    g(s,e,t) = call_gex - put_gex          within-expiry net gex (established)
    C(s,e,t) = a_e(t) * g(s,e,t)           cell value
    V(s,t)   = sum_e C(s,e,t)              node value (established, exact)
    star     = argmax_(s,e) |C|            per-expiry star = column max
    king     = argmax_s |V(s,t)|           established

Cross-expiry layer (spec §3.3/§3.4/§4):
    psi_e(t) = sgn(net_col_e) * exp(gamma * theta . x_e(t))   (gamma = MAG_GAMMA,
                                          E0.5b magnitude temper, spec §12)
    a_e(t)   = lambda * a_e(t_prev) + (1 - lambda) * psi_e(t)   (EWMA)
    w_e(t)   = a_e(t) / (sum_e' |a_e'(t)| / E)                  (display)

EXACT feature semantics match the E0.2 fit design matrix that produced the
fitted theta (scripts/e02_cross_expiry_fit.py:expiry_features); where the spec
prose notates a term more loosely, the fit matrix wins, per spec §8.4 (theta is
meaningful only against its own design matrix):

    dte            = max((expiry_date - batch_date).days, 0.25)   calendar days
    log_dte        = log(dte)
    log_gmag       = log(G_e + 1)        (spec §3.3 notates "log G_e")
    net_col        = sum_s g(s,e)
    net_col_sign_log = copysign(log1p(|net_col|), net_col)
    ask            = sum_s (call_ask_vol + put_ask_vol)
    bid            = sum_s (call_bid_vol + put_bid_vol)
    askbid_imb     = (ask - bid) / (ask + bid + 1)
    doi            = sum_s [(call_oi - call_prev_oi) + (put_oi - put_prev_oi)]
    doi_migration  = copysign(log1p(|doi|), doi)
    COM_e          = sum_s |g(s,e)| * s / G_e
    com_dist_rel   = |COM_e - spot| / spot    (0.0 when G_e == 0 or spot <= 0)
    tod_frac       = (hour*60 + minute) / 1440        of the batch timestamp

Column aggregates run over ALL batch rows for the expiry (production has no
second grid; spec §6.1 "column features from the UW batch itself"). The E0.2
fit computed g-derived features on the Skylit capture grid subset only — that
is a fit-time artifact of pairing and is not reproducible in production.

Fitted constants below are the ONLY fitted inputs (spec §8.4); provenance is
stated next to each. Everything else is established math or spec edge rules.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

# ---------------------------------------------------------------- constants
# Provenance: E0.2 fit, data/e02/fit_results.json:feature_model.theta
# (OLS of log|a_e| on [intercept] + the 7 features above, 14,470 samples).
THETA: Tuple[float, ...] = (
    25.345046,    # intercept
    -0.982964,    # log_dte
    -0.674570,    # log_gmag
    -0.674570,    # net_col_sign_log   (rank-deficient split with log_gmag,
    -0.300289,    # askbid_imbalance    treat their sum as one effective term)
    0.077756,     # doi_migration
    -12.066771,   # com_dist_rel
    1.449352,     # tod_frac
)
FEATURE_ORDER: Tuple[str, ...] = (
    "log_dte", "log_gmag", "net_col_sign_log", "askbid_imbalance",
    "doi_migration", "com_dist_rel", "tod_frac",
)

# Provenance: E0.2 fit, data/e02/fit_results.json:dynamic.per_day (lambda grid
# corner 0.995 at the 5-s trajectory step for all 11 symbol-days).
LAMBDA_5S: float = 0.995
# lambda_batch = lambda_5s^(cadence_s / 5) with measured cadence 234-248 s
# -> 0.78-0.80; spec §3.4/§4 fixes the batch value at 0.79.
LAMBDA_BATCH: float = 0.79
# Measured UW daemon batch cadence (spec §4): median 234 s (09-28), 248 s (09-30).
MEDIAN_CADENCE_S: float = 241.0
# One batch interval = 2 x median cadence ~= 480 s (spec §6.3 wording).
BATCH_INTERVAL_S: float = 2.0 * MEDIAN_CADENCE_S

# Provenance: E0.5b magnitude temper (spec 12, card E0.5b G2). The psi
# log-magnitude is tempered: |psi_e| = exp(MAG_GAMMA * theta.x_e), i.e.
# |psi| -> |psi|^MAG_GAMMA. Derivation: our per-batch |a_e| spread (max/min)
# p50 11,370x vs their empirical free-weight spread p50 623x on the Tier-A
# set (scripts/e05b_king_fix.py probe lineage, data/e05b/sweep.json) ->
# gamma = ln(623.3)/ln(11370.2) = 0.689, rounded 0.7; the variant sweep
# (gamma grid {0, 0.25, 0.5, 0.7, 0.85}) confirms 0.7 as the best grid point
# for king exact. Sign convention (spec 6.4) is NOT changed -- measured
# unpredictable (all candidates ~50%, docs/build/e05b-king-parity.md). Valid
# only on the 3 Tier-A days (pilot-grade; gate re-measure ~2026-10-28, card
# t_b157a485). gamma = 1.0 reproduces the pre-E0.5b model exactly.
MAG_GAMMA: float = 0.7

# UW gamma_data_v2 columns consumed (spec §8.3). Other columns are ignored.
UW_COLUMNS: Tuple[str, ...] = (
    "strike", "expiry_date", "call_gex", "put_gex", "call_oi", "put_oi",
    "call_volume", "put_volume", "call_ask_vol", "call_bid_vol",
    "put_ask_vol", "put_bid_vol", "call_prev_oi", "put_prev_oi", "spot_price",
)

TsLike = Union[str, float, int, datetime]
Row = Mapping[str, Any]


# ---------------------------------------------------------------- utilities

def parse_ts(value: TsLike) -> datetime:
    """Accept ISO strings (Z or +00:00), epoch seconds, or datetime -> aware UTC."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    else:
        raise TypeError(f"unsupported timestamp: {type(value).__name__}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _f(row: Row, key: str) -> float:
    v = row.get(key)
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def net_gex(row: Row) -> float:
    """g(s,e,t) = call_gex - put_gex (established within-expiry math, spec §2)."""
    return _f(row, "call_gex") - _f(row, "put_gex")


# ---------------------------------------------------------------- batch

def normalize_batch(
    rows: Iterable[Row],
    ts: TsLike,
    prev_ts: Optional[TsLike] = None,
    symbol: Optional[str] = None,
    spot: Optional[float] = None,
) -> dict:
    """Canonical batch dict from UW gamma_data_v2 rows.

    Spec §6.5 (UW-side hygiene): rows whose `fetched_at` deviates more than one
    batch interval (BATCH_INTERVAL_S) from the batch timestamp are dropped and
    counted. Rows without `fetched_at` are kept (nothing to check against).

    `prev_ts` = timestamp of the previous batch for this symbol; callers should
    always pass it so `cross_expiry_weights` can apply the §6.3 gap rule.
    `spot` overrides the per-row `spot_price` median (e.g. when the row cache
    does not carry spot_price); without either, com_dist_rel falls back to 0.0.
    """
    t = parse_ts(ts)
    kept: List[dict] = []
    dropped = 0
    spot_vals: List[float] = []
    for row in rows:
        fetched = row.get("fetched_at")
        if fetched:
            try:
                dev = abs((parse_ts(str(fetched)) - t).total_seconds())
            except (TypeError, ValueError):
                dev = 0.0
            if dev > BATCH_INTERVAL_S:
                dropped += 1
                continue
        try:
            strike = float(row["strike"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        expiry = row.get("expiry_date")
        if not expiry:
            dropped += 1
            continue
        rec = {"strike": strike, "expiry_date": str(expiry)}
        for key in UW_COLUMNS:
            if key in ("strike", "expiry_date"):
                continue
            rec[key] = _f(row, key)
        sp = row.get("spot_price")
        if sp is not None:
            try:
                spot_vals.append(float(sp))
            except (TypeError, ValueError):
                pass
        kept.append(rec)
    if spot is None and spot_vals:
        spot_vals.sort()
        spot = spot_vals[len(spot_vals) // 2]
    batch = {
        "ts": t.isoformat(),
        "symbol": symbol,
        "spot": float(spot) if spot else None,
        "rows": kept,
        "n_rows": len(kept),
        "dropped_stale_rows": dropped,
    }
    if prev_ts is not None:
        batch["prev_ts"] = parse_ts(prev_ts).isoformat()
    return batch


# ---------------------------------------------------------------- psi layer

def _columns(batch: Mapping) -> Dict[str, dict]:
    """Per-expiry column aggregates over ALL batch rows (spec §3.3/§6.1)."""
    cols: Dict[str, dict] = {}
    for row in batch["rows"]:
        e = row["expiry_date"]
        col = cols.setdefault(e, {"gmag": 0.0, "net_col": 0.0, "ask": 0.0,
                                  "bid": 0.0, "doi": 0.0, "com_num": 0.0})
        g = net_gex(row)
        col["gmag"] += abs(g)
        col["net_col"] += g
        col["com_num"] += abs(g) * row["strike"]
        col["ask"] += row["call_ask_vol"] + row["put_ask_vol"]
        col["bid"] += row["call_bid_vol"] + row["put_bid_vol"]
        col["doi"] += (row["call_oi"] - row["call_prev_oi"]) \
            + (row["put_oi"] - row["put_prev_oi"])
    return cols


def expiry_features(batch: Mapping, expiry: str) -> List[float]:
    """Feature row x_e(t) for one expiry (7 terms, FEATURE_ORDER)."""
    t = parse_ts(batch["ts"])
    col = _columns(batch)[expiry]
    dte = max((date.fromisoformat(expiry) - t.date()).days, 0.25)
    gmag = col["gmag"]
    net_col = col["net_col"]
    ask, bid = col["ask"], col["bid"]
    doi = col["doi"]
    spot = batch.get("spot") or 0.0
    if gmag > 0 and spot > 0:
        com = col["com_num"] / gmag
        com_dist = abs(com - spot) / spot
    else:
        com_dist = 0.0
    tod = (t.hour * 60 + t.minute) / (24 * 60)
    return [
        math.log(dte),
        math.log(gmag + 1.0),
        math.copysign(math.log1p(abs(net_col)), net_col),
        (ask - bid) / (ask + bid + 1.0),
        math.copysign(math.log1p(abs(doi)), doi),
        com_dist,
        tod,
    ]


def psi_weights(batch: Mapping, gamma: float = MAG_GAMMA) -> Dict[str, float]:
    """psi_e(t) = sgn(net_col_e) * exp(gamma * theta . [1, x_e]) per batch expiry.

    Magnitude temper (E0.5b, spec §12): |psi| = exp(gamma * dot), i.e.
    |psi| -> |psi|^gamma; gamma = 1.0 reproduces the pre-E0.5b model exactly.
    Sign convention (spec §6.4, OPEN ITEM): sgn(a_e) = sgn(sum_s g(s,e)),
    net_col == 0 counts as positive (matches the fit matrix convention). Do NOT
    trust the sign for dollar-signed display; king selection uses |V|.
    """
    out: Dict[str, float] = {}
    for expiry in sorted(_columns(batch)):
        col = _columns(batch)[expiry]
        if col["gmag"] == 0.0:
            out[expiry] = 0.0  # spec §6.2: zero column contributes nothing
            continue
        x = expiry_features(batch, expiry)
        dot = THETA[0] + sum(th * xi for th, xi in zip(THETA[1:], x))
        sgn = 1.0 if x[2] >= 0 else -1.0  # x[2] == net_col_sign_log
        out[expiry] = sgn * math.exp(gamma * dot)
    return out


def cross_expiry_weights(batch: Mapping, state: Mapping[str, float],
                         gamma: float = MAG_GAMMA) -> Dict[str, float]:
    """Normative layer (spec §3.4/§4): EWMA recursion over psi.

    a_e(t) = LAMBDA_BATCH * a_e(t_prev) + (1 - LAMBDA_BATCH) * psi_e(t)

    - cold start (expiry absent from `state`): a_e = psi_e (spec §4).
    - gap rule (spec §6.3): when (ts - prev_ts) exceeds one batch interval
      (~480 s) the state is stale -> reset to psi on this batch. `prev_ts` is
      read from `batch["prev_ts"]`; without it the gap is treated as 0 (state
      assumed fresh) — pass it for exact §6.3 behaviour.
    - zero column (spec §6.2): a_e = 0 exactly.
    - only expiries present in the batch are returned (absent expiries have no
      rows to weight and contribute nothing, spec §6.6).
    """
    t = parse_ts(batch["ts"])
    gap_s = 0.0
    if batch.get("prev_ts"):
        gap_s = (t - parse_ts(batch["prev_ts"])).total_seconds()
    fresh = gap_s <= BATCH_INTERVAL_S
    psi = psi_weights(batch, gamma=gamma)
    zero_cols = {e for e, col in _columns(batch).items() if col["gmag"] == 0.0}
    out: Dict[str, float] = {}
    for expiry, psi_e in psi.items():
        if expiry in zero_cols:
            out[expiry] = 0.0  # spec §6.2: zero column overrides the recursion
            continue
        prev = state.get(expiry)
        if fresh and prev is not None:
            out[expiry] = LAMBDA_BATCH * float(prev) + (1.0 - LAMBDA_BATCH) * psi_e
        else:
            out[expiry] = psi_e
    return out


# ---------------------------------------------------------------- outputs

def cell_values(batch: Mapping, weights: Mapping[str, float]) -> Dict[Tuple[float, str], float]:
    """C(s,e,t) = a_e(t) * g(s,e,t) for every batch (strike, expiry) pair."""
    cells: Dict[Tuple[float, str], float] = {}
    for row in batch["rows"]:
        key = (row["strike"], row["expiry_date"])
        cells[key] = cells.get(key, 0.0) + weights.get(row["expiry_date"], 0.0) * net_gex(row)
    return cells


def node_values(batch: Mapping, weights: Mapping[str, float]) -> Dict[float, float]:
    """V(s,t) = sum_e a_e(t) * g(s,e,t) — per-strike node value (spec §8.1)."""
    values: Dict[float, float] = {}
    for row in batch["rows"]:
        s = row["strike"]
        values[s] = values.get(s, 0.0) + weights.get(row["expiry_date"], 0.0) * net_gex(row)
    return values


def select_nodes(values: Mapping[float, float],
                 cells: Optional[Mapping[Tuple[float, str], float]] = None) -> dict:
    """king = argmax|V|, top-6 by |V|, per-expiry + global star from cells.

    Ties break toward the smallest strike (then smallest expiry for the global
    star) so results are deterministic. `cells` enables star selection
    (star = argmax |C| cell of the grid; per-expiry star = column max).
    """
    if not values:
        return {"king": None, "top6": [], "stars": {}, "global_star": None}
    ordered = sorted(values.items())  # strike asc -> deterministic ties
    king = min(ordered, key=lambda kv: (-abs(kv[1]), kv[0]))[0]
    top6 = [s for s, _ in sorted(ordered, key=lambda kv: (-abs(kv[1]), kv[0]))[:6]]
    stars: Dict[str, float] = {}
    global_star = None
    if cells:
        per_exp: Dict[str, Tuple[float, str, float]] = {}
        for (s, e), v in cells.items():
            cur = per_exp.get(e)
            if cur is None or (-abs(v), s) < (-abs(cur[2]), cur[0]):
                per_exp[e] = (s, e, v)
        stars = {e: rec[0] for e, rec in sorted(per_exp.items())}
        best: Optional[Tuple[float, str, float]] = None
        for (s, e), v in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if best is None or (-abs(v), s, e) < (-abs(best[2]), best[0], best[1]):
                best = (s, e, v)
        if best is not None:
            global_star = {"strike": best[0], "expiry": best[1], "value": best[2]}
    return {"king": king, "top6": top6, "stars": stars, "global_star": global_star}


def display_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    """Scale-free display weights w_e = a_e / (sum|a_e| / E) (spec §3.4/§6.8)."""
    if not weights:
        return {}
    denom = sum(abs(a) for a in weights.values()) / len(weights)
    if denom == 0.0:
        return {e: 0.0 for e in weights}
    return {e: a / denom for e, a in weights.items()}


# ------------------------------------------------- §10 cell-level dynamic state
# State-augmented value model (spec §10.3), linear in STATE_BETA:
#
#   C(s,e,t) = a_e(t) * (b1*g + b2*q_g + b3*f + b4*q_f + b5*g*rho_e)
#              + (b6*d(s) + b7*r(s) + b8*tau(s)) / E(t)
#   V(s,t)   = sum_e C(s,e,t)
#
# With STATE_BETA == (1, 0, ..., 0) this reduces EXACTLY to the §2 baseline
# C = a_e * g. State variables (spec §10.2): per-cell gex/flow EWMAs with
# time-aware decay, per-expiry rolling ceiling/floor of G_e within the session
# day, and node interaction counts (touched / rejected / delivered) from the
# batch-resolution spot path. State survives gaps (never reset — §10.4.2).

STATE_FEATURE_ORDER: Tuple[str, ...] = (
    "g", "q_g", "f", "q_f", "g_rho", "node_deliver", "node_reject", "node_touch",
)
# Provenance: E0.5a fit, data/e05a/state_fit.json (profiled-LS over the Tier-A
# set, 2026-09-28/29/30; PILOT-GRADE on < 20 aligned days — spec §10.4.4.
# Daily refit: python3 scripts/e05a_state_fit.py fit (cron gammasummit-e02-daily-refit).
LAMBDA_CELL: float = 0.99
STATE_BETA: Tuple[float, ...] = (
    0.791887839, -0.258052945, -0.000170497, -0.000108827,
    -0.553463898, -3.517e-06, -1.216e-06, -1.7323e-05,
)


def cell_flow(row: Row) -> float:
    """f(s,e,t) = (call_oi - call_prev_oi) + (put_oi - put_prev_oi) (spec §10.2)."""
    return ((row.get("call_oi", 0.0) - row.get("call_prev_oi", 0.0))
            + (row.get("put_oi", 0.0) - row.get("put_prev_oi", 0.0)))


def new_cell_state() -> dict:
    """Fresh §10 state store for one symbol (spec §10.4.1)."""
    return {"q_g": {}, "q_f": {}, "n_tch": {}, "n_del": {}, "n_rej": {},
            "ceil": {}, "floor": {}, "day": None,
            "prev_spot": None, "prev_ts": None}


def _node_band(grid: List[float], s: float) -> float:
    """delta_s = min(s - s_prev, s_next - s) / 2 (spec §10.2.4)."""
    if not grid:
        return 2.5
    gaps = []
    # exact neighbors in the sorted grid
    prevs = [x for x in grid if x < s]
    nexts = [x for x in grid if x > s]
    if prevs:
        gaps.append(s - max(prevs))
    if nexts:
        gaps.append(min(nexts) - s)
    if not gaps:
        return 2.5
    return min(gaps) / 2.0


def update_cell_state(batch: Mapping, state: Mapping, lam: float = LAMBDA_CELL) -> dict:
    """One §10.2 state update from one UW batch; returns a NEW dict (input kept).

    - per-cell q_g / q_f: q = lam_k * q_prev + (1 - lam_k) * obs, lam_k =
      lam ** (dt / MEDIAN_CADENCE_S), dt clamped to >= 1 s; first observation
      initializes q = obs. Never reset (§10.4.2).
    - rolling ceil/floor of G_e per session day (UTC date change resets).
    - interaction counts from the spot path: touch / deliver / reject per
      §10.2.4. Requires spot on both consecutive batches (§10.4.7) — without
      either spot the step updates no counts.
    """
    st = {"q_g": dict(state.get("q_g", {})), "q_f": dict(state.get("q_f", {})),
          "n_tch": dict(state.get("n_tch", {})), "n_del": dict(state.get("n_del", {})),
          "n_rej": dict(state.get("n_rej", {})), "ceil": dict(state.get("ceil", {})),
          "floor": dict(state.get("floor", {})), "day": state.get("day"),
          "prev_spot": state.get("prev_spot"), "prev_ts": state.get("prev_ts")}
    t = parse_ts(batch["ts"])
    day = t.date().isoformat()
    if st["day"] != day:
        st["day"] = day
        st["ceil"] = {}
        st["floor"] = {}
    if st["prev_ts"] is not None:
        dt = max((t - parse_ts(st["prev_ts"])).total_seconds(), 1.0)
    else:
        dt = MEDIAN_CADENCE_S
    lam_k = lam ** (dt / MEDIAN_CADENCE_S)
    cols: Dict[str, float] = {}
    for row in batch["rows"]:
        key = (row["strike"], row["expiry_date"])
        g = net_gex(row)
        f = cell_flow(row)
        qg = st["q_g"].get(key)
        qf = st["q_f"].get(key)
        st["q_g"][key] = g if qg is None else lam_k * qg + (1.0 - lam_k) * g
        st["q_f"][key] = f if qf is None else lam_k * qf + (1.0 - lam_k) * f
        cols[row["expiry_date"]] = cols.get(row["expiry_date"], 0.0) + abs(g)
    for e, gmag in cols.items():
        st["ceil"][e] = max(gmag, st["ceil"].get(e, gmag))
        st["floor"][e] = min(gmag, st["floor"].get(e, gmag))
    # interaction counts (spec §10.2.4)
    spot = batch.get("spot")
    prev_spot = st["prev_spot"]
    if spot is not None and prev_spot is not None:
        grid = sorted({row["strike"] for row in batch["rows"]})
        for s in grid:
            delta = _node_band(grid, s)
            in_prev = abs(prev_spot - s) <= delta
            in_cur = abs(spot - s) <= delta
            crossed = (prev_spot - s) * (spot - s) < 0
            if in_cur:
                st["n_tch"][s] = st["n_tch"].get(s, 0) + 1
            if crossed:
                st["n_del"][s] = st["n_del"].get(s, 0) + 1
            if in_prev and not in_cur and not crossed:
                st["n_rej"][s] = st["n_rej"].get(s, 0) + 1
    if spot is not None:
        st["prev_spot"] = float(spot)
    st["prev_ts"] = t.isoformat()
    return st


def node_state_scores(state: Mapping, strike: float) -> Tuple[float, float, float]:
    """(d, r, tau) scores for one node (spec §10.2.4)."""
    nt = state.get("n_tch", {}).get(strike, 0)
    nd = state.get("n_del", {}).get(strike, 0)
    nr = state.get("n_rej", {}).get(strike, 0)
    return nd / (nt + 1.0), nr / (nt + 1.0), math.log1p(nt)


def state_node_design(batch: Mapping, weights: Mapping[str, float],
                      state: Mapping) -> Dict[float, List[float]]:
    """8-column node design row per strike (spec §10.5.1): V = dot(STATE_BETA, row).

    row = [sum_e a_e*g, sum_e a_e*q_g, sum_e a_e*f, sum_e a_e*q_f,
           sum_e a_e*g*rho_e, d, r, tau]
    """
    cols = _columns(batch)
    out: Dict[float, List[float]] = {}
    for row in batch["rows"]:
        s = row["strike"]
        e = row["expiry_date"]
        a = weights.get(e, 0.0)
        g = net_gex(row)
        f = cell_flow(row)
        qg = state.get("q_g", {}).get((s, e), 0.0)
        qf = state.get("q_f", {}).get((s, e), 0.0)
        gmag = cols[e]["gmag"]
        ceil = state.get("ceil", {}).get(e, gmag)
        floor = state.get("floor", {}).get(e, gmag)
        rho = (gmag - floor) / (ceil - floor + 1.0)
        p = out.setdefault(s, [0.0] * 8)
        p[0] += a * g
        p[1] += a * qg
        p[2] += a * f
        p[3] += a * qf
        p[4] += a * g * rho
    for s, p in out.items():
        d, r, tau = node_state_scores(state, s)
        p[5], p[6], p[7] = d, r, tau
    return out


def stateful_node_values(batch: Mapping, weights: Mapping[str, float], state: Mapping,
                         beta: Tuple[float, ...] = STATE_BETA) -> Dict[float, float]:
    """V(s,t) under the §10.3 state-augmented model (linear in beta)."""
    return {s: sum(b * x for b, x in zip(beta, p))
            for s, p in state_node_design(batch, weights, state).items()}


def stateful_cell_values(batch: Mapping, weights: Mapping[str, float], state: Mapping,
                         beta: Tuple[float, ...] = STATE_BETA) -> Dict[Tuple[float, str], float]:
    """C(s,e,t) under §10.3: a_e*(b1..b5 . phi_cell) + (b6..b8 . scores)/E."""
    cols = _columns(batch)
    n_exp = max(len(cols), 1)
    cells: Dict[Tuple[float, str], float] = {}
    for row in batch["rows"]:
        key = (row["strike"], row["expiry_date"])
        e = key[1]
        a = weights.get(e, 0.0)
        g = net_gex(row)
        f = cell_flow(row)
        qg = state.get("q_g", {}).get(key, 0.0)
        qf = state.get("q_f", {}).get(key, 0.0)
        gmag = cols[e]["gmag"]
        ceil = state.get("ceil", {}).get(e, gmag)
        floor = state.get("floor", {}).get(e, gmag)
        rho = (gmag - floor) / (ceil - floor + 1.0)
        d, r, tau = node_state_scores(state, key[0])
        c = (a * (beta[0] * g + beta[1] * qg + beta[2] * f + beta[3] * qf + beta[4] * g * rho)
             + (beta[5] * d + beta[6] * r + beta[7] * tau) / n_exp)
        cells[key] = cells.get(key, 0.0) + c
    return cells


__all__ = [
    "THETA", "FEATURE_ORDER", "LAMBDA_BATCH", "LAMBDA_5S", "MEDIAN_CADENCE_S",
    "BATCH_INTERVAL_S", "UW_COLUMNS", "MAG_GAMMA",
    "parse_ts", "net_gex", "normalize_batch", "expiry_features", "psi_weights",
    "cross_expiry_weights", "cell_values", "node_values", "select_nodes",
    "display_weights",
    "STATE_FEATURE_ORDER", "LAMBDA_CELL", "STATE_BETA",
    "cell_flow", "new_cell_state", "update_cell_state", "node_state_scores",
    "state_node_design", "stateful_node_values", "stateful_cell_values",
]

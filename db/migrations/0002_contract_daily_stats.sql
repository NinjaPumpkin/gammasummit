-- 0002_contract_daily_stats.sql — per-contract daily aggregates (E0.8, model doc §7 gap 1).
--
-- Remediation for the missing per-contract daily history that blocked contract-level
-- RVOL in E0.7 (top_chains keeps only top-15 contracts/ticker/day). Row shapes follow
-- the Skylit public `ContractStats` / `UnderlyingStats` doc shapes (clean-room: field
-- names normalized to snake_case; `prev_oi` added because the UW source carries it and
-- E0.8 H1 needs raw OI deltas), plus provenance columns. Source of truth = UW only;
-- these tables are populated by scripts/e08_contract_daily_persist.py.
--
-- Expand-only by law (docs/build/code-structure-and-release.md §4): forward-only
-- migrations, never alter/drop in place while serving.
--
-- Apply target: UW PHX Supabase Postgres (the DB behind GAMMASUMMIT_UW_URL /
-- SUPABASE_URL) so e07/e08 tooling reads it via PostgREST; identical DDL applies to
-- the app Postgres when provisioned.

CREATE TABLE contract_daily_stats (
    date              DATE        NOT NULL,
    occ               TEXT        NOT NULL,   -- bare OCC: SPY261001C00761000
    ticker            TEXT        NOT NULL,
    expiration        DATE        NOT NULL,
    strike            NUMERIC     NOT NULL,
    right             CHAR(1)     NOT NULL,   -- C/P
    dte               INTEGER,
    total_premium     DOUBLE PRECISION,
    total_volume      BIGINT,
    open_interest     BIGINT,
    prev_oi           BIGINT,
    oi_change         BIGINT,
    bid_volume        BIGINT,
    ask_volume        BIGINT,
    mid_volume        BIGINT,
    sweep_volume      BIGINT,
    sweep_premium     DOUBLE PRECISION,
    multi_leg_volume  BIGINT,
    multi_leg_premium DOUBLE PRECISION,
    vwap              DOUBLE PRECISION,
    last_price        DOUBLE PRECISION,
    underlying_price  DOUBLE PRECISION,
    iv                DOUBLE PRECISION,
    trade_count       BIGINT,
    source            TEXT        NOT NULL,   -- e.g. phx_chains_expiry
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, occ)
);

CREATE TABLE underlying_daily_stats (
    date               DATE        NOT NULL,
    ticker             TEXT        NOT NULL,
    last_price         DOUBLE PRECISION,
    total_premium      DOUBLE PRECISION,
    total_volume       BIGINT,
    call_premium       DOUBLE PRECISION,
    put_premium        DOUBLE PRECISION,
    call_volume        BIGINT,
    put_volume         BIGINT,
    net_premium        DOUBLE PRECISION,
    call_put_ratio     DOUBLE PRECISION,
    trade_count        BIGINT,
    unique_strikes     INTEGER,
    unique_expirations INTEGER,
    source             TEXT        NOT NULL,
    fetched_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker)
);

CREATE INDEX idx_cds_ticker_date ON contract_daily_stats (ticker, date);
CREATE INDEX idx_cds_date_volume ON contract_daily_stats (date, total_volume DESC);
CREATE INDEX idx_cds_oi_change ON contract_daily_stats (date, oi_change);
CREATE INDEX idx_uds_ticker_date ON underlying_daily_stats (ticker, date);

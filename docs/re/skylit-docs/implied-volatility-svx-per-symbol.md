SOURCE: https://www.skylit.ai/docs/api-reference/tempest/implied-volatility-svx-per-symbol.md
CAPTURED: 2026-10-02

# Implied volatility (SVX) per symbol

`GET https://api.skylit.ai/v1/vol/iv`

API: Heatseeker.

SVX, Tempest's constant-maturity implied volatility per symbol (a VIX-style
variance-strip reading on the symbol's own option chain), in annualised vol
points: `svx1d`, `svx9`, `svx30`, `svx3m`, `svx6m`, each also weekend-adjusted
(`*_adj`, the weekly calendar pattern removed). Plus IV rank and percentile
(`iv_rank`, `iv_pct`, over the trailing year, on the adjusted reading),
1y/3y/5y percentiles per tenor (`pct_by`), the one-year range, the ratio to the
VIX (`ratio_vix`, `ratio_z`), term slope and curve state, and historical
mean-reversion odds (`reversion`). `quality` / `thin` flag shallow chains.
Response: `data.symbols[]` has `symbol`, `asOf`, `sessionDate`, `stale` and `iv`.
Symbols Tempest does not cover are listed in `data.missing`. **Cost:** 1 credit per call (up to 10 symbols).

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `symbols` | query | string | yes | Comma-separated Tempest symbols (up to 10). Tempest keys the S&P complex on the option root `SPXW` and Nasdaq-100 on `NDXP`; see `/v1/vol/symbols`. |

## Example request

```bash
curl "https://api.skylit.ai/v1/vol/iv?symbols=NVDA,SPY" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

OK.

Shape (placeholder values):

```json
{
  "data": {
    "symbols": [
      {
        "symbol": "string",
        "asOf": "string",
        "sessionDate": "string",
        "stale": false
      }
    ],
    "missing": [
      {
        "symbol": "string",
        "reason": "not_covered"
      }
    ]
  },
  "meta": {
    "module": "string",
    "asOf": "string",
    "sessionDate": "string",
    "marketState": "pre_open",
    "frozen": false,
    "publishedAt": "string",
    "cached": false
  }
}
```

### 400

Request validation failed.

### 401

Missing API key (`unauthorized`), sent by the gateway.

### 402

Out of credits (`insufficient_credits`).

### 403

As `Forbidden`, or `not_entitled`: Tempest data is not enabled for this
account (it is in preview). Refunded.

### 404

Unknown symbol, no data available, or none of the requested
`expirations` exist for the symbol (`code: expiration_not_found`).

### 429

Per-minute rate limit exceeded.

Headers: `Retry-After`.

### 503

Tempest data is loading (`warming_up`, with `Retry-After`) or not configured (`unavailable`). Refunded.

### 504

The request did not finish in time (`gateway_timeout`). Refunded;
retry, or narrow the request.

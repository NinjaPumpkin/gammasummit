SOURCE: https://www.skylit.ai/docs/api-reference/heatmap/daily-statistics-per-symbol-ranking-and-spot-range.md
CAPTURED: 2026-10-02

# Daily statistics per symbol (ranking and spot range)

`GET https://api.skylit.ai/v1/stats/daily`

API: Heatseeker. Credits: 5.

Per symbol and UTC date: board spot open/high/low/close, the smallest
and largest single cell of the day, and the mean and maximum over the
day's frames of `max(|smallest cell|, |largest cell|)` (a measure of
how concentrated the exposure is, useful for ranking a universe).
Computed from 1-minute history, so every frame of a day is one minute
apart (`frames` counts them). Weight `peakAbsMean` by `frames` to
average across days. Today's row has `complete: false` and changes as
the session goes on.

Up to 50 symbols, 31 days and 400 symbol-days (symbols x days) per
call. Days with no data are omitted; a symbol with none is omitted.
Served from the historical file store. **Cost:** 5 credits per call.

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `symbols` | query | string | yes | Comma-separated tickers (up to 50). |
| `from` | query | string (date) | yes | First UTC date (`YYYY-MM-DD`), not before 2023-03-28. |
| `to` | query | string (date) | no | Last UTC date (`YYYY-MM-DD`), inclusive. Default today; at most 31 days after `from`. |
| `metric` | query | string | no | Which Greek exposure to return per strike. (one of `gamma`, `vanna`; default `gamma`) |

## Example request

```bash
curl "https://api.skylit.ai/v1/stats/daily?symbols=SPY,QQQ,NVDA&from=<from>" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

Daily statistics.

Shape (placeholder values):

```json
{
  "data": {
    "from": "string",
    "to": "string",
    "symbols": [
      {
        "symbol": "string",
        "days": [
          {
            "date": "string",
            "frames": 0,
            "complete": false,
            "firstAt": "string",
            "lastAt": "string",
            "spotOpen": 0,
            "spotHigh": 0,
            "spotLow": 0,
            "spotClose": 0,
            "minValue": 0,
            "maxValue": 0,
            "peakAbsMean": 0,
            "peakAbsMax": 0
          }
        ]
      }
    ]
  },
  "meta": {
    "metric": "gamma",
    "resolution": "1s",
    "mode": "live",
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

Unknown, revoked or expired key (`forbidden`, from the gateway), or an
admin-suspended account (`account_suspended`).

### 404

Unknown symbol, no data available, or none of the requested
`expirations` exist for the symbol (`code: expiration_not_found`).

### 429

Per-minute rate limit exceeded.

Headers: `Retry-After`.

### 503

Heatmap data is temporarily unavailable.

### 504

The request did not finish in time (`gateway_timeout`). Refunded;
retry, or narrow the request.

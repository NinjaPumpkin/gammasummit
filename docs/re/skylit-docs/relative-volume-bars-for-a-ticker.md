SOURCE: https://www.skylit.ai/docs/api-reference/underlying/relative-volume-bars-for-a-ticker.md
CAPTURED: 2026-10-02

# Relative-volume bars for a ticker

`GET https://api.skylit.ai/v1/underlying/{ticker}/rvol`

API: Flowseeker. Credits: 1.

Time-bucketed bars with call/put volume + premium and an
average-volume baseline computed from `avgPeriod` recent days,
plus aggregate RVOL stats.

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `ticker` | path | string | yes | Underlying ticker symbol (uppercase, e.g. `SPY`, `AAPL`). |
| `interval` | query | string | no | Trailing window — `{N}D` where N is 1–365 (e.g. `1D`, `7D`, `30D`). (default `1D`) |
| `bucket` | query | string | no |  (one of `1min`, `5min`, `10min`, `15min`, `30min`, `1d`, `1w`; default `5min`) |
| `avg_period` | query | string | no | Baseline lookback as `{N}d` (e.g. `14d`, `30d`). Max 365 days. (default `14d`) |
| `date` | query | string (date) | no | Trading date the request targets, in `YYYY-MM-DD`. Defaults to the current trading date (the most recent session that has settled enough data to be queryable). Past dates fall through to the daily rollup tables. |
| `order_by` | query | string | no |  (one of `rvol`, `volume`, `premium`, `time`; default `time`) |
| `order` | query | string | no | Sort direction. Defaults to `asc` when `order_by=time`, otherwise `desc`. (one of `asc`, `desc`) |
| `limit` | query | integer | no |  (min 1) |
| `format` | query | string | no |  (one of `full`, `summary`; default `full`) |

## Example request

```bash
curl "https://api.skylit.ai/v1/underlying/SPY/rvol" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

RVOL bars + aggregate stats.

Shape (placeholder values):

```json
{
  "data": {
    "bars": [
      {
        "timestamp": "string",
        "timestampEnd": "string",
        "callVolume": 0,
        "putVolume": 0,
        "volume": 0,
        "premium": 0,
        "stockPrice": 0,
        "avgCallVolume": 0,
        "avgPutVolume": 0,
        "avgVolume": 0,
        "avgPremium": 0,
        "avgDaysCount": 0
      }
    ],
    "stats": {
      "todayVolume": 0,
      "todayPremium": 0,
      "avgVolume": 0,
      "avgPremium": 0,
      "rvolVolume": 0,
      "rvolPremium": 0,
      "avgDaysCount": 0
    },
    "callRvol": 0,
    "putRvol": 0
  },
  "meta": {
    "timestamp": "string",
    "requestId": "d7574836"
  }
}
```

### 400

Request validation failed.

invalidParam:

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid value 'bogus' for 'timeframe'. Allowed: 5m, 15m, 1h, 4h, 1d."
  }
}
```

### 401

Missing or invalid API key.

missingKey:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required"
  }
}
```

### 402

The account's shared Skylit credit balance is lower than this route's cost. Top up to continue. Carries `X-Credits-Remaining: 0`.

Headers: `X-Credits-Remaining`.

outOfCredits:

```json
{
  "error": {
    "code": "insufficient_credits",
    "message": "Out of credits. Top up to continue making requests."
  }
}
```

### 403

Unknown, revoked or expired API key (the gateway's `forbidden`), the account's API access is suspended (`account_suspended`) or blocked (`account_blocked`). Not retryable.

badKey:

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Access to this API has been disallowed"
  }
}
```

accountSuspended:

```json
{
  "error": {
    "code": "account_suspended",
    "message": "API access has been suspended for this account. Contact support."
  }
}
```

### 404

Unknown ticker or contract (`SYMBOL_NOT_FOUND`), or no data for the requested window. Not charged.

unknownSymbol:

```json
{
  "error": {
    "code": "SYMBOL_NOT_FOUND",
    "message": "Unknown ticker 'ZZZZQ'."
  }
}
```

noData:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No trades found for AAPL on 2026-05-27 with timeframe 1d"
  }
}
```

### 429

The key exceeded its requests-per-minute limit (`X-RateLimit-Limit`). No `Retry-After` is sent; wait until `X-RateLimit-Reset`, then retry.

tooFast:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded."
  }
}
```

### 500

Unexpected server error (`INTERNAL_ERROR`, `DATABASE_ERROR`). Not charged; safe to retry with exponential backoff.

internal:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error"
  }
}
```

### 503

Underlying data source temporarily unavailable, the credit balance could not be verified (`credit_check_failed`), or the API is paused for maintenance (`api_paused`, with a `Retry-After` header and a `retry_after` field in seconds). Not charged; safe to retry.

ingestionLag:

```json
{
  "error": {
    "code": "UNAVAILABLE",
    "message": "Live feed is degraded; please retry in a few seconds."
  }
}
```

creditCheckFailed:

```json
{
  "error": {
    "code": "credit_check_failed",
    "message": "Could not verify credit balance. Please retry."
  }
}
```

### 504

The request did not complete within 25 seconds. Not charged; narrow the window or retry.

tooSlow:

```json
{
  "error": {
    "code": "GATEWAY_TIMEOUT",
    "message": "The request took too long and was not completed. It was not charged; narrow the request or retry."
  }
}
```

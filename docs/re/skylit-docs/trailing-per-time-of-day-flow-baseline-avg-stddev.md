SOURCE: https://www.skylit.ai/docs/api-reference/flow/trailing-per-time-of-day-flow-baseline-avg-stddev.md
CAPTURED: 2026-10-02

# Trailing per-time-of-day flow baseline (avg + stddev)

`GET https://api.skylit.ai/v1/flow/{ticker}/baseline`

API: Flowseeker. Credits: 3.

Time-of-day baseline buckets for `{ticker}` — average and standard
deviation of trade count, premium, and FIR per intraday bucket over a
configurable lookback window. The reference distribution behind
`/v1/flow/{ticker}/momentum` z-scores.

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `ticker` | path | string | yes | Underlying ticker symbol (uppercase, e.g. `SPY`, `AAPL`). |
| `bucket` | query | string | no | Bucket size for the time series. Pre-aggregated tables back the sub-hourly resolutions. Coarser buckets (`1d`, `1w`) are rejected on intraday endpoints. (one of `1min`, `5min`, `15min`, `30min`, `1h`; default `5min`) |
| `lookback_days` | query | integer | no | Trailing window size in trading days. (default `20`; min 1; max 30) |
| `start_time_of_day` | query | string | no | Lower bound of intraday window (HH:MM ET). (default `09:30`) |
| `end_time_of_day` | query | string | no | Upper bound of intraday window (HH:MM ET). (default `16:00`) |
| `min_dte` | query | integer | no |  (min 0) |
| `max_dte` | query | integer | no |  (min 0) |

## Example request

```bash
curl "https://api.skylit.ai/v1/flow/SPY/baseline" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

Per-bucket baseline statistics.

Shape (placeholder values):

```json
{
  "data": {
    "ticker": "string",
    "bucket": "string",
    "lookbackDays": 0,
    "startTimeOfDay": "string",
    "endTimeOfDay": "string",
    "buckets": [
      {
        "timeOfDay": "14:30",
        "daysCount": 0,
        "avgTradeCount": 0,
        "stddevTradeCount": 0,
        "avgPremium": 0,
        "stddevPremium": 0,
        "avgFir": 0,
        "stddevFir": 0
      }
    ],
    "queryTimeMs": 0
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

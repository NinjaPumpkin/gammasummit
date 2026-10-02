SOURCE: https://www.skylit.ai/docs/api-reference/market/market-wide-flow-overview-for-the-current-trading-day.md
CAPTURED: 2026-10-02

# Market-wide flow overview for the current trading day

`GET https://api.skylit.ai/v1/market/overview`

API: Flowseeker. Credits: 3.

Returns market-wide call/put premium, total volume, directional
bullish/bearish premium, FIR, premium relative volume vs the
trailing 20-day baseline at the same time of day, and the top 10
tickers by total premium. Optionally narrowed to a comma-separated
ticker filter.

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `tickers` | query | string | no | Comma-separated list of tickers (e.g. `AAPL,NVDA,SPY`, max 50). When omitted, returns true market-wide stats over every ticker. |

## Example request

```bash
curl "https://api.skylit.ai/v1/market/overview" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

Market-wide overview snapshot.

Shape (placeholder values):

```json
{
  "data": {
    "date": "string",
    "totalPremium": 0,
    "totalVolume": 0,
    "callPremium": 0,
    "putPremium": 0,
    "netPremium": 0,
    "callVolume": 0,
    "putVolume": 0,
    "callPutRatio": 0,
    "activeTickers": 0,
    "bullishPremium": 0,
    "bearishPremium": 0,
    "directionalNet": 0,
    "fir": 0,
    "premiumRvol": 0,
    "topTickers": [
      {
        "ticker": "string",
        "totalPremium": 0,
        "totalVolume": 0,
        "callPremium": 0,
        "putPremium": 0,
        "netPremium": 0
      }
    ]
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

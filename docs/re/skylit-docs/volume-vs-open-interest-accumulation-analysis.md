SOURCE: https://www.skylit.ai/docs/api-reference/analytics/volume-vs-open-interest-accumulation-analysis.md
CAPTURED: 2026-10-02

# Volume-vs-Open-Interest accumulation analysis

`GET https://api.skylit.ai/v1/vol-oi/{ticker}`

API: Flowseeker. Credits: 1.

Distinguishes new position building (accumulation) from position
closing (distribution) by bucketing Vol/OI ratios per option type
and moneyness band. Returns an overall accumulation score (0–100),
an estimate of the share of volume representing new positions, and
a one-token signal (`strong_accumulation` → `low_activity`).

## Authentication

Send your Skylit API key as a bearer token: `Authorization: Bearer <key>`. No other header is accepted.

## Parameters

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `ticker` | path | string | yes | Underlying ticker symbol (uppercase, e.g. `SPY`, `AAPL`). |
| `timeframe` | query | string | no |  (one of `daily`, `weekly`; default `daily`) |
| `option_type` | query | string | no |  (one of `call`, `put`, `all`; default `all`) |
| `moneyness` | query | string | no |  (one of `otm_10plus`, `otm_5_10`, `otm_3_5`, `atm_itm`, `all`; default `all`) |
| `min_oi` | query | integer | no |  (min 0) |
| `date` | query | string (date) | no |  |

## Example request

```bash
curl "https://api.skylit.ai/v1/vol-oi/SPY" \
  -H "Authorization: Bearer $SKYLIT_API_KEY"
```

## Responses

### 200

Vol/OI breakdown with accumulation score.

Shape (placeholder values):

```json
{
  "data": {
    "ticker": "string",
    "timestamp": "string",
    "timeframe": "daily",
    "volOiAnalysis": {
      "calls": {
        "totalVolume": 0,
        "totalOi": 0,
        "volOiRatio": 0,
        "signal": "strong_accumulation",
        "byMoneyness": {
          "otm10plus": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "otm510": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "otm35": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "atmItm": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          }
        }
      },
      "puts": {
        "totalVolume": 0,
        "totalOi": 0,
        "volOiRatio": 0,
        "signal": "strong_accumulation",
        "byMoneyness": {
          "otm10plus": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "otm510": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "otm35": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          },
          "atmItm": {
            "volume": 0,
            "oi": 0,
            "ratio": 0
          }
        }
      }
    },
    "accumulationScore": 0,
    "newPositionEstimatePct": 0,
    "signal": "strong_accumulation"
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

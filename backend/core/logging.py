"""Structured JSON logging (tree: core/logging.py) — card E2.1.

Law (docs/build/code-structure-and-release.md §3 + docs/ops/security.md):
structured JSON logs with request-id + payload timestamps (freshness trust),
and log scrubbing — never log tokens, full request bodies, or connection
strings. Scrubbing is enforced in the formatter so a careless call site cannot
leak a secret into journald.

Pure module: stdlib only, no DB, no network, no env reads.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from typing import Any, Optional

# Context bindings — set once per request/payload, read by every log line.
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
payload_ts_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "payload_ts", default=None
)

# Keys whose values are secrets wherever they appear in log extras. Broad on
# purpose — over-redaction is safe, leaking a key is not.
SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|key|authorization|credential|dsn)", re.I
)

# Connection strings: scheme://user:password@host -> scheme://user:***@host
DSN_RE = re.compile(r"(\w+://[^:/@\s]+):([^@\s]+)@")

REDACTED = "***"

_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


def scrub(value: Any) -> Any:
    """Recursively redact secret-looking values before they reach a log sink.

    - dict: values under sensitive keys become '***' (key name kept for debug)
    - list/tuple: scrubbed element-wise
    - str: DSN passwords masked
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED if SENSITIVE_KEY_RE.search(str(k)) else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return DSN_RE.sub(r"\1:" + REDACTED + "@", value)
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg, request_id,
    payload_ts, then scrubbed extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        payload_ts = payload_ts_var.get()
        if payload_ts:
            payload["payload_ts"] = payload_ts
        for key, val in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                # Key-aware: a sensitive field name redacts its value outright.
                payload[key] = REDACTED if SENSITIVE_KEY_RE.search(key) else scrub(val)
        if record.exc_info:
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", stream: Any = None) -> None:
    """Install the JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Named logger; formatting/scrubbing owned by configure_logging()."""
    return logging.getLogger(name)


def bind_request_id(request_id: Optional[str]) -> contextvars.Token:
    return request_id_var.set(request_id)


def bind_payload_ts(payload_ts: Optional[str]) -> contextvars.Token:
    """Payload timestamp (freshness trust): when the SOURCE data was made,
    not when we logged it."""
    return payload_ts_var.set(payload_ts)

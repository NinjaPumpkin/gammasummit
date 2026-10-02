"""Error hierarchy (tree: core/errors.py) — card E2.1.

The boring spine every module raises. Law (docs/build/README.md): error
responses never leak internals (SQL, stack, paths), and rate limits are NEVER
hit — `RateLimitError` carries the upstream cooldown so callers back off.

Pure module: stdlib only, no DB, no network, no env.
"""
from __future__ import annotations

from typing import Optional


class GammaSummitError(Exception):
    """Base for every deliberate error in this codebase."""

    code = "gammasummit_error"

    def __init__(self, message: str = "", *, detail: Optional[str] = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        # Internal-only context (SQL state, upstream body). Never serialized
        # to clients — security law: responses never leak internals.
        self.detail = detail


class ConfigError(GammaSummitError):
    """Missing/invalid configuration (GAMMASUMMIT_* keys)."""

    code = "config_error"


class DatabaseError(GammaSummitError):
    """Base for persistence-layer failures."""

    code = "database_error"


class DatabaseUnavailableError(DatabaseError):
    """Pool/connect failure — readiness degrades, callers retry with backoff."""

    code = "database_unavailable"


class QueryError(DatabaseError):
    """Query failed (timeout, constraint, syntax). Not retried blindly."""

    code = "query_error"


class IngestError(GammaSummitError):
    """Base for upstream data-source failures (UW PHX production source)."""

    code = "ingest_error"


class RateLimitError(IngestError):
    """Upstream rate signal. Hard rule: never hit rate limits — any holder of
    this error must pause the source for at least `retry_after_s` seconds."""

    code = "rate_limit"

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float,
        source: str = "unknown",
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message or f"{source} rate signal", detail=detail)
        self.retry_after_s = retry_after_s
        self.source = source


class UpstreamError(IngestError):
    """Upstream returned/transient failure other than a rate signal."""

    code = "upstream_error"

    def __init__(
        self,
        message: str = "",
        *,
        source: str = "unknown",
        status: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        super().__init__(message or f"{source} upstream failure", detail=detail)
        self.source = source
        self.status = status


class NotFoundError(GammaSummitError):
    """Requested resource does not exist."""

    code = "not_found"


class ContractError(GammaSummitError):
    """API contract drift (pydantic <-> zod pair, ADR 0003)."""

    code = "contract_error"

"""Asyncpg pool + query helpers (tree: core/db.py) — card E2.1.

The boring persistence spine: one pool per process, typed errors out, bounded
retry with exponential backoff + jitter for transient failures, and a scrubbed
DSN for every log/error message (security law: connection strings never leak).

ADR 0003: plain SQL via asyncpg — no ORM. Pool sizing/timeouts come from
core/config.py; this module never reads env itself.
"""
from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Mapping, Sequence
from typing import Any, Awaitable, Callable, Optional, TypeVar

import asyncpg

from backend.core.errors import DatabaseError, DatabaseUnavailableError, QueryError
from backend.core.logging import get_logger, scrub

log = get_logger(__name__)

T = TypeVar("T")

# Transient failures worth one more try (connection churn, timeouts). Query
# errors like constraint violations are NOT here — retrying cannot help.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    asyncpg.InterfaceError,      # connection closed/broken mid-flight
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.ConnectionRejectionError,
    OSError,                     # socket resets under pool churn
)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 8.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run `fn` with bounded retries on transient errors.

    Exponential backoff + jitter (±50%) — same shape the ingest fetchers use
    against upstream rate signals. Non-transient errors propagate immediately.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except TRANSIENT_ERRORS as exc:
            attempt += 1
            if attempt > retries:
                raise DatabaseUnavailableError(
                    f"transient failure after {retries} retries", detail=repr(exc)
                ) from exc
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay *= 0.5 + random.random()  # jitter ±50%
            log.warning(
                "db transient failure, retrying",
                extra={"attempt": attempt, "delay_s": round(delay, 3)},
            )
            await sleep(delay)


class Database:
    """asyncpg pool wrapper. Lifecycle: construct -> connect() -> queries -> close()."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
        command_timeout_s: float = 30.0,
        max_retries: int = 3,
        pool_factory: Optional[Callable[..., Awaitable[Any]]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not dsn:
            raise DatabaseError("database DSN is empty")
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._command_timeout_s = command_timeout_s
        self._max_retries = max_retries
        self._sleep = sleep
        # Injectable for tests (never hits a real network in unit tests).
        self._pool_factory = pool_factory or asyncpg.create_pool
        self._pool: Any = None

    @property
    def scrubbed_dsn(self) -> str:
        return scrub(self._dsn)

    async def connect(self) -> Any:
        if self._pool is not None:
            return self._pool
        try:
            self._pool = await self._pool_factory(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
                command_timeout=self._command_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 — typed at the boundary
            raise DatabaseUnavailableError(
                f"cannot open pool {self.scrubbed_dsn}", detail=repr(exc)
            ) from exc
        log.info("db pool open", extra={"dsn": self.scrubbed_dsn})
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            log.info("db pool closed")

    def _acquire(self) -> Any:
        if self._pool is None:
            raise DatabaseUnavailableError("pool not connected — call connect() first")
        return self._pool

    def session(self) -> Any:
        """Dedicated checked-out connection as an async context manager.

        For session-level state that must survive across queries on the SAME
        connection (advisory locks in jobs/scheduler.py). Job queries still go
        through the pool; only the lock holder rides this connection.
        """
        return self._acquire().acquire()

    async def _run(self, method: str, query: str, args: tuple[Any, ...]) -> Any:
        """One query path: transient retry inside, typed errors out.

        Non-transient failures (bad SQL, constraints) surface as QueryError —
        detail stays internal (responses never leak internals)."""
        pool = self._acquire()
        fn = getattr(pool, method)
        try:
            return await retry_async(
                lambda: fn(query, *args), retries=self._max_retries, sleep=self._sleep
            )
        except DatabaseError:
            raise
        except Exception as exc:  # noqa: BLE001 — typed at the boundary
            raise QueryError(
                f"query failed on {method}", detail=repr(exc)
            ) from exc

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        return await self._run("fetch", query, args)

    async def fetchrow(self, query: str, *args: Any) -> Any:
        return await self._run("fetchrow", query, args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        return await self._run("fetchval", query, args)

    async def execute(self, query: str, *args: Any) -> str:
        return await self._run("execute", query, args)

    async def executemany(self, query: str, args_seq: list[tuple[Any, ...]]) -> str:
        """Batch statement path (T0 batch-upsert writer). Same transient retry
        as `execute`; safe to re-run because callers write idempotent upserts."""
        return await self._run("executemany", query, (args_seq,))

    async def ping(self) -> bool:
        """Readiness probe — never raises; readyz contract."""
        try:
            val = await self.fetchval("SELECT 1")
            return val == 1
        except (DatabaseError, QueryError):
            return False


# ---------------------------------------------------------------------------
# Batch-upsert helper (reuse map, docs/ops/migration-from-signalforge.md:
# "lib/supabase_writer.py batch upsert + retry + stats — re-implement in
# backend/core/db.py; keep conflict-key upsert semantics"). Clean-room: the
# pattern is re-derived here, nothing is copied.
# ---------------------------------------------------------------------------

UPSERT_CHUNK_ROWS = 500
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

T0_UPSERT_TABLES = ("gamma_snapshot", "spot_tick", "flow_print", "darkpool_print")


def _ident(name: str, kind: str) -> str:
    """Table/column names are code constants, never user input — assert that
    loudly so a future caller cannot smuggle SQL through a name."""
    if not _IDENT_RE.match(name):
        raise QueryError(f"unsafe {kind} name", detail=name)
    return name


def upsert_sql(table: str, columns: Sequence[str], conflict_cols: Sequence[str]) -> str:
    """Conflict-key upsert: INSERT ... ON CONFLICT (keys) DO UPDATE SET rest.

    Idempotent by construction — re-running a batch overwrites identical rows
    instead of duplicating them, so a retried writer is always safe.
    """
    table = _ident(table, "table")
    cols = [_ident(c, "column") for c in columns]
    keys = [_ident(c, "column") for c in conflict_cols]
    if not cols or not keys:
        raise QueryError("upsert needs columns and conflict keys")
    missing = [k for k in keys if k not in cols]
    if missing:
        raise QueryError("conflict keys missing from columns", detail=str(missing))
    updates = [c for c in cols if c not in keys]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) or ", ".join(
        f"{k} = EXCLUDED.{k}" for k in keys
    )
    return (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(f'${i + 1}' for i in range(len(cols)))}) "
        f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {set_clause}"
    )


async def upsert_rows(
    db: Database,
    table: str,
    rows: Sequence[Mapping[str, Any]],
    conflict_cols: Sequence[str],
    *,
    chunk: int = UPSERT_CHUNK_ROWS,
) -> int:
    """Write homogeneous row dicts in chunks. Returns row count written.

    Homogeneous = every row has the same keys (the writers guarantee it);
    the column order comes from the first row and drives every chunk.
    """
    if not rows:
        return 0
    columns = list(rows[0].keys())
    for r in rows:
        if set(r.keys()) != set(columns):
            raise QueryError("rows are not homogeneous", detail=table)
    sql = upsert_sql(table, columns, conflict_cols)
    args = [tuple(r[c] for c in columns) for r in rows]
    written = 0
    for i in range(0, len(args), chunk):
        await db.executemany(sql, args[i : i + chunk])
        written += len(args[i : i + chunk])
    return written

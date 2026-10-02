"""Unit tests for the backend/core spine (card E2.1).

config/errors/logging/db — the boring modules everything imports. No network,
no real DB: asyncpg is faked at the pool boundary and log output is captured
in-memory.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import unittest

from backend.core import db as core_db
from backend.core.config import Settings, get_settings
from backend.core.errors import (
    ConfigError,
    ContractError,
    DatabaseError,
    DatabaseUnavailableError,
    GammaSummitError,
    IngestError,
    NotFoundError,
    QueryError,
    RateLimitError,
    UpstreamError,
)
from backend.core.logging import (
    bind_payload_ts,
    bind_request_id,
    configure_logging,
    scrub,
)


def _make_dsn(pw: str) -> str:
    """Build a DSN with a secret password.

    Assembled by concatenation on purpose: file-level secret scrubbing must
    never be able to neuter this fixture (a scrubbed fixture tests nothing)."""
    return "postgresql://" + "user" + ":" + pw + "@" + "host.internal:5432/gs"


class ErrorsTest(unittest.TestCase):
    def test_hierarchy(self):
        self.assertTrue(issubclass(ConfigError, GammaSummitError))
        self.assertTrue(issubclass(DatabaseError, GammaSummitError))
        self.assertTrue(issubclass(DatabaseUnavailableError, DatabaseError))
        self.assertTrue(issubclass(QueryError, DatabaseError))
        self.assertTrue(issubclass(IngestError, GammaSummitError))
        self.assertTrue(issubclass(RateLimitError, IngestError))
        self.assertTrue(issubclass(UpstreamError, IngestError))
        self.assertTrue(issubclass(NotFoundError, GammaSummitError))
        self.assertTrue(issubclass(ContractError, GammaSummitError))

    def test_rate_limit_carries_cooldown(self):
        err = RateLimitError(retry_after_s=42.0, source="uw_phx")
        self.assertEqual(err.retry_after_s, 42.0)
        self.assertEqual(err.source, "uw_phx")

    def test_detail_is_internal_only(self):
        err = QueryError("boom", detail="SQLSTATE 42601 near SELECT")
        self.assertEqual(err.detail, "SQLSTATE 42601 near SELECT")
        self.assertNotIn("42601", err.message)


class ConfigTest(unittest.TestCase):
    def test_pool_fields_have_defaults(self):
        cfg = Settings(_env_file=None, database_url=None)
        self.assertEqual(cfg.db_pool_min_size, 2)
        self.assertEqual(cfg.db_pool_max_size, 10)
        self.assertEqual(cfg.db_command_timeout_s, 30.0)

    def test_env_override(self):
        import os

        os.environ["GAMMASUMMIT_DB_POOL_MAX_SIZE"] = "25"
        try:
            cfg = Settings(_env_file=None, database_url=None)
            self.assertEqual(cfg.db_pool_max_size, 25)
        finally:
            del os.environ["GAMMASUMMIT_DB_POOL_MAX_SIZE"]

    def test_no_secret_defaults(self):
        cfg = get_settings()
        for name in ("database_url", "uw_api_key", "uw_service_key", "skylit_api_key"):
            if getattr(cfg, name) is not None:
                # A real local .env may hold values; defaults must stay empty.
                defaults = Settings.model_fields[name].default
                self.assertIsNone(defaults)


class ScrubTest(unittest.TestCase):
    def test_sensitive_keys_redacted(self):
        out = scrub({"api_key": "abc123", "password": "hunter2", "safe": "ok"})
        self.assertEqual(out["api_key"], "***")
        self.assertEqual(out["password"], "***")
        self.assertEqual(out["safe"], "ok")

    def test_dsn_password_masked(self):
        pw = "hunter2"
        dsn = _make_dsn(pw)
        self.assertIn(pw, dsn)  # fixture sanity — never test a scrubbed fixture
        out = scrub(dsn)
        self.assertNotIn(pw, out)
        self.assertIn("user:***@host.internal", out)

    def test_nested_structures(self):
        pw = "hunter2"
        out = scrub({"rows": [{"uw_service_key": pw}, _make_dsn(pw)]})
        self.assertEqual(out["rows"][0]["uw_service_key"], "***")
        self.assertNotIn(pw, out["rows"][1])


class JsonFormatterTest(unittest.TestCase):
    def _emit(self, **extra) -> dict:
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        logging.getLogger("t").info("hello", extra=extra)
        return json.loads(stream.getvalue().strip())

    def test_json_shape(self):
        bind_request_id("req-9")
        bind_payload_ts("2026-10-02T20:00:00+00:00")
        try:
            line = self._emit()
        finally:
            bind_request_id(None)
            bind_payload_ts(None)
        self.assertEqual(line["level"], "INFO")
        self.assertEqual(line["msg"], "hello")
        self.assertEqual(line["logger"], "t")
        self.assertEqual(line["request_id"], "req-9")
        self.assertEqual(line["payload_ts"], "2026-10-02T20:00:00+00:00")
        self.assertIn("ts", line)

    def test_extra_secrets_scrubbed(self):
        pw = "hunter2"
        line = self._emit(uw_api_key="leaky", dsn=_make_dsn(pw))
        self.assertEqual(line["uw_api_key"], "***")
        self.assertEqual(line["dsn"], "***")
        self.assertNotIn(pw, json.dumps(line))

    def test_message_dsn_scrubbed(self):
        pw = "hunter2"
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        logging.getLogger("t").info("connect " + _make_dsn(pw) + " failed")
        self.assertNotIn(pw, stream.getvalue())


class _FakePool:
    """Scriptable asyncpg pool stand-in (no network)."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls = 0
        self.closed = False
        self.slept: list[float] = []

    async def _next(self, method):
        self.calls += 1
        outcome = self.script.pop(0) if self.script else "ok"
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def fetch(self, q, *a):
        return await self._next("fetch")

    async def fetchrow(self, q, *a):
        return await self._next("fetchrow")

    async def fetchval(self, q, *a):
        return await self._next("fetchval")

    async def execute(self, q, *a):
        return await self._next("execute")

    async def close(self):
        self.closed = True


class DbTest(unittest.TestCase):
    def _db(self, script=None, **kw):
        pool = _FakePool(script)
        made = {}

        async def factory(dsn, **factory_kw):
            made.update(factory_kw)
            return pool

        async def fake_sleep(seconds: float) -> None:
            pool.slept.append(seconds)

        database = core_db.Database(
            _make_dsn("hunter2"),
            pool_factory=factory,
            sleep=fake_sleep,
            **kw,
        )
        return database, pool, made

    def test_connect_passes_pool_settings(self):
        database, pool, made = self._db()
        asyncio.run(database.connect())
        self.assertFalse(pool.closed)
        self.assertEqual(made["min_size"], 2)
        self.assertEqual(made["max_size"], 10)
        self.assertEqual(made["command_timeout"], 30.0)

    def test_scrubbed_dsn_never_leaks_password(self):
        database, _, _ = self._db()
        self.assertNotIn("hunter2", database.scrubbed_dsn)
        self.assertIn("user:***@", database.scrubbed_dsn)

    def test_query_before_connect_is_typed_error(self):
        database, _, _ = self._db()
        with self.assertRaises(DatabaseUnavailableError):
            asyncio.run(database.fetch("SELECT 1"))

    def test_empty_dsn_rejected(self):
        with self.assertRaises(DatabaseError):
            core_db.Database("")

    def test_transient_error_retries_then_succeeds(self):
        async def scenario():
            database, pool, _ = self._db(
                script=[asyncpg_interface_error(), "rows"]
            )
            await database.connect()
            slept = []

            async def fake_sleep(s):
                slept.append(s)

            result = await core_db.retry_async(
                lambda: pool.fetch("SELECT 1"), retries=3, sleep=fake_sleep
            )
            return pool, slept, result

        pool, slept, result = asyncio.run(scenario())
        self.assertEqual(pool.calls, 2)
        self.assertEqual(result, "rows")
        self.assertEqual(len(slept), 1)

    def test_transient_error_exhausts_retries(self):
        async def scenario():
            database, pool, _ = self._db()
            await database.connect()
            # initial attempt + 3 retries = 4 transient failures
            pool.script.extend([asyncpg_interface_error()] * 4)
            with self.assertRaises(DatabaseUnavailableError):
                await database.fetch("SELECT 1")

        asyncio.run(scenario())

    def test_query_error_not_retried(self):
        async def scenario():
            database, pool, _ = self._db(script=[ValueError("bad sql state")])
            await database.connect()
            with self.assertRaises(QueryError):
                await database.fetch("SELECT bad")
            return pool

        pool = asyncio.run(scenario())
        self.assertEqual(pool.calls, 1)

    def test_ping_true_and_false(self):
        async def scenario():
            ok_db, _, _ = self._db(script=[1])
            await ok_db.connect()
            bad_db, bad_pool, _ = self._db()
            await bad_db.connect()
            bad_pool.script.append(ValueError("down"))
            return await ok_db.ping(), await bad_db.ping()

        ok, bad = asyncio.run(scenario())
        self.assertTrue(ok)
        self.assertFalse(bad)

    def test_close_closes_pool(self):
        database, pool, _ = self._db()
        asyncio.run((lambda: _close(database, pool))())
        self.assertTrue(pool.closed)


async def _close(database, pool):
    await database.connect()
    await database.close()


def asyncpg_interface_error():
    return core_db.asyncpg.InterfaceError("connection closed")


if __name__ == "__main__":
    unittest.main()

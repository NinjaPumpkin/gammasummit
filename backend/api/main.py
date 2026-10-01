"""GammaSummit API — app factory (tree: api/main.py).

Thin by law (docs/build/code-structure-and-release.md §2): routers validate →
core computes → schemas serialize. Scaffold scope (E1.1): health/readiness
endpoints + middleware skeleton; routers land with the API workstream.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import FastAPI, Request, Response

from backend.api.deps import Settings, get_settings
from backend.api.schemas.contract import HealthResponse, ReadyCheck, ReadyResponse

APP_VERSION = "0.0.0"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Build the ASGI app. `settings` is injectable for tests (no real env/DB)."""
    cfg = settings if settings is not None else get_settings()

    app = FastAPI(
        title="GammaSummit API",
        version=APP_VERSION,
        description="Options-flow intelligence platform — clean-room build",
    )
    app.state.settings = cfg

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Request-id on every response (structured logging contract §3)."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    if cfg.cors_origin_list:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origin_list,
            allow_methods=["GET"],
            allow_headers=["authorization", "content-type", "x-request-id"],
        )

    @app.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthz() -> HealthResponse:
        """Process liveness — never touches DB or network."""
        return HealthResponse(status="ok", version=APP_VERSION)

    @app.get("/readyz", response_model=ReadyResponse, tags=["health"])
    async def readyz(response: Response) -> ReadyResponse:
        """Readiness: DB reachable + settings present. 503 when degraded."""
        checks: list[ReadyCheck] = []
        db_ok = await _check_db(cfg.database_url)
        checks.append(
            ReadyCheck(
                name="db",
                ok=db_ok,
                detail=None if db_ok else "GAMMASUMMIT_DATABASE_URL unset or unreachable",
            )
        )
        ready = all(c.ok for c in checks)
        response.status_code = 200 if ready else 503
        return ReadyResponse(status="ready" if ready else "degraded", checks=checks)

    return app


async def _check_db(database_url: Optional[str]) -> bool:
    """Real asyncpg ping — no fake success. Unset URL = not ready."""
    if not database_url:
        return False
    try:
        import asyncpg

        conn = await asyncpg.connect(database_url, timeout=2.0)
        await conn.close()
        return True
    except Exception:
        return False


app = create_app()

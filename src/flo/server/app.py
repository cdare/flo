"""FastAPI application factory and lifespan management."""

from __future__ import annotations

import secrets
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from flo.config import get_settings
from flo.server.persistence import init_checkpointer
from flo.server.routes import router as chat_router
from flo.tools import register_skills

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown.

    Startup order (per Ash's architecture review):
    1. Load settings
    2. Register skills (must happen before build_graph)
    3. Initialize SQLite checkpointer (WAL mode)
    4. Build and compile graph (D3 — singleton)

    Shutdown:
    1. Close SQLite connection
    """
    settings = get_settings()

    # 1. Register skills before graph compilation
    log.info("startup.register_skills")
    register_skills(settings)

    # 2. Initialize persistence (Ripley's fix: unpack tuple)
    log.info("startup.init_persistence", db_path=settings.db_path)
    checkpointer, db_conn = await init_checkpointer(settings.db_path)

    # 3. Build graph (D3 — compiled once, reused across requests)
    from flo.agent.graph import build_graph

    log.info("startup.build_graph")
    app.state.graph = build_graph(
        settings,
        checkpointer=checkpointer,
    )
    app.state.settings = settings

    log.info("startup.complete")
    yield

    # Shutdown: close DB connection directly (not via saver internals)
    log.info("shutdown.close_db")
    await db_conn.close()
    log.info("shutdown.complete")


def create_app() -> FastAPI:
    """Factory function for the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Flo",
        description="Personal assistant agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: only allow explicitly configured origins (issue #11).
    # Default is an empty list — all cross-origin browser requests are blocked.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    # Simple in-memory per-IP rate limiter for /chat (issue #3).
    # Tracks request timestamps per client IP in a rolling 60-second window.
    # The bucket dict is bounded to max_tracked_ips entries; once full, the
    # oldest entry is evicted to prevent unbounded memory growth.
    max_tracked_ips = 10_000
    _rate_buckets: dict[str, list[float]] = {}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
        if request.url.path == "/chat" and request.method == "POST":
            # Reject requests with no client address rather than bucket them
            # all together under a shared key (which could be abused).
            if request.client is None:
                return Response(
                    content='{"detail":"Unable to determine client address"}',
                    status_code=400,
                    media_type="application/json",
                )
            client_ip = request.client.host
            limit = settings.rate_limit_per_minute
            now = time.monotonic()
            window = 60.0

            # Initialise bucket; evict oldest entry when at capacity
            if client_ip not in _rate_buckets:
                if len(_rate_buckets) >= max_tracked_ips:
                    oldest_ip = next(iter(_rate_buckets))
                    del _rate_buckets[oldest_ip]
                _rate_buckets[client_ip] = []

            # Drop timestamps outside the rolling window
            _rate_buckets[client_ip] = [
                t for t in _rate_buckets[client_ip] if now - t < window
            ]
            if len(_rate_buckets[client_ip]) >= limit:
                return Response(
                    content='{"detail":"Rate limit exceeded. Try again later."}',
                    status_code=429,
                    media_type="application/json",
                )
            _rate_buckets[client_ip].append(now)
        return await call_next(request)

    # Optional API key authentication for /chat (issue #1).
    # When FLO_API_KEY is set, every /chat request must supply the same value
    # in the X-API-Key header.  Requests without a valid key get HTTP 401.
    # secrets.compare_digest() is used for constant-time comparison to prevent
    # timing-based key extraction attacks (issue from code review).
    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next: Any) -> Response:
        if request.url.path == "/chat" and request.method == "POST":
            required_key = settings.api_key
            if required_key:
                provided_key = request.headers.get("X-API-Key", "")
                if not secrets.compare_digest(provided_key, required_key):
                    return Response(
                        content='{"detail":"Missing or invalid API key"}',
                        status_code=401,
                        media_type="application/json",
                    )
        return await call_next(request)

    app.include_router(chat_router)
    return app


app = create_app()

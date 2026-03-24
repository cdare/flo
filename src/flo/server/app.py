"""FastAPI application factory and lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

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
    app = FastAPI(
        title="Flo",
        description="Personal assistant agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(chat_router)
    return app


app = create_app()

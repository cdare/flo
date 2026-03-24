"""SQLite persistence initialization for checkpointer and store."""

from __future__ import annotations

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


async def init_checkpointer(
    db_path: str,
) -> tuple[AsyncSqliteSaver, aiosqlite.Connection]:
    """Create an AsyncSqliteSaver with WAL mode enabled (D4).

    Returns the saver and the raw connection so the caller can close
    the connection directly on shutdown without reaching into saver internals.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Tuple of (saver, connection).
    """
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver, conn

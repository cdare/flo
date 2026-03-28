"""SQLite persistence initialization for checkpointer and store."""

from __future__ import annotations

import contextlib
import os

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


async def init_checkpointer(
    db_path: str,
) -> tuple[AsyncSqliteSaver, aiosqlite.Connection]:
    """Create an AsyncSqliteSaver with WAL mode enabled (D4).

    Returns the saver and the raw connection so the caller can close
    the connection directly on shutdown without reaching into saver internals.

    The database file is created with mode 0o600 (owner read/write only) to
    limit exposure of conversation history stored at rest (issue #12).

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Tuple of (saver, connection).
    """
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")

    # Restrict file permissions to owner-only after creation (issue #12).
    # aiosqlite.connect() creates the file if it does not exist, so by
    # the time we reach here the file is guaranteed to exist.
    if db_path not in (":memory:", ""):
        with contextlib.suppress(OSError):
            os.chmod(db_path, 0o600)

    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver, conn

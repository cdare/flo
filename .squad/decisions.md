# Squad Decisions

## Active Decisions

### D1: Checkpointer must be injectable
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

`build_graph()` must accept an optional `checkpointer` parameter (default `MemorySaver()`) to support SQLite and future PostgreSQL migration without changing the function signature.

### D2: Server → Agent invocation contract
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

FastAPI route handlers extract `user_id` and `conversation_id` from the request, construct the initial state dict, and call `graph.ainvoke(state, config={"configurable": {"thread_id": conversation_id}})`. The agent layer never knows about HTTP.

### D3: Compiled graph is a singleton
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

The compiled graph is created once during the FastAPI lifespan (after skill registration, checkpointer initialization) and reused across all requests. Tests continue to build per-test graphs.

### D4: SQLite WAL mode by default
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

Enable `PRAGMA journal_mode=WAL` when opening the SQLite connection. Safe for single-server deployment, prevents reader/writer contention.

### D5: Discord uses bot mode
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

A Discord bot (persistent WebSocket via `discord.py`) is required for the agent to send responses. Webhook-only is insufficient.

### D6: WhatsApp v1 is text-only
**Date:** 2026-03-22 | **Author:** Ash | **Approved by:** Ripley

Phase 8 handles text messages only. Media support (images, audio, documents) is deferred to a future phase.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction

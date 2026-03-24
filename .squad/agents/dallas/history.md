# Project Context

- **Owner:** Chris Dare
- **Project:** Flo — Personal assistant agent (Discord/WhatsApp → FastAPI → LangGraph → Skills → LLM Router)
- **Stack:** Python 3.14, FastAPI, LangGraph, litellm, langchain-core, pydantic-settings, structlog, pytest
- **Created:** 2026-03-22

## Key Architecture

- LangGraph StateGraph: classify → plan → execute → respond (with execute ↔ tool_node loop)
- Closure-based DI for node factories
- Skill dataclass + SkillRegistry for tool management
- Settings via pydantic-settings with FLO_ env prefix, .env file support
- Structured logging via structlog (JSON in prod, ConsoleRenderer in dev)
- Makefile for process lifecycle (run/stop/restart/status/logs/clean)

## Progress

- Phases 1-5 complete: scaffolding, LLM router, orchestrator, user memory, tool layer
- 76 tests passing, lint clean
- Phase 6 (my primary focus): FastAPI server + SQLite persistence
  - AsyncSqliteSaver replaces MemorySaver for conversation checkpointing
  - AsyncSqliteStore replaces InMemoryStore for user preferences
  - FLO_DB_PATH config setting needed
  - langgraph-checkpoint-sqlite dependency needed
- Phase 7: Discord integration
- Phase 8: WhatsApp integration (Meta Cloud API)

## Key Files

- `src/flo/config.py` — Settings (host, port, env, models, google creds, search config, db_path)
- `src/flo/agent/graph.py` — build_graph(settings, *, router=None, store=None, checkpointer=None)
- `src/flo/log.py` — configure_logging()
- `Makefile` — install, test, run/stop/restart targets
- `src/flo/server/app.py` — create_app() factory, lifespan (skills→DB→graph), module-level `app` for uvicorn
- `src/flo/server/routes.py` — /chat (POST) and /health (GET) endpoints
- `src/flo/server/models.py` — ChatRequest/ChatResponse pydantic models
- `src/flo/server/persistence.py` — init_checkpointer() returns (saver, conn) tuple

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- Phase 6: `init_checkpointer` returns `(saver, conn)` tuple per Ripley's review — lifespan closes `conn` directly instead of reaching into saver internals.
- Phase 6: Lifespan startup order matters: register_skills() → init_checkpointer() → build_graph(). Skills must be registered before graph compilation because build_graph calls get_all_skills() internally.
- Phase 6: ruff enforces TC003 — stdlib imports used only for type hints must go in `TYPE_CHECKING` block (e.g., `AsyncIterator`).
- Phase 6: ruff enforces B904 — exceptions raised inside `except` blocks need `from err` or `from None` to chain properly.
- Phase 6: `conftest.py` settings fixture uses `tmp_path` for `db_path` to avoid touching real databases during tests.
- Phase 6: The `langgraph-checkpoint-sqlite` package uses `AsyncSqliteSaver` from `langgraph.checkpoint.sqlite.aio`, not from a top-level import.

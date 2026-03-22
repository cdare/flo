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

- `src/flo/config.py` — Settings (host, port, env, models, google creds, search config)
- `src/flo/agent/graph.py` — build_graph(settings, *, router=None, store=None)
- `src/flo/log.py` — configure_logging()
- `Makefile` — install, test, run/stop/restart targets

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

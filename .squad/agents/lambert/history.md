# Project Context

- **Owner:** Chris Dare
- **Project:** Flo — Personal assistant agent (Discord/WhatsApp → FastAPI → LangGraph → Skills → LLM Router)
- **Stack:** Python 3.14, FastAPI, LangGraph, litellm, langchain-core, pydantic-settings, structlog, pytest
- **Created:** 2026-03-22

## Test Infrastructure

- pytest + pytest-asyncio (asyncio_mode="auto" in pyproject.toml)
- tests/ directory at repo root
- conftest.py: settings fixture (returns Settings with test defaults), guard import for package installation
- Mocking boundaries: litellm.acompletion, Google API service objects, search provider APIs
- NEVER mock LangGraph internals — test through the graph

## Current Test Inventory

- test_smoke.py: 5 tests (imports, config, logging)
- test_llm_router.py: 17 tests (routing, completion, structured output, usage stats)
- test_agent.py: ~25 tests (state, routing, nodes, graph paths, conversation continuity, preferences, corrections, windowing)
- test_tools.py: 29 tests (registry, calendar/gmail/search tools, LLMResponse tool_calls, classification, routing)
- Total: 76 tests, all passing, lint clean

## Key Patterns

- Mock litellm.acompletion for LLM tests — return ModelResponse-shaped dicts
- Use settings fixture with test defaults (no real API keys needed)
- Test node factories by calling the inner function directly
- Test graph paths by invoking the compiled graph with appropriate state
- 1 Pydantic compat warning (model_fields access on model instance) — cosmetic, not a bug

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- FastAPI server tests: mock the graph (not the LLM) — graph is the seam between HTTP and agent layers
- Bypass lifespan in server tests: create bare `FastAPI()`, include router, inject mock graph on `app.state`
- Use `httpx.AsyncClient` + `ASGITransport` for async FastAPI testing (no thread gymnastics, works with pytest-asyncio auto mode)
- `ruff` enforces `TYPE_CHECKING` block for stdlib imports like `collections.abc.AsyncIterator` — use `from typing import TYPE_CHECKING` pattern

# Project Context

- **Owner:** Chris Dare
- **Project:** Flo — Personal assistant agent (Discord/WhatsApp → FastAPI → LangGraph → Skills → LLM Router)
- **Stack:** Python 3.14, FastAPI, LangGraph, litellm, langchain-core, pydantic-settings, structlog, pytest
- **Created:** 2026-03-22

## Key Architecture

- LangGraph StateGraph: classify → plan → execute → respond (with execute ↔ tool_node loop)
- Closure-based DI for node factories (each node is a factory that takes LLMRouter and returns the node function)
- Skill dataclass + SkillRegistry for tool management
- LLMRouter with cheap (gpt-4o-mini) and premium (gpt-4o) model routing
- Message windowing (max_messages=20) + InMemoryStore for user preferences
- MemorySaver checkpointer for within-conversation memory

## Progress

- Phases 1-5 complete: scaffolding, LLM router, orchestrator, user memory, tool layer
- 76 tests passing, lint clean
- Phases 6-8 remaining: FastAPI server + SQLite persistence, Discord, WhatsApp

## Key Files

- `src/flo/agent/graph.py` — StateGraph builder
- `src/flo/agent/nodes.py` — Node factory functions
- `src/flo/agent/state.py` — AgentState TypedDict, Classification model
- `src/flo/llm/router.py` — LLMRouter class
- `src/flo/tools/base.py` — Skill, SkillRegistry
- `src/flo/config.py` — Settings with FLO_ env prefix

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

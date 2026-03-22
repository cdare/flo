# Squad Team

> flo — Personal assistant agent (Discord/WhatsApp → FastAPI → LangGraph → Tools → LLM Router)

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status |
|------|------|---------|--------|
| Ripley | Lead | [charter](.squad/agents/ripley/charter.md) | 🏗️ Active |
| Dallas | Backend Dev | [charter](.squad/agents/dallas/charter.md) | 🔧 Active |
| Ash | Agent Architect | [charter](.squad/agents/ash/charter.md) | 🧬 Active |
| Lambert | Tester | [charter](.squad/agents/lambert/charter.md) | 🧪 Active |
| Scribe | Session Logger | [charter](.squad/agents/scribe/charter.md) | 📋 Active |
| Ralph | Work Monitor | — | 🔄 Monitor |

## Project Context

- **Owner:** Chris Dare
- **Project:** Flo — Personal assistant agent
- **Stack:** Python 3.14, FastAPI, LangGraph, litellm, langchain-core, pydantic-settings, structlog, pytest
- **Created:** 2026-03-22
- **Architecture:** Discord/WhatsApp → FastAPI webhook server → LangGraph StateGraph (classify→plan→execute→respond) → Skill layer (Calendar, Gmail, Search) → LLM Router (cheap/premium)
- **Progress:** Phases 1-5 complete (scaffolding, LLM router, orchestrator, user memory, tool layer). Phases 6-8 remaining (FastAPI server + SQLite, Discord, WhatsApp).
- **Tests:** 76 passing, lint clean
- **Key patterns:** Closure-based DI for node factories, Skill dataclass with SkillRegistry, ToolNode loop for tool execution, message windowing + InMemoryStore for preferences

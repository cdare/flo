# Project Context

- **Owner:** Chris Dare
- **Project:** Flo — Personal assistant agent (Discord/WhatsApp → FastAPI → LangGraph → Skills → LLM Router)
- **Stack:** Python 3.14, FastAPI, LangGraph, litellm, langchain-core, pydantic-settings, structlog, pytest
- **Created:** 2026-03-22

## Key Architecture

- **Graph:** LangGraph StateGraph with nodes: load_preferences → classify → [plan | execute | store_correction] → respond
- **Execute loop:** execute ↔ tool_node (ToolNode from langgraph.prebuilt) — loops until no more tool_calls
- **State:** AgentState TypedDict: messages (Annotated list with operator.add), task_type, plan, response, conversation_id, user_id, user_preferences, is_correction, active_skills
- **Classification:** Pydantic model → complete_structured() on cheap model. Returns task_type (EXECUTION/PLANNING), is_correction, active_skills
- **Memory:** MemorySaver (checkpointer, within-conversation) + InMemoryStore (cross-conversation preferences). Phase 6 migrates to SQLite variants.
- **Skills:** Skill dataclass (name, description, tools, system_prompt, task_type_override). SkillRegistry manages all skills. Factory/closure DI pattern for tool creation.
- **LLM Router:** LLMRouter with complete() (accepts optional tools param via convert_to_openai_tool) and complete_structured() (Pydantic model output). Routes between cheap_model and premium_model based on TaskType.
- **Tool calls:** Execute node returns AIMessage with tool_calls when present. ToolNode handles tool execution. route_after_execute checks for tool_calls to loop.

## Design Decisions

- Closure-based DI over class-based DI — node factories take LLMRouter and return async callables
- Skills-first over multi-agent — one agent with modular skills, not multiple specialized agents
- Message windowing (max_messages=20) for context management
- InMemoryStore for preferences with correction detection (is_correction flag on Classification)

## Progress

- Phases 1-5 complete, 76 tests passing
- Phase 6 next: SQLite persistence (AsyncSqliteSaver + AsyncSqliteStore)
- Phases 7-8: Discord and WhatsApp integrations (these mainly affect the server layer, not the agent graph)

## Key Files

- `src/flo/agent/graph.py` — build_graph() wires the StateGraph
- `src/flo/agent/nodes.py` — All node factories + route_after_execute
- `src/flo/agent/state.py` — AgentState, Classification, ExtractedPreference
- `src/flo/llm/router.py` — LLMRouter class
- `src/flo/llm/models.py` — TaskType, UsageStats, LLMResponse
- `src/flo/tools/base.py` — Skill, SkillRegistry, credential helpers

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

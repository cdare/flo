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

### 2026-03-22 — Architecture Review (Phases 1-5 complete)

- **Checkpointer injection gap:** `build_graph()` hardcodes `MemorySaver()` at compile time (line 103 of graph.py). The `store` parameter is injectable but `checkpointer` is not. This MUST be fixed before Phase 6 SQLite migration.
- **Skill registration ordering:** `build_graph()` calls `get_all_skills()` to populate ToolNode, so `register_skills()` must run before `build_graph()`. This ordering is currently implicit — Phase 6 lifespan must make it explicit.
- **Execute node registry coupling:** `create_execute_node` imports `get_skill` from the module-level singleton registry inside the async callable. Acceptable for single-agent, but breaks isolation for multi-agent scenarios.
- **Settings gap:** `db_path` field is not yet in `config.py` — task.md specifies `FLO_DB_PATH` defaulting to `"flo.db"`.
- **Pattern verdict:** Closure-based DI for nodes, Skill registry, ToolNode loop, and LLMRouter strategy pattern are all appropriate for the current scale. No pattern changes needed for Phases 6-8.
- **Phase 6 contract:** Server routes must extract `user_id` + `conversation_id`, construct state, call `graph.ainvoke()`. Agent layer must never know about HTTP.
- **Discord requires bot mode** (persistent WebSocket), not webhook-only. WhatsApp v1 should be text-only.
- **SQLite WAL mode** should be enabled on connection for concurrent safety.

### 2026-03-23 — Phase 6 Plan: FastAPI Server + SQLite Persistence

- **Store gap:** `langgraph-checkpoint-sqlite` provides `AsyncSqliteSaver` (checkpointer) but no `AsyncSqliteStore` equivalent. Phase 6 keeps `InMemoryStore` for cross-conversation preferences; SQLite store migration deferred until LangGraph ships one or we build a custom adapter.
- **Lifespan ordering is critical:** `register_skills()` → `init_checkpointer()` → `build_graph()`. Skills must register before graph compilation because `build_graph()` calls `get_all_skills()` to populate `ToolNode`. This is now explicit in the lifespan function.
- **Test seam is the graph:** Server tests mock `graph.ainvoke()`, not the LLM or individual nodes. This keeps HTTP boundary tests fast and decoupled from agent internals.
- **`busy_timeout` pragma:** Added `PRAGMA busy_timeout=5000` alongside WAL mode — prevents immediate `SQLITE_BUSY` errors under concurrent async access.
- **Makefile already correct:** `SERVER_CMD` already targets `flo.server.app:app` — no changes needed to the Makefile for Phase 6.

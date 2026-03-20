from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from flo.agent.nodes import (
    create_classify_node,
    create_execute_node,
    create_load_preferences_node,
    create_plan_node,
    create_respond_node,
    create_store_correction_node,
)
from flo.agent.state import AgentState
from flo.llm.models import TaskType
from flo.llm.router import LLMRouter

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore

    from flo.config import Settings


def _route_after_classify(state: AgentState) -> str:
    """Route to plan, execute, or store_correction based on classification."""
    if state.get("is_correction"):
        return "store_correction"
    if state.get("task_type") == TaskType.PLANNING:
        return "plan"
    return "execute"


def build_graph(
    settings: Settings,
    *,
    router: LLMRouter | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph:
    """Build and compile the agent graph.

    Args:
        settings: Application settings for LLM configuration.
        router: Optional pre-built LLMRouter (for testing). If None,
            a new router is created from settings.
        store: Optional Store for cross-conversation memory. If None,
            a new InMemoryStore is created.

    Returns:
        Compiled LangGraph ready for invocation via ainvoke().
    """
    if router is None:
        router = LLMRouter(settings)

    if store is None:
        store = InMemoryStore()

    max_messages = settings.max_messages

    graph = StateGraph(AgentState)

    graph.add_node("load_preferences", create_load_preferences_node())
    graph.add_node("classify", create_classify_node(router, max_messages=max_messages))
    graph.add_node("plan", create_plan_node(router, max_messages=max_messages))
    graph.add_node("execute", create_execute_node(router, max_messages=max_messages))
    graph.add_node(
        "store_correction",
        create_store_correction_node(router, max_messages=max_messages),
    )
    graph.add_node("respond", create_respond_node())

    graph.add_edge(START, "load_preferences")
    graph.add_edge("load_preferences", "classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "plan": "plan",
            "execute": "execute",
            "store_correction": "store_correction",
        },
    )
    graph.add_edge("plan", "execute")
    graph.add_edge("store_correction", "execute")
    graph.add_edge("execute", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=MemorySaver(), store=store)

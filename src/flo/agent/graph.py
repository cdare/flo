from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from flo.agent.nodes import (
    create_classify_node,
    create_execute_node,
    create_plan_node,
    create_respond_node,
)
from flo.agent.state import AgentState
from flo.llm.models import TaskType
from flo.llm.router import LLMRouter

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from flo.config import Settings


def _route_after_classify(state: AgentState) -> str:
    """Route to plan or execute based on task classification."""
    if state.get("task_type") == TaskType.PLANNING:
        return "plan"
    return "execute"


def build_graph(
    settings: Settings,
    *,
    router: LLMRouter | None = None,
) -> CompiledStateGraph:
    """Build and compile the agent graph.

    Args:
        settings: Application settings for LLM configuration.
        router: Optional pre-built LLMRouter (for testing). If None,
            a new router is created from settings.

    Returns:
        Compiled LangGraph ready for invocation via ainvoke().
    """
    if router is None:
        router = LLMRouter(settings)

    graph = StateGraph(AgentState)

    graph.add_node("classify", create_classify_node(router))
    graph.add_node("plan", create_plan_node(router))
    graph.add_node("execute", create_execute_node(router))
    graph.add_node("respond", create_respond_node())

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {"plan": "plan", "execute": "execute"},
    )
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "respond")
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=MemorySaver())

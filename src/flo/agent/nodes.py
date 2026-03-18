from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from flo.agent.state import AgentState, Classification
from flo.llm.models import TaskType

if TYPE_CHECKING:
    from flo.llm.router import LLMRouter

log = structlog.get_logger(__name__)

CLASSIFY_SYSTEM_PROMPT = (
    "You are a task classifier. Analyze the user's message and determine if it "
    "requires complex multi-step planning (PLANNING) or can be handled with a "
    "simple direct response (EXECUTION).\n\n"
    "Examples of PLANNING tasks: scheduling meetings, researching topics, "
    "multi-step workflows, tasks requiring multiple tools.\n"
    "Examples of EXECUTION tasks: simple questions, greetings, single lookups, "
    "direct answers."
)

PLAN_SYSTEM_PROMPT = (
    "You are a planning assistant. Break down the user's request into "
    "a clear, step-by-step plan. Be specific and actionable."
)

EXECUTE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant. Respond clearly and concisely."
)


def create_classify_node(
    router: LLMRouter,
) -> Any:
    """Create the classify node that determines task complexity."""

    async def classify(state: AgentState) -> dict[str, Any]:
        log.info("node.classify", conversation_id=state.get("conversation_id"))
        messages = [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            *state["messages"],
        ]
        result, _ = await router.complete_structured(
            task_type=TaskType.EXECUTION,
            messages=messages,
            response_model=Classification,
            temperature=0.0,
        )
        log.info(
            "node.classify.result",
            task_type=result.task_type,
            reasoning=result.reasoning,
        )
        return {"task_type": result.task_type}

    return classify


def create_plan_node(
    router: LLMRouter,
) -> Any:
    """Create the plan node that breaks complex tasks into steps."""

    async def plan(state: AgentState) -> dict[str, Any]:
        log.info("node.plan", conversation_id=state.get("conversation_id"))
        messages = [
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            *state["messages"],
        ]
        result = await router.complete(
            task_type=TaskType.PLANNING,
            messages=messages,
        )
        log.info("node.plan.complete", plan_length=len(result.content))
        return {"plan": result.content}

    return plan


def create_execute_node(
    router: LLMRouter,
) -> Any:
    """Create the execute node that carries out the task."""

    async def execute(state: AgentState) -> dict[str, Any]:
        log.info("node.execute", conversation_id=state.get("conversation_id"))
        system_parts = [EXECUTE_SYSTEM_PROMPT]
        if state.get("plan"):
            system_parts.append(f"\nFollow this plan:\n{state['plan']}")

        messages = [
            {"role": "system", "content": "\n".join(system_parts)},
            *state["messages"],
        ]
        result = await router.complete(
            task_type=TaskType.EXECUTION,
            messages=messages,
        )
        log.info("node.execute.complete")
        return {"response": result.content}

    return execute


def create_respond_node() -> Any:
    """Create the respond node that appends the assistant reply to messages."""

    async def respond(state: AgentState) -> dict[str, Any]:
        log.info("node.respond", conversation_id=state.get("conversation_id"))
        return {
            "messages": [{"role": "assistant", "content": state["response"]}],
        }

    return respond

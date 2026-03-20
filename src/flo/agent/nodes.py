from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from flo.agent.state import AgentState, Classification, ExtractedPreference
from flo.llm.models import TaskType

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

    from flo.llm.router import LLMRouter

log = structlog.get_logger(__name__)

CLASSIFY_SYSTEM_PROMPT = (
    "You are a task classifier. Analyze the user's message and determine:\n"
    "1. If it requires complex multi-step planning (PLANNING) or a simple "
    "direct response (EXECUTION).\n"
    "2. If the user is correcting your behavior or stating a preference "
    "(is_correction=true).\n\n"
    "Examples of PLANNING tasks: scheduling meetings, researching topics, "
    "multi-step workflows, tasks requiring multiple tools.\n"
    "Examples of EXECUTION tasks: simple questions, greetings, single lookups, "
    "direct answers.\n"
    "Examples of CORRECTIONS: 'I prefer short answers', 'Don't use emojis', "
    "'Call me Chris', 'Remember that I'm vegetarian', "
    "'Actually I meant next week not this week'."
)

PLAN_SYSTEM_PROMPT = (
    "You are a planning assistant. Break down the user's request into "
    "a clear, step-by-step plan. Be specific and actionable."
)

EXECUTE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant. Respond clearly and concisely."
)

EXTRACT_PREFERENCE_PROMPT = (
    "Extract the user's preference or correction from the conversation. "
    "Summarize it as a short, actionable preference statement.\n\n"
    "Examples:\n"
    "- User says 'I prefer short answers' → "
    "preference: 'Prefers short, concise answers'\n"
    "- User says 'Call me Chris' → "
    "preference: 'Wants to be called Chris'\n"
    "- User says 'Don't use emojis' → "
    "preference: 'Does not want emojis in responses'"
)


def create_load_preferences_node() -> Any:
    """Create the load_preferences node that reads user preferences from Store."""

    async def load_preferences(
        state: AgentState, *, store: BaseStore
    ) -> dict[str, Any]:
        log.info(
            "node.load_preferences",
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        user_id = state.get("user_id", "")
        if not user_id:
            return {"user_preferences": []}

        items = await store.asearch(("users", user_id, "preferences"), limit=20)
        preferences = [item.value for item in items]
        log.info(
            "node.load_preferences.loaded",
            count=len(preferences),
        )
        return {"user_preferences": preferences}

    return load_preferences


def create_classify_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the classify node that determines task complexity."""

    async def classify(state: AgentState) -> dict[str, Any]:
        log.info("node.classify", conversation_id=state.get("conversation_id"))
        system_parts = [CLASSIFY_SYSTEM_PROMPT]
        prefs = state.get("user_preferences", [])
        if prefs:
            pref_lines = [p.get("preference", "") for p in prefs if p.get("preference")]
            if pref_lines:
                system_parts.append(
                    "\nKnown user preferences:\n"
                    + "\n".join(f"- {p}" for p in pref_lines)
                )

        messages = [
            {"role": "system", "content": "\n".join(system_parts)},
            *state["messages"][-max_messages:],
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
            is_correction=result.is_correction,
            reasoning=result.reasoning,
        )
        return {"task_type": result.task_type, "is_correction": result.is_correction}

    return classify


def create_plan_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the plan node that breaks complex tasks into steps."""

    async def plan(state: AgentState) -> dict[str, Any]:
        log.info("node.plan", conversation_id=state.get("conversation_id"))
        messages = [
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            *state["messages"][-max_messages:],
        ]
        result = await router.complete(
            task_type=TaskType.PLANNING,
            messages=messages,
        )
        log.info("node.plan.complete", plan_length=len(result.content))
        return {"plan": result.content}

    return plan


def create_execute_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the execute node that carries out the task."""

    async def execute(state: AgentState) -> dict[str, Any]:
        log.info("node.execute", conversation_id=state.get("conversation_id"))
        system_parts = [EXECUTE_SYSTEM_PROMPT]
        prefs = state.get("user_preferences", [])
        if prefs:
            pref_lines = [p.get("preference", "") for p in prefs if p.get("preference")]
            if pref_lines:
                system_parts.append(
                    "\nUser preferences:\n" + "\n".join(f"- {p}" for p in pref_lines)
                )
        if state.get("plan"):
            system_parts.append(f"\nFollow this plan:\n{state['plan']}")

        messages = [
            {"role": "system", "content": "\n".join(system_parts)},
            *state["messages"][-max_messages:],
        ]
        result = await router.complete(
            task_type=TaskType.EXECUTION,
            messages=messages,
        )
        log.info("node.execute.complete")
        return {"response": result.content}

    return execute


def create_store_correction_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the store_correction node that extracts and stores user preferences."""

    async def store_correction(
        state: AgentState, *, store: BaseStore
    ) -> dict[str, Any]:
        log.info(
            "node.store_correction",
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        messages = [
            {"role": "system", "content": EXTRACT_PREFERENCE_PROMPT},
            *state["messages"][-max_messages:],
        ]
        result, _ = await router.complete_structured(
            task_type=TaskType.EXECUTION,
            messages=messages,
            response_model=ExtractedPreference,
            temperature=0.0,
        )

        user_id = state.get("user_id", "default")
        key = uuid.uuid4().hex[:8]
        value = {
            "preference": result.preference,
            "source": "user_correction",
            "created": datetime.now(UTC).isoformat(),
        }
        await store.aput(("users", user_id, "preferences"), key, value)

        log.info(
            "node.store_correction.stored",
            preference=result.preference,
            key=key,
        )

        # Add new preference to state so execute sees it immediately
        existing = state.get("user_preferences", [])
        return {"user_preferences": [*existing, value]}

    return store_correction


def create_respond_node() -> Any:
    """Create the respond node that appends the assistant reply to messages."""

    async def respond(state: AgentState) -> dict[str, Any]:
        log.info("node.respond", conversation_id=state.get("conversation_id"))
        return {
            "messages": [{"role": "assistant", "content": state["response"]}],
        }

    return respond

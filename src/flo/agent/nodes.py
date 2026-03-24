from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.messages import AIMessage

from flo.agent.state import AgentState, Classification, ExtractedPreference
from flo.llm.models import TaskType

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore

    from flo.llm.router import LLMRouter

log = structlog.get_logger(__name__)


def _convert_tool_calls_to_langchain(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert OpenAI tool_calls format to LangChain format.

    OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
    LangChain format: {"id": "...", "name": "...", "args": {...}, "type": "tool_call"}
    """
    result = []
    for tc in tool_calls:
        # Handle OpenAI format
        if "function" in tc:
            args_str = tc["function"].get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            result.append({
                "id": tc.get("id", ""),
                "name": tc["function"]["name"],
                "args": args,
                "type": "tool_call",
            })
        # Already in LangChain format
        elif "name" in tc and "args" in tc:
            result.append(tc)
    return result


def _convert_tool_calls_to_openai(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert LangChain tool_calls format to OpenAI format.

    LangChain format: {"id": "...", "name": "...", "args": {...}, "type": "tool_call"}
    OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
    """
    result = []
    for tc in tool_calls:
        # Handle LangChain format
        if "name" in tc and "args" in tc:
            args = tc.get("args", {})
            args_str = json.dumps(args) if isinstance(args, dict) else str(args)
            result.append({
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": args_str,
                },
            })
        # Already in OpenAI format
        elif "function" in tc:
            result.append(tc)
    return result


def _sanitize_message_window(messages: list[Any]) -> list[Any]:
    """Drop leading tool messages that have no paired tool-call AIMessage in the window.

    When the message window is sliced, a ToolMessage can end up at the front
    without its paired AIMessage(tool_calls=[...]). Gemini (and some other
    providers) reject this. Drop those orphaned messages from the front.
    """
    result = list(messages)
    while result:
        msg = result[0]
        is_tool = False
        if isinstance(msg, dict):
            is_tool = msg.get("role") == "tool"
        elif hasattr(msg, "type"):
            is_tool = msg.type == "tool"
        if not is_tool:
            break
        result.pop(0)
    return result


def _convert_messages_to_openai(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert LangChain messages to OpenAI message format."""
    result = []
    for msg in messages:
        # Already a dict - pass through but check tool_calls
        if isinstance(msg, dict):
            if "tool_calls" in msg and msg["tool_calls"]:
                msg = dict(msg)
                msg["tool_calls"] = _convert_tool_calls_to_openai(msg["tool_calls"])
            result.append(msg)
            continue

        # Convert LangChain message types
        if hasattr(msg, "type"):
            msg_type = msg.type
            if msg_type == "human":
                result.append({"role": "user", "content": msg.content})
            elif msg_type == "ai":
                entry: dict[str, Any] = {"role": "assistant", "content": msg.content}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    entry["tool_calls"] = _convert_tool_calls_to_openai(msg.tool_calls)
                result.append(entry)
            elif msg_type == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": getattr(msg, "tool_call_id", ""),
                    "content": msg.content,
                })
            elif msg_type == "system":
                result.append({"role": "system", "content": msg.content})
            else:
                # Fallback
                result.append({"role": "user", "content": str(msg.content)})
        else:
            # Unknown format - try to extract content
            result.append({"role": "user", "content": str(msg)})
    return result


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
    from flo.tools import get_skill_descriptions

    skill_descriptions = get_skill_descriptions()
    skill_list = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skill_descriptions
    )

    async def classify(state: AgentState) -> dict[str, Any]:
        log.info("node.classify", conversation_id=state.get("conversation_id"))
        system_parts = [CLASSIFY_SYSTEM_PROMPT]

        if skill_list:
            system_parts.append(
                f"\nAvailable skills (select 0 or more by name):\n{skill_list}\n"
                "If the task requires tools, include the relevant skill names "
                "in active_skills. "
                "If no tools are needed, return an empty list."
            )

        prefs = state.get("user_preferences", [])
        if prefs:
            pref_lines = [p.get("preference", "") for p in prefs if p.get("preference")]
            if pref_lines:
                system_parts.append(
                    "\nKnown user preferences:\n"
                    + "\n".join(f"- {p}" for p in pref_lines)
                )

        # Convert LangChain messages to OpenAI format for litellm
        window = _sanitize_message_window(state["messages"][-max_messages:])
        converted_messages = _convert_messages_to_openai(window)
        messages = [
            {"role": "system", "content": "\n".join(system_parts)},
            *converted_messages,
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
            active_skills=result.active_skills,
            reasoning=result.reasoning,
        )
        return {
            "task_type": result.task_type,
            "is_correction": result.is_correction,
            "active_skills": result.active_skills,
        }

    return classify


def create_plan_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the plan node that breaks complex tasks into steps."""

    async def plan(state: AgentState) -> dict[str, Any]:
        log.info("node.plan", conversation_id=state.get("conversation_id"))
        # Convert LangChain messages to OpenAI format for litellm
        window = _sanitize_message_window(state["messages"][-max_messages:])
        converted_messages = _convert_messages_to_openai(window)
        messages = [
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            *converted_messages,
        ]
        result = await router.complete(
            task_type=TaskType.PLANNING,
            messages=messages,
        )
        log.info("node.plan.complete", plan_length=len(result.content))
        return {"plan": result.content}

    return plan


def create_execute_node(router: LLMRouter, *, max_messages: int = 20) -> Any:
    """Create the execute node that carries out the task.

    Loads tools from active_skills via SkillRegistry. If the LLM returns
    tool_calls, they are stored in messages for routing to ToolNode.
    """

    async def execute(state: AgentState) -> dict[str, Any]:
        log.info("node.execute", conversation_id=state.get("conversation_id"))

        system_parts = [EXECUTE_SYSTEM_PROMPT]

        from flo.tools import get_skill

        active_skill_names = state.get("active_skills", [])
        tools: list[Any] = []
        task_type = state.get("task_type") or TaskType.EXECUTION

        # Honor explicit model preference from the request
        model_pref = state.get("model_preference")
        if model_pref == "premium":
            task_type = TaskType.PLANNING
        elif model_pref == "fast":
            task_type = TaskType.EXECUTION

        for skill_name in active_skill_names:
            skill = get_skill(skill_name)
            if skill is None:
                continue
            tools.extend(skill.tools)
            system_parts.append(f"\n{skill.system_prompt}")
            if skill.task_type_override is not None:
                task_type = skill.task_type_override

        prefs = state.get("user_preferences", [])
        if prefs:
            pref_lines = [p.get("preference", "") for p in prefs if p.get("preference")]
            if pref_lines:
                system_parts.append(
                    "\nUser preferences:\n" + "\n".join(f"- {p}" for p in pref_lines)
                )
        if state.get("plan"):
            system_parts.append(f"\nFollow this plan:\n{state['plan']}")

        # Convert LangChain messages to OpenAI format for litellm
        window = _sanitize_message_window(state["messages"][-max_messages:])
        converted_messages = _convert_messages_to_openai(window)
        messages = [
            {"role": "system", "content": "\n".join(system_parts)},
            *converted_messages,
        ]

        if tools:
            result = await router.complete(
                task_type=task_type,
                messages=messages,
                tools=tools,
            )
        else:
            result = await router.complete(
                task_type=task_type,
                messages=messages,
            )

        log.info("node.execute.complete", active_skills=active_skill_names)

        if result.tool_calls:
            return {
                "messages": [
                    AIMessage(
                        content=result.content or "",
                        tool_calls=_convert_tool_calls_to_langchain(result.tool_calls),
                    )
                ],
                "response": "",
            }

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
        # Convert LangChain messages to OpenAI format for litellm
        window = _sanitize_message_window(state["messages"][-max_messages:])
        converted_messages = _convert_messages_to_openai(window)
        messages = [
            {"role": "system", "content": EXTRACT_PREFERENCE_PROMPT},
            *converted_messages,
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


def route_after_execute(state: AgentState) -> str:
    """Route to tool_node if tool_calls present, else to respond."""
    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tool_node"
    return "respond"

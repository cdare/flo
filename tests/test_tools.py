"""Tests for skill registry, tool factories, and tool-calling integration."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from flo.agent.nodes import (
    create_classify_node,
    create_execute_node,
    route_after_execute,
)
from flo.agent.state import Classification
from flo.llm.models import LLMResponse, TaskType
from flo.tools.base import Skill, SkillRegistry
from flo.tools.calendar.tools import create_calendar_tools
from flo.tools.gmail.tools import create_gmail_tools
from flo.tools.search.tools import (
    SerpAPIProvider,
    TavilyProvider,
    create_search_tools,
    make_search_provider,
)

# ---------------------------------------------------------------------------
# SkillRegistry tests
# ---------------------------------------------------------------------------


class TestSkillRegistry:
    def test_register_and_get_skill(self) -> None:
        reg = SkillRegistry()
        skill = Skill(name="test", description="A test skill")
        reg.register(skill)
        assert reg.get("test") is skill

    def test_get_unknown_skill_returns_none(self) -> None:
        reg = SkillRegistry()
        assert reg.get("unknown") is None

    def test_get_all_skills(self) -> None:
        reg = SkillRegistry()
        s1 = Skill(name="a", description="A")
        s2 = Skill(name="b", description="B")
        reg.register(s1)
        reg.register(s2)
        assert len(reg.get_all()) == 2

    def test_get_descriptions(self) -> None:
        reg = SkillRegistry()
        reg.register(Skill(name="cal", description="Calendar stuff"))
        descs = reg.get_descriptions()
        assert descs == [{"name": "cal", "description": "Calendar stuff"}]


# ---------------------------------------------------------------------------
# Calendar tool tests (factory DI with mock service)
# ---------------------------------------------------------------------------


def _make_calendar_service() -> MagicMock:
    """Build a mock Google Calendar API service."""
    svc = MagicMock()
    svc.events().list().execute.return_value = {
        "items": [
            {
                "id": "evt1",
                "summary": "Standup",
                "start": {"dateTime": "2026-03-20T09:00:00Z"},
                "end": {"dateTime": "2026-03-20T09:30:00Z"},
            }
        ]
    }
    svc.events().insert().execute.return_value = {
        "id": "new1",
        "summary": "Lunch",
    }
    svc.events().get().execute.return_value = {
        "id": "evt1",
        "summary": "Standup",
        "start": {"dateTime": "2026-03-20T09:00:00Z"},
        "end": {"dateTime": "2026-03-20T09:30:00Z"},
    }
    svc.events().update().execute.return_value = {
        "id": "evt1",
        "summary": "Updated",
    }
    svc.events().delete().execute.return_value = None
    return svc


class TestCalendarTools:
    def test_list_events(self) -> None:
        svc = _make_calendar_service()
        tools = create_calendar_tools(svc)
        list_events = tools[0]
        result = list_events.invoke({"max_results": 5})
        assert len(result) == 1
        assert result[0]["id"] == "evt1"
        assert result[0]["summary"] == "Standup"

    def test_list_events_uses_utc_now(self) -> None:
        """Verify datetime.now(UTC) is called, not utcnow()."""
        svc = _make_calendar_service()
        tools = create_calendar_tools(svc)
        list_events = tools[0]
        with patch("flo.tools.calendar.tools.datetime") as mock_dt:
            mock_dt.now.return_value.isoformat.return_value = (
                "2026-03-20T00:00:00+00:00"
            )
            from datetime import UTC

            list_events.invoke({"max_results": 5})
            mock_dt.now.assert_called_with(UTC)

    def test_create_event(self) -> None:
        svc = _make_calendar_service()
        tools = create_calendar_tools(svc)
        create_event = tools[1]
        result = create_event.invoke(
            {
                "summary": "Lunch",
                "start_time": "2026-03-20T12:00:00Z",
                "end_time": "2026-03-20T13:00:00Z",
            }
        )
        assert result["id"] == "new1"

    def test_update_event(self) -> None:
        svc = _make_calendar_service()
        tools = create_calendar_tools(svc)
        update_event = tools[2]
        result = update_event.invoke({"event_id": "evt1", "summary": "Updated"})
        assert result["id"] == "evt1"

    def test_delete_event(self) -> None:
        svc = _make_calendar_service()
        tools = create_calendar_tools(svc)
        delete_event = tools[3]
        result = delete_event.invoke({"event_id": "evt1"})
        assert "evt1" in result
        assert "deleted" in result.lower()


# ---------------------------------------------------------------------------
# Gmail tool tests (factory DI with mock service)
# ---------------------------------------------------------------------------


def _make_gmail_service() -> MagicMock:
    """Build a mock Gmail API service."""
    svc = MagicMock()
    svc.users().messages().list().execute.return_value = {"messages": [{"id": "msg1"}]}

    # For metadata get
    meta_msg = {
        "id": "msg1",
        "snippet": "Hey there",
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "2026-03-20"},
            ]
        },
    }

    import base64

    body_data = base64.urlsafe_b64encode(b"Email body text").decode()
    full_msg = {
        "id": "msg1",
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "2026-03-20"},
            ],
            "body": {"data": body_data},
        },
    }

    def _get_side_effect(**kwargs: Any) -> MagicMock:
        m = MagicMock()
        if kwargs.get("format") == "metadata":
            m.execute.return_value = meta_msg
        else:
            m.execute.return_value = full_msg
        return m

    svc.users().messages().get = _get_side_effect

    svc.users().messages().send().execute.return_value = {"id": "sent1"}
    return svc


class TestGmailTools:
    def test_list_emails(self) -> None:
        svc = _make_gmail_service()
        tools = create_gmail_tools(svc)
        list_emails = tools[0]
        result = list_emails.invoke({"max_results": 5})
        assert len(result) == 1
        assert result[0]["id"] == "msg1"
        assert result[0]["from"] == "alice@example.com"

    def test_read_email(self) -> None:
        svc = _make_gmail_service()
        tools = create_gmail_tools(svc)
        read_email = tools[1]
        result = read_email.invoke({"message_id": "msg1"})
        assert result["id"] == "msg1"
        assert result["body"] == "Email body text"

    def test_send_email(self) -> None:
        svc = _make_gmail_service()
        tools = create_gmail_tools(svc)
        send_email = tools[2]
        result = send_email.invoke(
            {
                "to": "bob@example.com",
                "subject": "Hi",
                "body": "Hello!",
            }
        )
        assert result["id"] == "sent1"
        assert result["status"] == "sent"

    def test_search_emails_delegates_to_shared_logic(self) -> None:
        svc = _make_gmail_service()
        tools = create_gmail_tools(svc)
        search_emails = tools[3]
        result = search_emails.invoke({"query": "from:alice", "max_results": 5})
        assert len(result) == 1
        assert result[0]["id"] == "msg1"


# ---------------------------------------------------------------------------
# Search tool tests (factory DI with mock provider)
# ---------------------------------------------------------------------------


class TestSearchTools:
    async def test_web_search_with_mock_provider(self) -> None:
        provider = AsyncMock()
        provider.search.return_value = [
            {"title": "Result", "url": "https://example.com", "content": "..."}
        ]
        tools = create_search_tools(provider)
        web_search = tools[0]
        result = await web_search.ainvoke({"query": "test query", "max_results": 3})
        assert len(result) == 1
        provider.search.assert_awaited_once_with("test query", 3)

    def test_make_search_provider_tavily(self) -> None:
        p = make_search_provider("tavily", "key-123")
        assert isinstance(p, TavilyProvider)

    def test_make_search_provider_serpapi(self) -> None:
        p = make_search_provider("serpapi", "key-456")
        assert isinstance(p, SerpAPIProvider)

    def test_make_search_provider_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown search provider"):
            make_search_provider("unknown", "key")


# ---------------------------------------------------------------------------
# LLMResponse tool_calls tests
# ---------------------------------------------------------------------------


class TestLLMResponseToolCalls:
    def test_tool_calls_default_none(self) -> None:
        resp = LLMResponse(
            content="hi",
            model="test",
            task_type=TaskType.EXECUTION,
        )
        assert resp.tool_calls is None

    def test_tool_calls_populated(self) -> None:
        calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "list_events", "arguments": "{}"},
            }
        ]
        resp = LLMResponse(
            content="",
            model="test",
            task_type=TaskType.EXECUTION,
            tool_calls=calls,
        )
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_router_complete_extracts_tool_calls(
        self,
        mock_cost: Any,
        mock_acompletion: AsyncMock,
    ) -> None:
        from flo.config import Settings
        from flo.llm.router import LLMRouter

        settings = Settings(
            env="test",
            cheap_model="test-cheap-model",
            premium_model="test-premium-model",
        )
        router = LLMRouter(settings)

        tc = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(
                name="list_events", arguments='{"max_results": 5}'
            ),
        )
        resp = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc]))
            ],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )
        mock_acompletion.return_value = resp

        result = await router.complete(
            task_type=TaskType.EXECUTION,
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result.tool_calls is not None
        assert result.tool_calls[0]["function"]["name"] == "list_events"


# ---------------------------------------------------------------------------
# Classification model backward compatibility
# ---------------------------------------------------------------------------


class TestClassificationActiveSkills:
    def test_default_empty_active_skills(self) -> None:
        c = Classification(
            task_type=TaskType.EXECUTION,
            is_correction=False,
            reasoning="Simple",
        )
        assert c.active_skills == []

    def test_active_skills_set(self) -> None:
        c = Classification(
            task_type=TaskType.EXECUTION,
            is_correction=False,
            active_skills=["calendar"],
            reasoning="Need calendar",
        )
        assert c.active_skills == ["calendar"]


# ---------------------------------------------------------------------------
# Agent node integration tests
# ---------------------------------------------------------------------------


class TestClassifyNodeSkills:
    async def test_classify_returns_active_skills(self) -> None:
        router = AsyncMock()
        router.complete_structured.return_value = (
            Classification(
                task_type=TaskType.EXECUTION,
                is_correction=False,
                active_skills=["calendar"],
                reasoning="Calendar query",
            ),
            LLMResponse(
                content="{}",
                model="test",
                task_type=TaskType.EXECUTION,
            ),
        )
        classify = create_classify_node(router)
        result = await classify(
            {
                "messages": [{"role": "user", "content": "What's on my calendar?"}],
                "conversation_id": "test",
                "user_preferences": [],
            }
        )
        assert result["active_skills"] == ["calendar"]


class TestExecuteNodeSkills:
    async def test_execute_loads_skill_tools(self) -> None:
        """Active skill's tools are passed to LLM via router.complete()."""
        from flo.tools import _registry, register_skill

        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        skill = Skill(
            name="mock_skill",
            description="Mock",
            tools=[mock_tool],
            system_prompt="Use mock tool.",
        )
        register_skill(skill)

        try:
            router = AsyncMock()
            router.complete.return_value = LLMResponse(
                content="Done with tools",
                model="test",
                task_type=TaskType.EXECUTION,
            )
            execute = create_execute_node(router)
            result = await execute(
                {
                    "messages": [{"role": "user", "content": "Do something"}],
                    "plan": None,
                    "conversation_id": "test",
                    "user_preferences": [],
                    "active_skills": ["mock_skill"],
                }
            )
            assert result["response"] == "Done with tools"
            call_kwargs = router.complete.call_args.kwargs
            assert call_kwargs["tools"] == [mock_tool]
        finally:
            _registry._skills.pop("mock_skill", None)

    async def test_execute_no_skills(self) -> None:
        """Empty active_skills → execute works without tools."""
        router = AsyncMock()
        router.complete.return_value = LLMResponse(
            content="No tools needed",
            model="test",
            task_type=TaskType.EXECUTION,
        )
        execute = create_execute_node(router)
        result = await execute(
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "plan": None,
                "conversation_id": "test",
                "user_preferences": [],
                "active_skills": [],
            }
        )
        assert result["response"] == "No tools needed"
        call_kwargs = router.complete.call_args.kwargs
        assert "tools" not in call_kwargs

    async def test_skill_system_prompt_injected(self) -> None:
        """Active skill's system_prompt appears in execute LLM prompt."""
        from flo.tools import _registry, register_skill

        skill = Skill(
            name="prompt_skill",
            description="Test prompt injection",
            tools=[],
            system_prompt="USE THE SPECIAL TOOL.",
        )
        register_skill(skill)

        try:
            router = AsyncMock()
            router.complete.return_value = LLMResponse(
                content="ok",
                model="test",
                task_type=TaskType.EXECUTION,
            )
            execute = create_execute_node(router)
            await execute(
                {
                    "messages": [{"role": "user", "content": "hi"}],
                    "plan": None,
                    "conversation_id": "test",
                    "user_preferences": [],
                    "active_skills": ["prompt_skill"],
                }
            )
            call_kwargs = router.complete.call_args.kwargs
            system_msg = call_kwargs["messages"][0]["content"]
            assert "USE THE SPECIAL TOOL." in system_msg
        finally:
            _registry._skills.pop("prompt_skill", None)


# ---------------------------------------------------------------------------
# Route after execute tests
# ---------------------------------------------------------------------------


class TestRouteAfterExecute:
    def test_routes_to_tool_node(self) -> None:
        state: dict[str, Any] = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "list_events",
                            "args": {},
                        }
                    ],
                )
            ],
            "response": "",
        }
        assert route_after_execute(state) == "tool_node"  # type: ignore[arg-type]

    def test_routes_to_respond(self) -> None:
        state: dict[str, Any] = {
            "messages": [{"role": "assistant", "content": "Done"}],
            "response": "Done",
        }
        assert route_after_execute(state) == "respond"  # type: ignore[arg-type]

    def test_routes_to_respond_when_no_messages(self) -> None:
        state: dict[str, Any] = {"messages": [], "response": ""}
        assert route_after_execute(state) == "respond"  # type: ignore[arg-type]

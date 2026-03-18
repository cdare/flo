from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from flo.agent.graph import _route_after_classify, build_graph
from flo.agent.nodes import (
    create_classify_node,
    create_execute_node,
    create_plan_node,
    create_respond_node,
)
from flo.agent.state import AgentState, Classification
from flo.llm.models import LLMResponse, TaskType

if TYPE_CHECKING:
    from flo.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_router() -> AsyncMock:
    """LLMRouter mock with default EXECUTION classification."""
    router = AsyncMock()
    router.complete_structured.return_value = (
        Classification(task_type=TaskType.EXECUTION, reasoning="Simple query"),
        LLMResponse(
            content='{"task_type": "execution", "reasoning": "Simple query"}',
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        ),
    )
    router.complete.return_value = LLMResponse(
        content="Test response",
        model="test-cheap-model",
        task_type=TaskType.EXECUTION,
    )
    return router


@pytest.fixture
def planning_router(mock_router: AsyncMock) -> AsyncMock:
    """LLMRouter mock that classifies as PLANNING."""
    mock_router.complete_structured.return_value = (
        Classification(task_type=TaskType.PLANNING, reasoning="Complex task"),
        LLMResponse(
            content='{"task_type": "planning", "reasoning": "Complex task"}',
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        ),
    )
    # First call = plan node (planning model), second call = execute node
    mock_router.complete.side_effect = [
        LLMResponse(
            content="Step 1: Do X\nStep 2: Do Y",
            model="test-premium-model",
            task_type=TaskType.PLANNING,
        ),
        LLMResponse(
            content="Done! I completed X and Y.",
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        ),
    ]
    return mock_router


USER_MSG: dict[str, str] = {"role": "user", "content": "Hello"}


# ---------------------------------------------------------------------------
# State & Classification tests
# ---------------------------------------------------------------------------


class TestAgentState:
    def test_state_fields(self) -> None:
        state: AgentState = {
            "messages": [USER_MSG],
            "task_type": TaskType.EXECUTION,
            "plan": None,
            "response": "Hi!",
            "conversation_id": "test-123",
        }
        assert state["messages"] == [USER_MSG]
        assert state["task_type"] == TaskType.EXECUTION
        assert state["conversation_id"] == "test-123"


class TestClassification:
    def test_execution(self) -> None:
        c = Classification(task_type=TaskType.EXECUTION, reasoning="Simple")
        assert c.task_type == TaskType.EXECUTION

    def test_planning(self) -> None:
        c = Classification(task_type=TaskType.PLANNING, reasoning="Complex")
        assert c.task_type == TaskType.PLANNING


# ---------------------------------------------------------------------------
# Routing logic tests
# ---------------------------------------------------------------------------


class TestRouting:
    def test_routes_execution_to_execute(self) -> None:
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.EXECUTION,
            "plan": None,
            "response": "",
            "conversation_id": "test",
        }
        assert _route_after_classify(state) == "execute"

    def test_routes_planning_to_plan(self) -> None:
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.PLANNING,
            "plan": None,
            "response": "",
            "conversation_id": "test",
        }
        assert _route_after_classify(state) == "plan"

    def test_routes_none_to_execute(self) -> None:
        """Default to execute if task_type is not set."""
        state: AgentState = {
            "messages": [],
            "task_type": None,
            "plan": None,
            "response": "",
            "conversation_id": "test",
        }
        assert _route_after_classify(state) == "execute"


# ---------------------------------------------------------------------------
# Individual node tests
# ---------------------------------------------------------------------------


class TestClassifyNode:
    async def test_classifies_as_execution(self, mock_router: AsyncMock) -> None:
        classify = create_classify_node(mock_router)
        result = await classify({"messages": [USER_MSG], "conversation_id": "test"})
        assert result["task_type"] == TaskType.EXECUTION
        mock_router.complete_structured.assert_awaited_once()

    async def test_classifies_as_planning(self, planning_router: AsyncMock) -> None:
        classify = create_classify_node(planning_router)
        result = await classify({"messages": [USER_MSG], "conversation_id": "test"})
        assert result["task_type"] == TaskType.PLANNING


class TestPlanNode:
    async def test_creates_plan(self, mock_router: AsyncMock) -> None:
        mock_router.complete.return_value = LLMResponse(
            content="Step 1: Do this",
            model="test-premium-model",
            task_type=TaskType.PLANNING,
        )
        plan = create_plan_node(mock_router)
        result = await plan({"messages": [USER_MSG], "conversation_id": "test"})
        assert result["plan"] == "Step 1: Do this"
        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task_type"] == TaskType.PLANNING


class TestExecuteNode:
    async def test_executes_without_plan(self, mock_router: AsyncMock) -> None:
        execute = create_execute_node(mock_router)
        result = await execute(
            {"messages": [USER_MSG], "plan": None, "conversation_id": "test"}
        )
        assert result["response"] == "Test response"
        call_kwargs = mock_router.complete.call_args.kwargs
        assert call_kwargs["task_type"] == TaskType.EXECUTION

    async def test_executes_with_plan(self, mock_router: AsyncMock) -> None:
        execute = create_execute_node(mock_router)
        result = await execute(
            {
                "messages": [USER_MSG],
                "plan": "Step 1: Greet",
                "conversation_id": "test",
            }
        )
        assert result["response"] == "Test response"
        # Verify plan was included in the system prompt
        call_kwargs = mock_router.complete.call_args.kwargs
        system_msg = call_kwargs["messages"][0]["content"]
        assert "Step 1: Greet" in system_msg


class TestRespondNode:
    async def test_appends_assistant_message(self) -> None:
        respond = create_respond_node()
        result = await respond({"response": "Hello!", "conversation_id": "test"})
        assert result["messages"] == [{"role": "assistant", "content": "Hello!"}]


# ---------------------------------------------------------------------------
# Full graph integration tests
# ---------------------------------------------------------------------------


class TestGraphSimplePath:
    async def test_simple_query_skips_planning(
        self, settings: Settings, mock_router: AsyncMock
    ) -> None:
        """classify(EXECUTION) → execute → respond — plan node not called."""
        graph = build_graph(settings, router=mock_router)
        result = await graph.ainvoke(
            {
                "messages": [USER_MSG],
                "conversation_id": "test-simple",
            },
            config={"configurable": {"thread_id": "test-simple"}},
        )
        assert result["task_type"] == TaskType.EXECUTION
        assert result["response"] == "Test response"
        assert result.get("plan") is None
        # execute was called once (no plan call)
        assert mock_router.complete.await_count == 1
        # Assistant message appended
        assert {"role": "assistant", "content": "Test response"} in result["messages"]


class TestGraphComplexPath:
    async def test_complex_query_includes_planning(
        self, settings: Settings, planning_router: AsyncMock
    ) -> None:
        """classify(PLANNING) → plan → execute → respond."""
        graph = build_graph(settings, router=planning_router)
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Schedule meetings for next week",
                    }
                ],
                "conversation_id": "test-complex",
            },
            config={"configurable": {"thread_id": "test-complex"}},
        )
        assert result["task_type"] == TaskType.PLANNING
        assert result["plan"] == "Step 1: Do X\nStep 2: Do Y"
        assert result["response"] == "Done! I completed X and Y."
        # plan + execute = 2 complete() calls
        assert planning_router.complete.await_count == 2


class TestGraphConversation:
    async def test_conversation_continuity(
        self, settings: Settings, mock_router: AsyncMock
    ) -> None:
        """Second invocation on same thread sees prior messages."""
        graph = build_graph(settings, router=mock_router)
        thread_config = {"configurable": {"thread_id": "convo-1"}}

        # First turn
        result1 = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "conversation_id": "convo-1",
            },
            config=thread_config,
        )
        assert {"role": "assistant", "content": "Test response"} in result1["messages"]

        # Reset mock for second turn
        mock_router.reset_mock()
        mock_router.complete_structured.return_value = (
            Classification(task_type=TaskType.EXECUTION, reasoning="Follow-up"),
            LLMResponse(
                content="{}",
                model="test-cheap-model",
                task_type=TaskType.EXECUTION,
            ),
        )
        mock_router.complete.return_value = LLMResponse(
            content="Second response",
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        )

        # Second turn on same thread
        result2 = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": "Follow up"}],
                "conversation_id": "convo-1",
            },
            config=thread_config,
        )
        # Should see accumulated messages from both turns
        assert len(result2["messages"]) >= 4  # user1 + assistant1 + user2 + assistant2
        assert result2["response"] == "Second response"

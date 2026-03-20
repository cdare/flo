from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore

from flo.agent.graph import _route_after_classify, build_graph
from flo.agent.nodes import (
    create_classify_node,
    create_execute_node,
    create_load_preferences_node,
    create_plan_node,
    create_respond_node,
    create_store_correction_node,
)
from flo.agent.state import AgentState, Classification, ExtractedPreference
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
        Classification(
            task_type=TaskType.EXECUTION,
            reasoning="Simple query",
            is_correction=False,
        ),
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
        Classification(
            task_type=TaskType.PLANNING,
            reasoning="Complex task",
            is_correction=False,
        ),
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
            "is_correction": False,
            "plan": None,
            "response": "Hi!",
            "conversation_id": "test-123",
            "user_id": "test-user",
            "user_preferences": [],
        }
        assert state["messages"] == [USER_MSG]
        assert state["task_type"] == TaskType.EXECUTION
        assert state["conversation_id"] == "test-123"


class TestClassification:
    def test_execution(self) -> None:
        c = Classification(
            task_type=TaskType.EXECUTION, reasoning="Simple", is_correction=False
        )
        assert c.task_type == TaskType.EXECUTION

    def test_planning(self) -> None:
        c = Classification(
            task_type=TaskType.PLANNING, reasoning="Complex", is_correction=False
        )
        assert c.task_type == TaskType.PLANNING


# ---------------------------------------------------------------------------
# Routing logic tests
# ---------------------------------------------------------------------------


class TestRouting:
    def test_routes_execution_to_execute(self) -> None:
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.EXECUTION,
            "is_correction": False,
            "plan": None,
            "response": "",
            "conversation_id": "test",
            "user_id": "test",
            "user_preferences": [],
        }
        assert _route_after_classify(state) == "execute"

    def test_routes_planning_to_plan(self) -> None:
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.PLANNING,
            "is_correction": False,
            "plan": None,
            "response": "",
            "conversation_id": "test",
            "user_id": "test",
            "user_preferences": [],
        }
        assert _route_after_classify(state) == "plan"

    def test_routes_none_to_execute(self) -> None:
        """Default to execute if task_type is not set."""
        state: AgentState = {
            "messages": [],
            "task_type": None,
            "is_correction": False,
            "plan": None,
            "response": "",
            "conversation_id": "test",
            "user_id": "test",
            "user_preferences": [],
        }
        assert _route_after_classify(state) == "execute"

    def test_routes_correction_to_store_correction(self) -> None:
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.EXECUTION,
            "is_correction": True,
            "plan": None,
            "response": "",
            "conversation_id": "test",
            "user_id": "test",
            "user_preferences": [],
        }
        assert _route_after_classify(state) == "store_correction"

    def test_routes_correction_with_planning_to_store_correction(self) -> None:
        """Corrections skip planning even when task_type is PLANNING.

        Documents intended behavior: is_correction takes priority over
        task_type. Planning-aware corrections are deferred to a future phase.
        """
        state: AgentState = {
            "messages": [],
            "task_type": TaskType.PLANNING,
            "is_correction": True,
            "plan": None,
            "response": "",
            "conversation_id": "test",
            "user_id": "test",
            "user_preferences": [],
        }
        assert _route_after_classify(state) == "store_correction"


# ---------------------------------------------------------------------------
# Individual node tests
# ---------------------------------------------------------------------------


class TestClassifyNode:
    async def test_classifies_as_execution(self, mock_router: AsyncMock) -> None:
        classify = create_classify_node(mock_router)
        result = await classify(
            {
                "messages": [USER_MSG],
                "conversation_id": "test",
                "user_preferences": [],
            }
        )
        assert result["task_type"] == TaskType.EXECUTION
        assert result["is_correction"] is False
        mock_router.complete_structured.assert_awaited_once()

    async def test_classifies_as_planning(self, planning_router: AsyncMock) -> None:
        classify = create_classify_node(planning_router)
        result = await classify(
            {
                "messages": [USER_MSG],
                "conversation_id": "test",
                "user_preferences": [],
            }
        )
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
            {
                "messages": [USER_MSG],
                "plan": None,
                "conversation_id": "test",
                "user_preferences": [],
            }
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
                "user_preferences": [],
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
# Load preferences node tests
# ---------------------------------------------------------------------------


class TestLoadPreferencesNode:
    async def test_loads_preferences(self) -> None:
        """Preferences loaded from Store are returned in state."""
        store = InMemoryStore()
        store.put(
            ("users", "user-1", "preferences"),
            "pref-1",
            {"preference": "Prefers short answers", "source": "user_correction"},
        )
        load_prefs = create_load_preferences_node()
        result = await load_prefs(
            {"user_id": "user-1", "messages": [], "conversation_id": "test"},
            store=store,
        )
        assert len(result["user_preferences"]) == 1
        assert result["user_preferences"][0]["preference"] == "Prefers short answers"

    async def test_empty_when_no_preferences(self) -> None:
        """Empty list returned when no preferences stored."""
        store = InMemoryStore()
        load_prefs = create_load_preferences_node()
        result = await load_prefs(
            {"user_id": "user-1", "messages": [], "conversation_id": "test"},
            store=store,
        )
        assert result["user_preferences"] == []

    async def test_empty_when_no_user_id(self) -> None:
        """Empty list returned when user_id is empty."""
        store = InMemoryStore()
        load_prefs = create_load_preferences_node()
        result = await load_prefs(
            {"user_id": "", "messages": [], "conversation_id": "test"},
            store=store,
        )
        assert result["user_preferences"] == []


# ---------------------------------------------------------------------------
# Store correction node tests
# ---------------------------------------------------------------------------


class TestStoreCorrectionNode:
    async def test_stores_preference(self, mock_router: AsyncMock) -> None:
        """Correction is extracted and stored in Store."""
        mock_router.complete_structured.return_value = (
            ExtractedPreference(
                preference="Prefers short answers",
                reasoning="User asked for brevity",
            ),
            LLMResponse(
                content='{"preference": "Prefers short answers", "reasoning": "..."}',
                model="test-cheap-model",
                task_type=TaskType.EXECUTION,
            ),
        )
        store = InMemoryStore()
        store_corr = create_store_correction_node(mock_router)
        result = await store_corr(
            {
                "messages": [{"role": "user", "content": "I prefer short answers"}],
                "user_id": "user-1",
                "user_preferences": [],
                "conversation_id": "test",
            },
            store=store,
        )
        # Verify preference stored in Store
        items = store.search(("users", "user-1", "preferences"))
        assert len(items) == 1
        assert items[0].value["preference"] == "Prefers short answers"
        assert items[0].value["source"] == "user_correction"
        # Verify state updated
        assert len(result["user_preferences"]) == 1


# ---------------------------------------------------------------------------
# Classify correction tests
# ---------------------------------------------------------------------------


class TestClassifyNodeCorrection:
    async def test_classifies_correction(self, mock_router: AsyncMock) -> None:
        """Messages like 'I prefer short answers' are classified as corrections."""
        mock_router.complete_structured.return_value = (
            Classification(
                task_type=TaskType.EXECUTION,
                is_correction=True,
                reasoning="User stating preference",
            ),
            LLMResponse(
                content="{}",
                model="test-cheap-model",
                task_type=TaskType.EXECUTION,
            ),
        )
        classify = create_classify_node(mock_router)
        result = await classify(
            {
                "messages": [{"role": "user", "content": "I prefer short answers"}],
                "conversation_id": "test",
                "user_preferences": [],
            }
        )
        assert result["is_correction"] is True


# ---------------------------------------------------------------------------
# Message windowing tests
# ---------------------------------------------------------------------------


class TestMessageWindowing:
    async def test_messages_sliced_to_max(self, mock_router: AsyncMock) -> None:
        """Only last max_messages messages are sent to LLM."""
        mock_router.complete.return_value = LLMResponse(
            content="Response",
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        )
        many_messages = [{"role": "user", "content": f"Message {i}"} for i in range(30)]
        execute = create_execute_node(mock_router, max_messages=5)
        await execute(
            {
                "messages": many_messages,
                "plan": None,
                "conversation_id": "test",
                "user_preferences": [],
            }
        )
        call_msgs = mock_router.complete.call_args.kwargs["messages"]
        # system prompt + last 5 user messages
        assert len(call_msgs) == 6  # 1 system + 5 windowed


# ---------------------------------------------------------------------------
# Preference injection tests
# ---------------------------------------------------------------------------


class TestPreferenceInjection:
    async def test_preferences_in_execute_prompt(self, mock_router: AsyncMock) -> None:
        """User preferences are included in execute system prompt."""
        execute = create_execute_node(mock_router)
        await execute(
            {
                "messages": [{"role": "user", "content": "Hello"}],
                "plan": None,
                "conversation_id": "test",
                "user_preferences": [
                    {"preference": "Prefers short answers"},
                    {"preference": "Wants to be called Chris"},
                ],
            }
        )
        call_msgs = mock_router.complete.call_args.kwargs["messages"]
        system_msg = call_msgs[0]["content"]
        assert "Prefers short answers" in system_msg
        assert "Wants to be called Chris" in system_msg


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
                "user_id": "test-user",
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
                "user_id": "test-user",
            },
            config={"configurable": {"thread_id": "test-complex"}},
        )
        assert result["task_type"] == TaskType.PLANNING
        assert result["plan"] == "Step 1: Do X\nStep 2: Do Y"
        assert result["response"] == "Done! I completed X and Y."
        # plan + execute = 2 complete() calls
        assert planning_router.complete.await_count == 2


class TestGraphCorrectionFlow:
    async def test_correction_stores_and_responds(self, settings: Settings) -> None:
        """Correction message → store_correction → execute → respond."""
        router = AsyncMock()
        # 1st call: classify (correction detected)
        router.complete_structured.side_effect = [
            (
                Classification(
                    task_type=TaskType.EXECUTION,
                    is_correction=True,
                    reasoning="User correction",
                ),
                LLMResponse(content="{}", model="m", task_type=TaskType.EXECUTION),
            ),
            # 2nd call: store_correction (extract preference)
            (
                ExtractedPreference(
                    preference="Prefers short answers",
                    reasoning="Brevity requested",
                ),
                LLMResponse(content="{}", model="m", task_type=TaskType.EXECUTION),
            ),
        ]
        router.complete.return_value = LLMResponse(
            content="Got it, I'll keep answers short!",
            model="test-cheap-model",
            task_type=TaskType.EXECUTION,
        )
        store = InMemoryStore()
        graph = build_graph(settings, router=router, store=store)
        result = await graph.ainvoke(
            {
                "messages": [{"role": "user", "content": "I prefer short answers"}],
                "conversation_id": "test-correction",
                "user_id": "user-1",
            },
            config={"configurable": {"thread_id": "test-correction"}},
        )
        assert "short" in result["response"].lower()
        # Verify preference was persisted in Store
        items = store.search(("users", "user-1", "preferences"))
        assert len(items) == 1
        assert items[0].value["preference"] == "Prefers short answers"


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
                "user_id": "test-user",
            },
            config=thread_config,
        )
        assert {"role": "assistant", "content": "Test response"} in result1["messages"]

        # Reset mock for second turn
        mock_router.reset_mock()
        mock_router.complete_structured.return_value = (
            Classification(
                task_type=TaskType.EXECUTION,
                reasoning="Follow-up",
                is_correction=False,
            ),
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
                "user_id": "test-user",
            },
            config=thread_config,
        )
        # Should see accumulated messages from both turns
        assert len(result2["messages"]) >= 4  # user1 + assistant1 + user2 + assistant2
        assert result2["response"] == "Second response"

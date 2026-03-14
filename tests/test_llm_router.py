from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pydantic
import pytest
from pydantic import BaseModel

from flo.llm import LLMRouter, TaskType
from flo.llm.models import LLMResponse, UsageStats

if TYPE_CHECKING:
    from flo.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Uses shared `settings` fixture from conftest.py
# (cheap_model="test-cheap-model", premium_model="test-premium-model")


@pytest.fixture
def router(settings: Settings) -> LLMRouter:
    return LLMRouter(settings)


def _mock_response(
    content: str = "Hello!",
    model: str = "test-model",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    """Build a fake litellm response object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


MESSAGES: list[dict[str, str]] = [{"role": "user", "content": "Hi"}]


# ---------------------------------------------------------------------------
# TaskType & models tests
# ---------------------------------------------------------------------------


class TestTaskType:
    def test_values(self) -> None:
        assert TaskType.EXECUTION == "execution"
        assert TaskType.PLANNING == "planning"

    def test_is_str(self) -> None:
        assert isinstance(TaskType.EXECUTION, str)


class TestUsageStats:
    def test_defaults(self) -> None:
        usage = UsageStats()
        assert usage.prompt_tokens == 0
        assert usage.cost_usd == 0.0

    def test_frozen(self) -> None:
        usage = UsageStats(prompt_tokens=10)
        with pytest.raises(AttributeError):
            usage.prompt_tokens = 20  # type: ignore[misc]


class TestLLMResponse:
    def test_creation(self) -> None:
        resp = LLMResponse(
            content="test",
            model="gpt-4o-mini",
            task_type=TaskType.EXECUTION,
        )
        assert resp.content == "test"
        assert resp.usage.total_tokens == 0


# ---------------------------------------------------------------------------
# Router construction tests
# ---------------------------------------------------------------------------


class TestRouterInit:
    def test_model_for_execution(self, router: LLMRouter) -> None:
        assert router.model_for(TaskType.EXECUTION) == "test-cheap-model"

    def test_model_for_planning(self, router: LLMRouter) -> None:
        assert router.model_for(TaskType.PLANNING) == "test-premium-model"


# ---------------------------------------------------------------------------
# complete() tests
# ---------------------------------------------------------------------------


class TestComplete:
    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0001)
    async def test_routes_execution_to_cheap(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response(content="Done")

        result = await router.complete(task_type=TaskType.EXECUTION, messages=MESSAGES)

        mock_acompletion.assert_awaited_once()
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["model"] == "test-cheap-model"
        assert result.content == "Done"
        assert result.task_type == TaskType.EXECUTION
        assert result.model == "test-cheap-model"

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.005)
    async def test_routes_planning_to_premium(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response(content="Plan ready")

        result = await router.complete(task_type=TaskType.PLANNING, messages=MESSAGES)

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["model"] == "test-premium-model"
        assert result.content == "Plan ready"
        assert result.task_type == TaskType.PLANNING

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.001)
    async def test_usage_stats_populated(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response(
            prompt_tokens=50, completion_tokens=25
        )

        result = await router.complete(task_type=TaskType.EXECUTION, messages=MESSAGES)

        assert result.usage.prompt_tokens == 50
        assert result.usage.completion_tokens == 25
        assert result.usage.total_tokens == 75
        assert result.usage.cost_usd == pytest.approx(0.001)

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_passes_temperature_and_max_tokens(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response()

        await router.complete(
            task_type=TaskType.EXECUTION,
            messages=MESSAGES,
            temperature=0.2,
            max_tokens=100,
        )

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["max_tokens"] == 100

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_passes_extra_kwargs(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response()

        await router.complete(
            task_type=TaskType.EXECUTION,
            messages=MESSAGES,
            top_p=0.9,
        )

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["top_p"] == 0.9

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    async def test_handles_missing_usage(
        self, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        resp = _mock_response()
        resp.usage = None
        mock_acompletion.return_value = resp

        result = await router.complete(task_type=TaskType.EXECUTION, messages=MESSAGES)

        assert result.usage.prompt_tokens == 0
        assert result.usage.cost_usd == 0.0

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_handles_none_content(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        resp = _mock_response()
        resp.choices[0].message.content = None
        mock_acompletion.return_value = resp

        result = await router.complete(task_type=TaskType.EXECUTION, messages=MESSAGES)

        assert result.content == ""


# ---------------------------------------------------------------------------
# complete_structured() tests
# ---------------------------------------------------------------------------


class _TestPlan(BaseModel):
    goal: str
    steps: list[str]


class TestCompleteStructured:
    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.002)
    async def test_parses_pydantic_model(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        json_content = (
            '{"goal": "Buy groceries", "steps": ["Make list", "Go to store"]}'
        )
        mock_acompletion.return_value = _mock_response(content=json_content)

        parsed, llm_resp = await router.complete_structured(
            task_type=TaskType.PLANNING,
            messages=MESSAGES,
            response_model=_TestPlan,
        )

        assert isinstance(parsed, _TestPlan)
        assert parsed.goal == "Buy groceries"
        assert len(parsed.steps) == 2
        assert llm_resp.model == "test-premium-model"
        assert llm_resp.usage.cost_usd == pytest.approx(0.002)

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_passes_response_format(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response(
            content='{"goal": "x", "steps": []}'
        )

        await router.complete_structured(
            task_type=TaskType.EXECUTION,
            messages=MESSAGES,
            response_model=_TestPlan,
        )

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["response_format"] is _TestPlan

    @patch("flo.llm.router.litellm.acompletion", new_callable=AsyncMock)
    @patch("flo.llm.router.litellm.completion_cost", return_value=0.0)
    async def test_invalid_json_raises(
        self, mock_cost: Any, mock_acompletion: AsyncMock, router: LLMRouter
    ) -> None:
        mock_acompletion.return_value = _mock_response(content="not json")

        with pytest.raises(pydantic.ValidationError):
            await router.complete_structured(
                task_type=TaskType.PLANNING,
                messages=MESSAGES,
                response_model=_TestPlan,
            )

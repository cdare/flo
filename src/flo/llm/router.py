from __future__ import annotations

from typing import TYPE_CHECKING, Any

import litellm
import structlog

from flo.llm.models import LLMResponse, TaskType, UsageStats

if TYPE_CHECKING:
    from pydantic import BaseModel

    from flo.config import Settings

log = structlog.get_logger(__name__)


class LLMRouter:
    """Routes LLM calls to cheap or premium models based on task type."""

    def __init__(self, settings: Settings) -> None:
        self._models: dict[TaskType, str] = {
            TaskType.EXECUTION: settings.cheap_model,
            TaskType.PLANNING: settings.premium_model,
        }

    def model_for(self, task_type: TaskType) -> str:
        """Return the model name for a given task type."""
        return self._models[task_type]

    async def complete(
        self,
        *,
        task_type: TaskType,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request to the appropriate model.

        Args:
            task_type: Determines which model tier to use.
            messages: OpenAI-format message list.
            temperature: Sampling temperature.
            max_tokens: Optional max tokens for the response.
            **kwargs: Additional litellm parameters.

        Returns:
            LLMResponse with content, usage stats, and model info.
        """
        model = self.model_for(task_type)
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        if tools is not None:
            from langchain_core.utils.function_calling import convert_to_openai_tool

            params["tools"] = [convert_to_openai_tool(t) for t in tools]
            params["tool_choice"] = "auto"

        log.debug(
            "llm.request", model=model, task_type=task_type, num_messages=len(messages)
        )

        response = await litellm.acompletion(**params)

        usage = self._extract_usage(response, model)
        content = response.choices[0].message.content or ""

        raw_tool_calls = None
        message = response.choices[0].message
        if hasattr(message, "tool_calls") and message.tool_calls:
            raw_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        log.info(
            "llm.response",
            model=model,
            task_type=task_type,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=f"${usage.cost_usd:.6f}",
        )

        return LLMResponse(
            content=content,
            model=model,
            task_type=task_type,
            usage=usage,
            tool_calls=raw_tool_calls,
        )

    async def complete_structured(
        self,
        *,
        task_type: TaskType,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> tuple[BaseModel, LLMResponse]:
        """Send a chat completion and parse the response into a Pydantic model.

        Uses litellm's response_format parameter with a JSON schema derived
        from the Pydantic model. Falls back to JSON-mode parsing if the
        provider doesn't support native structured output.

        Args:
            task_type: Determines which model tier to use.
            messages: OpenAI-format message list.
            response_model: Pydantic model class to parse into.
            temperature: Sampling temperature.
            max_tokens: Optional max tokens for the response.
            **kwargs: Additional litellm parameters.

        Returns:
            Tuple of (parsed Pydantic instance, LLMResponse metadata).
        """
        model = self.model_for(task_type)
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": response_model,
            **kwargs,
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens

        log.debug(
            "llm.structured_request",
            model=model,
            task_type=task_type,
            response_model=response_model.__name__,
        )

        response = await litellm.acompletion(**params)

        usage = self._extract_usage(response, model)
        raw_content = response.choices[0].message.content or ""

        parsed = response_model.model_validate_json(raw_content)

        llm_response = LLMResponse(
            content=raw_content,
            model=model,
            task_type=task_type,
            usage=usage,
        )

        log.info(
            "llm.structured_response",
            model=model,
            task_type=task_type,
            response_model=response_model.__name__,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

        return parsed, llm_response

    @staticmethod
    def _extract_usage(response: Any, model: str) -> UsageStats:
        """Extract token usage and cost from a litellm response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return UsageStats()

        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            cost = 0.0

        return UsageStats(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            cost_usd=cost,
        )

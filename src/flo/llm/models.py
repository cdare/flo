from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TaskType(StrEnum):
    """Classifies an LLM request for routing purposes."""

    EXECUTION = "execution"  # Simple tasks → cheap model
    PLANNING = "planning"  # Complex reasoning → premium model


@dataclass(frozen=True, slots=True)
class UsageStats:
    """Token usage and cost for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Wrapper around an LLM completion response."""

    content: str
    model: str
    task_type: TaskType
    usage: UsageStats = field(default_factory=UsageStats)

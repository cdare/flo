from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel

from flo.llm.models import TaskType  # noqa: TC001 - Pydantic needs this at runtime


class AgentState(TypedDict):
    """State schema for the agent graph."""

    messages: Annotated[list[dict[str, str]], operator.add]
    task_type: TaskType | None
    is_correction: bool
    plan: str | None
    response: str
    conversation_id: str
    user_id: str
    user_preferences: list[dict[str, Any]]


class Classification(BaseModel):
    """Structured LLM output for task classification."""

    task_type: TaskType
    is_correction: bool
    reasoning: str


class ExtractedPreference(BaseModel):
    """Structured LLM output for extracting a user preference from a correction."""

    preference: str
    reasoning: str

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel

from flo.llm.models import TaskType  # noqa: TC001 - Pydantic needs this at runtime


class AgentState(TypedDict):
    """State schema for the agent graph."""

    messages: Annotated[list[dict[str, str]], operator.add]
    task_type: TaskType | None
    plan: str | None
    response: str
    conversation_id: str


class Classification(BaseModel):
    """Structured LLM output for task classification."""

    task_type: TaskType
    reasoning: str

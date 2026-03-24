"""HTTP request/response models for the Flo server."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from any channel."""

    user_id: str = Field(min_length=1, description="Unique user identifier")
    conversation_id: str = Field(
        min_length=1, description="Conversation thread identifier"
    )
    message: str = Field(min_length=1, description="User message text")
    model_preference: Literal["fast", "premium"] | None = Field(
        default=None,
        description="Force model tier: 'fast' (cheap model) or 'premium'. Omit for auto.",
    )


class ChatResponse(BaseModel):
    """Agent response to a chat message."""

    response: str
    conversation_id: str

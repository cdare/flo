"""HTTP request/response models for the Flo server."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from any channel."""

    user_id: str = Field(min_length=1, description="Unique user identifier")
    conversation_id: str = Field(
        min_length=1, description="Conversation thread identifier"
    )
    message: str = Field(min_length=1, description="User message text")


class ChatResponse(BaseModel):
    """Agent response to a chat message."""

    response: str
    conversation_id: str

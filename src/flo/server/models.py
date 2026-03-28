"""HTTP request/response models for the Flo server."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from any channel."""

    user_id: str = Field(min_length=1, description="Unique user identifier")
    conversation_id: str = Field(
        min_length=1, description="Conversation thread identifier"
    )
    # max_length guards against unbounded LLM token spend (issue #9).
    # The hard cap here (32768) is a safety net; the operator-configurable
    # FLO_MAX_MESSAGE_LENGTH (default 4096) is enforced in the route handler.
    message: str = Field(
        min_length=1, max_length=32768, description="User message text"
    )


class ChatResponse(BaseModel):
    """Agent response to a chat message."""

    response: str
    conversation_id: str

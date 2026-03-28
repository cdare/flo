"""FastAPI route handlers for the Flo server."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, HTTPException, Request

from flo.server.models import ChatRequest, ChatResponse

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Route a chat message to the agent graph.

    Implements D2: extract IDs, construct state, call graph.ainvoke().
    The agent layer never knows about HTTP.
    """
    graph: CompiledStateGraph = request.app.state.graph
    settings = getattr(request.app.state, "settings", None)

    # Enforce configurable message length cap (issue #9)
    max_len = getattr(settings, "max_message_length", 4096)
    if len(req.message) > max_len:
        raise HTTPException(
            status_code=422,
            detail=f"Message exceeds maximum length of {max_len} characters",
        )

    # Prefix thread_id with user_id to prevent cross-user thread hijacking (issue #2).
    # A caller who guesses another user's conversation_id cannot load that thread
    # because the stored key incorporates the caller-supplied user_id.
    thread_id = f"{req.user_id}:{req.conversation_id}"

    state = {
        "messages": [{"role": "user", "content": req.message}],
        "task_type": None,
        "is_correction": False,
        "plan": None,
        "response": "",
        "conversation_id": req.conversation_id,
        "user_id": req.user_id,
        "user_preferences": [],
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(state, config=config)
    except Exception as exc:
        log.exception("agent.invoke_failed", conversation_id=req.conversation_id)
        is_dev = settings is not None and not settings.is_production
        detail = f"{type(exc).__name__}: {exc}" if is_dev else "Agent processing failed"
        raise HTTPException(status_code=502, detail=detail) from None

    return ChatResponse(
        response=result["response"],
        conversation_id=req.conversation_id,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}

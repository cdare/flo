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

    config = {"configurable": {"thread_id": req.conversation_id}}

    try:
        result = await graph.ainvoke(state, config=config)
    except Exception:
        log.exception("agent.invoke_failed", conversation_id=req.conversation_id)
        raise HTTPException(status_code=502, detail="Agent processing failed") from None

    return ChatResponse(
        response=result["response"],
        conversation_id=req.conversation_id,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}

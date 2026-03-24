"""Tests for the FastAPI server HTTP boundary (Phase 6).

Mock the graph, not the LLM. These tests verify the HTTP contract
(request validation, response shape, error mapping) — agent behavior
is tested in test_agent.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from flo.server.routes import router as chat_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph() -> MagicMock:
    """Graph mock that returns a successful agent response."""
    graph = MagicMock()
    graph.ainvoke = AsyncMock(
        return_value={"response": "Hello!", "messages": []},
    )
    return graph


@pytest.fixture
def app(mock_graph: MagicMock) -> FastAPI:
    """Create app with mock graph, bypassing lifespan."""
    app = FastAPI()
    app.include_router(chat_router)
    app.state.graph = mock_graph
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


VALID_CHAT_BODY = {
    "user_id": "user-1",
    "conversation_id": "conv-1",
    "message": "Hi there",
}


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    async def test_health_endpoint(self, client: AsyncClient) -> None:
        resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat endpoint — success
# ---------------------------------------------------------------------------


class TestChatEndpointSuccess:
    async def test_chat_endpoint_success(
        self,
        client: AsyncClient,
        mock_graph: MagicMock,
    ) -> None:
        resp = await client.post("/chat", json=VALID_CHAT_BODY)

        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "Hello!"
        mock_graph.ainvoke.assert_awaited_once()

    async def test_chat_response_contains_conversation_id(
        self,
        client: AsyncClient,
    ) -> None:
        resp = await client.post("/chat", json=VALID_CHAT_BODY)

        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "conv-1"


# ---------------------------------------------------------------------------
# Chat endpoint — validation errors (422)
# ---------------------------------------------------------------------------


class TestChatEndpointValidation:
    async def test_chat_endpoint_validation_error(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /chat with empty message returns 422."""
        body = {**VALID_CHAT_BODY, "message": ""}
        resp = await client.post("/chat", json=body)

        assert resp.status_code == 422

    async def test_chat_endpoint_missing_fields(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /chat with missing user_id returns 422."""
        body = {"conversation_id": "conv-1", "message": "Hi"}
        resp = await client.post("/chat", json=body)

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Chat endpoint — agent failure (502)
# ---------------------------------------------------------------------------


class TestChatEndpointAgentFailure:
    async def test_chat_endpoint_agent_failure(
        self,
        client: AsyncClient,
        mock_graph: MagicMock,
    ) -> None:
        """POST /chat returns 502 when graph.ainvoke raises."""
        mock_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("LLM provider down"),
        )

        resp = await client.post("/chat", json=VALID_CHAT_BODY)

        assert resp.status_code == 502
        assert "Agent processing failed" in resp.json()["detail"]

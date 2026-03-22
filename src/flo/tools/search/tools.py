"""Web search tool functions (factory/closure DI)."""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog
from langchain_core.tools import BaseTool, tool

log = structlog.get_logger(__name__)


class SearchProvider(Protocol):
    """Interface for swappable search providers."""

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Execute a web search and return results."""
        ...


class TavilyProvider:
    """Tavily search API provider."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.BASE_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict[str, str]] = []
        if data.get("answer"):
            results.append({"title": "AI Answer", "url": "", "content": data["answer"]})
        for item in data.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
            )
        return results[:max_results]


class SerpAPIProvider:
    """SerpAPI search provider."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.BASE_URL,
                params={
                    "api_key": self._api_key,
                    "q": query,
                    "num": max_results,
                    "engine": "google",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict[str, str]] = []
        for item in data.get("organic_results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "content": item.get("snippet", ""),
                }
            )
        return results[:max_results]


def make_search_provider(provider_name: str, api_key: str) -> SearchProvider:
    """Create a search provider by name. Pure factory — no global state."""
    providers: dict[str, type[TavilyProvider | SerpAPIProvider]] = {
        "tavily": TavilyProvider,
        "serpapi": SerpAPIProvider,
    }
    cls = providers.get(provider_name)
    if cls is None:
        msg = f"Unknown search provider: {provider_name}. Available: {list(providers)}"
        raise ValueError(msg)
    return cls(api_key)


def create_search_tools(provider: SearchProvider) -> list[BaseTool]:
    """Create web search tool functions with injected provider.

    Args:
        provider: A SearchProvider instance (Tavily, SerpAPI, or mock).

    Returns:
        List of LangChain BaseTool instances.
    """

    @tool
    async def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Search the web for information.

        Args:
            query: The search query.
            max_results: Maximum number of results to return (default 5).
        """
        log.info("tool.web_search", query=query, max_results=max_results)
        return await provider.search(query, max_results)

    return [web_search]

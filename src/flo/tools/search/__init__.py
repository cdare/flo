"""Web search skill."""

from __future__ import annotations

from flo.tools.base import Skill
from flo.tools.search.tools import SearchProvider, create_search_tools

SEARCH_SYSTEM_PROMPT = (
    "You have access to web search. "
    "Use this when the user asks a question you don't know the answer to, "
    "needs current information, or asks you to look something up. "
    "Cite sources when providing search results."
)


def create_search_skill(provider: SearchProvider) -> Skill:
    """Create a Search skill with injected provider."""
    return Skill(
        name="search",
        description=(
            "Search the web for current information, news, facts, and research."
        ),
        tools=create_search_tools(provider),
        system_prompt=SEARCH_SYSTEM_PROMPT,
    )

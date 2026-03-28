"""Gmail skill."""

from __future__ import annotations

from typing import Any

from flo.tools.base import Skill
from flo.tools.gmail.tools import create_gmail_tools

GMAIL_SYSTEM_PROMPT = (
    "You have access to Gmail tools. "
    "When the user asks about their email, use these tools to help them. "
    "For sending emails, always confirm the recipient and content with the "
    "user before sending. Summarize long emails concisely."
)


def create_gmail_skill(service: Any, allowed_domains: list[str] | None = None) -> Skill:
    """Create a Gmail skill with injected Google service.

    Args:
        service: Gmail API service resource.
        allowed_domains: Optional allowlist of permitted recipient domains for
            send_email (issue #5). Empty/None means all domains are permitted.
    """
    return Skill(
        name="gmail",
        description="Read, search, and send emails via Gmail.",
        tools=create_gmail_tools(service, allowed_domains),
        system_prompt=GMAIL_SYSTEM_PROMPT,
    )

"""Google Calendar skill."""

from __future__ import annotations

from typing import Any

from flo.tools.base import Skill
from flo.tools.calendar.tools import create_calendar_tools

CALENDAR_SYSTEM_PROMPT = (
    "You have access to Google Calendar tools. "
    "When the user asks about their schedule, meetings, or events, "
    "use these tools to help them. Always confirm times and details "
    "before creating events. Format dates and times clearly for the user."
)


def create_calendar_skill(service: Any) -> Skill:
    """Create a Calendar skill with injected Google service."""
    return Skill(
        name="calendar",
        description=(
            "Manage Google Calendar events — list, create, update, and delete events."
        ),
        tools=create_calendar_tools(service),
        system_prompt=CALENDAR_SYSTEM_PROMPT,
    )

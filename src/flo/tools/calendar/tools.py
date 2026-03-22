"""Google Calendar tool functions (factory/closure DI)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.tools import BaseTool, tool

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def create_calendar_tools(service: Any) -> list[BaseTool]:
    """Create Google Calendar tool functions with injected service.

    The service is captured in closures — no module-level globals.
    For testing, pass a mock service.

    Args:
        service: Google Calendar API service resource.

    Returns:
        List of LangChain BaseTool instances.
    """

    @tool
    def list_events(
        max_results: int = 10,
        time_min: str | None = None,
    ) -> list[dict[str, Any]]:
        """List upcoming Google Calendar events.

        Args:
            max_results: Maximum number of events to return (default 10).
            time_min: ISO datetime string for earliest event. Defaults to now.
        """
        if time_min is None:
            time_min = datetime.now(UTC).isoformat()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = result.get("items", [])
        return [
            {
                "id": e["id"],
                "summary": e.get("summary", ""),
                "start": e.get("start", {}).get(
                    "dateTime", e.get("start", {}).get("date", "")
                ),
                "end": e.get("end", {}).get(
                    "dateTime", e.get("end", {}).get("date", "")
                ),
            }
            for e in events
        ]

    @tool
    def create_event(
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        """Create a new Google Calendar event.

        Args:
            summary: Event title.
            start_time: ISO datetime string for event start.
            end_time: ISO datetime string for event end.
            description: Optional event description.
            location: Optional event location.
        """
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        return service.events().insert(calendarId="primary", body=body).execute()

    @tool
    def update_event(
        event_id: str,
        summary: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing Google Calendar event.

        Args:
            event_id: The event ID to update.
            summary: New event title (optional).
            start_time: New start time as ISO datetime (optional).
            end_time: New end time as ISO datetime (optional).
            description: New description (optional).
            location: New location (optional).
        """
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        if summary is not None:
            event["summary"] = summary
        if start_time is not None:
            event["start"] = {"dateTime": start_time, "timeZone": "UTC"}
        if end_time is not None:
            event["end"] = {"dateTime": end_time, "timeZone": "UTC"}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        return (
            service.events()
            .update(calendarId="primary", eventId=event_id, body=event)
            .execute()
        )

    @tool
    def delete_event(event_id: str) -> str:
        """Delete a Google Calendar event.

        Args:
            event_id: The event ID to delete.
        """
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return f"Event {event_id} deleted."

    return [list_events, create_event, update_event, delete_event]

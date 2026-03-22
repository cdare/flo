"""Gmail tool functions (factory/closure DI)."""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from langchain_core.tools import BaseTool, tool

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def create_gmail_tools(service: Any) -> list[BaseTool]:
    """Create Gmail tool functions with injected service.

    Args:
        service: Gmail API service resource.

    Returns:
        List of LangChain BaseTool instances.
    """

    def _list_emails(max_results: int = 10, query: str = "") -> list[dict[str, str]]:
        """Shared email listing logic (private, not a tool)."""
        params: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
            "labelIds": ["INBOX"],
        }
        if query:
            params["q"] = query
        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])

        summaries = []
        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata")
                .execute()
            )
            headers = {
                h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
            }
            summaries.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                }
            )
        return summaries

    @tool
    def list_emails(max_results: int = 10, query: str = "") -> list[dict[str, str]]:
        """List recent emails from Gmail inbox.

        Args:
            max_results: Maximum number of emails to return (default 10).
            query: Gmail search query (e.g., "from:alice subject:meeting").
        """
        return _list_emails(max_results=max_results, query=query)

    @tool
    def read_email(message_id: str) -> dict[str, str]:
        """Read a specific email by message ID.

        Args:
            message_id: The Gmail message ID.
        """
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {
            h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
        }

        body = ""
        payload = msg.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get(
                    "data"
                ):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
                    break

        return {
            "id": msg["id"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    @tool
    def send_email(to: str, subject: str, body: str) -> dict[str, str]:
        """Send an email via Gmail.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body text (plain text).
        """
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = (
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
        )
        return {"id": result["id"], "status": "sent"}

    @tool
    def search_emails(query: str, max_results: int = 10) -> list[dict[str, str]]:
        """Search Gmail with a query string.

        Args:
            query: Gmail search query (e.g., "from:alice has:attachment").
            max_results: Maximum number of results (default 10).
        """
        return _list_emails(max_results=max_results, query=query)

    return [list_emails, read_email, send_email, search_emails]

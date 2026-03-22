"""Skill dataclass, SkillRegistry, and credential helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from flo.llm.models import TaskType


@dataclass(frozen=True, slots=True)
class Skill:
    """A self-contained capability with tools and prompt context."""

    name: str
    description: str
    tools: list[BaseTool] = field(default_factory=list)
    system_prompt: str = ""
    task_type_override: TaskType | None = None


class SkillRegistry:
    """Registry for looking up skills by name."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_all(self) -> list[Skill]:
        return list(self._skills.values())

    def get_descriptions(self) -> list[dict[str, str]]:
        """Return name+description pairs for LLM skill selection."""
        return [
            {"name": s.name, "description": s.description}
            for s in self._skills.values()
        ]


def load_or_refresh_credentials(
    credentials_path: str,
    token_path: str,
    scopes: list[str],
) -> Any:
    """Load or refresh Google OAuth2 credentials.

    Handles file I/O and the OAuth interactive flow. Separated from
    service construction so each concern is independently testable.

    Args:
        credentials_path: Path to OAuth2 client credentials JSON.
        token_path: Path to stored token JSON.
        scopes: OAuth2 scopes required.

    Returns:
        google.oauth2.credentials.Credentials instance.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Credentials | None = None
    token_file = Path(token_path)

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    return creds


def build_google_service(
    credentials: Any,
    service_name: str,
    version: str,
) -> Any:
    """Build a Google API service client from pre-loaded credentials.

    Pure construction — no file I/O, no token refresh.

    Args:
        credentials: google.oauth2.credentials.Credentials instance.
        service_name: Google API service name (e.g., "calendar", "gmail").
        version: API version (e.g., "v3", "v1").

    Returns:
        Google API service resource.
    """
    from googleapiclient.discovery import build

    return build(service_name, version, credentials=credentials)

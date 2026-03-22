"""Flo tools module — skill registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flo.tools.base import Skill, SkillRegistry

if TYPE_CHECKING:
    from flo.config import Settings

_registry = SkillRegistry()


def register_skills(settings: Settings) -> None:
    """Register skills with injected services. Called during app startup.

    This replaces module-level registration — skills require services
    that aren't available at import time.
    """
    from flo.tools.base import build_google_service, load_or_refresh_credentials
    from flo.tools.calendar import create_calendar_skill
    from flo.tools.gmail import create_gmail_skill

    creds = load_or_refresh_credentials(
        settings.google_credentials_path,
        settings.google_token_path,
        scopes=[
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
    )
    cal_service = build_google_service(creds, "calendar", "v3")
    gmail_service = build_google_service(creds, "gmail", "v1")

    _registry.register(create_calendar_skill(cal_service))
    _registry.register(create_gmail_skill(gmail_service))

    if settings.search_api_key:
        from flo.tools.search import create_search_skill
        from flo.tools.search.tools import make_search_provider

        provider = make_search_provider(
            settings.search_provider, settings.search_api_key
        )
        _registry.register(create_search_skill(provider))


def register_skill(skill: Skill) -> None:
    """Register a single skill (for testing)."""
    _registry.register(skill)


def get_skill(name: str) -> Skill | None:
    """Look up a skill by name."""
    return _registry.get(name)


def get_all_skills() -> list[Skill]:
    """Return all registered skills."""
    return _registry.get_all()


def get_skill_descriptions() -> list[dict[str, str]]:
    """Return name+description pairs for all skills (for LLM classification)."""
    return _registry.get_descriptions()


__all__ = [
    "Skill",
    "SkillRegistry",
    "get_all_skills",
    "get_skill",
    "get_skill_descriptions",
    "register_skill",
    "register_skills",
]

from __future__ import annotations


def test_import_flo() -> None:
    """Verify the flo package is importable."""
    import flo

    assert flo is not None


def test_import_subpackages() -> None:
    """Verify all sub-packages are importable."""
    import flo.agent
    import flo.integrations
    import flo.llm
    import flo.server
    import flo.tools

    assert all(
        m is not None
        for m in [flo.llm, flo.agent, flo.tools, flo.server, flo.integrations]
    )


def test_config_defaults(settings) -> None:
    """Verify config loads with defaults."""
    assert settings.env == "testing"
    assert settings.port == 8000
    assert settings.host == "0.0.0.0"
    assert settings.cheap_model == "test-cheap-model"


def test_config_is_production(settings) -> None:
    """Verify is_production property."""
    assert not settings.is_production


def test_setup_logging() -> None:
    """Verify structured logging can be configured without error."""
    from flo.log import get_logger, setup_logging

    setup_logging(log_level="debug", env="development")
    logger = get_logger("test")
    assert logger is not None

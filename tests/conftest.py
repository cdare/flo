from __future__ import annotations

try:
    import flo  # noqa: F401
except ImportError as err:
    raise RuntimeError("Run 'make install-dev' before running tests") from err

import pytest

from flo.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Test settings with safe defaults."""
    return Settings(
        env="testing",
        log_level="debug",
        cheap_model="test-cheap-model",
        premium_model="test-premium-model",
    )

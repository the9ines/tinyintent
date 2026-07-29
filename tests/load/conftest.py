"""
Pytest configuration for load tests.

This allows running load test assertions with pytest.
"""

import os
import pytest


def pytest_configure(config):
    """Configure pytest for load testing."""
    config.addinivalue_line(
        "markers", "load: mark test as a load test"
    )
    config.addinivalue_line(
        "markers", "stress: mark test as a stress test"
    )


@pytest.fixture
def base_url():
    """Get the base URL for API testing."""
    return os.getenv("TINYINTENT_URL", "http://localhost:8787")


@pytest.fixture
def auth_headers():
    """Get authentication headers."""
    return {
        "X-Shortcut-Token": os.getenv("SHORTCUT_TOKEN", "test-token"),
        "X-TinyIntent-Secret": os.getenv("TINYINTENT_SECRET", "test-secret"),
        "Content-Type": "application/json"
    }

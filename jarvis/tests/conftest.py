"""Pytest configuration for Jarvis."""

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue("markers", "asyncio: mark test as async")

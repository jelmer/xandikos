"""General-purpose fixtures for xandikos's testsuite."""

from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def setup_logging():
    """Configure logging for tests, hiding DEBUG output from dulwich."""
    # Hide DEBUG logging from dulwich to reduce noise in test output
    logging.getLogger("dulwich").setLevel(logging.WARNING)

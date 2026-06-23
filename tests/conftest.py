# tests/conftest.py
"""
Test configuration and fixtures for StratOS.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stratos.api.main import app


@pytest.fixture
def client():
    """Get a synchronous test client for the API."""
    with TestClient(app) as client:
        yield client
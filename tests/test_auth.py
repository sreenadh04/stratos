# tests/test_auth.py
"""
Tests for API authentication.
"""
import pytest
from stratos.config import settings


def test_auth_required_for_runs(client):
    """Test that /runs requires authentication."""
    response = client.get("/runs")
    assert response.status_code == 401
    assert "API key required" in response.text


def test_auth_required_for_signals(client):
    """Test that /runs/{id}/signals requires authentication."""
    response = client.get("/runs/123/signals")
    assert response.status_code == 401


def test_valid_api_key_works(client):
    """Test that valid API key grants access."""
    if not settings.api_key:
        pytest.skip("No API key configured")
    headers = {"X-API-Key": settings.api_key}
    response = client.get("/runs", headers=headers)
    # May return 200 or 500 if no runs exist, but not 401
    assert response.status_code != 401


def test_invalid_api_key_fails(client):
    """Test that invalid API key is rejected."""
    headers = {"X-API-Key": "invalid_key_123"}
    response = client.get("/runs", headers=headers)
    assert response.status_code == 401
    assert "Invalid API key" in response.text
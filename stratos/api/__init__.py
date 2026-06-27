# stratos/api/__init__.py
"""
API package for StratOS.
Contains FastAPI app, authentication, and dashboard rendering.
"""
from stratos.api.main import app
from stratos.api.auth import (
    validate_api_key,
    optional_api_key,
    setup_cors,
    create_api_key,
    revoke_api_key,
    log_api_action,
    _api_keys,
)
from stratos.api.dashboard import render_dashboard

__all__ = [
    "app",
    "validate_api_key",
    "optional_api_key",
    "setup_cors",
    "create_api_key",
    "revoke_api_key",
    "log_api_action",
    "_api_keys",
    "render_dashboard",
]
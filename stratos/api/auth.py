# stratos/api/auth.py
"""
API Authentication and Security utilities.
Provides API key validation, rate limiting, and security headers.
"""
import secrets
from fastapi import Security, HTTPException, Header, Request, status
from fastapi.security import APIKeyHeader
from typing import Optional
from stratos.config import settings
from stratos.logging_config import get_logger

logger = get_logger("auth")

# API Key header name
API_KEY_HEADER = "X-API-Key"

# Create security scheme
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def validate_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> str:
    """
    Validate the API key from the request header.
    
    Args:
        api_key: The API key from the header
    
    Returns:
        The validated API key
    
    Raises:
        HTTPException: If API key is missing or invalid
    """
    # For development, skip validation if no API key is set
    if not hasattr(settings, "api_key") or not settings.api_key:
        logger.warning("⚠️ No API key configured - skipping authentication")
        return "development"
    
    if not api_key:
        logger.warning("❌ API key missing in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "APIKey"},
        )
    
    # Validate the API key using constant-time comparison
    if not secrets.compare_digest(api_key, settings.api_key):
        logger.warning(f"❌ Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "APIKey"},
        )
    
    logger.info(f"✅ API key validated")
    return api_key


async def optional_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Optional API key validation (does not raise error if missing).
    Used for public endpoints like health check.
    """
    if not api_key:
        return None
    
    if not hasattr(settings, "api_key") or not settings.api_key:
        return "development"
    
    if secrets.compare_digest(api_key, settings.api_key):
        return api_key
    
    return None


def get_rate_limit_key(request: Request) -> str:
    """
    Generate a rate limit key based on client IP and API key.
    """
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Get API key if present
    api_key = request.headers.get(API_KEY_HEADER, "none")
    
    return f"ratelimit:{api_key}:{client_ip}"
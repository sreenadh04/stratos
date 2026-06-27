# stratos/api/auth.py
"""
API Authentication and Security utilities.
Provides API key validation, rate limiting, rotation, CORS, and audit logging.
"""
import secrets
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import Security, HTTPException, Header, Request, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from stratos.config import settings
from stratos.logging_config import get_logger, audit_logger

logger = get_logger("auth")

# API Key header name
API_KEY_HEADER = "X-API-Key"

# Create security scheme
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


# ============================================================
# #31: RATE LIMITING
# ============================================================
# Simple in-memory rate limiter
# In production, use Redis or a distributed cache
_rate_limit_store: Dict[str, Dict[str, Any]] = {}


def get_rate_limit_key(request: Request, api_key: str = "anonymous") -> str:
    """
    Generate a rate limit key based on client IP and API key.
    """
    client_ip = request.client.host if request.client else "unknown"
    return f"ratelimit:{api_key}:{client_ip}"


async def check_rate_limit(
    request: Request,
    api_key: str = "anonymous",
    limit: int = 30,
    window: int = 60,
) -> bool:
    """
    Check if request is within rate limit.
    
    Args:
        request: FastAPI request object
        api_key: API key (or "anonymous")
        limit: Max requests per window
        window: Time window in seconds
    
    Returns:
        True if within limit, False if exceeded
    """
    key = get_rate_limit_key(request, api_key)
    current_time = time.time()
    
    # Get existing data
    data = _rate_limit_store.get(key, {"requests": [], "limit": limit, "window": window})
    
    # Clean old requests
    data["requests"] = [t for t in data["requests"] if current_time - t < window]
    
    # Check limit
    if len(data["requests"]) >= limit:
        return False
    
    # Add current request
    data["requests"].append(current_time)
    _rate_limit_store[key] = data
    
    return True


# ============================================================
# #34: API KEY ROTATION
# ============================================================
# In-memory key store
# In production, store in database with user association
_api_keys: Dict[str, Dict[str, Any]] = {}


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


async def create_api_key(user_id: str = "default") -> str:
    """
    Create a new API key for a user.
    """
    key = generate_api_key()
    _api_keys[key] = {
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "is_active": True,
    }
    logger.info(f"API key created for user: {user_id}")
    return key


async def revoke_api_key(api_key: str) -> bool:
    """
    Revoke an API key.
    """
    if api_key in _api_keys:
        _api_keys[api_key]["is_active"] = False
        logger.info(f"API key revoked: {api_key[:8]}...")
        return True
    return False


async def validate_api_key_from_store(api_key: str) -> bool:
    """
    Validate API key from store.
    """
    if not api_key:
        return False
    key_data = _api_keys.get(api_key)
    if not key_data:
        return False
    if not key_data.get("is_active", True):
        return False
    # Update last used
    key_data["last_used"] = datetime.now(timezone.utc).isoformat()
    return True


# ============================================================
# #36: AUDIT LOGGING FOR API
# ============================================================
async def log_api_action(
    request: Request,
    action: str,
    api_key: str = None,
    resource_id: str = None,
    resource_type: str = None,
    details: Dict[str, Any] = None,
    success: bool = True,
    error_message: str = None,
):
    """
    Log API actions for audit trail.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    audit_logger.log(
        action=action,
        user_id=api_key,
        resource_id=resource_id,
        resource_type=resource_type,
        details=details,
        success=success,
        error_message=error_message,
        ip_address=client_ip,
        user_agent=user_agent,
    )


# ============================================================
# MAIN VALIDATION FUNCTION
# ============================================================
async def validate_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """
    Validate the API key from the request header.
    Includes rate limiting and audit logging.
    """
    # For development, skip validation if no API key is set
    if not hasattr(settings, "api_key") or not settings.api_key:
        logger.warning("⚠️ No API key configured - skipping authentication")
        await log_api_action(request, "SKIP_AUTH", api_key="development")
        return "development"
    
    if not api_key:
        logger.warning("❌ API key missing in request")
        await log_api_action(
            request,
            "AUTH_FAILED",
            success=False,
            error_message="API key missing"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "APIKey"},
        )
    
    # #34: Check if key is valid and active
    is_valid = await validate_api_key_from_store(api_key)
    
    # Also check static config key for backward compatibility
    if not is_valid and hasattr(settings, "api_key"):
        is_valid = secrets.compare_digest(api_key, settings.api_key)
    
    if not is_valid:
        logger.warning(f"❌ Invalid API key attempt: {api_key[:8]}...")
        await log_api_action(
            request,
            "AUTH_FAILED",
            api_key=api_key[:8],
            success=False,
            error_message="Invalid API key"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "APIKey"},
        )
    
    # #31: Rate limiting
    rate_limit = getattr(settings, "rate_limit_per_minute", 30)
    within_limit = await check_rate_limit(request, api_key, limit=rate_limit)
    
    if not within_limit:
        logger.warning(f"⚠️ Rate limit exceeded for: {api_key[:8]}...")
        await log_api_action(
            request,
            "RATE_LIMIT_EXCEEDED",
            api_key=api_key[:8],
            success=False,
            error_message="Rate limit exceeded"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {rate_limit} requests per minute.",
        )
    
    await log_api_action(
        request,
        "AUTH_SUCCESS",
        api_key=api_key[:8],
        success=True
    )
    
    logger.info(f"✅ API key validated: {api_key[:8]}...")
    return api_key


async def optional_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
) -> Optional[str]:
    """
    Optional API key validation (does not raise error if missing).
    Used for public endpoints like health check.
    """
    if not api_key:
        return None
    
    # Check if valid
    is_valid = await validate_api_key_from_store(api_key)
    if not is_valid and hasattr(settings, "api_key"):
        is_valid = secrets.compare_digest(api_key, settings.api_key)
    
    if is_valid:
        await log_api_action(
            request,
            "OPTIONAL_AUTH_SUCCESS",
            api_key=api_key[:8],
            success=True
        )
        return api_key
    
    return None


# ============================================================
# #35: CORS CONFIGURATION
# ============================================================
def setup_cors(app):
    """
    Setup CORS middleware for the FastAPI app.
    """
    # Get allowed origins from settings or use default
    allowed_origins = getattr(
        settings,
        "cors_allowed_origins",
        [
            "http://localhost:3000",
            "http://localhost:8000",
            "https://stratos-vtya.onrender.com",
        ]
    )
    
    # If in production, only allow specific origins
    if settings.is_production:
        allowed_origins = [origin for origin in allowed_origins if not origin.startswith("http://localhost")]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Accept", "Authorization"],
        expose_headers=["X-API-Key"],
        max_age=86400,  # 24 hours
    )
    
    logger.info(f"✅ CORS configured with origins: {allowed_origins}")


# ============================================================
# API KEY MANAGEMENT ENDPOINTS (to be added to main.py)
# ============================================================
# These endpoints should be added to api/main.py
#
# @app.post("/api-keys/create")
# async def create_api_key_endpoint():
#     """Create a new API key."""
#     key = await create_api_key()
#     return {"api_key": key, "message": "Store this key securely. It will not be shown again."}
#
# @app.post("/api-keys/revoke")
# async def revoke_api_key_endpoint(api_key: str):
#     """Revoke an API key."""
#     success = await revoke_api_key(api_key)
#     if success:
#         return {"message": "API key revoked successfully"}
#     return {"message": "API key not found"}, 404
#
# @app.get("/api-keys/list")
# async def list_api_keys_endpoint():
#     """List all active API keys."""
#     active_keys = [k for k, v in _api_keys.items() if v.get("is_active", True)]
#     return {"keys": active_keys}
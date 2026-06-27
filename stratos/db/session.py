# stratos/db/session.py
"""
Async database session management using SQLAlchemy.
Provides connection pooling and session lifecycle management.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from stratos.config import settings
import os


def get_async_database_url():
    """Convert sync database URL to async URL."""
    url = settings.database_url
    
    # Convert to async
    if "postgresql://" in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    
    # Remove sslmode if present
    if "sslmode=" in url:
        parts = url.split("?")
        if len(parts) > 1:
            params = [p for p in parts[1].split("&") if not p.startswith("sslmode=")]
            url = parts[0] + ("?" + "&".join(params) if params else "")
    
    return url


# Create async engine with NullPool to avoid loop issues
engine = create_async_engine(
    get_async_database_url(),
    echo=False,
    poolclass=NullPool,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        "server_settings": {
            "application_name": "stratos",
        },
        "timeout": 10,  # Connection timeout
    }
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def get_db_session_manual():
    """Get a session for manual use (outside FastAPI)."""
    return AsyncSessionLocal()
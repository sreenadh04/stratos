# scripts/init_db.py
"""
Initialize the database schema.
Creates all tables defined in SQLAlchemy models.
"""
import os
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from stratos.db.models import Base


def clean_database_url(url: str) -> str:
    """Remove sslmode parameter from database URL if present."""
    if "sslmode=" in url:
        parts = url.split("?")
        if len(parts) > 1:
            params = [p for p in parts[1].split("&") if not p.startswith("sslmode=")]
            return parts[0] + ("?" + "&".join(params) if params else "")
    return url


async def init_db():
    """Initialize database with all tables."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ Error: DATABASE_URL not found in .env")
        return False
    
    # Clean and convert to async URL
    cleaned_url = clean_database_url(database_url)
    async_url = cleaned_url.replace("postgresql://", "postgresql+asyncpg://")
    
    try:
        # Create engine
        engine = create_async_engine(async_url, echo=True)
        
        # Create all tables
        async with engine.begin() as conn:
            print("📋 Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Tables created successfully")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False


async def main():
    print("=" * 50)
    print("  StratOS - Database Initialization")
    print("=" * 50)
    
    success = await init_db()
    
    if success:
        print("\n✅ Database initialization complete.")
        print("📋 Next steps:")
        print("  1. Run: python scripts/seed_competitors.py")
        print("  2. Start the API: uvicorn stratos.api.main:app --reload")
    else:
        print("\n❌ Database initialization failed. Check your DATABASE_URL.")
        print("   Make sure PostgreSQL is running and accessible.")


if __name__ == "__main__":
    asyncio.run(main())
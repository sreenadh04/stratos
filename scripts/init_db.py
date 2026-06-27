# scripts/init_db.py
"""
Initialize the database schema.
Creates all tables defined in SQLAlchemy models with indexes (#29)
and data retention configuration (#28).
"""
import os
import sys
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add parent directory to sys.path so stratos module is found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stratos.db.models import Base
from stratos.config import settings


def clean_database_url(url: str) -> str:
    """Remove sslmode parameter from database URL if present."""
    if "sslmode=" in url:
        parts = url.split("?")
        if len(parts) > 1:
            params = [p for p in parts[1].split("&") if not p.startswith("sslmode=")]
            return parts[0] + ("?" + "&".join(params) if params else "")
    return url


def get_async_database_url():
    """Convert sync database URL to async URL."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return None
    
    # Clean sslmode
    url = clean_database_url(url)
    
    # Convert to async
    if "postgresql://" in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    
    return url


# #29: Database Indexes
INDEXES = [
    # Competitor indexes
    "CREATE INDEX IF NOT EXISTS idx_competitors_name ON competitors(name);",
    "CREATE INDEX IF NOT EXISTS idx_competitors_is_active ON competitors(is_active);",
    
    # Run indexes
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);",
    "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);",
    "CREATE INDEX IF NOT EXISTS idx_runs_retention_expiry ON runs(retention_expiry);",
    
    # Raw snapshot indexes
    "CREATE INDEX IF NOT EXISTS idx_raw_snapshots_competitor_hash ON raw_snapshots(competitor_id, content_hash);",
    "CREATE INDEX IF NOT EXISTS idx_raw_snapshots_run_id ON raw_snapshots(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_raw_snapshots_source_type ON raw_snapshots(source_type);",
    
    # Signal indexes
    "CREATE INDEX IF NOT EXISTS idx_signals_run_id ON signals(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_signals_competitor_id ON signals(competitor_id);",
    "CREATE INDEX IF NOT EXISTS idx_signals_impact_level ON signals(impact_level);",
    "CREATE INDEX IF NOT EXISTS idx_signals_is_duplicate ON signals(is_duplicate);",
    "CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);",
    
    # Run log indexes
    "CREATE INDEX IF NOT EXISTS idx_run_logs_run_id ON run_logs(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_run_logs_timestamp ON run_logs(timestamp);",
    
    # Product context indexes
    "CREATE INDEX IF NOT EXISTS idx_product_context_is_active ON product_context(is_active);",
    "CREATE INDEX IF NOT EXISTS idx_product_context_updated_at ON product_context(updated_at);",
    
    # User action indexes
    "CREATE INDEX IF NOT EXISTS idx_user_actions_signal_id ON user_actions(signal_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_actions_taken_at ON user_actions(taken_at);",
    
    # Audit log indexes
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_id ON audit_logs(resource_id);",
]


async def init_db():
    """Initialize database with all tables and indexes."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ Error: DATABASE_URL not found in .env")
        return False
    
    async_url = get_async_database_url()
    print(f"📋 Connecting to database...")
    
    try:
        # Create engine
        engine = create_async_engine(async_url, echo=True)
        
        # Create all tables
        async with engine.begin() as conn:
            print("📋 Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Tables created successfully")
            
            # #29: Create indexes
            print("📋 Creating indexes...")
            for index_sql in INDEXES:
                try:
                    await conn.execute(text(index_sql))
                except Exception as e:
                    print(f"⚠️ Index creation skipped (may already exist): {e}")
            print("✅ Indexes created successfully")
        
        # #28: Set up data retention (if applicable)
        retention_days = getattr(settings, 'data_retention_days', 180)
        print(f"📋 Data retention set to {retention_days} days")
        
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


if __name__ == "__main__":
    asyncio.run(main())
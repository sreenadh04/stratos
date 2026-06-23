# scripts/seed_competitors.py
"""
Seed the database with initial competitors.
Uses async SQLAlchemy for database operations.
"""
import os
import asyncio
import uuid
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from stratos.db.models import Competitor


def clean_database_url(url: str) -> str:
    """Remove sslmode parameter from database URL if present."""
    if "sslmode=" in url:
        parts = url.split("?")
        if len(parts) > 1:
            params = [p for p in parts[1].split("&") if not p.startswith("sslmode=")]
            return parts[0] + ("?" + "&".join(params) if params else "")
    return url


async def seed_competitors():
    """Seed competitors into the database."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ Error: DATABASE_URL not found in .env")
        return False
    
    # Clean and convert to async URL
    cleaned_url = clean_database_url(database_url)
    async_url = cleaned_url.replace("postgresql://", "postgresql+asyncpg://")
    
    competitors = [
        {
            "name": "OpenAI",
            "website_url": "https://openai.com",
            "blog_url": "https://openai.com/blog"
        },
        {
            "name": "Anthropic",
            "website_url": "https://anthropic.com",
            "blog_url": "https://www.anthropic.com/news"
        },
        {
            "name": "Cohere",
            "website_url": "https://cohere.com",
            "blog_url": "https://cohere.com/blog"
        }
    ]
    
    try:
        # Create engine
        engine = create_async_engine(async_url, echo=False)
        AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        
        async with AsyncSessionLocal() as session:
            # Check if competitors already exist
            for comp in competitors:
                # Check if exists
                result = await session.execute(
                    text("SELECT id FROM competitors WHERE name = :name"),
                    {"name": comp["name"]}
                )
                existing = result.fetchone()
                
                if existing:
                    print(f"⏭️  Skipped (already exists): {comp['name']}")
                    continue
                
                # Create new competitor
                competitor = Competitor(
                    id=str(uuid.uuid4()),
                    name=comp["name"],
                    website_url=comp["website_url"],
                    blog_url=comp["blog_url"],
                )
                session.add(competitor)
                print(f"✅ Seeded: {comp['name']}")
            
            await session.commit()
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        return False


async def main():
    print("=" * 50)
    print("  StratOS - Seed Competitors")
    print("=" * 50)
    
    success = await seed_competitors()
    
    if success:
        print("\n✅ Seeding complete.")
    else:
        print("\n❌ Seeding failed.")


if __name__ == "__main__":
    asyncio.run(main())
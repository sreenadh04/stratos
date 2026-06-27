# scripts/seed_competitors.py
"""
Seed the database with initial competitors.
"""
import os
import sys
import asyncio
import uuid
from dotenv import load_dotenv

# Add parent directory to sys.path so stratos module is found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stratos.db.models import Competitor
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import CompetitorRepository
from stratos.logging_config import get_logger

logger = get_logger("seed")


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
    
    competitors = [
        {
            "name": "OpenAI",
            "website_url": "https://openai.com",
            "blog_url": "https://openai.com/blog",
            "source_type": "blog"
        },
        {
            "name": "Anthropic",
            "website_url": "https://anthropic.com",
            "blog_url": "https://www.anthropic.com/news",
            "source_type": "blog"
        },
        {
            "name": "Cohere",
            "website_url": "https://cohere.com",
            "blog_url": "https://cohere.com/blog",
            "source_type": "blog"
        }
    ]
    
    try:
        async with get_db_session_manual() as session:
            repo = CompetitorRepository(session)
            
            for comp in competitors:
                # Check if exists
                existing = await repo.get_by_name(comp["name"])
                if existing:
                    print(f"⏭️  Skipped (already exists): {comp['name']}")
                    continue
                
                # Create new competitor
                competitor = Competitor(
                    id=str(uuid.uuid4()),
                    name=comp["name"],
                    website_url=comp["website_url"],
                    blog_url=comp["blog_url"],
                    is_active=True,
                )
                session.add(competitor)
                print(f"✅ Seeded: {comp['name']}")
            
            await session.commit()
        
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
import os
import uuid
import psycopg2
from dotenv import load_dotenv

def seed_competitors():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("Error: DATABASE_URL not found in .env")
        return

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
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        # Add UNIQUE constraint on name if it doesn't exist
        cur.execute("ALTER TABLE competitors ADD CONSTRAINT competitors_name_key UNIQUE (name);")
        conn.commit()
    except psycopg2.errors.DuplicateObject:
        conn.rollback()
    except Exception as e:
        print(f"Warning adding constraint: {e}")
        conn.rollback()

    try:
        if 'conn' not in locals() or conn.closed:
             conn = psycopg2.connect(database_url)
             cur = conn.cursor()

        for comp in competitors:
            comp_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO competitors (id, name, website_url, blog_url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
                RETURNING id;
            """, (comp_id, comp["name"], comp["website_url"], comp["blog_url"]))
            
            result = cur.fetchone()
            if result or cur.rowcount > 0:
                print(f"Seeded: {comp['name']}")
            else:
                print(f"Skipped (already exists): {comp['name']}")

        conn.commit()
        cur.close()
        conn.close()
        print("Seeding complete.")

    except Exception as e:
        print(f"An error occurred during seeding: {e}")

if __name__ == "__main__":
    seed_competitors()

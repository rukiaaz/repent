"""
Database Migration: Add leveling_enabled column to guilds table
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'repent.db')


async def migrate_leveling_enabled():
    """Add leveling_enabled column to guilds table."""
    db = await aiosqlite.connect(DB_PATH)
    
    try:
        # Check if column already exists
        cursor = await db.execute("PRAGMA table_info(guilds)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Add column if it doesn't exist
        if 'leveling_enabled' not in column_names:
            await db.execute("ALTER TABLE guilds ADD COLUMN leveling_enabled INTEGER DEFAULT 1")
            print("✅ Added 'leveling_enabled' column to guilds")
        else:
            print("ℹ️ 'leveling_enabled' column already exists in guilds table")
        
        await db.commit()
        print("✅ Migration completed successfully")
        
    except Exception as e:
        await db.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate_leveling_enabled())

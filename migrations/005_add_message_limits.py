"""
Database Migration: Add character and line limit columns to automod_config table
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'repent.db')


async def migrate_message_limits():
    """Add character and line limit columns to automod_config table."""
    db = await aiosqlite.connect(DB_PATH)
    
    try:
        # Check if automod_config table exists
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automod_config'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            print("INFO: automod_config table does not exist yet. It will be created with new columns when the bot starts.")
            print("Migration skipped (will be handled automatically by bot initialization)")
            return
        
        # Check if columns already exist
        cursor = await db.execute("PRAGMA table_info(automod_config)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Add columns if they don't exist
        if 'char_limit_enabled' not in column_names:
            await db.execute("ALTER TABLE automod_config ADD COLUMN char_limit_enabled INTEGER DEFAULT 1")
            print("OK: Added 'char_limit_enabled' column to automod_config")
        else:
            print("INFO: 'char_limit_enabled' column already exists in automod_config")
        
        if 'char_limit' not in column_names:
            await db.execute("ALTER TABLE automod_config ADD COLUMN char_limit INTEGER DEFAULT 3000")
            print("OK: Added 'char_limit' column to automod_config")
        else:
            print("INFO: 'char_limit' column already exists in automod_config")
        
        if 'line_limit_enabled' not in column_names:
            await db.execute("ALTER TABLE automod_config ADD COLUMN line_limit_enabled INTEGER DEFAULT 1")
            print("OK: Added 'line_limit_enabled' column to automod_config")
        else:
            print("INFO: 'line_limit_enabled' column already exists in automod_config")
        
        if 'line_limit' not in column_names:
            await db.execute("ALTER TABLE automod_config ADD COLUMN line_limit INTEGER DEFAULT 15")
            print("OK: Added 'line_limit' column to automod_config")
        else:
            print("INFO: 'line_limit' column already exists in automod_config")
        
        await db.commit()
        print("OK: Migration completed successfully")
        
    except Exception as e:
        await db.rollback()
        print(f"ERROR: Migration failed: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate_message_limits())

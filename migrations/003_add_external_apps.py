"""
Migration 003: Add external apps detection columns
"""

import sqlite3
import asyncio
import aiosqlite
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH

async def migrate():
    """Add external apps detection columns to guilds table."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if columns exist
        cursor = await db.execute("PRAGMA table_info(guilds)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        # Add missing columns
        if 'external_apps_enabled' not in columns:
            await db.execute("ALTER TABLE guilds ADD COLUMN external_apps_enabled INTEGER DEFAULT 1")
        
        if 'external_apps_auto_punish' not in columns:
            await db.execute("ALTER TABLE guilds ADD COLUMN external_apps_auto_punish INTEGER DEFAULT 1")
        
        if 'safe_bots' not in columns:
            await db.execute("ALTER TABLE guilds ADD COLUMN safe_bots TEXT DEFAULT ''")
        
        await db.commit()
        print("Migration 003 completed: Added external apps detection columns")

if __name__ == "__main__":
    asyncio.run(migrate())
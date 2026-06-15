"""
Database Migration: Enhance guild_snapshots table for multi-snapshot support
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'repent.db')


async def migrate_snapshots_table():
    """Add new columns to guild_snapshots table."""
    db = await aiosqlite.connect(DB_PATH)
    
    try:
        # Check if columns already exist
        cursor = await db.execute("PRAGMA table_info(guild_snapshots)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Add columns if they don't exist
        if 'version' not in column_names:
            await db.execute("ALTER TABLE guild_snapshots ADD COLUMN version INTEGER DEFAULT 1")
            print("✅ Added 'version' column to guild_snapshots")
        
        if 'checksum' not in column_names:
            await db.execute("ALTER TABLE guild_snapshots ADD COLUMN checksum TEXT")
            print("✅ Added 'checksum' column to guild_snapshots")
        
        if 'is_protected' not in column_names:
            await db.execute("ALTER TABLE guild_snapshots ADD COLUMN is_protected INTEGER DEFAULT 0")
            print("✅ Added 'is_protected' column to guild_snapshots")
        
        if 'trigger_event' not in column_names:
            await db.execute("ALTER TABLE guild_snapshots ADD COLUMN trigger_event TEXT")
            print("✅ Added 'trigger_event' column to guild_snapshots")
        
        if 'previous_snapshot_id' not in column_names:
            await db.execute("ALTER TABLE guild_snapshots ADD COLUMN previous_snapshot_id INTEGER")
            print("✅ Added 'previous_snapshot_id' column to guild_snapshots")
        
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
    asyncio.run(migrate_snapshots_table())

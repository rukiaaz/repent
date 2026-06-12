"""
Balance - Database Index Optimization
Adds performance indexes to the database for faster queries.
"""

import aiosqlite
import asyncio
from config import DB_PATH

async def add_indexes():
    """Add performance indexes to the database."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    
    try:
        print("Adding database indexes...")
        
        # Guilds table indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guilds_log_channel ON guilds(log_channel)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guilds_mod_channel ON guilds(mod_channel)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guilds_welcome_channel ON guilds(welcome_channel)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guilds_antinuke_enabled ON guilds(antinuke_enabled)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_guilds_automod_enabled ON guilds(automod_enabled)")
        
        # Warnings indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_warnings_guild ON warnings(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings(user_id)")
        
        # Logs indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_guild ON logs(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_action ON logs(action)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_guild_action ON logs(guild_id, action)")
        
        # Whitelists indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_whitelists_guild ON whitelists(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_whitelists_type ON whitelists(type)")
        
        # Hardbans indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_hardbans_guild ON hardbans(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_hardbans_user ON hardbans(user_id)")
        
        # AFK indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_afk_guild ON afk(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_afk_user ON afk(user_id)")
        
        # Cases indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cases_guild ON cases(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cases_action ON cases(action)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cases_target ON cases(target_id)")
        
        # Custom commands indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_custom_commands_guild ON custom_commands(guild_id)")
        
        # Reaction roles indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reaction_roles_guild ON reaction_roles(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reaction_roles_channel ON reaction_roles(channel_id)")
        
        await db.commit()
        print("Database indexes added successfully!")
        
    except Exception as e:
        print(f"Error adding indexes: {e}")
        await db.rollback()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(add_indexes())
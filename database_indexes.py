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
        
        # Logs indexes (action_log table)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_guild ON action_log(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_action ON action_log(action_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log(timestamp)")
        
        # Whitelist indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_guild ON whitelist(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_user ON whitelist(user_id)")
        
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
        
        # Additional performance indexes for frequently queried tables
        await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_guild_user ON action_log(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_automod_strikes_guild_user ON automod_strikes(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_punished_users_guild ON punished_users(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ignored_channels_guild_module ON ignored_channels(guild_id, module)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bad_words_guild ON bad_words(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_antinuke_thresholds_guild ON antinuke_thresholds(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cached_roles_guild ON cached_roles(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cached_channels_guild ON cached_channels(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_xp_guild_user ON xp(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rate_tracker_guild_user ON rate_tracker(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bot_whitelist_guild ON bot_whitelist(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_role_whitelist_guild_role ON role_whitelist(guild_id, role_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_backups_guild ON backups(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_guild_user ON whitelist(guild_id, user_id)")
        
        await db.commit()
        print("Database indexes added successfully!")
        
    except Exception as e:
        print(f"Error adding indexes: {e}")
        await db.rollback()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(add_indexes())
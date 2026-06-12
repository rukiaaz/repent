"""
Repent - Database layer
SQLite via aiosqlite. All operations are async.
"""

import os
import json
import asyncio
import aiosqlite
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple, Set
from config import DB_PATH

# Cache layer import (will be initialized later)
_cache_layer = None

def set_cache_layer(cache_layer):
    """Set the global cache layer instance."""
    global _cache_layer
    _cache_layer = cache_layer

def get_cache_layer():
    """Get the global cache layer instance."""
    return _cache_layer

# ── Security: Allowed column names for SQL injection prevention ──
GUILDS_ALLOWED_COLUMNS = {
    "log_channel", "mod_channel", "welcome_channel", "farewell_channel",
    "autorole", "punishment", "antinuke_enabled", "automod_enabled",
    "welcome_msg", "farewell_msg", "level_up_channel", "level_up_dm",
    "raid_mode", "raid_join_threshold", "raid_join_window", "raid_account_age",
    "verification_channel", "boost_channel", "boost_msg", "verification_enabled",
    "verification_role", "verification_title", "verification_description",
    "verification_color", "verification_button_text", "raid_quarantine_channel",
    "raid_sensitivity_level", "raid_auto_mode", "raid_webhook_url",
    "antinuke_sensitivity_level", "antinuke_lockdown_mode", "antinuke_safe_admins",
    "antinuke_webhook_safe_mode", "antinuke_instant_restore", "antinuke_log_all_punishments",
    "message_log_channel", "guild_log_channel", "all_message_log_channel",
    "voice_log_channel", "mod_log_channel", "custom_prefix", "automod_anti_nsfw",
    "log_voice_events", "log_thread_events", "log_role_events", "log_nickname_events",
    "anti_token_enabled"
}

AUTOMOD_ALLOWED_COLUMNS = {
    "anti_spam", "anti_invite", "anti_link", "anti_caps", "anti_mention",
    "anti_emoji", "spam_threshold", "spam_window", "mention_limit",
    "caps_percent", "emoji_limit"
}

def _validate_column_names(columns: set, allowed_columns: set) -> bool:
    """Validate that column names are in the allowed whitelist."""
    return columns.issubset(allowed_columns)

# ── Helpers ──
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Connection Pooling ──
class ConnectionPool:
    """Simple connection pool for database connections."""
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self._pool: List[aiosqlite.Connection] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> aiosqlite.Connection:
        """Acquire a connection from the pool."""
        async with self._lock:
            if self._pool:
                db = self._pool.pop()
                # Reset the connection to clear any stale WAL snapshots
                try:
                    await db.execute("PRAGMA query_only = 0")
                    await db.execute("PRAGMA read_uncommitted = 0")
                except Exception:
                    pass
                return db
            # Create new connection
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            db = await aiosqlite.connect(DB_PATH)
            db.row_factory = aiosqlite.Row
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode = WAL")
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            # Set busy timeout to handle concurrent access
            await db.execute("PRAGMA busy_timeout = 5000")
            return db
    
    async def release(self, db: aiosqlite.Connection):
        """Release a connection back to the pool."""
        async with self._lock:
            if len(self._pool) < self.max_connections:
                self._pool.append(db)
            else:
                await db.close()
    
    async def close_all(self):
        """Close all connections in the pool."""
        async with self._lock:
            for db in self._pool:
                await _release_db(db)
            self._pool.clear()


# Global connection pool
_connection_pool: Optional[ConnectionPool] = None

def get_connection_pool() -> ConnectionPool:
    """Get or create the global connection pool."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool(max_connections=10)
    return _connection_pool


async def _get_db() -> aiosqlite.Connection:
    """Get or create a database connection."""
    pool = get_connection_pool()
    return await pool.acquire()


async def _release_db(db: aiosqlite.Connection):
    """Release a database connection back to the pool."""
    pool = get_connection_pool()
    await pool.release(db)


# ── Initialization ──
async def cleanup_database_locks():
    """Attempt to clean up stale database locks by removing lock files."""
    import os
    
    # Don't close connections here - let the retry logic handle that
    # Just remove stale lock files if they exist and are old
    
    db_dir = os.path.dirname(DB_PATH)
    db_name = os.path.basename(DB_PATH)
    
    # Possible lock files
    lock_files = [
        os.path.join(db_dir, db_name + "-wal"),
        os.path.join(db_dir, db_name + "-shm"),
    ]
    
    for lock_file in lock_files:
        try:
            if os.path.exists(lock_file):
                # Try to remove stale lock files (only if they're not in use)
                file_age = time.time() - os.path.getmtime(lock_file)
                # Only remove files older than 2 minutes (likely stale)
                if file_age > 120:
                    print(f"[INFO] Removing stale lock file: {lock_file}")
                    os.remove(lock_file)
        except Exception as e:
            # If we can't remove the file, it's probably in use by another process
            # Don't warn about this - it's expected if the bot is already running
            pass


async def init_db():
    """Create all tables if they don't exist with retry logic for database locks."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Add retry logic for database locking
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Use a direct connection instead of the pool for initialization
            db = await aiosqlite.connect(DB_PATH)
            db.row_factory = aiosqlite.Row
            
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode = WAL")
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            # Set busy timeout to handle concurrent access (increased to 10 seconds)
            await db.execute("PRAGMA busy_timeout = 10000")
            
            break  # Success, exit retry loop
        except aiosqlite.OperationalError as e:
            if "locked" in str(e).lower():
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s, 8s
                    print(f"[WARN] Database locked, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Failed to connect to database after {max_retries} attempts: {e}")
            else:
                raise e

    # Define all required tables
    table_creation_scripts = [
        # Guild settings
        """CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY,
            log_channel INTEGER DEFAULT 0,
            mod_channel INTEGER DEFAULT 0,
            welcome_channel INTEGER DEFAULT 0,
            farewell_channel INTEGER DEFAULT 0,
            autorole INTEGER DEFAULT 0,
            punishment TEXT DEFAULT 'ban',
            antinuke_enabled INTEGER DEFAULT 1,
            automod_enabled INTEGER DEFAULT 1,
            welcome_msg TEXT DEFAULT '',
            farewell_msg TEXT DEFAULT '',
            level_up_channel INTEGER DEFAULT 0,
            level_up_dm INTEGER DEFAULT 0,
            raid_mode INTEGER DEFAULT 0,
            raid_join_threshold INTEGER DEFAULT 10,
            raid_join_window INTEGER DEFAULT 10,
            raid_account_age INTEGER DEFAULT 7,
            verification_channel INTEGER DEFAULT 0,
            boost_channel INTEGER DEFAULT 0,
            boost_msg TEXT DEFAULT '',
            verification_enabled INTEGER DEFAULT 0,
            verification_role INTEGER DEFAULT 0,
            verification_title TEXT DEFAULT 'Verification Required',
            verification_description TEXT DEFAULT 'Click the button below to verify yourself and gain access to the server.',
            verification_color INTEGER DEFAULT 0x4488FF,
            verification_button_text TEXT DEFAULT 'Verify',
            raid_quarantine_channel INTEGER DEFAULT 0,
            raid_sensitivity_level INTEGER DEFAULT 5,
            raid_auto_mode INTEGER DEFAULT 0,
            raid_webhook_url TEXT DEFAULT '',
            antinuke_sensitivity_level INTEGER DEFAULT 5,
            antinuke_lockdown_mode INTEGER DEFAULT 0,
            antinuke_safe_admins TEXT DEFAULT '[]',
            antinuke_webhook_safe_mode INTEGER DEFAULT 0,
            antinuke_instant_restore INTEGER DEFAULT 1,
            antinuke_log_all_punishments INTEGER DEFAULT 1,
            message_log_channel INTEGER DEFAULT 0,
            guild_log_channel INTEGER DEFAULT 0,
            all_message_log_channel INTEGER DEFAULT 0,
            voice_log_channel INTEGER DEFAULT 0,
            mod_log_channel INTEGER DEFAULT 0,
            custom_prefix TEXT DEFAULT 'x',
            automod_anti_nsfw INTEGER DEFAULT 0,
            log_voice_events INTEGER DEFAULT 0,
            log_thread_events INTEGER DEFAULT 0,
            log_role_events INTEGER DEFAULT 0,
            log_nickname_events INTEGER DEFAULT 0,
            anti_token_enabled INTEGER DEFAULT 0
        )""",

        # Raid log for history
        """CREATE TABLE IF NOT EXISTS raid_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            started_at TEXT DEFAULT '',
            ended_at TEXT DEFAULT '',
            joins_detected INTEGER DEFAULT 0,
            lockdown_triggered INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0
        )""",

        # Automod strikes for escalating punishments
        """CREATE TABLE IF NOT EXISTS automod_strikes (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            strikes INTEGER DEFAULT 0,
            last_strike_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Whitelist: trusted users per guild
        """CREATE TABLE IF NOT EXISTS whitelist (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            trust_level INTEGER DEFAULT 1,
            added_by INTEGER DEFAULT 0,
            added_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Action log (moderation + antinuke actions)
        """CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER DEFAULT 0,
            action_type TEXT NOT NULL,
            details TEXT DEFAULT '{}',
            timestamp TEXT DEFAULT ''
        )""",

        # Cached roles for rollback
        """CREATE TABLE IF NOT EXISTS cached_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            permissions INTEGER DEFAULT 0,
            color INTEGER DEFAULT 0,
            hoist INTEGER DEFAULT 0,
            mentionable INTEGER DEFAULT 0,
            position INTEGER DEFAULT 0,
            json_overwrites TEXT DEFAULT '{}',
            cached_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, role_id)
        )""",

        # Cached channels for rollback
        """CREATE TABLE IF NOT EXISTS cached_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            type INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT 0,
            position INTEGER DEFAULT 0,
            topic TEXT DEFAULT '',
            nsfw INTEGER DEFAULT 0,
            slowmode INTEGER DEFAULT 0,
            json_overwrites TEXT DEFAULT '{}',
            cached_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, channel_id)
        )""",

        # Moderation cases
        """CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            case_number INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            reason TEXT DEFAULT '',
            evidence TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            resolved INTEGER DEFAULT 0,
            resolved_by INTEGER DEFAULT 0,
            resolved_at TEXT DEFAULT '',
            resolved_reason TEXT DEFAULT ''
        )""",

        # Modmail threads
        """CREATE TABLE IF NOT EXISTS modmail_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            thread_id INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT '',
            closed_at TEXT DEFAULT '',
            closed_by INTEGER DEFAULT 0,
            last_message_at TEXT DEFAULT ''
        )""",

        # Reaction roles
        """CREATE TABLE IF NOT EXISTS reaction_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            is_button INTEGER DEFAULT 0,
            button_label TEXT DEFAULT '',
            button_style TEXT DEFAULT 'PRIMARY',
            required_role INTEGER DEFAULT 0,
            blacklist_role INTEGER DEFAULT 0,
            cooldown INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            created_by INTEGER NOT NULL
        )""",

        # User role tracking (for cooldowns)
        """CREATE TABLE IF NOT EXISTS reaction_role_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role_message_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            given_at TEXT DEFAULT '',
            expires_at TEXT DEFAULT ''
        )""",

        # Custom commands
        """CREATE TABLE IF NOT EXISTS custom_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            response TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT DEFAULT '',
            cooldown INTEGER DEFAULT 0,
            required_role INTEGER DEFAULT 0,
            aliases TEXT DEFAULT '[]'
        )""",

        # Rate tracker for antinuke rolling window
        """CREATE TABLE IF NOT EXISTS rate_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            timestamp TEXT DEFAULT ''
        )""",

        # Punished users (antinuke punishments)
        """CREATE TABLE IF NOT EXISTS punished_users (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            punished_at TEXT DEFAULT '',
            punished_by INTEGER DEFAULT 0,
            punishment_type TEXT DEFAULT 'ban',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Warnings
        """CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            warned_by INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT ''
        )""",

        # User Notes (private moderation notes)
        """CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            note TEXT DEFAULT '',
            added_by INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT ''
        )""",

        # Strikes (escalating punishment system)
        """CREATE TABLE IF NOT EXISTS strikes (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            strikes INTEGER DEFAULT 0,
            last_strike_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Strike Log (history of strikes)
        """CREATE TABLE IF NOT EXISTS strike_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            added_by INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT ''
        )""",

        # Hardbans (auto-reban on rejoin)
        """CREATE TABLE IF NOT EXISTS hardbans (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            banned_by INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # XP / Leveling
        """CREATE TABLE IF NOT EXISTS xp (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            last_message TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Level roles (role rewards at levels)
        """CREATE TABLE IF NOT EXISTS level_roles (
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, level)
        )""",

        # XP cooldown
        """CREATE TABLE IF NOT EXISTS xp_cooldown (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_xp TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # AutoMod config per guild
        """CREATE TABLE IF NOT EXISTS automod_config (
            guild_id INTEGER PRIMARY KEY,
            anti_spam INTEGER DEFAULT 1,
            anti_invite INTEGER DEFAULT 1,
            anti_link INTEGER DEFAULT 0,
            anti_caps INTEGER DEFAULT 1,
            anti_mention INTEGER DEFAULT 1,
            anti_emoji INTEGER DEFAULT 1,
            spam_threshold INTEGER DEFAULT 5,
            spam_window INTEGER DEFAULT 5,
            mention_limit INTEGER DEFAULT 5,
            caps_percent INTEGER DEFAULT 70,
            emoji_limit INTEGER DEFAULT 8
        )""",

        # Bad words per guild
        """CREATE TABLE IF NOT EXISTS bad_words (
            guild_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            PRIMARY KEY (guild_id, word)
        )""",

        # Antinuke thresholds per guild per action
        """CREATE TABLE IF NOT EXISTS antinuke_thresholds (
            guild_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            max_count INTEGER DEFAULT 3,
            window_seconds INTEGER DEFAULT 10,
            PRIMARY KEY (guild_id, action_type)
        )""",

        # AFK
        """CREATE TABLE IF NOT EXISTS afk (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            set_at TEXT DEFAULT '',
            PRIMARY KEY (guild_id, user_id)
        )""",

        # Ignored channels for modules
        """CREATE TABLE IF NOT EXISTS ignored_channels (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            module TEXT DEFAULT 'all',
            PRIMARY KEY (guild_id, channel_id, module)
        )""",

        # Bot whitelist (whitelisted bots that won't be punished)
        """CREATE TABLE IF NOT EXISTS bot_whitelist (
            guild_id INTEGER NOT NULL,
            bot_id INTEGER NOT NULL,
            added_by INTEGER DEFAULT 0,
            added_at TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            PRIMARY KEY (guild_id, bot_id)
        )""",

        # Role whitelist (whitelisted roles - members with these roles won't be punished)
        """CREATE TABLE IF NOT EXISTS role_whitelist (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            added_by INTEGER DEFAULT 0,
            added_at TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            PRIMARY KEY (guild_id, role_id)
        )""",

        # Backups metadata
        """CREATE TABLE IF NOT EXISTS backups (
            backup_id TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT '',
            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
        )""",

        # Backup roles
        """CREATE TABLE IF NOT EXISTS backup_roles (
            backup_id TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            permissions INTEGER DEFAULT 0,
            color INTEGER DEFAULT 0,
            hoist INTEGER DEFAULT 0,
            mentionable INTEGER DEFAULT 0,
            position INTEGER DEFAULT 0,
            json_overwrites TEXT DEFAULT '{}',
            PRIMARY KEY (backup_id, role_id),
            FOREIGN KEY (backup_id) REFERENCES backups(backup_id) ON DELETE CASCADE,
            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
        )""",

        # Backup channels
        """CREATE TABLE IF NOT EXISTS backup_channels (
            backup_id TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            type INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT 0,
            position INTEGER DEFAULT 0,
            topic TEXT DEFAULT '',
            nsfw INTEGER DEFAULT 0,
            slowmode INTEGER DEFAULT 0,
            json_overwrites TEXT DEFAULT '{}',
            PRIMARY KEY (backup_id, channel_id),
            FOREIGN KEY (backup_id) REFERENCES backups(backup_id) ON DELETE CASCADE,
            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
        )""",
    ]

    # Create each table individually for better error handling
    for table_script in table_creation_scripts:
        try:
            await db.execute(table_script)
        except Exception as e:
            print(f"[ERROR] Failed to create table: {e}")
            # Continue with other tables

    # Create indexes separately
    index_creation_scripts = [
        "CREATE INDEX IF NOT EXISTS idx_rate_tracker_lookup ON rate_tracker(guild_id, user_id, action_type, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_action_log_guild_timestamp ON action_log(guild_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_action_log_user ON action_log(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_xp_guild_xp ON xp(guild_id, xp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_hardbans_guild ON hardbans(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_bad_words_guild ON bad_words(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_ignored_channels_guild_module ON ignored_channels(guild_id, module)",
        "CREATE INDEX IF NOT EXISTS idx_bot_whitelist_guild ON bot_whitelist(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_role_whitelist_guild ON role_whitelist(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_reaction_roles_guild_message ON reaction_roles(guild_id, message_id)",
        "CREATE INDEX IF NOT EXISTS idx_custom_commands_guild ON custom_commands(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_strikes_guild_user ON strikes(guild_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_afk_guild_user ON afk(guild_id, user_id)",
    ]

    for index_script in index_creation_scripts:
        try:
            await db.execute(index_script)
        except Exception as e:
            print(f"[WARN] Failed to create index: {e}")
            # Continue with other indexes

    # Run migrations for existing database to add columns
    columns_to_add = [
        ("raid_mode", "INTEGER DEFAULT 0"),
        ("raid_join_threshold", "INTEGER DEFAULT 10"),
        ("raid_join_window", "INTEGER DEFAULT 10"),
        ("raid_account_age", "INTEGER DEFAULT 7"),
        ("verification_channel", "INTEGER DEFAULT 0"),
        ("boost_channel", "INTEGER DEFAULT 0"),
        ("boost_msg", "TEXT DEFAULT ''"),
        ("verification_enabled", "INTEGER DEFAULT 0"),
        ("verification_role", "INTEGER DEFAULT 0"),
        ("verification_title", "TEXT DEFAULT 'Verification Required'"),
        ("verification_description", "TEXT DEFAULT 'Click the button below to verify yourself and gain access to the server.'"),
        ("verification_color", "INTEGER DEFAULT 0x4488FF"),
        ("verification_button_text", "TEXT DEFAULT 'Verify'"),
        ("raid_quarantine_channel", "INTEGER DEFAULT 0"),
        ("raid_sensitivity_level", "INTEGER DEFAULT 5"),
        ("raid_auto_mode", "INTEGER DEFAULT 0"),
        ("raid_webhook_url", "TEXT DEFAULT ''"),
        ("antinuke_sensitivity_level", "INTEGER DEFAULT 5"),
        ("antinuke_lockdown_mode", "INTEGER DEFAULT 0"),
        ("antinuke_safe_admins", "TEXT DEFAULT '[]'"),
        ("antinuke_webhook_safe_mode", "INTEGER DEFAULT 0"),
        ("antinuke_instant_restore", "INTEGER DEFAULT 1"),
        ("antinuke_log_all_punishments", "INTEGER DEFAULT 1"),
        ("message_log_channel", "INTEGER DEFAULT 0"),
        ("guild_log_channel", "INTEGER DEFAULT 0"),
        ("all_message_log_channel", "INTEGER DEFAULT 0"),
        ("voice_log_channel", "INTEGER DEFAULT 0"),
        ("mod_log_channel", "INTEGER DEFAULT 0"),
        ("custom_prefix", "TEXT DEFAULT 'x'"),
        ("automod_anti_nsfw", "INTEGER DEFAULT 0"),
        ("log_voice_events", "INTEGER DEFAULT 0"),
        ("log_thread_events", "INTEGER DEFAULT 0"),
        ("log_role_events", "INTEGER DEFAULT 0"),
        ("log_nickname_events", "INTEGER DEFAULT 0"),
        ("anti_token_enabled", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in columns_to_add:
        try:
            await db.execute(f"ALTER TABLE guilds ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    await db.commit()
    
    # Verify critical tables exist
    critical_tables = ["warnings", "guilds", "action_log", "xp", "cases", "whitelist", "hardbans"]
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in await cursor.fetchall()}
    
    missing_tables = [table for table in critical_tables if table not in existing_tables]
    if missing_tables:
        print(f"[ERROR] Critical tables missing after initialization: {missing_tables}")
        raise Exception(f"Failed to create critical tables: {missing_tables}")
    
    await db.close()
    
    # Run database migrations
    try:
        from utils.migrations import get_migration_runner
        runner = get_migration_runner()
        await runner.migrate()
    except ImportError:
        # Migrations module not available yet (first run)
        pass
    except Exception as e:
        # Log migration errors but don't fail initialization
        import logging
        logging.error(f"Migration error: {e}")


async def purge_old_data():
    """Remove action_log and rate_tracker entries older than 30 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    db = await _get_db()
    await db.execute("DELETE FROM action_log WHERE timestamp < ?", (cutoff,))
    await db.execute("DELETE FROM rate_tracker WHERE timestamp < ?", (cutoff,))
    await db.commit()
    await _release_db(db)


# ── Guild Settings ──
async def get_guild(guild_id: int) -> Dict[str, Any]:
    # Try cache first
    if _cache_layer:
        cached = await _cache_layer.get("guild", guild_id)
        if cached is not None:
            return cached
    
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)
    )
    row = await row.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO guilds (guild_id) VALUES (?)", (guild_id,)
        )
        await db.commit()
        row = await db.execute(
            "SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)
        )
        row = await row.fetchone()
    await _release_db(db)
    result = dict(row) if row else {}
    
    # Cache the result
    if _cache_layer and result:
        await _cache_layer.set("guild", result, guild_id, ttl=300)
    
    return result


async def update_guild(guild_id: int, **kwargs):
    # Security: Validate column names to prevent SQL injection
    if not _validate_column_names(set(kwargs.keys()), GUILDS_ALLOWED_COLUMNS):
        raise ValueError("Invalid column names in update_guild")
    
    db = await _get_db()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [guild_id]
    await db.execute(
        f"UPDATE guilds SET {fields} WHERE guild_id = ?", values
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("guild", guild_id)


# ── Whitelist ──
async def get_whitelist(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM whitelist WHERE guild_id = ?", (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def get_whitelist_entry(guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    # Try cache first
    if _cache_layer:
        cached = await _cache_layer.get("whitelist_entry", guild_id, user_id)
        if cached is not None:
            return cached if cached else None
    
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM whitelist WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    result = dict(row) if row else None
    
    # Cache the result (cache even None to avoid repeated queries for non-whitelisted users)
    if _cache_layer:
        await _cache_layer.set("whitelist_entry", result, guild_id, user_id, ttl=300)
    
    return result


async def add_whitelist(guild_id: int, user_id: int, trust_level: int, added_by: int):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO whitelist
           (guild_id, user_id, trust_level, added_by, added_at)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, user_id, trust_level, added_by, _now()),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("whitelist_entry", guild_id, user_id)


async def remove_whitelist(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM whitelist WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("whitelist_entry", guild_id, user_id)


# ── Bot Whitelist ──
async def add_bot_whitelist(guild_id: int, bot_id: int, added_by: int, reason: str = ""):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO bot_whitelist
           (guild_id, bot_id, added_by, added_at, reason)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, bot_id, added_by, _now(), reason),
    )
    await db.commit()
    await _release_db(db)


async def remove_bot_whitelist(guild_id: int, bot_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM bot_whitelist WHERE guild_id = ? AND bot_id = ?",
        (guild_id, bot_id),
    )
    await db.commit()
    await _release_db(db)


async def get_bot_whitelist(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM bot_whitelist WHERE guild_id = ?",
        (guild_id,),
    )
    rows = await cursor.fetchall()
    await _release_db(db)
    return [dict(row) for row in rows]


async def is_bot_whitelisted(guild_id: int, bot_id: int) -> bool:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM bot_whitelist WHERE guild_id = ? AND bot_id = ?",
        (guild_id, bot_id),
    )
    row = await cursor.fetchone()
    await _release_db(db)
    return row is not None


# ── Role Whitelist ──
async def add_role_whitelist(guild_id: int, role_id: int, added_by: int, reason: str = ""):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO role_whitelist
           (guild_id, role_id, added_by, added_at, reason)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, role_id, added_by, _now(), reason),
    )
    await db.commit()
    await _release_db(db)


async def remove_role_whitelist(guild_id: int, role_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM role_whitelist WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id),
    )
    await db.commit()
    await _release_db(db)


async def get_role_whitelist(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM role_whitelist WHERE guild_id = ?",
        (guild_id,),
    )
    rows = await cursor.fetchall()
    await _release_db(db)
    return [dict(row) for row in rows]


async def is_role_whitelisted(guild_id: int, role_id: int) -> bool:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM role_whitelist WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id),
    )
    row = await cursor.fetchone()
    await _release_db(db)
    return row is not None


async def user_has_whitelisted_role(guild_id: int, user_id: int, user_roles) -> bool:
    """Check if user has any whitelisted roles using optimized SQL query."""
    if not user_roles:
        return False
    
    # Convert to list if it's a set (handle both types for robustness)
    if isinstance(user_roles, set):
        user_roles = list(user_roles)
    
    # Optimized: Use SQL IN clause instead of fetching all roles
    db = await _get_db()
    placeholders = ','.join('?' * len(user_roles))
    cursor = await db.execute(
        f"SELECT COUNT(*) FROM role_whitelist WHERE guild_id = ? AND role_id IN ({placeholders})",
        [guild_id] + user_roles
    )
    count = await cursor.fetchone()
    await _release_db(db)
    
    return count[0] > 0


async def is_user_whitelisted_optimized(guild_id: int, user_id: int, is_bot: bool = False) -> bool:
    """
    Optimized single-query whitelist check combining all whitelist types.
    
    Returns True if user is whitelisted via any method:
    - User whitelist with trust level >= 2
    - Bot whitelist (if user is a bot)
    - Role whitelist (requires user_roles to be passed separately)
    """
    # Check user whitelist with high trust
    db = await _get_db()
    
    # Check user whitelist
    cursor = await db.execute(
        "SELECT trust_level FROM whitelist WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id)
    )
    row = await cursor.fetchone()
    if row and row[0] >= 2:
        await _release_db(db)
        return True
    
    # Check bot whitelist if user is a bot
    if is_bot:
        cursor = await db.execute(
            "SELECT 1 FROM bot_whitelist WHERE guild_id = ? AND bot_id = ?",
            (guild_id, user_id)
        )
        if await cursor.fetchone():
            await _release_db(db)
            return True
    
    await _release_db(db)
    return False


# ── User Notes ──
async def add_user_note(guild_id: int, user_id: int, note: str, added_by: int):
    db = await _get_db()
    await db.execute(
        "INSERT INTO notes (guild_id, user_id, note, added_by, timestamp) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, note, added_by, _now()),
    )
    await db.commit()
    await _release_db(db)


async def get_user_notes(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM notes WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC",
        (guild_id, user_id),
    )
    rows = await cursor.fetchall()
    await _release_db(db)
    return [dict(row) for row in rows]


async def delete_user_note(guild_id: int, note_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM notes WHERE guild_id = ? AND id = ?",
        (guild_id, note_id),
    )
    await db.commit()
    await _release_db(db)


# ── User Strikes ──
async def add_user_strike(guild_id: int, user_id: int, reason: str, added_by: int):
    db = await _get_db()
    # First, check if user has strikes, increment if exists
    cursor = await db.execute(
        "SELECT strikes FROM strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await cursor.fetchone()
    if row:
        new_count = row["strikes"] + 1
        await db.execute(
            "UPDATE strikes SET strikes = ?, last_strike_at = ? WHERE guild_id = ? AND user_id = ?",
            (new_count, _now(), guild_id, user_id),
        )
    else:
        await db.execute(
            "INSERT INTO strikes (guild_id, user_id, strikes, last_strike_at) VALUES (?, ?, 1, ?)",
            (guild_id, user_id, _now()),
        )
    await db.commit()
    await _release_db(db)
    
    # Log the strike
    db2 = await _get_db()
    await db2.execute(
        "INSERT INTO strike_log (guild_id, user_id, reason, added_by, timestamp) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, reason, added_by, _now()),
    )
    await db2.commit()
    await _release_db(db2)


async def get_user_strikes(guild_id: int, user_id: int) -> Dict[str, Any]:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await cursor.fetchone()
    await _release_db(db)
    return dict(row) if row else {"strikes": 0, "last_strike_at": ""}


async def get_user_strike_log(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    cursor = await db.execute(
        "SELECT * FROM strike_log WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC",
        (guild_id, user_id),
    )
    rows = await cursor.fetchall()
    await _release_db(db)
    return [dict(row) for row in rows]


async def clear_user_strikes(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


async def remove_user_strike(guild_id: int, user_id: int):
    db = await _get_db()
    cursor = await db.execute(
        "SELECT strikes FROM strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await cursor.fetchone()
    if row and row["strikes"] > 0:
        new_count = row["strikes"] - 1
        if new_count <= 0:
            await db.execute(
                "DELETE FROM strikes WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        else:
            await db.execute(
                "UPDATE strikes SET strikes = ? WHERE guild_id = ? AND user_id = ?",
                (new_count, guild_id, user_id),
            )
    await db.commit()
    await _release_db(db)


# ── Rate Tracker (rolling window) ──
async def add_rate_event(guild_id: int, user_id: int, action_type: str):
    db = await _get_db()
    await db.execute(
        "INSERT INTO rate_tracker (guild_id, user_id, action_type, timestamp) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, action_type, _now()),
    )
    await db.commit()
    await _release_db(db)


async def count_rate_events(guild_id: int, user_id: int, action_type: str, window_seconds: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()
    db = await _get_db()
    row = await db.execute(
        """SELECT COUNT(*) as cnt FROM rate_tracker
           WHERE guild_id = ? AND user_id = ? AND action_type = ? AND timestamp > ?""",
        (guild_id, user_id, action_type, cutoff),
    )
    row = await row.fetchone()
    await _release_db(db)
    return row["cnt"] if row else 0


async def clear_rate_events(guild_id: int, user_id: int, action_type: str):
    db = await _get_db()
    await db.execute(
        "DELETE FROM rate_tracker WHERE guild_id = ? AND user_id = ? AND action_type = ?",
        (guild_id, user_id, action_type),
    )
    await db.commit()
    await _release_db(db)


# ── Punished Users ──
async def add_punished_user(
    guild_id: int, user_id: int, reason: str, punished_by: int, punishment_type: str
):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO punished_users
           (guild_id, user_id, reason, punished_at, punished_by, punishment_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (guild_id, user_id, reason, _now(), punished_by, punishment_type),
    )
    await db.commit()
    await _release_db(db)


async def remove_punished_user(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM punished_users WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


async def get_punished_users(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM punished_users WHERE guild_id = ?", (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def is_punished(guild_id: int, user_id: int) -> bool:
    db = await _get_db()
    row = await db.execute(
        "SELECT 1 FROM punished_users WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    return row is not None


# ── Warnings ──
async def add_warning(guild_id: int, user_id: int, reason: str, warned_by: int) -> int:
    db = await _get_db()
    cursor = await db.execute(
        """INSERT INTO warnings (guild_id, user_id, reason, warned_by, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, user_id, reason, warned_by, _now()),
    )
    await db.commit()
    warn_id = cursor.lastrowid
    await _release_db(db)
    return warn_id


async def get_warnings(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC",
        (guild_id, user_id),
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def clear_warnings(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


async def get_warning_by_id(warn_id: int) -> Optional[Dict[str, Any]]:
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM warnings WHERE id = ?", (warn_id,)
    )
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


# ── Hardbans ──
async def add_hardban(guild_id: int, user_id: int, reason: str, banned_by: int):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO hardbans
           (guild_id, user_id, reason, banned_by, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, user_id, reason, banned_by, _now()),
    )
    await db.commit()
    await _release_db(db)


async def remove_hardban(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM hardbans WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


async def is_hardbanned(guild_id: int, user_id: int) -> bool:
    db = await _get_db()
    row = await db.execute(
        "SELECT 1 FROM hardbans WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    return row is not None


# ── Role / Channel Cache ──
async def cache_role(guild_id: int, role):
    """Cache a single role."""
    db = await _get_db()
    overwrites = {}
    for target, perm in role.overwrites.items():
        overwrites[str(target.id)] = {
            "type": "member" if isinstance(target, type(role.guild.me)) else "role",
            "allow": perm.pair()[0].value,
            "deny": perm.pair()[1].value,
        }
    await db.execute(
        """INSERT OR REPLACE INTO cached_roles
           (guild_id, role_id, name, permissions, color, hoist, mentionable, position, json_overwrites, cached_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            guild_id, role.id, role.name, role.permissions.value,
            role.color.value, int(role.hoist), int(role.mentionable),
            role.position, json.dumps(overwrites), _now(),
        ),
    )
    await db.commit()
    await _release_db(db)


async def cache_channel(guild_id: int, channel):
    """Cache a single channel."""
    db = await _get_db()
    overwrites = {}
    for target, perm in channel.overwrites.items():
        overwrites[str(target.id)] = {
            "type": "member" if hasattr(target, "guild") else "role",
            "allow": perm.pair()[0].value,
            "deny": perm.pair()[1].value,
        }
    await db.execute(
        """INSERT OR REPLACE INTO cached_channels
           (guild_id, channel_id, name, type, category_id, position, topic, nsfw, slowmode, json_overwrites, cached_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            guild_id, channel.id, channel.name, channel.type.value,
            channel.category_id or 0, channel.position,
            getattr(channel, "topic", "") or "", int(getattr(channel, "nsfw", False)),
            getattr(channel, "slowmode_delay", 0), json.dumps(overwrites), _now(),
        ),
    )
    await db.commit()
    await _release_db(db)


async def get_cached_roles(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM cached_roles WHERE guild_id = ?", (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def get_cached_channels(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM cached_channels WHERE guild_id = ?", (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def delete_cached_role(guild_id: int, role_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM cached_roles WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id),
    )
    await db.commit()
    await _release_db(db)


async def delete_cached_channel(guild_id: int, channel_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM cached_channels WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id),
    )
    await db.commit()
    await _release_db(db)


# ── XP / Leveling ──
async def get_xp(guild_id: int, user_id: int) -> Dict[str, Any]:
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM xp WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO xp (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        await db.commit()
        row = await db.execute(
            "SELECT * FROM xp WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else {"xp": 0, "level": 0}


async def add_xp(guild_id: int, user_id: int, amount: int) -> Tuple[int, int]:
    """Add XP, return (new_level, did_level_up)."""
    db = await _get_db()
    row = await db.execute(
        "SELECT xp, level FROM xp WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO xp (guild_id, user_id, xp) VALUES (?, ?, ?)",
            (guild_id, user_id, amount),
        )
        new_xp = amount
        old_level = 0
    else:
        new_xp = row["xp"] + amount
        old_level = row["level"]
        await db.execute(
            "UPDATE xp SET xp = ?, last_message = ? WHERE guild_id = ? AND user_id = ?",
            (new_xp, _now(), guild_id, user_id),
        )

    new_level = int((new_xp ** 0.5) * 0.1)
    if new_level > old_level:
        await db.execute(
            "UPDATE xp SET level = ? WHERE guild_id = ? AND user_id = ?",
            (new_level, guild_id, user_id),
        )

    await db.commit()
    await _release_db(db)
    return new_level, new_level > old_level


async def set_xp_level(guild_id: int, user_id: int, level: int):
    xp_needed = int((level / 0.1) ** 2)
    db = await _get_db()
    await db.execute(
        """INSERT INTO xp (guild_id, user_id, xp, level)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level""",
        (guild_id, user_id, xp_needed, level),
    )
    await db.commit()
    await _release_db(db)


async def reset_xp(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM xp WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


async def get_leaderboard(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM xp WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
        (guild_id, limit),
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


# ── XP Cooldown ──
async def get_xp_cooldown(guild_id: int, user_id: int) -> Optional[str]:
    db = await _get_db()
    row = await db.execute(
        "SELECT last_xp FROM xp_cooldown WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    return row["last_xp"] if row else None


async def set_xp_cooldown(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        """INSERT INTO xp_cooldown (guild_id, user_id, last_xp)
           VALUES (?, ?, ?)
           ON CONFLICT(guild_id, user_id) DO UPDATE SET last_xp=excluded.last_xp""",
        (guild_id, user_id, _now()),
    )
    await db.commit()
    await _release_db(db)


# ── Level Roles ──
async def get_level_roles(guild_id: int) -> List[Dict[str, Any]]:
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM level_roles WHERE guild_id = ? ORDER BY level ASC",
        (guild_id,),
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def add_level_role(guild_id: int, level: int, role_id: int):
    db = await _get_db()
    await db.execute(
        """INSERT INTO level_roles (guild_id, level, role_id)
           VALUES (?, ?, ?)
           ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id""",
        (guild_id, level, role_id),
    )
    await db.commit()
    await _release_db(db)


async def remove_level_role(guild_id: int, level: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM level_roles WHERE guild_id = ? AND level = ?",
        (guild_id, level),
    )
    await db.commit()
    await _release_db(db)


# ── AutoMod ──
async def get_automod_config(guild_id: int) -> Dict[str, Any]:
    # Try cache first
    if _cache_layer:
        cached = await _cache_layer.get("automod_config", guild_id)
        if cached is not None:
            return cached
    
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
    )
    row = await row.fetchone()
    if not row:
        from config import DEFAULT_AUTOMOD
        await db.execute(
            """INSERT INTO automod_config
               (guild_id, anti_spam, anti_invite, anti_link, anti_caps, anti_mention, anti_emoji,
                spam_threshold, spam_window, mention_limit, caps_percent, emoji_limit)
               VALUES (?, 1, 1, 0, 1, 1, 1, 5, 5, 5, 70, 8)""",
            (guild_id,),
        )
        await db.commit()
        row = await db.execute(
            "SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)
        )
        row = await row.fetchone()
    await _release_db(db)
    result = dict(row) if row else {}
    
    # Cache the result
    if _cache_layer and result:
        await _cache_layer.set("automod_config", result, guild_id, ttl=300)
    
    return result


async def update_automod_config(guild_id: int, **kwargs):
    # Security: Validate column names to prevent SQL injection
    if not _validate_column_names(set(kwargs.keys()), AUTOMOD_ALLOWED_COLUMNS):
        raise ValueError("Invalid column names in update_automod_config")
    
    db = await _get_db()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [guild_id]
    await db.execute(
        f"UPDATE automod_config SET {fields} WHERE guild_id = ?", values
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("automod_config", guild_id)


# ── Bad Words ──
async def get_bad_words(guild_id: int) -> List[str]:
    # Try cache first
    if _cache_layer:
        cached = await _cache_layer.get("bad_words", guild_id)
        if cached is not None:
            return cached
    
    db = await _get_db()
    rows = await db.execute(
        "SELECT word FROM bad_words WHERE guild_id = ?", (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    result = [r["word"] for r in rows]
    
    # Cache the result
    if _cache_layer:
        await _cache_layer.set("bad_words", result, guild_id, ttl=300)
    
    return result


async def add_bad_word(guild_id: int, word: str):
    db = await _get_db()
    await db.execute(
        "INSERT OR IGNORE INTO bad_words (guild_id, word) VALUES (?, ?)",
        (guild_id, word.lower()),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("bad_words", guild_id)


async def remove_bad_word(guild_id: int, word: str):
    db = await _get_db()
    await db.execute(
        "DELETE FROM bad_words WHERE guild_id = ? AND word = ?",
        (guild_id, word.lower()),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        await _cache_layer.delete("bad_words", guild_id)


# ── Antinuke Thresholds ──
async def get_antinuke_threshold(guild_id: int, action_type: str) -> Tuple[int, int]:
    from config import DEFAULT_ANTINUKE_THRESHOLDS
    
    # Try cache first
    cache_key = f"{guild_id}:{action_type}"
    if _cache_layer:
        cached = await _cache_layer.get("antinuke_threshold", cache_key)
        if cached is not None:
            return cached
    
    db = await _get_db()
    row = await db.execute(
        "SELECT max_count, window_seconds FROM antinuke_thresholds WHERE guild_id = ? AND action_type = ?",
        (guild_id, action_type),
    )
    row = await row.fetchone()
    await _release_db(db)
    if row:
        result = (row["max_count"], row["window_seconds"])
    else:
        defaults = DEFAULT_ANTINUKE_THRESHOLDS.get(action_type, (3, 10))
        result = defaults
    
    # Cache the result
    if _cache_layer:
        await _cache_layer.set("antinuke_threshold", result, cache_key, ttl=300)
    
    return result


async def set_antinuke_threshold(guild_id: int, action_type: str, max_count: int, window_seconds: int):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO antinuke_thresholds
           (guild_id, action_type, max_count, window_seconds)
           VALUES (?, ?, ?, ?)""",
        (guild_id, action_type, max_count, window_seconds),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache
    if _cache_layer:
        cache_key = f"{guild_id}:{action_type}"
        await _cache_layer.delete("antinuke_threshold", cache_key)


# ── AFK ──
async def set_afk(guild_id: int, user_id: int, reason: str):
    db = await _get_db()
    await db.execute(
        """INSERT OR REPLACE INTO afk (guild_id, user_id, reason, set_at)
           VALUES (?, ?, ?, ?)""",
        (guild_id, user_id, reason, _now()),
    )
    await db.commit()
    await _release_db(db)


async def get_afk(guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM afk WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


async def remove_afk(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM afk WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


# ── Ignored Channels ──
async def get_ignored_channels(guild_id: int, module: str = "all") -> List[int]:
    # Try cache first
    cache_key = f"{guild_id}:{module}"
    if _cache_layer:
        cached = await _cache_layer.get("ignored_channels", cache_key)
        if cached is not None:
            return cached
    
    db = await _get_db()
    rows = await db.execute(
        """SELECT channel_id FROM ignored_channels
           WHERE guild_id = ? AND (module = ? OR module = 'all')""",
        (guild_id, module),
    )
    rows = await rows.fetchall()
    await _release_db(db)
    result = [r["channel_id"] for r in rows]
    
    # Cache the result
    if _cache_layer:
        await _cache_layer.set("ignored_channels", result, cache_key, ttl=300)
    
    return result


async def add_ignored_channel(guild_id: int, channel_id: int, module: str = "all"):
    db = await _get_db()
    await db.execute(
        "INSERT OR IGNORE INTO ignored_channels (guild_id, channel_id, module) VALUES (?, ?, ?)",
        (guild_id, channel_id, module),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache (clear all module variants for this guild)
    if _cache_layer:
        await _cache_layer.clear_pattern(f"ignored_channels:{guild_id}:")


async def remove_ignored_channel(guild_id: int, channel_id: int, module: str = "all"):
    db = await _get_db()
    await db.execute(
        "DELETE FROM ignored_channels WHERE guild_id = ? AND channel_id = ? AND module = ?",
        (guild_id, channel_id, module),
    )
    await db.commit()
    await _release_db(db)
    
    # Invalidate cache (clear all module variants for this guild)
    if _cache_layer:
        await _cache_layer.clear_pattern(f"ignored_channels:{guild_id}:")


# ── Action Log ──
async def log_action(guild_id: int, action_type: str, user_id: int = 0, details: dict = None):
    db = await _get_db()
    await db.execute(
        """INSERT INTO action_log (guild_id, user_id, action_type, details, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (guild_id, user_id, action_type, json.dumps(details or {}), _now()),
    )
    await db.commit()
    await _release_db(db)


async def get_recent_logs(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent action logs for a guild."""
    db = await _get_db()
    cursor = await db.execute(
        """SELECT user_id, action_type, details, timestamp 
           FROM action_log 
           WHERE guild_id = ? 
           ORDER BY timestamp DESC 
           LIMIT ?""",
        (guild_id, limit),
    )
    rows = await cursor.fetchall()
    await _release_db(db)
    
    logs = []
    for row in rows:
        logs.append({
            "user_id": row["user_id"],
            "action_type": row["action_type"],
            "details": json.loads(row["details"]) if row["details"] else {},
            "timestamp": row["timestamp"],
        })
    return logs


# ── Automod Strikes ──
async def get_strikes(guild_id: int, user_id: int) -> int:
    db = await _get_db()
    row = await db.execute(
        "SELECT strikes FROM automod_strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    row = await row.fetchone()
    await _release_db(db)
    return row["strikes"] if row else 0


async def add_strike(guild_id: int, user_id: int) -> int:
    new_strikes = await get_strikes(guild_id, user_id) + 1
    db = await _get_db()
    await db.execute(
        """INSERT INTO automod_strikes (guild_id, user_id, strikes, last_strike_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(guild_id, user_id) DO UPDATE SET strikes = excluded.strikes, last_strike_at = excluded.last_strike_at""",
        (guild_id, user_id, new_strikes, _now()),
    )
    await db.commit()
    await _release_db(db)
    return new_strikes


async def clear_strikes(guild_id: int, user_id: int):
    db = await _get_db()
    await db.execute(
        "DELETE FROM automod_strikes WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    await db.commit()
    await _release_db(db)


# ── Raid Log ──
async def log_raid_start(guild_id: int, joins_detected: int, lockdown_triggered: int) -> int:
    db = await _get_db()
    cursor = await db.execute(
        """INSERT INTO raid_log (guild_id, started_at, joins_detected, lockdown_triggered)
           VALUES (?, ?, ?, ?)""",
        (guild_id, _now(), joins_detected, lockdown_triggered),
    )
    await db.commit()
    raid_id = cursor.lastrowid
    await _release_db(db)
    return raid_id


async def log_raid_end(raid_id: int, resolved: int):
    db = await _get_db()
    await db.execute(
        "UPDATE raid_log SET ended_at = ?, resolved = ? WHERE id = ?",
        (_now(), resolved, raid_id),
    )
    await db.commit()
    await _release_db(db)


# ── Backups ──
async def save_backup(guild_id: int, backup_id: str, name: str, roles: list, channels: list):
    # Use a fresh connection for backup operations to avoid WAL snapshot issues
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    # Enable WAL mode for better concurrency
    await db.execute("PRAGMA journal_mode = WAL")
    # Enable foreign key constraints
    await db.execute("PRAGMA foreign_keys = ON")
    # Set busy timeout to handle concurrent access
    await db.execute("PRAGMA busy_timeout = 5000")

    try:
        # Insert backup metadata
        await db.execute(
            "INSERT INTO backups (backup_id, guild_id, name, created_at) VALUES (?, ?, ?, ?)",
            (backup_id, guild_id, name, _now())
        )

        # Insert backup roles
        for r in roles:
            # Roles don't have overwrites, only channels do
            # Store empty overwrites for roles
            overwrites = {}
            await db.execute(
                """INSERT OR REPLACE INTO backup_roles
                   (backup_id, guild_id, role_id, name, permissions, color, hoist, mentionable, position, json_overwrites)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    backup_id, guild_id, r.id, r.name, r.permissions.value,
                    r.color.value, int(r.hoist), int(r.mentionable),
                    r.position, json.dumps(overwrites)
                )
            )

        # Insert backup channels
        for ch in channels:
            overwrites = {}
            for target, perm in ch.overwrites.items():
                overwrites[str(target.id)] = {
                    "type": "member" if hasattr(target, "guild") else "role",
                    "allow": perm.pair()[0].value,
                    "deny": perm.pair()[1].value,
                }
            await db.execute(
                """INSERT OR REPLACE INTO backup_channels
                   (backup_id, guild_id, channel_id, name, type, category_id, position, topic, nsfw, slowmode, json_overwrites)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    backup_id, guild_id, ch.id, ch.name, ch.type.value,
                    ch.category_id or 0, ch.position,
                    getattr(ch, "topic", "") or "", int(getattr(ch, "nsfw", False)),
                    getattr(ch, "slowmode_delay", 0), json.dumps(overwrites)
                )
            )

        await db.commit()
    finally:
        await db.close()


async def get_backups(guild_id: int) -> list:
    db = await _get_db()
    rows = await db.execute("SELECT * FROM backups WHERE guild_id = ? ORDER BY created_at DESC", (guild_id,))
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def get_backup(guild_id: int, backup_id: str) -> dict | None:
    db = await _get_db()
    row = await db.execute("SELECT * FROM backups WHERE guild_id = ? AND backup_id = ?", (guild_id, backup_id))
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


# ── Case Management ──
async def create_case(guild_id: int, user_id: int, moderator_id: int, action_type: str, 
                     reason: str = "", evidence: dict = None) -> int:
    """Create a new moderation case and return case number."""
    db = await _get_db()
    
    # Get next case number for this guild
    cursor = await db.execute(
        "SELECT COALESCE(MAX(case_number), 0) + 1 FROM cases WHERE guild_id = ?",
        (guild_id,)
    )
    result = await cursor.fetchone()
    case_number = result[0] if result else 1
    
    await db.execute(
        """INSERT INTO cases (guild_id, case_number, user_id, moderator_id, action_type, reason, evidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (guild_id, case_number, user_id, moderator_id, action_type, reason, 
         json.dumps(evidence or {}), _now())
    )
    await db.commit()
    await _release_db(db)
    
    return case_number


async def get_case(guild_id: int, case_number: int) -> dict | None:
    """Get a specific case by case number."""
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM cases WHERE guild_id = ? AND case_number = ?",
        (guild_id, case_number)
    )
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


async def get_user_cases(guild_id: int, user_id: int, limit: int = 10) -> list:
    """Get cases for a specific user."""
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM cases WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
        (guild_id, user_id, limit)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def get_all_cases(guild_id: int, limit: int = 20) -> list:
    """Get all cases for a guild."""
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM cases WHERE guild_id = ? ORDER BY created_at DESC LIMIT ?",
        (guild_id, limit)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def resolve_case(guild_id: int, case_number: int, resolved_by: int, resolved_reason: str = ""):
    """Mark a case as resolved."""
    db = await _get_db()
    await db.execute(
        """UPDATE cases SET resolved = 1, resolved_by = ?, resolved_at = ?, resolved_reason = ?
           WHERE guild_id = ? AND case_number = ?""",
        (resolved_by, _now(), resolved_reason, guild_id, case_number)
    )
    await db.commit()
    await _release_db(db)


async def update_case_evidence(guild_id: int, case_number: int, evidence: dict):
    """Update case evidence."""
    db = await _get_db()
    await db.execute(
        "UPDATE cases SET evidence = ? WHERE guild_id = ? AND case_number = ?",
        (json.dumps(evidence), guild_id, case_number)
    )
    await db.commit()
    await _release_db(db)


# ── Modmail System ──
async def create_modmail_thread(guild_id: int, user_id: int, channel_id: int) -> int:
    """Create a new modmail thread."""
    db = await _get_db()
    
    # Check if thread already exists
    existing = await db.execute(
        "SELECT id FROM modmail_threads WHERE guild_id = ? AND user_id = ? AND status = 'open'",
        (guild_id, user_id)
    )
    if await existing.fetchone():
        await _release_db(db)
        return None  # Thread already exists
    
    await db.execute(
        """INSERT INTO modmail_threads (guild_id, user_id, channel_id, status, created_at, last_message_at)
           VALUES (?, ?, ?, 'open', ?, ?)""",
        (guild_id, user_id, channel_id, _now(), _now())
    )
    await db.commit()
    
    # Get the thread ID
    cursor = await db.execute("SELECT last_insert_rowid()")
    thread_id = (await cursor.fetchone())[0]
    await _release_db(db)
    
    return thread_id


async def get_modmail_thread(guild_id: int, user_id: int) -> dict | None:
    """Get an open modmail thread for a user."""
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM modmail_threads WHERE guild_id = ? AND user_id = ? AND status = 'open'",
        (guild_id, user_id)
    )
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


async def get_open_modmail_threads(guild_id: int) -> list:
    """Get all open modmail threads for a guild."""
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM modmail_threads WHERE guild_id = ? AND status = 'open' ORDER BY created_at DESC",
        (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def close_modmail_thread(guild_id: int, user_id: int, closed_by: int) -> bool:
    """Close a modmail thread."""
    db = await _get_db()
    
    result = await db.execute(
        "UPDATE modmail_threads SET status = 'closed', closed_at = ?, closed_by = ? WHERE guild_id = ? AND user_id = ? AND status = 'open'",
        (_now(), closed_by, guild_id, user_id)
    )
    
    await db.commit()
    await _release_db(db)
    
    return result.rowcount > 0


async def update_modmail_activity(guild_id: int, user_id: int):
    """Update the last message time for a modmail thread."""
    db = await _get_db()
    await db.execute(
        "UPDATE modmail_threads SET last_message_at = ? WHERE guild_id = ? AND user_id = ? AND status = 'open'",
        (_now(), guild_id, user_id)
    )
    await db.commit()
    await _release_db(db)


# ── Reaction Role System ──
async def create_reaction_role(guild_id: int, message_id: int, emoji: str, role_id: int, 
                           created_by: int, is_button: int = 0, button_label: str = "", button_style: str = "PRIMARY",
                           required_role: int = 0, blacklist_role: int = 0, cooldown: int = 0) -> int:
    """Create a reaction role."""
    db = await _get_db()
    
    # Parse emoji to ensure it's in consistent format
    if is_button:
        emoji = button_label  # For buttons, use label as identifier
    
    await db.execute(
        """INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id, is_button, button_label, button_style, required_role, blacklist_role, cooldown, created_at, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (guild_id, message_id, emoji, role_id, is_button, button_label, button_style, 
         required_role, blacklist_role, cooldown, _now(), created_by)
    )
    await db.commit()
    
    cursor = await db.execute("SELECT last_insert_rowid()")
    reaction_role_id = (await cursor.fetchone())[0]
    await _release_db(db)
    
    return reaction_role_id


async def get_reaction_roles(guild_id: int, message_id: int) -> list:
    """Get all reaction roles for a message."""
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM reaction_roles WHERE guild_id = ? AND message_id = ?",
        (guild_id, message_id)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def remove_reaction_role(guild_id: int, reaction_role_id: int) -> bool:
    """Remove a reaction role."""
    db = await _get_db()
    result = await db.execute(
        "DELETE FROM reaction_roles WHERE id = ? AND guild_id = ?",
        (reaction_role_id, guild_id)
    )
    await db.commit()
    await _release_db(db)
    return result.rowcount > 0


async def get_user_reaction_role_history(guild_id: int, user_id: int, role_message_id: int, role_id: int) -> dict | None:
    """Check if user has cooldown for a reaction role."""
    db = await _get_db()
    now = _now()
    rows = await db.execute(
        """SELECT * FROM reaction_role_history 
           WHERE guild_id = ? AND user_id = ? AND role_message_id = ? AND role_id = ? 
           AND expires_at > ? 
           ORDER BY expires_at DESC LIMIT 1""",
        (guild_id, user_id, role_message_id, role_id, now)
    )
    row = await rows.fetchone()
    await _release_db(db)
    return dict(row) if row else None


async def add_reaction_role_history(guild_id: int, user_id: int, role_message_id: int, role_id: int, cooldown_seconds: int = 0):
    """Add reaction role history entry."""
    db = await _get_db()
    
    # Set expiration time
    expires_at = None
    if cooldown_seconds > 0:
        from datetime import datetime, timedelta, timezone
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)).isoformat()
    
    await db.execute(
        """INSERT INTO reaction_role_history (guild_id, user_id, role_message_id, role_id, given_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (guild_id, user_id, role_message_id, role_id, _now(), expires_at)
    )
    await db.commit()
    await _release_db(db)


async def cleanup_reaction_role_history():
    """Clean up expired reaction role history entries."""
    db = await _get_db()
    now = _now()
    await db.execute(
        "DELETE FROM reaction_role_history WHERE expires_at < ?",
        (now,)
    )
    await db.commit()
    await _release_db(db)


# ── Custom Commands System ──
async def create_custom_command(guild_id: int, name: str, response: str, created_by: int, 
                              cooldown: int = 0, required_role: int = 0, aliases: list = None) -> int:
    """Create a custom command."""
    db = await _get_db()
    
    await db.execute(
        """INSERT INTO custom_commands (guild_id, name, response, created_by, created_at, cooldown, required_role, aliases)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (guild_id, name, response, created_by, _now(), cooldown, required_role, json.dumps(aliases or []))
    )
    await db.commit()
    
    cursor = await db.execute("SELECT last_insert_rowid()")
    cmd_id = (await cursor.fetchone())[0]
    await _release_db(db)
    
    return cmd_id


async def get_custom_command(guild_id: int, name: str) -> dict | None:
    """Get a custom command by name."""
    db = await _get_db()
    row = await db.execute(
        "SELECT * FROM custom_commands WHERE guild_id = ? AND name = ?",
        (guild_id, name)
    )
    row = await row.fetchone()
    await _release_db(db)
    return dict(row) if row else None


async def get_all_custom_commands(guild_id: int) -> list:
    """Get all custom commands for a guild."""
    db = await _get_db()
    rows = await db.execute(
        "SELECT * FROM custom_commands WHERE guild_id = ? ORDER BY name ASC",
        (guild_id,)
    )
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def delete_custom_command(guild_id: int, command_name: str) -> bool:
    """Delete a custom command."""
    db = await _get_db()
    result = await db.execute(
        "DELETE FROM custom_commands WHERE guild_id = ? AND name = ?",
        (guild_id, command_name)
    )
    await db.commit()
    await _release_db(db)
    return result.rowcount > 0


async def update_custom_command(guild_id: int, name: str, response: str = None, cooldown: int = None) -> bool:
    """Update a custom command."""
    db = await _get_db()
    
    updates = []
    values = []
    
    if response is not None:
        updates.append("response = ?")
        values.append(response)
    if cooldown is not None:
        updates.append("cooldown = ?")
        values.append(cooldown)
    
    if not updates:
        return False
    
    values.extend([guild_id, name])
    
    result = await db.execute(
        f"UPDATE custom_commands SET {', '.join(updates)} WHERE guild_id = ? AND name = ?",
        values
    )
    await db.commit()
    await _release_db(db)
    
    return result.rowcount > 0


async def get_backup_roles(backup_id: str) -> list:
    db = await _get_db()
    rows = await db.execute("SELECT * FROM backup_roles WHERE backup_id = ? ORDER BY position ASC", (backup_id,))
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def get_backup_channels(backup_id: str) -> list:
    db = await _get_db()
    rows = await db.execute("SELECT * FROM backup_channels WHERE backup_id = ? ORDER BY position ASC", (backup_id,))
    rows = await rows.fetchall()
    await _release_db(db)
    return [dict(r) for r in rows]


async def delete_backup(guild_id: int, backup_id: str):
    db = await _get_db()
    await db.execute("DELETE FROM backups WHERE guild_id = ? AND backup_id = ?", (guild_id, backup_id))
    await db.execute("DELETE FROM backup_roles WHERE backup_id = ?", (backup_id,))
    await db.execute("DELETE FROM backup_channels WHERE backup_id = ?", (backup_id,))
    await db.commit()
    await _release_db(db)


async def close_all_connections():
    """Close all database connections for graceful shutdown."""
    pool = get_connection_pool()
    await pool.close_all()

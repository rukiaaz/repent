"""
Repent - Advanced Discord Antinuke & Security Bot
Entry point. Loads cogs, initializes cache, auto-purges old data.
Updated: Fixed database initialization and type errors
"""

import os
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import signal

from config import TOKEN, BOT_NAME, VERSION, OWNER_ID, CACHE_AUTO_SAVE_INTERVAL
from database import init_db, purge_old_data, close_all_connections, set_cache_layer
from utils.cache import snapshot_guild
from utils.logger import get_logger
from utils.health_check import get_health_checker
from utils.cache_layer import get_cache_layer
from utils.rate_limiter import set_cache_layer_for_rate_limiter
from utils.sync_simple import sync_commands_simple


class Repent(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        # Members intent required for accurate antinuke + welcome
        # Message content required for automod
        # Audit log required for on_audit_log_entry_create

        super().__init__(
            command_prefix="x",  # Legacy prefix kept for emergencies
            intents=intents,
            owner_id=OWNER_ID,
            help_command=None,
        )
        self.start_time = datetime.now(timezone.utc)
        self.logger = get_logger()
        self._shutdown_event = asyncio.Event()

    async def setup_hook(self):
        # Initialize database with retry logic
        await init_db()
        await purge_old_data()
        self.logger.info("Database initialized and old data purged")

        # Initialize health checker
        get_health_checker(self)
        self.logger.info("Health checker initialized")
        
        # Initialize cache layer
        cache_layer = get_cache_layer()
        await cache_layer.start()
        self.logger.info("Cache layer initialized")
        
        # Set cache layer for database and rate limiter
        set_cache_layer(cache_layer)
        set_cache_layer_for_rate_limiter(cache_layer)
        self.logger.info("Cache layer integrated with database and rate limiter")

        # Load all cogs (guard against duplicate loads)
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        cogs_to_load = []
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                cog_name = f"cogs.{filename[:-3]}"
                cogs_to_load.append(cog_name)
        
        for cog_name in cogs_to_load:
            try:
                if cog_name in self.extensions:
                    continue
                await self.load_extension(cog_name)
                self.logger.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                self.logger.error(f"Failed to load cog {cog_name}", exc_info=True)

        # Log all commands in the tree after loading
        self.logger.info("=" * 70)
        self.logger.info("COMMAND TREE INVENTORY")
        self.logger.info("=" * 70)
        tree_commands = list(self.tree.walk_commands())
        self.logger.info(f"Total commands in tree: {len(tree_commands)}")
        for cmd in tree_commands:
            self.logger.info(f"  /{cmd.qualified_name}")
        self.logger.info("=" * 70)

        # Simple, robust command sync
        stats = await sync_commands_simple(self)
        
        if not stats.get('success', False):
            self.logger.error(f"❌ Command sync failed: {stats.get('error', 'Unknown error')}")
        else:
            self.logger.info(f"✓ Command sync successful: {stats['synced']} commands synced")

        # Start background tasks
        asyncio.create_task(self.cache_snapshot_loop())
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

    async def on_ready(self):
        self.logger.info("=" * 50)
        self.logger.info(f"{BOT_NAME} v{VERSION} is online!")
        self.logger.info(f"Logged in as: {self.user} ({self.user.id})")
        self.logger.info(f"Owner: {OWNER_ID}")
        self.logger.info(f"Guilds: {len(self.guilds)}")
        self.logger.info(f"Users: {sum(g.member_count for g in self.guilds)}")
        self.logger.info("=" * 50)

        # Permission validation for each guild
        for guild in self.guilds:
            await self._validate_guild_permissions(guild)

        # Initial cache snapshot for all guilds
        for guild in self.guilds:
            try:
                await snapshot_guild(guild, trigger_event="startup")
                self.logger.info(f"Snapshotted guild: {guild.name} ({guild.id})")
            except Exception as e:
                self.logger.error(f"Failed to snapshot guild {guild.id}", exc_info=True)

        # Set presence
        await self.update_presence()

    async def update_presence(self):
        """Update bot presence with current statistics."""
        total_guilds = len(self.guilds)
        total_members = sum(guild.member_count for guild in self.guilds)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{total_guilds} servers | {total_members:,} members | xhelp"
            ),
            status=discord.Status.online,
        )

    async def on_guild_join(self, guild: discord.Guild):
        """Cache newly joined guild immediately."""
        try:
            await snapshot_guild(guild, trigger_event="guild_join")
            self.logger.info(f"Joined and cached guild: {guild.name} ({guild.id})")
            # Update presence with new count
            await self.update_presence()
        except Exception as e:
            self.logger.error(f"Failed to cache guild {guild.id}", exc_info=True)

        # Notify owner
        try:
            owner = await self.fetch_user(OWNER_ID)
            if owner:
                embed = discord.Embed(
                    title="📥 New Server",
                    description=f"**{guild.name}** (`{guild.id}`)\nMembers: {guild.member_count}",
                    color=0x44FF88,
                )
                await owner.send(embed=embed)
        except Exception as e:
            self.logger.error("Failed to notify owner of new guild", exc_info=True)

    async def on_guild_remove(self, guild: discord.Guild):
        self.logger.info(f"Left guild: {guild.name} ({guild.id})")
        # Update presence with new count
        try:
            await self.update_presence()
        except Exception as e:
            self.logger.error(f"Failed to update presence after leaving guild", exc_info=True)

    async def _validate_guild_permissions(self, guild: discord.Guild):
        """Validate bot permissions and log warnings for missing permissions."""
        bot_member = guild.me
        missing_permissions = []
        
        # Critical permissions for antinuke
        critical_permissions = [
            ("administrator", "Administrator"),
            ("ban_members", "Ban Members"),
            ("kick_members", "Kick Members"),
            ("manage_roles", "Manage Roles"),
            ("manage_channels", "Manage Channels"),
            ("view_audit_log", "View Audit Log"),
        ]
        
        for perm_name, perm_display in critical_permissions:
            if not getattr(bot_member.guild_permissions, perm_name, False):
                missing_permissions.append(perm_display)
        
        if missing_permissions:
            self.logger.warning(
                f"Guild {guild.name} ({guild.id}) is missing critical permissions: "
                f"{', '.join(missing_permissions)}. Antinuke may not function properly."
            )
            
            # Try to notify the owner
            try:
                owner = guild.get_member(guild.owner_id)
                if owner:
                    embed = discord.Embed(
                        title="⚠️ Missing Permissions Warning",
                        description=f"{self.user.name} is missing critical permissions in **{guild.name}**:\n\n"
                                    f"```\n{chr(10).join(f'• {perm}' for perm in missing_permissions)}\n```\n\n"
                                    f"Please grant these permissions for full antinuke protection.",
                        color=0xFFAA00
                    )
                    await owner.send(embed=embed)
            except Exception as e:
                self.logger.error(f"Failed to send permission warning to owner of {guild.id}: {e}")
        else:
            self.logger.info(f"Guild {guild.name} ({guild.id}) has all required permissions.")

    async def on_member_join(self, member: discord.Member):
        """Check hardbans immediately on join."""
        from database import is_hardbanned
        if await is_hardbanned(member.guild.id, member.id):
            try:
                await member.guild.ban(
                    member,
                    reason="[Repent] Hardban — auto reban on rejoin",
                    delete_message_days=0,
                )
                self.logger.security("HARDBAN_REBAN", f"Re-banned user {member.id}", guild_id=member.guild.id, user_id=member.id)
            except Exception as e:
                self.logger.error(f"Failed to reban hardbanned user {member.id}", exc_info=True)

    # ── Cache snapshot loop ──
    async def cache_snapshot_loop(self):
        """Background task to create auto-snapshots every 10 minutes with cleanup (OPTIMIZED)."""
        await self.wait_until_ready()
        
        while not self.is_closed():
            try:
                # Process snapshots in batches to reduce API calls
                snapshot_tasks = []
                for guild in self.guilds:
                    async def snapshot_guild_safe(guild):
                        try:
                            # Create snapshot using the enhanced function
                            antinuke_cog = self.get_cog('Antinuke')
                            if antinuke_cog:
                                success = await antinuke_cog.create_auto_snapshot(guild)
                                if success:
                                    # Clean up old snapshots (keep only 3 most recent)
                                    await antinuke_cog.cleanup_old_snapshots(guild, keep_count=3)
                            else:
                                # Fallback to basic snapshot
                                await snapshot_guild(guild, trigger_event="scheduled")
                        except Exception as e:
                            self.logger.error(f"Failed to snapshot guild {guild.id}", exc_info=True)
                    
                    snapshot_tasks.append(snapshot_guild_safe(guild))
                
                # Execute snapshots concurrently with rate limiting
                if snapshot_tasks:
                    # Process in batches of 5 to avoid API rate limits
                    for i in range(0, len(snapshot_tasks), 5):
                        batch = snapshot_tasks[i:i+5]
                        await asyncio.gather(*batch, return_exceptions=True)
                        if i + 5 < len(snapshot_tasks):
                            await asyncio.sleep(1)  # Small delay between batches
                
                # Update presence after snapshot to keep member counts current
                try:
                    await self.update_presence()
                except Exception as e:
                    self.logger.error(f"Failed to update presence in snapshot loop", exc_info=True)
                
            except Exception as e:
                self.logger.error(f"Error in snapshot loop: {e}", exc_info=True)
            
            # Wait 10 minutes before next snapshot (OPTIMIZED from 5 minutes)
            await asyncio.sleep(600)

    # ── Error Handlers ──
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        self.logger.command_error(str(ctx.command), ctx.author.id, str(error))

    async def on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CheckFailure):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Permission Denied",
                    description=str(error),
                    color=0xFF4444,
                ),
                ephemeral=True,
            )
        else:
            self.logger.command_error(str(interaction.command), interaction.user.id, str(error))
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An unexpected error occurred. The issue has been logged.",
                        color=0xFF4444,
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass

    # ── Graceful Shutdown ──
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        try:
            import signal
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except Exception as e:
            self.logger.error(f"Failed to setup signal handlers: {e}")

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        # Set the shutdown event in a thread-safe way
        self.loop.call_soon_threadsafe(self._shutdown_event.set)

    async def shutdown(self):
        """Perform graceful shutdown."""
        self.logger.info("Starting graceful shutdown")
        
        try:
            # Cache layer will be stopped when the loop exits naturally
            # No need to cancel the task as it checks self.is_closed()
            
            # Stop cache layer
            cache_layer = get_cache_layer()
            await cache_layer.stop()
            self.logger.info("Cache layer stopped")
            
            # Close database connections
            await close_all_connections()
            self.logger.info("Database connections closed")
            
            # Close Discord connection
            await self.close()
            self.logger.info("Discord connection closed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
        finally:
            self.logger.info("Graceful shutdown complete")


# ── Run ──
if __name__ == "__main__":
    if not TOKEN:
        print("[FATAL] DISCORD_TOKEN not found. Set it in your .env file.")
        exit(1)
    if OWNER_ID == 0:
        print("[WARN] OWNER_ID not set. Some features will be restricted.")

    bot = Repent()
    try:
        bot.run(TOKEN, reconnect=True)
    except Exception as e:
        print(f"[FATAL] Failed to start bot: {e}")

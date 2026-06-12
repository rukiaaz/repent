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
from utils.announcements import get_recent_announcements


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


        # Sync slash commands
        try:
            await self.tree.sync()
            self.logger.info("Slash commands synced globally")
        except Exception as e:
            self.logger.error(f"Failed to sync commands", exc_info=True)

        # Start background tasks
        self.cache_snapshot_loop.start()
        
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
                await snapshot_guild(guild)
                self.logger.info(f"Snapshotted guild: {guild.name} ({guild.id})")
            except Exception as e:
                self.logger.error(f"Failed to snapshot guild {guild.id}", exc_info=True)

        # Send announcements to all guilds
        await self._send_announcements_to_guilds()

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

    async def _get_or_create_announcement_channel(self, guild: discord.Guild):
        """Get existing announcement channel or create a new one."""
        # Try to find existing announcement channel
        announcement_channel = discord.utils.get(guild.text_channels, name="repent-announcements")
        
        if not announcement_channel:
            try:
                # Create new announcement channel
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        add_reactions=False
                    ),
                    guild.me: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        embed_links=True,
                        manage_channels=True
                    )
                }
                
                announcement_channel = await guild.create_text_channel(
                    name="repent-announcements",
                    reason="[Repent] Auto-created announcement channel for bot updates",
                    overwrites=overwrites,
                    position=0  # Put at top of channel list
                )
                
                # Send welcome message
                welcome_embed = discord.Embed(
                    title="📢 Repent Announcements",
                    description="This channel will automatically receive updates about bot changes, new features, and important announcements.",
                    color=0x4488FF
                )
                welcome_embed.add_field(
                    name="About",
                    value="You can safely mute this channel if you don't want to receive update notifications, but we recommend keeping an eye on important updates.",
                    inline=False
                )
                welcome_embed.set_footer(text=f"Powered by {self.user.name}")
                await announcement_channel.send(embed=welcome_embed)
                
            except discord.Forbidden:
                self.logger.warning(f"Failed to create announcement channel for guild {guild.id} - missing permissions")
                return None
            except Exception as e:
                self.logger.error(f"Error creating announcement channel for guild {guild.id}: {e}", exc_info=True)
                return None
        
        return announcement_channel

    async def _send_announcements(self, channel: discord.TextChannel):
        """Send recent announcements to a channel."""
        try:
            announcements = get_recent_announcements(limit=3)
            
            if not announcements:
                return
            
            for ann in announcements:
                # Choose color based on importance
                color_map = {
                    "low": 0x888888,
                    "normal": 0x4488FF,
                    "high": 0xFFAA00,
                    "critical": 0xFF4444
                }
                color = color_map.get(ann.get("importance", "normal"), 0x4488FF)
                
                embed = discord.Embed(
                    title=f"📢 {ann['title']}",
                    description=ann['description'],
                    color=color
                )
                
                # Add date if available
                if ann.get("date"):
                    try:
                        date_str = datetime.fromisoformat(ann['date']).strftime("%Y-%m-%d %H:%M UTC")
                        embed.add_field(name="Date", value=date_str, inline=True)
                    except:
                        pass
                
                # Add version if available
                if ann.get("version"):
                    embed.add_field(name="Version", value=ann['version'], inline=True)
                
                embed.set_footer(text=f"Update ID: {ann['id']} | Powered by {self.user.name}")
                
                await channel.send(embed=embed)
                
        except Exception as e:
            self.logger.error(f"Error sending announcements to channel {channel.id}: {e}", exc_info=True)

    async def _send_announcements_to_guilds(self):
        """Send announcements to all guilds."""
        for guild in self.guilds:
            try:
                announcement_channel = await self._get_or_create_announcement_channel(guild)
                if announcement_channel:
                    await self._send_announcements(announcement_channel)
                    self.logger.info(f"Sent announcements to guild {guild.name} ({guild.id})")
            except Exception as e:
                self.logger.error(f"Failed to send announcements to guild {guild.id}: {e}", exc_info=True)

    async def on_guild_join(self, guild: discord.Guild):
        """Cache newly joined guild immediately."""
        try:
            await snapshot_guild(guild)
            self.logger.info(f"Joined and cached guild: {guild.name} ({guild.id})")
            # Update presence with new count
            await self.update_presence()
        except Exception as e:
            self.logger.error(f"Failed to cache guild {guild.id}", exc_info=True)

        # Create announcement channel and send announcements
        try:
            announcement_channel = await self._get_or_create_announcement_channel(guild)
            if announcement_channel:
                await self._send_announcements(announcement_channel)
                self.logger.info(f"Created announcement channel for new guild {guild.name} ({guild.id})")
        except Exception as e:
            self.logger.error(f"Failed to setup announcements for new guild {guild.id}: {e}", exc_info=True)

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
    @tasks.loop(seconds=CACHE_AUTO_SAVE_INTERVAL)
    async def cache_snapshot_loop(self):
        for guild in self.guilds:
            try:
                await snapshot_guild(guild)
            except Exception as e:
                self.logger.error(f"Failed to snapshot guild {guild.id} in loop", exc_info=True)
        
        # Update presence after snapshot to keep member counts current
        try:
            await self.update_presence()
        except Exception as e:
            self.logger.error(f"Failed to update presence in snapshot loop", exc_info=True)

    @cache_snapshot_loop.before_loop
    async def before_cache_loop(self):
        await self.wait_until_ready()

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
            # Cancel background tasks
            self.cache_snapshot_loop.cancel()
            
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

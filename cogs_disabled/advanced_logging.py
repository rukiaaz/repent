"""Repent - Advanced Logging System

Comprehensive logging for voice, threads, role changes, nicknames, and audit logs.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from config import OWNER_ID
from database import get_guild, update_guild, log_action
from utils.embeds import info_embed, success_embed, error_embed
from utils.logger import get_logger


class AdvancedLogging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    # ── Advanced Logging Configuration ──
    @app_commands.command(name="logging", description="Configure advanced logging (Admin only)")
    @app_commands.describe(
        action="configure, enable, or disable",
        event_type="voice, thread, role, or nickname",
        channel="Channel for the log (optional)"
    )
    async def logging_config(
        self,
        interaction: discord.Interaction,
        action: str,
        event_type: str,
        channel: discord.TextChannel = None
    ):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Administrator required."),
                ephemeral=True
            )
        
        guild = interaction.guild
        action_l = action.lower()
        event_type_l = event_type.lower()
        
        # Map event types to database columns
        event_columns = {
            "voice": "log_voice_events",
            "thread": "log_thread_events", 
            "role": "log_role_events",
            "nickname": "log_nickname_events"
        }
        
        if event_type_l not in event_columns:
            return await interaction.response.send_message(
                embed=error_embed("Invalid event type. Use: voice, thread, role, or nickname"),
                ephemeral=True
            )
        
        column = event_columns[event_type_l]
        
        if action_l == "enable":
            # Set log channel if provided, otherwise use general log channel
            if channel:
                channel_column = f"{event_type_l}_log_channel"
                try:
                    await update_guild(guild.id, **{channel_column: channel.id})
                except:
                    # Column doesn't exist yet, use general log channel
                    pass
            
            # Enable the event logging
            await update_guild(guild.id, **{column: 1})
            
            return await interaction.response.send_message(
                embed=success_embed(f"Enabled {event_type_l} logging", 
                f"{event_type_l} events will now be logged."),
                ephemeral=False
            )
        
        elif action_l == "disable":
            await update_guild(guild.id, **{column: 0})
            return await interaction.response.send_message(
                embed=success_embed(f"Disabled {event_type_l} logging", 
                f"{event_type_l} events will no longer be logged."),
                ephemeral=False
            )
        
        elif action_l == "configure":
            if not channel:
                return await interaction.response.send_message(
                    embed=error_embed("Channel is required for configuration."),
                    ephemeral=True
                )
            
            channel_column = f"{event_type_l}_log_channel"
            try:
                await update_guild(guild.id, **{channel_column: channel.id})
                return await interaction.response.send_message(
                    embed=success_embed(f"Configured {event_type_l} Log Channel", 
                    f"{event_type_l} events will be logged to {channel.mention}"),
                    ephemeral=False
                )
            except:
                # If specific channel column doesn't exist, use general log channel
                await update_guild(guild.id, log_channel=channel.id)
                return await interaction.response.send_message(
                    embed=success_embed(f"Configured {event_type_l} Log Channel", 
                    f"{event_type_l} events will be logged to {channel.mention} (using general log channel)"),
                    ephemeral=False
                )
        
        else:
            return await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: enable, disable, or configure"),
                ephemeral=True
            )

    # ── Voice Event Listeners ──
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Log voice state changes."""
        if member.bot:  # Skip bot voice events
            return
        
        guild = member.guild
        settings = await get_guild(guild.id)
        
        if not settings.get("log_voice_events", 0):
            return
        
        # Determine the log channel
        log_channel_id = settings.get("voice_log_channel") or settings.get("log_channel", 0)
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        try:
            # Determine what changed
            if before.channel != after.channel:
                if after.channel:
                    # User joined or moved to a channel
                    if before.channel:
                        # User moved channels
                        embed = discord.Embed(
                            title="🔊 Voice Channel Move",
                            description=f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}",
                            color=0xFFAA00
                        )
                    else:
                        # User joined voice channel
                        embed = discord.Embed(
                            title="🎤 Voice Channel Join",
                            description=f"{member.mention} joined {after.channel.mention}",
                            color=0x44FF88
                        )
                else:
                    # User left voice channel
                    if before.channel:
                        embed = discord.Embed(
                            title="🔇 Voice Channel Leave",
                            description=f"{member.mention} left {before.channel.mention}",
                            color=0xFF4444
                        )
                
                embed.add_field(name="User ID", value=str(member.id), inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"User: {member.name} ({member.id})")
                embed.timestamp = datetime.now(timezone.utc)
                
                await log_channel.send(embed=embed)
                
                await log_action(guild.id, "voice_state_change", member.id, {
                    "before_channel": before.channel.id if before.channel else None,
                    "after_channel": after.channel.id if after.channel else None,
                    "self_mute": before.self_mute != after.self_mute,
                    "self_deaf": before.self_deaf != after.self_deaf,
                    "self_stream": before.self_stream != after.self_stream
                })
                
        except Exception as e:
            self.logger.error(f"Failed to log voice state change for {member.id}", exc_info=True)

    # ── Thread Event Listeners ──
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Log thread creation."""
        guild = thread.guild
        settings = await get_guild(guild.id)
        
        if not settings.get("log_thread_events", 0):
            return
        
        log_channel_id = settings.get("thread_log_channel") or settings.get("log_channel", 0)
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        try:
            embed = discord.Embed(
                title="🧵 Thread Created",
                description=f"New thread created: {thread.mention}",
                color=0x4488FF
            )
            embed.add_field(name="Thread ID", value=str(thread.id), inline=True)
            embed.add_field(name="Parent Channel", value=thread.parent.mention if thread.parent else "Unknown", inline=True)
            embed.add_field(name="Owner", value=thread.owner.mention if thread.owner else "Unknown", inline=True)
            embed.add_field(name="Archived", value="Yes" if thread.archived else "No", inline=True)
            embed.add_field(name="Locked", value="Yes" if thread.locked else "No", inline=True)
            embed.set_footer(text=f"Created by {thread.owner.name if thread.owner else 'Unknown'}")
            embed.timestamp = thread.created_at if thread.created_at else datetime.now(timezone.utc)
            
            await log_channel.send(embed=embed)
            
            await log_action(guild.id, "thread_created", thread.owner.id if thread.owner else 0, {
                "thread_id": thread.id,
                "thread_name": thread.name,
                "parent_channel": thread.parent_id if thread.parent else None
            })
            
        except Exception as e:
            self.logger.error(f"Failed to log thread creation for {thread.id}", exc_info=True)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        """Log thread deletion."""
        guild = thread.guild
        settings = await get_guild(guild.id)
        
        if not settings.get("log_thread_events", 0):
            return
        
        log_channel_id = settings.get("thread_log_channel") or settings.get("log_channel", 0)
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        try:
            embed = discord.Embed(
                title="🧵 Thread Deleted",
                description=f"Thread deleted: {thread.name}",
                color=0xFF4444
            )
            embed.add_field(name="Thread ID", value=str(thread.id), inline=True)
            embed.add_field(name="Parent Channel", value=thread.parent.mention if thread.parent else "Unknown", inline=True)
            embed.set_footer(text="Thread has been deleted")
            embed.timestamp = datetime.now(timezone.utc)
            
            await log_channel.send(embed=embed)
            
            await log_action(guild.id, "thread_deleted", 0, {
                "thread_id": thread.id,
                "thread_name": thread.name,
                "parent_channel": thread.parent_id if thread.parent else None
            })
            
        except Exception as e:
            self.logger.error(f"Failed to log thread deletion for {thread.id}", exc_info=True)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        """Log thread updates."""
        guild = before.guild
        settings = await get_guild(guild.id)
        
        if not settings.get("log_thread_events", 0):
            return
        
        log_channel_id = settings.get("thread_log_channel") or settings.get("log_channel", 0)
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        try:
            # Only log important changes
            important_changes = []
            
            if before.name != after.name:
                important_changes.append(f"Name: {before.name} → {after.name}")
            if before.archived != after.archived:
                important_changes.append(f"Archived: {before.archived} → {after.archived}")
            if before.locked != after.locked:
                important_changes.append(f"Locked: {before.locked} → {after.locked}")
            if before.slowmode_delay != after.slowmode_delay:
                important_changes.append(f"Slowmode: {before.slowmode_delay}s → {after.slowmode_delay}s")
            
            if important_changes:
                embed = discord.Embed(
                    title="🧵 Thread Updated",
                    description=f"Thread: {after.mention}",
                    color=0xFFAA00
                )
                embed.add_field(name="Changes", value="\n".join(important_changes), inline=False)
                embed.add_field(name="Thread ID", value=str(after.id), inline=True)
                embed.set_footer(text=f"Thread {after.name} has been updated")
                embed.timestamp = datetime.now(timezone.utc)
                
                await log_channel.send(embed=embed)
                
                await log_action(guild.id, "thread_updated", 0, {
                    "thread_id": after.id,
                    "changes": important_changes
                })
            
        except Exception as e:
            self.logger.error(f"Failed to log thread update for {after.id}", exc_info=True)

    # ── Role Event Listeners ──
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Log member role and nickname changes."""
        guild = after.guild
        settings = await get_guild(guild.id)
        
        # Role changes
        if before.roles != after.roles and settings.get("log_role_events", 0):
            log_channel_id = settings.get("role_log_channel") or settings.get("log_channel", 0)
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    try:
                        added_roles = set(after.roles) - set(before.roles)
                        removed_roles = set(before.roles) - set(after.roles)
                        
                        if added_roles or removed_roles:
                            embed = discord.Embed(
                                title="📛 Role Changes",
                                description=f"{after.mention}",
                                color=0xFFAA00
                            )
                            
                            if added_roles:
                                added_mentions = [role.mention for role in added_roles if not role.is_default()]
                                if added_mentions:
                                    embed.add_field(name="Roles Added", value=", ".join(added_mentions), inline=False)
                            
                            if removed_roles:
                                removed_mentions = [role.mention for role in removed_roles if not role.is_default()]
                                if removed_mentions:
                                    embed.add_field(name="Roles Removed", value=", ".join(removed_mentions), inline=False)
                            
                            embed.add_field(name="User ID", value=str(after.id), inline=True)
                            embed.set_thumbnail(url=after.display_avatar.url)
                            embed.set_footer(text=f"User: {after.name} ({after.id})")
                            embed.timestamp = datetime.now(timezone.utc)
                            
                            await log_channel.send(embed=embed)
                            
                            await log_action(guild.id, "role_change", after.id, {
                                "added_roles": [role.id for role in added_roles],
                                "removed_roles": [role.id for role in removed_roles]
                            })
                    
                    except Exception as e:
                        self.logger.error(f"Failed to log role change for {after.id}", exc_info=True)
        
        # Nickname changes
        if before.nick != after.nick and settings.get("log_nickname_events", 0):
            log_channel_id = settings.get("nickname_log_channel") or settings.get("log_channel", 0)
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    try:
                        embed = discord.Embed(
                            title="✏️ Nickname Change",
                            description=f"{after.mention}",
                            color=0x4488FF
                        )
                        embed.add_field(name="Previous", value=before.nick or "None (Server Default)", inline=True)
                        embed.add_field(name="New", value=after.nick or "None (Server Default)", inline=True)
                        embed.add_field(name="User ID", value=str(after.id), inline=True)
                        embed.set_thumbnail(url=after.display_avatar.url)
                        embed.set_footer(text=f"User: {after.name} ({after.id})")
                        embed.timestamp = datetime.now(timezone.utc)
                        
                        await log_channel.send(embed=embed)
                        
                        await log_action(guild.id, "nickname_change", after.id, {
                            "previous": before.nick,
                            "new": after.nick
                        })
                    
                    except Exception as e:
                        self.logger.error(f"Failed to log nickname change for {after.id}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdvancedLogging(bot))
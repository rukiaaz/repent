"""Repent - Case Management & Modmail System

Comprehensive case tracking and modmail functionality for professional moderation workflows.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from config import OWNER_ID
from database import (
    create_case, get_case, get_user_cases, get_all_cases, resolve_case,
    update_case_evidence, create_modmail_thread, get_modmail_thread,
    get_open_modmail_threads, close_modmail_thread, update_modmail_activity
)
from utils.embeds import success_embed, error_embed, info_embed, warning_embed
from utils.logger import get_logger


class Cases(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()

    async def _is_mod(self, interaction: discord.Interaction) -> bool:
        """Check if user has moderation permissions."""
        return (interaction.user.guild_permissions.ban_members or 
                interaction.user.guild_permissions.kick_members or
                interaction.user.id == OWNER_ID)

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user is administrator."""
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    # ── Case Management Commands ──
    @app_commands.command(name="case", description="Create or view moderation cases")
    @app_commands.describe(
        action="create, view, resolve, or add_evidence",
        user="User for the case (for create/view)",
        reason="Reason for the action",
        case_number="Case number (for view/resolve)"
    )
    async def case_command(
        self,
        interaction: discord.Interaction,
        action: str,
        user: discord.Member = None,
        reason: str = None,
        case_number: int = None
    ):
        guild = interaction.guild
        action_l = action.lower()
        
        if action_l == "create":
            if not await self._is_mod(interaction):
                return await interaction.response.send_message(
                    embed=error_embed("Moderation permissions required."), 
                    ephemeral=True
                )
            
            if not user or not reason:
                return await interaction.response.send_message(
                    embed=error_embed("User and reason are required for creating a case."),
                    ephemeral=True
                )
            
            # Create the case
            case_num = await create_case(
                guild.id, user.id, interaction.user.id, "MANUAL", reason
            )
            
            await log_action(guild.id, "case_created", user.id, {
                "case_number": case_num,
                "moderator": interaction.user.id,
                "reason": reason
            })
            
            embed = discord.Embed(
                title=f"📋 Case #{case_num} Created",
                description=f"Case created for {user.mention}",
                color=0x4488FF
            )
            embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Status", value="Open", inline=True)
            embed.set_footer(text=f"Use /case view {case_num} to manage this case")
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
        elif action_l == "view":
            if not case_number:
                return await interaction.response.send_message(
                    embed=error_embed("Case number is required to view a case."),
                    ephemeral=True
                )
            
            case = await get_case(guild.id, case_number)
            if not case:
                return await interaction.response.send_message(
                    embed=error_embed(f"Case #{case_number} not found."),
                    ephemeral=True
                )
            
            user_member = guild.get_member(case["user_id"])
            user_mention = user_member.mention if user_member else f"<@{case['user_id']}>"
            moderator = guild.get_member(case["moderator_id"])
            mod_mention = moderator.mention if moderator else f"<@{case['moderator_id']}>"
            
            status = "✅ Resolved" if case["resolved"] else "🔴 Open"
            
            embed = discord.Embed(
                title=f"📋 Case #{case['case_number']}",
                description=status,
                color=0x44FF88 if case["resolved"] else 0xFF4444
            )
            embed.add_field(name="User", value=user_mention, inline=True)
            embed.add_field(name="Moderator", value=mod_mention, inline=True)
            embed.add_field(name="Action Type", value=case["action_type"], inline=True)
            embed.add_field(name="Reason", value=case["reason"] or "No reason", inline=False)
            
            if case["evidence"]:
                try:
                    evidence = eval(case["evidence"]) if isinstance(case["evidence"], str) else case["evidence"]
                    if evidence:
                        evidence_text = "\n".join([f"• {k}: {v}" for k, v in evidence.items()])
                        embed.add_field(name="Evidence", value=evidence_text, inline=False)
                except:
                    pass
            
            embed.add_field(name="Created", value=f"<t:{int(datetime.fromisoformat(case['created_at']).timestamp())}:R>", inline=True)
            
            if case["resolved"]:
                embed.add_field(name="Resolved By", value=f"<@{case['resolved_by']}>", inline=True)
                embed.add_field(name="Resolved At", value=f"<t:{int(datetime.fromisoformat(case['resolved_at']).timestamp())}:R>", inline=True)
                if case["resolved_reason"]:
                    embed.add_field(name="Resolution Reason", value=case["resolved_reason"], inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
        elif action_l == "resolve":
            if not await self._is_mod(interaction):
                return await interaction.response.send_message(
                    embed=error_embed("Moderation permissions required."), 
                    ephemeral=True
                )
            
            if not case_number:
                return await interaction.response.send_message(
                    embed=error_embed("Case number is required to resolve a case."),
                    ephemeral=True
                )
            
            resolution_reason = reason or "No reason provided"
            await resolve_case(guild.id, case_number, interaction.user.id, resolution_reason)
            
            embed = discord.Embed(
                title=f"✅ Case #{case_number} Resolved",
                description=f"Case resolved by {interaction.user.mention}",
                color=0x44FF88
            )
            embed.add_field(name="Reason", value=resolution_reason, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
        elif action_l == "add_evidence":
            if not await self._is_mod(interaction):
                return await interaction.response.send_message(
                    embed=error_embed("Moderation permissions required."), 
                    ephemeral=True
                )
            
            if not case_number or not reason:
                return await interaction.response.send_message(
                    embed=error_embed("Case number and evidence are required."),
                    ephemeral=True
                )
            
            case = await get_case(guild.id, case_number)
            if not case:
                return await interaction.response.send_message(
                    embed=error_embed(f"Case #{case_number} not found."),
                    ephemeral=True
                )
            
            try:
                current_evidence = eval(case["evidence"]) if case["evidence"] else {}
            except:
                current_evidence = {}
            
            # Add new evidence
            evidence_key = f"Evidence_{len(current_evidence) + 1}"
            current_evidence[evidence_key] = {
                "added_by": interaction.user.id,
                "content": reason,
                "timestamp": _now()
            }
            
            await update_case_evidence(guild.id, case_number, current_evidence)
            
            await interaction.response.send_message(
                embed=success_embed("Evidence Added", f"Added evidence to case #{case_number}"),
                ephemeral=False
            )
        
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: create, view, resolve, or add_evidence"),
                ephemeral=True
            )

    @app_commands.command(name="cases", description="View all recent cases or cases for a user")
    @app_commands.describe(user="User to view cases for (optional)", limit="Number of cases to show")
    async def cases_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        limit: int = 10
    ):
        guild = interaction.guild
        limit = max(1, min(50, limit))
        
        if user:
            # View specific user's cases
            cases = await get_user_cases(guild.id, user.id, limit)
            if not cases:
                return await interaction.response.send_message(
                    embed=info_embed(f"{user.display_name}'s Cases", "No cases found for this user."),
                    ephemeral=False
                )
            
            embed = discord.Embed(
                title=f"📋 {user.display_name}'s Cases",
                description=f"Showing {len(cases)} recent cases",
                color=0x4488FF
            )
            
            for case in cases:
                status = "✅" if case["resolved"] else "🔴"
                moderator = guild.get_member(case["moderator_id"])
                mod_mention = moderator.mention if moderator else f"<@{case['moderator_id']}>"
                
                embed.add_field(
                    name=f"{status} Case #{case['case_number']} - {case['action_type']}",
                    value=f"**Moderator:** {mod_mention}\n**Reason:** {case['reason'][:50] or 'No reason'}\n**Created:** <t:{int(datetime.fromisoformat(case['created_at']).timestamp())}:R>",
                    inline=False
                )
            
        else:
            # View all recent cases
            cases = await get_all_cases(guild.id, limit)
            if not cases:
                return await interaction.response.send_message(
                    embed=info_embed("Server Cases", "No cases found in this server."),
                    ephemeral=False
                )
            
            embed = discord.Embed(
                title=f"📋 Server Cases",
                description=f"Showing {len(cases)} recent cases",
                color=0x4488FF
            )
            
            for case in cases:
                status = "✅" if case["resolved"] else "🔴"
                user_member = guild.get_member(case["user_id"])
                user_mention = user_member.mention if user_member else f"<@{case['user_id']}>"
                
                embed.add_field(
                    name=f"{status} Case #{case['case_number']} - {case['action_type']}",
                    value=f"**User:** {user_mention}\n**Reason:** {case['reason'][:50] or 'No reason'}\n**Created:** <t:{int(datetime.fromisoformat(case['created_at']).timestamp())}:R>",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ── Modmail Commands ──
    @app_commands.command(name="modmail", description="Configure and manage modmail system (Admin only)")
    @app_commands.describe(
        action="setup, close, or list",
        channel="Channel for modmail (for setup)"
    )
    async def modmail_command(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: discord.TextChannel = None
    ):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Administrator required."),
                ephemeral=True
            )
        
        guild = interaction.guild
        action_l = action.lower()
        
        if action_l == "setup":
            if not channel:
                return await interaction.response.send_message(
                    embed=error_embed("Channel is required for modmail setup."),
                    ephemeral=True
                )
            
            # Save modmail channel to guild settings
            from database import update_guild
            await update_guild(guild.id, modmail_channel=channel.id)
            
            embed = discord.Embed(
                title="📬 Modmail Setup",
                description=f"Modmail channel set to {channel.mention}",
                color=0x4488FF
            )
            embed.add_field(
                name="Instructions",
                value="Users can DM the bot to create modmail threads. Moderators can respond in the modmail channel.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
        
        elif action_l == "list":
            # List all open modmail threads
            threads = await get_open_modmail_threads(guild.id)
            if not threads:
                return await interaction.response.send_message(
                    embed=info_embed("Modmail Threads", "No open modmail threads."),
                    ephemeral=False
                )
            
            embed = discord.Embed(
                title=f"📬 Open Modmail Threads ({len(threads)})",
                color=0x4488FF
            )
            
            for thread in threads:
                user = guild.get_member(thread["user_id"])
                user_mention = user.mention if user else f"<@{thread['user_id']}>"
                channel = guild.get_channel(thread["channel_id"])
                
                last_activity = f"<t:{int(datetime.fromisoformat(thread['last_message_at']).timestamp())}:R>" if thread["last_message_at"] else "Never"
                
                embed.add_field(
                    name=f"{user_mention}",
                    value=f"**Channel:** {channel.mention if channel else 'Unknown'}\n**Last Activity:** {last_activity}\n**Created:** <t:{int(datetime.fromisoformat(thread['created_at']).timestamp())}:R>",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
        
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: setup or list"),
                ephemeral=True
            )

    # ── Modmail Listeners ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle incoming DM messages for modmail."""
        if message.guild:  # Only process DMs
            return
        if message.author.bot:  # Ignore bot messages
            return
        if message.author.id == self.bot.user.id:  # Ignore self
            return
        
        # Get the user's guilds that have modmail enabled
        # For simplicity, we'll check if the user is in a guild with modmail set up
        user = message.author
        
        # Check each guild the user is in
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if not member:  # User not in this guild
                continue
            
            # Check if modmail is configured for this guild
            from database import get_guild
            settings = await get_guild(guild.id)
            modmail_channel_id = settings.get("modmail_channel", 0)
            
            if not modmail_channel_id:
                continue
            
            # Check if modmail thread already exists
            existing_thread = await get_modmail_thread(guild.id, user.id)
            modmail_channel = guild.get_channel(modmail_channel_id)
            
            if not modmail_channel:
                continue
            
            try:
                if existing_thread:
                    # Add message to existing thread
                    existing_channel = guild.get_channel(existing_thread["channel_id"])
                    if existing_channel:
                        webhook = await self._get_or_create_webhook(existing_channel)
                        await webhook.send(
                            content=message.content,
                            username=message.author.name,
                            avatar_url=message.author.display_avatar.url,
                            wait=True
                        )
                        await update_modmail_activity(guild.id, user.id)
                    
                    # Send confirmation to user
                    await message.channel.send(
                        "✅ Your message has been forwarded to the moderators.",
                        delete_after=5
                    )
                else:
                    # Create new modmail thread
                    thread = await modmail_channel.create_thread(
                        name=f"Modmail-{user.name}",
                        message=None,
                        auto_archive_duration=60,
                        reason=f"Modmail thread for {user.name}"
                    )
                    
                    await create_modmail_thread(guild.id, user.id, thread.id)
                    
                    # Send initial message to thread
                    embed = discord.Embed(
                        title=f"📬 New Modmail from {user.name}",
                        description=message.content,
                        color=0x4488FF
                    )
                    embed.add_field(name="User ID", value=str(user.id), inline=True)
                    embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    await thread.send(embed=embed)
                    
                    # Send confirmation to user
                    await message.channel.send(
                        f"✅ Your message has been sent to the moderators of {guild.name}.",
                        delete_after=10
                    )
                    
                    self.logger.info(f"Created modmail thread for {user.id} in {guild.name}")
            
            except Exception as e:
                self.logger.error(f"Failed to process modmail message: {e}", exc_info=True)
                try:
                    await message.channel.send(
                        "❌ Failed to send your message to moderators. Please try again later.",
                        delete_after=10
                    )
                except:
                    pass

    async def _get_or_create_webhook(self, channel: discord.TextChannel):
        """Get or create a webhook for the channel."""
        webhooks = await channel.webhooks()
        for webhook in webhooks:
            if webhook.user.id == self.bot.user.id:
                return webhook
        
        # Create new webhook
        return await channel.create_webhook(name="Modmail Webhook")


async def setup(bot: commands.Bot):
    await bot.add_cog(Cases(bot))
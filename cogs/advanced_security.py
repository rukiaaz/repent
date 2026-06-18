"""
Balance - Advanced Security Systems
Simplified security management for the bot.
"""

from __future__ import annotations

import json
import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed

class AdvancedSecurity(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    # === Defense Layer Management ===

    @app_commands.command(name="defense", description="Manage defense system status (Admin only)")
    @app_commands.describe(action="status or lockdown")
    async def defense(self, interaction: discord.Interaction, action: str):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        action_l = action.lower()

        if action_l == "status":
            # Get current antinuke status
            antinuke_enabled = settings.get("antinuke_enabled", 0)
            automod_enabled = settings.get("automod_enabled", 0)
            raid_mode = settings.get("raid_mode", 0)
            
            embed = discord.Embed(title="🛡️ Defense Status", color=0x4488FF)
            embed.add_field(name="Antinuke", value="✅ Active" if antinuke_enabled else "❌ Inactive", inline=True)
            embed.add_field(name="AutoMod", value="✅ Active" if automod_enabled else "❌ Inactive", inline=True)
            embed.add_field(name="Raid Mode", value="🔒 Active" if raid_mode else "⚪ Inactive", inline=True)
            return await interaction.response.send_message(embed=embed, ephemeral=False)

        elif action_l == "lockdown":
            # Enable raid mode (lockdown)
            await update_guild(guild.id, raid_mode=1)
            return await interaction.response.send_message(
                embed=success_embed("Lockdown Initiated", "Raid mode has been enabled. Server is now in lockdown."),
                ephemeral=False
            )

        elif action_l == "unlockdown":
            # Disable raid mode
            await update_guild(guild.id, raid_mode=0)
            return await interaction.response.send_message(
                embed=success_embed("Lockdown Lifted", "Raid mode has been disabled. Server is now normal."),
                ephemeral=False
            )

        else:
            return await interaction.response.send_message(
                embed=error_embed("Use: `status`, `lockdown`, or `unlockdown`."),
                ephemeral=True
            )

    # === Trust System (Simplified) ===

    @app_commands.command(name="trust", description="View user activity logs (Admin only)")
    @app_commands.describe(user="User to check")
    async def trust(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        
        if user:
            # Get user's join date and activity
            join_date = user.joined_at.strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "Unknown"
            account_age = user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "Unknown"
            days_on_server = (discord.utils.utcnow() - user.joined_at).days if user.joined_at else 0
            days_on_discord = (discord.utils.utcnow() - user.created_at).days if user.created_at else 0
            
            embed = discord.Embed(title=f"🔐 User Profile: {user.display_name}", color=0x4488FF)
            embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
            embed.add_field(name="Member Count", value=f"#{len(guild.members) - list(guild.members).index(user)}", inline=True)
            embed.add_field(name="Joined Server", value=join_date, inline=False)
            embed.add_field(name="Days on Server", value=f"{days_on_server} days", inline=True)
            embed.add_field(name="Account Created", value=account_age, inline=False)
            embed.add_field(name="Days on Discord", value=f"{days_on_discord} days", inline=True)
            embed.add_field(name="Roles", value=f"{len(user.roles) - 1} roles", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            return await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            return await interaction.response.send_message(
                embed=error_embed("Please specify a user to check."),
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """Load the AdvancedSecurity cog."""
    # Clear any existing commands that might conflict
    try:
        existing_commands = bot.tree.get_commands()
        for cmd in existing_commands:
            if cmd.name == "defense":
                bot.tree.remove_command(cmd.name)
    except Exception as e:
        pass  # Ignore errors during cleanup
    
    await bot.add_cog(AdvancedSecurity(bot))
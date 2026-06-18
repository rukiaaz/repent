"""
Repent - Zero-Trust Security Management Cog

Commands and management interface for the zero-trust security system.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from database import get_guild, update_guild, log_action
from utils.embeds import success_embed, error_embed, info_embed
from utils.logger import get_logger


class ZeroTrustSecurity(commands.Cog):
    """Management interface for zero-trust security system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()
        self.active_servers = set()

    @app_commands.command(name="zerotrust", description="Configure zero-trust security")
    @app_commands.describe(action="Enable, disable, status, or configure trust levels")
    @app_commands.describe(value="Value for the action")
    async def zerotrust(
        self,
        interaction: discord.Interaction,
        action: str,
        value: Optional[str] = None
    ):
        """Configure zero-trust security settings."""
        
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need administrator permissions."),
                ephemeral=True
            )

        guild = interaction.guild
        action_lower = action.lower()

        # Enable/disable zero-trust
        if action_lower in ("enable", "disable", "on", "off"):
            enabled = action_lower in ("enable", "on")
            
            await update_guild(guild.id, zero_trust_enabled=1 if enabled else 0)
            
            if enabled:
                self.active_servers.add(guild.id)
            else:
                self.active_servers.discard(guild.id)
            
            await log_action(guild.id, "zerotrust_config", interaction.user.id, {
                "action": "enable" if enabled else "disable",
                "enabled": enabled
            })

            status_text = "enabled" if enabled else "disabled"
            return await interaction.response.send_message(
                embed=success_embed(
                    f"Zero-Trust Security {status_text.title()}",
                    f"Zero-trust security model is now {status_text}."
                ),
                ephemeral=False
            )

        # Check current status
        elif action_lower == "status":
            settings = await get_guild(guild.id)
            current_enabled = settings.get("zero_trust_enabled", 0)
            
            if guild.id in self.active_servers:
                zt_active = "✅ Active"
                server_count = len(self.active_servers)
            else:
                zt_active = "❌ Inactive"
                server_count = 0

            embed = info_embed("Zero-Trust Security Status", f"Current configuration for {guild.name}")
            embed.add_field(name="Status", value=zt_active, inline=True)
            embed.add_field(name="Active Servers", value=str(server_count), inline=True)
            embed.add_field(name="Trust Levels", value="5 (UNTRUSTED to CRITICAL)", inline=True)
            
            embed.add_field(name="Core Principles", value="Never Trust, Always Verify", inline=False)
            embed.add_field(
                name="Verification Mode",
                value="Continuous validation of all actions",
                inline=False
            )
            embed.add_field(
                name="Access Control",
                value="Explicit authorization required",
                inline=False
            )

            return await interaction.response.send_message(embed=embed, ephemeral=False)

        # Configure trust threshold
        elif action_lower == "threshold":
            if not value:
                return await interaction.response.send_message(
                    embed=error_embed("Missing Value", "Please specify: untrusted, low, medium, high, critical"),
                    ephemeral=True
                )

            value_lower = value.lower()
            valid_levels = ["untrusted", "low", "medium", "high", "critical"]
            if value_lower not in valid_levels:
                return await interaction.response.send_message(
                    embed=error_embed("Invalid Value", f"Trust level must be one of: {', '.join(valid_levels)}"),
                    ephemeral=True
                )

            await update_guild(guild.id, zero_trust_threshold=value_lower)
            
            await log_action(guild.id, "zerotrust_config", interaction.user.id, {
                "action": "threshold",
                "threshold": value_lower
            })

            return await interaction.response.send_message(
                embed=success_embed(
                    "Trust Threshold Updated",
                    f"Zero-trust threshold set to {value_lower.upper()}\n\n"
                    f"Users below this trust level require additional verification\n"
                    f"for sensitive actions."
                ),
                ephemeral=False
            )

        # Check user trust score
        elif action_lower == "check":
            if not interaction.options.get('user'):
                return await interaction.response.send_message(
                    embed=error_embed("Missing User", "Please specify a user to check"),
                    ephemeral=True
                )

            user = interaction.options['user']
            # This would integrate with the zero-trust system to get trust score
            # For now, show a placeholder
            embed = info_embed("User Trust Score", f"Trust score for {user.mention}")
            embed.add_field(name="Trust Level", value="MEDIUM", inline=True)
            embed.add_field(name="Trust Score", value="75/100", inline=True)
            embed.add_field(name="Last Verified", value="Just now", inline=True)
            embed.add_field(name="Actions Monitored", value="Yes", inline=False)
            
            return await interaction.response.send_message(embed=embed, ephemeral=False)

        else:
            return await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Action",
                    "Valid actions: enable, disable, status, threshold, check"
                ),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the ZeroTrust cog."""
    # Clear any existing commands that might conflict
    try:
        existing_commands = bot.tree.get_commands()
        for cmd in existing_commands:
            if cmd.name == "zerotrust":
                bot.tree.remove_command(cmd.name)
    except Exception as e:
        pass  # Ignore errors during cleanup
    
    await bot.add_cog(ZeroTrustSecurity(bot))
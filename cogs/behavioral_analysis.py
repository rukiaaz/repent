"""
Repent - Behavioral Analysis Management Cog

Commands and management interface for the behavioral analysis system.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database import get_guild, update_guild, log_action
from utils.embeds import success_embed, error_embed, info_embed
from utils.logger import get_logger


class BehavioralAnalysis(commands.Cog):
    """Management interface for behavioral analysis system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()
        self.active_servers = set()

    @app_commands.command(name="behavior", description="Configure behavioral analysis")
    @app_commands.describe(action="Enable, disable, status, or configure analysis")
    @app_commands.describe(value="Value for the action")
    async def behavior(
        self,
        interaction: discord.Interaction,
        action: str,
        value: Optional[str] = None
    ):
        """Configure behavioral analysis settings."""
        
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need administrator permissions."),
                ephemeral=True
            )

        guild = interaction.guild
        action_lower = action.lower()

        # Enable/disable behavioral analysis
        if action_lower in ("enable", "disable", "on", "off"):
            enabled = action_lower in ("enable", "on")
            
            await update_guild(guild.id, behavioral_analysis_enabled=1 if enabled else 0)
            
            if enabled:
                self.active_servers.add(guild.id)
            else:
                self.active_servers.discard(guild.id)
            
            await log_action(guild.id, "behavioral_analysis_config", interaction.user.id, {
                "action": "enable" if enabled else "disable",
                "enabled": enabled
            })

            status_text = "enabled" if enabled else "disabled"
            return await interaction.response.send_message(
                embed=success_embed(
                    f"Behavioral Analysis {status_text.title()}",
                    f"Behavioral profiling is now {status_text}."
                ),
                ephemeral=False
            )

        # Check current status
        elif action_lower == "status":
            settings = await get_guild(guild.id)
            current_enabled = settings.get("behavioral_analysis_enabled", 0)
            
            if guild.id in self.active_servers:
                ba_active = "✅ Active"
                server_count = len(self.active_servers)
            else:
                ba_active = "❌ Inactive"
                server_count = 0

            embed = info_embed("Behavioral Analysis Status", f"Current configuration for {guild.name}")
            embed.add_field(name="Status", value=ba_active, inline=True)
            embed.add_field(name="Active Servers", value=str(server_count), inline=True)
            embed.add_field(name="Profiled Users", value="Calculating...", inline=True)
            
            embed.add_field(name="Detection Types", value="6 Types", inline=False)
            embed.add_field(
                name="1. Velocity",
                value="Unusually fast action detection",
                inline=False
            )
            embed.add_field(
                name="2. Temporal",
                value="Unusual timing pattern detection",
                inline=False
            )
            embed.add_field(
                name="3. Sequential",
                value="Unusual action sequence detection",
                inline=False
            )
            embed.add_field(
                name="4. Permission",
                value="Unexpected permission usage detection",
                inline=False
            )
            embed.add_field(
                name="5. Social",
                value="Unusual social interaction detection",
                inline=False
            )
            embed.add_field(
                name="6. Cross-Guild",
                value="Correlated anomaly detection across guilds",
                inline=False
            )

            return await interaction.response.send_message(embed=embed, ephemeral=False)

        # Configure sensitivity
        elif action_lower == "sensitivity":
            if not value:
                return await interaction.response.send_message(
                    embed=error_embed("Missing Value", "Please specify: low, medium, or high"),
                    ephemeral=True
                )

            value_lower = value.lower()
            if value_lower not in ("low", "medium", "high"):
                return await interaction.response.send_message(
                    embed=error_embed("Invalid Value", "Sensitivity must be: low, medium, or high"),
                    ephemeral=True
                )

            await update_guild(guild.id, behavioral_analysis_sensitivity=value_lower)
            
            await log_action(guild.id, "behavioral_analysis_config", interaction.user.id, {
                "action": "sensitivity",
                "sensitivity": value_lower
            })

            return await interaction.response.send_message(
                embed=success_embed(
                    "Analysis Sensitivity Updated",
                    f"Behavioral analysis sensitivity set to {value_lower.title()}\n\n"
                    f"Low: Conservative detection, fewer false positives\n"
                    f"Medium: Balanced detection\n"
                    f"High: Aggressive detection, maximum anomaly detection"
                ),
                ephemeral=False
            )

        else:
            return await interaction.response.send_message(
                embed=error_embed(
                    "Invalid Action",
                    "Valid actions: enable, disable, status, sensitivity"
                ),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the BehavioralAnalysis cog."""
    await bot.add_cog(BehavioralAnalysis(bot))
"""
Repent - Multi-Layer Defense Management Cog

Commands and management interface for the multi-layer defense system.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from database import get_guild, update_guild, log_action
from utils.embeds import success_embed, error_embed, info_embed
from utils.logger import get_logger
from utils.multi_layer_defense import MultiLayerDefenseSystem, ThreatLevel


class MultiLayerDefense(commands.Cog):
    """Management interface for multi-layer defense system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()
        self.defense_system = MultiLayerDefenseSystem()
        self.active_servers = set()

    @app_commands.command(name="defense", description="Configure multi-layer defense")
    @app_commands.describe(action="Enable, disable, status, or configure layers")
    @app_commands.describe(value="Value for the action")
    async def defense(
        self,
        interaction: discord.Interaction,
        action: str,
        value: Optional[str] = None
    ):
        """Configure multi-layer defense settings."""
        
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need administrator permissions."),
                ephemeral=True
            )

        guild = interaction.guild
        action_lower = action.lower()

        # Enable/disable multi-layer defense
        if action_lower in ("enable", "disable", "on", "off"):
            enabled = action_lower in ("enable", "on")
            
            await update_guild(guild.id, multi_layer_defense_enabled=1 if enabled else 0)
            
            if enabled:
                self.active_servers.add(guild.id)
            else:
                self.active_servers.discard(guild.id)
            
            await log_action(guild.id, "multilayer_defense_config", interaction.user.id, {
                "action": "enable" if enabled else "disable",
                "enabled": enabled
            })

            status_text = "enabled" if enabled else "disabled"
            return await interaction.response.send_message(
                embed=success_embed(
                    f"Multi-Layer Defense {status_text.title()}",
                    f"Advanced multi-layer defense is now {status_text}."
                ),
                ephemeral=False
            )

        # Check current status
        elif action_lower == "status":
            settings = await get_guild(guild.id)
            current_enabled = settings.get("multi_layer_defense_enabled", 0)
            
            if guild.id in self.active_servers:
                defense_active = "✅ Active"
                server_count = len(self.active_servers)
            else:
                defense_active = "❌ Inactive"
                server_count = 0

            embed = info_embed("Multi-Layer Defense Status", f"Current configuration for {guild.name}")
            embed.add_field(name="Status", value=defense_active, inline=True)
            embed.add_field(name="Active Servers", value=str(server_count), inline=True)
            embed.add_field(name="Threat Levels", value="5 (SAFE to CRITICAL)", inline=True)
            
            embed.add_field(name="Defense Layers", value="5 Layers", inline=False)
            embed.add_field(
                name="Layer 0",
                value="Pre-Flight Validation (Rate limiting, sanitization)",
                inline=False
            )
            embed.add_field(
                name="Layer 1",
                value="Behavioral Analysis (User profiling, anomaly detection)",
                inline=False
            )
            embed.add_field(
                name="Layer 2",
                value="Contextual Analysis (Temporal, social context)",
                inline=False
            )
            embed.add_field(
                name="Layer 3",
                value="Pattern Recognition (Attack patterns)",
                inline=False
            )
            embed.add_field(
                name="Layer 4",
                value="Decision Engine (Risk scoring)",
                inline=False
            )

            return await interaction.response.send_message(embed=embed, ephemeral=False)

        # Configure sensitivity/threshold
        elif action_lower in ("sensitivity", "threshold"):
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

            await update_guild(guild.id, multi_layer_defense_sensitivity=value_lower)
            
            await log_action(guild.id, "multilayer_defense_config", interaction.user.id, {
                "action": "sensitivity",
                "sensitivity": value_lower
            })

            return await interaction.response.send_message(
                embed=success_embed(
                    "Defense Sensitivity Updated",
                    f"Multi-layer defense sensitivity set to {value_lower.title()}\n\n"
                    f"Low: Conservative approach, fewer false positives\n"
                    f"Medium: Balanced detection\n"
                    f"High: Aggressive detection, maximum protection"
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
    """Load the MultiLayerDefense cog."""
    await bot.add_cog(MultiLayerDefense(bot))
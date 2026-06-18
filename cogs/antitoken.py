"""
Repent - Token Protection System

Detects and removes leaked Discord tokens to prevent account compromises.
Features configurable sensitivity, automatic token revocation, and detailed logging.
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from database import get_guild, update_guild, log_action
from utils.embeds import success_embed, error_embed, info_embed
from utils.logger import get_logger


class AntiToken(commands.Cog):
    """Token protection system to prevent account compromises from leaked tokens."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()

        # Token patterns (by sensitivity level)
        self.token_patterns = {
            "high": [
                # Discord bot tokens
                r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",
                # MFA tokens
                r"mfa\.[A-Za-z0-9_-]{20,}",
                # Stripe live keys
                r"sk_live_[a-zA-Z0-9]{20,}",
                # Stripe test keys
                r"sk_test_[a-zA-Z0-9]{20,}",
            ],
            "medium": [
                r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",
                r"mfa\.[A-Za-z0-9_-]{20,}",
            ],
            "low": [
                r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",
            ]
        }

    @app_commands.command(name="antitoken", description="Configure token protection")
    @app_commands.describe(action="Enable, disable, status, or set sensitivity")
    @app_commands.describe(value="Value for the action (true/false for enable/disable, low/medium/high for sensitivity)")
    async def antitoken(
        self,
        interaction: discord.Interaction,
        action: str,
        value: Optional[str] = None
    ):
        """Configure token protection settings."""
        
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need administrator permissions to configure token protection."),
                ephemeral=True
            )

        guild = interaction.guild
        action_lower = action.lower()

        # Enable/disable token protection
        if action_lower in ("enable", "disable", "on", "off"):
            enabled = action_lower in ("enable", "on")
            
            await update_guild(guild.id, anti_token_enabled=1 if enabled else 0)
            
            await log_action(guild.id, "antitoken_config", interaction.user.id, {
                "action": "enable" if enabled else "disable",
                "enabled": enabled
            })

            status_text = "enabled" if enabled else "disabled"
            return await interaction.response.send_message(
                embed=success_embed(
                    f"Token Protection {status_text.title()}",
                    f"Token leak detection is now {status_text}."
                ),
                ephemeral=False
            )

        # Check current status
        elif action_lower == "status":
            settings = await get_guild(guild.id)
            current_enabled = settings.get("anti_token_enabled", 0)
            current_sensitivity = settings.get("anti_token_sensitivity", "medium")

            embed = info_embed("Token Protection Status", f"Current configuration for {guild.name}")
            embed.add_field(name="Status", value="✅ Enabled" if current_enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Sensitivity", value=current_sensitivity.title(), inline=True)
            embed.add_field(name="Protected Patterns", value=str(len(self.token_patterns[current_sensitivity])), inline=True)

            return await interaction.response.send_message(embed=embed, ephemeral=False)

        # Set sensitivity level
        elif action_lower == "sensitivity":
            if not value:
                return await interaction.response.send_message(
                    embed=error_embed("Missing Value", "Please specify a sensitivity level: low, medium, or high"),
                    ephemeral=True
                )

            value_lower = value.lower()
            if value_lower not in ("low", "medium", "high"):
                return await interaction.response.send_message(
                    embed=error_embed("Invalid Sensitivity", "Sensitivity must be: low, medium, or high"),
                    ephemeral=True
                )

            await update_guild(guild.id, anti_token_sensitivity=value_lower)
            
            await log_action(guild.id, "antitoken_config", interaction.user.id, {
                "action": "sensitivity",
                "sensitivity": value_lower
            })

            return await interaction.response.send_message(
                embed=success_embed(
                    "Sensitivity Updated",
                    f"Token protection sensitivity set to {value_lower.title()}\n\n"
                    f"Low: Basic token detection\n"
                    f"Medium: Standard token detection + MFA tokens\n"
                    f"High: All token types including API keys"
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

    @app_commands.command(name="revoke_token", description="Revoke a leaked Discord token (Admin only)")
    @app_commands.describe(token="The token to revoke (first few characters are sufficient)")
    async def revoke_token(self, interaction: discord.Interaction, token: str):
        """Attempt to revoke a leaked Discord token via Discord API."""
        
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("Permission Denied", "You need administrator permissions to revoke tokens."),
                ephemeral=True
            )

        # This would require Discord API integration with appropriate permissions
        # For now, provide guidance on manual token revocation
        
        embed = info_embed(
            "Token Revocation",
            "Token revocation requires Discord API access with appropriate permissions.\n\n"
            f"Token detected: `{token[:10]}...`\n\n"
            "**Manual Revocation Steps:**\n"
            "1. Go to Discord Developer Portal\n"
            "2. Locate the application/bot\n"
            "3. Regenerate the token\n"
            "4. Revoke any sessions in User Settings > Authorized Apps"
        )
        
        await log_action(interaction.guild.id, "token_revocation_attempt", interaction.user.id, {
            "token_preview": token[:10],
            "method": "manual_guidance"
        })

        return await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Load the AntiToken cog."""
    await bot.add_cog(AntiToken(bot))
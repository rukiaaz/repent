"""
Balance - Premium System
Monetization and premium features for the bot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed

class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Premium tiers configuration
        self.tiers = {
            "free": {
                "name": "Free",
                "features": ["Basic antinuke", "Basic automod", "Verification", "Welcome messages"],
                "max_servers": 1,
                "max_members_per_server": 1000,
                "advanced_features": False
            },
            "basic": {
                "name": "Basic",
                "features": ["All free features", "Multi-layer defense", "Behavioral analysis", "Ticket system"],
                "max_servers": 5,
                "max_members_per_server": 5000,
                "advanced_features": True
            },
            "pro": {
                "name": "Pro",
                "features": ["All basic features", "Zero-trust security", "Captcha system", "Priority support"],
                "max_servers": 10,
                "max_members_per_server": 25000,
                "advanced_features": True
            },
            "enterprise": {
                "name": "Enterprise",
                "features": ["All pro features", "Custom integrations", "Dedicated support", "SLA guarantee"],
                "max_servers": -1,  # Unlimited
                "max_members_per_server": -1,  # Unlimited
                "advanced_features": True
            }
        }

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    @app_commands.command(name="premium", description="View premium status and features")
    async def premium(self, interaction: discord.Interaction):
        guild = interaction.guild
        settings = await get_guild(guild.id)
        
        current_tier = settings.get("premium_tier", "free")
        tier_config = self.tiers.get(current_tier, self.tiers["free"])
        
        embed = discord.Embed(title="💎 Premium Status", color=0xFFD700)
        embed.add_field(name="Current Tier", value=tier_config["name"], inline=True)
        embed.add_field(name="Max Servers", value=str(tier_config["max_servers"]) if tier_config["max_servers"] > 0 else "Unlimited", inline=True)
        embed.add_field(name="Max Members", value=str(tier_config["max_members_per_server"]) if tier_config["max_members_per_server"] > 0 else "Unlimited", inline=True)
        
        features_list = "\n".join([f"✅ {f}" for f in tier_config["features"]])
        embed.add_field(name="Features", value=features_list, inline=False)
        
        if current_tier == "free":
            embed.add_field(
                name="Upgrade",
                value="Contact support or visit our website to upgrade to premium!",
                inline=False
            )
        
        return await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="premium-features", description="View all premium tier features")
    async def premium_features(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💎 Premium Tiers", color=0xFFD700)
        embed.set_footer(text="Contact support to upgrade your plan")
        
        for tier_id, tier_config in self.tiers.items():
            if tier_id == "free":
                continue
            
            features_list = "\n".join([f"• {f}" for f in tier_config["features"]])
            embed.add_field(
                name=f"{tier_config['name']} Tier",
                value=f"Max Servers: {tier_config['max_servers'] if tier_config['max_servers'] > 0 else 'Unlimited'}\n\nFeatures:\n{features_list}",
                inline=False
            )
        
        return await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="premium-set", description="Set premium tier (Owner only)")
    @app_commands.describe(guild_id="Server ID", tier="Premium tier")
    async def premium_set(self, interaction: discord.Interaction, guild_id: str, tier: str):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Owner only."), ephemeral=True)

        tier = tier.lower()
        if tier not in self.tiers:
            return await interaction.response.send_message(
                embed=error_embed(f"Invalid tier. Use: {', '.join(self.tiers.keys())}"),
                ephemeral=True
            )

        # This would update the premium_servers table
        # For now, update guild config
        try:
            guild_id_int = int(guild_id)
            await update_guild(guild_id_int, premium_tier=tier)
            return await interaction.response.send_message(
                embed=success_embed("Premium Updated", f"Guild {guild_id} is now {self.tiers[tier]['name']} tier."),
                ephemeral=False
            )
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Invalid guild ID."),
                ephemeral=True
            )

    @app_commands.command(name="premium-usage", description="View premium usage statistics (Admin only)")
    async def premium_usage(self, interaction: discord.Interaction):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        current_tier = settings.get("premium_tier", "free")
        tier_config = self.tiers.get(current_tier, self.tiers["free"])
        
        member_count = guild.member_count
        server_count = 1  # This would query premium_servers table
        
        embed = discord.Embed(title="📊 Premium Usage", color=0xFFD700)
        embed.add_field(name="Current Tier", value=tier_config["name"], inline=True)
        embed.add_field(name="Members", value=f"{member_count} / {tier_config['max_members_per_server'] if tier_config['max_members_per_server'] > 0 else '∞'}", inline=True)
        embed.add_field(name="Servers", value=f"{server_count} / {tier_config['max_servers'] if tier_config['max_servers'] > 0 else '∞'}", inline=True)
        
        # Check limits
        members_over = max(0, member_count - tier_config['max_members_per_server']) if tier_config['max_members_per_server'] > 0 else 0
        if members_over > 0:
            embed.add_field(name="⚠️ Warning", value=f"{members_over} members over limit. Consider upgrading.", inline=False)
        
        return await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    # Temporarily disabled due to Discord's 100 global command limit
    # Re-enable after consolidating other commands or using guild-specific commands
    # await bot.add_cog(Premium(bot))
    pass
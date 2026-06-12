"""
Balance - URL Scanning and Link Protection
Protects users from malicious URLs and phishing links.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed

class URLScanner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Common malicious domains (would use VirusTotal API in production)
        self.malicious_domains = set([
            "discord-gift.com",
            "discord nitro.com",
            "free-discord-nitro.com",
            "steam-community.com",
            "steampowered.com",
        ])
        # Known phishing patterns
        self.phishing_patterns = [
            r"discord\.gift",
            r"steamcommunity\.com\/gifts",
            r"free.*nitro",
            r"free.*steam",
            r"account.*suspended",
            r"verify.*account",
        ]

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    def extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        return re.findall(url_pattern, text, re.IGNORECASE)

    def is_malicious(self, url: str) -> bool:
        """Check if URL is malicious."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Check against known malicious domains
        if domain in self.malicious_domains:
            return True
        
        # Check against phishing patterns
        for pattern in self.phishing_patterns:
            if re.search(pattern, url.lower()):
                return True
        
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Scan messages for malicious URLs."""
        if message.author.bot:
            return
        
        guild = message.guild
        if not guild:
            return
        
        settings = await get_guild(guild.id)
        if not settings.get("url_scan_enabled", 0):
            return
        
        # Check if user is whitelisted
        if settings.get("url_scan_whitelist", "").find(str(message.author.id)) != -1:
            return
        
        # Extract URLs
        urls = self.extract_urls(message.content)
        
        for url in urls:
            if self.is_malicious(url):
                # Delete the message
                try:
                    await message.delete()
                    
                    # Warn the user
                    warning_msg = await message.channel.send(
                        embed=error_embed(
                            "Malicious Link Detected",
                            f"{message.author.mention}, your message contained a malicious URL and has been removed."
                        )
                    )
                    
                    # Log the action
                    settings = await get_guild(guild.id)
                    log_channel_id = settings.get("log_channel", 0)
                    if log_channel_id:
                        log_channel = guild.get_channel(log_channel_id)
                        if log_channel:
                            embed = discord.Embed(
                                title="🔗 Malicious URL Blocked",
                                color=0xFF4444,
                                timestamp=discord.utils.utcnow()
                            )
                            embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})", inline=True)
                            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                            embed.add_field(name="URL", value=url[:200], inline=False)
                            embed.add_field(name="Message", value=message.content[:200], inline=False)
                            await log_channel.send(embed=embed)
                    
                    # Delete warning after 5 seconds
                    await asyncio.sleep(5)
                    await warning_msg.delete()
                    
                except discord.Forbidden:
                    pass  # Can't delete, notify in logs if possible

    @app_commands.command(name="urlscan", description="Configure URL scanning (Admin only)")
    @app_commands.describe(action="enable, disable, whitelist, or status")
    async def urlscan(self, interaction: discord.Interaction, action: str, user: discord.Member = None):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        action_l = action.lower()

        if action_l == "enable":
            await update_guild(guild.id, url_scan_enabled=1)
            return await interaction.response.send_message(
                embed=success_embed("URL Scanning Enabled", "Malicious URL protection has been enabled."),
                ephemeral=False
            )

        elif action_l == "disable":
            await update_guild(guild.id, url_scan_enabled=0)
            return await interaction.response.send_message(
                embed=success_embed("URL Scanning Disabled", "Malicious URL protection has been disabled."),
                ephemeral=False
            )

        elif action_l == "whitelist":
            if not user:
                return await interaction.response.send_message(embed=error_embed("Please specify a user to whitelist."), ephemeral=True)
            
            whitelist = settings.get("url_scan_whitelist", "")
            if str(user.id) in whitelist:
                # Remove from whitelist
                whitelist = whitelist.replace(str(user.id), "")
                await update_guild(guild.id, url_scan_whitelist=whitelist)
                return await interaction.response.send_message(
                    embed=success_embed("User Removed", f"{user.mention} has been removed from the URL scan whitelist."),
                    ephemeral=False
                )
            else:
                # Add to whitelist
                whitelist = f"{whitelist},{user.id}" if whitelist else str(user.id)
                await update_guild(guild.id, url_scan_whitelist=whitelist)
                return await interaction.response.send_message(
                    embed=success_embed("User Whitelisted", f"{user.mention} has been added to the URL scan whitelist."),
                    ephemeral=False
                )

        elif action_l == "status":
            enabled = settings.get("url_scan_enabled", 0)
            whitelist = settings.get("url_scan_whitelist", "")
            
            embed = discord.Embed(title="🔗 URL Scanning Status", color=0x4488FF)
            embed.add_field(name="Status", value="✅ Enabled" if enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Whitelisted Users", value=str(whitelist.count(",") + 1) if whitelist else "0", inline=True)
            return await interaction.response.send_message(embed=embed, ephemeral=False)

        else:
            return await interaction.response.send_message(
                embed=error_embed("Use: `enable`, `disable`, `whitelist [user]`, or `status`."),
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(URLScanner(bot))
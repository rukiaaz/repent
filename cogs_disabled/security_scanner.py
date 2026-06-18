"""Repent - Advanced Security Scanner

Anti-token grabber detection, malicious link scanning, and security enhancements.
"""

from __future__ import annotations

import re
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import aiohttp
import asyncio

from config import OWNER_ID
from database import get_guild, update_guild, log_action
from utils.embeds import warning_embed, error_embed, success_embed, info_embed
from utils.logger import get_logger


class SecurityScanner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()
        self.session = None
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Clean up HTTP session when cog is unloaded."""
        if self.session:
            await self.session.close()

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    # Known token grabbing patterns
    TOKEN_PATTERNS = [
        # Common token grabber domains
        r'github\.com/[^/]+/[^/]+/blob/master/[^/]+/index\.js',
        r'cdn\.discord(app)?\.com/attachments/.*\.js',
        r'discord\.gg/.* giveaway.*token',
        r'free.*nitro.*token',
        r'claim.*token.*free',
        r'token.*generator.*free',
        r'boost.*token.*reward',
        r'discord.*token.*login',
        r'login.*with.*token',
        r'token.*for.*nitro',
        # Suspicious URL patterns
        r'discordtoken\.com',
        r'freediscordtokens?\.(com|net|org)',
        r'claimdiscordgift\.com',
        r'discordgift\.card',
        r'discord\.com/api.*token',
        r'discord\.com.*grant.*token',
        r'api\.discord\.com.*entitlements',
        # Suspicious redirect patterns
        r'bit\.ly.*discord.*token',
        r'tinyurl.*discord.*token',
        r'short.*link.*discord.*token',
    ]

    MALICIOUS_DOMAINS = [
        'discordtoken.com',
        'freediscordtokens.com',
        'freediscordtokens.net',
        'freediscordtokens.org',
        'claimdiscordgift.com',
        'discordgift.card',
    ]

    # ── Security Scanner Commands ──
    @app_commands.command(name="antitoken", description="Configure anti-token grabber detection (Admin only)")
    @app_commands.describe(
        action="enable, disable, or check",
        url="URL to check (for check action)"
    )
    async def anti_token_command(
        self,
        interaction: discord.Interaction,
        action: str,
        url: str = None
    ):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Administrator required."),
                ephemeral=True
            )
        
        guild = interaction.guild
        action_l = action.lower()
        
        if action_l == "enable":
            await update_guild(guild.id, anti_token_enabled=1)
            return await interaction.response.send_message(
                embed=success_embed("Anti-Token Grabber Enabled", 
                "Token grabber detection is now active. Suspicious links will be blocked."),
                ephemeral=False
            )
        
        elif action_l == "disable":
            await update_guild(guild.id, anti_token_enabled=0)
            return await interaction.response.send_message(
                embed=success_embed("Anti-Token Grabber Disabled", 
                "Token grabber detection has been disabled."),
                ephemeral=False
            )
        
        elif action_l == "check":
            if not url:
                return await interaction.response.send_message(
                    embed=error_embed("URL is required for checking."),
                    ephemeral=True
                )
            
            await interaction.response.defer(thinking=True)
            
            result = await self._scan_url(url)
            
            embed = discord.Embed(
                title="🔒 URL Security Scan",
                description=f"Scanning: {url}",
                color=0x4488FF
            )
            
            embed.add_field(name="Safety Score", value=f"{result['score']}/10", inline=True)
            embed.add_field(name="Classification", value=result['classification'], inline=True)
            embed.add_field(name="Threat Level", value=result['threat_level'], inline=True)
            
            if result['suspicious_patterns']:
                embed.add_field(
                    name="Suspicious Patterns",
                    value=", ".join(result['suspicious_patterns']),
                    inline=False
                )
            
            if result['domain_blacklisted']:
                embed.add_field(
                    name="⚠️ Warning",
                    value="This domain is known for token grabbing",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        else:
            return await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: enable, disable, or check"),
                ephemeral=True
            )

    # ── Message Scanning ──
    async def _scan_url(self, url: str) -> dict:
        """Scan a URL for malicious content."""
        result = {
            'url': url,
            'score': 10,  # 10 = safe, 0 = dangerous
            'classification': 'Unknown',
            'threat_level': 'Low',
            'suspicious_patterns': [],
            'domain_blacklisted': False
        }
        
        # Check domain blacklist
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            if domain in self.MALICIOUS_DOMAINS:
                result['domain_blacklisted'] = True
                result['score'] = 0
                result['classification'] = 'Malicious'
                result['threat_level'] = 'Critical'
                return result
        except:
            pass
        
        # Check against patterns
        suspicious_found = []
        for pattern in self.TOKEN_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                suspicious_found.append(pattern)
                result['score'] -= 3
        
        if suspicious_found:
            result['suspicious_patterns'] = suspicious_found
            result['classification'] = 'Suspicious'
            result['threat_level'] = 'High'
        
        # Score classification
        if result['score'] >= 8:
            result['threat_level'] = 'Low'
        elif result['score'] >= 5:
            result['threat_level'] = 'Medium'
        else:
            result['threat_level'] = 'High'
        
        if result['score'] == 0:
            result['classification'] = 'Malicious'
        elif result['score'] < 5:
            result['classification'] = 'Suspicious'
        else:
            result['classification'] = 'Safe'
        
        return result

    # ── Message Listener for Scanning ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Scan messages for token grabbing attempts."""
        if not message.guild:
            return
        if message.author.bot:
            return
        if message.author.guild_permissions.administrator:
            return  # Skip admins
        
        guild = message.guild
        settings = await get_guild(guild.id)
        
        if not settings.get("anti_token_enabled", 0):
            return
        
        # Check if message contains URLs
        urls = re.findall(r'https?://[^\s]+', message.content.lower())
        
        for url in urls:
            result = await self._scan_url(url)
            
            if result['score'] < 5:  # Suspicious or malicious
                try:
                    await message.delete()
                    
                    # Warn user
                    warning_msg = f"⚠️ Your message contained a suspicious link and has been deleted.\n\n**URL:** {url}\n**Reason:** {result['classification']}\n**Threat Level:** {result['threat_level']}"
                    
                    try:
                        await message.author.send(warning_msg, delete_after=30)
                    except:
                        pass
                    
                    # Log the action
                    await log_action(guild.id, "token_grabber_blocked", message.author.id, {
                        "url": url,
                        "classification": result['classification'],
                        "threat_level": result['threat_level'],
                        "patterns": result['suspicious_patterns']
                    })
                    
                    # Notify staff if configured
                    self._notify_staff(guild, message.author, url, result, message)
                    
                    self.logger.security("TOKEN_GRABBER_BLOCKED", f"Blocked token grabber link: {url} from {message.author.id}", guild_id=guild.id, user_id=message.author.id)
                    
                except Exception as e:
                    self.logger.error(f"Failed to delete suspicious message: {e}", exc_info=True)

    async def _notify_staff(self, guild: discord.Guild, author: discord.Member, url: str, scan_result: dict, message: discord.Message):
        """Notify staff about blocked token grabber attempt."""
        try:
            settings = await get_guild(guild.id)
            mod_channel_id = settings.get("mod_channel", 0)
            if not mod_channel_id:
                return
            
            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel:
                return
            
            embed = warning_embed(
                f"🚨 Token Grabber Blocked",
                f"{author.mention} ({author.id}) attempted to send a token grabbing link."
            )
            embed.add_field(name="Blocked URL", value=url, inline=False)
            embed.add_field(name="Classification", value=scan_result['classification'], inline=True)
            embed.add_field(name="Threat Level", value=scan_result['threat_level'], inline=True)
            if scan_result['suspicious_patterns']:
                embed.add_field(name="Patterns", value=", ".join(scan_result['suspicious_patterns']), inline=False)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.set_footer(text="User has been warned | User is still on the server")
            embed.timestamp = datetime.now(timezone.utc)
            
            await mod_channel.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Failed to notify staff about token grabber: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityScanner(bot))
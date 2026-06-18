"""Repent - External Application & Bot Detection System

Monitors bot additions, OAuth2 authorizations, and external applications
with advanced threat detection and risk assessment.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque

import discord
from discord.ext import commands

from database import get_guild, update_guild, log_action
from utils.embeds import error_embed, info_embed, success_embed, alert_embed
from config import OWNER_ID


class ExternalAppRiskScorer:
    """Risk assessment system for external applications and bots."""
    
    # High-risk bot patterns
    SUSPICIOUS_BOT_PATTERNS = [
        r'nuke', r'raid', r'spam', r'crash', r'boom', 
        r'destroy', r'kill', r'hack', r'exploit'
    ]
    
    # High-risk permissions
    DANGEROUS_PERMISSIONS = {
        'administrator', 'ban_members', 'kick_members', 
        'manage_roles', 'manage_channels', 'manage_guild',
        'manage_webhooks', 'mention_everyone'
    }
    
    def __init__(self):
        # Known safe bots (whitelist)
        self.safe_bot_ids: Set[int] = set()
        
        # Bot reputation scores: {bot_id: score (-10 to 10)}
        self.bot_reputation: Dict[int, int] = {}
        
        # User bot addition history: {user_id: [(bot_id, timestamp, guild_id)]}
        self.user_bot_history: Dict[int, List[Tuple[int, datetime, int]]] = {}
        
        # OAuth2 authorization tracking: {user_id: [(app_id, permissions, timestamp)]}
        self.oauth_history: Dict[int, List[Tuple[str, str, datetime]]] = {}
    
    def calculate_bot_risk(self, bot: discord.Member, adder: discord.Member) -> Dict[str, any]:
        """Calculate risk score for a bot being added to a server."""
        risk_factors = []
        risk_score = 0
        
        # Check bot age
        bot_age = (datetime.now(timezone.utc) - bot.created_at).days
        if bot_age < 7:
            risk_score += 3
            risk_factors.append(f"New bot ({bot_age} days)")
        elif bot_age < 30:
            risk_score += 1
            risk_factors.append(f"Recent bot ({bot_age} days)")
        
        # Check bot username patterns
        import re
        username_lower = bot.name.lower()
        for pattern in self.SUSPICIOUS_BOT_PATTERNS:
            if pattern in username_lower:
                risk_score += 2
                risk_factors.append(f"Suspicious name pattern: {pattern}")
        
        # Check for numbers/special characters in name
        if re.search(r'\d{4,}', username_lower):
            risk_score += 1
            risk_factors.append("Many numbers in username")
        
        # Check bot avatar
        if not bot.avatar or bot.default_avatar:
            risk_score += 1
            risk_factors.append("No custom avatar")
        
        # Check if bot is verified by Discord
        if not bot.public_flags.verified_bot:
            risk_score += 2
            risk_factors.append("Unverified bot")
        
        # Check user's bot addition history
        if adder.id in self.user_bot_history:
            recent_bots = [
                b for b in self.user_bot_history[adder.id] 
                if (datetime.now(timezone.utc) - b[1]).total_seconds() < 3600
            ]
            if len(recent_bots) > 3:
                risk_score += 3
                risk_factors.append(f"User added {len(recent_bots)} bots in last hour")
        
        # Check bot reputation
        if bot.id in self.bot_reputation:
            rep_score = self.bot_reputation[bot.id]
            if rep_score < -5:
                risk_score += 4
                risk_factors.append("Poor bot reputation")
            elif rep_score > 5:
                risk_score = max(0, risk_score - 2)  # Reduce risk for trusted bots
                risk_factors.append("Good bot reputation")
        
        # Cap risk score at 10
        risk_score = min(risk_score, 10)
        
        return {
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "risk_level": "CRITICAL" if risk_score >= 7 else "HIGH" if risk_score >= 5 else "MEDIUM" if risk_score >= 3 else "LOW"
        }
    
    def assess_oauth_permissions(self, permissions_str: str) -> Dict[str, any]:
        """Assess risk of OAuth2 permissions requested by an application."""
        risk_score = 0
        risky_permissions = []
        
        # Check for dangerous permissions
        for perm in self.DANGEROUS_PERMISSIONS:
            if perm in permissions_str.lower():
                risk_score += 2
                risky_permissions.append(perm)
        
        # Check for permission count
        perm_count = len(permissions_str.split(','))
        if perm_count > 10:
            risk_score += 2
            risky_permissions.append(f"Excessive permissions ({perm_count})")
        
        return {
            "risk_score": min(risk_score, 10),
            "risky_permissions": risky_permissions,
            "permission_count": perm_count
        }
    
    def track_bot_addition(self, user_id: int, bot_id: int, guild_id: int):
        """Track when a user adds a bot to a server."""
        if user_id not in self.user_bot_history:
            self.user_bot_history[user_id] = []
        
        self.user_bot_history[user_id].append((bot_id, datetime.now(timezone.utc), guild_id))
        
        # Keep only last 50 entries per user
        if len(self.user_bot_history[user_id]) > 50:
            self.user_bot_history[user_id] = self.user_bot_history[user_id][-50:]
    
    def track_oauth_authorization(self, user_id: int, app_id: str, permissions: str):
        """Track OAuth2 authorizations by users."""
        if user_id not in self.oauth_history:
            self.oauth_history[user_id] = []
        
        self.oauth_history[user_id].append((app_id, permissions, datetime.now(timezone.utc)))
        
        # Keep only last 20 entries per user
        if len(self.oauth_history[user_id]) > 20:
            self.oauth_history[user_id] = self.oauth_history[user_id][-20:]
    
    def update_bot_reputation(self, bot_id: int, delta: int):
        """Update bot reputation score."""
        if bot_id not in self.bot_reputation:
            self.bot_reputation[bot_id] = 0
        
        self.bot_reputation[bot_id] += delta
        self.bot_reputation[bot_id] = max(-10, min(10, self.bot_reputation[bot_id]))
    
    def add_safe_bot(self, bot_id: int):
        """Add bot to safe/whitelisted list."""
        self.safe_bot_ids.add(bot_id)
        self.update_bot_reputation(bot_id, 5)  # Boost reputation
    
    def remove_safe_bot(self, bot_id: int):
        """Remove bot from safe/whitelisted list."""
        self.safe_bot_ids.discard(bot_id)
        self.update_bot_reputation(bot_id, -3)  # Reduce reputation


class ExternalApps(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.risk_scorer = ExternalAppRiskScorer()
        
        # Tracking
        self.recent_bot_additions: Dict[int, deque] = {}  # guild_id -> deque of recent additions
        self.suspicious_activity: Dict[Tuple[int, int], int] = {}  # (guild_id, user_id) -> warning count
        
        # Settings
        self.auto_punish_high_risk = True
        self.require_bot_approval = False
        
    async def cog_load(self):
        """Initialize the cog."""
        # Load whitelisted bots from database
        await self._load_safe_bots()
    
    async def _load_safe_bots(self):
        """Load safe bot list from database/guild settings."""
        try:
            for guild in self.bot.guilds:
                settings = await get_guild(guild.id)
                safe_bots = settings.get("safe_bots", "")
                if safe_bots:
                    try:
                        bot_ids = [int(bid.strip()) for bid in safe_bots.split(',') if bid.strip()]
                        for bot_id in bot_ids:
                            self.risk_scorer.add_safe_bot(bot_id)
                    except (ValueError, AttributeError):
                        pass
        except Exception as e:
            print(f"[EXTERNAL_APPS] Failed to load safe bots: {e}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Monitor new bot joins and assess their risk."""
        if not member.bot:
            return  # Only monitor bots
        
        guild = member.guild
        settings = await get_guild(guild.id)
        
        # Skip if external app detection is disabled
        if not settings.get("external_apps_enabled", 1):
            return
        
        # Check if bot is whitelisted
        if member.id in self.risk_scorer.safe_bot_ids:
            return
        
        # Try to get the inviter/adder (this requires audit log access)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if entry.target.id == member.id:
                    adder = entry.user
                    if adder:
                        # Calculate risk
                        risk_assessment = self.risk_scorer.calculate_bot_risk(member, adder)
                        
                        # Track the addition
                        self.risk_scorer.track_bot_addition(adder.id, member.id, guild.id)
                        
                        # Add to guild tracking
                        if guild.id not in self.recent_bot_additions:
                            self.recent_bot_additions[guild.id] = deque(maxlen=100)
                        self.recent_bot_additions[guild.id].append({
                            "bot_id": member.id,
                            "adder_id": adder.id,
                            "timestamp": datetime.now(timezone.utc),
                            "risk_score": risk_assessment["risk_score"]
                        })
                        
                        # Handle based on risk level
                        await self._handle_bot_addition(guild, member, adder, risk_assessment, settings)
                    break
        except Exception as e:
            print(f"[EXTERNAL_APPS] Failed to audit bot addition: {e}")
    
    async def _handle_bot_addition(self, guild: discord.Guild, bot: discord.Member, adder: discord.Member, risk_assessment: dict, settings: dict):
        """Handle bot addition based on risk assessment."""
        risk_score = risk_assessment["risk_score"]
        risk_level = risk_assessment["risk_level"]
        
        # Log the addition
        await log_action(guild.id, "bot_addition", bot.id, {
            "added_by": adder.id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_assessment["risk_factors"]
        })
        
        # Send alert
        log_ch_id = settings.get("log_channel", 0)
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            if ch:
                embed = alert_embed(
                    f"🤖 Bot Added - {risk_level} Risk",
                    f"**Bot:** {bot.mention} (`{bot.id}`)\n"
                    f"**Added by:** {adder.mention} (`{adder.id}`)\n"
                    f"**Risk Score:** {risk_score}/10\n"
                    f"**Risk Factors:**\n" + "\n".join(f"• {f}" for f in risk_assessment["risk_factors"])
                )
                embed.add_field(name="Bot Age", value=f"{(datetime.now(timezone.utc) - bot.created_at).days} days", inline=True)
                embed.add_field(name="Verified", value="✅ Yes" if bot.public_flags.verified_bot else "❌ No", inline=True)
                embed.set_thumbnail(url=bot.display_avatar.url)
                await ch.send(embed=embed)
        
        # High-risk actions
        if risk_score >= 7 and self.auto_punish_high_risk:
            try:
                # Kick the bot
                await bot.kick(reason=f"[Repent External Apps] High-risk bot (Score: {risk_score})")
                
                # Punish the adder
                await self._punish_bot_adder(guild, adder, risk_score)
                
                # Update bot reputation
                self.risk_scorer.update_bot_reputation(bot.id, -5)
                
                if log_ch_id:
                    await ch.send(embed=alert_embed("🚨 Bot Kicked", f"High-risk bot {bot.mention} was kicked. Adder {adder.mention} was punished."))
                
            except Exception as e:
                print(f"[EXTERNAL_APPS] Failed to kick high-risk bot: {e}")
        
        # Medium-risk warnings
        elif risk_score >= 5:
            # Track suspicious activity
            key = (guild.id, adder.id)
            self.suspicious_activity[key] = self.suspicious_activity.get(key, 0) + 1
            
            if self.suspicious_activity[key] >= 3:
                # Escalate to punishment
                await self._punish_bot_adder(guild, adder, risk_score)
    
    async def _punish_bot_adder(self, guild: discord.Guild, adder: discord.Member, risk_score: int):
        """Punish user for adding high-risk bots."""
        try:
            # Check if user has admin permissions
            if adder.guild_permissions.administrator:
                # Just warn admins
                try:
                    await adder.send(f"⚠️ You added a high-risk bot to **{guild.name}**. Please be more careful with bot additions.")
                except Exception:
                    pass
                return
            
            # For non-admins, apply timeout
            timeout_duration = min(risk_score * 10, 1440)  # Max 24 hours
            until = datetime.now(timezone.utc) + timedelta(minutes=timeout_duration)
            
            await adder.timeout(until, reason=f"[Repent External Apps] Added high-risk bot (Risk score: {risk_score})")
            await log_action(guild.id, "bot_adder_timeout", adder.id, {"risk_score": risk_score, "duration_minutes": timeout_duration})
            
        except Exception as e:
            print(f"[EXTERNAL_APPS] Failed to punish bot adder: {e}")
    
    # ── Commands ──
    @discord.app_commands.default_permissions(administrator=True)
    class ExternalAppsGroup(discord.app_commands.Group):
        def __init__(self, bot: commands.Bot, cog: ExternalApps):
            super().__init__(name="extapps", description="External application security management")
            self.bot = bot
            self.cog = cog
        
        @discord.app_commands.command(name="status", description="Show external apps security status")
        async def status(self, interaction: discord.Interaction):
            if not interaction.guild:
                return
            
            guild = interaction.guild
            risk_scorer = self.cog.risk_scorer
            
            embed = discord.Embed(
                title="🔒 External Apps Security",
                description="External application and bot monitoring status",
                color=0x4488FF
            )
            
            # Bot count
            bot_count = len([m for m in guild.members if m.bot])
            embed.add_field(name="Total Bots", value=bot_count, inline=True)
            
            # Safe bots count
            safe_bot_count = len([m for m in guild.members if m.bot and m.id in risk_scorer.safe_bot_ids])
            embed.add_field(name="Whitelisted Bots", value=safe_bot_count, inline=True)
            
            # Recent additions
            if guild.id in self.cog.recent_bot_additions:
                recent_count = len([
                    a for a in self.cog.recent_bot_additions[guild.id]
                    if (datetime.now(timezone.utc) - a['timestamp']).total_seconds() < 3600
                ])
                embed.add_field(name="Recent Bot Additions (1h)", value=recent_count, inline=True)
            
            # Suspicious users
            suspicious_count = len([
                (uid, count) for (gid, uid), count in self.cog.suspicious_activity.items()
                if gid == guild.id and count >= 2
            ])
            embed.add_field(name="Suspicious Users", value=suspicious_count, inline=True)
            
            await interaction.response.send_message(embed=embed)
        
        @discord.app_commands.command(name="whitelist", description="Add a bot to the safe/whitelist")
        @discord.app_commands.describe(bot="Bot to whitelist")
        async def whitelist(self, interaction: discord.Interaction, bot: discord.Member):
            if not interaction.guild:
                return
            
            if not bot.bot:
                return await interaction.response.send_message(embed=error_embed("This is not a bot."), ephemeral=True)
            
            # Add to safe list
            self.cog.risk_scorer.add_safe_bot(bot.id)
            
            # Update database
            settings = await get_guild(interaction.guild.id)
            current_safe = settings.get("safe_bots", "")
            safe_list = [bid.strip() for bid in current_safe.split(',') if bid.strip()]
            
            if str(bot.id) not in safe_list:
                safe_list.append(str(bot.id))
                await update_guild(interaction.guild.id, safe_bots=','.join(safe_list))
            
            await interaction.response.send_message(embed=success_embed("Bot Whitelisted", f"{bot.mention} has been added to the safe bots list."))
        
        @discord.app_commands.command(name="unwhitelist", description="Remove a bot from the safe/whitelist")
        @discord.app_commands.describe(bot="Bot to unwhitelist")
        async def unwhitelist(self, interaction: discord.Interaction, bot: discord.Member):
            if not interaction.guild:
                return
            
            # Remove from safe list
            self.cog.risk_scorer.remove_safe_bot(bot.id)
            
            # Update database
            settings = await get_guild(interaction.guild.id)
            current_safe = settings.get("safe_bots", "")
            safe_list = [bid.strip() for bid in current_safe.split(',') if bid.strip() and bid != str(bot.id)]
            
            await update_guild(interaction.guild.id, safe_bots=','.join(safe_list))
            
            await interaction.response.send_message(embed=success_embed("Bot Unwhitelisted", f"{bot.mention} has been removed from the safe bots list."))
        
        @discord.app_commands.command(name="config", description="Configure external apps settings")
        @discord.app_commands.describe(
            enabled="Enable external apps monitoring",
            auto_punish="Auto-punish high-risk bot additions"
        )
        async def config(
            self,
            interaction: discord.Interaction,
            enabled: Optional[bool] = None,
            auto_punish: Optional[bool] = None
        ):
            if not interaction.guild:
                return
            
            updates = {}
            if enabled is not None:
                updates["external_apps_enabled"] = 1 if enabled else 0
            if auto_punish is not None:
                updates["external_apps_auto_punish"] = 1 if auto_punish else 0
                self.cog.auto_punish_high_risk = auto_punish
            
            if not updates:
                return await interaction.response.send_message(embed=error_embed("No configuration options provided."))
            
            await update_guild(interaction.guild.id, **updates)
            
            desc = "\n".join(f"**{k}:** {v}" for k, v in updates.items())
            await interaction.response.send_message(embed=success_embed("Configuration Updated", desc))
    
    async def cog_load(self):
        await super().cog_load()
        try:
            self.bot.tree.add_command(self.ExternalAppsGroup(self.bot, self))
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ExternalApps(bot))
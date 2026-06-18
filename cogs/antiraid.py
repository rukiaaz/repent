"""Repent - Anti-Raid System

Detects mass joins, triggers server lockdown, filters new accounts, and runs verification gates.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional
from collections import deque

import discord
from discord.ext import commands

from database import get_guild, update_guild, log_raid_start, log_raid_end, log_action
from utils.embeds import error_embed, info_embed, success_embed
from config import OWNER_ID, DEFAULT_PUNISHMENT
from utils.behavioral_analysis import BehavioralAnalysisEngine, AnomalyType
from utils.cross_guild_security import CrossGuildSecurityCorrelation


class VerificationView(discord.ui.View):
    """Persistent verification button view."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id="repent_verify_button", emoji="🛡️")
    async def verify_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        if not guild or not member:
            return

        settings = await get_guild(guild.id)
        unverified_role = discord.utils.get(guild.roles, name="Repent Unverified")

        if unverified_role and unverified_role not in member.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return

        # If raid mode is active, enforce account age check
        if settings.get("raid_mode", 0):
            account_age_days = settings.get("raid_account_age", 7)
            created_days = (datetime.now(timezone.utc) - member.created_at.replace(tzinfo=None)).days
            if created_days < account_age_days:
                await interaction.response.send_message(
                    f"❌ Verification Failed: Your account is too new ({created_days} days old). The threshold is {account_age_days} days during lockdown.",
                    ephemeral=True
                )
                return

        # Remove unverified role
        try:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="[Repent] Completed verification")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I do not have permission to remove your unverified role. Please contact a server admin.", ephemeral=True)
            return
        except Exception:
            pass

        # Give autorole
        autorole_id = settings.get("autorole", 0)
        if autorole_id:
            role = guild.get_role(autorole_id)
            if role:
                try:
                    await member.add_roles(role, reason="[Repent] Verification Autorole")
                except Exception:
                    pass

        # Send welcome message
        welcome_ch_id = settings.get("welcome_channel", 0)
        welcome_msg = settings.get("welcome_msg", "")
        if welcome_ch_id and welcome_msg:
            ch = guild.get_channel(welcome_ch_id)
            if ch:
                msg = (welcome_msg
                       .replace("{user}", member.mention)
                       .replace("{username}", member.name)
                       .replace("{server}", guild.name)
                       .replace("{count}", str(guild.member_count)))
                embed = discord.Embed(description=msg, color=0x44FF88)
                embed.set_author(name=f"Welcome to {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Member #{guild.member_count}")
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

        await interaction.response.send_message("✅ Verification successful! Welcome to the server.", ephemeral=True)


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_tracker: Dict[int, deque[datetime]] = {}
        self.active_raids: Dict[int, dict] = {}
        self.original_everyone_perms: Dict[int, int] = {}
        
        # Enhanced raid detection features
        self.raid_scores: Dict[int, Dict[int, int]] = {}  # guild_id -> user_id -> score
        self.suspicious_users: Dict[int, Set[int]] = {}  # guild_id -> set of suspicious user IDs
        
        # Webhook alert system
        self.webhook_alerts_enabled: bool = True
        
        # Behavioral analysis integration
        self.behavioral_engine = BehavioralAnalysisEngine()
        
        # Cross-guild attack correlation
        self.cross_guild_security = CrossGuildSecurityCorrelation()
        
        # Adaptive thresholds based on server baselines
        self.adaptive_thresholds: Dict[int, Dict[str, float]] = {}  # guild_id -> {threshold_name: value}
        
        # Attack patterns for ML-based detection
        self.attack_patterns: Dict[str, Dict] = {
            "rapid_join": {"threshold": 5, "window": 3, "weight": 3},
            "new_account_cluster": {"threshold": 3, "window": 10, "weight": 2},
            "suspicious_names": {"patterns": [r'\d{4,}', r'_[^_]+_[^_]+_', r'\.{2,}'], "weight": 1},
        }

    def calculate_raid_score(self, member: discord.Member, guild_id: int) -> int:
        """Calculate suspicious raid score for a member (0-10)."""
        score = 0
        settings = self.bot.loop.run_until_complete(get_guild(guild_id))
        account_age_days = settings.get("raid_account_age", 7)
        
        # Account age check (most significant)
        account_age = (datetime.now(timezone.utc) - member.created_at.replace(tzinfo=None)).days
        if account_age < account_age_days:
            score += 3  # New account
        if account_age < 1:
            score += 2  # Very new account (less than 1 day)
        
        # Avatar checks
        if not member.avatar:
            score += 1  # No avatar
        if member.default_avatar:
            score += 1  # Default avatar
        
        # Username pattern analysis
        username = member.name.lower()
        if len(username) < 3:
            score += 2  # Too short username
        if any(c in username for c in ['_.', '-', '0123456789']):
            score += 1  # Suspicious characters
        if bool(re.search(r'\d{4,}', username)):
            score += 1  # Many numbers (like discord discriminator)
        
        # Display name analysis
        if member.nick:
            nick = member.nick.lower()
            if len(nick) < 3:
                score += 1
            if any(c in nick for c in ['_.', '-']):
                score += 1
        
        # Bot check (if it's a bot, highly suspicious during raid)
        if member.bot:
            score += 2
        
        return min(score, 10)  # Cap at 10
    
    async def analyze_join_behavior(self, member: discord.Member, guild_id: int) -> Dict[str, any]:
        """Use behavioral analysis to assess join patterns."""
        try:
            # Analyze this action with behavioral engine
            anomaly_report = await self.behavioral_engine.analyze_user_action(
                guild_id=guild_id,
                user_id=member.id,
                action_type="member_join",
                timestamp=datetime.now(timezone.utc),
                additional_context={
                    "account_age": (datetime.now(timezone.utc) - member.created_at).days,
                    "has_avatar": bool(member.avatar),
                    "is_bot": member.bot
                }
            )
            
            return {
                "anomaly_score": anomaly_report.overall_score,
                "anomaly_types": [a.anomaly_type.value for a in anomaly_report.individual_anomalies],
                "recommended_action": anomaly_report.recommended_action,
                "user_risk_score": anomaly_report.context.get('user_risk_score', 0.0)
            }
        except Exception as e:
            print(f"[ANTIRAID] Behavioral analysis failed: {e}")
            return {
                "anomaly_score": 0.0,
                "anomaly_types": [],
                "recommended_action": "monitor",
                "user_risk_score": 0.0
            }
    
    def calculate_adaptive_threshold(self, guild_id: int, base_threshold: int) -> int:
        """Calculate adaptive threshold based on server baseline."""
        if guild_id not in self.adaptive_thresholds:
            self.adaptive_thresholds[guild_id] = {
                "baseline_threshold": base_threshold,
                "current_threshold": base_threshold,
                "adjustment_factor": 1.0
            }
            return base_threshold
        
        adaptive = self.adaptive_thresholds[guild_id]
        
        # Get server baseline from behavioral engine
        baseline = self.behavioral_engine.server_baselines.get(guild_id)
        if baseline:
            # Adjust threshold based on typical activity
            typical_join_rate = baseline.typical_join_rate
            if typical_join_rate > base_threshold * 0.8:
                # High-activity server, increase threshold
                adaptive["adjustment_factor"] = 1.3
            elif typical_join_rate < base_threshold * 0.3:
                # Low-activity server, decrease threshold
                adaptive["adjustment_factor"] = 0.7
            else:
                adaptive["adjustment_factor"] = 1.0
        
        adaptive["current_threshold"] = int(base_threshold * adaptive["adjustment_factor"])
        return adaptive["current_threshold"]
    
    def update_server_baseline(self, guild_id: int, join_rate: float):
        """Update server baseline with current data."""
        if guild_id not in self.behavioral_engine.server_baselines:
            baseline = self.behavioral_engine.server_baselines[guild_id]
        else:
            baseline = self.behavioral_engine.server_baselines[guild_id]
        
        # Update typical join rate using exponential moving average
        if baseline.typical_join_rate == 0.0:
            baseline.typical_join_rate = join_rate
        else:
            baseline.typical_join_rate = 0.9 * baseline.typical_join_rate + 0.1 * join_rate
    
    async def send_webhook_alert(self, guild: discord.Guild, alert_type: str, member: discord.Member = None, details: str = ""):
        """Send raid alert via webhook if configured."""
        try:
            settings = await get_guild(guild.id)
            webhook_url = settings.get("raid_webhook_url", "")
            if not webhook_url or not self.webhook_alerts_enabled:
                return
            
            webhook = discord.SyncWebhook.from_url(webhook_url)
            embed = discord.Embed(
                title=f"🚨 {alert_type}",
                description=details,
                color=0xFF4444,
                timestamp=datetime.now(timezone.utc)
            )
            if member:
                embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
                embed.add_field(name="Account Age", value=f"{(datetime.now(timezone.utc) - member.created_at).days} days", inline=True)
                embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
            embed.add_field(name="Server", value=f"{guild.name} ({guild.id})", inline=False)
            embed.set_footer(text="Repent Anti-Raid System")
            webhook.send(embed=embed)
        except Exception as e:
            print(f"[ANTIRAID] Failed to send webhook alert: {e}")
    
    async def quarantine_user(self, member: discord.Member, reason: str):
        """Move suspicious user to quarantine channel if configured."""
        try:
            settings = await get_guild(member.guild.id)
            quarantine_ch_id = settings.get("raid_quarantine_channel", 0)
            if not quarantine_ch_id:
                return False
            
            quarantine_ch = member.guild.get_channel(quarantine_ch_id)
            if not quarantine_ch or not isinstance(quarantine_ch, discord.VoiceChannel):
                return False
            
            await member.move_to(quarantine_ch, reason=f"[Repent Anti-Raid] Quarantined: {reason}")
            await log_action(member.guild.id, "quarantine", member.id, {"reason": reason})
            return True
        except Exception as e:
            print(f"[ANTIRAID] Failed to quarantine user {member.id}: {e}")
            return False

    async def cog_load(self):
        self.bot.add_view(VerificationView(self.bot))

    def cog_unload(self):
        # Cancel any running auto-unlock timers
        for raid in self.active_raids.values():
            if "timer" in raid:
                raid["timer"].cancel()

    async def _log_to_channel(self, guild: discord.Guild, text: str) -> None:
        try:
            settings = await get_guild(guild.id)
            log_ch_id = settings.get("log_channel", 0)
            if not log_ch_id:
                return
            ch = guild.get_channel(log_ch_id)
            if ch:
                await ch.send(text)
        except Exception:
            pass

    async def trigger_raid_mode(self, guild: discord.Guild, joins_detected: int, enhanced_data: dict = None):
        settings = await get_guild(guild.id)
        if settings.get("raid_mode", 0):
            return

        # Update DB
        await update_guild(guild.id, raid_mode=1)

        # Log raid start with enhanced data
        raid_id = await log_raid_start(guild.id, joins_detected, lockdown_triggered=1)
        self.active_raids[guild.id] = {
            "raid_id": raid_id,
            "timer": asyncio.create_task(self.auto_unlock_timer(guild.id, 900)),  # 15 minutes
            "enhanced_data": enhanced_data or {}
        }
        
        # Record in cross-guild security system
        self.cross_guild_security.record_security_event(
            event_type="raid",
            guild_id=guild.id,
            attacker_id=0,  # Raids don't always have a single attacker
            severity="HIGH" if joins_detected > 20 else "MEDIUM",
            details={
                "joins_detected": joins_detected,
                "enhanced_data": enhanced_data or {},
                "raid_id": raid_id
            }
        )

        # Lockdown @everyone
        everyone = guild.default_role
        original_perms = everyone.permissions
        self.original_everyone_perms[guild.id] = original_perms.value

        new_perms = discord.Permissions(original_perms.value)
        new_perms.update(
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            connect=False
        )

        try:
            await everyone.edit(permissions=new_perms, reason="[Repent Anti-Raid] Guild Lockdown")
        except Exception as e:
            print(f"[ANTIRAID] Failed to lockdown guild {guild.id}: {e}")

        # Enhanced Embed Alert with pattern analysis
        description = f"Mass join flood detected: **{joins_detected} joins** in the last {settings.get('raid_join_window', 10)} seconds.\n\n"
        description += f"🔒 **Lockdown Status:** Active (All channels locked for `@everyone`)\n"
        description += f"🛡️ **Anti-Raid Mode:** Enabled (New accounts age filter active)\n"
        description += f"⏳ **Auto-Unlock:** In 15 minutes of inactivity."
        
        # Add enhanced data if available
        if enhanced_data:
            description += f"\n\n📊 **Enhanced Analysis:**\n"
            if enhanced_data.get("rapid_join_count"):
                description += f"• Rapid joins (3s): {enhanced_data['rapid_join_count']}\n"
            if enhanced_data.get("avg_raid_score"):
                description += f"• Average raid score: {enhanced_data['avg_raid_score']:.2f}/10\n"
            if enhanced_data.get("avg_anomaly_score"):
                description += f"• Average anomaly score: {enhanced_data['avg_anomaly_score']:.2f}/10\n"
            if enhanced_data.get("suspicious_count"):
                description += f"• Suspicious users: {enhanced_data['suspicious_count']}\n"
            if enhanced_data.get("adaptive_threshold"):
                description += f"• Adaptive threshold: {enhanced_data['adaptive_threshold']}\n"
            if enhanced_data.get("behavioral_alerts"):
                description += f"• Behavioral alerts: {enhanced_data['behavioral_alerts']}\n"
        
        embed = discord.Embed(
            title="🚨 Raid Detected — Lockdown Active!",
            description=description,
            color=0xFF4444
        )
        embed.set_footer(text="Repent Anti-Raid System")
        embed.timestamp = datetime.now(timezone.utc)

        log_ch_id = settings.get("log_channel", 0)
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            if ch:
                await ch.send(embed=embed)

        try:
            owner = guild.get_member(guild.owner_id)
            if owner:
                await owner.send(embed=embed)
        except Exception:
            pass

        # Send webhook alert
        await self.send_webhook_alert(guild, "Raid Mode Activated", None, f"{joins_detected} joins in {settings.get('raid_join_window', 10)}s")

    async def auto_unlock_timer(self, guild_id: int, delay: int):
        await asyncio.sleep(delay)
        guild = self.bot.get_guild(guild_id)
        if guild:
            await self.unlock_guild(guild, "Auto-unlock after 15 minutes of inactivity")

    async def unlock_guild(self, guild: discord.Guild, reason: str):
        settings = await get_guild(guild.id)
        if not settings.get("raid_mode", 0):
            return

        # Update DB
        await update_guild(guild.id, raid_mode=0)

        # Remove timer
        raid_info = self.active_raids.pop(guild.id, None)
        if raid_info:
            if "timer" in raid_info:
                raid_info["timer"].cancel()
            await log_raid_end(raid_info["raid_id"], resolved=1)

        # Restore permissions
        everyone = guild.default_role
        saved_perms = self.original_everyone_perms.pop(guild.id, None)
        if saved_perms is not None:
            new_perms = discord.Permissions(saved_perms)
        else:
            new_perms = everyone.permissions
            new_perms.update(send_messages=True, send_messages_in_threads=True, connect=True)

        try:
            await everyone.edit(permissions=new_perms, reason=f"[Repent Anti-Raid] Unlock: {reason}")
        except Exception as e:
            print(f"[ANTIRAID] Failed to unlock guild {guild.id}: {e}")

        # Alert
        embed = discord.Embed(
            title="🔓 Server Unlocked",
            description=f"Anti-Raid lockdown has been lifted.\n**Reason:** {reason}\n\nAll normal user permissions have been restored.",
            color=0x44FF88
        )
        embed.timestamp = datetime.now(timezone.utc)

        log_ch_id = settings.get("log_channel", 0)
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            if ch:
                await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        settings = await get_guild(guild.id)

        # Whitelist checks
        if member.id == OWNER_ID or member.id == guild.owner_id:
            return

        # Initialize guild tracking
        guild_id = guild.id
        if guild_id not in self.join_tracker:
            self.join_tracker[guild_id] = deque()
            self.raid_scores[guild_id] = {}
            self.suspicious_users[guild_id] = set()

        # Calculate raid score for enhanced detection
        raid_score = self.calculate_raid_score(member, guild_id)
        self.raid_scores[guild_id][member.id] = raid_score

        # Behavioral analysis integration
        behavior_analysis = await self.analyze_join_behavior(member, guild_id)
        anomaly_score = behavior_analysis["anomaly_score"]
        
        # Combine raid score and anomaly score for enhanced detection
        combined_score = (raid_score + (anomaly_score * 10)) / 2  # Normalize to 0-10 scale

        # Get enhanced settings
        auto_mode = settings.get("raid_auto_mode", 0)
        sensitivity = settings.get("raid_sensitivity_level", 5)
        is_raid_active = settings.get("raid_mode", 0)

        # Enhanced account age check with auto-mode
        account_age_days = settings.get("raid_account_age", 7)
        created_days = (datetime.now(timezone.utc) - member.created_at.replace(tzinfo=None)).days

        # Auto-kick new accounts during raid mode or auto-mode
        if is_raid_active or auto_mode:
            if created_days < account_age_days:
                try:
                    await member.send(f"⚠️ You were kicked from **{guild.name}** because your account is too new ({created_days} days old) and the server is in Raid Mode.")
                except Exception:
                    pass
                try:
                    await member.kick(reason=f"[Repent Anti-Raid] Account age filter ({created_days}d < {account_age_days}d)")
                    await log_action(guild.id, "raid_kick", member.id, {"reason": f"Account age {created_days}d < threshold {account_age_days}d", "behavioral_analysis": behavior_analysis})
                    await self._log_to_channel(guild, f"📥 **Kick**: {member.mention} (`{member.id}`) was auto-kicked (Account age: {created_days} days).")
                    
                    # Send webhook alert
                    await self.send_webhook_alert(guild, "Account Age Kick", member, f"Account too new: {created_days} days, Anomaly score: {anomaly_score:.2f}")
                except Exception:
                    pass
                return

        # Enhanced quarantine using combined score and behavioral analysis
        effective_threshold = (10 - sensitivity) - (anomaly_score * 2)  # Lower threshold for high anomaly scores
        if combined_score >= effective_threshold and not is_raid_active:
            self.suspicious_users[guild_id].add(member.id)
            
            # Log behavioral analysis findings
            if behavior_analysis["anomaly_types"]:
                anomaly_details = f"Anomalies: {', '.join(behavior_analysis['anomaly_types'])}"
            else:
                anomaly_details = "No behavioral anomalies detected"
            
            quarantined = await self.quarantine_user(member, f"High combined score: {combined_score:.2f}, {anomaly_details}")
            if quarantined:
                await self.send_webhook_alert(guild, "User Quarantined", member, f"Combined score: {combined_score:.2f}, Anomaly score: {anomaly_score:.2f}")
                await self._log_to_channel(guild, f"🔒 **Quarantine**: {member.mention} (`{member.id}`) quarantined (Combined Score: {combined_score:.2f}, Anomaly Score: {anomaly_score:.2f}).")
                return

        # Verification channel check during raid mode
        if is_raid_active:
            verification_channel_id = settings.get("verification_channel", 0)
            if verification_channel_id:
                ch = guild.get_channel(verification_channel_id)
                if ch:
                    unverified_role = discord.utils.get(guild.roles, name="Repent Unverified")
                    if not unverified_role:
                        try:
                            unverified_role = await guild.create_role(
                                name="Repent Unverified",
                                reason="[Repent Anti-Raid] Created unverified role for verification gate"
                            )
                        except Exception:
                            pass

                    if unverified_role:
                        try:
                            await member.add_roles(unverified_role, reason="[Repent Anti-Raid] Placed in verification gate")
                            try:
                                await member.send(f"🔒 **{guild.name}** is in Raid Mode. Please verify in the verification channel: {ch.mention}.")
                            except Exception:
                                pass
                        except Exception:
                            pass
                return

        # Enhanced join rate tracking with pattern detection
        now = datetime.now(timezone.utc)
        self.join_tracker[guild_id].append(now)

        window = settings.get("raid_join_window", 10)
        cutoff = now - timedelta(seconds=window)
        while self.join_tracker[guild_id] and self.join_tracker[guild_id][0] <= cutoff:
            self.join_tracker[guild_id].popleft()

        # Use adaptive threshold based on behavioral baseline
        base_threshold = settings.get("raid_join_threshold", 10)
        adaptive_threshold = self.calculate_adaptive_threshold(guild_id, base_threshold)
        
        join_count = len(self.join_tracker[guild_id])

        # Update server baseline
        join_rate = join_count / (window / 60) if window > 0 else 0  # joins per minute
        self.update_server_baseline(guild_id, join_rate)

        # Enhanced raid detection with pattern analysis and behavioral integration
        if join_count >= adaptive_threshold:
            # Check for attack patterns
            recent_joins = [t for t in self.join_tracker[guild_id] if (now - t).total_seconds() <= window]
            rapid_join_count = len([t for t in recent_joins if (now - t).total_seconds() <= 3])
            
            # Calculate behavioral metrics
            avg_raid_score = sum(self.raid_scores[guild_id].values()) / max(len(self.raid_scores[guild_id]), 1)
            avg_anomaly_score = sum([
                self.behavioral_engine.user_profiles.get(uid, type('obj', (object,), {'risk_score': 0.0})).risk_score 
                for uid in self.raid_scores[guild_id]
            ]) / max(len(self.raid_scores[guild_id]), 1)
            
            # Trigger raid mode with enhanced detection
            await self.trigger_raid_mode(guild, join_count, {
                "rapid_join_count": rapid_join_count,
                "avg_raid_score": avg_raid_score,
                "avg_anomaly_score": avg_anomaly_score,
                "suspicious_count": len(self.suspicious_users[guild_id]),
                "adaptive_threshold": adaptive_threshold,
                "behavioral_alerts": len([uid for uid, score in self.raid_scores[guild_id].items() if score >= 5])
            })

    # ── Command Group ──
    @discord.app_commands.default_permissions(administrator=True)
    class RaidGroup(discord.app_commands.Group):
        def __init__(self, bot: commands.Bot, cog: AntiRaid):
            super().__init__(name="raid", description="Anti-Raid management commands")
            self.bot = bot
            self.cog = cog

        @discord.app_commands.command(name="status", description="Show the current anti-raid status and configuration")
        async def status(self, interaction: discord.Interaction):
            if not interaction.guild:
                return
            settings = await get_guild(interaction.guild.id)
            is_active = settings.get("raid_mode", 0)

            status_str = "🔴 **Lockdown Active**" if is_active else "🟢 **Normal Operation**"

            ver_ch_id = settings.get("verification_channel", 0)
            ver_ch_str = f"<#{ver_ch_id}>" if ver_ch_id else "*None*"
            
            quarantine_ch_id = settings.get("raid_quarantine_channel", 0)
            quarantine_ch_str = f"<#{quarantine_ch_id}>" if quarantine_ch_id else "*None*"
            
            webhook_url = settings.get("raid_webhook_url", "")
            webhook_str = "✅ Configured" if webhook_url else "❌ Not set"

            embed = discord.Embed(
                title="🛡️ Anti-Raid Status",
                description=f"Status: {status_str}\n\n"
                            f"**Threshold:** {settings.get('raid_join_threshold', 10)} joins\n"
                            f"**Window:** {settings.get('raid_join_window', 10)} seconds\n"
                            f"**Account Age Filter:** {settings.get('raid_account_age', 7)} days\n"
                            f"**Sensitivity:** {settings.get('raid_sensitivity_level', 5)}/10\n"
                            f"**Auto Mode:** {'✅ Enabled' if settings.get('raid_auto_mode', 0) else '❌ Disabled'}\n"
                            f"**Verification Channel:** {ver_ch_str}\n"
                            f"**Quarantine Channel:** {quarantine_ch_str}\n"
                            f"**Webhook Alerts:** {webhook_str}",
                color=0x4488FF if not is_active else 0xFF4444
            )
            
            # Show recent joins if data available
            if interaction.guild.id in self.join_tracker:
                recent_joins = len([t for t in self.join_tracker[interaction.guild.id] if (datetime.now(timezone.utc) - t).total_seconds() < 60])
                embed.add_field(name="Recent Joins (1m)", value=recent_joins, inline=True)
            
            # Show suspicious users count
            if interaction.guild.id in self.suspicious_users:
                embed.add_field(name="Suspicious Users", value=len(self.suspicious_users[interaction.guild.id]), inline=True)
            
            await interaction.response.send_message(embed=embed)

        @discord.app_commands.command(name="toggle", description="Manually enable/disable raid lockdown mode")
        @discord.app_commands.describe(enabled="Enable or disable raid lockdown mode")
        async def toggle(self, interaction: discord.Interaction, enabled: bool):
            if not interaction.guild:
                return

            settings = await get_guild(interaction.guild.id)
            current = settings.get("raid_mode", 0)

            if enabled and not current:
                await interaction.response.defer(thinking=True)
                await self.cog.trigger_raid_mode(interaction.guild, 0)
                await interaction.followup.send(embed=success_embed("Raid Mode Activated", "Server has been locked down manually."))
            elif not enabled and current:
                await interaction.response.defer(thinking=True)
                await self.cog.unlock_guild(interaction.guild, f"Manually unlocked by {interaction.user}")
                await interaction.followup.send(embed=success_embed("Raid Mode Deactivated", "Server lockdown lifted manually."))
            else:
                await interaction.response.send_message(embed=info_embed("Info", f"Raid mode is already {'enabled' if enabled else 'disabled'}."))

        @discord.app_commands.command(name="config", description="Configure anti-raid settings")
        @discord.app_commands.describe(
            threshold="Number of joins to trigger raid mode",
            window="Sliding window in seconds",
            account_age="Minimum account age in days to allow joining during raid mode",
            verification_channel="Verification channel for new members",
            sensitivity="Detection sensitivity (1-10, higher = more strict)",
            auto_mode="Enable automatic raid mode triggering",
            quarantine_channel="Voice channel to quarantine suspicious users",
            webhook_url="Webhook URL for raid alerts"
        )
        async def config(
            self,
            interaction: discord.Interaction,
            threshold: Optional[int] = None,
            window: Optional[int] = None,
            account_age: Optional[int] = None,
            verification_channel: Optional[discord.TextChannel] = None,
            sensitivity: Optional[int] = None,
            auto_mode: Optional[bool] = None,
            quarantine_channel: Optional[discord.VoiceChannel] = None,
            webhook_url: Optional[str] = None
        ):
            if not interaction.guild:
                return

            updates = {}
            if threshold is not None:
                updates["raid_join_threshold"] = threshold
            if window is not None:
                updates["raid_join_window"] = window
            if account_age is not None:
                updates["raid_account_age"] = account_age
            if verification_channel is not None:
                updates["verification_channel"] = verification_channel.id
            if sensitivity is not None:
                sensitivity = max(1, min(10, sensitivity))
                updates["raid_sensitivity_level"] = sensitivity
            if auto_mode is not None:
                updates["raid_auto_mode"] = 1 if auto_mode else 0
            if quarantine_channel is not None:
                updates["raid_quarantine_channel"] = quarantine_channel.id
            if webhook_url is not None:
                updates["raid_webhook_url"] = webhook_url

            if not updates:
                return await interaction.response.send_message(embed=error_embed("No configuration options provided."))

            await update_guild(interaction.guild.id, **updates)

            desc = "\n".join(f"**{k.replace('raid_', '').replace('_', ' ').title()}:** {v}" for k, v in updates.items())
            await interaction.response.send_message(embed=success_embed("Configuration Updated", desc))

        @discord.app_commands.command(name="unlock", description="Manually lift the lockdown and restore normal permissions")
        async def unlock(self, interaction: discord.Interaction):
            if not interaction.guild:
                return
            settings = await get_guild(interaction.guild.id)
            if not settings.get("raid_mode", 0):
                return await interaction.response.send_message(embed=error_embed("Server is not currently locked down."))

            await interaction.response.defer(thinking=True)
            await self.cog.unlock_guild(interaction.guild, f"Manually unlocked by {interaction.user}")
            await interaction.followup.send(embed=success_embed("Server Unlocked", "Lockdown has been lifted."))

        @discord.app_commands.command(name="verification-setup", description="Setup verification message in the verification channel")
        async def verification_setup(self, interaction: discord.Interaction):
            if not interaction.guild:
                return

            settings = await get_guild(interaction.guild.id)
            ver_ch_id = settings.get("verification_channel", 0)
            if not ver_ch_id:
                return await interaction.response.send_message(embed=error_embed("Please set a verification channel first using `/raid config`."), ephemeral=True)

            ch = interaction.guild.get_channel(ver_ch_id)
            if not ch:
                return await interaction.response.send_message(embed=error_embed("Configured verification channel not found."), ephemeral=True)

            embed = discord.Embed(
                title="🛡️ Server Verification Gate",
                description="Welcome to the server! To prevent spam, selfbots, and raids, we require you to verify before accessing the rest of the server.\n\n"
                            "Click the **Verify** button below to complete verification.",
                color=0x4488FF
            )
            embed.set_footer(text="Repent Security")

            view = VerificationView(self.bot)
            try:
                await ch.send(embed=embed, view=view)
                await interaction.response.send_message(embed=success_embed("Verification Gate Set", f"Verification message sent to {ch.mention}."), ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(embed=error_embed(f"Failed to send message: {e}"), ephemeral=True)

        @discord.app_commands.command(name="score", description="Check the raid score for a user")
        @discord.app_commands.describe(user="User to check")
        async def check_score(self, interaction: discord.Interaction, user: discord.Member):
            if not interaction.guild:
                return
            
            guild_id = interaction.guild.id
            raid_score = self.raid_scores.get(guild_id, {}).get(user.id, 0)
            
            # Calculate current score if not tracked
            if raid_score == 0:
                raid_score = self.calculate_raid_score(user, guild_id)
                self.raid_scores[guild_id][user.id] = raid_score

            embed = discord.Embed(
                title=f"🎯 Raid Score for {user.name}",
                description=f"**Score:** {raid_score}/10 (Higher = More Suspicious)",
                color=0xFF4444 if raid_score >= 5 else 0xFFAA00 if raid_score >= 3 else 0x44FF88
            )

            # Score breakdown
            reasons = []
            account_age = (datetime.now(timezone.utc) - user.created_at).days
            if account_age < 7:
                reasons.append(f"🔴 New account ({account_age} days)")
            if not user.avatar:
                reasons.append("🟡 No avatar")
            if user.default_avatar:
                reasons.append("🟡 Default avatar")
            if len(user.name) < 3 or any(c in user.name for c in ['_.', '-', '0123456789']):
                reasons.append("🟡 Suspicious username pattern")

            if reasons:
                embed.add_field(name="Score Factors", value="\n".join(reasons), inline=False)
            else:
                embed.add_field(name="Score Factors", value="✅ No suspicious patterns detected", inline=False)

            embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d"), inline=True)
            embed.add_field(name="Account Age", value=f"{account_age} days", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

    def cog_load_complete(self):
        # We need to register the slash command group
        # In discord.py v2, this is how we register groups from cogs:
        self.bot.tree.add_command(self.RaidGroup(self.bot, self))

    async def cog_load(self):
        await super().cog_load()
        # Add the command group during cog load
        try:
            self.bot.tree.add_command(self.RaidGroup(self.bot, self))
        except Exception:
            pass  # Already added


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))

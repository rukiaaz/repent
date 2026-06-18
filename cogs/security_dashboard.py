"""
Repent - Security Dashboard and Monitoring System

Comprehensive security monitoring dashboard with real-time metrics,
threat intelligence display, and system health monitoring.
"""

from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict

from database import get_guild
from utils.embeds import info_embed, success_embed, error_embed, alert_embed
from config import OWNER_ID


class SecurityDashboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # References to other security systems (will be populated after load)
        self.antiraid_cog = None
        self.antinuke_cog = None
        self.automod_cog = None
        self.external_apps_cog = None
        
        # Dashboard update task
        self._update_task = None
        self._dashboard_data = {}
    
    async def cog_load(self):
        """Initialize dashboard and get references to other cogs."""
        # Get references to security cogs
        self.antiraid_cog = self.bot.get_cog("AntiRaid")
        self.antinuke_cog = self.bot.get_cog("Antinuke")
        self.automod_cog = self.bot.get_cog("AutoMod")
        self.external_apps_cog = self.bot.get_cog("ExternalApps")
        
        # Start dashboard update task
        self._update_task = asyncio.create_task(self._dashboard_update_loop())
    
    async def cog_unload(self):
        """Clean up dashboard task."""
        if self._update_task:
            self._update_task.cancel()
    
    async def _dashboard_update_loop(self):
        """Periodically update dashboard data."""
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(60)  # Update every minute
                await self._update_dashboard_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SECURITY DASHBOARD] Update error: {e}")
    
    async def _update_dashboard_data(self):
        """Update dashboard data from all security systems."""
        for guild in self.bot.guilds:
            guild_data = {
                "guild_id": guild.id,
                "guild_name": guild.name,
                "timestamp": datetime.now(timezone.utc),
                "antiraid": await self._get_antiraid_data(guild.id),
                "antinuke": await self._get_antinuke_data(guild.id),
                "automod": await self._get_automod_data(guild.id),
                "external_apps": await self._get_external_apps_data(guild.id),
                "cache": await self._get_cache_data(),
                "cross_guild": await self._get_cross_guild_data(guild.id)
            }
            self._dashboard_data[guild.id] = guild_data
    
    async def _get_antiraid_data(self, guild_id: int) -> Dict:
        """Get anti-raid system data."""
        if not self.antiraid_cog:
            return {"status": "not_loaded"}
        
        try:
            settings = await get_guild(guild_id)
            return {
                "status": "active",
                "raid_mode": settings.get("raid_mode", 0),
                "threshold": settings.get("raid_join_threshold", 10),
                "sensitivity": settings.get("raid_sensitivity_level", 5),
                "recent_joins": len(self.antiraid_cog.join_tracker.get(guild_id, [])),
                "suspicious_users": len(self.antiraid_cog.suspicious_users.get(guild_id, set())),
                "active_raids": len(self.antiraid_cog.active_raids)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_antinuke_data(self, guild_id: int) -> Dict:
        """Get antinuke system data."""
        if not self.antinuke_cog:
            return {"status": "not_loaded"}
        
        try:
            return {
                "status": "active",
                "metrics": self.antinuke_cog.get_metrics_summary(),
                "emergency_mode": guild_id in self.antinuke_cog._emergency_mode_active,
                "enhanced_restore": bool(self.antinuke_cog.enhanced_restore),
                "cross_guild": bool(self.antinuke_cog.cross_guild_security)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_automod_data(self, guild_id: int) -> Dict:
        """Get automod system data."""
        if not self.automod_cog:
            return {"status": "not_loaded"}
        
        try:
            settings = await get_guild(guild_id)
            return {
                "status": "active",
                "enabled": settings.get("automod_enabled", 1),
                "ml_detector": bool(self.automod_cog.ml_detector),
                "webhook_detector": bool(self.automod_cog.webhook_detector),
                "message_history_size": sum(
                    len(user_msgs) for user_msgs in 
                    self.automod_cog.message_history.get(guild_id, {}).values()
                )
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_external_apps_data(self, guild_id: int) -> Dict:
        """Get external apps system data."""
        if not self.external_apps_cog:
            return {"status": "not_loaded"}
        
        try:
            settings = await get_guild(guild_id)
            return {
                "status": "active",
                "enabled": settings.get("external_apps_enabled", 1),
                "auto_punish": settings.get("external_apps_auto_punish", 1),
                "safe_bots": len(self.external_apps_cog.risk_scorer.safe_bot_ids),
                "recent_additions": len(self.external_apps_cog.recent_bot_additions.get(guild_id, []))
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_cache_data(self) -> Dict:
        """Get unified cache data."""
        try:
            from utils.unified_cache import security_cache
            return {
                "status": "active",
                "metrics": security_cache.get_metrics()
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _get_cross_guild_data(self, guild_id: int) -> Dict:
        """Get cross-guild security data."""
        try:
            # Try to get from antinuke or antiraid
            cross_guild = None
            if self.antinuke_cog:
                cross_guild = self.antinuke_cog.cross_guild_security
            elif self.antiraid_cog:
                cross_guild = self.antiraid_cog.cross_guild_security
            
            if not cross_guild:
                return {"status": "not_loaded"}
            
            return {
                "status": "active",
                "intelligence": cross_guild.get_threat_intelligence(guild_id),
                "statistics": cross_guild.get_statistics()
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    @app_commands.command(name="security-dashboard", description="Show comprehensive security dashboard")
    @app_commands.describe(system="Filter by specific system (all, antiraid, antinuke, automod, external_apps)")
    async def security_dashboard(self, interaction: discord.Interaction, system: str = "all"):
        if not interaction.guild:
            return
        
        guild_id = interaction.guild.id
        
        # Check permissions
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        
        # Get latest data
        await self._update_dashboard_data()
        guild_data = self._dashboard_data.get(guild_id)
        
        if not guild_data:
            return await interaction.followup.send(embed=error_embed("No security data available for this guild."))
        
        # Filter by system if requested
        if system != "all":
            system_data = guild_data.get(system)
            if not system_data:
                return await interaction.followup.send(embed=error_embed(f"No data available for system: {system}"))
            embed = self._create_system_embed(system, system_data, guild_data)
        else:
            embed = self._create_comprehensive_embed(guild_data)
        
        await interaction.followup.send(embed=embed)
    
    def _create_comprehensive_embed(self, guild_data: Dict) -> discord.Embed:
        """Create comprehensive security dashboard embed."""
        embed = discord.Embed(
            title="🛡️ Security Dashboard",
            description=f"Security status for **{guild_data['guild_name']}**",
            color=0x4488FF,
            timestamp=guild_data["timestamp"]
        )
        
        # Anti-Raid Status
        antiraid = guild_data["antiraid"]
        if antiraid["status"] == "active":
            raid_status = "🔴 LOCKDOWN" if antiraid["raid_mode"] else "🟢 Normal"
            embed.add_field(
                name="🚨 Anti-Raid",
                value=f"Status: {raid_status}\nThreshold: {antiraid['threshold']}\nRecent Joins: {antiraid['recent_joins']}\nSuspicious Users: {antiraid['suspicious_users']}",
                inline=True
            )
        
        # Anti-Nuke Status
        antinuke = guild_data["antinuke"]
        if antinuke["status"] == "active":
            metrics = antinuke["metrics"]
            embed.add_field(
                name="⚡ Anti-Nuke",
                value=f"Events: {metrics['events_processed']}\nHit Rate: {metrics['cache_hit_rate']:.1f}%\nAvg Detection: {metrics['avg_detection_time_ms']:.1f}ms",
                inline=True
            )
        
        # AutoMod Status
        automod = guild_data["automod"]
        if automod["status"] == "active":
            embed.add_field(
                name="🤖 AutoMod",
                value=f"Status: {'✅ Enabled' if automod['enabled'] else '❌ Disabled'}\nML Detection: {'✅' if automod['ml_detector'] else '❌'}\nWebhook Security: {'✅' if automod['webhook_detector'] else '❌'}",
                inline=True
            )
        
        # External Apps Status
        external_apps = guild_data["external_apps"]
        if external_apps["status"] == "active":
            embed.add_field(
                name="🔌 External Apps",
                value=f"Status: {'✅ Enabled' if external_apps['enabled'] else '❌ Disabled'}\nSafe Bots: {external_apps['safe_bots']}\nRecent Additions: {external_apps['recent_additions']}",
                inline=True
            )
        
        # Cross-Guild Status
        cross_guild = guild_data["cross_guild"]
        if cross_guild["status"] == "active":
            stats = cross_guild["statistics"]
            embed.add_field(
                name="🌐 Cross-Guild",
                value=f"Total Events: {stats['total_events']}\nActive Attacks: {stats['active_coordinated_attacks']}\nBlacklisted: {stats['global_blacklist_size']}",
                inline=True
            )
        
        # Cache Performance
        cache = guild_data["cache"]
        if cache["status"] == "active":
            metrics = cache["metrics"]
            embed.add_field(
                name="💾 Cache Performance",
                value=f"Hit Rate: {metrics['hit_rate_percent']:.1f}%\nSize: {metrics['cache_size']}\nMemory: {metrics['estimated_memory_mb']:.2f}MB",
                inline=True
            )
        
        embed.set_footer(text="Security Dashboard • Repent")
        return embed
    
    def _create_system_embed(self, system: str, system_data: Dict, guild_data: Dict) -> discord.Embed:
        """Create embed for specific system."""
        system_names = {
            "antiraid": "🚨 Anti-Raid System",
            "antinuke": "⚡ Anti-Nuke System",
            "automod": "🤖 AutoMod System",
            "external_apps": "🔌 External Apps System",
            "cache": "💾 Cache System",
            "cross_guild": "🌐 Cross-Guild Security"
        }
        
        embed = discord.Embed(
            title=system_names.get(system, f"{system.title()} System"),
            description=f"Detailed status for {system}",
            color=0x4488FF,
            timestamp=guild_data["timestamp"]
        )
        
        # Format system data
        for key, value in system_data.items():
            if key == "status":
                continue
            embed.add_field(name=key.replace("_", " ").title(), value=str(value), inline=True)
        
        embed.set_footer(text=f"{system_names.get(system, system)} • Repent")
        return embed
    
    @app_commands.command(name="security-metrics", description="Show detailed security metrics and performance")
    async def security_metrics(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        
        # Check permissions
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        
        # Get latest data
        await self._update_dashboard_data()
        guild_data = self._dashboard_data.get(interaction.guild.id)
        
        if not guild_data:
            return await interaction.followup.send(embed=error_embed("No security data available for this guild."))
        
        # Create detailed metrics embed
        embed = discord.Embed(
            title="📊 Security Metrics",
            description="Detailed performance metrics for all security systems",
            color=0x44FF88,
            timestamp=guild_data["timestamp"]
        )
        
        # Add metrics for each system
        for system_name, system_data in guild_data.items():
            if system_name in ["guild_id", "guild_name", "timestamp"]:
                continue
            
            if system_data.get("status") == "active":
                if "metrics" in system_data:
                    metrics = system_data["metrics"]
                    for metric_name, metric_value in metrics.items():
                        if isinstance(metric_value, float):
                            display_value = f"{metric_value:.2f}"
                        else:
                            display_value = str(metric_value)
                        embed.add_field(
                            name=f"{system_name.replace('_', ' ').title()} - {metric_name.replace('_', ' ').title()}",
                            value=display_value,
                            inline=True
                        )
                else:
                    embed.add_field(
                        name=system_name.replace("_", " ").title(),
                        value=str(system_data),
                        inline=True
                    )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="threat-intelligence", description="Show threat intelligence and cross-guild attack data")
    async def threat_intelligence(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        
        # Check permissions
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        
        # Get cross-guild data
        cross_guild_data = await self._get_cross_guild_data(interaction.guild.id)
        
        if cross_guild_data["status"] != "active":
            return await interaction.followup.send(embed=error_embed("Cross-guild security system not available."))
        
        intelligence = cross_guild_data["intelligence"]
        embed = discord.Embed(
            title="🌐 Threat Intelligence",
            description="Cross-guild security analysis and threat detection",
            color=0xFFAA00,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Blacklist info
        blacklist = intelligence["guild_blacklist"]
        embed.add_field(name="🚫 Blacklisted Users", value=f"{len(blacklist)} users", inline=True)
        
        # Coordinated attacks
        coordinated = intelligence["coordinated_attacks"]
        embed.add_field(name="⚔️ Coordinated Attacks", value=f"{len(coordinated)} active", inline=True)
        
        # Global threats
        global_blacklist = intelligence["global_blacklist"]
        embed.add_field(name="🌍 Global Blacklist", value=f"{len(global_blacklist)} users", inline=True)
        
        # Attack details
        if coordinated:
            attack_info = "\n".join([
                f"• {attack['attack_type']}: {len(attack['affected_guilds'])} guilds"
                for attack in coordinated[:3]
            ])
            embed.add_field(name="Active Attacks", value=attack_info, inline=False)
        
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityDashboard(bot))
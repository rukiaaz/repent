"""
Repent - Premium Embed Factory
Specialized embed builders for different contexts and use cases.
"""

import discord
from typing import List, Dict, Any, Optional
from utils.ui_manager import UIManager
from utils.theme_manager import ThemeManager
from database import get_whitelist
from config import DEFAULT_PUNISHMENT


class EmbedFactory:
    """
    Factory for creating premium embeds with consistent design.
    
    Provides specialized embed builders for specific use cases like
    antinuke status, setup wizard, security alerts, etc.
    """
    
    ui_manager = UIManager()
    theme = ThemeManager()
    
    @classmethod
    async def antinuke_status(cls, guild: discord.Guild, settings: dict) -> discord.Embed:
        """
        Create premium antinuke status embed.
        
        Args:
            guild: Discord guild
            settings: Guild settings dictionary
        
        Returns:
            Premium antinuke status dashboard embed
        """
        # Determine protection level
        if settings.get("antinuke_enabled"):
            protection_level = "MAXIMUM"
            status = "active"
        else:
            protection_level = "DISABLED"
            status = "inactive"
        
        # Build metrics
        whitelist_data = await get_whitelist(guild.id)
        
        metrics = {
            "Modules Active": "12/12" if settings.get("antinuke_enabled") else "0/12",
            "Punishment Mode": settings.get("punishment", "ban").upper(),
            "Whitelisted Users": str(len(whitelist_data)),
            "Lockdown Mode": "Active" if settings.get("antinuke_lockdown_mode") else "Normal",
        }
        
        return cls.ui_manager.create_security_embed(
            status=status,
            protection_level=protection_level,
            metrics=metrics,
            guild=guild
        )
    
    @classmethod
    def setup_step(
        cls,
        step: int,
        total_steps: int,
        title: str,
        fields: List[Dict[str, Any]],
        guild: discord.Guild
    ) -> discord.Embed:
        """
        Create premium setup wizard step embed.
        
        Args:
            step: Current step number (1-based)
            total_steps: Total number of steps
            title: Step title
            fields: List of field dictionaries
            guild: Discord guild
        
        Returns:
            Premium setup wizard step embed with progress indication
        """
        sections = [
            {
                "name": field["name"],
                "value": field["value"],
                "inline": field.get("inline", False)
            }
            for field in fields
        ]
        
        embed = cls.ui_manager.create_dashboard_embed(
            title=f"⚡ Quick Setup - Step {step}",
            description=title,
            sections=sections,
            guild=guild
        )
        
        embed.set_footer(text=f"Step {step}/{total_steps} • {title}")
        
        return embed
    
    @classmethod
    def security_alert(
        cls,
        threat_type: str,
        user: discord.Member,
        action: str,
        guild: discord.Guild,
        additional_info: Dict[str, Any] = None
    ) -> discord.Embed:
        """
        Create premium security alert embed.
        
        Args:
            threat_type: Type of threat (ban, channel_delete, etc.)
            user: User who triggered the alert
            action: Action that was taken
            guild: Discord guild
            additional_info: Additional information to include
        
        Returns:
            Premium security alert embed with full context
        """
        # Determine threat level based on threat type
        threat_levels = {
            "ban": "Critical",
            "channel_delete": "Critical",
            "role_delete": "Critical",
            "webhook_create": "Critical",
            "kick": "High",
            "channel_create": "High",
            "role_create": "High",
            "channel_update": "Medium",
            "role_update": "Medium",
            "webhook_delete": "Medium",
            "server_update": "High",
        }
        
        threat_level = threat_levels.get(threat_type, "Medium")
        
        description = f"Suspicious activity detected from user {user.mention}"
        
        if additional_info:
            # Add context to description
            if "target" in additional_info:
                description += f"\nTarget: {additional_info['target']}"
            if "details" in additional_info:
                description += f"\nDetails: {additional_info['details']}"
        
        return cls.ui_manager.create_alert_embed(
            title="Security Alert",
            description=description,
            threat_level=threat_level,
            action_taken=action,
            guild=guild,
            user=user
        )
    
    @classmethod
    def antinuke_config(
        cls,
        guild: discord.Guild,
        settings: dict
    ) -> discord.Embed:
        """
        Create premium antinuke configuration dashboard embed.
        
        Args:
            guild: Discord guild
            settings: Guild settings dictionary
        
        Returns:
            Premium antinuke configuration dashboard embed
        """
        enabled = settings.get("antinuke_enabled", 1)
        punishment = settings.get("punishment", DEFAULT_PUNISHMENT)
        
        sections = [
            {
                "name": "Antinuke Status",
                "value": f"{'✓ Enabled' if enabled else '✗ Disabled'}",
                "inline": True
            },
            {
                "name": "Punishment Mode",
                "value": f"{punishment.upper()}",
                "inline": True
            },
            {
                "name": "Protection Level",
                "value": "MAXIMUM" if enabled else "DISABLED",
                "inline": True
            },
        ]
        
        return cls.ui_manager.create_dashboard_embed(
            title="🛡️ Antinuke Configuration",
            description="Configure antinuke protection settings",
            sections=sections,
            guild=guild
        )
    
    @classmethod
    def whitelist_dashboard(
        cls,
        guild: discord.Guild,
        users: List[Dict[str, Any]]
    ) -> discord.Embed:
        """
        Create premium whitelist management dashboard embed.
        
        Args:
            guild: Discord guild
            users: List of whitelisted users
        
        Returns:
            Premium whitelist dashboard embed with action buttons
        """
        return cls.ui_manager.create_whitelist_embed(
            users=users,
            guild=guild
        )
    
    @classmethod
    def server_security_score(
        cls,
        guild: discord.Guild,
        security_metrics: Dict[str, Any]
    ) -> discord.Embed:
        """
        Create premium server security score embed.
        
        Args:
            guild: Discord guild
            security_metrics: Dictionary of security metrics
        
        Returns:
            Premium security score embed with visual indicators
        """
        # Calculate overall score
        overall_score = security_metrics.get("overall_score", 0)
        
        # Determine score color
        if overall_score >= 80:
            color = cls.theme.color_security_high
        elif overall_score >= 50:
            color = cls.theme.color_security_med
        else:
            color = cls.theme.color_security_low
        
        # Build progress bar
        filled = int(overall_score / 10)
        progress_bar = "█" * filled + "░" * (10 - filled)
        
        embed = discord.Embed(
            title="📊 Server Security Score",
            description=f"Overall Security Score: **{overall_score}/100**",
            color=color
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Progress bar
        embed.add_field(
            name="Security Score",
            value=f"{progress_bar} {overall_score}/100",
            inline=False
        )
        
        # Individual metrics
        for metric_name, metric_value in security_metrics.items():
            if metric_name != "overall_score":
                embed.add_field(
                    name=metric_name.replace("_", " ").title(),
                    value=str(metric_value),
                    inline=True
                )
        
        cls.ui_manager._set_premium_footer(embed)
        
        return embed
    
    @classmethod
    def audit_log_entry(
        cls,
        guild: discord.Guild,
        log_entry: Dict[str, Any]
    ) -> discord.Embed:
        """
        Create premium audit log entry embed.
        
        Args:
            guild: Discord guild
            log_entry: Audit log entry data
        
        Returns:
            Premium audit log embed with proper formatting
        """
        # Determine severity
        severity = log_entry.get("severity", "info")
        
        # Determine color
        if severity == "critical":
            color = cls.theme.color_danger
        elif severity == "warning":
            color = cls.theme.color_warning
        else:
            color = cls.theme.color_info
        
        embed = discord.Embed(
            title=f"{'🚨' if severity == 'critical' else '🔔'} Security Log",
            color=color
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Log details
        embed.add_field(
            name="Event Type",
            value=log_entry.get("action_type", "Unknown"),
            inline=True
        )
        
        embed.add_field(
            name="Severity",
            value=severity.upper(),
            inline=True
        )
        
        if "user_id" in log_entry:
            embed.add_field(
                name="User",
                value=f"<@{log_entry['user_id']}>",
                inline=True
            )
        
        if "details" in log_entry:
            embed.add_field(
                name="Details",
                value=log_entry["details"],
                inline=False
            )
        
        # Timestamp
        if "timestamp" in log_entry:
            embed.add_field(
                name="Time",
                value=log_entry["timestamp"],
                inline=True
            )
        
        cls.ui_manager._set_premium_footer(embed)
        
        return embed
    
    @classmethod
    def threat_detected(
        cls,
        guild: discord.Guild,
        threat_data: Dict[str, Any]
    ) -> discord.Embed:
        """
        Create premium threat detection embed.
        
        Args:
            guild: Discord guild
            threat_data: Threat detection data
        
        Returns:
            Premium threat detection embed with risk indicators
        """
        threat_level = threat_data.get("threat_level", "Medium")
        
        # Determine color based on threat level
        color = cls.theme.get_color_for_security_level(threat_level)
        
        embed = discord.Embed(
            title="⚡ Threat Detected",
            description=f"Threat level: **{threat_level.upper()}**",
            color=color
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Threat details
        embed.add_field(
            name="User",
            value=f"<@{threat_data.get('user_id', 'Unknown')}>",
            inline=True
        )
        
        embed.add_field(
            name="Threat Level",
            value=f"**{threat_level.upper()}**",
            inline=True
        )
        
        embed.add_field(
            name="Actions Detected",
            value=str(threat_data.get("action_count", 0)),
            inline=True
        )
        
        embed.add_field(
            name="Time Window",
            value=f"{threat_data.get('time_window', 0)}s",
            inline=True
        )
        
        # Additional information
        if "threats" in threat_data:
            threat_list = "\n".join([f"• {t}" for t in threat_data["threats"][:5]])
            embed.add_field(
                name="Detected Threats",
                value=threat_list,
                inline=False
            )
        
        cls.ui_manager._set_premium_footer(embed, status="danger" if threat_level == "Critical" else "warning")
        
        return embed
    
    @classmethod
    def quick_setup_completed(
        cls,
        guild: discord.Guild,
        config: Dict[str, Any]
    ) -> discord.Embed:
        """
        Create premium setup completion embed.
        
        Args:
            guild: Discord guild
            config: Configuration summary
        
        Returns:
            Premium setup completion embed with summary
        """
        sections = [
            {
                "name": "Log Channel",
                "value=f"<#{config.get('log_channel')}>" if config.get('log_channel') else "Not set",
                "inline": True
            },
            {
                "name": "Punishment",
                "value": config.get('punishment', 'ban').upper(),
                "inline": True
            },
            {
                "name": "Antinuke",
                "value": "[PASS] Enabled" if config.get('antinuke_enabled') else "[FAIL] Disabled",
                "inline": True
            },
        ]
        
        embed = cls.ui_manager.create_dashboard_embed(
            title="[SUCCESS] Setup Complete",
            description="Your server is now protected by Repent",
            sections=sections,
            guild=guild
        )
        
        embed.set_footer(text=f"Setup completed in 3 steps")
        
        return embed
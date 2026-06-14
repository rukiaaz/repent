"""
Repent - Premium UI Manager
Centralized embed and component creation with consistent design system.
"""

import discord
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from config import BOT_NAME, VERSION
from utils.theme_manager import ThemeManager


class UIManager:
    """
    Centralized UI management for consistent premium design.
    
    This manager provides a unified interface for creating all UI elements,
    ensuring brand consistency across all bot interactions.
    """
    
    def __init__(self):
        """Initialize the UI manager with theme system."""
        self.theme = ThemeManager()
    
    def create_dashboard_embed(
        self,
        title: str,
        description: str = "",
        sections: List[Dict[str, Any]] = None,
        color: int = None,
        thumbnail: str = None,
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium dashboard-style embed.
        
        Args:
            title: Dashboard title
            description: Dashboard description
            sections: List of section dictionaries with 'name' and 'value'
            color: Embed color (uses theme default if None)
            thumbnail: Thumbnail URL
            guild: Guild for thumbnail (overrides thumbnail parameter)
        
        Returns:
            Premium dashboard embed with consistent design
        """
        if color is None:
            color = self.theme.color_primary
        
        if guild and guild.icon:
            thumbnail = guild.icon.url
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        # Add sections with visual spacing
        if sections:
            for i, section in enumerate(sections):
                embed.add_field(
                    name=section['name'],
                    value=section['value'],
                    inline=section.get('inline', False)
                )
                
                # Add visual separator between block sections
                if i < len(sections) - 1 and not section.get('inline', False):
                    embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        # Premium footer
        self._set_premium_footer(embed)
        
        return embed
    
    def create_security_embed(
        self,
        status: str,
        protection_level: str,
        metrics: Dict[str, Any],
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium security status embed.
        
        Args:
            status: Security status (Active, Inactive, Warning)
            protection_level: Protection level (Maximum, High, Medium, Low)
            metrics: Dictionary of security metrics
            guild: Guild for thumbnail
        
        Returns:
            Premium security status embed
        """
        # Determine color based on status
        color = self.theme.get_color_for_status(status)
        
        embed = discord.Embed(
            title="🛡️ Security Dashboard",
            description=f"Protection level: **{protection_level.upper()}**",
            color=color
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Status indicator
        status_icon = self.theme.get_icon_for_status(status)
        embed.add_field(
            name="Security Status",
            value=f"{status_icon} {status.capitalize()}",
            inline=False
        )
        
        # Security level icon
        level_icon = self.theme.get_icon_for_security_level(protection_level)
        embed.add_field(
            name="Protection Level",
            value=f"{level_icon} {protection_level.upper()}",
            inline=True
        )
        
        # Metrics
        for metric_name, metric_value in metrics.items():
            embed.add_field(
                name=metric_name,
                value=str(metric_value),
                inline=True
            )
        
        self._set_premium_footer(embed, status=status)
        
        return embed
    
    def create_alert_embed(
        self,
        title: str,
        description: str,
        threat_level: str,
        action_taken: str,
        guild: discord.Guild = None,
        user: discord.Member = None
    ) -> discord.Embed:
        """
        Create a premium security alert embed.
        
        Args:
            title: Alert title
            description: Alert description
            threat_level: Threat level (Critical, High, Medium, Low)
            action_taken: Action that was taken
            guild: Guild for thumbnail
            user: User who triggered alert
        
        Returns:
            Premium security alert embed
        """
        # Determine color based on threat level
        color = self.theme.get_color_for_security_level(threat_level)
        
        embed = discord.Embed(
            title=f"⚡ {title}",
            description=description,
            color=color
        )
        
        # Thumbnail priority: guild > user > none
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        elif user:
            embed.set_thumbnail(url=user.display_avatar.url)
        
        # Threat level
        embed.add_field(
            name="Threat Level",
            value=f"**{threat_level.upper()}**",
            inline=True
        )
        
        # Action taken
        embed.add_field(
            name="Action Taken",
            value=action_taken,
            inline=True
        )
        
        # User information if available
        if user:
            embed.add_field(
                name="Responsible User",
                value=user.mention,
                inline=False
            )
        
        self._set_premium_footer(embed, status="danger" if threat_level == "Critical" else "warning")
        
        return embed
    
    def create_success_embed(
        self,
        title: str,
        description: str = "",
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium success embed.
        
        Args:
            title: Success message title
            description: Success message description
            guild: Guild for thumbnail
        
        Returns:
            Premium success embed
        """
        embed = discord.Embed(
            title=f"✓ {title}",
            description=description,
            color=self.theme.color_success
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        self._set_premium_footer(embed, status="success")
        
        return embed
    
    def create_error_embed(
        self,
        description: str = "An error occurred.",
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium error embed.
        
        Args:
            description: Error message
            guild: Guild for thumbnail
        
        Returns:
            Premium error embed
        """
        embed = discord.Embed(
            title="✗ Error",
            description=description,
            color=self.theme.color_danger
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        self._set_premium_footer(embed, status="error")
        
        return embed
    
    def create_warning_embed(
        self,
        title: str,
        description: str = "",
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium warning embed.
        
        Args:
            title: Warning message title
            description: Warning message description
            guild: Guild for thumbnail
        
        Returns:
            Premium warning embed
        """
        embed = discord.Embed(
            title=f"! {title}",
            description=description,
            color=self.theme.color_warning
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        self._set_premium_footer(embed, status="warning")
        
        return embed
    
    def create_info_embed(
        self,
        title: str,
        description: str = "",
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium info embed.
        
        Args:
            title: Info message title
            description: Info message description
            guild: Guild for thumbnail
        
        Returns:
            Premium info embed
        """
        embed = discord.Embed(
            title=f"i {title}",
            description=description,
            color=self.theme.color_info
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        self._set_premium_footer(embed)
        
        return embed
    
    def create_whitelist_embed(
        self,
        users: List[Dict[str, Any]],
        guild: discord.Guild = None
    ) -> discord.Embed:
        """
        Create a premium whitelist management embed.
        
        Args:
            users: List of whitelisted users with trust levels
            guild: Guild for thumbnail
        
        Returns:
            Premium whitelist embed with visual trust indicators
        """
        embed = discord.Embed(
            title="⭐ Whitelist Management",
            description=f"Total whitelisted: **{len(users)}** users",
            color=self.theme.color_primary
        )
        
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Group by trust level
        full_trust = [u for u in users if u.get('trust_level', 1) == 2]
        partial_trust = [u for u in users if u.get('trust_level', 1) == 1]
        
        embed.add_field(
            name="Full Trust",
            value=f"{len(full_trust)} users",
            inline=True
        )
        
        embed.add_field(
            name="Partial Trust",
            value=f"{len(partial_trust)} users",
            inline=True
        )
        
        # Display users (limit to 8 for embed space)
        if users:
            user_list = []
            for user in users[:8]:
                trust_level = "Full" if user.get('trust_level', 1) == 2 else "Partial"
                user_list.append(f"{trust_level}: <@{user['user_id']}>")
            
            embed.add_field(
                name="Whitelisted Users",
                value="\n".join(user_list) + ("\n..." if len(users) > 8 else ""),
                inline=False
            )
        
        self._set_premium_footer(embed)
        
        return embed
    
    def _set_premium_footer(self, embed: discord.Embed, status: str = "success"):
        """
        Set premium footer with bot info and timestamp.
        
        Args:
            embed: Embed to add footer to
            status: Footer status (success, warning, error)
        """
        status_icon = self.theme.get_icon_for_status(status)
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        
        embed.set_footer(
            text=f"{status_icon} {BOT_NAME} v{VERSION} | {timestamp} UTC"
        )
        embed.timestamp = datetime.now(timezone.utc)


# Singleton instance for consistent UI management
_ui_manager = None

def get_ui_manager() -> UIManager:
    """Get the global UI manager instance."""
    global _ui_manager
    if _ui_manager is None:
        _ui_manager = UIManager()
    return _ui_manager
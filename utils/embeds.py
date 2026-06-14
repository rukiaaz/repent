"""
Repent - Premium Embed System
Enterprise-grade embeds with consistent design language.
Uses the new UI Manager and Theme Manager for premium appearance.
"""

import discord
from datetime import datetime, timezone
from config import BOT_NAME, VERSION
from utils.ui_manager import get_ui_manager
from utils.theme_manager import get_theme_manager

# Get singleton instances
ui_manager = get_ui_manager()
theme = get_theme_manager()

# ═══════════════════════════════════════════════════════════════
# PREMIUM EMBED BUILDERS
# ═══════════════════════════════════════════════════════════════

def success_embed(title: str, description: str = "", guild: discord.Guild = None) -> discord.Embed:
    """Premium success embed with consistent design."""
    return ui_manager.create_success_embed(title, description, guild)

def error_embed(description: str = "An error occurred.", guild: discord.Guild = None) -> discord.Embed:
    """Premium error embed with consistent design."""
    return ui_manager.create_error_embed(description, guild)

def warning_embed(title: str, description: str = "", guild: discord.Guild = None) -> discord.Embed:
    """Premium warning embed with consistent design."""
    return ui_manager.create_warning_embed(title, description, guild)

def info_embed(title: str, description: str = "", guild: discord.Guild = None) -> discord.Embed:
    """Premium info embed with consistent design."""
    return ui_manager.create_info_embed(title, description, guild)

def security_embed(title: str, description: str = "", status: str = "active", guild: discord.Guild = None) -> discord.Embed:
    """Premium security embed with status indication."""
    return ui_manager.create_security_embed(
        status=status,
        protection_level="Maximum",
        metrics={},
        guild=guild
    )

def dashboard_embed(title: str, sections: list, guild: discord.Guild = None) -> discord.Embed:
    """Premium dashboard embed with sections."""
    return ui_manager.create_dashboard_embed(
        title=title,
        sections=sections,
        guild=guild
    )

def alert_embed(title: str, description: str, threat_level: str = "Medium", guild: discord.Guild = None) -> discord.Embed:
    """Premium security alert embed with threat level."""
    return ui_manager.create_alert_embed(
        title=title,
        description=description,
        threat_level=threat_level,
        action_taken="Monitoring",
        guild=guild
    )

# ═══════════════════════════════════════════════════════════════
# LEGACY COMPATIBILITY LAYER
# ═══════════════════════════════════════════════════════════════
# These functions maintain backward compatibility while using the new premium design

def antinuke_embed(action: str, target: str, responsible: str, punishment: str, guild: discord.Guild) -> discord.Embed:
    """
    Legacy antinuke embed - now uses premium design.
    Kept for backward compatibility with existing code.
    """
    description = f"Suspicious activity detected in **{guild.name}**"
    
    # Determine threat level based on action
    threat_levels = {
        "ban": "Critical",
        "channel_delete": "Critical",
        "role_delete": "Critical",
        "webhook_create": "Critical",
        "kick": "High",
    }
    threat_level = threat_levels.get(action, "Medium")
    
    return ui_manager.create_alert_embed(
        title="Security Alert",
        description=description,
        threat_level=threat_level,
        action_taken=f"Punishment applied: {punishment}",
        guild=guild
    )

def mod_action_embed(action: str, moderator: discord.Member, target: discord.Member, reason: str, color: int = None) -> discord.Embed:
    """
    Legacy moderation action embed - now uses premium design.
    Kept for backward compatibility with existing code.
    """
    if color is None:
        color = theme.color_info
    
    embed = discord.Embed(
        title=f"🛡️ {action}",
        description=f"Moderation action performed",
        color=color
    )
    
    embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    embed.add_field(name="Target", value=target.mention, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    
    if target.display_avatar:
        embed.set_thumbnail(url=target.display_avatar.url)
    
    ui_manager._set_premium_footer(embed)
    
    return embed

def log_embed(title: str, fields: list, color: int = None, thumbnail: str = None) -> discord.Embed:
    """
    Legacy log embed - now uses premium design.
    Kept for backward compatibility with existing code.
    """
    if color is None:
        color = theme.color_info
    
    sections = [
        {
            "name": field[0],
            "value": field[1],
            "inline": field[2] if len(field) > 2 else False
        }
        for field in fields[:4]
    ]
    
    # Create a basic dashboard embed
    embed = discord.Embed(title=title, color=color)
    
    for section in sections:
        embed.add_field(
            name=section["name"],
            value=section["value"],
            inline=section["inline"]
        )
    
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    
    ui_manager._set_premium_footer(embed)
    
    return embed

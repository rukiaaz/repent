"""
Professional Embed Templates
Consistent, professional embed templates for the bot.
White/Light theme to match website.
"""

import discord
from datetime import datetime
from typing import List, Dict, Optional

# Color Scheme - White/Light Theme
COLOR_WHITE = 0xFFFFFF          # White - Primary background
COLOR_SUCCESS = 0x10B981        # Emerald green - Success states
COLOR_WARNING = 0xF59E0B        # Amber - Warnings
COLOR_DANGER = 0xEF4444         # Red - Critical/Errors
COLOR_INFO = 0x3B82F6          # Blue - Information
COLOR_MUTED = 0x9CA3AF         # Gray - Disabled/Secondary
COLOR_ACCENT = 0x6366F1        # Indigo - Highlights


def config_setup_embed(
    title: str,
    description: str,
    config_fields: List[Dict],
    action_buttons: Optional[List[str]] = None,
    color: int = COLOR_WHITE
) -> discord.Embed:
    """
    Create professional configuration embed with dropdown-style layout.
    
    Args:
        title: Embed title
        description: Embed description
        config_fields: List of field dicts with 'name', 'value', 'inline' keys
        action_buttons: Optional list of action button names
        color: Embed color (default white)
    
    Returns:
        discord.Embed object
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    
    for field in config_fields:
        embed.add_field(
            name=field.get("name"),
            value=field.get("value"),
            inline=field.get("inline", True)
        )
    
    # Add timestamp
    embed.set_footer(text=f"Requested at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return embed


def action_confirmation_embed(
    action_type: str,
    target: str,
    details: Dict,
    warning: Optional[str] = None
) -> discord.Embed:
    """
    Create professional action confirmation embed.
    
    Args:
        action_type: Type of action (e.g., "Ban", "Kick", "Timeout")
        target: Target of the action
        details: Dictionary of action details
        warning: Optional warning message
    
    Returns:
        discord.Embed object
    """
    # Choose color based on action severity
    if "ban" in action_type.lower():
        color = COLOR_DANGER
    elif "kick" in action_type.lower():
        color = COLOR_WARNING
    else:
        color = COLOR_WHITE
    
    embed = discord.Embed(
        title=f"⚡ {action_type}",
        color=color
    )
    
    embed.add_field(name="Target", value=target, inline=False)
    
    for key, value in details.items():
        embed.add_field(name=key.replace("_", " ").title(), value=str(value), inline=False)
    
    if warning:
        embed.add_field(name="⚠️ Warning", value=warning, inline=False)
    
    embed.set_footer(text="Confirm or cancel this action")
    
    return embed


def status_dashboard_embed(
    system_name: str,
    status: str,
    metrics: Dict,
    color: Optional[int] = None
) -> discord.Embed:
    """
    Create professional status dashboard embed.
    
    Args:
        system_name: Name of the system (e.g., "Antinuke", "AutoMod")
        status: Current status (e.g., "Active", "Inactive")
        metrics: Dictionary of metrics to display
        color: Optional override color (defaults to status-based)
    
    Returns:
        discord.Embed object
    """
    # Determine color based on status
    if color is None:
        if status.lower() == "active" or status.lower() == "enabled":
            color = COLOR_SUCCESS
        elif status.lower() == "inactive" or status.lower() == "disabled":
            color = COLOR_MUTED
        else:
            color = COLOR_WARNING
    
    embed = discord.Embed(
        title=f"📊 {system_name} Status",
        color=color
    )
    
    embed.add_field(name="Status", value=f"{'✅' if status.lower() in ['active', 'enabled'] else '❌'} {status}", inline=False)
    
    for key, value in metrics.items():
        embed.add_field(name=key, value=str(value), inline=False)
    
    embed.set_footer(text=f"Updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return embed


def whitelist_list_embed(
    users: List[Dict],
    guild_name: str
) -> discord.Embed:
    """
    Create whitelist list embed.
    
    Args:
        users: List of user dictionaries with user_id, trust_level, etc.
        guild_name: Name of the guild
    
    Returns:
        discord.Embed object
    """
    embed = discord.Embed(
        title=f"⭐ Whitelist - {guild_name}",
        color=COLOR_WHITE
    )
    
    if not users:
        embed.description = "No whitelisted users."
        return embed
    
    # Group by trust level
    level_1 = [u for u in users if u.get("trust_level") == 1]
    level_2 = [u for u in users if u.get("trust_level") == 2]
    
    if level_1:
        level_1_names = "\n".join(f"<@{u['user_id']}> ⭐" for u in level_1[:20])
        embed.add_field(name="Level 1 (Partial)", value=level_1_names, inline=False)
    
    if level_2:
        level_2_names = "\n".join(f"<@{u['user_id']}> ⭐⭐" for u in level_2[:20])
        embed.add_field(name="Level 2 (Full)", value=level_2_names, inline=False)
    
    total = len(users)
    embed.set_footer(text=f"Total: {total} user(s)")
    
    return embed


def antinuke_config_embed(
    enabled: bool,
    punishment: str,
    thresholds: Dict,
    guild_name: str
) -> discord.Embed:
    """
    Create antinuke configuration embed.
    
    Args:
        enabled: Whether antinuke is enabled
        punishment: Punishment type
        thresholds: Dictionary of action thresholds
        guild_name: Name of the guild
    
    Returns:
        discord.Embed object
    """
    color = COLOR_SUCCESS if enabled else COLOR_MUTED
    
    embed = discord.Embed(
        title=f"🛡️ Antinuke Configuration - {guild_name}",
        color=color
    )
    
    embed.add_field(
        name="Protection Status",
        value="✅ Enabled" if enabled else "❌ Disabled",
        inline=True
    )
    
    embed.add_field(
        name="Punishment Mode",
        value=f"`{punishment}`",
        inline=True
    )
    
    # Format thresholds
    threshold_lines = []
    for action_type, (max_count, window) in thresholds.items():
        threshold_lines.append(f"`{action_type}`: {max_count}/{window}s")
    
    if threshold_lines:
        embed.add_field(
            name="Thresholds",
            value="\n".join(threshold_lines),
            inline=False
        )
    
    embed.set_footer(text="Configure thresholds with /antinukeconfig")
    
    return embed


def moderation_result_embed(
    action: str,
    target: str,
    moderator: str,
    reason: str,
    success: bool
) -> discord.Embed:
    """
    Create moderation action result embed.
    
    Args:
        action: Action performed (Ban, Kick, Timeout, etc.)
        target: Target user
        moderator: Moderator who performed action
        reason: Reason for action
        success: Whether action was successful
    
    Returns:
        discord.Embed object
    """
    color = COLOR_SUCCESS if success else COLOR_DANGER
    
    emoji = "✅" if success else "❌"
    embed = discord.Embed(
        title=f"{emoji} {action} Result",
        color=color
    )
    
    embed.add_field(name="Target", value=target, inline=True)
    embed.add_field(name="Moderator", value=moderator, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    embed.set_footer(text=f"Requested at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return embed

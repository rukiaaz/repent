"""
Dropdown Utility Functions
Reusable dropdown builders for Discord select menus.
"""

import discord
from typing import List, Optional


def create_action_dropdown(
    enable_label: str = "Enable",
    disable_label: str = "Disable",
    view_label: str = "View Status",
    custom_action: Optional[str] = None,
    custom_label: Optional[str] = None
) -> List[discord.SelectOption]:
    """
    Create standard action dropdown options for enable/disable/view patterns.
    
    Args:
        enable_label: Label for enable option
        disable_label: Label for disable option
        view_label: Label for view status option
        custom_action: Optional custom action value
        custom_label: Optional custom action label
    
    Returns:
        List of SelectOption objects
    """
    options = [
        discord.SelectOption(
            label=enable_label,
            value="enable",
            description="Turn on system",
            emoji="✅"
        ),
        discord.SelectOption(
            label=disable_label,
            value="disable",
            description="Turn off system",
            emoji="❌"
        ),
        discord.SelectOption(
            label=view_label,
            value="status",
            description="Check current status",
            emoji="📊"
        )
    ]
    
    if custom_action and custom_label:
        options.append(
            discord.SelectOption(
                label=custom_label,
                value=custom_action,
                emoji="⚙️"
            )
        )
    
    return options


def create_duration_dropdown(
    include_off: bool = False,
    short_durations_only: bool = False,
    include_week: bool = True
) -> List[discord.SelectOption]:
    """
    Create duration dropdown with time options.
    
    Args:
        include_off: Include "Off" option
        short_durations_only: Only show short durations (under 1 hour)
        include_week: Include 1 week option
    
    Returns:
        List of SelectOption objects with duration in seconds
    """
    options = []
    
    if include_off:
        options.append(
            discord.SelectOption(
                label="Off",
                value="0",
                description="Disable",
                emoji="🚫"
            )
        )
    
    # Short durations
    options.extend([
        discord.SelectOption(label="1 Minute", value="60", description="1 minute"),
        discord.SelectOption(label="5 Minutes", value="300", description="5 minutes"),
        discord.SelectOption(label="10 Minutes", value="600", description="10 minutes"),
        discord.SelectOption(label="15 Minutes", value="900", description="15 minutes"),
    ])
    
    if not short_durations_only:
        # Longer durations
        options.extend([
            discord.SelectOption(label="30 Minutes", value="1800", description="30 minutes"),
            discord.SelectOption(label="1 Hour", value="3600", description="1 hour"),
            discord.SelectOption(label="6 Hours", value="21600", description="6 hours"),
            discord.SelectOption(label="12 Hours", value="43200", description="12 hours"),
            discord.SelectOption(label="1 Day", value="86400", description="24 hours"),
        ])
        
        if include_week:
            options.append(
                discord.SelectOption(
                    label="1 Week",
                    value="604800",
                    description="7 days"
                )
            )
            options.append(
                discord.SelectOption(
                    label="28 Days (Max)",
                    value="2419200",
                    description="28 days"
                )
            )
    
    return options


def create_reason_dropdown(context: str = "moderation") -> List[discord.SelectOption]:
    """
    Create reason dropdown based on context (moderation, antinuke, etc.).
    
    Args:
        context: Context for reasons (moderation, antinuke, spam, etc.)
    
    Returns:
        List of SelectOption objects
    """
    if context == "moderation":
        return [
            discord.SelectOption(
                label="Nuke/Ban Evasion",
                value="nuke_evasion",
                description="Evading ban/nuke",
                emoji="⚡"
            ),
            discord.SelectOption(
                label="Spam",
                value="spam",
                description="Spamming messages",
                emoji="📢"
            ),
            discord.SelectOption(
                label="Harassment",
                value="harassment",
                description="Harassing users",
                emoji="⚠️"
            ),
            discord.SelectOption(
                label="Rule Violation",
                value="rule_violation",
                description="Breaking server rules",
                emoji="⚠️"
            ),
            discord.SelectOption(
                label="Self-Bot",
                value="self_bot",
                description="Using self-bot",
                emoji="🤖"
            ),
            discord.SelectOption(
                label="Custom Reason",
                value="custom",
                description="Enter custom reason",
                emoji="✏️"
            )
        ]
    elif context == "antinuke":
        return [
            discord.SelectOption(
                label="Nuke Attempt",
                value="nuke",
                description="Server nuke attempt",
                emoji="💥"
            ),
            discord.SelectOption(
                label="Mass Ban",
                value="mass_ban",
                description="Mass banning users",
                emoji="🔨"
            ),
            discord.SelectOption(
                label="Mass Role Deletion",
                value="role_deletion",
                description="Deleting roles",
                emoji="🗑️"
            ),
            discord.SelectOption(
                label="Mass Channel Deletion",
                value="channel_deletion",
                description="Deleting channels",
                emoji="📉"
            ),
            discord.SelectOption(
                label="Other",
                value="other",
                description="Other threat",
                emoji="⚠️"
            )
        ]
    else:
        # Default reasons
        return [
            discord.SelectOption(label="Rule Violation", value="rule_violation", emoji="⚠️"),
            discord.SelectOption(label="Custom", value="custom", emoji="✏️")
        ]


def create_trust_level_dropdown() -> List[discord.SelectOption]:
    """
    Create trust level dropdown for whitelists.
    
    Returns:
        List of SelectOption objects
    """
    return [
        discord.SelectOption(
            label="Level 1 (Partial)",
            value="1",
            description="Bypasses AutoMod only",
            emoji="⭐"
        ),
        discord.SelectOption(
            label="Level 2 (Full)",
            value="2",
            description="Bypasses AutoMod + Antinuke",
            emoji="⭐⭐"
        )
    ]


def create_punishment_type_dropdown() -> List[discord.SelectOption]:
    """
    Create punishment type dropdown.
    
    Returns:
        List of SelectOption objects
    """
    return [
        discord.SelectOption(
            label="Ban",
            value="ban",
            description="Permanent removal",
            emoji="🔨"
        ),
        discord.SelectOption(
            label="Kick",
            value="kick",
            description="Removal (can rejoin)",
            emoji="👢"
        ),
        discord.SelectOption(
            label="Strip Roles",
            value="strip",
            description="Remove all roles",
            emoji="🗑️"
        ),
        discord.SelectOption(
            label="Timeout",
            value="timeout",
            description="Temporarily silence (28 days max)",
            emoji="⏰"
        )
    ]


def create_bool_dropdown(
    yes_label: str = "Yes",
    no_label: str = "No",
    yes_desc: str = "Enable/Confirm",
    no_desc: str = "Disable/Cancel"
) -> List[discord.SelectOption]:
    """
    Create boolean dropdown options.
    
    Args:
        yes_label: Label for yes option
        no_label: Label for no option
        yes_desc: Description for yes option
        no_desc: Description for no option
    
    Returns:
        List of SelectOption objects
    """
    return [
        discord.SelectOption(
            label=yes_label,
            value="yes",
            description=yes_desc,
            emoji="✅"
        ),
        discord.SelectOption(
            label=no_label,
            value="no",
            description=no_desc,
            emoji="❌"
        )
    ]


def create_whitelist_action_dropdown() -> List[discord.SelectOption]:
    """
    Create dropdown for whitelist actions.
    
    Returns:
        List of SelectOption objects
    """
    return [
        discord.SelectOption(
            label="Add User to Whitelist",
            value="add",
            description="Add user to whitelist",
            emoji="➕"
        ),
        discord.SelectOption(
            label="Remove from Whitelist",
            value="remove",
            description="Remove from whitelist",
            emoji="➖"
        ),
        discord.SelectOption(
            label="View Whitelist",
            value="list",
            description="Show all whitelisted users",
            emoji="📋"
        )
    ]


def create_case_action_dropdown() -> List[discord.SelectOption]:
    """
    Create dropdown for case actions.
    
    Returns:
        List of SelectOption objects
    """
    return [
        discord.SelectOption(
            label="Create Case",
            value="create",
            description="Create new case",
            emoji="📝"
        ),
        discord.SelectOption(
            label="View Cases",
            value="view",
            description="View cases for user",
            emoji="👁️"
        ),
        discord.SelectOption(
            label="Resolve Case",
            value="resolve",
            description="Mark case as resolved",
            emoji="✅"
        ),
        discord.SelectOption(
            label="Add Evidence",
            value="evidence",
            description="Add evidence to case",
            emoji="📎"
        )
    ]

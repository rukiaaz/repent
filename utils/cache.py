"""
Repent - Role and channel snapshot/caching logic
"""

import discord
from database import cache_role, cache_channel, delete_cached_role, delete_cached_channel
import json


async def snapshot_guild(guild: discord.Guild, trigger_event: str = "manual"):
    """Cache all roles and channels for a guild. Called on_ready and when changes happen."""
    for role in guild.roles:
        try:
            await cache_role(guild.id, role)
        except Exception:
            pass
    for channel in guild.channels:
        try:
            await cache_channel(guild.id, channel)
        except Exception:
            pass
    
    # Also create a full timestamped snapshot for restoration
    try:
        from database import create_snapshot
        snapshot_data = {
            'guild_name': guild.name,
            'guild_icon': str(guild.icon) if guild.icon else None,  # Convert Asset to string
            'channels': [],
            'roles': []
        }
        
        for channel in guild.channels:
            channel_data = {
                'id': channel.id,
                'name': channel.name,
                'type': channel.type.value,
                'category_id': channel.category_id,
                'position': channel.position
            }
            
            # Add type-specific settings
            if hasattr(channel, 'topic'):
                channel_data['topic'] = channel.topic or ''
            if hasattr(channel, 'nsfw'):
                channel_data['nsfw'] = channel.nsfw
            if hasattr(channel, 'slowmode_delay'):
                channel_data['slowmode'] = channel.slowmode_delay
            if hasattr(channel, 'bitrate'):
                channel_data['bitrate'] = channel.bitrate
            if hasattr(channel, 'user_limit'):
                channel_data['user_limit'] = channel.user_limit
            if hasattr(channel, 'rtc_region'):
                channel_data['rtc_region'] = str(channel.rtc_region) if channel.rtc_region else None
            if hasattr(channel, 'overwrites'):
                # Serialize overwrites
                overwrites_dict = {}
                for target, overwrite in channel.overwrites.items():
                    target_id = target.id
                    overwrites_dict[str(target_id)] = {
                        'allow': overwrite.pair[0].value,
                        'deny': overwrite.pair[1].value,
                        'type': 'role' if isinstance(target, discord.Role) else 'member'
                    }
                channel_data['overwrites'] = overwrites_dict
            
            snapshot_data['channels'].append(channel_data)
        
        for role in guild.roles:
            snapshot_data['roles'].append({
                'id': role.id,
                'name': role.name,
                'color': role.color.value,
                'position': role.position,
                'permissions': role.permissions.value,
                'hoist': role.hoist,
                'mentionable': role.mentionable
            })
        
        # Create snapshot with protection if triggered by attack detection
        is_protected = 1 if trigger_event in ["attack_detected", "emergency_mode"] else 0
        
        await create_snapshot(
            guild.id,
            snapshot_data,
            is_protected=is_protected,
            trigger_event=trigger_event
        )
    except Exception as e:
        print(f"Failed to create snapshot: {e}")


async def snapshot_role(role: discord.Role):
    """Cache a single role."""
    try:
        await cache_role(role.guild.id, role)
    except Exception:
        pass


async def snapshot_channel(channel: discord.abc.GuildChannel):
    """Cache a single channel."""
    try:
        await cache_channel(channel.guild.id, channel)
    except Exception:
        pass


async def remove_cached_role(role: discord.Role):
    try:
        await delete_cached_role(role.guild.id, role.id)
    except Exception:
        pass


async def remove_cached_channel(channel: discord.abc.GuildChannel):
    try:
        await delete_cached_channel(channel.guild.id, channel.id)
    except Exception:
        pass

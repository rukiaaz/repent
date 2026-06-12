"""
Repent - Role and channel snapshot/caching logic
"""

import discord
from database import cache_role, cache_channel, delete_cached_role, delete_cached_channel


async def snapshot_guild(guild: discord.Guild):
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
            'guild_icon': guild.icon,
            'channels': [],
            'roles': []
        }
        
        for channel in guild.channels:
            snapshot_data['channels'].append({
                'id': channel.id,
                'name': channel.name,
                'type': channel.type.value,
                'category_id': channel.category_id,
                'position': channel.position
            })
        
        for role in guild.roles:
            snapshot_data['roles'].append({
                'id': role.id,
                'name': role.name,
                'color': role.color.value,
                'position': role.position,
                'permissions': role.permissions.value
            })
        
        await create_snapshot(guild.id, snapshot_data)
    except Exception:
        pass


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

"""
Simple, Robust Command Sync System
Guaranteed to work without complex validation that could block sync.
"""

import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)


async def sync_commands_simple(bot: commands.Bot, clear_first: bool = False) -> dict:
    """
    Simple, robust command sync.
    Just sync everything without complex validation.
    
    Args:
        bot: The bot instance
        clear_first: If True, clear all commands before syncing
    
    Returns:
        Dictionary with sync statistics
    """
    logger.info("=" * 70)
    logger.info("SIMPLE COMMAND SYNC")
    logger.info("=" * 70)
    
    try:
        # Optionally clear all commands first
        if clear_first:
            logger.info("Clearing all commands...")
            await bot.tree.clear()
            logger.info("✓ Commands cleared")
        
        # Get all commands in tree before sync
        tree_commands = list(bot.tree.walk_commands())
        logger.info(f"Commands in tree before sync: {len(tree_commands)}")
        
        # Log all commands
        for cmd in tree_commands:
            logger.info(f"  - /{cmd.qualified_name}")
        
        # Sync globally
        logger.info("Syncing commands globally...")
        synced = await bot.tree.sync()
        logger.info(f"✓ Synced {len(synced)} commands to Discord")
        
        # Verify sync
        logger.info("Verifying sync...")
        global_commands = await bot.tree.fetch_global_commands()
        logger.info(f"✓ Verified {len(global_commands)} commands in Discord")
        
        # Log synced commands
        for cmd in global_commands:
            logger.info(f"  ✓ /{cmd['name']}")
        
        if len(tree_commands) != len(global_commands):
            logger.warning(f"⚠ Mismatch: Tree has {len(tree_commands)}, Discord has {len(global_commands)}")
        
        stats = {
            'tree_commands': len(tree_commands),
            'synced': len(synced),
            'verified': len(global_commands),
            'success': True
        }
        
        logger.info("=" * 70)
        logger.info(f"SYNC COMPLETE: {stats}")
        logger.info("=" * 70)
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


async def sync_guild_commands(bot: commands.Bot, guild_id: int) -> dict:
    """
    Sync commands to a specific guild.
    
    Args:
        bot: The bot instance
        guild_id: Guild ID to sync to
    
    Returns:
        Dictionary with sync statistics
    """
    logger.info(f"Syncing commands to guild {guild_id}...")
    
    try:
        # Sync to guild
        synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        logger.info(f"✓ Synced {len(synced)} commands to guild {guild_id}")
        
        # Verify
        guild_commands = await bot.tree.fetch_commands(guild=discord.Object(id=guild_id))
        logger.info(f"✓ Verified {len(guild_commands)} commands in guild {guild_id}")
        
        return {
            'synced': len(synced),
            'verified': len(guild_commands),
            'success': True
        }
        
    except Exception as e:
        logger.error(f"❌ Guild sync failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }

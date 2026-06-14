"""
Quick script to test command sync without restarting the bot.
Run this while the bot is running.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import discord
from discord.ext import commands

# Import your bot (you'll need to adapt this)
# This is a simplified version that connects to your bot's token

import logging
logging.basicConfig(level=logging.INFO)

async def test_sync():
    """Test command sync."""
    
    # You'll need to provide your bot token here temporarily for testing
    # Or we can use the bot if it's already running
    
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN not set in environment")
        return
    
    # Create a minimal bot instance
    intents = discord.Intents.default()
    intents.message_content = False
    
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")
        
        # Walk the command tree
        print("\nCommands in tree:")
        for cmd in bot.tree.walk_commands():
            print(f"  - /{cmd.qualified_name}")
        
        # Try to sync
        print("\nAttempting to sync...")
        try:
            synced = await bot.tree.sync()
            print(f"✓ Synced {len(synced)} commands")
            
            # Verify
            global_cmds = await bot.tree.fetch_global_commands()
            print(f"✓ Verified {len(global_cmds)} commands in Discord")
            
            print("\nCommands in Discord:")
            for cmd in global_cmds:
                print(f"  ✓ /{cmd['name']}")
                
        except Exception as e:
            print(f"❌ Sync failed: {e}")
            import traceback
            traceback.print_exc()
        
        await bot.close()
    
    try:
        await bot.start(token)
    except Exception as e:
        print(f"Failed to start bot: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sync())

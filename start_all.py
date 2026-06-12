"""
Balance Bot & API Server Startup Script
Runs both the Discord bot and the FastAPI server together.
"""

import asyncio
import subprocess
import sys
from dotenv import load_dotenv
load_dotenv()

async def run_bot():
    """Run the Discord bot."""
    print("Starting Discord bot...")
    process = await asyncio.create_subprocess_exec(
        sys.executable, "main.py"
    )
    await process.wait()

def run_api():
    """Run the FastAPI server."""
    print("Starting API server...")
    subprocess.run([sys.executable, "bot_api.py"])

async def main():
    """Run both bot and API server concurrently."""
    # Start API server in background
    api_process = await asyncio.create_subprocess_exec(
        sys.executable, "bot_api.py"
    )
    
    # Start bot
    bot_process = await asyncio.create_subprocess_exec(
        sys.executable, "main.py"
    )
    
    # Wait for both
    await asyncio.gather(
        api_process.wait(),
        bot_process.wait()
    )

if __name__ == "__main__":
    print("Starting Balance Bot and API Server...")
    print("=" * 50)
    print("Bot: python main.py")
    print("API: python bot_api.py")
    print("=" * 50)
    
    # For now, just run API server first (simpler for testing)
    # In production, use the async version above
    print("\nStarting API server first (for development)...")
    print("Once API is running, you can start the bot in another terminal.\n")
    run_api()
"""
Repent - Production-Grade Command Synchronization System

This module provides a complete command sync solution with:
- Automatic sync on startup
- Sync logging
- Failed command detection
- Missing command detection
- Duplicate command detection
- Sync statistics
- Validation and diagnostics
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class SyncStatistics:
    """Track sync statistics."""
    
    def __init__(self):
        self.total_commands: int = 0
        self.synced_commands: int = 0
        self.failed_commands: int = 0
        self.missing_commands: int = 0
        self.duplicate_commands: int = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.sync_errors: List[Dict[str, str]] = []
        self.failed_cogs: List[str] = []
    
    def start(self):
        """Start the sync timer."""
        self.start_time = datetime.now(timezone.utc)
    
    def end(self):
        """End the sync timer."""
        self.end_time = datetime.now(timezone.utc)
    
    def duration(self) -> float:
        """Get sync duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def report(self) -> str:
        """Generate a sync report."""
        report = []
        report.append("=" * 70)
        report.append("COMMAND SYNC REPORT")
        report.append("=" * 70)
        report.append(f"Duration: {self.duration():.2f}s")
        report.append(f"Total Commands: {self.total_commands}")
        report.append(f"Synced: {self.synced_commands}")
        report.append(f"Failed: {self.failed_commands}")
        report.append(f"Missing: {self.missing_commands}")
        report.append(f"Duplicates: {self.duplicate_commands}")
        
        if self.sync_errors:
            report.append("\n" + "=" * 70)
            report.append("SYNC ERRORS")
            report.append("=" * 70)
            for error in self.sync_errors:
                report.append(f"[ERROR] {error['command']}: {error['error']}")
        
        if self.failed_cogs:
            report.append("\n" + "=" * 70)
            report.append("FAILED COGS")
            report.append("=" * 70)
            for cog in self.failed_cogs:
                report.append(f"[FAIL] {cog}")
        
        report.append("=" * 70)
        return "\n".join(report)


class CommandSyncManager:
    """Production-grade command synchronization manager."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stats = SyncStatistics()
        self.logger = logger
    
    async def sync_all(self, guild_id: Optional[int] = None) -> SyncStatistics:
        """
        Synchronize all commands.
        
        Args:
            guild_id: If provided, sync only to this guild. If None, sync globally.
        
        Returns:
            SyncStatistics object with sync results
        """
        self.stats = SyncStatistics()
        self.stats.start()
        
        self.logger.info("=" * 70)
        self.logger.info("STARTING COMMAND SYNCHRONIZATION")
        self.logger.info(f"Sync target: {'Guild ' + str(guild_id) if guild_id else 'Global'}")
        self.logger.info("=" * 70)
        
        try:
            # Step 1: Validate loaded cogs and commands
            await self._validate_loaded_commands()
            
            # Step 2: Detect duplicate commands
            await self._detect_duplicates()
            
            # Step 3: Perform sync
            if guild_id:
                await self._sync_guild(guild_id)
            else:
                await self._sync_global()
            
            # Step 4: Verify sync
            await self._verify_sync(guild_id)
            
            # Step 5: Generate report
            self.stats.end()
            report = self.stats.report()
            self.logger.info(report)
            
            return self.stats
            
        except Exception as e:
            self.stats.end()
            self.logger.error(f"Sync failed with exception: {e}", exc_info=True)
            return self.stats
    
    async def _validate_loaded_commands(self):
        """Validate that all cogs loaded successfully."""
        self.logger.info("Step 1: Validating loaded commands")
        
        # Get all loaded cogs
        loaded_cogs = self.bot.cogs
        
        if not loaded_cogs:
            self.logger.warning("[WARN] No cogs loaded!")
            self.stats.failed_cogs.append("No cogs loaded")
            return
        
        self.logger.info(f"[OK] {len(loaded_cogs)} cogs loaded")
        
        # Count commands in each cog
        for cog_name, cog in loaded_cogs.items():
            try:
                # Get app commands from cog
                if hasattr(cog, '__cog_app_commands__'):
                    cmd_count = len(cog.__cog_app_commands__)
                    self.stats.total_commands += cmd_count
                    self.logger.info(f"[OK] {cog_name}: {cmd_count} commands")
                else:
                    self.logger.warning(f"[WARN] {cog_name}: No app_commands attribute")
                    self.stats.failed_cogs.append(cog_name)
            except Exception as e:
                self.logger.error(f"[ERROR] {cog_name}: {e}")
                self.stats.failed_cogs.append(cog_name)
    
    async def _detect_duplicates(self):
        """Detect duplicate command names."""
        self.logger.info("Step 2: Detecting duplicate commands")
        
        command_names: Dict[str, List[str]] = {}
        
        # Walk the command tree
        for command in self.bot.tree.walk_commands():
            name = command.qualified_name
            if name not in command_names:
                command_names[name] = []
            command_names[name].append(str(command))
        
        # Check for duplicates
        for name, locations in command_names.items():
            if len(locations) > 1:
                self.stats.duplicate_commands += 1
                self.logger.warning(f"[WARN] Duplicate command: /{name} in {locations}")
                self.stats.sync_errors.append({
                    'command': name,
                    'error': f'Duplicate in {locations}'
                })
    
    async def _sync_global(self):
        """Sync commands globally."""
        self.logger.info("Step 3: Syncing global commands")
        
        try:
            synced = await self.bot.tree.sync()
            self.stats.synced_commands = len(synced)
            self.logger.info(f"[OK] Synced {len(synced)} global commands")
            
            # Log each synced command
            for cmd in synced:
                self.logger.info(f"  [SYNCED] /{cmd['name']}")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Global sync failed: {e}", exc_info=True)
            self.stats.failed_commands = self.stats.total_commands
            self.stats.sync_errors.append({
                'command': 'GLOBAL_SYNC',
                'error': str(e)
            })
    
    async def _sync_guild(self, guild_id: int):
        """Sync commands to a specific guild."""
        self.logger.info(f"Step 3: Syncing to guild {guild_id}")
        
        try:
            synced = await self.bot.tree.sync(guild=discord.Object(id=guild_id))
            self.stats.synced_commands = len(synced)
            self.logger.info(f"[OK] Synced {len(synced)} commands to guild {guild_id}")
            
            # Log each synced command
            for cmd in synced:
                self.logger.info(f"  [SYNCED] /{cmd['name']}")
            
        except Exception as e:
            self.logger.error(f"[ERROR] Guild sync failed: {e}", exc_info=True)
            self.stats.failed_commands = self.stats.total_commands
            self.stats.sync_errors.append({
                'command': f'GUILD_SYNC_{guild_id}',
                'error': str(e)
            })
    
    async def _verify_sync(self, guild_id: Optional[int] = None):
        """Verify that commands were successfully synced."""
        self.logger.info("Step 4: Verifying sync")
        
        try:
            if guild_id:
                synced_commands = await self.bot.tree.fetch_commands(guild=discord.Object(id=guild_id))
            else:
                synced_commands = await self.bot.tree.fetch_global_commands()
            
            self.logger.info(f"[OK] Verified {len(synced_commands)} commands in Discord")
            
            # Compare with tree
            tree_commands = list(self.bot.tree.walk_commands())
            
            if len(synced_commands) != len(tree_commands):
                missing = len(tree_commands) - len(synced_commands)
                self.stats.missing_commands = missing
                self.logger.warning(f"[WARN] {missing} commands missing from Discord")
                
                # Find missing commands
                synced_names = {cmd['name'] for cmd in synced_commands}
                tree_names = {cmd.qualified_name for cmd in tree_commands}
                
                missing_names = tree_names - synced_names
                for name in missing_names:
                    self.logger.warning(f"  [MISSING] /{name}")
                    self.stats.sync_errors.append({
                        'command': name,
                        'error': 'Missing from Discord after sync'
                    })
            else:
                self.logger.info("[OK] All commands verified in Discord")
        
        except Exception as e:
            self.logger.error(f"[ERROR] Sync verification failed: {e}", exc_info=True)


class StartupValidator:
    """Validate bot startup and command loading."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger
        self.validation_errors: List[Dict[str, str]] = []
    
    async def validate_all(self) -> bool:
        """
        Validate all aspects of bot startup.
        
        Returns:
            True if all validations passed, False otherwise
        """
        self.logger.info("=" * 70)
        self.logger.info("STARTUP VALIDATION")
        self.logger.info("=" * 70)
        
        all_passed = True
        
        # Validate cogs
        if not await self._validate_cogs():
            all_passed = False
        
        # Validate commands
        if not await self._validate_commands():
            all_passed = False
        
        # Validate tree
        if not await self._validate_tree():
            all_passed = False
        
        # Generate report
        if self.validation_errors:
            self.logger.info("\n" + "=" * 70)
            self.logger.info("VALIDATION ERRORS")
            self.logger.info("=" * 70)
            for error in self.validation_errors:
                self.logger.error(f"[FAIL] {error['command']}: {error['error']}")
            self.logger.info("=" * 70)
        else:
            self.logger.info("[OK] All validations passed")
        
        return all_passed
    
    async def _validate_cogs(self) -> bool:
        """Validate that all cogs loaded successfully."""
        self.logger.info("Validating cogs...")
        
        loaded_cogs = self.bot.cogs
        
        if not loaded_cogs:
            self.logger.error("[FAIL] No cogs loaded!")
            self.validation_errors.append({
                'command': 'COG_LOADING',
                'error': 'No cogs loaded'
            })
            return False
        
        self.logger.info(f"[OK] {len(loaded_cogs)} cogs loaded")
        return True
    
    async def _validate_commands(self) -> bool:
        """Validate that all commands are properly registered."""
        self.logger.info("Validating commands...")
        
        all_valid = True
        
        for cog_name, cog in self.bot.cogs.items():
            try:
                if hasattr(cog, '__cog_app_commands__'):
                    commands = cog.__cog_app_commands__
                    for cmd in commands:
                        # Check if command has a callback
                        if not hasattr(cmd, 'callback') or cmd.callback is None:
                            self.logger.error(f"[FAIL] /{cmd.qualified_name}: Missing callback")
                            self.validation_errors.append({
                                'command': cmd.qualified_name,
                                'error': 'Missing callback'
                            })
                            all_valid = False
                        else:
                            self.logger.info(f"[OK] /{cmd.qualified_name}: Valid")
            except Exception as e:
                self.logger.error(f"[FAIL] {cog_name}: {e}")
                self.validation_errors.append({
                    'command': cog_name,
                    'error': str(e)
                })
                all_valid = False
        
        return all_valid
    
    async def _validate_tree(self) -> bool:
        """Validate the command tree."""
        self.logger.info("Validating command tree...")
        
        try:
            tree_commands = list(self.bot.tree.walk_commands())
            
            if not tree_commands:
                self.logger.error("[FAIL] No commands in tree!")
                self.validation_errors.append({
                    'command': 'TREE',
                    'error': 'No commands in tree'
                })
                return False
            
            self.logger.info(f"[OK] {len(tree_commands)} commands in tree")
            return True
            
        except Exception as e:
            self.logger.error(f"[FAIL] Tree validation failed: {e}")
            self.validation_errors.append({
                'command': 'TREE',
                'error': str(e)
            })
            return False


def get_sync_manager(bot: commands.Bot) -> CommandSyncManager:
    """Get the sync manager instance."""
    return CommandSyncManager(bot)


def get_startup_validator(bot: commands.Bot) -> StartupValidator:
    """Get the startup validator instance."""
    return StartupValidator(bot)

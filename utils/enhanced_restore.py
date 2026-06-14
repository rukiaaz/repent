"""
Enhanced Auto-Restore System
Handles consecutive nuke protection, multi-snapshot selection, and full state restoration.
"""

import discord
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Set, Optional
from database import select_best_snapshot, get_cached_channels, get_cached_roles


class ConsecutiveAttackDetector:
    """Detect consecutive nuke attempts to activate emergency mode."""
    
    def __init__(self, window_seconds: int = 300, threshold: int = 3):
        self.attack_history = {}  # guild_id -> list of attack timestamps
        self.window_seconds = window_seconds
        self.threshold = threshold
    
    def is_consecutive_attack(self, guild_id: int) -> bool:
        """Check if this is part of a consecutive attack sequence."""
        now = datetime.now(timezone.utc)
        window = timedelta(seconds=self.window_seconds)
        
        history = self.attack_history.get(guild_id, [])
        
        # Filter to attacks within window
        recent_attacks = [t for t in history if now - t < window]
        
        return len(recent_attacks) >= self.threshold
    
    def record_attack(self, guild_id: int):
        """Record an attack for this guild."""
        now = datetime.now(timezone.utc)
        if guild_id not in self.attack_history:
            self.attack_history[guild_id] = []
        self.attack_history[guild_id].append(now)
        
        # Clean old history
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds * 2)
        self.attack_history[guild_id] = [
            t for t in self.attack_history[guild_id] if t > cutoff
        ]
    
    def get_attack_count(self, guild_id: int, window_seconds: int = None) -> int:
        """Get count of attacks in specified time window."""
        window = timedelta(seconds=window_seconds) if window_seconds else timedelta(seconds=self.window_seconds)
        now = datetime.now(timezone.utc)
        
        history = self.attack_history.get(guild_id, [])
        recent_attacks = [t for t in history if now - t < window]
        
        return len(recent_attacks)


class EnhancedRestoreSystem:
    """Enhanced restoration system with full state recovery."""
    
    def __init__(self, bot, logger):
        self.bot = bot
        self.logger = logger
        self.attack_detector = ConsecutiveAttackDetector()
        self.emergency_mode_guilds: Set[int] = set()
    
    async def select_restore_snapshot(self, guild_id: int, attack_timestamp: str = None) -> Optional[Dict[str, Any]]:
        """Select the best snapshot for restoration."""
        try:
            snapshot = await select_best_snapshot(guild_id, attack_timestamp)
            if not snapshot:
                self.logger.warning(f"No snapshot found for guild {guild_id}")
                return None
            
            # Verify snapshot integrity
            from database import verify_snapshot_checksum
            if not await verify_snapshot_checksum(snapshot['id']):
                self.logger.error(f"Snapshot {snapshot['id']} failed checksum verification")
                return None
            
            return snapshot
        except Exception as e:
            self.logger.error(f"Failed to select snapshot: {e}", exc_info=True)
            return None
    
    async def restore_channels_full(self, guild: discord.Guild, snapshot_data: Dict[str, Any]) -> bool:
        """Restore channels with full state including category structure."""
        try:
            # Parse snapshot data
            channels_data = snapshot_data.get('channels', [])
            
            # 1. Create categories first (in correct position order)
            categories = sorted(
                [c for c in channels_data if c.get('type') == 4],
                key=lambda x: x.get('position', 0)
            )
            category_map = {}  # old_id -> new_id mapping
            
            for cat in categories:
                try:
                    new_cat = await guild.create_category(
                        name=cat.get('name', 'restored-category'),
                        position=cat.get('position', 0),
                        overwrites=self._parse_overwrites(guild, cat.get('overwrites', {})),
                        reason="[Repent] Restore category"
                    )
                    category_map[cat['id']] = new_cat.id
                    self.logger.info(f"Restored category: {cat.get('name')} (ID: {new_cat.id})")
                except Exception as e:
                    self.logger.error(f"Failed to restore category {cat.get('name')}: {e}")
            
            # 2. Create channels (in categories, correct position)
            non_category_channels = [
                c for c in channels_data if c.get('type') != 4
            ]
            
            for channel in non_category_channels:
                try:
                    # Map old category_id to new category_id
                    old_category_id = channel.get('category_id', 0)
                    new_category_id = category_map.get(old_category_id)
                    category = guild.get_channel(new_category_id) if new_category_id else None
                    
                    await self._create_channel_from_snapshot(guild, channel, category)
                    self.logger.info(f"Restored channel: {channel.get('name')} (type: {channel.get('type')})")
                except Exception as e:
                    self.logger.error(f"Failed to restore channel {channel.get('name')}: {e}")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore channels: {e}", exc_info=True)
            return False
    
    async def restore_roles_full(self, guild: discord.Guild, snapshot_data: Dict[str, Any]) -> Dict[int, int]:
        """Restore roles with correct hierarchy.
        
        Returns mapping of old_role_id -> new_role_id
        """
        role_map = {}
        
        try:
            roles_data = snapshot_data.get('roles', [])
            
            # Sort roles by position (bottom to top) to maintain hierarchy
            roles = sorted(
                roles_data,
                key=lambda x: x.get('position', 0)
            )
            
            for role in roles:
                try:
                    # Skip @everyone (cannot be recreated)
                    if role.get('name') == '@everyone':
                        role_map[role['id']] = guild.default_role.id
                        continue
                    
                    new_role = await guild.create_role(
                        name=role.get('name', 'restored-role'),
                        permissions=discord.Permissions(role.get('permissions', 0)),
                        color=discord.Color(role.get('color', 0)),
                        hoist=role.get('hoist', False),
                        mentionable=role.get('mentionable', False),
                        reason="[Repent] Restore role"
                    )
                    
                    # Set position after creation
                    await new_role.edit(position=role.get('position', 0))
                    
                    role_map[role['id']] = new_role.id
                    self.logger.info(f"Restored role: {role.get('name')} (ID: {new_role.id})")
                except Exception as e:
                    self.logger.error(f"Failed to restore role {role.get('name')}: {e}")
            
            return role_map
        except Exception as e:
            self.logger.error(f"Failed to restore roles: {e}", exc_info=True)
            return role_map
    
    async def _create_channel_from_snapshot(
        self,
        guild: discord.Guild,
        channel_data: Dict[str, Any],
        category: discord.CategoryChannel = None
    ) -> discord.abc.GuildChannel:
        """Create a channel from snapshot data."""
        channel_type = channel_data.get('type', 0)
        overwrites = self._parse_overwrites(guild, channel_data.get('overwrites', {}))
        
        kwargs = {
            'name': channel_data.get('name', 'restored'),
            'category': category,
            'position': channel_data.get('position', 0),
            'overwrites': overwrites,
            'reason': '[Repent] Restore deleted channel'
        }
        
        # Type-specific settings
        if channel_type == 0:  # Text channel
            kwargs.update({
                'topic': channel_data.get('topic', '') or None,
                'nsfw': channel_data.get('nsfw', False),
                'slowmode_delay': channel_data.get('slowmode', 0) or 0,
            })
            return await guild.create_text_channel(**kwargs)
        elif channel_type == 2:  # Voice channel
            kwargs.update({
                'bitrate': channel_data.get('bitrate'),
                'user_limit': channel_data.get('user_limit'),
            })
            if channel_data.get('rtc_region'):
                kwargs['rtc_region'] = channel_data['rtc_region']
            return await guild.create_voice_channel(**kwargs)
        elif channel_type == 4:  # Category
            kwargs.pop('category', None)
            return await guild.create_category(**kwargs)
        elif channel_type == 5:  # News channel
            kwargs.update({
                'topic': channel_data.get('topic', '') or None,
                'nsfw': channel_data.get('nsfw', False),
            })
            return await guild.create_news_channel(**kwargs)
        else:
            # Fallback to text channel
            return await guild.create_text_channel(**kwargs)
    
    def _parse_overwrites(self, guild: discord.Guild, overwrites_dict: Dict[str, Dict]) -> Dict:
        """Parse permission overwrites from dictionary."""
        overwrites = {}
        
        for target_id_str, overwrite_data in overwrites_dict.items():
            try:
                target_id = int(target_id_str)
                allow = overwrite_data.get('allow', 0)
                deny = overwrite_data.get('deny', 0)
                target_type = overwrite_data.get('type', 'role')
                
                if target_type == 'role':
                    target = guild.get_role(target_id)
                else:
                    target = guild.get_member(target_id)
                
                if target:
                    overwrites[target] = discord.PermissionOverwrite(
                        permissions=discord.Permissions(allow, deny)
                    )
            except Exception as e:
                self.logger.warning(f"Failed to parse overwrite for {target_id_str}: {e}")
        
        return overwrites
    
    async def activate_emergency_mode(self, guild: discord.Guild):
        """Activate emergency mode for a guild under consecutive attack."""
        if guild.id in self.emergency_mode_guilds:
            return  # Already in emergency mode
        
        self.emergency_mode_guilds.add(guild.id)
        
        # Create protected snapshot BEFORE any restoration
        try:
            from utils.cache import snapshot_guild
            await snapshot_guild(guild, trigger_event="emergency_mode")
            self.logger.security("EMERGENCY_MODE", f"Emergency mode activated for guild {guild.name}", guild.id)
        except Exception as e:
            self.logger.error(f"Failed to create emergency snapshot: {e}")
        
        # TODO: Add additional emergency mode actions
        # - Alert server owner
        # - Increase monitoring frequency
        # - Lock down risky operations
    
    def is_emergency_mode(self, guild_id: int) -> bool:
        """Check if guild is in emergency mode."""
        return guild_id in self.emergency_mode_guilds
    
    def deactivate_emergency_mode(self, guild_id: int):
        """Deactivate emergency mode for a guild."""
        self.emergency_mode_guilds.discard(guild_id)
        self.logger.info(f"Emergency mode deactivated for guild {guild_id}")

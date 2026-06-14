"""
Repent - Channel Rename Threshold System
Production-grade channel rename protection with per-user tracking.
"""

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
import aiosqlite
from config import DB_PATH


class ChannelRenameTracker:
    """
    Memory-efficient channel rename tracker with sliding window.
    
    Architecture:
    - Per-guild, per-user rename counting
    - Sliding time window for accurate rate limiting
    - Configurable thresholds per guild
    - Redis/cache friendly design
    - Minimal database writes
    - Survives high-activity raids
    """
    
    def __init__(self, window_seconds: int = 30):
        self.window_seconds = window_seconds
        
        # Memory structure: {guild_id: {user_id: deque of timestamps}}
        self._rename_history: Dict[int, Dict[int, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=100))
        )
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Default threshold settings
        self._default_threshold = 3  # renames
        self._default_window = 30  # seconds
        
        # Cached thresholds from database
        self._cached_thresholds: Dict[Tuple[int, str], Tuple[int, int]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps: Dict[Tuple[int, str], datetime] = {}
    
    async def start(self):
        """Start the cleanup background task."""
        if self._running:
            return
            
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Stop the cleanup background task."""
        if not self._running:
            return
            
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_loop(self):
        """Periodically clean up old rename history."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Clean up every minute
                await self._cleanup_old_history()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error in cleanup loop: {e}", exc_info=True)
    
    async def _cleanup_old_history(self):
        """Clean up rename history entries older than the window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds * 2)
        
        for guild_id in list(self._rename_history.keys()):
            for user_id in list(self._rename_history[guild_id].keys()):
                # Filter out old entries
                old_entries = [
                    ts for ts in self._rename_history[guild_id][user_id]
                    if ts < cutoff
                ]
                
                for ts in old_entries:
                    self._rename_history[guild_id][user_id].remove(ts)
                
                # Remove empty user entries
                if not self._rename_history[guild_id][user_id]:
                    del self._rename_history[guild_id][user_id]
            
            # Remove empty guild entries
            if not self._rename_history[guild_id]:
                del self._rename_history[guild_id]
    
    async def track_rename(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int,
        old_name: str,
        new_name: str
    ) -> Tuple[int, int]:
        """
        Track a channel rename event.
        
        Args:
            guild_id: Guild ID
            user_id: User ID who performed the rename
            channel_id: Channel ID that was renamed
            old_name: Old channel name
            new_name: New channel name
        
        Returns:
            (rename_count, threshold) - Current count and threshold
        """
        now = datetime.now(timezone.utc)
        
        # Add to history
        self._rename_history[guild_id][user_id].append(now)
        
        # Clean up old entries for this specific user
        cutoff = now - timedelta(seconds=self.window_seconds)
        old_entries = [
            ts for ts in self._rename_history[guild_id][user_id]
            if ts < cutoff
        ]
        
        for ts in old_entries:
            self._rename_history[guild_id][user_id].remove(ts)
        
        # Get current count and threshold
        rename_count = len(self._rename_history[guild_id][user_id])
        threshold = await self._get_threshold(guild_id, "channel_rename")
        
        return (rename_count, threshold)
    
    async def _get_threshold(self, guild_id: int, action_type: str) -> Tuple[int, int]:
        """
        Get threshold settings for a guild and action.
        
        Args:
            guild_id: Guild ID
            action_type: Action type (e.g., "channel_rename")
        
        Returns:
            (threshold_count, window_seconds)
        """
        cache_key = (guild_id, action_type)
        now = datetime.now(timezone.utc)
        
        # Check cache
        if cache_key in self._cached_thresholds:
            if (now - self._cache_timestamps[cache_key]).total_seconds() < self._cache_ttl:
                return self._cached_thresholds[cache_key]
        
        # Query database
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT max_count, window_seconds FROM antinuke_thresholds "
                    "WHERE guild_id = ? AND action_type = ?",
                    (guild_id, action_type)
                )
                row = await cursor.fetchone()
                
                if row:
                    result = (row["max_count"], row["window_seconds"])
                else:
                    result = (self._default_threshold, self._default_window)
                
                # Cache result
                self._cached_thresholds[cache_key] = result
                self._cache_timestamps[cache_key] = now
                
                return result
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error getting threshold: {e}", exc_info=True)
            return (self._default_threshold, self._default_window)
    
    async def set_threshold(
        self,
        guild_id: int,
        action_type: str,
        threshold: int,
        window_seconds: int
    ) -> bool:
        """
        Set threshold settings for a guild and action.
        
        Args:
            guild_id: Guild ID
            action_type: Action type
            threshold: Maximum count threshold
            window_seconds: Time window in seconds
        
        Returns:
            True if successful, False otherwise
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT OR REPLACE INTO antinuke_thresholds
                       (guild_id, action_type, max_count, window_seconds)
                       VALUES (?, ?, ?, ?)""",
                    (guild_id, action_type, threshold, window_seconds)
                )
                await db.commit()
            
            # Update cache
            cache_key = (guild_id, action_type)
            self._cached_thresholds[cache_key] = (threshold, window_seconds)
            self._cache_timestamps[cache_key] = datetime.now(timezone.utc)
            
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error setting threshold: {e}", exc_info=True)
            return False
    
    def get_user_rename_count(
        self,
        guild_id: int,
        user_id: int,
        window_seconds: Optional[int] = None
    ) -> int:
        """
        Get the current rename count for a user.
        
        Args:
            guild_id: Guild ID
            user_id: User ID
            window_seconds: Optional custom window (uses default if not provided)
        
        Returns:
            Current rename count within the window
        """
        window = window_seconds or self.window_seconds
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
        
        if guild_id not in self._rename_history:
            return 0
        
        if user_id not in self._rename_history[guild_id]:
            return 0
        
        # Count renames within the window
        count = sum(
            1 for ts in self._rename_history[guild_id][user_id]
            if ts >= cutoff
        )
        
        return count
    
    def clear_user_history(self, guild_id: int, user_id: int):
        """Clear rename history for a specific user."""
        if guild_id in self._rename_history:
            if user_id in self._rename_history[guild_id]:
                del self._rename_history[guild_id][user_id]
    
    def clear_guild_history(self, guild_id: int):
        """Clear all rename history for a guild."""
        if guild_id in self._rename_history:
            del self._rename_history[guild_id]
    
    def get_stats(self) -> Dict:
        """Get tracker statistics."""
        total_users = sum(
            len(users) for users in self._rename_history.values()
        )
        total_renames = sum(
            len(history) for guild in self._rename_history.values()
            for history in guild.values()
        )
        
        return {
            "total_guilds": len(self._rename_history),
            "total_users": total_users,
            "total_renames": total_renames,
            "cache_entries": len(self._cached_thresholds)
        }


# Global tracker instance
_rename_tracker: Optional[ChannelRenameTracker] = None

def get_rename_tracker() -> ChannelRenameTracker:
    """Get the global rename tracker instance."""
    global _rename_tracker
    if _rename_tracker is None:
        _rename_tracker = ChannelRenameTracker()
    return _rename_tracker

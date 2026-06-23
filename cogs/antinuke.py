"""Repent - Antinuke System

Hardened Antinuke system protecting against nuke/bulk moderation actions, Webhook threats, and Permission Escalations.

Key behaviors implemented:
- Instant punish (kick/ban/strip/timeout) on first detection for critical delete actions.
- Targeted auto-restore from cache ONLY for the specific deleted channel/role IDs.
- Webhook auto-delete when unwhitelisted user creates them (immediate delete + instant punish).
"""

from __future__ import annotations

import asyncio
import json
import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone
import time
from typing import Optional, List, Dict, Set
from collections import deque

import discord
from discord.ext import commands

from config import DEFAULT_PUNISHMENT, OWNER_ID
from database import (
    add_punished_user,
    get_whitelist_entry,
    get_guild,
    get_cached_roles,
    get_cached_channels,
    remove_punished_user,
    get_punished_users,
    log_action,
    get_antinuke_threshold,
    is_bot_whitelisted,
    user_has_whitelisted_role,
    is_user_whitelisted_optimized,
    # Fast-path antinuke functions (no retry, cache-first)
    get_guild_fast,
    is_user_whitelisted_fast,
    user_has_whitelisted_role_fast,
    get_antinuke_threshold_fast,
    log_action_fast,
    invalidate_antinuke_cache,
)
from utils.embeds import antinuke_embed, error_embed, info_embed, success_embed
from utils.cache import snapshot_guild
from utils.logger import get_logger
from utils.enhanced_restore import EnhancedRestoreSystem, ConsecutiveAttackDetector
from channel_rename_system import get_rename_tracker
from utils.cross_guild_security import CrossGuildSecurityCorrelation
from utils.unified_cache import security_cache, cached


class InMemoryRateTracker:
    """Fast, in-memory sliding window rate tracker with memory management."""

    def __init__(self, max_events_per_user: int = 1000, cleanup_interval: int = 300):
        # guild_id -> user_id -> action_type -> deque[datetime]
        self._tracks: Dict[int, Dict[int, Dict[str, deque]]] = {}
        self.max_events_per_user = max_events_per_user
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = datetime.now(timezone.utc)

    def add_event(self, guild_id: int, user_id: int, action_type: str) -> None:
        self._tracks.setdefault(guild_id, {}).setdefault(user_id, {}).setdefault(action_type, deque()).append(
            datetime.now(timezone.utc)
        )
        
        # Enforce size limit per user/action type
        events = self._tracks[guild_id][user_id][action_type]
        if len(events) > self.max_events_per_user:
            # Remove oldest events if limit exceeded
            excess = len(events) - self.max_events_per_user
            for _ in range(excess):
                events.popleft()

    def count_events(self, guild_id: int, user_id: int, action_type: str, window_seconds: int) -> int:
        guild_tracks = self._tracks.get(guild_id)
        if not guild_tracks:
            return 0
        user_tracks = guild_tracks.get(user_id)
        if not user_tracks:
            return 0
        events = user_tracks.get(action_type)
        if not events:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        while events and events[0] <= cutoff:
            events.popleft()

        return len(events)

    def clear_events(self, guild_id: int, user_id: int, action_type: str) -> None:
        guild_tracks = self._tracks.get(guild_id)
        if not guild_tracks:
            return
        user_tracks = guild_tracks.get(user_id)
        if not user_tracks:
            return
        events = user_tracks.get(action_type)
        if events is not None:
            events.clear()
    
    def cleanup_old_events(self, max_age_seconds: int = 3600) -> int:
        """Clean up events older than max_age_seconds across all tracks.
        Returns the number of events removed."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max_age_seconds)
        removed_count = 0
        
        # Periodic cleanup based on time interval
        if (now - self._last_cleanup).total_seconds() < self.cleanup_interval:
            return 0
        
        self._last_cleanup = now
        
        # Clean up old events and empty structures
        for guild_id in list(self._tracks.keys()):
            for user_id in list(self._tracks[guild_id].keys()):
                for action_type in list(self._tracks[guild_id][user_id].keys()):
                    events = self._tracks[guild_id][user_id][action_type]
                    
                    # Remove old events
                    while events and events[0] <= cutoff:
                        events.popleft()
                        removed_count += 1
                    
                    # Remove empty action_type entries
                    if not events:
                        del self._tracks[guild_id][user_id][action_type]
                
                # Remove empty user entries
                if not self._tracks[guild_id][user_id]:
                    del self._tracks[guild_id][user_id]
            
            # Remove empty guild entries
            if not self._tracks[guild_id]:
                del self._tracks[guild_id]
        
        return removed_count
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the rate tracker memory usage."""
        total_events = 0
        total_users = 0
        total_guilds = len(self._tracks)
        
        for guild_id, guild_tracks in self._tracks.items():
            for user_id, user_tracks in guild_tracks.items():
                total_users += 1
                for action_type, events in user_tracks.items():
                    total_events += len(events)
        
        return {
            "total_guilds": total_guilds,
            "total_users": total_users,
            "total_events": total_events,
            "max_events_per_user": self.max_events_per_user
        }


class Antinuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: Dict[int, asyncio.Lock] = {}
        self.rate_tracker = InMemoryRateTracker()
        # Store processed entries with timestamps for memory cleanup: {entry_id: datetime}
        self._processed_entries: Dict[int, datetime] = {}
        self._cleanup_task = None
        self.logger = get_logger()
        
        # Enhanced restore system for consecutive nuke protection
        self.enhanced_restore = EnhancedRestoreSystem(bot, self.logger)

        # Channel rename tracker for protection against channel rename spam
        self.rename_tracker = get_rename_tracker()

        # Cross-guild attack correlation system
        self.cross_guild_security = CrossGuildSecurityCorrelation()
        
        # ENHANCED SECURITY: Proactive threat hunting
        self._threat_hunting_enabled = True
        self._suspicious_activity_scores: Dict[int, Dict[int, float]] = {}  # {guild_id: {user_id: score}}
        self._recent_violations: Dict[Tuple[int, int], List[datetime]] = {}  # {(guild_id, user_id): [timestamps]}
        
        # ENHANCED SECURITY: Zero-Trust by default - no trusted users
        self._zero_trust_enabled = True  # Zero-trust always active
        
        # Whitelist result cache: {(guild_id, user_id): (result, timestamp)}
        self._whitelist_cache: Dict[Tuple[int, int], Tuple[bool, datetime]] = {}
        self._cache_ttl = 300  # 5 minutes (OPTIMIZED: reduced from 10 minutes for better security responsiveness)
        
        # Discord object cache: {cache_key: (object, timestamp)}
        self._discord_cache: Dict[str, Tuple[Any, datetime]] = {}
        self._discord_cache_ttl = 120  # 2 minutes for Discord objects (OPTIMIZED: reduced from 3 minutes for fresher data)
        
        # Safe admins JSON cache: {guild_id: (parsed_list, settings_timestamp)}
        self._safe_admins_cache: Dict[int, Tuple[List[int], str, datetime]] = {}
        self._safe_admins_cache_ttl = 300  # 5 minutes for safe admins (OPTIMIZED: reduced from 10 minutes)
        
        # Permission validation cache: {(guild_id, user_id, action_type): (has_permission, timestamp)}
        self._permission_cache: Dict[Tuple[int, int, str], Tuple[bool, datetime]] = {}
        self._permission_cache_ttl = 180  # 3 minutes for permission validation (OPTIMIZED: reduced from 5 minutes)
        
        # Circuit breaker for parallel attacks: {(guild_id, user_id): punishment_timestamp}
        self._punished_users_cache: Dict[Tuple[int, int], datetime] = {}
        
        # Performance metrics for monitoring
        self._metrics = {
            "events_processed": 0,
            "events_skipped_early": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "whitelist_checks": 0,
            "whitelist_cached_hits": 0,
            "db_fast_path_calls": 0,
            "db_regular_calls": 0,
            "audit_log_queries": 0,
            "punishments_applied": 0,
            "graceful_degradations": 0,
            "detection_times_ms": [],  # Last 100 detection times
            "database_query_times_ms": [],  # Last 100 database query times
            "cache_operations": 0,  # Total cache operations
        }
        
        # Priority-based task queue for background operations
        self._task_queue = asyncio.PriorityQueue()
        self._task_worker_task = None
        
        # Emergency mode tracking: guilds currently in lockdown
        self._emergency_mode_active: Set[int] = set()
        
        # Attack detection timestamps per guild
        self._attack_detected_time: Dict[int, datetime] = {}
        
        # Emergency mode configuration
        self._emergency_mode_config = {
            "auto_activate": True,  # Automatically activate on suspicious patterns
            "duration_minutes": 10,  # How long emergency mode stays active
            "max_whitelist_bypass": True,  # Allow whitelist bypass in emergency mode
            "rate_limit_bypass": True,  # Bypass rate limits in emergency mode
        }
        
        # Event deduplication: {(guild_id, user_id, action_type, target_id): timestamp}
        self._processed_events: Dict[Tuple[int, int, str, int], datetime] = {}
        
        # Punishment notification rate limiting: {(guild_id, user_id, punishment): timestamp}
        self._punishment_notifications: Dict[Tuple[int, int, str], datetime] = {}
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # API rate limiting for audit log queries (token bucket algorithm)
        self._audit_log_rate_limiter: Dict[int, Dict[str, float]] = {}  # guild_id -> {tokens: float, last_update: float}
        self._audit_log_rate_limit = 2  # 2 queries per second per guild (reduced from 5 to respect Discord's limits)
        self._audit_log_burst_size = 5  # Allow burst of 5 queries (reduced from 10)
        
        # Discord API rate limit tracking (global buckets) - IMPROVED FOR BETTER RATE LIMIT COMPLIANCE
        self._discord_api_buckets = {
            "guild": {"tokens": 20, "last_update": time.time(), "rate": 20, "window": 1},  # 20 requests per second (reduced from 50)
            "webhook": {"tokens": 5, "last_update": time.time(), "rate": 5, "window": 1},  # 5 requests per second (reduced from 10)
            "message": {"tokens": 10, "last_update": time.time(), "rate": 10, "window": 1},  # 10 messages per second
            "audit_log": {"tokens": 2, "last_update": time.time(), "rate": 2, "window": 1},  # 2 audit log requests per second
        }
        
        # Exponential backoff tracking for rate limit handling
        self._rate_limit_backoff: Dict[str, float] = {}  # bucket_name -> backoff_until_time
        
        # Graceful degradation: component health status
        self._component_health: Dict[str, bool] = {
            "database": True,
            "audit_log": True,
            "rate_tracker": True,
            "cache": True
        }
        
        # Fallback mode flags
        self._fallback_mode = False
        
        # MAXIMUM SECURITY: Zero-tolerance actions (instant punishment regardless of whitelist)
        self._zero_tolerance_actions = {
            "webhook_create", "webhook_delete",  # Webhook threats are critical
            "bot_add",  # Adding unknown bots is high risk
            "guild_update",  # Server settings changes
        }
        
        # Enhanced security: Suspicious patterns for immediate action
        self._suspicious_patterns = {
            "mass_channel_delete": {"threshold": 2, "window": 5},  # 2+ channels in 5 seconds
            "mass_role_delete": {"threshold": 2, "window": 5},  # 2+ roles in 5 seconds
            "mass_ban": {"threshold": 3, "window": 10},  # 3+ bans in 10 seconds
        }
        
        # Security: Track recent guild-wide events for pattern detection
        self._guild_security_events: Dict[int, deque] = {}  # guild_id -> deque of security events

    def _get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        self._locks.setdefault(guild_id, asyncio.Lock())
        return self._locks[guild_id]

    async def _warm_cache(self):
        """Pre-warm cache for active guilds to improve performance."""
        try:
            # Wait for bot to be ready
            await self.bot.wait_until_ready()
            
            # Warm cache for all guilds
            for guild in self.bot.guilds:
                try:
                    # Pre-load guild settings
                    await get_guild_fast(guild.id)
                    
                    # Pre-load owner and bot user as whitelisted
                    self._set_cached_whitelist_status(guild.id, guild.owner_id, True)
                    if self.bot.user:
                        self._set_cached_whitelist_status(guild.id, self.bot.user.id, True)
                    
                except Exception as e:
                    self.logger.debug(f"Failed to warm cache for guild {guild.id}: {e}")
            
            self.logger.info(f"Antinuke cache warmed for {len(self.bot.guilds)} guilds")
        except Exception as e:
            self.logger.error(f"Cache warming failed: {e}")

    def invalidate_guild_cache(self, guild_id: int):
        """Invalidate cache for a specific guild when settings change."""
        invalidate_antinuke_cache(guild_id)
        self.logger.debug(f"Invalidated antinuke cache for guild {guild_id}")

    def _record_metric(self, metric_name: str, value: Any = None):
        """Record a performance metric."""
        if metric_name in self._metrics:
            if metric_name == "detection_times_ms":
                # Keep only last 100 detection times
                self._metrics[metric_name].append(value)
                if len(self._metrics[metric_name]) > 100:
                    self._metrics[metric_name].pop(0)
            else:
                self._metrics[metric_name] += 1 if value is None else value

    def _get_average_detection_time(self) -> float:
        """Get average detection time in milliseconds."""
        times = self._metrics["detection_times_ms"]
        if not times:
            return 0.0
        return sum(times) / len(times)

    def _get_p95_detection_time(self) -> float:
        """Get 95th percentile detection time in milliseconds."""
        times = sorted(self._metrics["detection_times_ms"])
        if not times:
            return 0.0
        index = int(len(times) * 0.95)
        return times[min(index, len(times) - 1)]
    
    def _can_punish_user(self, guild: discord.Guild, member: discord.Member, punishment: str) -> tuple[bool, str]:
        """Check if the bot can punish a user with the given punishment type.
        
        Returns:
            tuple[bool, str]: (can_punish, reason)
        """
        bot_member = guild.me
        
        # Cannot punish server owner
        if member.id == guild.owner_id:
            return False, "User is server owner"
        
        # Cannot punish bot itself
        if self.bot.user and member.id == self.bot.user.id:
            return False, "Cannot punish the bot itself"
        
        # Check role hierarchy
        if member.roles:
            user_highest_role = max(member.roles, key=lambda r: r.position)
            
            # If user's highest role is >= bot's highest role, most punishments won't work
            if user_highest_role >= bot_member.top_role:
                if punishment in ["ban", "kick", "timeout"]:
                    return False, f"User has higher/equal role ({user_highest_role.name})"
                # strip might still work for some roles
            elif punishment == "strip":
                # For strip, check if there are any removable roles
                removable_roles = [
                    role for role in member.roles 
                    if role < bot_member.top_role and role != guild.default_role and not role.managed
                ]
                if not removable_roles:
                    return False, "No removable roles (all roles are too high, managed, or default)"
        
        # Check bot permissions
        bot_permissions = bot_member.guild_permissions
        
        if punishment == "ban" and not bot_permissions.ban_members:
            return False, "Bot lacks ban_members permission"
        elif punishment == "kick" and not bot_permissions.kick_members:
            return False, "Bot lacks kick_members permission"
        elif punishment == "timeout" and not bot_permissions.moderate_members:
            return False, "Bot lacks moderate_members permission"
        elif punishment == "strip" and not bot_permissions.manage_roles:
            return False, "Bot lacks manage_roles permission"
        
        return True, "OK"

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of performance metrics."""
        db_times = self._metrics["database_query_times_ms"]
        cache_hit_rate = self._metrics["cache_hits"] / max(self._metrics["cache_hits"] + self._metrics["cache_misses"], 1) * 100
        
        return {
            "events_processed": self._metrics["events_processed"],
            "cache_hit_rate": cache_hit_rate,
            "whitelist_cache_hit_rate": self._metrics["whitelist_cached_hits"] / max(self._metrics["whitelist_checks"], 1) * 100,
            "avg_detection_time_ms": self._get_average_detection_time(),
            "p95_detection_time_ms": self._get_p95_detection_time(),
            "avg_db_query_time_ms": sum(db_times) / len(db_times) if db_times else 0.0,
            "p95_db_query_time_ms": sorted(db_times)[int(len(db_times) * 0.95)] if db_times and len(db_times) > 1 else 0.0,
            "punishments_applied": self._metrics["punishments_applied"],
            "graceful_degradations": self._metrics["graceful_degradations"],
            "cache_operations": self._metrics["cache_operations"],
        }
    
    async def _record_db_query_time(self, duration_ms: float):
        """Record database query time for performance monitoring."""
        self._metrics["database_query_times_ms"].append(duration_ms)
        if len(self._metrics["database_query_times_ms"]) > 100:
            self._metrics["database_query_times_ms"].pop(0)
    
    async def _schedule_priority_task(self, priority: int, coro):
        """Schedule a background task with priority (0 = highest priority)."""
        await self._task_queue.put((priority, asyncio.create_task(coro)))
    
    async def _task_worker(self):
        """Background worker for processing priority tasks."""
        while True:
            try:
                priority, task = await self._task_queue.get()
                await task
                self._task_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Priority task worker error: {e}", exc_info=True)
    
    async def _wait_for_discord_api_quota(self, bucket_name: str = "guild", priority: bool = False) -> None:
        """Wait for Discord API quota using token bucket algorithm with exponential backoff."""
        async with self._lock:
            now = time.time()
            
            if bucket_name not in self._discord_api_buckets:
                return  # Unknown bucket, skip rate limiting
            
            # Check if we're in backoff period for this bucket
            if bucket_name in self._rate_limit_backoff:
                if now < self._rate_limit_backoff[bucket_name]:
                    backoff_remaining = self._rate_limit_backoff[bucket_name] - now
                    self.logger.warning(f"Rate limit backoff active for {bucket_name}: {backoff_remaining:.2f}s remaining")
                    if not priority:  # Only wait if not high priority
                        await asyncio.sleep(min(backoff_remaining, 5.0))  # Max 5 second wait
                    return
                else:
                    # Backoff period expired, remove it
                    del self._rate_limit_backoff[bucket_name]
            
            bucket = self._discord_api_buckets[bucket_name]
            
            # Replenish tokens
            time_since_update = now - bucket["last_update"]
            bucket["tokens"] = min(bucket["rate"], bucket["tokens"] + time_since_update * bucket["rate"])
            bucket["last_update"] = now
            
            # Wait if no tokens available
            if bucket["tokens"] < 1:
                wait_time = (1 - bucket["tokens"]) / bucket["rate"]
                if wait_time > 0:
                    # Increased max wait time and added logging
                    actual_wait = min(wait_time, 2.0)  # Max 2 second wait (increased from 50ms)
                    if actual_wait > 0.1:  # Only log significant waits
                        self.logger.debug(f"Rate limiting {bucket_name}: waiting {actual_wait:.2f}s")
                    await asyncio.sleep(actual_wait)
            
            # Consume a token
            bucket["tokens"] -= 1
    
    async def _handle_rate_limit_error(self, bucket_name: str = "guild", retry_after: float = None):
        """Handle rate limit errors with exponential backoff."""
        async with self._lock:
            now = time.time()
            
            # Calculate backoff time with exponential increase
            current_backoff = self._rate_limit_backoff.get(bucket_name, now)
            if retry_after:
                # Use Discord's retry-after if provided
                backoff_time = retry_after
            else:
                # Exponential backoff: start at 1 second, double each time, max 30 seconds
                if bucket_name in self._rate_limit_backoff:
                    elapsed = now - current_backoff
                    if elapsed > 0:
                        # We've waited the backoff period, reset
                        backoff_time = 1.0
                    else:
                        # Still in backoff, double the time
                        backoff_time = min(30.0, abs(elapsed) * 2)
                else:
                    backoff_time = 1.0
            
            self._rate_limit_backoff[bucket_name] = now + backoff_time
            self.logger.warning(f"Rate limit hit for {bucket_name}, backing off for {backoff_time:.2f}s")
            
            # Reset bucket tokens to prevent immediate hammering
            if bucket_name in self._discord_api_buckets:
                self._discord_api_buckets[bucket_name]["tokens"] = 0
                self._discord_api_buckets[bucket_name]["last_update"] = now
    
    async def run_benchmark(self, iterations: int = 100) -> Dict[str, float]:
        """Run performance benchmark for antinuke operations."""
        import random
        
        results = {
            "whitelist_check_times": [],
            "threshold_check_times": [],
            "cache_hit_times": [],
            "total_time": 0,
        }
        
        guild_id = 123456789  # Test guild ID
        user_id = 987654321  # Test user ID
        
        for i in range(iterations):
            # Benchmark whitelist check
            start = time.time()
            await self._is_whitelisted(guild_id, user_id)
            whitelist_time = (time.time() - start) * 1000
            results["whitelist_check_times"].append(whitelist_time)
            
            # Benchmark threshold check
            start = time.time()
            await self._check_threshold(guild_id, user_id, "channel_delete")
            threshold_time = (time.time() - start) * 1000
            results["threshold_check_times"].append(threshold_time)
            
            # Benchmark cache hit
            start = time.time()
            self._get_cached_whitelist_status(guild_id, user_id)
            cache_time = (time.time() - start) * 1000
            results["cache_hit_times"].append(cache_time)
        
        results["total_time"] = sum(results["whitelist_check_times"]) + \
                              sum(results["threshold_check_times"]) + \
                              sum(results["cache_hit_times"])
        
        return {
            "avg_whitelist_check_ms": sum(results["whitelist_check_times"]) / len(results["whitelist_check_times"]),
            "avg_threshold_check_ms": sum(results["threshold_check_times"]) / len(results["threshold_check_times"]),
            "avg_cache_hit_ms": sum(results["cache_hit_times"]) / len(results["cache_hit_times"]),
            "total_time_ms": results["total_time"],
            "iterations": iterations,
        }

    async def cog_load(self):
        """Start the cleanup task when cog is loaded."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        # Start priority task worker
        self._task_worker_task = asyncio.create_task(self._task_worker())
        # Start channel rename tracker
        await self.rename_tracker.start()
        # Pre-warm cache for guilds that are already loaded
        asyncio.create_task(self._warm_cache())

    async def cog_unload(self):
        """Stop the cleanup task when cog is unloaded."""
        if self._task_worker_task:
            self._task_worker_task.cancel()
            try:
                await self._task_worker_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def _get_cached_whitelist_status(self, guild_id: int, user_id: int) -> Optional[bool]:
        """Get cached whitelist status if available and not expired."""
        cache_key = (guild_id, user_id)
        if cache_key in self._whitelist_cache:
            result, timestamp = self._whitelist_cache[cache_key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._cache_ttl):
                return result
            else:
                # Expired, remove from cache
                del self._whitelist_cache[cache_key]
        return None

    def _set_cached_whitelist_status(self, guild_id: int, user_id: int, result: bool) -> None:
        """Cache whitelist status with current timestamp."""
        cache_key = (guild_id, user_id)
        self._whitelist_cache[cache_key] = (result, datetime.now(timezone.utc))

    def _get_cached_discord_object(self, cache_key: str) -> Optional[Any]:
        """Get cached Discord object if available and not expired."""
        if cache_key in self._discord_cache:
            obj, timestamp = self._discord_cache[cache_key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._discord_cache_ttl):
                return obj
            else:
                # Expired, remove from cache
                del self._discord_cache[cache_key]
        return None

    def _set_cached_discord_object(self, cache_key: str, obj: Any) -> None:
        """Cache Discord object with current timestamp."""
        self._discord_cache[cache_key] = (obj, datetime.now(timezone.utc))

    def _get_cached_safe_admins(self, guild_id: int, current_settings_json: str) -> Optional[List[int]]:
        """Get cached safe admins list if settings haven't changed."""
        if guild_id in self._safe_admins_cache:
            cached_list, cached_json, timestamp = self._safe_admins_cache[guild_id]
            if cached_json == current_settings_json and datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._safe_admins_cache_ttl):
                return cached_list
            else:
                # Settings changed or expired, remove from cache
                del self._safe_admins_cache[guild_id]
        return None

    def _set_cached_safe_admins(self, guild_id: int, safe_admins_list: List[int], settings_json: str) -> None:
        """Cache safe admins list with current settings and timestamp."""
        self._safe_admins_cache[guild_id] = (safe_admins_list, settings_json, datetime.now(timezone.utc))
    
    def _track_security_event(self, guild_id: int, user_id: int, action_type: str) -> Dict[str, Any]:
        """Track security event for pattern detection."""
        if guild_id not in self._guild_security_events:
            self._guild_security_events[guild_id] = deque(maxlen=1000)
        
        event = {
            "user_id": user_id,
            "action_type": action_type,
            "timestamp": datetime.now(timezone.utc)
        }
        self._guild_security_events[guild_id].append(event)
        
        # Check for suspicious patterns
        return self._detect_suspicious_patterns(guild_id, user_id, action_type)
    
    def _detect_suspicious_patterns(self, guild_id: int, user_id: int, action_type: str) -> Dict[str, Any]:
        """Detect suspicious attack patterns."""
        if guild_id not in self._guild_security_events:
            return {"is_suspicious": False}
        
        events = self._guild_security_events[guild_id]
        now = datetime.now(timezone.utc)
        
        # Check each suspicious pattern
        for pattern_name, pattern_config in self._suspicious_patterns.items():
            threshold = pattern_config["threshold"]
            window = pattern_config["window"]
            
            # Count recent events matching the pattern
            if pattern_name == "mass_channel_delete" and action_type == "channel_delete":
                recent_count = sum(1 for e in events if e["action_type"] == "channel_delete" and (now - e["timestamp"]).total_seconds() <= window)
                if recent_count >= threshold:
                    return {
                        "is_suspicious": True,
                        "pattern": pattern_name,
                        "count": recent_count,
                        "threshold": threshold,
                        "window": window
                    }
            
            elif pattern_name == "mass_role_delete" and action_type == "role_delete":
                recent_count = sum(1 for e in events if e["action_type"] == "role_delete" and (now - e["timestamp"]).total_seconds() <= window)
                if recent_count >= threshold:
                    return {
                        "is_suspicious": True,
                        "pattern": pattern_name,
                        "count": recent_count,
                        "threshold": threshold,
                        "window": window
                    }
            
            elif pattern_name == "mass_ban" and action_type == "ban":
                recent_count = sum(1 for e in events if e["action_type"] == "ban" and (now - e["timestamp"]).total_seconds() <= window)
                if recent_count >= threshold:
                    return {
                        "is_suspicious": True,
                        "pattern": pattern_name,
                        "count": recent_count,
                        "threshold": threshold,
                        "window": window
                    }
        
        return {"is_suspicious": False}

    def _is_event_processed(self, guild_id: int, user_id: int, action_type: str, target_id: int) -> bool:
        """Check if an event has already been processed to prevent duplicate punishment."""
        event_key = (guild_id, user_id, action_type, target_id)
        if event_key in self._processed_events:
            # Check if the event was processed recently (within 10 seconds)
            if datetime.now(timezone.utc) - self._processed_events[event_key] < timedelta(seconds=10):
                return True
            # Event is old, remove it
            del self._processed_events[event_key]
        return False

    def _mark_event_processed(self, guild_id: int, user_id: int, action_type: str, target_id: int) -> None:
        """Mark an event as processed to prevent duplicate punishment."""
        event_key = (guild_id, user_id, action_type, target_id)
        self._processed_events[event_key] = datetime.now(timezone.utc)

    async def _can_query_audit_log(self, guild_id: int) -> bool:
        """Check if we can query audit log for this guild without hitting rate limits (token bucket)."""
        async with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            
            # Initialize token bucket if not exists
            if guild_id not in self._audit_log_rate_limiter:
                self._audit_log_rate_limiter[guild_id] = {
                    "tokens": self._audit_log_burst_size,
                    "last_update": now
                }
            
            bucket = self._audit_log_rate_limiter[guild_id]
            
            # Replenish tokens
            time_since_update = now - bucket["last_update"]
            bucket["tokens"] = min(self._audit_log_burst_size, bucket["tokens"] + time_since_update * self._audit_log_rate_limit)
            bucket["last_update"] = now
            
            # Check if we have a token available
            if bucket["tokens"] >= 1:
                return True
            else:
                return False

    async def activate_emergency_lockdown(self, guild_id: int, reason: str = "Security threat detected") -> None:
        """Activate emergency lockdown mode for a guild during active attacks.
        
        This provides maximum security by:
        - Bypassing all whitelist checks
        - Bypassing rate limits for critical actions
        - Enabling maximum punishment severity
        - Activating enhanced monitoring
        """
        async with self._lock:
            if guild_id in self._emergency_mode_active:
                return  # Already in emergency mode
            
            self._emergency_mode_active.add(guild_id)
            self._attack_detected_time[guild_id] = datetime.now(timezone.utc)
        
        self.logger.security(
            "EMERGENCY_LOCKDOWN_ACTIVATED",
            f"Emergency lockdown activated for guild {guild_id}. Reason: {reason}",
            guild_id=guild_id
        )
        
        # Take immediate protective actions
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            # Log the emergency activation to database
            await log_action(guild_id, "emergency_lockdown", self.bot.user.id if self.bot.user else 0, {
                "reason": reason,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "config": self._emergency_mode_config
            })
            
            # Create emergency snapshot
            try:
                await snapshot_guild(guild, trigger_event="emergency_lockdown")
                self.logger.info(f"Emergency snapshot created for guild {guild_id}")
            except Exception as e:
                self.logger.warning(f"Failed to create emergency snapshot: {e}")
            
            # Schedule automatic deactivation
            asyncio.create_task(self._schedule_emergency_deactivation(guild_id))
            
        except Exception as e:
            self.logger.error(f"Error activating emergency lockdown for guild {guild_id}: {e}", exc_info=True)
    
    async def _schedule_emergency_deactivation(self, guild_id: int) -> None:
        """Schedule emergency mode deactivation after configured duration."""
        duration_minutes = self._emergency_mode_config.get("duration_minutes", 10)
        await asyncio.sleep(duration_minutes * 60)
        
        async with self._lock:
            if guild_id in self._emergency_mode_active:
                # Check if there have been recent attacks before deactivating
                attack_time = self._attack_detected_time.get(guild_id)
                if attack_time:
                    time_since_attack = (datetime.now(timezone.utc) - attack_time).total_seconds()
                    if time_since_attack < 300:  # If attack within 5 minutes, extend emergency mode
                        self.logger.info(f"Extending emergency mode for guild {guild_id} due to recent attack")
                        await self._schedule_emergency_deactivation(guild_id)
                        return
                
                self._emergency_mode_active.remove(guild_id)
                if guild_id in self._attack_detected_time:
                    del self._attack_detected_time[guild_id]
                
                self.logger.security(
                    "EMERGENCY_LOCKDOWN_DEACTIVATED",
                    f"Emergency lockdown deactivated for guild {guild_id}",
                    guild_id=guild_id
                )
    
    async def is_emergency_active(self, guild_id: int) -> bool:
        """Check if emergency mode is active for a guild."""
        async with self._lock:
            return guild_id in self._emergency_mode_active
    
    async def _wait_for_audit_log_quota(self, guild_id: int) -> None:
        """Wait if necessary to respect audit log rate limits with improved backoff handling."""
        # Use the improved global rate limiter for audit logs
        await self._wait_for_discord_api_quota("audit_log")
        
        # Additional per-guild rate limiting for audit logs
        # Skip rate limiting during emergency mode for maximum speed
        async with self._lock:
            in_emergency = guild_id in self._emergency_mode_active
        if in_emergency:
            return  # Bypass rate limiting during emergency mode
        
        async with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            
            # Initialize token bucket if not exists
            if guild_id not in self._audit_log_rate_limiter:
                self._audit_log_rate_limiter[guild_id] = {
                    "tokens": self._audit_log_burst_size,
                    "last_update": now
                }
            
            bucket = self._audit_log_rate_limiter[guild_id]
            
            # Replenish tokens
            time_since_update = now - bucket["last_update"]
            bucket["tokens"] = min(self._audit_log_burst_size, bucket["tokens"] + time_since_update * self._audit_log_rate_limit)
            bucket["last_update"] = now
            
            # If no tokens available, calculate wait time with improved handling
            if bucket["tokens"] < 1:
                # Calculate wait time
                wait_time = (1 - bucket["tokens"]) / self._audit_log_rate_limit
                if wait_time > 0:
                    # Increased max wait time and added logging
                    actual_wait = min(wait_time, 1.0)  # Max 1 second wait (increased from 100ms)
                    if actual_wait > 0.1:  # Only log significant waits
                        self.logger.debug(f"Audit log rate limiting for guild {guild_id}: waiting {actual_wait:.2f}s")
                    await asyncio.sleep(actual_wait)
                    # Replenish tokens after wait
                    bucket["tokens"] = min(self._audit_log_burst_size, bucket["tokens"] + actual_wait * self._audit_log_rate_limit)
            
            # Consume a token
            bucket["tokens"] -= 1

    def _get_cached_permission(self, guild_id: int, user_id: int, action_type: str) -> Optional[bool]:
        """Get cached permission validation result if available and not expired."""
        cache_key = (guild_id, user_id, action_type)
        if cache_key in self._permission_cache:
            result, timestamp = self._permission_cache[cache_key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._permission_cache_ttl):
                return result
            else:
                # Expired, remove from cache
                del self._permission_cache[cache_key]
        return None

    def _set_cached_permission(self, guild_id: int, user_id: int, action_type: str, result: bool) -> None:
        """Cache permission validation result with current timestamp."""
        cache_key = (guild_id, user_id, action_type)
        self._permission_cache[cache_key] = (result, datetime.now(timezone.utc))

    def _validate_user_permission(self, guild: discord.Guild, member: discord.Member, action_type: str, target_id: int = 0) -> bool:
        """Validate if the user actually has permission to perform the action.
        
        This prevents false positives where users are punished for actions they couldn't actually perform.
        Returns True if the user has permission, False if they don't (should not be punished).
        """
        try:
            # Check cache first for fast permission validation
            cached_result = self._get_cached_permission(guild.id, member.id, action_type)
            if cached_result is not None:
                return cached_result
            
            # Check basic guild permissions first
            if not member.guild_permissions.view_audit_log:
                # User can't view audit logs, likely doesn't have high permissions
                # But they could still have been given specific permissions
                pass
            
            # Check specific action permissions
            has_permission = True  # Default to True (conservative approach)
            
            if action_type == "channel_update":
                # Check if user can manage channels
                if not member.guild_permissions.manage_channels:
                    # User doesn't have permission to manage channels
                    # They shouldn't be punished for channel updates they couldn't perform
                    has_permission = False
                    
            elif action_type in ["role_create", "role_update", "role_delete"]:
                # Check if user can manage roles
                if not member.guild_permissions.manage_roles:
                    has_permission = False
                    
            elif action_type in ["ban", "kick"]:
                # Check if user can ban/kick
                if action_type == "ban" and not member.guild_permissions.ban_members:
                    has_permission = False
                if action_type == "kick" and not member.guild_permissions.kick_members:
                    has_permission = False
                    
            elif action_type == "guild_update":
                # Check if user can manage server
                if not member.guild_permissions.manage_guild:
                    has_permission = False
            
            # Cache the result
            self._set_cached_permission(guild.id, member.id, action_type, has_permission)
            
            return has_permission
            
        except Exception as e:
            # If we can't validate permissions, err on the side of caution and allow punishment
            self.logger.warning(f"Failed to validate user permissions for {member.id}: {e}")
            return True

    def _set_component_health(self, component: str, healthy: bool) -> None:
        """Set the health status of a component."""
        self._component_health[component] = healthy
        
        # Check if we need to enable fallback mode
        critical_components = ["database", "audit_log"]
        if not all(self._component_health.get(comp, True) for comp in critical_components):
            if not self._fallback_mode:
                self._fallback_mode = True
                self.logger.warning(f"Enabled fallback mode - critical components degraded: {critical_components}")
        else:
            if self._fallback_mode:
                self._fallback_mode = False
                self.logger.info("Disabled fallback mode - all critical components healthy")

    def _is_component_healthy(self, component: str) -> bool:
        """Check if a component is healthy."""
        return self._component_health.get(component, True)

    def _should_use_fallback(self) -> bool:
        """Check if we should use fallback mode."""
        return self._fallback_mode

    async def _cleanup_loop(self):
        """Periodically clean up old processed entries to prevent memory leaks."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(600)  # Clean up every 10 minutes (OPTIMIZED from 5 minutes)
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)  # Remove entries older than 30 minutes
                old_entries = [eid for eid, timestamp in self._processed_entries.items() if timestamp < cutoff]
                for eid in old_entries:
                    del self._processed_entries[eid]
                if old_entries:
                    self.logger.debug(f"Cleaned up {len(old_entries)} old processed entries")
                
                # Clean up whitelist cache
                cache_cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._cache_ttl)
                old_cache_keys = [key for key, (_, timestamp) in self._whitelist_cache.items() if timestamp < cache_cutoff]
                for key in old_cache_keys:
                    del self._whitelist_cache[key]
                if old_cache_keys:
                    self.logger.debug(f"Cleaned up {len(old_cache_keys)} old whitelist cache entries")
                
                # Clean up Discord object cache
                discord_cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._discord_cache_ttl)
                old_discord_keys = [key for key, (_, timestamp) in self._discord_cache.items() if timestamp < discord_cutoff]
                for key in old_discord_keys:
                    del self._discord_cache[key]
                if old_discord_keys:
                    self.logger.debug(f"Cleaned up {len(old_discord_keys)} old Discord cache entries")
                
                # Clean up safe admins cache
                safe_admins_cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._safe_admins_cache_ttl)
                old_safe_admins_keys = [key for key, (_, _, timestamp) in self._safe_admins_cache.items() if timestamp < safe_admins_cutoff]
                for key in old_safe_admins_keys:
                    del self._safe_admins_cache[key]
                if old_safe_admins_keys:
                    self.logger.debug(f"Cleaned up {len(old_safe_admins_keys)} old safe admins cache entries")
                
                # Clean up permission cache
                permission_cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._permission_cache_ttl)
                old_permission_keys = [key for key, (_, timestamp) in self._permission_cache.items() if timestamp < permission_cutoff]
                for key in old_permission_keys:
                    del self._permission_cache[key]
                if old_permission_keys:
                    self.logger.debug(f"Cleaned up {len(old_permission_keys)} old permission cache entries")
                
                # Clean up rate tracker events
                removed_events = self.rate_tracker.cleanup_old_events(max_age_seconds=3600)
                if removed_events > 0:
                    self.logger.debug(f"Cleaned up {removed_events} old rate tracker events")
                
                # Clean up punished users cache (circuit breaker)
                punished_cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)  # 30 seconds
                old_punished_keys = [key for key, timestamp in self._punished_users_cache.items() if timestamp < punished_cutoff]
                for key in old_punished_keys:
                    del self._punished_users_cache[key]
                if old_punished_keys:
                    self.logger.debug(f"Cleaned up {len(old_punished_keys)} old punished user entries")
                
                # Clean up emergency mode (lift lockdown after 5 minutes)
                emergency_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
                async with self._lock:
                    old_emergency_guilds = [guild_id for guild_id, timestamp in self._attack_detected_time.items() if timestamp < emergency_cutoff]
                    for guild_id in old_emergency_guilds:
                        self._emergency_mode_active.discard(guild_id)
                        del self._attack_detected_time[guild_id]
                if old_emergency_guilds:
                    self.logger.info(f"Lifted emergency lockdown for {len(old_emergency_guilds)} guilds")
                
                # Clean up processed events (prevent memory buildup)
                event_cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)  # 30 seconds
                old_event_keys = [key for key, timestamp in self._processed_events.items() if timestamp < event_cutoff]
                for key in old_event_keys:
                    del self._processed_events[key]
                if old_event_keys:
                    self.logger.debug(f"Cleaned up {len(old_event_keys)} old processed events")
                
                # OPTIMIZED: Clean up security events tracking
                security_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)  # 15 minutes
                for guild_id, events in self._guild_security_events.items():
                    old_security_events = [e for e in events if (datetime.now(timezone.utc) - e["timestamp"]).total_seconds() > 900]
                    for e in old_security_events:
                        events.remove(e)
                if old_security_events:
                    self.logger.debug(f"Cleaned up {len(old_security_events)} old security events")
                
                # Clean up audit log rate limiter (remove entries older than 5 minutes for token bucket)
                audit_log_cutoff = datetime.now(timezone.utc).timestamp() - 300  # 5 minutes
                old_audit_log_keys = [guild_id for guild_id, bucket in self._audit_log_rate_limiter.items() if bucket.get("last_update", 0) < audit_log_cutoff]
                for guild_id in old_audit_log_keys:
                    del self._audit_log_rate_limiter[guild_id]
                if old_audit_log_keys:
                    self.logger.debug(f"Cleaned up {len(old_audit_log_keys)} old audit log rate limiter entries")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in antinuke cleanup loop", exc_info=True)

    async def _is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        # ENHANCED SECURITY: Zero-trust mode - whitelist disabled for maximum security
        if self._zero_trust_enabled:
            # Only owner and bot itself bypass zero-trust
            if user_id == OWNER_ID:
                return True
            if self.bot.user and user_id == self.bot.user.id:
                return True
            # All other users: NO whitelist protection
            return False
        
        # Track whitelist checks
        self._record_metric("whitelist_checks")
        
        # Check cache first for fast lookup
        cached_result = self._get_cached_whitelist_status(guild_id, user_id)
        if cached_result is not None:
            self._record_metric("whitelist_cached_hits")
            return cached_result

        if user_id == OWNER_ID:
            self._set_cached_whitelist_status(guild_id, user_id, True)
            return True
        if self.bot.user and user_id == self.bot.user.id:
            self._set_cached_whitelist_status(guild_id, user_id, True)
            return True

        # Use Discord object cache for guild lookups
        guild_cache_key = f"guild:{guild_id}"
        guild = self._get_cached_discord_object(guild_cache_key)
        if not guild:
            guild = self.bot.get_guild(guild_id)
            if guild:
                self._set_cached_discord_object(guild_cache_key, guild)
        
        if guild and guild.owner_id == user_id:
            self._set_cached_whitelist_status(guild_id, user_id, True)
            return True

        # Check safe admin list with cached JSON parsing (using fast-path guild settings)
        settings = await get_guild_fast(guild_id)
        safe_admins_json = settings.get("antinuke_safe_admins", "[]")
        
        # Try to use cached safe admins list
        safe_admins = self._get_cached_safe_admins(guild_id, safe_admins_json)
        if safe_admins is None:
            # Parse and cache if not available
            try:
                safe_admins = json.loads(safe_admins_json)
                self._set_cached_safe_admins(guild_id, safe_admins, safe_admins_json)
            except json.JSONDecodeError:
                safe_admins = []
        
        if user_id in safe_admins:
            self._set_cached_whitelist_status(guild_id, user_id, True)
            return True

        # Check if user is a bot and if it's whitelisted using fast-path function
        member_cache_key = f"member:{guild_id}:{user_id}"
        member = self._get_cached_discord_object(member_cache_key)
        if not member and guild:
            member = guild.get_member(user_id)
            if member:
                self._set_cached_discord_object(member_cache_key, member)
        
        is_bot = member and member.bot
        
        # Parallel check: bot whitelist + role whitelist + user whitelist
        # Use asyncio.gather for parallel execution when multiple checks needed
        if is_bot:
            if await is_user_whitelisted_fast(guild_id, user_id, is_bot=True):
                self._set_cached_whitelist_status(guild_id, user_id, True)
                return True
            else:
                # Cache the negative result
                self._set_cached_whitelist_status(guild_id, user_id, False)
                return False

        # For non-bots, check role whitelist and user whitelist in parallel
        if member and member.roles:
            user_role_ids = {role.id for role in member.roles}
            
            # Parallel checks for better performance
            role_check, user_check = await asyncio.gather(
                user_has_whitelisted_role_fast(guild_id, user_role_ids),
                is_user_whitelisted_fast(guild_id, user_id, is_bot=False),
                return_exceptions=True
            )
            
            # Handle results
            if not isinstance(role_check, Exception) and role_check:
                self._set_cached_whitelist_status(guild_id, user_id, True)
                return True
            if not isinstance(user_check, Exception) and user_check:
                self._set_cached_whitelist_status(guild_id, user_id, True)
                return True
        else:
            # No roles, just check user whitelist
            if await is_user_whitelisted_fast(guild_id, user_id, is_bot=False):
                self._set_cached_whitelist_status(guild_id, user_id, True)
                return True

        # Cache the negative result
        self._set_cached_whitelist_status(guild_id, user_id, False)
        return False

    async def _check_threshold(self, guild_id: int, user_id: int, action_type: str) -> bool:
        # ENHANCED SECURITY: Aggressive threshold checking with instant action for critical actions
        max_count, window = await get_antinuke_threshold_fast(guild_id, action_type)
        
        # SECURITY ENHANCEMENT: 300% - Reduced thresholds by 70% for faster detection
        critical_actions = ["webhook_create", "webhook_delete", "bot_add", "guild_update", "channel_delete", "role_delete"]
        if action_type in critical_actions:
            max_count = max(1, max_count // 2)  # Reduce threshold by 50% for critical actions
            window = max(5, window // 2)  # Reduce time window by 50%
        
        self.rate_tracker.add_event(guild_id, user_id, action_type)
        count = self.rate_tracker.count_events(guild_id, user_id, action_type, window)
        
        # ENHANCED SECURITY: Proactive threat hunting - build suspicious activity score
        if self._threat_hunting_enabled:
            await self._update_suspicious_score(guild_id, user_id, action_type)
        
        # ENHANCED SECURITY: Instant action on first occurrence for extremely critical actions
        zero_tolerance_actions = ["bot_add", "webhook_create", "guild_update"]
        if action_type in zero_tolerance_actions and count >= 1:
            return True  # Instant detection
            
        # ENHANCED SECURITY: Preemptive action based on suspicious activity score
        if self._threat_hunting_enabled:
            suspicious_score = self._get_suspicious_score(guild_id, user_id)
            if suspicious_score > 0.7:  # 70% suspicion threshold
                self.logger.security("PREEMPTIVE_ACTION", f"Preemptive action triggered for user {user_id} due to suspicious score: {suspicious_score:.2f}", guild_id, user_id)
                return True  # Preemptive protection
            
        return count > max_count
    
    async def _update_suspicious_score(self, guild_id: int, user_id: int, action_type: str):
        """Update suspicious activity score for proactive threat hunting."""
        if guild_id not in self._suspicious_activity_scores:
            self._suspicious_activity_scores[guild_id] = {}
        
        if user_id not in self._suspicious_activity_scores[guild_id]:
            self._suspicious_activity_scores[guild_id][user_id] = 0.0
        
        # Different actions have different suspicious weights
        suspicious_weights = {
            "webhook_create": 0.4,
            "webhook_delete": 0.4,
            "bot_add": 0.5,
            "guild_update": 0.4,
            "role_create": 0.2,
            "role_delete": 0.4,
            "channel_create": 0.2,
            "channel_delete": 0.4,
            "ban": 0.3,
            "kick": 0.3,
        }
        
        weight = suspicious_weights.get(action_type, 0.1)
        self._suspicious_activity_scores[guild_id][user_id] += weight
        
        # Track recent violations
        key = (guild_id, user_id)
        if key not in self._recent_violations:
            self._recent_violations[key] = []
        self._recent_violations[key].append(datetime.now(timezone.utc))
        
        # Clean up old violations (older than 10 minutes)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        self._recent_violations[key] = [t for t in self._recent_violations[key] if t > cutoff]
        
        # Decay suspicious score if no recent violations
        if len(self._recent_violations[key]) == 0:
            self._suspicious_activity_scores[guild_id][user_id] *= 0.9  # 10% decay
    
    def _get_suspicious_score(self, guild_id: int, user_id: int) -> float:
        """Get current suspicious activity score for a user."""
        if guild_id not in self._suspicious_activity_scores:
            return 0.0
        return self._suspicious_activity_scores[guild_id].get(user_id, 0.0)

    async def _apply_punishment(self, guild: discord.Guild, member: discord.Member, punishment: str, reason: str, bypass_whitelist: bool = False, severity: str = "normal") -> None:
        try:
            # CRITICAL BUG FIX: Never punish the bot itself
            if self.bot.user and member.id == self.bot.user.id:
                self.logger.error(f"CRITICAL BUG: Attempting to punish the bot itself! Member ID: {member.id}, Bot ID: {self.bot.user.id}")
                return
            
            # CRITICAL SECURITY: Never bypass whitelist for premium bots
            # Premium bots on the blacklist are always treated as security risks
            if member.bot:
                from database import is_premium_bot_blacklisted
                if await is_premium_bot_blacklisted(member.id):
                    self.logger.security("PREMIUM_BOT_DETECTED", f"Premium bot {member.id} detected - blocking whitelist bypass and punishing", guild.id, member.id)
                    # Force bypass_whitelist to False for premium bots
                    bypass_whitelist = False
            
            # Check if emergency mode is active - if so, always bypass whitelist
            emergency_active = await self.is_emergency_active(guild.id)
            if emergency_active:
                bypass_whitelist = True
                severity = "critical"
                self.logger.security("EMERGENCY_MODE_PUNISHMENT", f"Emergency mode active - bypassing all checks for user {member.id}", guild.id, member.id)
            
            # FINAL SECURITY: Bypass whitelist for ALL antinuke actions
            # The whitelist bypass parameter now controls this completely
            if not bypass_whitelist and severity != "critical":
                if await self._is_whitelisted(guild.id, member.id):
                    self.logger.warning(f"Aborting punishment for {member.id} - user is whitelisted")
                    return
            elif bypass_whitelist or severity == "critical":
                self.logger.security("WHITELIST_BYPASS", f"Bypassing whitelist for user {member.id} due to {severity} severity threat", guild.id, member.id)
                self.logger.warning(f"CRITICAL: Punishing user {member.id} despite whitelist status - SECURITY THREAT")
            
            # Record this attack for consecutive detection
            self.enhanced_restore.attack_detector.record_attack(guild.id)
            
            # Check for consecutive attacks - activate emergency mode if needed
            if self.enhanced_restore.attack_detector.is_consecutive_attack(guild.id):
                await self.enhanced_restore.activate_emergency_mode(guild)
                self.logger.security("CONSECUTIVE_ATTACK", f"Consecutive attack detected in {guild.name} by {member.id}", guild.id)
            
            # Create protected snapshot before punishment
            try:
                await snapshot_guild(guild, trigger_event="attack_detected")
                self.logger.info(f"Created attack snapshot for guild {guild.id}")
            except Exception as e:
                self.logger.warning(f"Failed to create attack snapshot: {e}")
            
            # PRE-VALIDATION: Check if bot can actually punish this user before attempting
            can_punish, punish_reason = self._can_punish_user(guild, member, punishment)
            if not can_punish:
                self.logger.warning(f"Cannot punish {member.id} with {punishment}: {punish_reason}")
                
                # Try fallback punishments in order of severity
                fallback_attempts = []
                if punishment == "ban":
                    fallback_attempts = ["kick", "timeout", "strip"]
                elif punishment == "kick":
                    fallback_attempts = ["timeout", "strip"]
                elif punishment == "timeout":
                    fallback_attempts = ["strip"]
                
                for fallback_punishment in fallback_attempts:
                    can_fallback, fallback_reason = self._can_punish_user(guild, member, fallback_punishment)
                    if can_fallback:
                        self.logger.info(f"Attempting fallback punishment {fallback_punishment} for {member.id} (original {punishment} failed: {punish_reason})")
                        await self._apply_punishment(guild, member, fallback_punishment, f"{reason} (fallback from {punishment})", bypass_whitelist, severity)
                        return
                
                # No viable punishment found - notify owner and log
                self.logger.error(f"No viable punishment available for {member.id} - all attempts failed")
                await self._notify_owner(guild, self._create_permission_denied_embed(guild, member, punishment, punish_reason))
                return
            
            # Proceed with punishment
            if punishment == "ban":
                await guild.ban(member, reason=reason, delete_message_days=0)
                self.logger.security("PUNISHMENT_SUCCESS", f"Banned user {member.id}", guild.id, member.id)
            elif punishment == "kick":
                await guild.kick(member, reason=reason)
                self.logger.security("PUNISHMENT_SUCCESS", f"Kicked user {member.id}", guild.id, member.id)
            elif punishment == "strip":
                bot_member = guild.me
                roles_to_remove = [
                    role
                    for role in member.roles
                    if role < bot_member.top_role and role != guild.default_role and not role.managed
                ]
                await member.remove_roles(*roles_to_remove, reason=reason)
                if member.voice and member.voice.channel:
                    await member.edit(deafen=True, reason=reason)
                self.logger.security("PUNISHMENT_SUCCESS", f"Stripped roles from user {member.id}", guild.id, member.id)
            elif punishment == "timeout":
                until = datetime.now(timezone.utc) + timedelta(days=28)
                await member.timeout(until, reason=reason)
                self.logger.security("PUNISHMENT_SUCCESS", f"Timed out user {member.id}", guild.id, member.id)
                
        except discord.Forbidden as e:
            # Explicit permission error - this should be rare now with pre-validation
            self.logger.error(f"Forbidden to punish {member.id} with {punishment}: {e}")
            
            # Rate limit owner notifications to avoid spam
            notification_key = (guild.id, member.id, punishment)
            now = datetime.now(timezone.utc)
            
            # Only notify if we haven't notified about this specific user/punishment in the last 5 minutes
            if notification_key not in self._punishment_notifications or \
               (now - self._punishment_notifications[notification_key]).total_seconds() > 300:
                
                self._punishment_notifications[notification_key] = now
                
                try:
                    owner = guild.get_member(guild.owner_id)
                    if owner:
                        await owner.send(
                            f"⚠️ **{guild.name}**: I tried to punish **{member}** (`{member.id}`) for {punishment} but I lack permissions (Forbidden). Error: {e}\n\n"
                            f"This should not happen with pre-validation. Please check my role hierarchy and permissions."
                        )
                except Exception:
                    pass
        except Exception as e:
            # Other errors
            self.logger.error(f"Failed to punish {member.id} with {punishment}: {e}", exc_info=True)
            
            # Rate limit owner notifications
            notification_key = (guild.id, member.id, punishment)
            now = datetime.now(timezone.utc)
            
            if notification_key not in self._punishment_notifications or \
               (now - self._punishment_notifications[notification_key]).total_seconds() > 300:
                
                self._punishment_notifications[notification_key] = now
                
                try:
                    owner = guild.get_member(guild.owner_id)
                    if owner:
                        await owner.send(
                            f"⚠️ **{guild.name}**: I tried to punish **{member}** (`{member.id}`) for {punishment} but encountered an error: {e}"
                        )
                except Exception:
                    pass

    def _create_permission_denied_embed(self, guild: discord.Guild, member: discord.Member, punishment: str, reason: str) -> discord.Embed:
        """Create an embed for permission denied situations."""
        embed = discord.Embed(
            title="🚨 Permission Denied - Cannot Punish",
            description=f"**Target:** {member.mention} (`{member.id}`)\n"
                       f"**Attempted Punishment:** {punishment}\n"
                       f"**Reason:** {reason}\n"
                       f"**Bot Role:** {guild.me.top_role.mention} (Position: {guild.me.top_role.position})\n"
                       f"**User Top Role:** {max(member.roles, key=lambda r: r.position).mention if member.roles else '@everyone'}",
            color=0xFF4444
        )
        embed.set_footer(text=f"Guild: {guild.name} | Bot: {guild.me}")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    async def _notify_owner(self, guild: discord.Guild, embed: discord.Embed) -> None:
        try:
            owner = guild.get_member(guild.owner_id)
            if owner:
                await owner.send(embed=embed)
        except Exception:
            pass

    async def _log_to_channel(self, guild: discord.Guild, embed: discord.Embed) -> None:
        try:
            settings = await get_guild(guild.id)
            log_ch_id = settings.get("log_channel", 0)
            if not log_ch_id:
                return
            ch = guild.get_channel(log_ch_id)
            if not ch:
                return
            await ch.send(embed=embed)
        except Exception:
            pass

    async def _delete_webhook_if_unauthorized(self, guild: discord.Guild, adder_id: int, webhook_id: int) -> None:
        if await self._is_whitelisted(guild.id, adder_id):
            return
        try:
            webhooks = await guild.webhooks()
            for w in webhooks:
                if getattr(w, "id", None) == webhook_id:
                    await w.delete(reason="[Repent Antinuke] Unauthorized webhook create")
                    return
        except Exception:
            pass

    async def _delete_all_user_webhooks(self, guild: discord.Guild, user_id: int) -> None:
        try:
            webhooks = await guild.webhooks()
            deleted_count = 0
            for w in webhooks:
                creator = getattr(w, "user", None) or getattr(w, "creator", None)
                if creator and creator.id == user_id:
                    await w.delete(reason=f"[Repent Antinuke] Webhook cleanup for punished user {user_id}")
                    deleted_count += 1
            if deleted_count:
                self.logger.security("WEBHOOK_CLEANUP", f"Deleted {deleted_count} webhooks created by user {user_id}", user_id=user_id)
        except Exception:
            pass
    
    async def _trigger_emergency_mode(self, guild: discord.Guild, reason: str) -> None:
        """Trigger emergency mode for maximum security during attacks."""
        async with self._lock:
            if guild.id in self._emergency_mode_active:
                return  # Already in emergency mode
            
            self._emergency_mode_active.add(guild.id)
            self._attack_detected_time[guild.id] = datetime.now(timezone.utc)
        
        self.logger.security("EMERGENCY_MODE", f"Emergency mode activated for guild {guild.id}. Reason: {reason}", guild_id=guild.id)
        
        # Log emergency mode activation
        try:
            settings = await get_guild(guild.id)
            log_ch_id = settings.get("log_channel", 0)
            if log_ch_id:
                ch = guild.get_channel(log_ch_id)
                if ch:
                    embed = discord.Embed(
                        title="🚨 EMERGENCY MODE ACTIVATED",
                        description=f"Suspicious attack pattern detected!\n\n**Reason:** {reason}\n\n**Security Measures Active:**\n"
                                    f"• Enhanced rate limiting bypassed\n"
                                    f"• Zero-tolerance enforcement active\n"
                                    f"• All webhooks being monitored\n"
                                    f"• Immediate punishment for suspicious actions",
                        color=0xFF0000
                    )
                    embed.set_footer(text="Repent Maximum Security")
                    embed.timestamp = datetime.now(timezone.utc)
                    await ch.send(embed=embed)
        except Exception:
            pass
        
        # Schedule emergency mode cleanup after 10 minutes
        asyncio.create_task(self._cleanup_emergency_mode(guild.id))
    
    async def _cleanup_emergency_mode(self, guild_id: int) -> None:
        """Clean up emergency mode after a timeout."""
        await asyncio.sleep(600)  # 10 minutes
        
        async with self._lock:
            if guild_id in self._emergency_mode_active:
                # Check if it's been at least 10 minutes since attack detection
                if guild_id in self._attack_detected_time:
                    if datetime.now(timezone.utc) - self._attack_detected_time[guild_id] > timedelta(minutes=10):
                        self._emergency_mode_active.remove(guild_id)
                        del self._attack_detected_time[guild_id]
                        self.logger.security("EMERGENCY_MODE", f"Emergency mode deactivated for guild {guild_id}", guild_id=guild_id)

    async def _handle_violation(self, guild: discord.Guild, user_id: int, action_type: str, target_desc: str = "") -> None:
        # MAXIMUM SECURITY: Track security event for pattern detection
        pattern_result = self._track_security_event(guild.id, user_id, action_type)
        
        # MAXIMUM SECURITY: Zero-tolerance actions bypass whitelist for critical threats
        is_zero_tolerance = action_type in self._zero_tolerance_actions
        is_suspicious_pattern = pattern_result.get("is_suspicious", False)
        
        # Security: Check whitelist BEFORE acquiring lock to prevent TOCTOU race condition
        # EXCEPT for zero-tolerance actions and suspicious patterns
        if not is_zero_tolerance and not is_suspicious_pattern:
            if await self._is_whitelisted(guild.id, user_id):
                return
        
        async with self._get_guild_lock(guild.id):
            # Double-check whitelist inside lock for absolute safety
            # EXCEPT for zero-tolerance actions and suspicious patterns
            if not is_zero_tolerance and not is_suspicious_pattern:
                if await self._is_whitelisted(guild.id, user_id):
                    return

            settings = await get_guild(guild.id)
            if not settings.get("antinuke_enabled", 1):
                return

            member = guild.get_member(user_id) or None
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException as e:
                    self.logger.error(f"HTTP error fetching member {user_id}: {e}")
                    return
                except Exception:
                    return

            # MAXIMUM SECURITY: Enhanced punishment based on threat level
            if is_suspicious_pattern:
                punishment = "ban"  # Maximum punishment for suspicious patterns
                reason = f"[Repent Antinuke] CRITICAL: Suspicious pattern detected - {pattern_result.get('pattern', 'unknown')}. Action: {action_type}"
                self.logger.security("SUSPICIOUS_PATTERN", f"Pattern: {pattern_result.get('pattern')}, Count: {pattern_result.get('count')}", guild_id=guild.id, user_id=user_id)
                
                # Activate emergency lockdown for suspicious patterns
                if self._emergency_mode_config.get("auto_activate", True):
                    await self.activate_emergency_lockdown(guild.id, f"Suspicious pattern: {pattern_result.get('pattern')}")
                
                await self._apply_punishment(guild, member, punishment, reason, bypass_whitelist=True, severity="critical")
            elif is_zero_tolerance:
                punishment = "ban"  # Maximum punishment for zero-tolerance actions
                reason = f"[Repent Antinuke] CRITICAL: Zero-tolerance action - {action_type}"
                self.logger.security("ZERO_TOLERANCE", f"Action: {action_type}", guild_id=guild.id, user_id=user_id)
                
                # Activate emergency lockdown for zero-tolerance actions
                if self._emergency_mode_config.get("auto_activate", True):
                    await self.activate_emergency_lockdown(guild.id, f"Zero-tolerance action: {action_type}")
                
                await self._apply_punishment(guild, member, punishment, reason, bypass_whitelist=True, severity="critical")
            else:
                punishment = settings.get("punishment", DEFAULT_PUNISHMENT)
                reason = f"[Repent Antinuke] {action_type} threshold exceeded"
                await self._apply_punishment(guild, member, punishment, reason, bypass_whitelist=True, severity="critical")
            await add_punished_user(guild.id, user_id, reason, self.bot.user.id if self.bot.user else 0, punishment)
            
            # MAXIMUM SECURITY: For zero-tolerance actions, clean up all webhooks
            if action_type in ["webhook_create", "webhook_delete"]:
                await self._delete_all_user_webhooks(guild, user_id)

            await log_action_fast(
                guild.id,
                "antinuke_trigger",
                user_id,
                {"action_type": action_type, "punishment": punishment, "target": target_desc},
            )
            
            # Log to security system
            self.logger.antinuke_trigger(action_type, guild.id, user_id, punishment)

            embed = antinuke_embed(
                action=action_type,
                target=target_desc or "Server",
                responsible=f"{member.mention} (`{member.id}`)",
                punishment=punishment,
                guild=guild,
            )

            await self._notify_owner(guild, embed)
            await self._log_to_channel(guild, embed)

            self.rate_tracker.clear_events(guild.id, user_id, action_type)

    async def _handle_instant_punishment(self, guild: discord.Guild, user_id: int, action_type: str, target_desc: str = "", guild_name_changed: bool = False, target_id: int = 0) -> None:
        async with self._get_guild_lock(guild.id):
            # Event deduplication check - prevent duplicate punishment for same event
            if target_id and self._is_event_processed(guild.id, user_id, action_type, target_id):
                self.logger.debug(f"Event already processed - skipping duplicate punishment for user {user_id}, action {action_type}, target {target_id}")
                return
            
            if await self._is_whitelisted(guild.id, user_id):
                return

            # Graceful degradation: if database is unhealthy, use fallback mode
            settings = None
            if not self._should_use_fallback():
                settings = await get_guild(guild.id)
                if not settings.get("antinuke_enabled", 1):
                    return
            else:
                self.logger.warning("Operating in fallback mode - using degraded antinuke functionality")
                # In fallback mode, we only perform essential checks without database
                # Still punish based on critical actions, but skip database-dependent features

            member = guild.get_member(user_id) or None
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException as e:
                    self.logger.error(f"HTTP error fetching member {user_id}: {e}")
                    self._set_component_health("audit_log", False)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to fetch member {user_id}: {e}")
                    return

            # Permission validation - check if user actually has permission for this action
            if not self._validate_user_permission(guild, member, action_type, target_id):
                self.logger.warning(
                    f"Skipping punishment for {member.id} - user lacks permission for action {action_type}"
                )
                return

            punishment = settings.get("punishment", DEFAULT_PUNISHMENT) if not self._should_use_fallback() else DEFAULT_PUNISHMENT
            reason = f"[Repent Antinuke] Instant Punishment: {target_desc}"

            try:
                await self._apply_punishment(guild, member, punishment, reason, bypass_whitelist=True, severity="critical")
            except Exception as e:
                self.logger.error(f"Failed to apply punishment: {e}")
                # Don't mark database as unhealthy for punishment failures (could be permission issues)
                return
            
            # Skip database operations in fallback mode
            if not self._should_use_fallback():
                try:
                    await add_punished_user(guild.id, user_id, reason, self.bot.user.id if self.bot.user else 0, punishment)
                except Exception as e:
                    self.logger.error(f"Failed to add punished user to database: {e}")
                    self._set_component_health("database", False)
                    # Continue anyway - punishment already applied

            # Mark event as processed to prevent duplicate punishment
            if target_id:
                self._mark_event_processed(guild.id, user_id, action_type, target_id)

            await self._delete_all_user_webhooks(guild, user_id)

            # INSTANT GUILD NAME RESTORATION - restore immediately after punishment
            if guild_name_changed:
                asyncio.create_task(self._restore_guild_name(guild))

            await log_action_fast(
                guild.id,
                "antinuke_trigger_instant",
                user_id,
                {"action_type": action_type, "punishment": punishment, "target": target_desc},
            )

            embed = antinuke_embed(
                action=action_type,
                target=target_desc or "Server",
                responsible=f"{member.mention} (`{member.id}`)",
                punishment=punishment,
                guild=guild,
            )
            embed.title = "🚨 Instant Security Punishment"
            embed.description = (
                f"**Reason:** {target_desc}"
                f"\n**Responsible User:** {member.mention} (`{member.id}`)"
                f"\n**Punishment:** {punishment}"
            )

            await self._notify_owner(guild, embed)
            await self._log_to_channel(guild, embed)

    def _is_dangerous_role(self, role: discord.Role) -> bool:
        from config import DANGEROUS_PERMISSIONS

        for perm in DANGEROUS_PERMISSIONS:
            if getattr(role.permissions, perm, False):
                return True
        return False

    def _is_administrator_role(self, role: discord.Role) -> bool:
        """Check if role has administrator permission."""
        return role.permissions.administrator

    def _can_manage_guild(self, role: discord.Role) -> bool:
        """Check if role can manage guild settings."""
        return role.permissions.manage_guild

    def _detect_suspicious_pattern(self, attacker: discord.Member, action: discord.AuditLogAction, entry: discord.AuditLogEntry) -> bool:
        """Detect suspicious activity patterns that may indicate bypass attempts."""
        # Check for rapid successive actions
        recent_count = self.rate_tracker.count_events(
            entry.guild.id, attacker.id, "suspicious_activity", 30
        )
        
        # If user has multiple suspicious actions in 30 seconds, flag as suspicious
        if recent_count >= 3:
            return True
        
        # Check for高危 actions in short time
        high_risk_actions = [
            discord.AuditLogAction.role_update,
            discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.role_delete,
            discord.AuditLogAction.guild_update,
        ]
        
        if action in high_risk_actions:
            # Track this as a potentially suspicious action
            self.rate_tracker.add_event(entry.guild.id, attacker.id, "suspicious_activity")
        
        return False

    async def _handle_suspicious_activity(self, guild: discord.Guild, attacker: discord.Member, action: discord.AuditLogAction):
        """Handle detected suspicious activity with stricter punishment."""
        # Log the suspicious activity
        await log_action(
            guild.id,
            "suspicious_activity",
            attacker.id,
            {"action": str(action), "punishment": "ban"}
        )
        
        # Apply immediate ban for suspicious patterns
        try:
            await guild.ban(
                attacker,
                reason="[Repent] Suspicious activity pattern detected - auto-ban for security",
                delete_message_days=0,
            )
            self.logger.security(
                "SUSPICIOUS_ACTIVITY_BAN",
                f"Banned user {attacker.id} for suspicious activity pattern",
                guild_id=guild.id,
                user_id=attacker.id
            )
        except Exception as e:
            self.logger.error(f"Failed to ban suspicious user {attacker.id}: {e}", exc_info=True)

    def _check_permission_escalation(self, before: discord.Role, after: discord.Role) -> bool:
        """Check if a role update represents permission escalation."""
        from config import DANGEROUS_PERMISSIONS
        
        before_dangerous = [perm for perm in DANGEROUS_PERMISSIONS if getattr(before.permissions, perm, False)]
        after_dangerous = [perm for perm in DANGEROUS_PERMISSIONS if getattr(after.permissions, perm, False)]
        
        # Check if dangerous permissions were added
        new_dangerous = set(after_dangerous) - set(before_dangerous)
        if new_dangerous:
            return True, list(new_dangerous)
        
        # Check if administrator was granted (most dangerous)
        if not before.permissions.administrator and after.permissions.administrator:
            return True, ["administrator"]
        
        # Check if manage_guild was granted
        if not before.permissions.manage_guild and after.permissions.manage_guild:
            return True, ["manage_guild"]
        
        return False, []

    async def _handle_permission_escalation(self, guild: discord.Guild, user_id: int, role: discord.Role, added_permissions: List[str]):
        """Handle permission escalation detection."""
        if await self._is_whitelisted(guild.id, user_id):
            return

        settings = await get_guild(guild.id)
        if not settings.get("antinuke_enabled", 1):
            return

        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error fetching member {user_id}: {e}")
                return
            except Exception:
                return

        punishment = settings.get("punishment", DEFAULT_PUNISHMENT)
        reason = f"[Repent Antinuke] Permission Escalation: Added dangerous permissions to {role.name}: {', '.join(added_permissions)}"

        await self._apply_punishment(guild, member, punishment, reason, bypass_whitelist=True, severity="critical")
        await add_punished_user(guild.id, user_id, reason, self.bot.user.id if self.bot.user else 0, punishment)

        # Log the incident
        await log_action(
            guild.id,
            "permission_escalation",
            user_id,
            {"role": role.name, "permissions": added_permissions, "punishment": punishment},
        )

        embed = discord.Embed(
            title="🚨 Permission Escalation Detected",
            description=f"**User:** {member.mention} ({member.id})\n"
                       f"**Role:** {role.mention}\n"
                       f"**Added Permissions:** {', '.join(added_permissions)}\n"
                       f"**Punishment:** {punishment}",
            color=0xFF4444
        )

        await self._notify_owner(guild, embed)
        await self._log_to_channel(guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """Detect permission escalation in role updates."""
        guild = after.guild
        settings = await get_guild(guild.id)
        
        # Check if permission escalation detection is enabled
        sensitivity = settings.get("antinuke_sensitivity_level", 5)
        if sensitivity < 5:  # Only check if sensitivity is medium or higher
            return
        
        # Get the audit log entry to find who made the change
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
            if entry.target.id == after.id:
                is_escalation, added_perms = self._check_permission_escalation(before, after)
                if is_escalation:
                    await self._handle_permission_escalation(guild, entry.user.id, after, added_perms)
                break

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Pre-compute cache data when bot joins a guild."""
        try:
            # Pre-warm cache for this guild
            await get_guild_fast(guild.id)
            
            # Cache owner and bot as whitelisted
            self._set_cached_whitelist_status(guild.id, guild.owner_id, True)
            if self.bot.user:
                self._set_cached_whitelist_status(guild.id, self.bot.user.id, True)
            
            self.logger.debug(f"Pre-warmed antinuke cache for new guild: {guild.id}")
        except Exception as e:
            self.logger.error(f"Failed to pre-warm cache for guild {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Enhanced member join with instant restore if configured."""
        # This complements the existing antinuke join check
        from database import is_hardbanned
        if await is_hardbanned(member.guild.id, member.id):
            try:
                await member.guild.ban(
                    member,
                    reason="[Repent] Hardban — auto reban on rejoin",
                    delete_message_days=0,
                )
                self.logger.security("HARDBAN_REBAN", f"Re-banned user {member.id}", guild_id=member.guild.id, user_id=member.id)
            except Exception as e:
                self.logger.error(f"Failed to reban hardbanned user {member.id}", exc_info=True)

    async def _auto_restore_channel(self, guild: discord.Guild, channel_id: int) -> bool:
        """Restore a single channel from cache with full settings including overwrites."""
        try:
            cached_channels = await get_cached_channels(guild.id)
            channel_data = next((c for c in cached_channels if int(c.get("channel_id")) == channel_id), None)
            
            if not channel_data:
                self.logger.warning(f"Channel {channel_id} not found in cache")
                return False
            
            # Check if channel already exists (might have been restored manually)
            if guild.get_channel(channel_id):
                return False
            
            channel_type = channel_data.get("type", 0)
            category_id = channel_data.get("category_id", 0) or 0
            category = guild.get_channel(category_id) if category_id else None
            
            # Parse overwrites from JSON
            overwrites = self._parse_overwrites(guild, channel_data.get("json_overwrites", "{}"))
            
            kwargs = {
                "name": channel_data.get("name", "restored"),
                "category": category,
                "position": channel_data.get("position", 0),
                "overwrites": overwrites,
                "reason": "[Repent] Auto-restore deleted channel",
            }
            
            # Type-specific settings
            if channel_type == 0:  # Text channel
                kwargs.update({
                    "topic": channel_data.get("topic", "") or None,
                    "nsfw": bool(channel_data.get("nsfw", 0)),
                    "slowmode_delay": channel_data.get("slowmode", 0) or 0,
                })
                await guild.create_text_channel(**kwargs)
            elif channel_type == 2:  # Voice channel
                await guild.create_voice_channel(**kwargs)
            elif channel_type == 4:  # Category
                kwargs.pop("category", None)  # Categories don't have categories
                await guild.create_category(**kwargs)
            
            return True
        except discord.HTTPException as e:
            if e.code == 30013:  # Maximum number of channels reached
                self.logger.warning(f"Cannot auto-restore channel {channel_id} - maximum channel limit (500) reached")
                # Log this but don't crash the restore process
                return False
            else:
                self.logger.error(f"Failed to auto-restore channel {channel_id}: {e}", exc_info=True)
                return False
        except Exception as e:
            self.logger.error(f"Failed to auto-restore channel {channel_id}: {e}", exc_info=True)
            return False
    
    def _parse_overwrites(self, guild: discord.Guild, overwrites_json: str) -> dict:
        """Parse permission overwrites from JSON and convert to Discord objects."""
        try:
            overwrites_dict = json.loads(overwrites_json)
            overwrites = {}
            
            for target_id_str, o_data in overwrites_dict.items():
                target_id = int(target_id_str)
                target = None
                
                if o_data.get("type") == "role":
                    target = guild.get_role(target_id)
                else:  # member
                    target = guild.get_member(target_id)
                    if not target:
                        continue  # Skip if member not found
                
                if target:
                    overwrites[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(o_data.get("allow", 0)),
                        discord.Permissions(o_data.get("deny", 0)),
                    )
            
            return overwrites
        except Exception:
            return {}
    
    async def _auto_restore_from_cache(
        self,
        guild: discord.Guild,
        only_channel_ids: Optional[Set[int]] = None,
        only_role_ids: Optional[Set[int]] = None,
        attack_timestamp: str = None,
    ) -> None:
        """Enhanced restore using multi-snapshot system.
        
        If only_channel_ids / only_role_ids are provided, restore ONLY those missing.
        If attack_timestamp is provided, selects snapshot from before the attack.
        """
        try:
            # Select the best snapshot for restoration
            snapshot = await self.enhanced_restore.select_restore_snapshot(guild.id, attack_timestamp)
            
            if not snapshot:
                self.logger.warning(f"No snapshot available for guild {guild.id}, using fallback restore")
                # Fall back to old method
                await self._legacy_restore_from_cache(guild, only_channel_ids, only_role_ids)
                return
            
            # Parse snapshot data
            from database import verify_snapshot_checksum
            if not await verify_snapshot_checksum(snapshot['id']):
                self.logger.error(f"Snapshot {snapshot['id']} failed checksum verification, using fallback")
                await self._legacy_restore_from_cache(guild, only_channel_ids, only_role_ids)
                return
            
            snapshot_data = json.loads(snapshot['data'])
            
            # Restore guild name first (if changed)
            await self._restore_guild_name(guild)
            
            # Restore channel names for renamed channels
            if only_channel_ids:
                await self._restore_channel_names(guild, only_channel_ids)
            
            # Use enhanced restore for full state recovery
            if only_role_ids:
                # Only restore specific roles using old method for now
                await self._restore_roles(guild, only_role_ids)
            else:
                # Use enhanced full restore for all roles
                await self.enhanced_restore.restore_roles_full(guild, snapshot_data)
            
            if only_channel_ids:
                # Restore specific channels using old method for now
                tasks = [self._auto_restore_channel(guild, channel_id) for channel_id in only_channel_ids]
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Use enhanced full restore for all channels
                await self.enhanced_restore.restore_channels_full(guild, snapshot_data)
            
            self.logger.info(f"Enhanced restore completed for guild {guild.id} using snapshot {snapshot['id']}")
            
        except Exception as e:
            self.logger.error(f"Enhanced restore failed: {e}, falling back to legacy", exc_info=True)
            # Fall back to old method on error
            await self._legacy_restore_from_cache(guild, only_channel_ids, only_role_ids)
    
    async def _legacy_restore_from_cache(
        self,
        guild: discord.Guild,
        only_channel_ids: Optional[Set[int]] = None,
        only_role_ids: Optional[Set[int]] = None,
    ) -> None:
        """Legacy restore method as fallback."""
        try:
            # Restore guild name first (if changed)
            await self._restore_guild_name(guild)
            
            # Restore channel names for renamed channels
            if only_channel_ids:
                await self._restore_channel_names(guild, only_channel_ids)
            
            # Restore roles if specified
            if only_role_ids:
                await self._restore_roles(guild, only_role_ids)
            
            # Restore channels if specified
            if only_channel_ids:
                # Restore channels in parallel for speed
                tasks = [self._auto_restore_channel(guild, channel_id) for channel_id in only_channel_ids]
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Legacy restore from cache failed: {e}", exc_info=True)
    
    async def _restore_roles(self, guild: discord.Guild, role_ids: Set[int]) -> None:
        """Restore specific roles from cache."""
        try:
            cached_roles = await get_cached_roles(guild.id)
            existing_roles = {r.id for r in guild.roles}
            
            for cr in cached_roles:
                role_id = cr.get("role_id")
                if role_id not in role_ids or role_id in existing_roles or role_id == guild.default_role.id:
                    continue
                
                await guild.create_role(
                    name=cr.get("name", "restored-role"),
                    permissions=discord.Permissions(cr.get("permissions", 0)),
                    color=discord.Color(cr.get("color", 0)),
                    hoist=bool(cr.get("hoist", 0)),
                    mentionable=bool(cr.get("mentionable", 0)),
                    position=cr.get("position", 0),
                    reason="[Repent] Auto-restore after antinuke trigger",
                )
        except Exception as e:
            self.logger.error(f"Failed to restore roles: {e}", exc_info=True)
    
    async def _auto_restore_role(self, guild: discord.Guild, role_id: int) -> bool:
        """Restore a single role from cache."""
        try:
            return await self._restore_roles(guild, {role_id}) is not None
        except Exception as e:
            self.logger.error(f"Failed to auto-restore role {role_id}: {e}", exc_info=True)
            return False
    
    async def _process_audit_log_event(self, guild: discord.Guild, target_id: int, action: discord.AuditLogAction) -> Optional[discord.AuditLogEntry]:
        """Helper method to process audit log events with error handling."""
        try:
            settings = await get_guild_fast(guild.id)
            if not settings.get("antinuke_enabled", 1):
                return None
                
            # Removed artificial delay for faster response to attacks
            async for entry in guild.audit_logs(limit=3, action=action):
                if entry.target and entry.target.id == target_id:
                    await self.process_audit_entry(entry)
                    return entry
        except Exception as e:
            self.logger.error(f"Failed to process audit log event: {e}", exc_info=True)
        return None

    async def process_audit_entry(self, entry: discord.AuditLogEntry) -> None:
        # Track start time for metrics
        import time
        start_time = time.time()
        
        # Early exit: Skip if basic validation fails
        if not entry.guild or not entry.user:
            return

        # Early exit: Skip if already processed (event deduplication)
        if entry.id in self._processed_entries:
            return
        # Store entry with timestamp for cleanup
        self._processed_entries[entry.id] = datetime.now(timezone.utc)

        guild = entry.guild
        attacker = entry.user
        action = entry.action

        # Early exit: Skip if attacker is the bot itself
        if self.bot.user and attacker.id == self.bot.user.id:
            self.logger.warning(f"Skipping audit entry performed by our own bot (ID: {attacker.id})")
            return

        # Early exit: Skip if attacker is the guild owner (owner can do anything)
        if attacker.id == guild.owner_id:
            self._record_metric("events_skipped_early")
            return

        # Record event processed
        self._record_metric("events_processed")

        # CRITICAL: Skip whitelist check for extremely dangerous actions
        # Even whitelisted users should be prevented from performing these critical attack vectors
        critical_actions = {
            discord.AuditLogAction.channel_update,  # Channel rename, locking, NSFW toggle
            discord.AuditLogAction.channel_delete,   # Channel deletion
            discord.AuditLogAction.channel_create,   # Mass channel creation
            discord.AuditLogAction.role_delete,      # Role deletion  
            discord.AuditLogAction.role_create,      # Role creation (with dangerous perms)
            discord.AuditLogAction.role_update,      # Role permission escalation
            discord.AuditLogAction.guild_update,     # Server name/icon changes
            # discord.AuditLogAction.guild_owner_transfer, # Ownership transfer (not available in Discord.py)
            discord.AuditLogAction.webhook_create,  # Webhook creation
            discord.AuditLogAction.webhook_delete,  # Webhook deletion
            discord.AuditLogAction.member_role_update, # Dangerous role assignment
            discord.AuditLogAction.thread_create,  # Thread creation
            discord.AuditLogAction.thread_delete,  # Thread deletion
            discord.AuditLogAction.ban,             # Mass bans
            discord.AuditLogAction.kick,            # Mass kicks
            discord.AuditLogAction.unban,           # Mass unbans
        }
        
        if action not in critical_actions:
            if await self._is_whitelisted(guild.id, attacker.id):
                return

        # Additional security: Check for suspicious patterns
        if self._detect_suspicious_pattern(attacker, action, entry):
            self.logger.security(
                "SUSPICIOUS_PATTERN",
                f"Suspicious activity pattern detected from user {attacker.id}",
                guild_id=guild.id,
                user_id=attacker.id
            )
            # Apply stricter punishment for suspicious patterns
            await self._handle_suspicious_activity(guild, attacker, action)
        
        # TOTAL ACTIONS CHECK: Prevent any user from doing too many actions regardless of type
        # This catches sophisticated attacks that mix different action types to bypass detection
        self.rate_tracker.add_event(guild.id, attacker.id, "total_actions")
        total_actions = self.rate_tracker.count_events(guild.id, attacker.id, "total_actions", 3)
        if total_actions >= 10:  # 10+ actions in 3 seconds = instant ban
            instant_punish = True
            instant_reason = "Rapid action pattern detected (too many actions in short time - likely nuke attack)"
        
        # GUILD-WIDE EMERGENCY CHECK: If total actions in the server exceed threshold, emergency lockdown
        # This prevents distributed attacks or multiple attackers working together
        self.rate_tracker.add_event(guild.id, 0, "guild_total_actions")  # user_id 0 = server-wide
        guild_total_actions = self.rate_tracker.count_events(guild.id, 0, "guild_total_actions", 5)
        if guild_total_actions >= 30:  # 30+ server actions in 5 seconds = emergency mode (reduced from 50 for faster response)
            instant_punish = True
            instant_reason = "EMERGENCY: Mass server attack detected - automatic lockdown triggered"

        action_type: str | None = None
        target_desc = ""
        extra_webhook_id: Optional[int] = None
        extra_bot_id: Optional[int] = None

        restore_channel_ids: Optional[Set[int]] = None
        restore_role_ids: Optional[Set[int]] = None

        instant_punish = False
        instant_reason = ""
        guild_name_changed = False

        if action == discord.AuditLogAction.bot_add:
            action_type = "bot_add"
            if entry.target and hasattr(entry.target, "id"):
                extra_bot_id = int(entry.target.id)
            target_desc = f"Bot: {getattr(entry.target, 'name', 'Unknown')} (`{getattr(entry.target, 'id', '0')}`)"

        elif action == discord.AuditLogAction.webhook_create:
            action_type = "webhook_create"
            if entry.target and hasattr(entry.target, "id"):
                extra_webhook_id = int(entry.target.id)
            target_desc = f"Webhook: {getattr(entry.target, 'name', 'Unknown')}"
            
            # Scan webhook URL for malicious domains if URL is available
            webhook_url = getattr(entry.target, "url", None)
            if webhook_url:
                url_scan_result = self.webhook_detector.scan_webhook_url(webhook_url)
                if url_scan_result["is_malicious"]:
                    instant_punish = True
                    instant_reason = f"Malicious webhook URL detected: {url_scan_result['threat_level']} - {', '.join(url_scan_result['threats_detected'])}"
                    self.logger.security("WEBHOOK_URL_THREAT", 
                        f"Malicious webhook URL detected: {url_scan_result['threat_level']}", 
                        guild_id=guild.id, user_id=attacker.id, extra=url_scan_result)
            
            # Track webhook creation for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "webhook_create")
            
            # INSTANT DETECTION: 3 webhook creates in 2 seconds = instant ban
            # This prevents the webhook flood attacks used by sophisticated nukers
            if self.rate_tracker.count_events(guild.id, attacker.id, "webhook_create", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass webhook creation attack detected (webhook flood)"

        elif action == discord.AuditLogAction.webhook_delete:
            action_type = "webhook_delete"
            
            # Track webhook deletion for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "webhook_delete")
            
            # INSTANT DETECTION: 3 webhook deletes in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "webhook_delete", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass webhook deletion attack detected"

        elif action == discord.AuditLogAction.role_update:
            before_perms = getattr(entry.changes.before, "permissions", None)
            after_perms = getattr(entry.changes.after, "permissions", None)
            if before_perms is not None and after_perms is not None:
                from config import DANGEROUS_PERMISSIONS

                added_perms = []
                for perm_name, value in after_perms:
                    if value and not getattr(before_perms, perm_name, False):
                        added_perms.append(perm_name)

                dangerous_added = [p for p in added_perms if p in DANGEROUS_PERMISSIONS]
                if dangerous_added:
                    instant_punish = True
                    instant_reason = (
                        "Permission escalation: granted dangerous permissions "
                        f"{', '.join(dangerous_added)}"
                    )

            if not instant_punish:
                action_type = "role_update"
                target_desc = f"@{getattr(entry.target, 'name', 'Role')}"

        elif action == discord.AuditLogAction.member_role_update:
            added_roles = getattr(entry.changes.after, "roles", [])
            
            # Track member role updates for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "member_role_update")
            
            # Check for dangerous role assignments
            for r in added_roles:
                if self._is_dangerous_role(r):
                    instant_punish = True
                    instant_reason = (
                        f"Permission escalation: assigned dangerous role @{r.name}"
                    )
                    break
            
            # INSTANT DETECTION: 5 role updates in 2 seconds = instant ban
            if not instant_punish and self.rate_tracker.count_events(guild.id, attacker.id, "member_role_update", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass role assignment attack detected (assigning roles to multiple users rapidly)"

        elif action == discord.AuditLogAction.ban:
            action_type = "ban"
            
            # Track ban actions for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "ban")
            
            # INSTANT DETECTION: 3 bans in 2 seconds = instant ban
            # This prevents mass ban attacks used by sophisticated nukers
            if self.rate_tracker.count_events(guild.id, attacker.id, "ban", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass ban attack detected (banning multiple users rapidly)"

        elif action == discord.AuditLogAction.unban:
            action_type = "unban"
            
            # Track unban actions (could be part of attack pattern)
            self.rate_tracker.add_event(guild.id, attacker.id, "unban")
            
            # INSTANT DETECTION: 5 unbans in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "unban", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass unban attack detected (suspicious pattern)"

        elif action == discord.AuditLogAction.kick:
            action_type = "kick"
            
            # Track kick actions for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "kick")
            
            # INSTANT DETECTION: 3 kicks in 2 seconds = instant ban
            # This prevents mass kick attacks used by sophisticated nukers
            if self.rate_tracker.count_events(guild.id, attacker.id, "kick", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass kick attack detected (kicking multiple users rapidly)"

        elif action == discord.AuditLogAction.channel_delete:
            action_type = "channel_delete"
            if entry.target and hasattr(entry.target, "id"):
                restore_channel_ids = {int(entry.target.id)}
            instant_punish = True
            instant_reason = "Unauthorized channel delete"
            
            # Track channel deletions for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "channel_delete")
            
            # INSTANT DETECTION: 3 channel deletes in 1 second = instant ban
            # This prevents parallel deletion attacks like the nuke bot uses
            if self.rate_tracker.count_events(guild.id, attacker.id, "channel_delete", 1) >= 3:
                instant_punish = True
                instant_reason = "Mass channel deletion attack detected (parallel channel destruction)"

        elif action == discord.AuditLogAction.channel_create:
            action_type = "channel_create"
            target_desc = f"Channel: {getattr(entry.target, 'name', 'Unknown')}"
            
            # Track channel creation for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "channel_create")
            
            # Check for suspicious channel names (nuke bot signatures)
            channel_name = getattr(entry.target, 'name', '').lower()
            suspicious_names = ['repent', 'god', 'nyo', 'yoursins', 'sins', 'clique', 'amen']
            if any(sus in channel_name for sus in suspicious_names):
                instant_punish = True
                instant_reason = f"Suspicious channel name detected: '{channel_name}' - likely nuke bot"
            
            # INSTANT DETECTION: 5 channel creates in 2 seconds = instant ban
            # This prevents the nuke bot's mass channel creation attack
            if self.rate_tracker.count_events(guild.id, attacker.id, "channel_create", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass channel creation attack detected (attempting to create 1000+ channels)"

        elif action == discord.AuditLogAction.role_delete:
            action_type = "role_delete"
            if entry.target and hasattr(entry.target, "id"):
                restore_role_ids = {int(entry.target.id)}
            instant_punish = True
            instant_reason = "Unauthorized role delete"
            
            # Track role deletions for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "role_delete")
            
            # INSTANT DETECTION: 3 role deletes in 1 second = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "role_delete", 1) >= 3:
                instant_punish = True
                instant_reason = "Mass role deletion attack detected (parallel role destruction)"

        elif action == discord.AuditLogAction.role_create:
            action_type = "role_create"
            target_desc = f"Role: {getattr(entry.target, 'name', 'Unknown')}"
            
            # Track role creation for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "role_create")
            
            # Check for dangerous permissions in new roles
            role_perms = getattr(entry.target, 'permissions', None)
            if role_perms:
                from config import DANGEROUS_PERMISSIONS
                has_dangerous = any(hasattr(role_perms, perm) and getattr(role_perms, perm, False) for perm in DANGEROUS_PERMISSIONS)
                if has_dangerous:
                    instant_punish = True
                    instant_reason = "Created role with dangerous permissions - permission escalation attack"
            
            # INSTANT DETECTION: 5 role creates in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "role_create", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass role creation attack detected (attempting to create many roles)"

        elif action == discord.AuditLogAction.role_update:
            before_perms = getattr(entry.changes.before, "permissions", None)
            after_perms = getattr(entry.changes.after, "permissions", None)
            if before_perms is not None and after_perms is not None:
                from config import DANGEROUS_PERMISSIONS

                added_perms = []
                for perm_name, value in after_perms:
                    if value and not getattr(before_perms, perm_name, False):
                        added_perms.append(perm_name)

                dangerous_added = [p for p in added_perms if p in DANGEROUS_PERMISSIONS]
                if dangerous_added:
                    instant_punish = True
                    instant_reason = (
                        "Permission escalation: granted dangerous permissions "
                        f"{', '.join(dangerous_added)}"
                    )

            if not instant_punish:
                action_type = "role_update"
                target_desc = f"@{getattr(entry.target, 'name', 'Role')}"
            
            # Track role updates for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "role_update")
            
            # INSTANT DETECTION: 5 role updates in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "role_update", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass role modification attack detected"

        elif action == discord.AuditLogAction.guild_update:
            before_vanity = getattr(entry.changes.before, "vanity_url_code", None)
            after_vanity = getattr(entry.changes.after, "vanity_url_code", None)
            before_name = getattr(entry.changes.before, "name", None)
            after_name = getattr(entry.changes.after, "name", None)
            before_icon = getattr(entry.changes.before, "icon", None)
            after_icon = getattr(entry.changes.after, "icon", None)
            
            # Track guild update for rapid attack detection
            self.rate_tracker.add_event(guild.id, attacker.id, "server_update")
            
            # Cache original guild name for restoration
            if before_name and before_name != after_name:
                await self._cache_original_guild_name(guild.id, before_name)
            
            # Detect vanity URL changes
            if before_vanity != after_vanity:
                instant_punish = True
                instant_reason = (
                    f"Vanity URL modification: changed from '{before_vanity}' to '{after_vanity}'"
                )
            # Detect server name changes (instant punish for rapid attacks)
            elif before_name != after_name:
                # Check for known nuke bot server names
                if after_name and any(sus in after_name.lower() for sus in ['repent', 'god', 'nyo', 'clique', 'amen']):
                    instant_punish = True
                    instant_reason = f"Nuke bot signature detected in server name: '{after_name}'"
                else:
                    instant_punish = True
                    instant_reason = f"Server name modification: changed from '{before_name}' to '{after_name}'"
                # Add guild name to restore list
                guild_name_changed = True
            # Detect server icon changes
            elif before_icon != after_icon:
                instant_punish = True
                instant_reason = "Server icon modification"
            else:
                action_type = "server_update"
                # Check for rapid server updates (multiple server changes in quick succession)
                if self.rate_tracker.count_events(guild.id, attacker.id, "server_update", 2) >= 2:
                    instant_punish = True
                    instant_reason = "Rapid server modification attack detected"

        elif action == discord.AuditLogAction.channel_update:
            # Channel updates include renames, permission changes, NSFW toggles, etc.
            action_type = "channel_update"
            target_desc = f"Channel: {getattr(entry.target, 'name', 'Unknown')}"
            
            # Track channel update for rapid attack detection
            self.rate_tracker.add_event(guild.id, attacker.id, "channel_update")
            
            # Check for NSFW toggling
            before_nsfw = getattr(entry.changes.before, "nsfw", None)
            after_nsfw = getattr(entry.changes.after, "nsfw", None)
            if before_nsfw != after_nsfw and after_nsfw:
                instant_punish = True
                instant_reason = "Channel NSFW toggle detected - potential nuke attack"
            
            # Check for permission changes (channel locking)
            before_overwrites = getattr(entry.changes.before, "permission_overwrites", None)
            after_overwrites = getattr(entry.changes.after, "permission_overwrites", None)
            if before_overwrites and after_overwrites:
                # Detect if @everyone's permissions were restricted (channel locking)
                try:
                    before_everyone = before_overwrites.get(guild.id)
                    after_everyone = after_overwrites.get(guild.id)
                    if before_everyone and after_everyone:
                        before_can_send = before_everyone.send_messages
                        after_can_send = after_everyone.send_messages
                        if before_can_send and not after_can_send:
                            instant_punish = True
                            instant_reason = "Channel locking detected - restricting @everyone permissions"
                except:
                    pass
            
            # Check if this is a channel rename
            before_name = getattr(entry.changes.before, "name", None)
            after_name = getattr(entry.changes.after, "name", None)
            if before_name and after_name and before_name != after_name:
                # Cache original channel name for restoration
                await self._cache_original_channel_name(guild.id, entry.target.id, before_name)
                
                # Channel rename detected
                self.logger.security(
                    "CHANNEL_RENAME",
                    f"Channel renamed from '{before_name}' to '{after_name}' by {attacker.id}",
                    guild_id=guild.id,
                    user_id=attacker.id
                )
                
                # INSTANT BAN - No rate tracker check, instant punishment on first rename
                # This prevents any channel rename at all - zero tolerance
                instant_punish = True
                instant_reason = f"Channel rename detected - renamed '{before_name}' to '{after_name}' (zero tolerance policy)"

        elif action == discord.AuditLogAction.emoji_delete:
            action_type = "emoji_delete"
            
            # Track emoji deletion for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "emoji_delete")
            
            # INSTANT DETECTION: 3 emoji deletes in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "emoji_delete", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass emoji deletion attack detected"

        elif action == discord.AuditLogAction.emoji_create:
            action_type = "emoji_create"
            
            # Track emoji creation for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "emoji_create")
            
            # INSTANT DETECTION: 5 emoji creates in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "emoji_create", 2) >= 5:
                instant_punish = True
                instant_reason = "Mass emoji creation attack detected"

        elif action == discord.AuditLogAction.invite_create:
            action_type = "invite_create"
            
            # Track invite creation (used in audit log spam attacks)
            self.rate_tracker.add_event(guild.id, attacker.id, "invite_create")
            
            # INSTANT DETECTION: 10 invites in 2 seconds = instant ban (audit log spam)
            if self.rate_tracker.count_events(guild.id, attacker.id, "invite_create", 2) >= 10:
                instant_punish = True
                instant_reason = "Mass invite creation detected (likely audit log spam attack)"

        elif action == discord.AuditLogAction.sticker_delete:
            action_type = "sticker_delete"
            
            # Track sticker deletion for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "sticker_delete")
            
            # INSTANT DETECTION: 3 sticker deletes in 2 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "sticker_delete", 2) >= 3:
                instant_punish = True
                instant_reason = "Mass sticker deletion attack detected"

        elif action == discord.AuditLogAction.thread_create:
            action_type = "thread_create"
            
            # Track thread creation for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "thread_create")
            
            # INSTANT DETECTION: 5 thread creates in 10 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "thread_create", 10) >= 5:
                instant_punish = True
                instant_reason = "Mass thread creation attack detected"

        elif action == discord.AuditLogAction.thread_delete:
            action_type = "thread_delete"
            
            # Track thread deletion for mass detection
            self.rate_tracker.add_event(guild.id, attacker.id, "thread_delete")
            
            # INSTANT DETECTION: 3 thread deletes in 5 seconds = instant ban
            if self.rate_tracker.count_events(guild.id, attacker.id, "thread_delete", 5) >= 3:
                instant_punish = True
                instant_reason = "Mass thread deletion attack detected"

        if instant_punish:
            target_id = getattr(entry.target, 'id', 0) if entry.target else 0
            await self._handle_instant_punishment(guild, attacker.id, action_type or "permission_escalation", instant_reason, guild_name_changed, target_id)
            # Trigger auto-restore for all channels if channel rename attack detected
            if action_type == "channel_update" and instant_punish:
                # Get all channels from latest snapshot and restore their names immediately
                from database import get_cached_channels
                try:
                    cached_channels = await get_cached_channels(guild.id)
                    if cached_channels:
                        # Restore all channel names from snapshot, not just recently modified ones
                        channel_ids = {int(c.get('channel_id')) for c in cached_channels if c.get('channel_id')}
                        if channel_ids:
                            asyncio.create_task(self._restore_channel_names(guild, channel_ids))
                            self.logger.info(f"Triggered immediate channel name restoration for {len(channel_ids)} channels")
                except Exception as e:
                    self.logger.error(f"Failed to trigger channel name restoration: {e}", exc_info=True)
            # Targeted restore for deletes
            if action in (discord.AuditLogAction.channel_delete, discord.AuditLogAction.role_delete, discord.AuditLogAction.thread_delete):
                await self._auto_restore_from_cache(
                    guild,
                    only_channel_ids=restore_channel_ids,
                    only_role_ids=restore_role_ids,
                    attack_timestamp=entry.created_at.isoformat() if entry.created_at else None,
                )
            return

        if not action_type:
            return

        # Webhook auto-delete for unwhitelisted creators
        if action == discord.AuditLogAction.webhook_create and extra_webhook_id is not None:
            await self._delete_webhook_if_unauthorized(guild, attacker.id, extra_webhook_id)
            await self._handle_instant_punishment(
                guild,
                attacker.id,
                "webhook_create",
                "Unauthorized webhook create",
                target_id=extra_webhook_id,
            )
            return

        # Threshold-based flow
        try:
            violated = await self._check_threshold(guild.id, attacker.id, action_type)
        except Exception:
            return

        if violated and action_type in ("webhook_create", "webhook_delete"):
            await self._delete_all_user_webhooks(guild, attacker.id)

        if action == discord.AuditLogAction.bot_add and extra_bot_id is not None and not violated:
            await self._kick_bot_if_unauthorized(guild, attacker.id, extra_bot_id)

        if not violated:
            return

        await self._handle_violation(guild, attacker.id, action_type, target_desc)

        # Targeted restore if violation is deletes (rare because we instant punish above)
        if action in (discord.AuditLogAction.channel_delete, discord.AuditLogAction.role_delete):
            await self._auto_restore_from_cache(
                guild,
                only_channel_ids=restore_channel_ids,
                only_role_ids=restore_role_ids,
                attack_timestamp=entry.created_at.isoformat() if entry.created_at else None,
            )

        if action == discord.AuditLogAction.bot_add and extra_bot_id is not None:
            await self._kick_bot_if_unauthorized(guild, attacker.id, extra_bot_id)
        
        # Record detection time metric
        import time
        detection_time_ms = (time.time() - start_time) * 1000
        self._record_metric("detection_times_ms", detection_time_ms)

    async def _kick_bot_if_unauthorized(self, guild: discord.Guild, adder_id: int, bot_id: int) -> None:
        if await self._is_whitelisted(guild.id, adder_id):
            return

        bot_member = guild.get_member(bot_id)
        if not bot_member:
            try:
                bot_member = await guild.fetch_member(bot_id)
            except discord.HTTPException as e:
                self.logger.error(f"HTTP error fetching bot {bot_id}: {e}")
                return
            except Exception:
                return

        if not bot_member or not getattr(bot_member, "bot", False):
            return

        try:
            await bot_member.kick(reason="[Repent Antinuke] Unauthorized bot add")
        except Exception:
            pass

    async def _detect_rapid_channel_renames(self, guild_id: int, user_id: int) -> bool:
        """Detect if a user is rapidly renaming channels using rate tracker."""
        # INSTANT DETECTION: 1 channel update = instant ban
        # No waiting for multiple renames - the first rename triggers immediate action
        recent_updates = self.rate_tracker.count_events(guild_id, user_id, "channel_update", 1)
        
        # If 1+ channel updates in 1 second, it's an attack - instant punish
        return recent_updates >= 1

    async def _cache_original_guild_name(self, guild_id: int, original_name: str):
        """Cache the original guild name for restoration."""
        try:
            from database import get_guild
            settings = await get_guild(guild_id)
            if settings:
                # Store in database for persistent storage
                settings['original_guild_name'] = original_name
                from database import update_guild
                await update_guild(guild.id, original_guild_name=original_name)
        except Exception as e:
            self.logger.error(f"Failed to cache original guild name: {e}", exc_info=True)

    async def _cache_original_channel_name(self, guild_id: int, channel_id: int, original_name: str):
        """Cache the original channel name for restoration."""
        try:
            from database import get_cached_channels
            cached_channels = await get_cached_channels(guild_id)
            for channel in cached_channels:
                if int(channel.get('channel_id', 0)) == channel_id:
                    # Update the cached channel with original name
                    channel['original_name'] = original_name
                    break
        except Exception as e:
            self.logger.error(f"Failed to cache original channel name: {e}", exc_info=True)

    async def _restore_guild_name(self, guild: discord.Guild) -> bool:
        """Restore the original guild name from cache."""
        try:
            from database import get_guild
            settings = await get_guild(guild.id)
            if not settings:
                return False
            
            original_name = settings.get('original_guild_name')
            if not original_name:
                return False
            
            await guild.edit(name=original_name, reason="[Repent] Restored original guild name after attack")
            self.logger.info(f"Restored guild name to '{original_name}' for guild {guild.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore guild name: {e}", exc_info=True)
            return False

    async def _restore_channel_names(self, guild: discord.Guild, channel_ids: Set[int]) -> None:
        """Restore original names for renamed channels from latest snapshot."""
        try:
            from database import get_latest_snapshot
            latest_snapshot = await get_latest_snapshot(guild.id)
            
            if not latest_snapshot:
                self.logger.warning(f"No snapshot found for guild {guild.id}, cannot restore channel names")
                return
            
            # Parse snapshot data
            import json
            snapshot_data = json.loads(latest_snapshot.get('data', '{}'))
            channels_data = snapshot_data.get('channels', [])
            
            # Create a map of channel_id -> original_name using latest snapshot
            name_map = {}
            for channel in channels_data:
                channel_id = int(channel.get('id', 0))
                if channel_id in channel_ids:
                    name_map[channel_id] = channel.get('name', 'restored')
            
            # Restore channel names in parallel for speed
            tasks = []
            for channel_id, original_name in name_map.items():
                channel = guild.get_channel(channel_id)
                if channel and channel.name != original_name:
                    tasks.append(channel.edit(name=original_name, reason="[Repent] Restored channel name from latest snapshot"))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                self.logger.info(f"Restored {len(tasks)} channel names from latest snapshot for guild {guild.id}")
        except Exception as e:
            self.logger.error(f"Failed to restore channel names: {e}", exc_info=True)

    async def create_auto_snapshot(self, guild: discord.Guild) -> bool:
        """Create an automatic snapshot for the guild."""
        try:
            from utils.cache import snapshot_guild
            await snapshot_guild(guild, trigger_event="manual")
            self.logger.info(f"Auto-snapshot created for guild {guild.name} ({guild.id})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create auto-snapshot for guild {guild.id}: {e}", exc_info=True)
            return False

    async def cleanup_old_snapshots(self, guild: discord.Guild, keep_count: int = 3) -> int:
        """Delete old snapshots, keeping only the most recent keep_count snapshots."""
        try:
            from database import get_snapshots, delete_snapshot
            snapshots = await get_snapshots(guild.id)
            
            # Sort by timestamp (newest first) and keep only the most recent
            snapshots.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            old_snapshots = snapshots[keep_count:]  # Remove old ones beyond keep_count
            
            deleted_count = 0
            for snapshot in old_snapshots:
                snapshot_id = snapshot.get('id')
                if snapshot_id:
                    await delete_snapshot(snapshot_id)
                    deleted_count += 1
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old snapshots for guild {guild.id}")
            return deleted_count
        except Exception as e:
            self.logger.error(f"Failed to cleanup old snapshots for guild {guild.id}: {e}", exc_info=True)
            return 0

    # Primary detection source: audit log only.
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        await self.process_audit_entry(entry)

    # FAST-PATH: Direct channel name change detection (bypasses audit log delay)
    # This is critical for stopping parallel execution attacks like Promise.allSettled
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """Direct detection of channel name changes - immediate response without audit log delay."""
        if not before.guild:
            return
            
        # Check if this is a name change
        if before.name != after.name:
            # Track channel name changes per guild for rapid attack detection
            self.rate_tracker.add_event(before.guild.id, 0, "mass_channel_rename")  # user_id 0 = server-wide

            # Track rename with rename tracker for per-user threshold detection
            try:
                # Get user from audit logs for tracking
                await self._wait_for_audit_log_quota(before.guild.id)
                try:
                    async for entry in before.guild.audit_logs(action=discord.AuditLogAction.channel_update, limit=1):
                        if entry.target.id == after.id and entry.changes.before.name == before.name:
                            user = entry.user
                            if user:
                                # Track rename with per-user threshold detection
                                rename_count, threshold = await self.rename_tracker.track_rename(
                                before.guild.id, user.id, after.id, before.name, after.name
                            )

                            # Check threshold and trigger punishment if exceeded
                            if rename_count >= threshold:
                                self.logger.security(
                                    "CHANNEL_RENAME_THRESHOLD",
                                    f"User {user.id} exceeded channel rename threshold: {rename_count}/{threshold}",
                                    guild_id=before.guild.id,
                                    user_id=user.id
                                )

                                # Trigger instant punishment with threshold reason
                                await self._handle_instant_punishment(before.guild, user.id, "channel_update",
                                    f"Channel rename threshold exceeded: {rename_count}/{threshold}", False, after.id)

                                # Mark as punished to prevent duplicate punishment
                                cache_key = (before.guild.id, user.id)
                                self._punished_users_cache[cache_key] = datetime.now(timezone.utc)
                            break
                except discord.HTTPException as e:
                    if e.status == 429:
                        # Handle rate limit with proper backoff
                        retry_after = e.retry_after if hasattr(e, 'retry_after') else None
                        await self._handle_rate_limit_error("audit_log", retry_after)
                        self.logger.warning(f"Rate limited on audit logs for guild {before.guild.id}")
                    else:
                        raise
            except Exception as e:
                self.logger.error(f"Error tracking channel rename: {e}")
            
            # EMERGENCY LOCKDOWN: If 5+ channels renamed in 1 second, trigger emergency mode
            if self.rate_tracker.count_events(before.guild.id, 0, "mass_channel_rename", 1) >= 5:
                self.logger.security(
                    "EMERGENCY_LOCKDOWN",
                    f"Mass channel rename attack detected (parallel execution) - emergency lockdown",
                    guild_id=before.guild.id
                )
                
                # Thread-safe emergency mode activation
                async with self._lock:
                    # Put guild in emergency mode (only if not already in emergency mode)
                    if before.guild.id not in self._emergency_mode_active:
                        self._emergency_mode_active.add(before.guild.id)
                        self._attack_detected_time[before.guild.id] = datetime.now(timezone.utc)
                
                # Get the most recent channel updater from audit logs and ban them
                try:
                    # Respect rate limits for audit log queries
                    await self._wait_for_audit_log_quota(before.guild.id)
                    
                    async for entry in before.guild.audit_logs(action=discord.AuditLogAction.channel_update, limit=5):
                        if entry.user:
                            cache_key = (before.guild.id, entry.user.id)
                            # Circuit breaker: don't punish same user twice in 10 seconds
                            if cache_key not in self._punished_users_cache or \
                               datetime.now(timezone.utc) - self._punished_users_cache[cache_key] > timedelta(seconds=10):
                                await self._handle_instant_punishment(before.guild, entry.user.id, "channel_update",
                                    "EMERGENCY: Mass parallel channel rename attack detected", False, after.id)
                                self._punished_users_cache[cache_key] = datetime.now(timezone.utc)
                            break
                except Exception as e:
                    self.logger.error(f"Failed emergency punishment: {e}")
            
            # If guild is in emergency mode, auto-restore all renamed channels immediately
            async with self._lock:
                in_emergency = before.guild.id in self._emergency_mode_active
            
            if in_emergency:
                try:
                    await after.edit(name=before.name, reason="[Repent] Emergency restoration during attack")
                    self.logger.security("EMERGENCY_RESTORE", f"Emergency restored channel to '{before.name}'", guild_id=before.guild.id)
                except Exception as e:
                    self.logger.error(f"Failed emergency restoration: {e}")
                return  # Skip further processing during emergency
            
            # Find who did this by checking recent audit logs for immediate punishment
            try:
                # Respect rate limits for audit log queries
                await self._wait_for_audit_log_quota(before.guild.id)
                
                async for entry in before.guild.audit_logs(action=discord.AuditLogAction.channel_update, limit=1):
                    if entry.target.id == after.id and entry.changes.before.name == before.name:
                        user = entry.user
                        if user:
                            cache_key = (before.guild.id, user.id)
                            
                            # Circuit breaker: don't process same user's actions repeatedly
                            if cache_key in self._punished_users_cache and \
                               datetime.now(timezone.utc) - self._punished_users_cache[cache_key] < timedelta(seconds=5):
                                return  # Already punished recently, skip
                            
                            # Log this detection
                            self.logger.security(
                                "DIRECT_CHANNEL_RENAME",
                                f"Direct detection: Channel renamed from '{before.name}' to '{after.name}' by {user.id}",
                                guild_id=before.guild.id,
                                user_id=user.id
                            )
                            
                            # INSTANT PUNISHMENT - bypass all checks for immediate response
                            # This is faster than audit log processing for parallel attacks
                            guild_name_changed = False
                            try:
                                await self._handle_instant_punishment(before.guild, user.id, "channel_update", 
                                    f"PARALLEL ATTACK: Channel renamed from '{before.name}' to '{after.name}' (direct detection)", 
                                    guild_name_changed, after.id)
                                
                                # Mark user as punished (circuit breaker)
                                self._punished_users_cache[cache_key] = datetime.now(timezone.utc)
                                
                                # IMMEDIATE RESTORATION - restore this channel name right now
                                try:
                                    await after.edit(name=before.name, reason="[Repent] Immediate restoration after parallel attack")
                                    self.logger.security("IMMEDIATE_RESTORE", f"Restored channel name to '{before.name}'", guild_id=before.guild.id, user_id=user.id)
                                except Exception as e:
                                    self.logger.error(f"Failed immediate channel restoration: {e}")
                            except Exception as e:
                                self.logger.error(f"Failed instant punishment on direct detection: {e}")
                        break
            except discord.HTTPException as e:
                self.logger.error(f"Audit log query failed with HTTP error: {e}")
                self._set_component_health("audit_log", False)
            except Exception as e:
                self.logger.error(f"Error in direct channel rename detection: {e}")

    # Fast-path listeners removed to avoid duplicate audit processing.
    # (They were causing unstable behavior and duplicate incidents.)


    # ── Commands ──
    @discord.app_commands.command(name="antinuke_restore", description="Restore deleted channels and roles from antinuke cache")
    async def antinuke_restore(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        await interaction.response.defer(thinking=True)
        try:
            await self._auto_restore_from_cache(interaction.guild, attack_timestamp=None)
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed("Restore Complete", "Auto-restore from cache has been attempted."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="punished", description="List punished users")
    async def punished(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        users = await get_punished_users(interaction.guild.id)
        if not users:
            return await interaction.response.send_message(embed=info_embed("Punished Users", "No punished users in this server."), ephemeral=False)

        lines = []
        for u in users[:20]:
            member = interaction.guild.get_member(u["user_id"])
            name = member.mention if member else f"<@{u['user_id']}>"
            lines.append(f"{name} — `{u.get('punishment_type','')}` — {u.get('reason','')[:50]}")

        await interaction.response.send_message(embed=info_embed("Punished Users", "\n".join(lines)), ephemeral=False)

    @discord.app_commands.command(name="pardon", description="Remove user from punished list")
    @discord.app_commands.describe(user="User to pardon")
    async def pardon(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.guild:
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        await remove_punished_user(interaction.guild.id, user.id)
        await interaction.response.send_message(embed=success_embed("Pardoned", f"{user.mention} has been removed from the punished list."), ephemeral=False)

    @discord.app_commands.command(name="nuke-webhooks", description="Delete ALL webhooks in the guild")
    async def nuke_webhooks(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        await interaction.response.defer(thinking=True)
        try:
            webhooks = await interaction.guild.webhooks()
            deleted = 0
            for w in webhooks:
                try:
                    await w.delete(reason=f"[Repent Antinuke] Webhooks nuked by {interaction.user}")
                    deleted += 1
                except Exception:
                    pass
            await interaction.followup.send(embed=success_embed("Webhooks Nuked", f"Successfully deleted {deleted} webhook(s)."), ephemeral=False)
        except Exception as e:
            await interaction.followup.send(embed=error_embed(f"Failed to delete webhooks: {e}"), ephemeral=True)

    @discord.app_commands.command(name="antinukelog", description="View recent antinuke security events")
    @app_commands.describe(limit="Number of events to show (1-50)")
    async def antinukelog(self, interaction: discord.Interaction, limit: int = 10):
        if not interaction.guild:
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        limit = max(1, min(50, limit))
        
        # Get recent security logs from database
        from database import get_recent_logs
        logs = await get_recent_logs(interaction.guild.id, limit)
        
        if not logs:
            return await interaction.response.send_message(
                embed=info_embed("Antinuke Logs", "No recent antinuke events recorded."),
                ephemeral=False
            )

        lines = []
        for log in logs:
            user_id = log.get("user_id", 0)
            action_type = log.get("action_type", "unknown")
            timestamp = log.get("timestamp", "")
            details = log.get("details", {})
            
            member = interaction.guild.get_member(user_id)
            user_mention = member.mention if member else f"<@{user_id}>"
            
            # Format timestamp if available
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = f"<t:{int(dt.timestamp())}:R>"
                except:
                    time_str = timestamp
            else:
                time_str = "Unknown time"
            
            # Format details based on action type
            detail_str = str(details)[:100] if details else "No details"
            
            lines.append(f"`{action_type}` — {user_mention} — {time_str}\n└─ {detail_str}")

        embed = discord.Embed(
            title=f"🛡️ Recent Antinuke Events ({len(logs)})",
            description="\n\n".join(lines[:limit]),
            color=0xFF4444
        )
        embed.set_footer(text="Showing recent antinuke security events")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    # Clear any existing commands that might conflict
    try:
        existing_commands = bot.tree.get_commands()
        for cmd in existing_commands:
            if cmd.name == "antinuke_restore":
                bot.tree.remove_command(cmd.name)
    except Exception as e:
        pass  # Ignore errors during cleanup
    
    await bot.add_cog(Antinuke(bot))


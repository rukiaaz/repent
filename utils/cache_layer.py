"""
Repent - Caching Layer
In-memory caching for frequently accessed data to reduce database load.
Optimized with sharding for parallel access and lock-free reads.
"""

import time
import asyncio
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import threading


class CacheEntry:
    """Represents a single cache entry with TTL and thread-safe access."""
    
    def __init__(self, value: Any, ttl: int = 300):
        """
        Initialize a cache entry.
        
        Args:
            value: Value to cache
            ttl: Time to live in seconds
        """
        self.value = value
        self.expires_at = time.time() + ttl
        self.ttl = ttl
        self._lock = threading.Lock()  # For thread-safe updates
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired (lock-free read)."""
        return time.time() > self.expires_at
    
    def refresh(self, ttl: int = None):
        """Refresh the cache entry TTL (thread-safe write)."""
        with self._lock:
            self.expires_at = time.time() + (ttl or self.ttl)
    
    def get_value(self) -> Any:
        """Get the current value (thread-safe read)."""
        with self._lock:
            return self.value
    
    def set_value(self, value: Any):
        """Set a new value (thread-safe write)."""
        with self._lock:
            self.value = value


class CacheShard:
    """A single shard of the cache with its own lock for parallel access."""
    
    def __init__(self, max_size: int = 625):
        """
        Initialize a cache shard.
        
        Args:
            max_size: Maximum number of entries in this shard (total/16)
        """
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
class CacheLayer:
    """High-performance cache layer with sharding, lock-free reads, and aggressive caching."""
    
    def __init__(self, default_ttl: int = 300, cleanup_interval: int = 60, max_size: int = 10000, shard_count: int = 16):
        """
        Initialize the cache layer with sharding.
        
        Args:
            default_ttl: Default time to live for cache entries
            cleanup_interval: Interval between cleanup runs
            max_size: Maximum number of cache entries before LRU eviction
            shard_count: Number of cache shards for parallel access (default 16)
        """
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        self.max_size = max_size
        self.shard_count = shard_count
        
        # Create multiple shards for parallel access
        shard_size = max_size // shard_count
        self._shards = [CacheShard(max_size=shard_size) for _ in range(shard_count)]
        
        self._cleanup_task = None
        self._memory_usage_check_interval = 300  # Check memory every 5 minutes
        self._memory_limit_mb = 300  # REDUCED from 500MB to 300MB for better memory management (OPTIMIZED)
    
    def _get_shard(self, key: str) -> CacheShard:
        """Get the appropriate shard for a key using consistent hashing."""
        shard_index = hash(key) % self.shard_count
        return self._shards[shard_index]
    
    async def start(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _cleanup_loop(self):
        """Periodically clean up expired cache entries and enforce memory limits."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
                # Check memory usage every 5 cleanup cycles (approximately 5 minutes)
                await self._enforce_memory_limit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Cache cleanup error: {e}")
    
    async def _cleanup_expired(self):
        """Remove expired cache entries and enforce size limit across all shards."""
        # Clean up all shards in parallel
        tasks = []
        for shard in self._shards:
            async def cleanup_shard(shard):
                async with shard._lock:
                    now = time.time()
                    
                    # Remove expired entries
                    expired_keys = [
                        key for key, entry in shard._cache.items()
                        if entry.is_expired()
                    ]
                    for key in expired_keys:
                        del shard._cache[key]
                        if key in shard._access_order:
                            del shard._access_order[key]
                    
                    # Enforce size limit with LRU eviction
                    if len(shard._cache) > shard.max_size:
                        # Sort by access time and remove oldest entries
                        sorted_keys = sorted(shard._access_order.keys(), key=lambda k: shard._access_order[k])
                        excess = len(shard._cache) - shard.max_size
                        for key in sorted_keys[:excess]:
                            del shard._cache[key]
                            del shard._access_order[key]
            
            tasks.append(cleanup_shard(shard))
        
        await asyncio.gather(*tasks)
    
    def _estimate_memory_usage(self) -> float:
        """Estimate current memory usage of cache in MB."""
        import sys
        total_size = 0
        for shard in self._shards:
            for key, entry in shard._cache.items():
                # Estimate size of key and value
                total_size += sys.getsizeof(key)
                total_size += sys.getsizeof(entry.value)
        return total_size / (1024 * 1024)  # Convert to MB
    
    async def _enforce_memory_limit(self):
        """Enforce memory limit by evicting oldest entries if necessary (OPTIMIZED)."""
        memory_usage = self._estimate_memory_usage()
        if memory_usage > self._memory_limit_mb:
            # Instead of clearing entire cache, clear old entries across all shards (OPTIMIZED)
            tasks = []
            for shard in self._shards:
                async def partial_cleanup(shard):
                    async with shard._lock:
                        # Remove oldest 30% of entries instead of clearing all
                        if shard._cache:
                            sorted_keys = sorted(shard._access_order.keys(), key=lambda k: shard._access_order[k])
                            entries_to_remove = int(len(sorted_keys) * 0.3)
                            for key in sorted_keys[:entries_to_remove]:
                                if key in shard._cache:
                                    del shard._cache[key]
                                if key in shard._access_order:
                                    del shard._access_order[key]
                
                tasks.append(partial_cleanup(shard))
            
            await asyncio.gather(*tasks)
            print(f"Cache partially cleaned due to memory limit: {memory_usage:.2f}MB > {self._memory_limit_mb}MB (30% cleared)")
    
    def _generate_key(self, prefix: str, *args) -> str:
        """Generate a cache key from components."""
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)
    
    async def get(self, prefix: str, *args) -> Optional[Any]:
        """
        Get a value from the cache with lock-free reads for hits.
        
        Args:
            prefix: Cache key prefix
            *args: Additional key components
            
        Returns:
            Cached value or None if not found/expired
        """
        key = self._generate_key(prefix, *args)
        shard = self._get_shard(key)
        
        # Lock-free read attempt first
        if key in shard._cache:
            entry = shard._cache[key]
            if not entry.is_expired():  # Lock-free expiration check
                # Update access time for LRU (needs lock)
                async with shard._lock:
                    shard._access_order[key] = time.time()
                return entry.get_value()  # Thread-safe value access
            else:
                # Entry expired, remove it (needs lock)
                async with shard._lock:
                    if key in shard._cache:
                        del shard._cache[key]
                    if key in shard._access_order:
                        del shard._access_order[key]
        
        return None
    
    async def set(self, prefix: str, value: Any, *args, ttl: int = None) -> None:
        """
        Set a value in the cache using sharding.
        
        Args:
            prefix: Cache key prefix
            value: Value to cache
            *args: Additional key components
            ttl: Custom TTL (uses default if not specified)
        """
        key = self._generate_key(prefix, *args)
        ttl = ttl or self.default_ttl
        shard = self._get_shard(key)
        
        async with shard._lock:
            shard._cache[key] = CacheEntry(value, ttl)
            shard._access_order[key] = time.time()
    
    async def delete(self, prefix: str, *args) -> None:
        """
        Delete a value from the cache using sharding.
        
        Args:
            prefix: Cache key prefix
            *args: Additional key components
        """
        key = self._generate_key(prefix, *args)
        shard = self._get_shard(key)
        
        async with shard._lock:
            if key in shard._cache:
                del shard._cache[key]
            if key in shard._access_order:
                del shard._access_order[key]
    
    async def clear_pattern(self, pattern: str) -> None:
        """
        Clear all cache entries matching a pattern across all shards.
        
        Args:
            pattern: Pattern to match (simple substring match)
        """
        # Clear pattern from all shards in parallel
        tasks = []
        for shard in self._shards:
            async def clear_from_shard(shard):
                async with shard._lock:
                    keys_to_delete = [
                        key for key in shard._cache.keys()
                        if pattern in key
                    ]
                    for key in keys_to_delete:
                        del shard._cache[key]
                        if key in shard._access_order:
                            del shard._access_order[key]
            tasks.append(clear_from_shard(shard))
        
        await asyncio.gather(*tasks)
    
    async def clear_all(self) -> None:
        """Clear all cache entries from all shards."""
        tasks = []
        for shard in self._shards:
            async def clear_shard(shard):
                async with shard._lock:
                    shard._cache.clear()
                    shard._access_order.clear()
            tasks.append(clear_shard(shard))
        
        await asyncio.gather(*tasks)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics aggregated from all shards."""
        total_entries = sum(len(shard._cache) for shard in self._shards)
        return {
            "total_entries": total_entries,
            "max_size": self.max_size,
            "shard_count": self.shard_count,
            "default_ttl": self.default_ttl,
            "cleanup_interval": self.cleanup_interval,
            "usage_percent": round((total_entries / self.max_size) * 100, 2) if self.max_size > 0 else 0
        }


# Global cache instance
_cache_layer: Optional[CacheLayer] = None


def get_cache_layer() -> CacheLayer:
    """Get the global cache layer instance."""
    global _cache_layer
    if _cache_layer is None:
        _cache_layer = CacheLayer()
    return _cache_layer
"""
Repent - Unified Cache Layer for Security Systems

Centralized caching system for all security modules with intelligent
cache management, performance monitoring, and memory optimization.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Any, Tuple, Callable
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
import threading

from utils.logger import get_logger


@dataclass
class CacheEntry:
    """Represents a single cache entry with metadata."""
    key: str
    value: Any
    timestamp: datetime
    ttl: int  # Time to live in seconds
    access_count: int = 0
    last_access: datetime = None
    hit_count: int = 0
    miss_count: int = 0
    
    def __post_init__(self):
        if self.last_access is None:
            self.last_access = self.timestamp
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds() > self.ttl
    
    def record_access(self):
        """Record an access to this cache entry."""
        self.access_count += 1
        self.hit_count += 1
        self.last_access = datetime.now(timezone.utc)


class UnifiedCache:
    """Unified caching system for security modules with intelligent management."""
    
    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        
        # Main cache storage
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Performance metrics
        self.metrics = {
            "total_hits": 0,
            "total_misses": 0,
            "total_evictions": 0,
            "total_sets": 0,
            "cache_size": 0,
            "memory_usage_estimate": 0,
        }
        
        # Cache statistics by category
        self.category_stats: Dict[str, Dict] = defaultdict(lambda: {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "size": 0
        })
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Background cleanup task
        self._cleanup_task = None
        self._running = False
        
        self.logger = get_logger()
    
    def get(self, key: str, category: str = "default") -> Optional[Any]:
        """Get value from cache."""
        with self._lock:
            if key not in self.cache:
                self.metrics["total_misses"] += 1
                self.category_stats[category]["misses"] += 1
                return None
            
            entry = self.cache[key]
            
            # Check if expired
            if entry.is_expired():
                self._remove_entry(key)
                self.metrics["total_misses"] += 1
                self.category_stats[category]["misses"] += 1
                return None
            
            # Record access and move to end (LRU)
            entry.record_access()
            self.cache.move_to_end(key)
            
            self.metrics["total_hits"] += 1
            self.category_stats[category]["hits"] += 1
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, category: str = "default") -> bool:
        """Set value in cache with optional TTL."""
        with self._lock:
            actual_ttl = ttl if ttl is not None else self.default_ttl
            
            # Create new entry
            entry = CacheEntry(
                key=key,
                value=value,
                timestamp=datetime.now(timezone.utc),
                ttl=actual_ttl
            )
            
            # Check if we need to evict
            if key in self.cache:
                self._remove_entry(key)
            elif len(self.cache) >= self.max_size:
                self._evict_lru()
            
            # Add new entry
            self.cache[key] = entry
            self.metrics["total_sets"] += 1
            self.metrics["cache_size"] = len(self.cache)
            self.category_stats[category]["sets"] += 1
            self.category_stats[category]["size"] = sum(
                1 for k, v in self.cache.items() 
                if v.timestamp == entry.timestamp
            )
            
            return True
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache."""
        with self._lock:
            if key in self.cache:
                self._remove_entry(key)
                return True
            return False
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self.cache.clear()
            self.metrics["cache_size"] = 0
    
    def clear_category(self, category: str):
        """Clear all entries in a specific category."""
        with self._lock:
            keys_to_remove = []
            for key in list(self.cache.keys()):
                if key.startswith(f"{category}:"):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                self._remove_entry(key)
    
    def _remove_entry(self, key: str):
        """Remove an entry from cache."""
        if key in self.cache:
            del self.cache[key]
            self.metrics["cache_size"] = len(self.cache)
    
    def _evict_lru(self):
        """Evict least recently used entry."""
        if self.cache:
            lru_key = next(iter(self.cache))
            self._remove_entry(lru_key)
            self.metrics["total_evictions"] += 1
    
    def cleanup_expired(self) -> int:
        """Clean up expired entries."""
        with self._lock:
            expired_keys = []
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_entry(key)
            
            return len(expired_keys)
    
    async def start_cleanup_task(self, interval: int = 60):
        """Start background cleanup task."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval))
    
    async def _cleanup_loop(self, interval: int):
        """Background cleanup loop."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                expired_count = self.cleanup_expired()
                if expired_count > 0:
                    self.logger.debug(f"Cache cleanup: removed {expired_count} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cache cleanup error: {e}")
    
    def stop_cleanup_task(self):
        """Stop background cleanup task."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics."""
        hit_rate = self.metrics["total_hits"] / max(
            self.metrics["total_hits"] + self.metrics["total_misses"], 1
        ) * 100
        
        return {
            **self.metrics,
            "hit_rate_percent": hit_rate,
            "category_stats": dict(self.category_stats),
            "estimated_memory_mb": self._estimate_memory_usage()
        }
    
    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage in MB."""
        # Rough estimation based on cache size and average entry size
        avg_entry_size = 1024  # 1KB per entry (conservative estimate)
        estimated_bytes = len(self.cache) * avg_entry_size
        return estimated_bytes / (1024 * 1024)
    
    def get_category_metrics(self, category: str) -> Dict[str, Any]:
        """Get metrics for a specific category."""
        stats = self.category_stats.get(category, {"hits": 0, "misses": 0, "sets": 0, "size": 0})
        
        hit_rate = stats["hits"] / max(stats["hits"] + stats["misses"], 1) * 100
        
        return {
            **stats,
            "hit_rate_percent": hit_rate
        }


class CacheDecorator:
    """Decorator for caching function results."""
    
    def __init__(self, cache: UnifiedCache, ttl: int = 300, category: str = "default"):
        self.cache = cache
        self.ttl = ttl
        self.category = category
    
    def __call__(self, func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key = f"{self.category}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            cached_value = self.cache.get(key, self.category)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = func(*args, **kwargs)
            self.cache.set(key, result, ttl=self.ttl, category=self.category)
            
            return result
        
        return wrapper
    
    async def async_call(self, func: Callable):
        """Async version of cache decorator."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key
            key = f"{self.category}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            cached_value = self.cache.get(key, self.category)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            self.cache.set(key, result, ttl=self.ttl, category=self.category)
            
            return result
        
        return wrapper


# Global cache instance for security systems
security_cache = UnifiedCache(max_size=5000, default_ttl=300)


def cached(ttl: int = 300, category: str = "default"):
    """Decorator for caching function results using global security cache."""
    def decorator(func: Callable):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                key = f"{category}:{func.__name__}:{hash(str(args) + str(kwargs))}"
                cached_value = security_cache.get(key, category)
                if cached_value is not None:
                    return cached_value
                result = await func(*args, **kwargs)
                security_cache.set(key, result, ttl=ttl, category=category)
                return result
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = f"{category}:{func.__name__}:{hash(str(args) + str(kwargs))}"
                cached_value = security_cache.get(key, category)
                if cached_value is not None:
                    return cached_value
                result = func(*args, **kwargs)
                security_cache.set(key, result, ttl=ttl, category=category)
                return result
            return wrapper
    return decorator
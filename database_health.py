"""
Repent - Database Health Monitoring System
Comprehensive monitoring for database performance, locks, and metrics.
"""

import asyncio
import time
import logging
import psutil
import aiosqlite
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from config import DB_PATH
from database_write_queue import get_write_queue

logger = logging.getLogger(__name__)


class DatabaseHealthMonitor:
    """
    Comprehensive database health monitoring system.
    
    Monitors:
    - Query timing metrics
    - Slow query detection
    - Lock detection and duration
    - Pool utilization
    - Cache hit/miss tracking
    - Memory usage monitoring
    - Connection health
    - Write queue health
    """
    
    def __init__(
        self,
        check_interval: float = 5.0,
        slow_query_threshold: float = 1.0,  # seconds
        lock_threshold: float = 0.5,  # seconds
        history_size: int = 1000
    ):
        self.check_interval = check_interval
        self.slow_query_threshold = slow_query_threshold
        self.lock_threshold = lock_threshold
        self.history_size = history_size
        
        # Query history
        self._query_history: deque = deque(maxlen=history_size)
        
        # Slow query log
        self._slow_queries: deque = deque(maxlen=100)
        
        # Lock detection
        self._lock_events: deque = deque(maxlen=100)
        
        # Metrics
        self._metrics = {
            "total_queries": 0,
            "slow_queries": 0,
            "lock_events": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": 0.0,
            "avg_query_time_ms": 0.0,
            "max_query_time_ms": 0.0,
            "total_query_time_ms": 0.0,
            "connection_pool_size": 0,
            "connection_pool_active": 0,
            "connection_pool_idle": 0,
            "memory_usage_mb": 0.0,
            "database_size_mb": 0.0,
            "wal_size_mb": 0.0,
            "shm_size_mb": 0.0
        }
        
        # Health status
        self._health_status = {
            "status": "unknown",
            "score": 100.0,
            "issues": [],
            "last_check": None
        }
        
        # Background task
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Cache layer reference
        self._cache_layer = None
    
    def set_cache_layer(self, cache_layer):
        """Set the cache layer reference for monitoring."""
        self._cache_layer = cache_layer
    
    async def start(self):
        """Start the health monitoring background task."""
        if self._running:
            return
            
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Database health monitor started")
    
    async def stop(self):
        """Stop the health monitoring background task."""
        if not self._running:
            return
            
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Database health monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Health monitor loop started")
        
        while self._running:
            try:
                await self._collect_metrics()
                await self._assess_health()
                await self._cleanup_old_data()
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)
    
    async def _collect_metrics(self):
        """Collect database metrics."""
        # Memory usage
        process = psutil.Process()
        memory_info = process.memory_info()
        self._metrics["memory_usage_mb"] = memory_info.rss / (1024 * 1024)
        
        # Database file sizes
        try:
            db_size = (await self._get_file_size(DB_PATH)) / (1024 * 1024)
            self._metrics["database_size_mb"] = db_size
            
            wal_size = (await self._get_file_size(DB_PATH + "-wal")) / (1024 * 1024)
            self._metrics["wal_size_mb"] = wal_size
            
            shm_size = (await self._get_file_size(DB_PATH + "-shm")) / (1024 * 1024)
            self._metrics["shm_size_mb"] = shm_size
        except Exception as e:
            logger.debug(f"Could not measure database file sizes: {e}")
        
        # Connection pool metrics
        try:
            from database import get_connection_pool
            pool = get_connection_pool()
            self._metrics["connection_pool_size"] = pool.max_connections
            self._metrics["connection_pool_active"] = len(pool._pool)
            self._metrics["connection_pool_idle"] = pool.max_connections - len(pool._pool)
        except Exception as e:
            logger.debug(f"Could not measure connection pool: {e}")
        
        # Write queue metrics
        try:
            queue = get_write_queue()
            queue_metrics = queue.get_metrics()
            self._metrics.update({
                "write_queue_size": queue_metrics["queue_size"],
                "write_queue_utilization": queue_metrics["queue_utilization"],
                "write_queue_dropped": queue_metrics["dropped_writes"],
                "write_queue_failed": queue_metrics["failed_writes"]
            })
        except Exception as e:
            logger.debug(f"Could not measure write queue: {e}")
    
    async def _get_file_size(self, path: str) -> int:
        """Get file size asynchronously."""
        import os
        try:
            return os.path.getsize(path)
        except FileNotFoundError:
            return 0
    
    async def _assess_health(self):
        """Assess overall database health."""
        issues = []
        score = 100.0
        
        # Check memory usage
        if self._metrics["memory_usage_mb"] > 1000:  # 1GB
            issues.append("High memory usage")
            score -= 20
        elif self._metrics["memory_usage_mb"] > 500:  # 500MB
            issues.append("Elevated memory usage")
            score -= 10
        
        # Check database size
        if self._metrics["database_size_mb"] > 1000:  # 1GB
            issues.append("Large database size")
            score -= 15
        elif self._metrics["database_size_mb"] > 500:  # 500MB
            issues.append("Growing database size")
            score -= 5
        
        # Check WAL file size (indicates uncommitted transactions)
        if self._metrics["wal_size_mb"] > 100:  # 100MB
            issues.append("Large WAL file - possible transaction backup")
            score -= 20
        elif self._metrics["wal_size_mb"] > 10:  # 10MB
            issues.append("Growing WAL file")
            score -= 5
        
        # Check slow queries
        if len(self._slow_queries) > 10:
            issues.append("Many slow queries detected")
            score -= 15
        
        # Check lock events
        if len(self._lock_events) > 10:
            issues.append("Many database lock events")
            score -= 20
        
        # Check cache hit rate
        if self._metrics["cache_hit_rate"] < 0.5:
            issues.append("Low cache hit rate")
            score -= 10
        
        # Check write queue
        if self._metrics.get("write_queue_utilization", 0) > 0.8:
            issues.append("Write queue nearly full")
            score -= 25
        elif self._metrics.get("write_queue_utilization", 0) > 0.5:
            issues.append("Write queue filling")
            score -= 10
        
        # Check for dropped writes
        if self._metrics.get("write_queue_dropped", 0) > 0:
            issues.append("Write queue dropping writes")
            score -= 30
        
        # Update health status
        self._health_status = {
            "status": "healthy" if score >= 80 else "degraded" if score >= 50 else "unhealthy",
            "score": max(0, score),
            "issues": issues,
            "last_check": datetime.now(timezone.utc).isoformat()
        }
    
    async def _cleanup_old_data(self):
        """Clean up old metric data."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # Clean query history
        while self._query_history and len(self._query_history) > self.history_size:
            oldest = self._query_history[0]
            if datetime.fromisoformat(oldest["timestamp"]) < cutoff:
                self._query_history.popleft()
            else:
                break
        
        # Clean slow queries
        while self._slow_queries and len(self._slow_queries) > 100:
            self._slow_queries.popleft()
        
        # Clean lock events
        while self._lock_events and len(self._lock_events) > 100:
            self._lock_events.popleft()
    
    def record_query(
        self,
        query: str,
        duration_ms: float,
        success: bool,
        lock_detected: bool = False
    ):
        """
        Record a query for monitoring.
        
        Args:
            query: SQL query (truncated for storage)
            duration_ms: Query duration in milliseconds
            success: Whether the query succeeded
            lock_detected: Whether a lock was encountered
        """
        self._metrics["total_queries"] += 1
        self._metrics["total_query_time_ms"] += duration_ms
        self._metrics["avg_query_time_ms"] = (
            self._metrics["total_query_time_ms"] / self._metrics["total_queries"]
        )
        self._metrics["max_query_time_ms"] = max(
            self._metrics["max_query_time_ms"],
            duration_ms
        )
        
        # Record query history
        self._query_history.append({
            "query": query[:100],  # Truncate for storage
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Detect slow queries
        if duration_ms / 1000 > self.slow_query_threshold:
            self._metrics["slow_queries"] += 1
            self._slow_queries.append({
                "query": query[:200],
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.warning(f"Slow query detected: {duration_ms:.2f}ms - {query[:100]}")
        
        # Detect lock events
        if lock_detected:
            self._metrics["lock_events"] += 1
            self._lock_events.append({
                "query": query[:200],
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            logger.warning(f"Database lock detected: {duration_ms:.2f}ms - {query[:100]}")
    
    def record_cache_hit(self, cache_type: str):
        """Record a cache hit."""
        self._metrics["cache_hits"] += 1
        self._update_cache_hit_rate()
    
    def record_cache_miss(self, cache_type: str):
        """Record a cache miss."""
        self._metrics["cache_misses"] += 1
        self._update_cache_hit_rate()
    
    def _update_cache_hit_rate(self):
        """Update cache hit rate."""
        total = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        if total > 0:
            self._metrics["cache_hit_rate"] = self._metrics["cache_hits"] / total
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all health metrics."""
        return {
            **self._metrics,
            "slow_query_count": len(self._slow_queries),
            "lock_event_count": len(self._lock_events),
            "query_history_size": len(self._query_history),
            "health_status": self._health_status
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get a comprehensive health report."""
        metrics = self.get_metrics()
        
        return {
            "overall_health": self._health_status["status"],
            "health_score": self._health_status["score"],
            "issues": self._health_status["issues"],
            "last_check": self._health_status["last_check"],
            "performance": {
                "avg_query_time_ms": metrics["avg_query_time_ms"],
                "max_query_time_ms": metrics["max_query_time_ms"],
                "slow_query_rate": metrics["slow_queries"] / max(metrics["total_queries"], 1),
                "lock_rate": metrics["lock_events"] / max(metrics["total_queries"], 1)
            },
            "caching": {
                "cache_hit_rate": metrics["cache_hit_rate"],
                "cache_hits": metrics["cache_hits"],
                "cache_misses": metrics["cache_misses"]
            },
            "resources": {
                "memory_usage_mb": metrics["memory_usage_mb"],
                "database_size_mb": metrics["database_size_mb"],
                "wal_size_mb": metrics["wal_size_mb"],
                "shm_size_mb": metrics["shm_size_mb"]
            },
            "connections": {
                "pool_size": metrics["connection_pool_size"],
                "active_connections": metrics["connection_pool_active"],
                "idle_connections": metrics["connection_pool_idle"]
            },
            "write_queue": {
                "queue_size": metrics.get("write_queue_size", 0),
                "queue_utilization": metrics.get("write_queue_utilization", 0),
                "dropped_writes": metrics.get("write_queue_dropped", 0),
                "failed_writes": metrics.get("write_queue_failed", 0)
            }
        }
    
    def get_slow_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent slow queries."""
        return list(self._slow_queries)[-limit:]
    
    def get_lock_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent lock events."""
        return list(self._lock_events)[-limit:]


# Global health monitor instance
_health_monitor: Optional[DatabaseHealthMonitor] = None

def get_health_monitor() -> DatabaseHealthMonitor:
    """Get the global health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = DatabaseHealthMonitor()
    return _health_monitor


# Decorator to instrument database queries
def instrument_query(func):
    """Decorator to instrument database queries for monitoring."""
    async def wrapper(*args, **kwargs):
        monitor = get_health_monitor()
        start_time = time.time()
        lock_detected = False
        
        try:
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            monitor.record_query(
                query=func.__name__,
                duration_ms=duration_ms,
                success=True,
                lock_detected=lock_detected
            )
            return result
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e).lower():
                lock_detected = True
            duration_ms = (time.time() - start_time) * 1000
            monitor.record_query(
                query=func.__name__,
                duration_ms=duration_ms,
                success=False,
                lock_detected=lock_detected
            )
            raise
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            monitor.record_query(
                query=func.__name__,
                duration_ms=duration_ms,
                success=False,
                lock_detected=lock_detected
            )
            raise
    
    return wrapper

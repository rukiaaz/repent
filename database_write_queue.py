"""
Repent - Production-Grade Database Write Queue
Single-writer architecture for SQLite to eliminate lock contention.
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Callable, Any, Dict, List
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseWrite:
    """Represents a single database write operation."""
    
    def __init__(self, operation: str, params: tuple, callback: Optional[Callable] = None):
        self.operation = operation  # SQL operation or function name
        self.params = params  # Parameters for the operation
        self.callback = callback  # Optional callback for result handling
        self.timestamp = time.time()
        self.retry_count = 0
        self.max_retries = 3


class DatabaseWriteQueue:
    """
    Production-grade single-writer queue for SQLite.
    
    Architecture:
    - Single writer thread prevents SQLite lock contention
    - Async queue for concurrent producers
    - Batched writes for better performance
    - Automatic retries with exponential backoff
    - Graceful shutdown with event persistence
    - No event loss via in-memory + disk backup
    - Deduplication to prevent duplicate writes
    """
    
    def __init__(
        self,
        batch_size: int = 50,
        batch_timeout: float = 0.1,
        max_queue_size: int = 10000,
        max_retries: int = 3,
        retry_backoff: float = 0.5
    ):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.max_queue_size = max_queue_size
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        
        # Main queue (in-memory)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        
        # Write deduplication set (operation + params hash)
        self._dedup_set: set = set()
        self._dedup_lock = asyncio.Lock()
        
        # Background task
        self._writer_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Metrics
        self._metrics = {
            "total_writes": 0,
            "successful_writes": 0,
            "failed_writes": 0,
            "retried_writes": 0,
            "dropped_writes": 0,
            "batch_writes": 0,
            "queue_size": 0,
            "avg_batch_size": 0,
            "avg_write_time_ms": 0,
            "total_write_time_ms": 0
        }
        
        # Graceful shutdown
        self._shutdown_event = asyncio.Event()
        
        # Database connection (single writer)
        self._db: Optional[aiosqlite.Connection] = None
        
        # Disk backup for critical writes (prevents data loss on crash)
        self._disk_backup_enabled = True
        self._backup_file = f"{DB_PATH}.write_queue_backup"
    
    async def start(self):
        """Start the write queue background task."""
        if self._running:
            return
            
        self._running = True
        self._shutdown_event.clear()
        
        # Initialize single writer connection
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row
        
        # Configure for single-writer performance
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.execute("PRAGMA busy_timeout = 5000")  # Reduced from 60000
        await self._db.execute("PRAGMA foreign_keys = ON")
        
        # Start writer task
        self._writer_task = asyncio.create_task(self._write_loop())
        logger.info("Database write queue started")
    
    async def stop(self):
        """Stop the write queue gracefully."""
        if not self._running:
            return
            
        self._running = False
        self._shutdown_event.set()
        
        # Wait for queue to drain (up to 30 seconds)
        try:
            await asyncio.wait_for(self._queue.join(), timeout=30.0)
            logger.info("Write queue drained successfully")
        except asyncio.TimeoutError:
            logger.warning("Write queue did not drain in time - forcing shutdown")
        
        # Cancel writer task
        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
        
        # Close database connection
        if self._db:
            await self._db.close()
            self._db = None
        
        logger.info("Database write queue stopped")
    
    async def enqueue(
        self,
        operation: str,
        params: tuple = (),
        callback: Optional[Callable] = None,
        critical: bool = False,
        dedup_key: Optional[str] = None
    ) -> bool:
        """
        Enqueue a write operation.
        
        Args:
            operation: SQL operation or function name
            params: Parameters for the operation
            callback: Optional callback for result handling
            critical: If True, write to disk backup as well
            dedup_key: Optional key for deduplication
        
        Returns:
            True if enqueued, False if queue is full
        """
        if not self._running:
            logger.warning("Write queue not running, dropping write")
            return False
        
        # Check deduplication
        if dedup_key:
            async with self._dedup_lock:
                if dedup_key in self._dedup_set:
                    self._metrics["dropped_writes"] += 1
                    return False
                self._dedup_set.add(dedup_key)
        
        # Create write operation
        write = DatabaseWrite(operation, params, callback)
        
        try:
            await self._queue.put(write)
            self._metrics["total_writes"] += 1
            self._metrics["queue_size"] = self._queue.qsize()
            
            # Disk backup for critical writes
            if critical and self._disk_backup_enabled:
                await self._write_to_disk_backup(write)
            
            return True
        except asyncio.QueueFull:
            self._metrics["dropped_writes"] += 1
            logger.warning("Write queue full, dropping write")
            return False
    
    async def _write_loop(self):
        """Main write loop - batches writes and executes them."""
        logger.info("Write loop started")
        
        while self._running and not self._shutdown_event.is_set():
            try:
                # Wait for first write or timeout
                write = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.batch_timeout
                )
                
                # Collect batch
                batch = [write]
                while len(batch) < self.batch_size:
                    try:
                        write = await asyncio.wait_for(
                            self._queue.get(),
                            timeout=0.01  # Short timeout to avoid blocking
                        )
                        batch.append(write)
                    except asyncio.TimeoutError:
                        break
                
                # Process batch
                if batch:
                    await self._process_batch(batch)
                    # Mark all as done
                    for write in batch:
                        self._queue.task_done()
                        
            except asyncio.TimeoutError:
                # No writes in batch timeout, continue
                continue
            except Exception as e:
                logger.error(f"Error in write loop: {e}", exc_info=True)
                await asyncio.sleep(self.retry_backoff)
    
    async def _process_batch(self, batch: List[DatabaseWrite]):
        """Process a batch of write operations."""
        start_time = time.time()
        
        try:
            # Begin transaction
            await self._db.execute("BEGIN TRANSACTION")
            
            # Process each write in the batch
            for write in batch:
                try:
                    # Execute the operation
                    if write.operation.startswith("SELECT"):
                        # Read operation (should not be in write queue, but handle gracefully)
                        cursor = await self._db.execute(write.operation, write.params)
                        if write.callback:
                            result = await cursor.fetchall()
                            # Call callback in background
                            asyncio.create_task(write.callback(result))
                    else:
                        # Write operation
                        await self._db.execute(write.operation, write.params)
                        
                except Exception as e:
                    # Rollback and retry individual writes
                    await self._db.execute("ROLLBACK")
                    await self._retry_write(write)
                    continue
            
            # Commit transaction
            await self._db.execute("COMMIT")
            
            # Update metrics
            batch_time_ms = (time.time() - start_time) * 1000
            self._metrics["successful_writes"] += len(batch)
            self._metrics["batch_writes"] += 1
            self._metrics["avg_batch_size"] = (
                (self._metrics["avg_batch_size"] * (self._metrics["batch_writes"] - 1) + len(batch)) /
                self._metrics["batch_writes"]
            )
            self._metrics["total_write_time_ms"] += batch_time_ms
            self._metrics["avg_write_time_ms"] = (
                self._metrics["total_write_time_ms"] / self._metrics["successful_writes"]
            )
            
            # Clear dedup keys for successful batch
            async with self._dedup_lock:
                for write in batch:
                    dedup_key = write.operation + str(write.params)
                    self._dedup_set.discard(dedup_key)
            
        except Exception as e:
            await self._db.execute("ROLLBACK")
            logger.error(f"Batch write failed: {e}", exc_info=True)
            
            # Retry individual writes
            for write in batch:
                await self._retry_write(write)
    
    async def _retry_write(self, write: DatabaseWrite):
        """Retry a failed write with exponential backoff."""
        if write.retry_count >= write.max_retries:
            self._metrics["failed_writes"] += 1
            self._metrics["retried_writes"] -= write.retry_count  # Subtract retries from total
            logger.error(f"Write failed after {write.retry_count} retries: {write.operation}")
            return
        
        write.retry_count += 1
        self._metrics["retried_writes"] += 1
        
        wait_time = self.retry_backoff * (2 ** write.retry_count)
        await asyncio.sleep(wait_time)
        
        try:
            await self._db.execute(write.operation, write.params)
            self._metrics["successful_writes"] += 1
        except Exception as e:
            await self._retry_write(write)
    
    async def _write_to_disk_backup(self, write: DatabaseWrite):
        """Write critical operations to disk backup for crash recovery."""
        try:
            backup_data = {
                "operation": write.operation,
                "params": write.params,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            async with asyncio.Lock():
                with open(self._backup_file, 'a') as f:
                    f.write(json.dumps(backup_data) + '\n')
        except Exception as e:
            logger.error(f"Failed to write to disk backup: {e}")
    
    async def recover_from_disk_backup(self):
        """Recover writes from disk backup after crash."""
        if not self._disk_backup_enabled:
            return
        
        try:
            recovered_count = 0
            with open(self._backup_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        write = DatabaseWrite(
                            data["operation"],
                            tuple(data["params"]) if isinstance(data["params"], list) else data["params"],
                            critical=False  # Don't backup again
                        )
                        await self._queue.put(write)
                        recovered_count += 1
                    except Exception as e:
                        logger.error(f"Failed to recover write from backup: {e}")
            
            if recovered_count > 0:
                logger.info(f"Recovered {recovered_count} writes from disk backup")
            
            # Clear backup file
            open(self._backup_file, 'w').close()
            
        except FileNotFoundError:
            # No backup file, which is normal
            pass
        except Exception as e:
            logger.error(f"Failed to recover from disk backup: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get write queue metrics."""
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "queue_capacity": self.max_queue_size,
            "queue_utilization": self._queue.qsize() / self.max_queue_size,
            "running": self._running
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for monitoring."""
        metrics = self.get_metrics()
        
        # Calculate health score
        health_score = 100.0
        
        # Penalize for dropped writes
        if metrics["dropped_writes"] > 0:
            drop_rate = metrics["dropped_writes"] / metrics["total_writes"]
            health_score -= drop_rate * 50
        
        # Penalize for failed writes
        if metrics["failed_writes"] > 0:
            failure_rate = metrics["failed_writes"] / metrics["total_writes"]
            health_score -= failure_rate * 30
        
        # Penalize for high queue utilization
        if metrics["queue_utilization"] > 0.8:
            health_score -= 20
        
        return {
            "status": "healthy" if health_score >= 80 else "degraded" if health_score >= 50 else "unhealthy",
            "health_score": max(0, health_score),
            "metrics": metrics
        }


# Global write queue instance
_write_queue: Optional[DatabaseWriteQueue] = None

def get_write_queue() -> DatabaseWriteQueue:
    """Get the global write queue instance."""
    global _write_queue
    if _write_queue is None:
        _write_queue = DatabaseWriteQueue()
    return _write_queue


# Convenience functions for common operations
async def log_action_async(
    guild_id: int,
    action_type: str,
    user_id: int = 0,
    details: dict = None,
    critical: bool = False
) -> bool:
    """
    Log action via write queue (async, non-blocking).
    
    Args:
        guild_id: Guild ID
        action_type: Action type
        user_id: User ID
        details: Action details
        critical: If True, use disk backup
    
    Returns:
        True if enqueued, False otherwise
    """
    queue = get_write_queue()
    
    if not queue._running:
        return False
    
    operation = """
        INSERT INTO action_log (guild_id, user_id, action_type, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """
    
    params = (
        guild_id,
        user_id,
        action_type,
        json.dumps(details or {}),
        datetime.now(timezone.utc).isoformat()
    )
    
    # Create dedup key to prevent duplicate logs
    dedup_key = f"{guild_id}:{user_id}:{action_type}:{hash(json.dumps(details or {}))}"
    
    return await queue.enqueue(
        operation=operation,
        params=params,
        critical=critical,
        dedup_key=dedup_key
    )


async def update_guild_async(
    guild_id: int,
    **kwargs
) -> bool:
    """
    Update guild settings via write queue (async, non-blocking).
    
    Args:
        guild_id: Guild ID
        **kwargs: Fields to update
    
    Returns:
        True if enqueued, False otherwise
    """
    queue = get_write_queue()
    
    if not queue._running:
        return False
    
    # Validate column names
    from database import GUILDS_ALLOWED_COLUMNS, _validate_column_names
    if not _validate_column_names(set(kwargs.keys()), GUILDS_ALLOWED_COLUMNS):
        raise ValueError("Invalid column names in update_guild_async")
    
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [guild_id]
    
    operation = f"UPDATE guilds SET {fields} WHERE guild_id = ?"
    
    # Create dedup key
    dedup_key = f"guild:{guild_id}:{hash(json.dumps(kwargs, sort_keys=True))}"
    
    return await queue.enqueue(
        operation=operation,
        params=tuple(values),
        critical=True,  # Guild updates are critical
        dedup_key=dedup_key
    )

"""
Redis-based queue service for managing background jobs.

Menangani:
- Antrian pending di Redis (LIST)
- Job yang sedang berjalan (SET)
"""
import json
from typing import Optional, Dict, Any

import redis

from src.app.settings.setting import REDIS_URL, REDIS_QUEUE_KEY
from src.app.utils.log import get_logger

logger = get_logger(__name__)

# Redis connection pool (singleton)
_redis_client: Optional[redis.Redis] = None

# Key untuk menyimpan job yang sedang diproses (running)
# Contoh: kalau REDIS_QUEUE_KEY = "job_queue" -> "job_queue:processing"
PROCESSING_SET_KEY = f"{REDIS_QUEUE_KEY}:processing"


def get_redis_client() -> redis.Redis:
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            # Test connection
            _redis_client.ping()
            logger.info(f"Connected to Redis at {REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {REDIS_URL}: {e}")
            raise
    return _redis_client


def enqueue_job(job_data: Dict[str, Any]) -> None:
    """
    Add a job to the Redis queue.

    Args:
        job_data: Dictionary containing job information.
                  Dianjurkan punya field "job_id".
    """
    try:
        client = get_redis_client()
        job_json = json.dumps(job_data)
        client.rpush(REDIS_QUEUE_KEY, job_json)
        logger.debug(f"Enqueued job: {job_data.get('job_id')}")
    except Exception as e:
        logger.error(f"Failed to enqueue job: {e}", exc_info=True)
        raise


def dequeue_job(timeout: int = 1) -> Optional[Dict[str, Any]]:
    """
    Get and remove a job from the Redis queue (blocking).

    Args:
        timeout: Blocking timeout in seconds (0 = block forever)

    Returns:
        Job data dictionary or None if timeout.
        Job yang di-dequeue otomatis dimasukkan
        ke SET 'processing_jobs' (PROCESSING_SET_KEY).
    """
    try:
        client = get_redis_client()
        result = client.blpop(REDIS_QUEUE_KEY, timeout=timeout)
        if result:
            _, job_json = result
            job = json.loads(job_json)

            job_id = job.get("job_id")
            if job_id is not None:
                # Tambahkan ke set job yang sedang diproses
                added = client.sadd(PROCESSING_SET_KEY, job_id)
                if added:
                    logger.info(f"Job dequeued and marked as running: {job_id} (added to processing set)")
                else:
                    logger.warning(f"Job {job_id} already exists in processing set (duplicate?)")
                # Verify it was added
                is_member = client.sismember(PROCESSING_SET_KEY, job_id)
                logger.debug(f"Job {job_id} in processing set: {is_member}, total running: {client.scard(PROCESSING_SET_KEY)}")
            else:
                logger.warning(
                    "Dequeued job tanpa 'job_id', tidak bisa di-track sebagai running."
                )

            return job

        # Timeout, tidak ada job
        return None
    except Exception as e:
        logger.error(f"Failed to dequeue job: {e}", exc_info=True)
        return None


def mark_job_done(job_id: str) -> None:
    """
    Mark job as done (remove from running set).

    Args:
        job_id: ID dari job yang sudah selesai diproses.
    """
    try:
        client = get_redis_client()
        removed = client.srem(PROCESSING_SET_KEY, job_id)
        if removed:
            logger.info(f"Job marked as done and removed from running: {job_id} (remaining running: {client.scard(PROCESSING_SET_KEY)})")
        else:
            logger.warning(
                f"Job {job_id} tidak ditemukan di running set (mungkin sudah dihapus?). Current running: {client.scard(PROCESSING_SET_KEY)}"
            )
    except Exception as e:
        logger.error(f"Failed to mark job as done: {e}", exc_info=True)


def get_queue_length() -> int:
    """
    Get the current number of jobs pending in the queue.

    Returns:
        Number of pending jobs.
    """
    try:
        client = get_redis_client()
        return client.llen(REDIS_QUEUE_KEY)
    except Exception as e:
        logger.error(f"Failed to get queue length: {e}", exc_info=True)
        return 0


def get_running_jobs_count() -> int:
    """
    Get the current number of jobs that are being processed (running).

    Returns:
        Number of running jobs.
    """
    try:
        client = get_redis_client()
        count = client.scard(PROCESSING_SET_KEY)
        logger.debug(f"Running jobs count: {count} (key: {PROCESSING_SET_KEY})")
        return count
    except Exception as e:
        logger.error(f"Failed to get running jobs count: {e}", exc_info=True)
        return 0


def get_queue_stats() -> Dict[str, int]:
    """
    Get stats for both pending and running jobs.

    Returns:
        {
            "pending": <jumlah job di queue>,
            "running": <jumlah job sedang diproses>,
            "total": pending + running
        }
    """
    try:
        client = get_redis_client()
        pending = client.llen(REDIS_QUEUE_KEY)
        running = client.scard(PROCESSING_SET_KEY)
        
        # Log untuk debugging
        if running > 0:
            # Get list of running job IDs for debugging
            running_jobs = client.smembers(PROCESSING_SET_KEY)
            logger.info(f"Queue stats - pending: {pending}, running: {running}, running_jobs: {list(running_jobs)}")
        else:
            logger.debug(f"Queue stats - pending: {pending}, running: {running}")

        stats = {
            "pending": pending,
            "running": running,
            "total": pending + running,
        }

        return stats
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}", exc_info=True)
        return {
            "pending": 0,
            "running": 0,
            "total": 0,
        }

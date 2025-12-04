"""
Redis-based queue service for managing background jobs.
"""
import json
import redis
from typing import Optional, Dict, Any
from src.app.settings.setting import REDIS_URL, REDIS_QUEUE_KEY
from src.app.utils.log import get_logger

logger = get_logger(__name__)

# Redis connection pool (singleton)
_redis_client: Optional[redis.Redis] = None


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
        job_data: Dictionary containing job information
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
        Job data dictionary or None if timeout
    """
    try:
        client = get_redis_client()
        result = client.blpop(REDIS_QUEUE_KEY, timeout=timeout)
        if result:
            _, job_json = result
            return json.loads(job_json)
        return None
    except Exception as e:
        logger.error(f"Failed to dequeue job: {e}", exc_info=True)
        return None


def get_queue_length() -> int:
    """
    Get the current number of jobs in the queue.
    
    Returns:
        Number of pending jobs
    """
    try:
        client = get_redis_client()
        return client.llen(REDIS_QUEUE_KEY)
    except Exception as e:
        logger.error(f"Failed to get queue length: {e}", exc_info=True)
        return 0


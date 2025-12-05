"""
Redis worker that processes jobs from the queue.
Run this as a separate process: python -m src.app.workers.redis_worker
"""
import sys
import signal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.app.services.redis_queue import dequeue_job, get_queue_length, mark_job_done
from src.app.api.api import process_snowy_and_callback
from src.app.utils.log import configure_logging, get_logger

configure_logging(log_subdir="api")
logger = get_logger(__name__)

# Graceful shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info("Shutdown signal received. Finishing current job and exiting...")
    shutdown_requested = True


def main():
    """Main worker loop."""
    global shutdown_requested
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Redis worker started. Waiting for jobs...")
    logger.info(f"Initial queue length: {get_queue_length()}")
    
    while not shutdown_requested:
        try:
            # Blocking dequeue (waits up to 40 seconds for a job)
            # dequeue_job automatically adds job to processing set
            job_data = dequeue_job(timeout=40)
            
            if job_data:
                job_id = job_data.get("job_id", "unknown")
                logger.info(f"Processing job: {job_id} (job_data keys: {list(job_data.keys())})")
                
                # Verify job is in processing set
                from src.app.services.redis_queue import get_running_jobs_count
                running_count = get_running_jobs_count()
                logger.info(f"Current running jobs count after dequeue: {running_count}")
                
                try:
                    result = process_snowy_and_callback(
                        job_id=job_id,
                        callback_url=job_data["callback_url"],
                        image_path=job_data["image_path"],
                        transaction_image_id=job_data["transaction_image_id"],
                        p_prompt=job_data.get("p_prompt"),
                        n_prompt=job_data.get("n_prompt"),
                        random_seed=job_data.get("random_seed", False),
                    )
                    logger.info(f"Job {job_id} completed successfully. Status: {result.get('status')}")
                    image_url = result.get("image_url")
                    image_path = result.get("image_path")
                    if image_url:
                        logger.debug(f"Job {job_id} S3 image URL: {image_url}")
                    else:
                        logger.debug(f"Job {job_id} image stored locally at: {image_path}")
                except Exception as e:
                    logger.exception(f"Error processing job {job_id}: {e}")
                    # Job failed but we continue processing other jobs
                finally:
                    # Mark job as done (remove from running set)
                    if job_id and job_id != "unknown":
                        mark_job_done(job_id)
            else:
                # No job available, continue loop
                continue
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down...")
            shutdown_requested = True
            break
        except Exception as e:
            logger.exception(f"Unexpected error in worker loop: {e}")
            # Continue processing despite errors
    
    logger.info("Redis worker stopped.")


if __name__ == "__main__":
    main()


import psutil
import logging
import subprocess
import asyncio
import random
from pathlib import Path
from src.app.utils.log import configure_logging, get_logger

configure_logging(log_subdir="api")
logging = get_logger(__name__)

async def resource_usage():
    """
    Returns the resource usage of the server.
    """
    logging.info("Getting resource usage metrics")
    cpu_usage = psutil.cpu_percent(interval=0.1)

    mem = psutil.virtual_memory()
    memory_used = mem.used / 1024 / 1024
    memory_total = mem.total / 1024 / 1024

    gpu = None
    try:
        logging.debug("Attempting to get GPU metrics")
        gpu_info = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,nounits,noheader"],
            encoding="utf-8"
        )

        gpu_parts = gpu_info.strip().split(", ")
        gpu = {
            "gpu_util_percent": float(gpu_parts[0]),
            "gpu_memory_used_mb": float(gpu_parts[1]),
            "gpu_memory_total_mb": float(gpu_parts[2])
        }
        logging.debug(f"GPU metrics retrieved: {gpu}")
    except Exception as e:
        logging.warning(f"Failed to get GPU metrics: {str(e)}")
        gpu = None

    response_data = {
        "cpu_percent": cpu_usage,
        "memory_used_mb": memory_used,
        "memory_total_mb": memory_total,
        "gpu": gpu 
    }
    logging.info(f"Resource usage metrics retrieved successfully: CPU={cpu_usage}%, Memory={memory_used:.2f}MB/{memory_total:.2f}MB")
    return response_data

async def inference_test():
    """
    Simulates an inference operation for testing purposes by introducing a random latency between 0.1 and 0.6 seconds.
    Returns a dictionary with the result status and the simulated latency.
    Useful for health checks, monitoring, or benchmarking the API's responsiveness.
    """
    logging.info("Starting inference test")
    latency = random.uniform(0.1, 0.6)
    await asyncio.sleep(latency) 
    logging.info(f"Inference test completed with latency: {latency:.3f}s")
    result = {
        "result": "OK",
        "latency": latency
    }
    return result
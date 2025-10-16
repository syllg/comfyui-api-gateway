import os
import time
import asyncio
import psutil
import logging
import subprocess

from functools import wraps
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Summary, REGISTRY, Gauge
from fastapi import FastAPI

cpu_usage = Gauge("app_cpu_percent", "CPU usage of FastAPI app")
memory_usage = Gauge("app_memory_usage_mb", "Memory usage of FastAPI app in MB")

async def start_monitor(app: FastAPI):
    """Start the monitoring task when the application starts"""
    try:
        monitor_task = asyncio.create_task(monitor_loop())
        app.state.monitor_task = monitor_task
        logging.info("Monitoring task started successfully")
    except Exception as e:
        logging.error(f"Failed to start monitoring task: {str(e)}")
        raise

async def stop_monitor(app: FastAPI):
    """Stop the monitoring task when the application shuts down"""
    if hasattr(app.state, 'monitor_task'):
        app.state.monitor_task.cancel()
        try:
            await app.state.monitor_task
        except asyncio.CancelledError:
            logging.info("Monitoring task cancelled successfully")
        except Exception as e:
            logging.error(f"Error while cancelling monitoring task: {str(e)}")

def track_resource_usage():
    """
        Function to tracking reasource usage CPU, Memory
    """
    try:
        process = psutil.Process()
        cpu = process.cpu_percent(interval=None)
        mem = process.memory_info().rss / 1024 / 1024

        cpu_usage.set(cpu)
        memory_usage.set(mem)
    except Exception as e:
        logging.error(f"Error tracking resource usage: {str(e)}")

async def monitor_loop():
    while True:
        try:
            await asyncio.get_event_loop().run_in_executor(None, track_resource_usage)
            await asyncio.sleep(10)  
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Error in monitor loop: {str(e)}")
            await asyncio.sleep(10) 

def get_metrics():
    """
        Function to get metrics from phrometheus
    """
    if 'inference_latency_seconds' not in REGISTRY._names_to_collectors:
        INFERENCE_LATENCY = Summary(
            "inference_latency_seconds",
            "Latency for inference requests",
            ["endpoint"]
        )
        
        # Request count metrics
        INFERENCE_COUNT = Counter(
            "inference_requests_total",
            "Total number of inference requests",
            ["endpoint", "status"]
        )
        
        # Error metrics
        INFERENCE_ERRORS = Counter(
            "inference_errors_total",
            "Total number of inference errors",
            ["endpoint", "error_type"]
        )
        
        # Processing time metrics
        PROCESSING_TIME = Summary(
            "image_processing_seconds",
            "Time spent processing images",
            ["operation"]
        )
        
        return INFERENCE_LATENCY, INFERENCE_COUNT, INFERENCE_ERRORS, PROCESSING_TIME
    return (
        REGISTRY._names_to_collectors['inference_latency_seconds'],
        REGISTRY._names_to_collectors['inference_requests_total'],
        REGISTRY._names_to_collectors['inference_errors_total'],
        REGISTRY._names_to_collectors['image_processing_seconds']
    )

def track_inference(endpoint: str):
    """Decorator to track inference metrics and expose endpoint parameters in Swagger
    
    Args:
        endpoint (str): The name of the endpoint being tracked
        
    This decorator:
    1. Tracks inference latency, request counts, and errors
    2. Exposes the original function's parameters in Swagger
    3. Maintains async compatibility
    """
    INFERENCE_LATENCY, INFERENCE_COUNT, INFERENCE_ERRORS, PROCESSING_TIME = get_metrics()
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                with INFERENCE_LATENCY.labels(endpoint=endpoint).time():
                    result = await func(*args, **kwargs)
                INFERENCE_COUNT.labels(endpoint=endpoint, status="success").inc()
                return result
            except Exception as e:
                INFERENCE_COUNT.labels(endpoint=endpoint, status="error").inc()
                INFERENCE_ERRORS.labels(endpoint=endpoint, error_type=type(e).__name__).inc()
                raise
            finally:
                duration = time.time() - start_time
                PROCESSING_TIME.labels(operation=endpoint).observe(duration)
        return wrapper
    return decorator


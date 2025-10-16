from pathlib import Path
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src.app.utils.log import configure_logging, get_logger

configure_logging(log_subdir="api")
logging = get_logger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Function to save log of API request

        Args:
            request: Request from client
            call_next: A function call_next that will receive the request as a parameter
        """
        client_ip = request.client.host
        method = request.method
        url = request.url.path

        response = await call_next(request)
        status_code = response.status_code

        logging.info(f"Response: {method} {url} returned {status_code} to {client_ip}")
        return response
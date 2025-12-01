import logging
import sys
from pathlib import Path
from typing import Literal
from src.app.settings.setting import DEBUG

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def configure_logging(log_subdir: Literal["gradio", "api"] = "gradio"):
    """
    Configure global logging with dynamic log subdirectory.

    Args:
        log_subdir: Folder under 'logs/' to store the log file (e.g., 'gradio', 'api').
    """
    log_dir = Path(__file__).parent.parent.parent / 'logs' / log_subdir
    log_file = log_dir / 'comfyui_api_client.log'
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(sys.stdout)]
    if DEBUG:
        handlers.insert(0, logging.FileHandler(log_file, encoding='utf-8'))
    
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.ERROR,
        format=LOG_FORMAT,
        handlers=handlers
    )
    
    for name in ['httpx', 'uvicorn', 'fastapi', '__main__', 'app']:
        logging.getLogger(name).setLevel(logging.DEBUG if DEBUG else logging.ERROR)

def get_logger(name: str) ->  logging.Logger:
    """
    Get a logger instance that respects the DEBUG setting.
    
    Args:
        name: The name of the logger
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    logger.setLevel(logging.DEBUG if DEBUG else logging.ERROR)
    return logger
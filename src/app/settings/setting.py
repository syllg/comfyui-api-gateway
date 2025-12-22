import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Get the directory where this settings file is located
SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(SETTINGS_DIR)
LIST_PROMPT = os.path.join(APP_DIR, "prompt", "prompt.json")
ANIME_TEMPLATE = os.path.join(APP_DIR, "template", "anime.json") 
SUPPORTED_IMAGE_EXTENSIONS: List[str] = ['.png', '.jpg', '.jpeg', '.webp']
BACKGROUND_REPLACEMENT_WORKFLOW = os.path.join(APP_DIR, "workflow", "background-replacement-v3.json")
BACKGROUND_REPLACEMENT_REMBG_WORKFLOW = os.path.join(APP_DIR, "workflow", "replace-background-rembg.json")
ANIME_STYLE_WORKFLOW = os.path.join(APP_DIR, "workflow", "anime.json")
FACE_SWAP_WORKFLOW = os.path.join(APP_DIR, "workflow", "face_swap_GIASS.json")
ANIME_STYLE_FACE_SWAP_MERGE_WORKFLOW = os.path.join(APP_DIR, "workflow", "face_swap_final_h0w2uyfhgdcyh.json")
FACE_SWAP_SINGLE_WORKFLOW = os.path.join(APP_DIR, "workflow", "face-swap-single.json")
MULTI_FACE_SWAP_WORKFLOW = os.path.join(APP_DIR, "workflow", "multi-faceswap-satu-input.json")
BACKGROUND_REPLACEMENT_MASK_WORKFLOW= os.path.join(APP_DIR, "workflow", "background_replacement_mask.json")
SNOWY_WORKFLOW = os.path.join(APP_DIR, "workflow", "qwen_image.json")
CHIBI_WORKFLOW = os.path.join(APP_DIR, "workflow", "chibi.json")
TARGET_SIZE = (1200, 1800)
DEBUG = False

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_QUEUE_KEY = "comfyui_job_queue"  # Redis list key for job queue

# AWS S3 configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
S3_ENABLED = os.getenv("S3_ENABLED", "false").lower() == "true"
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
S3_CUSTOM_DOMAIN=os.getenv("S3_CUSTOM_DOMAIN", "").strip()
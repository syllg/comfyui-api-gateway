import os
import uvicorn
import time
import uuid

import psutil
import logging
import subprocess
import json
from pathlib import Path
from urllib.parse import unquote

from typing import Optional, Dict, Any
import re
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator

from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Body, Depends, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from enum import Enum
import httpx

# Redis queue is used instead of in-memory counter

from src.app.schemas.schema import BackgroundRemovalRequest, BackgroundRemovalResponse, BackgroundReplacementRequest, BackgroundReplacementResponse, AnimeStyleRequest, AnimeStyleResponse, FaceSwapResponse, ListPromptRequest, ListPromptResponse, DeletePromptRequest, AnimeTemplateRequest, ListTemplateResponse, DeleteTemplateRequest, AnimeTemplateResponse, AnimeStyleFaceSwapResponse, StatusEnum, MultiFaceSwapResponse, FaceSwapSingleResponse, SnowyResponse, SnowyWebhookResponse
from src.app.utils.image_processing import validate_image_file, validate_image_type
from src.app.utils.file_handling import save_upload_file, save_result_image, get_file_url, UPLOAD_DIR, RESULT_DIR
from src.app.core.remove_background import get_model, BriaRMBG
from src.app.core.image_processing import process_image
from src.app.core.prompt import add_prompt_list, get_prompt_list, validate_prompt_format, delete_prompt_list
from src.app.core.template import get_anime_list, add_anime_list, validate_anime_format, delete_anime_list
from src.app.core.monitoring import start_monitor,stop_monitor,get_metrics, cpu_usage, memory_usage, track_inference, monitor_loop
from src.app.services.image_service import ImageService
from src.app.services.metrics_service import resource_usage, inference_test
from src.app.services.logging_middleware_service import LoggingMiddleware
from src.app.settings.setting import LIST_PROMPT
from src.app.settings.setting import ANIME_TEMPLATE
from src.app.settings.setting import S3_ENABLED
from src.app.utils.log import configure_logging, get_logger
from src.app.api.websockets_api import snowy as snowy_ws
from src.app.services.redis_queue import enqueue_job, get_queue_length
from src.app.services.s3_service import upload_file_to_s3

configure_logging(log_subdir="api")
logging = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
        Start monitoring when the app is running, if the app is shutdown will stop the monitoring
    """
    await start_monitor(app)
    try:
        yield
    finally:
        await stop_monitor(app)

app = FastAPI(
    title="ComfyUI API Client",
    description="API for ComfyUI",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
INSTRUMENTATOR_ENV_VAR = os.getenv("INSTRUMENTATOR_ENV_VAR", "ENABLE_INSTRUMENTATOR")
API_BASE_URL = os.getenv("API_BASE_URL")
app.mount("/images", StaticFiles(directory="images"), name="images")
INFERENCE_LATENCY, INFERENCE_COUNT, INFERENCE_ERRORS, PROCESSING_TIME = get_metrics()
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
    excluded_handlers=["/metrics"],
    env_var_name=INSTRUMENTATOR_ENV_VAR
)
# Instrument the app and expose metrics endpoint at /metrics
instrumentator.instrument(app).expose(app, include_in_schema=True, should_gzip=True)

# Dependency injection for ImageService
def get_image_service() -> ImageService:
    return ImageService()

app.add_middleware(LoggingMiddleware)

@app.get("/resource-usage",summary="Get current CPU, memory, GPU usage")
async def get_resource_usage():
    try:
        response_data = await resource_usage()
        return JSONResponse(content=response_data)
    except Exception as e:
        logging.error(f"Endpoint /resource-usage/ error: {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})


def process_snowy_and_callback(
    job_id: str,
    callback_url: str,
    image_path: str,
    transaction_image_id: str,
    p_prompt: Optional[str],
    n_prompt: Optional[str],
    random_seed: bool,
) -> Dict[str, Any]:
    """
    Process snowy generation and send webhook callback.
    This function is called by the Redis worker.
    
    Returns:
        Dict with job_id and status
    """
    # Normalize callback URL to avoid whitespace / invalid characters
    callback_url = (callback_url or "").strip()
    # Remove any non-printable ASCII characters inside the URL (e.g. stray tabs)
    cleaned_callback_url = re.sub(r"[\x00-\x1F\x7F]", "", callback_url)
    if cleaned_callback_url != callback_url:
        logging.warning(
            f"Sanitized callback_url for job_id={job_id} "
            f"(original contained control chars): {repr(callback_url)} -> {cleaned_callback_url}"
        )
    callback_url = cleaned_callback_url
    
    try:
        saved_paths = snowy_ws(
            image_path=image_path,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed,
        )

        image_path_result = None
        image_url = None
        
        if saved_paths and "60" in saved_paths and saved_paths["60"]:
            image_path_result = saved_paths["60"][0]
            
            # Upload to S3 if enabled
            if image_path_result and os.path.exists(image_path_result):
                # Use filename from API result path for S3 key
                filename = os.path.basename(image_path_result)
                s3_key = f"results/{filename}"
                
                file_ext = os.path.splitext(image_path_result)[1] or ".jpg"
                s3_url = upload_file_to_s3(
                    local_file_path=image_path_result,
                    s3_key=s3_key,
                    content_type="image/jpeg" if file_ext in [".jpg", ".jpeg"] else "image/png",
                )
                
                if s3_url:
                    image_url = s3_url
                    logging.info(f"Uploaded result image to S3: {s3_url}")

        # Build client-facing image_path:
        # - If using S3, strip domain and keep "results/<filename>"
        # - If not using S3, derive relative path from RESULT_DIR or fall back to "results/<basename>"
        client_image_path = None
        if image_url:
            # Example: https://storage-1.midory.id/results/output_xxx_60_0.jpg
            parsed = httpx.URL(image_url)
            url_path = parsed.path.lstrip("/")  # results/output_xxx_60_0.jpg
        elif image_path_result:
            # Local path -> make it relative to RESULT_DIR if possible
            try:
                rel_path = os.path.relpath(image_path_result, RESULT_DIR)
            except Exception:
                rel_path = os.path.basename(image_path_result)
            if rel_path.startswith("results/"):
                url_path = rel_path
            else:
                url_path = f"results/{os.path.basename(rel_path)}"
        else:
            url_path = None

        if url_path:
            # Keep full filename including node/index and extension
            client_image_path = url_path

        # Determine if S3 is being used
        # using_s3 can be: true, false, 1, 0, "1", "0", "true", "false"
        using_s3 = bool(image_url)  # Boolean format for JSON response (can be converted to other formats)
        logging.debug(
            f"S3 usage for job_id {job_id}: using_s3={using_s3}, "
            f"S3_ENABLED={S3_ENABLED}, image_url={'present' if image_url else 'none'}"
        )

        payload: Dict[str, Any] = {
            "job_id": job_id,
            "status": "success" if image_path_result else "error",
            "image_path": client_image_path or image_path_result,
            "transaction_image_id": transaction_image_id,
            "using_s3": using_s3,  # Boolean: true or false (JSON standard, convertible to other formats)
        }
    except Exception as e:
        # using_s3 can be: true, false, 1, 0, "1", "0", "true", "false"
        using_s3 = False  # Boolean format for JSON response (can be converted to other formats)
        logging.debug(f"S3 usage for job_id {job_id} (error): using_s3={using_s3}")
        payload = {
            "job_id": job_id,
            "status": "error",
            "detail": str(e),
            "transaction_image_id": transaction_image_id,
            "using_s3": using_s3,  # Boolean: false (JSON standard, convertible to other formats)
        }
    finally:
        # Clean up uploaded file
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception:
            pass

    try:
        with httpx.Client(timeout=45.0) as client:
            logging.info(f"Sending webhook callback for job_id: {job_id} to {callback_url} with payload: {payload}")
            response = client.post(callback_url, json=payload)
            
            # Log response details before raising
            try:
                response_body = response.text
                logging.debug(f"Callback response status: {response.status_code}, body: {response_body}")
            except Exception:
                pass
            
            response.raise_for_status()
            logging.info(f"Successfully sent webhook callback for job_id: {job_id} to {callback_url}")
    except httpx.HTTPStatusError as e:
        # Extract response body for better error logging
        response_body = ""
        try:
            response_body = e.response.text
        except Exception:
            pass
        logging.error(
            f"Failed to POST snowy result to callback_url={callback_url} for job_id={job_id}: "
            f"HTTP {e.response.status_code} - {response_body}. "
            f"Payload sent: {payload}",
            exc_info=True
        )
    except Exception as e:
        logging.error(
            f"Failed to POST snowy result to callback_url={callback_url} for job_id={job_id}: {e}. "
            f"Payload sent: {payload}",
            exc_info=True
        )
    
    return payload

@app.get("/infer-test")
@track_inference("infer_test")
async def infer():
    try:
        response_data = await inference_test()
        return response_data
    except Exception as e:
        logging.error(f"Endpoint /infer-test/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/remove-background/", response_model=BackgroundRemovalResponse)
@track_inference("remove_background")
async def remove_background(
    file: UploadFile = File(..., description="The image file to process"),
    params: Optional[BackgroundRemovalRequest] = Depends(BackgroundRemovalRequest),
    image_service: ImageService = Depends(get_image_service)
):  
    """
        Remove the background from an uploaded image.
        This endpoint processes the image and returns:
        - The processed image with background removed
        - Optional mask and original image URLs
        
        Performance metrics are tracked for:
        - Response time
        - Request count
        - Error rates
    """
    logging.info(f"Processing background removal request for file: {file.filename}")
    logging.debug(f"Request parameters: return_mask={params.return_mask}, return_original={params.return_original}")
    
    try:
        return await image_service.remove_background(
            file=file,
            return_mask=params.return_mask,
            return_original=params.return_original,
        )
        logging.info(f"Background removal completed successfully for {file.filename}")
    except Exception as e:
        logging.error(f"Background removal failed for {file.filename}", exc_info=True)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        ) from e

@app.post("/replace-background/", response_model=BackgroundReplacementResponse)
@track_inference("replace_background")
async def replace_background(
    file: UploadFile = File(..., description="The image file to process"),
    p_prompt: Optional[str] = Form(None, description="Positive prompt for image generation"),
    n_prompt: Optional[str] = Form(None, description="Negative prompt to avoid certain elements"),
    random_seed: Optional[bool] = Form(False, description="Whether to use random seed for generation"),
    image_service: ImageService = Depends(get_image_service)
):
    """
    Replace the background of an uploaded image using AI.
    
    This endpoint processes the image and returns:
    - The processed image with new background
    - Generation parameters used
    
    Performance metrics are tracked for:
    - Response time
    - Request count
    - Error rates
    """
    try:
        return await image_service.replace_background(
            file=file,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error("Background replacement failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        ) from e

@app.post("/anime-style/", response_model=AnimeStyleResponse)
async def anime_style_api(
    file: UploadFile = File(..., description="Main image file"),
    random_seed: Optional[bool] = Form(False),
    random_seed_2: Optional[bool] = Form(False),
    p_prompt: str = Form("preserve original colors, same color palette as input image, detailed, anime style"),
    n_prompt: str = Form("nude, bad quality, ugly, distorted, low quality, blurry"),
    denoise: Optional[float] = Form(0.45, ge=0.0, le=1.0, description="Denoising strength for the image generation"),
    image_service: ImageService = Depends(get_image_service)
):
    """
    Apply anime-style rendering to an image.
    This endpoint processes the image and returns:
    - The processed image in anime style
    - Generation parameters used
    """
    try:
        return await image_service.anime_style(
            file=file,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed,
            random_seed_2=random_seed_2,
            denoise=denoise
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error("Anime style application failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@app.post("/face-swap/", response_model=FaceSwapResponse)
async def face_swap_api(
    target: UploadFile = File(..., description="The target image file to process"),
    source: UploadFile = File(..., description="The source image file with the anime styled image to use"),
    p_prompt: str = Form("", description="Positive prompt for face swap"),
    n_prompt: Optional[str]  = Form("blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill", description="Negative prompt for face swap"),
    random_seed: Optional[bool] = Form(False, description="Whether to use random seed for generation"),
    denoise1: Optional[float] = Form(0.65, description="Denoising strength for the first stage"),
    denoise2: Optional[float] = Form(0.65, description="Denoising strength for the second stage"),
    image_service: ImageService = Depends(get_image_service)
):
    try:
        return await image_service.face_swap(
            target_file=target,
            source_file=source,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed,
            denoise1=denoise1,
            denoise2=denoise2
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    
@app.post("/anime-style-face-swap-merge-workflow/", response_model=AnimeStyleFaceSwapResponse)
async def anime_style_face_swap_merge_api(
    target: UploadFile = File(..., description="The target image file to process"),
    source: UploadFile = File(..., description="The source image (real face) file to be anime-styled and used for face swap"),
    anime_random_seed: Optional[bool] = Form(False),
    anime_random_seed_2: Optional[bool] = Form(False),
    anime_p_prompt: str = Form(None),
    anime_denoise: Optional[float] = Form(0.45, ge=0.0, le=1.0),
    face_p_prompt: Optional[str] = Form(None),
    face_n_prompt: Optional[str] = Form(None),
    face_random_seed: Optional[bool] = Form(False),
    face_denoise1: Optional[float] = Form(0.65),
    face_denoise2: Optional[float] = Form(0.65),
    image_service: ImageService = Depends(get_image_service)
):
    """
    Apply anime style to the source image and merge it with face swap in a single optimized workflow.
    This endpoint combines anime styling and face swapping in one pass, which is more efficient than
    doing them sequentially.
    """
    try:
        result = await image_service.anime_style_face_swap_merge(
            target_file=target,
            source_file=source,
            anime_random_seed=anime_random_seed,
            anime_random_seed_2=anime_random_seed_2,
            anime_p_prompt=anime_p_prompt,
            anime_denoise=anime_denoise,
            face_p_prompt=face_p_prompt,
            face_n_prompt=face_n_prompt,
            face_random_seed=face_random_seed,
            face_denoise1=face_denoise1,
            face_denoise2=face_denoise2
        )
        return AnimeStyleFaceSwapResponse(status=StatusEnum.SUCCESS, image=result["image"])
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.post("/anime-style-face-swap/", response_model=AnimeStyleFaceSwapResponse)
async def anime_style_face_swap_api(
    target: UploadFile = File(..., description="The target image file to process"),
    source: UploadFile = File(..., description="The source image (real face) file to be anime-styled and used for face swap"),
    anime_random_seed: Optional[bool] = Form(False),
    anime_random_seed_2: Optional[bool] = Form(False),
    anime_p_prompt: Optional[str] = Form(None),
    anime_n_prompt: Optional[str] = Form(None),
    anime_denoise: Optional[float] = Form(0.45, ge=0.0, le=1.0),
    face_p_prompt: Optional[str] = Form(None),
    face_n_prompt: Optional[str] = Form(None),
    face_denoise1: Optional[float] = Form(0.65),
    face_denoise2: Optional[float] = Form(0.65),
    image_service: ImageService = Depends(get_image_service)
):
    """Apply anime style to the source image, then use the result as the source for face swap with the target image."""
    try:
        result = await image_service.anime_style_face_swap(
            target_file=target,
            source_file=source,
            anime_random_seed=anime_random_seed,
            anime_random_seed_2=anime_random_seed_2,
            anime_p_prompt=anime_p_prompt,
            anime_n_prompt=anime_n_prompt,
            anime_denoise=anime_denoise,
            face_p_prompt=face_p_prompt,
            face_n_prompt=face_n_prompt,
            face_denoise1=face_denoise1,
            face_denoise2=face_denoise2
        )
        return AnimeStyleFaceSwapResponse(status=StatusEnum.SUCCESS, image=result["image"])
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.post("/face-swap-single/", response_model=FaceSwapSingleResponse)
async def face_swap_single_api(
    target: UploadFile = File(..., description="The target image file to process"),
    source: UploadFile = File(..., description="The source image (real face) file for face swap"),
    image_service: ImageService = Depends(get_image_service)
):
    """Apply anime style to the source image, then use the result as the source for face swap with the target image."""
    try:
        result = await image_service.face_swap_single(
            target_file=target,
            source_file=source,
        )
        return FaceSwapSingleResponse(status=StatusEnum.SUCCESS, image=result["image"])
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.post("/multi-face-swap/", response_model=MultiFaceSwapResponse)
async def multi_face_swap_api(
    target: UploadFile = File(..., description="The target image file to process"),
    source: UploadFile = File(..., description="The source image (real face) file for face swap"),
    denoise: Optional[float] = Form(0.55, ge=0.0, le=1.0),
    total_face: Optional[int] = Form(1, ge=1, le=10),
    image_service: ImageService = Depends(get_image_service)
):
    """Apply anime style to the source image, then use the result as the source for face swap with the target image."""
    try:
        result = await image_service.multi_face_swap(
            target_file=target,
            source_file=source,
            denoise=denoise,
            total_face=total_face
        )
        return MultiFaceSwapResponse(status=StatusEnum.SUCCESS, image=result["image"])
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.post("/replace-background-mask/", response_model=BackgroundReplacementResponse)
@track_inference("replace_background_mask")
async def replace_background(
    file: UploadFile = File(..., description="The image file to process"),
    p_prompt: Optional[str] = Form(None, description="Positive prompt for image generation"),
    n_prompt: Optional[str] = Form(None, description="Negative prompt to avoid certain elements"),
    random_seed: Optional[bool] = Form(False, description="Whether to use random seed for generation"),
    image_service: ImageService = Depends(get_image_service)
):
    """
    Replace the background of an uploaded image using AI with mask from src/app/mask folder.
    
    This endpoint processes the image and returns:
    - The processed image with new background
    - Generation parameters used
    
    Performance metrics are tracked for:
    - Response time
    - Request count
    - Error rates
    """
    try:
        return await image_service.replace_background_mask(
            file=file,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error("Background replacement failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        ) from e

@app.post("/snowy/", response_model=SnowyResponse)
async def snowy_api(
    file: UploadFile = File(..., description="The image file to process"),
    p_prompt: Optional[str] = Form(None, description="Positive prompt for image generation"),
    n_prompt: Optional[str] = Form(None, description="Negative prompt to avoid certain elements"),
    random_seed: Optional[bool] = Form(False, description="Whether to use random seed for generation"),
    transaction_image_id: str = Form(..., description="Transaction image ID for tracking the request"),
    image_service: ImageService = Depends(get_image_service)
):
    """
    Generate a snowy image using AI.
    This endpoint processes the image and returns:
    - The processed image with snowy background
    - Generation parameters used
    - Transaction image ID for tracking
    """
    try:
        return await image_service.snowy(
            file=file,
            transaction_image_id=transaction_image_id,
            p_prompt=p_prompt,
            n_prompt=n_prompt,
            random_seed=random_seed
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error("Snowy generation failed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        ) from e


@app.post("/snowy/webhook-style/", response_model=SnowyWebhookResponse)
async def snowy_webhook_style(
    file: UploadFile = File(..., description="The image file to process"),
    callback_url: str = Form(..., description="Difotoin server webhook URL"),
    transaction_image_id: str = Form(..., description="Transaction image ID for tracking the request"),
    p_prompt: Optional[str] = Form(None, description="Positive prompt for image generation"),
    n_prompt: Optional[str] = Form(None, description="Negative prompt to avoid certain elements"),
    random_seed: Optional[bool] = Form(False, description="Whether to use random seed for generation"),
):
    """
    Snowy generation in webhook style:
    - Camera box calls this endpoint with image + callback_url.
    - FastAPI immediately returns job_id and adds job to Redis queue.
    - Worker process picks up job from Redis queue and processes it.
    - When done, worker POSTs result to callback_url.
    
    Returns:
        - job_id: Unique identifier for tracking the job
        - status: "queued" indicating the job has been added to the queue
    """
    file_extension = os.path.splitext(file.filename)[1].lower() or ".jpg"
    upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{file_extension}")

    contents = await file.read()
    with open(upload_filename, "wb") as buffer:
        buffer.write(contents)

    job_id = str(uuid.uuid4())

    # Add job to Redis queue
    job_data = {
        "job_id": job_id,
        "callback_url": callback_url,
        "image_path": upload_filename,
        "transaction_image_id": transaction_image_id,
        "p_prompt": p_prompt,
        "n_prompt": n_prompt,
        "random_seed": bool(random_seed),
    }
    
    try:
        enqueue_job(job_data)
        queue_remaining = get_queue_length()
        logging.info(f"Job {job_id} queued to Redis. Queue remaining: {queue_remaining}")
    except Exception as e:
        # Clean up file if queueing fails
        try:
            if os.path.exists(upload_filename):
                os.remove(upload_filename)
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue job: {str(e)}"
        )

    return {"job_id": job_id, "status": "queued"}

@app.post("/test-webhook-receiver")
async def test_webhook_receiver(payload: dict):
    logging.info("TEST WEBHOOK RECEIVED: %s", payload)
    return {"ok": True}

@app.get("/queue-info/")
async def queue_info():
    """
    Get Redis queue information.
    
    Returns the count of pending jobs in the Redis queue,
    not the ComfyUI queue. This tracks jobs queued via webhook-style endpoints.
    
    Returns: {"exec_info": {"queue_remaining": <count>}}
    """
    try:
        queue_remaining = get_queue_length()
        return {"exec_info": {"queue_remaining": queue_remaining}}
    except Exception as e:
        logging.error(f"Failed to get queue info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get queue information: {str(e)}"
        )

@app.get("/results/{filename}")
async def get_result_image(filename: str):
    """Serve processed result image files."""
    file_path = os.path.join(RESULT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(file_path, media_type="image/jpeg")

class GenderEnum(str, Enum):
    all = "-"
    man = "man"
    woman = "woman"

@app.get("/anime-template/{gender}", response_model=AnimeTemplateResponse)
async def get_list_anime(
    request: Request,
    gender: GenderEnum
):
    try:
        anime_dict = get_anime_list(ANIME_TEMPLATE)
        
        # Filter by gender if not 'all'
        if gender != GenderEnum.all:
            anime_dict = {
                key: value for key, value in anime_dict.items()
                if isinstance(value, dict) and value.get("gender") == gender
            }
            
        # Build dynamic image URLs
        for key, value in anime_dict.items():
            if isinstance(value, dict) and "image_filename" in value:
                filename = value["image_filename"].strip()
                item_gender = value.get("gender", "")
                value["image_url"] = str(request.base_url) + f"images/{item_gender}/{filename}"
                
        return AnimeTemplateResponse(
            status=StatusEnum.SUCCESS,
            list_anime=anime_dict
        )
    except Exception as e:
        logging.error(f"Endpoint GET /anime-template/{{gender}} error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/anime-template/", response_model=AnimeTemplateResponse)
async def update_anime_template(new_anime: AnimeTemplateRequest = Body(...)):
    try:
        # Validate anime format
        if not validate_anime_format(new_anime.list_anime):
            raise HTTPException(
                status_code=400,
                detail="Invalid. Each value must be a dict with non-empty 'image_filename' fields."
            )
        updated_anime = add_anime_list(ANIME_TEMPLATE, new_anime.list_anime)
        return AnimeTemplateResponse(
            status=StatusEnum.SUCCESS,
            list_anime=updated_anime
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Endpoint POST /anime-template/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/anime-template/")
async def delete_anime(delete_request: DeleteTemplateRequest = Body(...)):
    try:
        # Validate that anime_keys is not empty
        if not delete_request.anime_keys:
            raise HTTPException(
                status_code=400,
                detail="anime_keys list cannot be empty."
            )
        
        updated_anime = delete_anime_list(ANIME_TEMPLATE, delete_request.anime_keys)
        return AnimeTemplateResponse(
            status=StatusEnum.SUCCESS,
            list_anime=updated_anime
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Endpoint DELETE /anime-template/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/list-prompt/", response_model=ListPromptResponse)
async def get_list_prompt(request: Request):
    try:
        prompt_dict = get_prompt_list(LIST_PROMPT)
        # Build dynamic image URLs
        for key, value in prompt_dict.items():
            if isinstance(value, dict) and "image_filename" in value:
                filename = value["image_filename"].strip()
                # Remove any leading/trailing spaces from filename
                value["image_url"] = str(request.base_url) + f"images/{filename}"
        return ListPromptResponse(
            status="success",
            list_prompt=prompt_dict
        )
    except Exception as e:
        logging.error(f"Endpoint GET /list-prompt/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/list-prompt/", response_model=ListPromptResponse)
async def update_list_prompt(new_prompt: ListPromptRequest = Body(...)):
    try:
        # Validate prompt format
        if not validate_prompt_format(new_prompt.list_prompt):
            raise HTTPException(
                status_code=400,
                detail="Invalid prompt format. Each value must be a dict with non-empty 'prompt' and 'image_filename' fields."
            )
        updated_prompts = add_prompt_list(LIST_PROMPT, new_prompt.list_prompt)
        return ListPromptResponse(
            status="success",
            list_prompt=updated_prompts
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Endpoint POST /list-prompt/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.delete("/list-prompt/")
async def delete_prompts(delete_request: DeletePromptRequest = Body(...)):
    try:
        # Validate that prompt_keys is not empty
        if not delete_request.prompt_keys:
            raise HTTPException(
                status_code=400,
                detail="prompt_keys list cannot be empty."
            )
        
        updated_prompts = delete_prompt_list(LIST_PROMPT, delete_request.prompt_keys)
        return ListPromptResponse(
            status="success",
            list_prompt=updated_prompts
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Endpoint DELETE /list-prompt/ error {str(e)}", exc_info=True)
        logging.error(f"Caused by: {e.__cause__}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/")
async def root():
    logging.info("Root endpoint accessed")
    return {
        "name": "ComfyUI API Client",
        "version": "2.0.0",
        "endpoints": {
            "/remove-background/": "POST - Remove background from images",
            "/replace-background/": "POST - Replace image background",
            "/anime-style/": "POST - Apply anime style with background",
            "/results/{filename}": "GET - Serve result image",
            "/docs": "Swagger UI",
            "/redoc": "ReDoc UI"
        }
    }

app.description = """
This API provides endpoints for image processing including background removal, replacement, and style transfer.

## Performance Metrics

The following metrics are available at `/metrics`:

- `inference_latency_seconds`: Latency for inference requests per endpoint
- `inference_requests_total`: Total number of inference requests per endpoint and status
- `inference_errors_total`: Total number of inference errors per endpoint and error type
- `image_processing_seconds`: Time spent processing images per operation

## Available Endpoints

- `/remove-background/`: Remove background from images
- `/replace-background/`: Replace image background with AI-generated content
- `/anime-style/`: Apply anime-style rendering to images
- `/hair-style/`: Apply hair style changes to images
- `/list-prompt/`: Manage prompt list (GET: retrieve, POST: add, DELETE: remove)
- `/results/{filename}`: Retrieve processed images
- `/metrics`: View performance metrics
- `/resource-usage`: View CPU, GPU, Memory Usage
- `/infer-test`: Inference testing
- `/`: Root API

"""

def main():
    uvicorn.run("src.app.api.api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()

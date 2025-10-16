import os
import uuid
import shutil
from fastapi import UploadFile
from typing import Optional, Tuple
import aiofiles
# Get the workspace root directory (3 levels up from this file)
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# Create uploads and results directories if they don't exist
UPLOAD_DIR = os.path.join(WORKSPACE_ROOT, "uploads")
RESULT_DIR = os.path.join(WORKSPACE_ROOT, "results")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)


async def save_upload_file(file: UploadFile) -> Tuple[str, str]:
    """
    Asynchronously save an uploaded file with a unique filename and return the saved path and unique filename.
    """
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    async with aiofiles.open(file_path, "wb") as buffer:
        while content := await file.read(1024 * 1024):
            await buffer.write(content)
    return file_path, unique_filename

def save_result_image(image_data, filename: Optional[str] = None, original_filename: Optional[str] = None) -> str:
    """
    Save a result image (PIL Image or bytes) and return the path
    
    Args:
        image_data: PIL Image or bytes data to save
        filename: Optional specific filename to use
        original_filename: Optional original uploaded filename to base the output name on
    """
    if filename is None:
        if original_filename:
            # Get the base name and extension from original filename
            base_name = os.path.splitext(os.path.basename(original_filename))[0]
            # Always use .png extension for RGBA images
            ext = '.png' if hasattr(image_data, 'mode') and image_data.mode == 'RGBA' else (os.path.splitext(original_filename)[1] or '.png')
            filename = f"output_{base_name}{ext}"
        else:
            filename = f"output_{uuid.uuid4().hex}.png"
    
    file_path = os.path.join(RESULT_DIR, filename)
    
    # If image_data is a PIL Image
    if hasattr(image_data, 'save'):
        # For RGBA images, always save as PNG
        if image_data.mode == 'RGBA':
            image_data.save(file_path, format='PNG')
        else:
            image_data.save(file_path)
    # If image_data is bytes
    else:
        with open(file_path, "wb") as f:
            f.write(image_data)
    
    return file_path

def get_file_url(file_path: str) -> str:
    """
    Get just the filename with results/ prefix
    Example: /path/to/results/image.png -> results/image.png
    """
    filename = os.path.basename(file_path)
    return f"results/{filename}"
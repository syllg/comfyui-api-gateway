import torch
import numpy as np
import os
import io
from torchvision.transforms.functional import normalize
from PIL import Image
from typing import Tuple, List
from fastapi import UploadFile, HTTPException
from src.app.settings.setting import SUPPORTED_IMAGE_EXTENSIONS, TARGET_SIZE


try:
    from src.app.settings.setting import SUPPORTED_IMAGE_EXTENSIONS, TARGET_SIZE
except ImportError:
    # Fallback for direct execution
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(current_dir)
    settings_dir = os.path.join(app_dir, 'settings')
    sys.path.append(settings_dir)
    

def resize_image(image: Image.Image, target_size: TARGET_SIZE) -> Image.Image:
    """
    Resize an image to the target size
    """
    image = image.convert('RGB')
    image = image.resize(target_size, Image.BILINEAR)
    return image

def pil_to_tensor(image: Image.Image) -> torch.Tensor:
    """
    Convert a PIL image to a normalized torch tensor
    """
    im_np = np.array(image)
    im_tensor = torch.tensor(im_np, dtype=torch.float32).permute(2, 0, 1)
    im_tensor = torch.unsqueeze(im_tensor, 0)
    im_tensor = torch.divide(im_tensor, 255.0)
    im_tensor = normalize(im_tensor, [0.5, 0.5, 0.5], [1.0, 1.0, 1.0])
    return im_tensor

def tensor_to_pil(tensor: torch.Tensor) -> Image.Image:
    """
    Convert a torch tensor to a PIL image
    """
    # Ensure the tensor is on CPU
    tensor = tensor.cpu()
    
    # Convert to numpy array
    if tensor.dim() == 4:
        tensor = tensor.squeeze(0)
    
    if tensor.dim() == 3:
        # If tensor has 3 dimensions (C, H, W), convert to (H, W, C)
        tensor = tensor.permute(1, 2, 0)
    
    # Convert to uint8
    array = (tensor * 255).numpy().astype(np.uint8)
    
    # Create PIL image
    return Image.fromarray(array)

def create_transparent_image(image: Image.Image, mask: Image.Image) -> Image.Image:
    """
    Create a transparent image using the original image and a mask
    """
    # Ensure the mask is grayscale
    if mask.mode != 'L':
        mask = mask.convert('L')
    
    # Create a new RGBA image
    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    
    # Convert the original image to RGBA if it's not already
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Paste the original image using the mask
    result.paste(image, mask=mask)
    
    return result

def overlay_image(foreground: Image.Image, background: Image.Image, resize_foreground: bool = True) -> Image.Image:
    """
    Overlay a foreground image (with transparency) onto a background image
    """
    # Ensure the foreground is RGBA
    if foreground.mode != 'RGBA':
        foreground = foreground.convert('RGBA')
    
    # Ensure the background is RGB or RGBA
    if background.mode not in ['RGB', 'RGBA']:
        background = background.convert('RGB')
    
    # Resize foreground to match background if needed
    if resize_foreground and foreground.size != background.size:
        foreground = foreground.resize(background.size, Image.LANCZOS)
    
    # Create a new image with the same size as the background
    result = background.copy()
    
    # Paste the foreground onto the background
    result.paste(foreground, (0, 0), foreground)
    
    return result

def validate_image_file(file: UploadFile) -> None:
    """Validate the uploaded file is an image."""
    if not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="File must be an image"
        )
    
    # Check file size (e.g., max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    file_size = 0
    for chunk in file.file:
        file_size += len(chunk)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds maximum limit of 10MB"
            )
    file.file.seek(0)  # Reset file pointer at the start

def validate_image_type(file: UploadFile) -> str:
    """Validate the uploaded file type and return the file extension.
    
    Args:
        file (UploadFile): The uploaded file to validate
        
    Returns:
        str: The validated file extension (including the dot)
        
    Raises:
        HTTPException: If the file type is not supported
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file provided"
        )
        
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in SUPPORTED_IMAGE_EXTENSIONS:
        supported_types = ', '.join(ext.replace('.', '') for ext in SUPPORTED_IMAGE_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported types are: {supported_types}"
        )
        
    return file_extension


def get_image_size_mb(image_data):
    """Get image size in MB"""
    if isinstance(image_data, bytes):
        return len(image_data) / (1024 * 1024)
    elif hasattr(image_data, 'size') and isinstance(image_data, Image.Image):
        width, height = image_data.size
        # Calculate bytes based on image mode
        if image_data.mode == 'RGB':
            bytes_per_pixel = 3
        elif image_data.mode == 'RGBA':
            bytes_per_pixel = 4
        elif image_data.mode == 'L':
            bytes_per_pixel = 1
        else:
            bytes_per_pixel = 3  # Default fallback
        
        total_bytes = width * height * bytes_per_pixel
        return total_bytes / (1024 * 1024)
    elif hasattr(image_data, 'tell') and hasattr(image_data, 'seek'):
        # For file-like objects
        current_pos = image_data.tell()
        image_data.seek(0, 2)  # Seek to end
        size = image_data.tell()
        image_data.seek(current_pos)  # Restore position
        return size / (1024 * 1024)
    else:
        return 0

def compress_image_for_processing(image: Image.Image, max_file_size_mb: float = 5.0, max_dimension: int = 1200) -> Tuple[Image.Image, dict]:
    """
    Compress image for processing without significant quality loss
    
    Args:
        image: PIL Image object
        max_file_size_mb: Maximum file size in MB
        max_dimension: Maximum width or height dimension
    
    Returns:
        Tuple of (compressed_image, compression_info)
    """
    original_size = image.size
    original_mode = image.mode

    # Jangan kompres jika gambar sudah kecil (agar deteksi wajah tidak gagal)
    if min(image.size) < 512:
        compression_info = {
            'original_size': original_size,
            'compressed_size': image.size,
            'original_mode': original_mode,
            'final_mode': image.mode,
            'quality_used': None,
            'size_mb': get_image_size_mb(image),
            'compression_ratio': '0% (skipped)'
        }
        return image, compression_info

    # Convert to RGB if necessary
    if image.mode in ('RGBA', 'LA', 'P'):
        # Create white background for transparent images
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Resize if dimensions are too large (jaga aspect ratio)
    width, height = image.size
    if max(width, height) > max_dimension:
        ratio = max_dimension / max(width, height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Check file size by saving to bytes
    quality = 95
    while quality > 60:
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=quality, optimize=True)
        size_mb = len(buffer.getvalue()) / (1024 * 1024)
        
        if size_mb <= max_file_size_mb:
            break
        quality -= 5
    
    # Final compression info
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=quality, optimize=True)
    final_size_mb = len(buffer.getvalue()) / (1024 * 1024)
    
    compression_info = {
        'original_size': original_size,
        'compressed_size': image.size,
        'original_mode': original_mode,
        'final_mode': 'RGB',
        'quality_used': quality,
        'size_mb': final_size_mb,
        'compression_ratio': f"{(1 - final_size_mb / max(get_image_size_mb(buffer.getvalue()), 0.001)) * 100:.1f}%"
    }
    return image, compression_info
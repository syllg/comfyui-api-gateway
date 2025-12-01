import os
import asyncio
import uuid
import datetime
import logging
from datetime import datetime
from zoneinfo import ZoneInfo 
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image
from fastapi import HTTPException, UploadFile
import io

from src.app.core.remove_background import get_model, BriaRMBG
from src.app.core.image_processing import process_image
from src.app.api.websockets_api import background_replacement, anime_style, background_replacement_rembg, face_swap, snowy
from src.app.api.websockets_api import face_swap_single 
from src.app.api.websockets_api import multi_face_swap
from src.app.api.websockets_api import background_replacement_masking
from src.app.utils.image_processing import validate_image_file
from src.app.utils.file_handling import save_upload_file, save_result_image, get_file_url, UPLOAD_DIR, RESULT_DIR
from src.app.utils.image_processing import compress_image_for_processing
from src.app.settings.setting import SUPPORTED_IMAGE_EXTENSIONS
from src.app.utils.log import configure_logging, get_logger
from src.app.api.websockets_api import anime_style_face_swap_merge
configure_logging(log_subdir="api")
logger = get_logger(__name__)

class ImageValidationError(Exception):
    """Custom exception for image validation errors."""
    pass

class ImageService:
    # Constants for validation
    MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
    MIN_IMAGE_DIMENSION = 64  # pixels
    MAX_IMAGE_DIMENSION = 4096  # pixels
    SUPPORTED_CONTENT_TYPES = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp'
    }

    def __init__(self):
        self.model = get_model()

    async def validate_image(
        self,
        file: UploadFile,
        check_dimensions: bool = True,
        check_content_type: bool = True
    ) -> str:
        """Validate an uploaded image file.
        
        Args:
            file: The uploaded file to validate
            check_dimensions: Whether to validate image dimensions
            check_content_type: Whether to validate content type
            
        Returns:
            str: The validated file extension (including the dot)
            
        Raises:
            ImageValidationError: If validation fails
            HTTPException: If file is invalid
        """
        try:
            # Basic file validation
            if not file or not file.filename:
                raise ImageValidationError("No file provided")

            # Validate file extension (case-insensitive)
            file_extension = os.path.splitext(file.filename)[1].lower()
            if file_extension not in SUPPORTED_IMAGE_EXTENSIONS:
                supported_types = ', '.join(ext.replace('.', '') for ext in SUPPORTED_IMAGE_EXTENSIONS)
                raise ImageValidationError(f"Unsupported file type. Supported types are: {supported_types}")

            # Validate content type if requested
            if check_content_type:
                expected_content_type = self.SUPPORTED_CONTENT_TYPES.get(file_extension)
                # Accept any image/* content type for supported extensions
                if not file.content_type or not file.content_type.startswith('image/'):
                    raise ImageValidationError(
                        f"Invalid content type. Expected an image content type for {file_extension} files, got {file.content_type}"
                    )

            # Validate file size
            file_size = 0
            for chunk in file.file:
                file_size += len(chunk)
                if file_size > self.MAX_IMAGE_SIZE:
                    raise ImageValidationError(f"File size exceeds maximum limit of {self.MAX_IMAGE_SIZE // (1024*1024)}MB")
            file.file.seek(0)

            # Validate image dimensions if requested
            if check_dimensions:
                try:
                    with Image.open(file.file) as img:
                        width, height = img.size
                        if width < self.MIN_IMAGE_DIMENSION or height < self.MIN_IMAGE_DIMENSION:
                            raise ImageValidationError(
                                f"Image dimensions too small. Minimum size is {self.MIN_IMAGE_DIMENSION}x{self.MIN_IMAGE_DIMENSION} pixels"
                            )
                        # Instead of rejecting large images, we'll resize them
                        if width > self.MAX_IMAGE_DIMENSION or height > self.MAX_IMAGE_DIMENSION:
                            # Calculate new dimensions while maintaining aspect ratio
                            ratio = min(self.MAX_IMAGE_DIMENSION / width, self.MAX_IMAGE_DIMENSION / height)
                            new_width = int(width * ratio)
                            new_height = int(height * ratio)
                            
                            img = img.resize((new_width, new_height), Image.LANCZOS)
                            
                            file.file.seek(0)
                            img.save(file.file, format=img.format or 'JPEG')
                            file.file.seek(0)
                            
                            print(f"Image resized from {width}x{height} to {new_width}x{new_height} pixels")
                except Exception as e:
                    raise ImageValidationError(f"Failed to validate image dimensions: {str(e)}")
                finally:
                    file.file.seek(0)  # Reset file pointer

            return file_extension

        except ImageValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error validating image: {str(e)}")

    async def remove_background(
        self,
        file: UploadFile,
        return_mask: bool = False,
        return_original: bool = False
    ) -> Dict[str, Any]:
        """Remove background from an image."""
        try:
            # Validate image
            await self.validate_image(file)
            
            file_path, filename = await save_upload_file(file)
            
            try:
                with Image.open(file_path) as orig_image:
                    result_image = process_image(orig_image, self.model)
                
                result_filename = os.path.splitext(file.filename)[0] + '.png'
                result_path = save_result_image(result_image, original_filename=result_filename)
                result_url = get_file_url(result_path)
                
                response = {
                    "result_url": result_url,
                    "message": "Background removed successfully"
                }
                
                if return_mask and result_image.mode == 'RGBA':
                    mask = result_image.split()[3]
                    mask_path = save_result_image(mask, f"mask_{os.path.basename(result_path)}", original_filename=result_filename)
                    response["mask_url"] = get_file_url(mask_path)
                
                if return_original:
                    response["original_url"] = get_file_url(file_path)
                
                return response
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")
            finally:
                self._cleanup_file(file_path)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    async def replace_background(
        self,
        file: UploadFile,
        p_prompt: Optional[str] = None,
        n_prompt: Optional[str] = None,
        random_seed: bool = False
    ) -> Dict[str, str]:
        """Replace background of an image."""
        upload_filename = ""
        image_without_bg = ""
        bg_removed_path = ""
        try:
            logger.info("Starting background replacement process for file: %s", file.filename)
            # Validate image
            await self.validate_image(file)
            logger.info("Image validated: %s", file.filename)
            
            file_extension = os.path.splitext(file.filename)[1].lower()
            upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{file_extension}")
            
            with open(upload_filename, "wb") as buffer:
                buffer.write(await file.read())
            logger.info("File saved to: %s", upload_filename)
            # First we remove the background
            with Image.open(upload_filename) as img:
                image_without_bg = process_image(img, self.model)
            logger.info("Background removed for file: %s", upload_filename)
            # Save the image_without_bg to a temp file
            bg_removed_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.png")
            image_without_bg.save(bg_removed_path, format="PNG")
            logger.info("Background-removed image saved to: %s", bg_removed_path)
            # Then we replace the background
            saved_paths = background_replacement(
                image_path=bg_removed_path,
                p_prompt=p_prompt,
                n_prompt=n_prompt,
                random_seed=random_seed
            )
            logger.info("Background replacement completed for: %s", bg_removed_path)
            
            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Convert paths to URLs and rename files with original filename as base
            urls = []
            first_url = None
            for node_id, paths in saved_paths.items():
                for idx, path in enumerate(paths):
                    if os.path.exists(path):
                        # Create a new filename based on the original
                        new_filename = f"bg_replaced_{os.path.splitext(file.filename)[0]}_{idx}.jpg"
                        new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        # If the new path already exists, add a unique identifier
                        if os.path.exists(new_path):
                            base, ext = os.path.splitext(new_filename)
                            new_filename = f"{base}_{str(uuid.uuid4())[:8]}{ext}"
                            new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        # Move and rename the file
                        os.rename(path, new_path)
                        url = f"/results/{new_filename}"
                        urls.append(url)
                        if first_url is None:
                            first_url = url

            if not urls:
                raise HTTPException(status_code=500, detail="Failed to process result images")

            return {"status": "success", "image": first_url}
            
        except HTTPException as http_exc:
            logger.error("HTTPException during background replacement: %s", http_exc)
            raise
        except Exception as e:
            logger.exception("An unexpected error occurred during background replacement for file: %s", file.filename)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            self._cleanup_file(upload_filename)
            self._cleanup_file(bg_removed_path)

    async def replace_background_rembg(
        self,
        foreground_image_file: UploadFile,
        background_image_file: UploadFile,
        position_x: Optional[int] = None,
        position_y: Optional[int] = None,
        foreground_scale: Optional[float] = None,
    ) -> Dict[str, str]:
        """Replace Background By Combining Foreground and Background"""
        foreground_upload_filename = ""
        background_upload_filename =""
        try:
            logger.info("Starting background replacement process for file: %s", foreground_image_file.filename)
            await self.validate_image(foreground_image_file)
            logger.info("Image validated: %s", foreground_image_file.filename)
            await self.validate_image(background_image_file)
            logger.info("Image validated: %s", background_image_file.filename)

            foreground_file_extension = os.path.splitext(foreground_image_file.filename)[1].lower()
            background_file_extension = os.path.splitext(background_image_file.filename)[1].lower()

            foreground_upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{foreground_file_extension}")
            background_upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{background_file_extension}")
            
            with open(foreground_upload_filename, "wb") as buffer:
                buffer.write(await foreground_image_file.read())
            with open(background_upload_filename, "wb") as buffer:
                buffer.write(await background_image_file.read())

            logger.info("Foreground image saved to: %s", foreground_upload_filename)
            logger.info("Background image saved to: %s", background_upload_filename)

            background_replacement_rembg(
                foreground_image_path=foreground_upload_filename,
                background_image_path=background_upload_filename,
                position_x=position_x,
                position_y=position_y,
                foreground_scale=foreground_scale
            )
        except HTTPException as http_exc:
            logger.error("HTTPException during background replacement rembg: %s", http_exc)
            raise
        except Exception as e:
            logger.exception("An unexpected error occurred during background replacement for file: %s", foreground_image_file.filename)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            self._cleanup_file(foreground_upload_filename)
            self._cleanup_file(background_upload_filename)
            

    async def anime_style(
            self,
            file: UploadFile,
            random_seed: bool = False,
            random_seed_2: bool = False,
            p_prompt: Optional[str] = None,
            n_prompt: Optional[str] = None,
            denoise: float = 0.45
        ) -> Dict[str, str]:
            """Apply anime style to an image."""
            file_path = ""
            try:
                # Validate image
                await self.validate_image(file)

                # Save file using the helper method
                file_path = await self._validate_and_save_files(file)

                # Process image
                saved_paths = anime_style(
                    image_path=os.path.abspath(file_path),
                    p_prompt=p_prompt,
                    n_prompt=n_prompt,
                    random_seed=random_seed,
                    random_seed_2=random_seed_2,
                    denoise=denoise
                )

                if not saved_paths or '38' not in saved_paths or not saved_paths['38']:
                    raise HTTPException(status_code=500, detail="No result image was generated")

                # Convert paths to URLs and rename files with original filename as base
                urls = []
                first_url = None
                for node_id, paths in saved_paths.items():
                    for idx, path in enumerate(paths):
                        if os.path.exists(path):
                            # Create a new filename based on the original
                            new_filename = f"anime_style_{os.path.splitext(file.filename)[0]}_{idx}.jpg"
                            new_path = os.path.join(RESULT_DIR, new_filename)
                            
                            # If the new path already exists, add a unique identifier
                            if os.path.exists(new_path):
                                base, ext = os.path.splitext(new_filename)
                                new_filename = f"{base}_{str(uuid.uuid4())[:8]}{ext}"
                                new_path = os.path.join(RESULT_DIR, new_filename)
                            
                            # Move and rename the file
                            os.rename(path, new_path)
                            url = f"/results/{new_filename}"
                            urls.append(url)
                            if first_url is None:
                                first_url = url

                if not urls:
                    raise HTTPException(status_code=500, detail="Failed to process result images")

                return {"status": "success", "images": urls, "image": first_url}

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error during anime style processing: {str(e)}")
            finally:
                self._cleanup_file(file_path)

    async def face_swap(
        self,
        target_file: UploadFile,
        source_file: UploadFile,
        p_prompt: Optional[str] = None,
        n_prompt: str = "blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
        random_seed: bool = False,
        denoise1: float = 0.65,
        denoise2: float = 0.65
    ) -> dict:
        """Apply face swap to an image."""
        target_file_path = ""
        source_file_path = ""
        try:
            # Validate images
            await self.validate_image(target_file)
            await self.validate_image(source_file)

            # Save files directly as PNG
            target_file_path = os.path.join(UPLOAD_DIR, f"target_{uuid.uuid4()}.jpg")
            source_file_path = os.path.join(UPLOAD_DIR, f"source_{uuid.uuid4()}.jpg")

            # Save uploaded files
            with open(target_file_path, "wb") as f:
                f.write(await target_file.read())
            with open(source_file_path, "wb") as f:
                f.write(await source_file.read())

            # Validate saved files
            try:
                with Image.open(target_file_path) as img:
                    img.verify()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Target image is invalid: {str(e)}")
            try:
                with Image.open(source_file_path) as img:
                    img.verify()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Source image is invalid: {str(e)}")

            saved_paths = face_swap(
                target_image_path=os.path.abspath(target_file_path),
                source_image_path=os.path.abspath(source_file_path),
                p_prompt=p_prompt,
                n_prompt=n_prompt,
                random_seed=random_seed,
                denoise1=denoise1,
                denoise2=denoise2
            )

            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Prepare response with flexible node selection logic
            result = {"status": "success", "images": {}}
            first_image_url = None

            # Flexible node selection based on target_file filename
            normalized_filename = (getattr(target_file, 'filename', '') or '').strip().lower()
            selected_node = None
            if "aries" in normalized_filename or "grey" in normalized_filename:
                selected_node = "118"
            elif "aghny" in normalized_filename or "red" in normalized_filename:
                selected_node = "118"
            else:
                # Fallback: pick the first available node
                if saved_paths:
                    selected_node = next(iter(saved_paths.keys()))

            # Add all available nodes to the response
            for node_id in saved_paths:
                if saved_paths[node_id]:
                    urls = [self._convert_result_path_to_url(p) for p in saved_paths[node_id]]
                    result["images"][node_id] = urls

            # Set the 'image' field to the selected node's first image, or fallback
            if selected_node and selected_node in result["images"] and result["images"][selected_node]:
                first_image_url = result["images"][selected_node][0]
            elif result["images"]:
                # fallback to any available image
                first_image_url = next(iter(result["images"].values()))[0]

            result["image"] = first_image_url or ""
            return result

        except Exception as e:
            error_msg = str(e)
            if "No images were generated" in error_msg:
                raise HTTPException(
                    status_code=500,
                    detail="The AI model failed to generate a result. Please try again with different parameters."
                )
            elif "Failed to save" in error_msg:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to save the generated image. Please try again."
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during face swap processing: {error_msg}"
                )
        finally:
            self._cleanup_file(target_file_path)
            self._cleanup_file(source_file_path)

    async def anime_style_face_swap_merge(
        self,
        target_file: UploadFile,
        source_file: UploadFile,
        anime_random_seed: bool = False,
        anime_random_seed_2: bool = False,
        anime_denoise: float = 0.45,
        anime_p_prompt: Optional[str] = None,
        face_p_prompt: Optional[str] = None,
        face_n_prompt: Optional[str] = None,
        face_random_seed: bool = False,
        face_denoise1: float = 0.65,
        face_denoise2: float = 0.65
    ) -> Dict[str, str]:
        """Apply anime style and face swap in a single optimized workflow."""
        target_file_path = ""
        source_file_path = ""
        try:
            logger.info("Starting anime_style_face_swap_merge with parameters: "
                       f"anime_denoise={anime_denoise}, face_denoise1={face_denoise1}, "
                       f"face_denoise2={face_denoise2}, anime_random_seed={anime_random_seed}, "
                       f"face_random_seed={face_random_seed}")
            
            # Validate images
            logger.info(f"Validating target file: {target_file.filename}")
            await self.validate_image(target_file)
            logger.info(f"Validating source file: {source_file.filename}")
            await self.validate_image(source_file)
            logger.info("Image validation completed successfully")

            # Save files directly as PNG
            target_file_path = os.path.join(UPLOAD_DIR, f"target_{uuid.uuid4()}.jpg")
            source_file_path = os.path.join(UPLOAD_DIR, f"source_{uuid.uuid4()}.jpg")
            logger.debug(f"Generated temporary file paths: target={target_file_path}, source={source_file_path}")

            # Save uploaded files
            logger.info("Saving uploaded files to temporary locations")
            with open(target_file_path, "wb") as f:
                f.write(await target_file.read())
            with open(source_file_path, "wb") as f:
                f.write(await source_file.read())
            logger.info("Files saved successfully")

            # Validate saved files
            logger.info("Validating saved files")
            try:
                with Image.open(target_file_path) as img:
                    img.verify()
                logger.debug("Target image verified successfully")
            except Exception as e:
                logger.error(f"Target image validation failed: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Target image is invalid: {str(e)}")
            try:
                with Image.open(source_file_path) as img:
                    img.verify()
                logger.debug("Source image verified successfully")
            except Exception as e:
                logger.error(f"Source image validation failed: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Source image is invalid: {str(e)}")

            # Call the websocket API with the merge workflow
            logger.info("Calling websocket API for anime style face swap merge")
            saved_paths = anime_style_face_swap_merge(
                target_image_path=os.path.abspath(target_file_path),
                source_image_path=os.path.abspath(source_file_path),
                anime_random_seed=anime_random_seed,
                anime_random_seed_2=anime_random_seed_2,
                anime_denoise=anime_denoise,
                anime_p_prompt=anime_p_prompt,
                face_p_prompt=face_p_prompt,
                face_n_prompt=face_n_prompt,
                face_random_seed=face_random_seed,
                face_denoise1=face_denoise1,
                face_denoise2=face_denoise2
            )
            logger.info(f"Websocket API call completed. Received paths: {saved_paths}")

            if not saved_paths:
                logger.error("No result image was generated")
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Convert paths to URLs and rename files with original filename as base
            logger.info("Processing generated images")
            urls = []
            first_url = None
            for node_id, paths in saved_paths.items():
                logger.debug(f"Processing node {node_id} with {len(paths)} paths")
                for idx, path in enumerate(paths):
                    if os.path.exists(path):
                        # Create a new filename based on the original with UUID
                        new_filename = f"anime_face_swap_{os.path.splitext(target_file.filename)[0]}_{idx}.jpg"
                        new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        # If the new path already exists, add a unique identifier
                        if os.path.exists(new_path):
                            base, ext = os.path.splitext(new_filename)
                            new_filename = f"{base}_{str(uuid.uuid4())[:8]}{ext}"
                            new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        logger.debug(f"Moving file from {path} to {new_path}")
                        # Move and rename the file
                        os.rename(path, new_path)
                        url = f"/results/{new_filename}"
                        urls.append(url)
                        if first_url is None:
                            first_url = url
                            logger.debug(f"Set first URL to: {first_url}")

            if not urls:
                logger.error("Failed to process result images - no URLs generated")
                raise HTTPException(status_code=500, detail="Failed to process result images")

            logger.info(f"Successfully processed {len(urls)} images")
            return {"status": "success", "images": urls, "image": first_url}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in anime_style_face_swap_merge: {error_msg}", exc_info=True)
            if "No images were generated" in error_msg:
                raise HTTPException(
                    status_code=500,
                    detail="The AI model failed to generate a result. Please try again with different parameters."
                )
            elif "Failed to save" in error_msg:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to save the generated image. Please try again."
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error during anime style face swap merge processing: {error_msg}"
                )
        finally:
            logger.info("Cleaning up temporary files")
            self._cleanup_file(target_file_path)
            self._cleanup_file(source_file_path)
            logger.info("Cleanup completed")
                                
    async def anime_style_face_swap(
        self,
        target_file: UploadFile,
        source_file: UploadFile,
        anime_random_seed: bool = False,
        anime_random_seed_2: bool = False,
        anime_p_prompt: str = "preserve original colors, same color palette as input image, detailed, anime style",
        anime_n_prompt: str = "nude, bad quality, ugly, distorted, low quality, blurry",
        anime_denoise: float = 0.45,
        face_p_prompt: Optional[str] = None,
        face_n_prompt: Optional[str] = "blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
        face_random_seed: bool = False,
        face_denoise1: float = 0.65,
        face_denoise2: float = 0.65
    ) -> Dict[str, str]:
        """Apply anime style to source image then use it for face swap with target image."""
        anime_upload = None
        spooled = None
        try:
            # Log input parameters
            logger.info(f"Starting anime_style_face_swap with parameters: anime_denoise={anime_denoise}, face_denoise1={face_denoise1}, face_denoise2={face_denoise2}")
            
            # First apply anime style to source image
            logger.info("Starting anime style processing for source image")
            anime_result = await self.anime_style(
                file=source_file,
                random_seed=anime_random_seed,
                random_seed_2=anime_random_seed_2,
                p_prompt=anime_p_prompt,
                n_prompt=anime_n_prompt,
                denoise=anime_denoise
            )
            logger.info(f"Anime style result: {anime_result}")
            
            if not anime_result or 'image' not in anime_result:
                raise HTTPException(status_code=500, detail="Failed to apply anime style to source image")
            
            # Get the anime-styled image
            anime_image_url = anime_result['image']
            anime_image_path = os.path.join(RESULT_DIR, os.path.basename(anime_image_url.lstrip('/results/')))
            logger.info(f"Anime image path: {anime_image_path}")
            
            if not os.path.exists(anime_image_path):
                raise HTTPException(status_code=500, detail=f"Anime-styled image not found at path: {anime_image_path}")
            
            # Create UploadFile from the anime-styled image
            anime_image_filename = os.path.basename(anime_image_path)
            logger.info(f"Reading anime image from: {anime_image_path}")
            
            # Verify the image can be opened
            try:
                with Image.open(anime_image_path) as img:
                    img.verify()
                logger.info("Image verification successful")
            except Exception as e:
                logger.error(f"Image verification failed: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Invalid anime-styled image: {str(e)}")
            
            # Read the image content
            with open(anime_image_path, 'rb') as f:
                anime_image_content = f.read()
            logger.info(f"Read {len(anime_image_content)} bytes from anime image")
            
            # Create a SpooledTemporaryFile for the UploadFile
            from tempfile import SpooledTemporaryFile
            spooled = SpooledTemporaryFile()
            spooled.write(anime_image_content)
            spooled.seek(0)
            logger.info("Created SpooledTemporaryFile")
            
            # Create UploadFile with proper content type
            anime_upload = UploadFile(
                file=spooled,
                filename=anime_image_filename,
                headers={"content-type": "image/png"}
            )
            logger.info(f"Created UploadFile with filename: {anime_image_filename}")
            
            # Now use the anime-styled image as source for face swap
            logger.info("Starting face swap with anime-styled source image")
            face_swap_result = await self.face_swap(
                target_file=target_file,
                source_file=anime_upload,
                p_prompt=face_p_prompt,
                n_prompt=face_n_prompt,
                random_seed=face_random_seed,
                denoise1=face_denoise1,
                denoise2=face_denoise2
            )
            logger.info(f"Face swap result: {face_swap_result}")
            
            if not face_swap_result or 'image' not in face_swap_result:
                raise HTTPException(status_code=500, detail="Failed to apply face swap")
            
            return face_swap_result
            
        except HTTPException as he:
            logger.error(f"HTTP Exception in anime_style_face_swap: {str(he)}")
            raise
        except Exception as e:
            logger.error(f"Error in anime_style_face_swap: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            # Clean up the temporary files
            if anime_upload is not None:
                try:
                    await anime_upload.close()
                    logger.info("Cleaned up anime_upload file")
                except Exception as e:
                    logger.error(f"Error cleaning up anime_upload file: {str(e)}")
            if spooled is not None:
                try:
                    spooled.close()
                    logger.info("Cleaned up spooled temporary file")
                except Exception as e:
                    logger.error(f"Error cleaning up spooled temporary file: {str(e)}")

    async def face_swap_single(
        self,
        target_file: UploadFile,
        source_file: UploadFile
    ) -> Dict[str, str]:
        """Run face swap single workflow and return first image URL."""
        target_file_path = ""
        source_file_path = ""
        try:
            # Validate
            await self.validate_image(target_file)
            await self.validate_image(source_file)

            # Save inputs
            target_file_path = os.path.join(UPLOAD_DIR, f"target_{uuid.uuid4()}.jpg")
            source_file_path = os.path.join(UPLOAD_DIR, f"source_{uuid.uuid4()}.jpg")
            with open(target_file_path, "wb") as f:
                f.write(await target_file.read())
            with open(source_file_path, "wb") as f:
                f.write(await source_file.read())

            # Verify
            try:
                with Image.open(target_file_path) as img:
                    img.verify()
                with Image.open(source_file_path) as img:
                    img.verify()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Invalid input image: {str(e)}")

            # Run workflow
            saved_paths = face_swap_single(
                target_image_path=os.path.abspath(target_file_path),
                source_image_path=os.path.abspath(source_file_path)
            )

            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Convert paths to URLs
            images_map = {node: [self._convert_result_path_to_url(p) for p in paths] for node, paths in saved_paths.items() if paths}
            first_url = None
            
            # Try preferred nodes first, then fallback to any available
            preferred_nodes = ['5']
            for node_id in preferred_nodes:
                if node_id in images_map and images_map[node_id]:
                    first_url = images_map[node_id][0]
                    print(f"[DEBUG] Using output from preferred node {node_id}: {first_url}")
                    break
            
            # If no preferred node found, use any available
            if not first_url and images_map:
                first_url = next(iter(images_map.values()))[0]
                print(f"[DEBUG] Using output from fallback node: {first_url}")

            return {"status": "success", "image": first_url}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error during face swap single: {str(e)}")
        finally:
            self._cleanup_file(target_file_path)
            self._cleanup_file(source_file_path)

    async def multi_face_swap(
        self,
        target_file: UploadFile,
        source_file: UploadFile,
        denoise: float = 0.55,
        total_face: int = 1
    ) -> Dict[str, str]:
        """Run multi face swap workflow and return first image URL."""
        target_file_path = ""
        source_file_path = ""
        try:
            # Validate
            await self.validate_image(target_file)
            await self.validate_image(source_file)

            # Save inputs
            target_file_path = os.path.join(UPLOAD_DIR, f"target_{uuid.uuid4()}.jpg")
            source_file_path = os.path.join(UPLOAD_DIR, f"source_{uuid.uuid4()}.jpg")
            with open(target_file_path, "wb") as f:
                f.write(await target_file.read())
            with open(source_file_path, "wb") as f:
                f.write(await source_file.read())

            # Verify
            try:
                with Image.open(target_file_path) as img:
                    img.verify()
                with Image.open(source_file_path) as img:
                    img.verify()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Invalid input image: {str(e)}")

            # Run workflow
            saved_paths = multi_face_swap(
                target_image_path=os.path.abspath(target_file_path),
                source_image_path=os.path.abspath(source_file_path),
                denoise=denoise,
                total_face=total_face
            )

            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Convert paths to URLs
            images_map = {node: [self._convert_result_path_to_url(p) for p in paths] for node, paths in saved_paths.items() if paths}
            first_url = None
            
            # Try preferred nodes first, then fallback to any available
            preferred_nodes = ['68']
            for node_id in preferred_nodes:
                if node_id in images_map and images_map[node_id]:
                    first_url = images_map[node_id][0]
                    print(f"[DEBUG] Using output from preferred node {node_id}: {first_url}")
                    break
            
            # If no preferred node found, use any available
            if not first_url and images_map:
                first_url = next(iter(images_map.values()))[0]
                print(f"[DEBUG] Using output from fallback node: {first_url}")

            return {"status": "success", "image": first_url}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error during multi face swap: {str(e)}")
        finally:
            self._cleanup_file(target_file_path)
            self._cleanup_file(source_file_path)

    async def replace_background_mask(
        self,
        file: UploadFile,
        p_prompt: Optional[str] = None,
        n_prompt: Optional[str] = None,
        random_seed: bool = False
    ) -> Dict[str, str]:
        """Replace background of an image using mask from src/app/mask folder."""
        upload_filename = ""
        try:
            await self.validate_image(file)
            logger.info("Image validated: %s", file.filename)
            
            file_extension = os.path.splitext(file.filename)[1].lower()
            upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{file_extension}")
            
            
            with open(upload_filename, "wb") as buffer:
                buffer.write(await file.read())
            logger.info("File saved to: %s", upload_filename)
            
            # Use background_replacement_masking which looks for mask in src/app/mask folder
            saved_paths = background_replacement_masking(
                image_path=upload_filename,
                image_mask="",  # Will be determined by filename in the function
                p_prompt=p_prompt,
                n_prompt=n_prompt,
                random_seed=random_seed
            )
            logger.info("Background replacement with mask completed for: %s", upload_filename)
            
            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")

            # Convert paths to URLs and rename files with original filename as base
            urls = []
            first_url = None
            for node_id, paths in saved_paths.items():
                for idx, path in enumerate(paths):
                    if os.path.exists(path):
                        # Create a new filename based on the original
                        new_filename = f"bg_replaced_mask_{os.path.splitext(file.filename)[0]}_{idx}.jpg"
                        new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        # If the new path already exists, add a unique identifier
                        if os.path.exists(new_path):
                            base, ext = os.path.splitext(new_filename)
                            new_filename = f"{base}_{str(uuid.uuid4())[:8]}{ext}"
                            new_path = os.path.join(RESULT_DIR, new_filename)
                        
                        # Move and rename the file
                        os.rename(path, new_path)
                        url = f"/results/{new_filename}"
                        urls.append(url)
                        if first_url is None:
                            first_url = url

            if not urls:
                raise HTTPException(status_code=500, detail="Failed to process result images")

            return {"status": "success", "image": first_url}
            
        except HTTPException as http_exc:
            logger.error("HTTPException during background replacement with mask: %s", http_exc)
            raise
        except Exception as e:
            logger.exception("An unexpected error occurred during background replacement with mask for file: %s", file.filename)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            self._cleanup_file(upload_filename)

    async def snowy(
        self,
        file: UploadFile,
        p_prompt: Optional[str] = None,
        n_prompt: Optional[str] = None,
        random_seed: bool = False
    ) -> Dict[str, str]:
        """Generate a snowy image using AI."""
        upload_filename = ""
        try:
            await self.validate_image(file)
            logger.info("Image validated: %s", file.filename)
            
            file_extension = os.path.splitext(file.filename)[1].lower()
            upload_filename = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{file_extension}")
            
            with open(upload_filename, "wb") as buffer:
                buffer.write(await file.read())
            logger.info("File saved to: %s", upload_filename)
            
            saved_paths = snowy(
                image_path=upload_filename,
                p_prompt=p_prompt,
                n_prompt=n_prompt,
                random_seed=random_seed
            )
            logger.info("Snowy generation completed for: %s", upload_filename)
            
            if not saved_paths:
                raise HTTPException(status_code=500, detail="No result image was generated")
            
            return {"status": "success", "image": saved_paths['60'][0]}
        except HTTPException as http_exc:
            logger.error("HTTPException during snowy generation: %s", http_exc)
            raise
        except Exception as e:
            logger.exception("An unexpected error occurred during snowy generation for file: %s", file.filename)
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
        finally:
            self._cleanup_file(upload_filename)
            
    async def _validate_and_save_files(
        self,
        file: UploadFile    ) -> Tuple[str, str]:
        """Validate and save uploaded files."""
        file_ext_1 = os.path.splitext(file.filename)[1].lower()
        
        if file_ext_1 not in SUPPORTED_IMAGE_EXTENSIONS:
            supported_types = ', '.join(ext.replace('.', '') for ext in SUPPORTED_IMAGE_EXTENSIONS)
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported types are: {supported_types}"
            )

        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{file_ext_1}")

        with open(file_path, "wb") as f:
            f.write(await file.read())

        return file_path
# built-in from Python 3.9+

    def _handle_result_file(self, original_filename: str, add_timestamp: bool = False) -> str:
        """Handle the result file naming and moving using Indonesian local time."""
        result_files = [f for f in os.listdir(RESULT_DIR) if f.endswith(".jpg")]
        print("Files in RESULT_DIR:", result_files)
        print("RESULT_DIR absolute path:", os.path.abspath(RESULT_DIR))
        if not result_files:
            raise HTTPException(status_code=500, detail="No output file was generated")

        original_name = os.path.splitext(os.path.basename(original_filename))[0]

        # Set time to Indonesian WIB timezone
        if add_timestamp:
            now = datetime.now(ZoneInfo("Asia/Jakarta"))
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            new_filename = f"output_{original_name}_{timestamp}_{unique_id}.jpg"
        else:
            new_filename = f"output_{original_name}.jpg"

        latest_result = max(result_files, key=lambda f: os.path.getctime(os.path.join(RESULT_DIR, f)))
        old_path = os.path.join(RESULT_DIR, latest_result)
        new_path = os.path.join(RESULT_DIR, new_filename)

        try:
            os.rename(old_path, new_path)
        except FileExistsError:
            random_suffix = str(uuid.uuid4())[:8]
            new_filename = f"output_{original_name}_{timestamp}_{random_suffix}.jpg" if add_timestamp else f"output_{original_name}_{random_suffix}.jpg"
            new_path = os.path.join(RESULT_DIR, new_filename)
            os.rename(old_path, new_path)

        return f"/results/{new_filename}"


    @staticmethod
    def _cleanup_file(file_path: str) -> None:
        """Clean up temporary files."""
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Warning: Failed to clean up file {file_path}: {str(e)}")

    def get_format_and_ext(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            return "JPEG", ".jpg"
        elif ext == ".png":
            return "PNG", ".png"
        elif ext == ".webp":
            return "WEBP", ".webp"
        else:
            return "PNG", ".png"  # fallback

    def get_content_type(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            return "image/jpeg"
        elif ext == ".png":
            return "image/png"
        elif ext == ".webp":
            return "image/webp"
        else:
            return "application/octet-stream"

    def _convert_result_path_to_url(self, path: str) -> str:
        # Convert a local result file path to an API URL
        filename = os.path.basename(path)
        return f"/results/{filename}"







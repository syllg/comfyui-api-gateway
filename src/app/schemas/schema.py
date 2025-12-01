from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

class StatusEnum(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PROCESSING = "processing"

class BackgroundRemovalRequest(BaseModel):
    """Request model for Background Removal"""
    return_mask: bool = Field(
        default=False,
        description="Whether to return the mask image as well.",
        example=False
    )
    return_original: bool = Field(
        default=False,
        description="Whether to return the original image as well.",
        example=False
    )
    class Config:
        json_schema_extra = {
            "example": {
                "return_mask": False,
                "return_original": False
            }
        }

class BackgroundRemovalResponse(BaseModel):
    """Response model for Background Removal"""
    result_url: str = Field(
        description="URL to the processed image with background removed.",
        example="/results/output_no_bg.png"
    )
    mask_url: Optional[str] = Field(
        default=None,
        description="URL to the mask image, if requested.",
        example="/results/output_mask.png"
    )
    original_url: Optional[str] = Field(
        default=None,
        description="URL to the original image, if requested.",
        example="/results/original.png"
    )
    message: str = Field(
        default="Background removal completed",
        description="Status message for the operation.",
        example="Background removal completed"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "result_url": "/results/output_no_bg.png",
                "mask_url": "/results/output_mask.png",
                "original_url": "/results/original.png",
                "message": "Background removal completed"
            }
        }

class BackgroundReplacementRequest(BaseModel):
    """
    Request model for background replacement operation.
    """
    p_prompt: Optional[str] = Field(
        default=None,
        description="Positive prompt for image generation.",
        example="a beautiful landscape with mountains and lake",
        min_length=3,
        max_length=512
    )
    n_prompt: Optional[str] = Field(
        default=None,
        description="Negative prompt to avoid certain elements.",
        example="blurry, low quality, distorted",
        min_length=3,
        max_length=512
    )
    random_seed: Optional[bool] = Field(
        default=False,
        description="Whether to use random seed for generation.",
        example=False
    )
    class Config:
        json_schema_extra = {
            "example": {
                "p_prompt": "a beautiful landscape with mountains and lake",
                "n_prompt": "blurry, low quality, distorted",
                "random_seed": False
            }
        }

class BackgroundReplacementResponse(BaseModel):
    """
    Response model for background replacement operation.
    """
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="Base64 encoded image or URL to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
            }
        }

class AnimeStyleRequest(BaseModel):
    """
    Request model for anime-style image generation.
    """
    random_seed: Optional[bool] = Field(
        default=False,
        description="Use random seed for first stage generation.",
        example=False
    )
    random_seed_2: Optional[bool] = Field(
        default=False,
        description="Use random seed for second stage/background generation.",
        example=False
    )
    denoise: Optional[float] = Field(
        default=0.45,
        description="Denoising strength for the image generation (0.0-1.0).",
        ge=0.0, le=1.0,
        example=0.45
    )
    class Config:
        json_schema_extra = {
            "example": {
                "random_seed": False,
                "random_seed_2": False,
                "denoise": 0.45
            }
        }

class AnimeStyleResponse(BaseModel):
    """
    Response model for anime-style image generation.
    """
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="URL or path to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-anime.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-anime.png"
            }
        }

class FaceSwapRequest(BaseModel):
    """
    Request model for face swap operation.
    """
    p_prompt: Optional[str] = Field(
        default=None,
        description="Positive prompt for face swap.",
        example="swap face with anime character",
        min_length=3,
        max_length=512
    )
    n_prompt: Optional[str] = Field(
        default="blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
        description="Negative prompt for face swap.",
        example="blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
        min_length=3,
        max_length=512
    )
    random_seed: Optional[bool] = Field(
        default=False,
        description="Whether to use random seed for generation.",
        example=False
    )
    denoise1: Optional[float] = Field(
        default=0.65,
        description="Denoising strength for the first stage (0.0-1.0).",
        ge=0.0, le=1.0,
        example=0.65
    )
    denoise2: Optional[float] = Field(
        default=0.65,
        description="Denoising strength for the second stage (0.0-1.0).",
        ge=0.0, le=1.0,
        example=0.65
    )
    class Config:
        json_schema_extra = {
            "example": {
                "p_prompt": "swap face with anime character",
                "n_prompt": "blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
                "random_seed": False,
                "denoise1": 0.65,
                "denoise2": 0.65
            }
        }

class FaceSwapResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="Base64 encoded image or URL to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
            }
        }
        
class AnimeStyleFaceSwapResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="URL or path to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-anime-faceswap.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-anime-faceswap.png"
            }
        }

class FaceSwapSingleResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="URL or path to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-faceswap-single.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-faceswap-single.png"
            }
        }

class MultiFaceSwapRequest(BaseModel):
    """
    Request model for face swap operation.
    """

    denoise: Optional[float] = Field(
        default=0.65,
        description="Denoising strength for the first stage (0.0-1.0).",
        ge=0.0, le=1.0,
        example=0.55
    )
    total_face:str=Field(
        default=1,
        description="Total face to be swapped",
        ge=1, le=10,
        example=2
    )

    class Config:
        json_schema_extra = {
            "example": {
                "denoise": 0.55,
                "total_face":1
            }
        }

class MultiFaceSwapResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="Base64 encoded image or URL to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
            }
        }

class SnowyRequest(BaseModel):
    p_prompt: Optional[str] = Field(
        default=None,
        description="Positive prompt for image generation.",
        example="replace background with consistent characters in a winter scene, heavy snowfall, heavy snowflakes, strong wind, cold atmosphere, icy air, high detail environment, ultra realistic, cinematic composition, depth of field, frozen landscape, white haze, winter mood"
    )
    n_prompt: Optional[str] = Field(
        default=None,
        description="Negative prompt to avoid certain elements.",
        example="blurry, low quality, distorted"
    )
    random_seed: Optional[bool] = Field(
        default=False,
        description="Whether to use random seed for generation.",
        example=False
    )
    class Config:
        json_schema_extra = {
            "example": {
                "p_prompt": "replace background with consistent characters in a winter scene, heavy snowfall, heavy snowflakes, strong wind, cold atmosphere, icy air, high detail environment, ultra realistic, cinematic composition, depth of field, frozen landscape, white haze, winter mood",
                "n_prompt": "",
                "random_seed": False
            }
        }

class SnowyResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    image: str = Field(
        description="Base64 encoded image or URL to the generated image.",
        example="/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "image": "/results/output_3c586680-eaf1-41bd-a310-7c4a0f2eeb12_29.png"
            }
        }


class PromptEntry(BaseModel):
    prompt: str = Field(
        description="Prompt text for image generation.",
        example="A hyper-realistic landscape of a serene pine forest ..."
    )
    image_filename: str = Field(
        description="Filename of the associated image.",
        example="hutan_pinus.jpg"
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL to the associated image.",
        example="http://127.0.0.1:8000/images/hutan_pinus.jpg"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "A hyper-realistic landscape of a serene pine forest ...",
                "image_filename": "hutan_pinus.jpg",
                "image_url": "http://127.0.0.1:8000/images/hutan_pinus.jpg"
            }
        }

class ListPromptRequest(BaseModel):
    list_prompt: Dict[str, PromptEntry] = Field(
        description="Dictionary list of prompt, keyed by prompt name.",
        example={
            "Hutan Pinus": {
                "prompt": "A hyper-realistic landscape of a serene pine forest ...",
                "image_filename": "hutan_pinus.jpg",
                "image_url": "http://127.0.0.1:8000/images/hutan_pinus.jpg"
            },
            "Danau Toba": {
                "prompt": "...",
                "image_filename": "danau_toba.jpg",
                "image_url": "http://127.0.0.1:8000/images/danau_toba.jpg"
            }
        }
    )
    class Config:
        json_schema_extra = {
            "example": {
                "list_prompt": {
                    "Hutan Pinus": {
                        "prompt": "A hyper-realistic landscape of a serene pine forest ...",
                        "image_filename": "hutan_pinus.jpg",
                        "image_url": "http://127.0.0.1:8000/images/hutan_pinus.jpg"
                    },
                    "Danau Toba": {
                        "prompt": "...",
                        "image_filename": "danau_toba.jpg",
                        "image_url": "http://127.0.0.1:8000/images/danau_toba.jpg"
                    }
                }
            }
        }

class DeletePromptRequest(BaseModel):
    prompt_keys: List[str] = Field(
        description="List of prompt keys to delete",
        example=["Mountain", "Waterfall"],
        min_items=1
    )

    class Config:
        json_schema_extra = {
            "example": {
                "prompt_keys": ["Mountain", "Waterfall"]
            }
        }

class ListPromptResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    list_prompt: Dict[str, PromptEntry] = Field(
        description="Dictionary list of prompt, keyed by prompt name.",
        example={
            "Hutan Pinus": {
                "prompt": "A hyper-realistic landscape of a serene pine forest ...",
                "image_filename": "hutan_pinus.jpg",
                "image_url": "http://127.0.0.1:8000/images/hutan_pinus.jpg"
            },
            "Danau Toba": {
                "prompt": "...",
                "image_filename": "danau_toba.jpg",
                "image_url": "http://127.0.0.1:8000/images/danau_toba.jpg"
            }
        }
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "list_prompt": {
                    "Hutan Pinus": {
                        "prompt": "A hyper-realistic landscape of a serene pine forest ...",
                        "image_filename": "hutan_pinus.jpg",
                        "image_url": "http://127.0.0.1:8000/images/hutan_pinus.jpg"
                    },
                    "Danau Toba": {
                        "prompt": "...",
                        "image_filename": "danau_toba.jpg",
                        "image_url": "http://127.0.0.1:8000/images/danau_toba.jpg"
                    }
                }
            }
        }

#batas
class AnimeEntry(BaseModel):
    image_filename: str = Field(
        description="Filename of the associated image.",
        example="RED.png"
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL to the associated image.",
        example="http://127.0.0.1:8000/images/RED.png"
    )
    class Config:
        json_schema_extra = {
            "example": {
                "image_filename": "RED.png",
                "image_url": "http://127.0.0.1:8000/images/RED.png"
            }
        }

class AnimeTemplateRequest(BaseModel):
    list_anime: Dict[str, AnimeEntry] = Field(
        description="Dictionary list of anime templates, keyed by template name.",
        example={
            "Model A": {
                "image_filename": "RED.png"
            },
            "Model B": {
                "image_filename": "AGHNY.png"
            }
        }
    )
    class Config:
        json_schema_extra = {
            "example": {
                "list_anime": {
                    "Model A": {
                        "image_filename": "RED.png"
                    },
                    "Model B": {
                        "image_filename": "AGHNY.png"
                    }
                }
            }
        }

class AnimeTemplateResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    list_anime: Dict[str, AnimeEntry] = Field(
        description="Dictionary list of anime-template, keyed by templatename.",
        example={
            "Model A": {
                "image_filename": "RED.png",
                "image_url": "http://127.0.0.1:8000/images/RED.png"
            },
            "Model B": {
                "image_filename": "AGHNY.png",
                "image_url": "http://127.0.0.1:8000/images/AGHNY.png"
            }
        }
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "list_anime": {
                    "Model A": {
                        "image_filename": "RED.png",
                        "image_url": "http://127.0.0.1:8000/images/RED.png"
                    },
                    "Model B": {
                        "image_filename": "AGHNY.png",
                        "image_url": "http://127.0.0.1:8000/images/AGHNY.png"
                    }
                }
            }
        }

class DeleteTemplateRequest(BaseModel):
    anime_keys: List[str] = Field(
        description="List of anime keys to delete",
        example=["Model A", "Model B"],
        min_items=1
    )

    class Config:
        json_schema_extra = {
            "example": {
                "anime_keys": ["Model A", "Model B"]
            }
        }

class ListTemplateResponse(BaseModel):
    status: StatusEnum = Field(
        description="Status of the operation.",
        example="success"
    )
    list_anime: Dict[str, AnimeEntry] = Field(
        description="Dictionary list of prompt, keyed by template-name.",
        example={
            "Model A": {
                "image_filename": "RED.png",
                "image_url": "http://127.0.0.1:8000/images/RED.png"
            },
            "Model B": {
                "image_filename": "AGHNY.png",
                "image_url": "http://127.0.0.1:8000/images/AGHNY.png"
            }
        }
    )
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "list_anime": {
                    "Model A": {
                        "image_filename": "RED.png",
                        "image_url": "http://127.0.0.1:8000/images/RED.png"
                    },
                    "Model B": {
                        "image_filename": "AGHNY.png",
                        "image_url": "http://127.0.0.1:8000/images/AGHNY.png"
                    }
                }
            }
        }


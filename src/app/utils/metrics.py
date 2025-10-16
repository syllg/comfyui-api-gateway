import time
import psutil
import torch
from PIL import Image
import numpy as np
from typing import Dict, Any

class ImageProcessingMetrics:
    @staticmethod
    def calculate_image_metrics(image: Image.Image) -> Dict[str, float]:
        """Calculate image quality metrics"""
        img_array = np.array(image)
        return {
            "image_width": image.width,
            "image_height": image.height,
            "image_channels": len(image.getbands()),
            "mean_pixel_value": float(np.mean(img_array)),
            "std_pixel_value": float(np.std(img_array))
        }
    
    @staticmethod
    def get_system_metrics() -> Dict[str, float]:
        """Get system resource usage metrics"""
        gpu_memory_used = 0
        if torch.cuda.is_available():
            gpu_memory_used = torch.cuda.memory_allocated() / 1024 / 1024  # MB
        
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "gpu_memory_used_mb": gpu_memory_used
        }
    
    @staticmethod
    def get_prompt_metrics(p_prompt: str = None, n_prompt: str = None) -> Dict[str, int]:
        """Analyze prompt characteristics"""
        return {
            "positive_prompt_length": len(p_prompt) if p_prompt else 0,
            "negative_prompt_length": len(n_prompt) if n_prompt else 0,
            "total_prompt_tokens": len(p_prompt.split()) + len(n_prompt.split()) if p_prompt and n_prompt else 0
        }

class ProcessingTimer:
    def __init__(self):
        self.start_time = None
        self.splits = {}
    
    def start(self):
        """Start the timer"""
        self.start_time = time.time()
        return self
    
    def split(self, name: str):
        """Record a split time"""
        if self.start_time is None:
            raise RuntimeError("Timer not started")
        self.splits[name] = time.time() - self.start_time
    
    def get_metrics(self) -> Dict[str, float]:
        """Get all timing metrics"""
        return {
            f"time_{k}": round(v, 3)
            for k, v in self.splits.items()
        }

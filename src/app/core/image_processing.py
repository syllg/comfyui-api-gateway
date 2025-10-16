import torch
import numpy as np
from PIL import Image
from ..core.remove_background import get_model, BriaRMBG
from ..utils.image_processing import validate_image_file, resize_image, pil_to_tensor, create_transparent_image
from ..settings.setting import TARGET_SIZE
def process_image(image: Image.Image, model: BriaRMBG) -> Image.Image:
    """
    Process an image with the BriaRMBG model
    """
    w, h = image.size
    
    # Resize image for model
    resized_image = resize_image(image, TARGET_SIZE)
    
    # Convert to tensor
    im_tensor = pil_to_tensor(resized_image)

    if torch.cuda.is_available():
        im_tensor = im_tensor.cuda()
    
    with torch.no_grad():
        result = model(im_tensor)
    
    result = torch.squeeze(torch.nn.functional.interpolate(
        result[0][0], size=(h, w), mode='bilinear'), 0)
    
    ma = torch.max(result)
    mi = torch.min(result)
    result = (result - mi) / (ma - mi)
    
    im_array = (result * 255).cpu().data.numpy().astype(np.uint8)
    mask = Image.fromarray(np.squeeze(im_array))

    transparent_image = create_transparent_image(image, mask)
    
    return transparent_image
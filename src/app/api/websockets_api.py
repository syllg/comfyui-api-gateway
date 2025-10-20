#This is an example that uses the websockets api to know when a prompt execution is done
#Once the prompt execution is done it downloads the images using the /history endpoint
import urllib.parse
import base64
import os
import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
import json
import io
import urllib.request
import random
from PIL import Image
from dotenv import load_dotenv
from src.app.settings.setting import BACKGROUND_REPLACEMENT_WORKFLOW, ANIME_STYLE_WORKFLOW, FACE_SWAP_WORKFLOW, BACKGROUND_REPLACEMENT_REMBG_WORKFLOW, ANIME_STYLE_FACE_SWAP_MERGE_WORKFLOW, MULTI_FACE_SWAP_WORKFLOW, FACE_SWAP_SINGLE_WORKFLOW, BACKGROUND_REPLACEMENT_MASK_WORKFLOW
from src.app.core.remove_background import get_model
from src.app.core.image_processing import process_image
from src.app.core.template import workflow_cache
from typing import Optional


load_dotenv()
OPEN_BUTTON_TOKEN=os.getenv("OPEN_BUTTON_TOKEN")
server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1:8188")  # ComfyUI's default port
client_id = str(uuid.uuid4())

auth_header = {"Authorization": f"Bearer {OPEN_BUTTON_TOKEN}"}

def get_protocol():
    if "ngrok" in server_address or "https" in server_address:
        return "https", "wss"
    return "http", "ws"

http_protocol, ws_protocol = get_protocol()

def build_url(path):
    """
    Build a proper URL by checking if server_address already contains protocol
    """
    if server_address.startswith(('http://', 'https://')):
        # Remove trailing slash if present to avoid double slashes
        base = server_address.rstrip('/')
        return f"{base}/{path.lstrip('/')}"
    else:
        return f"{http_protocol}://{server_address}/{path.lstrip('/')}"

def build_ws_url(path):
    """
    Build a proper WebSocket URL by checking if server_address already contains protocol
    """
    if server_address.startswith(('http://', 'https://')):
        # Convert http to ws, https to wss
        if server_address.startswith('https://'):
            base = server_address.replace('https://', 'wss://')
        else:
            base = server_address.replace('http://', 'ws://')
        base = base.rstrip('/')
        return f"{base}/{path.lstrip('/')}"
    else:
        return f"{ws_protocol}://{server_address}/{path.lstrip('/')}"

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    url = build_url("prompt")

    try:
        req = urllib.request.Request(url, data=data, headers=auth_header)
        response = urllib.request.urlopen(req, timeout=30)
        return json.loads(response.read())
    except Exception as e:
        raise

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    url = build_url(f"view?{url_values}")
    try:
        req = urllib.request.Request(url, headers=auth_header)
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        raise

def get_history(prompt_id):
    url = build_url(f"history/{prompt_id}")
    req = urllib.request.Request(url, headers=auth_header)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())

def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    # print(f"[DEBUG] Queued prompt with ID: {prompt_id}")
    output_images = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                # print(f"[DEBUG] Executing node: {data['node']}")
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
        else:
            continue #previews are binary data

    history = get_history(prompt_id)[prompt_id]
    # print(f"[DEBUG] Available output nodes in history: {list(history['outputs'].keys())}")
    
    for node_id in ['117', '118', '38', '29','68', '5']:
        # print(f"[DEBUG] Checking node {node_id}")
        if node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            # print(f"[DEBUG] Found output for node {node_id}: {node_output}")
            images_output = []
            if 'images' in node_output:
                for image in node_output['images']:
                    # print(f"[DEBUG] Processing image from node {node_id}: {image}")
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    images_output.append(image_data)
            if images_output:
                # print(f"[DEBUG] Added {len(images_output)} images from node {node_id}")
                output_images[node_id] = images_output
        else:
            print(f"[DEBUG] Node {node_id} not found in outputs")

    # print(f"[DEBUG] Final output_images keys: {list(output_images.keys())}")
    return output_images

def get_images_websocket(prompt):
    ws_url = build_ws_url(f"ws?clientId={client_id}")
    ws = websocket.WebSocket()
    ws.connect(ws_url, header=[f"{k}: {v}" for k, v in auth_header.items()])
    images = get_images(ws, prompt)
    ws.close()
    return images

def save_images(images):
    saved_paths = {}
    for node_id in images:
        node_paths = []
        for idx, image_data in enumerate(images[node_id]):
            image = Image.open(io.BytesIO(image_data))
            output_path = f"results/output_{client_id}_{node_id}_{idx}.jpg"
            image.save(output_path)
            node_paths.append(output_path)
        saved_paths[node_id] = node_paths
    return saved_paths

def upload_image(image_path):
    with open(image_path, 'rb') as f:
        image_data = f.read()

    original_filename = os.path.basename(image_path)
    boundary = '----WebKitFormBoundary' + ''.join(random.choices('0123456789abcdef', k=16))

    form_data = [
        f'--{boundary}'.encode(),
        b'Content-Disposition: form-data; name="image"; filename="' + original_filename.encode() + b'"',
        b'Content-Type: image/jpeg',
        b'',
        image_data,
        f'--{boundary}--'.encode()
    ]

    body = b'\r\n'.join(form_data)
    url = build_url("upload/image")

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body)),
        **auth_header
    }

    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        response = urllib.request.urlopen(req, timeout=30)
        return json.loads(response.read())['name']
    except Exception as e:
        raise


def background_replacement(image_path: str, p_prompt: str = None, n_prompt: str = None, random_seed: bool = False):
    """
    Function to replace the background of an image with a new one based on a prompt.
    
    Args:
        image_path (str): Path to the image file to replace the background of.
        p_prompt (str): Prompt to generate a new background image. If None, a random prompt will be generated.
        n_prompt (str): Number of prompts to generate. If None, only one prompt will be generated.
        random_seed (bool): If True, the random seed will be set to 0, so the same background will be generated every time the function is called.
    """
    try:
        if not os.path.exists(BACKGROUND_REPLACEMENT_WORKFLOW):
            raise Exception(f"Workflow file not found: {BACKGROUND_REPLACEMENT_WORKFLOW}")
            
        # print(f"[DEBUG] Starting background replacement for image: {image_path}")
        
        # First generate the mask using rembg
        with Image.open(image_path) as img:
            result_image = process_image(img, get_model())
            # Get alpha channel as mask
            mask = result_image.split()[3]
            # Save mask temporarily
            mask_path = os.path.join(os.path.dirname(image_path), "temp_mask.jpg")
            mask.save(mask_path)
            # print(f"[DEBUG] Generated and saved mask to: {mask_path}")
        
        # Upload both the original image and mask
        uploaded_filename = upload_image(image_path)
        uploaded_mask = upload_image(mask_path)
        # print(f"[DEBUG] Uploaded image as: {uploaded_filename}")
        # print(f"[DEBUG] Uploaded mask as: {uploaded_mask}")
        
        with open(BACKGROUND_REPLACEMENT_WORKFLOW, "r", encoding="utf-8") as f:
            workflow_background_replacement = f.read()
        workflow = json.loads(workflow_background_replacement)
        
        # Set both image and mask inputs
        workflow["3"]["inputs"]["image"] = uploaded_filename
        workflow["3"]["inputs"]["upload"] = "image"
        workflow["3"]["inputs"]["mask"] = uploaded_mask
        
        if p_prompt is not None and p_prompt != "":
            workflow["11"]["inputs"]["text"] = p_prompt
        if n_prompt is not None and n_prompt != "":
            workflow["12"]["inputs"]["text"] = n_prompt
        
        if random_seed:
            workflow["14"]["inputs"]["seed"] = random.randint(0, 777777777777)
        
        # print("[DEBUG] Executing workflow")
        images = get_images_websocket(workflow)
        # print(f"[DEBUG] Got images response: {bool(images)}")
        if not images:
            raise Exception("No images were generated by the workflow")
        
        # print("[DEBUG] Saving images")
        saved_paths = save_images(images)
        # print(f"[DEBUG] Saved paths: {saved_paths}")
        
        # Note: mask_path is not a temporary file, so we don't remove it
        
        # Validate the generated images
        for node_id in ['29']:  # Background replacement uses node 29
            if node_id in saved_paths:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            # print(f"[DEBUG] Validated image: {path}")
                    except Exception as e:
                        raise Exception(f"Generated image for node {node_id} is invalid: {str(e)}")
            else:
                raise Exception(f"No output found from node {node_id}")
        
        return saved_paths
    except Exception as e:
        print(f"Error in background_replacement: {str(e)}")
        raise

def background_replacement_rembg(foreground_image_path: str, background_image_path: str, position_x: int, position_y: int, foreground_scale: float):
    """
        Function to replace background by simple approach combine foreground and background image using RMBG

        Args:
            foreground_image_path (str): Path to the image file containing the foreground or object to be added to the background.
            background_image_path (str): Path to the background image file to combine with the foreground.
            position_x (int): Horizontal position of the foreground on the background image. A higher value moves it to the right, a lower value to the left. `50` centers it horizontally.
            position_y (int): Vertical position of the foreground on the background image. A higher value moves it downward, a lower value upward. `50` centers it vertically.
            foreground_scale (float): Scale factor for the foreground image. A larger value increases its size.
    """
    foreground = upload_image(foreground_image_path)
    background = upload_image(background_image_path)
    with open(BACKGROUND_REPLACEMENT_REMBG_WORKFLOW, "r", encoding="utf-8") as f:
        workflow_background_replacement_rembg = f.read()
    workflow = json.load(workflow_background_replacement_rembg)

    # foreground and background
    workflow["9"]["inputs"]["image"] = foreground
    workflow["9"]["inputs"]["upload"] = "image"
    workflow["8"]["inputs"]["image"] = background
    workflow["8"]["inputs"]["upload"] = "image"

    # position_x, position_y, foreground_scale
    if position_x is not None and position_x != "":
        workflow["1"]["inputs"]["position_x"] = position_x
    if position_y is not None and position_y != "":
        workflow["1"]["inputs"]["position_y"] = position_y
    if foreground_scale is not None and foreground_scale != "":
        workflow["1"]["inputs"]["foreground_scale"] = foreground_scale
    images = get_images_websocket(workflow)
    save_images(images)

def anime_style(image_path: str, p_prompt: str = "preserve original colors, same color palette as input image, detailed, anime style, expressive", 
                n_prompt: str = "nude, bad quality, ugly, distorted, low quality, blurry",  random_seed: bool = False, random_seed_2: bool = False, denoise = 0.45):
    try:
        if not os.path.exists(ANIME_STYLE_WORKFLOW):
            raise Exception(f"Workflow file not found: {ANIME_STYLE_WORKFLOW}") 

        uploaded_main = upload_image(image_path)
        
        # Get workflow from cache
        try:
            workflow = workflow_cache.get_workflow(ANIME_STYLE_WORKFLOW)
            print(f"[DEBUG] Successfully loaded anime workflow from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading workflow from cache: {str(e)}")
            raise Exception(f"Failed to load anime workflow: {str(e)}")

        # Update image inputs
        workflow["10"]["inputs"]["image"] = uploaded_main
        workflow["10"]["inputs"]["upload"] = "image"
        workflow["3"]["inputs"]["denoise"] = denoise
        if p_prompt is not None and p_prompt != "":
            workflow["13"]["inputs"]["postive_prompt"] = p_prompt
        if n_prompt is not None and n_prompt != "":
            workflow["13"]["inputs"]["base_negative"] = n_prompt

        # Set seeds
        if random_seed:
            workflow["13"]["inputs"]["seed"] = random.randint(0, 777777777777)
        if random_seed_2:
            workflow["3"]["inputs"]["seed"] = 638765238772440
            
        print(f"[DEBUG] Executing anime workflow with denoise={denoise}")
        images = get_images_websocket(workflow)
        if not images:
            raise Exception("No images were generated by the workflow")    
        saved_paths = save_images(images)
                
        # Validate the generated images
        for node_id in ['38']:
            if node_id in saved_paths:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            print(f"[DEBUG] Validated anime output image: {path}")
                    except Exception as e:
                        raise Exception(f"Generated image for node {node_id} is invalid: {str(e)}")
            else:
                print(f"[DEBUG] Node {node_id} not found in saved paths")
        
        return saved_paths
    except Exception as e:
        print(f"Error in anime_style: {str(e)}")
        raise

def face_swap(
    target_image_path: str, 
    source_image_path: str,
    p_prompt: str = None, 
    n_prompt: str = "blurry, malformed, low quality, worst quality, artifacts, noise, text, watermark, glitch, deformed, ugly, horror, ill",
    random_seed: bool = False,
    denoise1: float = 0.65,
    denoise2: float = 0.65,
):
    try:
        # Validate workflow file
        if not os.path.exists(FACE_SWAP_WORKFLOW):
            raise Exception(f"Workflow file not found: {FACE_SWAP_WORKFLOW}")
            
        # Upload images to ComfyUI server
        uploaded_target_filename = upload_image(target_image_path)
        uploaded_source_filename = upload_image(source_image_path)
        
        # Get workflow from cache
        try:
            workflow = workflow_cache.get_workflow(FACE_SWAP_WORKFLOW)
            print(f"[DEBUG] Successfully loaded face swap workflow from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading workflow from cache: {str(e)}")
            raise Exception(f"Failed to load face swap workflow: {str(e)}")
        
        # Update workflow to use the uploaded image
        workflow["90"]["inputs"]["image"] = uploaded_target_filename
        workflow["137"]["inputs"]["image"] = uploaded_source_filename
        workflow["3"]["inputs"]["denoise"] = denoise1
        workflow["49"]["inputs"]["denoise"] = denoise2
        
        # Update prompts using the correct workflow nodes
        if p_prompt is not None:
            workflow["22"]["inputs"]["text"] = p_prompt  # Positive prompt node
        if n_prompt:
            workflow["23"]["inputs"]["text"] = n_prompt  # Negative prompt node
            
        # Always set seed to random
        workflow["89"]["inputs"]["seed"] = random.randint(0, 777777777777)
        
        print(f"[DEBUG] Executing face swap workflow with denoise1={denoise1}, denoise2={denoise2}")
        images = get_images_websocket(workflow)
        if not images:
            raise Exception("No images were generated by the workflow")
            
        saved_paths = save_images(images)
        
        # Add validation for saved paths
        if not saved_paths:
            raise Exception("No paths returned from save_images")
            
        print(f"[DEBUG] Face swap completed successfully. Saved paths: {saved_paths}")
        return saved_paths
        
    except json.JSONDecodeError as e:
        print(f"[DEBUG] JSON decode error in face swap: {str(e)}")
        raise Exception(f"Invalid workflow file format: {str(e)}")
    except Exception as e:
        print(f"[DEBUG] Error in face swap: {str(e)}")
        raise Exception(f"Failed to process face swap: {str(e)}")
    
    
def anime_style_face_swap_merge(
    target_image_path: str,
    source_image_path: str,
    anime_random_seed: bool = False,
    anime_random_seed_2: bool = False,
    anime_denoise: float = 0.45,
    anime_p_prompt: Optional[str] = None,
    anime_n_prompt: Optional[str] = None,
    face_p_prompt: Optional[str] = None,
    face_n_prompt: Optional[str] = None,
    face_random_seed: bool = False,
    face_denoise1: float = 0.65,
    face_denoise2: float = 0.65
):
    """Apply anime style and face swap in a single optimized workflow."""
    try:
        # Validate workflow file
        if not os.path.exists(ANIME_STYLE_FACE_SWAP_MERGE_WORKFLOW):
            raise Exception(f"Workflow file not found: {ANIME_STYLE_FACE_SWAP_MERGE_WORKFLOW}")
            
        # Upload images to ComfyUI server
        uploaded_target_filename = upload_image(target_image_path)
        uploaded_source_filename = upload_image(source_image_path)
        
        # Get workflow from cache
        try:
            workflow = workflow_cache.get_workflow(ANIME_STYLE_FACE_SWAP_MERGE_WORKFLOW)
            print(f"[DEBUG] Successfully loaded anime style face swap merge workflow from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading workflow from cache: {str(e)}")
            raise Exception(f"Failed to load anime style face swap merge workflow: {str(e)}")
        
        # Update workflow inputs based on workflow structure
        # Anime branch
        workflow["155"]["inputs"]["image"] = uploaded_source_filename  # Source image for anime style
        workflow["155"]["inputs"]["upload"] = "image"
        # Face swap branch
        workflow["90"]["inputs"]["image"] = uploaded_target_filename  # Target image for face swap
        workflow["90"]["inputs"]["upload"] = "image"
        
        # Anime style parameters
        workflow["154"]["inputs"]["denoise"] = anime_denoise
        if anime_random_seed_2:
            workflow["154"]["inputs"]["seed"] = random.randint(0, 777777777777)
        if anime_random_seed:
            workflow["148"]["inputs"]["seed"] = random.randint(0, 777777777777)
        if anime_p_prompt is not None and anime_p_prompt != "":
            workflow["148"]["inputs"]["postive_prompt"] = anime_p_prompt
        if anime_n_prompt is not None and anime_n_prompt != "":
            workflow["148"]["inputs"]["base_negative"] = anime_n_prompt
        
        # Face swap parameters
        if face_p_prompt is not None and face_p_prompt != "":
            workflow["22"]["inputs"]["text"] = face_p_prompt
        if face_n_prompt is not None and face_n_prompt != "":
            workflow["23"]["inputs"]["text"] = face_n_prompt
        workflow["167"]["inputs"]["denoise"] = face_denoise1
        workflow["49"]["inputs"]["denoise"] = face_denoise2
        if face_random_seed:
            workflow["89"]["inputs"]["seed"] = random.randint(0, 777777777777)
        
        print(f"[DEBUG] Executing anime style face swap merge workflow with parameters: anime_denoise={anime_denoise}, face_denoise1={face_denoise1}, face_denoise2={face_denoise2}")
        images = get_images_websocket(workflow)
        if not images:
            raise Exception("No images were generated by the workflow")    
        saved_paths = save_images(images)
                
        for node_id in ['118']:
            if node_id in saved_paths:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            print(f"[DEBUG] Validated anime output image: {path}")
                    except Exception as e:
                        raise Exception(f"Generated image for node {node_id} is invalid: {str(e)}")
            else:
                print(f"[DEBUG] Node {node_id} not found in saved paths")
        return saved_paths
    except Exception as e:
        raise Exception(f"Error in anime style swap merge: {e}")

def face_swap_single(
    target_image_path: str,
    source_image_path: str
):
    """Apply face swap single in optimized workflow."""
    try:
        # Validate workflow file
        if not os.path.exists(FACE_SWAP_SINGLE_WORKFLOW):
            raise Exception(f"Workflow file not found: {FACE_SWAP_SINGLE_WORKFLOW}")
            
        # Upload images to ComfyUI server
        uploaded_target_filename = upload_image(target_image_path)
        uploaded_source_filename = upload_image(source_image_path)
        
        # Get workflow from cache
        try:
            workflow = workflow_cache.get_workflow(FACE_SWAP_SINGLE_WORKFLOW)
            print(f"[DEBUG] Successfully loaded  face swap single workflow from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading workflow from cache: {str(e)}")
            raise Exception(f"Failed to load single face swap workflow: {str(e)}")
        
        # Update workflow inputs based on workflow structure
        # Anime branch
        workflow["4"]["inputs"]["image"] = uploaded_source_filename  # Source image (real face)
        workflow["4"]["inputs"]["upload"] = "image"
        # Face swap branch
        workflow["3"]["inputs"]["image"] = uploaded_target_filename  # Target image for face swap
        workflow["3"]["inputs"]["upload"] = "image"

        images = get_images_websocket(workflow)
        if not images:
            raise Exception("No images were generated by the workflow")    
        saved_paths = save_images(images)
        
        print(f"[DEBUG] Available nodes in saved_paths: {list(saved_paths.keys())}")
        
        # Try to find output from expected nodes, fallback to any available node
        validated_nodes = []
        for node_id in ['5']:  # Try multiple possible output nodes
            if node_id in saved_paths and saved_paths[node_id]:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            print(f"[DEBUG] Validated faceswap single output image from node {node_id}: {path}")
                            validated_nodes.append(node_id)
                    except Exception as e:
                        print(f"[DEBUG] Invalid image for node {node_id}: {str(e)}")
                        
        # If no expected nodes found, try any available node
        if not validated_nodes:
            for node_id, paths in saved_paths.items():
                if paths:
                    for path in paths:
                        try:
                            with Image.open(path) as img:
                                img.verify()
                                print(f"[DEBUG] Validated faceswap single output image from fallback node {node_id}: {path}")
                                validated_nodes.append(node_id)
                                break
                        except Exception as e:
                            print(f"[DEBUG] Invalid image for fallback node {node_id}: {str(e)}")
                    if validated_nodes:
                        break
        
        if not validated_nodes:
            raise Exception("No valid output images were generated by the workflow")
            
        return saved_paths
    except Exception as e:
        print(f"Error in background_replacement: {str(e)}")
        raise

def multi_face_swap(
    target_image_path: str,
    source_image_path: str,
    denoise: float = 0.55,
    total_face: int=1
):
    """Apply multi face swap in optimized workflow."""
    try:
        # Validate workflow file
        if not os.path.exists(MULTI_FACE_SWAP_WORKFLOW):
            raise Exception(f"Workflow file not found: {MULTI_FACE_SWAP_WORKFLOW}")
            
        # Upload images to ComfyUI server
        uploaded_target_filename = upload_image(target_image_path)
        uploaded_source_filename = upload_image(source_image_path)
        
        # Get workflow from cache
        try:
            workflow = workflow_cache.get_workflow(MULTI_FACE_SWAP_WORKFLOW)
            print(f"[DEBUG] Successfully loaded anime style face swap merge workflow from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading workflow from cache: {str(e)}")
            raise Exception(f"Failed to load anime style face swap merge workflow: {str(e)}")
        
        # Update workflow inputs based on workflow structure
        # Anime branch
        workflow["4"]["inputs"]["image"] = uploaded_source_filename  # Source image (real face)
        workflow["4"]["inputs"]["upload"] = "image"
        # Face swap branch
        workflow["18"]["inputs"]["image"] = uploaded_target_filename  # Target image for face swap
        workflow["18"]["inputs"]["upload"] = "image"
        
        # Anime style parameters
        workflow["61"]["inputs"]["denoise"] = denoise
        workflow["29"]["inputs"]["total"]=total_face
        
        print(f"[DEBUG] Executing multi face swap merge workflow with parameters: denoise={denoise}, total_face={total_face}")
        images = get_images_websocket(workflow)
        if not images:
            raise Exception("No images were generated by the workflow")    
        saved_paths = save_images(images)
        
        print(f"[DEBUG] Available nodes in saved_paths: {list(saved_paths.keys())}")
        
        # Try to find output from expected nodes, fallback to any available node
        validated_nodes = []
        for node_id in ['68']:  # Try multiple possible output nodes
            if node_id in saved_paths and saved_paths[node_id]:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            print(f"[DEBUG] Validated multi faceswap output image from node {node_id}: {path}")
                            validated_nodes.append(node_id)
                    except Exception as e:
                        print(f"[DEBUG] Invalid image for node {node_id}: {str(e)}")
                        
        # If no expected nodes found, try any available node
        if not validated_nodes:
            for node_id, paths in saved_paths.items():
                if paths:
                    for path in paths:
                        try:
                            with Image.open(path) as img:
                                img.verify()
                                print(f"[DEBUG] Validated multi faceswap output image from fallback node {node_id}: {path}")
                                validated_nodes.append(node_id)
                                break
                        except Exception as e:
                            print(f"[DEBUG] Invalid image for fallback node {node_id}: {str(e)}")
                    if validated_nodes:
                        break
        
        if not validated_nodes:
            raise Exception("No valid output images were generated by the workflow")
            
        return saved_paths
    except Exception as e:
        raise Exception(f"Error in multi faceswap: {e}")

def background_replacement_masking(image_path: str, image_mask:str, p_prompt: str = None, n_prompt: str = None, random_seed: bool = False):
    """
    Function to replace the background of an image with a new one based on a prompt.
    
    Args:
        image_path (str): Path to the image file to replace the background of.
        p_prompt (str): Prompt to generate a new background image. If None, a random prompt will be generated.
        n_prompt (str): Number of prompts to generate. If None, only one prompt will be generated.
        random_seed (bool): If True, the random seed will be set to 0, so the same background will be generated every time the function is called.
    """
    try:
        if not os.path.exists(BACKGROUND_REPLACEMENT_MASK_WORKFLOW):
            raise Exception(f"Workflow file not found: {BACKGROUND_REPLACEMENT_MASK_WORKFLOW}")
            
        # Use mask from uploads directory (generated previously by the system)
        # Default expected path: uploads/temp_mask.jpg
        mask_path = os.path.join("./uploads", "temp_mask.png")
        
        # Check if mask file exists
        if not os.path.exists(mask_path):
            raise Exception(f"Mask file not found: {mask_path}")
        
        # Upload both the original image and mask (from uploads)
        uploaded_filename = upload_image(image_path)
        uploaded_mask = upload_image(mask_path)
        print(f"[DEBUG] Uploaded image as: {uploaded_filename}")
        print(f"[DEBUG] Uploaded mask as: {uploaded_mask}")
        
        with open(BACKGROUND_REPLACEMENT_MASK_WORKFLOW, "r", encoding="utf-8") as f:
            workflow_background_replacement_mask = f.read()
        workflow = json.loads(workflow_background_replacement_mask)
        
        # Set both image and mask inputs
        workflow["30"]["inputs"]["image"] = uploaded_filename
        workflow["30"]["inputs"]["upload"] = "image"
        workflow["3"]["inputs"]["image"] = uploaded_mask
        workflow["3"]["inputs"]["upload"]="image"
        print(f"[DEBUG] Set workflow inputs - image: {uploaded_filename}, mask: {uploaded_mask}")
        
        if p_prompt is not None and p_prompt != "":
            workflow["11"]["inputs"]["text"] = p_prompt
        if n_prompt is not None and n_prompt != "":
            workflow["12"]["inputs"]["text"] = n_prompt
        
        if random_seed:
            workflow["14"]["inputs"]["seed"] = random.randint(0, 777777777777)
        
        print("[DEBUG] Executing workflow")
        images = get_images_websocket(workflow)
        print(f"[DEBUG] Got images response: {bool(images)}")
        if images:
            print(f"[DEBUG] Images keys: {list(images.keys())}")
        if not images:
            raise Exception("No images were generated by the workflow")
        
        print("[DEBUG] Saving images")
        saved_paths = save_images(images)
        print(f"[DEBUG] Saved paths: {saved_paths}")
        
        # Validate the generated images
        for node_id in ['29']:  # Background replacement uses node 29
            if node_id in saved_paths:
                for path in saved_paths[node_id]:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            # print(f"[DEBUG] Validated image: {path}")
                    except Exception as e:
                        raise Exception(f"Generated image for node {node_id} is invalid: {str(e)}")
            else:
                raise Exception(f"No output found from node {node_id}")
        
        return saved_paths
    except Exception as e:
        print(f"Error in background_replacement: {str(e)}")
        raise
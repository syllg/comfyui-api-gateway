import gradio as gr
import requests
import os
import io
import uuid
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
if not API_BASE_URL.startswith(('http://', 'https://')):
    API_BASE_URL = f"http://{API_BASE_URL}"

# Create uploads directory if it doesn't exist
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

def get_prompt_options():
    try:
        response = requests.get(f"{API_BASE_URL}/list-prompt/")
        response.raise_for_status()
        prompt_list = response.json()

        if prompt_list.get("status") == "success" and prompt_list.get("list_prompt"):
            return list(prompt_list['list_prompt'].keys())
        return []
    except Exception as e:
        return []

def get_prompt_value(selected_key):
    """Get the prompt value for the selected key (returns the 'prompt' field)"""
    try:
        response = requests.get(f"{API_BASE_URL}/list-prompt/")
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success" and data.get("list_prompt"):
            entry = data["list_prompt"].get(selected_key, None)
            if entry and isinstance(entry, dict):
                return entry.get("prompt", "")
        return ""
    except Exception as e:
        return ""

def get_prompt_image_url(selected_key):
    """Get the image_url for the selected prompt key (for preview)"""
    try:
        response = requests.get(f"{API_BASE_URL}/list-prompt/")
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success" and data.get("list_prompt"):
            entry = data["list_prompt"].get(selected_key, None)
            if entry and isinstance(entry, dict):
                return entry.get("image_url", None)
        return None
    except Exception as e:
        return None

def refresh_prompts():
    """Refresh prompt options from API"""
    try:
        options = get_prompt_options()
        return gr.Dropdown(choices=options, value=options[0] if options else None)
    except Exception as e:
        return gr.Dropdown(choices=[], value=None)

def remove_bg(image):
    """Remove background from the uploaded image"""
    if image is None:
        return None, "Please upload an image first"
    
    # Convert image to bytes
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()
    
    # Prepare the files for the request
    files = {
        'file': ('image.png', img_byte_arr, 'image/png')
    }
    
    try:
        response = requests.post(f"{API_BASE_URL}/remove-background/", files=files)
        response.raise_for_status()
        
        # Get the result image URL from the response
        result_url = response.json()['result_url']
        result_image = requests.get(f"{API_BASE_URL}/{result_url}")
        result_image.raise_for_status()
        
        # Convert response content to PIL Image
        return Image.open(io.BytesIO(result_image.content)), "Background removed successfully!"
    except Exception as e:
        return None, f"Error: {str(e)}"


def replace_background(file, selected_prompt_key, n_prompt="", random_seed=False):
    """Replace background of the uploaded image"""
    if file is None:
        return None, "Please upload an image first"
    
    # Get the actual prompt value from the selected key
    p_prompt = get_prompt_value(selected_prompt_key)
    if not p_prompt:
        return None, "Please select a valid prompt"
    
    try:
        # Generate a unique filename using UUID
        original_filename = os.path.basename(file.name)
        file_extension = os.path.splitext(original_filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        input_path = os.path.join(UPLOADS_DIR, unique_filename)
        
        # Read the file content
        with open(file.name, 'rb') as f:
            file_content = f.read()
        
        # Prepare the files for the request
        files = {
            'file': (unique_filename, file_content, "image/png")
        }

        response = requests.post(
            f"{API_BASE_URL}/replace-background/",
            files=files,
            data={
                'p_prompt': p_prompt,
                'n_prompt': n_prompt,
                'random_seed': str(random_seed)
            }
        )
        response.raise_for_status()
        
        # Get the result image URL from the response
        result_url = response.json()['image']
        result_image = requests.get(f"{API_BASE_URL}{result_url}")
        result_image.raise_for_status()
        
        # Convert response content to PIL Image
        return Image.open(io.BytesIO(result_image.content)), "Background replaced successfully!"
    except Exception as e:
        return None, f"Error: {str(e)}"

def style_anime(main_image, denoise=0.45):
    if main_image is None:
        return None, "Please upload an image"

    # Convert images to bytes
    orig_byte_arr = io.BytesIO()
    main_image.save(orig_byte_arr, format='PNG')

    files = {
        'file': ('main.png', orig_byte_arr.getvalue(), 'image/png'),
    }
    data = {
        'denoise': str(denoise)
    }

    try:
        response = requests.post(f"{API_BASE_URL}/anime-style/", files=files, data=data)
        response.raise_for_status()
        
        # Get the result image URL from the response
        result_path = response.json()['image']
        result_image = requests.get(f"{API_BASE_URL}{result_path}")
        result_image.raise_for_status()
        
        # Convert response content to PIL Image
        return Image.open(io.BytesIO(result_image.content)), "Anime style applied successfully!"
    except Exception as e:
        return None, f"Error: {str(e)}"

def face_swap(target_image, source_image, positive_prompt=None, target_filename=None, denoise1=0.65, denoise2=0.65):
    """Face swap function"""
    if target_image is None or source_image is None:
        return None, "Please upload both target and source images"
    if not target_filename:
        target_filename = ""
    # Ensure positive_prompt is empty string if None or 'string'
    if positive_prompt is None:
        positive_prompt = ""
    try:
        # Save the images in PNG format
        target_buffer = io.BytesIO()
        source_buffer = io.BytesIO()
        target_image.save(target_buffer, format='PNG')
        source_image.save(source_buffer, format='PNG')
        target_buffer.seek(0)
        source_buffer.seek(0)

        # Prepare file upload
        ext = ".png"
        media_type = "image/png"
        base_name = os.path.splitext(target_filename or "target")[0]
        target_upload_name = base_name + ext
        
        files = {
            "target": (target_upload_name, target_buffer, media_type),
            "source": ("source.png", source_buffer, "image/png")
        }
        
        # Call API
        response = requests.post(
            f"{API_BASE_URL}/face-swap/",
            files=files,
            data={
                'denoise1': str(denoise1),
                'denoise2': str(denoise2)
            }
        )
        response.raise_for_status()
        
        # Get the result image URL from the response
        result_path = response.json()['image']
        result_image = requests.get(f"{API_BASE_URL}/{result_path}")
        result_image.raise_for_status()
        
        # Convert response content to PIL Image
        return Image.open(io.BytesIO(result_image.content)), "Face Swap is Successful!"
    except Exception as e:
        return None, f"Error: {str(e)}"

def anime_style_face_swap_gradio(target_image, source_image, anime_denoise=0.45):
    if target_image is None or source_image is None:
        return None, "Please upload both target and source images"
    try:
        # Convert images to bytes
        target_buffer = io.BytesIO()
        source_buffer = io.BytesIO()
        target_image.save(target_buffer, format='PNG')
        source_image.save(source_buffer, format='PNG')
        target_buffer.seek(0)
        source_buffer.seek(0)
        files = {
            "target": ("target.png", target_buffer, "image/png"),
            "source": ("source.png", source_buffer, "image/png")
        }
        data = {
            "anime_denoise": float(anime_denoise),
        }

        response = requests.post(f"{API_BASE_URL}/anime-style-face-swap/", files=files, data=data)
        response.raise_for_status()
        result_path = response.json()['image']
        # The API returns a path like /results/xxx.png
        if result_path.startswith("/results/"):
            result_url = f"{API_BASE_URL}{result_path}"
        else:
            result_url = result_path
        result_image = requests.get(result_url)
        result_image.raise_for_status()
        return Image.open(io.BytesIO(result_image.content)), "Anime Style + Face Swap Successful!"
    except Exception as e:
        return None, f"Error: {str(e)}"

def face_swap_single(target_image, source_image):
    """Face swap function"""
    if target_image is None or source_image is None:
        return None, "Please upload both target and source images"
    if not target_filename:
        target_filename = ""

    try:
        # Save the images in PNG format
        target_buffer = io.BytesIO()
        source_buffer = io.BytesIO()
        target_image.save(target_buffer, format='PNG')
        source_image.save(source_buffer, format='PNG')
        target_buffer.seek(0)
        source_buffer.seek(0)

        # Prepare file upload
        ext = ".png"
        media_type = "image/png"
        base_name = os.path.splitext(target_filename or "target")[0]
        target_upload_name = base_name + ext
        
        files = {
            "target": (target_upload_name, target_buffer, media_type),
            "source": ("source.png", source_buffer, "image/png")
        }
        
        # Call API
        response = requests.post(
            f"{API_BASE_URL}/face-swap-single/",
            files=files
        )
        response.raise_for_status()
        
        # Get the result image URL from the response
        result_path = response.json()['image']
        result_image = requests.get(f"{API_BASE_URL}/{result_path}")
        result_image.raise_for_status()
        
        # Convert response content to PIL Image
        return Image.open(io.BytesIO(result_image.content)), "Face Swap is Successful!"
    except Exception as e:
        return None, f"Error: {str(e)}"


def multi_faceswap(target_image, source_image, denoise=0.55, total_face=1):
    if target_image is None or source_image is None:
        return None, "Please upload both target and source images"
    try:
        # Convert images to bytes
        target_buffer = io.BytesIO()
        source_buffer = io.BytesIO()
        target_image.save(target_buffer, format='PNG')
        source_image.save(source_buffer, format='PNG')
        target_buffer.seek(0)
        source_buffer.seek(0)

        files = {
            "target": ("target.png", target_buffer, "image/png"),
            "source": ("source.png", source_buffer, "image/png")
        }
        data = {
            "denoise": float(denoise),
            "total_face": int(total_face)
        }

        response = requests.post(f"{API_BASE_URL}/multi-face-swap/", files=files, data=data)
        response.raise_for_status()

        result_path = response.json()['image']
        # The API may return a path like /results/xxx.png
        if isinstance(result_path, str) and result_path.startswith("/results/"):
            result_url = f"{API_BASE_URL}{result_path}"
        else:
            result_url = result_path

        result_image = requests.get(result_url)
        result_image.raise_for_status()
        return Image.open(io.BytesIO(result_image.content)), "Multi FaceSwap Successful!"
    except Exception as e:
        return None, f"Error: {str(e)}"

# Create the Gradio interface
with gr.Blocks(title="Image Processing App", theme=gr.themes.Soft()) as app:
    gr.Markdown("<div style='text-align: center; padding: 20px 0;'><span style='font-size: 36px; font-weight: bold;'>Toyota x Giass</span></div>")
    
    with gr.Tab("Remove_Background"):
        with gr.Row():
            with gr.Column():
                remove_bg_input = gr.Image(type="pil", label="Upload Image")
                remove_bg_btn = gr.Button("Remove Background", variant="primary")
            
            with gr.Column():
                remove_bg_output = gr.Image(type="pil", label="Result")
                remove_bg_message = gr.Textbox(label="Status", interactive=False)
        
        remove_bg_btn.click(
            fn=remove_bg,
            inputs=[remove_bg_input],
            outputs=[remove_bg_output, remove_bg_message]
        )

    with gr.Tab("Background Replacement"):
        with gr.Row():
            with gr.Column():
                input_file = gr.File(label="Upload Image File", file_types=["image"])
                with gr.Row():
                    prompt_options = get_prompt_options()
                    p_prompt_dropdown = gr.Dropdown(
                        choices=prompt_options,
                        label="Background Prompt",
                        value=prompt_options[0] if prompt_options else None
                    )
                    refresh_btn = gr.Button("🔄 Refresh", size="sm")
                    n_prompt = gr.Textbox(label="Negative Prompt", placeholder="Elements to avoid...")
                random_seed = gr.Checkbox(label="Use Random Seed")
                replace_btn = gr.Button("Replace Background", variant="primary")
            
            with gr.Column():
                output_image = gr.Image(type="pil", label="Result")
                output_message = gr.Textbox(label="Status", interactive=False)
        
        # Update image preview when file is uploaded
        def update_preview(file):
            if file is None:
                return None
            return Image.open(file.name)
        
        input_file.change(
            fn=update_preview,
            inputs=[input_file],
            outputs=[output_image]
        )
        
        # Refresh prompts
        refresh_btn.click(
            fn=refresh_prompts,
            inputs=[],
            outputs=[p_prompt_dropdown]
        )
        
        replace_btn.click(
            fn=replace_background,
            inputs=[input_file, p_prompt_dropdown, n_prompt, random_seed],
            outputs=[output_image, output_message]
        )
    
    with gr.Tab("Anime Style"):
        with gr.Row():
            with gr.Column():
                anime_input_image = gr.Image(type="pil", label="Upload Image")
                anime_denoise_slider = gr.Slider(minimum=0.0, maximum=1.0, value=0.45, label="Anime Style Strength")
                anime_process_btn = gr.Button("Process Image", variant="primary")
            with gr.Column():
                anime_output = gr.Image(type="pil", label="Result")
                anime_message = gr.Textbox(label="Status", interactive=False)
        anime_process_btn.click(
            fn=style_anime,
            inputs=[anime_input_image, anime_denoise_slider],
            outputs=[anime_output, anime_message]
        )

    with gr.Tab("Face Swap"):
        with gr.Row():
            with gr.Column():
                target_file = gr.Image(label="Upload Target Image", type="pil")
                face_source_file = gr.Image(label="Upload Source Image", type="pil")    
                process_btn = gr.Button("Process Image", variant="primary")
            with gr.Column():
                face_output = gr.Image(type="pil", label="Result")
                face_message = gr.Textbox(label="Status", interactive=False)
        
        # Map template type to filename
        def get_template_filename(template_type):
            mapping = {
                "Aries": "TEMPLATE ARIES.png",
                "Grey": "TEMPLATE GREY.png",
                "Aghny": "TEMPLATE AGHNY.png",
                "Red": "TEMPLATE RED.png"
            }
            return mapping.get(template_type, "TEMPLATE RED.png")
        
        process_btn.click(
            fn=lambda target_img, source_img, template_type: face_swap(
                target_img, source_img, "", get_template_filename(template_type), 0.65, 0.65),
            inputs=[target_file, face_source_file],
            outputs=[face_output, face_message]
        )

    with gr.Tab("Anime Style + Face Swap"):
        with gr.Row():
            with gr.Column():
                asfs_target = gr.Image(type="pil", label="Upload Target Image")
                asfs_source = gr.Image(type="pil", label="Upload Source Image")
                asfs_anime_denoise = gr.Slider(minimum=0.0, maximum=1.0, value=0.45, label="Anime-Style Strenght")
                asfs_btn = gr.Button("Process Anime Style", variant="primary")
            with gr.Column():
                asfs_output = gr.Image(type="pil", label="Result")
                asfs_message = gr.Textbox(label="Status", interactive=False)
        asfs_btn.click(
            fn=anime_style_face_swap_gradio,
            inputs=[asfs_target, asfs_source, asfs_anime_denoise],
            outputs=[asfs_output, asfs_message]
        )

    with gr.Tab("FaceSwap Single"):
        with gr.Row():
            with gr.Column():
                asfs_target = gr.Image(type="pil", label="Upload Target Image")
                asfs_source = gr.Image(type="pil", label="Upload Source Image")
                asfs_btn = gr.Button("Process Anime Style", variant="primary")
            with gr.Column():
                asfs_output = gr.Image(type="pil", label="Result")
                asfs_message = gr.Textbox(label="Status", interactive=False)
        asfs_btn.click(
            fn=face_swap_single,
            inputs=[asfs_target, asfs_source],
            outputs=[asfs_output, asfs_message]
        )

    with gr.Tab("Multi FaceSwap"):
        with gr.Row():
            with gr.Column():
                asfs_target = gr.Image(type="pil", label="Upload Target Image")
                asfs_source = gr.Image(type="pil", label="Upload Source Image")
                asfs_multi_faceswap_denoise = gr.Slider(minimum=0.0, maximum=1.0, value=0.55, label="Multi-FaceSwap Strenght")
                asfs_total_face=gr.Slider(minimum=1, maximum=10, value=1, label="Total Face to be swapped")
                asfs_btn = gr.Button("Process Multi FaceSwap", variant="primary")
            with gr.Column():
                asfs_output = gr.Image(type="pil", label="Result")
                asfs_message = gr.Textbox(label="Status", interactive=False)
        asfs_btn.click(
            fn=multi_faceswap,
            inputs=[asfs_target, asfs_source, asfs_multi_faceswap_denoise,asfs_total_face],
            outputs=[asfs_output, asfs_message]
        )

if __name__ == "__main__":
    app.launch()
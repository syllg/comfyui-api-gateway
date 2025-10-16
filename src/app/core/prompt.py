import json
import os
from typing import Dict

def add_prompt_list(list_prompt_path: str, new_list_prompt: dict) -> dict:
    """
    Add new prompts to the existing prompt list.
    
    Args:
        list_prompt_path (str): The path to the list prompt file
        new_list_prompt (dict): The new prompts to be added

    Returns:
        dict: The updated list prompt
    """
    # Check if file exists, create if it doesn't
    if not os.path.exists(list_prompt_path):
        current_list_prompt = {}
    else:
        try:
            with open(list_prompt_path, 'r') as f:
                current_list_prompt = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            current_list_prompt = {}
    
    # Merge new prompts with existing ones
    current_list_prompt.update(new_list_prompt)
    
    # Write back to file
    try:
        with open(list_prompt_path, 'w') as f:
            json.dump(current_list_prompt, f, indent=4)
    except Exception as e:
        raise Exception(f"Failed to write to prompt file: {str(e)}")

    return current_list_prompt

def get_prompt_list(list_prompt_path: str) -> dict:
    """
    Get the current list of prompts from the file.
    
    Args:
        list_prompt_path (str): The path to the list prompt file
        
    Returns:
        dict: The current list of prompts
    """
    if not os.path.exists(list_prompt_path):
        return {}
    
    try:
        with open(list_prompt_path, "r") as f:
            prompt = json.load(f)
        return prompt
    except (json.JSONDecodeError, FileNotFoundError) as e:
        raise Exception(f"Failed to read prompt file: {str(e)}")

def delete_prompt_list(list_prompt_path: str, prompt_keys: list) -> dict:
    """
    Delete specific prompts from the prompt list.
    
    Args:
        list_prompt_path (str): The path to the list prompt file
        prompt_keys (list): List of prompt keys to delete
        
    Returns:
        dict: The updated list prompt
    """
    if not os.path.exists(list_prompt_path):
        return {}
    
    try:
        with open(list_prompt_path, 'r') as f:
            current_list_prompt = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    
    # Remove specified prompts
    for key in prompt_keys:
        current_list_prompt.pop(key, None)
    
    # Write back to file
    try:
        with open(list_prompt_path, 'w') as f:
            json.dump(current_list_prompt, f, indent=4)
    except Exception as e:
        raise Exception(f"Failed to write to prompt file: {str(e)}")

    return current_list_prompt

def validate_prompt_format(prompt_dict: dict) -> bool:
    """
    Validate that the prompt dictionary has the correct format.
    Each value must be a dict with non-empty 'prompt' and 'image_filename' fields.
    """
    if not isinstance(prompt_dict, dict):
        return False
    for key, value in prompt_dict.items():
        if not isinstance(key, str) or not key.strip():
            return False
        if not isinstance(value, dict):
            return False
        if not value.get('prompt') or not isinstance(value['prompt'], str) or not value['prompt'].strip():
            return False
        if not value.get('image_filename') or not isinstance(value['image_filename'], str) or not value['image_filename'].strip():
            return False
    return True


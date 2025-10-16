import json
import os
from typing import Dict, Optional
from datetime import datetime

def get_anime_list(anime_template_path: str) -> dict:
    """
    Get the current list of anime templates from the file.
    
    Args:
        anime_template_path (str): The path to the anime template file
        
    Returns:
        dict: The current list of anime templates
    """
    if not os.path.exists(anime_template_path):
        return {}
    
    try:
        with open(anime_template_path, "r") as f:
            templates = json.load(f)
        return templates
    except (json.JSONDecodeError, FileNotFoundError) as e:
        raise Exception(f"Failed to read anime template file: {str(e)}")

def add_anime_list(anime_template_path: str, new_anime_list: dict) -> dict:
    """
    Add new anime templates to the existing template list.
    
    Args:
        anime_template_path (str): The path to the anime template file
        new_anime_list (dict): The new templates to be added

    Returns:
        dict: The updated anime template list
    """
    # Check if file exists, create if it doesn't
    if not os.path.exists(anime_template_path):
        current_anime_list = {}
    else:
        try:
            with open(anime_template_path, 'r') as f:
                current_anime_list = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            current_anime_list = {}
    
    # Merge new templates with existing ones
    current_anime_list.update(new_anime_list)
    
    # Write back to file
    try:
        with open(anime_template_path, 'w') as f:
            json.dump(current_anime_list, f, indent=4)
    except Exception as e:
        raise Exception(f"Failed to write to anime template file: {str(e)}")

    return current_anime_list

def delete_anime_list(anime_template_path: str, anime_keys: list) -> dict:
    """
    Delete specific templates from the anime template list.
    
    Args:
        anime_template_path (str): The path to the anime template file
        anime_keys (list): List of template keys to delete
        
    Returns:
        dict: The updated anime template list
    """
    if not os.path.exists(anime_template_path):
        return {}
    
    try:
        with open(anime_template_path, 'r') as f:
            current_anime_list = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    
    # Remove specified templates
    for key in anime_keys:
        current_anime_list.pop(key, None)
    
    # Write back to file
    try:
        with open(anime_template_path, 'w') as f:
            json.dump(current_anime_list, f, indent=4)
    except Exception as e:
        raise Exception(f"Failed to write to anime template file: {str(e)}")

    return current_anime_list

def validate_anime_format(anime_dict: dict) -> bool:
    """
    Validate that the anime dictionary has the correct format.
    Each value must be a dict with non-empty 'image_filename' field.
    """
    if not isinstance(anime_dict, dict):
        return False
    for key, value in anime_dict.items():
        if not isinstance(key, str) or not key.strip():
            return False
        if not isinstance(value, dict):
            return False
        if not value.get('image_filename') or not isinstance(value['image_filename'], str) or not value['image_filename'].strip():
            return False
    return True 

class WorkflowCache:
    """A class to manage workflow caching for ComfyUI."""
    
    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._last_modified: Dict[str, float] = {}
    
    def get_workflow(self, workflow_path: str) -> Optional[dict]:
        """
        Get a workflow from cache or load it from file if needed.
        
        Args:
            workflow_path: Path to the workflow JSON file
            
        Returns:
            dict: The workflow configuration
        """
        if not os.path.exists(workflow_path):
            raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
            
        # Check if file has been modified
        current_mtime = os.path.getmtime(workflow_path)
        cached_mtime = self._last_modified.get(workflow_path)
        
        # If file is not in cache or has been modified, reload it
        if (workflow_path not in self._cache or 
            cached_mtime is None or 
            current_mtime > cached_mtime):
            try:
                with open(workflow_path, "r", encoding="utf-8") as f:
                    workflow = json.load(f)
                self._cache[workflow_path] = workflow
                self._last_modified[workflow_path] = current_mtime
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid workflow file format: {str(e)}")
            except Exception as e:
                raise Exception(f"Failed to read workflow file: {str(e)}")
        
        return self._cache[workflow_path]
    
    def clear_cache(self):
        """Clear the entire workflow cache."""
        self._cache.clear()
        self._last_modified.clear()
    
    def remove_workflow(self, workflow_path: str):
        """Remove a specific workflow from the cache."""
        self._cache.pop(workflow_path, None)
        self._last_modified.pop(workflow_path, None)

# Create a global instance of the workflow cache
workflow_cache = WorkflowCache() 
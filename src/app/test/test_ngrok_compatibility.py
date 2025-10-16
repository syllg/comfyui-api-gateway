#!/usr/bin/env python3
"""
Test script to verify ngrok compatibility with the ComfyUI API client
"""

import os
import sys
import requests
import json
from dotenv import load_dotenv
from pathlib import Path
from src.app.api.websockets_api import test_connection
from src.app.api.websockets_api import test_connection, get_protocol

# Add the src directory to the path
sys.path.append(str(Path(__file__).parent / "src"))

load_dotenv()
SERVER_ADDRESS = os.getenv("SERVER_ADDRESS")
def test_ngrok_setup():
    """Test the ngrok setup with the provided SERVER_ADDRESS"""
    
    test_server_address = SERVER_ADDRESS
    
    print(f"Testing ngrok compatibility with: {test_server_address}")
    print("=" * 60)
    print("NOTE: This test is checking connectivity to the ComfyUI server (port 8188)")
    print("      The API client endpoints are on a different port (8000)")
    print("=" * 60)
    
    print("1. Testing protocol detection...")
    try:
        http_protocol, ws_protocol = get_protocol()
        print(f"   HTTP Protocol: {http_protocol}")
        print(f"   WebSocket Protocol: {ws_protocol}")
        print(f"   ✓ Protocol detection working correctly")
    except Exception as e:
        print(f"   ✗ Protocol detection failed: {e}")
        return False
    
    print("\n2. Testing basic connection...")
    try:
        
        if test_connection():
            print("   ✓ Basic connection successful")
        else:
            print("   ✗ Basic connection failed")
            return False
    except Exception as e:
        print(f"   ✗ Connection test error: {e}")
        return False
    
    # Test API endpoints
    print("\n3. Testing ComfyUI server endpoints...")
    try:
        # Test the root endpoint - use the full URL directly since it already contains protocol
        response = requests.get(f"{test_server_address}/", timeout=10)
        print(f"   Response status: {response.status_code}")
        print(f"   Response content type: {response.headers.get('content-type', 'unknown')}")
        
        if response.status_code == 200:
            print("   ✓ ComfyUI server accessible")
            
            # Try to parse as JSON, but handle non-JSON responses gracefully
            try:
                data = response.json()
                print(f"   API Name: {data.get('name', 'Unknown')}")
                print(f"   API Version: {data.get('version', 'Unknown')}")
            except json.JSONDecodeError:
                # If it's not JSON, it might be HTML or plain text
                content_preview = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"   ⚠ Response is HTML (ComfyUI web interface): {content_preview}")
                print("   ✓ ComfyUI web interface is accessible")
        else:
            print(f"   ✗ ComfyUI server failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ ComfyUI server test failed: {e}")
        return False
    
    # Test list-prompt endpoint (this won't exist on ComfyUI server)
    print("\n4. Testing custom API endpoints...")
    try:
        response = requests.get(f"{test_server_address}/list-prompt/", timeout=10)
        print(f"   Response status: {response.status_code}")
        print(f"   Response content type: {response.headers.get('content-type', 'unknown')}")
        
        if response.status_code == 200:
            print("   ✓ Custom API endpoint accessible")
            try:
                data = response.json()
                if data.get("status") == "success":
                    print("   ✓ Prompt list retrieved successfully")
                    prompts = data.get("list_prompt", {})
                    print(f"   Available prompts: {len(prompts)}")
                else:
                    print("   ⚠ Prompt list status not successful")
            except json.JSONDecodeError:
                content_preview = response.text[:200] + "..." if len(response.text) > 200 else response.text
                print(f"   ⚠ Response is not JSON: {content_preview}")
                print("   ✓ Endpoint is accessible (non-JSON response)")
        else:
            print(f"   ⚠ Custom API endpoint not found (404) - This is expected!")
            print("   ℹ️  This endpoint is part of our API client, not the ComfyUI server")
    except Exception as e:
        print(f"   ✗ Custom API test failed: {e}")
    
    print("\n" + "=" * 60)
    print("✓ Ngrok compatibility test completed successfully!")
    print("\nThe ngrok tunnel is working correctly with your ComfyUI server.")
    print("\nTo use this setup with your API client:")
    print("1. Set SERVER_ADDRESS=https://5e82-110-137-51-252.ngrok-free.app")
    print("2. Set API_BASE_URL=https://5e82-110-137-51-252.ngrok-free.app")
    print("3. Run your API client: python -m src.app.api.api")
    print("4. Access your API client at: http://localhost:8000")
    print("5. The API client will communicate with ComfyUI via the ngrok tunnel")
    
    return True

if __name__ == "__main__":
    test_ngrok_setup() 
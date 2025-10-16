#!/usr/bin/env python3
"""
Test script to verify URL construction fixes
"""

import os
import sys
import src.app.api.websockets_api as ws_api
from src.app.api.websockets_api import build_url, build_ws_url, test_connection
sys.path.append('src')


def test_url_construction():
    """Test URL construction with different server address formats"""
    
    # Test cases
    test_cases = [
        "127.0.0.1:8188",
        "localhost:8188", 
        "https://5e82-110-137-51-252.ngrok-free.app",
        "http://localhost:8188",
        "https://example.com:8188"
    ]
    
    print("Testing URL construction...")
    print("=" * 50)
    
    for server_addr in test_cases:
        print(f"\nServer address: {server_addr}")
        
        original_server_address = ws_api.server_address
        ws_api.server_address = server_addr
        
        try:
            # Test HTTP URL
            http_url = build_url("upload/image")
            print(f"  HTTP URL: {http_url}")
            
            # Test WebSocket URL
            ws_url = build_ws_url("ws?clientId=test")
            print(f"  WS URL: {ws_url}")
            
            # Test base URL
            base_url = build_url("")
            print(f"  Base URL: {base_url}")
            
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            # Restore original server address
            ws_api.server_address = original_server_address

if __name__ == "__main__":
    test_url_construction() 
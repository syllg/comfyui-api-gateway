# ComfyUI API Client

A Python client library for interacting with ComfyUI's API, enabling programmatic control and automation of ComfyUI workflows.

## Description

This project provides a robust Python interface to interact with ComfyUI's API, allowing you to:
- Programmatically control ComfyUI workflows
- Automate image generation and processing tasks
- Integrate ComfyUI capabilities into your Python applications
- Manage and monitor ComfyUI workflows through a RESTful API

## Prerequisites

- Python 3.10 or higher
- Conda (recommended) or pip
- ComfyUI instance running (local or remote)

## Environment Setup

### Using Conda (Recommended)
```bash
# Create and activate conda environment
conda create --name comfyui-api-client python=3.10
conda activate comfyui-api-client

# Install dependencies
pip install -r requirements.txt
```

You can install this package using pip:

# Install dependencies
pip install -r requirements.txt
```

## Installation

Install the package in development mode:
```bash
pip install -e .
```

## Quick Start

1. Ensure ComfyUI is running on your system
2. Start the API server:
```bash
make run
```
The server will start on `http://localhost:8000` by default.

3. Start Gradio:
```bash
make Gradio
```

### Key Dependencies
- FastAPI (v0.104.1) - Web framework for building APIs
- Uvicorn (v0.24.0) - ASGI server
- PyTorch - Deep learning framework
- Gradio (≥4.0.0) - UI components
- Pydantic (v2.5.2) - Data validation
- Python-multipart - File upload handling
- Websocket-client - WebSocket support

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- `src/` - Source code directory
- `uploads/` - Directory for uploaded files
- `results/` - Directory for generated results
- `setup.py` - Package installation configuration
- `requirements.txt` - Project dependencies
